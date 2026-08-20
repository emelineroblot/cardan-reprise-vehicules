"""`GET|POST /admin/demo-reset` — plan.md § 4 décision D et § 3.8-7.

Authentification par `Authorization: Bearer $CRON_SECRET`, comparée en **temps constant**
(`hmac.compare_digest`). Vercel pose cet en-tête automatiquement sur les cron jobs — **et
invoque les cron jobs par une requête GET sur le `path` déclaré**, jamais POST (revue § 🟠 « le
cron nocturne ne se déclenchera probablement jamais »). Exposé sur les deux verbes : c'est le
`CRON_SECRET` qui protège l'endpoint, pas le verbe HTTP ; `POST` reste documenté pour un
déclenchement manuel explicite (ex. `python -m app.cli demo-reset` appelle la fonction
directement, mais un opérateur pourrait aussi vouloir `curl -X POST` en test).
"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Header

from app.core.config import get_settings
from app.core.errors import ApiError
from app.seed.reset import run_demo_reset

router = APIRouter()


def _run_authenticated_reset(authorization: str | None) -> dict:
    settings = get_settings()

    expected = f"Bearer {settings.cron_secret}".encode()
    provided = (authorization or "").encode("utf-8", errors="replace")
    # Comparaison en bytes, pas en str : `hmac.compare_digest` lève `TypeError` sur une chaîne
    # non-ASCII (revue § 🟡), ce qui remonterait en 500 au lieu de 401 sur un en-tête malformé.
    if not hmac.compare_digest(provided, expected):
        raise ApiError("unauthenticated", "Authentification cron invalide.")

    try:
        return run_demo_reset()
    except RuntimeError as exc:
        raise ApiError("internal_error", str(exc)) from exc


@router.get("/demo-reset")
def demo_reset_get(authorization: str | None = Header(default=None)) -> dict:
    return _run_authenticated_reset(authorization)


@router.post("/demo-reset")
def demo_reset_post(authorization: str | None = Header(default=None)) -> dict:
    return _run_authenticated_reset(authorization)
