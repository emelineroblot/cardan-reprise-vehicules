"use client";

import { useState } from "react";
import Link from "next/link";
import { ChartCard, ChartLegend } from "@/components/charts/ChartCard";
import { DivergingBarChart } from "@/components/charts/DivergingBarChart";
import { VIZ_DIVERGING } from "@/components/charts/colors";
import { DataTable, type DataTableColumn, type DataTableSort } from "@/components/ui/data-table";
import { StateBadge } from "@/components/ui/state-badge";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useMarge, type MargeFilters } from "@/lib/api/hooks/useAnalytics";
import { buildMargeChartData, countWithoutMarge } from "@/lib/dashboard/prepare";
import { formatDate, formatMoneyCents, formatPercentagePoints } from "@/lib/format";
import { VEHICLE_STATE_LABELS, VEHICLE_STATES, type VehicleState, type VehiculeMarge } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const SORT_KEYS = new Set(["marge_cents", "date_proposition"]);

/**
 * Marge par véhicule — le cœur de la démonstration (brief J3). Une marge `null` (`has_marge =
 * false`) ne s'affiche JAMAIS comme `0` : `formatMoneyCents` renvoie « — », et
 * `buildMargeChartData` exclut ces véhicules du graphique (comptés à part, jamais masqués).
 * Une marge négative s'affiche telle quelle, en rouge — le jeu de démo en garantit au moins
 * une par construction (implementation.md § J3 Backend).
 */
export function MargeSection() {
  const [state, setState] = useState<VehicleState | undefined>(undefined);
  const [sort, setSort] = useState<MargeFilters["sort"]>("-marge_cents");

  const marge = useMarge({ state, sort });
  const rows = marge.data ?? [];
  const missing = countWithoutMarge(rows);
  const chartData = buildMargeChartData(rows);

  const currentSort: DataTableSort | null = sort
    ? { key: sort.replace(/^-/, ""), direction: sort.startsWith("-") ? "desc" : "asc" }
    : null;

  const handleSortChange = (key: string) => {
    if (!SORT_KEYS.has(key)) return;
    const next =
      currentSort?.key === key && currentSort.direction === "desc"
        ? (key as MargeFilters["sort"])
        : (`-${key}` as MargeFilters["sort"]);
    setSort(next);
  };

  const columns: DataTableColumn<VehiculeMarge>[] = [
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
    { key: "societe", header: "Société", cell: (r) => r.company_denomination },
    { key: "vehicule", header: "Véhicule", cell: (r) => `${r.marque} ${r.modele}` },
    {
      key: "date_proposition",
      header: "Proposé le",
      sortable: true,
      cell: (r) => formatDate(r.date_proposition),
    },
    {
      key: "valeur_revente_estimee_cents",
      header: "Valeur revente",
      className: "text-right tabular-nums",
      headerClassName: "text-right",
      cell: (r) => formatMoneyCents(r.valeur_revente_estimee_cents),
    },
    {
      key: "cout_atelier_reel_cents",
      header: "Coût atelier réel",
      className: "text-right tabular-nums",
      headerClassName: "text-right",
      cell: (r) => formatMoneyCents(r.cout_atelier_reel_cents),
    },
    {
      key: "marge_cents",
      header: "Marge",
      sortable: true,
      className: "text-right tabular-nums",
      headerClassName: "text-right",
      cell: (r) => (
        <span
          className={cn(
            "font-medium",
            r.marge_cents !== null && r.marge_cents < 0 ? "text-destructive" : "text-foreground",
          )}
        >
          {formatMoneyCents(r.marge_cents)}
        </span>
      ),
    },
    {
      key: "marge_pct",
      header: "Marge %",
      className: "text-right tabular-nums",
      headerClassName: "text-right",
      cell: (r) => formatPercentagePoints(r.marge_pct),
    },
  ];

  return (
    <ChartCard
      id="chart-marge"
      title="Marge par véhicule"
      description="Coûts d'atelier réels inclus — jamais l'estimé. La marge n'est calculée que pour un véhicule réellement acheté ; une marge non calculable n'est jamais confondue avec une marge nulle."
      legend={<ChartLegend items={[{ color: VIZ_DIVERGING.positive, label: "Positive" }, { color: VIZ_DIVERGING.negative, label: "Négative" }]} />}
      isLoading={marge.isLoading}
      error={marge.error}
      onRetry={() => marge.refetch()}
      isEmpty={rows.length === 0}
      emptyDescription="Aucun véhicule ne correspond à ce filtre."
      chart={
        <div className="flex flex-col gap-3">
          <FilterRow state={state} onStateChange={setState} />
          {chartData.length > 0 ? (
            <DivergingBarChart data={chartData} />
          ) : (
            <p className="py-6 text-center text-sm text-muted-foreground">
              Aucun véhicule avec une marge calculable pour ce filtre.
            </p>
          )}
          {missing > 0 ? (
            <p className="text-xs text-muted-foreground">
              {missing} véhicule{missing > 1 ? "s" : ""} sans marge calculable (pas encore
              acheté{missing > 1 ? "s" : ""}, ou sans valeur de revente estimée), exclu
              {missing > 1 ? "s" : ""} du graphique (visible{missing > 1 ? "s" : ""} dans le tableau, marge « — »).
            </p>
          ) : null}
        </div>
      }
      table={
        <div className="flex flex-col gap-3">
          <FilterRow state={state} onStateChange={setState} />
          <DataTable
            columns={columns}
            rows={rows}
            rowKey={(r) => r.vehicle_id}
            caption="Marge par véhicule"
            sort={currentSort}
            onSortChange={handleSortChange}
          />
        </div>
      }
    />
  );
}

function FilterRow({
  state,
  onStateChange,
}: {
  state: VehicleState | undefined;
  onStateChange: (state: VehicleState | undefined) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <Label htmlFor="marge-state-filter" className="text-xs text-muted-foreground">
        État
      </Label>
      <Select value={state ?? "__all__"} onValueChange={(v) => onStateChange(v === "__all__" ? undefined : (v as VehicleState))}>
        <SelectTrigger id="marge-state-filter" size="sm" className="w-48">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="__all__">Tous les états</SelectItem>
          {VEHICLE_STATES.map((s) => (
            <SelectItem key={s} value={s}>
              {VEHICLE_STATE_LABELS[s]}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
