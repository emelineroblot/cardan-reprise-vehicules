"""Smoke test **réel** contre un vrai projet Supabase Storage — jamais exécuté par défaut.

Contrairement à `tests/unit/test_storage_supabase.py` (mock `httpx.MockTransport`, toujours
actif), ce fichier appelle le vrai réseau et exige un vrai bucket. Activé uniquement si
`RUN_SUPABASE_LIVE_TESTS=1` **et** que `SUPABASE_URL`/`SUPABASE_SERVICE_KEY` sont renseignées
(déjà présentes dans `backend/.env` si un projet a été créé — jamais commitées, § `.gitignore`) :
la suite `pytest` complète doit rester **entièrement verte sans la moindre clé** (857+ tests),
ce module ne doit donc jamais tourner par accident en CI ou sur une machine sans compte Supabase.

Écrit puis nettoie systématiquement sous un préfixe dédié (`_LIVE_TEST_PREFIX`), jamais sous
`seed/`/`runtime/`/`demo/` — pas de risque de collision avec de vraies données.

Lancer explicitement :
`RUN_SUPABASE_LIVE_TESTS=1 pytest tests/integration/test_storage_supabase_live.py -v`
"""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest

from app.core.config import get_settings
from app.services.storage.supabase import SupabaseStorage

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_SUPABASE_LIVE_TESTS") != "1",
    reason="Réseau réel désactivé par défaut — RUN_SUPABASE_LIVE_TESTS=1 pour l'activer.",
)

_LIVE_TEST_PREFIX = "live-test-dev-backend"


@pytest.fixture
def live_storage() -> Generator[tuple[SupabaseStorage, str], None, None]:
    settings = get_settings()
    if not settings.supabase_storage_configured:
        pytest.skip("SUPABASE_URL/SUPABASE_SERVICE_KEY absentes — impossible de tester en réel.")
    assert settings.supabase_url is not None
    assert settings.supabase_service_key is not None
    storage = SupabaseStorage(
        base_url=settings.supabase_url, service_key=settings.supabase_service_key
    )
    bucket = settings.supabase_bucket
    yield storage, bucket
    # Nettoyage systématique, même si le test a échoué en cours de route.
    storage.delete_prefix(bucket=bucket, prefix=f"{_LIVE_TEST_PREFIX}/")


def test_save_load_exists_roundtrip(live_storage: tuple[SupabaseStorage, str]) -> None:
    storage, bucket = live_storage
    key = f"{_LIVE_TEST_PREFIX}/roundtrip/photo.png"
    content = b"\x89PNG\r\n\x1a\n" + b"x" * 200

    assert storage.exists(bucket=bucket, key=key) is False

    storage.save(bucket=bucket, key=key, content=content)

    assert storage.exists(bucket=bucket, key=key) is True
    assert storage.load(bucket=bucket, key=key) == content


def test_load_missing_key_raises_file_not_found(
    live_storage: tuple[SupabaseStorage, str],
) -> None:
    storage, bucket = live_storage
    with pytest.raises(FileNotFoundError):
        storage.load(bucket=bucket, key=f"{_LIVE_TEST_PREFIX}/absent.png")


def test_list_top_level_and_delete_prefix(live_storage: tuple[SupabaseStorage, str]) -> None:
    storage, bucket = live_storage
    storage.save(bucket=bucket, key=f"{_LIVE_TEST_PREFIX}/veh1/a.png", content=b"a")
    storage.save(bucket=bucket, key=f"{_LIVE_TEST_PREFIX}/veh2/b.png", content=b"b")

    top = storage.list_top_level(bucket=bucket, prefix=f"{_LIVE_TEST_PREFIX}/")
    assert sorted(top) == ["veh1", "veh2"]

    deleted = storage.delete_prefix(bucket=bucket, prefix=f"{_LIVE_TEST_PREFIX}/veh1/")
    assert deleted == 1
    assert storage.exists(bucket=bucket, key=f"{_LIVE_TEST_PREFIX}/veh1/a.png") is False
    assert storage.exists(bucket=bucket, key=f"{_LIVE_TEST_PREFIX}/veh2/b.png") is True
