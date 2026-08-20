"""`vehicle_cost` — J3, coûts hors atelier (transport, carburant, administratif...)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import VehicleCostType, check_in


class VehicleCost(Base):
    __tablename__ = "vehicle_cost"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    vehicle_id: Mapped[UUID] = mapped_column(ForeignKey("vehicle.id"), nullable=False)
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    montant_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    commentaire: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[UUID] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))

    __table_args__ = (
        CheckConstraint(f"type IN ({check_in(*VehicleCostType)})", name="type_valide"),
    )
