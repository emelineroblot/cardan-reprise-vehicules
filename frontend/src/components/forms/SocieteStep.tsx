"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { CircleAlert, Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { FieldError } from "@/components/ui/field-error";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useCompanyLookup } from "@/lib/api/hooks/useCompanyLookup";
import { useCreateCompany } from "@/lib/api/hooks/useCreateCompany";
import { api, ApiError } from "@/lib/api/client";
import { describeError } from "@/components/ui/error-state";
import { normalizeSiret } from "@/lib/validation/siret";
import {
  lookupCompletionSchema,
  siretLookupSchema,
  societeSchema,
  typeFlotteValues,
  type LookupCompletionValues,
  type SocieteFormValues,
} from "@/lib/validation/societe";
import { TYPE_FLOTTE_LABELS, type Company, type CompanyLookupResponse } from "@/lib/api/types";

type Mode = "search" | "confirm" | "manual";

interface SocieteStepProps {
  onCompanyReady: (company: Company) => void;
}

const SOURCE_BADGE_LABEL: Record<CompanyLookupResponse["source"], string> = {
  api: "Source : API Recherche d'entreprises",
  cache: "Source : cache local",
  demo: "Source : jeu de démonstration",
};

/**
 * Étape société — SIRET, remplissage automatique, bascule manuelle obligatoire sur
 * indisponibilité (plan.md § 4 décision B, § 6 vague 3).
 */
export function SocieteStep({ onCompanyReady }: SocieteStepProps) {
  const [mode, setMode] = useState<Mode>("search");
  const [lookupResult, setLookupResult] = useState<CompanyLookupResponse | null>(null);
  const [unavailableBanner, setUnavailableBanner] = useState(false);
  const [manualPrefillSiret, setManualPrefillSiret] = useState<string | undefined>(undefined);

  const lookup = useCompanyLookup();
  const createCompany = useCreateCompany();

  /**
   * `POST /companies` renvoie `409 conflict` (`details.company_id`) quand le SIRET est déjà
   * enregistré — c'est le cas nominal, pas une exception, dès qu'on ressaisit une flotte
   * déjà cliente (le jeu de démo précharge d'ailleurs le lookup de sociétés qui ont déjà des
   * véhicules). Plutôt que de bloquer l'opératrice sur une erreur, on réutilise la fiche
   * société existante : `GET /companies/{id}` avec l'id renvoyé par le conflit.
   */
  const createOrReuseCompany: typeof createCompany.mutateAsync = async (payload) => {
    try {
      return await createCompany.mutateAsync(payload);
    } catch (err) {
      const companyId =
        err instanceof ApiError && err.code === "conflict" ? err.details?.company_id : undefined;
      if (typeof companyId === "string") {
        return api.get<Company>(`/companies/${companyId}`);
      }
      throw err;
    }
  };

  const searchForm = useForm<{ siret: string }>({
    resolver: zodResolver(siretLookupSchema),
    defaultValues: { siret: "" },
  });

  const handleSearch = searchForm.handleSubmit(async ({ siret }) => {
    setUnavailableBanner(false);
    const normalized = normalizeSiret(siret);
    try {
      const result = await lookup.mutateAsync(normalized);
      setLookupResult(result);
      setMode("confirm");
    } catch (err) {
      if (err instanceof ApiError && err.code === "siret_lookup_unavailable") {
        setUnavailableBanner(true);
        setManualPrefillSiret(normalized);
        setMode("manual");
        return;
      }
      // 404 siret_not_found / 422 siret_invalid : erreur affichee sous le champ,
      // l operatrice reste en recherche ou bascule manuellement de son propre chef.
      searchForm.setError("siret", { message: describeError(err) });
    }
  });

  if (mode === "confirm" && lookupResult) {
    return (
      <ConfirmLookupForm
        result={lookupResult}
        isSubmitting={createCompany.isPending}
        submitError={createCompany.error}
        onBack={() => {
          setMode("search");
          setLookupResult(null);
        }}
        onSwitchManual={() => {
          setManualPrefillSiret(lookupResult.company.siret);
          setMode("manual");
        }}
        onSubmit={async (values) => {
          const company = await createOrReuseCompany({
            ...lookupResult.company,
            // `CompanyLookupCompany` ne porte pas `pays` (donnée externe, hors périmètre
            // du lookup) : toujours FR pour ce projet (plan.md § 5.1, défaut du modèle).
            pays: "FR",
            type_flotte: values.type_flotte,
            source_enrichissement: lookupResult.source,
            contact_nom: values.contact_nom || null,
            contact_telephone: values.contact_telephone || null,
          });
          onCompanyReady(company);
        }}
      />
    );
  }

  if (mode === "manual") {
    return (
      <ManualCompanyForm
        prefillSiret={manualPrefillSiret}
        showUnavailableBanner={unavailableBanner}
        isSubmitting={createCompany.isPending}
        submitError={createCompany.error}
        onBackToSearch={() => {
          setUnavailableBanner(false);
          setMode("search");
        }}
        onSubmit={async (values) => {
          const company = await createOrReuseCompany({
            ...values,
            contact_nom: values.contact_nom || null,
            contact_telephone: values.contact_telephone || null,
            source_enrichissement: "manuel",
          });
          onCompanyReady(company);
        }}
      />
    );
  }

  return (
    <form onSubmit={handleSearch} className="flex flex-col gap-4" noValidate>
      <div>
        <Label htmlFor="siret">Numéro SIRET</Label>
        <div className="mt-1.5 flex gap-2">
          <Input
            id="siret"
            inputMode="numeric"
            autoComplete="off"
            placeholder="14 chiffres, ex. 55208131766522"
            aria-invalid={Boolean(searchForm.formState.errors.siret) || undefined}
            aria-describedby={searchForm.formState.errors.siret ? "siret-error" : undefined}
            {...searchForm.register("siret")}
          />
          <Button type="submit" disabled={lookup.isPending}>
            <Search className="size-4" aria-hidden="true" />
            {lookup.isPending ? "Recherche…" : "Rechercher"}
          </Button>
        </div>
        <FieldError id="siret-error" message={searchForm.formState.errors.siret?.message} />
      </div>

      <div className="text-sm text-muted-foreground">
        Vous n&apos;avez pas le SIRET, ou l&apos;entreprise n&apos;existe pas dans le répertoire ?{" "}
        <Button
          type="button"
          variant="link"
          className="h-auto p-0 text-sm"
          onClick={() => setMode("manual")}
        >
          Saisir la société manuellement
        </Button>
      </div>
    </form>
  );
}

function ConfirmLookupForm({
  result,
  isSubmitting,
  submitError,
  onBack,
  onSwitchManual,
  onSubmit,
}: {
  result: CompanyLookupResponse;
  isSubmitting: boolean;
  submitError: unknown;
  onBack: () => void;
  onSwitchManual: () => void;
  onSubmit: (values: LookupCompletionValues) => Promise<void>;
}) {
  const form = useForm<LookupCompletionValues>({
    resolver: zodResolver(lookupCompletionSchema),
    defaultValues: { type_flotte: undefined, contact_nom: "", contact_telephone: "" },
  });

  const { company } = result;

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
      <div className="rounded-lg border border-border bg-muted/30 p-4">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <Badge variant="secondary">{SOURCE_BADGE_LABEL[result.source]}</Badge>
          {result.stale ? (
            <Badge variant="outline" className="border-amber-300 text-amber-700">
              Données mises en cache (peut-être non à jour)
            </Badge>
          ) : null}
        </div>
        <p className="font-medium text-foreground">{company.denomination}</p>
        <p className="text-sm text-muted-foreground">
          {company.adresse_ligne1}, {company.code_postal} {company.commune}
        </p>
        <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm text-muted-foreground">
          <div>
            <dt className="inline font-medium text-foreground">SIRET : </dt>
            <dd className="inline">{company.siret}</dd>
          </div>
          {company.forme_juridique ? (
            <div>
              <dt className="inline font-medium text-foreground">Forme juridique : </dt>
              <dd className="inline">{company.forme_juridique}</dd>
            </div>
          ) : null}
          {company.libelle_naf ? (
            <div>
              <dt className="inline font-medium text-foreground">Activité (NAF) : </dt>
              <dd className="inline">{company.libelle_naf}</dd>
            </div>
          ) : null}
          {company.tranche_effectif ? (
            <div>
              <dt className="inline font-medium text-foreground">Effectif : </dt>
              <dd className="inline">{company.tranche_effectif}</dd>
            </div>
          ) : null}
        </dl>
      </div>

      <div>
        <Label htmlFor="type_flotte">Type de flotte</Label>
        <Select
          onValueChange={(value) =>
            form.setValue("type_flotte", value as LookupCompletionValues["type_flotte"], {
              shouldValidate: true,
            })
          }
        >
          <SelectTrigger
            id="type_flotte"
            className="mt-1.5 w-full"
            aria-invalid={Boolean(form.formState.errors.type_flotte) || undefined}
          >
            <SelectValue placeholder="Sélectionnez…" />
          </SelectTrigger>
          <SelectContent>
            {typeFlotteValues.map((value) => (
              <SelectItem key={value} value={value}>
                {TYPE_FLOTTE_LABELS[value]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <FieldError
          message={form.formState.errors.type_flotte ? "Le type de flotte est obligatoire." : undefined}
        />
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <Label htmlFor="contact_nom">Contact (nom)</Label>
          <Input id="contact_nom" className="mt-1.5" {...form.register("contact_nom")} />
        </div>
        <div>
          <Label htmlFor="contact_telephone">Contact (téléphone)</Label>
          <Input id="contact_telephone" className="mt-1.5" {...form.register("contact_telephone")} />
        </div>
      </div>

      {submitError ? (
        <Alert variant="destructive">
          <CircleAlert />
          <AlertTitle>Impossible d&apos;enregistrer la société</AlertTitle>
          <AlertDescription>{describeError(submitError)}</AlertDescription>
        </Alert>
      ) : null}

      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Enregistrement…" : "Valider cette société"}
        </Button>
        <Button type="button" variant="outline" onClick={onBack}>
          Ce n&apos;est pas la bonne société
        </Button>
        <Button type="button" variant="ghost" onClick={onSwitchManual}>
          Corriger manuellement
        </Button>
      </div>
    </form>
  );
}

function ManualCompanyForm({
  prefillSiret,
  showUnavailableBanner,
  isSubmitting,
  submitError,
  onBackToSearch,
  onSubmit,
}: {
  prefillSiret?: string;
  showUnavailableBanner: boolean;
  isSubmitting: boolean;
  submitError: unknown;
  onBackToSearch: () => void;
  onSubmit: (values: SocieteFormValues) => Promise<void>;
}) {
  const form = useForm<SocieteFormValues>({
    resolver: zodResolver(societeSchema),
    defaultValues: {
      siret: prefillSiret ?? "",
      denomination: "",
      adresse_ligne1: "",
      code_postal: "",
      commune: "",
      pays: "FR",
      type_flotte: undefined,
    },
  });

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
      {showUnavailableBanner ? (
        <Alert>
          <CircleAlert />
          <AlertTitle>Service d&apos;enrichissement SIRET momentanément indisponible</AlertTitle>
          <AlertDescription>
            Vous pouvez continuer la saisie manuellement — rien n&apos;est bloqué. Les données de
            l&apos;entreprise pourront être complétées plus tard.
          </AlertDescription>
        </Alert>
      ) : (
        <div className="text-sm text-muted-foreground">
          <Button type="button" variant="link" className="h-auto p-0 text-sm" onClick={onBackToSearch}>
            ← Revenir à la recherche par SIRET
          </Button>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <Label htmlFor="m_siret">SIRET</Label>
          <Input id="m_siret" inputMode="numeric" className="mt-1.5" {...form.register("siret")} />
          <FieldError message={form.formState.errors.siret?.message} />
        </div>
        <div>
          <Label htmlFor="m_denomination">Dénomination</Label>
          <Input id="m_denomination" className="mt-1.5" {...form.register("denomination")} />
          <FieldError message={form.formState.errors.denomination?.message} />
        </div>
      </div>

      <div>
        <Label htmlFor="m_adresse">Adresse</Label>
        <Input id="m_adresse" className="mt-1.5" {...form.register("adresse_ligne1")} />
        <FieldError message={form.formState.errors.adresse_ligne1?.message} />
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <Label htmlFor="m_cp">Code postal</Label>
          <Input id="m_cp" className="mt-1.5" {...form.register("code_postal")} />
          <FieldError message={form.formState.errors.code_postal?.message} />
        </div>
        <div>
          <Label htmlFor="m_commune">Commune</Label>
          <Input id="m_commune" className="mt-1.5" {...form.register("commune")} />
          <FieldError message={form.formState.errors.commune?.message} />
        </div>
      </div>

      <div>
        <Label htmlFor="m_type_flotte">Type de flotte</Label>
        <Select
          onValueChange={(value) =>
            form.setValue("type_flotte", value as SocieteFormValues["type_flotte"], {
              shouldValidate: true,
            })
          }
        >
          <SelectTrigger
            id="m_type_flotte"
            className="mt-1.5 w-full"
            aria-invalid={Boolean(form.formState.errors.type_flotte) || undefined}
          >
            <SelectValue placeholder="Sélectionnez…" />
          </SelectTrigger>
          <SelectContent>
            {typeFlotteValues.map((value) => (
              <SelectItem key={value} value={value}>
                {TYPE_FLOTTE_LABELS[value]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <FieldError
          message={form.formState.errors.type_flotte ? "Le type de flotte est obligatoire." : undefined}
        />
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <Label htmlFor="m_contact_nom">Contact (nom)</Label>
          <Input id="m_contact_nom" className="mt-1.5" {...form.register("contact_nom")} />
        </div>
        <div>
          <Label htmlFor="m_contact_telephone">Contact (téléphone)</Label>
          <Input id="m_contact_telephone" className="mt-1.5" {...form.register("contact_telephone")} />
        </div>
      </div>

      {submitError ? (
        <Alert variant="destructive">
          <CircleAlert />
          <AlertTitle>Impossible d&apos;enregistrer la société</AlertTitle>
          <AlertDescription>{describeError(submitError)}</AlertDescription>
        </Alert>
      ) : null}

      <div>
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Enregistrement…" : "Valider cette société"}
        </Button>
      </div>
    </form>
  );
}
