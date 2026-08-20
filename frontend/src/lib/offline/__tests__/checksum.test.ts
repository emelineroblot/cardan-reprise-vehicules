import { describe, expect, it } from "vitest";
import { sha256Hex } from "@/lib/offline/checksum";

describe("sha256Hex", () => {
  it("produit le sha256 hexadécimal attendu d'un contenu connu", async () => {
    // sha256("cardan") — valeur de référence calculée indépendamment (openssl), pour
    // vérifier que l'encodage hex ne décale rien (padding des octets < 0x10).
    const blob = new Blob(["cardan"], { type: "text/plain" });
    const hex = await sha256Hex(blob);
    expect(hex).toBe("fea0266b345796ec6803417b8709764ebb490eb08ce51db08f46437c9ed84bc1");
  });
});
