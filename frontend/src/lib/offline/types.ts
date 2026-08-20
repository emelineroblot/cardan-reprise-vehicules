import type {
  ChecklistTemplate,
  EtatGeneral,
  InspectionConclusion,
  PhotoAngle,
  PhotoPhase,
} from "@/lib/api/types";

/** Une réponse de checklist en brouillon local — miroir de `InspectionItemUpsert`. */
export interface LocalItemAnswer {
  item_template_id: string;
  valeur_bool?: boolean | null;
  valeur_note?: number | null;
  valeur_texte?: string | null;
  valeur_num?: number | null;
  commentaire?: string | null;
}

/**
 * Brouillon d'inspection en IndexedDB (décision C, plan.md § 4) — source de vérité
 * pendant tout le contrôle terrain. `client_uuid` est la clé d'idempotence envoyée à
 * `POST /inspections` : générée côté client, elle survit à une coupure réseau au moment
 * précis où le chauffeur commence son contrôle (voir implementation.md § J2 Backend,
 * « inspection créée par le client, pas par la transition »).
 */
export interface LocalInspection {
  /** Clé primaire du store — généré par `crypto.randomUUID()` à la création locale. */
  client_uuid: string;
  vehicle_id: string;
  mission_id: string;
  template_id: string;
  started_at: string;

  kilometrage_releve: number | null;
  etat_general: EtatGeneral | null;
  conclusion: InspectionConclusion | null;
  commentaire: string | null;
  items: Record<string, LocalItemAnswer>;

  /** `id` réel côté serveur — `null` tant que `POST /inspections` n'a pas abouti. */
  server_id: string | null;
  /** Angles requis mis en cache lors du dernier `GET .../required-angles` réussi. */
  required_angles: string[] | null;

  fields_dirty: boolean;
  items_dirty: boolean;
  /** Soumission demandée par l'utilisateur, en attente de synchronisation complète. */
  pending_submit: boolean;
  submitted_at: string | null;

  /** Dernière erreur de synchronisation lisible (réseau mis à part) — pour affichage. */
  last_sync_error: string | null;
  /** Détail d'un `409 inspection_incomplete` — items/angles manquants côté serveur. */
  missing_items: string[] | null;
  missing_angles: string[] | null;

  updated_at: string;
}

/**
 * `"failed"` = échec TRANSITOIRE, encore retenté automatiquement au tick suivant.
 * `"failed_permanent"` = échec DÉFINITIF (409/422, ou tout échec récurrent au-delà de
 * `MAX_UPLOAD_ATTEMPTS`, voir `sync.ts::isDefinitivePhotoError`) — plus jamais rejoué
 * automatiquement, la seule issue est « Reprendre » (`PhotoAngleGrid.tsx`). Distinction
 * ajoutée en revue finale J2 § 🟠 n°1 : sans elle, une photo en échec définitif rejouait
 * indéfiniment le même envoi ET gelait `pending_submit` à vie (`sync.ts` étape 6).
 */
export type LocalPhotoUploadState = "queued" | "uploading" | "sent" | "failed" | "failed_permanent";

/** Une photo en file d'attente (décision C) — l'octet ne quitte le brouillon local
 * qu'une fois `upload_state === "sent"`. */
export interface LocalPhoto {
  /** Clé primaire du store — idempotence serveur (`photo.client_uuid`, § 5.1). */
  client_uuid: string;
  inspection_client_uuid: string;
  vehicle_id: string;
  angle: PhotoAngle;
  phase: PhotoPhase;

  blob: Blob;
  content_type: string;
  byte_size: number;
  width: number;
  height: number;
  checksum_sha256: string;
  captured_at: string;

  upload_state: LocalPhotoUploadState;
  attempts: number;
  error: string | null;
  /** `id`/`url` renvoyés par le serveur une fois envoyée — pour l'aperçu sans re-fetch. */
  server_id: string | null;
  server_url: string | null;
}

/** Référentiel checklist mis en cache pour rester lisible hors ligne (§ décision C). */
export interface CachedChecklistTemplate {
  template_id: string;
  template: ChecklistTemplate;
  cached_at: string;
}
