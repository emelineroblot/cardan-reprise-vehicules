"use client";

import { VIZ_DIVERGING } from "@/components/charts/colors";
import { cn } from "@/lib/utils";

export interface DivergingBarDatum {
  id: string;
  /** Libellé de catégorie (jamais coloré — skill `dataviz` : le texte porte les tokens de
   * texte, la couleur reste sur la marque). */
  label: string;
  /** Valeur signée (centimes) — la marge peut être négative, affichée telle quelle. */
  value: number;
  /** Valeur déjà formatée (`formatMoneyCents`) — jamais reformatée dans le composant. */
  formattedValue: string;
}

interface DivergingBarChartProps {
  data: DivergingBarDatum[];
}

/**
 * Barres divergentes horizontales (baseline à 0) — cœur du tableau de bord (brief J3).
 * Bleu = marge positive, rouge = marge négative (paire divergente, skill `dataviz` §
 * color-formula.md). Une seule série : pas de légende de couleur nécessaire (la couleur EST
 * le signe, expliqué dans le titre de la carte).
 *
 * Rendu en HTML/CSS, pas en SVG — ce sont des barres, pas un tracé vectoriel (revue § 🟠 « Les
 * quatre graphiques du tableau de bord déforment leur texte ») : un `viewBox` étiré
 * indépendamment en x/y (`preserveAspectRatio="none"`) déformait le texte à l'intérieur du SVG
 * d'un facteur ~3,4 sur un écran de bureau. Le libellé et la valeur sont ici du texte HTML
 * natif, donc jamais mis à l'échelle — et toujours visibles en direct, sans dépendre d'un
 * survol (skill `dataviz` § interaction.md : une tooltip n'est jamais la seule façon de lire
 * une valeur).
 */
export function DivergingBarChart({ data }: DivergingBarChartProps) {
  if (data.length === 0) return null;

  const maxAbs = Math.max(...data.map((d) => Math.abs(d.value)), 1);

  return (
    <ul role="list" aria-label="Marge par véhicule, triée par valeur absolue" className="flex flex-col gap-1.5">
      {data.map((d) => {
        const positive = d.value >= 0;
        const pctOfHalf = (Math.abs(d.value) / maxAbs) * 100;
        const color = positive ? VIZ_DIVERGING.positive : VIZ_DIVERGING.negative;
        return (
          <li
            key={d.id}
            tabIndex={0}
            aria-label={`${d.label} : ${d.formattedValue}`}
            className="group grid grid-cols-[9rem_1fr_6.5rem] items-center gap-2 rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-ring sm:grid-cols-[13rem_1fr_7rem]"
          >
            <span className="truncate text-right text-xs text-muted-foreground" title={d.label}>
              {d.label}
            </span>
            <span className="relative h-5">
              <span aria-hidden="true" className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-border" />
              {positive ? (
                <span
                  aria-hidden="true"
                  className="absolute inset-y-0 left-1/2 rounded-r-sm transition-opacity group-hover:opacity-80"
                  style={{ width: `${pctOfHalf / 2}%`, backgroundColor: color }}
                />
              ) : (
                <span
                  aria-hidden="true"
                  className="absolute inset-y-0 right-1/2 rounded-l-sm transition-opacity group-hover:opacity-80"
                  style={{ width: `${pctOfHalf / 2}%`, backgroundColor: color }}
                />
              )}
            </span>
            <span className={cn("text-right text-xs font-medium tabular-nums", positive ? "text-foreground" : "text-destructive")}>
              {d.formattedValue}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
