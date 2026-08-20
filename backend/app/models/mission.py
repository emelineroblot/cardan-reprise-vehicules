"""`mission` — table créée en J1, remplie en J2 (affectation chauffeur / rendez-vous)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import MissionState, check_in


class Mission(Base):
    __tablename__ = "mission"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    vehicle_id: Mapped[UUID] = mapped_column(ForeignKey("vehicle.id"), nullable=False)
    driver_id: Mapped[UUID] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    rdv_at: Mapped[datetime | None] = mapped_column(nullable=True)
    rdv_adresse: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rdv_contact_nom: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rdv_contact_telephone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    assigned_by_id: Mapped[UUID] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
    accepted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(f"state IN ({check_in(*MissionState)})", name="state_valide"),
        # Un seul chantier actif par véhicule, garanti en base (plan.md § 5.1).
        Index(
            "uq_mission_vehicle_active",
            "vehicle_id",
            unique=True,
            postgresql_where=text("state NOT IN ('terminee', 'annulee')"),
        ),
        Index("ix_mission_driver_state", "driver_id", "state"),
    )
