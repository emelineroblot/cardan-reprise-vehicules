"""Schémas Pydantic v2 — missions du chauffeur (brief J2, plan.md § 5.1).

Aucun schéma d'écriture ici : la prise de rendez-vous et les autres changements d'état de
mission restent des **effets** de `POST /vehicles/{id}/transitions` (plan.md § 5.3, « un seul
point d'entrée ») — ce module n'expose que de la lecture.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class MissionVehicleBrief(BaseModel):
    """De quoi afficher la mission dans la liste du chauffeur sans recharger la fiche complète."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    reference: str
    marque: str
    modele: str
    version: str | None
    state: str
    company_id: UUID


class MissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    vehicle_id: UUID
    driver_id: UUID
    state: str
    rdv_at: datetime | None
    rdv_adresse: str | None
    rdv_contact_nom: str | None
    rdv_contact_telephone: str | None
    assigned_by_id: UUID
    assigned_at: datetime
    accepted_at: datetime | None
    completed_at: datetime | None
    notes: str | None
    vehicle: MissionVehicleBrief
