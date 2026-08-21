"""Cloisonnement des données financières — régression directe du 🔴 « le cloisonnement des
données financières n'existe pas côté serveur » (revue J3). Masquer un champ dans l'interface ne
protège rien : ces tests appellent l'API réelle en tant que `chauffeur` et vérifient l'ABSENCE
des valeurs financières dans le CORPS de la réponse, pas seulement un code de statut — le piège
symétrique du bug 🔴 « `!= 403` laisse passer un `500` » de ce même jalon serait un test qui
vérifie `== 200` sans jamais lire le contenu.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
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

_FINANCE_FIELDS = (
    "prix_achat_negocie_cents",
    "valeur_revente_estimee_cents",
    "frais_transport_cents",
)


def _make_company(db_session: Session, user, **overrides) -> Company:
    base = {
        "id": uuid4(),
        "siren": "732829320",
        "siret": "73282932000074",
        "denomination": "Flotte Finances Test",
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


def _priced_vehicle_assigned_to_driver(
    client: TestClient, db_session: Session, admin, chauffeur
) -> str:
    """Véhicule affecté à `chauffeur`, avec des valeurs financières réelles et non nulles en
    base — précondition indispensable : un test qui vérifierait l'absence d'un champ resté à
    `None` par construction (jamais saisi) ne prouverait rien sur la rédaction elle-même."""
    company = _make_company(db_session, admin)
    login_client(client, admin)
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

    patch = client.patch(
        f"/api/v1/vehicles/{vehicle_id}",
        json={
            "prix_achat_negocie_cents": 500_000,
            "valeur_revente_estimee_cents": 750_000,
            "frais_transport_cents": 12_000,
        },
    )
    assert patch.status_code == 200, patch.text
    assert patch.json()["prix_achat_negocie_cents"] == 500_000  # admin voit la vraie valeur

    client.post(
        f"/api/v1/vehicles/{vehicle_id}/transitions",
        json={"to_state": "A_PLANIFIER", "reason": "validation"},
    )
    affect = client.post(
        f"/api/v1/vehicles/{vehicle_id}/transitions",
        json={"to_state": "AFFECTE", "payload": {"driver_id": str(chauffeur.id)}},
    )
    assert affect.status_code == 200, affect.text

    vehicle = db_session.get(Vehicle, vehicle_id)
    assert vehicle.prix_achat_negocie_cents == 500_000
    assert vehicle.valeur_revente_estimee_cents == 750_000
    assert vehicle.frais_transport_cents == 12_000
    return vehicle_id


def test_chauffeur_never_receives_financial_fields_on_vehicle_list(
    client: TestClient, db_session: Session
) -> None:
    admin = make_user(db_session, UserRole.ADMINISTRATEUR)
    chauffeur = make_user(db_session, UserRole.CHAUFFEUR)
    vehicle_id = _priced_vehicle_assigned_to_driver(client, db_session, admin, chauffeur)

    login_client(client, chauffeur)
    response = client.get("/api/v1/vehicles")
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    matching = [v for v in items if v["id"] == vehicle_id]
    assert matching, "le véhicule affecté doit rester visible au chauffeur (scope_vehicles)"
    vehicle_payload = matching[0]
    for field in _FINANCE_FIELDS:
        assert vehicle_payload[field] is None, (
            f"chauffeur a reçu {field}={vehicle_payload[field]!r} dans GET /vehicles — la "
            "valeur ne doit jamais quitter le serveur pour ce rôle"
        )


def test_chauffeur_never_receives_financial_fields_on_vehicle_detail(
    client: TestClient, db_session: Session
) -> None:
    admin = make_user(db_session, UserRole.ADMINISTRATEUR)
    chauffeur = make_user(db_session, UserRole.CHAUFFEUR)
    vehicle_id = _priced_vehicle_assigned_to_driver(client, db_session, admin, chauffeur)

    login_client(client, chauffeur)
    response = client.get(f"/api/v1/vehicles/{vehicle_id}")
    assert response.status_code == 200, response.text
    body = response.json()
    for field in _FINANCE_FIELDS:
        assert (
            body[field] is None
        ), f"chauffeur a reçu {field}={body[field]!r} dans GET /vehicles/{{id}}"


def test_chauffeur_never_receives_financial_fields_on_transition_response(
    client: TestClient, db_session: Session
) -> None:
    """La rédaction doit s'appliquer aussi à la réponse de `POST /transitions` — le chauffeur
    l'appelle légitimement pour son propre parcours terrain (`AFFECTE -> RDV_PLANIFIE`, etc.)."""
    admin = make_user(db_session, UserRole.ADMINISTRATEUR)
    chauffeur = make_user(db_session, UserRole.CHAUFFEUR)
    vehicle_id = _priced_vehicle_assigned_to_driver(client, db_session, admin, chauffeur)

    login_client(client, chauffeur)
    rdv_at = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    response = client.post(
        f"/api/v1/vehicles/{vehicle_id}/transitions",
        json={"to_state": "RDV_PLANIFIE", "payload": {"rdv_at": rdv_at}},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    for field in _FINANCE_FIELDS:
        assert (
            body[field] is None
        ), f"chauffeur a reçu {field}={body[field]!r} dans la réponse de POST /transitions"


def test_operatrice_and_administrateur_still_receive_real_financial_values(
    client: TestClient, db_session: Session
) -> None:
    """Contraste indispensable : la rédaction ne doit s'appliquer QU'aux rôles sans besoin
    métier — sinon un correctif trop large casserait le tableau de bord et la fiche véhicule
    pour les rôles qui en ont l'usage légitime."""
    admin = make_user(db_session, UserRole.ADMINISTRATEUR)
    operatrice = make_user(db_session, UserRole.OPERATRICE)
    chauffeur = make_user(db_session, UserRole.CHAUFFEUR)
    vehicle_id = _priced_vehicle_assigned_to_driver(client, db_session, admin, chauffeur)

    for user in (admin, operatrice):
        login_client(client, user)
        detail = client.get(f"/api/v1/vehicles/{vehicle_id}")
        assert detail.status_code == 200, detail.text
        body = detail.json()
        assert body["prix_achat_negocie_cents"] == 500_000, user.role
        assert body["valeur_revente_estimee_cents"] == 750_000, user.role
        assert body["frais_transport_cents"] == 12_000, user.role

        listing = client.get("/api/v1/vehicles")
        assert listing.status_code == 200
        matching = [v for v in listing.json()["items"] if v["id"] == vehicle_id][0]
        assert matching["prix_achat_negocie_cents"] == 500_000, user.role


def _vehicle_with_work_order_and_costs(
    client: TestClient, db_session: Session, admin, chauffeur
) -> tuple[str, str]:
    """Véhicule affecté au chauffeur, en `TRAVAUX_REQUIS` avec un `work_order`, plus un
    `vehicle_cost` hors atelier — de quoi vérifier que le chauffeur n'a accès ni à l'un ni à
    l'autre, alors même que le véhicule lui reste affecté."""
    seed_reference(db_session)
    template = db_session.scalar(select(ChecklistTemplate))

    company = _make_company(db_session, admin)
    login_client(client, admin)
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

    travaux = client.post(
        f"/api/v1/vehicles/{vehicle_id}/transitions",
        json={
            "to_state": "TRAVAUX_REQUIS",
            "payload": {"work_orders": [{"type": "mecanique", "description": "Révision"}]},
        },
    )
    assert travaux.status_code == 200, travaux.text
    work_order = db_session.scalar(select(WorkOrder).where(WorkOrder.vehicle_id == vehicle_id))
    work_order_id = str(work_order.id)

    cost = client.post(
        f"/api/v1/vehicles/{vehicle_id}/costs",
        json={"type": "transport", "montant_cents": 8_000},
    )
    assert cost.status_code == 201, cost.text

    return vehicle_id, work_order_id


def test_chauffeur_cannot_list_work_orders(client: TestClient, db_session: Session) -> None:
    admin = make_user(db_session, UserRole.ADMINISTRATEUR)
    chauffeur = make_user(db_session, UserRole.CHAUFFEUR)
    vehicle_id, _ = _vehicle_with_work_order_and_costs(client, db_session, admin, chauffeur)

    login_client(client, chauffeur)
    response = client.get(f"/api/v1/vehicles/{vehicle_id}/work-orders")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden_role"
    assert "montant" not in response.text and "libelle" not in response.text


def test_chauffeur_cannot_read_single_work_order(client: TestClient, db_session: Session) -> None:
    admin = make_user(db_session, UserRole.ADMINISTRATEUR)
    chauffeur = make_user(db_session, UserRole.CHAUFFEUR)
    _, work_order_id = _vehicle_with_work_order_and_costs(client, db_session, admin, chauffeur)

    login_client(client, chauffeur)
    response = client.get(f"/api/v1/work-orders/{work_order_id}")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden_role"


def test_chauffeur_cannot_list_vehicle_costs(client: TestClient, db_session: Session) -> None:
    admin = make_user(db_session, UserRole.ADMINISTRATEUR)
    chauffeur = make_user(db_session, UserRole.CHAUFFEUR)
    vehicle_id, _ = _vehicle_with_work_order_and_costs(client, db_session, admin, chauffeur)

    login_client(client, chauffeur)
    response = client.get(f"/api/v1/vehicles/{vehicle_id}/costs")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden_role"
    assert "montant_cents" not in response.text


def test_atelier_operatrice_administrateur_can_still_read_work_orders(
    client: TestClient, db_session: Session
) -> None:
    """Contraste : la restriction ne doit pas priver les rôles qui en ont besoin."""
    admin = make_user(db_session, UserRole.ADMINISTRATEUR)
    chauffeur = make_user(db_session, UserRole.CHAUFFEUR)
    atelier = make_user(db_session, UserRole.ATELIER)
    operatrice = make_user(db_session, UserRole.OPERATRICE)
    vehicle_id, work_order_id = _vehicle_with_work_order_and_costs(
        client, db_session, admin, chauffeur
    )

    for user in (atelier, operatrice, admin):
        login_client(client, user)
        listing = client.get(f"/api/v1/vehicles/{vehicle_id}/work-orders")
        assert listing.status_code == 200, (user.role, listing.text)
        detail = client.get(f"/api/v1/work-orders/{work_order_id}")
        assert detail.status_code == 200, (user.role, detail.text)
        costs = client.get(f"/api/v1/vehicles/{vehicle_id}/costs")
        assert costs.status_code == 200, (user.role, costs.text)
