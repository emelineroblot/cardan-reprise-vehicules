"""`/missions/*` — brief J2 : « liste de ses missions, détail » pour le chauffeur.

Les transitions elles-mêmes (prise de rendez-vous incluse) restent `POST
/vehicles/{id}/transitions` (plan.md § 5.3, « un seul point d'entrée ») : aucun endpoint ici ne
modifie l'état d'une mission, il ne fait que la lire, dérivée de l'automate véhicule
(`app/services/missions.py`).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.sql import Select

from app.api.deps import require_roles
from app.core.errors import ApiError
from app.core.pagination import Page, PageParams, page_params, paginate
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.mission import Mission
from app.models.user import AppUser
from app.schemas.mission import MissionRead

router = APIRouter()

_ALLOWED_ROLES = ("chauffeur", "administrateur")


def _scoped_missions_stmt(user: AppUser) -> Select:
    stmt = select(Mission).options(joinedload(Mission.vehicle))
    if user.role == UserRole.CHAUFFEUR.value:
        stmt = stmt.where(Mission.driver_id == user.id)
    return stmt


@router.get("", response_model=Page[MissionRead])
def list_missions(
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_roles(*_ALLOWED_ROLES)),
    params: PageParams = Depends(page_params),
    state: str | None = None,
    driver_id: UUID | None = None,
) -> Page[MissionRead]:
    stmt = _scoped_missions_stmt(user)
    if state:
        stmt = stmt.where(Mission.state == state)
    if driver_id is not None and user.role == UserRole.ADMINISTRATEUR.value:
        stmt = stmt.where(Mission.driver_id == driver_id)
    stmt = stmt.order_by(Mission.assigned_at.desc())

    items, total = paginate(db, stmt, params)
    return Page[MissionRead](
        items=[MissionRead.model_validate(i) for i in items],
        total=total,
        limit=params.limit,
        offset=params.offset,
    )


@router.get("/{mission_id}", response_model=MissionRead)
def get_mission(
    mission_id: UUID,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_roles(*_ALLOWED_ROLES)),
) -> Mission:
    stmt = _scoped_missions_stmt(user).where(Mission.id == mission_id)
    mission = db.scalar(stmt)
    if mission is None:
        raise ApiError("not_found", "Mission introuvable.")
    return mission
