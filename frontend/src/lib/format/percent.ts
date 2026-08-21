/**
 * Pourcentages — deux conventions distinctes côté API (brief J3), jamais interchangeables :
 * `mart_refus.taux_refus` est une FRACTION 0-1 (`round(nb_refuses::numeric / nb_proposes, 4)`),
 * `mart_vehicule_marge.marge_pct` est déjà en POINTS de pourcentage (`× 100` fait en SQL). Deux
 * formateurs distincts pour ne jamais appliquer un second `× 100` par erreur.
 */

const PERCENT_FORMATTER = new Intl.NumberFormat("fr-FR", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

/** Formate une fraction (0-1, ex. `mart_refus.taux_refus`) en « 12,3 % ». `null` → « — ». */
export function formatFractionAsPercent(fraction: number | null | undefined): string {
  if (fraction === null || fraction === undefined || Number.isNaN(fraction)) return "—";
  return `${PERCENT_FORMATTER.format(fraction * 100)} %`;
}

/** Formate des points de pourcentage déjà calculés (ex. `mart_vehicule_marge.marge_pct`) en
 * « 12,3 % ». `null` → « — ». Jamais multiplié par 100 une seconde fois. */
export function formatPercentagePoints(points: number | null | undefined): string {
  if (points === null || points === undefined || Number.isNaN(points)) return "—";
  return `${PERCENT_FORMATTER.format(points)} %`;
}
