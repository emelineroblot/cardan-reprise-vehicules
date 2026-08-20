"""Schémas Pydantic v2 — véhicules, dédoublonnage, automate d'états (plan.md § 5, § 6 vague 3)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.company import CompanyBrief


class VehicleDraftIn(BaseModel):
    """Corps commun à `duplicate-check` et à la création — un brouillon de fiche."""

    company_id: UUID
    intake_batch_id: UUID | None = None
    marque: str
    modele: str
    version: str | None = None
    energie: str | None = None
    boite: str | None = None
    couleur: str | None = None
    vin: str | None = None
    immatriculation: str | None = None
    date_mise_en_circulation: date | None = None
    kilometrage: int | None = Field(default=None, ge=0)
    date_proposition: date


class VehicleCreate(VehicleDraftIn):
    prix_achat_negocie_cents: int | None = Field(default=None, ge=0)
    valeur_revente_estimee_cents: int | None = None
    frais_transport_cents: int = Field(default=0, ge=0)
    commentaire: str | None = None
    force_create: bool = False  # ignore les alertes "similar" (jamais les "exact"/"probable")


class VehiclePatch(BaseModel):
    """`state` n'apparaît jamais ici — seul `POST /transitions` change l'état (plan.md § 5.3)."""

    marque: str | None = None
    modele: str | None = None
    version: str | None = None
    energie: str | None = None
    boite: str | None = None
    couleur: str | None = None
    vin: str | None = None
    immatriculation: str | None = None
    date_mise_en_circulation: date | None = None
    kilometrage: int | None = Field(default=None, ge=0)
    date_proposition: date | None = None
    prix_achat_negocie_cents: int | None = Field(default=None, ge=0)
    valeur_revente_estimee_cents: int | None = None
    frais_transport_cents: int | None = Field(default=None, ge=0)
    commentaire: str | None = None
    # Miroir de `VehicleCreate.force_create` : une correction qui rapproche la fiche d'une autre
    # (marque/modèle/version/km/date/énergie) rejoue le dédoublonnage (revue § 🟠 « le filtre
    # duplicate_review est du code mort ») — `force_update` lève le blocage `duplicate_probable`
    # après arbitrage, symétriquement à la création.
    force_update: bool = False


class VehicleStateTransitionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    from_state: str | None
    to_state: str
    actor_id: UUID
    actor_role: str
    reason: str | None
    occurred_at: datetime


class VehicleReadBase(BaseModel):
    """Champs communs à la liste et au détail — la liste s'arrête ici, le détail ajoute
    `state_history` (revue § 🟠 « N+1 sur la liste de suivi »)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    reference: str
    company_id: UUID
    company: CompanyBrief
    intake_batch_id: UUID | None
    state: str
    marque: str
    modele: str
    version: str | None
    energie: str | None
    boite: str | None
    couleur: str | None
    vin: str | None
    immatriculation: str | None
    date_mise_en_circulation: date | None
    kilometrage: int | None
    date_proposition: date
    prix_achat_negocie_cents: int | None
    valeur_revente_estimee_cents: int | None
    frais_transport_cents: int
    commentaire: str | None
    created_by_id: UUID
    assigned_driver_id: UUID | None
    refus_motif: str | None
    refus_commentaire: str | None
    state_changed_at: datetime
    created_at: datetime
    updated_at: datetime


class VehicleListItem(VehicleReadBase):
    """`GET /vehicles` — sans `state_history` : la liste ne l'affiche pas, et l'embarquer
    déclenchait un N+1 (`Vehicle.state_history` en lazy load, un aller-retour par ligne)."""


class VehicleRead(VehicleReadBase):
    """Fiche détail — `GET /vehicles/{id}`, `POST /vehicles`, `PATCH`, `POST /transitions`.

    Frise d'historique d'états, triée chronologiquement — plan.md § 6 vague 4 (front).
    """

    state_history: list[VehicleStateTransitionRead] = Field(default_factory=list)


class DuplicateComponents(BaseModel):
    s_modele: float
    s_date: float
    s_km: float
    s_energie: float
    bonus_terminal: float


class DuplicateCandidate(BaseModel):
    """Fiche existante candidate à un doublon — assez complète pour une comparaison côte à côte
    (brief § critères d'acceptation J1) : chaque composante de `features` doit pouvoir être
    justifiée par les deux valeurs comparées (correction dev-frontend, jalon J1).

    Réservé aux rôles `operatrice`/`administrateur` (seuls appelants de `duplicate-check`, voir
    `_WRITE_ROLES` dans `api/v1/vehicles.py`) : ces champs sont déjà visibles par ces rôles sur
    n'importe quel véhicule via `GET /vehicles` et `GET /vehicles/{id}` (`scope_vehicles` ne les
    restreint pas — plan.md § 3.4), donc cet enrichissement ne crée aucune fuite d'information
    au-delà de ce que ces rôles voient déjà.
    """

    vehicle_id: UUID
    reference: str
    marque: str
    modele: str
    version: str | None
    energie: str | None
    vin: str | None
    immatriculation: str | None
    kilometrage: int | None
    date_mise_en_circulation: date | None
    date_proposition: date
    created_at: datetime
    state: str
    refus_motif: str | None
    refus_commentaire: str | None
    score: float
    # Nommé `features` — identique au champ attendu par `DuplicateReviewCreate.features`
    # (plan.md § 5.1) : le front peut renvoyer tel quel ce candidat à `POST /duplicate-reviews`.
    features: DuplicateComponents


class DuplicateCheckResponse(BaseModel):
    exact: list[dict] = Field(default_factory=list)
    probable: list[DuplicateCandidate] = Field(default_factory=list)
    similar: list[DuplicateCandidate] = Field(default_factory=list)


class IntakeBatchCreate(BaseModel):
    company_id: UUID
    label: str


class IntakeBatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    label: str
    created_by_id: UUID
    created_at: datetime


class TransitionRequest(BaseModel):
    to_state: str
    reason: str | None = None
    payload: dict | None = None


class TransitionOptionRead(BaseModel):
    """Une entrée de `GET /vehicles/{id}/transitions` — le front dérive son bouton de ceci sans
    connaître l'automate (plan.md § 5.3, revue § 🔴 « enrichis GET /vehicles/{id}/transitions »).
    """

    to_state: str
    label: str
    requires_reason: bool
    requires_payload_fields: list[str]


class AllowedTransitionsResponse(BaseModel):
    """Forme figée : objet `{"allowed": [...]}`, pas un tableau nu — laisse la place à des
    métadonnées de niveau supérieur (ex. `state`, `state_changed_at`) sans rupture de contrat
    si besoin en J2/J3."""

    allowed: list[TransitionOptionRead]


class DuplicateReviewCreate(BaseModel):
    vehicle_a_id: UUID
    vehicle_b_id: UUID
    verdict: Literal["duplicate", "not_duplicate"]
    score: float = Field(ge=0, le=1)
    features: dict


class DuplicateReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    vehicle_a_id: UUID
    vehicle_b_id: UUID
    verdict: str
    score: float
    features: dict
    decided_by_id: UUID
    decided_at: datetime
