"""Envoi Web Push — brief J2, arbitrage « notifications en base, web push optionnel ».

Le chemin nominal est la notification persistée en base (`app/services/notifications.py`),
toujours actif, sans aucune clé. L'envoi Web Push réel ne s'active que si `VAPID_PUBLIC_KEY` et
`VAPID_PRIVATE_KEY` sont toutes deux configurées (`is_push_enabled`) ; son absence — ou tout
échec réseau — ne doit **jamais** dégrader le parcours nominal : une démo devant un prospect ne
peut pas dépendre d'une autorisation navigateur. Aucune fonction de ce module ne lève.

`send_web_push` distingue deux familles d'échec (revue J2, § 🔴 n°7) :
- **transitoire** (`"failed_transient"`) : timeout, panne réseau, 5xx du service de push, extra
  `pywebpush` non installé, VAPID désactivée — rien de tout cela ne signifie que l'abonnement est
  mort, l'appelant ne doit donc jamais le désactiver sur cette base ;
- **définitif** (`"failed_permanent"`) : le service de push a répondu `404`/`410` (« Gone »),
  seul cas où l'abonnement peut être considéré comme mort côté navigateur.

`timeout` borne chaque appel réseau à une durée courte : `webpush()` est invoqué de façon
synchrone dans la requête HTTP de transition (`app/services/vehicles.py::transition_vehicle`),
après le commit métier. Une tâche de fond (ex. `BackgroundTasks` de FastAPI) n'offrirait ici
aucune garantie d'exécution sur une fonction serverless Vercel — le runtime peut geler le
processus dès la réponse HTTP envoyée — c'est pourquoi ce module reste volontairement synchrone
et se contente de borner le pire cas plutôt que de s'appuyer sur un mécanisme non fiable.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Literal

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Délai maximal imposé à chaque appel réseau vers le service de push (revue J2, § 🔴 n°7) : assez
# court pour ne jamais faire traîner sensiblement la transition qui le déclenche, assez long pour
# ne pas transformer une réponse simplement lente en faux échec transitoire.
PUSH_TIMEOUT_SECONDS = 3.0

_GONE_STATUS_CODES = frozenset({404, 410})

PushOutcome = Literal["sent", "failed_transient", "failed_permanent"]


def is_push_enabled(settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    return bool(s.vapid_public_key and s.vapid_private_key)


@dataclass(frozen=True)
class PushTarget:
    endpoint: str
    p256dh: str
    auth: str


def send_web_push(
    target: PushTarget,
    *,
    title: str,
    body: str,
    data: dict[str, Any] | None,
    timeout: float = PUSH_TIMEOUT_SECONDS,
) -> PushOutcome:
    """Best-effort : ne lève jamais. Renvoie `"sent"`, `"failed_transient"` ou
    `"failed_permanent"` — voir docstring de module pour la distinction.

    `pywebpush` est un **extra de packaging** (`pyproject.toml`, `[project.optional-dependencies]
    webpush`), pas une dépendance de base : sur une fonction serverless, payer son poids
    (`cryptography`, `aiohttp`) au cold start pour une fonctionnalité désactivée par défaut est
    un mauvais compromis (plan.md § 3.8-6 « dépendances légères », § 9 « double démarrage à
    froid »). L'import est donc différé ici, **et seulement atteint quand `is_push_enabled()` est
    vrai** — un déploiement qui n'installe pas l'extra `webpush` (cas nominal : VAPID absent)
    n'importe jamais ce module lourd. S'il est vrai mais que l'extra n'a pas été installé (VAPID
    configurée sans avoir régénéré `requirements.txt` avec `--extra webpush`), l'échec reste
    silencieux côté utilisateur — et **transitoire** : ce n'est pas l'abonnement qui est en
    cause, mais le déploiement.
    """
    settings = get_settings()
    if not is_push_enabled(settings):
        return "failed_transient"

    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        logger.warning(
            "VAPID configurée mais pywebpush n'est pas installé (extra `webpush` manquant) : "
            "notification push ignorée."
        )
        return "failed_transient"

    try:
        webpush(
            subscription_info={
                "endpoint": target.endpoint,
                "keys": {"p256dh": target.p256dh, "auth": target.auth},
            },
            data=json.dumps({"title": title, "body": body, "data": data or {}}),
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={"sub": settings.vapid_subject},
            timeout=timeout,
        )
        return "sent"
    except WebPushException as exc:
        status_code = getattr(exc.response, "status_code", None)
        if status_code in _GONE_STATUS_CODES:
            logger.info("Abonnement expiré/révoqué (%s), désactivation : %s", status_code, exc)
            return "failed_permanent"
        logger.info("Envoi push échoué de façon transitoire (%s) : %s", status_code, exc)
        return "failed_transient"
    except Exception:  # noqa: BLE001 — best-effort, ne doit jamais interrompre le parcours nominal
        # Regroupe timeouts et pannes réseau (`requests.exceptions.*`, non enveloppées par
        # `WebPushException`, cf. `pywebpush.webpush`) : toujours transitoire par construction,
        # jamais un signal que l'abonnement est mort.
        logger.exception("Erreur inattendue (transitoire) lors de l'envoi push.")
        return "failed_transient"
