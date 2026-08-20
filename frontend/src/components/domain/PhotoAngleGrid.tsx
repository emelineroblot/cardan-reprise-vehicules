"use client";

import { useEffect, useMemo, type ReactNode } from "react";
import { Camera, Check, Clock, Plus, RotateCcw, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { PHOTO_ANGLE_LABELS, type PhotoAngle } from "@/lib/api/types";
import type { LocalPhoto } from "@/lib/offline/types";

interface PhotoAngleGridProps {
  /** Angles requis — `null` tant que le premier `GET .../required-angles` n'a pas abouti
   * (voir `lib/offline/draft.ts::computeAngleProgress`) : la grille affiche alors les 12
   * angles connus côté présentation, sans pouvoir encore certifier la complétude. */
  requiredAngles: string[] | null;
  photos: LocalPhoto[];
  onCapture: (file: File, angle: PhotoAngle) => Promise<void>;
  onRetake: (photo: LocalPhoto) => Promise<void>;
  maxPhotos: number;
}

const PRESENTATION_ANGLES: PhotoAngle[] = [
  "face_avant",
  "trois_quarts_avant_gauche",
  "profil_gauche",
  "trois_quarts_arriere_gauche",
  "face_arriere",
  "trois_quarts_arriere_droit",
  "profil_droit",
  "trois_quarts_avant_droit",
  "interieur_avant",
  "interieur_arriere",
  "coffre",
  "compteur",
];

export function PhotoAngleGrid({ requiredAngles, photos, onCapture, onRetake, maxPhotos }: PhotoAngleGridProps) {
  const angles = requiredAngles ?? PRESENTATION_ANGLES;
  const defautPhotos = photos.filter((p) => p.angle === "defaut");
  const totalCount = photos.length;
  const atQuota = totalCount >= maxPhotos;

  return (
    <div className="flex flex-col gap-4">
      {requiredAngles === null ? (
        <p className="flex items-center gap-2 rounded-md bg-muted px-3 py-2 text-sm text-muted-foreground">
          <TriangleAlert className="size-4 shrink-0" aria-hidden="true" />
          Liste des angles obligatoires en attente de connexion — la capture reste possible, la
          vérification finale se fera au retour du réseau.
        </p>
      ) : null}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {angles.map((angle) => {
          const photo = photos.find((p) => p.angle === angle);
          return (
            <AngleTile
              key={angle}
              angle={angle as PhotoAngle}
              photo={photo}
              disabled={!photo && atQuota}
              onCapture={(file) => onCapture(file, angle as PhotoAngle)}
              onRetake={photo ? () => onRetake(photo) : undefined}
            />
          );
        })}
      </div>

      <div className="flex flex-col gap-2">
        <h3 className="text-sm font-medium text-foreground">Photos de défauts constatés (optionnel)</h3>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {defautPhotos.map((photo) => (
            <AngleTile key={photo.client_uuid} angle="defaut" photo={photo} onRetake={() => onRetake(photo)} />
          ))}
          <CaptureTile
            label="Ajouter un défaut"
            icon={<Plus className="size-6" aria-hidden="true" />}
            disabled={atQuota}
            onCapture={(file) => onCapture(file, "defaut")}
          />
        </div>
      </div>

      <p className="text-xs text-muted-foreground">
        {totalCount} / {maxPhotos} photos utilisées pour ce véhicule.
      </p>
    </div>
  );
}

function AngleTile({
  angle,
  photo,
  disabled,
  onCapture,
  onRetake,
}: {
  angle: PhotoAngle;
  photo: LocalPhoto | undefined;
  disabled?: boolean;
  onCapture?: (file: File) => void;
  onRetake?: () => void;
}) {
  if (!photo) {
    return (
      <CaptureTile
        label={PHOTO_ANGLE_LABELS[angle]}
        icon={<Camera className="size-6" aria-hidden="true" />}
        disabled={disabled}
        onCapture={onCapture as (file: File) => void}
      />
    );
  }

  // `failed_permanent` (échec définitif — 409/422, ou plafond de tentatives atteint,
  // `sync.ts::isDefinitivePhotoError`) doit rester reprenable : c'est la SEULE issue offerte
  // au chauffeur pour cet angle, la photo n'étant plus jamais rejouée automatiquement (revue
  // finale § 🟠 n°1).
  const canRetake =
    photo.upload_state === "queued" || photo.upload_state === "failed" || photo.upload_state === "failed_permanent";

  return (
    <div className="relative flex flex-col overflow-hidden rounded-lg border border-border">
      <PhotoThumbnail photo={photo} />
      <div className="flex items-center justify-between gap-1 px-2 py-1.5 text-xs">
        <span className="truncate text-muted-foreground">{PHOTO_ANGLE_LABELS[angle]}</span>
        <PhotoStatusIcon photo={photo} />
      </div>
      {canRetake && onRetake ? (
        <Button
          type="button"
          variant="secondary"
          size="sm"
          className="absolute right-1 top-1 h-7 w-7 p-0"
          aria-label={`Reprendre la photo — ${PHOTO_ANGLE_LABELS[angle]}`}
          onClick={onRetake}
        >
          <RotateCcw className="size-3.5" aria-hidden="true" />
        </Button>
      ) : null}
    </div>
  );
}

function PhotoStatusIcon({ photo }: { photo: LocalPhoto }) {
  if (photo.upload_state === "sent") {
    return (
      <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
        <Check className="size-3.5" aria-hidden="true" />
        <span className="sr-only">Envoyée</span>
      </span>
    );
  }
  if (photo.upload_state === "failed_permanent") {
    return (
      <span
        className="flex items-center gap-1 text-destructive"
        title={photo.error ? `Échec définitif — ${photo.error}. Reprenez cette photo.` : "Échec définitif — reprenez cette photo."}
      >
        <TriangleAlert className="size-3.5" aria-hidden="true" />
        <span className="sr-only">Échec définitif, reprise nécessaire — {photo.error}</span>
      </span>
    );
  }
  if (photo.upload_state === "failed") {
    return (
      <span
        className="flex items-center gap-1 text-destructive"
        title={photo.error ? `${photo.error} — nouvel envoi automatique en cours.` : "Échec passager — nouvel envoi automatique en cours."}
      >
        <TriangleAlert className="size-3.5" aria-hidden="true" />
        <span className="sr-only">Échec passager, nouvelle tentative automatique — {photo.error}</span>
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1 text-amber-600 dark:text-amber-400">
      <Clock className="size-3.5" aria-hidden="true" />
      <span className="sr-only">En attente d&apos;envoi</span>
    </span>
  );
}

function PhotoThumbnail({ photo }: { photo: LocalPhoto }) {
  // `URL.createObjectURL` calculée pendant le rendu (comme `MoneyInput`, § J1) plutôt que
  // posée en state depuis un effet : seul le nettoyage (`revokeObjectURL`) est un effet de
  // bord, jamais un `setState`.
  const url = useMemo(() => URL.createObjectURL(photo.blob), [photo.blob]);
  useEffect(() => () => URL.revokeObjectURL(url), [url]);

  return (
    // eslint-disable-next-line @next/next/no-img-element -- aperçu d'un Blob local (`URL.createObjectURL`), `next/image` n'a rien à optimiser ici.
    <img src={url} alt="" className="aspect-square w-full object-cover" />
  );
}

function CaptureTile({
  label,
  icon,
  disabled,
  onCapture,
}: {
  label: string;
  icon: ReactNode;
  disabled?: boolean;
  onCapture: (file: File) => void;
}) {
  return (
    <label
      className={cn(
        "flex aspect-square flex-col items-center justify-center gap-1.5 rounded-lg border-2 border-dashed border-border p-2 text-center text-xs text-muted-foreground transition-colors",
        disabled ? "cursor-not-allowed opacity-50" : "cursor-pointer hover:border-primary hover:text-foreground",
      )}
    >
      {icon}
      <span>{label}</span>
      <input
        type="file"
        accept="image/*"
        capture="environment"
        className="sr-only"
        disabled={disabled}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onCapture(file);
          // Réinitialise pour permettre de reprendre exactement le même angle juste après
          // un `onRetake` sans que le navigateur ignore une sélection « identique ».
          e.target.value = "";
        }}
      />
    </label>
  );
}
