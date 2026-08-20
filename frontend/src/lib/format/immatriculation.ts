/**
 * Immatriculation — normalisation et affichage.
 *
 * La normalisation qui fait autorité (déduplication, index unique partiel) vit côté
 * backend (`app/services/normalize.py`, plan.md § 4 décision A étape 0). Les fonctions
 * ci-dessous ne servent que l'UI : affichage lisible et pré-validation de saisie.
 */

const SIV_PATTERN = /^[A-Z]{2}[0-9]{3}[A-Z]{2}$/;

/** Majuscule, sans espaces ni tirets — la forme envoyée à l'API. */
export function normalizeImmatriculation(raw: string): string {
  return raw.trim().toUpperCase().replace(/[\s-]/g, "");
}

/** Affichage lisible : `AA123BB` → `AA-123-BB`. Formats non reconnus renvoyés tels quels. */
export function formatImmatriculation(raw: string | null | undefined): string {
  if (!raw) return "—";
  const normalized = normalizeImmatriculation(raw);
  if (SIV_PATTERN.test(normalized)) {
    return `${normalized.slice(0, 2)}-${normalized.slice(2, 5)}-${normalized.slice(5, 7)}`;
  }
  return raw;
}

/** Pré-validation de format (SIV uniquement) — la vérité reste le backend. */
export function isPlausibleImmatriculation(raw: string): boolean {
  return SIV_PATTERN.test(normalizeImmatriculation(raw));
}
