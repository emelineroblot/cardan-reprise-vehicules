import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import type {
  AnalyticsRefreshResponse,
  AnalyticsStatusResponse,
  CycleTemps,
  KpiGlobal,
  PipelineEtat,
  Refus,
  Travaux,
  VehicleState,
  VehiculeMarge,
} from "@/lib/api/types";

/**
 * Couche analytique J3 (brief « Dashboard ») — chaque endpoint est une lecture DIRECTE d'un
 * `mart_*` (implementation.md § J3 Backend) : aucun champ n'est recalculé ici, seulement lu et
 * affiché. Réservés à `administrateur` côté backend.
 */

const ANALYTICS_STATUS_KEY = ["analytics", "status"] as const;

export interface MargeFilters {
  state?: VehicleState;
  sort?: "marge_cents" | "-marge_cents" | "date_proposition" | "-date_proposition";
}

export function useMarge(filters: MargeFilters) {
  const params = new URLSearchParams();
  if (filters.state) params.set("state", filters.state);
  if (filters.sort) params.set("sort", filters.sort);
  const qs = params.toString();
  return useQuery<VehiculeMarge[]>({
    queryKey: ["analytics", "marge", filters],
    queryFn: () => api.get<VehiculeMarge[]>(`/analytics/marge${qs ? `?${qs}` : ""}`),
  });
}

export function useCycleTemps() {
  return useQuery<CycleTemps[]>({
    queryKey: ["analytics", "cycle-temps"],
    queryFn: () => api.get<CycleTemps[]>("/analytics/cycle-temps"),
  });
}

export function usePipelineEtat() {
  return useQuery<PipelineEtat[]>({
    queryKey: ["analytics", "pipeline-etat"],
    queryFn: () => api.get<PipelineEtat[]>("/analytics/pipeline-etat"),
  });
}

export function useRefus() {
  return useQuery<Refus[]>({
    queryKey: ["analytics", "refus"],
    queryFn: () => api.get<Refus[]>("/analytics/refus"),
  });
}

export function useTravaux() {
  return useQuery<Travaux[]>({
    queryKey: ["analytics", "travaux"],
    queryFn: () => api.get<Travaux[]>("/analytics/travaux"),
  });
}

export function useKpiGlobal() {
  return useQuery<KpiGlobal>({
    queryKey: ["analytics", "kpi-global"],
    queryFn: () => api.get<KpiGlobal>("/analytics/kpi-global"),
  });
}

/** `GET /analytics/status` — le dernier `refreshed_at` par mart, affiché « à jour il y a … ». */
export function useAnalyticsStatus() {
  return useQuery<AnalyticsStatusResponse>({
    queryKey: ANALYTICS_STATUS_KEY,
    queryFn: () => api.get<AnalyticsStatusResponse>("/analytics/status"),
  });
}

/** `POST /analytics/refresh` — câblé sur le bouton « Actualiser les indicateurs ». */
export function useRefreshAnalytics() {
  const queryClient = useQueryClient();
  return useMutation<AnalyticsRefreshResponse, unknown, void>({
    mutationFn: () => api.post<AnalyticsRefreshResponse>("/analytics/refresh"),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["analytics"] });
    },
  });
}
