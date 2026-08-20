import { useMutation } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api/client";
import type { CompanyLookupResponse } from "@/lib/api/types";

/**
 * `GET /companies/lookup/{siret}` (plan.md § 4 décision B). Déclenché à la demande
 * (pas au montage) : c'est une recherche, pas une lecture de ressource.
 *
 * 503 `siret_lookup_unavailable` n'est PAS traité comme une erreur bloquante par
 * l'appelant : c'est le signal du bandeau de bascule manuelle (voir SocieteStep).
 */
export function useCompanyLookup() {
  return useMutation<CompanyLookupResponse, ApiError, string>({
    mutationFn: (siret: string) => api.get<CompanyLookupResponse>(`/companies/lookup/${siret}`),
  });
}
