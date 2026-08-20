import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";

interface ErrorStateProps {
  error?: unknown;
  title?: string;
  onRetry?: () => void;
  className?: string;
}

/** État d'erreur générique — traduit une `ApiError` en message lisible sans exposer le code brut. */
export function ErrorState({ error, title, onRetry, className }: ErrorStateProps) {
  const message = describeError(error);
  return (
    <div
      role="alert"
      className={`flex flex-col items-center justify-center gap-3 rounded-lg border border-destructive/30 bg-destructive/5 py-10 px-6 text-center ${className ?? ""}`}
    >
      <AlertTriangle className="size-7 text-destructive" aria-hidden="true" />
      <p className="font-medium text-foreground">{title ?? "Une erreur est survenue"}</p>
      <p className="max-w-sm text-sm text-muted-foreground">{message}</p>
      {onRetry ? (
        <Button type="button" variant="outline" size="sm" onClick={onRetry}>
          Réessayer
        </Button>
      ) : null}
    </div>
  );
}

export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message || "Le serveur a renvoyé une erreur inattendue.";
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Erreur inattendue. Merci de réessayer.";
}
