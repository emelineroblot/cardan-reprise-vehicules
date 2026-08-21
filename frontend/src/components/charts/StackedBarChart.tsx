"use client";

export interface StackedBarSegment {
  key: string;
  label: string;
  value: number;
  color: string;
}

export interface StackedBarRow {
  id: string;
  label: string;
  segments: StackedBarSegment[];
}

interface StackedBarChartProps {
  rows: StackedBarRow[];
  formatValue: (value: number) => string;
}

/**
 * Barres empilées horizontales — part-à-tout PAR VÉHICULE (jamais une moyenne recalculée côté
 * front : chaque ligne affiche les délais bruts de `mart_cycle_temps`, brief J3 « le dashboard
 * lit les marts »). Un segment manquant (étape non atteinte, `null`) est simplement absent —
 * pas une largeur 0 trompeuse avec un libellé « 0 h ».
 *
 * Rendu en HTML/CSS, pas en SVG — voir `DivergingBarChart.tsx` pour la justification complète
 * (revue § 🟠 texte déformé par un `viewBox` étiré indépendamment en x/y). La valeur de chaque
 * segment reste accessible via `title` (infobulle native) et, de façon garantie, dans l'onglet
 * « Tableau » de la carte (jumeau WCAG) — jamais uniquement au survol.
 */
export function StackedBarChart({ rows, formatValue }: StackedBarChartProps) {
  if (rows.length === 0) return null;

  const totals = rows.map((r) => r.segments.reduce((sum, s) => sum + s.value, 0));
  const max = Math.max(...totals, 1);

  return (
    <ul role="list" aria-label="Décomposition du délai de cycle par véhicule et par étape" className="flex flex-col gap-1.5">
      {rows.map((row, rowIndex) => {
        const total = totals[rowIndex];
        let cursorPct = 0;
        return (
          <li key={row.id} className="grid grid-cols-[5rem_1fr_6rem] items-center gap-2 sm:grid-cols-[6rem_1fr_6.5rem]">
            <span className="truncate text-right text-xs text-muted-foreground" title={row.label}>
              {row.label}
            </span>
            <span className="relative h-4.5 rounded-sm bg-muted/50">
              {row.segments.map((seg) => {
                if (seg.value <= 0) return null;
                const widthPct = (seg.value / max) * 100;
                const left = cursorPct;
                cursorPct += widthPct;
                return (
                  <span
                    key={seg.key}
                    tabIndex={0}
                    title={`${row.label} — ${seg.label} : ${formatValue(seg.value)}`}
                    aria-label={`${row.label} — ${seg.label} : ${formatValue(seg.value)}`}
                    className="absolute inset-y-0 outline-none first:rounded-l-sm last:rounded-r-sm focus-visible:ring-2 focus-visible:ring-ring"
                    style={{
                      left: `${left}%`,
                      width: `calc(${widthPct}% - 2px)`,
                      backgroundColor: seg.color,
                    }}
                  />
                );
              })}
            </span>
            <span className="text-right text-xs font-medium tabular-nums text-foreground">{formatValue(total)}</span>
          </li>
        );
      })}
    </ul>
  );
}
