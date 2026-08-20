import { expect, test } from "@playwright/test";

/**
 * Parcours J1 (plan.md § 6 vague 4) : login opératrice → SIRET → lot de 3 → doublon →
 * arbitrage → liste.
 *
 * Exécuté pour la première fois contre le backend + le jeu de démo réels (vague 5) — les
 * valeurs ci-dessous ne sont plus des placeholders, elles ont été vérifiées contre la base
 * seedée (`python -m app.cli demo-reset`) :
 * - `DEMO_SIRET` = SIRET de « Benard SARL », précaché `source = 'demo'` dans
 *   `company_lookup_cache` — et déjà une société opérationnelle du jeu de démo. C'est le
 *   cas nominal, pas une exception : tous les SIRET précachés en démo ont déjà une fiche
 *   société (le seed les précache justement parce qu'ils ont des véhicules). `SocieteStep`
 *   réutilise donc la société existante sur un `409 conflict` (`GET /companies/{id}` avec
 *   `details.company_id`) plutôt que d'échouer.
 * - Le 3ᵉ véhicule du lot (Kangoo essence, ~120 500 km, sans immatriculation) est
 *   volontairement très proche de l'unique Renault Kangoo déjà enregistrée pour cette
 *   société (essence, ~120 279 km, proposée il y a une quinzaine de jours) : ces deux fiches
 *   scorent au-dessus du seuil `duplicate_probable` (≥ 0,85 — plan.md § 4 décision A étape
 *   4), avec une marge suffisante pour rester robuste au reset nocturne (les dates du seed
 *   sont recalculées relativement à `date.today()`, l'écart en jours reste stable).
 */
const DEMO_SIRET = "11951548967612"; // Benard SARL

test.describe("J1 — saisie opératrice", () => {
  test("login → SIRET → lot de 3 véhicules → arbitrage doublon → liste", async ({ page }) => {
    // 1. Connexion en un clic (plan.md § 3.4)
    await page.goto("/login");
    await page
      .getByRole("button", { name: /Se connecter en tant que Opératrice/i })
      .click();
    await expect(page).toHaveURL(/\/vehicules$/);

    // 2. Nouvelle fiche d'achat — locator strict : la nav porte aussi un lien "Nouvelle
    // fiche d'achat" (AppNav) qui matcherait sinon en recherche non-exacte.
    await page.getByRole("link", { name: "Nouvelle fiche", exact: true }).click();
    await expect(page).toHaveURL(/\/fiches\/nouvelle$/);

    // 3. Étape société — SIRET de démo, remplissage automatique
    await page.getByLabel("Numéro SIRET").fill(DEMO_SIRET);
    await page.getByRole("button", { name: "Rechercher" }).click();

    await expect(page.getByText(/Source : jeu de démonstration/i)).toBeVisible();

    await page.getByLabel("Type de flotte").click();
    await page.getByRole("option", { name: "Taxi" }).click();
    await page.getByRole("button", { name: "Valider cette société" }).click();

    // 4. Étape véhicule — mode lot (3 véhicules)
    await expect(page.getByText(/^Société :/)).toBeVisible();

    await page.getByRole("button", { name: "Ajouter un véhicule à ce lot" }).click();
    await page.getByRole("button", { name: "Ajouter un véhicule à ce lot" }).click();
    await expect(page.getByRole("heading", { name: "Véhicule 3 du lot" })).toBeVisible();

    const vehicules = [
      { marque: "Renault", modele: "Kangoo", immat: "AA-111-BB" },
      { marque: "Renault", modele: "Kangoo", immat: "AA-222-BB" },
      // Volontairement très proche de l'unique Kangoo déjà enregistrée pour Benard SARL
      // dans le jeu de démo (même marque/modèle, kilométrage voisin, énergie identique,
      // date proche, sans immatriculation ni VIN) pour déclencher `duplicate_probable`
      // (plan.md § 4 décision A étape 4) — score ≈ 0,94, voir le commentaire en tête de
      // fichier.
      { marque: "Renault", modele: "Kangoo", immat: null, kilometrage: "120500", energie: "Essence" },
    ];

    for (const [index, vehicule] of vehicules.entries()) {
      const section = page.getByRole("region", { name: new RegExp(`Véhicule ${index + 1}`) });
      await section.getByLabel("Marque").fill(vehicule.marque);
      await section.getByLabel("Modèle").fill(vehicule.modele);
      if (vehicule.immat) {
        await section.getByLabel("Immatriculation").fill(vehicule.immat);
        await section.getByLabel("Immatriculation").blur();
      }
      if (vehicule.kilometrage) {
        await section.getByLabel("Kilométrage").fill(vehicule.kilometrage);
      }
      if (vehicule.energie) {
        await section.getByLabel("Énergie").click();
        await page.getByRole("option", { name: vehicule.energie }).click();
      }
    }

    await page
      .getByRole("button", { name: /Enregistrer le lot \(3 véhicules\)/ })
      .click();

    // 5. Écran d'arbitrage — doublon probable sur le 3e véhicule
    const arbitrage = page.getByRole("dialog", { name: /Doublon potentiel/i });
    await expect(arbitrage).toBeVisible({ timeout: 15_000 });
    await expect(arbitrage.getByText(/Détail du score de similarité/)).toBeVisible();
    await arbitrage.getByRole("button", { name: "Ce n'est pas un doublon" }).click();
    await expect(arbitrage).toBeHidden();

    // 6. Confirmation puis retour à la liste
    await expect(page.getByText(/fiche.*enregistrée/i)).toBeVisible({ timeout: 15_000 });
    await page.getByRole("button", { name: "Voir la liste de suivi" }).click();
    await expect(page).toHaveURL(/\/vehicules$/);

    // 7. Liste filtrable — URL partageable. Locator par rôle : le tableau porte aussi un
    // bouton de tri "Trier par État" (aria-label), que `getByLabel("État")` matcherait aussi.
    await page.getByRole("combobox", { name: "État" }).click();
    await page.getByRole("option", { name: "Brouillon" }).click();
    await expect(page).toHaveURL(/state=BROUILLON/);
    await expect(page.getByRole("table")).toBeVisible();
  });
});
