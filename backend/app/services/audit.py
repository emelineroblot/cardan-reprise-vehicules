"""Écriture `audit_log` + `vehicle_state_transition` — plan.md § 5.3.

Toute transition écrit les deux lignes dans la même transaction SQL que le changement d'état.
Pas de trace = pas de délai de cycle en J3.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.vehicle import VehicleStateTransition


def write_audit_log(
    db: Session,
    *,
    entity_type: str,
    entity_id: UUID,
    action: str,
    actor_id: UUID | None,
    actor_role: str | None,
    diff: dict[str, Any] | None = None,
) -> AuditLog:
    entry = AuditLog(
        id=uuid4(),
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor_id=actor_id,
        actor_role=actor_role,
        diff=diff,
    )
    db.add(entry)
    db.flush()
    return entry


def write_vehicle_transition(
    db: Session,
    *,
    vehicle_id: UUID,
    from_state: str | None,
    to_state: str,
    actor_id: UUID,
    actor_role: str,
    reason: str | None = None,
    payload: dict[str, Any] | None = None,
) -> VehicleStateTransition:
    """Écrit l'historique d'états **et** la ligne d'audit correspondante (même transaction)."""
    transition = VehicleStateTransition(
        id=uuid4(),
        vehicle_id=vehicle_id,
        from_state=from_state,
        to_state=to_state,
        actor_id=actor_id,
        actor_role=actor_role,
        reason=reason,
        payload=payload,
    )
    db.add(transition)

    write_audit_log(
        db,
        entity_type="vehicle",
        entity_id=vehicle_id,
        action="state_transition",
        actor_id=actor_id,
        actor_role=actor_role,
        diff={"from_state": from_state, "to_state": to_state, "reason": reason},
    )
    db.flush()
    return transition
