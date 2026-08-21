import type { ReactNode } from "react";
import Link from "next/link";
import { ChevronRight } from "lucide-react";

export interface Crumb {
  label: string;
  href?: string;
}

interface PageHeaderProps {
  title: string;
  description?: string;
  /** Fil d'Ariane affiché sous le titre (inspiration DashboardKit § breadcrumb) — « Accueil »
   * est systématique et implicite, ne pas le repasser dans `breadcrumb`. */
  breadcrumb: Crumb[];
  actions?: ReactNode;
}

/**
 * En-tête de page commun : titre, description, fil d'Ariane. Remplace les blocs `<h1>` ad hoc
 * dupliqués sur chaque écran — un seul endroit pour la hiérarchie de titre et la navigation
 * de repérage.
 */
export function PageHeader({ title, description, breadcrumb, actions }: PageHeaderProps) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">{title}</h1>
        {description ? <p className="mt-1 text-sm text-muted-foreground">{description}</p> : null}
        <nav aria-label="Fil d'Ariane" className="mt-2 flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
          <Link href="/vehicules" className="hover:text-foreground hover:underline">
            Accueil
          </Link>
          {breadcrumb.map((crumb, index) => {
            const isLast = index === breadcrumb.length - 1;
            return (
              <span key={crumb.label} className="flex items-center gap-1">
                <ChevronRight className="size-3" aria-hidden="true" />
                {crumb.href && !isLast ? (
                  <Link href={crumb.href} className="hover:text-foreground hover:underline">
                    {crumb.label}
                  </Link>
                ) : (
                  <span aria-current={isLast ? "page" : undefined} className={isLast ? "text-foreground" : undefined}>
                    {crumb.label}
                  </span>
                )}
              </span>
            );
          })}
        </nav>
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </div>
  );
}
