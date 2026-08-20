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
