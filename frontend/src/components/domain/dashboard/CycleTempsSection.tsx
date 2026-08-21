"use client";

import Link from "next/link";
import { ChartCard, ChartLegend } from "@/components/charts/ChartCard";
import { StackedBarChart } from "@/components/charts/StackedBarChart";
import { VIZ_CATEGORICAL } from "@/components/charts/colors";
import { DataTable, type DataTableColumn } from "@/components/ui/data-table";
import { StateBadge } from "@/components/ui/state-badge";
import { useCycleTemps } from "@/lib/api/hooks/useAnalytics";
import { buildCycleTempsChartData } from "@/lib/dashboard/prepare";
import { formatDurationHours } from "@/lib/format";
import type { CycleTemps } from "@/lib/api/types";

const PHASE_LEGEND = [
  { color: VIZ_CATEGORICAL[0], label: "Saisie → affectation" },
  { color: VIZ_CATEGORICAL[1], label: "Affectation → contrôle" },
  { color: VIZ_CATEGORICAL[2], label: "Contrôle → décision" },
];

/**
 * Délai de cycle — décomposition PAR VÉHICULE (brief J3), jamais une moyenne recalculée côté
 * front (`mart_kpi_global.delai_cycle_moyen_heures` porte déjà la moyenne globale, affichée
 * dans `KpiRow`). Une étape non atteinte reste `null`, jamais confondue avec `0`.
 */
export function CycleTempsSection() {
  const cycleTemps = useCycleTemps();
  const rows = cycleTemps.data ?? [];
  const chartData = buildCycleTempsChartData(rows);

  const columns: DataTableColumn<CycleTemps>[] = [
    {
      key: "reference",
      header: "Référence",
      cell: (r) => (
        <Link href={`/vehicules/${r.vehicle_id}`} className="font-medium text-primary hover:underline">
          {r.reference}
        </Link>
      ),
    },
    { key: "state", header: "État", cell: (r) => <StateBadge state={r.state} /> },
    { key: "vehicule", header: "Véhicule", cell: (r) => `${r.marque} ${r.modele}` },
    {
      key: "saisie",
      header: "Saisie → affectation",
      className: "text-right tabular-nums",
      headerClassName: "text-right",
      cell: (r) => formatDurationHours(r.delai_saisie_affectation_heures),
    },
    {
      key: "affectation",
      header: "Affectation → contrôle",
      className: "text-right tabular-nums",
      headerClassName: "text-right",
      cell: (r) => formatDurationHours(r.delai_affectation_controle_heures),
    },
    {
      key: "controle",
      header: "Contrôle → décision",
      className: "text-right tabular-nums",
      headerClassName: "text-right",
      cell: (r) => formatDurationHours(r.delai_controle_decision_heures),
    },
    {
      key: "total",
      header: "Total",
      className: "text-right font-medium tabular-nums",
      headerClassName: "text-right",
      cell: (r) => formatDurationHours(r.delai_total_heures),
    },
  ];

  return (
    <ChartCard
      id="chart-cycle-temps"
      title="Délai de cycle"
      description="Les 12 véhicules au cycle le plus long, décomposés par étape — délais bruts, aucune moyenne recalculée ici."
      legend={<ChartLegend items={PHASE_LEGEND} />}
      isLoading={cycleTemps.isLoading}
      error={cycleTemps.error}
      onRetry={() => cycleTemps.refetch()}
      isEmpty={rows.length === 0}
      emptyDescription="Aucun véhicule n'a encore atteint une décision."
      chart={
        chartData.length > 0 ? (
          <StackedBarChart rows={chartData} formatValue={(v) => formatDurationHours(v)} />
        ) : (
          <p className="py-6 text-center text-sm text-muted-foreground">
            Aucun véhicule n&apos;a encore atteint une décision (achat validé, refus ou annulation).
          </p>
        )
      }
      table={
        <DataTable
          columns={columns}
          rows={rows}
          rowKey={(r) => r.vehicle_id}
          caption="Délai de cycle par véhicule"
        />
      }
    />
  );
}
