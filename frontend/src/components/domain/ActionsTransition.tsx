"use client";

import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
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
import { useUsers } from "@/lib/api/hooks/useUsers";
import { datetimeLocalToIso, minDatetimeLocalValue } from "@/lib/format/date";
import {
  REFUS_MOTIF_LABELS,
  VEHICLE_STATE_LABELS,
  WORK_ORDER_TYPE_LABELS,
  type RefusMotif,
  type TransitionOption,
  type WorkOrderType,
} from "@/lib/api/types";

interface ActionsTransitionProps {
  vehicleId: string;
  /** `lg` : cibles tactiles généreuses pour l'écran de contrôle terrain (mission/[id]).
   * `default` (J1, inchangé) reste le rendu compact de la fiche véhicule admin/opératrice. */
  size?: "default" | "lg";
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
 *
 * `driver_id` ajouté en J2 : `GET /users?role=chauffeur` (dette J1) débloque enfin la
 * sélection — voir implementation.md § J2 Backend « GET /users — dette J1 ».
 *
 * `work_orders` ajouté en J3 : `CONTROLE_EN_COURS → TRAVAUX_REQUIS` (implementation.md § J3
 * Backend) — liste non vide obligatoire, un ordre par entrée, effet unique (création des
 * `work_order`, aucun autre).
 */
const SUPPORTED_PAYLOAD_FIELDS = new Set<string>([
  "refus_motif",
  "prix_achat_negocie_cents",
  "rdv_at",
  "driver_id",
  "work_orders",
]);

interface WorkOrderDraft {
  key: string;
  type: WorkOrderType;
  description: string;
  montantEstimeCents: number | null;
}

const WORK_ORDER_TYPE_VALUES = Object.keys(WORK_ORDER_TYPE_LABELS) as WorkOrderType[];

function emptyWorkOrderDraft(): WorkOrderDraft {
  return { key: crypto.randomUUID(), type: "carrosserie", description: "", montantEstimeCents: null };
}

const UNSUPPORTED_FIELD_MESSAGES: Record<string, string> = {};

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
export function ActionsTransition({ vehicleId, size = "default" }: ActionsTransitionProps) {
  const transitions = useVehicleTransitions(vehicleId);
  const applyTransition = useApplyTransition(vehicleId);
  const [pending, setPending] = useState<TransitionOption | null>(null);
  const [reason, setReason] = useState("");
  const [refusMotif, setRefusMotif] = useState<RefusMotif | undefined>(undefined);
  const [prixCents, setPrixCents] = useState<number | null>(null);
  const [rdvAt, setRdvAt] = useState("");
  const [rdvAdresse, setRdvAdresse] = useState("");
  const [rdvContactNom, setRdvContactNom] = useState("");
  const [rdvContactTelephone, setRdvContactTelephone] = useState("");
  const [driverId, setDriverId] = useState<string | undefined>(undefined);
  const [workOrders, setWorkOrders] = useState<WorkOrderDraft[]>([]);
  // Dérivés de `rdvAt` mais calculés en dehors du rendu (poignées d'événement) : `Date.now()`
  // est impur, l'appeler pendant le rendu casse la règle react-hooks/purity.
  const [rdvAtIsFuture, setRdvAtIsFuture] = useState(false);
  const [rdvAtMin, setRdvAtMin] = useState("");

  const needsDriverId = pending?.requires_payload_fields.includes("driver_id") ?? false;
  const drivers = useUsers({ role: "chauffeur", is_active: true, limit: 100 }, needsDriverId);

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
    setRdvAdresse("");
    setRdvContactNom("");
    setRdvContactTelephone("");
    setDriverId(undefined);
    setWorkOrders([emptyWorkOrderDraft()]);
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
  const needsWorkOrders = pending?.requires_payload_fields.includes("work_orders") ?? false;
  const workOrdersValid =
    workOrders.length > 0 && workOrders.every((wo) => wo.description.trim().length > 0);

  const canConfirm =
    pending !== null &&
    pendingUnsupported.length === 0 &&
    (!pending.requires_reason || reason.trim().length > 0) &&
    (!needsRefusMotif || refusMotif !== undefined) &&
    (!needsPrix || prixCents !== null) &&
    (!needsRdvAt || rdvAtIsFuture) &&
    (!needsDriverId || Boolean(driverId)) &&
    (!needsWorkOrders || workOrdersValid);

  const addWorkOrderRow = () => setWorkOrders((rows) => [...rows, emptyWorkOrderDraft()]);
  const removeWorkOrderRow = (key: string) =>
    setWorkOrders((rows) => rows.filter((row) => row.key !== key));
  const updateWorkOrderRow = (key: string, patch: Partial<WorkOrderDraft>) =>
    setWorkOrders((rows) => rows.map((row) => (row.key === key ? { ...row, ...patch } : row)));

  const handleConfirm = async () => {
    if (!pending || pendingUnsupported.length > 0) return;
    const payload: Record<string, unknown> = {};
    if (needsRefusMotif && refusMotif) payload.refus_motif = refusMotif;
    if (needsPrix && prixCents !== null) payload.prix_achat_negocie_cents = prixCents;
    if (needsDriverId && driverId) payload.driver_id = driverId;
    if (needsWorkOrders) {
      payload.work_orders = workOrders.map((wo) => ({
        type: wo.type,
        description: wo.description.trim(),
        ...(wo.montantEstimeCents !== null ? { montant_estime_cents: wo.montantEstimeCents } : {}),
      }));
    }
    if (needsRdvAt) {
      const rdvAtIso = datetimeLocalToIso(rdvAt);
      if (rdvAtIso) payload.rdv_at = rdvAtIso;
      // Optionnels côté backend (implementation.md § J2 : absents de
      // `requires_payload_fields`, jamais bloquants) — envoyés seulement s'ils sont
      // renseignés, la mission garde sinon ses valeurs précédentes.
      if (rdvAdresse.trim()) payload.rdv_adresse = rdvAdresse.trim();
      if (rdvContactNom.trim()) payload.rdv_contact_nom = rdvContactNom.trim();
      if (rdvContactTelephone.trim()) payload.rdv_contact_telephone = rdvContactTelephone.trim();
    }

    await applyTransition.mutateAsync({
      to_state: pending.to_state,
      reason: pending.requires_reason ? reason.trim() : null,
      payload: Object.keys(payload).length > 0 ? payload : null,
    });
    setPending(null);
  };

  const buttonSizeClass = size === "lg" ? "h-14 px-6 text-base" : undefined;

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
            className={buttonSizeClass}
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
            {needsDriverId ? (
              <div>
                <Label htmlFor="driver_id">Chauffeur</Label>
                {drivers.isLoading ? (
                  <p className="mt-1.5 text-sm text-muted-foreground">Chargement des chauffeurs…</p>
                ) : drivers.error ? (
                  <ErrorState error={drivers.error} title="Chauffeurs indisponibles" onRetry={() => drivers.refetch()} />
                ) : (
                  <Select value={driverId} onValueChange={setDriverId}>
                    <SelectTrigger id="driver_id" className="mt-1.5 w-full">
                      <SelectValue placeholder="Sélectionnez un chauffeur…" />
                    </SelectTrigger>
                    <SelectContent>
                      {(drivers.data?.items ?? []).map((driver) => (
                        <SelectItem key={driver.id} value={driver.id}>
                          {driver.full_name}
                        </SelectItem>
                      ))}
                      {drivers.data && drivers.data.items.length === 0 ? (
                        <p className="px-2 py-1.5 text-sm text-muted-foreground">Aucun chauffeur actif.</p>
                      ) : null}
                    </SelectContent>
                  </Select>
                )}
              </div>
            ) : null}

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
              <>
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
                <div>
                  <Label htmlFor="rdv_adresse">Adresse du rendez-vous (optionnel)</Label>
                  <Input
                    id="rdv_adresse"
                    className="mt-1.5"
                    value={rdvAdresse}
                    onChange={(e) => setRdvAdresse(e.target.value)}
                  />
                </div>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <Label htmlFor="rdv_contact_nom">Contact vendeur (optionnel)</Label>
                    <Input
                      id="rdv_contact_nom"
                      className="mt-1.5"
                      value={rdvContactNom}
                      onChange={(e) => setRdvContactNom(e.target.value)}
                    />
                  </div>
                  <div>
                    <Label htmlFor="rdv_contact_telephone">Téléphone du contact (optionnel)</Label>
                    <Input
                      id="rdv_contact_telephone"
                      type="tel"
                      className="mt-1.5"
                      value={rdvContactTelephone}
                      onChange={(e) => setRdvContactTelephone(e.target.value)}
                    />
                  </div>
                </div>
              </>
            ) : null}

            {needsWorkOrders ? (
              <div className="flex flex-col gap-3">
                <div className="flex items-center justify-between">
                  <Label>Ordres de travaux à ouvrir</Label>
                  <Button type="button" variant="outline" size="sm" onClick={addWorkOrderRow}>
                    <Plus className="size-4" aria-hidden="true" />
                    Ajouter
                  </Button>
                </div>
                {workOrders.map((wo, index) => (
                  <div key={wo.key} className="flex flex-col gap-2 rounded-md border border-border p-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-medium text-muted-foreground">Ordre {index + 1}</span>
                      {workOrders.length > 1 ? (
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          className="size-7"
                          aria-label={`Retirer l'ordre ${index + 1}`}
                          onClick={() => removeWorkOrderRow(wo.key)}
                        >
                          <Trash2 className="size-3.5" aria-hidden="true" />
                        </Button>
                      ) : null}
                    </div>
                    <div>
                      <Label htmlFor={`wo-type-${wo.key}`}>Type</Label>
                      <Select
                        value={wo.type}
                        onValueChange={(v) => updateWorkOrderRow(wo.key, { type: v as WorkOrderType })}
                      >
                        <SelectTrigger id={`wo-type-${wo.key}`} className="mt-1.5 w-full">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {WORK_ORDER_TYPE_VALUES.map((value) => (
                            <SelectItem key={value} value={value}>
                              {WORK_ORDER_TYPE_LABELS[value]}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label htmlFor={`wo-description-${wo.key}`}>Description</Label>
                      <Textarea
                        id={`wo-description-${wo.key}`}
                        className="mt-1.5"
                        rows={2}
                        value={wo.description}
                        aria-invalid={wo.description.trim().length === 0 ? true : undefined}
                        onChange={(e) => updateWorkOrderRow(wo.key, { description: e.target.value })}
                      />
                    </div>
                    <div>
                      <Label htmlFor={`wo-montant-${wo.key}`}>Montant estimé (optionnel)</Label>
                      <div className="mt-1.5">
                        <MoneyInput
                          id={`wo-montant-${wo.key}`}
                          value={wo.montantEstimeCents}
                          onValueChange={(cents) => updateWorkOrderRow(wo.key, { montantEstimeCents: cents })}
                        />
                      </div>
                    </div>
                  </div>
                ))}
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
            <Button type="button" variant="outline" className={buttonSizeClass} onClick={() => setPending(null)}>
              Annuler
            </Button>
            <Button
              type="button"
              disabled={!canConfirm || applyTransition.isPending}
              className={buttonSizeClass}
              onClick={handleConfirm}
            >
              {applyTransition.isPending ? "Application…" : "Confirmer"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
