"""Matrice endpoint × rôle — plan.md § 3.4 : « un test d'intégration parcourt chaque endpoint
× chaque rôle et vérifie 200/403 ». Étage route uniquement (cloisonnement `require_roles`) ;
l'étage ligne (`scope_vehicles`) est couvert par `test_vehicles.py`.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.enums import UserRole
from tests.conftest import login_client, make_user

ALL_ROLES = tuple(UserRole)

VALID_COMPANY_BODY = {
    "siret": "73282932000074",
    "denomination": "Société Test",
    "adresse_ligne1": "1 rue du Test",
    "code_postal": "75001",
    "commune": "Paris",
    "type_flotte": "taxi",
    "source_enrichissement": "manuel",
}

VALID_VEHICLE_BODY = {
    "company_id": str(uuid4()),
    "marque": "Renault",
    "modele": "Kangoo",
    "date_proposition": "2026-08-01",
}

VALID_INTAKE_BATCH_BODY = {"company_id": str(uuid4()), "label": "Lot test"}

VALID_DUPLICATE_REVIEW_BODY = {
    "vehicle_a_id": str(uuid4()),
    "vehicle_b_id": str(uuid4()),
    "verdict": "not_duplicate",
    "score": 0.5,
    "features": {},
}

# (méthode, chemin, rôles autorisés, corps JSON éventuel)
ENDPOINT_CASES: list[tuple[str, str, tuple[UserRole, ...], dict | None]] = [
    (
        "GET",
        f"/api/v1/companies/lookup/{'73282932000074'}",
        (UserRole.OPERATRICE, UserRole.ADMINISTRATEUR),
        None,
    ),
    (
        "POST",
        "/api/v1/companies",
        (UserRole.OPERATRICE, UserRole.ADMINISTRATEUR),
        VALID_COMPANY_BODY,
    ),
    ("GET", "/api/v1/companies", (UserRole.OPERATRICE, UserRole.ADMINISTRATEUR), None),
    ("GET", f"/api/v1/companies/{uuid4()}", (UserRole.OPERATRICE, UserRole.ADMINISTRATEUR), None),
    (
        "POST",
        "/api/v1/vehicles/duplicate-check",
        (UserRole.OPERATRICE, UserRole.ADMINISTRATEUR),
        VALID_VEHICLE_BODY,
    ),
    (
        "POST",
        "/api/v1/vehicles",
        (UserRole.OPERATRICE, UserRole.ADMINISTRATEUR),
        VALID_VEHICLE_BODY,
    ),
    ("GET", "/api/v1/vehicles", ALL_ROLES, None),
    ("GET", f"/api/v1/vehicles/{uuid4()}", ALL_ROLES, None),
    ("GET", f"/api/v1/vehicles/{uuid4()}/transitions", ALL_ROLES, None),
    (
        "PATCH",
        f"/api/v1/vehicles/{uuid4()}",
        (UserRole.OPERATRICE, UserRole.ADMINISTRATEUR),
        {"commentaire": "test"},
    ),
    (
        "POST",
        "/api/v1/intake-batches",
        (UserRole.OPERATRICE, UserRole.ADMINISTRATEUR),
        VALID_INTAKE_BATCH_BODY,
    ),
    (
        "POST",
        "/api/v1/duplicate-reviews",
        (UserRole.OPERATRICE, UserRole.ADMINISTRATEUR),
        VALID_DUPLICATE_REVIEW_BODY,
    ),
]


_MATRIX = [
    (method, path, allowed_roles, body, role)
    for method, path, allowed_roles, body in ENDPOINT_CASES
    for role in ALL_ROLES
]


@pytest.mark.parametrize(
    "method,path,allowed_roles,body,role",
    _MATRIX,
    ids=[f"{m}:{p}:{r.value}" for m, p, _a, _b, r in _MATRIX],
)
def test_endpoint_role_matrix(
    client: TestClient,
    db_session: Session,
    method: str,
    path: str,
    allowed_roles: tuple[UserRole, ...],
    body: dict | None,
    role: UserRole,
) -> None:
    user = make_user(db_session, role)
    login_client(client, user)

    response = client.request(method, path, json=body)

    if role in allowed_roles:
        assert (
            response.status_code != 403
        ), f"{method} {path} rôle {role.value} (autorisé) a reçu 403 : {response.text}"
    else:
        assert response.status_code == 403, (
            f"{method} {path} rôle {role.value} (non autorisé) attendu 403, "
            f"obtenu {response.status_code} : {response.text}"
        )
        assert response.json()["error"]["code"] == "forbidden_role"


def test_unauthenticated_request_is_401_not_403(client: TestClient) -> None:
    """Sans cookie, l'erreur est `unauthenticated` (401), jamais `forbidden_role` (403)."""
    response = client.get("/api/v1/vehicles")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_chauffeur_sees_no_vehicles_without_assignment(
    client: TestClient, db_session: Session
) -> None:
    """Étage ligne minimal : un chauffeur sans mission active reçoit une liste vide, pas 403."""
    chauffeur = make_user(db_session, UserRole.CHAUFFEUR)
    login_client(client, chauffeur)

    response = client.get("/api/v1/vehicles")
    assert response.status_code == 200
    assert response.json()["items"] == []
