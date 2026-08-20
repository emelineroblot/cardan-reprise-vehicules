"""Schémas Pydantic v2 — inspections et checklist interactive (brief J2, plan.md § 4 décision C)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class InspectionCreate(BaseModel):
    """Idempotent par `client_uuid`, généré côté client (décision C : le brouillon doit pouvoir
    naître hors ligne). `vehicle_id` doit être en `CONTROLE_EN_COURS` avec une mission active
    affectée à l'appelant."""

    client_uuid: UUID
    vehicle_id: UUID
    template_id: UUID | None = None


class InspectionItemUpsert(BaseModel):
    item_template_id: UUID
    valeur_bool: bool | None = None
    valeur_note: int | None = Field(default=None, ge=1, le=5)
    valeur_texte: str | None = None
    valeur_num: float | None = None
    commentaire: str | None = None
    photo_id: UUID | None = None


class InspectionItemsUpsertRequest(BaseModel):
    items: list[InspectionItemUpsert]


class InspectionPatch(BaseModel):
    """Champs de brouillon modifiables tant que `submitted_at` est nul."""

    kilometrage_releve: int | None = Field(default=None, ge=0)
    etat_general: str | None = None
    commentaire: str | None = None


class InspectionSubmitRequest(BaseModel):
    """Corps optionnel de `POST /inspections/{id}/submit` — permet de poser les champs de
    synthèse en même temps que la soumission plutôt que d'exiger un `PATCH` préalable."""

    kilometrage_releve: int | None = Field(default=None, ge=0)
    etat_general: str | None = None
    conclusion: str | None = None
    commentaire: str | None = None


class InspectionItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    item_template_id: UUID
    valeur_bool: bool | None
    valeur_note: int | None
    valeur_texte: str | None
    valeur_num: float | None
    commentaire: str | None
    photo_id: UUID | None


class InspectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    vehicle_id: UUID
    mission_id: UUID
    driver_id: UUID
    template_id: UUID
    client_uuid: UUID
    started_at: datetime
    submitted_at: datetime | None
    kilometrage_releve: int | None
    etat_general: str | None
    conclusion: str | None
    commentaire: str | None
    created_at: datetime
    items: list[InspectionItemRead] = Field(default_factory=list)
