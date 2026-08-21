import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import { compressImage } from "@/lib/offline/image";
import { sha256Hex } from "@/lib/offline/checksum";
import type { Photo, PhotoPhase } from "@/lib/api/types";

/**
 * `GET /vehicles/{id}/photos?work_order_id=&phase=` — photos avant/après travaux (brief J3).
 * Contrairement au contrôle terrain (J2), l'atelier n'a pas de brouillon local à synchroniser :
 * l'envoi est direct, sans file d'attente IndexedDB — l'atelier travaille sur un poste avec
 * réseau (pas le même contexte que le contrôle en extérieur qui a motivé le moteur hors ligne
 * de J2, plan.md § 4 décision C).
 */
export function useWorkOrderPhotos(vehicleId: string | undefined, workOrderId: string, phase: PhotoPhase) {
  return useQuery<Photo[]>({
    queryKey: ["vehicles", vehicleId, "photos", { workOrderId, phase }],
    queryFn: () =>
      api.get<Photo[]>(`/vehicles/${vehicleId}/photos?work_order_id=${workOrderId}&phase=${phase}`),
    enabled: Boolean(vehicleId),
  });
}

interface UploadWorkOrderPhotoInput {
  file: File;
  phase: PhotoPhase;
}

/**
 * Upload direct d'une photo avant/après travaux — mêmes champs de formulaire que J2
 * (`checksum_sha256` recalculé et vérifié côté serveur, `angle` fixé à `"defaut"`, seul angle
 * répétable et pertinent hors du parcours de contrôle imposé, plan.md § 6 « Parcours photo »),
 * `work_order_id` remplace `inspection_id` (contrat J3 : l'un OU l'autre selon `phase`, jamais
 * les deux). Compression client réutilisée telle quelle (`lib/offline/image.ts`).
 */
export function useUploadWorkOrderPhoto(vehicleId: string | undefined, workOrderId: string) {
  const queryClient = useQueryClient();
  return useMutation<Photo, unknown, UploadWorkOrderPhotoInput>({
    mutationFn: async ({ file, phase }) => {
      const { blob, width, height } = await compressImage(file);
      const checksum = await sha256Hex(blob);
      const formData = new FormData();
      formData.append("file", blob, `${crypto.randomUUID()}.jpg`);
      formData.append("client_uuid", crypto.randomUUID());
      formData.append("angle", "defaut");
      formData.append("phase", phase);
      formData.append("captured_at", new Date().toISOString());
      formData.append("checksum_sha256", checksum);
      formData.append("width", String(width));
      formData.append("height", String(height));
      formData.append("work_order_id", workOrderId);
      return api.upload<Photo>(`/vehicles/${vehicleId}/photos`, formData);
    },
    onSuccess: (_photo, variables) => {
      queryClient.invalidateQueries({
        queryKey: ["vehicles", vehicleId, "photos", { workOrderId, phase: variables.phase }],
      });
    },
  });
}
