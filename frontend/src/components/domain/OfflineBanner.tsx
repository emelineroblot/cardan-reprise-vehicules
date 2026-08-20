"use client";

import { WifiOff, RefreshCw, CloudUpload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useQueryClient } from "@tanstack/react-query";
import { triggerSync } from "@/lib/offline/sync";
import type { OfflineSummary } from "@/lib/offline/useOfflineSyncEngine";

interface OfflineBannerProps {
  isOnline: boolean;
  summary: OfflineSummary | undefined;
}

/**
 * Bandeau persistant (décision C, critère d'acceptation le plus important de J2) : rendu
 * dès qu'il y a quelque chose à dire — hors ligne, ou une file d'envoi non vide même en
 * ligne (le temps qu'elle se vide). Jamais alarmant en rouge pour le cas nominal « hors
 * ligne, tout est enregistré » : c'est un état attendu du métier (parking souterrain), pas
 * une panne.
 */
export function OfflineBanner({ isOnline, summary }: OfflineBannerProps) {
  const queryClient = useQueryClient();

  if (!summary || !summary.hasAnything) return null;

  const pending = summary.pendingPhotos + summary.pendingInspections;
  const hasTransientFailure = summary.failedPhotos > 0;
  // Échec DÉFINITIF (409/422, ou plafond de tentatives — `sync.ts::isDefinitivePhotoError`) :
  // distinct de `hasTransientFailure` pour ne plus jamais annoncer « nouvelle tentative en
  // cours » sur une photo qui ne sera plus jamais retentée automatiquement (revue finale §
  // 🟠 n°1 — le bandeau doit dire la vérité, jamais entretenir une illusion de progression).
  const hasPermanentFailure = summary.failedPermanentPhotos > 0;

  if (isOnline && pending === 0 && !hasTransientFailure && !hasPermanentFailure) return null;

  const messages: string[] = [];
  if (!isOnline) {
    messages.push(
      "Hors ligne — vos réponses et photos sont enregistrées sur l'appareil, elles partiront automatiquement au retour du réseau.",
    );
  }
  if (hasPermanentFailure) {
    messages.push(
      `${summary.failedPermanentPhotos} photo${summary.failedPermanentPhotos > 1 ? "s" : ""} n'a pas pu être envoyée après plusieurs tentatives — reprenez la prise depuis l'écran de contrôle du véhicule.`,
    );
  }
  if (hasTransientFailure) {
    messages.push(
      `${summary.failedPhotos} photo${summary.failedPhotos > 1 ? "s" : ""} en échec passager — nouvelle tentative automatique en cours.`,
    );
  }
  if (isOnline && !hasTransientFailure && !hasPermanentFailure) {
    messages.push(`Envoi en cours… ${pending} élément${pending > 1 ? "s" : ""} restant${pending > 1 ? "s" : ""}.`);
  }

  const hasFailed = hasTransientFailure || hasPermanentFailure;

  return (
    <div
      role="status"
      aria-live="polite"
      className={
        "flex flex-wrap items-center justify-between gap-2 border-b px-4 py-2 text-sm " +
        (!isOnline
          ? "border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200"
          : hasFailed
            ? "border-destructive/30 bg-destructive/5 text-destructive"
            : "border-sky-200 bg-sky-50 text-sky-900 dark:border-sky-900 dark:bg-sky-950 dark:text-sky-200")
      }
    >
      <span className="flex items-center gap-2">
        {!isOnline ? <WifiOff className="size-4 shrink-0" aria-hidden="true" /> : <CloudUpload className="size-4 shrink-0" aria-hidden="true" />}
        {messages.join(" ")}
      </span>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => triggerSync(queryClient).then(() => queryClient.invalidateQueries({ queryKey: ["offline"] }))}
      >
        <RefreshCw className="size-3.5" aria-hidden="true" />
        Réessayer
      </Button>
    </div>
  );
}
