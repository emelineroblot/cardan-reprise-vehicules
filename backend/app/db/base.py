"""Base déclarative SQLAlchemy 2.0 — convention de nommage obligatoire (plan.md § 3.3).

Sans cette convention, `alembic revision --autogenerate` produit des noms de contraintes
instables et les `downgrade` cassent.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, MetaData, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Classe déclarative commune à tous les modèles du schéma `public`."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    # `Mapped[datetime]` seul retombe sur `DateTime()` NAIF (sans fuseau) — revue § 🟠. Le plan
    # § 5 impose `timestamptz` partout : ce mapping global couvre tous les modèles d'un coup,
    # sans avoir à répéter `DateTime(timezone=True)` colonne par colonne.
    type_annotation_map = {
        datetime: DateTime(timezone=True),
    }


class UUIDPKMixin:
    """Clé primaire UUID générée côté base (`gen_random_uuid()`, extension `pgcrypto`)."""

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        default=uuid4,
    )


class TimestampMixin:
    """`created_at` / `updated_at` en `timestamptz`, alimentés côté base."""

    created_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"),
        onupdate=text("now()"),
        nullable=False,
    )
