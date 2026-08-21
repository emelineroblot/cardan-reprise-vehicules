import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import type { Page, VehicleListItem, VehicleState } from "@/lib/api/types";

export interface VehiclesFilters {
  state?: VehicleState;
  company_id?: string;
  marque?: string;
  created_by_id?: string;
  date_proposition_from?: string;
  date_proposition_to?: string;
  q?: string;
  sort?: string;
  limit?: number;
  offset?: number;
}

function buildQueryString(filters: VehiclesFilters): string {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") return;
    params.set(key, String(value));
  });
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

/**
 * `GET /vehicles` — filtres, tri, pagination (plan.md § 3.5, liste de suivi § 6 vague 4).
 * `VehicleListItem` (pas `Vehicle`) : le backend n'embarque pas `state_history` en liste
 * (évite le N+1 signalé en revue), mais embarque `company` (dénomination affichée).
 */
export function useVehicles(filters: VehiclesFilters, enabled = true) {
  return useQuery<Page<VehicleListItem>>({
    queryKey: ["vehicles", filters],
    queryFn: () => api.get<Page<VehicleListItem>>(`/vehicles${buildQueryString(filters)}`),
    placeholderData: keepPreviousData,
    enabled,
  });
}
