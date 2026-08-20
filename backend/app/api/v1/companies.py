"""`GET /companies/lookup/{siret}`, `POST /companies`, `GET /companies`, `GET /companies/{id}`.

Plan.md § 6 vague 2. Le fallback manuel n'est jamais bloquant : un `503` du lookup n'empêche
jamais la création d'une société en saisie manuelle (critère d'acceptation du brief).
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.pagination import Page, PageParams, page_params, paginate
from app.db.session import get_db
from app.models.company import Company
from app.models.user import AppUser
from app.schemas.company import (
    CompanyCreate,
    CompanyLookupCompany,
    CompanyLookupResponse,
    CompanyRead,
)
from app.services.company_lookup.service import get_provider, lookup_company
from app.services.siret import is_valid_siret, normalize_siret

router = APIRouter()

_ALLOWED_ROLES = ("operatrice", "administrateur")


@router.get("/lookup/{siret}", response_model=CompanyLookupResponse)
def lookup_siret(
    siret: str,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_roles(*_ALLOWED_ROLES)),
) -> CompanyLookupResponse:
    settings = get_settings()
    provider = get_provider(settings)
    normalized = normalize_siret(siret)
    outcome = lookup_company(db, normalized, provider)
    db.commit()
    return CompanyLookupResponse(
        source=outcome.source,
        stale=outcome.stale,
        company=CompanyLookupCompany(**dataclasses.asdict(outcome.company)),
    )


@router.post("", response_model=CompanyRead, status_code=201)
def create_company(
    payload: CompanyCreate,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_roles(*_ALLOWED_ROLES)),
) -> Company:
    siret = normalize_siret(payload.siret)
    if not is_valid_siret(siret):
        raise ApiError("siret_invalid", "Le SIRET est invalide (14 chiffres, clé de Luhn).")

    existing = db.scalar(select(Company).where(Company.siret == siret))
    if existing is not None:
        raise ApiError(
            "conflict",
            "Une société avec ce SIRET existe déjà.",
            details={"company_id": str(existing.id)},
        )

    company = Company(
        id=uuid4(),
        siren=siret[:9],
        siret=siret,
        denomination=payload.denomination,
        forme_juridique=payload.forme_juridique,
        code_naf=payload.code_naf,
        libelle_naf=payload.libelle_naf,
        adresse_ligne1=payload.adresse_ligne1,
        code_postal=payload.code_postal,
        commune=payload.commune,
        pays=payload.pays,
        tranche_effectif=payload.tranche_effectif,
        date_creation=payload.date_creation,
        type_flotte=payload.type_flotte,
        source_enrichissement=payload.source_enrichissement,
        enriched_at=None if payload.source_enrichissement == "manuel" else datetime.now(UTC),
        contact_nom=payload.contact_nom,
        contact_telephone=payload.contact_telephone,
        created_by_id=user.id,
    )
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


@router.get("", response_model=Page[CompanyRead])
def list_companies(
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_roles(*_ALLOWED_ROLES)),
    params: PageParams = Depends(page_params),
    q: str | None = None,
) -> Page[CompanyRead]:
    stmt = select(Company)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(Company.denomination.ilike(like) | Company.siret.ilike(like))
    stmt = stmt.order_by(Company.denomination)
    items, total = paginate(db, stmt, params)
    return Page[CompanyRead](
        items=[CompanyRead.model_validate(i) for i in items],
        total=total,
        limit=params.limit,
        offset=params.offset,
    )


@router.get("/{company_id}", response_model=CompanyRead)
def get_company(
    company_id: UUID,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_roles(*_ALLOWED_ROLES)),
) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise ApiError("not_found", "Société introuvable.")
    return company
