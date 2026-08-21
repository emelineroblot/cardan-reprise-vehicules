"use client";

import { VIZ_SEQUENTIAL } from "@/components/charts/colors";

export interface SequentialBarDatum {
  id: string;
  label: string;
  value: number;
  formattedValue: string;
}

interface SequentialBarChartProps {
  data: SequentialBarDatum[];
}

/**
 * Barres horizontales à hue unique — comparaison de magnitude sur des catégories déjà
 * ordonnées par l'axe (skill `dataviz` § choosing-a-form.md : « compare magnitude → sequential,
 * one hue »), jamais une couleur par barre ici (ce serait un ramp de valeur sur des catégories
 * nominales, anti-pattern explicite). Une seule série : pas de légende de couleur.
 *
 * Rendu en HTML/CSS, pas en SVG — voir `DivergingBarChart.tsx` pour la justification complète
 * (revue § 🟠 texte déformé par un `viewBox` étiré indépendamment en x/y).
 */
export function SequentialBarChart({ data }: SequentialBarChartProps) {
  if (data.length === 0) return null;

  const max = Math.max(...data.map((d) => d.value), 1);

  return (
    <ul role="list" aria-label="Comparaison de magnitude par état du pipeline" className="flex flex-col gap-1.5">
      {data.map((d) => {
        const pct = Math.max((d.value / max) * 100, 1.5);
        return (
          <li
            key={d.id}
            tabIndex={0}
            aria-label={`${d.label} : ${d.formattedValue}`}
            className="group grid grid-cols-[7rem_1fr_6.5rem] items-center gap-2 rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-ring sm:grid-cols-[9rem_1fr_7rem]"
          >
            <span className="truncate text-right text-xs text-muted-foreground" title={d.label}>
              {d.label}
            </span>
            <span className="relative h-4.5">
              <span
                aria-hidden="true"
                className="absolute inset-y-0 left-0 rounded-r-sm transition-opacity group-hover:opacity-80"
                style={{ width: `${pct}%`, backgroundColor: VIZ_SEQUENTIAL }}
              />
            </span>
            <span className="text-right text-xs font-medium tabular-nums text-foreground">{d.formattedValue}</span>
          </li>
        );
      })}
    </ul>
  );
}
