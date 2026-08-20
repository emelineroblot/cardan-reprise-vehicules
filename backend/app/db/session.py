"""Engine et session SQLAlchemy — sync (plan.md § 3.3), pool réduit adapté au serverless.

Voir plan.md § 3.8-1/2 : pool_size=1, max_overflow=2, pool_pre_ping=True, pool_recycle=280,
et `prepared_statement_cache_size=0` quand on passe par le pooler Neon (mode transaction).
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

_connect_args: dict[str, object] = {}
if settings.is_remote:
    # PgBouncer en mode transaction : les instructions préparées ne survivent pas au multiplexage.
    # `is_remote` (pas seulement `production`) : un déploiement *preview* est aussi derrière
    # PgBouncer (revue § 🟡).
    _connect_args["prepare_threshold"] = None

engine = create_engine(
    settings.database_url,
    pool_size=1,
    max_overflow=2,
    pool_pre_ping=True,
    pool_recycle=280,
    connect_args=_connect_args,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """Dépendance FastAPI : une session par requête, fermée systématiquement."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
