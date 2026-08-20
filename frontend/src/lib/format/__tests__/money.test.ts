import { describe, expect, it } from "vitest";
import { centsToEditableString, formatMoneyCents, parseEurosToCents } from "@/lib/format/money";

// Intl.NumberFormat("fr-FR", { style: "currency" }) insère des espaces insécables
// (U+202F entre groupes de milliers, U+00A0 avant le symbole €) : on compare toujours
// à la sortie du même formateur plutôt qu'à une chaîne recopiée à la main.
const eur = (value: number) =>
  new Intl.NumberFormat("fr-FR", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);

describe("formatMoneyCents", () => {
  it("formate des centimes entiers en euros avec virgule française", () => {
    expect(formatMoneyCents(123456)).toBe(eur(1234.56));
  });

  it("formate zéro correctement (à distinguer de l'absence de valeur)", () => {
    expect(formatMoneyCents(0)).toBe(eur(0));
  });

  it("affiche un tiret pour null (jamais 0 €) — plan.md § 5.2", () => {
    expect(formatMoneyCents(null)).toBe("—");
  });

  it("affiche un tiret pour undefined", () => {
    expect(formatMoneyCents(undefined)).toBe("—");
  });

  it("gère les montants négatifs (marge négative possible, plan.md § 5.2)", () => {
    expect(formatMoneyCents(-50000)).toBe(eur(-500));
  });
});

describe("parseEurosToCents", () => {
  it("convertit une saisie avec virgule en centimes", () => {
    expect(parseEurosToCents("12,50")).toBe(1250);
  });

  it("convertit une saisie avec point en centimes", () => {
    expect(parseEurosToCents("12.5")).toBe(1250);
  });

  it("ignore les espaces et le symbole €", () => {
    expect(parseEurosToCents("1 234,56 €")).toBe(123456);
  });

  it("renvoie null pour une saisie vide", () => {
    expect(parseEurosToCents("")).toBeNull();
  });

  it("renvoie null pour une saisie non numérique", () => {
    expect(parseEurosToCents("abc")).toBeNull();
  });

  it("arrondit les fractions de centime", () => {
    expect(parseEurosToCents("12,505")).toBe(1251);
  });
});

describe("centsToEditableString", () => {
  it("convertit des centimes en chaîne éditable à deux décimales", () => {
    expect(centsToEditableString(123456)).toBe("1234.56");
  });

  it("renvoie une chaîne vide pour null", () => {
    expect(centsToEditableString(null)).toBe("");
  });

  it("aller-retour parse -> format préserve la valeur", () => {
    const cents = parseEurosToCents("999,99");
    expect(centsToEditableString(cents)).toBe("999.99");
  });
});
