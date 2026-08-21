"use client";

import { Suspense, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Search } from "lucide-react";
import { RoleGuard } from "@/components/domain/RoleGuard";
import { DataTable, type DataTableColumn, type DataTableSort } from "@/components/ui/data-table";
import { StateBadge } from "@/components/ui/state-badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { LoadingState } from "@/components/ui/loading-state";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useVehicles, type VehiclesFilters } from "@/lib/api/hooks/useVehicles";
import { useAuth } from "@/lib/auth/AuthProvider";
import { hasRole } from "@/lib/auth/roles";
import { formatDate, formatImmatriculation, formatMoneyCents } from "@/lib/format";
import {
  VEHICLE_STATE_LABELS,
  VEHICLE_STATES,
  type VehicleListItem,
  type VehicleState,
} from "@/lib/api/types";

const LIMIT = 25;
const SORTABLE_KEYS = new Set(["date_proposition", "reference", "state", "kilometrage"]);

export default function VehiculesPage() {
  return (
    <RoleGuard allowed={["operatrice", "chauffeur", "administrateur", "atelier"]}>
      <Suspense fallback={<LoadingState label="Chargement du suivi…" />}>
        <VehiculesListPage />
      </Suspense>
    </RoleGuard>
  );
}

function VehiculesListPage() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { user } = useAuth();
  // Même garde que la fiche détail (`vehicules/[id]/page.tsx`) : prix négocié réservé à
  // opératrice/administrateur. Absente de la liste jusqu'ici — le backend renvoie désormais
  // `null` pour le chauffeur (cloisonnement financier), mais la colonne restait affichée avec un
  // « — » sur toutes les lignes : trompeur (donnée qui semble manquante plutôt qu'interdite) et
  // incohérent avec la fiche détail qui masque la section entière.
  const canSeeFinances = hasRole(user, ["operatrice", "administrateur"]);

  const filters = useMemo<VehiclesFilters>(() => {
    const state = searchParams.get("state");
    return {
      state: state ? (state as VehicleState) : undefined,
      marque: searchParams.get("marque") ?? undefined,
      date_proposition_from: searchParams.get("date_proposition_from") ?? undefined,
      date_proposition_to: searchParams.get("date_proposition_to") ?? undefined,
      q: searchParams.get("q") ?? undefined,
      sort: searchParams.get("sort") ?? "-date_proposition",
      limit: LIMIT,
      offset: Number(searchParams.get("offset") ?? 0),
    };
  }, [searchParams]);

  const [qDraft, setQDraft] = useState(filters.q ?? "");

  const { data, isLoading, error, refetch, isFetching } = useVehicles(filters);

  const updateParams = (patch: Record<string, string | undefined>, resetOffset = true) => {
    const next = new URLSearchParams(searchParams.toString());
    Object.entries(patch).forEach(([key, value]) => {
      if (value === undefined || value === "") {
        next.delete(key);
      } else {
        next.set(key, value);
      }
    });
    if (resetOffset) next.delete("offset");
    router.push(`${pathname}?${next.toString()}`);
  };

  const sort: DataTableSort | null = filters.sort
    ? {
        key: filters.sort.replace(/^-/, ""),
        direction: filters.sort.startsWith("-") ? "desc" : "asc",
      }
    : null;

  const handleSortChange = (key: string) => {
    if (!SORTABLE_KEYS.has(key)) return;
    const next = sort?.key === key && sort.direction === "asc" ? `-${key}` : key;
    updateParams({ sort: next });
  };

  const columns: DataTableColumn<VehicleListItem>[] = [
    {
      key: "reference",
      header: "Référence",
      sortable: true,
      cell: (v) => (
        <Link href={`/vehicules/${v.id}`} className="font-medium text-primary hover:underline">
          {v.reference}
        </Link>
      ),
    },
    {
      key: "state",
      header: "État",
      sortable: true,
      cell: (v) => <StateBadge state={v.state} />,
    },
    {
      key: "societe",
      header: "Société",
      cell: (v) => v.company?.denomination ?? "—",
    },
    {
      key: "vehicule",
      header: "Véhicule",
      cell: (v) => `${v.marque} ${v.modele}`,
    },
    {
      key: "immatriculation",
      header: "Immat.",
      cell: (v) => formatImmatriculation(v.immatriculation),
    },
    {
      key: "date_proposition",
      header: "Proposé le",
      sortable: true,
      cell: (v) => formatDate(v.date_proposition),
    },
    {
      key: "kilometrage",
      header: "Kilométrage",
      sortable: true,
      className: "text-right tabular-nums",
      headerClassName: "text-right",
      cell: (v) => (v.kilometrage != null ? `${v.kilometrage.toLocaleString("fr-FR")} km` : "—"),
    },
    ...(canSeeFinances
      ? [
          {
            key: "prix_achat_negocie_cents",
            header: "Prix négocié",
            className: "text-right tabular-nums",
            headerClassName: "text-right",
            cell: (v) => formatMoneyCents(v.prix_achat_negocie_cents),
          } satisfies DataTableColumn<VehicleListItem>,
        ]
      : []),
  ];

  const total = data?.total ?? 0;
  const offset = filters.offset ?? 0;
  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + LIMIT, total);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Suivi des véhicules</h1>
          <p className="text-sm text-muted-foreground">
            {total > 0 ? `${total} résultat${total > 1 ? "s" : ""}` : "Aucun résultat pour ces filtres."}
            {isFetching ? " · actualisation…" : ""}
          </p>
        </div>
        <Button asChild>
          <Link href="/fiches/nouvelle">Nouvelle fiche</Link>
        </Button>
      </div>

      <form
        className="grid gap-3 rounded-lg border border-border p-4 sm:grid-cols-2 lg:grid-cols-5"
        onSubmit={(e) => {
          e.preventDefault();
          updateParams({ q: qDraft || undefined });
        }}
      >
        <div>
          <Label htmlFor="filter-state">État</Label>
          <Select
            value={filters.state ?? "__all__"}
            onValueChange={(value) => updateParams({ state: value === "__all__" ? undefined : value })}
          >
            <SelectTrigger id="filter-state" className="mt-1.5 w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">Tous les états</SelectItem>
              {VEHICLE_STATES.map((state) => (
                <SelectItem key={state} value={state}>
                  {VEHICLE_STATE_LABELS[state]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div>
          <Label htmlFor="filter-marque">Marque</Label>
          <Input
            id="filter-marque"
            className="mt-1.5"
            defaultValue={filters.marque ?? ""}
            onBlur={(e) => updateParams({ marque: e.target.value || undefined })}
          />
        </div>

        <div>
          <Label htmlFor="filter-from">Proposé depuis le</Label>
          <Input
            id="filter-from"
            type="date"
            className="mt-1.5"
            defaultValue={filters.date_proposition_from ?? ""}
            onChange={(e) => updateParams({ date_proposition_from: e.target.value || undefined })}
          />
        </div>

        <div>
          <Label htmlFor="filter-to">Jusqu&apos;au</Label>
          <Input
            id="filter-to"
            type="date"
            className="mt-1.5"
            defaultValue={filters.date_proposition_to ?? ""}
            onChange={(e) => updateParams({ date_proposition_to: e.target.value || undefined })}
          />
        </div>

        <div>
          <Label htmlFor="filter-q">Recherche libre</Label>
          <div className="mt-1.5 flex gap-2">
            <Input
              id="filter-q"
              placeholder="Référence, VIN, immat., modèle, société…"
              value={qDraft}
              onChange={(e) => setQDraft(e.target.value)}
            />
            <Button type="submit" size="icon" variant="outline" aria-label="Rechercher">
              <Search className="size-4" aria-hidden="true" />
            </Button>
          </div>
        </div>

        {filters.state || filters.marque || filters.date_proposition_from || filters.date_proposition_to || filters.q ? (
          <div className="lg:col-span-5">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => {
                setQDraft("");
                router.push(pathname);
              }}
            >
              Réinitialiser les filtres
            </Button>
          </div>
        ) : null}
      </form>

      <DataTable
        columns={columns}
        rows={data?.items ?? []}
        rowKey={(v) => v.id}
        caption="Liste des véhicules suivis"
        isLoading={isLoading}
        error={error}
        onRetry={() => refetch()}
        emptyTitle="Aucun véhicule ne correspond à ces filtres"
        emptyDescription="Ajustez les filtres ou créez une nouvelle fiche d'achat."
        sort={sort}
        onSortChange={handleSortChange}
        onRowClick={(v) => router.push(`/vehicules/${v.id}`)}
      />

      {total > 0 ? (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>
            {from}–{to} sur {total}
          </span>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={offset === 0}
              onClick={() => updateParams({ offset: String(Math.max(0, offset - LIMIT)) }, false)}
            >
              Précédent
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={offset + LIMIT >= total}
              onClick={() => updateParams({ offset: String(offset + LIMIT) }, false)}
            >
              Suivant
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
