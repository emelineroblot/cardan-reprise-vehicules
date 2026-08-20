"""Dispatch Web Push depuis la transition réelle — revue J2 § 🔴 n°7.

Volontairement testé au niveau de `POST /vehicles/{id}/transitions`, jamais en appelant
`dispatch_pending_push`/`send_web_push` directement : c'est le seul niveau qui aurait attrapé la
régression d'origine (n'importe quel échec de push désactivait définitivement l'abonnement, et
`webpush()` n'avait aucun délai maximal dans le chemin de la transition). Un test unitaire sur la
fonction interne resterait vert même si l'appelant réintroduisait le même bug (cf. circuit
breaker resté vert en J1, cité par l'orchestrateur).
"""

from __future__ import annotations

import sys
from datetime import date
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.company import Company
from app.models.enums import UserRole
from app.models.notification import PushSubscription
from app.services.push import PUSH_TIMEOUT_SECONDS
from tests.conftest import login_client, make_user

TODAY = date(2026, 8, 20)


def _make_company(db_session: Session, user, **overrides) -> Company:
    base = {
        "id": uuid4(),
        "siren": "732829320",
        "siret": "73282932000074",
        "denomination": "Flotte Push Test",
        "adresse_ligne1": "1 rue du Test",
        "code_postal": "75001",
        "commune": "Paris",
        "pays": "FR",
        "type_flotte": "taxi",
        "source_enrichissement": "manuel",
        "created_by_id": user.id,
    }
    base.update(overrides)
    company = Company(**base)
    db_session.add(company)
    db_session.flush()
    return company


def _enable_vapid(monkeypatch: pytest.MonkeyPatch) -> None:
    """VAPID est désactivée par défaut dans toute la suite (`tests/conftest.py`) : seuls ces
    tests l'activent, en ne patchant que `app.services.push.get_settings` (même technique que
    `tests/unit/test_push.py`) pour ne pas affecter le reste de l'app (ex. `push-public-key`)."""
    from app.services import push

    def _settings() -> Settings:
        return Settings(
            jwt_secret="x" * 32,
            cron_secret="y" * 32,
            vapid_public_key="pub",
            vapid_private_key="priv",
        )

    monkeypatch.setattr(push, "get_settings", _settings)


def _subscribe_chauffeur(client: TestClient, chauffeur) -> str:
    login_client(client, chauffeur)
    response = client.post(
        "/api/v1/notifications/push-subscriptions",
        json={"endpoint": f"https://push.example/{uuid4()}", "p256dh": "k", "auth": "a"},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _create_and_plan_vehicle(client: TestClient, db_session: Session, admin) -> str:
    login_client(client, admin)
    company = _make_company(db_session, admin)
    created = client.post(
        "/api/v1/vehicles",
        json={
            "company_id": str(company.id),
            "marque": "Renault",
            "modele": "Kangoo",
            "date_proposition": TODAY.isoformat(),
        },
    )
    assert created.status_code == 201, created.text
    vehicle_id = created.json()["id"]
    planned = client.post(
        f"/api/v1/vehicles/{vehicle_id}/transitions",
        json={"to_state": "A_PLANIFIER", "reason": "validation"},
    )
    assert planned.status_code == 200, planned.text
    return vehicle_id


def _affect(client: TestClient, vehicle_id: str, driver_id) -> None:
    """Déclenche la création de la mission + de la notification, puis la tentative de push
    (`app/services/vehicles.py::transition_vehicle`, après le commit métier)."""
    response = client.post(
        f"/api/v1/vehicles/{vehicle_id}/transitions",
        json={"to_state": "AFFECTE", "payload": {"driver_id": str(driver_id)}},
    )
    assert response.status_code == 200, response.text


def test_transient_push_failure_does_not_fail_transition_nor_deactivate_subscription(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Timeout réseau simulé sur `webpush()` : la transition doit tout de même réussir et
    l'abonnement doit rester actif — c'était le bug bloquant (revue J2 § 🔴 n°7)."""
    pywebpush = pytest.importorskip("pywebpush")
    _enable_vapid(monkeypatch)

    def _flaky_webpush(**kwargs):
        raise TimeoutError("simulated network timeout")

    monkeypatch.setattr(pywebpush, "webpush", _flaky_webpush)

    admin = make_user(db_session, UserRole.ADMINISTRATEUR)
    chauffeur = make_user(db_session, UserRole.CHAUFFEUR)
    subscription_id = _subscribe_chauffeur(client, chauffeur)
    vehicle_id = _create_and_plan_vehicle(client, db_session, admin)

    _affect(client, vehicle_id, chauffeur.id)

    subscription = db_session.get(PushSubscription, subscription_id)
    assert subscription is not None
    assert subscription.is_active is True


def test_missing_pywebpush_extra_does_not_deactivate_subscription(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """VAPID configurée sans l'extra `webpush` installé (`requirements.txt` non régénéré) : le
    cas explicitement cité par la revue — ne doit désactiver aucun abonnement, cause = le
    déploiement, pas le navigateur du chauffeur."""
    pytest.importorskip("pywebpush")  # l'extra est bien présent dans ce venv de test/CI
    _enable_vapid(monkeypatch)
    monkeypatch.setitem(sys.modules, "pywebpush", None)

    admin = make_user(db_session, UserRole.ADMINISTRATEUR)
    chauffeur = make_user(db_session, UserRole.CHAUFFEUR)
    subscription_id = _subscribe_chauffeur(client, chauffeur)
    vehicle_id = _create_and_plan_vehicle(client, db_session, admin)

    _affect(client, vehicle_id, chauffeur.id)

    subscription = db_session.get(PushSubscription, subscription_id)
    assert subscription is not None
    assert subscription.is_active is True


def test_gone_response_deactivates_subscription(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """410 « Gone » du service de push : seul cas où l'abonnement doit être désactivé — la
    transition reste néanmoins gagnante (l'affectation n'est jamais annulée par le push)."""
    pywebpush = pytest.importorskip("pywebpush")
    _enable_vapid(monkeypatch)

    class _GoneResponse:
        status_code = 410
        reason = "Gone"
        text = "expired"

    def _gone_webpush(**kwargs):
        raise pywebpush.WebPushException("Push failed: 410 Gone", response=_GoneResponse())

    monkeypatch.setattr(pywebpush, "webpush", _gone_webpush)

    admin = make_user(db_session, UserRole.ADMINISTRATEUR)
    chauffeur = make_user(db_session, UserRole.CHAUFFEUR)
    subscription_id = _subscribe_chauffeur(client, chauffeur)
    vehicle_id = _create_and_plan_vehicle(client, db_session, admin)

    _affect(client, vehicle_id, chauffeur.id)

    subscription = db_session.get(PushSubscription, subscription_id)
    assert subscription is not None
    assert subscription.is_active is False


def test_push_call_carries_a_short_bounded_timeout_within_the_transition_request(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Vérifie, jusqu'au bout du chemin HTTP réel, qu'un délai maximal est bien transmis à
    `webpush()` — pas seulement au niveau de la fonction unitaire (`tests/unit/test_push.py`)."""
    pywebpush = pytest.importorskip("pywebpush")
    _enable_vapid(monkeypatch)

    calls: list[dict] = []

    def _capturing_webpush(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(pywebpush, "webpush", _capturing_webpush)

    admin = make_user(db_session, UserRole.ADMINISTRATEUR)
    chauffeur = make_user(db_session, UserRole.CHAUFFEUR)
    _subscribe_chauffeur(client, chauffeur)
    vehicle_id = _create_and_plan_vehicle(client, db_session, admin)

    _affect(client, vehicle_id, chauffeur.id)

    assert len(calls) == 1
    assert calls[0]["timeout"] == PUSH_TIMEOUT_SECONDS
    assert 0 < PUSH_TIMEOUT_SECONDS <= 5
