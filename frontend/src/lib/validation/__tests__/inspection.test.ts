import { describe, expect, it } from "vitest";
import { isItemAnswered, missingAngles, missingRequiredItems } from "@/lib/validation/inspection";
import type { ChecklistItemTemplate } from "@/lib/api/types";
import type { LocalItemAnswer } from "@/lib/offline/types";

function item(overrides: Partial<ChecklistItemTemplate>): ChecklistItemTemplate {
  return {
    id: overrides.id ?? "item-1",
    template_id: "template-1",
    code: overrides.code ?? "code-1",
    libelle: overrides.libelle ?? "Libellé",
    categorie: overrides.categorie ?? "exterieur",
    ordre: overrides.ordre ?? 1,
    is_required: overrides.is_required ?? true,
    response_type: overrides.response_type ?? "ok_ko",
  };
}

describe("isItemAnswered", () => {
  it("est faux sans réponse locale", () => {
    expect(isItemAnswered(undefined)).toBe(false);
  });

  it("détecte une réponse ok_ko même à false (pas un truthy check naïf)", () => {
    const answer: LocalItemAnswer = { item_template_id: "item-1", valeur_bool: false };
    expect(isItemAnswered(answer)).toBe(true);
  });

  it("détecte une note", () => {
    expect(isItemAnswered({ item_template_id: "item-1", valeur_note: 3 })).toBe(true);
  });

  it("ignore un texte vide ou uniquement des espaces", () => {
    expect(isItemAnswered({ item_template_id: "item-1", valeur_texte: "   " })).toBe(false);
    expect(isItemAnswered({ item_template_id: "item-1", valeur_texte: "ok" })).toBe(true);
  });

  it("détecte une valeur numérique à zéro (pas un truthy check naïf)", () => {
    expect(isItemAnswered({ item_template_id: "item-1", valeur_num: 0 })).toBe(true);
  });
});

describe("missingRequiredItems", () => {
  it("liste les items obligatoires sans réponse, par code", () => {
    const items = [
      item({ id: "a", code: "pneus", is_required: true }),
      item({ id: "b", code: "phares", is_required: true }),
      item({ id: "c", code: "clim", is_required: false }),
    ];
    const answers: Record<string, LocalItemAnswer> = {
      a: { item_template_id: "a", valeur_bool: true },
    };
    expect(missingRequiredItems(items, answers)).toEqual(["phares"]);
  });

  it("ne réclame jamais un item optionnel", () => {
    const items = [item({ id: "a", code: "clim", is_required: false })];
    expect(missingRequiredItems(items, {})).toEqual([]);
  });

  it("renvoie un tableau vide quand tout est répondu", () => {
    const items = [item({ id: "a", code: "pneus", is_required: true })];
    const answers = { a: { item_template_id: "a", valeur_bool: true } };
    expect(missingRequiredItems(items, answers)).toEqual([]);
  });
});

describe("missingAngles", () => {
  it("calcule la différence ensembliste triviale", () => {
    const required = ["face_avant", "face_arriere", "coffre"];
    const captured = ["face_avant"];
    expect(missingAngles(required, captured)).toEqual(["face_arriere", "coffre"]);
  });

  it("est vide quand tous les angles requis sont capturés", () => {
    expect(missingAngles(["face_avant"], ["face_avant", "coffre"])).toEqual([]);
  });
});
