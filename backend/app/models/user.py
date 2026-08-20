"""`app_user` — J1. Compte applicatif, un des 4 rôles cloisonnés (plan.md § 3.4)."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import UserRole, check_in


class AppUser(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "app_user"

    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    telephone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)

    __table_args__ = (
        # Unicité fonctionnelle sur lower(email) — pas d'extension `citext` (plan.md § 5.1).
        # Index fonctionnel : `alembic --autogenerate` ne le détecte pas fiablement, à vérifier
        # à la main dans la migration (plan.md § 9 — risque migration).
        Index("uq_app_user_email_lower", text("lower(email)"), unique=True),
        Index("ix_app_user_role", "role"),
        CheckConstraint(f"role IN ({check_in(*UserRole)})", name="role_valide"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AppUser {self.email} ({self.role})>"
