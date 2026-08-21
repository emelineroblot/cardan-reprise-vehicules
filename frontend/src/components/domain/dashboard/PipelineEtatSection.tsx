"use client";

import { ChartCard } from "@/components/charts/ChartCard";
import { SequentialBarChart } from "@/components/charts/SequentialBarChart";
import { DataTable, type DataTableColumn } from "@/components/ui/data-table";
import { StateBadge } from "@/components/ui/state-badge";
import { usePipelineEtat } from "@/lib/api/hooks/useAnalytics";
import { buildPipelineEtatChartData } from "@/lib/dashboard/prepare";
import { formatMoneyCents } from "@/lib/format";
import type { PipelineEtat } from "@/lib/api/types";

/**
 * Valeur immobilisée par état du pipeline (brief J3) — vue ANALYTIQUE, à la fraîcheur du
 * dernier rafraîchissement (`AnalyticsFreshnessBar`), distincte du Kanban opérationnel
 * (`/pipeline`, live). Ordonnée par la séquence du pipeline, pas par magnitude — un pipeline
 * se lit dans l'ordre, jamais trié.
 */
export function PipelineEtatSection() {
  const pipelineEtat = usePipelineEtat();
  const rows = pipelineEtat.data ?? [];
  const chartData = buildPipelineEtatChartData(rows);

  const columns: DataTableColumn<PipelineEtat>[] = [
    { key: "state", header: "État", cell: (r) => <StateBadge state={r.state} /> },
    {
      key: "nb_vehicules",
      header: "Véhicules",
      className: "text-right tabular-nums",
      headerClassName: "text-right",
      cell: (r) => r.nb_vehicules,
    },
    {
      key: "valeur_immobilisee_cents",
      header: "Valeur immobilisée",
      className: "text-right font-medium tabular-nums",
      headerClassName: "text-right",
      cell: (r) => formatMoneyCents(r.valeur_immobilisee_cents),
    },
  ];

  return (
    <ChartCard
      id="chart-pipeline-etat"
      title="Valeur immobilisée par état"
      description="Où dort le capital engagé, étape par étape du pipeline."
      isLoading={pipelineEtat.isLoading}
      error={pipelineEtat.error}
      onRetry={() => pipelineEtat.refetch()}
      isEmpty={rows.length === 0}
      chart={<SequentialBarChart data={chartData} />}
      table={<DataTable columns={columns} rows={rows} rowKey={(r) => r.state} caption="Valeur immobilisée par état" />}
    />
  );
}
