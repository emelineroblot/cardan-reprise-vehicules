"""`checklist_template`, `checklist_item_template` — J1, référentiel utilisé dès J2."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import ChecklistCategorie, ResponseType, check_in


class ChecklistTemplate(Base):
    __tablename__ = "checklist_template"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    libelle: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)

    __table_args__ = (UniqueConstraint("code", name="uq_checklist_template_code"),)


class ChecklistItemTemplate(Base):
    __tablename__ = "checklist_item_template"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    template_id: Mapped[UUID] = mapped_column(ForeignKey("checklist_template.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    libelle: Mapped[str] = mapped_column(String(255), nullable=False)
    categorie: Mapped[str] = mapped_column(String(20), nullable=False)
    ordre: Mapped[int] = mapped_column(Integer, nullable=False)
    is_required: Mapped[bool] = mapped_column(nullable=False, default=True)
    response_type: Mapped[str] = mapped_column(String(20), nullable=False)

    __table_args__ = (
        UniqueConstraint("template_id", "code", name="uq_checklist_item_template_template_code"),
        CheckConstraint(f"categorie IN ({check_in(*ChecklistCategorie)})", name="categorie_valide"),
        CheckConstraint(
            f"response_type IN ({check_in(*ResponseType)})", name="response_type_valide"
        ),
    )
