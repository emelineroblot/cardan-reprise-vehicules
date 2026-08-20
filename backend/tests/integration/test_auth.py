"""`POST /auth/login`, `POST /auth/logout`, `GET /auth/me` — plan.md § 6 vague 1."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password
from app.models.enums import UserRole
from app.models.user import AppUser
from tests.conftest import login_client, make_user

settings = get_settings()


def test_login_ok_sets_httponly_cookie(client: TestClient, db_session: Session) -> None:
    user = AppUser(
        id=__import__("uuid").uuid4(),
        email="claire@example.com",
        password_hash=hash_password("s3cret-pass"),
        full_name="Claire",
        role=UserRole.OPERATRICE.value,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    response = client.post(
        "/api/v1/auth/login", json={"email": "claire@example.com", "password": "s3cret-pass"}
    )
    assert response.status_code == 200
    assert response.json()["email"] == "claire@example.com"
    assert settings.session_cookie_name in response.cookies

    set_cookie_header = response.headers.get("set-cookie", "")
    assert "HttpOnly" in set_cookie_header


def test_login_wrong_password_returns_401(client: TestClient, db_session: Session) -> None:
    user = AppUser(
        id=__import__("uuid").uuid4(),
        email="wrong@example.com",
        password_hash=hash_password("correct-pass"),
        full_name="Wrong",
        role=UserRole.OPERATRICE.value,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    response = client.post(
        "/api/v1/auth/login", json={"email": "wrong@example.com", "password": "incorrect"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_login_unknown_email_returns_401_not_404(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login", json={"email": "ghost@example.com", "password": "whatever"}
    )
    assert response.status_code == 401


def test_login_inactive_account_returns_401(client: TestClient, db_session: Session) -> None:
    user = AppUser(
        id=__import__("uuid").uuid4(),
        email="inactive@example.com",
        password_hash=hash_password("s3cret-pass"),
        full_name="Inactive",
        role=UserRole.OPERATRICE.value,
        is_active=False,
    )
    db_session.add(user)
    db_session.flush()

    response = client.post(
        "/api/v1/auth/login", json={"email": "inactive@example.com", "password": "s3cret-pass"}
    )
    assert response.status_code == 401


def test_me_without_cookie_returns_401(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_me_with_valid_cookie_returns_user(client: TestClient, db_session: Session) -> None:
    user = make_user(db_session, UserRole.ADMINISTRATEUR)
    login_client(client, user)

    response = client.get("/api/v1/auth/me")
    assert response.status_code == 200
    assert response.json()["role"] == "administrateur"


def test_logout_clears_cookie(client: TestClient, db_session: Session) -> None:
    # Connexion via le vrai endpoint (et non `login_client`, qui injecte le cookie sans passer
    # par une réponse HTTP réelle) : la suppression de cookie dépend du `domain` implicite posé
    # par `Set-Cookie`, que seul un aller-retour HTTP complet reproduit fidèlement.
    user = AppUser(
        id=__import__("uuid").uuid4(),
        email="logout@example.com",
        password_hash=hash_password("s3cret-pass"),
        full_name="Logout",
        role=UserRole.OPERATRICE.value,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    login_response = client.post(
        "/api/v1/auth/login", json={"email": "logout@example.com", "password": "s3cret-pass"}
    )
    assert login_response.status_code == 200

    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 200

    me_response = client.get("/api/v1/auth/me")
    assert me_response.status_code == 401


def test_expired_token_returns_401(client: TestClient, db_session: Session) -> None:
    user = make_user(db_session, UserRole.OPERATRICE)
    expired_payload = {
        "sub": str(user.id),
        "role": user.role,
        "iat": datetime.now(UTC) - timedelta(hours=13),
        "exp": datetime.now(UTC) - timedelta(hours=1),
    }
    expired_token = jwt.encode(
        expired_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm
    )
    client.cookies.set(settings.session_cookie_name, expired_token)

    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_tampered_token_returns_401(client: TestClient, db_session: Session) -> None:
    user = make_user(db_session, UserRole.OPERATRICE)
    tampered = jwt.encode(
        {"sub": str(user.id), "role": user.role}, "wrong-secret", algorithm=settings.jwt_algorithm
    )
    client.cookies.set(settings.session_cookie_name, tampered)

    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_deactivated_user_with_valid_token_returns_401(
    client: TestClient, db_session: Session
) -> None:
    """Un jeton valide mais un compte désactivé après coup doit être refusé (garde-fou)."""
    user = make_user(db_session, UserRole.OPERATRICE)
    login_client(client, user)
    user.is_active = False
    db_session.flush()

    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
