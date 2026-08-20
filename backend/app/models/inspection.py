"""`inspection`, `inspection_item` — J2. Colonnes posées dès J1 (décision C : idempotence)."""

from __future__ import annotations

from datetime import datetime
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
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import EtatGeneral, InspectionConclusion, check_in


class Inspection(Base):
    __tablename__ = "inspection"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    vehicle_id: Mapped[UUID] = mapped_column(ForeignKey("vehicle.id"), nullable=False)
    mission_id: Mapped[UUID] = mapped_column(ForeignKey("mission.id"), nullable=False)
    driver_id: Mapped[UUID] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    template_id: Mapped[UUID] = mapped_column(ForeignKey("checklist_template.id"), nullable=False)
    client_uuid: Mapped[UUID] = mapped_column(nullable=False)
    started_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
    submitted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    kilometrage_releve: Mapped[int | None] = mapped_column(Integer, nullable=True)
    etat_general: Mapped[str | None] = mapped_column(String(10), nullable=True)
    conclusion: Mapped[str | None] = mapped_column(String(20), nullable=True)
    commentaire: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))

    __table_args__ = (
        UniqueConstraint("client_uuid", name="uq_inspection_client_uuid"),
        CheckConstraint(
            f"etat_general IS NULL OR etat_general IN ({check_in(*EtatGeneral)})",
            name="etat_general_valide",
        ),
        CheckConstraint(
            f"conclusion IS NULL OR conclusion IN ({check_in(*InspectionConclusion)})",
            name="conclusion_valide",
        ),
        Index("ix_inspection_vehicle", "vehicle_id"),
    )


class InspectionItem(Base):
    __tablename__ = "inspection_item"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    inspection_id: Mapped[UUID] = mapped_column(ForeignKey("inspection.id"), nullable=False)
    item_template_id: Mapped[UUID] = mapped_column(
        ForeignKey("checklist_item_template.id"), nullable=False
    )
    valeur_bool: Mapped[bool | None] = mapped_column(nullable=True)
    valeur_note: Mapped[int | None] = mapped_column(Integer, nullable=True)
    valeur_texte: Mapped[str | None] = mapped_column(Text, nullable=True)
    valeur_num: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    commentaire: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_id: Mapped[UUID | None] = mapped_column(ForeignKey("photo.id"), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "inspection_id", "item_template_id", name="uq_inspection_item_inspection_template"
        ),
    )
