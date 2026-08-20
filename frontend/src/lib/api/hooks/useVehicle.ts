import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import type { Vehicle } from "@/lib/api/types";

/** `GET /vehicles/{id}` — fiche véhicule. */
export function useVehicle(id: string | undefined) {
  return useQuery<Vehicle>({
    queryKey: ["vehicles", id],
    queryFn: () => api.get<Vehicle>(`/vehicles/${id}`),
    enabled: Boolean(id),
  });
}
