"use client";

import { useEffect } from "react";

/**
 * Préchauffage du double démarrage à froid (plan.md § 3.8-5) : la fonction Vercel et la
 * base Neon se réveillent pendant que le prospect lit la page d'accueil, avant même qu'il
 * ait cliqué sur « Se connecter ». Silencieux, sans état, sans effet sur le rendu : un
 * échec ici (backend pas encore déployé, hors ligne en dev) n'est jamais montré.
 */
export function HealthPrewarm() {
  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/backend/v1/health", { signal: controller.signal, cache: "no-store" }).catch(() => {
      // Volontairement silencieux : le préchauffage est un bonus, jamais un blocage.
    });
    return () => controller.abort();
  }, []);

  return null;
}
