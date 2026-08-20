import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import type {
  AllowedTransitionsResponse,
  TransitionOption,
  Vehicle,
  VehicleTransitionCreate,
} from "@/lib/api/types";

/**
 * `GET /vehicles/{id}/transitions` — boutons d'action DÉRIVÉS de cette liste, jamais
 * codés en dur côté front (plan.md § 6 vague 4, § 5.3 : l'automate ne vit qu'en un seul
 * endroit, `app/services/state_machine.py`).
 *
 * Réponse enveloppée `{ "allowed": TransitionOption[] }` (contrat backend final) — jamais
 * un tableau nu. `TransitionOption` porte `label`, `requires_reason` et
 * `requires_payload_fields`, déjà déterminés par les gardes contextuelles côté serveur :
 * un bouton affiché ici est garanti exécutable (les gardes qui dépendent d'un état en
 * base — inspection, work order — sont déjà appliquées par le backend, § 5.3).
 */
export function useVehicleTransitions(vehicleId: string | undefined) {
  return useQuery<TransitionOption[]>({
    queryKey: ["vehicles", vehicleId, "transitions"],
    queryFn: async () => {
      const res = await api.get<AllowedTransitionsResponse>(`/vehicles/${vehicleId}/transitions`);
      return res.allowed;
    },
    enabled: Boolean(vehicleId),
  });
}

export function useApplyTransition(vehicleId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation<Vehicle, unknown, VehicleTransitionCreate>({
    mutationFn: (body: VehicleTransitionCreate) =>
      api.post<Vehicle>(`/vehicles/${vehicleId}/transitions`, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vehicles", vehicleId] });
      queryClient.invalidateQueries({ queryKey: ["vehicles"] });
    },
  });
}
