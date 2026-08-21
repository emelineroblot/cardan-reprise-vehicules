"""`GET /analytics/*` — appelés réellement par HTTP, chacun, avec et sans filtre.

Écrit en réponse à un bug passé inaperçu par 781 tests verts (`GET /analytics/marge` répondait
`500 psycopg.errors.AmbiguousParameter` de façon systématique, aucun test ne l'atteignait) —
troisième occurrence sur ce projet d'une suite verte masquant un défaut sur le chemin réel (après
le circuit breaker de J1 et le parcours end-to-end vert par accident de J2). Principe appliqué
ici : un endpoint qu'aucun test n'atteint est un endpoint qui ne marche pas — chaque route
`GET /analytics/*` est donc appelée via `TestClient` (jamais la fonction Python interne), avec une
assertion stricte `== 200` (jamais seulement `!= 403`, ce qui aurait laissé passer le 500).

`analytics.runner.build()` est appelé une fois pour la session de test — il ouvre sa propre
connexion (`engine.begin()`), distincte de la transaction annulée de `db_session`
(§ 4 décision F) : les vues créées sont donc réellement committées et persistent pour tout le
run, comme documenté dans `test_demo_reset.py` pour un motif analogue. Sans données seedées, les
marts sont vides (listes vides, `kpi-global` renvoie ses agrégats à `NULL`/`0`) — suffisant pour
prouver que chaque requête s'exécute sans lever, ce qui est précisément ce qui manquait.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.analytics.runner import build as analytics_build
from app.models.enums import UserRole
from tests.conftest import login_client, make_user


@pytest.fixture(scope="session", autouse=True)
def _analytics_schema_built(engine) -> None:
    """Construit `analytics.stg_*`/`analytics.mart_*` une fois pour la session de test — sans
    cela, chaque requête ci-dessous échouerait sur `relation "analytics.mart_*" does not
    exist`, un faux positif qui masquerait le vrai bug (le binding du paramètre `:state`)."""
    analytics_build()


def _admin_client(client: TestClient, db_session: Session) -> TestClient:
    admin = make_user(db_session, UserRole.ADMINISTRATEUR)
    return login_client(client, admin)


def test_get_marge_without_filter(client: TestClient, db_session: Session) -> None:
    """Régression du 🔴 signalé par dev-frontend : `WHERE (:state IS NULL OR state = :state)`
    sans cast explicite est ambigu pour psycopg 3 en protocole étendu — reproduit hors HTTP
    avant correctif (`psycopg.errors.AmbiguousParameter`), corrigé en n'émettant la clause
    `WHERE state = :state` que lorsque `state` est effectivement fourni."""
    _admin_client(client, db_session)
    response = client.get("/api/v1/analytics/marge")
    assert response.status_code == 200, response.text
    assert isinstance(response.json(), list)


def test_get_marge_with_state_filter(client: TestClient, db_session: Session) -> None:
    _admin_client(client, db_session)
    response = client.get("/api/v1/analytics/marge", params={"state": "ACHAT_VALIDE"})
    assert response.status_code == 200, response.text
    assert all(row["state"] == "ACHAT_VALIDE" for row in response.json())


def test_get_marge_with_sort(client: TestClient, db_session: Session) -> None:
    _admin_client(client, db_session)
    response = client.get("/api/v1/analytics/marge", params={"sort": "date_proposition"})
    assert response.status_code == 200, response.text


def test_get_cycle_temps(client: TestClient, db_session: Session) -> None:
    _admin_client(client, db_session)
    response = client.get("/api/v1/analytics/cycle-temps")
    assert response.status_code == 200, response.text
    assert isinstance(response.json(), list)


def test_get_pipeline_etat(client: TestClient, db_session: Session) -> None:
    _admin_client(client, db_session)
    response = client.get("/api/v1/analytics/pipeline-etat")
    assert response.status_code == 200, response.text
    assert isinstance(response.json(), list)


def test_get_refus(client: TestClient, db_session: Session) -> None:
    _admin_client(client, db_session)
    response = client.get("/api/v1/analytics/refus")
    assert response.status_code == 200, response.text
    assert isinstance(response.json(), list)


def test_get_travaux(client: TestClient, db_session: Session) -> None:
    _admin_client(client, db_session)
    response = client.get("/api/v1/analytics/travaux")
    assert response.status_code == 200, response.text
    assert isinstance(response.json(), list)


def test_get_kpi_global(client: TestClient, db_session: Session) -> None:
    _admin_client(client, db_session)
    response = client.get("/api/v1/analytics/kpi-global")
    assert response.status_code == 200, response.text
    body = response.json()
    assert "nb_vehicules_total" in body
    assert "marge_moyenne_cents" in body


def test_get_status(client: TestClient, db_session: Session) -> None:
    _admin_client(client, db_session)
    response = client.get("/api/v1/analytics/status")
    assert response.status_code == 200, response.text


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/analytics/marge",
        "/api/v1/analytics/cycle-temps",
        "/api/v1/analytics/pipeline-etat",
        "/api/v1/analytics/refus",
        "/api/v1/analytics/travaux",
        "/api/v1/analytics/kpi-global",
        "/api/v1/analytics/status",
    ],
)
def test_analytics_endpoints_forbidden_to_non_administrateur(
    client: TestClient, db_session: Session, path: str
) -> None:
    operatrice = make_user(db_session, UserRole.OPERATRICE)
    login_client(client, operatrice)
    response = client.get(path)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden_role"
