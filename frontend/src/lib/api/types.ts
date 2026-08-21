import type { components } from "./schema";

/**
 * Unions de domaine — le backend expose ces champs en `string` nu dans son OpenAPI
 * (StrEnum interne + CHECK en base, jamais de Literal Pydantic sur ces champs-là,
 * cf. .agent-team/review.md). On les renarrowe localement pour garder un typage utile
 * côté UI (labels, StateBadge, `<Select>`...) ; la valeur réelle est garantie par la
 * contrainte serveur, seul le typage TS est enrichi ici.
 */
export type Role = "operatrice" | "chauffeur" | "administrateur" | "atelier";

export type VehicleState =
  | "BROUILLON"
  | "A_PLANIFIER"
  | "AFFECTE"
  | "RDV_PLANIFIE"
  | "CONTROLE_EN_COURS"
  | "TRAVAUX_REQUIS"
  | "TRAVAUX_EN_COURS"
  | "TRAVAUX_TERMINES"
  | "ACHAT_VALIDE"
  | "REFUSE"
  | "ANNULE";

export type TypeFlotte = "taxi" | "ambulance" | "transport" | "auto_ecole" | "location" | "autre";
export type Energie = "essence" | "diesel" | "hybride" | "electrique" | "gpl" | "autre";
export type Boite = "manuelle" | "automatique";
export type RefusMotif =
  | "etat_mecanique"
  | "carrosserie"
  | "kilometrage"
  | "prix"
  | "vendeur_retracte"
  | "autre";
export type SourceEnrichissement = "api" | "cache" | "demo" | "manuel";
export type DuplicateReviewVerdict = "duplicate" | "not_duplicate";

// --- Auth ---------------------------------------------------------------

/** `GET /auth/me` ET `POST /auth/login` — même forme à plat, sans enveloppe (contrat figé). */
export type AppUser = Omit<components["schemas"]["MeResponse"], "role"> & { role: Role };

// --- Sociétés -------------------------------------------------------------

export type CompanyBrief = components["schemas"]["CompanyBrief"];

export type Company = Omit<
  components["schemas"]["CompanyRead"],
  "type_flotte" | "source_enrichissement"
> & {
  type_flotte: TypeFlotte;
  source_enrichissement: SourceEnrichissement;
};

export type CompanyCreate = Omit<
  components["schemas"]["CompanyCreate"],
  "type_flotte" | "source_enrichissement"
> & {
  type_flotte: TypeFlotte;
  source_enrichissement: SourceEnrichissement;
};

export type CompanyLookupCompany = components["schemas"]["CompanyLookupCompany"];

export type CompanyLookupResponse = Omit<components["schemas"]["CompanyLookupResponse"], "source"> & {
  source: "api" | "cache" | "demo";
};

// --- Véhicules --------------------------------------------------------------

/** Corps de `POST /vehicles/duplicate-check` et `POST /vehicles` (avec `force_create`). */
export type VehicleCreate = Omit<components["schemas"]["VehicleCreate"], "energie" | "boite"> & {
  energie?: Energie | null;
  boite?: Boite | null;
};

export type VehiclePatch = Omit<components["schemas"]["VehiclePatch"], "energie" | "boite"> & {
  energie?: Energie | null;
  boite?: Boite | null;
};

type VehicleEnumFields = "state" | "energie" | "boite" | "refus_motif";
type VehicleEnumOverrides = {
  state: VehicleState;
  energie: Energie | null;
  boite: Boite | null;
  refus_motif: RefusMotif | null;
};

/** `GET /vehicles` — sans `state_history` (évite le N+1, cf. contrat backend final). */
export type VehicleListItem = Omit<components["schemas"]["VehicleListItem"], VehicleEnumFields> &
  VehicleEnumOverrides;

export type VehicleStateTransitionRecord = Omit<
  components["schemas"]["VehicleStateTransitionRead"],
  "from_state" | "to_state" | "actor_role"
> & {
  from_state: VehicleState | null;
  to_state: VehicleState;
  actor_role: Role;
};

/**
 * `GET /vehicles/{id}`, `POST /vehicles`, `PATCH`, `POST /transitions` — avec
 * `state_history`. `state_history` est `Field(default_factory=list)` côté backend
 * (`schemas/vehicle.py`) : jamais absent à l'exécution (voir `DuplicateCheckResult` pour
 * la même remarque sur `default_factory`) — renarrowé en tableau garanti.
 */
export type Vehicle = Omit<
  components["schemas"]["VehicleRead"],
  VehicleEnumFields | "state_history"
> &
  VehicleEnumOverrides & {
    state_history: VehicleStateTransitionRecord[];
  };

// --- Dédoublonnage ----------------------------------------------------------

export type DuplicateComponents = components["schemas"]["DuplicateComponents"];

/**
 * Candidat PLAT (`vehicle_id`, `reference`, ... au même niveau) — jamais `{vehicle: ...}`.
 * Enrichi (contrat backend cycle 3) de `vin`/`immatriculation`/`kilometrage`/`energie`/
 * `date_mise_en_circulation`/`created_at` — valeurs BRUTES, pas normalisées (cohérent avec
 * `VehicleReadBase`) — pour permettre à `ArbitrageDoublon` de justifier chaque composante du
 * score par les deux valeurs comparées.
 */
export type DuplicateCandidate = Omit<
  components["schemas"]["DuplicateCandidate"],
  "state" | "refus_motif" | "energie"
> & {
  state: VehicleState;
  refus_motif: RefusMotif | null;
  energie: Energie | null;
};

/**
 * Le backend ne type pas encore `exact[]` dans son OpenAPI (`{[key: string]: unknown}[]`
 * générique) ; forme réelle observée par `dev-tester` via `curl` : `{champ, vehicle_id,
 * reference}`. À resserrer côté backend si un schéma Pydantic dédié est ajouté un jour.
 */
export interface DuplicateExactMatch {
  champ: string;
  vehicle_id: string;
  reference: string;
}

/**
 * `exact`/`probable`/`similar` sont `Field(default_factory=list)` côté backend
 * (`schemas/vehicle.py`) : jamais absents à l'exécution, toujours au moins `[]`. L'OpenAPI
 * les marque `?` uniquement parce qu'une `default_factory` n'émet pas de clé `default`
 * dans le JSON Schema — on les renarrowe ici en tableaux garantis (jamais `undefined`),
 * et `probable`/`similar` reprennent le `DuplicateCandidate` local (`state`/`refus_motif`
 * typés), pas le schéma brut.
 */
export type DuplicateCheckResult = Omit<
  components["schemas"]["DuplicateCheckResponse"],
  "exact" | "probable" | "similar"
> & {
  exact: DuplicateExactMatch[];
  probable: DuplicateCandidate[];
  similar: DuplicateCandidate[];
};

export type DuplicateReviewCreate = Omit<components["schemas"]["DuplicateReviewCreate"], "verdict"> & {
  verdict: DuplicateReviewVerdict;
};

export type DuplicateReview = Omit<components["schemas"]["DuplicateReviewRead"], "verdict"> & {
  verdict: DuplicateReviewVerdict;
};

// --- Automate d'états ---------------------------------------------------

/** Un élément de `AllowedTransitionsResponse.allowed` — jamais un tableau nu à la racine. */
export type TransitionOption = Omit<components["schemas"]["TransitionOptionRead"], "to_state"> & {
  to_state: VehicleState;
};

export type AllowedTransitionsResponse = {
  allowed: TransitionOption[];
};

export type VehicleTransitionCreate = Omit<components["schemas"]["TransitionRequest"], "to_state"> & {
  to_state: VehicleState;
};

// --- Lots ---------------------------------------------------------------

export type IntakeBatch = components["schemas"]["IntakeBatchRead"];
export type IntakeBatchCreate = components["schemas"]["IntakeBatchCreate"];

// --- Pagination -----------------------------------------------------------

export type Page<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};

export const VEHICLE_STATES: VehicleState[] = [
  "BROUILLON",
  "A_PLANIFIER",
  "AFFECTE",
  "RDV_PLANIFIE",
  "CONTROLE_EN_COURS",
  "TRAVAUX_REQUIS",
  "TRAVAUX_EN_COURS",
  "TRAVAUX_TERMINES",
  "ACHAT_VALIDE",
  "REFUSE",
  "ANNULE",
];

export const VEHICLE_STATE_LABELS: Record<VehicleState, string> = {
  BROUILLON: "Brouillon",
  A_PLANIFIER: "À planifier",
  AFFECTE: "Affecté",
  RDV_PLANIFIE: "RDV planifié",
  CONTROLE_EN_COURS: "Contrôle en cours",
  TRAVAUX_REQUIS: "Travaux requis",
  TRAVAUX_EN_COURS: "Travaux en cours",
  TRAVAUX_TERMINES: "Travaux terminés",
  ACHAT_VALIDE: "Achat validé",
  REFUSE: "Refusé",
  ANNULE: "Annulé",
};

export const ROLE_LABELS: Record<Role, string> = {
  operatrice: "Opératrice",
  chauffeur: "Chauffeur",
  administrateur: "Administrateur",
  atelier: "Atelier",
};

export const TYPE_FLOTTE_LABELS: Record<TypeFlotte, string> = {
  taxi: "Taxi",
  ambulance: "Ambulance",
  transport: "Transport",
  auto_ecole: "Auto-école",
  location: "Location",
  autre: "Autre",
};

export const ENERGIE_LABELS: Record<Energie, string> = {
  essence: "Essence",
  diesel: "Diesel",
  hybride: "Hybride",
  electrique: "Électrique",
  gpl: "GPL",
  autre: "Autre",
};

export const BOITE_LABELS: Record<Boite, string> = {
  manuelle: "Manuelle",
  automatique: "Automatique",
};

export const REFUS_MOTIF_LABELS: Record<RefusMotif, string> = {
  etat_mecanique: "État mécanique",
  carrosserie: "Carrosserie",
  kilometrage: "Kilométrage",
  prix: "Prix",
  vendeur_retracte: "Vendeur rétracté",
  autre: "Autre",
};

// --- J2 : missions, inspections, checklist, photos, notifications --------

export type MissionState = "affectee" | "acceptee" | "rdv_planifie" | "en_cours" | "terminee" | "annulee";

export type MissionVehicleBrief = Omit<components["schemas"]["MissionVehicleBrief"], "state"> & {
  state: VehicleState;
};

export type Mission = Omit<components["schemas"]["MissionRead"], "state" | "vehicle"> & {
  state: MissionState;
  vehicle: MissionVehicleBrief;
};

export type UserBrief = Omit<components["schemas"]["UserBrief"], "role"> & { role: Role };

export type ChecklistCategorie = "exterieur" | "interieur" | "mecanique" | "documents" | "securite";
export type ChecklistResponseType = "ok_ko" | "note_1_5" | "texte" | "numerique";

export type ChecklistItemTemplate = Omit<
  components["schemas"]["ChecklistItemTemplateRead"],
  "categorie" | "response_type"
> & {
  categorie: ChecklistCategorie;
  response_type: ChecklistResponseType;
};

export type ChecklistTemplateBrief = components["schemas"]["ChecklistTemplateBrief"];

export type ChecklistTemplate = Omit<components["schemas"]["ChecklistTemplateRead"], "items"> & {
  items: ChecklistItemTemplate[];
};

export type InspectionItem = components["schemas"]["InspectionItemRead"];
export type InspectionItemUpsert = components["schemas"]["InspectionItemUpsert"];

export type EtatGeneral = "bon" | "moyen" | "mauvais";
export type InspectionConclusion = "achat_direct" | "travaux_requis" | "refus";

export type Inspection = Omit<
  components["schemas"]["InspectionRead"],
  "etat_general" | "conclusion" | "items"
> & {
  etat_general: EtatGeneral | null;
  conclusion: InspectionConclusion | null;
  items: InspectionItem[];
};

export type InspectionCreate = components["schemas"]["InspectionCreate"];
export type InspectionPatch = components["schemas"]["InspectionPatch"];
export type InspectionSubmitRequest = components["schemas"]["InspectionSubmitRequest"];

/**
 * Détail renvoyé par `409 inspection_incomplete` (`ApiError.details`) — pas un schéma
 * Pydantic dédié côté OpenAPI (une `dict` brute dans le corps d'erreur), typé ici à la
 * main comme `DuplicateExactMatch` (même remarque, § J1 `types.ts`).
 */
export interface InspectionIncompleteDetails {
  missing_items: string[];
  missing_angles: string[];
}

export const PHOTO_ANGLES = [
  "face_avant",
  "trois_quarts_avant_gauche",
  "profil_gauche",
  "trois_quarts_arriere_gauche",
  "face_arriere",
  "trois_quarts_arriere_droit",
  "profil_droit",
  "trois_quarts_avant_droit",
  "interieur_avant",
  "interieur_arriere",
  "coffre",
  "compteur",
  "defaut",
] as const;
export type PhotoAngle = (typeof PHOTO_ANGLES)[number];

export type PhotoPhase = "controle" | "avant_travaux" | "apres_travaux";
export type PhotoUploadState = "en_attente" | "envoyee" | "echouee";

export type Photo = Omit<components["schemas"]["PhotoRead"], "angle" | "phase" | "upload_state"> & {
  angle: PhotoAngle;
  phase: PhotoPhase;
  upload_state: PhotoUploadState;
};

export type RequiredAnglesResponse = components["schemas"]["RequiredAnglesResponse"];

export type NotificationType = "mission_affectee";

export type Notification = Omit<components["schemas"]["NotificationRead"], "type"> & {
  type: NotificationType;
};

export type PushPublicKeyResponse = components["schemas"]["PushPublicKeyResponse"];
export type PushSubscriptionCreate = components["schemas"]["PushSubscriptionCreate"];
export type PushSubscriptionRead = components["schemas"]["PushSubscriptionRead"];

export const MISSION_STATE_LABELS: Record<MissionState, string> = {
  affectee: "Affectée",
  acceptee: "Acceptée",
  rdv_planifie: "RDV planifié",
  en_cours: "Contrôle en cours",
  terminee: "Terminée",
  annulee: "Annulée",
};

export const CHECKLIST_CATEGORIE_LABELS: Record<ChecklistCategorie, string> = {
  exterieur: "Extérieur",
  interieur: "Intérieur",
  mecanique: "Mécanique",
  documents: "Documents",
  securite: "Sécurité",
};

export const ETAT_GENERAL_LABELS: Record<EtatGeneral, string> = {
  bon: "Bon",
  moyen: "Moyen",
  mauvais: "Mauvais",
};

export const INSPECTION_CONCLUSION_LABELS: Record<InspectionConclusion, string> = {
  achat_direct: "Achat direct",
  travaux_requis: "Travaux requis",
  refus: "Refus",
};

/**
 * Libellés et instructions de prise de vue — contenu de PRÉSENTATION uniquement (icône,
 * phrase d'aide). La liste des angles **requis** et le calcul de complétude restent
 * dérivés de `GET /vehicles/{id}/photos/required-angles` (voir `lib/offline/`), jamais de
 * cette table : les 13 clés existent ici seulement parce que l'UI doit savoir comment
 * *afficher* chaque angle, pas lesquels sont obligatoires.
 */
export const PHOTO_ANGLE_LABELS: Record<PhotoAngle, string> = {
  face_avant: "Face avant",
  trois_quarts_avant_gauche: "3/4 avant gauche",
  profil_gauche: "Profil gauche",
  trois_quarts_arriere_gauche: "3/4 arrière gauche",
  face_arriere: "Face arrière",
  trois_quarts_arriere_droit: "3/4 arrière droit",
  profil_droit: "Profil droit",
  trois_quarts_avant_droit: "3/4 avant droit",
  interieur_avant: "Intérieur avant",
  interieur_arriere: "Intérieur arrière",
  coffre: "Coffre",
  compteur: "Compteur (kilométrage)",
  defaut: "Défaut constaté",
};

// --- J3 : atelier, coûts, Kanban, analytique ------------------------------

export type WorkOrderType = "carrosserie" | "mecanique" | "nettoyage" | "pneumatiques" | "autre";
export type WorkOrderState = "demande" | "en_cours" | "termine" | "annule";
export type WorkOrderLineCategorie = "piece" | "main_oeuvre" | "sous_traitance" | "consommable";
export type VehicleCostType =
  | "transport"
  | "carburant"
  | "administratif"
  | "remise_en_etat_externe"
  | "autre";

export type WorkOrderLine = Omit<components["schemas"]["WorkOrderLineRead"], "categorie"> & {
  categorie: WorkOrderLineCategorie;
};

export type WorkOrderLineCreate = Omit<components["schemas"]["WorkOrderLineCreate"], "categorie"> & {
  categorie: WorkOrderLineCategorie;
};

/**
 * `lines` porté par `WorkOrderRead` — `?` côté OpenAPI (valeur par défaut Pydantic non émise
 * en JSON Schema, même remarque que `state_history`/`DuplicateCheckResult` ailleurs dans ce
 * fichier) mais toujours présent à l'exécution (`GET /vehicles/{id}/work-orders` et
 * `GET /work-orders/{id}` le chargent explicitement, implementation.md § J3 Backend).
 */
export type WorkOrder = Omit<
  components["schemas"]["WorkOrderRead"],
  "type" | "state" | "lines"
> & {
  type: WorkOrderType;
  state: WorkOrderState;
  lines: WorkOrderLine[];
};

export type WorkOrderStateUpdate = Omit<components["schemas"]["WorkOrderStateUpdate"], "to_state"> & {
  to_state: Exclude<WorkOrderState, "demande">;
};

export type VehicleCost = Omit<components["schemas"]["VehicleCostRead"], "type"> & {
  type: VehicleCostType;
};

export type VehicleCostCreate = Omit<components["schemas"]["VehicleCostCreate"], "type"> & {
  type: VehicleCostType;
};

export type PipelineStateCount = Omit<components["schemas"]["PipelineStateCount"], "state"> & {
  state: VehicleState;
};

/** `GET /vehicles/pipeline-counts` — toujours les 11 états, même à `count: 0` (contrat backend). */
export type PipelineCounts = {
  counts: PipelineStateCount[];
};

/**
 * `GET /analytics/marge` — cœur de la démonstration (brief J3). `marge_cents`/`marge_pct` sont
 * `null` quand `has_marge` est `false` — JAMAIS `0` (règle non négociable, ne jamais appliquer
 * `Math.max(0, …)` côté front). `marge_cents` peut être négatif : affiché tel quel.
 */
export type VehiculeMarge = Omit<components["schemas"]["VehiculeMargeRead"], "state"> & {
  state: VehicleState;
};

/** `GET /analytics/cycle-temps` — chaque délai est `null` (jamais `0`) tant que l'étape n'a pas été atteinte. */
export type CycleTemps = Omit<components["schemas"]["CycleTempsRead"], "state"> & {
  state: VehicleState;
};

/** `GET /analytics/pipeline-etat` — vue analytique (valeur immobilisée), distincte du Kanban opérationnel. */
export type PipelineEtat = Omit<components["schemas"]["PipelineEtatRead"], "state"> & {
  state: VehicleState;
};

/** `GET /analytics/refus` — `ANNULE` exclu du numérateur ET du dénominateur ; `taux_refus` est `null` sans donnée. */
export type Refus = Omit<components["schemas"]["RefusRead"], "type_flotte"> & {
  type_flotte: TypeFlotte;
};

/** `GET /analytics/travaux` — coût moyen/écart calculés uniquement sur les ordres clos, `null` sinon. */
export type Travaux = Omit<components["schemas"]["TravauxRead"], "type"> & {
  type: WorkOrderType;
};

/** `GET /analytics/kpi-global` — un objet unique (pas de liste), les tuiles du dashboard. */
export type KpiGlobal = components["schemas"]["KpiGlobalRead"];

export interface AnalyticsRefreshResult {
  mart_name: string;
  status: "succes" | "echec" | (string & {});
  duration_ms: number;
}

export interface AnalyticsRefreshResponse {
  results: AnalyticsRefreshResult[];
}

export interface AnalyticsMartStatus {
  mart_name: string;
  refreshed_at: string;
  status: "succes" | "echec" | (string & {});
  duration_ms: number;
}

export interface AnalyticsStatusResponse {
  marts: AnalyticsMartStatus[];
}

export const WORK_ORDER_TYPE_LABELS: Record<WorkOrderType, string> = {
  carrosserie: "Carrosserie",
  mecanique: "Mécanique",
  nettoyage: "Nettoyage",
  pneumatiques: "Pneumatiques",
  autre: "Autre",
};

export const WORK_ORDER_STATE_LABELS: Record<WorkOrderState, string> = {
  demande: "Demandé",
  en_cours: "En cours",
  termine: "Terminé",
  annule: "Annulé",
};

export const WORK_ORDER_LINE_CATEGORIE_LABELS: Record<WorkOrderLineCategorie, string> = {
  piece: "Pièce",
  main_oeuvre: "Main d'œuvre",
  sous_traitance: "Sous-traitance",
  consommable: "Consommable",
};

export const VEHICLE_COST_TYPE_LABELS: Record<VehicleCostType, string> = {
  transport: "Transport",
  carburant: "Carburant",
  administratif: "Administratif",
  remise_en_etat_externe: "Remise en état externe",
  autre: "Autre",
};
