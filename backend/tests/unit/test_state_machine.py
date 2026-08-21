"""Balayage complet de l'automate d'états — plan.md § 5.3 / § 8 : pour chaque (état, état, rôle),
la transition passe si et seulement si elle figure dans le tableau du plan.
"""

from __future__ import annotations

import itertools

import pytest

from app.models.enums import TERMINAL_STATES, UserRole, VehicleState
from app.services.state_machine import (
    TRANSITIONS,
    InvalidTransitionError,
    TransitionContext,
    apply_transition,
    can_transition,
)


def _permissive_context(role: UserRole) -> TransitionContext:
    """Contexte où toutes les gardes métier sont satisfaites — isole le cloisonnement de rôle."""
    return TransitionContext(
        assigned_driver_id="driver-1",
        actor_id="actor-1",
        actor_role=role.value,
        is_assigned_driver=(role == UserRole.CHAUFFEUR),
        is_owner_operatrice=(role == UserRole.OPERATRICE),
        rdv_at_is_future=True,
        inspection_submitted_with_required_angles=True,
        prix_achat_negocie_present=True,
        refus_motif_present=True,
        reason_present=True,
        driver_target_is_active_chauffeur=True,
        has_work_order_en_demande=True,
        all_work_orders_closed_with_cost_line=True,
        active_work_orders_count=1,
        work_orders_payload_present=True,
    )


ALL_COMBINATIONS = list(itertools.product(VehicleState, VehicleState, UserRole))


@pytest.mark.parametrize(
    "from_state,to_state,role",
    ALL_COMBINATIONS,
    ids=[f"{f.value}->{t.value}:{r.value}" for f, t, r in ALL_COMBINATIONS],
)
def test_exhaustive_sweep_matches_declared_table(
    from_state: VehicleState, to_state: VehicleState, role: UserRole
) -> None:
    ctx = _permissive_context(role)
    transition = TRANSITIONS.get((from_state, to_state))
    expected = transition is not None and transition.allowed_roles_check(ctx)

    actual = can_transition(from_state, to_state, ctx)
    assert actual == expected, (
        f"{from_state.value} -> {to_state.value} pour {role.value} : "
        f"attendu={expected}, obtenu={actual}"
    )


def test_terminal_states_have_no_outgoing_transition() -> None:
    for state in TERMINAL_STATES:
        outgoing = [(f, t) for (f, t) in TRANSITIONS if f == state]
        assert outgoing == [], f"{state.value} est terminal mais a des transitions sortantes"


def test_terminal_state_raises_on_any_attempt() -> None:
    ctx = _permissive_context(UserRole.ADMINISTRATEUR)
    for state in TERMINAL_STATES:
        with pytest.raises(InvalidTransitionError):
            apply_transition(state, VehicleState.BROUILLON, ctx)


@pytest.mark.parametrize(
    "from_state,to_state,allowed_roles",
    [
        (
            VehicleState.BROUILLON,
            VehicleState.A_PLANIFIER,
            {UserRole.OPERATRICE, UserRole.ADMINISTRATEUR},
        ),
        (VehicleState.A_PLANIFIER, VehicleState.AFFECTE, {UserRole.ADMINISTRATEUR}),
        (VehicleState.AFFECTE, VehicleState.AFFECTE, {UserRole.ADMINISTRATEUR}),
        (
            VehicleState.AFFECTE,
            VehicleState.RDV_PLANIFIE,
            {UserRole.CHAUFFEUR, UserRole.ADMINISTRATEUR},
        ),
        (VehicleState.RDV_PLANIFIE, VehicleState.CONTROLE_EN_COURS, {UserRole.CHAUFFEUR}),
        (
            VehicleState.CONTROLE_EN_COURS,
            VehicleState.TRAVAUX_REQUIS,
            {UserRole.CHAUFFEUR, UserRole.ADMINISTRATEUR},
        ),
        (
            VehicleState.CONTROLE_EN_COURS,
            VehicleState.ACHAT_VALIDE,
            {UserRole.CHAUFFEUR, UserRole.ADMINISTRATEUR},
        ),
        (
            VehicleState.CONTROLE_EN_COURS,
            VehicleState.REFUSE,
            {UserRole.CHAUFFEUR, UserRole.ADMINISTRATEUR},
        ),
        (
            VehicleState.TRAVAUX_REQUIS,
            VehicleState.TRAVAUX_EN_COURS,
            {UserRole.ATELIER, UserRole.ADMINISTRATEUR},
        ),
        (
            VehicleState.TRAVAUX_EN_COURS,
            VehicleState.TRAVAUX_TERMINES,
            {UserRole.ATELIER, UserRole.ADMINISTRATEUR},
        ),
        (VehicleState.TRAVAUX_TERMINES, VehicleState.ACHAT_VALIDE, {UserRole.ADMINISTRATEUR}),
        (VehicleState.TRAVAUX_TERMINES, VehicleState.REFUSE, {UserRole.ADMINISTRATEUR}),
    ],
)
def test_declared_transition_role_set_matches_plan(
    from_state: VehicleState, to_state: VehicleState, allowed_roles: set[UserRole]
) -> None:
    for role in UserRole:
        ctx = _permissive_context(role)
        expected = role in allowed_roles
        actual = can_transition(from_state, to_state, ctx)
        assert actual == expected, f"{from_state.value}->{to_state.value} rôle {role.value}"


@pytest.mark.parametrize(
    "state",
    [
        VehicleState.BROUILLON,
        VehicleState.A_PLANIFIER,
        VehicleState.AFFECTE,
        VehicleState.RDV_PLANIFIE,
    ],
)
def test_operatrice_can_cancel_only_early_states_as_owner(state: VehicleState) -> None:
    ctx = _permissive_context(UserRole.OPERATRICE)
    assert can_transition(state, VehicleState.ANNULE, ctx) is True


@pytest.mark.parametrize(
    "state",
    [
        VehicleState.CONTROLE_EN_COURS,
        VehicleState.TRAVAUX_REQUIS,
        VehicleState.TRAVAUX_EN_COURS,
        VehicleState.TRAVAUX_TERMINES,
    ],
)
def test_operatrice_cannot_cancel_late_states(state: VehicleState) -> None:
    ctx = _permissive_context(UserRole.OPERATRICE)
    assert can_transition(state, VehicleState.ANNULE, ctx) is False


def test_admin_can_cancel_from_any_non_terminal_state() -> None:
    ctx = _permissive_context(UserRole.ADMINISTRATEUR)
    for state in VehicleState:
        if state in TERMINAL_STATES:
            continue
        assert can_transition(state, VehicleState.ANNULE, ctx) is True


def test_guard_blocks_transition_even_with_correct_role() -> None:
    """La garde `reason_present` bloque l'annulation, même pour un rôle habilité."""
    ctx = TransitionContext(
        assigned_driver_id=None,
        actor_id="actor-1",
        actor_role=UserRole.ADMINISTRATEUR.value,
        is_assigned_driver=False,
        is_owner_operatrice=False,
        rdv_at_is_future=True,
        inspection_submitted_with_required_angles=True,
        prix_achat_negocie_present=True,
        refus_motif_present=True,
        reason_present=False,  # <- garde manquante
        driver_target_is_active_chauffeur=True,
        has_work_order_en_demande=True,
        all_work_orders_closed_with_cost_line=True,
        active_work_orders_count=1,
    )
    assert can_transition(VehicleState.BROUILLON, VehicleState.ANNULE, ctx) is False


def test_apply_transition_raises_with_allowed_list() -> None:
    ctx = _permissive_context(UserRole.CHAUFFEUR)
    with pytest.raises(InvalidTransitionError) as excinfo:
        apply_transition(VehicleState.BROUILLON, VehicleState.ACHAT_VALIDE, ctx)
    assert VehicleState.A_PLANIFIER.value not in excinfo.value.allowed  # chauffeur non habilité ici
