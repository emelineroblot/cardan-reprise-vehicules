"""Format d'erreur unique de l'API — plan.md § 3.5.

Toute erreur, y compris `RequestValidationError` et `HTTPException`, est rendue sous la forme :

    { "error": { "code": "...", "message": "...", "details": {...} } }

Le front mappe le `code` (jamais le `message`, non stable pour l'UI) vers ses libellés.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

# Catalogue de codes stables — ne jamais renommer une valeur existante (le front dépend du code).
ErrorCode = Literal[
    "validation_error",
    "unauthenticated",
    "forbidden_role",
    "not_found",
    "duplicate_exact",
    "duplicate_probable",
    "invalid_transition",
    "siret_invalid",
    "siret_not_found",
    "siret_lookup_unavailable",
    "conflict",
    "internal_error",
]

_STATUS_BY_CODE: dict[str, int] = {
    "validation_error": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "unauthenticated": status.HTTP_401_UNAUTHORIZED,
    "forbidden_role": status.HTTP_403_FORBIDDEN,
    "not_found": status.HTTP_404_NOT_FOUND,
    "duplicate_exact": status.HTTP_409_CONFLICT,
    "duplicate_probable": status.HTTP_409_CONFLICT,
    "invalid_transition": status.HTTP_409_CONFLICT,
    "siret_invalid": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "siret_not_found": status.HTTP_404_NOT_FOUND,
    "siret_lookup_unavailable": status.HTTP_503_SERVICE_UNAVAILABLE,
    "conflict": status.HTTP_409_CONFLICT,
    "internal_error": status.HTTP_500_INTERNAL_SERVER_ERROR,
}

# Filet de sécurité pour toute écriture qui n'a pas rejoué le contrôle applicatif en amont
# (ex. `PATCH /vehicles/{id}` modifiant le VIN vers une valeur déjà prise par une autre fiche,
# ou une collision concurrente) — revue § 🟠 « zéro handler IntegrityError dans tout `app/` ».
# Les contrôles applicatifs restent la première ligne de défense ; ceci est le filet, pas la
# stratégie principale.
_CONSTRAINT_TO_ERROR: dict[str, tuple[ErrorCode, str, dict[str, str]]] = {
    "uq_vehicle_vin_normalise": (
        "duplicate_exact",
        "Ce VIN existe déjà.",
        {"champ": "vin"},
    ),
    "uq_vehicle_immat_normalisee": (
        "duplicate_exact",
        "Cette immatriculation existe déjà.",
        {"champ": "immatriculation"},
    ),
    "uq_company_siret": (
        "conflict",
        "Une société avec ce SIRET existe déjà.",
        {"champ": "siret"},
    ),
    "uq_vehicle_reference": (
        "conflict",
        "Cette référence véhicule existe déjà.",
        {"champ": "reference"},
    ),
    "uq_duplicate_review_paire": (
        "conflict",
        "Un arbitrage existe déjà pour cette paire de véhicules.",
        {},
    ),
}


def _constraint_name_from_integrity_error(exc: IntegrityError) -> str | None:
    """Nom de la contrainte violée, si le driver l'expose (psycopg 3 : `diag.constraint_name`)."""
    diag = getattr(exc.orig, "diag", None)
    name = getattr(diag, "constraint_name", None)
    if name:
        return str(name)
    # Repli : certains messages embarquent le nom entre guillemets doubles.
    text = str(exc.orig) if exc.orig is not None else str(exc)
    match = re.search(r'"([a-z0-9_]+)"', text)
    return match.group(1) if match else None


class ApiError(Exception):
    """Exception métier portant un code stable du catalogue + détails structurés."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        status_code: int | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.details = details or {}
        self.status_code = status_code or _STATUS_BY_CODE.get(code, status.HTTP_400_BAD_REQUEST)
        super().__init__(message)

    def to_response(self) -> JSONResponse:
        return JSONResponse(
            status_code=self.status_code,
            content={
                "error": {
                    "code": self.code,
                    "message": self.message,
                    "details": self.details,
                }
            },
        )


def _error_response(
    status_code: int, code: str, message: str, details: dict[str, Any] | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": details or {}}},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Enregistre les exception handlers globaux — appelé une fois depuis `app.main`."""

    @app.exception_handler(ApiError)
    async def _handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        return exc.to_response()

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "validation_error",
            "Les données envoyées sont invalides.",
            {"errors": exc.errors()},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code_by_status = {
            status.HTTP_401_UNAUTHORIZED: "unauthenticated",
            status.HTTP_403_FORBIDDEN: "forbidden_role",
            status.HTTP_404_NOT_FOUND: "not_found",
            status.HTTP_409_CONFLICT: "conflict",
        }
        code = code_by_status.get(exc.status_code, "internal_error")
        message = exc.detail if isinstance(exc.detail, str) else "Une erreur est survenue."
        return _error_response(exc.status_code, code, message)

    @app.exception_handler(IntegrityError)
    async def _handle_integrity_error(request: Request, exc: IntegrityError) -> JSONResponse:
        constraint = _constraint_name_from_integrity_error(exc)
        mapped = _CONSTRAINT_TO_ERROR.get(constraint or "")
        if mapped is not None:
            code, message, details = mapped
            return _error_response(_STATUS_BY_CODE[code], code, message, dict(details))
        # Contrainte non répertoriée (ex. NOT NULL, FK) : 409 générique plutôt qu'un 500 brut —
        # c'est toujours une violation de contrainte d'intégrité, jamais une erreur serveur.
        return _error_response(
            status.HTTP_409_CONFLICT,
            "conflict",
            "L'opération viole une contrainte d'intégrité (donnée déjà utilisée ou invalide).",
            {"constraint": constraint} if constraint else {},
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "internal_error",
            "Une erreur interne est survenue.",
        )
