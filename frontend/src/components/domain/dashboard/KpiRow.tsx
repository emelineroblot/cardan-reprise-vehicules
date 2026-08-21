"use client";

import { Car, Gauge, PercentCircle, ShieldX, TrendingDown, TrendingUp, Wallet, Wrench } from "lucide-react";
import { StatTile } from "@/components/charts/StatTile";
import { LoadingState } from "@/components/ui/loading-state";
import { ErrorState } from "@/components/ui/error-state";
import { useKpiGlobal } from "@/lib/api/hooks/useAnalytics";
import { formatDurationHours, formatFractionAsPercent, formatMoneyCents } from "@/lib/format";

/**
 * Les tuiles du tableau de bord — lecture DIRECTE de `GET /analytics/kpi-global`
 * (`mart_kpi_global`, brief J3), aucun champ recalculé ici. `marge_moyenne_cents`,
 * `taux_refus_global`, `delai_cycle_moyen_heures` et `cout_travaux_moyen_cents` sont `null`
 * (jamais `0`) quand la base ne permet pas encore de les calculer — les formateurs partagés
 * (`formatMoneyCents`/`formatFractionAsPercent`/`formatDurationHours`) affichent alors « — ».
 */
export function KpiRow() {
  const kpi = useKpiGlobal();

  if (kpi.isLoading) return <LoadingState label="Chargement des indicateurs…" />;
  if (kpi.error) {
    return <ErrorState error={kpi.error} title="Indicateurs indisponibles" onRetry={() => kpi.refetch()} />;
  }
  const data = kpi.data;
  if (!data) return null;

  const margeTone = data.marge_moyenne_cents !== null && data.marge_moyenne_cents < 0 ? "critical" : "default";

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
      <StatTile
        featured
        label="Véhicules au total"
        value={data.nb_vehicules_total.toLocaleString("fr-FR")}
        hint={`${data.nb_vehicules_actifs} en cours`}
        icon={<Car className="size-4" aria-hidden="true" />}
      />
      <StatTile
        label="Achats validés"
        value={data.nb_achats_valides.toLocaleString("fr-FR")}
        icon={<TrendingUp className="size-4" aria-hidden="true" />}
      />
      <StatTile
        label="Refusés"
        value={data.nb_refuses.toLocaleString("fr-FR")}
        icon={<ShieldX className="size-4" aria-hidden="true" />}
      />
      <StatTile
        label="Taux de refus global"
        value={formatFractionAsPercent(data.taux_refus_global)}
        icon={<PercentCircle className="size-4" aria-hidden="true" />}
      />
      <StatTile
        label="Marge moyenne"
        value={formatMoneyCents(data.marge_moyenne_cents)}
        tone={margeTone}
        icon={<Wallet className="size-4" aria-hidden="true" />}
      />
      <StatTile
        label="Marges négatives"
        value={data.nb_marges_negatives.toLocaleString("fr-FR")}
        tone={data.nb_marges_negatives > 0 ? "critical" : "default"}
        icon={<TrendingDown className="size-4" aria-hidden="true" />}
      />
      <StatTile
        label="Délai de cycle moyen"
        value={formatDurationHours(data.delai_cycle_moyen_heures)}
        icon={<Gauge className="size-4" aria-hidden="true" />}
      />
      <StatTile
        label="Coût moyen des travaux"
        value={formatMoneyCents(data.cout_travaux_moyen_cents)}
        icon={<Wrench className="size-4" aria-hidden="true" />}
      />
    </div>
  );
}
