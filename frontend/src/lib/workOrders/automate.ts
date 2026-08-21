import type { WorkOrderState } from "@/lib/api/types";

/**
 * Cibles permises du mini-automate `work_order.state` (implementation.md § J3 Backend,
 * `app/services/work_orders.py::_WORK_ORDER_TRANSITIONS`) : `demande → en_cours|annule`,
 * `en_cours → termine|annule`, aucune sortie de `termine`/`annule` (états terminaux).
 *
 * ⚠️ Contrairement à l'automate véhicule, **aucun endpoint `GET .../transitions` n'expose ce
 * sous-automate côté backend** (contrat J3 relu explicitement) : cette table est donc la seule
 * source côté front, à tenir strictement synchronisée avec `_WORK_ORDER_TRANSITIONS`. Le
 * serveur reste l'arbitre final (`409 invalid_transition`/`conflict`) — cette table ne sert
 * qu'à afficher les bons boutons, jamais à décider seule qu'une transition va réussir.
 */
export const WORK_ORDER_TRANSITIONS: Record<WorkOrderState, Exclude<WorkOrderState, "demande">[]> = {
  demande: ["en_cours", "annule"],
  en_cours: ["termine", "annule"],
  termine: [],
  annule: [],
};

/** Cibles qui exigent au moins une ligne de coût (garde « clos ⇒ ≥ 1 ligne », 409 sinon). */
const CLOSING_TARGETS = new Set<WorkOrderState>(["termine", "annule"]);

export function requiresCostLine(target: WorkOrderState): boolean {
  return CLOSING_TARGETS.has(target);
}
