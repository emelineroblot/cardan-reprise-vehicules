"use client";

import type { ReactNode } from "react";
import { useAuth } from "@/lib/auth/AuthProvider";
import { hasRole } from "@/lib/auth/roles";
import type { Role } from "@/lib/api/types";
import { EmptyState } from "@/components/ui/empty-state";
import { ShieldAlert } from "lucide-react";

interface RoleGuardProps {
  allowed: Role[];
  children: ReactNode;
  fallback?: ReactNode;
}

/**
 * Garde d'affichage par rôle. Confort d'UI uniquement : le cloisonnement qui fait
 * autorité vit côté backend (route + ligne, plan.md § 3.4). Utilisé pour éviter
 * d'afficher des actions qu'un rôle ne pourra de toute façon pas exécuter.
 */
export function RoleGuard({ allowed, children, fallback }: RoleGuardProps) {
  const { user } = useAuth();

  if (!hasRole(user, allowed)) {
    return (
      fallback ?? (
        <EmptyState
          icon={<ShieldAlert className="size-8" />}
          title="Accès non autorisé"
          description="Votre rôle ne permet pas d'accéder à cette page."
        />
      )
    );
  }

  return <>{children}</>;
}
