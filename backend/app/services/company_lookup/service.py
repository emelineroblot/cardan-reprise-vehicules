"""Orchestration du lookup SIRET — cache + circuit breaker PERSISTÉS EN BASE (décision B).

Persisté et non en mémoire : en serverless, chaque instance de fonction repart de zéro
(plan.md § 3.8-4). Le flux complet :

1. Validation locale (Luhn) — 422 `siret_invalid` sans appel réseau.
2. Circuit ouvert → tente un hit de cache (même périmé) en mode dégradé, sinon 503.
3. Cache frais (< 30 j) → servi tel quel, `stale=false`.
4. Appel provider : succès → cache mis à jour, circuit remis à zéro.
                      indisponible → circuit incrémenté, fallback sur cache périmé sinon 503.
                      introuvable → 404 `siret_not_found` (pas de fallback : réponse faisant foi).
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.models.company import CompanyLookupCache, LookupHealth
from app.models.enums import CacheSource
from app.services.company_lookup.base import (
    CompanyLookupNotFound,
    CompanyLookupProvider,
    CompanyLookupResult,
    CompanyLookupUnavailable,
)
from app.services.company_lookup.disabled import DisabledProvider
from app.services.company_lookup.insee import SireneInseeProvider
from app.services.company_lookup.recherche_entreprises import RechercheEntreprisesProvider
from app.services.siret import is_valid_siret

CACHE_TTL_DAYS = 30
CIRCUIT_FAILURE_THRESHOLD = 3
CIRCUIT_OPEN_DURATION = timedelta(minutes=5)


def get_provider(settings: Settings) -> CompanyLookupProvider:
    if settings.company_lookup_provider == "disabled":
        return DisabledProvider()
    if settings.company_lookup_provider == "insee" and settings.insee_api_key:
        return SireneInseeProvider(settings.insee_api_key)
    return RechercheEntreprisesProvider()


def _now() -> datetime:
    return datetime.now(UTC)


def _get_health(db: Session, provider_name: str) -> LookupHealth | None:
    return db.scalar(select(LookupHealth).where(LookupHealth.provider == provider_name))


def is_circuit_open(db: Session, provider_name: str) -> bool:
    health = _get_health(db, provider_name)
    if health is None or health.opened_until is None:
        return False
    opened_until = health.opened_until
    if opened_until.tzinfo is None:
        opened_until = opened_until.replace(tzinfo=UTC)
    return opened_until > _now()


def record_success(db: Session, provider_name: str) -> None:
    """Écriture d'infrastructure, pas de la logique métier transactionnelle : committée
    immédiatement pour rester durable même si le reste de la requête lève ensuite (revue § 🟠
    « circuit breaker qui ne s'ouvre jamais » — un `flush()` seul dépend d'un `commit()` situé
    plus loin dans l'appelant, jamais atteint sur un chemin d'erreur)."""
    health = _get_health(db, provider_name)
    if health is None:
        health = LookupHealth(
            provider=provider_name, consecutive_failures=0, opened_until=None, updated_at=_now()
        )
        db.add(health)
    health.consecutive_failures = 0
    health.opened_until = None
    health.last_error = None
    health.updated_at = _now()
    db.commit()


def record_failure(db: Session, provider_name: str, error: str) -> None:
    """Idem `record_success` : `commit()` immédiat, pas un `flush()` qui dépend d'un commit
    situé plus loin — c'est exactement ce qui empêchait le circuit de s'ouvrir en production."""
    health = _get_health(db, provider_name)
    if health is None:
        health = LookupHealth(
            provider=provider_name, consecutive_failures=0, opened_until=None, updated_at=_now()
        )
        db.add(health)
    health.consecutive_failures += 1
    health.last_error = error[:500]
    health.updated_at = _now()
    if health.consecutive_failures >= CIRCUIT_FAILURE_THRESHOLD:
        health.opened_until = _now() + CIRCUIT_OPEN_DURATION
    db.commit()


def _get_cache(db: Session, siret: str) -> CompanyLookupCache | None:
    return db.scalar(select(CompanyLookupCache).where(CompanyLookupCache.siret == siret))


def _is_fresh(cache_row: CompanyLookupCache) -> bool:
    fetched_at = cache_row.fetched_at
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=UTC)
    return _now() - fetched_at < timedelta(days=CACHE_TTL_DAYS)


def upsert_cache(
    db: Session,
    siret: str,
    result: CompanyLookupResult,
    *,
    source: CacheSource,
    http_status: int,
    provider_name: str,
) -> CompanyLookupCache:
    row = _get_cache(db, siret)
    payload = dataclasses.asdict(result)
    if row is None:
        row = CompanyLookupCache(
            siret=siret,
            payload=payload,
            source=source.value,
            http_status=http_status,
            fetched_at=_now(),
            provider=provider_name,
        )
        db.add(row)
    else:
        row.payload = payload
        row.source = source.value
        row.http_status = http_status
        row.fetched_at = _now()
        row.provider = provider_name
    db.flush()
    return row


@dataclasses.dataclass(frozen=True)
class LookupOutcome:
    source: str  # "api" | "cache" | "demo"
    stale: bool
    company: CompanyLookupResult


def lookup_company(db: Session, siret: str, provider: CompanyLookupProvider) -> LookupOutcome:
    if not is_valid_siret(siret):
        raise ApiError("siret_invalid", "Le SIRET est invalide (14 chiffres, clé de Luhn).")

    if is_circuit_open(db, provider.name):
        cached = _get_cache(db, siret)
        if cached is not None:
            return LookupOutcome(
                source=cached.source, stale=True, company=CompanyLookupResult(**cached.payload)
            )
        raise ApiError(
            "siret_lookup_unavailable",
            "Le service d'enrichissement est temporairement indisponible.",
        )

    cached = _get_cache(db, siret)
    if cached is not None and _is_fresh(cached):
        return LookupOutcome(
            source=cached.source, stale=False, company=CompanyLookupResult(**cached.payload)
        )

    try:
        result = provider.lookup(siret)
    except CompanyLookupNotFound as exc:
        raise ApiError("siret_not_found", "Aucune entreprise trouvée pour ce SIRET.") from exc
    except CompanyLookupUnavailable as exc:
        record_failure(db, provider.name, str(exc))
        if cached is not None:
            return LookupOutcome(
                source=cached.source, stale=True, company=CompanyLookupResult(**cached.payload)
            )
        raise ApiError(
            "siret_lookup_unavailable",
            "Le service d'enrichissement est temporairement indisponible.",
        ) from exc

    record_success(db, provider.name)
    upsert_cache(
        db, siret, result, source=CacheSource.API, http_status=200, provider_name=provider.name
    )
    return LookupOutcome(source="api", stale=False, company=result)
