"""`/vehicles/*` — plan.md § 6 vague 3 (le cœur de J1).

Aucun endpoint ne modifie `vehicle.state` directement : seul `POST /{id}/transitions` le fait
(plan.md § 5.3). Toute lecture passe par `scope_vehicles` (étage ligne du cloisonnement).
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.api.deps import get_current_user, require_roles
from app.core.errors import ApiError
from app.core.pagination import Page, PageParams, page_params, paginate
from app.db.session import get_db
from app.models.company import Company
from app.models.enums import UserRole, VehicleState
from app.models.user import AppUser
from app.models.vehicle import Vehicle
from app.schemas.vehicle import (
    AllowedTransitionsResponse,
    DuplicateCandidate,
    DuplicateCheckResponse,
    PipelineCountsResponse,
    PipelineStateCount,
    TransitionOptionRead,
    TransitionRequest,
    VehicleCreate,
    VehicleDraftIn,
    VehicleListItem,
    VehiclePatch,
    VehicleRead,
)
from app.services.audit import write_audit_log
from app.services.normalize import normalize_immatriculation, normalize_modele, normalize_vin
from app.services.state_machine import allowed_transitions
from app.services.vehicle_scope import scope_vehicles
from app.services.vehicles import (
    build_transition_context,
    check_exact_duplicate,
    create_vehicle,
    run_duplicate_check,
    transition_vehicle,
)

router = APIRouter()

_WRITE_ROLES = ("operatrice", "administrateur")

# Champs qui pèsent dans le score de dédoublonnage (dedup.py) — une correction sur l'un
# d'eux doit rejouer le contrôle (revue § 🟠).
DEDUP_RELEVANT_FIELDS = frozenset(
    {"marque", "modele", "version", "energie", "kilometrage", "date_proposition"}
)

# Cloisonnement des données financières (revue J3, 🔴 « le cloisonnement des données financières
# n'existe pas côté serveur ») — mêmes rôles que `canSeeFinances` côté front
# (`vehicules/[id]/page.tsx`), pour rester cohérent avec l'écran qu'ils alimentent tous les deux.
_FINANCE_VISIBLE_ROLES = frozenset({"operatrice", "administrateur"})


def _redact_finances(payload: VehicleRead | VehicleListItem, role: str) -> None:
    """Met les trois champs financiers à `None` pour tout rôle hors `_FINANCE_VISIBLE_ROLES` —
    appliquée en Python, après construction du schéma de réponse, jamais laissée à l'affichage
    front (« masquer dans l'interface ne protège rien », commentaire déjà présent dans
    `vehicle_scope.py`). Un chauffeur ou un atelier reçoit `null`, jamais la valeur réelle : le
    contrat MÊME (`prix_achat_negocie_cents`/`valeur_revente_estimee_cents` déjà nullable pour
    « pas de valeur saisie », `frais_transport_cents` rendu nullable pour ce motif) absorbe la
    rédaction sans ambiguïté observable pour ces rôles, qui n'ont de toute façon jamais accès à
    la valeur réelle pour distinguer les deux cas."""
    if role in _FINANCE_VISIBLE_ROLES:
        return
    payload.prix_achat_negocie_cents = None
    payload.valeur_revente_estimee_cents = None
    payload.frais_transport_cents = None


def _jsonable(value: Any) -> Any:
    """Rend une valeur (issue d'un modèle ORM ou d'un `model_dump`) sérialisable en JSONB —
    `audit_log.diff` stocke des `date`/`UUID`/`Decimal` que `json.dumps` ne sait pas convertir
    nativement."""
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, dt.date | dt.datetime):
        return value.isoformat()
    if isinstance(value, UUID | Decimal):
        return str(value)
    return value


@router.post("/duplicate-check", response_model=DuplicateCheckResponse)
def duplicate_check(
    payload: VehicleCreate,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_roles(*_WRITE_ROLES)),
) -> DuplicateCheckResponse:
    result = run_duplicate_check(db, payload)
    return DuplicateCheckResponse(
        exact=result["exact"],
        probable=[DuplicateCandidate(**c) for c in result["probable"]],
        similar=[DuplicateCandidate(**c) for c in result["similar"]],
    )


@router.post("", response_model=VehicleRead, status_code=201)
def create(
    payload: VehicleCreate,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_roles(*_WRITE_ROLES)),
) -> Vehicle:
    return create_vehicle(db, payload, user)


@router.get("", response_model=Page[VehicleListItem])
def list_vehicles(
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
    params: PageParams = Depends(page_params),
    state: str | None = None,
    company_id: UUID | None = None,
    marque: str | None = None,
    created_by_id: UUID | None = None,
    date_proposition_from: dt.date | None = None,
    date_proposition_to: dt.date | None = None,
    q: str | None = None,
    sort: str = "-date_proposition",
) -> Page[VehicleListItem]:
    # `joinedload` (une jointure) plutôt que le lazy load par défaut : sans lui, sérialiser
    # `VehicleListItem.company` déclencherait une requête par ligne (revue § 🟠 « N+1 sur la
    # liste de suivi »). `state_history` n'est délibérément pas chargé ici (non affiché, non
    # exposé par `VehicleListItem`).
    stmt = select(Vehicle).options(joinedload(Vehicle.company))
    stmt = scope_vehicles(stmt, user)

    if state:
        stmt = stmt.where(Vehicle.state == state)
    if company_id:
        stmt = stmt.where(Vehicle.company_id == company_id)
    if marque:
        stmt = stmt.where(Vehicle.marque.ilike(f"%{marque}%"))
    if created_by_id:
        stmt = stmt.where(Vehicle.created_by_id == created_by_id)
    if date_proposition_from:
        stmt = stmt.where(Vehicle.date_proposition >= date_proposition_from)
    if date_proposition_to:
        stmt = stmt.where(Vehicle.date_proposition <= date_proposition_to)
    if q:
        # « recherche libre sur référence / immat / VIN / modèle / société » (plan.md § 3.5).
        like = f"%{q}%"
        stmt = stmt.join(Company, Company.id == Vehicle.company_id).where(
            Vehicle.reference.ilike(like)
            | Vehicle.immatriculation.ilike(like)
            | Vehicle.vin.ilike(like)
            | Vehicle.modele.ilike(like)
            | Company.denomination.ilike(like)
        )

    sort_columns = {
        "date_proposition": Vehicle.date_proposition,
        "created_at": Vehicle.created_at,
        "reference": Vehicle.reference,
        "state": Vehicle.state,
    }
    sort_key = sort.lstrip("-")
    column = sort_columns.get(sort_key, Vehicle.date_proposition)
    stmt = stmt.order_by(column.desc() if sort.startswith("-") else column.asc())

    items, total = paginate(db, stmt, params)
    read_items = [VehicleListItem.model_validate(i) for i in items]
    for item in read_items:
        _redact_finances(item, user.role)
    return Page[VehicleListItem](
        items=read_items,
        total=total,
        limit=params.limit,
        offset=params.offset,
    )


@router.get("/pipeline-counts", response_model=PipelineCountsResponse)
def pipeline_counts(
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_roles("administrateur")),
) -> PipelineCountsResponse:
    """Kanban administrateur (brief J3) — nombre de véhicules par état, tous les 11 états
    représentés même à zéro (une colonne vide reste une colonne). **Doit être déclaré avant**
    `GET /vehicles/{vehicle_id}` dans ce routeur : sans quoi FastAPI tenterait de parser
    `"pipeline-counts"` comme un UUID de véhicule.

    Lecture strictement opérationnelle (`vehicle` en direct, jamais un mart) : contrairement au
    dashboard analytique, un Kanban est une vue **interactive** dont l'état doit refléter la
    dernière transition, pas la dernière fenêtre de rafraîchissement (plan.md § 3.7 : la règle
    « le dashboard lit les marts » vise les indicateurs de pilotage, pas cet écran opérationnel).
    """
    rows = db.execute(
        scope_vehicles(select(Vehicle.state, func.count()).group_by(Vehicle.state), user)
    ).all()
    counts_by_state: dict[str, int] = {row[0]: row[1] for row in rows}
    return PipelineCountsResponse(
        counts=[
            PipelineStateCount(state=s.value, count=counts_by_state.get(s.value, 0))
            for s in VehicleState
        ]
    )


def _get_scoped_vehicle(db: Session, vehicle_id: UUID, user: AppUser) -> Vehicle:
    # `company` (jointure) et `state_history` (requête séparée, IN unique) chargés en une fois :
    # un accès mono-véhicule, jamais de N+1 ici (contrairement à la liste — voir `list_vehicles`).
    stmt = scope_vehicles(select(Vehicle).where(Vehicle.id == vehicle_id), user).options(
        joinedload(Vehicle.company), selectinload(Vehicle.state_history)
    )
    vehicle = db.scalar(stmt)
    if vehicle is None:
        raise ApiError("not_found", "Véhicule introuvable.")
    return vehicle


@router.get("/{vehicle_id}", response_model=VehicleRead)
def get_vehicle(
    vehicle_id: UUID, db: Session = Depends(get_db), user: AppUser = Depends(get_current_user)
) -> VehicleRead:
    vehicle = _get_scoped_vehicle(db, vehicle_id, user)
    read_vehicle = VehicleRead.model_validate(vehicle)
    _redact_finances(read_vehicle, user.role)
    return read_vehicle


@router.patch("/{vehicle_id}", response_model=VehicleRead)
def patch_vehicle(
    vehicle_id: UUID,
    payload: VehiclePatch,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_roles(*_WRITE_ROLES)),
) -> Vehicle:
    vehicle = _get_scoped_vehicle(db, vehicle_id, user)
    if user.role == UserRole.OPERATRICE.value and vehicle.created_by_id != user.id:
        raise ApiError("forbidden_role", "Vous ne pouvez modifier que vos propres fiches.")

    # `force_update` est un drapeau de contrôle (comme `VehicleCreate.force_create`), pas un
    # champ du véhicule : exclu explicitement, sinon `setattr(vehicle, "force_update", ...)`
    # échoue (`AttributeError`, bug réel révélé par
    # `test_patch_force_update_bypasses_dedup_block`).
    updates = payload.model_dump(exclude_unset=True, exclude={"force_update"})
    before = {field: getattr(vehicle, field) for field in updates}
    for field, value in updates.items():
        setattr(vehicle, field, value)

    if any(f in updates for f in ("marque", "modele", "version")):
        vehicle.modele_normalise = normalize_modele(vehicle.marque, vehicle.modele, vehicle.version)
    if "vin" in updates:
        vehicle.vin_normalise = normalize_vin(vehicle.vin)
    if "immatriculation" in updates:
        vehicle.immat_normalisee = normalize_immatriculation(vehicle.immatriculation)

    # Rejoue le contrôle de doublon exact — sans ceci, corriger l'immatriculation d'une fiche
    # vers une valeur déjà prise remonte en 500 brut plutôt qu'en 409 duplicate_exact propre
    # (revue § 🟠). Le handler IntegrityError global (core/errors.py) reste le filet en cas de
    # collision concurrente réelle entre ce contrôle et le commit.
    if "vin" in updates or "immatriculation" in updates:
        exact_result = check_exact_duplicate(
            db, vehicle.vin_normalise, vehicle.immat_normalisee, exclude_vehicle_id=vehicle.id
        )
        if exact_result is not None:
            exact, champ = exact_result
            raise ApiError(
                "duplicate_exact",
                f"Ce {champ} existe déjà.",
                details={
                    "champ": champ,
                    "vehicle_id": str(exact.id),
                    "reference": exact.reference,
                },
            )

    # Rejoue le dédoublonnage approximatif si un champ qui pèse dans le score change — sinon
    # `exclude_vehicle_id`/le filtre `duplicate_review` restent du code mort qu'aucun appelant
    # n'atteint jamais (revue § 🟠). Un verdict `not_duplicate` déjà arbitré pour cette paire
    # n'est jamais reproposé (`run_duplicate_check` filtre sur `exclude_vehicle_id`).
    _DEDUP_RELEVANT_FIELDS = {
        "marque",
        "modele",
        "version",
        "energie",
        "kilometrage",
        "date_proposition",
    }
    if not payload.force_update and _DEDUP_RELEVANT_FIELDS & updates.keys():
        draft = VehicleDraftIn(
            company_id=vehicle.company_id,
            intake_batch_id=vehicle.intake_batch_id,
            marque=vehicle.marque,
            modele=vehicle.modele,
            version=vehicle.version,
            energie=vehicle.energie,
            boite=vehicle.boite,
            couleur=vehicle.couleur,
            vin=vehicle.vin,
            immatriculation=vehicle.immatriculation,
            date_mise_en_circulation=vehicle.date_mise_en_circulation,
            kilometrage=vehicle.kilometrage,
            date_proposition=vehicle.date_proposition,
        )
        check = run_duplicate_check(db, draft, exclude_vehicle_id=vehicle.id)
        if check["probable"]:
            raise ApiError(
                "duplicate_probable",
                "Cette correction rapproche la fiche d'un véhicule très proche existant — "
                "vérifiez avant de continuer.",
                details=check,
            )

    write_audit_log(
        db,
        entity_type="vehicle",
        entity_id=vehicle.id,
        action="patch",
        actor_id=user.id,
        actor_role=user.role,
        diff={"before": _jsonable(before), "after": _jsonable(updates)},
    )

    db.commit()
    db.refresh(vehicle)
    return vehicle


@router.get("/{vehicle_id}/transitions", response_model=AllowedTransitionsResponse)
def get_allowed_transitions(
    vehicle_id: UUID, db: Session = Depends(get_db), user: AppUser = Depends(get_current_user)
) -> AllowedTransitionsResponse:
    vehicle = _get_scoped_vehicle(db, vehicle_id, user)
    ctx = build_transition_context(db, vehicle, user, {})
    options = allowed_transitions(VehicleState(vehicle.state), ctx)
    return AllowedTransitionsResponse(
        allowed=[
            TransitionOptionRead(
                to_state=opt.to_state.value,
                label=opt.label,
                requires_reason=opt.requires_reason,
                requires_payload_fields=list(opt.requires_payload_fields),
            )
            for opt in options
        ]
    )


@router.post("/{vehicle_id}/transitions", response_model=VehicleRead)
def post_transition(
    vehicle_id: UUID,
    payload: TransitionRequest,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> VehicleRead:
    vehicle = _get_scoped_vehicle(db, vehicle_id, user)
    updated = transition_vehicle(
        db, vehicle, payload.to_state, user, payload.reason, payload.payload
    )
    read_vehicle = VehicleRead.model_validate(updated)
    _redact_finances(read_vehicle, user.role)
    return read_vehicle
