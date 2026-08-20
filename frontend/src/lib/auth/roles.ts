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
    case "operatrice":
    case "administrateur":
      return "/vehicules";
    case "chauffeur":
    case "atelier":
      // J2/J3 : espaces dédiés à venir. En J1, tous les rôles retombent sur la liste
      // (le cloisonnement ligne côté backend limite déjà ce qu'ils y voient).
      return "/vehicules";
    default:
      return "/vehicules";
  }
}
