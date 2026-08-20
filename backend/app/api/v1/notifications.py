"""`/notifications/*` — brief J2, arbitrage « notifications en base, web push optionnel ».

Le chemin nominal (pastille, liste) fonctionne sans aucune clé : `GET /notifications`,
`GET /notifications/unread-count` et les deux endpoints « marquer comme lu » n'ont aucune
dépendance à la configuration VAPID. `push-public-key`/`push-subscriptions` sont le seul point
où le push réel entre en jeu, et restent inertes (mais jamais en erreur) si VAPID est absent.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.pagination import Page, PageParams, page_params, paginate
from app.db.session import get_db
from app.models.notification import Notification, PushSubscription
from app.models.user import AppUser
from app.schemas.notification import (
    NotificationRead,
    PushPublicKeyResponse,
    PushSubscriptionCreate,
    PushSubscriptionRead,
    UnreadCountResponse,
)
from app.services.push import is_push_enabled

router = APIRouter()


@router.get("", response_model=Page[NotificationRead])
def list_notifications(
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
    params: PageParams = Depends(page_params),
    unread_only: bool = False,
) -> Page[NotificationRead]:
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    stmt = stmt.order_by(Notification.created_at.desc())

    items, total = paginate(db, stmt, params)
    return Page[NotificationRead](
        items=[NotificationRead.model_validate(i) for i in items],
        total=total,
        limit=params.limit,
        offset=params.offset,
    )


@router.get("/unread-count", response_model=UnreadCountResponse)
def unread_count(
    db: Session = Depends(get_db), user: AppUser = Depends(get_current_user)
) -> UnreadCountResponse:
    count = (
        db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        )
        or 0
    )
    return UnreadCountResponse(count=count)


@router.post("/{notification_id}/read", response_model=NotificationRead)
def mark_read(
    notification_id: UUID,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> Notification:
    notification = db.scalar(
        select(Notification).where(
            Notification.id == notification_id, Notification.user_id == user.id
        )
    )
    if notification is None:
        raise ApiError("not_found", "Notification introuvable.")
    if notification.read_at is None:
        notification.read_at = datetime.now(UTC)
        db.commit()
        db.refresh(notification)
    return notification


@router.post("/read-all", response_model=UnreadCountResponse)
def mark_all_read(
    db: Session = Depends(get_db), user: AppUser = Depends(get_current_user)
) -> UnreadCountResponse:
    unread = list(
        db.scalars(
            select(Notification).where(
                Notification.user_id == user.id, Notification.read_at.is_(None)
            )
        ).all()
    )
    now = datetime.now(UTC)
    for notification in unread:
        notification.read_at = now
    db.commit()
    return UnreadCountResponse(count=0)


@router.get("/push-public-key", response_model=PushPublicKeyResponse)
def push_public_key() -> PushPublicKeyResponse:
    settings = get_settings()
    enabled = is_push_enabled(settings)
    return PushPublicKeyResponse(
        enabled=enabled, public_key=settings.vapid_public_key if enabled else None
    )


@router.post("/push-subscriptions", response_model=PushSubscriptionRead, status_code=201)
def create_push_subscription(
    payload: PushSubscriptionCreate,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> PushSubscription:
    """Upsert par `endpoint` (unique en base) — un abonnement déjà connu est réattaché à
    l'utilisateur courant plutôt que dupliqué (ex. reconnexion sur le même appareil/navigateur)."""
    existing = db.scalar(
        select(PushSubscription).where(PushSubscription.endpoint == payload.endpoint)
    )
    if existing is not None:
        existing.user_id = user.id
        existing.p256dh = payload.p256dh
        existing.auth = payload.auth
        existing.user_agent = payload.user_agent
        existing.is_active = True
        db.commit()
        db.refresh(existing)
        return existing

    subscription = PushSubscription(
        id=uuid4(),
        user_id=user.id,
        endpoint=payload.endpoint,
        p256dh=payload.p256dh,
        auth=payload.auth,
        user_agent=payload.user_agent,
        is_active=True,
    )
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    return subscription


@router.delete("/push-subscriptions/{subscription_id}", status_code=204, response_model=None)
def delete_push_subscription(
    subscription_id: UUID,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> None:
    subscription = db.scalar(
        select(PushSubscription).where(
            PushSubscription.id == subscription_id, PushSubscription.user_id == user.id
        )
    )
    if subscription is None:
        raise ApiError("not_found", "Abonnement introuvable.")
    subscription.is_active = False
    db.commit()
