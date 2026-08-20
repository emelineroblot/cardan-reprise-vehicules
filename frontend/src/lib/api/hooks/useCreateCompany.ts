import { useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import type { Company, CompanyCreate } from "@/lib/api/types";

/** `POST /companies` — création finale, que le remplissage vienne du lookup ou de la saisie manuelle. */
export function useCreateCompany() {
  return useMutation<Company, unknown, CompanyCreate>({
    mutationFn: (body: CompanyCreate) => api.post<Company>("/companies", body),
  });
}
