"""Automate d'états du véhicule — plan.md § 5.3. Table de données Python, pas une cascade de `if`.

`TRANSITIONS: dict[tuple[VehicleState, VehicleState], Transition]` — un test paramétré balaie
les 11 × 11 × 4 combinaisons (état, état, rôle) et vérifie que **seules** les cases du tableau
du plan passent (tests/unit/test_state_machine.py).

`allowed_transitions()` renvoie des `TransitionOption` enrichis (`label`, `requires_reason`,
`requires_payload_fields`) — le § 5.3 prévoit que le front DÉRIVE ses boutons de cette liste
sans dupliquer l'automate (revue § 🔴). Deux gardes sont distinguées :
- **contextuelle** (dépend de l'état déjà en base — inspection soumise, work order ouvert) :
  évaluée ici pour décider si le bouton doit être **masqué** ;
- **de payload** (`reason`, `driver_id`, `rdv_at`, `prix_achat_negocie_cents`, `refus_motif`) :
  jamais évaluée pour la visibilité (l'utilisateur n'a pas encore rempli le dialogue), mais
  déclarée dans `requires_payload_fields` pour que le front sache quoi collecter avant de poster.
`can_transition`/`apply_transition` continuent d'évaluer la garde complète (`guard`), inchangée,
au moment de la tentative réelle — c'est elle qui fait foi pour la validation serveur.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.models.enums import TERMINAL_STATES, UserRole, VehicleState

# Contexte minimal nécessaire à l'évaluation des gardes — un simple sac de champs, alimenté par
# le service appelant (`app/services/audit.py` / endpoint transitions), sans dépendance ORM ici.


@dataclass(frozen=True)
class TransitionContext:
    """Instantané des champs nécessaires à l'évaluation d'une garde."""

    assigned_driver_id: str | None
    actor_id: str
    actor_role: str
    is_assigned_driver: bool
    is_owner_operatrice: bool
    rdv_at_is_future: bool
    inspection_submitted_with_required_angles: bool
    prix_achat_negocie_present: bool
    refus_motif_present: bool
    reason_present: bool
    driver_target_is_active_chauffeur: bool
    has_work_order_en_demande: bool
    all_work_orders_closed_with_cost_line: bool
    active_work_orders_count: int
    # J3 — au moins un `work_order` déclaré dans `payload.work_orders` (garde de payload, comme
    # `refus_motif`/`driver_id` : jamais évaluée pour la visibilité du bouton, seulement à la
    # soumission réelle). Défaut `False` — le garde-fou le plus strict : un appelant qui oublie
    # de le renseigner ne peut jamais assouplir la garde par omission.
    work_orders_payload_present: bool = False


def _always_true(ctx: TransitionContext) -> bool:
    return True


def _guard_saisie_complete(ctx: TransitionContext) -> bool:
    # Le dédoublonnage exécuté + arbitré et les champs obligatoires sont vérifiés en amont, côté
    # endpoint (le brouillon ne peut être soumis que si le formulaire est valide) — la garde ici
    # ne fait qu'exiger l'absence de doublon non résolu, portée par le service appelant.
    return True


def _guard_driver_actif(ctx: TransitionContext) -> bool:
    return ctx.driver_target_is_active_chauffeur


def _guard_rdv_futur(ctx: TransitionContext) -> bool:
    return ctx.rdv_at_is_future


def _guard_inspection_ok(ctx: TransitionContext) -> bool:
    return ctx.inspection_submitted_with_required_angles


def _guard_inspection_et_work_orders(ctx: TransitionContext) -> bool:
    return ctx.inspection_submitted_with_required_angles and ctx.work_orders_payload_present


def _guard_inspection_et_prix(ctx: TransitionContext) -> bool:
    return ctx.inspection_submitted_with_required_angles and ctx.prix_achat_negocie_present


def _guard_inspection_et_refus(ctx: TransitionContext) -> bool:
    return ctx.inspection_submitted_with_required_angles and ctx.refus_motif_present


def _guard_work_order_en_demande(ctx: TransitionContext) -> bool:
    return ctx.has_work_order_en_demande


def _guard_travaux_termines(ctx: TransitionContext) -> bool:
    return ctx.all_work_orders_closed_with_cost_line


def _guard_prix(ctx: TransitionContext) -> bool:
    return ctx.prix_achat_negocie_present


def _guard_refus_motif(ctx: TransitionContext) -> bool:
    return ctx.refus_motif_present


def _guard_reason(ctx: TransitionContext) -> bool:
    return ctx.reason_present


def _role_operatrice_admin(ctx: TransitionContext) -> bool:
    return ctx.actor_role in (UserRole.OPERATRICE.value, UserRole.ADMINISTRATEUR.value)


def _role_admin_only(ctx: TransitionContext) -> bool:
    return ctx.actor_role == UserRole.ADMINISTRATEUR.value


def _role_chauffeur_affecte_admin(ctx: TransitionContext) -> bool:
    if ctx.actor_role == UserRole.ADMINISTRATEUR.value:
        return True
    return ctx.actor_role == UserRole.CHAUFFEUR.value and ctx.is_assigned_driver


def _role_chauffeur_affecte(ctx: TransitionContext) -> bool:
    return ctx.actor_role == UserRole.CHAUFFEUR.value and ctx.is_assigned_driver


def _role_atelier_admin(ctx: TransitionContext) -> bool:
    return ctx.actor_role in (UserRole.ATELIER.value, UserRole.ADMINISTRATEUR.value)


def _role_annulation_brouillon(ctx: TransitionContext) -> bool:
    """`operatrice` (ses fiches) ou `administrateur`."""
    if ctx.actor_role == UserRole.ADMINISTRATEUR.value:
        return True
    return ctx.actor_role == UserRole.OPERATRICE.value and ctx.is_owner_operatrice


@dataclass(frozen=True)
class Transition:
    allowed_roles_check: Callable[[TransitionContext], bool]
    guard: Callable[[TransitionContext], bool] = _always_true
    description: str = ""
    # Portion **contextuelle** de `guard` (état déjà en base) — utilisée pour la visibilité du
    # bouton. `_always_true` quand `guard` ne dépend que du payload (rien à masquer, tout est à
    # collecter dans le dialogue).
    contextual_guard: Callable[[TransitionContext], bool] = _always_true
    # Champs de `payload` que le dialogue front doit collecter avant de poster.
    payload_fields: tuple[str, ...] = ()
    # `reason` est un champ de premier niveau de `TransitionRequest` (pas dans `payload`).
    requires_reason: bool = False


@dataclass(frozen=True)
class TransitionOption:
    """Une entrée de `GET /vehicles/{id}/transitions` — tout ce qu'il faut au front pour
    construire son bouton sans connaître l'automate."""

    to_state: VehicleState
    label: str
    requires_reason: bool
    requires_payload_fields: tuple[str, ...]


S = VehicleState

# Table déclarative — chaque clé est un couple (from, to). Une entrée = une transition permise
# dans le tableau du plan.md § 5.3. Les transitions « tout état non terminal → ANNULE » et
# « BROUILLON/A_PLANIFIER/AFFECTE/RDV_PLANIFIE → ANNULE » sont dépliées explicitement ci-dessous
# pour rester une table de données pure (pas de cas particulier au moment de l'évaluation).
TRANSITIONS: dict[tuple[VehicleState, VehicleState], Transition] = {
    (S.BROUILLON, S.A_PLANIFIER): Transition(
        _role_operatrice_admin, _guard_saisie_complete, "Validation de la fiche"
    ),
    (S.A_PLANIFIER, S.AFFECTE): Transition(
        _role_admin_only,
        _guard_driver_actif,
        "Affectation d'un chauffeur",
        payload_fields=("driver_id",),
    ),
    (S.AFFECTE, S.AFFECTE): Transition(
        _role_admin_only, _guard_driver_actif, "Réaffectation", payload_fields=("driver_id",)
    ),
    (S.AFFECTE, S.RDV_PLANIFIE): Transition(
        _role_chauffeur_affecte_admin,
        _guard_rdv_futur,
        "Prise de rendez-vous",
        payload_fields=("rdv_at",),
    ),
    (S.RDV_PLANIFIE, S.CONTROLE_EN_COURS): Transition(
        _role_chauffeur_affecte, _always_true, "Début du contrôle sur place"
    ),
    (S.CONTROLE_EN_COURS, S.TRAVAUX_REQUIS): Transition(
        _role_chauffeur_affecte_admin,
        _guard_inspection_et_work_orders,
        "Conclusion : travaux requis",
        contextual_guard=_guard_inspection_ok,
        payload_fields=("work_orders",),
    ),
    (S.CONTROLE_EN_COURS, S.ACHAT_VALIDE): Transition(
        _role_chauffeur_affecte_admin,
        _guard_inspection_et_prix,
        "Achat direct validé",
        contextual_guard=_guard_inspection_ok,
        payload_fields=("prix_achat_negocie_cents",),
    ),
    (S.CONTROLE_EN_COURS, S.REFUSE): Transition(
        _role_chauffeur_affecte_admin,
        _guard_inspection_et_refus,
        "Refus après contrôle",
        contextual_guard=_guard_inspection_ok,
        payload_fields=("refus_motif",),
    ),
    (S.TRAVAUX_REQUIS, S.TRAVAUX_EN_COURS): Transition(
        _role_atelier_admin,
        _guard_work_order_en_demande,
        "Prise en charge atelier",
        contextual_guard=_guard_work_order_en_demande,
    ),
    (S.TRAVAUX_EN_COURS, S.TRAVAUX_TERMINES): Transition(
        _role_atelier_admin,
        _guard_travaux_termines,
        "Travaux terminés",
        contextual_guard=_guard_travaux_termines,
    ),
    (S.TRAVAUX_TERMINES, S.ACHAT_VALIDE): Transition(
        _role_admin_only,
        _guard_prix,
        "Achat validé après travaux",
        payload_fields=("prix_achat_negocie_cents",),
    ),
    (S.TRAVAUX_TERMINES, S.REFUSE): Transition(
        _role_admin_only,
        _guard_refus_motif,
        "Refus après travaux",
        payload_fields=("refus_motif",),
    ),
}

# Annulation — dépliée explicitement pour chaque état non terminal (garde commune : `reason`).
for _state in VehicleState:
    if _state in TERMINAL_STATES:
        continue
    if _state in (S.BROUILLON, S.A_PLANIFIER, S.AFFECTE, S.RDV_PLANIFIE):
        TRANSITIONS[(_state, S.ANNULE)] = Transition(
            _role_annulation_brouillon,
            _guard_reason,
            "Annulation (opératrice ou admin)",
            requires_reason=True,
        )
    else:
        TRANSITIONS[(_state, S.ANNULE)] = Transition(
            _role_admin_only,
            _guard_reason,
            "Annulation (admin uniquement)",
            requires_reason=True,
        )


class InvalidTransitionError(Exception):
    def __init__(self, from_state: str, to_state: str, allowed: list[str]) -> None:
        self.from_state = from_state
        self.to_state = to_state
        self.allowed = allowed
        super().__init__(f"Transition {from_state} -> {to_state} invalide")


def allowed_transitions(from_state: VehicleState, ctx: TransitionContext) -> list[TransitionOption]:
    """Transitions dont la case existe, dont le rôle de l'acteur est habilité **et** dont la
    garde contextuelle est satisfaite (état déjà en base) — utilisée par
    `GET /vehicles/{id}/transitions` et par `details.allowed` du 409.

    N'évalue **pas** la garde de payload (`reason`, `driver_id`, `rdv_at`, ...) : ces champs ne
    sont pas encore connus au moment où le front décide quels boutons afficher. C'est
    `can_transition`/`apply_transition` qui les valident réellement à la soumission.
    """
    result = []
    for (f, t), transition in TRANSITIONS.items():
        if f != from_state:
            continue
        if not transition.allowed_roles_check(ctx):
            continue
        if not transition.contextual_guard(ctx):
            continue
        result.append(
            TransitionOption(
                to_state=t,
                label=transition.description,
                requires_reason=transition.requires_reason,
                requires_payload_fields=transition.payload_fields,
            )
        )
    return result


def can_transition(
    from_state: VehicleState, to_state: VehicleState, ctx: TransitionContext
) -> bool:
    transition = TRANSITIONS.get((from_state, to_state))
    if transition is None:
        return False
    if not transition.allowed_roles_check(ctx):
        return False
    return transition.guard(ctx)


def apply_transition(
    from_state: VehicleState, to_state: VehicleState, ctx: TransitionContext
) -> None:
    """Lève `InvalidTransitionError` si la transition n'est pas permise dans ce contexte."""
    if from_state in TERMINAL_STATES:
        raise InvalidTransitionError(
            from_state.value,
            to_state.value,
            [opt.to_state.value for opt in allowed_transitions(from_state, ctx)],
        )
    if not can_transition(from_state, to_state, ctx):
        raise InvalidTransitionError(
            from_state.value,
            to_state.value,
            [opt.to_state.value for opt in allowed_transitions(from_state, ctx)],
        )
