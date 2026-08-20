"""Implémentation disque local de `PhotoStorage` — brief J2, arbitrage « stockage local simulé
pour l'instant ». Basculer vers Supabase Storage au déploiement : écrire une nouvelle classe
`PhotoStorage` (ex. `supabase.py`) et la brancher dans `service.py` — aucun appelant ailleurs
dans l'application ne connaît un chemin disque, ce module est le seul à en manipuler.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from app.services.storage.base import PhotoStorage


class LocalDiskStorage(PhotoStorage):
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _safe_path(self, *, bucket: str, key: str) -> Path:
        """Résout `bucket/key` sous la racine de stockage, en refusant toute tentative de
        traversée de répertoire — `key` transite par l'URL sur la route de lecture
        (`GET /photos/file/{bucket}/{key}`), donc potentiellement manipulable côté client."""
        candidate = (self._root / bucket.strip("/") / key.strip("/")).resolve()
        if candidate != self._root and self._root not in candidate.parents:
            raise ValueError("Chemin de stockage invalide (hors du répertoire racine).")
        return candidate

    def save(self, *, bucket: str, key: str, content: bytes) -> None:
        path = self._safe_path(bucket=bucket, key=key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def load(self, *, bucket: str, key: str) -> bytes:
        path = self._safe_path(bucket=bucket, key=key)
        if not path.is_file():
            raise FileNotFoundError(f"Fichier introuvable : {bucket}/{key}")
        return path.read_bytes()

    def exists(self, *, bucket: str, key: str) -> bool:
        return self._safe_path(bucket=bucket, key=key).is_file()

    def read_url(self, *, bucket: str, key: str) -> str:
        return f"/api/v1/photos/file/{bucket}/{key}"

    def delete_prefix(self, *, bucket: str, prefix: str) -> int:
        target = self._safe_path(bucket=bucket, key=prefix)
        if not target.exists():
            return 0
        count = sum(1 for p in target.rglob("*") if p.is_file())
        shutil.rmtree(target, ignore_errors=True)
        return count
