"""Fabrique du backend de stockage photos — point de bascule unique (brief J2, arbitrage
« stockage local simulé, Supabase Storage au déploiement »).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.core.config import Settings, get_settings
from app.services.storage.base import PhotoStorage
from app.services.storage.local import LocalDiskStorage

# `app/services/storage/service.py` -> `app/services/storage` -> `app/services` -> `app` -> backend/
BACKEND_DIR = Path(__file__).resolve().parents[3]


def _resolve_storage_root(settings: Settings) -> Path:
    configured = Path(settings.local_storage_dir)
    return configured if configured.is_absolute() else BACKEND_DIR / configured


@lru_cache
def get_storage_backend() -> PhotoStorage:
    """Toujours `LocalDiskStorage` aujourd'hui. Basculer vers Supabase Storage au déploiement :
    implémenter `PhotoStorage` et retourner l'instance ici — c'est le seul endroit du code qui
    change (décision « stockage local simulé »)."""
    settings = get_settings()
    return LocalDiskStorage(_resolve_storage_root(settings))
