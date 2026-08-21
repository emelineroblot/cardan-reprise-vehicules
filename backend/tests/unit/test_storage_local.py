"""`LocalDiskStorage` — sauvegarde/lecture/purge, et refus des tentatives de traversée de
répertoire (brief J2, arbitrage « stockage local simulé »)."""

from __future__ import annotations

import pytest

from app.services.storage.local import LocalDiskStorage


def test_save_then_load_roundtrip(tmp_path) -> None:
    storage = LocalDiskStorage(tmp_path)
    storage.save(bucket="cardan-photos", key="runtime/veh1/photo1.jpg", content=b"hello")

    assert storage.exists(bucket="cardan-photos", key="runtime/veh1/photo1.jpg")
    assert storage.load(bucket="cardan-photos", key="runtime/veh1/photo1.jpg") == b"hello"


def test_load_missing_key_raises_file_not_found(tmp_path) -> None:
    storage = LocalDiskStorage(tmp_path)
    with pytest.raises(FileNotFoundError):
        storage.load(bucket="cardan-photos", key="runtime/absent.jpg")


def test_read_url_is_a_backend_route_not_a_filesystem_path(tmp_path) -> None:
    storage = LocalDiskStorage(tmp_path)
    url = storage.read_url(bucket="cardan-photos", key="runtime/veh1/photo1.jpg")
    assert str(tmp_path) not in url


def test_read_url_is_prefixed_for_direct_browser_consumption(tmp_path) -> None:
    """Le navigateur n'appelle jamais le backend en direct (rewrite Next `/api/backend`,
    docs/wiki/pieges-projet.md § « Module terrain / PWA (J2) ») : `url` doit être utilisable
    telle quelle dans un `<img src>`, sans que le front n'ait à en reconstruire le préfixe."""
    storage = LocalDiskStorage(tmp_path)
    url = storage.read_url(bucket="cardan-photos", key="runtime/veh1/photo1.jpg")
    assert url == "/api/backend/v1/photos/file/cardan-photos/runtime/veh1/photo1.jpg"


def test_delete_prefix_removes_only_matching_keys(tmp_path) -> None:
    storage = LocalDiskStorage(tmp_path)
    storage.save(bucket="cardan-photos", key="runtime/veh1/photo1.jpg", content=b"a")
    storage.save(bucket="cardan-photos", key="runtime/veh2/photo2.jpg", content=b"b")
    storage.save(bucket="cardan-photos", key="demo/placeholder.jpg", content=b"c")

    deleted = storage.delete_prefix(bucket="cardan-photos", prefix="runtime/")

    assert deleted == 2
    assert not storage.exists(bucket="cardan-photos", key="runtime/veh1/photo1.jpg")
    assert not storage.exists(bucket="cardan-photos", key="runtime/veh2/photo2.jpg")
    assert storage.exists(bucket="cardan-photos", key="demo/placeholder.jpg")


def test_delete_prefix_on_missing_prefix_is_a_noop(tmp_path) -> None:
    storage = LocalDiskStorage(tmp_path)
    assert storage.delete_prefix(bucket="cardan-photos", prefix="runtime/") == 0


def test_path_traversal_is_rejected(tmp_path) -> None:
    storage = LocalDiskStorage(tmp_path)
    with pytest.raises(ValueError):
        storage.load(bucket="cardan-photos", key="../../etc/passwd")


def test_list_top_level_returns_immediate_subdirectory_names(tmp_path) -> None:
    """Sert à `app/seed/demo.py::snapshot_stale_seed_photo_prefixes` — doit lister les segments
    immédiatement sous le préfixe (ex. les UUID de véhicule sous `seed/`), sans descendre plus
    profondément ni renvoyer de fichier."""
    storage = LocalDiskStorage(tmp_path)
    storage.save(bucket="cardan-photos", key="seed/veh1/photo1.jpg", content=b"a")
    storage.save(bucket="cardan-photos", key="seed/veh1/photo2.jpg", content=b"b")
    storage.save(bucket="cardan-photos", key="seed/veh2/photo3.jpg", content=b"c")
    storage.save(bucket="cardan-photos", key="runtime/veh3/photo4.jpg", content=b"d")

    assert storage.list_top_level(bucket="cardan-photos", prefix="seed/") == ["veh1", "veh2"]


def test_list_top_level_on_missing_prefix_returns_empty_list(tmp_path) -> None:
    storage = LocalDiskStorage(tmp_path)
    assert storage.list_top_level(bucket="cardan-photos", prefix="seed/") == []


def test_list_top_level_then_delete_prefix_purges_only_listed_entries(tmp_path) -> None:
    """Reproduit le motif « snapshot avant, purge sélective après » utilisé par
    `app/seed/demo.py::snapshot_stale_seed_photo_prefixes` / `purge_stale_seed_photos` : lister
    une génération, en écrire une nouvelle sous le même préfixe, puis ne purger que les entrées
    de la génération photographiée — jamais celles écrites depuis."""
    storage = LocalDiskStorage(tmp_path)
    storage.save(bucket="cardan-photos", key="seed/old-veh/photo1.jpg", content=b"a")

    stale = storage.list_top_level(bucket="cardan-photos", prefix="seed/")
    assert stale == ["old-veh"]

    # La "nouvelle génération" apparaît sous le même préfixe avant la purge.
    storage.save(bucket="cardan-photos", key="seed/new-veh/photo2.jpg", content=b"b")

    for entry in stale:
        storage.delete_prefix(bucket="cardan-photos", prefix=f"seed/{entry}/")

    assert not storage.exists(bucket="cardan-photos", key="seed/old-veh/photo1.jpg")
    assert storage.exists(bucket="cardan-photos", key="seed/new-veh/photo2.jpg")
