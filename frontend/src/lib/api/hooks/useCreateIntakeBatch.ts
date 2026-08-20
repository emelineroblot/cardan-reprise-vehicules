import { useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import type { IntakeBatch, IntakeBatchCreate } from "@/lib/api/types";

/**
 * `POST /intake-batches` — saisie en lot d'une flotte (plan.md § 4 décision A étape 5) :
 * les membres d'un même lot ne sont jamais comparés entre eux au dédoublonnage.
 */
export function useCreateIntakeBatch() {
  return useMutation<IntakeBatch, unknown, IntakeBatchCreate>({
    mutationFn: (body: IntakeBatchCreate) => api.post<IntakeBatch>("/intake-batches", body),
  });
}
