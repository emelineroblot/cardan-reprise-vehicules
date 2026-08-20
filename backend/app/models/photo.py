"""`photo` — J2, colonnes posées dès J1 (décision C : idempotence hors ligne)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import PhotoAngle, PhotoPhase, UploadState, check_in


class Photo(Base):
    __tablename__ = "photo"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    vehicle_id: Mapped[UUID] = mapped_column(ForeignKey("vehicle.id"), nullable=False)
    inspection_id: Mapped[UUID | None] = mapped_column(ForeignKey("inspection.id"), nullable=True)
    work_order_id: Mapped[UUID | None] = mapped_column(ForeignKey("work_order.id"), nullable=True)
    angle: Mapped[str] = mapped_column(String(40), nullable=False)
    phase: Mapped[str] = mapped_column(String(20), nullable=False)
    storage_bucket: Mapped[str] = mapped_column(String(50), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(50), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    client_uuid: Mapped[UUID] = mapped_column(nullable=False)
    upload_state: Mapped[str] = mapped_column(String(20), nullable=False)
    is_placeholder: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    captured_at: Mapped[datetime] = mapped_column(nullable=False)
    uploaded_at: Mapped[datetime | None] = mapped_column(nullable=True)
    uploaded_by_id: Mapped[UUID] = mapped_column(ForeignKey("app_user.id"), nullable=False)

    __table_args__ = (
        UniqueConstraint("storage_key", name="uq_photo_storage_key"),
        UniqueConstraint("client_uuid", name="uq_photo_client_uuid"),
        CheckConstraint(f"angle IN ({check_in(*PhotoAngle)})", name="angle_valide"),
        CheckConstraint(f"phase IN ({check_in(*PhotoPhase)})", name="phase_valide"),
        CheckConstraint(f"upload_state IN ({check_in(*UploadState)})", name="upload_state_valide"),
        # Le parcours d'angles imposé devient une garantie de base, pas une règle d'UI.
        Index(
            "uq_photo_inspection_angle_controle",
            "inspection_id",
            "angle",
            unique=True,
            postgresql_where=text("phase = 'controle' AND angle <> 'defaut'"),
        ),
        Index("ix_photo_vehicle_phase", "vehicle_id", "phase"),
    )
