"""Fixtures pytest — PostgreSQL réel, jamais SQLite (plan.md § 4 décision F).

Le modèle repose sur des index uniques partiels, `jsonb`, des colonnes générées et des index
fonctionnels : SQLite validerait un code qui casse en production. `alembic upgrade head`
s'applique une fois par session ; chaque test s'exécute dans une transaction annulée à la fin.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from collections.abc import Generator
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

BACKEND_DIR = Path(__file__).resolve().parent.parent

_TEST_DATABASE_URL = "postgresql+psycopg://cardan:cardan@localhost:5433/cardan_test"

os.environ["ENVIRONMENT"] = "test"
# Écrasement explicit (pas `setdefault`) : `.env` peut définir DATABASE_URL_DIRECT vers la base
# de dev, ce qui ferait tourner `alembic upgrade head` sur la mauvaise base (bug constaté).
os.environ["DATABASE_URL"] = _TEST_DATABASE_URL
os.environ["DATABASE_URL_DIRECT"] = _TEST_DATABASE_URL
os.environ.setdefault("JWT_SECRET", "test-secret-at-least-32-bytes-long-xxxxx")
os.environ.setdefault("CRON_SECRET", "test-cron-secret")
os.environ["COMPANY_LOOKUP_PROVIDER"] = "disabled"  # jamais de réseau réel pendant les tests
# Stockage photos — répertoire temporaire dédié à la session de test, jamais le `var/storage`
# de dev (§ 4 décision F : isolation complète). VAPID volontairement absent : le push réel
# reste désactivé par défaut en test (`app/services/push.py::is_push_enabled`), voir
# `tests/unit/test_push.py` pour le cas où il est explicitement activé.
os.environ["LOCAL_STORAGE_DIR"] = str(Path(tempfile.mkdtemp(prefix="cardan-test-storage-")))

from app.core.config import get_settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.enums import UserRole  # noqa: E402
from app.models.user import AppUser  # noqa: E402

get_settings.cache_clear()
settings = get_settings()


def _admin_database_url() -> str:
    """Chaîne de connexion à la base `postgres` par défaut, pour créer/droper la base de test."""
    return settings.database_url.rsplit("/", 1)[0] + "/postgres"


@pytest.fixture(scope="session", autouse=True)
def _prepare_test_database() -> Generator[None, None, None]:
    from sqlalchemy import text as sa_text

    db_name = settings.database_url.rsplit("/", 1)[1]
    admin_engine = create_engine(_admin_database_url(), isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(sa_text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        conn.execute(sa_text(f'CREATE DATABASE "{db_name}"'))
    admin_engine.dispose()

    env = os.environ.copy()
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(BACKEND_DIR),
        env=env,
        check=True,
    )
    yield


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(settings.database_url)
    yield eng
    eng.dispose()


@pytest.fixture
def db_session(engine) -> Generator[Session, None, None]:
    """Une transaction externe par test, annulée à la fin (isolation rapide et parfaite)."""
    connection = engine.connect()
    transaction = connection.begin()
    session_factory = sessionmaker(bind=connection, expire_on_commit=False)
    session = session_factory()

    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(sess, trans):
        nonlocal nested
        if not nested.is_active:
            nested = connection.begin_nested()

    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()


@pytest.fixture
def app_with_db(db_session):
    """Instancie l'app FastAPI en substituant `get_db` par la session de test transactionnelle."""
    from app.db.session import get_db
    from app.main import app as fastapi_app

    def _override_get_db() -> Generator[Session, None, None]:
        yield db_session

    fastapi_app.dependency_overrides[get_db] = _override_get_db
    yield fastapi_app
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
def client(app_with_db) -> Generator[TestClient, None, None]:
    with TestClient(app_with_db) as c:
        yield c


def make_user(db_session: Session, role: UserRole, email: str | None = None) -> AppUser:
    user = AppUser(
        id=uuid4(),
        email=email or f"{role.value}-{uuid4().hex[:8]}@example.com",
        password_hash=hash_password("test-password"),
        full_name=f"Test {role.value}",
        role=role.value,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


def login_client(client: TestClient, user: AppUser) -> TestClient:
    """Pose directement le cookie de session (évite de dépendre de /auth/login dans les tests
    qui ne testent pas l'authentification elle-même)."""
    from app.core.security import create_access_token

    token = create_access_token(user.id, user.role)
    client.cookies.set(settings.session_cookie_name, token)
    return client
