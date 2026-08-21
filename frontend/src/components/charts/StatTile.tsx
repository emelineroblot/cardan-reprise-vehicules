import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface StatTileProps {
  label: string;
  value: string;
  /** Précision affichée sous la valeur (ex. « sur 90 véhicules »), jamais une seconde valeur
   * concurrente — un stat tile porte un seul chiffre (skill `dataviz` § choosing-a-form.md). */
  hint?: string;
  icon?: ReactNode;
  /** Ton de la valeur — `critical` réservé aux constats réellement défavorables (ex. marge
   * moyenne négative), jamais décoratif (skill `dataviz` § status is fixed). */
  tone?: "default" | "good" | "critical";
}

const TONE_CLASSES: Record<NonNullable<StatTileProps["tone"]>, string> = {
  default: "text-foreground",
  good: "text-viz-status-good",
  critical: "text-destructive",
};

/**
 * Tuile d'indicateur (contrat « stat tile », skill `dataviz` § marks-and-anatomy.md) : un
 * libellé, une valeur en chiffres proportionnels (jamais `tabular-nums` sur un grand nombre —
 * anti-pattern explicite), une précision optionnelle. Utilisée pour les 9 champs de
 * `GET /analytics/kpi-global`.
 */
export function StatTile({ label, value, hint, icon, tone = "default" }: StatTileProps) {
  return (
    <div className="flex flex-col gap-1 rounded-lg border border-border bg-card p-4">
      <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
        {icon}
        <span>{label}</span>
      </div>
      <p className={cn("text-2xl font-semibold tracking-tight", TONE_CLASSES[tone])}>{value}</p>
      {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  );
}
