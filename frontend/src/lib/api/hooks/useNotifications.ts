import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import type { Notification, Page } from "@/lib/api/types";

const UNREAD_COUNT_KEY = ["notifications", "unread-count"] as const;

/**
 * Chemin nominal des notifications (implementation.md § J2 Backend) : aucune clé requise,
 * persistées en base — pastille + liste ne dépendent JAMAIS du web push réel.
 */
export function useNotifications(unreadOnly = false) {
  return useQuery<Page<Notification>>({
    queryKey: ["notifications", { unreadOnly }],
    queryFn: () => api.get<Page<Notification>>(`/notifications?unread_only=${unreadOnly}&limit=20`),
    refetchInterval: 30_000,
  });
}

export function useUnreadNotificationCount() {
  return useQuery<{ count: number }>({
    queryKey: UNREAD_COUNT_KEY,
    queryFn: () => api.get<{ count: number }>("/notifications/unread-count"),
    refetchInterval: 30_000,
  });
}

export function useMarkNotificationRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post<Notification>(`/notifications/${id}/read`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
      queryClient.invalidateQueries({ queryKey: UNREAD_COUNT_KEY });
    },
  });
}

export function useMarkAllNotificationsRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<{ count: number }>("/notifications/read-all"),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
      queryClient.invalidateQueries({ queryKey: UNREAD_COUNT_KEY });
    },
  });
}
