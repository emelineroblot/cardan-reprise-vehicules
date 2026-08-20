"""`work_order`, `work_order_line` — J3. Le coût réel = somme des lignes, jamais un champ libre."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Computed,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import WorkOrderLineCategorie, WorkOrderState, WorkOrderType, check_in


class WorkOrder(Base):
    __tablename__ = "work_order"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    vehicle_id: Mapped[UUID] = mapped_column(ForeignKey("vehicle.id"), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    montant_estime_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by_id: Mapped[UUID] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    assigned_to_id: Mapped[UUID | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    commentaire_atelier: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(f"type IN ({check_in(*WorkOrderType)})", name="type_valide"),
        CheckConstraint(f"state IN ({check_in(*WorkOrderState)})", name="state_valide"),
        Index("ix_work_order_vehicle", "vehicle_id"),
        Index("ix_work_order_state_assignee", "state", "assigned_to_id"),
    )


class WorkOrderLine(Base):
    """`montant_cents` est une colonne `GENERATED ALWAYS AS ... STORED` (plan.md § 5.1) —
    piège classique de `autogenerate` (§ 9), à vérifier à la main dans la migration."""

    __tablename__ = "work_order_line"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    work_order_id: Mapped[UUID] = mapped_column(ForeignKey("work_order.id"), nullable=False)
    libelle: Mapped[str] = mapped_column(String(255), nullable=False)
    categorie: Mapped[str] = mapped_column(String(20), nullable=False)
    quantite: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    prix_unitaire_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    montant_cents: Mapped[int] = mapped_column(
        Integer,
        Computed("round(quantite * prix_unitaire_cents)::integer", persisted=True),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))

    __table_args__ = (
        CheckConstraint(
            f"categorie IN ({check_in(*WorkOrderLineCategorie)})", name="categorie_valide"
        ),
        CheckConstraint("quantite > 0", name="quantite_positive"),
        CheckConstraint("prix_unitaire_cents >= 0", name="prix_unitaire_positif"),
    )
