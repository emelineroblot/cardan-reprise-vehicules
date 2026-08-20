import { z } from "zod";
import { isPlausibleImmatriculation, normalizeImmatriculation } from "@/lib/format/immatriculation";
import { isPlausibleVin, normalizeVin } from "@/lib/format/vin";
import type { VehicleCreate } from "@/lib/api/types";

/**
 * Schéma de l'étape véhicule (react-hook-form + zod, plan.md § 6 vague 3).
 * Reflète `VehicleDraft` (schema.d.ts) : les champs optionnels côté modèle
 * (`vehicle` table, § 5.1) restent optionnels ici — la vérité de contrainte
 * (index uniques partiels, CHECK) reste en base, ce schéma ne fait que guider
 * la saisie et éviter un aller-retour réseau inutile.
 */

export const energieValues = ["essence", "diesel", "hybride", "electrique", "gpl", "autre"] as const;
export const boiteValues = ["manuelle", "automatique"] as const;

export const vehiculeSchema = z
  .object({
    marque: z.string().trim().min(1, "La marque est obligatoire."),
    modele: z.string().trim().min(1, "Le modèle est obligatoire."),
    version: z.string().trim().optional(),
    energie: z.enum(energieValues).optional(),
    boite: z.enum(boiteValues).optional(),
    couleur: z.string().trim().optional(),
    vin: z
      .string()
      .trim()
      .optional()
      .refine((v) => !v || isPlausibleVin(v), {
        message: "VIN invalide (17 caractères, lettres/chiffres, sans I, O ni Q).",
      }),
    immatriculation: z
      .string()
      .trim()
      .optional()
      .refine((v) => !v || isPlausibleImmatriculation(v), {
        message: "Format non reconnu (attendu : AA-123-BB).",
      }),
    date_mise_en_circulation: z.string().trim().optional(),
    // Conversion "" -> undefined faite côté champ (`setValueAs`, VehiculeStep.tsx), pas ici :
    // un `z.preprocess`/`.transform()` casse l'inférence de type avec le resolver
    // react-hook-form en zod v4 (constaté au type-check, cf. commit).
    kilometrage: z.number().int().nonnegative("Le kilométrage ne peut pas être négatif.").optional(),
    date_proposition: z.string().trim().min(1, "La date de proposition est obligatoire."),
    // Nullable : `MoneyInput` renvoie `null` (pas `undefined`) quand le champ est vide.
    prix_achat_negocie_cents: z
      .number()
      .int()
      .nonnegative("Le prix ne peut pas être négatif.")
      .nullable()
      .optional(),
    valeur_revente_estimee_cents: z
      .number()
      .int()
      .nonnegative("La valeur estimée ne peut pas être négative.")
      .nullable()
      .optional(),
    frais_transport_cents: z
      .number()
      .int()
      .nonnegative("Les frais ne peuvent pas être négatifs.")
      .nullable()
      .optional(),
    commentaire: z.string().trim().optional(),
  })
  .strict();

export type VehiculeFormValues = z.infer<typeof vehiculeSchema>;

export const vehiculeDefaultValues: Partial<VehiculeFormValues> = {
  date_proposition: new Date().toISOString().slice(0, 10),
};

/**
 * Mode lot (plan.md § 6 vague 3, décision A étape 5) : N véhicules pour une même société,
 * portés par un seul formulaire (`useFieldArray`) pour que la soumission — et le contrôle
 * de doublons qui la précède — reste une opération unique et cohérente.
 */
export const vehiculeLotSchema = z.object({
  vehicules: z.array(vehiculeSchema).min(1, "Ajoutez au moins un véhicule."),
});

export type VehiculeLotFormValues = z.infer<typeof vehiculeLotSchema>;

/**
 * Convertit une entrée de formulaire en `VehicleCreate` (contrat backend figé — voir
 * `implementation.md` § Backend « Contrat final »). Chaînes vides -> null,
 * VIN/immatriculation normalisés côté affichage avant envoi (la normalisation qui fait
 * autorité reste côté backend, § 4 décision A étape 0). `force_create` par défaut à
 * `false` : c'est l'appelant (`VehiculeLot`) qui le bascule à `true` après arbitrage.
 */
export function toVehicleDraft(
  values: VehiculeFormValues,
  companyId: string,
  intakeBatchId: string | null,
): VehicleCreate {
  return {
    company_id: companyId,
    intake_batch_id: intakeBatchId,
    marque: values.marque,
    modele: values.modele,
    version: values.version || null,
    energie: values.energie ?? null,
    boite: values.boite ?? null,
    couleur: values.couleur || null,
    vin: values.vin ? normalizeVin(values.vin) : null,
    immatriculation: values.immatriculation ? normalizeImmatriculation(values.immatriculation) : null,
    date_mise_en_circulation: values.date_mise_en_circulation || null,
    kilometrage: values.kilometrage ?? null,
    date_proposition: values.date_proposition,
    prix_achat_negocie_cents: values.prix_achat_negocie_cents ?? null,
    valeur_revente_estimee_cents: values.valeur_revente_estimee_cents ?? null,
    frais_transport_cents: values.frais_transport_cents ?? 0,
    commentaire: values.commentaire || null,
    force_create: false,
  };
}
