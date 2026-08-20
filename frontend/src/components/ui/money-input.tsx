"use client";

import { useId, useRef, useState, type ComponentProps } from "react";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { centsToEditableString, parseEurosToCents } from "@/lib/format/money";

interface MoneyInputProps
  extends Omit<ComponentProps<typeof Input>, "value" | "onChange" | "type"> {
  /** Montant en centimes entiers — jamais de flottant sur de l'argent (plan.md § 3.5). */
  value: number | null | undefined;
  onValueChange: (cents: number | null) => void;
  invalid?: boolean;
}

/** Champ de saisie monétaire : affiche des euros, produit des centimes entiers. */
export function MoneyInput({ value, onValueChange, invalid, id, ...props }: MoneyInputProps) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const normalizedValue = value ?? null;
  const [draft, setDraft] = useState(() => centsToEditableString(normalizedValue));
  const lastEmitted = useRef<number | null>(normalizedValue);

  // Resynchronise l'affichage seulement si `value` a changé pour une raison EXTERNE
  // (reset de formulaire, chargement de données…), jamais suite à notre propre onChange —
  // ajustement pendant le rendu plutôt qu'un effet (évite le reformatage sous les doigts
  // de l'utilisatrice et la règle react-hooks/set-state-in-effect).
  if (normalizedValue !== lastEmitted.current) {
    lastEmitted.current = normalizedValue;
    setDraft(centsToEditableString(normalizedValue));
  }

  return (
    <div className="relative">
      <Input
        id={inputId}
        inputMode="decimal"
        aria-invalid={invalid || undefined}
        className={cn("pr-8", props.className)}
        value={draft}
        onChange={(event) => {
          const raw = event.target.value;
          setDraft(raw);
          const cents = parseEurosToCents(raw);
          lastEmitted.current = cents;
          onValueChange(cents);
        }}
        onBlur={() => setDraft(centsToEditableString(lastEmitted.current))}
        {...props}
      />
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-y-0 right-2.5 flex items-center text-sm text-muted-foreground"
      >
        €
      </span>
    </div>
  );
}
