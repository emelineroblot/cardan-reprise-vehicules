"use client";

import { useMemo } from "react";
import { ChartTooltip, useChartTooltip } from "@/components/charts/ChartTooltip";

export interface LineSeries {
  key: string;
  label: string;
  color: string;
  /** `null` = donnée absente à ce mois pour cette série (skill dataviz : jamais interpolée en
   * 0, le tracé s'interrompt). */
  values: (number | null)[];
}

interface MultiSeriesLineChartProps {
  /** Libellés d'axe X, un par point (mois formatés « août 2026 »). */
  xLabels: string[];
  series: LineSeries[];
  formatY: (value: number) => string;
}

// Toutes les coordonnées vivent dans un `viewBox` de 100 unités de large : la largeur du
// conteneur HTML mappe donc directement sur ces unités en pourcentage (`xAt(i)` réutilisé tel
// quel comme `left: ${..}%` pour les libellés de mois, rendus hors du SVG — voir plus bas).
const VIEWBOX_WIDTH = 100;
const VIEWBOX_HEIGHT = 33;
const PLOT_HEIGHT = 27;
const PLOT_TOP = 3;
const PLOT_LEFT = 4;
const PLOT_RIGHT = 98;
const AXIS_Y = PLOT_TOP + PLOT_HEIGHT;

/**
 * Ligne multi-séries (skill `dataviz` § choosing-a-form.md « trend over time → line,
 * categorical color »). Une seule tooltip lit TOUTES les séries au même point X (jamais besoin
 * de viser une ligne précise) ; le trait vertical de croisement piste le pointeur et se cale
 * sur le point le plus proche.
 *
 * Le SVG garde un rapport largeur/hauteur FIXE et identique à son `viewBox`
 * (`aspectRatio` CSS posé sur le conteneur, `preserveAspectRatio` par défaut) : les deux
 * facteurs d'échelle x/y restent toujours égaux, quelle que soit la largeur réelle du
 * conteneur — c'était la cause du texte étiré signalée en revue (§ 🟠), un `viewBox` haut fixe
 * combiné à `preserveAspectRatio="none"` découplait les deux échelles d'un facteur ~3,4 sur un
 * écran de bureau. Les libellés de mois sont en plus sortis du SVG (calque HTML positionné en
 * `%`, même technique que `ChartTooltip`) : plus aucun `<text>` ne vit dans un repère mis à
 * l'échelle.
 */
export function MultiSeriesLineChart({ xLabels, series, formatY }: MultiSeriesLineChartProps) {
  const { tooltip, show, hide } = useChartTooltip();

  const allValues = series.flatMap((s) => s.values).filter((v): v is number => v !== null);
  const max = Math.max(...allValues, 0.0001);

  const xStep = xLabels.length > 1 ? (PLOT_RIGHT - PLOT_LEFT) / (xLabels.length - 1) : 0;
  const xAt = (i: number) => PLOT_LEFT + i * xStep;
  const yAt = (value: number) => AXIS_Y - (value / max) * PLOT_HEIGHT;

  const paths = useMemo(
    () =>
      series.map((s) => {
        // Un trou (`null`, mois sans donnée pour cette série) interrompt le tracé : un
        // nouveau `M` redémarre le chemin après chaque absence, jamais interpolé à 0.
        let d = "";
        let drawing = false;
        s.values.forEach((v, i) => {
          if (v === null) {
            drawing = false;
            return;
          }
          d += `${drawing ? "L" : "M"}${xAt(i)},${yAt(v)} `;
          drawing = true;
        });
        return { key: s.key, d: d.trim() };
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `xAt`/`yAt` dérivent de `series`/`xLabels`, déjà en dépendance.
    [series, xLabels],
  );

  const handleMove = (clientX: number, clientY: number, rect: DOMRect) => {
    const relX = ((clientX - rect.left) / rect.width) * 100;
    const relY = ((clientY - rect.top) / rect.height) * 100;
    const nearestIndex = xStep > 0 ? Math.round((relX - PLOT_LEFT) / xStep) : 0;
    const index = Math.min(Math.max(nearestIndex, 0), xLabels.length - 1);
    const rows = series
      .map((s) => ({ label: s.label, value: s.values[index], color: s.color }))
      .filter((r) => r.value !== null);
    if (rows.length === 0) {
      hide();
      return;
    }
    show({
      x: relX,
      y: relY,
      content: (
        <div className="flex flex-col gap-0.5">
          <span className="font-medium">{xLabels[index]}</span>
          {rows.map((r) => (
            <span key={r.label} className="flex items-center gap-1.5">
              <span aria-hidden="true" className="inline-block h-0.5 w-2.5" style={{ backgroundColor: r.color }} />
              <strong>{formatY(r.value as number)}</strong> {r.label}
            </span>
          ))}
        </div>
      ),
    });
  };

  if (xLabels.length === 0) return null;

  // N'affiche qu'un sous-ensemble de libellés (≤ 6) pour éviter le chevauchement sur des séries
  // longues — même logique que l'ancien filtre `<text>`, déplacée ici.
  const labelStep = Math.max(Math.ceil(xLabels.length / 6), 1);

  return (
    <div className="flex flex-col gap-1">
      <div className="relative" style={{ aspectRatio: `${VIEWBOX_WIDTH} / ${VIEWBOX_HEIGHT}` }}>
        <svg
          viewBox={`0 0 ${VIEWBOX_WIDTH} ${VIEWBOX_HEIGHT}`}
          width="100%"
          height="100%"
          role="img"
          aria-label="Évolution mensuelle par catégorie"
          onPointerMove={(e) => handleMove(e.clientX, e.clientY, e.currentTarget.getBoundingClientRect())}
          onPointerLeave={hide}
        >
          <line x1={PLOT_LEFT} y1={AXIS_Y} x2={PLOT_RIGHT} y2={AXIS_Y} className="stroke-border" strokeWidth={0.3} />
          {[0, 0.5, 1].map((frac) => (
            <line
              key={frac}
              x1={PLOT_LEFT}
              y1={AXIS_Y - frac * PLOT_HEIGHT}
              x2={PLOT_RIGHT}
              y2={AXIS_Y - frac * PLOT_HEIGHT}
              className="stroke-border"
              strokeWidth={0.15}
            />
          ))}
          {paths.map((p) => (
            <path
              key={p.key}
              d={p.d}
              fill="none"
              stroke={series.find((s) => s.key === p.key)?.color}
              strokeWidth={0.6}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          ))}
          {series.map((s) =>
            s.values.map((v, i) =>
              v === null ? null : (
                <circle
                  key={`${s.key}-${i}`}
                  cx={xAt(i)}
                  cy={yAt(v)}
                  r={0.8}
                  style={{ fill: s.color }}
                  className="stroke-card"
                  strokeWidth={0.4}
                />
              ),
            ),
          )}
        </svg>
        <ChartTooltip tooltip={tooltip} />
      </div>
      <div className="relative h-4" aria-hidden="true">
        {xLabels.map((label, i) =>
          i % labelStep === 0 ? (
            <span
              key={label}
              className="absolute -translate-x-1/2 text-[11px] whitespace-nowrap text-muted-foreground"
              style={{ left: `${xAt(i)}%` }}
            >
              {label}
            </span>
          ) : null,
        )}
      </div>
    </div>
  );
}
