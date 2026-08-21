/**
 * Rôles de couleur du tableau de bord (skill `dataviz`, palette de référence — voir
 * `globals.css` § « Palette dataviz »). 8 teintes catégorielles à ORDRE FIXE : ne jamais les
 * permuter, cycler, ni en assigner une 9ᵉ générée. Chaque `var(--viz-N)` porte déjà son couple
 * clair/sombre (défini une fois dans `:root`/`.dark`) — un composant de chart ne choisit jamais
 * un hex directement.
 */

/** Ordre catégoriel fixe — slot 1..8. Assigné en séquence, jamais par rang/valeur (règle
 * anti-pattern « recolor-on-filter » : un filtre qui change le nombre de séries ne doit
 * jamais repeindre les survivantes). */
export const VIZ_CATEGORICAL = [
  "var(--viz-1)",
  "var(--viz-2)",
  "var(--viz-3)",
  "var(--viz-4)",
  "var(--viz-5)",
  "var(--viz-6)",
  "var(--viz-7)",
  "var(--viz-8)",
] as const;

/** Diverging pair (blue ↔ red) — marge positive / négative, jamais réutilisé comme identité. */
export const VIZ_DIVERGING = {
  positive: "var(--viz-1)",
  negative: "var(--viz-8)",
  mid: "var(--viz-diverging-mid)",
} as const;

/** Séquentiel par défaut (magnitude, un seul hue) — pipeline (valeur immobilisée), travaux. */
export const VIZ_SEQUENTIAL = "var(--viz-1)";

/** Réservé au sens bon/mauvais (écart estimé/réel) — toujours icône + libellé, jamais seul. */
export const VIZ_STATUS = {
  good: "var(--viz-status-good)",
  warning: "var(--viz-status-warning)",
  serious: "var(--viz-status-serious)",
  critical: "var(--viz-status-critical)",
} as const;
