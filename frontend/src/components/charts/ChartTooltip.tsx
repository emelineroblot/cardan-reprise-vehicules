"use client";

import { useState, type ReactNode } from "react";

export interface TooltipState {
  x: number;
  y: number;
  content: ReactNode;
}

/**
 * État de survol/focus partagé par tous les charts (skill `dataviz` § interaction.md) :
 * « le trait est la cible de survol », une tooltip par marque, même contenu au clavier qu'à la
 * souris. `x`/`y` sont exprimés en pourcentage du conteneur (0-100), pas en pixels : les charts
 * sont dessinés en `viewBox` fluide, jamais en taille fixe.
 */
export function useChartTooltip() {
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);
  return { tooltip, show: setTooltip, hide: () => setTooltip(null) };
}

/**
 * Rendu de la tooltip — jamais la SEULE façon de lire une valeur (chaque chart porte aussi des
 * libellés directs et une vue tableau, voir `ChartCard`). `role="status"` : annoncée sans voler
 * le focus, cohérent avec le survol clavier.
 */
export function ChartTooltip({ tooltip }: { tooltip: TooltipState | null }) {
  if (!tooltip) return null;
  return (
    <div
      role="status"
      className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full rounded-md border border-border bg-popover px-2.5 py-1.5 text-xs whitespace-nowrap text-popover-foreground shadow-md"
      style={{ left: `${tooltip.x}%`, top: `${tooltip.y}%`, marginTop: "-8px" }}
    >
      {tooltip.content}
    </div>
  );
}
