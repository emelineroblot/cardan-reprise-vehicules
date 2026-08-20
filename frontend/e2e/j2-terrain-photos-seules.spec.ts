import path from "node:path";
import { expect, test } from "@playwright/test";

/**
 * Parcours e2e J2 — variante ciblée du scénario réel signalé par la revue orchestrateur
 * (`.agent-team/review-j2.md` § Bloquant n°1) : `j2-terrain.spec.ts` remplit la checklist
 * PENDANT la coupure réseau, ce qui pose `items_dirty` et sert d'amorce accidentelle au rejeu
 * des photos — un tick de synchronisation a donc toujours une raison de passer par ce
 * brouillon, quoi qu'il arrive. Ce test-ci coupe le réseau APRÈS que la checklist a été
 * intégralement saisie ET synchronisée : à la reprise du réseau, les photos sont le SEUL
 * élément en attente. C'est le scénario réel le plus probable (le chauffeur remplit son
 * contrôle, puis descend photographier le véhicule), et c'est celui qui expose le bug
 * `needsSync()` (`lib/offline/sync.ts:112-116`) — une photo mise en file n'y déclenche aucun
 * drapeau, donc aucun rejeu, ni par l'évènement `online`, ni par le minuteur de 20 s, ni par
 * le bouton « Réessayer ».
 *
 * Attendu ROUGE tant que `needsSync` (ou `runSyncTick`) n'a pas été corrigé pour tenir compte
 * de `getAllPhotos()`. Ne clique JAMAIS sur un bouton de conclusion : cliquer « Achat direct »
 * poserait `pending_submit`/`fields_dirty` (`draft.ts::requestSubmit`) et redéclencherait le
 * rejeu par un autre chemin, masquant exactement le bug visé — voir `sync.concurrency.test.ts`
 * pour la version unitaire déterministe de cette même preuve.
 *
 * Nécessite le backend + PostgreSQL démarrés et seedés, comme `j2-terrain.spec.ts`.
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

/** Formes minimales — reflètent `LocalInspection`/`LocalPhoto` (`lib/offline/types.ts`), lues
 * directement depuis le contexte navigateur (`page.evaluate`/`page.waitForFunction` s'exécutent
 * hors du bundle applicatif : pas d'import possible, juste les champs réellement lus ici). */
interface OfflineInspectionRecord {
  server_id: string | null;
  vehicle_id: string;
  items_dirty: boolean;
  fields_dirty: boolean;
}
interface OfflinePhotoRecord {
  upload_state: "queued" | "uploading" | "sent" | "failed";
}

/**
 * Preuve par l'état RÉEL d'IndexedDB, pas par un minuteur arbitraire ou l'absence d'un
 * message d'erreur à l'écran : le brouillon terrain doit avoir un `server_id`, et ses deux
 * drapeaux `*_dirty` doivent être retombés à `false` — c'est-à-dire que la checklist et les
 * champs généraux sont RÉELLEMENT arrivés côté serveur, pas seulement « en file d'attente ».
 */
async function waitForDraftFullySynced(page: import("@playwright/test").Page) {
  await page.waitForFunction(
    async () => {
      const req = indexedDB.open("cardan-terrain");
      const db = await new Promise<IDBDatabase>((resolve, reject) => {
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
      });
      const tx = db.transaction("inspections", "readonly");
      const all = await new Promise<OfflineInspectionRecord[]>((resolve, reject) => {
        const r = tx.objectStore("inspections").getAll();
        r.onsuccess = () => resolve(r.result as OfflineInspectionRecord[]);
        r.onerror = () => reject(r.error);
      });
      db.close();
      return (
        all.length > 0 &&
        all.every((i) => Boolean(i.server_id) && i.items_dirty === false && i.fields_dirty === false)
      );
    },
    null,
    { timeout: 20_000 },
  );
}

/** Lit l'état du brouillon + des photos directement en IndexedDB — l'état final des DONNÉES,
 * pas un texte affiché à l'écran. */
async function readOfflineState(
  page: import("@playwright/test").Page,
): Promise<{ inspections: OfflineInspectionRecord[]; photos: OfflinePhotoRecord[] }> {
  return page.evaluate(async () => {
    const req = indexedDB.open("cardan-terrain");
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
    const getAll = <T>(storeName: string) =>
      new Promise<T[]>((resolve, reject) => {
        const tx = db.transaction(storeName, "readonly");
        const r = tx.objectStore(storeName).getAll();
        r.onsuccess = () => resolve(r.result as T[]);
        r.onerror = () => reject(r.error);
      });
    const [inspections, photos] = await Promise.all([
      getAll<OfflineInspectionRecord>("inspections"),
      getAll<OfflinePhotoRecord>("photos"),
    ]);
    db.close();
    return { inspections, photos };
  });
}

test.describe("J2 — module terrain chauffeur — coupure réseau APRÈS la checklist (photos seules en attente)", () => {
  test("des photos mises en file après une checklist déjà synchronisée doivent repartir au retour du réseau, sans action de conclusion", async ({
    page,
    context,
  }) => {
    const unique = Date.now();
    const marque = `J2PhotosSeules${unique}`;
    const modele = `J2Modele${unique}`;

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

    await page.getByLabel("Recherche libre").fill(modele);
    await page.getByRole("button", { name: "Rechercher" }).click();
    await page.locator("table tbody tr", { hasText: modele }).first().click();
    await expect(page).toHaveURL(/\/vehicules\/[0-9a-f-]+$/);
    const vehicleUrl = page.url();

    await page.getByRole("button", { name: "Validation de la fiche" }).click();
    await page.getByRole("button", { name: "Confirmer" }).click();
    await expect(page.getByText("À planifier").first()).toBeVisible();

    await logout(page);

    await login(page, "Administrateur");
    await page.goto(vehicleUrl);
    await page.getByRole("button", { name: "Affectation d'un chauffeur" }).click();
    await page.getByLabel("Chauffeur", { exact: true }).click();
    await page.getByRole("option", { name: "Karim Benali" }).click();
    await page.getByRole("button", { name: "Confirmer" }).click();
    await expect(page.getByText("Affecté", { exact: true }).first()).toBeVisible();

    await logout(page);

    await login(page, "Chauffeur");
    await expect(page).toHaveURL(/\/missions$/);
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
    await page.getByLabel("Adresse du rendez-vous (optionnel)").fill("12 rue du Garage, Nantes");
    await page.getByRole("button", { name: "Confirmer" }).click();
    await expect(page.getByText("RDV planifié", { exact: true }).first()).toBeVisible();

    await page.getByRole("button", { name: "Début du contrôle sur place" }).click();
    await page.getByRole("button", { name: "Confirmer" }).click();

    await page.getByRole("link", { name: "Ouvrir le contrôle véhicule" }).click();
    await expect(page).toHaveURL(/\/controle$/);

    // Checklist + champs généraux REMPLIS et SYNCHRONISÉS EN LIGNE — le scénario réel : le
    // chauffeur remplit son contrôle avant de descendre photographier.
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

    // Preuve par l'état réel des données locales — pas un délai arbitraire — que la
    // checklist est bien arrivée côté serveur AVANT de couper le réseau.
    await waitForDraftFullySynced(page);

    // Coupure réseau — à ce stade, le brouillon est « propre » (aucun champ modifié depuis
    // la dernière synchronisation) : seules les photos vont maintenant s'accumuler.
    await context.setOffline(true);
    await expect(
      page.getByText(/Hors ligne — vos réponses et photos sont enregistrées/i),
    ).toBeVisible({ timeout: 10_000 });

    for (const label of REQUIRED_ANGLE_LABELS) {
      await page.getByLabel(label, { exact: true }).setInputFiles(FIXTURE_IMAGE);
    }
    await expect(page.locator("img[alt='']")).toHaveCount(12, { timeout: 10_000 });

    const offlineState = await readOfflineState(page);
    expect(offlineState.photos).toHaveLength(12);
    expect(offlineState.photos.every((p) => p.upload_state === "queued")).toBe(true);

    // Retour du réseau — AUCUNE action de conclusion n'est prise ici (voir en-tête du
    // fichier) : c'est la reprise réseau SEULE qui doit renvoyer les photos en attente,
    // exactement le libellé du critère d'acceptation J2 du brief.
    await context.setOffline(false);

    // Attente généreuse (30 s ≈ 1,5 cycle du minuteur de fond de 20 s) : si le bug 🔴
    // (`needsSync` ignore les photos seules) n'est pas corrigé, aucune de ces 12 photos ne
    // passera jamais à `sent`, quel que soit le temps attendu — ce test échouera alors
    // proprement par timeout, ce qui EST la preuve attendue à ce stade.
    await expect
      .poll(
        async () => {
          const state = await readOfflineState(page);
          return state.photos.filter((p) => p.upload_state === "sent").length;
        },
        { timeout: 30_000, message: "photos réellement envoyées au serveur (upload_state === 'sent')" },
      )
      .toBe(12);

    // Contre-preuve côté SERVEUR (pas seulement l'état local) : le référentiel d'angles
    // requis ne doit plus signaler aucun angle manquant pour cette inspection.
    const finalState = await readOfflineState(page);
    const inspection = finalState.inspections[0];
    const anglesResponse = await context.request.get(
      `/api/backend/v1/vehicles/${inspection.vehicle_id}/photos/required-angles?inspection_id=${inspection.server_id}`,
    );
    expect(anglesResponse.ok()).toBe(true);
    const anglesBody = await anglesResponse.json();
    expect(anglesBody.missing_angles).toEqual([]);
  });
});
