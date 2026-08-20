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
      // J3 : espace atelier à venir. En attendant, retombe sur la liste (le
      // cloisonnement ligne côté backend limite déjà ce qu'il y voit).
      return "/vehicules";
    default:
      return "/vehicules";
  }
}
