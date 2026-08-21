"use client";

import { useVehicleWorkOrders } from "@/lib/api/hooks/useWorkOrders";
import { WorkOrderCard } from "@/components/domain/WorkOrderCard";
import { LoadingState } from "@/components/ui/loading-state";
import { ErrorState } from "@/components/ui/error-state";
import { EmptyState } from "@/components/ui/empty-state";
import { Wrench } from "lucide-react";

interface WorkOrdersSectionProps {
  vehicleId: string;
  canManage: boolean;
}

/**
 * Liste des ordres de travaux du véhicule (brief J3 « atelier »). Créés en effet de la
 * transition `CONTROLE_EN_COURS → TRAVAUX_REQUIS` (payload `work_orders`, voir
 * `ActionsTransition`) — jamais par un formulaire de création dédié ici, conformément au
 * contrat (« un seul point d'entrée », implementation.md § J3 Backend).
 */
export function WorkOrdersSection({ vehicleId, canManage }: WorkOrdersSectionProps) {
  const workOrders = useVehicleWorkOrders(vehicleId);

  if (workOrders.isLoading) return <LoadingState label="Chargement des ordres de travaux…" />;
  if (workOrders.error) {
    return <ErrorState error={workOrders.error} title="Ordres de travaux indisponibles" onRetry={() => workOrders.refetch()} />;
  }
  const orders = workOrders.data ?? [];
  if (orders.length === 0) {
    return (
      <EmptyState
        icon={<Wrench className="size-8" />}
        title="Aucun ordre de travaux"
        description="Les ordres de travaux apparaissent ici une fois le véhicule passé en « Travaux requis »."
      />
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {orders.map((order) => (
        <WorkOrderCard key={order.id} vehicleId={vehicleId} order={order} canManage={canManage} />
      ))}
    </div>
  );
}
