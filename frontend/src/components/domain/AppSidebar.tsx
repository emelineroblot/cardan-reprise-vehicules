"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Car } from "lucide-react";
import { hasRole } from "@/lib/auth/roles";
import { useAuth } from "@/lib/auth/AuthProvider";
import { NAV_ITEMS } from "@/components/domain/nav-items";
import { cn } from "@/lib/utils";

/**
 * Barre latérale sombre pleine hauteur (inspiration DashboardKit § navigation) — délibérément
 * sombre quel que soit le thème clair/sombre du contenu (comme Vercel/Linear/Stripe) : c'est le
 * "chrome" applicatif, pas une donnée métier soumise à la bascule de thème (§ 3 « ne casse rien »
 * ne visait que le thème du contenu, jamais spécifié pour la navigation elle-même).
 *
 * Un seul groupe pour l'instant (5 routes) : pas de sections multiples façon DashboardKit
 * (NAVIGATION / WIDGET / ADMIN PANEL) — ç'aurait été de la structure sans contenu réel à
 * hiérarchiser, contraire à la consigne « outil interne, pas décoration ».
 */
export function AppSidebar({ className }: { className?: string }) {
  const { user } = useAuth();
  const pathname = usePathname();
  const visibleItems = NAV_ITEMS.filter((item) => hasRole(user, item.allowed));

  return (
    <aside
      className={cn(
        "flex w-64 shrink-0 flex-col gap-6 border-r border-white/10 bg-zinc-950 px-4 py-5 text-zinc-100",
        className,
      )}
    >
      <Link href="/vehicules" className="flex items-center gap-2 px-2 text-base font-semibold tracking-tight text-white">
        <span className="flex size-8 items-center justify-center rounded-lg bg-white/10">
          <Car className="size-4" aria-hidden="true" />
        </span>
        Cardan
      </Link>

      <div className="flex flex-col gap-1.5">
        <p className="px-2 text-xs font-medium tracking-wide text-zinc-500 uppercase">Navigation</p>
        <nav aria-label="Navigation principale" className="flex flex-col gap-0.5">
          {visibleItems.map((item) => {
            const active = pathname?.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex items-center gap-2.5 rounded-lg border-l-2 border-transparent px-2.5 py-2 text-sm font-medium transition-colors",
                  active
                    ? "border-zinc-100 bg-white/10 text-white"
                    : "text-zinc-400 hover:bg-white/5 hover:text-zinc-100",
                )}
              >
                <item.icon className="size-4 shrink-0" aria-hidden="true" />
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </aside>
  );
}
