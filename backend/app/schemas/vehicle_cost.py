"""Schémas Pydantic v2 — `vehicle_cost`, coûts hors atelier (plan.md § 5.1, J3).

Distinct de `work_order_line` (coût atelier, saisi par le rôle `atelier`) : `vehicle_cost` couvre
le transport, le carburant, l'administratif et la remise en état externe — saisis par
l'administration (`Décision d'implémentation` : voir `implementation.md` § J3, ces coûts n'ont pas
de rôle métier dédié comme l'atelier, ils restent dans le périmètre « Administration » du brief).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class VehicleCostCreate(BaseModel):
    type: str
    montant_cents: int = Field(ge=0)
    commentaire: str | None = None


class VehicleCostRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    vehicle_id: UUID
    type: str
    montant_cents: int
    commentaire: str | None
    created_by_id: UUID
    created_at: datetime
