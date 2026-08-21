"""Implémentation Supabase Storage de `PhotoStorage` — bascule de déploiement (brief J2, arbitrage
« stockage local simulé, Supabase Storage au déploiement », `docs/wiki/architecture.md` §
« Stockage des photos »). Branchée dans `service.py`, jamais importée ailleurs.

Appelle directement l'API REST publique de Supabase Storage via `httpx` (déjà une dépendance de
base, cf. `app/services/company_lookup/`) plutôt que le SDK `storage3`/`supabase-py` : ce dernier
tire `yarl`, `deprecation` et l'extra `httpx[http2]` pour un gain nul ici — la forme des requêtes
(upload multipart avec `x-upsert`, liste par `POST .../object/list/{bucket}`, suppression par
`DELETE .../object/{bucket}` avec un tableau de chemins complets sous la clé `prefixes`) a d'abord
été établie par lecture du code source de `storage3` (paquet publié sur PyPI), **puis validée en
conditions réelles** contre le projet Supabase déjà configuré dans `backend/.env` au moment de ce
développement (bucket `cardan-photos` existant) : écriture, lecture, `exists`, listage et
suppression par lot exercés pour de vrai, nettoyés après coup — voir `docs/wiki/deploiement.md`
§ reset nocturne pour les chiffres mesurés. `tests/integration/test_storage_supabase_live.py`
(ignoré par défaut, activé par variable d'environnement) permet de rejouer ce smoke test à volonté
contre un nouveau projet.

Trois pièges trouvés par cette validation réelle, pas par lecture de documentation :
- `DELETE .../object/{bucket}` n'accepte que des chemins **complets** sous la clé `prefixes`
  (malgré son nom, ce n'est pas un préfixe façon système de fichiers) — il n'y a pas d'équivalent
  serveur d'un `rm -r` par préfixe. `delete_prefix` liste donc récursivement tous les objets sous
  le préfixe demandé avant de les supprimer par lot.
- `HEAD .../object/{bucket}/{clé}` sur une clé absente répond **400, pas 404**, sans corps JSON
  exploitable (constaté contre le vrai projet). `exists` traite donc tout statut différent de 200
  comme « absent », sans tenter de distinguer les codes d'erreur — voir sa docstring.
- `GET .../object/{bucket}/{clé}` sur une clé absente répond, lui aussi, **400 et non 404** — mais
  avec un corps JSON exploitable cette fois : `{"statusCode": "404", "error": "not_found", "code":
  "NoSuchKey", ...}`. C'est ce corps, pas le code HTTP de la réponse, qui porte l'information
  fiable. `load` inspecte donc le corps avant de conclure à une erreur générique — voir
  `_is_not_found_body`.
"""

from __future__ import annotations

import mimetypes
from typing import Any

import httpx

from app.services.storage.base import PhotoStorage

# Une même page de résultats suffit très largement au volume de ce projet (~90 véhicules, quelques
# centaines de photos) ; la pagination protège seulement contre un dépassement inattendu, jamais
# sensée être atteinte en usage normal.
_LIST_PAGE_SIZE = 1000
_MAX_LIST_PAGES = 20
# Nombre de chemins par appel `DELETE` — évite un corps de requête déraisonnablement gros si un
# préfixe venait à contenir un très grand nombre d'objets.
_DELETE_BATCH_SIZE = 100
_DEFAULT_TIMEOUT_SECONDS = 20.0


class SupabaseStorageError(RuntimeError):
    """Erreur renvoyée par l'API Supabase Storage (statut HTTP en échec, hors 404 sur lecture)."""


class SupabaseStorage(PhotoStorage):
    def __init__(
        self,
        *,
        base_url: str,
        service_key: str,
        timeout: float = _DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        storage_base_url = base_url.rstrip("/") + "/storage/v1"
        headers = {
            # Kong (la passerelle API Supabase) exige `apikey` sur toute requête ; `Authorization`
            # est ensuite ce que le service de stockage lit pour l'autorisation elle-même — la clé
            # `service_role` contourne les policies RLS du bucket (comportement voulu : c'est le
            # backend, jamais le navigateur, qui écrit).
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
        }
        # Un client unique, partagé par toutes les méthodes (l'instance est mise en cache par
        # `get_storage_backend`, cf. `service.py`) : `httpx.Client` réutilise ses connexions
        # (keep-alive), ce qui compte quand des centaines d'appels sont faits en séquence (voir
        # `docs/wiki/deploiement.md` § reset nocturne). Le nombre de connexions gardées ouvertes
        # est volontairement généreux pour ne pas pénaliser une future parallélisation des envois.
        self._client = client or httpx.Client(
            base_url=storage_base_url,
            headers=headers,
            timeout=timeout,
            limits=httpx.Limits(max_connections=32, max_keepalive_connections=32),
        )

    def _object_path(self, *, bucket: str, key: str) -> str:
        return f"/object/{bucket}/{key.strip('/')}"

    def save(self, *, bucket: str, key: str, content: bytes) -> None:
        content_type = mimetypes.guess_type(key)[0] or "application/octet-stream"
        filename = key.rsplit("/", 1)[-1]
        response = self._client.post(
            self._object_path(bucket=bucket, key=key),
            # `x-upsert: true` : les clés sont générées côté serveur avec un UUID
            # (`app/services/photos.py`, `app/seed/demo.py`) — une collision n'arrive jamais en
            # usage normal, mais upsert rend un éventuel rejeu (retry réseau) idempotent plutôt que
            # de le faire échouer sur un conflit.
            headers={"x-upsert": "true"},
            files={"file": (filename, content, content_type)},
        )
        if response.status_code >= 400:
            raise SupabaseStorageError(
                f"Échec de l'écriture de {bucket}/{key} (HTTP {response.status_code}) : "
                f"{response.text}"
            )

    def load(self, *, bucket: str, key: str) -> bytes:
        response = self._client.get(self._object_path(bucket=bucket, key=key))
        if response.status_code >= 400:
            if response.status_code == 404 or self._is_not_found_body(response):
                raise FileNotFoundError(f"Fichier introuvable : {bucket}/{key}")
            raise SupabaseStorageError(
                f"Échec de la lecture de {bucket}/{key} (HTTP {response.status_code}) : "
                f"{response.text}"
            )
        return response.content

    @staticmethod
    def _is_not_found_body(response: httpx.Response) -> bool:
        """L'API réelle a été observée renvoyant un statut HTTP **400** (pas 404) sur `GET` pour
        une clé absente, avec un corps JSON `{"statusCode": "404", "error": "not_found", "code":
        "NoSuchKey", ...}` — c'est ce corps, pas le code HTTP, qui porte l'information fiable
        (constaté contre le vrai projet ; possiblement lié au proxy Kong devant le service de
        stockage). Défensif sur un corps non-JSON ou incomplet : ne jamais lever autre chose
        qu'une non-correspondance dans ce cas, laissée à l'appelant via `False`."""
        try:
            body = response.json()
        except ValueError:
            return False
        return (
            str(body.get("statusCode")) == "404"
            or body.get("error") == "not_found"
            or body.get("code") == "NoSuchKey"
        )

    def exists(self, *, bucket: str, key: str) -> bool:
        """`HEAD` renvoie un corps vide sur toute réponse en échec — l'API réelle a été observée
        renvoyant `400` (pas `404`) pour une clé absente, sans corps JSON exploitable pour
        distinguer « objet absent » d'une autre erreur côté requête (constaté en pratique contre
        un vrai projet, `storage3` traite le même cas de la même façon : toute réponse HEAD non
        `200` vaut « absent »). Un vrai souci de configuration (mauvaise clé, bucket inexistant)
        se voit de toute façon ailleurs — `save`/`load` lèvent, eux, sur un corps JSON exploitable.
        """
        response = self._client.head(self._object_path(bucket=bucket, key=key))
        return response.status_code == 200

    def read_url(self, *, bucket: str, key: str) -> str:
        # Même route backend authentifiée que `LocalDiskStorage`, volontairement — c'est elle qui
        # scope la lecture par véhicule (`scope_vehicles`, `app/api/v1/photos.py::get_photo_file`).
        # Une URL signée Supabase directe donnerait un accès en lecture à quiconque la possède,
        # sans ce scoping ; retraiter ce choix est noté comme travail futur possible dans
        # `docs/wiki/architecture.md` § Stockage des photos, pas une exigence de ce jalon.
        return f"/api/backend/v1/photos/file/{bucket}/{key}"

    def _list_page(
        self, *, bucket: str, prefix: str, limit: int, offset: int
    ) -> list[dict[str, Any]]:
        response = self._client.post(
            f"/object/list/{bucket}",
            json={
                "prefix": prefix,
                "limit": limit,
                "offset": offset,
                "sortBy": {"column": "name", "order": "asc"},
            },
        )
        if response.status_code >= 400:
            raise SupabaseStorageError(
                f"Échec du listage de {bucket}/{prefix} (HTTP {response.status_code}) : "
                f"{response.text}"
            )
        data: list[dict[str, Any]] = response.json()
        return data

    def _list_all_entries(self, *, bucket: str, prefix: str) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        offset = 0
        for _ in range(_MAX_LIST_PAGES):
            page = self._list_page(
                bucket=bucket, prefix=prefix, limit=_LIST_PAGE_SIZE, offset=offset
            )
            entries.extend(page)
            if len(page) < _LIST_PAGE_SIZE:
                break
            offset += _LIST_PAGE_SIZE
        return entries

    def list_top_level(self, *, bucket: str, prefix: str) -> list[str]:
        normalized = prefix if prefix.endswith("/") or prefix == "" else f"{prefix}/"
        entries = self._list_all_entries(bucket=bucket, prefix=normalized)
        # Un objet réel porte un `id` ; un "dossier" virtuel (un préfixe intermédiaire sous lequel
        # d'autres objets existent) est renvoyé sans `id` ni `metadata` — c'est le seul signal
        # disponible pour distinguer les deux dans la réponse de l'API Supabase Storage.
        return sorted(entry["name"] for entry in entries if entry.get("id") is None)

    def _collect_object_paths_recursive(self, *, bucket: str, prefix: str) -> list[str]:
        normalized = prefix if prefix.endswith("/") or prefix == "" else f"{prefix}/"
        entries = self._list_all_entries(bucket=bucket, prefix=normalized)
        paths: list[str] = []
        for entry in entries:
            name = entry["name"]
            if entry.get("id") is None:
                # Dossier virtuel : on descend d'un niveau (même logique que `shutil.rmtree` côté
                # `LocalDiskStorage` — une purge doit être récursive, quelle que soit la
                # profondeur réellement utilisée par les appelants actuels).
                paths.extend(
                    self._collect_object_paths_recursive(
                        bucket=bucket, prefix=f"{normalized}{name}"
                    )
                )
            else:
                paths.append(f"{normalized}{name}")
        return paths

    def delete_prefix(self, *, bucket: str, prefix: str) -> int:
        paths = self._collect_object_paths_recursive(bucket=bucket, prefix=prefix)
        deleted = 0
        for start in range(0, len(paths), _DELETE_BATCH_SIZE):
            batch = paths[start : start + _DELETE_BATCH_SIZE]
            response = self._client.request(
                "DELETE", f"/object/{bucket}", json={"prefixes": batch}
            )
            if response.status_code >= 400:
                raise SupabaseStorageError(
                    f"Échec de la suppression sous {bucket}/{prefix} (HTTP "
                    f"{response.status_code}) : {response.text}"
                )
            deleted += len(response.json())
        return deleted
