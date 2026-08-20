import { StateBadge } from "@/components/ui/state-badge";
import { EmptyState } from "@/components/ui/empty-state";
import { formatDateTime } from "@/lib/format/date";
import { ROLE_LABELS, type VehicleStateTransitionRecord } from "@/lib/api/types";

interface HistoriqueEtatsProps {
  history: VehicleStateTransitionRecord[];
}

/**
 * Frise d'historique d'états (plan.md § 6 vague 4). Chaque ligne = une transition tracée
 * en base (`vehicle_state_transition`, § 5.1), jamais reconstruite côté front.
 */
export function HistoriqueEtats({ history }: HistoriqueEtatsProps) {
  if (history.length === 0) {
    return <EmptyState title="Aucun historique" description="Cette fiche n'a pas encore changé d'état." />;
  }

  const sorted = [...history].sort(
    (a, b) => new Date(a.occurred_at).getTime() - new Date(b.occurred_at).getTime(),
  );

  return (
    <ol className="flex flex-col gap-4" aria-label="Historique des états">
      {sorted.map((entry, index) => (
        <li key={entry.id} className="flex gap-3">
          <div className="flex flex-col items-center">
            <span
              aria-hidden="true"
              className="mt-1 size-2.5 shrink-0 rounded-full bg-primary"
            />
            {index < sorted.length - 1 ? (
              <span aria-hidden="true" className="w-px flex-1 bg-border" />
            ) : null}
          </div>
          <div className="flex-1 pb-2">
            <div className="flex flex-wrap items-center gap-2">
              <StateBadge state={entry.to_state} />
              <span className="text-xs text-muted-foreground">{formatDateTime(entry.occurred_at)}</span>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              {entry.actor_role ? ROLE_LABELS[entry.actor_role] : "Système"}
              {entry.reason ? ` — ${entry.reason}` : ""}
            </p>
          </div>
        </li>
      ))}
    </ol>
  );
}
