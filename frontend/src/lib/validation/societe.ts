import { z } from "zod";
import { isValidSiretChecksum, isValidSiretFormat } from "@/lib/validation/siret";

export const typeFlotteValues = [
  "taxi",
  "ambulance",
  "transport",
  "auto_ecole",
  "location",
  "autre",
] as const;

/**
 * Étape société — couvre à la fois le remplissage automatique (SIRET valide, lookup
 * réussi) et la saisie manuelle obligatoire (bandeau de bascule sur 503, plan.md § 4
 * décision B). Le SIRET n'est pas revalidé par Luhn ici pour la saisie manuelle : une
 * opératrice qui bascule manuellement a déjà vu l'échec du lookup, lui imposer un SIRET
 * ne ferait que reproduire le blocage qu'on cherche à contourner — seul le format
 * 14 chiffres reste requis.
 */
export const societeSchema = z.object({
  siret: z
    .string()
    .trim()
    .min(1, "Le SIRET est obligatoire.")
    .refine((v) => isValidSiretFormat(v), { message: "Le SIRET doit comporter 14 chiffres." }),
  denomination: z.string().trim().min(1, "La dénomination est obligatoire."),
  forme_juridique: z.string().trim().optional(),
  code_naf: z.string().trim().optional(),
  libelle_naf: z.string().trim().optional(),
  adresse_ligne1: z.string().trim().min(1, "L'adresse est obligatoire."),
  code_postal: z.string().trim().min(1, "Le code postal est obligatoire."),
  commune: z.string().trim().min(1, "La commune est obligatoire."),
  // Pas de `.default()` ici : zod v4 distingue type d'entrée et de sortie pour
  // `.default()`, ce qui casse l'inférence du resolver react-hook-form. Le défaut "FR"
  // est posé dans `defaultValues` du formulaire (composant), pas dans le schéma.
  pays: z.string().trim().min(1, "Le pays est obligatoire."),
  tranche_effectif: z.string().trim().optional(),
  date_creation: z.string().trim().optional(),
  type_flotte: z.enum(typeFlotteValues),
  contact_nom: z.string().trim().optional(),
  contact_telephone: z.string().trim().optional(),
});

export type SocieteFormValues = z.infer<typeof societeSchema>;

export const siretLookupSchema = z.object({
  siret: z
    .string()
    .trim()
    .min(1, "Saisissez un SIRET.")
    .refine((v) => isValidSiretFormat(v), { message: "Le SIRET doit comporter 14 chiffres." })
    .refine((v) => isValidSiretChecksum(v), { message: "Ce SIRET n'est pas valide (clé de contrôle)." }),
});

/**
 * Champs complémentaires demandés après un lookup SIRET réussi : la source externe ne
 * connaît pas le type de flotte (dimension métier propre à Cardan, § 5.1) ni le contact.
 */
export const lookupCompletionSchema = z.object({
  type_flotte: z.enum(typeFlotteValues),
  contact_nom: z.string().trim().optional(),
  contact_telephone: z.string().trim().optional(),
});

export type LookupCompletionValues = z.infer<typeof lookupCompletionSchema>;
