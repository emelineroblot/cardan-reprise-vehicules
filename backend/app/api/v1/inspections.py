"""`/inspections/*` — formulaire de contrôle + checklist interactive (brief J2, plan.md § 4
décision C, § 5.3).

Seul le chauffeur affecté crée/renseigne/soumet son inspection (miroir de la garde
`RDV_PLANIFIE → CONTROLE_EN_COURS`, réservée au chauffeur affecté dans l'automate — jamais
l'administrateur). La lecture reste ouverte à l'administrateur pour supervision.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_roles
from app.core.errors import ApiError
from app.db.session import get_db
from app.models.inspection import Inspection
from app.models.user import AppUser
from app.models.vehicle import Vehicle
from app.schemas.inspection import (
    InspectionCreate,
    InspectionItemsUpsertRequest,
    InspectionPatch,
    InspectionRead,
    InspectionSubmitRequest,
)
from app.services.inspections import get_or_create_inspection, submit_inspection, upsert_items
from app.services.vehicle_scope import scope_vehicles

router = APIRouter()

_READ_ROLES = ("chauffeur", "administrateur")
_WRITE_ROLES = ("chauffeur",)


def _scoped_inspection(db: Session, inspection_id: UUID, user: AppUser) -> Inspection:
    inspection = db.scalar(
        select(Inspection)
        .where(Inspection.id == inspection_id)
        .options(selectinload(Inspection.items))
    )
    if inspection is None:
        raise ApiError("not_found", "Inspection introuvable.")
    vehicle = db.scalar(
        scope_vehicles(select(Vehicle).where(Vehicle.id == inspection.vehicle_id), user)
    )
    if vehicle is None:
        raise ApiError("not_found", "Inspection introuvable.")
    return inspection


@router.post("", response_model=InspectionRead)
def create_inspection(
    payload: InspectionCreate,
    response: Response,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_roles(*_WRITE_ROLES)),
) -> Inspection:
    vehicle = db.scalar(
        scope_vehicles(select(Vehicle).where(Vehicle.id == payload.vehicle_id), user)
    )
    if vehicle is None:
        raise ApiError("not_found", "Véhicule introuvable.")

    inspection, created = get_or_create_inspection(
        db,
        vehicle=vehicle,
        driver=user,
        client_uuid=payload.client_uuid,
        template_id=payload.template_id,
    )
    db.commit()
    db.refresh(inspection)
    response.status_code = 201 if created else 200
    return inspection


@router.get("/{inspection_id}", response_model=InspectionRead)
def get_inspection(
    inspection_id: UUID,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_roles(*_READ_ROLES)),
) -> Inspection:
    return _scoped_inspection(db, inspection_id, user)


@router.patch("/{inspection_id}", response_model=InspectionRead)
def patch_inspection(
    inspection_id: UUID,
    payload: InspectionPatch,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_roles(*_WRITE_ROLES)),
) -> Inspection:
    inspection = _scoped_inspection(db, inspection_id, user)
    if inspection.submitted_at is not None:
        raise ApiError(
            "conflict", "Cette inspection est déjà soumise, elle ne peut plus être modifiée."
        )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(inspection, field, value)
    db.commit()
    db.refresh(inspection)
    return inspection


@router.put("/{inspection_id}/items", response_model=InspectionRead)
def put_inspection_items(
    inspection_id: UUID,
    payload: InspectionItemsUpsertRequest,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_roles(*_WRITE_ROLES)),
) -> Inspection:
    inspection = _scoped_inspection(db, inspection_id, user)
    upsert_items(db, inspection, payload.items)
    db.commit()
    db.refresh(inspection)
    return _scoped_inspection(db, inspection_id, user)


@router.post("/{inspection_id}/submit", response_model=InspectionRead)
def submit(
    inspection_id: UUID,
    payload: InspectionSubmitRequest,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_roles(*_WRITE_ROLES)),
) -> Inspection:
    inspection = _scoped_inspection(db, inspection_id, user)
    result = submit_inspection(db, inspection, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(result)
    return result
