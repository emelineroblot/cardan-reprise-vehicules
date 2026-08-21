"use client";

import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { Button } from "@/components/ui/button";

/**
 * Bascule clair/sombre (inspiration DashboardKit § barre supérieure) — jusqu'ici absente de
 * l'application : les variables `.dark` de globals.css existaient déjà (palette dataviz
 * validée, skill `dataviz`) mais rien ne posait la classe. `next-themes` la pose sur `<html>`.
 */
export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  // Évite un mismatch d'icône serveur/client : le thème résolu n'est connu qu'après montage.
  // Contrairement aux autres cas de la base (money-input, login), aucun état dérivable en
  // initialiseur paresseux n'existe ici — `resolvedTheme` de `next-themes` n'est fiable
  // qu'après hydratation, l'effet est la garde recommandée par la librairie elle-même.
  const [mounted, setMounted] = useState(false);
  // eslint-disable-next-line react-hooks/set-state-in-effect -- garde d'hydratation ci-dessus, pas un état dérivable au rendu.
  useEffect(() => setMounted(true), []);

  const isDark = mounted && resolvedTheme === "dark";

  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      aria-label={isDark ? "Passer au thème clair" : "Passer au thème sombre"}
      onClick={() => setTheme(isDark ? "light" : "dark")}
    >
      {mounted ? (
        isDark ? (
          <Sun className="size-4" aria-hidden="true" />
        ) : (
          <Moon className="size-4" aria-hidden="true" />
        )
      ) : (
        <span className="size-4" aria-hidden="true" />
      )}
    </Button>
  );
}
