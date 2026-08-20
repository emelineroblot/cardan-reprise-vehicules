"use client";

import { use } from "react";
import Link from "next/link";
import { ArrowLeft, ClipboardCheck, MapPin, Phone, User } from "lucide-react";
import { RoleGuard } from "@/components/domain/RoleGuard";
import { ActionsTransition } from "@/components/domain/ActionsTransition";
import { Button } from "@/components/ui/button";
import { StateBadge } from "@/components/ui/state-badge";
import { LoadingState } from "@/components/ui/loading-state";
import { ErrorState } from "@/components/ui/error-state";
import { useMission } from "@/lib/api/hooks/useMissions";
import { formatDateTime } from "@/lib/format/date";
import { MISSION_STATE_LABELS } from "@/lib/api/types";

export default function MissionDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <RoleGuard allowed={["chauffeur", "administrateur"]}>
      <MissionDetail missionId={id} />
    </RoleGuard>
  );
}

function MissionDetail({ missionId }: { missionId: string }) {
  const { data: mission, isLoading, error, refetch } = useMission(missionId);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Button asChild variant="ghost" size="sm" className="-ml-2">
          <Link href="/missions">
            <ArrowLeft className="size-4" aria-hidden="true" />
            Retour aux missions
          </Link>
        </Button>
      </div>

      {isLoading ? <LoadingState label="Chargement de la mission…" /> : null}
      {error ? <ErrorState error={error} title="Mission introuvable" onRetry={() => refetch()} /> : null}

      {mission ? (
        <>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-sm text-muted-foreground">{mission.vehicle.reference}</p>
              <h1 className="text-2xl font-semibold tracking-tight">
                {mission.vehicle.marque} {mission.vehicle.modele} {mission.vehicle.version ?? ""}
              </h1>
              <p className="mt-1 text-sm text-muted-foreground">{MISSION_STATE_LABELS[mission.state]}</p>
            </div>
            <StateBadge state={mission.vehicle.state} className="text-sm" />
          </div>

          {mission.rdv_at || mission.rdv_adresse || mission.rdv_contact_nom ? (
            <section aria-labelledby="rdv-heading" className="rounded-lg border border-border p-4">
              <h2 id="rdv-heading" className="mb-3 font-medium text-foreground">
                Rendez-vous
              </h2>
              <dl className="flex flex-col gap-2 text-sm">
                {mission.rdv_at ? (
                  <div className="flex items-center gap-2">
                    <MapPin className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                    <span>{formatDateTime(mission.rdv_at)}</span>
                  </div>
                ) : null}
                {mission.rdv_adresse ? (
                  <div className="flex items-center gap-2 pl-6 text-muted-foreground">{mission.rdv_adresse}</div>
                ) : null}
                {mission.rdv_contact_nom ? (
                  <div className="flex items-center gap-2">
                    <User className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                    <span>{mission.rdv_contact_nom}</span>
                  </div>
                ) : null}
                {mission.rdv_contact_telephone ? (
                  <div className="flex items-center gap-2 pl-6">
                    <Phone className="size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
                    <a href={`tel:${mission.rdv_contact_telephone}`} className="text-primary underline-offset-2 hover:underline">
                      {mission.rdv_contact_telephone}
                    </a>
                  </div>
                ) : null}
              </dl>
            </section>
          ) : null}

          {mission.vehicle.state === "CONTROLE_EN_COURS" ? (
            <Button asChild size="lg" className="h-14 justify-start gap-3 text-base">
              <Link href={`/missions/${mission.id}/controle`}>
                <ClipboardCheck className="size-5" aria-hidden="true" />
                Ouvrir le contrôle véhicule
              </Link>
            </Button>
          ) : null}

          <section aria-labelledby="actions-heading" className="flex flex-col gap-2">
            <h2 id="actions-heading" className="text-sm font-medium text-muted-foreground">
              Actions
            </h2>
            <ActionsTransition vehicleId={mission.vehicle.id} size="lg" />
          </section>
        </>
      ) : null}
    </div>
  );
}
