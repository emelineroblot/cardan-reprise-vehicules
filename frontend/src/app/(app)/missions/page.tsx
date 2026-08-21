"use client";

import Link from "next/link";
import { ChevronRight, MapPin } from "lucide-react";
import { RoleGuard } from "@/components/domain/RoleGuard";
import { PageHeader } from "@/components/domain/PageHeader";
import { PushSubscribeButton } from "@/components/domain/PushSubscribeButton";
import { LoadingState } from "@/components/ui/loading-state";
import { ErrorState } from "@/components/ui/error-state";
import { EmptyState } from "@/components/ui/empty-state";
import { StateBadge } from "@/components/ui/state-badge";
import { useMissions } from "@/lib/api/hooks/useMissions";
import { formatDateTime } from "@/lib/format/date";
import { MISSION_STATE_LABELS } from "@/lib/api/types";

export default function MissionsPage() {
  return (
    <RoleGuard allowed={["chauffeur", "administrateur"]}>
      <MissionsList />
    </RoleGuard>
  );
}

function MissionsList() {
  const missions = useMissions({ limit: 50 });

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Mes missions"
        description="Contrôles véhicule à effectuer sur place, du rendez-vous à la validation."
        breadcrumb={[{ label: "Mes missions" }]}
        actions={<PushSubscribeButton />}
      />

      {missions.isLoading ? <LoadingState label="Chargement des missions…" /> : null}
      {missions.error ? (
        <ErrorState error={missions.error} title="Missions indisponibles" onRetry={() => missions.refetch()} />
      ) : null}
      {missions.data && missions.data.items.length === 0 ? (
        <EmptyState title="Aucune mission" description="Aucune mission ne vous a été affectée pour l'instant." />
      ) : null}

      <ul className="flex flex-col gap-3">
        {(missions.data?.items ?? []).map((mission) => (
          <li key={mission.id}>
            <Link
              href={`/missions/${mission.id}`}
              className="flex items-center justify-between gap-4 rounded-xl bg-card p-4 ring-1 ring-foreground/10 transition-colors hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
            >
              <div className="flex flex-col gap-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-foreground">
                    {mission.vehicle.marque} {mission.vehicle.modele} {mission.vehicle.version ?? ""}
                  </span>
                  <StateBadge state={mission.vehicle.state} />
                </div>
                <p className="text-sm text-muted-foreground">{mission.vehicle.reference}</p>
                {mission.rdv_at ? (
                  <p className="flex items-center gap-1 text-sm text-muted-foreground">
                    <MapPin className="size-3.5" aria-hidden="true" />
                    Rendez-vous le {formatDateTime(mission.rdv_at)}
                    {mission.rdv_adresse ? ` — ${mission.rdv_adresse}` : ""}
                  </p>
                ) : (
                  <p className="text-sm text-muted-foreground">{MISSION_STATE_LABELS[mission.state]}</p>
                )}
              </div>
              <ChevronRight className="size-5 shrink-0 text-muted-foreground" aria-hidden="true" />
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
