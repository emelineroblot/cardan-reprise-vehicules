import type { QueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api/client";
import {
  deleteSentPhotosForInspection,
  getAllInspections,
  getAllPhotos,
  getInspection,
  getPhotosForInspection,
  updateInspection,
  updatePhoto,
} from "@/lib/offline/db";
import type { LocalInspection, LocalPhoto } from "@/lib/offline/types";
import type {
  Inspection,
  InspectionIncompleteDetails,
  Photo,
  RequiredAnglesResponse,
} from "@/lib/api/types";

/**
 * Moteur de rejeu (décision C, plan.md § 4) : IndexedDB + rejeu au premier plan, jamais
 * Background Sync API seule (support inégal, absent sur iOS — utilisée en bonus ailleurs
 * si un jour posée, jamais comme unique garantie). Un tick = une tentative de faire
 * avancer TOUS les brouillons locaux d'un cran ; il s'arrête au premier signe réel de
 * coupure réseau plutôt que d'accumuler des échecs sur chaque brouillon.
 */

export type SyncTickStatus = "ok" | "offline" | "idle" | "error";

export interface SyncTickResult {
  status: SyncTickStatus;
  photosSent: number;
  photosFailed: number;
  inspectionsSubmitted: number;
}

function isNetworkError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 0;
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Erreur de synchronisation inconnue.";
}

/**
 * 🟠 Correctif revue finale § n°1 — effet de bord direct du correctif du 🔴 `needsSync` : une
 * photo en échec redevient éligible à chaque tick, ce qui est correct pour un échec
 * TRANSITOIRE (réseau, 5xx passager) mais absurde pour un échec DÉFINITIF, qui renverra
 * indéfiniment exactement le même verdict pour exactement le même octet :
 * - `409 conflict` (« Cet angle a déjà été photographié », `photos.py:107-120`) — l'angle est
 *   déjà pris côté serveur par une autre photo (`sent`), sans endpoint de suppression pour la
 *   libérer (`draft.ts::removeUnsentPhoto`) ; retenter n'y change jamais rien.
 * - `422 validation_error` — format de fichier refusé (ex. HEIC parti sans compression,
 *   `image.ts` § repli) ; le même octet renverra toujours la même erreur de validation.
 */
function isDefinitivePhotoError(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 409 || error.status === 422);
}

/**
 * Plafond de tentatives automatiques pour tout AUTRE échec (401 de session expirée, 413,
 * 500 passager…) : sans ce filet, un échec non classifié en définitif mais qui ne se résorbe
 * jamais réellement (ex. panne prolongée du stockage serveur) rejouerait le même envoi toutes
 * les 20 s pour toujours, exactement le symptôme que ce correctif élimine. Volontairement
 * généreux (~1,5 min de tentatives au rythme du minuteur de fond) : assez pour couvrir une
 * panne réseau/serveur passagère réaliste, sans laisser le chauffeur face à un envoi qui
 * boucle indéfiniment sur du 3G facturé au volume.
 */
export const MAX_UPLOAD_ATTEMPTS = 5;

let tickInFlight: Promise<SyncTickResult> | null = null;
let rerunRequested = false;

/**
 * Point d'entrée public — sérialise les appels concurrents (bouton « Réessayer » +
 * minuteur + évènement `online` déclenchés en même temps) sur un seul tick réel.
 *
 * Un appel qui arrive PENDANT un tick déjà en cours ne déclenche pas un second tick
 * immédiat : il se contente de rendre la même promesse. Sans le `rerunRequested`
 * ci-dessous, un état posé juste après le début de ce tick (ex. `pending_submit` mis à
 * `true` par un clic de soumission pendant qu'un tick de fond est déjà en train d'envoyer
 * les dernières photos) ne serait vu qu'au *prochain* déclenchement — potentiellement
 * jusqu'au minuteur de fond (20 s). `rerunRequested` programme un tick de RATTRAPAGE
 * immédiat dès que le tick en cours se termine, sans attendre ce minuteur.
 */
export function triggerSync(queryClient?: QueryClient): Promise<SyncTickResult> {
  if (tickInFlight) {
    rerunRequested = true;
    return tickInFlight;
  }
  tickInFlight = runSyncTick(queryClient).finally(() => {
    tickInFlight = null;
    if (rerunRequested) {
      rerunRequested = false;
      void triggerSync(queryClient);
    }
  });
  return tickInFlight;
}

async function runSyncTick(queryClient?: QueryClient): Promise<SyncTickResult> {
  const result: SyncTickResult = { status: "idle", photosSent: 0, photosFailed: 0, inspectionsSubmitted: 0 };

  let inspections: LocalInspection[];
  let photos: LocalPhoto[];
  try {
    [inspections, photos] = await Promise.all([getAllInspections(), getAllPhotos()]);
  } catch {
    // IndexedDB indisponible (mode privé strict) : rien à synchroniser, ce n'est pas une
    // erreur réseau — cf. lib/offline/db.ts.
    return { ...result, status: "idle" };
  }

  // 🔴 Correctif bloquant (revue J2 § 1) : `needsSync` ne regardait QUE l'état du brouillon
  // (`fields_dirty`/`items_dirty`/`pending_submit`) — rien dans le cycle de vie d'une photo
  // (`draft.ts::enqueuePhoto`) ne posait l'un de ces drapeaux. Un brouillon déjà synchronisé
  // auquel on ajoute des photos hors ligne n'était donc plus JAMAIS repris : ni par
  // l'évènement `online`, ni par le minuteur de 20 s, ni par le bouton « Réessayer ». Même
  // chose pour une photo passée en `failed` (401/413/500 passager) — le bandeau annonçait
  // « nouvelle tentative en cours » sans qu'aucune tentative n'ait jamais lieu. Le coût de
  // `getAllPhotos()` est nul : `useOfflineSyncEngine` le fait déjà toutes les 3 s pour le
  // résumé affiché dans le bandeau.
  // `"failed"` ici est un échec TRANSITOIRE, encore retenté (voir `uploadOnePhoto`) —
  // volontairement exclusif de `"failed_permanent"` : un échec définitif (409/422, ou un
  // échec quelconque au-delà de `MAX_UPLOAD_ATTEMPTS`) ne doit plus jamais rendre un
  // brouillon éligible de ce seul fait, sans quoi il retomberait dans le même piège que le
  // bloquant ci-dessus — un tick qui tourne pour toujours sans jamais rien accomplir (revue
  // finale § 🟠 n°1).
  const inspectionIdsWithPendingPhotos = new Set(
    photos
      .filter((p) => p.upload_state === "queued" || p.upload_state === "failed")
      .map((p) => p.inspection_client_uuid),
  );

  const pending = inspections.filter((i) => needsSync(i, inspectionIdsWithPendingPhotos));
  if (pending.length === 0) return { ...result, status: "idle" };

  result.status = "ok";

  for (const draft of pending) {
    try {
      const synced = await syncOneInspection(draft, result, queryClient);
      if (synced === "offline") {
        result.status = "offline";
        break;
      }
    } catch (error) {
      // Erreur inattendue (bug, pas un cas métier prévu) : ne PAS l'avaler — elle
      // remonte dans la console pour rester visible, le tick continue sur les autres
      // brouillons plutôt que de tout bloquer sur un seul (garde-fou anti-régression J1 :
      // « ne confiner que les erreurs métier attendues »).
      console.error("Erreur inattendue pendant la synchronisation d'un brouillon d'inspection.", error);
      result.status = result.status === "offline" ? "offline" : "error";
    }
  }

  return result;
}

function needsSync(draft: LocalInspection, inspectionIdsWithPendingPhotos: Set<string>): boolean {
  if (!draft.server_id) return true;
  if (draft.fields_dirty || draft.items_dirty || draft.pending_submit) return true;
  if (inspectionIdsWithPendingPhotos.has(draft.client_uuid)) return true;
  return false;
}

async function syncOneInspection(
  draftIn: LocalInspection,
  result: SyncTickResult,
  queryClient?: QueryClient,
): Promise<"ok" | "offline"> {
  let draft = draftIn;

  // 1. Créer l'inspection côté serveur si nécessaire (idempotent par client_uuid).
  if (!draft.server_id) {
    try {
      const created = await api.post<Inspection>("/inspections", {
        client_uuid: draft.client_uuid,
        vehicle_id: draft.vehicle_id,
        template_id: draft.template_id,
      });
      draft = await updateInspection(draft.client_uuid, (current) => ({
        ...current,
        server_id: created.id,
        last_sync_error: null,
      }));
      queryClient?.invalidateQueries({ queryKey: ["missions", draft.mission_id] });
    } catch (error) {
      if (isNetworkError(error)) return "offline";
      await updateInspection(draft.client_uuid, (current) => ({
        ...current,
        last_sync_error: errorMessage(error),
      }));
      return "ok"; // erreur métier (409 inspection_not_allowed…) : pas la peine d'insister ce tick-ci.
    }
  }

  const inspectionId = draft.server_id;
  if (!inspectionId) return "ok";

  // 2. Champs de synthèse (kilométrage, état général, commentaire). Relus JUSTE AVANT
  // l'envoi (pas `draft`, capturé au tout début du tick — potentiellement périmé si une
  // saisie locale a eu lieu entre-temps, l'appel réseau qui précède prenant un temps réel)
  // et `fields_dirty` n'est effacé QUE si rien n'a changé depuis cette lecture, sinon un
  // champ modifié pendant l'envoi serait marqué synchronisé sans jamais avoir été transmis
  // — perte silencieuse constatée en conditions réelles sur `items` (voir étape 3), même
  // schéma de course appliqué ici par précaution symétrique.
  if (draft.fields_dirty) {
    const latestForFields = (await getInspection(draft.client_uuid)) ?? draft;
    try {
      await api.patch(`/inspections/${inspectionId}`, {
        kilometrage_releve: latestForFields.kilometrage_releve,
        etat_general: latestForFields.etat_general,
        commentaire: latestForFields.commentaire,
      });
      draft = await updateInspection(draft.client_uuid, (current) => ({
        ...current,
        fields_dirty:
          current.kilometrage_releve === latestForFields.kilometrage_releve &&
          current.etat_general === latestForFields.etat_general &&
          current.commentaire === latestForFields.commentaire
            ? false
            : current.fields_dirty,
        last_sync_error: null,
      }));
    } catch (error) {
      if (isNetworkError(error)) return "offline";
      draft = await updateInspection(draft.client_uuid, (current) => ({
        ...current,
        last_sync_error: errorMessage(error),
      }));
    }
  }

  // 3. Réponses de checklist — réémission complète, upsert idempotent côté serveur.
  // 🔴 Correctif : envoyer `draft.items` (capturé au début du tick) a fait perdre des
  // réponses saisies APRÈS ce point mais AVANT l'envoi réseau — `items_dirty` était
  // ensuite effacé, donc plus jamais retenté, alors que le serveur n'avait reçu qu'une
  // version incomplète (observé : 2 réponses sur 11 manquantes à la soumission, alors que
  // le brouillon local les avait bien). Relecture juste avant l'envoi, `items_dirty`
  // effacé seulement si rien n'a changé depuis cette lecture (comparaison de contenu).
  if (draft.items_dirty) {
    const latestForItems = (await getInspection(draft.client_uuid)) ?? draft;
    const itemsToSend = latestForItems.items;
    try {
      await api.put(`/inspections/${inspectionId}/items`, {
        items: Object.values(itemsToSend),
      });
      draft = await updateInspection(draft.client_uuid, (current) => ({
        ...current,
        items_dirty: JSON.stringify(current.items) === JSON.stringify(itemsToSend) ? false : current.items_dirty,
        last_sync_error: null,
      }));
    } catch (error) {
      if (isNetworkError(error)) return "offline";
      draft = await updateInspection(draft.client_uuid, (current) => ({
        ...current,
        last_sync_error: errorMessage(error),
      }));
    }
  }

  // 4. Angles requis — rafraîchi à chaque tick en ligne pour garder la progression
  // exacte (décision C : le front dérive, ne recopie jamais la règle métier).
  try {
    const angles = await api.get<RequiredAnglesResponse>(
      `/vehicles/${draft.vehicle_id}/photos/required-angles?inspection_id=${inspectionId}`,
    );
    draft = await updateInspection(draft.client_uuid, (current) => ({
      ...current,
      required_angles: angles.required_angles,
    }));
  } catch (error) {
    if (isNetworkError(error)) return "offline";
    // Erreur métier sur cet appel de confort (ex. véhicule hors scope) : la progression
    // locale continue de s'appuyer sur la dernière valeur connue, sans bloquer le tick.
  }

  // 5. Photos en file — jamais tentées avant que l'inspection n'ait un id serveur. Liste
  // figée en tête de boucle (une photo capturée PENDANT cette boucle, rafale de captures,
  // n'est pas tentée dans CE tick) : comportement volontairement conservé — le correctif du
  // bloquant ci-dessus (§ étape ci-dessus) garantit qu'un tick ULTÉRIEUR la rattrapera, sans
  // avoir besoin de rouvrir la liste à chaque itération (revue § 3).
  const photos = await getPhotosForInspection(draft.client_uuid);
  for (const photo of photos) {
    if (photo.upload_state !== "queued" && photo.upload_state !== "failed") continue;
    const outcome = await uploadOnePhoto(photo, inspectionId);
    if (outcome === "offline") return "offline";
    if (outcome === "sent") result.photosSent += 1;
    else if (outcome === "failed") result.photosFailed += 1;
    // "skipped" : la photo a été supprimée par le chauffeur (« Reprendre l'angle ») pendant
    // que cet envoi était en vol (revue § 2) — ni un succès ni un échec, rien à compter.
  }

  // 6. Soumission — relecture fraîche AVANT même de tester `pending_submit` : la valeur
  // capturée au début du tick (`draft`) peut dater d'avant un clic de soumission survenu
  // PENDANT que ce tick envoyait les dernières photos (rendu possible par le rattrapage de
  // `triggerSync`, voir son commentaire). Se fier à `draft.pending_submit` ici retarderait
  // la soumission d'un tick entier alors que tout est déjà prêt. Idem pour `photos` : les
  // entrées de la boucle d'upload ci-dessus ne sont pas mutées en place par
  // `uploadOnePhoto`, donc `stillPendingPhotos` doit relire l'état réel, pas ce tableau.
  //
  // 🟠 Correctif revue finale § n°1 : `stillPendingPhotos` ne teste QUE `"queued"`/
  // `"uploading"`/`"failed"` (transitoire) — jamais `"failed_permanent"`. Avant ce correctif,
  // une photo en échec définitif (409/422, cf. `isDefinitivePhotoError`) gelait
  // `pending_submit` à `true` pour toujours : le contrôle ne pouvait plus jamais être soumis
  // depuis cet appareil. Désormais la soumission est tentée quand même ; si la photo en échec
  // couvrait un angle obligatoire, le serveur le dit explicitement (`409
  // inspection_incomplete`, `missing_angles`, capturé plus bas) — un message actionnable
  // plutôt qu'un blocage silencieux.
  const freshDraft = await getInspection(draft.client_uuid);
  if (freshDraft?.pending_submit) {
    const freshPhotos = await getPhotosForInspection(draft.client_uuid);
    const stillPendingPhotos = freshPhotos.some(
      (p) => p.upload_state === "queued" || p.upload_state === "uploading" || p.upload_state === "failed",
    );
    if (freshDraft.fields_dirty || freshDraft.items_dirty || stillPendingPhotos) {
      return "ok"; // pas encore prêt à soumettre, retenté au prochain tick.
    }
    draft = freshDraft;
    try {
      const submitted = await api.post<Inspection>(`/inspections/${inspectionId}/submit`, {
        kilometrage_releve: draft.kilometrage_releve,
        etat_general: draft.etat_general,
        conclusion: draft.conclusion,
        commentaire: draft.commentaire,
      });
      draft = await updateInspection(draft.client_uuid, (current) => ({
        ...current,
        submitted_at: submitted.submitted_at,
        pending_submit: false,
        last_sync_error: null,
        missing_items: null,
        missing_angles: null,
      }));
      result.inspectionsSubmitted += 1;
      queryClient?.invalidateQueries({ queryKey: ["vehicles", draft.vehicle_id] });
      queryClient?.invalidateQueries({ queryKey: ["missions"] });
      // Purge locale (revue J2 § 6) : une fois la soumission confirmée côté serveur, les
      // photos déjà `sent` de ce brouillon n'ont plus aucune raison d'occuper le quota
      // IndexedDB — aucun endpoint de suppression ne les rendrait de toute façon modifiables
      // (`draft.ts::removeUnsentPhoto`), et le récapitulatif ne réaffiche plus la grille.
      // Best-effort : un échec de purge ne doit jamais faire échouer une soumission déjà
      // réussie.
      await deleteSentPhotosForInspection(draft.client_uuid).catch(() => undefined);
    } catch (error) {
      if (isNetworkError(error)) return "offline";
      if (error instanceof ApiError && error.code === "inspection_incomplete") {
        const details = (error.details ?? {}) as Partial<InspectionIncompleteDetails>;
        draft = await updateInspection(draft.client_uuid, (current) => ({
          ...current,
          pending_submit: false,
          missing_items: details.missing_items ?? [],
          missing_angles: details.missing_angles ?? [],
          last_sync_error: error.message,
        }));
      } else {
        draft = await updateInspection(draft.client_uuid, (current) => ({
          ...current,
          last_sync_error: errorMessage(error),
        }));
      }
    }
  }

  return "ok";
}

/**
 * 🟠 Correctif revue § 2 (dernière occurrence de la famille « lire avant `await` réseau,
 * écrire un instantané périmé après ») : chaque écriture passe par `updatePhoto`, qui relit
 * l'état frais DANS sa propre transaction juste avant d'écrire (`lib/offline/db.ts`). Si le
 * chauffeur a supprimé la photo pendant que l'upload était en vol (« Reprendre l'angle »),
 * `updatePhoto` renvoie `undefined` — l'écriture finale ne la ressuscite jamais.
 */
async function uploadOnePhoto(
  photo: LocalPhoto,
  inspectionId: string,
): Promise<"sent" | "failed" | "offline" | "skipped"> {
  const uploading = await updatePhoto(photo.client_uuid, (current) => ({ ...current, upload_state: "uploading" }));
  if (!uploading) return "skipped"; // déjà supprimée avant même de tenter l'envoi.

  const formData = new FormData();
  formData.append("file", uploading.blob, `${uploading.client_uuid}.jpg`);
  formData.append("client_uuid", uploading.client_uuid);
  formData.append("angle", uploading.angle);
  formData.append("phase", uploading.phase);
  formData.append("captured_at", uploading.captured_at);
  formData.append("checksum_sha256", uploading.checksum_sha256);
  formData.append("width", String(uploading.width));
  formData.append("height", String(uploading.height));
  formData.append("inspection_id", inspectionId);

  try {
    const sent = await api.upload<Photo>(`/vehicles/${uploading.vehicle_id}/photos`, formData);
    const updated = await updatePhoto(uploading.client_uuid, (current) => ({
      ...current,
      upload_state: "sent",
      server_id: sent.id,
      server_url: sent.url,
      error: null,
    }));
    return updated ? "sent" : "skipped"; // supprimée pendant l'envoi lui-même.
  } catch (error) {
    if (isNetworkError(error)) {
      await updatePhoto(uploading.client_uuid, (current) => ({ ...current, upload_state: "queued" }));
      return "offline";
    }
    // 🟠 Correctif revue finale § n°1 : un échec business classé DÉFINITIF (409/422, voir
    // `isDefinitivePhotoError`) passe directement en `failed_permanent` dès le premier échec
    // — inutile de gâcher des tentatives sur une erreur qui ne peut pas changer d'issue. Tout
    // AUTRE échec reste `failed` (retenté au tick suivant, `needsSync`) jusqu'à
    // `MAX_UPLOAD_ATTEMPTS`, au-delà duquel il bascule lui aussi en `failed_permanent` — c'est
    // ce qui fait enfin SERVIR le compteur `attempts`, jusqu'ici incrémenté sans être lu nulle
    // part. `failed_permanent` sort du calcul de `needsSync`/`stillPendingPhotos` (aucun des
    // deux ne teste que `"queued"`/`"failed"`, jamais cette nouvelle valeur) : la photo
    // n'est plus rejouée automatiquement et ne bloque plus `pending_submit` indéfiniment — le
    // chauffeur retrouve la main via « Reprendre » (`PhotoAngleGrid.tsx`), et si l'angle était
    // obligatoire, le serveur le redira clairement à la soumission (`409
    // inspection_incomplete`) plutôt que de laisser le contrôle bloqué en silence.
    await updatePhoto(uploading.client_uuid, (current) => {
      const attempts = current.attempts + 1;
      const definitive = isDefinitivePhotoError(error) || attempts >= MAX_UPLOAD_ATTEMPTS;
      return {
        ...current,
        upload_state: definitive ? "failed_permanent" : "failed",
        attempts,
        error: errorMessage(error),
      };
    });
    return "failed";
  }
}
