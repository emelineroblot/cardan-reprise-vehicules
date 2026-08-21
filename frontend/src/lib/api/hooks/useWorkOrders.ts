import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import type { WorkOrder, WorkOrderLine, WorkOrderLineCreate, WorkOrderStateUpdate } from "@/lib/api/types";

/**
 * `GET /vehicles/{id}/work-orders` — tout rôle authentifié pouvant voir le véhicule
 * (`scope_vehicles`, implementation.md § J3 Backend). Triée `requested_at` croissant côté
 * serveur, avec ses `lines`.
 */
export function useVehicleWorkOrders(vehicleId: string | undefined) {
  return useQuery<WorkOrder[]>({
    queryKey: ["vehicles", vehicleId, "work-orders"],
    queryFn: () => api.get<WorkOrder[]>(`/vehicles/${vehicleId}/work-orders`),
    enabled: Boolean(vehicleId),
  });
}

/**
 * `POST /work-orders/{id}/state` — rôles `atelier`/`administrateur`. Mini-automate séparé de
 * celui du véhicule (`demande → en_cours|annule`, `en_cours → termine|annule`), **pas de
 * `GET .../transitions` dédié côté backend** pour ce sous-automate (contrat J3) : la table des
 * cibles permises est donc portée côté front par `lib/workOrders/automate.ts`, pas par cette
 * mutation — elle se contente de poster et de laisser le `409 invalid_transition`/`conflict`
 * du serveur faire foi en dernier ressort.
 */
export function useTransitionWorkOrderState(vehicleId: string | undefined, workOrderId: string) {
  const queryClient = useQueryClient();
  return useMutation<WorkOrder, unknown, WorkOrderStateUpdate>({
    mutationFn: (body) => api.post<WorkOrder>(`/work-orders/${workOrderId}/state`, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vehicles", vehicleId, "work-orders"] });
      queryClient.invalidateQueries({ queryKey: ["vehicles", vehicleId, "transitions"] });
      queryClient.invalidateQueries({ queryKey: ["vehicles", vehicleId] });
      queryClient.invalidateQueries({ queryKey: ["vehicles", "pipeline-counts"] });
    },
  });
}

/**
 * `POST /work-orders/{id}/lines` — rôles `atelier`/`administrateur`. `montant_cents` est une
 * colonne `GENERATED` côté base (`round(quantite * prix_unitaire_cents)`) : jamais calculée
 * côté client, la réponse `201` fait foi.
 */
export function useAddWorkOrderLine(vehicleId: string | undefined, workOrderId: string) {
  const queryClient = useQueryClient();
  return useMutation<WorkOrderLine, unknown, WorkOrderLineCreate>({
    mutationFn: (body) => api.post<WorkOrderLine>(`/work-orders/${workOrderId}/lines`, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vehicles", vehicleId, "work-orders"] });
      // Une ligne de coût ouvre potentiellement la garde « clos ⇒ ≥ 1 ligne » : les boutons de
      // transition véhicule (TRAVAUX_EN_COURS → TRAVAUX_TERMINES) peuvent en dépendre.
      queryClient.invalidateQueries({ queryKey: ["vehicles", vehicleId, "transitions"] });
    },
  });
}
