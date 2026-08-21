"""Service atelier — création des `work_order` (effet de `CONTROLE_EN_COURS -> TRAVAUX_REQUIS`,
plan.md § 5.3), mini-automate de leur propre `state` et lignes de coût réel (plan.md § 5.1, J3).

`work_order.state` (`demande|en_cours|termine|annule`) est un automate **séparé** de celui du
véhicule (`app/services/state_machine.py`) : un ordre de travaux se clôture indépendamment des
autres (« chaque ordre terminé ou annulé doit porter au moins une ligne de coût », brief J3),
alors que c'est `build_transition_context` (`app/services/vehicles.py`) qui vérifie, lui, que
**tous** les ordres du véhicule sont clos avant d'autoriser `TRAVAUX_EN_COURS -> TRAVAUX_TERMINES`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.enums import WorkOrderLineCategorie, WorkOrderState, WorkOrderType
from app.models.user import AppUser
from app.models.vehicle import Vehicle
from app.models.work_order import WorkOrder, WorkOrderLine

# États terminaux de `work_order` — miroir de la garde brief J3 « chaque ordre terminé ou
# annulé doit porter au moins une ligne de coût ».
_CLOSED_WORK_ORDER_STATES = (WorkOrderState.TERMINE.value, WorkOrderState.ANNULE.value)

# Mini-automate déclaratif de `work_order.state` — même esprit que `state_machine.py` (une table
# de données plutôt qu'une cascade de `if`), à l'échelle d'un ordre de travaux.
_WORK_ORDER_TRANSITIONS: dict[str, tuple[str, ...]] = {
    WorkOrderState.DEMANDE.value: (WorkOrderState.EN_COURS.value, WorkOrderState.ANNULE.value),
    WorkOrderState.EN_COURS.value: (WorkOrderState.TERMINE.value, WorkOrderState.ANNULE.value),
    WorkOrderState.TERMINE.value: (),
    WorkOrderState.ANNULE.value: (),
}


def parse_work_orders_payload(raw: object) -> list[dict]:
    """Valide `payload.work_orders` (effet de `CONTROLE_EN_COURS -> TRAVAUX_REQUIS`) — au moins
    une entrée, chacune avec un `type` connu et une `description` non vide. Lève `ApiError
    validation_error` (jamais un 500 brut) sur une forme invalide : `payload` est un dict client
    libre (même piège que `_parse_iso_datetime_field`, `app/services/vehicles.py`)."""
    if not isinstance(raw, list) or not raw:
        raise ApiError(
            "validation_error",
            "payload.work_orders doit contenir au moins un ordre de travaux.",
        )
    parsed = []
    valid_types = {t.value for t in WorkOrderType}
    for entry in raw:
        if not isinstance(entry, dict):
            raise ApiError(
                "validation_error", "Chaque entrée de payload.work_orders doit être un objet."
            )
        wo_type = entry.get("type")
        description = entry.get("description")
        if wo_type not in valid_types:
            raise ApiError("validation_error", f"Type de travaux inconnu : {wo_type!r}.")
        if not isinstance(description, str) or not description.strip():
            raise ApiError(
                "validation_error", "Chaque ordre de travaux doit porter une description."
            )
        montant = entry.get("montant_estime_cents")
        if montant is not None and (not isinstance(montant, int) or montant < 0):
            raise ApiError(
                "validation_error", "montant_estime_cents doit être un entier positif ou nul."
            )
        parsed.append(
            {"type": wo_type, "description": description.strip(), "montant_estime_cents": montant}
        )
    return parsed


def create_work_orders(
    db: Session, vehicle: Vehicle, entries: list[dict], user: AppUser
) -> list[WorkOrder]:
    """Effet de `CONTROLE_EN_COURS -> TRAVAUX_REQUIS` — la transition elle-même a déjà validé la
    garde (`payload.work_orders` non vide) avant d'appeler cette fonction ; `entries` est donc
    supposé déjà passé par `parse_work_orders_payload`."""
    created = []
    for entry in entries:
        work_order = WorkOrder(
            id=uuid4(),
            vehicle_id=vehicle.id,
            type=entry["type"],
            state=WorkOrderState.DEMANDE.value,
            description=entry["description"],
            montant_estime_cents=entry.get("montant_estime_cents"),
            created_by_id=user.id,
            requested_at=datetime.now(UTC),
        )
        db.add(work_order)
        created.append(work_order)
    db.flush()
    return created


def has_cost_line(db: Session, work_order_id: UUID) -> bool:
    return bool(
        db.scalar(
            select(func.count())
            .select_from(WorkOrderLine)
            .where(WorkOrderLine.work_order_id == work_order_id)
        )
    )


def update_work_order_state(
    db: Session, work_order: WorkOrder, to_state: str, user: AppUser
) -> WorkOrder:
    """Applique le mini-automate de `work_order.state`. Garde brief J3, non négociable : un ordre
    ne peut atteindre `termine`/`annule` que s'il porte déjà au moins une ligne de coût — la
    ligne doit donc avoir été postée *avant* cet appel (`POST /work-orders/{id}/lines`)."""
    allowed = _WORK_ORDER_TRANSITIONS.get(work_order.state, ())
    if to_state not in allowed:
        raise ApiError(
            "invalid_transition",
            f"Transition {work_order.state} -> {to_state} invalide pour cet ordre de travaux.",
            details={"allowed": list(allowed)},
        )
    if to_state in _CLOSED_WORK_ORDER_STATES and not has_cost_line(db, work_order.id):
        raise ApiError(
            "conflict",
            "Un ordre de travaux terminé ou annulé doit porter au moins une ligne de coût.",
            details={"work_order_id": str(work_order.id)},
        )

    work_order.state = to_state
    if to_state == WorkOrderState.EN_COURS.value and work_order.started_at is None:
        work_order.started_at = datetime.now(UTC)
    if to_state in _CLOSED_WORK_ORDER_STATES:
        work_order.completed_at = datetime.now(UTC)
    db.flush()
    return work_order


def create_work_order_line(
    db: Session,
    work_order: WorkOrder,
    *,
    libelle: str,
    categorie: str,
    quantite,
    prix_unitaire_cents: int,
) -> WorkOrderLine:
    if categorie not in {c.value for c in WorkOrderLineCategorie}:
        raise ApiError("validation_error", "Catégorie de ligne de coût inconnue.")
    if work_order.state in _CLOSED_WORK_ORDER_STATES:
        raise ApiError(
            "conflict", "Cet ordre de travaux est déjà clos, il n'accepte plus de nouvelle ligne."
        )
    line = WorkOrderLine(
        id=uuid4(),
        work_order_id=work_order.id,
        libelle=libelle,
        categorie=categorie,
        quantite=quantite,
        prix_unitaire_cents=prix_unitaire_cents,
    )
    db.add(line)
    db.flush()
    db.refresh(line)  # `montant_cents` est une colonne GENERATED, calculée côté base
    return line
