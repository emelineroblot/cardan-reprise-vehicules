"""`SupabaseStorage` — implémentation Supabase Storage de `PhotoStorage` (bascule de déploiement).

Aucun de ces tests n'appelle un vrai projet Supabase : `httpx.MockTransport` simule les réponses
de l'API REST de stockage (upload multipart, liste, suppression par lot) telles que documentées
et vérifiées contre le code source de `storage3` (voir la docstring de module de
`app/services/storage/supabase.py`). La suite doit rester entièrement verte sans la moindre clé —
`tests/integration/test_storage_supabase_live.py` couvre, lui, le vrai réseau, ignoré par défaut.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.services.storage.supabase import SupabaseStorage, SupabaseStorageError

BASE_URL = "https://project-ref.supabase.co"
BUCKET = "cardan-photos"


class _RecordingTransport(httpx.MockTransport):
    """Enregistre chaque requête reçue, en plus de répondre via le handler fourni — pour pouvoir
    vérifier la forme exacte des appels (méthode, chemin, en-têtes, corps) sans réseau réel."""

    def __init__(self, handler) -> None:
        self.requests: list[httpx.Request] = []

        def _wrapped(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return handler(request)

        super().__init__(_wrapped)


def _storage(handler) -> tuple[SupabaseStorage, _RecordingTransport]:
    transport = _RecordingTransport(handler)
    client = httpx.Client(
        base_url=f"{BASE_URL}/storage/v1", headers={"apikey": "x", "Authorization": "Bearer x"},
        transport=transport,
    )
    storage = SupabaseStorage(base_url=BASE_URL, service_key="service-role-key", client=client)
    return storage, transport


def test_constructor_sets_apikey_and_bearer_headers_on_shared_client() -> None:
    storage = SupabaseStorage(base_url=BASE_URL, service_key="my-service-key")
    assert storage._client.headers["apikey"] == "my-service-key"
    assert storage._client.headers["Authorization"] == "Bearer my-service-key"
    # httpx normalise `base_url` avec un `/` final : on compare sans lui.
    assert str(storage._client.base_url).rstrip("/") == f"{BASE_URL}/storage/v1"


def test_constructor_strips_trailing_slash_from_base_url() -> None:
    storage = SupabaseStorage(base_url=f"{BASE_URL}/", service_key="k")
    assert str(storage._client.base_url).rstrip("/") == f"{BASE_URL}/storage/v1"


def test_save_posts_multipart_upload_with_upsert_header() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"Key": f"{BUCKET}/seed/veh1/photo1.png"})

    storage, transport = _storage(handler)
    storage.save(bucket=BUCKET, key="seed/veh1/photo1.png", content=b"\x89PNG-fake-bytes")

    assert len(transport.requests) == 1
    req = transport.requests[0]
    assert req.method == "POST"
    assert req.url.path == f"/storage/v1/object/{BUCKET}/seed/veh1/photo1.png"
    assert req.headers["x-upsert"] == "true"
    assert b"photo1.png" in req.content
    assert b"\x89PNG-fake-bytes" in req.content


def test_save_raises_supabase_storage_error_on_http_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"message": "boom"})

    storage, _ = _storage(handler)
    with pytest.raises(SupabaseStorageError):
        storage.save(bucket=BUCKET, key="seed/veh1/photo1.png", content=b"x")


def test_load_returns_bytes_on_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == f"/storage/v1/object/{BUCKET}/seed/veh1/photo1.png"
        return httpx.Response(200, content=b"the-bytes")

    storage, _ = _storage(handler)
    assert storage.load(bucket=BUCKET, key="seed/veh1/photo1.png") == b"the-bytes"


def test_load_raises_file_not_found_on_404() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "not found"})

    storage, _ = _storage(handler)
    with pytest.raises(FileNotFoundError):
        storage.load(bucket=BUCKET, key="seed/veh1/absent.png")


def test_load_raises_file_not_found_on_400_with_not_found_json_body() -> None:
    """Constaté contre un vrai projet Supabase : une clé absente répond **400**, pas 404, avec un
    corps `{"statusCode": "404", "error": "not_found", "code": "NoSuchKey"}` — c'est ce corps
    qu'il faut lire, pas le code HTTP de la réponse elle-même."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "statusCode": "404",
                "error": "not_found",
                "message": "Object not found",
                "code": "NoSuchKey",
            },
        )

    storage, _ = _storage(handler)
    with pytest.raises(FileNotFoundError):
        storage.load(bucket=BUCKET, key="seed/veh1/absent.png")


def test_load_raises_supabase_storage_error_on_other_http_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "forbidden"})

    storage, _ = _storage(handler)
    with pytest.raises(SupabaseStorageError):
        storage.load(bucket=BUCKET, key="seed/veh1/photo1.png")


def test_load_raises_supabase_storage_error_on_400_with_non_matching_json_body() -> None:
    """Un 400 dont le corps ne ressemble pas à un « objet absent » ne doit pas être avalé comme
    un `FileNotFoundError` silencieux — seule la forme précise observée en réel déclenche ce
    traitement spécial."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"statusCode": "400", "error": "bad_request"})

    storage, _ = _storage(handler)
    with pytest.raises(SupabaseStorageError):
        storage.load(bucket=BUCKET, key="seed/veh1/photo1.png")


def test_load_raises_supabase_storage_error_on_400_with_non_json_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, content=b"not json at all")

    storage, _ = _storage(handler)
    with pytest.raises(SupabaseStorageError):
        storage.load(bucket=BUCKET, key="seed/veh1/photo1.png")


def test_exists_true_on_200() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "HEAD"
        return httpx.Response(200)

    storage, _ = _storage(handler)
    assert storage.exists(bucket=BUCKET, key="seed/veh1/photo1.png") is True


def test_exists_false_on_404() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    storage, _ = _storage(handler)
    assert storage.exists(bucket=BUCKET, key="seed/veh1/absent.png") is False


def test_exists_false_on_400_without_json_body() -> None:
    """Constaté contre un vrai projet Supabase : une clé absente répond `400` sur `HEAD`, pas
    `404`, sans corps JSON exploitable — même comportement que `storage3` (voir la docstring de
    `SupabaseStorage.exists`)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400)

    storage, _ = _storage(handler)
    assert storage.exists(bucket=BUCKET, key="seed/veh1/absent.png") is False


def test_exists_false_on_any_non_200_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    storage, _ = _storage(handler)
    assert storage.exists(bucket=BUCKET, key="seed/veh1/photo1.png") is False


def test_read_url_matches_local_disk_storage_shape() -> None:
    """Même contrat que `LocalDiskStorage.read_url` — la lecture passe toujours par la route
    backend authentifiée (scoping par véhicule), jamais par une URL Supabase directe."""
    storage, _ = _storage(lambda request: httpx.Response(200))
    url = storage.read_url(bucket=BUCKET, key="runtime/veh1/photo1.png")
    assert url == f"/api/backend/v1/photos/file/{BUCKET}/runtime/veh1/photo1.png"


def _list_response(entries: list[dict]) -> httpx.Response:
    return httpx.Response(200, json=entries)


def test_list_top_level_returns_only_folder_entries() -> None:
    """Un objet réel porte un `id`, un dossier virtuel n'en porte pas — c'est ce qui distingue
    les deux dans la réponse Supabase (`list_top_level` ne doit renvoyer que les dossiers, comme
    `LocalDiskStorage.list_top_level`)."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == f"/storage/v1/object/list/{BUCKET}"
        body = json.loads(request.content)
        assert body["prefix"] == "seed/"
        return _list_response(
            [
                {"name": "veh1", "id": None, "metadata": None},
                {"name": "veh2", "id": None, "metadata": None},
                {"name": "orphan.png", "id": "abc-123", "metadata": {"size": 42}},
            ]
        )

    storage, _ = _storage(handler)
    assert storage.list_top_level(bucket=BUCKET, prefix="seed/") == ["veh1", "veh2"]


def test_list_top_level_normalizes_prefix_without_trailing_slash() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["prefix"] == "seed/"
        return _list_response([])

    storage, _ = _storage(handler)
    assert storage.list_top_level(bucket=BUCKET, prefix="seed") == []


def test_list_top_level_on_missing_prefix_returns_empty_list() -> None:
    storage, _ = _storage(lambda request: _list_response([]))
    assert storage.list_top_level(bucket=BUCKET, prefix="seed/") == []


def test_list_top_level_paginates_across_full_pages() -> None:
    """`_LIST_PAGE_SIZE` vaut 1000 : simule deux pages pleines suivies d'une page partielle pour
    vérifier que la pagination s'arrête bien dès qu'une page n'est pas pleine."""
    from app.services.storage import supabase as supabase_module

    page_size = supabase_module._LIST_PAGE_SIZE
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        offset = body["offset"]
        calls.append(offset)
        if offset == 0:
            return _list_response(
                [{"name": f"veh{i}", "id": None, "metadata": None} for i in range(page_size)]
            )
        if offset == page_size:
            return _list_response(
                [{"name": "veh-last", "id": None, "metadata": None}]
            )
        raise AssertionError(f"appel de pagination inattendu (offset={offset})")

    storage, _ = _storage(handler)
    result = storage.list_top_level(bucket=BUCKET, prefix="seed/")
    assert calls == [0, page_size]
    assert "veh-last" in result
    assert len(result) == page_size + 1


def test_delete_prefix_recurses_into_subfolders_before_deleting() -> None:
    """`seed/{vehicle}/` contient des fichiers directement, mais `delete_prefix` doit rester
    correct même si un préfixe contient un niveau de dossier supplémentaire — même garantie que
    `shutil.rmtree` côté `LocalDiskStorage`."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == f"/storage/v1/object/list/{BUCKET}":
            body = json.loads(request.content)
            prefix = body["prefix"]
            if prefix == "seed/veh1/":
                return _list_response(
                    [
                        {"name": "sub", "id": None, "metadata": None},
                        {"name": "photo1.png", "id": "id-1", "metadata": {}},
                    ]
                )
            if prefix == "seed/veh1/sub/":
                return _list_response([{"name": "photo2.png", "id": "id-2", "metadata": {}}])
            raise AssertionError(f"préfixe de listage inattendu : {prefix}")
        if request.method == "DELETE" and request.url.path == f"/storage/v1/object/{BUCKET}":
            body = json.loads(request.content)
            assert sorted(body["prefixes"]) == [
                "seed/veh1/photo1.png",
                "seed/veh1/sub/photo2.png",
            ]
            return httpx.Response(200, json=[{"name": p} for p in body["prefixes"]])
        raise AssertionError(f"requête inattendue : {request.method} {request.url.path}")

    storage, _ = _storage(handler)
    deleted = storage.delete_prefix(bucket=BUCKET, prefix="seed/veh1/")
    assert deleted == 2


def test_delete_prefix_on_missing_prefix_is_a_noop() -> None:
    storage, transport = _storage(lambda request: _list_response([]))
    assert storage.delete_prefix(bucket=BUCKET, prefix="seed/absent/") == 0
    # Aucun appel DELETE ne doit être fait si la liste est vide.
    assert all(r.method != "DELETE" for r in transport.requests)


def test_delete_prefix_batches_large_generations() -> None:
    """Vérifie le découpage en lots de `_DELETE_BATCH_SIZE` — sans lui, une génération de démo
    volumineuse (plusieurs centaines de photos) partirait dans un unique corps de requête."""
    from app.services.storage import supabase as supabase_module

    batch_size = supabase_module._DELETE_BATCH_SIZE
    n_files = batch_size + 5
    delete_calls: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return _list_response(
                [{"name": f"p{i}.png", "id": str(i), "metadata": {}} for i in range(n_files)]
            )
        body = json.loads(request.content)
        delete_calls.append(body["prefixes"])
        return httpx.Response(200, json=[{"name": p} for p in body["prefixes"]])

    storage, _ = _storage(handler)
    deleted = storage.delete_prefix(bucket=BUCKET, prefix="seed/veh1/")

    assert deleted == n_files
    assert len(delete_calls) == 2
    assert len(delete_calls[0]) == batch_size
    assert len(delete_calls[1]) == 5


def test_delete_prefix_raises_supabase_storage_error_on_http_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return _list_response([{"name": "p.png", "id": "1", "metadata": {}}])
        return httpx.Response(500, json={"message": "boom"})

    storage, _ = _storage(handler)
    with pytest.raises(SupabaseStorageError):
        storage.delete_prefix(bucket=BUCKET, prefix="seed/veh1/")
