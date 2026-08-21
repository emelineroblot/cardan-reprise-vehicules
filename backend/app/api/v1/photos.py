"""`/vehicles/{vehicle_id}/photos`, `/photos/file/{bucket}/{key}` — parcours photo guidé
(plan.md § 3.6, § 4 décision C).

Le parcours d'angles imposé est une garantie de base (`UNIQUE(inspection_id, angle) WHERE
phase = 'controle'`) doublée ici d'un contrôle applicatif explicite (message clair, 409 plutôt
qu'une violation de contrainte brute) — et `submit_inspection`
(`app/services/inspections.py`) est le point qui **refuse de valider** s'il manque un angle
obligatoire (critère d'acceptation du brief).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Form, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.errors import ApiError
from app.db.session import get_db
from app.models.photo import Photo
from app.models.user import AppUser
from app.models.vehicle import Vehicle
from app.schemas.photo import PhotoRead, RequiredAnglesResponse
from app.services.inspections import REQUIRED_PHOTO_ANGLES
from app.services.photos import create_photo
from app.services.storage.service import get_storage_backend
from app.services.vehicle_scope import scope_vehicles

router = APIRouter()

# `atelier` — photos avant/après travaux (J3, phases `avant_travaux`/`apres_travaux`, liées à un
# `work_order_id` plutôt qu'à un `inspection_id`, voir `app/services/photos.py::create_photo`).
_UPLOAD_ROLES = ("chauffeur", "administrateur", "atelier")


def _get_scoped_vehicle(db: Session, vehicle_id: UUID, user: AppUser) -> Vehicle:
    vehicle = db.scalar(scope_vehicles(select(Vehicle).where(Vehicle.id == vehicle_id), user))
    if vehicle is None:
        raise ApiError("not_found", "Véhicule introuvable.")
    return vehicle


def _to_read(photo: Photo) -> PhotoRead:
    storage = get_storage_backend()
    return PhotoRead(
        id=photo.id,
        vehicle_id=photo.vehicle_id,
        inspection_id=photo.inspection_id,
        work_order_id=photo.work_order_id,
        angle=photo.angle,
        phase=photo.phase,
        content_type=photo.content_type,
        byte_size=photo.byte_size,
        width=photo.width,
        height=photo.height,
        client_uuid=photo.client_uuid,
        upload_state=photo.upload_state,
        is_placeholder=photo.is_placeholder,
        captured_at=photo.captured_at,
        uploaded_at=photo.uploaded_at,
        url=storage.read_url(bucket=photo.storage_bucket, key=photo.storage_key),
    )


def _parse_captured_at(raw: str) -> datetime:
    try:
        value = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ApiError(
            "validation_error", "`captured_at` invalide (date ISO-8601 attendue)."
        ) from exc
    return value


@router.post("/vehicles/{vehicle_id}/photos", response_model=PhotoRead, status_code=201)
async def upload_photo(
    vehicle_id: UUID,
    file: UploadFile,
    client_uuid: Annotated[UUID, Form()],
    angle: Annotated[str, Form()],
    phase: Annotated[str, Form()],
    captured_at: Annotated[str, Form()],
    checksum_sha256: Annotated[str, Form()],
    width: Annotated[int, Form()],
    height: Annotated[int, Form()],
    inspection_id: Annotated[UUID | None, Form()] = None,
    work_order_id: Annotated[UUID | None, Form()] = None,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_roles(*_UPLOAD_ROLES)),
) -> PhotoRead:
    vehicle = _get_scoped_vehicle(db, vehicle_id, user)
    content = await file.read()
    storage = get_storage_backend()
    photo, created = create_photo(
        db,
        storage,
        vehicle=vehicle,
        uploader=user,
        client_uuid=client_uuid,
        angle=angle,
        phase=phase,
        inspection_id=inspection_id,
        work_order_id=work_order_id,
        captured_at=_parse_captured_at(captured_at),
        checksum_sha256=checksum_sha256,
        width=width,
        height=height,
        content=content,
        content_type=file.content_type or "application/octet-stream",
    )
    db.commit()
    db.refresh(photo)
    return _to_read(photo)


@router.get("/vehicles/{vehicle_id}/photos", response_model=list[PhotoRead])
def list_vehicle_photos(
    vehicle_id: UUID,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
    inspection_id: UUID | None = None,
    work_order_id: UUID | None = None,
    phase: str | None = None,
) -> list[PhotoRead]:
    _get_scoped_vehicle(db, vehicle_id, user)
    stmt = select(Photo).where(Photo.vehicle_id == vehicle_id)
    if inspection_id:
        stmt = stmt.where(Photo.inspection_id == inspection_id)
    if work_order_id:
        stmt = stmt.where(Photo.work_order_id == work_order_id)
    if phase:
        stmt = stmt.where(Photo.phase == phase)
    stmt = stmt.order_by(Photo.captured_at)
    photos = list(db.scalars(stmt).all())
    return [_to_read(p) for p in photos]


@router.get("/vehicles/{vehicle_id}/photos/required-angles", response_model=RequiredAnglesResponse)
def get_required_angles(
    vehicle_id: UUID,
    inspection_id: UUID,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> RequiredAnglesResponse:
    """Ce que le front doit encore capturer pour `inspection_id` — la liste des 12 angles
    imposés est portée par le backend (`REQUIRED_PHOTO_ANGLES`), jamais recopiée côté front."""
    _get_scoped_vehicle(db, vehicle_id, user)
    captured = set(
        db.scalars(
            select(Photo.angle).where(
                Photo.inspection_id == inspection_id,
                Photo.phase == "controle",
                Photo.upload_state == "envoyee",
            )
        ).all()
    )
    required = [a.value for a in REQUIRED_PHOTO_ANGLES]
    return RequiredAnglesResponse(
        required_angles=required,
        captured_angles=[a for a in required if a in captured],
        missing_angles=[a for a in required if a not in captured],
    )


@router.get("/photos/file/{bucket}/{key:path}")
def get_photo_file(
    bucket: str,
    key: str,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> Response:
    photo = db.scalar(select(Photo).where(Photo.storage_bucket == bucket, Photo.storage_key == key))
    if photo is None:
        raise ApiError("not_found", "Photo introuvable.")
    vehicle = db.scalar(scope_vehicles(select(Vehicle).where(Vehicle.id == photo.vehicle_id), user))
    if vehicle is None:
        # Ne jamais distinguer « photo inexistante » de « accès refusé » (fuite d'existence) —
        # même convention que `_get_scoped_vehicle` (`app/api/v1/vehicles.py`).
        raise ApiError("not_found", "Photo introuvable.")

    storage = get_storage_backend()
    try:
        content = storage.load(bucket=bucket, key=key)
    except FileNotFoundError as exc:
        raise ApiError("not_found", "Fichier introuvable.") from exc
    return Response(content=content, media_type=photo.content_type)
