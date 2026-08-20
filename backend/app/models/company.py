"""`company`, `company_lookup_cache`, `lookup_health` — J1 (décision B, enrichissement SIRET)."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import CacheSource, SourceEnrichissement, TypeFlotte, check_in


class Company(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "company"

    siren: Mapped[str] = mapped_column(String(9), nullable=False)
    siret: Mapped[str] = mapped_column(String(14), nullable=False)
    denomination: Mapped[str] = mapped_column(String(255), nullable=False)
    forme_juridique: Mapped[str | None] = mapped_column(String(255), nullable=True)
    code_naf: Mapped[str | None] = mapped_column(String(10), nullable=True)
    libelle_naf: Mapped[str | None] = mapped_column(String(255), nullable=True)
    adresse_ligne1: Mapped[str] = mapped_column(String(255), nullable=False)
    code_postal: Mapped[str] = mapped_column(String(10), nullable=False)
    commune: Mapped[str] = mapped_column(String(255), nullable=False)
    pays: Mapped[str] = mapped_column(String(2), nullable=False, default="FR", server_default="FR")
    tranche_effectif: Mapped[str | None] = mapped_column(String(10), nullable=True)
    date_creation: Mapped[date | None] = mapped_column(nullable=True)
    type_flotte: Mapped[str] = mapped_column(String(20), nullable=False)
    source_enrichissement: Mapped[str] = mapped_column(String(10), nullable=False)
    enriched_at: Mapped[datetime | None] = mapped_column(nullable=True)
    contact_nom: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_telephone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_by_id: Mapped[UUID] = mapped_column(ForeignKey("app_user.id"), nullable=False)

    __table_args__ = (
        UniqueConstraint("siret", name="uq_company_siret"),
        CheckConstraint("siret ~ '^[0-9]{14}$'", name="siret_format"),
        CheckConstraint("siren = left(siret, 9)", name="siren_coherent_avec_siret"),
        CheckConstraint(f"type_flotte IN ({check_in(*TypeFlotte)})", name="type_flotte_valide"),
        CheckConstraint(
            f"source_enrichissement IN ({check_in(*SourceEnrichissement)})",
            name="source_enrichissement_valide",
        ),
        Index("ix_company_siren", "siren"),
        Index("ix_company_denomination", "denomination"),
        Index("ix_company_type_flotte", "type_flotte"),
    )


class CompanyLookupCache(Base):
    """Cache TTL 30 j des réponses du provider SIRET — persisté en base (§ 3.8-4)."""

    __tablename__ = "company_lookup_cache"

    siret: Mapped[str] = mapped_column(String(14), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    source: Mapped[str] = mapped_column(String(10), nullable=False)
    http_status: Mapped[int] = mapped_column(Integer, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)

    __table_args__ = (
        CheckConstraint(f"source IN ({check_in(*CacheSource)})", name="source_valide"),
        Index("ix_company_lookup_cache_fetched_at", "fetched_at"),
    )


class LookupHealth(Base):
    """Circuit breaker du lookup SIRET — persisté (une instance serverless repart de zéro sinon)."""

    __tablename__ = "lookup_health"

    provider: Mapped[str] = mapped_column(String(50), primary_key=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    opened_until: Mapped[datetime | None] = mapped_column(nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)
