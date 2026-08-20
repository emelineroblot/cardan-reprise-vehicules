/**
 * Montants — toujours des entiers de centimes côté API (plan.md § 3.5, suffixe `_cents`).
 * Jamais de flottant sur de l'argent : toute la conversion vit ici, au bord de l'UI.
 */

const EUR_FORMATTER = new Intl.NumberFormat("fr-FR", {
  style: "currency",
  currency: "EUR",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** Formate des centimes entiers en « 1 234,56 € ». `null`/`undefined` → « — ». */
export function formatMoneyCents(cents: number | null | undefined): string {
  if (cents === null || cents === undefined || Number.isNaN(cents)) {
    return "—";
  }
  return EUR_FORMATTER.format(cents / 100);
}

/** Convertit une saisie utilisateur en euros (chaîne, virgule ou point) en centimes entiers. */
export function parseEurosToCents(input: string): number | null {
  const trimmed = input.trim().replace(/\s/g, "").replace(/€/g, "");
  if (trimmed === "") return null;
  const normalized = trimmed.replace(",", ".");
  const value = Number(normalized);
  if (!Number.isFinite(value)) return null;
  return Math.round(value * 100);
}

/** Convertit des centimes en une chaîne éditable dans un champ (« 1234.56 », pas de symbole). */
export function centsToEditableString(cents: number | null | undefined): string {
  if (cents === null || cents === undefined) return "";
  return (cents / 100).toFixed(2);
}
