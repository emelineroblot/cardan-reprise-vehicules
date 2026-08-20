import { describe, expect, it } from "vitest";
import {
  formatImmatriculation,
  isPlausibleImmatriculation,
  normalizeImmatriculation,
} from "@/lib/format/immatriculation";

describe("normalizeImmatriculation", () => {
  it("met en majuscules et retire espaces et tirets", () => {
    expect(normalizeImmatriculation("aa-123-bb")).toBe("AA123BB");
    expect(normalizeImmatriculation("AA 123 BB")).toBe("AA123BB");
  });
});

describe("isPlausibleImmatriculation", () => {
  it("accepte le format SIV standard", () => {
    expect(isPlausibleImmatriculation("AA-123-BB")).toBe(true);
    expect(isPlausibleImmatriculation("aa123bb")).toBe(true);
  });

  it("rejette un format non reconnu", () => {
    expect(isPlausibleImmatriculation("1234 AB 75")).toBe(false);
    expect(isPlausibleImmatriculation("")).toBe(false);
  });
});

describe("formatImmatriculation", () => {
  it("formate en AA-123-BB pour l'affichage", () => {
    expect(formatImmatriculation("AA123BB")).toBe("AA-123-BB");
  });

  it("affiche un tiret cadratin pour une valeur absente", () => {
    expect(formatImmatriculation(null)).toBe("—");
    expect(formatImmatriculation(undefined)).toBe("—");
  });

  it("renvoie la valeur brute si le format n'est pas reconnu (ex. ancien format FNI)", () => {
    expect(formatImmatriculation("1234 AB 75")).toBe("1234 AB 75");
  });
});
