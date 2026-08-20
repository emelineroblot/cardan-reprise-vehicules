import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { VEHICLE_STATE_LABELS, type VehicleState } from "@/lib/api/types";

/**
 * Couleurs des 11 états du véhicule (plan.md § 5.3). Regroupées par famille pour rester
 * lisibles en un coup d'œil dans la liste de suivi et la frise d'historique :
 * gris = pas encore engagé, bleu = en cours de saisie/planification, ambre = travaux,
 * vert = issue positive, rouge/gris foncé = issues négatives (distinctes : REFUSE compte
 * dans le taux de refus, ANNULE non — § 5.3).
 */
const STATE_STYLES: Record<VehicleState, string> = {
  BROUILLON: "bg-zinc-100 text-zinc-700 border-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:border-zinc-700",
  A_PLANIFIER: "bg-sky-100 text-sky-700 border-sky-200 dark:bg-sky-950 dark:text-sky-300 dark:border-sky-800",
  AFFECTE: "bg-sky-100 text-sky-700 border-sky-200 dark:bg-sky-950 dark:text-sky-300 dark:border-sky-800",
  RDV_PLANIFIE: "bg-sky-100 text-sky-700 border-sky-200 dark:bg-sky-950 dark:text-sky-300 dark:border-sky-800",
  CONTROLE_EN_COURS: "bg-indigo-100 text-indigo-700 border-indigo-200 dark:bg-indigo-950 dark:text-indigo-300 dark:border-indigo-800",
  TRAVAUX_REQUIS: "bg-amber-100 text-amber-800 border-amber-200 dark:bg-amber-950 dark:text-amber-300 dark:border-amber-800",
  TRAVAUX_EN_COURS: "bg-amber-100 text-amber-800 border-amber-200 dark:bg-amber-950 dark:text-amber-300 dark:border-amber-800",
  TRAVAUX_TERMINES: "bg-amber-100 text-amber-800 border-amber-200 dark:bg-amber-950 dark:text-amber-300 dark:border-amber-800",
  ACHAT_VALIDE: "bg-emerald-100 text-emerald-800 border-emerald-200 dark:bg-emerald-950 dark:text-emerald-300 dark:border-emerald-800",
  REFUSE: "bg-rose-100 text-rose-800 border-rose-200 dark:bg-rose-950 dark:text-rose-300 dark:border-rose-800",
  ANNULE: "bg-zinc-200 text-zinc-600 border-zinc-300 dark:bg-zinc-800 dark:text-zinc-400 dark:border-zinc-700",
};

interface StateBadgeProps {
  state: VehicleState;
  className?: string;
}

export function StateBadge({ state, className }: StateBadgeProps) {
  return (
    <Badge variant="outline" className={cn("border", STATE_STYLES[state], className)}>
      {VEHICLE_STATE_LABELS[state]}
    </Badge>
  );
}
