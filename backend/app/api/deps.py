"""Dépendances FastAPI transverses — authentification et cloisonnement de rôle.

Voir plan.md § 3.4 : cloisonnement à deux étages, non négociable.
- Étage route : `require_roles(...)` sur chaque endpoint → 403 `forbidden_role`.
- Étage ligne : `scope_vehicles` (app/services/vehicle_scope.py, vague 3), appliqué par
  tous les accès en lecture. Le front n'est jamais la barrière.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

import jwt
from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import AppUser

settings = get_settings()


def get_current_user(request: Request, db: Session = Depends(get_db)) -> AppUser:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise ApiError("unauthenticated", "Authentification requise.")

    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError as exc:
        raise ApiError("unauthenticated", "Session invalide ou expirée.") from exc

    try:
        user_id = UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise ApiError("unauthenticated", "Session invalide ou expirée.") from exc

    user = db.scalar(select(AppUser).where(AppUser.id == user_id))
    if user is None or not user.is_active:
        raise ApiError("unauthenticated", "Compte introuvable ou désactivé.")

    return user


def require_roles(*roles: str) -> Callable[[AppUser], AppUser]:
    """Dépendance paramétrée : `Depends(require_roles("administrateur", "operatrice"))`."""

    def _check(user: AppUser = Depends(get_current_user)) -> AppUser:
        if user.role not in roles:
            raise ApiError(
                "forbidden_role",
                "Ce rôle ne permet pas d'accéder à cette ressource.",
                details={"role": user.role, "allowed": list(roles)},
            )
        return user

    return _check
