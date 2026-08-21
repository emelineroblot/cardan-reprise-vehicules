"""Service photos — parcours d'angles imposé, plafond par véhicule, idempotence par
`client_uuid` (plan.md § 3.6, § 4 décision C).

Le stockage des octets passe systématiquement par l'abstraction `PhotoStorage`
(`app/services/storage/`) : ce module ne connaît que `bucket`/`key`, jamais un chemin disque.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError
from app.models.enums import PhotoAngle, PhotoPhase, UploadState
from app.models.inspection import Inspection
from app.models.photo import Photo
from app.models.user import AppUser
from app.models.vehicle import Vehicle
from app.models.work_order import WorkOrder
from app.services.storage.base import PhotoStorage

# Plafond applicatif par véhicule (plan.md § 3.6 : « CHECK métier à 30 photos par véhicule,
# refus 409 conflict au-delà ») — 12 angles imposés + 8 défauts optionnels au parcours de
# contrôle, marge pour les phases atelier (J3, `avant_travaux`/`apres_travaux`).
MAX_PHOTOS_PER_VEHICLE = 30

_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
_EXTENSION_BY_CONTENT_TYPE = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


def create_photo(
    db: Session,
    storage: PhotoStorage,
    *,
    vehicle: Vehicle,
    uploader: AppUser,
    client_uuid: UUID,
    angle: str,
    phase: str,
    inspection_id: UUID | None,
    work_order_id: UUID | None = None,
    captured_at: datetime,
    checksum_sha256: str,
    width: int,
    height: int,
    content: bytes,
    content_type: str,
) -> tuple[Photo, bool]:
    """Idempotent par `client_uuid` — un rejeu après coupure réseau renvoie la photo déjà reçue
    sans réécrire l'octet (décision C : « un renvoi ne duplique rien »).
    Renvoie `(photo, created)`.

    Deux familles de photo, mutuellement exclusives (plan.md § 5.1 : `photo.inspection_id` et
    `photo.work_order_id` sont tous deux nullable) :
    - `phase = 'controle'` -> rattachée à une `inspection` (parcours J2, inchangé) ;
    - `phase in ('avant_travaux', 'apres_travaux')` -> rattachée à un `work_order` (atelier, J3,
      ouverture additive de la colonne posée dès J1 — pas une révision du parcours J2).
    """
    existing = db.scalar(select(Photo).where(Photo.client_uuid == client_uuid))
    if existing is not None:
        return existing, False

    if angle not in {a.value for a in PhotoAngle}:
        raise ApiError("validation_error", "Angle de photo inconnu.")
    if phase not in {p.value for p in PhotoPhase}:
        raise ApiError("validation_error", "Phase de photo inconnue.")
    if content_type not in _ALLOWED_CONTENT_TYPES:
        raise ApiError(
            "validation_error", "Type de fichier non pris en charge (JPEG, PNG ou WEBP attendu)."
        )

    inspection: Inspection | None = None
    work_order: WorkOrder | None = None
    if phase == PhotoPhase.CONTROLE.value:
        if inspection_id is None:
            raise ApiError(
                "validation_error", "`inspection_id` est requis pour une photo de contrôle."
            )
        inspection = db.get(Inspection, inspection_id)
        if inspection is None or inspection.vehicle_id != vehicle.id:
            raise ApiError("not_found", "Inspection introuvable pour ce véhicule.")
        if inspection.submitted_at is not None:
            raise ApiError(
                "conflict", "Cette inspection est déjà soumise, elle n'accepte plus de photos."
            )
    else:
        # `avant_travaux` / `apres_travaux` (J3)
        if work_order_id is None:
            raise ApiError(
                "validation_error",
                "`work_order_id` est requis pour une photo avant/après travaux.",
            )
        work_order = db.get(WorkOrder, work_order_id)
        if work_order is None or work_order.vehicle_id != vehicle.id:
            raise ApiError("not_found", "Ordre de travaux introuvable pour ce véhicule.")

    computed_checksum = hashlib.sha256(content).hexdigest()
    if computed_checksum != checksum_sha256.strip().lower():
        raise ApiError(
            "validation_error",
            "Le checksum transmis ne correspond pas au contenu reçu (fichier corrompu ou tronqué).",
        )

    total = (
        db.scalar(select(func.count()).select_from(Photo).where(Photo.vehicle_id == vehicle.id))
        or 0
    )
    if total >= MAX_PHOTOS_PER_VEHICLE:
        raise ApiError(
            "photo_quota_exceeded",
            "Ce véhicule a atteint le nombre maximal de photos autorisé.",
            details={"limit": MAX_PHOTOS_PER_VEHICLE},
        )

    if inspection is not None and angle != PhotoAngle.DEFAUT.value:
        # Contrainte d'unicité en base (`uq_photo_inspection_angle_controle`) scopée à
        # `phase = 'controle'` — sans objet pour `avant_travaux`/`apres_travaux`, où l'angle n'a
        # pas de sens de parcours imposé (l'atelier documente ce qu'il veut, sans liste fermée).
        duplicate_angle = db.scalar(
            select(Photo).where(
                Photo.inspection_id == inspection.id,
                Photo.angle == angle,
                Photo.phase == PhotoPhase.CONTROLE.value,
            )
        )
        if duplicate_angle is not None:
            raise ApiError(
                "conflict",
                "Cet angle a déjà été photographié pour ce contrôle.",
                details={"angle": angle, "photo_id": str(duplicate_angle.id)},
            )

    settings = get_settings()
    bucket = settings.supabase_bucket
    key = f"runtime/{vehicle.id}/{uuid4().hex}{_EXTENSION_BY_CONTENT_TYPE.get(content_type, '')}"
    # Écriture avant l'insertion en base : en cas d'échec applicatif après coup, l'octet orphelin
    # sur disque local n'a pas de conséquence pratique en démo (purgé au reset nocturne — le
    # préfixe `runtime/` est vidé dans son ensemble, orphelins compris).
    storage.save(bucket=bucket, key=key, content=content)

    photo = Photo(
        id=uuid4(),
        vehicle_id=vehicle.id,
        inspection_id=inspection.id if inspection is not None else None,
        work_order_id=work_order.id if work_order is not None else None,
        angle=angle,
        phase=phase,
        storage_bucket=bucket,
        storage_key=key,
        content_type=content_type,
        byte_size=len(content),
        width=width,
        height=height,
        checksum_sha256=computed_checksum,
        client_uuid=client_uuid,
        upload_state=UploadState.ENVOYEE.value,
        is_placeholder=False,
        captured_at=captured_at,
        uploaded_at=datetime.now(UTC),
        uploaded_by_id=uploader.id,
    )
    db.add(photo)
    db.flush()
    return photo, True
