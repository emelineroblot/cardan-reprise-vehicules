"""Configuration applicative — lue depuis l'environnement (.env en local)."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Valeurs de secours **explicitement locales** — jamais utilisées comme secret réel. Distinctes
# de la documentation de `.env.example` (qui, elle, ne contient aucune valeur) pour qu'un secret
# oublié sur Vercel ne puisse jamais être confondu avec un JWT signable/un cron déclenchable
# depuis le dépôt public (revue § 🔴 « secrets par défaut publics et exploitables »).
_LOCAL_DEV_JWT_SECRET = "local-dev-only-insecure-jwt-secret-never-use-outside-local"
_LOCAL_DEV_CRON_SECRET = "local-dev-only-insecure-cron-secret-never-use-outside-local"


class Settings(BaseSettings):
    """Paramètres applicatifs, jamais de valeur par défaut sensible hors `environment=local`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["local", "test", "preview", "production"] = "local"

    # Vercel injecte automatiquement `VERCEL=1` sur toute exécution de la plateforme (build,
    # preview, production) — contrairement à `ENVIRONMENT`, cette variable ne peut pas être
    # oubliée par une déployeuse : elle n'est jamais déclarée à la main (revue § 🔴 « le fail-fast
    # est contournable en oubliant ENVIRONMENT »). Sert uniquement à durcir `is_remote` : la
    # détection prime sur la déclaration, jamais l'inverse.
    vercel: bool = False

    # Base de données — voir plan.md § 3.8. En local via docker-compose (port 5433).
    # En prod : chaîne "pooled" (PgBouncer) pour l'API, chaîne directe pour migrations/REFRESH.
    database_url: str = "postgresql+psycopg://cardan:cardan@localhost:5433/cardan"
    database_url_direct: str | None = None

    # Auth
    jwt_secret: str = _LOCAL_DEV_JWT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 12 * 60
    session_cookie_name: str = "cardan_session"

    # Cron nocturne (Vercel envoie Authorization: Bearer $CRON_SECRET)
    cron_secret: str = _LOCAL_DEV_CRON_SECRET

    # Stockage photos — colonnes posées en J1 (décision C), backend réel branché en J2.
    # Arbitrage J2 : stockage **disque local simulé** pour l'instant (aucun compte tiers, aucune
    # clé à manipuler) — voir `app/services/storage/`. `supabase_bucket` reste le nom de bucket
    # logique utilisé dès maintenant (colonne `photo.storage_bucket`) : au déploiement, seule
    # l'implémentation `PhotoStorage` change (`local.py` → un futur `supabase.py`), jamais son nom.
    supabase_url: str | None = None
    supabase_service_key: str | None = None
    supabase_bucket: str = "cardan-photos"
    # Racine du stockage local (relative à `backend/` si non absolue) — jamais commitée
    # (`backend/var/` est gitignoré).
    local_storage_dir: str = "var/storage"

    # Notifications web push (brief J2, arbitrage « notifications en base, push optionnel ») —
    # la notification persistée en base est le chemin nominal et fonctionne sans aucune clé
    # (voir `app/api/v1/notifications.py`). Le push réel ne s'active que si les deux clés VAPID
    # sont présentes (`app/services/push.py::is_push_enabled`) ; son absence ne dégrade jamais
    # le parcours — une démo devant un prospect ne doit jamais dépendre d'une autorisation
    # navigateur.
    vapid_public_key: str | None = None
    vapid_private_key: str | None = None
    vapid_subject: str = "mailto:demo@cardan.local"

    # Enrichissement société par SIRET (décision B)
    company_lookup_provider: Literal["recherche_entreprises", "insee", "disabled"] = (
        "recherche_entreprises"
    )
    insee_api_key: str | None = None

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def supabase_storage_configured(self) -> bool:
        """`True` seulement si les deux valeurs Supabase Storage sont posées — c'est ce que lit
        `app/services/storage/service.py::get_storage_backend` pour choisir le backend. Centralisé
        ici (plutôt que répété au point d'appel) pour qu'un seul endroit décide de la règle « sans
        clés, le disque local reste actif » (`docs/wiki/architecture.md` § Stockage des photos) —
        aucun développement local ne doit jamais dépendre d'un compte Supabase existant."""
        return bool(self.supabase_url and self.supabase_service_key)

    @property
    def is_remote(self) -> bool:
        """`True` pour test/preview/production — tout ce qui n'est pas `local` (revue § 🟡) :
        un déploiement Vercel *preview* posait le cookie de session sans `Secure` et gardait
        les instructions préparées actives derrière PgBouncer, faute d'être `production`.

        `self.vercel` (déduit de `VERCEL=1`, injecté par la plateforme) force également `True`,
        même si `ENVIRONMENT` a été oubliée et vaut donc sa valeur par défaut `local` (revue
        § 🔴). Le défaut le plus strict doit gagner : c'est la présence détectée d'un
        environnement distant qui décide, jamais l'absence d'une variable déclarative."""
        return self.environment != "local" or self.vercel

    @model_validator(mode="after")
    def _fail_fast_on_unsafe_secrets_outside_local(self) -> Settings:
        """Refuse de démarrer en environnement distant (`is_remote`) si `JWT_SECRET`/
        `CRON_SECRET` sont absents ou valent leur valeur de secours locale (revue § 🔴).

        Un secret oublié sur Vercel serait sinon lisible dans ce fichier, dans un dépôt public :
        JWT admin forgeable et `demo-reset` déclenchable (TRUNCATE des tables opérationnelles)
        par quiconque. En local, la valeur de secours reste acceptable mais est signalée pour ne
        jamais être prise pour un oubli silencieux.

        Le garde s'appuie sur `is_remote`, pas sur `environment == "local"` directement : `VERCEL`
        (détecté, pas déclaré) force `is_remote` même si `ENVIRONMENT` a été oubliée sur la
        plateforme — sinon l'oubli d'une seule variable déclarative désactivait tout le
        fail-fast (revue § 🔴 « le point de défaillance s'est juste déplacé »).
        """
        unsafe = {
            "JWT_SECRET": (self.jwt_secret, _LOCAL_DEV_JWT_SECRET),
            "CRON_SECRET": (self.cron_secret, _LOCAL_DEV_CRON_SECRET),
        }
        if not self.is_remote:
            for name, (value, placeholder) in unsafe.items():
                if not value or value == placeholder:
                    logger.warning(
                        "%s utilise la valeur de secours locale (insécurisée, jamais valide "
                        "en environnement distant). Poser une vraie valeur dans .env si besoin.",
                        name,
                    )
            return self

        missing_or_default = [
            name
            for name, (value, placeholder) in unsafe.items()
            if not value or value == placeholder
        ]
        if missing_or_default:
            raise ValueError(
                "Configuration invalide : "
                + ", ".join(missing_or_default)
                + " doi(ven)t être défini(s) explicitement en environnement distant "
                f"(environment={self.environment!r}, VERCEL détecté={self.vercel!r}). Valeur "
                "absente ou de secours détectée — l'application refuse de démarrer "
                "(revue § 🔴 secrets par défaut)."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
