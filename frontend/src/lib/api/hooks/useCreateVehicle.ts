import { useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import type { Vehicle, VehicleCreate } from "@/lib/api/types";

/**
 * `POST /vehicles` — le dédoublonnage est rejoué côté serveur à la création (plan.md § 4
 * décision A) : renvoie `409 duplicate_probable` sauf si `force_create: true` (posé après
 * arbitrage — voir `implementation.md` § Backend « Contrat final figé »). Un `probable`
 * sans `force_create` reste bloquant ; l'appelant doit être prêt à rouvrir l'écran
 * d'arbitrage sur ce code.
 */
export function useCreateVehicle() {
  return useMutation<Vehicle, unknown, VehicleCreate>({
    mutationFn: (draft: VehicleCreate) => api.post<Vehicle>("/vehicles", draft),
  });
}
