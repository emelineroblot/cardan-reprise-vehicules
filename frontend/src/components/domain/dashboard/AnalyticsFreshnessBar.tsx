"use client";

import { RefreshCw, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAnalyticsStatus, useRefreshAnalytics } from "@/lib/api/hooks/useAnalytics";
import { formatRelative } from "@/lib/format/date";

/**
 * Fraîcheur des indicateurs (plan.md § 3.7-5 : « la fraîcheur devient un objet affiché dans
 * l'UI »). `refreshed_at` le plus ANCIEN parmi les marts fait foi — c'est celui qui borne la
 * confiance qu'on peut avoir dans l'écran le moins à jour, pas le plus optimiste. Un mart en
 * échec (`status: "echec"`) reste affiché tel quel, jamais masqué.
 */
export function AnalyticsFreshnessBar() {
  const status = useAnalyticsStatus();
  const refresh = useRefreshAnalytics();

  const marts = status.data?.marts ?? [];
  const oldest = marts.length > 0 ? marts.reduce((a, b) => (a.refreshed_at < b.refreshed_at ? a : b)) : null;
  const hasFailure = marts.some((m) => m.status !== "succes");

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-card px-4 py-3">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        {hasFailure ? <TriangleAlert className="size-4 text-destructive" aria-hidden="true" /> : null}
        {oldest ? (
          <span>
            Indicateurs à jour {formatRelative(oldest.refreshed_at)}
            {hasFailure ? " — au moins un indicateur n'a pas pu être rafraîchi." : ""}
          </span>
        ) : (
          <span>Fraîcheur des indicateurs inconnue.</span>
        )}
      </div>
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={refresh.isPending}
        onClick={() => refresh.mutate()}
      >
        <RefreshCw className={refresh.isPending ? "size-4 animate-spin" : "size-4"} aria-hidden="true" />
        {refresh.isPending ? "Actualisation…" : "Actualiser les indicateurs"}
      </Button>
    </div>
  );
}
