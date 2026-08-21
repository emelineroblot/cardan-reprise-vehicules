"use client";

import { useState } from "react";
import { Plus } from "lucide-react";
import { Badge } from "@/components/ui/badge";
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
import { Input } from "@/components/ui/input";
import { MoneyInput } from "@/components/ui/money-input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ErrorState, describeError } from "@/components/ui/error-state";
import { WorkOrderPhotoStrip } from "@/components/domain/WorkOrderPhotoStrip";
import { useAddWorkOrderLine, useTransitionWorkOrderState } from "@/lib/api/hooks/useWorkOrders";
import { requiresCostLine, WORK_ORDER_TRANSITIONS } from "@/lib/workOrders/automate";
import { formatDateTime, formatMoneyCents } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  WORK_ORDER_LINE_CATEGORIE_LABELS,
  WORK_ORDER_STATE_LABELS,
  WORK_ORDER_TYPE_LABELS,
  type WorkOrder,
  type WorkOrderLineCategorie,
  type WorkOrderState,
} from "@/lib/api/types";

const STATE_STYLES: Record<WorkOrderState, string> = {
  demande: "bg-zinc-100 text-zinc-700 border-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:border-zinc-700",
  en_cours: "bg-amber-100 text-amber-800 border-amber-200 dark:bg-amber-950 dark:text-amber-300 dark:border-amber-800",
  termine: "bg-emerald-100 text-emerald-800 border-emerald-200 dark:bg-emerald-950 dark:text-emerald-300 dark:border-emerald-800",
  annule: "bg-zinc-200 text-zinc-600 border-zinc-300 dark:bg-zinc-800 dark:text-zinc-400 dark:border-zinc-700",
};

const CATEGORIE_VALUES = Object.keys(WORK_ORDER_LINE_CATEGORIE_LABELS) as WorkOrderLineCategorie[];
const DESTRUCTIVE_TARGETS = new Set<WorkOrderState>(["annule"]);

interface WorkOrderCardProps {
  vehicleId: string;
  order: WorkOrder;
  /** `atelier`/`administrateur` uniquement (contrat J3) — lecture seule pour les autres rôles. */
  canManage: boolean;
}

/**
 * Une carte par ordre de travaux (brief J3 « réception des ordres de travaux »). Les boutons de
 * transition dérivent de `lib/workOrders/automate.ts` (pas de `GET .../transitions` dédié côté
 * backend pour ce sous-automate, contrairement au véhicule) — désactivés côté client dès que la
 * garde « clos ⇒ ≥ 1 ligne » est visiblement non satisfaite, le serveur restant l'arbitre final
 * (`409 conflict`/`invalid_transition` affiché sinon).
 */
export function WorkOrderCard({ vehicleId, order, canManage }: WorkOrderCardProps) {
  const [lineDialogOpen, setLineDialogOpen] = useState(false);
  const [libelle, setLibelle] = useState("");
  const [categorie, setCategorie] = useState<WorkOrderLineCategorie>("piece");
  const [quantite, setQuantite] = useState("1");
  const [prixCents, setPrixCents] = useState<number | null>(null);

  const addLine = useAddWorkOrderLine(vehicleId, order.id);
  const transition = useTransitionWorkOrderState(vehicleId, order.id);

  const allowedTargets = WORK_ORDER_TRANSITIONS[order.state];
  const hasLines = order.lines.length > 0;

  const totalLinesCents = order.lines.reduce((sum, l) => sum + l.montant_cents, 0);

  const openLineDialog = () => {
    setLibelle("");
    setCategorie("piece");
    setQuantite("1");
    setPrixCents(null);
    addLine.reset();
    setLineDialogOpen(true);
  };

  const canSubmitLine = libelle.trim().length > 0 && Number(quantite) > 0 && prixCents !== null;

  const handleAddLine = async () => {
    if (!canSubmitLine) return;
    await addLine.mutateAsync({
      libelle: libelle.trim(),
      categorie,
      quantite,
      prix_unitaire_cents: prixCents ?? 0,
    });
    setLineDialogOpen(false);
  };

  return (
    <div className="flex flex-col gap-4 rounded-lg border border-border p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="font-medium text-foreground">{WORK_ORDER_TYPE_LABELS[order.type]}</p>
          <p className="text-sm text-muted-foreground">{order.description}</p>
        </div>
        <Badge variant="outline" className={cn("border", STATE_STYLES[order.state])}>
          {WORK_ORDER_STATE_LABELS[order.state]}
        </Badge>
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-3">
        <div>
          <dt className="text-muted-foreground">Montant estimé</dt>
          <dd className="font-medium text-foreground">{formatMoneyCents(order.montant_estime_cents)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Coût réel (lignes)</dt>
          <dd className="font-medium text-foreground">{hasLines ? formatMoneyCents(totalLinesCents) : "—"}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Demandé le</dt>
          <dd className="font-medium text-foreground">{formatDateTime(order.requested_at)}</dd>
        </div>
      </dl>

      <div className="flex flex-col gap-2">
        <h4 className="text-sm font-medium text-foreground">Lignes de coût</h4>
        {hasLines ? (
          <ul className="flex flex-col gap-1 text-sm">
            {order.lines.map((line) => (
              <li key={line.id} className="flex items-center justify-between gap-2 rounded-md bg-muted px-2.5 py-1.5">
                <span className="text-foreground">
                  {line.libelle}{" "}
                  <span className="text-muted-foreground">
                    ({WORK_ORDER_LINE_CATEGORIE_LABELS[line.categorie]} · {line.quantite} ×{" "}
                    {formatMoneyCents(line.prix_unitaire_cents)})
                  </span>
                </span>
                <span className="font-medium tabular-nums text-foreground">{formatMoneyCents(line.montant_cents)}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">Aucune ligne de coût saisie pour l&apos;instant.</p>
        )}
        {canManage && order.state !== "termine" && order.state !== "annule" ? (
          <Button type="button" variant="outline" size="sm" className="self-start" onClick={openLineDialog}>
            <Plus className="size-4" aria-hidden="true" />
            Ajouter une ligne
          </Button>
        ) : null}
      </div>

      {canManage && allowedTargets.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {allowedTargets.map((target) => {
            const blocked = requiresCostLine(target) && !hasLines;
            return (
              <Button
                key={target}
                type="button"
                size="sm"
                variant={DESTRUCTIVE_TARGETS.has(target) ? "destructive" : "default"}
                disabled={blocked || transition.isPending}
                title={blocked ? "Ajoutez au moins une ligne de coût avant de clore cet ordre." : undefined}
                onClick={() => transition.mutate({ to_state: target })}
              >
                {WORK_ORDER_STATE_LABELS[target]}
              </Button>
            );
          })}
        </div>
      ) : null}
      {transition.error ? (
        <p role="alert" className="text-sm text-destructive">
          {describeError(transition.error)}
        </p>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2">
        <WorkOrderPhotoStrip
          vehicleId={vehicleId}
          workOrderId={order.id}
          phase="avant_travaux"
          label="Avant travaux"
          canUpload={canManage}
        />
        <WorkOrderPhotoStrip
          vehicleId={vehicleId}
          workOrderId={order.id}
          phase="apres_travaux"
          label="Après travaux"
          canUpload={canManage}
        />
      </div>

      <Dialog open={lineDialogOpen} onOpenChange={setLineDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Ajouter une ligne de coût</DialogTitle>
            <DialogDescription>
              Le montant est calculé côté serveur (quantité × prix unitaire), jamais recalculé ici.
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-4">
            <div>
              <Label htmlFor="wol-libelle">Libellé</Label>
              <Input id="wol-libelle" className="mt-1.5" value={libelle} onChange={(e) => setLibelle(e.target.value)} />
            </div>
            <div>
              <Label htmlFor="wol-categorie">Catégorie</Label>
              <Select value={categorie} onValueChange={(v) => setCategorie(v as WorkOrderLineCategorie)}>
                <SelectTrigger id="wol-categorie" className="mt-1.5 w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CATEGORIE_VALUES.map((value) => (
                    <SelectItem key={value} value={value}>
                      {WORK_ORDER_LINE_CATEGORIE_LABELS[value]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor="wol-quantite">Quantité</Label>
                <Input
                  id="wol-quantite"
                  type="number"
                  min="0.01"
                  step="0.01"
                  className="mt-1.5"
                  value={quantite}
                  onChange={(e) => setQuantite(e.target.value)}
                />
              </div>
              <div>
                <Label htmlFor="wol-prix">Prix unitaire</Label>
                <div className="mt-1.5">
                  <MoneyInput id="wol-prix" value={prixCents} onValueChange={setPrixCents} />
                </div>
              </div>
            </div>
            {addLine.error ? <ErrorState error={addLine.error} title="Ligne refusée" /> : null}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setLineDialogOpen(false)}>
              Annuler
            </Button>
            <Button type="button" disabled={!canSubmitLine || addLine.isPending} onClick={handleAddLine}>
              {addLine.isPending ? "Ajout…" : "Ajouter"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
