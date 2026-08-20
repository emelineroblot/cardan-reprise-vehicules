"""Fallback SIRET — timeout, 500, 404, circuit ouvert, cache périmé (plan.md § 8, cas 3).

Dans les cinq cas, la saisie manuelle reste possible : c'est un critère d'acceptation du brief.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.company import CompanyLookupCache, LookupHealth
from app.models.enums import UserRole
from app.services.company_lookup.base import (
    CompanyLookupNotFound,
    CompanyLookupResult,
    CompanyLookupUnavailable,
)
from app.services.company_lookup.service import (
    CIRCUIT_FAILURE_THRESHOLD,
    is_circuit_open,
    lookup_company,
    record_failure,
)
from tests.conftest import login_client, make_user

VALID_SIRET = "73282932000074"


class _FakeProvider:
    """Double de test — pas de dépendance réseau (instruction `tests.instructions.md`)."""

    name = "fake"

    def __init__(self, outcome: str, result: CompanyLookupResult | None = None) -> None:
        self.outcome = outcome
        self.result = result
        self.calls = 0

    def lookup(self, siret: str) -> CompanyLookupResult:
        self.calls += 1
        if self.outcome == "success":
            assert self.result is not None
            return self.result
        if self.outcome == "not_found":
            raise CompanyLookupNotFound(siret)
        if self.outcome == "timeout":
            raise CompanyLookupUnavailable("Délai dépassé.")
        if self.outcome == "500":
            raise CompanyLookupUnavailable("HTTP 500")
        raise AssertionError(f"outcome inconnu : {self.outcome}")


def _sample_result(siret: str = VALID_SIRET) -> CompanyLookupResult:
    return CompanyLookupResult(
        siret=siret,
        siren=siret[:9],
        denomination="Société Fictive",
        forme_juridique=None,
        code_naf=None,
        libelle_naf=None,
        adresse_ligne1="1 rue Fictive",
        code_postal="75001",
        commune="Paris",
        tranche_effectif=None,
        date_creation=None,
    )


def test_lookup_success_populates_cache(db_session: Session) -> None:
    provider = _FakeProvider("success", _sample_result())
    outcome = lookup_company(db_session, VALID_SIRET, provider)
    assert outcome.source == "api"
    assert outcome.stale is False
    assert outcome.company.denomination == "Société Fictive"


def test_lookup_not_found_raises_404_without_cache_fallback(db_session: Session) -> None:
    from app.core.errors import ApiError

    provider = _FakeProvider("not_found")
    with pytest.raises(ApiError) as excinfo:
        lookup_company(db_session, VALID_SIRET, provider)
    assert excinfo.value.code == "siret_not_found"


def test_lookup_invalid_siret_never_calls_provider(db_session: Session) -> None:
    from app.core.errors import ApiError

    provider = _FakeProvider("success", _sample_result())
    with pytest.raises(ApiError) as excinfo:
        lookup_company(db_session, "0000000000000A", provider)
    assert excinfo.value.code == "siret_invalid"
    assert provider.calls == 0


def test_lookup_timeout_falls_back_to_stale_cache(db_session: Session) -> None:
    # Un hit périmé (> 30 j) préexiste.
    db_session.add(
        CompanyLookupCache(
            siret=VALID_SIRET,
            payload=__import__("dataclasses").asdict(_sample_result()),
            source="api",
            http_status=200,
            fetched_at=datetime.now(UTC) - timedelta(days=45),
            provider="fake",
        )
    )
    db_session.flush()

    provider = _FakeProvider("timeout")
    outcome = lookup_company(db_session, VALID_SIRET, provider)
    assert outcome.stale is True
    assert outcome.company.denomination == "Société Fictive"


def test_lookup_500_without_any_cache_raises_503(db_session: Session) -> None:
    from app.core.errors import ApiError

    provider = _FakeProvider("500")
    with pytest.raises(ApiError) as excinfo:
        lookup_company(db_session, VALID_SIRET, provider)
    assert excinfo.value.code == "siret_lookup_unavailable"


def test_circuit_opens_after_threshold_and_serves_stale_cache(db_session: Session) -> None:
    for _ in range(CIRCUIT_FAILURE_THRESHOLD):
        record_failure(db_session, "fake", "erreur simulée")

    db_session.add(
        CompanyLookupCache(
            siret=VALID_SIRET,
            payload=__import__("dataclasses").asdict(_sample_result()),
            source="api",
            http_status=200,
            fetched_at=datetime.now(UTC) - timedelta(days=1),
            provider="fake",
        )
    )
    db_session.flush()

    provider = _FakeProvider("success", _sample_result())  # ne doit jamais être appelé
    outcome = lookup_company(db_session, VALID_SIRET, provider)
    assert outcome.stale is True
    assert provider.calls == 0  # circuit ouvert : aucun appel réseau


def test_circuit_open_without_cache_raises_503_instantly(db_session: Session) -> None:
    from app.core.errors import ApiError

    for _ in range(CIRCUIT_FAILURE_THRESHOLD):
        record_failure(db_session, "fake", "erreur simulée")

    provider = _FakeProvider("success", _sample_result())
    with pytest.raises(ApiError) as excinfo:
        lookup_company(db_session, VALID_SIRET, provider)
    assert excinfo.value.code == "siret_lookup_unavailable"
    assert provider.calls == 0


def test_circuit_breaker_persists_across_service_calls(db_session: Session) -> None:
    """Persisté en base, pas en mémoire (plan.md § 3.8-4) : relu depuis une requête neuve."""
    for _ in range(CIRCUIT_FAILURE_THRESHOLD):
        record_failure(db_session, "fake", "erreur")
    db_session.flush()

    health = db_session.get(LookupHealth, "fake")
    assert health is not None
    assert health.opened_until is not None


def test_company_creation_possible_with_api_cut(client: TestClient, db_session: Session) -> None:
    """Critère d'acceptation du brief : couper l'API n'empêche pas la saisie manuelle."""
    user = make_user(db_session, UserRole.OPERATRICE)
    login_client(client, user)

    lookup_response = client.get(f"/api/v1/companies/lookup/{VALID_SIRET}")
    assert lookup_response.status_code == 503
    assert lookup_response.json()["error"]["code"] == "siret_lookup_unavailable"

    create_response = client.post(
        "/api/v1/companies",
        json={
            "siret": VALID_SIRET,
            "denomination": "Société saisie manuellement",
            "adresse_ligne1": "1 rue Manuelle",
            "code_postal": "75001",
            "commune": "Paris",
            "type_flotte": "taxi",
            "source_enrichissement": "manuel",
        },
    )
    assert create_response.status_code == 201
    assert create_response.json()["source_enrichissement"] == "manuel"


def test_circuit_breaker_opens_via_real_endpoint_after_three_failures(
    client: TestClient, db_session: Session
) -> None:
    """Régression — le circuit doit s'ouvrir en passant par l'endpoint réel, pas seulement en
    appelant `record_failure` en direct (c'est précisément ce qui masquait le bug : `get_db` ne
    commit pas, et `record_failure` faisait un `flush()` perdu quand `lookup_company` levait
    avant d'atteindre le `db.commit()` de `companies.py`)."""
    user = make_user(db_session, UserRole.OPERATRICE)
    login_client(client, user)

    for _ in range(CIRCUIT_FAILURE_THRESHOLD):
        response = client.get(f"/api/v1/companies/lookup/{VALID_SIRET}")
        assert response.status_code == 503

    health = db_session.get(LookupHealth, "disabled")
    assert health is not None
    assert health.consecutive_failures == CIRCUIT_FAILURE_THRESHOLD
    assert health.opened_until is not None
    assert is_circuit_open(db_session, "disabled") is True
