"""Fabrique du backend de stockage photos — point de bascule unique (brief J2, arbitrage
« stockage local simulé, Supabase Storage au déploiement »).

Le choix se fait par configuration, jamais par une variable d'environnement dédiée du type
`STORAGE_BACKEND` : c'est la **présence** de `SUPABASE_URL`/`SUPABASE_SERVICE_KEY`
(`Settings.supabase_storage_configured`) qui décide. Ainsi un clone du dépôt sans le moindre
compte Supabase reste sur le disque local par construction, sans variable supplémentaire à poser
ni à oublier — règle du projet, jamais de développement local dégradé par un tiers absent.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.core.config import Settings, get_settings
from app.services.storage.base import PhotoStorage
from app.services.storage.local import LocalDiskStorage
from app.services.storage.supabase import SupabaseStorage

# `app/services/storage/service.py` -> `app/services/storage` -> `app/services` -> `app` -> backend/
BACKEND_DIR = Path(__file__).resolve().parents[3]


def _resolve_storage_root(settings: Settings) -> Path:
    configured = Path(settings.local_storage_dir)
    return configured if configured.is_absolute() else BACKEND_DIR / configured


@lru_cache
def get_storage_backend() -> PhotoStorage:
    """`SupabaseStorage` si `SUPABASE_URL` et `SUPABASE_SERVICE_KEY` sont toutes deux renseignées
    (déploiement), `LocalDiskStorage` sinon (développement local, CI, tests — aucune clé requise).
    Basculer vers un futur troisième backend : implémenter `PhotoStorage` et l'ajouter ici, c'est
    le seul endroit du code qui change (décision « stockage local simulé »)."""
    settings = get_settings()
    if settings.supabase_storage_configured:
        assert settings.supabase_url is not None  # narrows for mypy, garanti par la propriété
        assert settings.supabase_service_key is not None
        return SupabaseStorage(
            base_url=settings.supabase_url, service_key=settings.supabase_service_key
        )
    return LocalDiskStorage(_resolve_storage_root(settings))
