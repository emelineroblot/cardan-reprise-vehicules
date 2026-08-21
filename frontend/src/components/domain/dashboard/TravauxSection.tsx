"use client";

import { TrendingDown, TrendingUp } from "lucide-react";
import { ChartCard, ChartLegend } from "@/components/charts/ChartCard";
import { MultiSeriesLineChart } from "@/components/charts/MultiSeriesLineChart";
import { DataTable, type DataTableColumn } from "@/components/ui/data-table";
import { useTravaux } from "@/lib/api/hooks/useAnalytics";
import { buildTravauxSeries } from "@/lib/dashboard/prepare";
import { formatDate, formatMoneyCents } from "@/lib/format";
import { WORK_ORDER_TYPE_LABELS, type Travaux } from "@/lib/api/types";
import { cn } from "@/lib/utils";

/**
 * Coût moyen réel des travaux, par mois × type (brief J3) — calculé UNIQUEMENT sur les ordres
 * clos (`termine`/`annule`) côté mart, `null` sinon (jamais `0`, ce qui biaiserait la moyenne
 * vers le bas). `ecart_estime_reel_cents` (réel − estimé) est lu tel quel, jamais recalculé :
 * positif = dépassement, négatif = économie — un statut, pas une identité, donc jamais une
 * couleur catégorielle.
 */
export function TravauxSection() {
  const travaux = useTravaux();
  const rows = travaux.data ?? [];
  const { xLabels, series } = buildTravauxSeries(rows, WORK_ORDER_TYPE_LABELS);

  const columns: DataTableColumn<Travaux>[] = [
    { key: "mois", header: "Mois", cell: (r) => formatDate(r.mois) },
    { key: "type", header: "Type", cell: (r) => WORK_ORDER_TYPE_LABELS[r.type] },
    {
      key: "volume",
      header: "Volume",
      className: "text-right tabular-nums",
      headerClassName: "text-right",
      cell: (r) => r.volume,
    },
    {
      key: "nb_clos",
      header: "Clos",
      className: "text-right tabular-nums",
      headerClassName: "text-right",
      cell: (r) => r.nb_clos,
    },
    {
      key: "cout_moyen_reel_cents",
      header: "Coût moyen réel",
      className: "text-right font-medium tabular-nums",
      headerClassName: "text-right",
      cell: (r) => formatMoneyCents(r.cout_moyen_reel_cents),
    },
    {
      key: "ecart_estime_reel_cents",
      header: "Écart estimé/réel",
      className: "text-right",
      headerClassName: "text-right",
      cell: (r) => <EcartBadge cents={r.ecart_estime_reel_cents} />,
    },
  ];

  return (
    <ChartCard
      id="chart-travaux"
      title="Coût moyen des travaux"
      description="Calculé uniquement sur les ordres clos (terminés ou annulés) — un ordre encore ouvert n'a pas de coût réel définitif."
      legend={<ChartLegend items={series.map((s) => ({ color: s.color, label: s.label }))} />}
      isLoading={travaux.isLoading}
      error={travaux.error}
      onRetry={() => travaux.refetch()}
      isEmpty={rows.length === 0}
      chart={<MultiSeriesLineChart xLabels={xLabels} series={series} formatY={(v) => formatMoneyCents(v)} />}
      table={<DataTable columns={columns} rows={rows} rowKey={(r) => `${r.mois}-${r.type}`} caption="Coût moyen des travaux par mois et type" />}
    />
  );
}

/** Écart status — jamais une couleur catégorielle (skill dataviz § status is fixed : icône +
 * libellé, jamais la couleur seule). */
function EcartBadge({ cents }: { cents: number | null }) {
  if (cents === null) return <span className="text-muted-foreground">—</span>;
  if (cents === 0) return <span className="text-muted-foreground">{formatMoneyCents(0)}</span>;
  const overrun = cents > 0;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 font-medium tabular-nums",
        overrun ? "text-viz-status-critical" : "text-viz-status-good",
      )}
    >
      {overrun ? (
        <TrendingUp className="size-3.5" aria-hidden="true" />
      ) : (
        <TrendingDown className="size-3.5" aria-hidden="true" />
      )}
      {formatMoneyCents(cents)}
      <span className="sr-only">{overrun ? "dépassement" : "économie"}</span>
    </span>
  );
}
