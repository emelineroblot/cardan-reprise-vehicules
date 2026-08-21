"""Implémentation disque local de `PhotoStorage` — brief J2, arbitrage « stockage local simulé
pour l'instant ». Basculer vers Supabase Storage au déploiement : écrire une nouvelle classe
`PhotoStorage` (ex. `supabase.py`) et la brancher dans `service.py` — aucun appelant ailleurs
dans l'application ne connaît un chemin disque, ce module est le seul à en manipuler.

Piège corrigé avant J3 (docs/wiki/pieges-projet.md § « Module terrain / PWA (J2) », 🔴 en tête
de section) : `read_url` doit renvoyer une URL que le **navigateur** peut résoudre telle quelle.
Le navigateur n'appelle jamais le backend en direct — il passe systématiquement par le rewrite
Next `/api/backend/:path*` (architecture.md § Déploiement, `frontend/next.config.ts`), y compris
en dev local (`BACKEND_ORIGIN`). La route backend elle-même reste montée sous `/api/v1/...`
(`app/main.py`) : c'est le champ `PhotoRead.url` qui doit porter le préfixe `/api/backend`, pas
la route. Poser ce préfixe ici, côté backend qui possède le contrat d'URL, plutôt que de le
coder en dur côté front — c'est exactement la parade à ne pas prendre (le front devrait alors
répéter cette règle pour la future implémentation objet, qui renverra une URL signée absolue
n'ayant besoin d'aucun préfixe). Basculer de backend de stockage = changer uniquement la valeur
renvoyée par `read_url`, jamais un appelant.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from app.services.storage.base import PhotoStorage

# Préfixe fixe imposé par le rewrite Next (`/api/backend/:path*` -> backend `/api/:path*`),
# identique en local et en production (plan.md § 3.1, § 3.8) : ce n'est pas une variable
# d'environnement, c'est une convention d'architecture invariante entre les deux couches.
# Le rewrite remplace le segment `/api/backend` par `/api` — il ne faut donc PAS répéter `/api`
# dans le suffixe ci-dessous (piège vécu : `/api/backend/api/v1/...` a d'abord été écrit par
# erreur, détecté par `tests/unit/test_storage_local.py`, jamais par un test d'intégration qui
# passerait par le vrai rewrite Next puisque ce dernier n'existe que côté frontend).
_BROWSER_PREFIX = "/api/backend"


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
        return f"{_BROWSER_PREFIX}/v1/photos/file/{bucket}/{key}"

    def delete_prefix(self, *, bucket: str, prefix: str) -> int:
        target = self._safe_path(bucket=bucket, key=prefix)
        if not target.exists():
            return 0
        count = sum(1 for p in target.rglob("*") if p.is_file())
        shutil.rmtree(target, ignore_errors=True)
        return count
