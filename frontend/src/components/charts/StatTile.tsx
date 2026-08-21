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
  /**
   * Remplissage plein pour UNE tuile « tête de ligne » par rangée (inspiration DashboardKit §
   * tuiles KPI alternant blanc/plein) — hiérarchie visuelle, indépendante de `tone` qui reste
   * réservé au sens bon/mauvais de la donnée. Neutre (`bg-foreground`), jamais une teinte de la
   * palette dataviz (`--viz-*`), réservée aux séries de graphique (skill `dataviz`).
   */
  featured?: boolean;
}

const TONE_CLASSES: Record<NonNullable<StatTileProps["tone"]>, string> = {
  default: "text-foreground",
  good: "text-viz-status-good",
  critical: "text-destructive",
};

const FEATURED_TONE_CLASSES: Record<NonNullable<StatTileProps["tone"]>, string> = {
  default: "text-background",
  good: "text-viz-status-good",
  critical: "text-destructive",
};

/**
 * Tuile d'indicateur (contrat « stat tile », skill `dataviz` § marks-and-anatomy.md) : un
 * libellé, une valeur en chiffres proportionnels (jamais `tabular-nums` sur un grand nombre —
 * anti-pattern explicite), une précision optionnelle. Utilisée pour les 9 champs de
 * `GET /analytics/kpi-global`.
 */
export function StatTile({ label, value, hint, icon, tone = "default", featured = false }: StatTileProps) {
  if (featured) {
    return (
      <div className="flex flex-col gap-1 rounded-lg bg-foreground p-4 text-background">
        <div className="flex items-start justify-between gap-2">
          <span className="text-sm text-background/70">{label}</span>
          {icon ? <span className="text-background/70">{icon}</span> : null}
        </div>
        <p className={cn("text-2xl font-semibold tracking-tight", FEATURED_TONE_CLASSES[tone])}>{value}</p>
        {hint ? <p className="text-xs text-background/60">{hint}</p> : null}
      </div>
    );
  }

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
