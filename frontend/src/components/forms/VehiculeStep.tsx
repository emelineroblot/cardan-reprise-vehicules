"use client";

import { Controller, useFormContext } from "react-hook-form";
import { AlertTriangle, CircleAlert, Info, Trash2 } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { FieldError } from "@/components/ui/field-error";
import { MoneyInput } from "@/components/ui/money-input";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { boiteValues, energieValues, type VehiculeLotFormValues } from "@/lib/validation/vehicule";
import { BOITE_LABELS, ENERGIE_LABELS, type DuplicateCheckResult } from "@/lib/api/types";

export type DuplicateStatus = "idle" | "checking" | "clear" | "exact" | "probable" | "similar" | "error";

export interface DuplicateState {
  status: DuplicateStatus;
  result?: DuplicateCheckResult;
  /** Détail affiché quand `status === "error"` — jamais un échec muet (voir VehiculeLot). */
  message?: string;
}

interface VehiculeStepProps {
  index: number;
  label: string;
  canRemove: boolean;
  onRemove: () => void;
  duplicateState: DuplicateState;
  onCheckDuplicate: () => void;
}

/**
 * Un véhicule du lot (plan.md § 6 vague 3). Rendu dans le contexte d'un
 * `useFieldArray` porté par `VehiculeLot` : tous les champs sont préfixés
 * `vehicules.{index}.*`.
 */
export function VehiculeStep({ index, label, canRemove, onRemove, duplicateState, onCheckDuplicate }: VehiculeStepProps) {
  const {
    register,
    control,
    formState: { errors },
  } = useFormContext<VehiculeLotFormValues>();

  const itemErrors = errors.vehicules?.[index];
  const base = `vehicules.${index}` as const;

  return (
    <section
      aria-label={label}
      className="flex flex-col gap-4 rounded-lg border border-border p-4"
    >
      <div className="flex items-center justify-between">
        <h3 className="font-medium text-foreground">{label}</h3>
        {canRemove ? (
          <Button type="button" variant="ghost" size="sm" onClick={onRemove}>
            <Trash2 className="size-4" aria-hidden="true" />
            Retirer du lot
          </Button>
        ) : null}
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <div>
          <Label htmlFor={`${base}.marque`}>Marque</Label>
          <Input id={`${base}.marque`} className="mt-1.5" {...register(`${base}.marque`)} />
          <FieldError message={itemErrors?.marque?.message} />
        </div>
        <div>
          <Label htmlFor={`${base}.modele`}>Modèle</Label>
          <Input id={`${base}.modele`} className="mt-1.5" {...register(`${base}.modele`)} />
          <FieldError message={itemErrors?.modele?.message} />
        </div>
        <div>
          <Label htmlFor={`${base}.version`}>Version</Label>
          <Input id={`${base}.version`} className="mt-1.5" {...register(`${base}.version`)} />
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <div>
          <Label htmlFor={`${base}.energie`}>Énergie</Label>
          <Controller
            control={control}
            name={`${base}.energie`}
            render={({ field }) => (
              <Select value={field.value ?? undefined} onValueChange={field.onChange}>
                <SelectTrigger id={`${base}.energie`} className="mt-1.5 w-full">
                  <SelectValue placeholder="Non renseigné" />
                </SelectTrigger>
                <SelectContent>
                  {energieValues.map((value) => (
                    <SelectItem key={value} value={value}>
                      {ENERGIE_LABELS[value]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
        </div>
        <div>
          <Label htmlFor={`${base}.boite`}>Boîte</Label>
          <Controller
            control={control}
            name={`${base}.boite`}
            render={({ field }) => (
              <Select value={field.value ?? undefined} onValueChange={field.onChange}>
                <SelectTrigger id={`${base}.boite`} className="mt-1.5 w-full">
                  <SelectValue placeholder="Non renseigné" />
                </SelectTrigger>
                <SelectContent>
                  {boiteValues.map((value) => (
                    <SelectItem key={value} value={value}>
                      {BOITE_LABELS[value]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
        </div>
        <div>
          <Label htmlFor={`${base}.couleur`}>Couleur</Label>
          <Input id={`${base}.couleur`} className="mt-1.5" {...register(`${base}.couleur`)} />
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <Label htmlFor={`${base}.vin`}>VIN</Label>
          <Input
            id={`${base}.vin`}
            className="mt-1.5 uppercase"
            autoCapitalize="characters"
            {...register(`${base}.vin`, { onBlur: onCheckDuplicate })}
          />
          <FieldError message={itemErrors?.vin?.message} />
        </div>
        <div>
          <Label htmlFor={`${base}.immatriculation`}>Immatriculation</Label>
          <Input
            id={`${base}.immatriculation`}
            className="mt-1.5 uppercase"
            placeholder="AA-123-BB"
            autoCapitalize="characters"
            {...register(`${base}.immatriculation`, { onBlur: onCheckDuplicate })}
          />
          <FieldError message={itemErrors?.immatriculation?.message} />
        </div>
      </div>

      <DuplicateFeedback state={duplicateState} />

      <div className="grid gap-4 sm:grid-cols-3">
        <div>
          <Label htmlFor={`${base}.date_mise_en_circulation`}>1ʳᵉ mise en circulation</Label>
          <Input
            id={`${base}.date_mise_en_circulation`}
            type="date"
            className="mt-1.5"
            {...register(`${base}.date_mise_en_circulation`)}
          />
        </div>
        <div>
          <Label htmlFor={`${base}.kilometrage`}>Kilométrage</Label>
          <Input
            id={`${base}.kilometrage`}
            type="number"
            min={0}
            inputMode="numeric"
            className="mt-1.5"
            {...register(`${base}.kilometrage`, {
              setValueAs: (v) => (v === "" || v === null || v === undefined ? undefined : Number(v)),
            })}
          />
          <FieldError message={itemErrors?.kilometrage?.message} />
        </div>
        <div>
          <Label htmlFor={`${base}.date_proposition`}>Date de proposition</Label>
          <Input
            id={`${base}.date_proposition`}
            type="date"
            className="mt-1.5"
            {...register(`${base}.date_proposition`)}
          />
          <FieldError message={itemErrors?.date_proposition?.message} />
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <div>
          <Label htmlFor={`${base}.prix_achat_negocie_cents`}>Prix négocié</Label>
          <Controller
            control={control}
            name={`${base}.prix_achat_negocie_cents`}
            render={({ field }) => (
              <div className="mt-1.5">
                <MoneyInput
                  id={`${base}.prix_achat_negocie_cents`}
                  value={field.value ?? null}
                  onValueChange={field.onChange}
                  invalid={Boolean(itemErrors?.prix_achat_negocie_cents)}
                />
              </div>
            )}
          />
          <FieldError message={itemErrors?.prix_achat_negocie_cents?.message} />
        </div>
        <div>
          <Label htmlFor={`${base}.valeur_revente_estimee_cents`}>Valeur de revente estimée</Label>
          <Controller
            control={control}
            name={`${base}.valeur_revente_estimee_cents`}
            render={({ field }) => (
              <div className="mt-1.5">
                <MoneyInput
                  id={`${base}.valeur_revente_estimee_cents`}
                  value={field.value ?? null}
                  onValueChange={field.onChange}
                  invalid={Boolean(itemErrors?.valeur_revente_estimee_cents)}
                />
              </div>
            )}
          />
        </div>
        <div>
          <Label htmlFor={`${base}.frais_transport_cents`}>Frais de transport</Label>
          <Controller
            control={control}
            name={`${base}.frais_transport_cents`}
            render={({ field }) => (
              <div className="mt-1.5">
                <MoneyInput
                  id={`${base}.frais_transport_cents`}
                  value={field.value ?? null}
                  onValueChange={field.onChange}
                  invalid={Boolean(itemErrors?.frais_transport_cents)}
                />
              </div>
            )}
          />
        </div>
      </div>

      <div>
        <Label htmlFor={`${base}.commentaire`}>Commentaire</Label>
        <Textarea id={`${base}.commentaire`} className="mt-1.5" rows={2} {...register(`${base}.commentaire`)} />
      </div>
    </section>
  );
}

function DuplicateFeedback({ state }: { state: DuplicateState }) {
  if (state.status === "idle" || state.status === "checking") {
    return null;
  }

  if (state.status === "exact" && state.result?.exact?.length) {
    const existing = state.result.exact[0];
    return (
      <Alert variant="destructive">
        <CircleAlert />
        <AlertTitle>Ce véhicule existe déjà</AlertTitle>
        <AlertDescription>
          VIN ou immatriculation déjà enregistré sous la fiche {existing.reference}. Corrigez la
          saisie ou consultez la fiche existante avant de continuer.
        </AlertDescription>
      </Alert>
    );
  }

  if (state.status === "probable") {
    return (
      <Alert>
        <AlertTriangle />
        <AlertTitle>Doublon potentiel détecté</AlertTitle>
        <AlertDescription>
          Un véhicule très proche existe déjà. Un écran d&apos;arbitrage s&apos;ouvrira à
          l&apos;enregistrement.
        </AlertDescription>
      </Alert>
    );
  }

  if (state.status === "similar") {
    return (
      <Alert>
        <Info />
        <AlertTitle>Fiche voisine</AlertTitle>
        <AlertDescription>
          Au moins une fiche proche existe (société, modèle et période voisins). Informatif — vous
          pouvez continuer.
        </AlertDescription>
      </Alert>
    );
  }

  if (state.status === "error") {
    return (
      <Alert variant="destructive">
        <CircleAlert />
        <AlertTitle>Vérification de doublon impossible</AlertTitle>
        <AlertDescription>
          {state.message ?? "Erreur inattendue."} La saisie reste possible ; la vérification sera
          rejouée à l&apos;enregistrement.
        </AlertDescription>
      </Alert>
    );
  }

  return null;
}
