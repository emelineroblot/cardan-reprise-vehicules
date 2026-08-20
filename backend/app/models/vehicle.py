"""`vehicle`, `vehicle_state_transition`, `duplicate_review` — J1, table centrale du modèle.

Voir plan.md § 5.1 et § 5.3 (automate d'états) et § 4 décision A (dédoublonnage).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import Boite, Energie, RefusMotif, VehicleState, check_in

if TYPE_CHECKING:
    from app.models.company import Company


class Vehicle(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "vehicle"

    reference: Mapped[str] = mapped_column(String(20), nullable=False)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("company.id"), nullable=False)
    intake_batch_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("intake_batch.id"), nullable=True
    )
    state: Mapped[str] = mapped_column(
        String(20), nullable=False, default=VehicleState.BROUILLON.value
    )
    marque: Mapped[str] = mapped_column(String(100), nullable=False)
    modele: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Calculé à l'écriture par le service `normalize` (plan.md § 6, vague 3) — sert au scoring.
    modele_normalise: Mapped[str | None] = mapped_column(String(255), nullable=True)
    energie: Mapped[str | None] = mapped_column(String(20), nullable=True)
    boite: Mapped[str | None] = mapped_column(String(20), nullable=True)
    couleur: Mapped[str | None] = mapped_column(String(50), nullable=True)
    vin: Mapped[str | None] = mapped_column(String(17), nullable=True)
    vin_normalise: Mapped[str | None] = mapped_column(String(17), nullable=True)
    immatriculation: Mapped[str | None] = mapped_column(String(20), nullable=True)
    immat_normalisee: Mapped[str | None] = mapped_column(String(10), nullable=True)
    date_mise_en_circulation: Mapped[date | None] = mapped_column(nullable=True)
    kilometrage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    date_proposition: Mapped[date] = mapped_column(nullable=False)
    prix_achat_negocie_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    valeur_revente_estimee_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    frais_transport_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    commentaire: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[UUID] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    assigned_driver_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("app_user.id"), nullable=True
    )
    refus_motif: Mapped[str | None] = mapped_column(String(20), nullable=True)
    refus_commentaire: Mapped[str | None] = mapped_column(Text, nullable=True)
    state_changed_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))

    # Frise d'historique d'états (front, plan.md § 6 vague 4) — lecture seule, triée
    # chronologiquement. Le nom `state_history` matche directement `VehicleRead.state_history`.
    # Chargée explicitement (`selectinload`) sur la fiche détail uniquement — jamais sur la
    # liste, qui ne l'affiche pas (revue § 🟠 « N+1 sur la liste de suivi »).
    state_history: Mapped[list[VehicleStateTransition]] = relationship(
        order_by="VehicleStateTransition.occurred_at",
        viewonly=True,
    )

    # Dénomination société — la liste de suivi comme la fiche l'affichent (revue § 🟠
    # « la colonne Société est vide partout »). Chargée via `joinedload` (une jointure, jamais
    # de N+1) dans les deux endpoints qui la lisent.
    company: Mapped[Company] = relationship(viewonly=True)

    __table_args__ = (
        UniqueConstraint("reference", name="uq_vehicle_reference"),
        # Index partiels — c'est précisément ce que `autogenerate` oublie le plus souvent
        # (plan.md § 9). Blocage dur du doublon exact, garanti en base (étape 0, décision A).
        Index(
            "uq_vehicle_vin_normalise",
            "vin_normalise",
            unique=True,
            postgresql_where=text("vin_normalise IS NOT NULL"),
        ),
        Index(
            "uq_vehicle_immat_normalisee",
            "immat_normalisee",
            unique=True,
            postgresql_where=text("immat_normalisee IS NOT NULL"),
        ),
        CheckConstraint(f"state IN ({check_in(*VehicleState)})", name="state_valide"),
        CheckConstraint(
            f"energie IS NULL OR energie IN ({check_in(*Energie)})", name="energie_valide"
        ),
        CheckConstraint(f"boite IS NULL OR boite IN ({check_in(*Boite)})", name="boite_valide"),
        CheckConstraint(
            f"refus_motif IS NULL OR refus_motif IN ({check_in(*RefusMotif)})",
            name="refus_motif_valide",
        ),
        CheckConstraint("kilometrage IS NULL OR kilometrage >= 0", name="kilometrage_positif"),
        CheckConstraint(
            "prix_achat_negocie_cents IS NULL OR prix_achat_negocie_cents >= 0",
            name="prix_achat_positif",
        ),
        CheckConstraint("frais_transport_cents >= 0", name="frais_transport_positif"),
        CheckConstraint(
            "vin_normalise IS NULL OR vin_normalise ~ '^[A-HJ-NPR-Z0-9]{17}$'",
            name="vin_normalise_format",
        ),
        CheckConstraint(
            f"state <> '{VehicleState.REFUSE.value}' OR refus_motif IS NOT NULL",
            name="refus_motif_requis_si_refuse",
        ),
        Index("ix_vehicle_company_date", "company_id", "date_proposition"),
        Index("ix_vehicle_state", "state"),
        Index("ix_vehicle_assigned_driver_state", "assigned_driver_id", "state"),
        Index("ix_vehicle_created_by_created_at", "created_by_id", "created_at"),
        Index("ix_vehicle_date_proposition", "date_proposition"),
    )


class VehicleStateTransition(Base):
    """Historique d'états — source des délais de cycle en J3, alimenté à chaque transition."""

    __tablename__ = "vehicle_state_transition"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    vehicle_id: Mapped[UUID] = mapped_column(ForeignKey("vehicle.id"), nullable=False)
    from_state: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_state: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))

    __table_args__ = (Index("ix_vst_vehicle_occurred", "vehicle_id", "occurred_at"),)


class DuplicateReview(Base):
    """Verdict d'arbitrage persistant — un `not_duplicate` est définitif (décision A, étape 5)."""

    __tablename__ = "duplicate_review"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    vehicle_a_id: Mapped[UUID] = mapped_column(ForeignKey("vehicle.id"), nullable=False)
    vehicle_b_id: Mapped[UUID] = mapped_column(ForeignKey("vehicle.id"), nullable=False)
    verdict: Mapped[str] = mapped_column(String(20), nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    features: Mapped[dict] = mapped_column(JSONB, nullable=False)
    decided_by_id: Mapped[UUID] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))

    __table_args__ = (
        CheckConstraint("vehicle_a_id < vehicle_b_id", name="paire_canonique"),
        UniqueConstraint("vehicle_a_id", "vehicle_b_id", name="uq_duplicate_review_paire"),
        CheckConstraint("verdict IN ('duplicate', 'not_duplicate')", name="verdict_valide"),
    )
