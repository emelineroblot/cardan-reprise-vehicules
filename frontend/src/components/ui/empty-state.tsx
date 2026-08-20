import type { ReactNode } from "react";
import { PackageSearch } from "lucide-react";

interface EmptyStateProps {
  title: string;
  description?: string;
  icon?: ReactNode;
  action?: ReactNode;
  className?: string;
}

/** État vide générique (aucune donnée, aucun résultat de filtre…). */
export function EmptyState({ title, description, icon, action, className }: EmptyStateProps) {
  return (
    <div
      className={`flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border py-12 px-6 text-center ${className ?? ""}`}
    >
      <div className="text-muted-foreground" aria-hidden="true">
        {icon ?? <PackageSearch className="size-8" />}
      </div>
      <p className="font-medium text-foreground">{title}</p>
      {description ? <p className="max-w-sm text-sm text-muted-foreground">{description}</p> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}
