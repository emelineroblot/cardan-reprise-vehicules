"""`Settings` — fail-fast sur les secrets, `is_remote` (plan.md § 3.4, revue § 🔴/🟡).

Instancie `Settings` directement (`_env_file=None`) pour ignorer le `.env` local et isoler
chaque scénario par ses seules variables d'environnement.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings


def _settings(**overrides: str | bool) -> Settings:
    base: dict[str, str | bool] = {"database_url": "postgresql+psycopg://x:x@localhost/x"}
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[call-arg,arg-type]


def test_local_environment_accepts_missing_secrets() -> None:
    settings = _settings(environment="local")
    assert settings.jwt_secret
    assert settings.cron_secret


def test_local_environment_accepts_explicit_secrets() -> None:
    settings = _settings(environment="local", jwt_secret="x" * 32, cron_secret="y" * 32)
    assert settings.jwt_secret == "x" * 32


@pytest.mark.parametrize("environment", ["test", "preview", "production"])
def test_non_local_environment_rejects_missing_secrets(environment: str) -> None:
    with pytest.raises(ValueError, match="JWT_SECRET"):
        _settings(environment=environment, jwt_secret="", cron_secret="")


@pytest.mark.parametrize("environment", ["test", "preview", "production"])
def test_non_local_environment_rejects_placeholder_secret(environment: str) -> None:
    with pytest.raises(ValueError):
        _settings(
            environment=environment,
            jwt_secret="local-dev-only-insecure-jwt-secret-never-use-outside-local",
            cron_secret="a-real-secret-value-32-bytes-min-xxxxx",
        )


@pytest.mark.parametrize("environment", ["test", "preview", "production"])
def test_non_local_environment_accepts_real_secrets(environment: str) -> None:
    settings = _settings(
        environment=environment,
        jwt_secret="a-real-secret-value-32-bytes-min-xxxxx",
        cron_secret="another-real-secret-value-xxxxxxxxxxxx",
    )
    assert settings.environment == environment


@pytest.mark.parametrize(
    "environment,expected",
    [("local", False), ("test", True), ("preview", True), ("production", True)],
)
def test_is_remote(environment: str, expected: bool) -> None:
    kwargs: dict[str, str] = {"environment": environment}
    if environment != "local":
        kwargs["jwt_secret"] = "a-real-secret-value-32-bytes-min-xxxxx"
        kwargs["cron_secret"] = "another-real-secret-value-xxxxxxxxxxxx"
    assert _settings(**kwargs).is_remote is expected


def test_vercel_detected_forces_is_remote_even_with_default_environment() -> None:
    """Régression revue finale § 🔴 : `ENVIRONMENT` oubliée sur Vercel garde sa valeur par défaut
    `local`, mais `VERCEL=1` (injecté automatiquement par la plateforme, jamais déclaré à la
    main) doit à lui seul faire basculer `is_remote` à `True` — le garde-fou ne doit jamais
    dépendre d'une seule variable déclarative oubliable."""
    # `environment="local"` explicite ci-dessous : reproduit l'oubli de la variable sur la
    # plateforme (la valeur par défaut du champ, sans ce kwarg, serait de toute façon "local").
    settings = _settings(
        environment="local",
        vercel=True,
        jwt_secret="a-real-secret-value-32-bytes-min-xxxxx",
        cron_secret="another-real-secret-value-xxxxxxxxxxxx",
    )
    assert settings.environment == "local"
    assert settings.is_remote is True


def test_vercel_detected_with_default_environment_rejects_missing_secrets() -> None:
    """Le scénario exact du bloquant : `ENVIRONMENT` oubliée sur Vercel, secrets absents — doit
    échouer au démarrage au lieu de servir silencieusement les valeurs de secours locales."""
    with pytest.raises(ValueError, match="JWT_SECRET"):
        _settings(environment="local", vercel=True, jwt_secret="", cron_secret="")


def test_vercel_detected_with_default_environment_rejects_placeholder_secret() -> None:
    with pytest.raises(ValueError):
        _settings(
            environment="local",
            vercel=True,
            jwt_secret="local-dev-only-insecure-jwt-secret-never-use-outside-local",
            cron_secret="a-real-secret-value-32-bytes-min-xxxxx",
        )


def test_vercel_absent_with_default_environment_keeps_local_behaviour() -> None:
    """Sans `VERCEL` (`vercel=False` explicite, cf. `ENVIRONMENT=test` posé par `conftest.py`
    pour toute la session de test), le fail-fast ne doit pas se déclencher tant que
    `environment="local"` — non-régression du comportement local nominal."""
    settings = _settings(environment="local", vercel=False)
    assert settings.vercel is False
    assert settings.is_remote is False
    assert settings.jwt_secret


def test_supabase_storage_configured_false_without_any_value() -> None:
    settings = _settings()
    assert settings.supabase_storage_configured is False


@pytest.mark.parametrize(
    "supabase_url,supabase_service_key",
    [("https://x.supabase.co", None), (None, "service-role-key")],
)
def test_supabase_storage_configured_false_with_only_one_value(
    supabase_url: str | None, supabase_service_key: str | None
) -> None:
    """Les deux valeurs sont requises — jamais un backend Supabase à moitié configuré (une clé
    seule ne suffit pas à construire une URL de stockage valide, et réciproquement)."""
    kwargs: dict[str, str] = {}
    if supabase_url is not None:
        kwargs["supabase_url"] = supabase_url
    if supabase_service_key is not None:
        kwargs["supabase_service_key"] = supabase_service_key
    settings = _settings(**kwargs)
    assert settings.supabase_storage_configured is False


def test_supabase_storage_configured_true_with_both_values() -> None:
    settings = _settings(
        supabase_url="https://x.supabase.co", supabase_service_key="service-role-key"
    )
    assert settings.supabase_storage_configured is True
