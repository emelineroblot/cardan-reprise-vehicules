"""`POST /analytics/refresh`, `GET /analytics/status` — plan.md § 6 vague 4."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.analytics.runner import latest_refresh_status, refresh
from app.api.deps import require_roles
from app.db.session import get_db
from app.models.user import AppUser

router = APIRouter()


@router.post("/refresh")
def refresh_analytics(
    user: AppUser = Depends(require_roles("administrateur")),
) -> dict:
    """Câblé sur le bouton « Actualiser les indicateurs » du dashboard (plan.md § 3.7-5)."""
    results = refresh()
    return {"results": results}


@router.get("/status")
def analytics_status(
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_roles("administrateur")),
) -> dict:
    return {"marts": latest_refresh_status(db)}
