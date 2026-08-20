import { defineConfig, devices } from "@playwright/test";

/**
 * Parcours e2e J1 (frontend/e2e/j1-saisie.spec.ts).
 *
 * Nécessite le backend + PostgreSQL démarrés et seedés (voir AGENTS.md § Commandes) :
 * ce fichier n'est PAS exécuté par dev-frontend, dont le périmètre est strictement
 * frontend/ — voir implementation.md.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  retries: 0,
  reporter: "list",
  use: {
    baseURL: "http://localhost:3000",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "npm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: true,
    timeout: 60_000,
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
