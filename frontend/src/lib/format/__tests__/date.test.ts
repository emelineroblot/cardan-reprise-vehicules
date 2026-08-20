import { describe, expect, it } from "vitest";
import { formatDate, formatDateTime, toDateInputValue } from "@/lib/format/date";

describe("formatDate", () => {
  it("formate une date ISO en jj/mm/aaaa", () => {
    expect(formatDate("2026-08-20")).toBe("20/08/2026");
  });

  it("affiche un tiret pour une valeur nulle", () => {
    expect(formatDate(null)).toBe("—");
  });

  it("affiche un tiret pour une valeur undefined", () => {
    expect(formatDate(undefined)).toBe("—");
  });

  it("affiche un tiret pour une date invalide plutôt que de planter", () => {
    expect(formatDate("pas-une-date")).toBe("—");
  });
});

describe("formatDateTime", () => {
  it("formate un horodatage ISO UTC en date + heure locale", () => {
    // Comparaison structurelle (jj/mm/aaaa hh:mm) plutôt qu'à une chaîne figée,
    // le fuseau d'exécution du test n'étant pas garanti.
    expect(formatDateTime("2026-08-20T14:32:00Z")).toMatch(/^\d{2}\/\d{2}\/\d{4} \d{2}:\d{2}$/);
  });

  it("affiche un tiret pour une valeur nulle", () => {
    expect(formatDateTime(null)).toBe("—");
  });
});

describe("toDateInputValue", () => {
  it("convertit une Date locale en chaîne ISO YYYY-MM-DD sans dérive de fuseau", () => {
    const date = new Date(2026, 7, 20); // 20 août 2026, mois 0-indexé
    expect(toDateInputValue(date)).toBe("2026-08-20");
  });

  it("préfixe les mois et jours à un chiffre avec un zéro", () => {
    const date = new Date(2026, 0, 5); // 5 janvier 2026
    expect(toDateInputValue(date)).toBe("2026-01-05");
  });
});
