import type { Role } from "@/lib/api/types";

/**
 * Comptes de démo — 4 comptes fixes, mots de passe publics (plan.md § 3.4 : « données
 * fictives, base réinitialisée chaque nuit, aucune donnée personnelle »).
 *
 * ⚠️ Convention d'email/mot de passe non fixée par le plan (qui décrit le comportement,
 * pas les identifiants). Tranchée ici par dev-frontend le temps du développement en
 * parallèle ; DOIT être alignée avec `backend/app/seed/reference.py` à l'intégration
 * (vague 5) — voir implementation.md § Points d'ambiguïté.
 */
export interface DemoAccount {
  role: Role;
  label: string;
  description: string;
  email: string;
  password: string;
}

export const DEMO_ACCOUNTS: DemoAccount[] = [
  {
    role: "operatrice",
    label: "Opératrice",
    description: "Saisit les fiches d'achat, gère le dédoublonnage",
    email: "operatrice@cardan.demo",
    password: "demo1234",
  },
  {
    role: "chauffeur",
    label: "Chauffeur",
    description: "Missions terrain, contrôle véhicule (J2)",
    email: "chauffeur@cardan.demo",
    password: "demo1234",
  },
  {
    role: "administrateur",
    label: "Administrateur",
    description: "Pilotage, affectations, validation d'achat",
    email: "administrateur@cardan.demo",
    password: "demo1234",
  },
  {
    role: "atelier",
    label: "Atelier",
    description: "Ordres de travaux, coûts réels (J3)",
    email: "atelier@cardan.demo",
    password: "demo1234",
  },
];
