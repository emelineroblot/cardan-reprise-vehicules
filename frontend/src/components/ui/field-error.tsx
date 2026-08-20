interface FieldErrorProps {
  message?: string;
  id?: string;
}

/** Message d'erreur de champ de formulaire — à référencer via `aria-describedby`. */
export function FieldError({ message, id }: FieldErrorProps) {
  if (!message) return null;
  return (
    <p id={id} role="alert" className="mt-1 text-sm text-destructive">
      {message}
    </p>
  );
}
