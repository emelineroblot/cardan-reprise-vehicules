import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import type { PipelineCounts } from "@/lib/api/types";

/**
 * `GET /vehicles/pipeline-counts` — Kanban administrateur (brief J3). Lecture **opérationnelle
 * et live** (`vehicle` en direct, jamais un mart, implementation.md § J3 Backend) : distincte de
 * `GET /analytics/pipeline-etat` (dashboard, à la fraîcheur du dernier refresh). Rafraîchie
 * périodiquement, comme `useNotifications` (30 s) — un déplacement de carte invalide déjà la
 * requête explicitement (`useApplyTransition`), le minuteur ne couvre que les transitions faites
 * par d'autres utilisateurs pendant que l'écran reste ouvert.
 */
export function usePipelineCounts() {
  return useQuery<PipelineCounts>({
    queryKey: ["vehicles", "pipeline-counts"],
    queryFn: () => api.get<PipelineCounts>("/vehicles/pipeline-counts"),
    refetchInterval: 30_000,
  });
}
