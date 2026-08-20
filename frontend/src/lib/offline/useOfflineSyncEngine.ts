"use client";

import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { getAllInspections, getAllPhotos } from "@/lib/offline/db";
import { triggerSync } from "@/lib/offline/sync";
import { useOnlineStatus } from "@/lib/offline/useOnlineStatus";

const SYNC_INTERVAL_MS = 20_000;
const SUMMARY_POLL_MS = 3_000;

export interface OfflineSummary {
  pendingPhotos: number;
  /** Échecs TRANSITOIRES — encore retentés automatiquement au tick suivant. */
  failedPhotos: number;
  /** Échecs DÉFINITIFS (409/422, ou plafond de tentatives atteint,
   * `sync.ts::isDefinitivePhotoError`) — jamais rejoués automatiquement, distincts de
   * `failedPhotos` pour que le bandeau ne mente plus en annonçant « nouvelle tentative en
   * cours » sur une photo qui ne sera plus jamais retentée (revue finale § 🟠 n°1). */
  failedPermanentPhotos: number;
  pendingInspections: number;
  hasAnything: boolean;
}

async function computeSummary(): Promise<OfflineSummary> {
  try {
    const [inspections, photos] = await Promise.all([getAllInspections(), getAllPhotos()]);
    const pendingInspections = inspections.filter((i) => !i.server_id || i.pending_submit).length;
    const pendingPhotos = photos.filter((p) => p.upload_state === "queued" || p.upload_state === "uploading").length;
    const failedPhotos = photos.filter((p) => p.upload_state === "failed").length;
    const failedPermanentPhotos = photos.filter((p) => p.upload_state === "failed_permanent").length;
    return {
      pendingPhotos,
      failedPhotos,
      failedPermanentPhotos,
      pendingInspections,
      hasAnything: inspections.length > 0 || photos.length > 0,
    };
  } catch {
    return { pendingPhotos: 0, failedPhotos: 0, failedPermanentPhotos: 0, pendingInspections: 0, hasAnything: false };
  }
}

/**
 * Moteur de rejeu en tâche de fond (décision C) — monté une seule fois dans la coquille
 * applicative `(app)/layout.tsx` pour que la file d'envoi continue de se vider même quand
 * le chauffeur n'est plus sur l'écran de contrôle. Retente : au montage, au retour du
 * réseau (`online`), et toutes les 20 s tant que l'onglet est visible et en ligne.
 *
 * Le résumé est un `useState` sondé directement, pas une `useQuery` (même arbitrage que
 * `useInspectionDraft`, § commentaire d'en-tête de ce fichier) : c'est un état d'appareil
 * local, pas un cache serveur.
 */
export function useOfflineSyncEngine() {
  const queryClient = useQueryClient();
  const isOnline = useOnlineStatus();
  const [summary, setSummary] = useState<OfflineSummary | undefined>(undefined);

  // Demande best-effort au navigateur de ne pas évincer le stockage de l'origine sous
  // pression (revue J2 § 6) : sans ça, des photos non encore envoyées peuvent être perdues
  // silencieusement en cas de pression mémoire, exactement ce que la file hors ligne promet
  // d'empêcher. Aucun effet si l'API est absente (Safari < 15.4, navigateurs anciens) ou si
  // la demande est refusée — c'est une demande, jamais une garantie.
  useEffect(() => {
    if (typeof navigator !== "undefined" && navigator.storage?.persist) {
      void navigator.storage.persist().catch(() => undefined);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    const refreshSummary = async () => {
      const next = await computeSummary();
      if (!cancelled) setSummary(next);
    };

    const tick = async () => {
      if (cancelled || document.visibilityState !== "visible") return;
      await triggerSync(queryClient);
      await refreshSummary();
    };

    void tick();
    const syncInterval = window.setInterval(tick, SYNC_INTERVAL_MS);
    const summaryInterval = window.setInterval(refreshSummary, SUMMARY_POLL_MS);
    window.addEventListener("online", tick);
    document.addEventListener("visibilitychange", tick);

    return () => {
      cancelled = true;
      window.clearInterval(syncInterval);
      window.clearInterval(summaryInterval);
      window.removeEventListener("online", tick);
      document.removeEventListener("visibilitychange", tick);
    };
  }, [queryClient]);

  return { isOnline, summary };
}
