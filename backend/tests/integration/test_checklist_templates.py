"""`/checklist-templates/*` — référentiel de checklist (brief J2, manque signalé en revue puis
tranché par l'orchestrateur : sans lui, dev-frontend ne peut pas rendre le formulaire de
contrôle avant la première réponse posée)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.enums import UserRole
from app.seed.reference import CHECKLIST_CONTROLE_CODE, CHECKLIST_ITEMS, seed_reference
from tests.conftest import login_client, make_user


def test_list_checklist_templates_returns_active_by_default(
    client: TestClient, db_session: Session
) -> None:
    seed_reference(db_session)
    user = make_user(db_session, UserRole.CHAUFFEUR)
    login_client(client, user)

    response = client.get("/api/v1/checklist-templates")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["code"] == CHECKLIST_CONTROLE_CODE
    assert body[0]["is_active"] is True
    assert "items" not in body[0]  # forme allégée, cohérent avec `ChecklistTemplateBrief`


def test_get_checklist_template_exposes_ordered_items_with_grouping(
    client: TestClient, db_session: Session
) -> None:
    seed_reference(db_session)
    user = make_user(db_session, UserRole.CHAUFFEUR)
    login_client(client, user)

    listing = client.get("/api/v1/checklist-templates")
    template_id = listing.json()[0]["id"]

    detail = client.get(f"/api/v1/checklist-templates/{template_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["code"] == CHECKLIST_CONTROLE_CODE

    items = body["items"]
    assert len(items) == len(CHECKLIST_ITEMS)

    # Triés par ordre d'affichage (garanti par la relation ORM, pas par l'ordre d'insertion).
    ordres = [item["ordre"] for item in items]
    assert ordres == sorted(ordres)

    # Chaque item porte libellé, type de réponse, obligation et regroupement (catégorie) —
    # exactement ce que l'orchestrateur a demandé pour rendre le formulaire.
    by_code = {item["code"]: item for item in items}
    carte_grise = by_code["carte_grise"]
    assert carte_grise["libelle"] == "Carte grise présente"
    assert carte_grise["categorie"] == "documents"
    assert carte_grise["response_type"] == "ok_ko"
    assert carte_grise["is_required"] is True

    triangle = by_code["triangle_gilet"]
    assert triangle["is_required"] is False


def test_get_checklist_template_unknown_id_returns_404(
    client: TestClient, db_session: Session
) -> None:
    from uuid import uuid4

    user = make_user(db_session, UserRole.ADMINISTRATEUR)
    login_client(client, user)

    response = client.get(f"/api/v1/checklist-templates/{uuid4()}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_list_checklist_templates_is_open_to_every_authenticated_role(
    client: TestClient, db_session: Session
) -> None:
    """Donnée de référence sans caractère sensible — tous les rôles peuvent la lire, au même
    titre que `GET /vehicles/{id}/transitions` (revue orchestrateur)."""
    seed_reference(db_session)
    for role in UserRole:
        user = make_user(db_session, role)
        login_client(client, user)
        response = client.get("/api/v1/checklist-templates")
        assert response.status_code == 200, f"{role.value} devrait pouvoir lire le référentiel"
