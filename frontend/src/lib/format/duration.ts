/**
 * Délais de cycle (brief J3, `analytics.mart_cycle_temps`/`mart_kpi_global`) — toujours en
 * heures côté API (`delai_*_heures`), jamais de secondes ni de millisecondes.
 */

/**
 * Formate un nombre d'heures en « 3 j 4 h » (≥ 24 h) ou « 4,5 h » (< 24 h). `null`/`undefined`
 * → « — » (absence de donnée, jamais confondue avec `0`, cf. règle générale marge/délai).
 *
 * Une valeur NÉGATIVE n'est jamais masquée ni tronquée à 0 : le backend a déjà corrigé le bug
 * de délais négatifs découvert en vérifiant les données réelles (implementation.md § J3
 * Backend) — si une valeur négative apparaît malgré tout, elle reste visible, préfixée `-`,
 * pour rester détectable plutôt que silencieusement aplatie.
 */
export function formatDurationHours(hours: number | null | undefined): string {
  if (hours === null || hours === undefined || Number.isNaN(hours)) {
    return "—";
  }
  const sign = hours < 0 ? "-" : "";
  const abs = Math.abs(hours);
  if (abs < 24) {
    return `${sign}${formatHourValue(abs)} h`;
  }
  const days = Math.floor(abs / 24);
  const remainingHours = Math.round(abs % 24);
  return `${sign}${days} j ${remainingHours} h`;
}

function formatHourValue(hours: number): string {
  // Une décimale, virgule française — pas d'arrondi trompeur sur des délais courts (ex. 2,3 h).
  return hours.toLocaleString("fr-FR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
}
