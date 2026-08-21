"""Schémas Pydantic v2 — lecture des marts J3 (`analytics.mart_*`, plan.md § 5.2).

Le dashboard ne lit **que** ces marts, jamais un calcul à la volée dans l'UI (brief J3, critère
d'acceptation) — chaque champ ci-dessous existe littéralement en colonne dans le mart
correspondant (`app/analytics/models/marts/*.sql`), rien n'est recalculé côté Python.

Règle de marge, non négociable (plan.md § 5.2, § « Décisions de second rang J1 ») : `marge_cents`
et `marge_pct` sont `None` (jamais `0`) quand `has_marge` est `false` — l'UI doit afficher « — »
dans ce cas, jamais un montant.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class VehiculeMargeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    vehicle_id: UUID
    reference: str
    company_id: UUID
    company_denomination: str
    state: str
    state_label: str
    marque: str
    modele: str
    date_proposition: date
    prix_achat_negocie_cents: int | None
    frais_transport_cents: int
    valeur_revente_estimee_cents: int | None
    cout_hors_atelier_cents: int
    cout_atelier_reel_cents: int
    marge_cents: int | None
    marge_pct: float | None
    has_marge: bool


class CycleTempsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    vehicle_id: UUID
    reference: str
    state: str
    marque: str
    modele: str
    delai_saisie_affectation_heures: float | None
    delai_affectation_controle_heures: float | None
    delai_controle_decision_heures: float | None
    delai_total_heures: float | None


class PipelineEtatRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    state: str
    nb_vehicules: int
    valeur_immobilisee_cents: int


class RefusRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    mois: date
    type_flotte: str
    nb_proposes: int
    nb_refuses: int
    taux_refus: float | None


class TravauxRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    mois: date
    type: str
    volume: int
    nb_clos: int
    cout_moyen_reel_cents: int | None
    ecart_estime_reel_cents: int | None


class KpiGlobalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    nb_vehicules_total: int
    nb_vehicules_actifs: int
    nb_achats_valides: int
    nb_refuses: int
    taux_refus_global: float | None
    marge_moyenne_cents: int | None
    nb_marges_negatives: int
    delai_cycle_moyen_heures: float | None
    cout_travaux_moyen_cents: int | None
