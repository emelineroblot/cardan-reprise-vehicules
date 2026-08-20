"use client";

import { Check, X } from "lucide-react";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { isItemAnswered } from "@/lib/validation/inspection";
import type { ChecklistItemTemplate } from "@/lib/api/types";
import type { LocalItemAnswer } from "@/lib/offline/types";

interface ChecklistItemFieldProps {
  item: ChecklistItemTemplate;
  answer: LocalItemAnswer | undefined;
  onChange: (answer: LocalItemAnswer) => void;
}

const NOTES = [1, 2, 3, 4, 5];

/**
 * Un item de checklist, rendu selon `response_type` (implementation.md § J2 Backend —
 * correspondance figée côté backend, jamais réinventée ici). Cibles tactiles généreuses
 * (brief : « se manipule debout, parfois avec des gants ») : boutons ≥ 44px, jamais de
 * simple `<input type="radio">` nu.
 */
export function ChecklistItemField({ item, answer, onChange }: ChecklistItemFieldProps) {
  const answered = isItemAnswered(answer);

  return (
    <div
      className={cn(
        "flex flex-col gap-2 rounded-lg border p-3",
        answered ? "border-border" : item.is_required ? "border-amber-300 bg-amber-50/60 dark:border-amber-800 dark:bg-amber-950/30" : "border-border",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <label htmlFor={`item-${item.id}`} className="text-sm font-medium text-foreground">
          {item.libelle}
          {item.is_required ? (
            <span aria-hidden="true" className="ml-1 text-destructive">
              *
            </span>
          ) : null}
        </label>
        {item.is_required && !answered ? (
          <span className="shrink-0 text-xs font-medium text-amber-700 dark:text-amber-400">Obligatoire</span>
        ) : null}
      </div>

      {item.response_type === "ok_ko" ? (
        <div className="flex gap-2" role="group" aria-label={item.libelle}>
          <Button
            type="button"
            variant={answer?.valeur_bool === true ? "default" : "outline"}
            className="h-12 flex-1 text-base"
            aria-pressed={answer?.valeur_bool === true}
            onClick={() => onChange({ ...answer, item_template_id: item.id, valeur_bool: true })}
          >
            <Check className="size-4" aria-hidden="true" />
            OK
          </Button>
          <Button
            type="button"
            variant={answer?.valeur_bool === false ? "destructive" : "outline"}
            className="h-12 flex-1 text-base"
            aria-pressed={answer?.valeur_bool === false}
            onClick={() => onChange({ ...answer, item_template_id: item.id, valeur_bool: false })}
          >
            <X className="size-4" aria-hidden="true" />
            Défaut
          </Button>
        </div>
      ) : null}

      {item.response_type === "note_1_5" ? (
        <div className="flex gap-2" role="group" aria-label={item.libelle}>
          {NOTES.map((note) => (
            <Button
              key={note}
              type="button"
              variant={answer?.valeur_note === note ? "default" : "outline"}
              className="h-12 flex-1 text-base"
              aria-pressed={answer?.valeur_note === note}
              onClick={() => onChange({ ...answer, item_template_id: item.id, valeur_note: note })}
            >
              {note}
            </Button>
          ))}
        </div>
      ) : null}

      {item.response_type === "texte" ? (
        <Textarea
          id={`item-${item.id}`}
          className="min-h-20 text-base"
          value={answer?.valeur_texte ?? ""}
          onChange={(e) => onChange({ ...answer, item_template_id: item.id, valeur_texte: e.target.value })}
        />
      ) : null}

      {item.response_type === "numerique" ? (
        <Input
          id={`item-${item.id}`}
          type="number"
          inputMode="decimal"
          className="h-12 max-w-40 text-base"
          value={answer?.valeur_num ?? ""}
          onChange={(e) => {
            const value = e.target.value;
            onChange({ ...answer, item_template_id: item.id, valeur_num: value === "" ? null : Number(value) });
          }}
        />
      ) : null}

      {item.response_type !== "texte" ? (
        <Textarea
          placeholder="Commentaire (optionnel)"
          className="min-h-9 text-sm"
          value={answer?.commentaire ?? ""}
          onChange={(e) => onChange({ ...answer, item_template_id: item.id, commentaire: e.target.value })}
        />
      ) : null}
    </div>
  );
}
