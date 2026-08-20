"""Schémas Pydantic v2 — référentiel de checklist (brief J2, `GET /checklist-templates`).

Manque signalé par dev-backend en revue puis tranché par l'orchestrateur : sans ce référentiel
exposé, dev-frontend ne peut pas rendre le formulaire de contrôle avant qu'une première réponse
ne soit posée (`GET /inspections/{id}` n'expose que les réponses déjà enregistrées).
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ChecklistItemTemplateRead(BaseModel):
    """Un item du formulaire de contrôle. `ordre` = ordre d'affichage ; `categorie` = son
    regroupement (`exterieur|interieur|mecanique|documents|securite`, plan.md § 5.1) — le front
    groupe côté client en triant par `ordre` puis en regroupant par `categorie`, sans dupliquer
    ce référentiel."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    template_id: UUID
    code: str
    libelle: str
    categorie: str
    ordre: int
    is_required: bool
    response_type: str


class ChecklistTemplateBrief(BaseModel):
    """`GET /checklist-templates` — sans les items, pour lister les modèles disponibles."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    libelle: str
    version: int
    is_active: bool


class ChecklistTemplateRead(ChecklistTemplateBrief):
    """`GET /checklist-templates/{id}` — items triés par `ordre` (garanti par la relation ORM,
    `app/models/checklist.py`)."""

    items: list[ChecklistItemTemplateRead] = Field(default_factory=list)
