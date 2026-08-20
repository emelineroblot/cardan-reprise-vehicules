"""Schémas Pydantic v2 — photos guidées (plan.md § 3.6, § 4 décision C)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class PhotoRead(BaseModel):
    """`url` est calculée à la volée par le backend de stockage actif
    (`app/services/storage/service.py`) — jamais stockée en base."""

    id: UUID
    vehicle_id: UUID
    inspection_id: UUID | None
    work_order_id: UUID | None
    angle: str
    phase: str
    content_type: str
    byte_size: int
    width: int
    height: int
    client_uuid: UUID
    upload_state: str
    is_placeholder: bool
    captured_at: datetime
    uploaded_at: datetime | None
    url: str


class RequiredAnglesResponse(BaseModel):
    """Parcours d'angles imposé (brief J2) — ce que le front doit encore capturer pour un
    `inspection_id` donné."""

    required_angles: list[str]
    captured_angles: list[str]
    missing_angles: list[str]
