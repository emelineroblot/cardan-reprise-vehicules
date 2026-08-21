"""Service notifications — persistées en base (chemin nominal, brief J2), web push best-effort.

`create_notification` fait partie de la même transaction que l'effet qui la déclenche (ex.
affectation d'une mission, `app/services/vehicles.py`). `dispatch_pending_push` est, elle,
appelée **après** le commit principal : un échec réseau du canal push ne doit jamais annuler
une affectation déjà actée (arbitrage « web push optionnel »).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.mission import Mission
from app.models.notification import Notification, PushSubscription
from app.models.vehicle import Vehicle
from app.services.push import PushTarget, is_push_enabled, send_web_push

logger = logging.getLogger(__name__)


def create_notification(
    db: Session,
    *,
    user_id: UUID,
    type: str,
    titre: str,
    corps: str,
    payload: dict[str, Any] | None = None,
) -> Notification:
    notification = Notification(
        id=uuid4(), user_id=user_id, type=type, titre=titre, corps=corps, payload=payload
    )
    db.add(notification)
    db.flush()
    return notification


def notify_mission_assigned(
    db: Session, *, driver_id: UUID, vehicle: Vehicle, mission: Mission
) -> Notification:
    """Brief J2 : « notifications à l'affectation d'une mission »."""
    return create_notification(
        db,
        user_id=driver_id,
        type="mission_affectee",
        titre="Nouvelle mission",
        corps=f"Véhicule {vehicle.reference} — {vehicle.marque} {vehicle.modele}",
        payload={"vehicle_id": str(vehicle.id), "mission_id": str(mission.id)},
    )


def dispatch_pending_push(db: Session, notification: Notification) -> None:
    """Tentative best-effort d'envoi Web Push pour tous les abonnements actifs du destinataire.

    Ne fait jamais échouer l'appelant (`send_web_push` ne lève jamais) et ne désactive un
    abonnement que sur un échec **définitif** (`"failed_permanent"`, réponse 404/410 du service
    de push — endpoint réellement mort). Un échec **transitoire** (`"failed_transient"` : timeout,
    5xx passager, panne réseau, extra `pywebpush` absent, VAPID désactivée) ne touche jamais à
    `is_active` — revue J2 § 🔴 n°7 : désactiver sur toute erreur privait silencieusement et
    définitivement le chauffeur de ses notifications futures.

    Chaque appel réseau est borné par `push.PUSH_TIMEOUT_SECONDS` (court, cf. docstring de
    `app.services.push`) : appelée après le commit métier de la transition qui la déclenche,
    cette fonction reste néanmoins synchrone dans la même requête HTTP — un mécanisme de tâche de
    fond n'aurait aucune garantie d'exécution sur une fonction serverless Vercel une fois la
    réponse envoyée, donc le seul levier fiable pour ne pas ralentir sensiblement la transition
    est de borner le pire cas, pas de la déporter.
    """
    if not is_push_enabled():
        return

    subscriptions = list(
        db.scalars(
            select(PushSubscription).where(
                PushSubscription.user_id == notification.user_id,
                PushSubscription.is_active.is_(True),
            )
        ).all()
    )
    if not subscriptions:
        return

    sent = False
    for subscription in subscriptions:
        outcome = send_web_push(
            PushTarget(
                endpoint=subscription.endpoint,
                p256dh=subscription.p256dh,
                auth=subscription.auth,
            ),
            title=notification.titre,
            body=notification.corps,
            data=notification.payload,
        )
        if outcome == "sent":
            sent = True
            subscription.last_used_at = datetime.now(UTC)
        elif outcome == "failed_permanent":
            subscription.is_active = False
        # "failed_transient" : aucune action — retenté au prochain envoi, jamais désactivé.

    if sent:
        notification.sent_at = datetime.now(UTC)
    try:
        db.commit()
    except Exception:  # noqa: BLE001 — best-effort (review-j2-finale.md § 🟡 n°6) : la
        # transition véhicule est déjà committée par l'appelant (`vehicles.py::transition_vehicle`)
        # avant que cette fonction ne soit invoquée. Un échec ici (ex. connexion coupée par la
        # mise en veille de la base Supabase pendant l'appel réseau push) ne doit jamais renvoyer
        # un 500 au client sur une action déjà réussie — seul le marquage `sent_at`/`is_active`
        # est perdu, sans conséquence fonctionnelle (retenté au prochain envoi).
        logger.exception(
            "Échec de la mise à jour post-push (sent_at/is_active) — sans conséquence sur la "
            "transition déjà committée."
        )
        db.rollback()
