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
# `app/api/v1/work_orders.py::_READ_ROLES` — ordres de travaux et coûts hors atelier sont des
# données financières (revue J3, 🔴), le chauffeur en est explicitement exclu.
_WORK_ORDER_READ_ROLES = (UserRole.ATELIER, UserRole.OPERATRICE, UserRole.ADMINISTRATEUR)

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

# (méthode, chemin, rôles autorisés, corps JSON éventuel, code attendu pour un rôle autorisé)
#
# Bug corrigé (revue J3, 🟡 n°1) : la version précédente n'assertait, pour un rôle autorisé, que
# `!= 500` et `!= 403` — un `404`/`409`/`422` inattendu sur un chemin nominal validait quand même
# le test. Chaque `expected_status` ci-dessous a été déterminé en instrumentant temporairement
# cette même fonction pour imprimer le code réel obtenu par chaque (méthode, chemin, rôle
# autorisé) contre le backend réel (`pytest -s`), jamais deviné : la plupart des routes prenant un
# identifiant en chemin (`{uuid4()}`) référencent volontairement une ressource inexistante — leur
# comportement nominal correct pour un rôle autorisé est donc `404 not_found` (la barrière de rôle
# a laissé passer, la ressource n'existe simplement pas), pas `200`. `POST /vehicles`,
# `/intake-batches`, `/duplicate-reviews` et `/inspections` référencent de même un `company_id`/
# `vehicle_id` fictif dans leur corps → `404` (violation de clé étrangère résolue en `404`, pas en
# `500`). Seule `GET /companies/lookup/{siret}` répond `503 siret_lookup_unavailable` — décision
# métier délibérée (`COMPANY_LOOKUP_PROVIDER=disabled` en test), pas un défaut.
ENDPOINT_CASES: list[tuple[str, str, tuple[UserRole, ...], dict | None, int]] = [
    (
        "GET",
        f"/api/v1/companies/lookup/{'73282932000074'}",
        (UserRole.OPERATRICE, UserRole.ADMINISTRATEUR),
        None,
        503,
    ),
    (
        "POST",
        "/api/v1/companies",
        (UserRole.OPERATRICE, UserRole.ADMINISTRATEUR),
        VALID_COMPANY_BODY,
        201,
    ),
    ("GET", "/api/v1/companies", (UserRole.OPERATRICE, UserRole.ADMINISTRATEUR), None, 200),
    (
        "GET",
        f"/api/v1/companies/{uuid4()}",
        (UserRole.OPERATRICE, UserRole.ADMINISTRATEUR),
        None,
        404,
    ),
    (
        "POST",
        "/api/v1/vehicles/duplicate-check",
        (UserRole.OPERATRICE, UserRole.ADMINISTRATEUR),
        VALID_VEHICLE_BODY,
        200,
    ),
    (
        "POST",
        "/api/v1/vehicles",
        (UserRole.OPERATRICE, UserRole.ADMINISTRATEUR),
        VALID_VEHICLE_BODY,
        404,  # company_id de VALID_VEHICLE_BODY est un uuid4() fictif
    ),
    ("GET", "/api/v1/vehicles", ALL_ROLES, None, 200),
    ("GET", f"/api/v1/vehicles/{uuid4()}", ALL_ROLES, None, 404),
    ("GET", f"/api/v1/vehicles/{uuid4()}/transitions", ALL_ROLES, None, 404),
    (
        "PATCH",
        f"/api/v1/vehicles/{uuid4()}",
        (UserRole.OPERATRICE, UserRole.ADMINISTRATEUR),
        {"commentaire": "test"},
        404,
    ),
    (
        "POST",
        "/api/v1/intake-batches",
        (UserRole.OPERATRICE, UserRole.ADMINISTRATEUR),
        VALID_INTAKE_BATCH_BODY,
        404,  # company_id fictif
    ),
    (
        "POST",
        "/api/v1/duplicate-reviews",
        (UserRole.OPERATRICE, UserRole.ADMINISTRATEUR),
        VALID_DUPLICATE_REVIEW_BODY,
        404,  # vehicle_a_id/vehicle_b_id fictifs
    ),
    # J2 — brief : missions, inspections, notifications. Les endpoints multipart
    # (`POST /vehicles/{id}/photos`) sont couverts séparément par `test_photos.py`, incompatibles
    # avec le corps JSON générique de cette matrice.
    ("GET", "/api/v1/users", (UserRole.ADMINISTRATEUR,), None, 200),
    ("GET", "/api/v1/missions", (UserRole.CHAUFFEUR, UserRole.ADMINISTRATEUR), None, 200),
    (
        "GET",
        f"/api/v1/missions/{uuid4()}",
        (UserRole.CHAUFFEUR, UserRole.ADMINISTRATEUR),
        None,
        404,
    ),
    (
        "POST",
        "/api/v1/inspections",
        (UserRole.CHAUFFEUR,),
        {"client_uuid": str(uuid4()), "vehicle_id": str(uuid4())},
        404,  # vehicle_id fictif
    ),
    (
        "GET",
        f"/api/v1/inspections/{uuid4()}",
        (UserRole.CHAUFFEUR, UserRole.ADMINISTRATEUR),
        None,
        404,
    ),
    ("GET", "/api/v1/notifications", ALL_ROLES, None, 200),
    ("GET", "/api/v1/notifications/unread-count", ALL_ROLES, None, 200),
    ("GET", "/api/v1/notifications/push-public-key", ALL_ROLES, None, 200),
    (
        "POST",
        "/api/v1/notifications/push-subscriptions",
        ALL_ROLES,
        {"endpoint": f"https://push.example/{uuid4()}", "p256dh": "k", "auth": "a"},
        201,
    ),
    # Référentiel de checklist (revue orchestrateur J2) — donnée de référence sans caractère
    # sensible, ouverte à tout rôle authentifié.
    ("GET", "/api/v1/checklist-templates", ALL_ROLES, None, 200),
    ("GET", f"/api/v1/checklist-templates/{uuid4()}", ALL_ROLES, None, 404),
    # J3 — atelier, coûts hors atelier, Kanban (implementation.md § « J3 — Backend »). Absents de
    # cette matrice jusqu'ici : aucun des 798 tests backend ne couvrait le cloisonnement de rôle
    # de ces endpoints par ce mécanisme centralisé (seulement par des assertions ponctuelles dans
    # `test_atelier_flow.py`) — complété en réponse à la consigne de l'orchestrateur de ce
    # jalon (« complète ce qui manque »). Les `GET` scopés par véhicule ne sont **pas** ouverts à
    # tout rôle authentifié : `work_order`/`vehicle_cost` sont des données financières au même
    # titre que `prix_achat_negocie_cents` (revue J3, 🔴 — cloisonnement corrigé dans
    # `app/api/v1/work_orders.py::_READ_ROLES`, le chauffeur en était exclu après coup). Rôles
    # alignés sur `_READ_ROLES`/`_ATELIER_WRITE_ROLES`/`_COST_WRITE_ROLES` de ce fichier.
    ("GET", f"/api/v1/vehicles/{uuid4()}/work-orders", _WORK_ORDER_READ_ROLES, None, 404),
    ("GET", f"/api/v1/work-orders/{uuid4()}", _WORK_ORDER_READ_ROLES, None, 404),
    (
        "POST",
        f"/api/v1/work-orders/{uuid4()}/state",
        (UserRole.ATELIER, UserRole.ADMINISTRATEUR),
        {"to_state": "en_cours"},
        404,
    ),
    (
        "POST",
        f"/api/v1/work-orders/{uuid4()}/lines",
        (UserRole.ATELIER, UserRole.ADMINISTRATEUR),
        {
            "libelle": "Test",
            "categorie": "piece",
            "quantite": "1",
            "prix_unitaire_cents": 1000,
        },
        404,
    ),
    ("GET", f"/api/v1/vehicles/{uuid4()}/costs", _WORK_ORDER_READ_ROLES, None, 404),
    (
        "POST",
        f"/api/v1/vehicles/{uuid4()}/costs",
        (UserRole.ADMINISTRATEUR,),
        {"type": "transport", "montant_cents": 1000},
        404,
    ),
    ("GET", "/api/v1/vehicles/pipeline-counts", (UserRole.ADMINISTRATEUR,), None, 200),
]


_MATRIX = [
    (method, path, allowed_roles, body, expected_status, role)
    for method, path, allowed_roles, body, expected_status in ENDPOINT_CASES
    for role in ALL_ROLES
]


@pytest.mark.parametrize(
    "method,path,allowed_roles,body,expected_status,role",
    _MATRIX,
    ids=[f"{m}:{p}:{r.value}" for m, p, _a, _b, _e, r in _MATRIX],
)
def test_endpoint_role_matrix(
    client: TestClient,
    db_session: Session,
    method: str,
    path: str,
    allowed_roles: tuple[UserRole, ...],
    body: dict | None,
    expected_status: int,
    role: UserRole,
) -> None:
    user = make_user(db_session, role)
    login_client(client, user)

    response = client.request(method, path, json=body)

    if role in allowed_roles:
        # Renforcé (dev-tester, jalon J3, puis resserré lors de la revue de `tests-j3.md`) :
        # assertion exacte sur le code attendu — plus seulement `!= 500`/`!= 403`, qui laissait
        # passer un `404`/`409`/`422` imprévu sur un rôle légitimement autorisé.
        assert response.status_code == expected_status, (
            f"{method} {path} rôle {role.value} (autorisé) attendu {expected_status}, "
            f"obtenu {response.status_code} : {response.text}"
        )
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
