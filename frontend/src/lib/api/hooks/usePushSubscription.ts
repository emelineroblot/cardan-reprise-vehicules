import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import type { PushPublicKeyResponse, PushSubscriptionCreate, PushSubscriptionRead } from "@/lib/api/types";

/**
 * `GET /notifications/push-public-key` — point de vérité RUNTIME de l'arbitrage « web
 * push optionnel » (implementation.md § J2 Backend). Ne jamais déduire la disponibilité
 * du push d'une variable d'environnement front : si `enabled=false`, le bouton
 * d'abonnement ne doit simplement pas s'afficher.
 */
export function usePushPublicKey() {
  return useQuery<PushPublicKeyResponse>({
    queryKey: ["notifications", "push-public-key"],
    queryFn: () => api.get<PushPublicKeyResponse>("/notifications/push-public-key"),
    staleTime: 5 * 60_000,
  });
}

export function useCreatePushSubscription() {
  const queryClient = useQueryClient();
  return useMutation<PushSubscriptionRead, unknown, PushSubscriptionCreate>({
    mutationFn: (body) => api.post<PushSubscriptionRead>("/notifications/push-subscriptions", body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notifications", "push-subscriptions"] });
    },
  });
}
