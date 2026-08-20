"""`/notifications/*` — chemin nominal en base (sans clé), push-subscriptions inertes tant que
VAPID est absent (brief J2, arbitrage « notifications »)."""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.enums import UserRole
from app.services.notifications import create_notification
from tests.conftest import login_client, make_user


def test_mark_read_and_unread_count(client: TestClient, db_session: Session) -> None:
    chauffeur = make_user(db_session, UserRole.CHAUFFEUR)
    n1 = create_notification(
        db_session, user_id=chauffeur.id, type="mission_affectee", titre="A", corps="corps A"
    )
    create_notification(
        db_session, user_id=chauffeur.id, type="mission_affectee", titre="B", corps="corps B"
    )
    login_client(client, chauffeur)

    unread = client.get("/api/v1/notifications/unread-count")
    assert unread.json()["count"] == 2

    read = client.post(f"/api/v1/notifications/{n1.id}/read")
    assert read.status_code == 200
    assert read.json()["read_at"] is not None

    unread_after = client.get("/api/v1/notifications/unread-count")
    assert unread_after.json()["count"] == 1

    mark_all = client.post("/api/v1/notifications/read-all")
    assert mark_all.status_code == 200
    assert mark_all.json()["count"] == 0

    unread_final = client.get("/api/v1/notifications/unread-count")
    assert unread_final.json()["count"] == 0


def test_notifications_are_scoped_to_owner(client: TestClient, db_session: Session) -> None:
    chauffeur = make_user(db_session, UserRole.CHAUFFEUR)
    other = make_user(db_session, UserRole.CHAUFFEUR)
    notification = create_notification(
        db_session, user_id=chauffeur.id, type="mission_affectee", titre="A", corps="corps A"
    )

    login_client(client, other)
    response = client.post(f"/api/v1/notifications/{notification.id}/read")
    assert response.status_code == 404

    listing = client.get("/api/v1/notifications")
    assert listing.json()["total"] == 0


def test_push_public_key_disabled_by_default(client: TestClient, db_session: Session) -> None:
    chauffeur = make_user(db_session, UserRole.CHAUFFEUR)
    login_client(client, chauffeur)

    response = client.get("/api/v1/notifications/push-public-key")
    assert response.status_code == 200
    assert response.json() == {"enabled": False, "public_key": None}


def test_push_subscription_upsert_and_delete(client: TestClient, db_session: Session) -> None:
    chauffeur = make_user(db_session, UserRole.CHAUFFEUR)
    login_client(client, chauffeur)
    endpoint = f"https://push.example/{uuid4()}"

    created = client.post(
        "/api/v1/notifications/push-subscriptions",
        json={"endpoint": endpoint, "p256dh": "k", "auth": "a"},
    )
    assert created.status_code == 201
    subscription_id = created.json()["id"]

    # Upsert : le même endpoint renvoyé deux fois ne crée pas un second abonnement.
    upserted = client.post(
        "/api/v1/notifications/push-subscriptions",
        json={"endpoint": endpoint, "p256dh": "k2", "auth": "a2"},
    )
    assert upserted.status_code == 201
    assert upserted.json()["id"] == subscription_id

    deleted = client.delete(f"/api/v1/notifications/push-subscriptions/{subscription_id}")
    assert deleted.status_code == 204
