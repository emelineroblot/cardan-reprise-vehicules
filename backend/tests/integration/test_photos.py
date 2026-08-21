"""Photos guidées — idempotence, plafond par véhicule, angle dupliqué, checksum, lecture
scopée (plan.md § 3.6, § 4 décision C)."""

from __future__ import annotations

import hashlib
from datetime import date, datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.enums import UserRole
from app.models.photo import Photo
from app.models.vehicle import Vehicle
from app.seed.reference import seed_reference
from tests.conftest import login_client, make_user

TODAY = date(2026, 8, 20)


def _make_company(db_session: Session, user, **overrides) -> Company:
    base = {
        "id": uuid4(),
        "siren": "732829320",
        "siret": "73282932000074",
        "denomination": "Flotte Photos Test",
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


def _setup_vehicle_in_control(client: TestClient, db_session: Session, admin, chauffeur) -> str:
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
    vehicle_id = created.json()["id"]
    client.post(
        f"/api/v1/vehicles/{vehicle_id}/transitions",
        json={"to_state": "A_PLANIFIER", "reason": "validation"},
    )
    client.post(
        f"/api/v1/vehicles/{vehicle_id}/transitions",
        json={"to_state": "AFFECTE", "payload": {"driver_id": str(chauffeur.id)}},
    )
    vehicle = db_session.get(Vehicle, vehicle_id)
    vehicle.state = "CONTROLE_EN_COURS"
    db_session.flush()
    return vehicle_id


def _create_inspection(client: TestClient, vehicle_id: str) -> str:
    response = client.post(
        "/api/v1/inspections", json={"client_uuid": str(uuid4()), "vehicle_id": vehicle_id}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _upload(
    client: TestClient,
    vehicle_id: str,
    *,
    inspection_id: str,
    angle: str = "face_avant",
    client_uuid: str | None = None,
    content: bytes = b"contenu-photo",
    checksum: str | None = None,
):
    checksum = checksum or hashlib.sha256(content).hexdigest()
    return client.post(
        f"/api/v1/vehicles/{vehicle_id}/photos",
        data={
            "client_uuid": client_uuid or str(uuid4()),
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


def test_photo_upload_idempotent_by_client_uuid(client: TestClient, db_session: Session) -> None:
    seed_reference(db_session)
    admin = make_user(db_session, UserRole.ADMINISTRATEUR)
    chauffeur = make_user(db_session, UserRole.CHAUFFEUR)
    login_client(client, admin)
    vehicle_id = _setup_vehicle_in_control(client, db_session, admin, chauffeur)

    login_client(client, chauffeur)
    inspection_id = _create_inspection(client, vehicle_id)

    client_uuid = str(uuid4())
    first = _upload(client, vehicle_id, inspection_id=inspection_id, client_uuid=client_uuid)
    assert first.status_code == 201, first.text
    photo_id = first.json()["id"]

    second = _upload(client, vehicle_id, inspection_id=inspection_id, client_uuid=client_uuid)
    assert second.status_code == 201  # même appel, même angle -> rejeu, pas de doublon
    assert second.json()["id"] == photo_id

    count = db_session.scalar(
        select(Photo).where(Photo.vehicle_id == vehicle_id, Photo.angle == "face_avant")
    )
    assert count is not None
    all_photos = list(db_session.scalars(select(Photo).where(Photo.vehicle_id == vehicle_id)).all())
    assert len(all_photos) == 1


def test_duplicate_angle_for_same_inspection_returns_409(
    client: TestClient, db_session: Session
) -> None:
    seed_reference(db_session)
    admin = make_user(db_session, UserRole.ADMINISTRATEUR)
    chauffeur = make_user(db_session, UserRole.CHAUFFEUR)
    login_client(client, admin)
    vehicle_id = _setup_vehicle_in_control(client, db_session, admin, chauffeur)

    login_client(client, chauffeur)
    inspection_id = _create_inspection(client, vehicle_id)

    first = _upload(client, vehicle_id, inspection_id=inspection_id, angle="face_avant")
    assert first.status_code == 201

    second = _upload(client, vehicle_id, inspection_id=inspection_id, angle="face_avant")
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "conflict"


def test_defaut_angle_can_repeat(client: TestClient, db_session: Session) -> None:
    """`defaut` échappe à la contrainte d'unicité d'angle — photos de défauts libres et
    répétables (plan.md § 5.1)."""
    seed_reference(db_session)
    admin = make_user(db_session, UserRole.ADMINISTRATEUR)
    chauffeur = make_user(db_session, UserRole.CHAUFFEUR)
    login_client(client, admin)
    vehicle_id = _setup_vehicle_in_control(client, db_session, admin, chauffeur)

    login_client(client, chauffeur)
    inspection_id = _create_inspection(client, vehicle_id)

    first = _upload(client, vehicle_id, inspection_id=inspection_id, angle="defaut")
    second = _upload(
        client, vehicle_id, inspection_id=inspection_id, angle="defaut", content=b"autre-defaut"
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


def test_checksum_mismatch_rejected(client: TestClient, db_session: Session) -> None:
    seed_reference(db_session)
    admin = make_user(db_session, UserRole.ADMINISTRATEUR)
    chauffeur = make_user(db_session, UserRole.CHAUFFEUR)
    login_client(client, admin)
    vehicle_id = _setup_vehicle_in_control(client, db_session, admin, chauffeur)

    login_client(client, chauffeur)
    inspection_id = _create_inspection(client, vehicle_id)

    response = _upload(
        client,
        vehicle_id,
        inspection_id=inspection_id,
        content=b"contenu-reel",
        checksum="0" * 64,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_photo_quota_exceeded_returns_409(client: TestClient, db_session: Session) -> None:
    seed_reference(db_session)
    admin = make_user(db_session, UserRole.ADMINISTRATEUR)
    chauffeur = make_user(db_session, UserRole.CHAUFFEUR)
    login_client(client, admin)
    vehicle_id = _setup_vehicle_in_control(client, db_session, admin, chauffeur)

    login_client(client, chauffeur)
    inspection_id = _create_inspection(client, vehicle_id)

    # 30 photos de défaut (angle répétable) pour atteindre le plafond sans buter sur la
    # contrainte d'unicité d'angle.
    for i in range(30):
        response = _upload(
            client,
            vehicle_id,
            inspection_id=inspection_id,
            angle="defaut",
            content=f"defaut-{i}".encode(),
        )
        assert response.status_code == 201, response.text

    over_quota = _upload(
        client, vehicle_id, inspection_id=inspection_id, angle="defaut", content=b"defaut-31"
    )
    assert over_quota.status_code == 409
    assert over_quota.json()["error"]["code"] == "photo_quota_exceeded"


def test_photo_file_is_scoped_to_assigned_driver(client: TestClient, db_session: Session) -> None:
    seed_reference(db_session)
    admin = make_user(db_session, UserRole.ADMINISTRATEUR)
    chauffeur = make_user(db_session, UserRole.CHAUFFEUR)
    other_driver = make_user(db_session, UserRole.CHAUFFEUR)
    login_client(client, admin)
    vehicle_id = _setup_vehicle_in_control(client, db_session, admin, chauffeur)

    login_client(client, chauffeur)
    inspection_id = _create_inspection(client, vehicle_id)
    upload = _upload(client, vehicle_id, inspection_id=inspection_id)
    assert upload.status_code == 201
    photo_url = upload.json()["url"]
    assert photo_url.startswith("/api/backend/v1/photos/file/")
    # `url` est la route **navigateur** (le rewrite Next `/api/backend/:path*` -> `BACKEND_ORIGIN
    # /api/:path*` remplace le segment `/api/backend` par `/api`, jamais appelé en direct par le
    # backend lui-même) — `TestClient` parle au backend sans ce proxy, donc la requête ci-dessous
    # cible la route backend réelle en rejouant la même substitution
    # (docs/wiki/pieges-projet.md § « Module terrain / PWA (J2) »).
    backend_path = photo_url.replace("/api/backend", "/api", 1)

    own_read = client.get(backend_path)
    assert own_read.status_code == 200
    assert own_read.content == b"contenu-photo"

    login_client(client, other_driver)
    other_read = client.get(backend_path)
    assert other_read.status_code == 404


def test_photo_upload_rejects_unknown_angle(client: TestClient, db_session: Session) -> None:
    seed_reference(db_session)
    admin = make_user(db_session, UserRole.ADMINISTRATEUR)
    chauffeur = make_user(db_session, UserRole.CHAUFFEUR)
    login_client(client, admin)
    vehicle_id = _setup_vehicle_in_control(client, db_session, admin, chauffeur)

    login_client(client, chauffeur)
    inspection_id = _create_inspection(client, vehicle_id)

    response = _upload(client, vehicle_id, inspection_id=inspection_id, angle="angle-inconnu")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_photo_upload_rejects_non_controle_phase(client: TestClient, db_session: Session) -> None:
    """La phase `avant_travaux`/`apres_travaux` (atelier, J3) n'est pas encore prise en charge."""
    seed_reference(db_session)
    admin = make_user(db_session, UserRole.ADMINISTRATEUR)
    chauffeur = make_user(db_session, UserRole.CHAUFFEUR)
    login_client(client, admin)
    vehicle_id = _setup_vehicle_in_control(client, db_session, admin, chauffeur)

    login_client(client, chauffeur)
    inspection_id = _create_inspection(client, vehicle_id)

    content = b"photo-atelier"
    response = client.post(
        f"/api/v1/vehicles/{vehicle_id}/photos",
        data={
            "client_uuid": str(uuid4()),
            "angle": "face_avant",
            "phase": "avant_travaux",
            "inspection_id": inspection_id,
            "captured_at": datetime.now().isoformat(),
            "checksum_sha256": hashlib.sha256(content).hexdigest(),
            "width": "1600",
            "height": "1200",
        },
        files={"file": ("photo.jpg", content, "image/jpeg")},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
