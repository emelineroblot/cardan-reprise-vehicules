"use client";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { StateBadge } from "@/components/ui/state-badge";
import { formatDate } from "@/lib/format/date";
import { formatImmatriculation } from "@/lib/format/immatriculation";
import {
  ENERGIE_LABELS,
  REFUS_MOTIF_LABELS,
  type DuplicateCandidate,
  type DuplicateReviewVerdict,
  type Energie,
} from "@/lib/api/types";
import type { VehiculeFormValues } from "@/lib/validation/vehicule";

interface ArbitrageDoublonProps {
  open: boolean;
  vehicleLabel: string;
  draft: VehiculeFormValues;
  candidate: DuplicateCandidate;
  allowBatchScope: boolean;
  isSubmitting?: boolean;
  onDecision: (verdict: DuplicateReviewVerdict, scope: "pair" | "batch") => void;
}

const SCORE_ROWS: { key: keyof DuplicateCandidate["features"]; label: string; weight: string }[] = [
  { key: "s_modele", label: "Marque / modèle / version", weight: "40 %" },
  { key: "s_date", label: "Proximité de date de proposition", weight: "25 %" },
  { key: "s_km", label: "Proximité de kilométrage", weight: "20 %" },
  { key: "s_energie", label: "Énergie identique", weight: "15 %" },
];

/**
 * Écran d'arbitrage — doublon probable (score ≥ 0,85, plan.md § 4 décision A étape 4).
 * Comparaison côte à côte + composantes du score en clair : jamais un nombre nu.
 */
export function ArbitrageDoublon({
  open,
  vehicleLabel,
  draft,
  candidate,
  allowBatchScope,
  isSubmitting,
  onDecision,
}: ArbitrageDoublonProps) {
  // Candidat PLAT (contrat backend final, implementation.md § Backend « Contrat final
  // figé ») : `vehicle_id`, `reference`, `marque`... au même niveau que `score`/`features`,
  // jamais un `{ vehicle: {...} }` imbriqué.
  const { features, score } = candidate;

  return (
    <Dialog open={open}>
      <DialogContent className="max-w-2xl" showCloseButton={false} onEscapeKeyDown={(e) => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle>Doublon potentiel — {vehicleLabel}</DialogTitle>
          <DialogDescription>
            Un véhicule très proche existe déjà dans le parc. Vérifiez la comparaison avant de
            continuer : l&apos;enregistrement est bloqué tant que ce doublon n&apos;est pas levé.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="rounded-lg border border-border p-3">
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Fiche en cours de saisie
            </p>
            <ComparisonFields
              marque={draft.marque}
              modele={draft.modele}
              version={draft.version}
              vin={draft.vin}
              immatriculation={draft.immatriculation}
              dateProposition={draft.date_proposition}
              kilometrage={draft.kilometrage ?? null}
              energie={draft.energie}
            />
          </div>

          <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 dark:bg-amber-950/30">
            <div className="mb-2 flex items-center justify-between">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Fiche existante — {candidate.reference}
              </p>
              <StateBadge state={candidate.state} />
            </div>
            <ComparisonFields
              marque={candidate.marque}
              modele={candidate.modele}
              version={candidate.version}
              vin={candidate.vin}
              immatriculation={candidate.immatriculation}
              dateProposition={candidate.date_proposition}
              kilometrage={candidate.kilometrage}
              energie={candidate.energie}
            />
            {candidate.state === "REFUSE" ? (
              <p className="mt-2 text-sm text-amber-900 dark:text-amber-200">
                Refusé{candidate.refus_motif ? ` — ${REFUS_MOTIF_LABELS[candidate.refus_motif]}` : ""}
                {candidate.refus_commentaire ? ` (${candidate.refus_commentaire})` : ""}
              </p>
            ) : null}
          </div>
        </div>

        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Détail du score de similarité — {Math.round(score * 100)} %
          </p>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-muted-foreground">
                <th className="py-1 font-normal">Composante</th>
                <th className="py-1 font-normal">Poids</th>
                <th className="py-1 font-normal text-right">Valeur</th>
              </tr>
            </thead>
            <tbody>
              {SCORE_ROWS.map((row) => (
                <tr key={row.key} className="border-t border-border">
                  <td className="py-1">{row.label}</td>
                  <td className="py-1 text-muted-foreground">{row.weight}</td>
                  <td className="py-1 text-right tabular-nums">{Math.round(features[row.key] * 100)} %</td>
                </tr>
              ))}
              {features.bonus_terminal ? (
                <tr className="border-t border-border">
                  <td className="py-1">Bonus — fiche existante refusée/annulée</td>
                  <td className="py-1 text-muted-foreground">+5 pts</td>
                  <td className="py-1 text-right tabular-nums">+{Math.round(features.bonus_terminal * 100)} %</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>

        <DialogFooter className="flex-col gap-2 sm:flex-col">
          <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
            <Button
              type="button"
              variant="outline"
              disabled={isSubmitting}
              onClick={() => onDecision("duplicate", "pair")}
            >
              C&apos;est un doublon
            </Button>
            <Button
              type="button"
              variant="default"
              disabled={isSubmitting}
              onClick={() => onDecision("not_duplicate", "pair")}
            >
              Ce n&apos;est pas un doublon
            </Button>
            {allowBatchScope ? (
              <Button
                type="button"
                variant="secondary"
                disabled={isSubmitting}
                onClick={() => onDecision("not_duplicate", "batch")}
              >
                Pas un doublon — pour tout ce lot
              </Button>
            ) : null}
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ComparisonFields({
  marque,
  modele,
  version,
  vin,
  immatriculation,
  dateProposition,
  kilometrage,
  energie,
}: {
  marque: string;
  modele: string;
  version?: string | null;
  vin?: string | null;
  immatriculation?: string | null;
  dateProposition: string;
  kilometrage: number | null | undefined;
  energie?: Energie | null;
}) {
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-1 text-sm">
      <dt className="text-muted-foreground">Véhicule</dt>
      <dd className="font-medium text-foreground">
        {marque} {modele} {version ?? ""}
      </dd>
      <dt className="text-muted-foreground">VIN</dt>
      <dd>{vin || "—"}</dd>
      <dt className="text-muted-foreground">Immat.</dt>
      <dd>{formatImmatriculation(immatriculation)}</dd>
      <dt className="text-muted-foreground">Proposition</dt>
      <dd>{formatDate(dateProposition)}</dd>
      <dt className="text-muted-foreground">Kilométrage</dt>
      <dd>{kilometrage != null ? `${kilometrage.toLocaleString("fr-FR")} km` : "—"}</dd>
      <dt className="text-muted-foreground">Énergie</dt>
      <dd>{energie ? ENERGIE_LABELS[energie] : "—"}</dd>
    </dl>
  );
}
