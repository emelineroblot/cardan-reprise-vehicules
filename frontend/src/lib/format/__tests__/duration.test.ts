import { describe, expect, it } from "vitest";
import { formatDurationHours } from "@/lib/format/duration";

describe("formatDurationHours", () => {
  it("affiche un tiret pour null (jamais 0 h) — pas de délai atteint, mart_cycle_temps", () => {
    expect(formatDurationHours(null)).toBe("—");
  });

  it("affiche un tiret pour undefined", () => {
    expect(formatDurationHours(undefined)).toBe("—");
  });

  it("formate zéro correctement (à distinguer de l'absence de valeur)", () => {
    expect(formatDurationHours(0)).toBe("0,0 h");
  });

  it("formate un délai court en heures avec une décimale", () => {
    expect(formatDurationHours(4.5)).toBe("4,5 h");
  });

  it("formate un délai proche de 24h sans bascule en jours", () => {
    expect(formatDurationHours(23.9)).toBe("23,9 h");
  });

  it("bascule en jours + heures à partir de 24h", () => {
    expect(formatDurationHours(28)).toBe("1 j 4 h");
  });

  it("formate un délai de plusieurs jours", () => {
    expect(formatDurationHours(76)).toBe("3 j 4 h");
  });

  it("ne masque jamais une valeur négative (bug de seed déjà corrigé côté backend, à détecter si elle réapparaît)", () => {
    expect(formatDurationHours(-5)).toBe("-5,0 h");
  });

  it("préserve le signe négatif au-delà de 24h", () => {
    expect(formatDurationHours(-30)).toBe("-1 j 6 h");
  });
});
