import { describe, expect, it } from "vitest";
import { computeTargetDimensions } from "@/lib/offline/image";

describe("computeTargetDimensions", () => {
  it("laisse une image déjà sous le seuil inchangée", () => {
    expect(computeTargetDimensions(800, 600)).toEqual({ width: 800, height: 600 });
  });

  it("ramène le côté long à 1600 px en conservant le ratio (paysage)", () => {
    const result = computeTargetDimensions(4000, 3000);
    expect(result.width).toBe(1600);
    expect(result.height).toBe(1200);
  });

  it("ramène le côté long à 1600 px en conservant le ratio (portrait)", () => {
    const result = computeTargetDimensions(3000, 4000);
    expect(result.width).toBe(1200);
    expect(result.height).toBe(1600);
  });

  it("respecte un maxSide personnalisé", () => {
    expect(computeTargetDimensions(2000, 1000, 800)).toEqual({ width: 800, height: 400 });
  });

  it("ne produit jamais une dimension nulle sur une image carrée juste au-dessus du seuil", () => {
    const result = computeTargetDimensions(1601, 1601);
    expect(result.width).toBeGreaterThan(0);
    expect(result.height).toBeGreaterThan(0);
  });

  it("dégrade proprement sur des dimensions invalides plutôt que de lever", () => {
    expect(computeTargetDimensions(0, 0)).toEqual({ width: 0, height: 0 });
    expect(computeTargetDimensions(-10, 500)).toEqual({ width: 0, height: 0 });
  });
});
