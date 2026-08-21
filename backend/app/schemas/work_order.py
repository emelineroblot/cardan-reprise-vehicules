"""Schémas Pydantic v2 — atelier : ordres de travaux et lignes de coût réel (plan.md § 5.1, J3).

Aucun schéma ne porte `work_order.state` en écriture libre : la création initiale est un effet de
`POST /vehicles/{id}/transitions` (payload `work_orders`, plan.md § 5.3) et les changements d'état
ultérieurs passent par `POST /work-orders/{id}/state` (mini-automate déclaratif,
`app/services/work_orders.py`) — jamais un `PATCH` généraliste, même principe que l'automate
véhicule (« un seul point d'entrée » par ressource à automate).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WorkOrderLineCreate(BaseModel):
    libelle: str = Field(min_length=1, max_length=255)
    categorie: str
    quantite: Decimal = Field(gt=0)
    prix_unitaire_cents: int = Field(ge=0)


class WorkOrderLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    work_order_id: UUID
    libelle: str
    categorie: str
    quantite: Decimal
    prix_unitaire_cents: int
    montant_cents: int  # colonne GENERATED (base) — jamais recalculée côté Python
    created_at: datetime


class WorkOrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    vehicle_id: UUID
    type: str
    state: str
    description: str
    montant_estime_cents: int | None
    created_by_id: UUID
    assigned_to_id: UUID | None
    requested_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    commentaire_atelier: str | None
    lines: list[WorkOrderLineRead] = Field(default_factory=list)


class WorkOrderStateUpdate(BaseModel):
    """`POST /work-orders/{id}/state` — mini-automate `demande -> en_cours -> termine|annule`."""

    to_state: str
    commentaire_atelier: str | None = None
    assigned_to_id: UUID | None = None
