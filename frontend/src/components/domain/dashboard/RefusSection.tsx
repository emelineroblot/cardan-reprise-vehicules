"use client";

import { ChartCard, ChartLegend } from "@/components/charts/ChartCard";
import { MultiSeriesLineChart } from "@/components/charts/MultiSeriesLineChart";
import { DataTable, type DataTableColumn } from "@/components/ui/data-table";
import { useRefus } from "@/lib/api/hooks/useAnalytics";
import { buildRefusSeries } from "@/lib/dashboard/prepare";
import { formatDate, formatFractionAsPercent } from "@/lib/format";
import { TYPE_FLOTTE_LABELS, type Refus } from "@/lib/api/types";

/**
 * Taux de refus par mois × type de flotte (brief J3). `ANNULE` est déjà exclu numérateur ET
 * dénominateur côté mart (vendeur rétracté/doublon confirmé ≠ décision de refus métier) — rien
 * à recalculer ici. `taux_refus` reste `null` (jamais `0`) sans véhicule comptabilisable.
 */
export function RefusSection() {
  const refus = useRefus();
  const rows = refus.data ?? [];
  const { xLabels, series } = buildRefusSeries(rows, TYPE_FLOTTE_LABELS);

  const columns: DataTableColumn<Refus>[] = [
    { key: "mois", header: "Mois", cell: (r) => formatDate(r.mois) },
    { key: "type_flotte", header: "Type de flotte", cell: (r) => TYPE_FLOTTE_LABELS[r.type_flotte] },
    {
      key: "nb_proposes",
      header: "Proposés",
      className: "text-right tabular-nums",
      headerClassName: "text-right",
      cell: (r) => r.nb_proposes,
    },
    {
      key: "nb_refuses",
      header: "Refusés",
      className: "text-right tabular-nums",
      headerClassName: "text-right",
      cell: (r) => r.nb_refuses,
    },
    {
      key: "taux_refus",
      header: "Taux de refus",
      className: "text-right font-medium tabular-nums",
      headerClassName: "text-right",
      cell: (r) => formatFractionAsPercent(r.taux_refus),
    },
  ];

  return (
    <ChartCard
      id="chart-refus"
      title="Taux de refus"
      description="Un véhicule annulé (vendeur rétracté, doublon confirmé) est exclu du calcul — seul REFUSE compte comme un refus métier."
      legend={<ChartLegend items={series.map((s) => ({ color: s.color, label: s.label }))} />}
      isLoading={refus.isLoading}
      error={refus.error}
      onRetry={() => refus.refetch()}
      isEmpty={rows.length === 0}
      chart={<MultiSeriesLineChart xLabels={xLabels} series={series} formatY={(v) => formatFractionAsPercent(v)} />}
      table={<DataTable columns={columns} rows={rows} rowKey={(r) => `${r.mois}-${r.type_flotte}`} caption="Taux de refus par mois et type de flotte" />}
    />
  );
}
