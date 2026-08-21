"""`scope_vehicles` — étage ligne du cloisonnement (plan.md § 3.4).

Appliquée par **tous** les accès en lecture aux véhicules. Le front n'est jamais la barrière :
masquer un bouton ne protège rien.
"""

from __future__ import annotations

from sqlalchemy import exists, or_, select
from sqlalchemy.sql import Select

from app.models.enums import UserRole, VehicleState, WorkOrderState
from app.models.user import AppUser
from app.models.vehicle import Vehicle
from app.models.work_order import WorkOrder

_OPEN_WORK_ORDER_STATES = (WorkOrderState.DEMANDE.value, WorkOrderState.EN_COURS.value)

# Bug corrigé (revue dev-frontend J3, 🟠) : un véhicule sortait du périmètre atelier dès la
# clôture de son dernier `work_order` — au moment précis où `TRAVAUX_EN_COURS ->
# TRAVAUX_TERMINES` (rôle `atelier`/`administrateur`, `_role_atelier_admin`) devient
# disponible, puisque cette transition exige justement que *tous* les ordres soient clos
# (`all_work_orders_closed_with_cost_line`, `app/services/vehicles.py`). L'atelier perdait donc
# l'accès à la ressource exactement quand l'action qu'il vient de débloquer devient possible.
# `TRAVAUX_EN_COURS` est donc un second critère de visibilité, indépendant de l'état des
# `work_order` : le véhicule reste visible pour l'atelier tant qu'il est dans cet état, qu'il
# porte encore un ordre ouvert ou non.
_ATELIER_VISIBLE_VEHICLE_STATES = (VehicleState.TRAVAUX_EN_COURS.value,)


def scope_vehicles(stmt: Select, user: AppUser) -> Select:
    """Restreint `stmt` (qui doit porter sur `Vehicle`) selon le rôle de `user`.

    - `chauffeur` → uniquement les véhicules qui lui sont affectés (mission active).
    - `atelier` → les véhicules ayant un ordre de travaux non terminé, **ou** actuellement en
      `TRAVAUX_EN_COURS` (même sans ordre ouvert — voir commentaire ci-dessus).
    - `operatrice`, `administrateur` → tout le parc (l'écriture reste contrôlée par endpoint).
    """
    if user.role == UserRole.CHAUFFEUR.value:
        return stmt.where(Vehicle.assigned_driver_id == user.id)

    if user.role == UserRole.ATELIER.value:
        return stmt.where(
            or_(
                exists(
                    select(WorkOrder.id).where(
                        WorkOrder.vehicle_id == Vehicle.id,
                        WorkOrder.state.in_(_OPEN_WORK_ORDER_STATES),
                    )
                ),
                Vehicle.state.in_(_ATELIER_VISIBLE_VEHICLE_STATES),
            )
        )

    return stmt
