/**
 * Fonctions PURES de préparation des données du tableau de bord (brief J3) — aucun accès
 * réseau, aucun état React. Elles ne font que SÉLECTIONNER/TRIER/METTRE EN FORME des champs déjà
 * calculés par les marts (`analytics.mart_*`) : jamais un recalcul de marge, de taux ou de coût
 * moyen — cette règle est non négociable (brief § critères d'acceptation J3, docs/wiki/
 * architecture.md § Marge). Testées explicitement sur les cas `NULL` et négatif.
 */
import { VIZ_CATEGORICAL } from "@/components/charts/colors";
import type { DivergingBarDatum } from "@/components/charts/DivergingBarChart";
import type { SequentialBarDatum } from "@/components/charts/SequentialBarChart";
import type { StackedBarRow } from "@/components/charts/StackedBarChart";
import type { LineSeries } from "@/components/charts/MultiSeriesLineChart";
import { formatDate, formatMoneyCents } from "@/lib/format";
import {
  VEHICLE_STATE_LABELS,
  VEHICLE_STATES,
  type CycleTemps,
  type PipelineEtat,
  type Refus,
  type Travaux,
  type TypeFlotte,
  type VehiculeMarge,
  type WorkOrderType,
} from "@/lib/api/types";

/**
 * Sélectionne les véhicules à représenter dans le graphique de marge : exclut `has_marge =
 * false` (véhicule jamais acheté — pas de `prix_achat_negocie` — OU sans valeur de revente
 * estimée ; dans les deux cas la marge n'a pas de sens et n'est jamais affichée comme une
 * marge nulle) et retient les `limit` écarts les plus significatifs (positifs ET négatifs),
 * triés par valeur absolue décroissante. Les marges négatives ne sont ni exclues ni écrêtées.
 */
export function selectTopMarge(rows: VehiculeMarge[], limit = 12): VehiculeMarge[] {
  return rows
    .filter((r) => r.has_marge && r.marge_cents !== null)
    .slice()
    .sort((a, b) => Math.abs(b.marge_cents as number) - Math.abs(a.marge_cents as number))
    .slice(0, limit);
}

export function buildMargeChartData(rows: VehiculeMarge[], limit = 12): DivergingBarDatum[] {
  return selectTopMarge(rows, limit).map((r) => ({
    id: r.vehicle_id,
    label: `${r.reference} — ${r.marque} ${r.modele}`,
    value: r.marge_cents as number,
    formattedValue: formatMoneyCents(r.marge_cents),
  }));
}

/** Nombre de véhicules sans marge calculable (`has_marge = false` : véhicule jamais acheté, ou
 * acheté mais sans valeur de revente estimée) — exclus du graphique, affichés en complément,
 * jamais silencieusement absorbés dans un « 0 ». */
export function countWithoutMarge(rows: VehiculeMarge[]): number {
  return rows.filter((r) => !r.has_marge).length;
}

/**
 * Valeur immobilisée par état — ordonnée par la SÉQUENCE du pipeline (brief J3), jamais triée
 * par magnitude : un pipeline est un ordre ordinal, pas un classement.
 */
export function buildPipelineEtatChartData(rows: PipelineEtat[]): SequentialBarDatum[] {
  const byState = new Map(rows.map((r) => [r.state, r]));
  return VEHICLE_STATES.filter((state) => byState.has(state)).map((state) => {
    const row = byState.get(state) as PipelineEtat;
    return {
      id: state,
      label: VEHICLE_STATE_LABELS[state],
      value: row.valeur_immobilisee_cents,
      formattedValue: formatMoneyCents(row.valeur_immobilisee_cents),
    };
  });
}

const CYCLE_PHASES: { key: keyof CycleTemps; label: string }[] = [
  { key: "delai_saisie_affectation_heures", label: "Saisie → affectation" },
  { key: "delai_affectation_controle_heures", label: "Affectation → contrôle" },
  { key: "delai_controle_decision_heures", label: "Contrôle → décision" },
];

/**
 * Décomposition du délai de cycle PAR VÉHICULE (jamais une moyenne recalculée côté front) :
 * ne retient que les véhicules ayant atteint une décision (`delai_total_heures` non `null`),
 * triés du plus long au plus court, les `limit` premiers. Une étape non atteinte (`null`) est
 * simplement absente du segment — jamais une largeur 0 « — 0 h ».
 */
export function buildCycleTempsChartData(rows: CycleTemps[], limit = 12): StackedBarRow[] {
  return rows
    .filter((r) => r.delai_total_heures !== null)
    .slice()
    .sort((a, b) => (b.delai_total_heures as number) - (a.delai_total_heures as number))
    .slice(0, limit)
    .map((r) => ({
      id: r.vehicle_id,
      label: r.reference,
      segments: CYCLE_PHASES.map((phase, i) => {
        const raw = r[phase.key] as number | null;
        return {
          key: phase.key,
          label: phase.label,
          value: raw ?? 0,
          color: VIZ_CATEGORICAL[i],
        };
      }),
    }));
}

/** Mois ISO triés, uniques, présents dans au moins une des lignes fournies. */
function sortedMonths(mois: string[]): string[] {
  return Array.from(new Set(mois)).sort();
}

/**
 * Construit les séries mensuelles du taux de refus, une par type de flotte présent dans les
 * données — un mois sans donnée pour un type reste `null` (jamais interpolé à 0), conformément
 * à `mart_refus.taux_refus`.
 */
export function buildRefusSeries(
  rows: Refus[],
  labels: Record<TypeFlotte, string>,
): { xLabels: string[]; series: LineSeries[] } {
  const months = sortedMonths(rows.map((r) => r.mois));
  const types = Array.from(new Set(rows.map((r) => r.type_flotte)));
  const byKey = new Map(rows.map((r) => [`${r.mois}|${r.type_flotte}`, r]));

  const series = types.map((type, i) => ({
    key: type,
    label: labels[type] ?? type,
    color: VIZ_CATEGORICAL[i % VIZ_CATEGORICAL.length],
    values: months.map((mois) => byKey.get(`${mois}|${type}`)?.taux_refus ?? null),
  }));

  return { xLabels: months.map((m) => formatDate(m)), series };
}

/**
 * Idem pour le coût moyen réel des travaux, une série par type de travaux — `null` si aucun
 * ordre clos ce mois-là pour ce type (`mart_travaux.cout_moyen_reel_cents`).
 */
export function buildTravauxSeries(
  rows: Travaux[],
  labels: Record<WorkOrderType, string>,
): { xLabels: string[]; series: LineSeries[] } {
  const months = sortedMonths(rows.map((r) => r.mois));
  const types = Array.from(new Set(rows.map((r) => r.type)));
  const byKey = new Map(rows.map((r) => [`${r.mois}|${r.type}`, r]));

  const series = types.map((type, i) => ({
    key: type,
    label: labels[type] ?? type,
    color: VIZ_CATEGORICAL[i % VIZ_CATEGORICAL.length],
    values: months.map((mois) => {
      const value = byKey.get(`${mois}|${type}`)?.cout_moyen_reel_cents;
      return value === undefined ? null : value;
    }),
  }));

  return { xLabels: months.map((m) => formatDate(m)), series };
}
