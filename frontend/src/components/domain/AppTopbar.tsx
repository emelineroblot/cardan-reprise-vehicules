"use client";

import { useRouter } from "next/navigation";
import { LogOut, Menu } from "lucide-react";
import { useAuth } from "@/lib/auth/AuthProvider";
import { ROLE_LABELS } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/domain/ThemeToggle";
import { NotificationBell } from "@/components/domain/NotificationBell";

function initials(fullName: string): string {
  const parts = fullName.trim().split(/\s+/);
  const first = parts[0]?.[0] ?? "";
  const last = parts.length > 1 ? (parts[parts.length - 1]?.[0] ?? "") : "";
  return (first + last).toUpperCase() || "?";
}

/**
 * Barre supérieure claire (inspiration DashboardKit § topbar) : bascule de thème, notifications,
 * identité (avatar + nom + rôle). Pas de recherche ni de sélecteur de langue dans le template
 * source — Cardan n'a ni recherche globale ni i18n, les ajouter aurait été de la décoration sans
 * fonction réelle (consigne « rigueur, pas décoration »).
 */
export function AppTopbar({ onOpenMobileNav }: { onOpenMobileNav: () => void }) {
  const { user, logout } = useAuth();
  const router = useRouter();

  const handleLogout = async () => {
    await logout();
    router.push("/login");
  };

  return (
    <header className="sticky top-0 z-20 flex h-14 items-center gap-2 border-b border-border bg-background/95 px-4 backdrop-blur">
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="lg:hidden"
        aria-label="Ouvrir la navigation"
        onClick={onOpenMobileNav}
      >
        <Menu className="size-4" aria-hidden="true" />
      </Button>

      <div className="flex flex-1 items-center justify-end gap-2">
        <ThemeToggle />
        <NotificationBell />
        {user ? (
          // Bloc identité (inspiration DashboardKit § avatar + nom + rôle) purement
          // informatif — le bouton de déconnexion reste un `<button>` de premier niveau,
          // pas replié dans un menu : les specs e2e j2/j3 cliquent directement
          // `getByRole("button", { name: "Se déconnecter" })`, un item de menu Radix
          // (role="menuitem", masqué tant que le menu n'est pas ouvert) casserait ces
          // parcours pour un gain cosmétique marginal.
          <span className="hidden items-center gap-2 sm:flex">
            <span
              aria-hidden="true"
              className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground"
            >
              {initials(user.full_name)}
            </span>
            <span className="text-left text-sm">
              <span className="block leading-tight font-medium text-foreground">{user.full_name}</span>
              <span className="block text-xs leading-tight text-muted-foreground">{ROLE_LABELS[user.role]}</span>
            </span>
          </span>
        ) : null}
        <Button type="button" variant="outline" size="sm" onClick={handleLogout}>
          <LogOut className="size-4" aria-hidden="true" />
          Se déconnecter
        </Button>
      </div>
    </header>
  );
}
