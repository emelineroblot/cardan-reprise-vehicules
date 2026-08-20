"use client";

import { useCallback, useRef, useState } from "react";
import { FormProvider, useFieldArray, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { CircleAlert, PlusCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { describeError } from "@/components/ui/error-state";
import { VehiculeStep, type DuplicateState } from "@/components/forms/VehiculeStep";
import { ArbitrageDoublon } from "@/components/domain/ArbitrageDoublon";
import { useDuplicateCheck } from "@/lib/api/hooks/useDuplicateCheck";
import { useCreateVehicle } from "@/lib/api/hooks/useCreateVehicle";
import { useCreateIntakeBatch } from "@/lib/api/hooks/useCreateIntakeBatch";
import { useDuplicateReview } from "@/lib/api/hooks/useDuplicateReview";
import {
  toVehicleDraft,
  vehiculeDefaultValues,
  vehiculeLotSchema,
  type VehiculeFormValues,
  type VehiculeLotFormValues,
} from "@/lib/validation/vehicule";
import type { Company, DuplicateCandidate, DuplicateReviewVerdict, Vehicle } from "@/lib/api/types";
import { ApiError } from "@/lib/api/client";

interface VehiculeLotProps {
  company: Company;
  onCompleted: (created: Vehicle[]) => void;
}

interface ArbitrationRequest {
  index: number;
  candidate: DuplicateCandidate;
  draft: VehiculeFormValues;
}

interface ItemOutcome {
  index: number;
  label: string;
  status: "created" | "skipped_duplicate" | "error";
  vehicle?: Vehicle;
  detail?: string;
}

/**
 * Mode lot — N véhicules pour une société (plan.md § 6 vague 3, décision A étape 5).
 * Un seul formulaire (`useFieldArray`), une seule file de soumission séquentielle qui
 * rejoue le dédoublonnage juste avant chaque création et ouvre l'écran d'arbitrage sur
 * les candidats probables.
 */
export function VehiculeLot({ company, onCompleted }: VehiculeLotProps) {
  const form = useForm<VehiculeLotFormValues>({
    resolver: zodResolver(vehiculeLotSchema),
    defaultValues: { vehicules: [vehiculeDefaultValues as VehiculeFormValues] },
  });
  const fieldArray = useFieldArray({ control: form.control, name: "vehicules" });

  const duplicateCheck = useDuplicateCheck();
  const createVehicle = useCreateVehicle();
  const createIntakeBatch = useCreateIntakeBatch();
  const duplicateReview = useDuplicateReview();

  const [duplicateStates, setDuplicateStates] = useState<Record<number, DuplicateState>>({});
  const [intakeBatchId, setIntakeBatchId] = useState<string | null>(null);
  const [arbitration, setArbitration] = useState<ArbitrationRequest | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [globalError, setGlobalError] = useState<string | null>(null);
  const [outcomes, setOutcomes] = useState<ItemOutcome[] | null>(null);

  const clearedCandidateIds = useRef<Set<string>>(new Set());
  const arbitrationResolver = useRef<((verdict: DuplicateReviewVerdict, scope: "pair" | "batch") => void) | null>(
    null,
  );

  const isLot = fieldArray.fields.length > 1;

  const runDuplicateCheck = useCallback(
    async (index: number, batchId: string | null) => {
      const values = form.getValues(`vehicules.${index}`);
      if (!values.vin && !values.immatriculation) {
        setDuplicateStates((prev) => ({ ...prev, [index]: { status: "idle" } }));
        return;
      }
      setDuplicateStates((prev) => ({ ...prev, [index]: { status: "checking" } }));
      try {
        const draft = toVehicleDraft(values, company.id, batchId);
        const result = await duplicateCheck.mutateAsync(draft);
        const status =
          result.exact.length > 0
            ? "exact"
            : result.probable.length > 0
              ? "probable"
              : result.similar.length > 0
                ? "similar"
                : "clear";
        setDuplicateStates((prev) => ({ ...prev, [index]: { status, result } }));
      } catch (err) {
        // Ne jamais avaler silencieusement : une divergence de contrat doit rester visible
        // (console + message affiché), pas disparaître dans un statut "error" muet.
        console.error(`duplicate-check a échoué pour le véhicule ${index + 1} du lot`, err);
        setDuplicateStates((prev) => ({
          ...prev,
          [index]: { status: "error", message: describeError(err) },
        }));
      }
    },
    [company.id, duplicateCheck, form],
  );

  const requestArbitration = useCallback(
    (index: number, candidate: DuplicateCandidate, draft: VehiculeFormValues) =>
      new Promise<{ verdict: DuplicateReviewVerdict; scope: "pair" | "batch" }>((resolve) => {
        arbitrationResolver.current = (verdict, scope) => resolve({ verdict, scope });
        setArbitration({ index, candidate, draft });
      }),
    [],
  );

  const handleArbitrationDecision = (verdict: DuplicateReviewVerdict, scope: "pair" | "batch") => {
    setArbitration(null);
    arbitrationResolver.current?.(verdict, scope);
    arbitrationResolver.current = null;
  };

  /**
   * Flux en deux temps figé côté backend (implementation.md § Backend « Contrat final
   * figé ») : `duplicate_resolution` n'existe pas côté serveur et n'est jamais lu.
   * 1. `POST /vehicles` avec `force_create: true` pour passer outre le `409
   *    duplicate_probable` une fois l'opératrice arbitrée.
   * 2. `POST /duplicate-reviews` avec l'id fraîchement créé + l'id du candidat + le verdict
   *    + `score`/`features` renvoyés tels quels par `duplicate-check` — cette paire précise
   *    ne sera plus jamais reproposée (décision A, étape 5).
   *
   * L'échec de l'étape 2 n'annule PAS l'étape 1 : à ce stade le véhicule existe déjà en base
   * (régression review-finale.md § 🟠 VehiculeLot — un `POST /duplicate-reviews` en échec
   * faisait passer toute la ligne en statut "error", l'opératrice ressaisissait alors une
   * fiche qui existait déjà, créant un vrai doublon dans l'outil censé les détecter). Seul
   * l'arbitrage n'est pas persisté ; au pire la paire pourra être reproposée à un prochain
   * contrôle, ce qui reste sans danger.
   */
  const createVehicleClearedAsDuplicate = useCallback(
    async (
      draft: ReturnType<typeof toVehicleDraft>,
      candidate: DuplicateCandidate,
    ): Promise<{ vehicle: Vehicle; reviewError: string | null }> => {
      const vehicle = await createVehicle.mutateAsync({ ...draft, force_create: true });
      try {
        await duplicateReview.mutateAsync({
          vehicle_a_id: vehicle.id,
          vehicle_b_id: candidate.vehicle_id,
          verdict: "not_duplicate",
          score: candidate.score,
          features: candidate.features,
        });
        return { vehicle, reviewError: null };
      } catch (err) {
        if (err instanceof ApiError) {
          console.error(
            `L'enregistrement de l'arbitrage a échoué pour le véhicule ${vehicle.reference} — la fiche est bien créée, seul le verdict de dédoublonnage n'est pas persisté`,
            err,
          );
          return { vehicle, reviewError: describeError(err) };
        }
        // Bug de programmation potentiel, pas une erreur métier attendue : ne pas le masquer
        // derrière un statut "créée" silencieux, remonter bruyamment comme le reste du fichier.
        console.error(
          `Échec inattendu (hors erreur métier) lors de l'enregistrement de l'arbitrage pour le véhicule ${vehicle.reference}`,
          err,
        );
        throw err;
      }
    },
    [createVehicle, duplicateReview],
  );

  const onSubmitLot = useCallback(
    async (values: VehiculeLotFormValues) => {
    setGlobalError(null);
    setOutcomes(null);
    setIsProcessing(true);

    try {
      let batchId = intakeBatchId;
      if (values.vehicules.length > 1 && !batchId) {
        const label = `Lot ${company.denomination} — ${new Date().toLocaleDateString("fr-FR")}`;
        const batch = await createIntakeBatch.mutateAsync({ company_id: company.id, label });
        batchId = batch.id;
        setIntakeBatchId(batchId);
      }

      const results: ItemOutcome[] = [];
      const created: Vehicle[] = [];

      for (let index = 0; index < values.vehicules.length; index += 1) {
        const item = values.vehicules[index];
        const label = `${item.marque} ${item.modele}`.trim() || `Véhicule ${index + 1}`;
        const draft = toVehicleDraft(item, company.id, batchId);

        try {
          const check = await duplicateCheck.mutateAsync(draft);

          if (check.exact.length > 0) {
            results.push({
              index,
              label,
              status: "skipped_duplicate",
              detail: `Doublon exact avec la fiche ${check.exact[0].reference} — non enregistré.`,
            });
            continue;
          }

          if (check.probable.length > 0) {
            const topCandidate = check.probable[0];

            if (clearedCandidateIds.current.has(topCandidate.vehicle_id)) {
              const { vehicle, reviewError } = await createVehicleClearedAsDuplicate(draft, topCandidate);
              created.push(vehicle);
              results.push({
                index,
                label,
                status: "created",
                vehicle,
                detail: reviewError
                  ? `Créée sous la référence ${vehicle.reference} — arbitrage non enregistré (${reviewError}). Cette paire pourra être reproposée.`
                  : undefined,
              });
              continue;
            }

            const decision = await requestArbitration(index, topCandidate, item);

            if (decision.verdict === "duplicate") {
              results.push({
                index,
                label,
                status: "skipped_duplicate",
                detail: `Confirmé comme doublon de la fiche ${topCandidate.reference} — non enregistré.`,
              });
              continue;
            }

            if (decision.scope === "batch") {
              clearedCandidateIds.current.add(topCandidate.vehicle_id);
            }

            const { vehicle, reviewError } = await createVehicleClearedAsDuplicate(draft, topCandidate);
            created.push(vehicle);
            results.push({
              index,
              label,
              status: "created",
              vehicle,
              detail: reviewError
                ? `Créée sous la référence ${vehicle.reference} — arbitrage non enregistré (${reviewError}). Cette paire pourra être reproposée.`
                : undefined,
            });
            continue;
          }

          const vehicle = await createVehicle.mutateAsync(draft);
          created.push(vehicle);
          results.push({ index, label, status: "created", vehicle });
        } catch (err) {
          // Seule une erreur métier attendue (`ApiError`, ex. 409/422 renvoyé par le
          // serveur) reste confinée à la ligne du récapitulatif. Toute autre exception
          // (bug de programmation, divergence de contrat) ne doit pas se cacher derrière
          // un statut "erreur" muet dans une liste qu'on peut ne pas relire ligne à ligne :
          // elle est journalisée et remonte pour interrompre tout le lot bruyamment.
          if (err instanceof ApiError) {
            results.push({ index, label, status: "error", detail: describeError(err) });
            continue;
          }
          console.error(
            `Échec inattendu (hors erreur métier) lors de l'enregistrement du véhicule ${index + 1} du lot`,
            err,
          );
          throw err;
        }
      }

      setOutcomes(results);
      if (created.length > 0) {
        onCompleted(created);
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setGlobalError(err.message);
      } else {
        console.error("Échec inattendu pendant l'enregistrement du lot", err);
        setGlobalError(`Erreur inattendue pendant l'enregistrement du lot : ${describeError(err)}`);
      }
    } finally {
      setIsProcessing(false);
    }
    },
    [
      company.id,
      company.denomination,
      intakeBatchId,
      createIntakeBatch,
      duplicateCheck,
      createVehicle,
      createVehicleClearedAsDuplicate,
      requestArbitration,
      onCompleted,
    ],
  );

  return (
    <FormProvider {...form}>
      <form
        // La soumission (donc la lecture des refs à l'intérieur de `onSubmitLot`) est
        // différée à l'événement réel : appeler `form.handleSubmit(...)` directement dans
        // le corps du composant serait détecté comme une lecture de ref pendant le rendu.
        onSubmit={(event) => {
          void form.handleSubmit(onSubmitLot)(event);
        }}
        className="flex flex-col gap-4"
        noValidate
      >
        {globalError ? (
          <Alert variant="destructive">
            <CircleAlert />
            <AlertTitle>Enregistrement interrompu</AlertTitle>
            <AlertDescription>{globalError}</AlertDescription>
          </Alert>
        ) : null}

        {outcomes ? <OutcomesSummary outcomes={outcomes} /> : null}

        {fieldArray.fields.map((field, index) => (
          <VehiculeStep
            key={field.id}
            index={index}
            label={isLot ? `Véhicule ${index + 1} du lot` : "Véhicule"}
            canRemove={fieldArray.fields.length > 1}
            onRemove={() => {
              fieldArray.remove(index);
              setDuplicateStates({});
            }}
            duplicateState={duplicateStates[index] ?? { status: "idle" }}
            onCheckDuplicate={() => runDuplicateCheck(index, intakeBatchId)}
          />
        ))}

        <div className="flex flex-wrap items-center justify-between gap-3">
          <Button
            type="button"
            variant="outline"
            onClick={() => fieldArray.append(vehiculeDefaultValues as VehiculeFormValues)}
          >
            <PlusCircle className="size-4" aria-hidden="true" />
            Ajouter un véhicule à ce lot
          </Button>

          <Button type="submit" disabled={isProcessing}>
            {isProcessing
              ? "Enregistrement…"
              : isLot
                ? `Enregistrer le lot (${fieldArray.fields.length} véhicules)`
                : "Enregistrer la fiche"}
          </Button>
        </div>
      </form>

      {arbitration ? (
        <ArbitrageDoublon
          open
          vehicleLabel={isLot ? `Véhicule ${arbitration.index + 1} du lot` : "Ce véhicule"}
          draft={arbitration.draft}
          candidate={arbitration.candidate}
          allowBatchScope={isLot}
          onDecision={handleArbitrationDecision}
        />
      ) : null}
    </FormProvider>
  );
}

function OutcomesSummary({ outcomes }: { outcomes: ItemOutcome[] }) {
  const createdCount = outcomes.filter((o) => o.status === "created").length;
  const skippedCount = outcomes.length - createdCount;

  return (
    <Alert>
      <AlertTitle>
        {createdCount} fiche{createdCount > 1 ? "s" : ""} enregistrée{createdCount > 1 ? "s" : ""}
        {skippedCount > 0 ? ` — ${skippedCount} non enregistrée${skippedCount > 1 ? "s" : ""}` : ""}
      </AlertTitle>
      <AlertDescription>
        <ul className="mt-1 flex flex-col gap-0.5">
          {outcomes.map((outcome) => (
            <li key={outcome.index}>
              {outcome.status === "created" ? "✓" : "—"} {outcome.label}
              {outcome.detail ? ` : ${outcome.detail}` : outcome.vehicle ? ` (${outcome.vehicle.reference})` : ""}
            </li>
          ))}
        </ul>
      </AlertDescription>
    </Alert>
  );
}
