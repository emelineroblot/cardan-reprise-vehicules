"""Cloisonnement chauffeur sur `/missions/*` — étage LIGNE (`Mission.driver_id == user.id`),
complément à `test_rbac_matrix.py` qui ne couvre que l'étage ROLE (`require_roles`). Brief J2 :
« un chauffeur ne peut ni lire ni écrire sur une mission qui n'est pas la sienne »."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.enums import UserRole
from tests.conftest import login_client, make_user

TODAY = date(2026, 8, 20)


def _make_company(db_session: Session, user) -> Company:
    company = Company(
        id=uuid4(),
        siren="732829320",
        siret="73282932000074",
        denomination="Flotte Scoping Test",
        adresse_ligne1="1 rue du Test",
        code_postal="75001",
        commune="Paris",
        pays="FR",
        type_flotte="taxi",
        source_enrichissement="manuel",
        created_by_id=user.id,
    )
    db_session.add(company)
    db_session.flush()
    return company


def _create_vehicle(client: TestClient, company_id) -> str:
    response = client.post(
        "/api/v1/vehicles",
        json={
            "company_id": str(company_id),
            "marque": "Renault",
            "modele": "Kangoo",
            "date_proposition": TODAY.isoformat(),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_chauffeur_cannot_read_another_drivers_mission_detail(
    client: TestClient, db_session: Session
) -> None:
    admin = make_user(db_session, UserRole.ADMINISTRATEUR)
    owner = make_user(db_session, UserRole.CHAUFFEUR)
    other = make_user(db_session, UserRole.CHAUFFEUR)

    login_client(client, admin)
    company = _make_company(db_session, admin)
    vehicle_id = _create_vehicle(client, company.id)
    client.post(
        f"/api/v1/vehicles/{vehicle_id}/transitions",
        json={"to_state": "A_PLANIFIER", "reason": "validation"},
    )
    affect = client.post(
        f"/api/v1/vehicles/{vehicle_id}/transitions",
        json={"to_state": "AFFECTE", "payload": {"driver_id": str(owner.id)}},
    )
    assert affect.status_code == 200, affect.text

    login_client(client, owner)
    own_missions = client.get("/api/v1/missions").json()
    assert own_missions["total"] == 1
    mission_id = own_missions["items"][0]["id"]
    own_read = client.get(f"/api/v1/missions/{mission_id}")
    assert own_read.status_code == 200

    # Le second chauffeur ne doit ni la voir dans sa liste, ni pouvoir la lire par id — 404
    # uniforme (pas de fuite d'existence), même principe que les inspections/photos.
    login_client(client, other)
    other_list = client.get("/api/v1/missions").json()
    assert other_list["total"] == 0
    other_read = client.get(f"/api/v1/missions/{mission_id}")
    assert other_read.status_code == 404
    assert other_read.json()["error"]["code"] == "not_found"


def test_chauffeur_driver_id_query_param_is_ignored_for_own_scope(
    client: TestClient, db_session: Session
) -> None:
    """`GET /missions?driver_id=<autre>` — le paramètre est ignoré pour un chauffeur (seul
    l'administrateur peut filtrer par `driver_id`, `missions.py::list_missions`)."""
    admin = make_user(db_session, UserRole.ADMINISTRATEUR)
    owner = make_user(db_session, UserRole.CHAUFFEUR)
    other = make_user(db_session, UserRole.CHAUFFEUR)

    login_client(client, admin)
    company = _make_company(db_session, admin)
    vehicle_id = _create_vehicle(client, company.id)
    client.post(
        f"/api/v1/vehicles/{vehicle_id}/transitions",
        json={"to_state": "A_PLANIFIER", "reason": "validation"},
    )
    client.post(
        f"/api/v1/vehicles/{vehicle_id}/transitions",
        json={"to_state": "AFFECTE", "payload": {"driver_id": str(owner.id)}},
    )

    login_client(client, other)
    attempt = client.get("/api/v1/missions", params={"driver_id": str(owner.id)})
    assert attempt.status_code == 200
    assert attempt.json()["total"] == 0  # toujours scopé sur `other`, pas sur `owner`.
