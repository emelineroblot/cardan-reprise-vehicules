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
from sqlalchemy.orm import Mapped, mapped_column, relationship

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

    # Réponses de checklist (formulaire de contrôle, brief J2) — lecture seule, chargée
    # explicitement (`selectinload`) par les endpoints qui en ont besoin (même convention que
    # `Vehicle.state_history`, jamais de lazy load implicite en série).
    items: Mapped[list[InspectionItem]] = relationship(
        order_by="InspectionItem.item_template_id", viewonly=True
    )

    __table_args__ = (
        UniqueConstraint("client_uuid", name="uq_inspection_client_uuid"),
        # Une seule inspection par mission — miroir en base de la règle applicative de
        # `get_or_create_inspection` (`app/services/inspections.py`) : `RDV_PLANIFIE →
        # CONTROLE_EN_COURS` est la seule transition qui crée une inspection, jamais rejouée
        # pour une même mission (plan.md § 5.3). Contrainte totale, pas un index partiel : à la
        # différence de `Photo` (angles répétables selon la phase), il n'existe aucun cas
        # légitime de deux inspections pour la même mission, quel que soit son état.
        UniqueConstraint("mission_id", name="uq_inspection_mission"),
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
