import { useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import type { DuplicateReview, DuplicateReviewCreate } from "@/lib/api/types";

/**
 * `POST /duplicate-reviews` — verdict d'arbitrage, deuxième temps du flux après
 * `force_create`/`force_update` (contrat backend final). Un verdict `not_duplicate` est
 * définitif (plan.md § 4 décision A étape 5) : la paire n'est plus jamais reproposée.
 * `score` et `features` sont obligatoires et se renvoient tels quels depuis le candidat
 * reçu par `duplicate-check` — aucune transformation nécessaire.
 *
 * Réponse : un seul `DuplicateReviewRead` (pas un tableau).
 */
export function useDuplicateReview() {
  return useMutation<DuplicateReview, unknown, DuplicateReviewCreate>({
    mutationFn: (body: DuplicateReviewCreate) => api.post<DuplicateReview>("/duplicate-reviews", body),
  });
}
