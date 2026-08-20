"""Point d'entrée FastAPI — création de l'app, routers, CORS, exception handlers.

Servi en local par `uvicorn app.main:app`, et en production via `backend/api/index.py`
(runtime ASGI Vercel — plan.md § 3.8).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.admin import router as admin_router
from app.api.v1.analytics import router as analytics_router
from app.api.v1.auth import router as auth_router
from app.api.v1.companies import router as companies_router
from app.api.v1.duplicates import router as duplicates_router
from app.api.v1.health import router as health_router
from app.api.v1.vehicles import router as vehicles_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers

settings = get_settings()

app = FastAPI(
    title="Cardan API",
    description="Outil interne de gestion d'achat de véhicules d'occasion — démonstration.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(health_router, prefix="/api/v1", tags=["health"])
app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(companies_router, prefix="/api/v1/companies", tags=["companies"])
app.include_router(vehicles_router, prefix="/api/v1/vehicles", tags=["vehicles"])
app.include_router(duplicates_router, prefix="/api/v1", tags=["duplicates"])
app.include_router(analytics_router, prefix="/api/v1/analytics", tags=["analytics"])
app.include_router(admin_router, prefix="/api/v1/admin", tags=["admin"])
