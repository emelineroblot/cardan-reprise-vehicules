"use client";

import { useEffect } from "react";

/**
 * Enregistre `public/sw.js` (installabilité PWA, décision C). Monté une seule fois dans
 * le layout racine — sans effet en `next dev` sous Turbopack tant que le fichier n'est
 * pas modifié par le pipeline (il est servi tel quel depuis `public/`, jamais transformé
 * par next-pwa/webpack : pas de conflit avec le pitfall Turbopack de `stack-pitfalls`).
 *
 * ⚠️ **Jamais enregistré en développement.** `sw.js` sert les fichiers `/_next/` en
 * *cache d'abord*, en supposant que leur nom porte un hash — vrai des bundles de
 * production, faux en `next dev` où chaque recompilation régénère les chunks. Le service
 * worker ressert alors des morceaux périmés que le serveur n'expose plus : l'application
 * ne démarre pas, l'écran reste vide et aucune erreur n'apparaît. Un rechargement forcé
 * n'y change rien, un service worker survivant aux rechargements (constaté en session).
 *
 * En développement, on fait donc l'inverse : on désinscrit tout service worker déjà posé
 * et on vide ses caches, pour réparer les navigateurs qui en portent un d'une session
 * précédente.
 */
export function ServiceWorkerRegister() {
  useEffect(() => {
    if (typeof window === "undefined" || !("serviceWorker" in navigator)) return;

    if (process.env.NODE_ENV !== "production") {
      void navigator.serviceWorker
        .getRegistrations()
        .then((registrations) => Promise.all(registrations.map((registration) => registration.unregister())))
        .then(async (unregistered) => {
          if (!unregistered.some(Boolean)) return;
          if ("caches" in window) {
            const keys = await caches.keys();
            await Promise.all(keys.map((key) => caches.delete(key)));
          }
          console.info(
            "Service worker désinscrit et caches vidés (développement) — rechargez la page si elle reste vide.",
          );
        })
        .catch(() => {
          /* Rien à réparer : aucun service worker joignable. */
        });
      return;
    }

    navigator.serviceWorker.register("/sw.js").catch((error) => {
      console.warn("Enregistrement du service worker impossible — la PWA fonctionnera en mode dégradé.", error);
    });
  }, []);

  return null;
}
