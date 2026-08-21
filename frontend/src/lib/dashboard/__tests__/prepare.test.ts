import { describe, expect, it } from "vitest";
import {
  buildCycleTempsChartData,
  buildMargeChartData,
  buildPipelineEtatChartData,
  buildRefusSeries,
  buildTravauxSeries,
  countMissingMarge,
  selectTopMarge,
} from "@/lib/dashboard/prepare";
import type { CycleTemps, PipelineEtat, Refus, Travaux, VehiculeMarge } from "@/lib/api/types";

function marge(overrides: Partial<VehiculeMarge>): VehiculeMarge {
  return {
    vehicle_id: "v1",
    reference: "REF-1",
    company_id: "c1",
    company_denomination: "Société Test",
    state: "ACHAT_VALIDE",
    state_label: "Achat validé",
    marque: "Renault",
    modele: "Kangoo",
    date_proposition: "2026-06-01",
    prix_achat_negocie_cents: 500000,
    frais_transport_cents: 5000,
    valeur_revente_estimee_cents: 600000,
    cout_hors_atelier_cents: 0,
    cout_atelier_reel_cents: 0,
    marge_cents: 95000,
    marge_pct: 15.83,
    has_marge: true,
    ...overrides,
  };
}

describe("selectTopMarge / buildMargeChartData", () => {
  it("exclut les véhicules sans valeur de revente estimée (has_marge = false), jamais affichés comme une marge à 0", () => {
    const rows = [
      marge({ vehicle_id: "a", marge_cents: 10000, has_marge: true }),
      marge({ vehicle_id: "b", marge_cents: null, marge_pct: null, has_marge: false }),
    ];
    const selected = selectTopMarge(rows);
    expect(selected.map((r) => r.vehicle_id)).toEqual(["a"]);
    expect(countMissingMarge(rows)).toBe(1);
  });

  it("conserve les marges négatives telles quelles, sans écrêtage à 0", () => {
    const rows = [marge({ vehicle_id: "neg", marge_cents: -33210, has_marge: true })];
    const chart = buildMargeChartData(rows);
    expect(chart[0].value).toBe(-33210);
    expect(chart[0].formattedValue).toContain("-");
  });

  it("trie par valeur absolue décroissante, positif et négatif mélangés", () => {
    const rows = [
      marge({ vehicle_id: "small-pos", marge_cents: 1000 }),
      marge({ vehicle_id: "big-neg", marge_cents: -50000 }),
      marge({ vehicle_id: "mid-pos", marge_cents: 20000 }),
    ];
    const chart = buildMargeChartData(rows);
    expect(chart.map((d) => d.id)).toEqual(["big-neg", "mid-pos", "small-pos"]);
  });

  it("respecte la limite demandée", () => {
    const rows = Array.from({ length: 20 }, (_, i) => marge({ vehicle_id: `v${i}`, marge_cents: i * 100 }));
    expect(buildMargeChartData(rows, 5)).toHaveLength(5);
  });

  it("ne renvoie rien si toutes les lignes sont sans marge", () => {
    const rows = [marge({ vehicle_id: "a", marge_cents: null, has_marge: false })];
    expect(buildMargeChartData(rows)).toHaveLength(0);
    expect(countMissingMarge(rows)).toBe(1);
  });
});

describe("buildPipelineEtatChartData", () => {
  it("ordonne selon la séquence du pipeline, pas selon la magnitude", () => {
    const rows: PipelineEtat[] = [
      { state: "ACHAT_VALIDE", nb_vehicules: 3, valeur_immobilisee_cents: 900000 },
      { state: "BROUILLON", nb_vehicules: 1, valeur_immobilisee_cents: 10000 },
    ];
    const chart = buildPipelineEtatChartData(rows);
    expect(chart.map((d) => d.id)).toEqual(["BROUILLON", "ACHAT_VALIDE"]);
  });

  it("omet les états absents de la réponse plutôt que d'inventer une valeur à 0", () => {
    const rows: PipelineEtat[] = [{ state: "REFUSE", nb_vehicules: 2, valeur_immobilisee_cents: 0 }];
    const chart = buildPipelineEtatChartData(rows);
    expect(chart).toHaveLength(1);
    expect(chart[0].id).toBe("REFUSE");
  });
});

function cycleTemps(overrides: Partial<CycleTemps>): CycleTemps {
  return {
    vehicle_id: "v1",
    reference: "REF-1",
    state: "ACHAT_VALIDE",
    marque: "Renault",
    modele: "Kangoo",
    delai_saisie_affectation_heures: 10,
    delai_affectation_controle_heures: 20,
    delai_controle_decision_heures: 30,
    delai_total_heures: 60,
    ...overrides,
  };
}

describe("buildCycleTempsChartData", () => {
  it("exclut les véhicules qui n'ont pas encore atteint de décision (delai_total_heures null)", () => {
    const rows = [
      cycleTemps({ vehicle_id: "done", delai_total_heures: 60 }),
      cycleTemps({ vehicle_id: "pending", delai_total_heures: null }),
    ];
    const chart = buildCycleTempsChartData(rows);
    expect(chart.map((r) => r.id)).toEqual(["done"]);
  });

  it("traite une étape non atteinte (null) comme un segment de valeur 0, jamais une exception", () => {
    const rows = [
      cycleTemps({
        vehicle_id: "partial",
        delai_saisie_affectation_heures: 5,
        delai_affectation_controle_heures: null,
        delai_controle_decision_heures: 15,
        delai_total_heures: 20,
      }),
    ];
    const chart = buildCycleTempsChartData(rows);
    expect(chart[0].segments.map((s) => s.value)).toEqual([5, 0, 15]);
  });

  it("trie du délai le plus long au plus court et respecte la limite", () => {
    const rows = [
      cycleTemps({ vehicle_id: "short", delai_total_heures: 10 }),
      cycleTemps({ vehicle_id: "long", delai_total_heures: 100 }),
    ];
    const chart = buildCycleTempsChartData(rows, 1);
    expect(chart).toHaveLength(1);
    expect(chart[0].id).toBe("long");
  });
});

describe("buildRefusSeries", () => {
  const labels = { taxi: "Taxi", ambulance: "Ambulance", transport: "Transport", auto_ecole: "Auto-école", location: "Location", autre: "Autre" };

  it("laisse un mois sans donnée à null plutôt que de l'interpoler à 0", () => {
    const rows: Refus[] = [
      { mois: "2026-05-01", type_flotte: "taxi", nb_proposes: 4, nb_refuses: 1, taux_refus: 0.25 },
      { mois: "2026-06-01", type_flotte: "taxi", nb_proposes: 0, nb_refuses: 0, taux_refus: null },
    ];
    const { xLabels, series } = buildRefusSeries(rows, labels);
    expect(xLabels).toHaveLength(2);
    expect(series[0].values).toEqual([0.25, null]);
  });

  it("crée une série distincte par type de flotte présent dans les données", () => {
    const rows: Refus[] = [
      { mois: "2026-05-01", type_flotte: "taxi", nb_proposes: 4, nb_refuses: 1, taux_refus: 0.25 },
      { mois: "2026-05-01", type_flotte: "ambulance", nb_proposes: 2, nb_refuses: 0, taux_refus: 0 },
    ];
    const { series } = buildRefusSeries(rows, labels);
    expect(series.map((s) => s.key).sort()).toEqual(["ambulance", "taxi"]);
  });
});

describe("buildTravauxSeries", () => {
  const labels = { carrosserie: "Carrosserie", mecanique: "Mécanique", nettoyage: "Nettoyage", pneumatiques: "Pneumatiques", autre: "Autre" };

  it("laisse un type sans ordre clos ce mois-là à null (jamais 0)", () => {
    const rows: Travaux[] = [
      { mois: "2026-05-01", type: "mecanique", volume: 3, nb_clos: 2, cout_moyen_reel_cents: 45000, ecart_estime_reel_cents: 2000 },
      { mois: "2026-06-01", type: "mecanique", volume: 1, nb_clos: 0, cout_moyen_reel_cents: null, ecart_estime_reel_cents: null },
    ];
    const { series } = buildTravauxSeries(rows, labels);
    expect(series[0].values).toEqual([45000, null]);
  });
});
