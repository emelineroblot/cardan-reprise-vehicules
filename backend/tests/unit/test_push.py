"""Web push — arbitrage « notifications en base, push optionnel » : absence de clés VAPID =
`is_push_enabled() is False`, jamais une exception (brief J2). `pywebpush` est un extra de
packaging (`pyproject.toml`, revue orchestrateur) importé paresseusement dans `send_web_push` —
couvert ici sur les deux chemins : extra installé (import réel, appel simulé) et extra absent
(`ImportError` avalée, jamais propagée).

Ces tests couvrent la fonction unitaire (`send_web_push` renvoie un `PushOutcome`, jamais une
exception). La distinction transitoire/définitif vue **depuis l'appelant** (désactivation ou non
de l'abonnement, non-ralentissement de la transition) est couverte à l'échelle de l'endpoint réel
dans `tests/integration/test_push_dispatch.py` — c'est là qu'un circuit breaker cassé se verrait,
pas ici (revue J2)."""

from __future__ import annotations

import sys

import pytest

from app.core.config import Settings
from app.services.push import PUSH_TIMEOUT_SECONDS, PushTarget, is_push_enabled, send_web_push

_ENABLED = {"vapid_public_key": "pub", "vapid_private_key": "priv"}


def _settings(**overrides) -> Settings:
    base = {"jwt_secret": "x" * 32, "cron_secret": "y" * 32}
    base.update(overrides)
    return Settings(**base)


def test_push_disabled_without_any_vapid_key() -> None:
    assert is_push_enabled(_settings()) is False


def test_push_disabled_with_only_public_key() -> None:
    assert is_push_enabled(_settings(vapid_public_key="pub")) is False


def test_push_enabled_with_both_keys() -> None:
    assert is_push_enabled(_settings(vapid_public_key="pub", vapid_private_key="priv")) is True


def test_send_web_push_is_a_noop_when_disabled(monkeypatch) -> None:
    """Ne doit jamais lever, même si `pywebpush` n'était pas installé — le chemin nominal
    (notification en base) ne dépend jamais du push. Considéré transitoire (pas définitif) :
    l'appelant ne doit désactiver aucun abonnement sur cette seule base."""
    from app.services import push

    monkeypatch.setattr(push, "get_settings", lambda: _settings())
    result = send_web_push(
        PushTarget(endpoint="https://push.example/x", p256dh="k", auth="a"),
        title="t",
        body="b",
        data=None,
    )
    assert result == "failed_transient"


def test_send_web_push_enabled_calls_pywebpush_with_expected_arguments(monkeypatch) -> None:
    """Chemin activé : l'extra `webpush` est installé (cas de ce venv de dev/CI) — l'import
    différé se résout réellement, `pywebpush.webpush()` simulé pour ne jamais toucher le réseau."""
    pywebpush = pytest.importorskip("pywebpush")
    from app.services import push

    monkeypatch.setattr(push, "get_settings", lambda: _settings(**_ENABLED))

    calls = []

    def _fake_webpush(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(pywebpush, "webpush", _fake_webpush)

    result = send_web_push(
        PushTarget(endpoint="https://push.example/x", p256dh="k", auth="a"),
        title="Nouvelle mission",
        body="Véhicule VH-2026-000001",
        data={"vehicle_id": "abc"},
    )

    assert result == "sent"
    assert len(calls) == 1
    call = calls[0]
    assert call["subscription_info"]["endpoint"] == "https://push.example/x"
    assert call["subscription_info"]["keys"] == {"p256dh": "k", "auth": "a"}
    assert call["vapid_private_key"] == "priv"
    assert call["vapid_claims"] == {"sub": "mailto:demo@cardan.local"}
    assert "Nouvelle mission" in call["data"]
    # Revue J2 § 🔴 n°7 : un délai maximal court doit être imposé à l'appel réseau.
    assert call["timeout"] == PUSH_TIMEOUT_SECONDS


def test_send_web_push_enabled_but_package_missing_degrades_gracefully(monkeypatch) -> None:
    """Chemin activé (VAPID configurée) mais extra `webpush` absent — cas d'un déploiement qui
    a configuré VAPID sans avoir régénéré `requirements.txt --extra webpush` : ne doit jamais
    lever, seulement logguer et renvoyer un échec transitoire (le parcours nominal reste intact,
    et l'abonnement de l'utilisateur n'est pas désactivé pour un problème de déploiement)."""
    from app.services import push

    monkeypatch.setattr(push, "get_settings", lambda: _settings(**_ENABLED))
    # Force `from pywebpush import ...` à lever `ImportError`, sans exiger que le paquet soit
    # réellement désinstallé du venv de test (technique standard : `None` dans `sys.modules`
    # fait échouer l'import pour ce nom).
    monkeypatch.setitem(sys.modules, "pywebpush", None)

    result = send_web_push(
        PushTarget(endpoint="https://push.example/x", p256dh="k", auth="a"),
        title="t",
        body="b",
        data=None,
    )
    assert result == "failed_transient"


def test_send_web_push_gone_response_is_a_permanent_failure(monkeypatch) -> None:
    """410/404 du service de push = abonnement réellement mort (revue J2 § 🔴 n°7) : seul cas où
    `send_web_push` doit signaler un échec définitif à l'appelant."""
    pywebpush = pytest.importorskip("pywebpush")
    from app.services import push

    monkeypatch.setattr(push, "get_settings", lambda: _settings(**_ENABLED))

    class _FakeResponse:
        status_code = 410
        reason = "Gone"
        text = "expired"

    def _fake_webpush(**kwargs):
        raise pywebpush.WebPushException("Push failed: 410 Gone", response=_FakeResponse())

    monkeypatch.setattr(pywebpush, "webpush", _fake_webpush)

    result = send_web_push(
        PushTarget(endpoint="https://push.example/x", p256dh="k", auth="a"),
        title="t",
        body="b",
        data=None,
    )
    assert result == "failed_permanent"


def test_send_web_push_server_error_response_is_a_transient_failure(monkeypatch) -> None:
    """Une 5xx passagère du service de push n'est pas un abonnement mort — ne doit jamais être
    traitée comme le 404/410 (revue J2 § 🔴 n°7)."""
    pywebpush = pytest.importorskip("pywebpush")
    from app.services import push

    monkeypatch.setattr(push, "get_settings", lambda: _settings(**_ENABLED))

    class _FakeResponse:
        status_code = 503
        reason = "Service Unavailable"
        text = "try again later"

    def _fake_webpush(**kwargs):
        raise pywebpush.WebPushException(
            "Push failed: 503 Service Unavailable", response=_FakeResponse()
        )

    monkeypatch.setattr(pywebpush, "webpush", _fake_webpush)

    result = send_web_push(
        PushTarget(endpoint="https://push.example/x", p256dh="k", auth="a"),
        title="t",
        body="b",
        data=None,
    )
    assert result == "failed_transient"


def test_send_web_push_network_timeout_is_a_transient_failure(monkeypatch) -> None:
    """Un timeout réseau (non enveloppé par `WebPushException`, cf. `pywebpush.webpush`) doit
    rester transitoire — c'est précisément le cas visé par le délai maximal imposé."""
    pywebpush = pytest.importorskip("pywebpush")
    from app.services import push

    monkeypatch.setattr(push, "get_settings", lambda: _settings(**_ENABLED))

    def _timeout_webpush(**kwargs):
        raise TimeoutError("simulated network timeout")

    monkeypatch.setattr(pywebpush, "webpush", _timeout_webpush)

    result = send_web_push(
        PushTarget(endpoint="https://push.example/x", p256dh="k", auth="a"),
        title="t",
        body="b",
        data=None,
    )
    assert result == "failed_transient"
