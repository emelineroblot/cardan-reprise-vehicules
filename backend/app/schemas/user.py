"""Schémas Pydantic v2 — comptes applicatifs (`GET /users`, dette J1)."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict


class UserBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str
    role: str
    telephone: str | None
    is_active: bool
