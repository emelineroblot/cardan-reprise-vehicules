"""Schémas Pydantic v2 — authentification."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class MeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str
    role: str
    telephone: str | None = None
