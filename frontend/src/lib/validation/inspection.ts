import type { ChecklistItemTemplate } from "@/lib/api/types";
import type { LocalItemAnswer } from "@/lib/offline/types";

/** Un item a une réponse dès qu'au moins un champ de valeur est renseigné — le champ
 * pertinent dépend de `response_type` (implementation.md § J2 Backend, correspondance
 * `ok_ko → valeur_bool`, `note_1_5 → valeur_note`, `texte → valeur_texte`,
 * `numerique → valeur_num`), mais un item répondu dans le mauvais champ ne doit pas non
 * plus compter comme manquant : on vérifie que N'IMPORTE QUEL champ de valeur est posé,
 * la contrainte de forme exacte étant appliquée à l'écriture (`upsertItemAnswer`), pas ici.
 */
export function isItemAnswered(answer: LocalItemAnswer | undefined): boolean {
  if (!answer) return false;
  if (answer.valeur_bool !== null && answer.valeur_bool !== undefined) return true;
  if (answer.valeur_note !== null && answer.valeur_note !== undefined) return true;
  if (answer.valeur_num !== null && answer.valeur_num !== undefined) return true;
  if (answer.valeur_texte && answer.valeur_texte.trim().length > 0) return true;
  return false;
}

/**
 * Items obligatoires sans réponse — pré-validation CLIENT, purement indicative (même
 * principe que `duplicate-check` en J1) : la source de vérité reste `409
 * inspection_incomplete` renvoyé par `POST /inspections/{id}/submit`. Retourne les
 * **codes** d'item (pas les ids), pour un affichage lisible sans aller-retour réseau.
 */
export function missingRequiredItems(
  items: ChecklistItemTemplate[],
  answers: Record<string, LocalItemAnswer>,
): string[] {
  return items
    .filter((item) => item.is_required && !isItemAnswered(answers[item.id]))
    .map((item) => item.code);
}

/** Différence ensembliste triviale (pas une règle métier — le contenu de `required` vient
 * toujours de `GET .../required-angles`, jamais halluciné ici). */
export function missingAngles(required: string[], captured: string[]): string[] {
  const capturedSet = new Set(captured);
  return required.filter((angle) => !capturedSet.has(angle));
}
