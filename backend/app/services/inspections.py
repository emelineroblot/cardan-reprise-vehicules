"""Service inspections — création idempotente, checklist, complétude (angles imposés + items
obligatoires) et soumission (plan.md § 4 décision C, § 5.3).

La garde d'automate `inspection_submitted_with_required_angles`
(`app/services/state_machine.py`, `app/services/vehicles.py::build_transition_context`) se
contente de vérifier qu'une `Inspection.submitted_at` existe pour le véhicule : c'est
`submit_inspection` ci-dessous qui porte la vérité de la complétude, **avant** de poser cette
date. Aucune autre voie ne peut poser `submitted_at`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.checklist import ChecklistItemTemplate, ChecklistTemplate
from app.models.enums import PhotoAngle, PhotoPhase, UploadState, VehicleState
from app.models.inspection import Inspection, InspectionItem
from app.models.photo import Photo
from app.models.user import AppUser
from app.models.vehicle import Vehicle
from app.schemas.inspection import InspectionItemUpsert
from app.services.missions import get_active_mission

# Les 12 angles imposés du parcours photo guidé — tous les angles sauf `defaut` (photos de
# défaut, libres et répétables, plan.md § 3.6/§ 5.1 : seule `defaut` échappe à la contrainte
# d'unicité `UNIQUE(inspection_id, angle) WHERE phase = 'controle' AND angle <> 'defaut'`).
REQUIRED_PHOTO_ANGLES: tuple[PhotoAngle, ...] = tuple(
    angle for angle in PhotoAngle if angle != PhotoAngle.DEFAUT
)

_RESPONSE_TYPE_OK_KO = "ok_ko"
_RESPONSE_TYPE_NOTE = "note_1_5"
_RESPONSE_TYPE_TEXTE = "texte"
_RESPONSE_TYPE_NUMERIQUE = "numerique"


def _default_template(db: Session) -> ChecklistTemplate:
    template = db.scalar(
        select(ChecklistTemplate)
        .where(ChecklistTemplate.is_active.is_(True))
        .order_by(ChecklistTemplate.version.desc())
    )
    if template is None:
        raise ApiError(
            "conflict",
            "Aucun modèle de checklist actif — le référentiel doit être chargé "
            "(`python -m app.cli seed --profile reference`).",
        )
    return template


def get_or_create_inspection(
    db: Session,
    *,
    vehicle: Vehicle,
    driver: AppUser,
    client_uuid: UUID,
    template_id: UUID | None,
) -> tuple[Inspection, bool]:
    """Idempotent par `client_uuid` (décision C — le brouillon peut naître hors ligne, sa
    création doit tolérer un rejeu au retour du réseau). Renvoie `(inspection, created)`."""
    existing = db.scalar(select(Inspection).where(Inspection.client_uuid == client_uuid))
    if existing is not None:
        return existing, False

    if vehicle.state != VehicleState.CONTROLE_EN_COURS.value:
        raise ApiError(
            "inspection_not_allowed",
            "Le contrôle sur place n'est pas en cours pour ce véhicule.",
            details={"vehicle_state": vehicle.state},
        )

    mission = get_active_mission(db, vehicle.id)
    if mission is None or mission.driver_id != driver.id:
        raise ApiError(
            "inspection_not_allowed", "Aucune mission active ne vous est affectée pour ce véhicule."
        )

    # Une seule inspection par mission (plan.md § 5.3 : `RDV_PLANIFIE → CONTROLE_EN_COURS` est
    # l'unique transition qui crée une `inspection`, aucune transition ne fait repasser un
    # véhicule par cet état pour la même mission). Le véhicule reste en `CONTROLE_EN_COURS`
    # jusqu'à la transition de conclusion suivante : un rechargement de l'écran juste après une
    # soumission régénère côté client un `client_uuid` FRAIS (`getOrCreateDraft` ne retrouve pas
    # le brouillon soumis, filtré par `!submitted_at`) — sans ce garde-fou, ce simple
    # rechargement ouvrait une seconde inspection concurrente pour le même contrôle
    # (review-j2.md § 5). On renvoie l'inspection existante de la mission, soumise ou non,
    # plutôt que d'en créer une seconde : c'est ce choix qui simplifie le plus le front, qui n'a
    # alors rien de spécial à gérer — `POST /inspections` reste idempotent au sens large, pas
    # seulement par `client_uuid`. Doublée d'une contrainte d'unicité en base
    # (`uq_inspection_mission`, migration 0003) pour fermer la fenêtre de concurrence entre deux
    # requêtes simultanées.
    existing_for_mission = db.scalar(select(Inspection).where(Inspection.mission_id == mission.id))
    if existing_for_mission is not None:
        return existing_for_mission, False

    if template_id is not None:
        template = db.get(ChecklistTemplate, template_id)
        if template is None:
            raise ApiError("not_found", "Modèle de checklist introuvable.")
    else:
        template = _default_template(db)

    inspection = Inspection(
        id=uuid4(),
        vehicle_id=vehicle.id,
        mission_id=mission.id,
        driver_id=driver.id,
        template_id=template.id,
        client_uuid=client_uuid,
        started_at=datetime.now(UTC),
    )
    db.add(inspection)
    db.flush()
    return inspection, True


def upsert_items(db: Session, inspection: Inspection, items: list[InspectionItemUpsert]) -> None:
    if inspection.submitted_at is not None:
        raise ApiError(
            "conflict", "Cette inspection est déjà soumise, elle ne peut plus être modifiée."
        )

    for item_in in items:
        response = db.scalar(
            select(InspectionItem).where(
                InspectionItem.inspection_id == inspection.id,
                InspectionItem.item_template_id == item_in.item_template_id,
            )
        )
        if response is None:
            response = InspectionItem(
                id=uuid4(),
                inspection_id=inspection.id,
                item_template_id=item_in.item_template_id,
            )
            db.add(response)
        response.valeur_bool = item_in.valeur_bool
        response.valeur_note = item_in.valeur_note
        response.valeur_texte = item_in.valeur_texte
        response.valeur_num = item_in.valeur_num
        response.commentaire = item_in.commentaire
        response.photo_id = item_in.photo_id
    db.flush()


def _has_value(response_type: str, response: InspectionItem) -> bool:
    if response_type == _RESPONSE_TYPE_OK_KO:
        return response.valeur_bool is not None
    if response_type == _RESPONSE_TYPE_NOTE:
        return response.valeur_note is not None
    if response_type == _RESPONSE_TYPE_TEXTE:
        return bool(response.valeur_texte and response.valeur_texte.strip())
    if response_type == _RESPONSE_TYPE_NUMERIQUE:
        return response.valeur_num is not None
    return False  # pragma: no cover — filet si `ResponseType` gagne une valeur non traitée ici


def _missing_required_items(db: Session, inspection: Inspection) -> list[str]:
    required_templates = list(
        db.scalars(
            select(ChecklistItemTemplate).where(
                ChecklistItemTemplate.template_id == inspection.template_id,
                ChecklistItemTemplate.is_required.is_(True),
            )
        ).all()
    )
    responses = {
        row.item_template_id: row
        for row in db.scalars(
            select(InspectionItem).where(InspectionItem.inspection_id == inspection.id)
        ).all()
    }
    missing = []
    for template in required_templates:
        response = responses.get(template.id)
        if response is None or not _has_value(template.response_type, response):
            missing.append(template.code)
    return missing


def _missing_required_angles(db: Session, inspection: Inspection) -> list[str]:
    captured = set(
        db.scalars(
            select(Photo.angle).where(
                Photo.inspection_id == inspection.id,
                Photo.phase == PhotoPhase.CONTROLE.value,
                Photo.upload_state == UploadState.ENVOYEE.value,
            )
        ).all()
    )
    return [angle.value for angle in REQUIRED_PHOTO_ANGLES if angle.value not in captured]


def submit_inspection(db: Session, inspection: Inspection, payload: dict) -> Inspection:
    """Refuse de valider s'il manque un item obligatoire ou un angle imposé (brief J2, critère
    d'acceptation). Idempotent : un rejeu après coupure réseau renvoie l'inspection déjà soumise
    telle quelle, sans revalider (décision C : « un renvoi ne duplique rien »)."""
    if inspection.submitted_at is not None:
        return inspection

    if payload.get("kilometrage_releve") is not None:
        inspection.kilometrage_releve = payload["kilometrage_releve"]
    if payload.get("etat_general") is not None:
        inspection.etat_general = payload["etat_general"]
    if payload.get("conclusion") is not None:
        inspection.conclusion = payload["conclusion"]
    if payload.get("commentaire") is not None:
        inspection.commentaire = payload["commentaire"]

    missing_items = _missing_required_items(db, inspection)
    missing_angles = _missing_required_angles(db, inspection)
    if missing_items or missing_angles:
        raise ApiError(
            "inspection_incomplete",
            "Le contrôle n'est pas complet — il manque des réponses obligatoires ou des photos "
            "d'angles imposés.",
            details={"missing_items": missing_items, "missing_angles": missing_angles},
        )

    inspection.submitted_at = datetime.now(UTC)
    db.flush()
    return inspection
