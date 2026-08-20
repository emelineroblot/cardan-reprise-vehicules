"""Schémas Pydantic v2 — notifications et abonnements web push (brief J2, arbitrage
« notifications en base, web push optionnel »)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: str
    titre: str
    corps: str
    payload: dict[str, Any] | None
    read_at: datetime | None
    sent_at: datetime | None
    created_at: datetime


class UnreadCountResponse(BaseModel):
    count: int


class PushSubscriptionCreate(BaseModel):
    """Corps de `pushManager.subscribe()` côté navigateur — enregistré même si le push n'est
    pas activé côté serveur (VAPID absent) : l'abonnement est prêt pour le jour où il le sera."""

    endpoint: str
    p256dh: str
    auth: str
    user_agent: str | None = None


class PushSubscriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    endpoint: str
    is_active: bool
    created_at: datetime
    last_used_at: datetime | None


class PushPublicKeyResponse(BaseModel):
    """`enabled=False` quand les clés VAPID sont absentes — le front ne doit alors jamais
    proposer l'abonnement push (arbitrage : son absence ne dégrade jamais le parcours)."""

    enabled: bool
    public_key: str | None
