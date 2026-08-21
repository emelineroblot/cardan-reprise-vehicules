"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import { X } from "lucide-react";
import { AppSidebar } from "@/components/domain/AppSidebar";
import { Button } from "@/components/ui/button";

/**
 * Tiroir mobile — même contenu que `AppSidebar`, en panneau superposé avec trame de fond.
 * Fermeture par Échap, clic sur la trame, ou navigation (changement de route).
 */
export function MobileNavDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const pathname = usePathname();

  useEffect(() => {
    onClose();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fermeture voulue à chaque changement de route, `onClose` non stable n'a pas besoin d'y figurer.
  }, [pathname]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
      <div className="fixed inset-0 bg-black/40" aria-hidden="true" onClick={onClose} />
      <div className="fixed inset-y-0 left-0 flex w-64 shadow-xl">
        <AppSidebar className="h-full" />
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="absolute top-3 right-[-2.75rem] text-zinc-100 hover:bg-white/10 hover:text-white"
          aria-label="Fermer la navigation"
          onClick={onClose}
        >
          <X className="size-5" aria-hidden="true" />
        </Button>
      </div>
    </div>
  );
}
