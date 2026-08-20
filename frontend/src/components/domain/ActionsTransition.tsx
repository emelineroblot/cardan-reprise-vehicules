"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { MoneyInput } from "@/components/ui/money-input";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ErrorState } from "@/components/ui/error-state";
import { LoadingState } from "@/components/ui/loading-state";
import { useApplyTransition, useVehicleTransitions } from "@/lib/api/hooks/useVehicleTransitions";
import { datetimeLocalToIso, minDatetimeLocalValue } from "@/lib/format/date";
import { REFUS_MOTIF_LABELS, VEHICLE_STATE_LABELS, type RefusMotif, type TransitionOption } from "@/lib/api/types";

interface ActionsTransitionProps {
  vehicleId: string;
}

const DESTRUCTIVE_TARGETS = new Set(["REFUSE", "ANNULE"]);
const REFUS_MOTIF_VALUES = Object.keys(REFUS_MOTIF_LABELS) as RefusMotif[];

/**
 * Champs de `requires_payload_fields` que ce dialogue sait réellement collecter. Un champ
 * absent de cet ensemble n'a **aucune saisie possible** ici — il ne doit alors jamais rester
 * silencieux dans un `payload` incomplet qui atterrirait en `409 invalid_transition`
 * (régression review-finale.md § 🟠 ActionsTransition : `driver_id`/`rdv_at` manquants côté
 * front alors que le backend les déclare). Le bouton correspondant est désactivé à la place —
 * voir `unsupportedFieldsOf`. Tenir cette liste à jour à chaque champ ajouté à l'automate
 * (`state_machine.py`) plutôt que de la contourner.
 */
const SUPPORTED_PAYLOAD_FIELDS = new Set<string>([
  "refus_motif",
  "prix_achat_negocie_cents",
  "rdv_at",
]);

/**
 * Message affiché quand un champ requis par le backend n'a pas de saisie côté front. Pas de
 * `<Select>` de chauffeurs pour `driver_id` : aucun endpoint ne liste les comptes `chauffeur`
 * à ce jour (voir implementation.md § Points d'attention) — inventer un contrat ici serait
 * exactement l'erreur que ce correctif corrige à l'inverse.
 */
const UNSUPPORTED_FIELD_MESSAGES: Record<string, string> = {
  driver_id: "Sélection de chauffeur indisponible pour l'instant — arrivera avec le module chauffeur (J2).",
};

function unsupportedFieldsOf(option: TransitionOption): string[] {
  return option.requires_payload_fields.filter((field) => !SUPPORTED_PAYLOAD_FIELDS.has(field));
}

function unsupportedMessage(fields: string[]): string {
  return fields
    .map((field) => UNSUPPORTED_FIELD_MESSAGES[field] ?? `Champ « ${field} » non pris en charge par cette version.`)
    .join(" ");
}

/**
 * Boutons d'action DÉRIVÉS de `GET /vehicles/{id}/transitions` — jamais codés en dur
 * (plan.md § 6 vague 4, § 5.3 : l'automate ne vit qu'à un seul endroit côté backend).
 *
 * Le dialogue se construit génériquement à partir de `requires_payload_fields` : chaque champ
 * connu (`SUPPORTED_PAYLOAD_FIELDS`) a son contrôle de saisie ; un champ inconnu désactive le
 * bouton plutôt que de laisser partir un `payload` incomplet.
 */
export function ActionsTransition({ vehicleId }: ActionsTransitionProps) {
  const transitions = useVehicleTransitions(vehicleId);
  const applyTransition = useApplyTransition(vehicleId);
  const [pending, setPending] = useState<TransitionOption | null>(null);
  const [reason, setReason] = useState("");
  const [refusMotif, setRefusMotif] = useState<RefusMotif | undefined>(undefined);
  const [prixCents, setPrixCents] = useState<number | null>(null);
  const [rdvAt, setRdvAt] = useState("");
  // Dérivés de `rdvAt` mais calculés en dehors du rendu (poignées d'événement) : `Date.now()`
  // est impur, l'appeler pendant le rendu casse la règle react-hooks/purity.
  const [rdvAtIsFuture, setRdvAtIsFuture] = useState(false);
  const [rdvAtMin, setRdvAtMin] = useState("");

  if (transitions.isLoading) {
    return <LoadingState label="Chargement des actions disponibles…" />;
  }

  if (transitions.error) {
    return <ErrorState error={transitions.error} title="Actions indisponibles" onRetry={() => transitions.refetch()} />;
  }

  const options = transitions.data ?? [];

  if (options.length === 0) {
    return <p className="text-sm text-muted-foreground">Aucune action disponible pour votre rôle sur cette fiche.</p>;
  }

  const openDialog = (option: TransitionOption) => {
    setReason("");
    setRefusMotif(undefined);
    setPrixCents(null);
    setRdvAt("");
    setRdvAtIsFuture(false);
    // Calculé une fois à l'ouverture (poignée d'événement, pas pendant le rendu) : borne
    // `min` du champ, purement indicative pour l'utilisateur.
    setRdvAtMin(minDatetimeLocalValue());
    setPending(option);
  };

  const handleRdvAtChange = (value: string) => {
    setRdvAt(value);
    const iso = datetimeLocalToIso(value);
    setRdvAtIsFuture(iso !== null && new Date(iso).getTime() > Date.now());
  };

  const pendingUnsupported = pending ? unsupportedFieldsOf(pending) : [];
  const needsRefusMotif = pending?.requires_payload_fields.includes("refus_motif") ?? false;
  const needsPrix = pending?.requires_payload_fields.includes("prix_achat_negocie_cents") ?? false;
  const needsRdvAt = pending?.requires_payload_fields.includes("rdv_at") ?? false;

  const canConfirm =
    pending !== null &&
    pendingUnsupported.length === 0 &&
    (!pending.requires_reason || reason.trim().length > 0) &&
    (!needsRefusMotif || refusMotif !== undefined) &&
    (!needsPrix || prixCents !== null) &&
    (!needsRdvAt || rdvAtIsFuture);

  const handleConfirm = async () => {
    if (!pending || pendingUnsupported.length > 0) return;
    const payload: Record<string, unknown> = {};
    if (needsRefusMotif && refusMotif) payload.refus_motif = refusMotif;
    if (needsPrix && prixCents !== null) payload.prix_achat_negocie_cents = prixCents;
    if (needsRdvAt) {
      const rdvAtIso = datetimeLocalToIso(rdvAt);
      if (rdvAtIso) payload.rdv_at = rdvAtIso;
    }

    await applyTransition.mutateAsync({
      to_state: pending.to_state,
      reason: pending.requires_reason ? reason.trim() : null,
      payload: Object.keys(payload).length > 0 ? payload : null,
    });
    setPending(null);
  };

  return (
    <div className="flex flex-wrap gap-2">
      {options.map((option) => {
        const unsupported = unsupportedFieldsOf(option);
        const isDisabled = unsupported.length > 0;
        return (
          <Button
            key={option.to_state}
            type="button"
            variant={DESTRUCTIVE_TARGETS.has(option.to_state) ? "destructive" : "default"}
            disabled={isDisabled}
            aria-disabled={isDisabled || undefined}
            title={isDisabled ? unsupportedMessage(unsupported) : undefined}
            onClick={() => openDialog(option)}
          >
            {option.label || VEHICLE_STATE_LABELS[option.to_state]}
          </Button>
        );
      })}

      <Dialog open={pending !== null} onOpenChange={(open) => !open && setPending(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{pending?.label || (pending ? VEHICLE_STATE_LABELS[pending.to_state] : "")}</DialogTitle>
            <DialogDescription>Cette action met à jour l&apos;état de la fiche et son historique.</DialogDescription>
          </DialogHeader>

          <div className="flex flex-col gap-4">
            {needsRefusMotif ? (
              <div>
                <Label htmlFor="refus_motif">Motif de refus</Label>
                <Select value={refusMotif} onValueChange={(v) => setRefusMotif(v as RefusMotif)}>
                  <SelectTrigger id="refus_motif" className="mt-1.5 w-full">
                    <SelectValue placeholder="Sélectionnez…" />
                  </SelectTrigger>
                  <SelectContent>
                    {REFUS_MOTIF_VALUES.map((value) => (
                      <SelectItem key={value} value={value}>
                        {REFUS_MOTIF_LABELS[value]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            ) : null}

            {needsPrix ? (
              <div>
                <Label htmlFor="prix_achat_negocie_cents">Prix d&apos;achat négocié</Label>
                <div className="mt-1.5">
                  <MoneyInput id="prix_achat_negocie_cents" value={prixCents} onValueChange={setPrixCents} />
                </div>
              </div>
            ) : null}

            {needsRdvAt ? (
              <div>
                <Label htmlFor="rdv_at">Date et heure du rendez-vous</Label>
                <Input
                  id="rdv_at"
                  type="datetime-local"
                  className="mt-1.5"
                  min={rdvAtMin}
                  value={rdvAt}
                  aria-invalid={rdvAt.length > 0 && !rdvAtIsFuture ? true : undefined}
                  onChange={(e) => handleRdvAtChange(e.target.value)}
                />
                {rdvAt.length > 0 && !rdvAtIsFuture ? (
                  <p className="mt-1 text-sm text-destructive">Le rendez-vous doit être fixé dans le futur.</p>
                ) : null}
              </div>
            ) : null}

            {pending?.requires_reason ? (
              <div>
                <Label htmlFor="reason">Motif / commentaire</Label>
                <Textarea
                  id="reason"
                  className="mt-1.5"
                  rows={3}
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                />
              </div>
            ) : null}

            {pendingUnsupported.length > 0 ? (
              // Filet de sécurité : inatteignable en usage normal (le bouton déclencheur est
              // désactivé), mais si `pending` était tout de même positionné avec un champ non
              // supporté, `canConfirm` le bloque et ce message explique pourquoi.
              <p className="text-sm text-destructive">{unsupportedMessage(pendingUnsupported)}</p>
            ) : null}

            {applyTransition.error ? <ErrorState error={applyTransition.error} title="Action impossible" /> : null}
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setPending(null)}>
              Annuler
            </Button>
            <Button type="button" disabled={!canConfirm || applyTransition.isPending} onClick={handleConfirm}>
              {applyTransition.isPending ? "Application…" : "Confirmer"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
