"use client";

import { RoleGuard } from "@/components/domain/RoleGuard";
import { PageHeader } from "@/components/domain/PageHeader";
import { KanbanColumn } from "@/components/domain/KanbanColumn";
import { LoadingState } from "@/components/ui/loading-state";
import { ErrorState } from "@/components/ui/error-state";
import { usePipelineCounts } from "@/lib/api/hooks/usePipelineCounts";

export default function PipelinePage() {
  return (
    <RoleGuard allowed={["administrateur"]}>
      <PipelineBoard />
    </RoleGuard>
  );
}

/**
 * Pipeline Kanban administrateur (brief J3) — « où en est mon parc », le premier écran que le
 * dirigeant ouvre. En-têtes de colonnes servis par `GET /vehicles/pipeline-counts`
 * (opérationnel, live, toujours les 11 états même à 0 — implementation.md § J3 Backend) ;
 * chaque colonne charge ensuite un aperçu de son propre contenu (`KanbanColumn`). Manipuler un
 * véhicule (l'affecter, le faire avancer) se fait depuis sa fiche — les actions restent
 * dérivées de `GET /vehicles/{id}/transitions`, jamais dupliquées ici.
 */
function PipelineBoard() {
  const pipeline = usePipelineCounts();

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Pipeline"
        description="Le parc par état, en direct. Cliquez un véhicule pour le manipuler depuis sa fiche."
        breadcrumb={[{ label: "Pipeline" }]}
      />

      {pipeline.isLoading ? <LoadingState label="Chargement du pipeline…" /> : null}
      {pipeline.error ? (
        <ErrorState error={pipeline.error} title="Pipeline indisponible" onRetry={() => pipeline.refetch()} />
      ) : null}

      {pipeline.data ? (
        <div className="flex gap-4 overflow-x-auto pb-2">
          {pipeline.data.counts.map((c) => (
            <KanbanColumn key={c.state} state={c.state} count={c.count} />
          ))}
        </div>
      ) : null}
    </div>
  );
}
