import { Loader2 } from "lucide-react";

interface LoadingStateProps {
  label?: string;
  className?: string;
}

/** État de chargement générique — annoncé aux lecteurs d'écran via `aria-live`. */
export function LoadingState({ label = "Chargement en cours…", className }: LoadingStateProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={`flex flex-col items-center justify-center gap-2 py-12 text-sm text-muted-foreground ${className ?? ""}`}
    >
      <Loader2 className="size-6 animate-spin" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}
