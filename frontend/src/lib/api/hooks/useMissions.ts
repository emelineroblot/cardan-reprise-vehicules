import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import type { Mission, MissionState, Page } from "@/lib/api/types";

export interface MissionsFilters {
  state?: MissionState;
  driver_id?: string;
  limit?: number;
  offset?: number;
}

function buildQueryString(filters: MissionsFilters): string {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") return;
    params.set(key, String(value));
  });
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

/**
 * `GET /missions` — lecture seule (contrat J2 : toute écriture passe par
 * `POST /vehicles/{id}/transitions`, jamais un endpoint mission dédié). Un `chauffeur` ne
 * voit que ses missions (scoping serveur, `driver_id` de la query ignoré pour ce rôle).
 */
export function useMissions(filters: MissionsFilters) {
  return useQuery<Page<Mission>>({
    queryKey: ["missions", filters],
    queryFn: () => api.get<Page<Mission>>(`/missions${buildQueryString(filters)}`),
  });
}

/** `GET /missions/{id}` — `404 not_found` si absente ou hors scope de l'appelant. */
export function useMission(id: string | undefined) {
  return useQuery<Mission>({
    queryKey: ["missions", id],
    queryFn: () => api.get<Mission>(`/missions/${id}`),
    enabled: Boolean(id),
  });
}
