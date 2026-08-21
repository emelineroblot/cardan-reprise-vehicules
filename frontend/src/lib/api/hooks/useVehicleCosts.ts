import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import type { VehicleCost, VehicleCostCreate } from "@/lib/api/types";

/** `GET /vehicles/{id}/costs` — tout rôle authentifié pouvant voir le véhicule. */
export function useVehicleCosts(vehicleId: string | undefined) {
  return useQuery<VehicleCost[]>({
    queryKey: ["vehicles", vehicleId, "costs"],
    queryFn: () => api.get<VehicleCost[]>(`/vehicles/${vehicleId}/costs`),
    enabled: Boolean(vehicleId),
  });
}

/**
 * `POST /vehicles/{id}/costs` — **rôle `administrateur` uniquement** (décision d'implémentation
 * J3 : aucun rôle métier dédié comme l'atelier pour ces coûts hors atelier).
 */
export function useAddVehicleCost(vehicleId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation<VehicleCost, unknown, VehicleCostCreate>({
    mutationFn: (body) => api.post<VehicleCost>(`/vehicles/${vehicleId}/costs`, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vehicles", vehicleId, "costs"] });
    },
  });
}
