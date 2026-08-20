"""`GET /users` — dette J1 (brief J2 : alimente le `<Select>` chauffeur de
« Affectation d'un chauffeur » côté front)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.enums import UserRole
from tests.conftest import login_client, make_user


def test_list_users_filtered_by_role_chauffeur(client: TestClient, db_session: Session) -> None:
    admin = make_user(db_session, UserRole.ADMINISTRATEUR)
    chauffeur = make_user(db_session, UserRole.CHAUFFEUR, email="karim@cardan.demo")
    make_user(db_session, UserRole.OPERATRICE, email="claire@cardan.demo")
    login_client(client, admin)

    response = client.get("/api/v1/users", params={"role": "chauffeur"})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == str(chauffeur.id)
    assert body["items"][0]["role"] == "chauffeur"


def test_list_users_rejects_unknown_role(client: TestClient, db_session: Session) -> None:
    admin = make_user(db_session, UserRole.ADMINISTRATEUR)
    login_client(client, admin)

    response = client.get("/api/v1/users", params={"role": "pdg"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_list_users_forbidden_for_non_admin(client: TestClient, db_session: Session) -> None:
    operatrice = make_user(db_session, UserRole.OPERATRICE)
    login_client(client, operatrice)

    response = client.get("/api/v1/users", params={"role": "chauffeur"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden_role"


def test_list_users_filters_inactive(client: TestClient, db_session: Session) -> None:
    admin = make_user(db_session, UserRole.ADMINISTRATEUR)
    chauffeur = make_user(db_session, UserRole.CHAUFFEUR, email="inactif@cardan.demo")
    chauffeur.is_active = False
    db_session.flush()
    login_client(client, admin)

    response = client.get("/api/v1/users", params={"role": "chauffeur", "is_active": True})
    assert response.status_code == 200
    assert response.json()["total"] == 0
