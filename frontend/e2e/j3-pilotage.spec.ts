import path from "node:path";
import { expect, test } from "@playwright/test";

/**
 * Parcours e2e J3 (brief « pilotage-marge ») : atelier → coûts réels → validation d'achat →
 * lecture de la marge dans le tableau de bord. Chauffe le parcours J2 (mission → rendez-vous →
 * contrôle → checklist → photos) pour produire un véhicule frais qui atteint réellement
 * `TRAVAUX_REQUIS`, exerce le mini-automate `work_order` (`demande → en_cours → termine`), la
 * garde véhicule « tous les ordres clos avec ligne de coût », puis vérifie que la marge —
 * coûts d'atelier réels inclus — apparaît dans le tableau de bord administrateur.
 *
 * Nécessite le backend + PostgreSQL démarrés et seedés (référentiel `reference`), comme
 * `j1-saisie.spec.ts`/`j2-terrain.spec.ts`.
 */

const FIXTURE_IMAGE = path.join(__dirname, "..", "public", "icons", "icon-192.png");
const DEMO_SIRET = "11951548967612"; // Benard SARL — voir j1-saisie.spec.ts pour la justification

const REQUIRED_ANGLE_LABELS = [
  "Face avant",
  "3/4 avant gauche",
  "Profil gauche",
  "3/4 arrière gauche",
  "Face arrière",
  "3/4 arrière droit",
  "Profil droit",
  "3/4 avant droit",
  "Intérieur avant",
  "Intérieur arrière",
  "Coffre",
  "Compteur (kilométrage)",
];

const REQUIRED_OK_KO_ITEMS = [
  "Pare-brise sans impact",
  "Démarrage sans anomalie",
  "Niveaux (huile, liquide de refroidissement)",
  "Freinage sans bruit ni vibration",
  "Carte grise présente",
  "Contrôle technique à jour",
];

const REQUIRED_NOTE_ITEMS = [
  "État général de la carrosserie",
  "État des pneumatiques",
  "Propreté intérieure",
  "État de la sellerie",
];

async function login(page: import("@playwright/test").Page, roleLabel: string) {
  await page.goto("/login");
  await page.getByRole("button", { name: new RegExp(`Se connecter en tant que ${roleLabel}`, "i") }).click();
  await expect(page).not.toHaveURL(/\/login$/, { timeout: 10_000 });
}

async function logout(page: import("@playwright/test").Page) {
  await page.getByRole("button", { name: "Se déconnecter" }).click();
  await expect(page).toHaveURL(/\/login$/);
}

test.describe("J3 — pilotage et marge", () => {
  test("atelier → coûts réels → validation d'achat → lecture de la marge dans le tableau de bord", async ({
    page,
  }) => {
    // Parcours long (5 connexions/déconnexions, capture de 12 photos, rafraîchissement de la
    // couche analytique) — au-delà du timeout par défaut de 30 s de playwright.config.ts.
    test.setTimeout(150_000);

    const unique = Date.now();
    const marque = `J3Marque${unique}`;
    const modele = `J3Modele${unique}`;

    // 1. Opératrice — nouvelle fiche, valeur de revente estimée renseignée dès la saisie (seule
    // occasion de le faire : aucun écran ultérieur ne la modifie).
    await login(page, "Opératrice");
    await expect(page).toHaveURL(/\/vehicules$/);
    await page.getByRole("link", { name: "Nouvelle fiche", exact: true }).click();

    await page.getByLabel("Numéro SIRET").fill(DEMO_SIRET);
    await page.getByRole("button", { name: "Rechercher" }).click();
    await expect(page.getByText(/Source : jeu de démonstration/i)).toBeVisible();
    await page.getByLabel("Type de flotte").click();
    await page.getByRole("option", { name: "Taxi" }).click();
    await page.getByRole("button", { name: "Valider cette société" }).click();

    await expect(page.getByText(/^Société :/)).toBeVisible();
    const vehicleSection = page.getByRole("region", { name: "Véhicule" });
    await vehicleSection.getByLabel("Marque").fill(marque);
    await vehicleSection.getByLabel("Modèle").fill(modele);
    await vehicleSection.getByLabel("Valeur de revente estimée").fill("9000");
    await page.getByRole("button", { name: "Enregistrer la fiche" }).click();

    await expect(page.getByText(/fiche.*enregistrée/i)).toBeVisible({ timeout: 15_000 });
    await page.getByRole("button", { name: "Voir la liste de suivi" }).click();
    await expect(page).toHaveURL(/\/vehicules$/);

    // 2. Retrouve la fiche fraîchement créée et la valide (BROUILLON → A_PLANIFIER).
    await page.getByLabel("Recherche libre").fill(modele);
    await page.getByRole("button", { name: "Rechercher" }).click();
    await page.locator("table tbody tr", { hasText: modele }).first().click();
    await expect(page).toHaveURL(/\/vehicules\/[0-9a-f-]+$/);
    const vehicleUrl = page.url();

    await page.getByRole("button", { name: "Validation de la fiche" }).click();
    await page.getByRole("button", { name: "Confirmer" }).click();
    await expect(page.getByText("À planifier").first()).toBeVisible();

    await logout(page);

    // 3. Administrateur — affecte le chauffeur de démo.
    await login(page, "Administrateur");
    await page.goto(vehicleUrl);
    await page.getByRole("button", { name: "Affectation d'un chauffeur" }).click();
    await page.getByLabel("Chauffeur", { exact: true }).click();
    await page.getByRole("option", { name: "Karim Benali" }).click();
    await page.getByRole("button", { name: "Confirmer" }).click();
    await expect(page.getByText("Affecté", { exact: true }).first()).toBeVisible();

    await logout(page);

    // 4. Chauffeur — rendez-vous, contrôle complet, conclusion « travaux requis ».
    await login(page, "Chauffeur");
    await expect(page).toHaveURL(/\/missions$/);

    await expect(
      page.getByRole("button", { name: /Notifications, \d+ non lue/ }),
    ).toBeVisible({ timeout: 10_000 });
    await page.getByRole("button", { name: /Notifications/ }).click();
    const notificationLink = page.getByRole("link", { name: new RegExp(marque) });
    await expect(notificationLink).toBeVisible();
    await notificationLink.click();

    await expect(page).toHaveURL(/\/missions\/[0-9a-f-]+$/);

    await page.getByRole("button", { name: "Prise de rendez-vous" }).click();
    const rdvInput = page.getByLabel("Date et heure du rendez-vous");
    const future = new Date(Date.now() + 3 * 24 * 60 * 60 * 1000);
    const pad = (n: number) => String(n).padStart(2, "0");
    const rdvValue = `${future.getFullYear()}-${pad(future.getMonth() + 1)}-${pad(future.getDate())}T10:00`;
    await rdvInput.fill(rdvValue);
    await page.getByRole("button", { name: "Confirmer" }).click();
    await expect(page.getByText("RDV planifié", { exact: true }).first()).toBeVisible();

    await page.getByRole("button", { name: "Début du contrôle sur place" }).click();
    await page.getByRole("button", { name: "Confirmer" }).click();

    await page.getByRole("link", { name: "Ouvrir le contrôle véhicule" }).click();
    await expect(page).toHaveURL(/\/controle$/);

    await expect(page.getByText(/en attente de connexion/i)).toHaveCount(0, { timeout: 15_000 });

    await page.getByLabel("Kilométrage relevé", { exact: true }).fill("142000");
    await page.getByRole("button", { name: "Moyen", exact: true }).click();

    for (const libelle of REQUIRED_OK_KO_ITEMS) {
      await page.getByRole("group", { name: libelle }).getByRole("button", { name: "OK" }).click();
    }
    for (const libelle of REQUIRED_NOTE_ITEMS) {
      await page.getByRole("group", { name: libelle }).getByRole("button", { name: "3" }).click();
    }
    await page.getByLabel("Kilométrage relevé au compteur").fill("142000");

    for (const label of REQUIRED_ANGLE_LABELS) {
      await page.getByLabel(label, { exact: true }).setInputFiles(FIXTURE_IMAGE);
    }
    await expect(page.locator("img[alt='']")).toHaveCount(12, { timeout: 15_000 });
    await expect(page.getByText(/n'a pas pu être envoyée/i)).toHaveCount(0, { timeout: 30_000 });

    await page.getByRole("button", { name: "Travaux requis", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Contrôle soumis" })).toBeVisible({ timeout: 30_000 });

    // 5. Transition véhicule CONTROLE_EN_COURS → TRAVAUX_REQUIS : ouvre le dialogue et saisit
    // l'ordre de travaux (contrat J3, payload `work_orders` non vide obligatoire).
    await page.getByRole("button", { name: "Conclusion : travaux requis", exact: true }).click();
    await page.getByLabel("Description", { exact: true }).fill("Pare-choc arrière enfoncé à reprendre");
    await page.getByRole("button", { name: "Confirmer" }).click();
    await expect(page.getByText("Travaux requis", { exact: true }).first()).toBeVisible({ timeout: 10_000 });

    await logout(page);

    // 6. Atelier — prend le véhicule en charge, saisit le coût réel, clôt l'ordre de travaux.
    await login(page, "Atelier");
    await page.goto(vehicleUrl);
    await expect(page.getByText("Travaux requis", { exact: true }).first()).toBeVisible();

    await page.getByRole("button", { name: "Prise en charge atelier", exact: true }).click();
    await page.getByRole("button", { name: "Confirmer" }).click();
    await expect(page.getByText("Travaux en cours", { exact: true }).first()).toBeVisible({ timeout: 10_000 });

    const atelierSection = page.getByRole("region", { name: /Atelier/i }).first();
    await atelierSection.getByRole("button", { name: "Ajouter une ligne", exact: true }).click();
    await page.getByLabel("Libellé", { exact: true }).fill("Peinture pare-choc arrière");
    await page.getByLabel("Quantité", { exact: true }).fill("1");
    await page.getByLabel("Prix unitaire", { exact: true }).fill("150");
    await page.getByRole("button", { name: "Ajouter", exact: true }).click();
    await expect(page.getByText("Peinture pare-choc arrière")).toBeVisible({ timeout: 10_000 });

    await page.getByRole("button", { name: "En cours", exact: true }).click();
    await expect(page.getByText("En cours", { exact: true }).first()).toBeVisible({ timeout: 10_000 });
    // Clore le DERNIER ordre de travaux ouvert du véhicule fait immédiatement sortir ce
    // véhicule du périmètre `scope_vehicles` de l'atelier (backend/app/services/
    // vehicle_scope.py : « atelier → uniquement les véhicules ayant un ordre de travaux non
    // terminé »). L'atelier ne peut donc plus, dans la même session, cliquer la transition
    // véhicule « Travaux terminés » qui vient elle-même d'être débloquée par cette clôture —
    // seul l'administrateur (également habilité par l'automate `TRAVAUX_EN_COURS →
    // TRAVAUX_TERMINES`, non scopé) peut la déclencher. Point d'attention consigné dans
    // implementation.md § J3 Frontend pour une éventuelle revue du contrat backend.
    await page.getByRole("button", { name: "Terminé", exact: true }).click();
    await expect(page.getByText("Terminé", { exact: true }).first()).toBeVisible({ timeout: 10_000 });

    await logout(page);

    // 7. Administrateur — clôture véhicule (« Travaux terminés », hors scope atelier une fois
    // le dernier ordre clos, voir remarque ci-dessus) puis validation d'achat après travaux.
    await login(page, "Administrateur");
    await page.goto(vehicleUrl);
    await page.getByRole("button", { name: "Travaux terminés", exact: true }).click();
    await page.getByRole("button", { name: "Confirmer" }).click();
    await expect(page.getByText("Travaux terminés", { exact: true }).first()).toBeVisible({ timeout: 10_000 });

    await page.getByRole("button", { name: "Achat validé après travaux", exact: true }).click();
    await page.getByLabel("Prix d'achat négocié").fill("5000");
    await page.getByRole("button", { name: "Confirmer" }).click();
    await expect(page.getByText("Achat validé", { exact: true }).first()).toBeVisible({ timeout: 10_000 });

    // 8. Tableau de bord — la couche analytique est une vue MATÉRIALISÉE (plan.md § 3.7) : elle
    // ne voit notre véhicule qu'après un rafraîchissement explicite, jamais en temps réel comme
    // le Kanban opérationnel (`GET /vehicles/pipeline-counts`). La marge (valeur de revente −
    // prix négocié − coût atelier réel) apparaît ensuite, positive et lisible, jamais « — »
    // (has_marge = true, la valeur de revente a été saisie à l'étape 1).
    // 9000 € − 5000 € − 150 € = 3850 € de marge attendue.
    await page.goto("/pilotage");
    await page.getByRole("button", { name: "Actualiser les indicateurs" }).click();
    await expect(page.getByRole("button", { name: "Actualisation…" })).toHaveCount(0, { timeout: 30_000 });

    const margeCard = page.getByTestId("chart-marge");
    await expect(margeCard).toBeVisible({ timeout: 15_000 });
    await margeCard.getByRole("tab", { name: "Tableau" }).click();

    const margeRow = margeCard.getByRole("row", { name: new RegExp(modele) });
    await expect(margeRow).toBeVisible({ timeout: 15_000 });
    await expect(margeRow).not.toContainText("—");
    // Espaces insécables/étroites de l'Intl.NumberFormat fr-FR — comparées via une regex plutôt
    // qu'une chaîne littérale (voir money.test.ts pour la même remarque côté Vitest).
    await expect(margeRow).toContainText(/3\s?850,00\s?€/);
  });
});
