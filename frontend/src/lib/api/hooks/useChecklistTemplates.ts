import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import { getCachedChecklistTemplate, putCachedChecklistTemplate } from "@/lib/offline/db";
import type { ChecklistTemplate, ChecklistTemplateBrief } from "@/lib/api/types";

/** `GET /checklist-templates?is_active=true` — ouvert à tout rôle authentifié. */
export function useChecklistTemplates() {
  return useQuery<ChecklistTemplateBrief[]>({
    queryKey: ["checklist-templates"],
    queryFn: () => api.get<ChecklistTemplateBrief[]>("/checklist-templates?is_active=true"),
  });
}

/**
 * `GET /checklist-templates/{id}` — items triés par `ordre`, groupés par `categorie` côté
 * front (jamais recalculé côté serveur). Mis en cache dans IndexedDB (décision C) : le
 * référentiel doit rester lisible hors ligne une fois consulté une première fois — c'est
 * une donnée de référence, pas un état métier, aucun risque de désynchronisation grave à
 * servir une version en cache le temps d'un contrôle.
 */
export function useChecklistTemplate(templateId: string | undefined) {
  return useQuery<ChecklistTemplate>({
    queryKey: ["checklist-templates", templateId],
    queryFn: async () => {
      if (!templateId) throw new Error("templateId manquant");
      try {
        const template = await api.get<ChecklistTemplate>(`/checklist-templates/${templateId}`);
        await putCachedChecklistTemplate(template);
        return template;
      } catch (error) {
        const cached = await getCachedChecklistTemplate(templateId);
        if (cached) return cached;
        throw error;
      }
    },
    enabled: Boolean(templateId),
    // Référentiel quasi-statique (plan.md § 5.1) : pas de refetch agressif, la version
    // en cache local reste valide toute une session de contrôle terrain.
    staleTime: 10 * 60_000,
  });
}
