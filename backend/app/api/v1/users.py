"""`GET /users` — dette J1 : sans lister les comptes `chauffeur`, le bouton « Affectation d'un
chauffeur » de l'écran admin (`ActionsTransition.tsx`) reste désactivé faute d'un `<Select>`
alimentable (voir `implementation.md`, revue § 🟠 dev-frontend). Réservé à l'administrateur :
c'est le seul rôle habilité à affecter un chauffeur (`A_PLANIFIER → AFFECTE`, plan.md § 5.3).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.errors import ApiError
from app.core.pagination import Page, PageParams, page_params, paginate
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.user import AppUser
from app.schemas.user import UserBrief

router = APIRouter()


@router.get("", response_model=Page[UserBrief])
def list_users(
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_roles("administrateur")),
    params: PageParams = Depends(page_params),
    role: str | None = None,
    is_active: bool | None = None,
    q: str | None = None,
) -> Page[UserBrief]:
    stmt = select(AppUser)
    if role is not None:
        if role not in {r.value for r in UserRole}:
            raise ApiError("validation_error", "Rôle inconnu.")
        stmt = stmt.where(AppUser.role == role)
    if is_active is not None:
        stmt = stmt.where(AppUser.is_active == is_active)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(AppUser.full_name.ilike(like) | AppUser.email.ilike(like))
    stmt = stmt.order_by(AppUser.full_name)

    items, total = paginate(db, stmt, params)
    return Page[UserBrief](
        items=[UserBrief.model_validate(i) for i in items],
        total=total,
        limit=params.limit,
        offset=params.offset,
    )
