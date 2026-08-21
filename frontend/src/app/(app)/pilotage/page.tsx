"use client";

import { RoleGuard } from "@/components/domain/RoleGuard";
import { AnalyticsFreshnessBar } from "@/components/domain/dashboard/AnalyticsFreshnessBar";
import { KpiRow } from "@/components/domain/dashboard/KpiRow";
import { MargeSection } from "@/components/domain/dashboard/MargeSection";
import { CycleTempsSection } from "@/components/domain/dashboard/CycleTempsSection";
import { RefusSection } from "@/components/domain/dashboard/RefusSection";
import { TravauxSection } from "@/components/domain/dashboard/TravauxSection";
import { PipelineEtatSection } from "@/components/domain/dashboard/PipelineEtatSection";

export default function PilotagePage() {
  return (
    <RoleGuard allowed={["administrateur"]}>
      <Dashboard />
    </RoleGuard>
  );
}

/**
 * Tableau de bord — l'écran décisif du portfolio (brief J3). Marge par véhicule, délai de
 * cycle, taux de refus, coût moyen des travaux : les quatre indicateurs demandés par le brief,
 * chacun lu directement dans son mart (`GET /analytics/*`), jamais recalculé côté client.
 */
function Dashboard() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Tableau de bord</h1>
        <p className="text-sm text-muted-foreground">
          Marge par véhicule, délai de cycle, taux de refus, coût moyen des travaux — lus dans
          la couche analytique.
        </p>
      </div>

      <AnalyticsFreshnessBar />
      <KpiRow />
      <MargeSection />
      <div className="grid gap-6 lg:grid-cols-2">
        <CycleTempsSection />
        <PipelineEtatSection />
      </div>
      <RefusSection />
      <TravauxSection />
    </div>
  );
}
