"""`demo_reset_run` — posée en J1, alimentée par le reset nocturne (décision D)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import DemoResetStatus, check_in


class DemoResetRun(Base):
    __tablename__ = "demo_reset_run"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    started_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    seed_version: Mapped[str] = mapped_column(String(50), nullable=False)
    rows_created: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(f"status IN ({check_in(*DemoResetStatus)})", name="status_valide"),
    )
