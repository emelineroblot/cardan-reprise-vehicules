"""Parcours terrain complet J2 — affectation → rendez-vous → contrôle → photos guidées →
soumission → validation d'achat (brief J2, plan.md § 5.3).

Couvre bout en bout : création de `mission` et de `notification` à l'affectation (effets de
`POST /vehicles/{id}/transitions`, `app/services/vehicles.py`), parcours d'angles imposé
(`app/services/photos.py`), complétude de checklist avant soumission
(`app/services/inspections.py`), et clôture de la mission à la sortie de `CONTROLE_EN_COURS`.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.enums import PhotoAngle, UserRole
from app.models.mission import Mission
from app.models.notification import Notification
from app.seed.reference import seed_reference
from tests.conftest import login_client, make_user

TODAY = date(2026, 8, 20)
REQUIRED_ANGLES = [angle.value for angle in PhotoAngle if angle != PhotoAngle.DEFAUT]


def _make_company(db_session: Session, user, **overrides) -> Company:
    base = {
        "id": uuid4(),
        "siren": "732829320",
        "siret": "73282932000074",
        "denomination": "Flotte Terrain Test",
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


def _upload_photo(client: TestClient, vehicle_id: str, *, inspection_id: str, angle: str) -> dict:
    content = f"contenu-photo-{angle}".encode()
    checksum = hashlib.sha256(content).hexdigest()
    response = client.post(
        f"/api/v1/vehicles/{vehicle_id}/photos",
        data={
            "client_uuid": str(uuid4()),
            "angle": angle,
            "phase": "controle",
            "inspection_id": inspection_id,
            "captured_at": datetime.now().isoformat(),
            "checksum_sha256": checksum,
            "width": "1600",
            "height": "1200",
        },
        files={"file": ("photo.jpg", content, "image/jpeg")},
    )
    return response


def test_full_terrain_flow_creates_mission_notification_and_completes_inspection(
    client: TestClient, db_session: Session
) -> None:
    from app.models.checklist import ChecklistItemTemplate

    seed_reference(db_session)

    admin = make_user(db_session, UserRole.ADMINISTRATEUR)
    chauffeur = make_user(db_session, UserRole.CHAUFFEUR)

    login_client(client, admin)
    company = _make_company(db_session, admin)
    vehicle_id = _create_vehicle(client, company.id)

    # BROUILLON -> A_PLANIFIER -> AFFECTE (crée la mission + la notification)
    client.post(
        f"/api/v1/vehicles/{vehicle_id}/transitions",
        json={"to_state": "A_PLANIFIER", "reason": "validation"},
    )
    affect = client.post(
        f"/api/v1/vehicles/{vehicle_id}/transitions",
        json={"to_state": "AFFECTE", "payload": {"driver_id": str(chauffeur.id)}},
    )
    assert affect.status_code == 200, affect.text

    mission = db_session.scalar(select(Mission).where(Mission.vehicle_id == vehicle_id))
    assert mission is not None
    assert mission.state == "affectee"
    assert mission.driver_id == chauffeur.id

    notification = db_session.scalar(
        select(Notification).where(Notification.user_id == chauffeur.id)
    )
    assert notification is not None
    assert notification.type == "mission_affectee"
    assert notification.read_at is None

    # Le chauffeur voit sa notification et sa mission.
    login_client(client, chauffeur)
    notif_list = client.get("/api/v1/notifications")
    assert notif_list.status_code == 200
    assert notif_list.json()["total"] == 1
    unread = client.get("/api/v1/notifications/unread-count")
    assert unread.json()["count"] == 1

    missions_list = client.get("/api/v1/missions")
    assert missions_list.status_code == 200
    assert missions_list.json()["total"] == 1
    assert missions_list.json()["items"][0]["vehicle"]["reference"]

    # AFFECTE -> RDV_PLANIFIE
    rdv_at = (datetime.now() + timedelta(days=2)).isoformat()
    rdv = client.post(
        f"/api/v1/vehicles/{vehicle_id}/transitions",
        json={
            "to_state": "RDV_PLANIFIE",
            "payload": {
                "rdv_at": rdv_at,
                "rdv_adresse": "12 avenue du Dépôt, Nantes",
                "rdv_contact_nom": "M. Dupont",
                "rdv_contact_telephone": "0601020304",
            },
        },
    )
    assert rdv.status_code == 200, rdv.text
    db_session.refresh(mission)
    assert mission.state == "rdv_planifie"
    assert mission.rdv_adresse == "12 avenue du Dépôt, Nantes"

    # RDV_PLANIFIE -> CONTROLE_EN_COURS
    start = client.post(
        f"/api/v1/vehicles/{vehicle_id}/transitions", json={"to_state": "CONTROLE_EN_COURS"}
    )
    assert start.status_code == 200, start.text
    db_session.refresh(mission)
    assert mission.state == "en_cours"

    # Création idempotente de l'inspection.
    client_uuid = str(uuid4())
    create_1 = client.post(
        "/api/v1/inspections",
        json={"client_uuid": client_uuid, "vehicle_id": vehicle_id},
    )
    assert create_1.status_code == 201, create_1.text
    inspection_id = create_1.json()["id"]

    create_2 = client.post(
        "/api/v1/inspections",
        json={"client_uuid": client_uuid, "vehicle_id": vehicle_id},
    )
    assert create_2.status_code == 200  # rejeu idempotent, pas de doublon
    assert create_2.json()["id"] == inspection_id

    # Soumission refusée tant que les items obligatoires et les 12 angles ne sont pas complets.
    submit_incomplete = client.post(f"/api/v1/inspections/{inspection_id}/submit", json={})
    assert submit_incomplete.status_code == 409
    assert submit_incomplete.json()["error"]["code"] == "inspection_incomplete"
    assert len(submit_incomplete.json()["error"]["details"]["missing_angles"]) == 12
    assert len(submit_incomplete.json()["error"]["details"]["missing_items"]) > 0

    # Renseigne tous les items obligatoires du référentiel.
    templates = list(db_session.scalars(select(ChecklistItemTemplate)).all())
    response_by_type = {
        "ok_ko": {"valeur_bool": True},
        "note_1_5": {"valeur_note": 4},
        "texte": {"valeur_texte": "RAS"},
        "numerique": {"valeur_num": 42000},
    }
    items_payload = [
        {"item_template_id": str(t.id), **response_by_type[t.response_type]}
        for t in templates
        if t.is_required
    ]
    put_items = client.put(
        f"/api/v1/inspections/{inspection_id}/items", json={"items": items_payload}
    )
    assert put_items.status_code == 200, put_items.text

    submit_missing_angles = client.post(f"/api/v1/inspections/{inspection_id}/submit", json={})
    assert submit_missing_angles.status_code == 409
    assert submit_missing_angles.json()["error"]["details"]["missing_items"] == []

    # Parcours d'angles imposé — capture les 12 angles requis.
    required = client.get(
        f"/api/v1/vehicles/{vehicle_id}/photos/required-angles",
        params={"inspection_id": inspection_id},
    )
    assert required.status_code == 200
    assert set(required.json()["missing_angles"]) == set(REQUIRED_ANGLES)

    for angle in REQUIRED_ANGLES:
        upload = _upload_photo(client, vehicle_id, inspection_id=inspection_id, angle=angle)
        assert upload.status_code == 201, upload.text

    required_after = client.get(
        f"/api/v1/vehicles/{vehicle_id}/photos/required-angles",
        params={"inspection_id": inspection_id},
    )
    assert required_after.json()["missing_angles"] == []

    submit_ok = client.post(
        f"/api/v1/inspections/{inspection_id}/submit",
        json={"conclusion": "achat_direct", "kilometrage_releve": 42000, "etat_general": "bon"},
    )
    assert submit_ok.status_code == 200, submit_ok.text
    assert submit_ok.json()["submitted_at"] is not None

    # Rejeu idempotent de la soumission.
    submit_replay = client.post(f"/api/v1/inspections/{inspection_id}/submit", json={})
    assert submit_replay.status_code == 200

    # Le bouton « achat validé » n'est disponible qu'une fois l'inspection soumise.
    allowed = client.get(f"/api/v1/vehicles/{vehicle_id}/transitions")
    assert "ACHAT_VALIDE" in {opt["to_state"] for opt in allowed.json()["allowed"]}

    achat = client.post(
        f"/api/v1/vehicles/{vehicle_id}/transitions",
        json={"to_state": "ACHAT_VALIDE", "payload": {"prix_achat_negocie_cents": 500000}},
    )
    assert achat.status_code == 200, achat.text
    assert achat.json()["state"] == "ACHAT_VALIDE"

    db_session.refresh(mission)
    assert mission.state == "terminee"
    assert mission.completed_at is not None


def test_reassignment_cancels_previous_mission_and_notifies_new_driver(
    client: TestClient, db_session: Session
) -> None:
    admin = make_user(db_session, UserRole.ADMINISTRATEUR)
    first_driver = make_user(db_session, UserRole.CHAUFFEUR)
    second_driver = make_user(db_session, UserRole.CHAUFFEUR)
    login_client(client, admin)
    company = _make_company(db_session, admin)
    vehicle_id = _create_vehicle(client, company.id)

    client.post(
        f"/api/v1/vehicles/{vehicle_id}/transitions",
        json={"to_state": "A_PLANIFIER", "reason": "validation"},
    )
    client.post(
        f"/api/v1/vehicles/{vehicle_id}/transitions",
        json={"to_state": "AFFECTE", "payload": {"driver_id": str(first_driver.id)}},
    )
    reassign = client.post(
        f"/api/v1/vehicles/{vehicle_id}/transitions",
        json={"to_state": "AFFECTE", "payload": {"driver_id": str(second_driver.id)}},
    )
    assert reassign.status_code == 200, reassign.text

    missions = list(
        db_session.scalars(select(Mission).where(Mission.vehicle_id == vehicle_id)).all()
    )
    assert len(missions) == 2
    by_driver = {m.driver_id: m for m in missions}
    assert by_driver[first_driver.id].state == "annulee"
    assert by_driver[second_driver.id].state == "affectee"

    notifications = list(
        db_session.scalars(
            select(Notification).where(Notification.user_id == second_driver.id)
        ).all()
    )
    assert len(notifications) == 1


def test_inspection_creation_rejected_outside_controle_en_cours(
    client: TestClient, db_session: Session
) -> None:
    admin = make_user(db_session, UserRole.ADMINISTRATEUR)
    chauffeur = make_user(db_session, UserRole.CHAUFFEUR)
    login_client(client, admin)
    company = _make_company(db_session, admin)
    vehicle_id = _create_vehicle(client, company.id)

    # Affecté (donc visible pour ce chauffeur via `scope_vehicles`), mais encore en
    # `A_PLANIFIER` — la garde d'état de `get_or_create_inspection` doit refuser, pas l'étage
    # ligne du cloisonnement.
    client.post(
        f"/api/v1/vehicles/{vehicle_id}/transitions",
        json={"to_state": "A_PLANIFIER", "reason": "validation"},
    )
    client.post(
        f"/api/v1/vehicles/{vehicle_id}/transitions",
        json={"to_state": "AFFECTE", "payload": {"driver_id": str(chauffeur.id)}},
    )

    login_client(client, chauffeur)
    response = client.post(
        "/api/v1/inspections",
        json={"client_uuid": str(uuid4()), "vehicle_id": vehicle_id},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "inspection_not_allowed"


def test_chauffeur_cannot_create_inspection_for_someone_elses_mission(
    client: TestClient, db_session: Session
) -> None:
    from app.models.vehicle import Vehicle

    admin = make_user(db_session, UserRole.ADMINISTRATEUR)
    assigned_driver = make_user(db_session, UserRole.CHAUFFEUR)
    other_driver = make_user(db_session, UserRole.CHAUFFEUR)
    login_client(client, admin)
    company = _make_company(db_session, admin)
    vehicle_id = _create_vehicle(client, company.id)

    client.post(
        f"/api/v1/vehicles/{vehicle_id}/transitions",
        json={"to_state": "A_PLANIFIER", "reason": "validation"},
    )
    client.post(
        f"/api/v1/vehicles/{vehicle_id}/transitions",
        json={"to_state": "AFFECTE", "payload": {"driver_id": str(assigned_driver.id)}},
    )

    vehicle = db_session.get(Vehicle, vehicle_id)
    vehicle.state = "CONTROLE_EN_COURS"
    db_session.flush()

    login_client(client, other_driver)
    response = client.post(
        "/api/v1/inspections",
        json={"client_uuid": str(uuid4()), "vehicle_id": vehicle_id},
    )
    # Le véhicule n'est pas visible pour ce chauffeur (non affecté) -> 404, pas de fuite d'info.
    assert response.status_code == 404
