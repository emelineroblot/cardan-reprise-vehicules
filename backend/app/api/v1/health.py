"""`GET /api/v1/health` — préchauffage (plan.md § 3.8-5).

Appelé par la page d'accueil publique dès son chargement pour réveiller la fonction Vercel et
la base Supabase (Postgres managé, offre gratuite avec mise en veille par inactivité) avant même
que le prospect ait cliqué sur « Se connecter ».
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter()


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ok", "time": datetime.now(UTC).isoformat()}
