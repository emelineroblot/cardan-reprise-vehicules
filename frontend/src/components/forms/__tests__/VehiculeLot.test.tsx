import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

import { VehiculeLot } from "@/components/forms/VehiculeLot";
import type { Company, DuplicateCandidate, Vehicle } from "@/lib/api/types";

/**
 * Régression review-finale.md § 🟠 VehiculeLot (jalon J1, corrigée par dev-frontend en passe
 * de correction) : si `POST /duplicate-reviews` échoue APRÈS un `POST /vehicles` réussi, le
 * véhicule doit rester compté comme créé — jamais comme « non enregistré », ce qui pousserait
 * l'opératrice à ressaisir une fiche qui existe déjà (un vrai doublon, créé par l'outil censé
 * les détecter). Aucun test ne couvrait ce chemin avant ce correctif.
 */

const COMPANY: Company = {
  id: "c0000000-0000-0000-0000-000000000001",
  siret: "12345678901234",
  siren: "123456789",
  denomination: "Taxis Réunis",
  forme_juridique: "SARL",
  adresse_ligne1: "1 rue du Test",
  code_postal: "75001",
  commune: "Paris",
  pays: "France",
  code_naf: "4932Z",
  libelle_naf: "Transports de voyageurs par taxis",
  tranche_effectif: "10 à 19 salariés",
  date_creation: "2010-01-01",
  contact_nom: "Jean Test",
  contact_telephone: "0600000000",
  type_flotte: "taxi",
  source_enrichissement: "manuel",
  enriched_at: null,
  created_by_id: "u0000000-0000-0000-0000-000000000001",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const EXISTING_CANDIDATE: DuplicateCandidate = {
  vehicle_id: "v0000000-0000-0000-0000-0000000000ex",
  reference: "VH-2026-00001",
  marque: "Renault",
  modele: "Kangoo",
  version: null,
  energie: null,
  vin: null,
  immatriculation: null,
  kilometrage: null,
  date_mise_en_circulation: null,
  date_proposition: "2026-08-19",
  created_at: "2026-08-19T10:00:00Z",
  state: "BROUILLON",
  refus_motif: null,
  refus_commentaire: null,
  score: 0.9,
  features: { s_modele: 1, s_date: 0.9, s_km: 0.8, s_energie: 1, bonus_terminal: 0 },
};

const CREATED_VEHICLE_RAW = {
  id: "v0000000-0000-0000-0000-0000000000nw",
  reference: "VH-2026-00042",
  company_id: COMPANY.id,
  company: { id: COMPANY.id, denomination: COMPANY.denomination, siret: COMPANY.siret },
  intake_batch_id: null,
  state: "BROUILLON",
  marque: "Renault",
  modele: "Kangoo",
  version: null,
  energie: null,
  boite: null,
  couleur: null,
  vin: null,
  immatriculation: null,
  date_mise_en_circulation: null,
  kilometrage: null,
  date_proposition: "2026-08-20",
  prix_achat_negocie_cents: null,
  valeur_revente_estimee_cents: null,
  frais_transport_cents: 0,
  commentaire: null,
  created_by_id: "u0000000-0000-0000-0000-000000000001",
  assigned_driver_id: null,
  refus_motif: null,
  refus_commentaire: null,
  state_changed_at: "2026-08-20T10:00:00Z",
  created_at: "2026-08-20T10:00:00Z",
  updated_at: "2026-08-20T10:00:00Z",
  state_history: [] as unknown[],
};

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function renderVehiculeLot(onCompleted: (created: Vehicle[]) => void) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <VehiculeLot company={COMPANY} onCompleted={onCompleted} />
    </QueryClientProvider>,
  );
}

describe("VehiculeLot — échec de POST /duplicate-reviews après un POST /vehicles réussi", () => {
  it("compte la fiche comme créée, ne dit jamais qu'elle n'est pas enregistrée", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/vehicles/duplicate-check")) {
        return jsonResponse({ exact: [], probable: [EXISTING_CANDIDATE], similar: [] }, 200);
      }
      if (url.endsWith("/duplicate-reviews")) {
        // Le second appel du flux en deux temps échoue — le véhicule, lui, a déjà été créé.
        return jsonResponse(
          { error: { code: "internal_error", message: "Erreur inattendue du serveur." } },
          500,
        );
      }
      if (url.endsWith("/vehicles")) {
        return jsonResponse(CREATED_VEHICLE_RAW, 201);
      }
      throw new Error(`URL non mockée dans ce test : ${url}`);
    });

    const onCompleted = vi.fn();
    renderVehiculeLot(onCompleted);

    fireEvent.change(screen.getByLabelText("Marque"), { target: { value: "Renault" } });
    fireEvent.change(screen.getByLabelText("Modèle"), { target: { value: "Kangoo" } });

    fireEvent.click(screen.getByRole("button", { name: "Enregistrer la fiche" }));

    // L'écran d'arbitrage s'ouvre sur le candidat probable renvoyé par duplicate-check.
    const notDuplicateButton = await screen.findByRole("button", { name: "Ce n'est pas un doublon" });
    fireEvent.click(notDuplicateButton);

    // Le véhicule existe déjà en base à ce stade (POST /vehicles a réussi) — le
    // récapitulatif doit le compter comme créé, jamais comme non enregistré.
    await waitFor(() => {
      expect(screen.getByText(/1 fiche enregistrée/)).toBeInTheDocument();
    });

    expect(screen.queryByText(/0 fiche enregistrée/)).not.toBeInTheDocument();
    expect(screen.getByText(/arbitrage non enregistré/)).toBeInTheDocument();
    expect(screen.getByText(new RegExp(CREATED_VEHICLE_RAW.reference))).toBeInTheDocument();

    // Le véhicule créé est bien transmis à l'appelant (utilisé pour la suite du parcours) —
    // jamais perdu parce que l'arbitrage, lui, a échoué.
    expect(onCompleted).toHaveBeenCalledTimes(1);
    expect(onCompleted).toHaveBeenCalledWith([expect.objectContaining({ id: CREATED_VEHICLE_RAW.id })]);

    fetchSpy.mockRestore();
  });
});
