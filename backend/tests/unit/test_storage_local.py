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
    assert url == "/api/v1/photos/file/cardan-photos/runtime/veh1/photo1.jpg"
    assert str(tmp_path) not in url


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
