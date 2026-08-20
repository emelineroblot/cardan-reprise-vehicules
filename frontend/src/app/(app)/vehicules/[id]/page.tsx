"use client";

import { use } from "react";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { StateBadge } from "@/components/ui/state-badge";
import { LoadingState } from "@/components/ui/loading-state";
import { ErrorState } from "@/components/ui/error-state";
import { Button } from "@/components/ui/button";
import { HistoriqueEtats } from "@/components/domain/HistoriqueEtats";
import { ActionsTransition } from "@/components/domain/ActionsTransition";
import { useVehicle } from "@/lib/api/hooks/useVehicle";
import { formatDate, formatDateTime, formatImmatriculation, formatMoneyCents } from "@/lib/format";
import { BOITE_LABELS, ENERGIE_LABELS, REFUS_MOTIF_LABELS } from "@/lib/api/types";

export default function VehiculeDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data: vehicle, isLoading, error, refetch } = useVehicle(id);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Button asChild variant="ghost" size="sm" className="-ml-2">
          <Link href="/vehicules">
            <ArrowLeft className="size-4" aria-hidden="true" />
            Retour à la liste
          </Link>
        </Button>
      </div>

      {isLoading ? <LoadingState label="Chargement de la fiche…" /> : null}
      {error ? <ErrorState error={error} title="Fiche introuvable" onRetry={() => refetch()} /> : null}

      {vehicle ? (
        <>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-sm text-muted-foreground">{vehicle.reference}</p>
              <h1 className="text-2xl font-semibold tracking-tight">
                {vehicle.marque} {vehicle.modele} {vehicle.version ?? ""}
              </h1>
              {vehicle.company ? (
                <p className="text-sm text-muted-foreground">{vehicle.company.denomination}</p>
              ) : null}
            </div>
            <StateBadge state={vehicle.state} className="text-sm" />
          </div>

          <section aria-labelledby="actions-heading" className="flex flex-col gap-2">
            <h2 id="actions-heading" className="text-sm font-medium text-muted-foreground">
              Actions
            </h2>
            <ActionsTransition vehicleId={vehicle.id} />
          </section>

          <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
            <div className="flex flex-col gap-6">
              <section aria-labelledby="identite-heading" className="rounded-lg border border-border p-4">
                <h2 id="identite-heading" className="mb-3 font-medium text-foreground">
                  Identité du véhicule
                </h2>
                <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-3">
                  <Field label="VIN" value={vehicle.vin || "—"} />
                  <Field label="Immatriculation" value={formatImmatriculation(vehicle.immatriculation)} />
                  <Field label="Énergie" value={vehicle.energie ? ENERGIE_LABELS[vehicle.energie] : "—"} />
                  <Field label="Boîte" value={vehicle.boite ? BOITE_LABELS[vehicle.boite] : "—"} />
                  <Field label="Couleur" value={vehicle.couleur || "—"} />
                  <Field
                    label="1ʳᵉ mise en circulation"
                    value={formatDate(vehicle.date_mise_en_circulation)}
                  />
                  <Field
                    label="Kilométrage"
                    value={vehicle.kilometrage != null ? `${vehicle.kilometrage.toLocaleString("fr-FR")} km` : "—"}
                  />
                  <Field label="Date de proposition" value={formatDate(vehicle.date_proposition)} />
                </dl>
                {vehicle.commentaire ? (
                  <p className="mt-3 text-sm text-muted-foreground">{vehicle.commentaire}</p>
                ) : null}
              </section>

              <section aria-labelledby="finances-heading" className="rounded-lg border border-border p-4">
                <h2 id="finances-heading" className="mb-3 font-medium text-foreground">
                  Éléments financiers
                </h2>
                <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-3">
                  <Field label="Prix négocié" value={formatMoneyCents(vehicle.prix_achat_negocie_cents)} />
                  <Field
                    label="Valeur de revente estimée"
                    value={formatMoneyCents(vehicle.valeur_revente_estimee_cents)}
                  />
                  <Field label="Frais de transport" value={formatMoneyCents(vehicle.frais_transport_cents)} />
                </dl>
              </section>

              {vehicle.state === "REFUSE" ? (
                <section className="rounded-lg border border-rose-200 bg-rose-50 p-4 dark:bg-rose-950/30">
                  <h2 className="mb-1 font-medium text-foreground">Refus</h2>
                  <p className="text-sm text-muted-foreground">
                    {vehicle.refus_motif ? REFUS_MOTIF_LABELS[vehicle.refus_motif] : "Motif non renseigné"}
                    {vehicle.refus_commentaire ? ` — ${vehicle.refus_commentaire}` : ""}
                  </p>
                </section>
              ) : null}

              <p className="text-xs text-muted-foreground">
                Créée le {formatDateTime(vehicle.created_at)} · dernière mise à jour le{" "}
                {formatDateTime(vehicle.updated_at)}
              </p>
            </div>

            <section aria-labelledby="historique-heading" className="rounded-lg border border-border p-4">
              <h2 id="historique-heading" className="mb-3 font-medium text-foreground">
                Historique des états
              </h2>
              <HistoriqueEtats history={vehicle.state_history} />
            </section>
          </div>
        </>
      ) : null}
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-medium text-foreground">{value}</dd>
    </div>
  );
}
