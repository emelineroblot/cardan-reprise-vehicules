"""Service missions — effets de bord de l'automate véhicule (plan.md § 5.3) et lecture pour le
chauffeur (brief J2 : « liste de ses missions, détail »).

Aucune fonction ici ne modifie `vehicle.state` : c'est
`app/services/vehicles.py::transition_vehicle` qui les appelle, une fois la transition validée
par l'automate — « un seul point d'entrée » (plan.md § 5.3) reste vrai côté véhicule ;
`mission` est un effet, jamais un déclencheur.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import MissionState
from app.models.mission import Mission
from app.models.vehicle import Vehicle

# États dans lesquels une mission n'est plus « active » — miroir de l'index unique partiel
# `uq_mission_vehicle_active` (`WHERE state NOT IN ('terminee', 'annulee')`, plan.md § 5.1).
_INACTIVE_MISSION_STATES = (MissionState.TERMINEE.value, MissionState.ANNULEE.value)


def get_active_mission(db: Session, vehicle_id: UUID) -> Mission | None:
    """Mission active courante — au plus une par véhicule, garanti en base."""
    return db.scalar(
        select(Mission).where(
            Mission.vehicle_id == vehicle_id,
            Mission.state.notin_(_INACTIVE_MISSION_STATES),
        )
    )


def create_mission(
    db: Session, vehicle: Vehicle, *, driver_id: UUID, assigned_by_id: UUID
) -> Mission:
    """Effet de `A_PLANIFIER → AFFECTE` et `AFFECTE → AFFECTE` (réaffectation) — plan.md § 5.3.
    L'appelant doit avoir annulé une éventuelle mission active existante au préalable
    (`cancel_mission`), sans quoi l'index unique partiel refuse l'insertion."""
    mission = Mission(
        id=uuid4(),
        vehicle_id=vehicle.id,
        driver_id=driver_id,
        state=MissionState.AFFECTEE.value,
        assigned_by_id=assigned_by_id,
        assigned_at=datetime.now(UTC),
    )
    db.add(mission)
    db.flush()
    return mission


def cancel_mission(db: Session, mission: Mission) -> None:
    mission.state = MissionState.ANNULEE.value
    db.flush()


def mark_rdv(
    db: Session,
    mission: Mission,
    *,
    rdv_at: datetime | None,
    rdv_adresse: str | None,
    rdv_contact_nom: str | None,
    rdv_contact_telephone: str | None,
) -> None:
    """Effet de `AFFECTE → RDV_PLANIFIE` — la garde `rdv_at` futur a déjà été validée par
    l'automate au moment où cette fonction est appelée (plan.md § 5.3)."""
    mission.state = MissionState.RDV_PLANIFIE.value
    if rdv_at is not None:
        mission.rdv_at = rdv_at
    if rdv_adresse is not None:
        mission.rdv_adresse = rdv_adresse
    if rdv_contact_nom is not None:
        mission.rdv_contact_nom = rdv_contact_nom
    if rdv_contact_telephone is not None:
        mission.rdv_contact_telephone = rdv_contact_telephone
    db.flush()


def start_control(db: Session, mission: Mission) -> None:
    """Effet de `RDV_PLANIFIE → CONTROLE_EN_COURS` — la création de l'`inspection` elle-même
    reste un acte distinct et idempotent côté client (`POST /inspections`, décision C : le
    brouillon doit pouvoir naître hors ligne), pas un effet automatique de cette transition."""
    mission.state = MissionState.EN_COURS.value
    db.flush()


def complete_mission(db: Session, mission: Mission) -> None:
    """Effet de sortie de `CONTROLE_EN_COURS` (vers `TRAVAUX_REQUIS`, `ACHAT_VALIDE` ou
    `REFUSE`) — le passage sur place du chauffeur est terminé dans les trois cas."""
    mission.state = MissionState.TERMINEE.value
    mission.completed_at = datetime.now(UTC)
    db.flush()
