import {
  getActiveInspectionForVehicle,
  getPhotosForInspection,
  putInspection,
  putPhoto,
  updateInspection,
} from "@/lib/offline/db";
import { compressImage } from "@/lib/offline/image";
import { sha256Hex } from "@/lib/offline/checksum";
import { missingAngles as diffAngles } from "@/lib/validation/inspection";
import type { LocalInspection, LocalItemAnswer, LocalPhoto } from "@/lib/offline/types";
import type { EtatGeneral, InspectionConclusion, PhotoAngle, PhotoPhase } from "@/lib/api/types";

/**
 * File d'exécution PAR VÉHICULE — protège `getOrCreateDraft` (ci-dessous) contre son propre
 * « lire, puis écrire » : constaté en conditions réelles (e2e `j2-terrain-photos-seules`,
 * backend `UNIQUE(mission_id)` sur `inspection`) que `useInspectionDraft`'s effet de
 * bootstrap peut s'exécuter deux fois quasi simultanément pour le même véhicule (montage en
 * double de React en développement, ou simplement deux montages rapprochés de l'écran de
 * contrôle) — les deux lectures voient alors « aucun brouillon », et les deux créent chacune
 * un nouveau `client_uuid` : deux inspections locales, puis deux `POST /inspections` pour la
 * MÊME mission, la seconde rejetée par la contrainte serveur. Sérialiser les appels sur cette
 * file, avec une relecture DANS la file, garantit que le second appel voit le brouillon que
 * le premier vient de créer plutôt que d'en créer un autre.
 */
const draftCreationQueues = new Map<string, Promise<unknown>>();

/**
 * Récupère le brouillon actif d'un véhicule, ou en crée un nouveau (client_uuid généré
 * localement, décision C). Idempotent même si deux appels concurrents visent le même
 * véhicule (voir `draftCreationQueues` ci-dessus) : le second renvoie le brouillon que le
 * premier vient de créer plutôt que d'en créer un autre.
 */
export async function getOrCreateDraft(
  vehicleId: string,
  missionId: string,
  templateId: string,
): Promise<LocalInspection> {
  const previous = draftCreationQueues.get(vehicleId) ?? Promise.resolve();
  const next = previous.then(async () => {
    // Relecture DANS la file, pas la lecture faite par l'appelant avant d'arriver ici (elle
    // peut dater d'avant l'écriture d'un appel concurrent qui nous précède dans cette même
    // file).
    const existing = await getActiveInspectionForVehicle(vehicleId);
    if (existing) return existing;

    const draft: LocalInspection = {
      client_uuid: crypto.randomUUID(),
      vehicle_id: vehicleId,
      mission_id: missionId,
      template_id: templateId,
      started_at: new Date().toISOString(),
      kilometrage_releve: null,
      etat_general: null,
      conclusion: null,
      commentaire: null,
      items: {},
      server_id: null,
      required_angles: null,
      fields_dirty: false,
      items_dirty: false,
      pending_submit: false,
      submitted_at: null,
      last_sync_error: null,
      missing_items: null,
      missing_angles: null,
      updated_at: new Date().toISOString(),
    };
    await putInspection(draft);
    return draft;
  });
  // La file continue même si cet appel échoue (erreur métier isolée), sinon un rejet
  // bloquerait tous les appels suivants sur ce véhicule indéfiniment.
  draftCreationQueues.set(
    vehicleId,
    next.catch(() => undefined),
  );
  return next;
}

export interface DraftFieldsPatch {
  kilometrage_releve?: number | null;
  etat_general?: EtatGeneral | null;
  commentaire?: string | null;
}

/**
 * Chaque mutation passe par `updateInspection` (mutex par `client_uuid`, `lib/offline/
 * db.ts`) — jamais un `getInspection` + `putInspection` isolé : deux réponses de
 * checklist tapées coup sur coup, ou une réponse tapée pendant qu'un tick de
 * synchronisation écrit le résultat d'un appel réseau précédent, doivent partir d'une
 * lecture fraîche chacune plutôt que s'écraser silencieusement.
 */
export async function updateDraftFields(clientUuid: string, patch: DraftFieldsPatch): Promise<LocalInspection> {
  return updateInspection(clientUuid, (draft) => ({
    ...draft,
    ...patch,
    fields_dirty: true,
    updated_at: new Date().toISOString(),
  }));
}

export async function upsertItemAnswer(
  clientUuid: string,
  answer: LocalItemAnswer,
): Promise<LocalInspection> {
  return updateInspection(clientUuid, (draft) => ({
    ...draft,
    items: { ...draft.items, [answer.item_template_id]: answer },
    items_dirty: true,
    updated_at: new Date().toISOString(),
  }));
}

export async function requestSubmit(
  clientUuid: string,
  conclusion: InspectionConclusion,
): Promise<LocalInspection> {
  return updateInspection(clientUuid, (draft) => ({
    ...draft,
    conclusion,
    pending_submit: true,
    fields_dirty: true,
    last_sync_error: null,
    missing_items: null,
    missing_angles: null,
    updated_at: new Date().toISOString(),
  }));
}

/** Capture, compresse, empreinte et met en file une photo — jamais d'octet perdu même si
 * l'upload n'est jamais tenté dans cette fonction (le rejeu vit dans `sync.ts`). */
export async function enqueuePhoto(
  inspectionClientUuid: string,
  vehicleId: string,
  file: File,
  angle: PhotoAngle,
  phase: PhotoPhase = "controle",
): Promise<LocalPhoto> {
  const compressed = await compressImage(file);
  const checksum = await sha256Hex(compressed.blob);
  const photo: LocalPhoto = {
    client_uuid: crypto.randomUUID(),
    inspection_client_uuid: inspectionClientUuid,
    vehicle_id: vehicleId,
    angle,
    phase,
    blob: compressed.blob,
    content_type: compressed.blob.type || "image/jpeg",
    byte_size: compressed.blob.size,
    width: compressed.width,
    height: compressed.height,
    checksum_sha256: checksum,
    captured_at: new Date().toISOString(),
    upload_state: "queued",
    attempts: 0,
    error: null,
    server_id: null,
    server_url: null,
  };
  await putPhoto(photo);
  return photo;
}

/** Retire une photo **jamais encore envoyée** (statut `queued`/`failed`) — permet de
 * reprendre un angle raté sans attendre un cycle serveur. Une photo `sent` est
 * irréversible côté client : le backend n'expose aucun endpoint de suppression (§ 5.1,
 * pas de `DELETE /photos`), ce n'est pas un oubli.
 *
 * 🟠 Correctif revue § 2 : la garde ne teste plus `photo.upload_state` sur l'objet React
 * passé par l'appelant — l'écran ne se rafraîchit que toutes les 1,5 s
 * (`useInspectionDraft.ts::RELOAD_INTERVAL_MS`), la vignette peut donc encore afficher
 * `queued` alors que l'envoi est déjà en vol côté réseau. `deleteUnsentPhoto` (`db.ts`)
 * relit l'état frais DANS la même transaction que la suppression. */
export async function removeUnsentPhoto(photo: LocalPhoto): Promise<void> {
  const { deleteUnsentPhoto } = await import("@/lib/offline/db");
  const outcome = await deleteUnsentPhoto(photo.client_uuid);
  if (outcome === "already_sent") {
    throw new Error("Cette photo est déjà envoyée ou en cours d'envoi, elle ne peut pas être retirée.");
  }
  // "not_found" : déjà retirée entre-temps (double clic, ou concurrence) — rien à signaler,
  // le résultat souhaité par le chauffeur (« cette photo n'est plus là ») est déjà acquis.
}

export interface AngleProgress {
  /** `null` tant que `GET .../required-angles` n'a jamais réussi pour ce brouillon —
   * distingue « on ne sait pas encore » de « aucun angle manquant ». */
  required: string[] | null;
  captured: string[];
  missing: string[] | null;
}

/** Photos comptées comme « capturées » dès qu'elles existent localement, envoyées ou non
 * — l'utilisateur ne doit pas revoir un angle déjà pris juste parce que l'envoi traîne. */
export async function computeAngleProgress(draft: LocalInspection): Promise<AngleProgress> {
  const photos = await getPhotosForInspection(draft.client_uuid);
  const captured = Array.from(new Set(photos.filter((p) => p.phase === "controle").map((p) => p.angle)));
  const required = draft.required_angles;
  return {
    required,
    captured,
    missing: required ? diffAngles(required, captured) : null,
  };
}
