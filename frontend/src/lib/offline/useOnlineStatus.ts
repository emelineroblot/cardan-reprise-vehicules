"use client";

import { useEffect, useState } from "react";

/**
 * `navigator.onLine` est un indicateur du lien réseau LOCAL (Wi-Fi/4G), pas de la
 * joignabilité du backend — un parking souterrain avec Wi-Fi mais sans passerelle
 * Internet reste `online === true`. C'est pour ça que le déclencheur réel du rejeu
 * (`lib/offline/sync.ts`) est un échec/succès de requête réelle, jamais cet indicateur
 * seul : il ne sert ici qu'à afficher un bandeau et à retenter à bon escient (évènement
 * `online`), pas à décider qu'un envoi va réussir.
 */
export function useOnlineStatus(): boolean {
  const [isOnline, setIsOnline] = useState(() =>
    typeof navigator === "undefined" ? true : navigator.onLine,
  );

  useEffect(() => {
    const handleOnline = () => setIsOnline(true);
    const handleOffline = () => setIsOnline(false);
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, []);

  return isOnline;
}
