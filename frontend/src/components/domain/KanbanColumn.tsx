"use client";

import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { LoadingState } from "@/components/ui/loading-state";
import { ErrorState } from "@/components/ui/error-state";
import { useVehicles } from "@/lib/api/hooks/useVehicles";
import { formatMoneyCents } from "@/lib/format";
import { VEHICLE_STATE_LABELS, type VehicleState } from "@/lib/api/types";

const COLUMN_PREVIEW_LIMIT = 6;

interface KanbanColumnProps {
  state: VehicleState;
  count: number;
}

/**
 * Une colonne du Kanban administrateur (brief J3) — un aperçu direct des `COLUMN_PREVIEW_LIMIT`
 * véhicules les plus récents de l'état, avec un lien vers la liste filtrée complète. Le
 * comptage d'en-tête vient de `GET /vehicles/pipeline-counts` (opérationnel, live) ; l'aperçu
 * de contenu vient de `GET /vehicles?state=…` (inchangé depuis J1) — deux lectures distinctes,
 * comme le documente le contrat J3.
 */
export function KanbanColumn({ state, count }: KanbanColumnProps) {
  // N'interroge le contenu que si la colonne n'est pas vide : une colonne à 0 n'a rien à
  // charger, et ça évite des requêtes systématiques dont plusieurs ne serviraient à rien sur
  // un parc de démo à faible profondeur par état.
  const vehicles = useVehicles(
    { state, limit: COLUMN_PREVIEW_LIMIT, sort: "-date_proposition" },
    count > 0,
  );

  return (
    <div className="flex w-72 shrink-0 flex-col gap-3 rounded-lg border border-border bg-muted/30 p-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-foreground">{VEHICLE_STATE_LABELS[state]}</h3>
        <Badge variant="secondary">{count}</Badge>
      </div>

      {count === 0 ? (
        <p className="py-6 text-center text-xs text-muted-foreground">Aucun véhicule</p>
      ) : vehicles.isLoading ? (
        <LoadingState label="Chargement…" />
      ) : vehicles.error ? (
        <ErrorState error={vehicles.error} title="Indisponible" onRetry={() => vehicles.refetch()} />
      ) : (
        <ul className="flex flex-col gap-2">
          {(vehicles.data?.items ?? []).map((v) => (
            <li key={v.id}>
              <Link
                href={`/vehicules/${v.id}`}
                className="flex flex-col gap-0.5 rounded-md border border-border bg-card p-2.5 text-sm transition-colors hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
              >
                <span className="font-medium text-foreground">
                  {v.marque} {v.modele}
                </span>
                <span className="text-xs text-muted-foreground">{v.reference}</span>
                {v.company ? <span className="text-xs text-muted-foreground">{v.company.denomination}</span> : null}
                {v.prix_achat_negocie_cents !== null ? (
                  <span className="text-xs tabular-nums text-muted-foreground">
                    {formatMoneyCents(v.prix_achat_negocie_cents)}
                  </span>
                ) : null}
              </Link>
            </li>
          ))}
        </ul>
      )}

      {count > COLUMN_PREVIEW_LIMIT ? (
        <Link
          href={`/vehicules?state=${state}`}
          className="text-center text-xs font-medium text-primary hover:underline"
        >
          Voir les {count} véhicules
        </Link>
      ) : null}
    </div>
  );
}
