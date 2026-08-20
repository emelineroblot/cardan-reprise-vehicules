/**
 * Pré-validation SIRET côté client (format + clé de Luhn, exception La Poste comprise —
 * plan.md § 4 décision B). C'est un confort de saisie : la validation qui fait autorité
 * reste `GET /api/v1/companies/lookup/{siret}` côté backend, rejouée à chaque appel.
 */

const LA_POSTE_SIREN = "356000000";

export function isValidSiretFormat(raw: string): boolean {
  return /^[0-9]{14}$/.test(raw.trim());
}

/** Clé de Luhn, avec l'exception connue de La Poste (SIREN 356000000). */
export function isValidSiretChecksum(raw: string): boolean {
  const siret = raw.trim();
  if (!isValidSiretFormat(siret)) return false;

  const digits = siret.split("").map(Number);
  const siren = siret.slice(0, 9);

  if (siren === LA_POSTE_SIREN) {
    const sum = digits.reduce((total, digit) => total + digit, 0);
    return sum % 5 === 0;
  }

  let sum = 0;
  for (let i = 0; i < digits.length; i += 1) {
    let digit = digits[digits.length - 1 - i];
    if (i % 2 === 1) {
      digit *= 2;
      if (digit > 9) digit -= 9;
    }
    sum += digit;
  }
  return sum % 10 === 0;
}

export function isValidSiret(raw: string): boolean {
  return isValidSiretChecksum(raw);
}

export function normalizeSiret(raw: string): string {
  return raw.trim().replace(/\s/g, "");
}
