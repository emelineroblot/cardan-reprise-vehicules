"""`scope_vehicles` — étage ligne du cloisonnement (plan.md § 3.4).

Appliquée par **tous** les accès en lecture aux véhicules. Le front n'est jamais la barrière :
masquer un bouton ne protège rien.
"""

from __future__ import annotations

from sqlalchemy import exists, select
from sqlalchemy.sql import Select

from app.models.enums import UserRole, WorkOrderState
from app.models.user import AppUser
from app.models.vehicle import Vehicle
from app.models.work_order import WorkOrder

_OPEN_WORK_ORDER_STATES = (WorkOrderState.DEMANDE.value, WorkOrderState.EN_COURS.value)


def scope_vehicles(stmt: Select, user: AppUser) -> Select:
    """Restreint `stmt` (qui doit porter sur `Vehicle`) selon le rôle de `user`.

    - `chauffeur` → uniquement les véhicules qui lui sont affectés (mission active).
    - `atelier` → uniquement les véhicules ayant un ordre de travaux non terminé.
    - `operatrice`, `administrateur` → tout le parc (l'écriture reste contrôlée par endpoint).
    """
    if user.role == UserRole.CHAUFFEUR.value:
        return stmt.where(Vehicle.assigned_driver_id == user.id)

    if user.role == UserRole.ATELIER.value:
        return stmt.where(
            exists(
                select(WorkOrder.id).where(
                    WorkOrder.vehicle_id == Vehicle.id,
                    WorkOrder.state.in_(_OPEN_WORK_ORDER_STATES),
                )
            )
        )

    return stmt
