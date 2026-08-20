"""`intake_batch` — J1. Saisie en lot d'une flotte : clé anti-faux-positif (décision A)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPKMixin


class IntakeBatch(UUIDPKMixin, Base):
    __tablename__ = "intake_batch"

    company_id: Mapped[UUID] = mapped_column(ForeignKey("company.id"), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by_id: Mapped[UUID] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))

    __table_args__ = (Index("ix_intake_batch_company_id", "company_id"),)
