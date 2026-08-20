"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { LogOut, Menu, PlusCircle, Wrench, X } from "lucide-react";
import { useState } from "react";
import { useAuth } from "@/lib/auth/AuthProvider";
import { hasRole } from "@/lib/auth/roles";
import { ROLE_LABELS } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface NavItem {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  allowed: ("operatrice" | "chauffeur" | "administrateur" | "atelier")[];
}

const NAV_ITEMS: NavItem[] = [
  {
    href: "/vehicules",
    label: "Suivi des véhicules",
    icon: Wrench,
    allowed: ["operatrice", "chauffeur", "administrateur", "atelier"],
  },
  {
    href: "/fiches/nouvelle",
    label: "Nouvelle fiche d'achat",
    icon: PlusCircle,
    allowed: ["operatrice", "administrateur"],
  },
];

/** Navigation applicative, filtrée par rôle. Le masquage est un confort, pas une barrière. */
export function AppNav() {
  const { user, logout } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [mobileOpen, setMobileOpen] = useState(false);

  const visibleItems = NAV_ITEMS.filter((item) => hasRole(user, item.allowed));

  const handleLogout = async () => {
    await logout();
    router.push("/login");
  };

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/95 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4">
        <div className="flex items-center gap-6">
          <Link href="/vehicules" className="font-semibold tracking-tight">
            Cardan
          </Link>
          <nav aria-label="Navigation principale" className="hidden md:flex md:items-center md:gap-1">
            {visibleItems.map((item) => {
              const active = pathname?.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                    active
                      ? "bg-muted text-foreground"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground",
                  )}
                >
                  <item.icon className="size-4" aria-hidden="true" />
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>

        <div className="flex items-center gap-3">
          {user ? (
            <span className="hidden text-sm text-muted-foreground sm:inline">
              {user.full_name} · {ROLE_LABELS[user.role]}
            </span>
          ) : null}
          <Button type="button" variant="outline" size="sm" onClick={handleLogout}>
            <LogOut className="size-4" aria-hidden="true" />
            Se déconnecter
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="md:hidden"
            aria-expanded={mobileOpen}
            aria-controls="mobile-nav"
            aria-label={mobileOpen ? "Fermer le menu" : "Ouvrir le menu"}
            onClick={() => setMobileOpen((open) => !open)}
          >
            {mobileOpen ? <X className="size-4" /> : <Menu className="size-4" />}
          </Button>
        </div>
      </div>

      {mobileOpen ? (
        <nav id="mobile-nav" aria-label="Navigation principale (mobile)" className="border-t border-border md:hidden">
          <ul className="flex flex-col p-2">
            {visibleItems.map((item) => (
              <li key={item.href}>
                <Link
                  href={item.href}
                  onClick={() => setMobileOpen(false)}
                  className="flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-foreground hover:bg-muted"
                >
                  <item.icon className="size-4" aria-hidden="true" />
                  {item.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      ) : null}
    </header>
  );
}
