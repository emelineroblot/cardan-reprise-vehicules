import { describe, expect, it } from "vitest";
import { isValidSiretChecksum, isValidSiretFormat, normalizeSiret } from "@/lib/validation/siret";

/**
 * Pré-validation client (plan.md § 4 décision B). Ce n'est pas l'autorité — le lookup
 * serveur rejoue la validation — mais une erreur ici renverrait un mauvais signal à
 * l'opératrice avant même l'appel réseau, d'où la couverture par table de cas.
 */
describe("isValidSiretFormat", () => {
  it("accepte 14 chiffres", () => {
    expect(isValidSiretFormat("73282932000074")).toBe(true);
  });

  it("rejette un nombre de chiffres différent de 14", () => {
    expect(isValidSiretFormat("123")).toBe(false);
    expect(isValidSiretFormat("732829320000745")).toBe(false);
  });

  it("rejette les caractères non numériques", () => {
    expect(isValidSiretFormat("7328293200007A")).toBe(false);
  });
});

describe("isValidSiretChecksum", () => {
  it("valide un SIRET correct (clé de Luhn)", () => {
    expect(isValidSiretChecksum("73282932000074")).toBe(true);
    expect(isValidSiretChecksum("55208131766522")).toBe(true);
  });

  it("rejette un SIRET dont la clé de Luhn est fausse", () => {
    expect(isValidSiretChecksum("12345678901234")).toBe(false);
  });

  it("rejette un format invalide sans planter", () => {
    expect(isValidSiretChecksum("abc")).toBe(false);
  });

  it("applique l'exception La Poste (SIREN 356000000 : somme des chiffres multiple de 5)", () => {
    expect(isValidSiretChecksum("35600000000001")).toBe(true);
    // Un NIC choisi pour lequel la somme n'est pas multiple de 5.
    expect(isValidSiretChecksum("35600000000002")).toBe(false);
  });
});

describe("normalizeSiret", () => {
  it("retire les espaces", () => {
    expect(normalizeSiret(" 732 829 320 00074 ")).toBe("73282932000074");
  });
});
