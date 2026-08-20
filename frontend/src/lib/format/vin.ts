/**
 * VIN — normalisation d'affichage. Autorité de validation côté backend
 * (17 caractères, `I`/`O`/`Q` interdits — plan.md § 4 décision A étape 0).
 */

const VIN_PATTERN = /^[A-HJ-NPR-Z0-9]{17}$/;

export function normalizeVin(raw: string): string {
  return raw.trim().toUpperCase().replace(/[\s-]/g, "");
}

export function isPlausibleVin(raw: string): boolean {
  return VIN_PATTERN.test(normalizeVin(raw));
}
