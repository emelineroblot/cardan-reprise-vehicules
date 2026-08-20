"""`POST /auth/login`, `POST /auth/logout`, `GET /auth/me` — plan.md § 3.4 / § 6 vague 1."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.errors import ApiError
from app.core.security import (
    clear_session_cookie,
    create_access_token,
    set_session_cookie,
    verify_password,
)
from app.db.session import get_db
from app.models.user import AppUser
from app.schemas.auth import LoginRequest, MeResponse

router = APIRouter()


@router.post("/login", response_model=MeResponse)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> AppUser:
    user = db.scalar(select(AppUser).where(AppUser.email == payload.email.lower()))
    if (
        user is None
        or not user.is_active
        or not verify_password(payload.password, user.password_hash)
    ):
        raise ApiError("unauthenticated", "Identifiants invalides.")

    token = create_access_token(user.id, user.role)
    set_session_cookie(response, token)
    return user


@router.post("/logout")
def logout(response: Response) -> dict[str, bool]:
    clear_session_cookie(response)
    return {"ok": True}


@router.get("/me", response_model=MeResponse)
def me(user: AppUser = Depends(get_current_user)) -> AppUser:
    return user
