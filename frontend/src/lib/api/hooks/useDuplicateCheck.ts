import { useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import type { DuplicateCheckResult, VehicleCreate } from "@/lib/api/types";

/**
 * `POST /vehicles/duplicate-check` (plan.md § 4 décision A) — appelé au blur du VIN/de
 * l'immatriculation puis rejoué juste avant soumission. Le verdict qui fait autorité
 * reste la création côté serveur (`POST /vehicles`) : ce hook ne fait qu'informer.
 *
 * Corps identique à `VehicleCreate` (contrat backend figé) : `force_create`/
 * `frais_transport_cents` doivent être fournis (défauts non implicites côté client).
 */
export function useDuplicateCheck() {
  return useMutation<DuplicateCheckResult, unknown, VehicleCreate>({
    mutationFn: (draft: VehicleCreate) => api.post<DuplicateCheckResult>("/vehicles/duplicate-check", draft),
  });
}
