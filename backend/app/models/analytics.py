"""`analytics.refresh_log` — plan.md § 3.7-5. Traçabilité du rafraîchissement des marts.

Seule table « réelle » du schéma `analytics` (le reste n'est que des vues dérivées, § 3.7-4) :
elle vit dans ce schéma pour rester co-localisée avec ce qu'elle trace, mais c'est une donnée
opérationnelle normale, gérée par Alembic comme n'importe quelle autre table.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import DemoResetStatus, check_in


class AnalyticsRefreshLog(Base):
    __tablename__ = "refresh_log"
    __table_args__ = (
        CheckConstraint(f"status IN ({check_in(*DemoResetStatus)})", name="status_valide"),
        {"schema": "analytics"},
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    mart_name: Mapped[str] = mapped_column(String(100), nullable=False)
    refreshed_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
