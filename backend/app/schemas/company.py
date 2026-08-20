"""Schémas Pydantic v2 — sociétés et enrichissement SIRET (plan.md § 4 décision B)."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CompanyLookupCompany(BaseModel):
    siret: str
    siren: str
    denomination: str
    forme_juridique: str | None = None
    code_naf: str | None = None
    libelle_naf: str | None = None
    adresse_ligne1: str
    code_postal: str
    commune: str
    tranche_effectif: str | None = None
    date_creation: str | None = None


class CompanyLookupResponse(BaseModel):
    source: str  # "api" | "cache" | "demo"
    stale: bool
    company: CompanyLookupCompany


class CompanyCreate(BaseModel):
    siret: str = Field(min_length=14, max_length=14)
    denomination: str
    forme_juridique: str | None = None
    code_naf: str | None = None
    libelle_naf: str | None = None
    adresse_ligne1: str
    code_postal: str
    commune: str
    pays: str = "FR"
    tranche_effectif: str | None = None
    date_creation: date | None = None
    type_flotte: str
    source_enrichissement: str
    contact_nom: str | None = None
    contact_telephone: str | None = None


class CompanyBrief(BaseModel):
    """Version allégée de `Company`, embarquée dans les réponses véhicule (liste **et** détail)
    pour que la colonne/en-tête « Société » soit renseignée sans recharger la ressource
    complète (revue § 🟠 « la colonne Société est vide partout »)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    denomination: str
    siret: str


class CompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    siren: str
    siret: str
    denomination: str
    forme_juridique: str | None
    code_naf: str | None
    libelle_naf: str | None
    adresse_ligne1: str
    code_postal: str
    commune: str
    pays: str
    tranche_effectif: str | None
    date_creation: date | None
    type_flotte: str
    source_enrichissement: str
    enriched_at: datetime | None
    contact_nom: str | None
    contact_telephone: str | None
    created_by_id: UUID
    created_at: datetime
    updated_at: datetime
