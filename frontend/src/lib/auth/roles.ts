import type { AppUser, Role } from "@/lib/api/types";

/**
 * Cloisonnement à deux étages (plan.md § 3.4) : l'étage route/ligne fait autorité côté
 * backend. Ces helpers ne servent que le confort d'UI (masquer un bouton n'a jamais été
 * la barrière de sécurité) — navigation, garde d'affichage, redirection après connexion.
 */

export function hasRole(user: AppUser | null | undefined, allowed: Role[]): boolean {
  if (!user) return false;
  return allowed.includes(user.role);
}

/** Route d'atterrissage par rôle après connexion. */
export function homeRouteForRole(role: Role): string {
  switch (role) {
    case "chauffeur":
      // J2 : le chauffeur atterrit directement sur ses missions terrain, pas sur la
      // liste globale (dont beaucoup de colonnes financières ne le concernent pas).
      return "/missions";
    case "operatrice":
    case "administrateur":
      return "/vehicules";
    case "atelier":
      // J3 : pas de liste dédiée — `GET /vehicles` scopé côté backend limite déjà
      // l'atelier aux véhicules portant un ordre de travaux ouvert (plan.md § 3.4).
      // Les ordres de travaux, lignes de coût et photos avant/après vivent dans la
      // fiche véhicule (`WorkOrdersSection`), pas dans un écran séparé.
      return "/vehicules";
    default:
      return "/vehicules";
  }
}
