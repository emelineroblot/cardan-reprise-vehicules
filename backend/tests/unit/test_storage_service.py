"""`get_storage_backend` — point de bascule unique entre `LocalDiskStorage` et `SupabaseStorage`
(brief J2/déploiement, `app/services/storage/service.py`).

Règle vérifiée ici, la plus importante du module : **sans les deux clés Supabase, le disque local
reste actif** — aucun développement local ne doit dépendre d'un compte tiers existant. `get_
storage_backend` est `lru_cache`d (singleton process) : chaque test le vide avant/après. La
`Settings` vue par `get_storage_backend` est injectée en monkeypatchant `get_settings` **dans le
module `service`** avec `_env_file=None` — jamais en manipulant `os.environ`/le `.env` local :
un `.env` de développement peut légitimement contenir de vraies clés Supabase (pour les tests
d'intégration réels, cf. `test_storage_supabase_live.py`), et `delenv` ne les masquerait pas
puisque pydantic-settings retomberait alors sur le fichier `.env` lui-même."""

from __future__ import annotations

from collections.abc import Generator

import pytest

from app.core.config import Settings
from app.services.storage import service as storage_service
from app.services.storage.local import LocalDiskStorage
from app.services.storage.supabase import SupabaseStorage


def _settings(**overrides: str | None) -> Settings:
    base: dict[str, str | None] = {"database_url": "postgresql+psycopg://x:x@localhost/x"}
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[call-arg,arg-type]


@pytest.fixture(autouse=True)
def _clear_storage_backend_cache() -> Generator[None, None, None]:
    storage_service.get_storage_backend.cache_clear()
    yield
    storage_service.get_storage_backend.cache_clear()


def test_returns_local_disk_storage_without_supabase_keys(monkeypatch) -> None:
    monkeypatch.setattr(storage_service, "get_settings", lambda: _settings())

    backend = storage_service.get_storage_backend()

    assert isinstance(backend, LocalDiskStorage)


def test_returns_local_disk_storage_with_only_one_supabase_value(monkeypatch) -> None:
    monkeypatch.setattr(
        storage_service,
        "get_settings",
        lambda: _settings(supabase_url="https://x.supabase.co", supabase_service_key=None),
    )

    backend = storage_service.get_storage_backend()

    assert isinstance(backend, LocalDiskStorage)


def test_returns_supabase_storage_with_both_supabase_values(monkeypatch) -> None:
    monkeypatch.setattr(
        storage_service,
        "get_settings",
        lambda: _settings(
            supabase_url="https://x.supabase.co", supabase_service_key="service-role-key"
        ),
    )

    backend = storage_service.get_storage_backend()

    assert isinstance(backend, SupabaseStorage)


def test_result_is_cached_across_calls(monkeypatch) -> None:
    monkeypatch.setattr(storage_service, "get_settings", lambda: _settings())

    assert storage_service.get_storage_backend() is storage_service.get_storage_backend()
