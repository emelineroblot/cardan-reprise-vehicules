"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Check } from "lucide-react";
import { RoleGuard } from "@/components/domain/RoleGuard";
import { SocieteStep } from "@/components/forms/SocieteStep";
import { VehiculeLot } from "@/components/forms/VehiculeLot";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { Company, Vehicle } from "@/lib/api/types";

type WizardStep = "societe" | "vehicules" | "termine";

const STEPS: { key: WizardStep; label: string }[] = [
  { key: "societe", label: "Société" },
  { key: "vehicules", label: "Véhicule(s)" },
  { key: "termine", label: "Terminé" },
];

export default function NouvelleFichePage() {
  return (
    <RoleGuard allowed={["operatrice", "administrateur"]}>
      <NouvelleFicheWizard />
    </RoleGuard>
  );
}

function NouvelleFicheWizard() {
  const router = useRouter();
  const [step, setStep] = useState<WizardStep>("societe");
  const [company, setCompany] = useState<Company | null>(null);
  const [createdVehicles, setCreatedVehicles] = useState<Vehicle[]>([]);

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Nouvelle fiche d&apos;achat</h1>
        <p className="text-sm text-muted-foreground">
          Société puis véhicule(s) — le dédoublonnage est vérifié automatiquement avant
          l&apos;enregistrement.
        </p>
      </div>

      <ol className="flex items-center gap-2" aria-label="Étapes">
        {STEPS.map((s, i) => {
          const currentIndex = STEPS.findIndex((x) => x.key === step);
          const done = i < currentIndex;
          const active = s.key === step;
          return (
            <li key={s.key} className="flex items-center gap-2">
              <span
                aria-current={active ? "step" : undefined}
                className={cn(
                  "flex size-6 items-center justify-center rounded-full border text-xs font-medium",
                  done
                    ? "border-emerald-500 bg-emerald-500 text-white"
                    : active
                      ? "border-primary text-primary"
                      : "border-border text-muted-foreground",
                )}
              >
                {done ? <Check className="size-3.5" aria-hidden="true" /> : i + 1}
              </span>
              <span className={cn("text-sm", active ? "font-medium text-foreground" : "text-muted-foreground")}>
                {s.label}
              </span>
              {i < STEPS.length - 1 ? <span className="h-px w-6 bg-border" aria-hidden="true" /> : null}
            </li>
          );
        })}
      </ol>

      {step === "societe" ? (
        <SocieteStep
          onCompanyReady={(created) => {
            setCompany(created);
            setStep("vehicules");
          }}
        />
      ) : null}

      {step === "vehicules" && company ? (
        <div className="flex flex-col gap-4">
          <div className="rounded-lg border border-border bg-muted/30 p-3 text-sm">
            <span className="font-medium text-foreground">Société : </span>
            {company.denomination} ({company.siret})
          </div>
          <VehiculeLot
            company={company}
            onCompleted={(created) => {
              setCreatedVehicles((prev) => [...prev, ...created]);
              setStep("termine");
            }}
          />
        </div>
      ) : null}

      {step === "termine" ? (
        <div className="flex flex-col items-start gap-4 rounded-lg border border-emerald-300 bg-emerald-50 p-4 dark:bg-emerald-950/30">
          <p className="font-medium text-foreground">
            {createdVehicles.length} fiche{createdVehicles.length > 1 ? "s" : ""} enregistrée
            {createdVehicles.length > 1 ? "s" : ""}.
          </p>
          <ul className="text-sm text-muted-foreground">
            {createdVehicles.map((v) => (
              <li key={v.id}>
                {v.reference} — {v.marque} {v.modele}
              </li>
            ))}
          </ul>
          <div className="flex gap-2">
            <Button type="button" onClick={() => router.push("/vehicules")}>
              Voir la liste de suivi
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setStep("societe");
                setCompany(null);
                setCreatedVehicles([]);
              }}
            >
              Saisir une autre fiche
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
