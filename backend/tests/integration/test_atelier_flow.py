"""Atelier J3 — création des `work_order` (effet de `CONTROLE_EN_COURS -> TRAVAUX_REQUIS`), garde
« chaque ordre terminé/annulé doit porter au moins une ligne de coût » et transition véhicule
`TRAVAUX_EN_COURS -> TRAVAUX_TERMINES` (plan.md § 5.1, § 5.3, brief J3).

Toute assertion de garde passe par l'endpoint réel (`POST /vehicles/{id}/transitions`,
`POST /work-orders/{id}/state`), jamais par l'appel direct d'une fonction de service — un bug de
contrat appelant/appelée ne se voit qu'à cette couche (docs/wiki mémoire dev-backend).
"""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.checklist import ChecklistTemplate
from app.models.company import Company
from app.models.enums import UserRole
from app.models.inspection import Inspection
from app.models.mission import Mission
from app.models.vehicle import Vehicle
from app.models.work_order import WorkOrder
from app.seed.reference import seed_reference
from tests.conftest import login_client, make_user

TODAY = date(2026, 8, 20)


def _make_company(db_session: Session, user, **overrides) -> Company:
    base = {
        "id": uuid4(),
        "siren": "732829320",
        "siret": "73282932000074",
        "denomination": "Flotte Atelier Test",
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


def _vehicle_ready_for_travaux(client: TestClient, db_session: Session, admin, chauffeur) -> str:
    """Véhicule affecté, en `CONTROLE_EN_COURS`, avec une inspection déjà soumise — précondition
    de `_guard_inspection_et_work_orders`, construite directement en base (même pattern que
    `test_photos.py::_setup_vehicle_in_control`) pour ne pas rejouer tout le parcours photo/
    checklist, hors périmètre de ce test."""
    seed_reference(db_session)
    template = db_session.scalar(select(ChecklistTemplate))

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
    mission = db_session.scalar(select(Mission).where(Mission.vehicle_id == vehicle_id))
    vehicle = db_session.get(Vehicle, vehicle_id)
    vehicle.state = "CONTROLE_EN_COURS"
    db_session.add(
        Inspection(
            id=uuid4(),
            vehicle_id=vehicle.id,
            mission_id=mission.id,
            driver_id=chauffeur.id,
            template_id=template.id,
            client_uuid=uuid4(),
            started_at=datetime.now(UTC),
            submitted_at=datetime.now(UTC),
        )
    )
    db_session.flush()
    return vehicle_id


def test_travaux_requis_transition_requires_work_orders_payload(
    client: TestClient, db_session: Session
) -> None:
    admin = make_user(db_session, UserRole.ADMINISTRATEUR)
    chauffeur = make_user(db_session, UserRole.CHAUFFEUR)
    login_client(client, admin)
    vehicle_id = _vehicle_ready_for_travaux(client, db_session, admin, chauffeur)

    missing_payload = client.post(
        f"/api/v1/vehicles/{vehicle_id}/transitions", json={"to_state": "TRAVAUX_REQUIS"}
    )
    assert missing_payload.status_code == 409
    assert missing_payload.json()["error"]["code"] == "invalid_transition"

    empty_list = client.post(
        f"/api/v1/vehicles/{vehicle_id}/transitions",
        json={"to_state": "TRAVAUX_REQUIS", "payload": {"work_orders": []}},
    )
    assert empty_list.status_code == 409


def test_travaux_requis_transition_creates_work_orders(
    client: TestClient, db_session: Session
) -> None:
    admin = make_user(db_session, UserRole.ADMINISTRATEUR)
    chauffeur = make_user(db_session, UserRole.CHAUFFEUR)
    login_client(client, admin)
    vehicle_id = _vehicle_ready_for_travaux(client, db_session, admin, chauffeur)

    response = client.post(
        f"/api/v1/vehicles/{vehicle_id}/transitions",
        json={
            "to_state": "TRAVAUX_REQUIS",
            "payload": {
                "work_orders": [
                    {"type": "carrosserie", "description": "Pare-chocs enfoncé"},
                    {
                        "type": "mecanique",
                        "description": "Révision complète",
                        "montant_estime_cents": 25000,
                    },
                ]
            },
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "TRAVAUX_REQUIS"

    work_orders = list(
        db_session.scalars(select(WorkOrder).where(WorkOrder.vehicle_id == vehicle_id)).all()
    )
    assert len(work_orders) == 2
    assert {w.type for w in work_orders} == {"carrosserie", "mecanique"}
    assert all(w.state == "demande" for w in work_orders)

    listing = client.get(f"/api/v1/vehicles/{vehicle_id}/work-orders")
    assert listing.status_code == 200
    assert len(listing.json()) == 2
    assert listing.json()[0]["lines"] == []


def _create_one_work_order(
    client: TestClient, db_session: Session, admin, chauffeur
) -> tuple[str, str]:
    vehicle_id = _vehicle_ready_for_travaux(client, db_session, admin, chauffeur)
    client.post(
        f"/api/v1/vehicles/{vehicle_id}/transitions",
        json={
            "to_state": "TRAVAUX_REQUIS",
            "payload": {"work_orders": [{"type": "mecanique", "description": "Révision"}]},
        },
    )
    work_order = db_session.scalar(select(WorkOrder).where(WorkOrder.vehicle_id == vehicle_id))
    return vehicle_id, str(work_order.id)


def test_work_order_cannot_close_without_a_cost_line(
    client: TestClient, db_session: Session
) -> None:
    admin = make_user(db_session, UserRole.ADMINISTRATEUR)
    chauffeur = make_user(db_session, UserRole.CHAUFFEUR)
    atelier = make_user(db_session, UserRole.ATELIER)
    login_client(client, admin)
    _, work_order_id = _create_one_work_order(client, db_session, admin, chauffeur)

    login_client(client, atelier)
    en_cours = client.post(
        f"/api/v1/work-orders/{work_order_id}/state", json={"to_state": "en_cours"}
    )
    assert en_cours.status_code == 200, en_cours.text

    termine_sans_ligne = client.post(
        f"/api/v1/work-orders/{work_order_id}/state", json={"to_state": "termine"}
    )
    assert termine_sans_ligne.status_code == 409
    assert termine_sans_ligne.json()["error"]["code"] == "conflict"

    add_line = client.post(
        f"/api/v1/work-orders/{work_order_id}/lines",
        json={
            "libelle": "Vidange complète",
            "categorie": "piece",
            "quantite": "1",
            "prix_unitaire_cents": 8000,
        },
    )
    assert add_line.status_code == 201, add_line.text
    assert add_line.json()["montant_cents"] == 8000  # colonne GENERATED, base = quantite * pu

    termine_avec_ligne = client.post(
        f"/api/v1/work-orders/{work_order_id}/state", json={"to_state": "termine"}
    )
    assert termine_avec_ligne.status_code == 200, termine_avec_ligne.text
    assert termine_avec_ligne.json()["state"] == "termine"
    assert len(termine_avec_ligne.json()["lines"]) == 1


def test_vehicle_cannot_reach_travaux_termines_while_a_work_order_is_open(
    client: TestClient, db_session: Session
) -> None:
    admin = make_user(db_session, UserRole.ADMINISTRATEUR)
    chauffeur = make_user(db_session, UserRole.CHAUFFEUR)
    atelier = make_user(db_session, UserRole.ATELIER)
    login_client(client, admin)
    vehicle_id, work_order_id = _create_one_work_order(client, db_session, admin, chauffeur)

    # TRAVAUX_REQUIS -> TRAVAUX_EN_COURS : au moins un work_order en "demande" (garde satisfaite).
    to_en_cours = client.post(
        f"/api/v1/vehicles/{vehicle_id}/transitions", json={"to_state": "TRAVAUX_EN_COURS"}
    )
    assert to_en_cours.status_code == 200, to_en_cours.text

    # Le seul work_order est toujours "demande" -> la garde véhicule doit refuser.
    too_early = client.post(
        f"/api/v1/vehicles/{vehicle_id}/transitions", json={"to_state": "TRAVAUX_TERMINES"}
    )
    assert too_early.status_code == 409
    assert too_early.json()["error"]["code"] == "invalid_transition"

    login_client(client, atelier)
    client.post(f"/api/v1/work-orders/{work_order_id}/state", json={"to_state": "en_cours"})
    client.post(
        f"/api/v1/work-orders/{work_order_id}/lines",
        json={
            "libelle": "Main d'œuvre",
            "categorie": "main_oeuvre",
            "quantite": "2",
            "prix_unitaire_cents": 5000,
        },
    )
    close = client.post(f"/api/v1/work-orders/{work_order_id}/state", json={"to_state": "termine"})
    assert close.status_code == 200, close.text

    login_client(client, admin)
    now_ok = client.post(
        f"/api/v1/vehicles/{vehicle_id}/transitions", json={"to_state": "TRAVAUX_TERMINES"}
    )
    assert now_ok.status_code == 200, now_ok.text
    assert now_ok.json()["state"] == "TRAVAUX_TERMINES"


def test_atelier_photo_avant_apres_travaux_requires_work_order_id(
    client: TestClient, db_session: Session
) -> None:
    admin = make_user(db_session, UserRole.ADMINISTRATEUR)
    chauffeur = make_user(db_session, UserRole.CHAUFFEUR)
    atelier = make_user(db_session, UserRole.ATELIER)
    login_client(client, admin)
    vehicle_id, work_order_id = _create_one_work_order(client, db_session, admin, chauffeur)

    login_client(client, atelier)
    content = b"avant-travaux"
    checksum = hashlib.sha256(content).hexdigest()

    missing_wo = client.post(
        f"/api/v1/vehicles/{vehicle_id}/photos",
        data={
            "client_uuid": str(uuid4()),
            "angle": "defaut",
            "phase": "avant_travaux",
            "captured_at": datetime.now().isoformat(),
            "checksum_sha256": checksum,
            "width": "800",
            "height": "600",
        },
        files={"file": ("avant.jpg", content, "image/jpeg")},
    )
    assert missing_wo.status_code == 422

    with_wo = client.post(
        f"/api/v1/vehicles/{vehicle_id}/photos",
        data={
            "client_uuid": str(uuid4()),
            "angle": "defaut",
            "phase": "avant_travaux",
            "work_order_id": work_order_id,
            "captured_at": datetime.now().isoformat(),
            "checksum_sha256": checksum,
            "width": "800",
            "height": "600",
        },
        files={"file": ("avant.jpg", content, "image/jpeg")},
    )
    assert with_wo.status_code == 201, with_wo.text
    assert with_wo.json()["work_order_id"] == work_order_id
    assert with_wo.json()["url"].startswith("/api/backend/v1/photos/file/")


def test_vehicle_cost_write_restricted_to_administrateur(
    client: TestClient, db_session: Session
) -> None:
    admin = make_user(db_session, UserRole.ADMINISTRATEUR)
    operatrice = make_user(db_session, UserRole.OPERATRICE)
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
    vehicle_id = created.json()["id"]

    login_client(client, operatrice)
    forbidden = client.post(
        f"/api/v1/vehicles/{vehicle_id}/costs",
        json={"type": "transport", "montant_cents": 5000},
    )
    assert forbidden.status_code == 403

    login_client(client, admin)
    ok = client.post(
        f"/api/v1/vehicles/{vehicle_id}/costs",
        json={"type": "transport", "montant_cents": 5000, "commentaire": "Convoyage"},
    )
    assert ok.status_code == 201, ok.text

    listing = client.get(f"/api/v1/vehicles/{vehicle_id}/costs")
    assert listing.status_code == 200
    assert len(listing.json()) == 1
    assert listing.json()[0]["montant_cents"] == 5000


def test_pipeline_counts_restricted_to_administrateur_and_covers_all_states(
    client: TestClient, db_session: Session
) -> None:
    admin = make_user(db_session, UserRole.ADMINISTRATEUR)
    operatrice = make_user(db_session, UserRole.OPERATRICE)
    login_client(client, admin)
    company = _make_company(db_session, admin)
    client.post(
        "/api/v1/vehicles",
        json={
            "company_id": str(company.id),
            "marque": "Renault",
            "modele": "Kangoo",
            "date_proposition": TODAY.isoformat(),
        },
    )

    login_client(client, operatrice)
    forbidden = client.get("/api/v1/vehicles/pipeline-counts")
    assert forbidden.status_code == 403

    login_client(client, admin)
    response = client.get("/api/v1/vehicles/pipeline-counts")
    assert response.status_code == 200
    counts = {c["state"]: c["count"] for c in response.json()["counts"]}
    assert len(counts) == 11  # les 11 états, même à zéro
    assert counts["BROUILLON"] == 1
    assert counts["ACHAT_VALIDE"] == 0


def test_atelier_keeps_access_after_closing_last_work_order_to_trigger_travaux_termines(
    client: TestClient, db_session: Session
) -> None:
    """Régression 🟠 signalée par dev-frontend (implementation.md § J3 — Frontend) :
    `scope_vehicles` ne montrait à `atelier` que les véhicules portant un `work_order`
    `demande`/`en_cours`. En clôturant son dernier ordre (`termine`), l'atelier sortait
    immédiatement du périmètre du véhicule — **avant** de pouvoir déclencher lui-même
    `TRAVAUX_EN_COURS -> TRAVAUX_TERMINES`, transition que ce rôle vient précisément de
    débloquer (`_role_atelier_admin`). Contrairement à `test_vehicle_cannot_reach_travaux_
    termines_while_a_work_order_is_open`, la clôture finale est jouée ici par `atelier`
    lui-même, pas par `administrateur` — c'est le contournement que dev-frontend a dû prendre
    dans son e2e, et c'est exactement le chemin qui doit rester ouvert."""
    admin = make_user(db_session, UserRole.ADMINISTRATEUR)
    chauffeur = make_user(db_session, UserRole.CHAUFFEUR)
    atelier = make_user(db_session, UserRole.ATELIER)
    login_client(client, admin)
    vehicle_id, work_order_id = _create_one_work_order(client, db_session, admin, chauffeur)

    to_en_cours = client.post(
        f"/api/v1/vehicles/{vehicle_id}/transitions", json={"to_state": "TRAVAUX_EN_COURS"}
    )
    assert to_en_cours.status_code == 200, to_en_cours.text

    login_client(client, atelier)
    # L'atelier voit toujours le véhicule pendant que son unique ordre est ouvert.
    still_visible_open = client.get(f"/api/v1/vehicles/{vehicle_id}")
    assert still_visible_open.status_code == 200, still_visible_open.text

    client.post(f"/api/v1/work-orders/{work_order_id}/state", json={"to_state": "en_cours"})
    client.post(
        f"/api/v1/work-orders/{work_order_id}/lines",
        json={
            "libelle": "Main d'œuvre",
            "categorie": "main_oeuvre",
            "quantite": "1",
            "prix_unitaire_cents": 6000,
        },
    )
    close_last_order = client.post(
        f"/api/v1/work-orders/{work_order_id}/state", json={"to_state": "termine"}
    )
    assert close_last_order.status_code == 200, close_last_order.text

    # Le véhicule doit rester visible à l'atelier — plus aucun ordre ouvert, mais le véhicule
    # est toujours en TRAVAUX_EN_COURS et la transition qu'il vient de débloquer n'a pas encore
    # été jouée.
    still_visible_after_close = client.get(f"/api/v1/vehicles/{vehicle_id}")
    assert still_visible_after_close.status_code == 200, still_visible_after_close.text

    # Et l'atelier peut lui-même déclencher la transition qu'il vient de débloquer.
    travaux_termines = client.post(
        f"/api/v1/vehicles/{vehicle_id}/transitions", json={"to_state": "TRAVAUX_TERMINES"}
    )
    assert travaux_termines.status_code == 200, travaux_termines.text
    assert travaux_termines.json()["state"] == "TRAVAUX_TERMINES"
