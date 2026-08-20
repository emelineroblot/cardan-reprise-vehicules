import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import type { Page, Role, UserBrief } from "@/lib/api/types";

export interface UsersFilters {
  role?: Role;
  is_active?: boolean;
  q?: string;
  limit?: number;
  offset?: number;
}

function buildQueryString(filters: UsersFilters): string {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") return;
    params.set(key, String(value));
  });
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

/**
 * `GET /users` (dette J1 fermée en J2) — réservé au rôle `administrateur` côté backend.
 * Usage principal : peupler le `<Select>` de `driver_id` dans `ActionsTransition`
 * (`A_PLANIFIER → AFFECTE`).
 */
export function useUsers(filters: UsersFilters, enabled = true) {
  return useQuery<Page<UserBrief>>({
    queryKey: ["users", filters],
    queryFn: () => api.get<Page<UserBrief>>(`/users${buildQueryString(filters)}`),
    enabled,
  });
}
