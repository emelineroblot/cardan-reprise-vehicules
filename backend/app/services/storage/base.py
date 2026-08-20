"""Interface de stockage des photos — brief J2, arbitrage « stockage local simulé pour
l'instant, bascule Supabase Storage triviale au déploiement ».

Le reste de l'application (`app/services/photos.py`, `app/api/v1/photos.py`) ne connaît que
`bucket`/`key` (déjà les colonnes `photo.storage_bucket`/`storage_key`, plan.md § 5.1 décision C)
et des octets : **aucun détail de système de fichiers ne doit fuiter au-delà de ce module et de
son implémentation active** (`local.py`, puis un futur `supabase.py`). Basculer de backend =
écrire une nouvelle classe `PhotoStorage` et la brancher dans `service.py`, sans toucher au
reste du code (aucun appelant n'a besoin de changer).
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class PhotoStorage(ABC):
    @abstractmethod
    def save(self, *, bucket: str, key: str, content: bytes) -> None:
        """Écrit `content` sous `bucket/key`. Les clés sont générées côté serveur avec un UUID
        (`app/services/photos.py`) : une collision n'arrive jamais en usage normal."""

    @abstractmethod
    def load(self, *, bucket: str, key: str) -> bytes:
        """Lit le contenu de `bucket/key`. Lève `FileNotFoundError` si absent."""

    @abstractmethod
    def exists(self, *, bucket: str, key: str) -> bool: ...

    @abstractmethod
    def read_url(self, *, bucket: str, key: str) -> str:
        """URL de lecture pour le front. En local : une route backend authentifiée par cookie
        (`GET /api/v1/photos/file/{bucket}/{key}`) — pas une URL signée à proprement parler,
        mais le contrat exposé au front (un champ `url` sur `PhotoRead`) reste identique une
        fois Supabase branché (plan.md § 3.6 : URL signée à 1 h). Seule la fabrication de
        l'URL change."""

    @abstractmethod
    def delete_prefix(self, *, bucket: str, prefix: str) -> int:
        """Supprime toute clé commençant par `prefix` dans `bucket` — purge nocturne du
        préfixe `runtime/` (plan.md § 4 décision D, étape 3 ; § 3.6). Renvoie le nombre de
        clés supprimées."""
