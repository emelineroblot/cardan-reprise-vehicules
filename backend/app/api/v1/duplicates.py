"""`POST /intake-batches`, `POST /duplicate-reviews` — plan.md § 6 vague 3."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.errors import ApiError
from app.db.session import get_db
from app.models.company import Company
from app.models.intake_batch import IntakeBatch
from app.models.user import AppUser
from app.models.vehicle import DuplicateReview, Vehicle
from app.schemas.vehicle import (
    DuplicateReviewCreate,
    DuplicateReviewRead,
    IntakeBatchCreate,
    IntakeBatchRead,
)

router = APIRouter()

_WRITE_ROLES = ("operatrice", "administrateur")


@router.post("/intake-batches", response_model=IntakeBatchRead, status_code=201)
def create_intake_batch(
    payload: IntakeBatchCreate,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_roles(*_WRITE_ROLES)),
) -> IntakeBatch:
    company = db.get(Company, payload.company_id)
    if company is None:
        raise ApiError("not_found", "Société introuvable.")

    batch = IntakeBatch(
        id=uuid4(), company_id=payload.company_id, label=payload.label, created_by_id=user.id
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


@router.post("/duplicate-reviews", response_model=DuplicateReviewRead, status_code=201)
def create_duplicate_review(
    payload: DuplicateReviewCreate,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_roles(*_WRITE_ROLES)),
) -> DuplicateReview:
    """Un verdict `not_duplicate` est définitif (décision A, étape 5) : la paire n'est plus
    jamais reproposée par `run_duplicate_check`. Idempotent : un second arbitrage sur la même
    paire met à jour le verdict existant au lieu de violer la contrainte d'unicité."""
    a_id, b_id = sorted((payload.vehicle_a_id, payload.vehicle_b_id))
    if a_id == b_id:
        raise ApiError("validation_error", "Un véhicule ne peut pas être comparé à lui-même.")

    for vehicle_id in (a_id, b_id):
        if db.get(Vehicle, vehicle_id) is None:
            raise ApiError(
                "not_found", "Véhicule introuvable.", details={"vehicle_id": str(vehicle_id)}
            )

    existing = db.scalar(
        select(DuplicateReview).where(
            DuplicateReview.vehicle_a_id == a_id, DuplicateReview.vehicle_b_id == b_id
        )
    )
    if existing is not None:
        existing.verdict = payload.verdict
        existing.score = Decimal(str(payload.score))
        existing.features = payload.features
        existing.decided_by_id = user.id
        db.commit()
        db.refresh(existing)
        return existing

    review = DuplicateReview(
        id=uuid4(),
        vehicle_a_id=a_id,
        vehicle_b_id=b_id,
        verdict=payload.verdict,
        score=Decimal(str(payload.score)),
        features=payload.features,
        decided_by_id=user.id,
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return review
