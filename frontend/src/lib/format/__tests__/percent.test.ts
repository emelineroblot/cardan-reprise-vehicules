import { describe, expect, it } from "vitest";
import { formatFractionAsPercent, formatPercentagePoints } from "@/lib/format/percent";

describe("formatFractionAsPercent", () => {
  it("convertit une fraction 0-1 en pourcentage (mart_refus.taux_refus)", () => {
    expect(formatFractionAsPercent(0.25)).toBe("25,0 %");
  });

  it("affiche un tiret pour null (aucun véhicule comptabilisable ce mois-là, jamais 0 %)", () => {
    expect(formatFractionAsPercent(null)).toBe("—");
  });

  it("affiche un tiret pour undefined", () => {
    expect(formatFractionAsPercent(undefined)).toBe("—");
  });

  it("gère une fraction nulle réelle (0 refus sur des propositions comptabilisées)", () => {
    expect(formatFractionAsPercent(0)).toBe("0,0 %");
  });
});

describe("formatPercentagePoints", () => {
  it("affiche des points de pourcentage déjà calculés sans les remultiplier (mart_vehicule_marge.marge_pct)", () => {
    expect(formatPercentagePoints(23.45)).toBe("23,5 %");
  });

  it("gère un pourcentage négatif (marge négative)", () => {
    expect(formatPercentagePoints(-12.3)).toBe("-12,3 %");
  });

  it("affiche un tiret pour null (has_marge = false)", () => {
    expect(formatPercentagePoints(null)).toBe("—");
  });
});
