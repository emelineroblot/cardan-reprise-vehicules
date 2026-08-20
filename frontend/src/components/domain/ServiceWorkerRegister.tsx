"use client";

import { useEffect } from "react";

/**
 * Enregistre `public/sw.js` (installabilité PWA, décision C). Monté une seule fois dans
 * le layout racine — sans effet en `next dev` sous Turbopack tant que le fichier n'est
 * pas modifié par le pipeline (il est servi tel quel depuis `public/`, jamais transformé
 * par next-pwa/webpack : pas de conflit avec le pitfall Turbopack de `stack-pitfalls`).
 */
export function ServiceWorkerRegister() {
  useEffect(() => {
    if (typeof window === "undefined" || !("serviceWorker" in navigator)) return;
    navigator.serviceWorker.register("/sw.js").catch((error) => {
      console.warn("Enregistrement du service worker impossible — la PWA fonctionnera en mode dégradé.", error);
    });
  }, []);

  return null;
}
