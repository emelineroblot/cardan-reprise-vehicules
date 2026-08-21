"""`/vehicles/{id}/work-orders`, `/work-orders/{id}`, `/vehicles/{id}/costs` — atelier et coûts
hors atelier (plan.md § 5.1, brief J3 : « réception des ordres de travaux, saisie des coûts
réels »).

La création initiale d'un `work_order` reste un effet de `POST /vehicles/{id}/transitions`
(`CONTROLE_EN_COURS -> TRAVAUX_REQUIS`, plan.md § 5.3) : rien ici ne crée un ordre de travaux.
Ce module expose sa lecture, son propre mini-automate d'état (`demande -> en_cours ->
termine|annule`) et ses lignes de coût réel.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_roles
from app.core.errors import ApiError
from app.db.session import get_db
from app.models.enums import VehicleCostType
from app.models.user import AppUser
from app.models.vehicle import Vehicle
from app.models.vehicle_cost import VehicleCost
from app.models.work_order import WorkOrder, WorkOrderLine
from app.schemas.vehicle_cost import VehicleCostCreate, VehicleCostRead
from app.schemas.work_order import (
    WorkOrderLineCreate,
    WorkOrderLineRead,
    WorkOrderRead,
    WorkOrderStateUpdate,
)
from app.services.vehicle_scope import scope_vehicles
from app.services.work_orders import create_work_order_line, update_work_order_state

router = APIRouter()

_ATELIER_WRITE_ROLES = ("atelier", "administrateur")
# Décision d'implémentation (implementation.md § J3) : les coûts hors atelier (transport,
# carburant, administratif, remise en état externe) sont saisis par l'administration, sans rôle
# métier dédié comme l'atelier pour `work_order_line`.
_COST_WRITE_ROLES = ("administrateur",)
# Cloisonnement des données financières (revue J3, 🔴) : les ordres de travaux et leurs lignes
# de coût réel sont des données financières au même titre que `prix_achat_negocie_cents` — ce
# module les ouvrait auparavant à tout rôle authentifié (`get_current_user`), donc au chauffeur.
# Restreint aux rôles qui en ont un usage métier réel : l'atelier (son propre travail),
# l'opératrice et l'administrateur (pilotage). Le chauffeur reçoit `403 forbidden_role`, jamais
# le contenu de la réponse.
_READ_ROLES = ("atelier", "operatrice", "administrateur")


def _get_scoped_vehicle(db: Session, vehicle_id: UUID, user: AppUser) -> Vehicle:
    vehicle = db.scalar(scope_vehicles(select(Vehicle).where(Vehicle.id == vehicle_id), user))
    if vehicle is None:
        raise ApiError("not_found", "Véhicule introuvable.")
    return vehicle


def _get_work_order_for_scoped_user(db: Session, work_order_id: UUID, user: AppUser) -> WorkOrder:
    """Un `work_order` n'est accessible que via un véhicule que l'utilisateur peut voir
    (`scope_vehicles`) — même principe que `photos.py::_get_scoped_vehicle` : ne jamais
    distinguer « ordre inexistant » de « accès refusé » (fuite d'existence)."""
    work_order = db.get(WorkOrder, work_order_id)
    if work_order is None:
        raise ApiError("not_found", "Ordre de travaux introuvable.")
    _get_scoped_vehicle(db, work_order.vehicle_id, user)  # lève not_found si hors périmètre
    return work_order


@router.get("/vehicles/{vehicle_id}/work-orders", response_model=list[WorkOrderRead])
def list_vehicle_work_orders(
    vehicle_id: UUID,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_roles(*_READ_ROLES)),
) -> list[WorkOrder]:
    _get_scoped_vehicle(db, vehicle_id, user)
    stmt = (
        select(WorkOrder)
        .where(WorkOrder.vehicle_id == vehicle_id)
        .options(selectinload(WorkOrder.lines))
        .order_by(WorkOrder.requested_at)
    )
    return list(db.scalars(stmt).all())


@router.get("/work-orders/{work_order_id}", response_model=WorkOrderRead)
def get_work_order(
    work_order_id: UUID,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_roles(*_READ_ROLES)),
) -> WorkOrder:
    work_order = _get_work_order_for_scoped_user(db, work_order_id, user)
    _ = work_order.lines  # déclenche le lazy load — un seul ordre lu ici, pas de N+1
    return work_order


@router.post("/work-orders/{work_order_id}/state", response_model=WorkOrderRead)
def transition_work_order_state(
    work_order_id: UUID,
    payload: WorkOrderStateUpdate,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_roles(*_ATELIER_WRITE_ROLES)),
) -> WorkOrder:
    work_order = _get_work_order_for_scoped_user(db, work_order_id, user)
    update_work_order_state(db, work_order, payload.to_state, user)
    if payload.commentaire_atelier is not None:
        work_order.commentaire_atelier = payload.commentaire_atelier
    if payload.assigned_to_id is not None:
        work_order.assigned_to_id = payload.assigned_to_id
    db.commit()
    db.refresh(work_order)
    _ = work_order.lines
    return work_order


@router.post(
    "/work-orders/{work_order_id}/lines", response_model=WorkOrderLineRead, status_code=201
)
def add_work_order_line(
    work_order_id: UUID,
    payload: WorkOrderLineCreate,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_roles(*_ATELIER_WRITE_ROLES)),
) -> WorkOrderLine:
    work_order = _get_work_order_for_scoped_user(db, work_order_id, user)
    line = create_work_order_line(
        db,
        work_order,
        libelle=payload.libelle,
        categorie=payload.categorie,
        quantite=payload.quantite,
        prix_unitaire_cents=payload.prix_unitaire_cents,
    )
    db.commit()
    db.refresh(line)
    return line


@router.get("/vehicles/{vehicle_id}/costs", response_model=list[VehicleCostRead])
def list_vehicle_costs(
    vehicle_id: UUID,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_roles(*_READ_ROLES)),
) -> list[VehicleCost]:
    _get_scoped_vehicle(db, vehicle_id, user)
    stmt = (
        select(VehicleCost)
        .where(VehicleCost.vehicle_id == vehicle_id)
        .order_by(VehicleCost.created_at)
    )
    return list(db.scalars(stmt).all())


@router.post("/vehicles/{vehicle_id}/costs", response_model=VehicleCostRead, status_code=201)
def add_vehicle_cost(
    vehicle_id: UUID,
    payload: VehicleCostCreate,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_roles(*_COST_WRITE_ROLES)),
) -> VehicleCost:
    vehicle = _get_scoped_vehicle(db, vehicle_id, user)
    if payload.type not in {t.value for t in VehicleCostType}:
        raise ApiError("validation_error", "Type de coût inconnu.")
    cost = VehicleCost(
        vehicle_id=vehicle.id,
        type=payload.type,
        montant_cents=payload.montant_cents,
        commentaire=payload.commentaire,
        created_by_id=user.id,
    )
    db.add(cost)
    db.commit()
    db.refresh(cost)
    return cost
