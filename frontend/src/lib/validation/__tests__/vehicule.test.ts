import { describe, expect, it } from "vitest";
import { toVehicleDraft, vehiculeSchema } from "@/lib/validation/vehicule";

const baseValid = {
  marque: "Renault",
  modele: "Kangoo",
  date_proposition: "2026-08-20",
};

describe("vehiculeSchema", () => {
  it("accepte le minimum requis (marque, modèle, date de proposition)", () => {
    const result = vehiculeSchema.safeParse(baseValid);
    expect(result.success).toBe(true);
  });

  it("refuse une marque vide", () => {
    const result = vehiculeSchema.safeParse({ ...baseValid, marque: "" });
    expect(result.success).toBe(false);
  });

  it("refuse une date de proposition manquante", () => {
    const withoutDate: Partial<typeof baseValid> = { ...baseValid };
    delete withoutDate.date_proposition;
    const result = vehiculeSchema.safeParse(withoutDate);
    expect(result.success).toBe(false);
  });

  it("refuse un VIN qui n'a pas exactement 17 caractères", () => {
    const result = vehiculeSchema.safeParse({ ...baseValid, vin: "VF1AA000000000001X" });
    expect(result.success).toBe(false);
  });

  it("accepte un VIN de 17 caractères valides", () => {
    const result = vehiculeSchema.safeParse({ ...baseValid, vin: "VF1AA00000A000001" });
    expect(result.success).toBe(true);
  });

  it("refuse un VIN contenant un I, O ou Q", () => {
    const result = vehiculeSchema.safeParse({ ...baseValid, vin: "VF1AA00000I000001" });
    expect(result.success).toBe(false);
  });

  it("accepte une immatriculation au format SIV", () => {
    const result = vehiculeSchema.safeParse({ ...baseValid, immatriculation: "AA-123-BB" });
    expect(result.success).toBe(true);
  });

  it("refuse une immatriculation dans un format non reconnu", () => {
    const result = vehiculeSchema.safeParse({ ...baseValid, immatriculation: "not-a-plate" });
    expect(result.success).toBe(false);
  });

  it("refuse un kilométrage négatif", () => {
    const result = vehiculeSchema.safeParse({ ...baseValid, kilometrage: -1 });
    expect(result.success).toBe(false);
  });

  it("accepte des montants nuls (MoneyInput vide -> null)", () => {
    const result = vehiculeSchema.safeParse({
      ...baseValid,
      prix_achat_negocie_cents: null,
      valeur_revente_estimee_cents: null,
      frais_transport_cents: null,
    });
    expect(result.success).toBe(true);
  });

  it("refuse un prix négatif", () => {
    const result = vehiculeSchema.safeParse({ ...baseValid, prix_achat_negocie_cents: -100 });
    expect(result.success).toBe(false);
  });
});

describe("toVehicleDraft", () => {
  it("convertit les chaînes vides en null pour les champs optionnels", () => {
    const draft = toVehicleDraft(
      { ...baseValid, version: "", couleur: "", commentaire: "" },
      "company-1",
      null,
    );
    expect(draft.version).toBeNull();
    expect(draft.couleur).toBeNull();
    expect(draft.commentaire).toBeNull();
  });

  it("normalise le VIN et l'immatriculation avant envoi", () => {
    const draft = toVehicleDraft(
      { ...baseValid, vin: "vf1aa00000a000001", immatriculation: "aa 123 bb" },
      "company-1",
      null,
    );
    expect(draft.vin).toBe("VF1AA00000A000001");
    expect(draft.immatriculation).toBe("AA123BB");
  });

  it("porte company_id et intake_batch_id", () => {
    const draft = toVehicleDraft(baseValid, "company-1", "batch-1");
    expect(draft.company_id).toBe("company-1");
    expect(draft.intake_batch_id).toBe("batch-1");
  });

  it("intake_batch_id est null hors mode lot", () => {
    const draft = toVehicleDraft(baseValid, "company-1", null);
    expect(draft.intake_batch_id).toBeNull();
  });
});
