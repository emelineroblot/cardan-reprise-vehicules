"use client";

import { useRef, useState } from "react";
import { Camera, Loader2 } from "lucide-react";
import { useUploadWorkOrderPhoto, useWorkOrderPhotos } from "@/lib/api/hooks/useWorkOrderPhotos";
import { LoadingState } from "@/components/ui/loading-state";
import { ErrorState, describeError } from "@/components/ui/error-state";
import type { PhotoPhase } from "@/lib/api/types";

interface WorkOrderPhotoStripProps {
  vehicleId: string;
  workOrderId: string;
  phase: PhotoPhase;
  label: string;
  /** Écriture réservée à `atelier`/`administrateur` (contrat J3) — lecture ouverte à tout rôle
   * voyant le véhicule. */
  canUpload: boolean;
}

/**
 * Bande de photos avant/après travaux (brief J3). Contrairement au parcours de contrôle
 * terrain (J2), aucun angle n'est imposé — l'atelier documente l'état du véhicule librement,
 * angle `"defaut"` recommandé côté front (contrat J3), sans plafond visible autre que le
 * quota serveur global de 30 photos/véhicule (piège consigné en J2, toujours vrai en J3).
 */
export function WorkOrderPhotoStrip({ vehicleId, workOrderId, phase, label, canUpload }: WorkOrderPhotoStripProps) {
  const photos = useWorkOrderPhotos(vehicleId, workOrderId, phase);
  const upload = useUploadWorkOrderPhoto(vehicleId, workOrderId);
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploadError, setUploadError] = useState<unknown>(null);

  const handleFile = async (file: File) => {
    setUploadError(null);
    try {
      await upload.mutateAsync({ file, phase });
    } catch (error) {
      setUploadError(error);
    }
  };

  return (
    <div className="flex flex-col gap-2">
      <h4 className="text-sm font-medium text-foreground">{label}</h4>
      {photos.isLoading ? <LoadingState label="Chargement des photos…" /> : null}
      {photos.error ? (
        <ErrorState error={photos.error} title="Photos indisponibles" onRetry={() => photos.refetch()} />
      ) : null}
      {uploadError ? (
        <p role="alert" className="text-sm text-destructive">
          {describeError(uploadError)}
        </p>
      ) : null}
      <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
        {(photos.data ?? []).map((photo) => (
          // eslint-disable-next-line @next/next/no-img-element -- `photo.url` est une route backend authentifiée par cookie, pas un asset optimisable par next/image.
          <img
            key={photo.id}
            src={photo.url}
            alt={`Photo ${label.toLowerCase()}`}
            className="aspect-square w-full rounded-lg border border-border object-cover"
          />
        ))}
        {canUpload ? (
          <label
            className="flex aspect-square cursor-pointer flex-col items-center justify-center gap-1 rounded-lg border-2 border-dashed border-border text-muted-foreground transition-colors hover:border-primary hover:text-foreground"
            aria-disabled={upload.isPending}
          >
            {upload.isPending ? (
              <Loader2 className="size-5 animate-spin" aria-hidden="true" />
            ) : (
              <Camera className="size-5" aria-hidden="true" />
            )}
            <span className="text-xs">Ajouter</span>
            <input
              ref={inputRef}
              type="file"
              accept="image/*"
              capture="environment"
              className="sr-only"
              disabled={upload.isPending}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void handleFile(file);
                e.target.value = "";
              }}
            />
          </label>
        ) : null}
      </div>
    </div>
  );
}
