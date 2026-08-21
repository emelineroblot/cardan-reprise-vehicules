"use client";

import { useState } from "react";
import { Plus } from "lucide-react";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { LoadingState } from "@/components/ui/loading-state";
import { ErrorState } from "@/components/ui/error-state";
import { useAddVehicleCost, useVehicleCosts } from "@/lib/api/hooks/useVehicleCosts";
import { formatDateTime, formatMoneyCents } from "@/lib/format";
import { VEHICLE_COST_TYPE_LABELS, type VehicleCostType } from "@/lib/api/types";

const COST_TYPE_VALUES = Object.keys(VEHICLE_COST_TYPE_LABELS) as VehicleCostType[];

interface VehicleCostsPanelProps {
  vehicleId: string;
  /** Écriture réservée à `administrateur` (décision d'implémentation J3, implementation.md § J3
   * Backend) : aucun rôle métier dédié comme l'atelier pour ces coûts hors atelier. */
  canManage: boolean;
}

/**
 * Coûts hors atelier (transport, carburant, administratif, remise en état externe — brief J3).
 * Distincts des lignes de coût d'un ordre de travaux : ceux-là documentent le travail
 * mécanique/carrosserie, ceux-ci les frais annexes à la reprise du véhicule.
 */
export function VehicleCostsPanel({ vehicleId, canManage }: VehicleCostsPanelProps) {
  const costs = useVehicleCosts(vehicleId);
  const addCost = useAddVehicleCost(vehicleId);
  const [open, setOpen] = useState(false);
  const [type, setType] = useState<VehicleCostType>("transport");
  const [montantCents, setMontantCents] = useState<number | null>(null);
  const [commentaire, setCommentaire] = useState("");

  const openDialog = () => {
    setType("transport");
    setMontantCents(null);
    setCommentaire("");
    addCost.reset();
    setOpen(true);
  };

  const canSubmit = montantCents !== null && montantCents >= 0;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    await addCost.mutateAsync({
      type,
      montant_cents: montantCents ?? 0,
      commentaire: commentaire.trim() || undefined,
    });
    setOpen(false);
  };

  if (costs.isLoading) return <LoadingState label="Chargement des coûts…" />;
  if (costs.error) {
    return <ErrorState error={costs.error} title="Coûts indisponibles" onRetry={() => costs.refetch()} />;
  }
  const rows = costs.data ?? [];
  const total = rows.reduce((sum, c) => sum + c.montant_cents, 0);

  return (
    <div className="flex flex-col gap-3">
      {rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">Aucun coût hors atelier saisi pour l&apos;instant.</p>
      ) : (
        <ul className="flex flex-col gap-1 text-sm">
          {rows.map((cost) => (
            <li key={cost.id} className="flex items-center justify-between gap-2 rounded-md bg-muted px-2.5 py-1.5">
              <span className="text-foreground">
                {VEHICLE_COST_TYPE_LABELS[cost.type]}
                {cost.commentaire ? ` — ${cost.commentaire}` : ""}
                <span className="text-muted-foreground"> · {formatDateTime(cost.created_at)}</span>
              </span>
              <span className="font-medium tabular-nums text-foreground">{formatMoneyCents(cost.montant_cents)}</span>
            </li>
          ))}
          <li className="flex items-center justify-between gap-2 px-2.5 pt-1 text-sm font-medium">
            <span>Total</span>
            <span className="tabular-nums">{formatMoneyCents(total)}</span>
          </li>
        </ul>
      )}
      {canManage ? (
        <Button type="button" variant="outline" size="sm" className="self-start" onClick={openDialog}>
          <Plus className="size-4" aria-hidden="true" />
          Ajouter un coût
        </Button>
      ) : null}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Ajouter un coût hors atelier</DialogTitle>
            <DialogDescription>Transport, carburant, administratif ou remise en état externe.</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-4">
            <div>
              <Label htmlFor="vc-type">Type</Label>
              <Select value={type} onValueChange={(v) => setType(v as VehicleCostType)}>
                <SelectTrigger id="vc-type" className="mt-1.5 w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {COST_TYPE_VALUES.map((value) => (
                    <SelectItem key={value} value={value}>
                      {VEHICLE_COST_TYPE_LABELS[value]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="vc-montant">Montant</Label>
              <div className="mt-1.5">
                <MoneyInput id="vc-montant" value={montantCents} onValueChange={setMontantCents} />
              </div>
            </div>
            <div>
              <Label htmlFor="vc-commentaire">Commentaire (optionnel)</Label>
              <Textarea id="vc-commentaire" className="mt-1.5" rows={2} value={commentaire} onChange={(e) => setCommentaire(e.target.value)} />
            </div>
            {addCost.error ? <ErrorState error={addCost.error} title="Coût refusé" /> : null}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Annuler
            </Button>
            <Button type="button" disabled={!canSubmit || addCost.isPending} onClick={handleSubmit}>
              {addCost.isPending ? "Ajout…" : "Ajouter"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
