"use client";

import { use } from "react";
import Link from "next/link";
import { ArrowLeft, TriangleAlert } from "lucide-react";
import { RoleGuard } from "@/components/domain/RoleGuard";
import { ActionsTransition } from "@/components/domain/ActionsTransition";
import { PhotoAngleGrid } from "@/components/domain/PhotoAngleGrid";
import { ChecklistItemField } from "@/components/domain/ChecklistItemField";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { LoadingState } from "@/components/ui/loading-state";
import { ErrorState } from "@/components/ui/error-state";
import { StateBadge } from "@/components/ui/state-badge";
import { useMission } from "@/lib/api/hooks/useMissions";
import { useChecklistTemplate } from "@/lib/api/hooks/useChecklistTemplates";
import { useInspectionDraft } from "@/lib/offline/useInspectionDraft";
import { missingRequiredItems } from "@/lib/validation/inspection";
import { cn } from "@/lib/utils";
import {
  CHECKLIST_CATEGORIE_LABELS,
  ETAT_GENERAL_LABELS,
  INSPECTION_CONCLUSION_LABELS,
  type ChecklistCategorie,
  type ChecklistItemTemplate,
  type EtatGeneral,
  type InspectionConclusion,
} from "@/lib/api/types";

/** Plafond de photos par véhicule (brief J2 / plan.md § 4 décision C) — figé, pas une
 * règle dérivée de l'API : affiché ici pour guider la capture, l'enforcement réel reste
 * `409 photo_quota_exceeded` côté serveur, `details.limit` fait foi en cas d'écart. */
const MAX_PHOTOS_PER_VEHICLE = 30;

const CATEGORY_ORDER: ChecklistCategorie[] = ["exterieur", "interieur", "mecanique", "documents", "securite"];

export default function ControlePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <RoleGuard allowed={["chauffeur", "administrateur"]}>
      <Controle missionId={id} />
    </RoleGuard>
  );
}

function Controle({ missionId }: { missionId: string }) {
  const mission = useMission(missionId);
  const vehicleId = mission.data?.vehicle.id;
  const draftState = useInspectionDraft(vehicleId ?? "", missionId);
  const template = useChecklistTemplate(draftState.draft?.template_id);

  if (mission.isLoading) return <LoadingState label="Chargement de la mission…" />;
  if (mission.error) {
    return <ErrorState error={mission.error} title="Mission introuvable" onRetry={() => mission.refetch()} />;
  }
  if (!mission.data) return null;

  const vehicle = mission.data.vehicle;
  const alreadySubmitted = Boolean(draftState.draft?.submitted_at);

  return (
    <div className="flex flex-col gap-6 pb-24">
      <div>
        <Button asChild variant="ghost" size="sm" className="-ml-2">
          <Link href={`/missions/${missionId}`}>
            <ArrowLeft className="size-4" aria-hidden="true" />
            Retour à la mission
          </Link>
        </Button>
      </div>

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm text-muted-foreground">{vehicle.reference}</p>
          <h1 className="text-2xl font-semibold tracking-tight">
            {vehicle.marque} {vehicle.modele} {vehicle.version ?? ""}
          </h1>
        </div>
        <StateBadge state={vehicle.state} className="text-sm" />
      </div>

      {vehicle.state !== "CONTROLE_EN_COURS" && !alreadySubmitted ? (
        <p className="flex items-center gap-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
          <TriangleAlert className="size-4 shrink-0" aria-hidden="true" />
          Ce véhicule n&apos;est plus « Contrôle en cours ». Le brouillon local reste consultable et sera
          synchronisé, mais aucune nouvelle réponse ne pourra être soumise pour cet état.
        </p>
      ) : null}

      {draftState.isLoading ? <LoadingState label="Ouverture du contrôle…" /> : null}
      {draftState.error ? (
        <ErrorState error={draftState.error} title="Contrôle indisponible" onRetry={() => draftState.refresh()} />
      ) : null}

      {draftState.draft && !alreadySubmitted ? (
        <ControleForm draftState={draftState} templateItems={template.data?.items ?? []} templateError={template.error} />
      ) : null}

      {alreadySubmitted ? (
        <section className="flex flex-col gap-3 rounded-lg border border-emerald-300 bg-emerald-50 p-4 dark:border-emerald-800 dark:bg-emerald-950/40">
          <h2 className="font-medium text-foreground">Contrôle soumis</h2>
          <p className="text-sm text-muted-foreground">
            Les réponses et les photos ont été envoyées. Choisissez la suite à donner au véhicule :
          </p>
          <ActionsTransition vehicleId={vehicle.id} size="lg" />
        </section>
      ) : null}
    </div>
  );
}

type DraftState = ReturnType<typeof useInspectionDraft>;

function ControleForm({
  draftState,
  templateItems,
  templateError,
}: {
  draftState: DraftState;
  templateItems: ChecklistItemTemplate[];
  templateError: unknown;
}) {
  const { draft, photos, angleProgress, setFields, setItemAnswer, addPhoto, retakePhoto, submit, photoError } =
    draftState;
  if (!draft) return null;

  const missingItems = missingRequiredItems(templateItems, draft.items);
  const missingAngles = angleProgress?.missing ?? null;
  const canSubmit = missingItems.length === 0 && (missingAngles === null || missingAngles.length === 0);

  const grouped = CATEGORY_ORDER.map((categorie) => ({
    categorie,
    items: templateItems.filter((item) => item.categorie === categorie).sort((a, b) => a.ordre - b.ordre),
  })).filter((group) => group.items.length > 0);

  return (
    <div className="flex flex-col gap-6">
      {draft.last_sync_error ? (
        <p role="alert" className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          {draft.last_sync_error}
        </p>
      ) : null}

      <section aria-labelledby="infos-heading" className="flex flex-col gap-4 rounded-lg border border-border p-4">
        <h2 id="infos-heading" className="font-medium text-foreground">
          Informations générales
        </h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <Label htmlFor="kilometrage_releve">Kilométrage relevé</Label>
            <Input
              id="kilometrage_releve"
              type="number"
              inputMode="numeric"
              className="mt-1.5 h-12 text-base"
              value={draft.kilometrage_releve ?? ""}
              onChange={(e) => {
                const value = e.target.value;
                void setFields({ kilometrage_releve: value === "" ? null : Number(value) });
              }}
            />
          </div>
          <div>
            <span className="block text-sm font-medium text-foreground">État général</span>
            <div className="mt-1.5 flex gap-2" role="group" aria-label="État général">
              {(Object.keys(ETAT_GENERAL_LABELS) as EtatGeneral[]).map((etat) => (
                <Button
                  key={etat}
                  type="button"
                  variant={draft.etat_general === etat ? "default" : "outline"}
                  className="h-12 flex-1 text-base"
                  aria-pressed={draft.etat_general === etat}
                  onClick={() => void setFields({ etat_general: etat })}
                >
                  {ETAT_GENERAL_LABELS[etat]}
                </Button>
              ))}
            </div>
          </div>
        </div>
        <div>
          <Label htmlFor="commentaire">Commentaire général (optionnel)</Label>
          <Textarea
            id="commentaire"
            className="mt-1.5 min-h-20 text-base"
            value={draft.commentaire ?? ""}
            onChange={(e) => void setFields({ commentaire: e.target.value })}
          />
        </div>
      </section>

      <section aria-labelledby="checklist-heading" className="flex flex-col gap-4 rounded-lg border border-border p-4">
        <h2 id="checklist-heading" className="font-medium text-foreground">
          Checklist de contrôle
        </h2>
        {templateError ? (
          <ErrorState error={templateError} title="Référentiel indisponible" />
        ) : templateItems.length === 0 ? (
          <LoadingState label="Chargement du référentiel…" />
        ) : (
          grouped.map((group) => (
            <div key={group.categorie} className="flex flex-col gap-3">
              <h3 className="text-sm font-semibold text-muted-foreground">
                {CHECKLIST_CATEGORIE_LABELS[group.categorie]}
              </h3>
              <div className="grid gap-3 sm:grid-cols-2">
                {group.items.map((item) => (
                  <ChecklistItemField
                    key={item.id}
                    item={item}
                    answer={draft.items[item.id]}
                    onChange={(answer) => void setItemAnswer(answer)}
                  />
                ))}
              </div>
            </div>
          ))
        )}
      </section>

      <section aria-labelledby="photos-heading" className="flex flex-col gap-4 rounded-lg border border-border p-4">
        <h2 id="photos-heading" className="font-medium text-foreground">
          Photos du véhicule
        </h2>
        {photoError ? (
          <p role="alert" className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
            {photoError}
          </p>
        ) : null}
        <PhotoAngleGrid
          requiredAngles={angleProgress?.required ?? null}
          photos={photos}
          onCapture={(file, angle) => addPhoto(file, angle)}
          onRetake={(photo) => retakePhoto(photo)}
          maxPhotos={MAX_PHOTOS_PER_VEHICLE}
        />
      </section>

      <ValidationSection
        missingItems={missingItems}
        missingAngles={missingAngles}
        canSubmit={canSubmit}
        onSubmit={(conclusion) => submit(conclusion)}
        missingFromServer={draft.missing_items}
        missingAnglesFromServer={draft.missing_angles}
      />
    </div>
  );
}

function ValidationSection({
  missingItems,
  missingAngles,
  canSubmit,
  onSubmit,
  missingFromServer,
  missingAnglesFromServer,
}: {
  missingItems: string[];
  missingAngles: string[] | null;
  canSubmit: boolean;
  onSubmit: (conclusion: InspectionConclusion) => void;
  missingFromServer: string[] | null;
  missingAnglesFromServer: string[] | null;
}) {
  const conclusions = Object.keys(INSPECTION_CONCLUSION_LABELS) as InspectionConclusion[];

  return (
    <section
      aria-labelledby="validation-heading"
      className="sticky bottom-0 flex flex-col gap-3 rounded-lg border border-border bg-background p-4 shadow-lg"
    >
      <h2 id="validation-heading" className="font-medium text-foreground">
        Conclusion du contrôle
      </h2>

      {!canSubmit ? (
        <div role="alert" className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
          <p className="font-medium">Il manque des éléments obligatoires :</p>
          <ul className="mt-1 list-inside list-disc">
            {missingItems.length > 0 ? <li>{missingItems.length} réponse(s) de checklist obligatoire(s)</li> : null}
            {missingAngles && missingAngles.length > 0 ? <li>{missingAngles.length} photo(s) d&apos;angle obligatoire(s)</li> : null}
          </ul>
        </div>
      ) : null}

      {(missingFromServer && missingFromServer.length > 0) || (missingAnglesFromServer && missingAnglesFromServer.length > 0) ? (
        <div role="alert" className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          Le serveur a refusé la dernière soumission — il manque encore : {[...(missingFromServer ?? []), ...(missingAnglesFromServer ?? [])].join(", ")}.
        </div>
      ) : null}

      <div className={cn("grid gap-2 sm:grid-cols-3")}>
        {conclusions.map((conclusion) => (
          <Button
            key={conclusion}
            type="button"
            size="lg"
            variant={conclusion === "refus" ? "destructive" : "default"}
            disabled={!canSubmit}
            className="h-14 text-base"
            onClick={() => onSubmit(conclusion)}
          >
            {INSPECTION_CONCLUSION_LABELS[conclusion]}
          </Button>
        ))}
      </div>
    </section>
  );
}
