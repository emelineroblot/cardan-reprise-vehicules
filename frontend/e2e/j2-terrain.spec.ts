import path from "node:path";
import { expect, test } from "@playwright/test";

/**
 * Parcours e2e J2 (plan.md § 4 décision C, brief « module terrain ») : mission → rendez-vous
 * → contrôle → checklist → photos → transition, chauffé par le dédoublonnage de J1 pour créer
 * un véhicule frais (marque/modèle horodatés — aucun risque de collision avec le jeu de démo
 * ni avec un rejeu de ce test).
 *
 * Le critère d'acceptation le plus important de J2 y est vérifié explicitement : couper le
 * réseau (`context.setOffline(true)`) en plein contrôle ne doit RIEN perdre, et la reprise
 * doit renvoyer automatiquement les réponses et les photos en attente.
 *
 * Nécessite le backend + PostgreSQL démarrés et seedés (référentiel `reference` — comptes de
 * démo et checklist standard), comme `j1-saisie.spec.ts`.
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
  // Attend la redirection post-connexion AVANT toute navigation suivante : sans ça, un
  // `page.goto()` immédiat peut gagner la course contre la pose du cookie de session et
  // atterrir sur une page non authentifiée (observé : redirection silencieuse vers /login).
  await expect(page).not.toHaveURL(/\/login$/, { timeout: 10_000 });
}

async function logout(page: import("@playwright/test").Page) {
  await page.getByRole("button", { name: "Se déconnecter" }).click();
  await expect(page).toHaveURL(/\/login$/);
}

test.describe("J2 — module terrain chauffeur", () => {
  test("mission → rendez-vous → contrôle hors ligne → checklist → photos → transition", async ({
    page,
    context,
  }) => {
    const unique = Date.now();
    const marque = `J2Marque${unique}`;
    const modele = `J2Modele${unique}`;

    // 1. Opératrice — nouvelle fiche, véhicule unique (aucun risque de doublon avec le jeu
    // de démo grâce au nom horodaté).
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

    // 3. Administrateur — affecte le chauffeur de démo (dette J1 fermée : sélection réelle
    // via GET /users?role=chauffeur, plus de bouton désactivé).
    await login(page, "Administrateur");
    await page.goto(vehicleUrl);
    await page.getByRole("button", { name: "Affectation d'un chauffeur" }).click();
    await page.getByLabel("Chauffeur", { exact: true }).click();
    await page.getByRole("option", { name: "Karim Benali" }).click();
    await page.getByRole("button", { name: "Confirmer" }).click();
    await expect(page.getByText("Affecté", { exact: true }).first()).toBeVisible();

    await logout(page);

    // 4. Chauffeur — reçoit la notification, réserve le rendez-vous, démarre le contrôle.
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
    const missionUrl = page.url();

    await page.getByRole("button", { name: "Prise de rendez-vous" }).click();
    const rdvInput = page.getByLabel("Date et heure du rendez-vous");
    const future = new Date(Date.now() + 3 * 24 * 60 * 60 * 1000);
    const pad = (n: number) => String(n).padStart(2, "0");
    const rdvValue = `${future.getFullYear()}-${pad(future.getMonth() + 1)}-${pad(future.getDate())}T10:00`;
    await rdvInput.fill(rdvValue);
    await page.getByLabel("Adresse du rendez-vous (optionnel)").fill("12 rue du Garage, Nantes");
    await page.getByRole("button", { name: "Confirmer" }).click();
    await expect(page.getByText("RDV planifié", { exact: true }).first()).toBeVisible();

    await page.getByRole("button", { name: "Début du contrôle sur place" }).click();
    await page.getByRole("button", { name: "Confirmer" }).click();

    await page.getByRole("link", { name: "Ouvrir le contrôle véhicule" }).click();
    await expect(page).toHaveURL(/\/controle$/);

    // 5. Contrôle — champs généraux et checklist REMPLIS EN LIGNE, pour laisser le temps au
    // référentiel des angles requis d'être mis en cache avant la coupure réseau (voir
    // lib/offline/draft.ts : la synchronisation initiale est déclenchée à l'ouverture).
    await expect(page.getByText(/en attente de connexion/i)).toHaveCount(0, { timeout: 15_000 });

    await page.getByLabel("Kilométrage relevé", { exact: true }).fill("128400");
    await page.getByRole("button", { name: "Bon", exact: true }).click();

    for (const libelle of REQUIRED_OK_KO_ITEMS) {
      await page.getByRole("group", { name: libelle }).getByRole("button", { name: "OK" }).click();
    }
    for (const libelle of REQUIRED_NOTE_ITEMS) {
      await page.getByRole("group", { name: libelle }).getByRole("button", { name: "4" }).click();
    }
    await page.getByLabel("Kilométrage relevé au compteur").fill("128400");

    // 6. Coupure réseau EN PLEIN CONTRÔLE — le scénario central de J2 (parking souterrain).
    // Les 12 photos d'angle sont capturées entièrement hors ligne.
    await context.setOffline(true);
    await expect(
      page.getByText(/Hors ligne — vos réponses et photos sont enregistrées/i),
    ).toBeVisible({ timeout: 10_000 });

    for (const label of REQUIRED_ANGLE_LABELS) {
      await page.getByLabel(label, { exact: true }).setInputFiles(FIXTURE_IMAGE);
    }
    // Rien n'est perdu : les 12 vignettes affichent la photo capturée malgré l'absence réseau.
    await expect(page.locator("img[alt='']")).toHaveCount(12, { timeout: 10_000 });

    // 7. Retour du réseau — la file d'envoi se vide automatiquement, sans action de
    // l'utilisateur au-delà de la reconnexion.
    await context.setOffline(false);
    await expect(
      page.getByText(/Hors ligne — vos réponses et photos sont enregistrées/i),
    ).toBeHidden({ timeout: 10_000 });
    await expect(page.getByText(/n'a pas pu être envoyée/i)).toHaveCount(0, { timeout: 30_000 });

    // 8. Validation — refuse tant qu'il manque un angle/une réponse obligatoire (vérifié
    // implicitement : le bouton n'était pas actionnable avant l'étape 6), puis soumission.
    await page.getByRole("button", { name: "Achat direct", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Contrôle soumis" })).toBeVisible({ timeout: 30_000 });

    // 9. Transition finale — dérivée de l'API, jamais codée en dur : achat validé.
    await page.getByRole("button", { name: "Achat direct validé" }).click();
    await page.getByLabel("Prix d'achat négocié").fill("8500");
    await page.getByRole("button", { name: "Confirmer" }).click();

    await page.goto(missionUrl);
    await expect(page.getByText("Achat validé").first()).toBeVisible({ timeout: 10_000 });
  });
});
