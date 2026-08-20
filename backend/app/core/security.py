"""Authentification native — argon2id + JWT en cookie httpOnly (plan.md § 3.4, décision native).

Pas de refresh token : c'est une démo, la session se réouvre en un clic. Le cookie n'est
lisible que parce que le front et l'API sont same-origin via le proxy `rewrites` de Next.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Response

from app.core.config import get_settings

settings = get_settings()
_hasher = PasswordHasher()

JWT_SUBJECT_CLAIM = "sub"
JWT_ROLE_CLAIM = "role"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except InvalidHashError:
        # `password_hash` corrompu ou vide en base — un cas anormal, jamais un mot de passe
        # incorrect ordinaire, mais qui doit rester un refus d'authentification (401), pas un
        # 500 (revue § 🟡).
        return False


def create_access_token(user_id: UUID, role: str) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        JWT_SUBJECT_CLAIM: str(user_id),
        JWT_ROLE_CLAIM: role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expires_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """Lève `jwt.PyJWTError` (ou une sous-classe) si le jeton est invalide ou expiré."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        httponly=True,
        secure=settings.is_remote,
        samesite="lax",
        path="/",
        max_age=settings.jwt_expires_minutes * 60,
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=settings.session_cookie_name, path="/")
