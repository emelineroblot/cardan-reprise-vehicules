"use client";

import type { ReactNode } from "react";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { LoadingState } from "@/components/ui/loading-state";
import { ErrorState } from "@/components/ui/error-state";
import { EmptyState } from "@/components/ui/empty-state";

export interface DataTableColumn<T> {
  key: string;
  header: string;
  sortable?: boolean;
  cell: (row: T) => ReactNode;
  className?: string;
  headerClassName?: string;
}

export interface DataTableSort {
  key: string;
  direction: "asc" | "desc";
}

interface DataTableProps<T> {
  columns: DataTableColumn<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  caption?: string;
  isLoading?: boolean;
  error?: unknown;
  onRetry?: () => void;
  emptyTitle?: string;
  emptyDescription?: string;
  sort?: DataTableSort | null;
  onSortChange?: (key: string) => void;
  onRowClick?: (row: T) => void;
}

/** Table de données générique : tri, chargement, vide et erreur gérés uniformément. */
export function DataTable<T>({
  columns,
  rows,
  rowKey,
  caption,
  isLoading,
  error,
  onRetry,
  emptyTitle = "Aucun résultat",
  emptyDescription,
  sort,
  onSortChange,
  onRowClick,
}: DataTableProps<T>) {
  if (isLoading) {
    return <LoadingState label="Chargement des résultats…" />;
  }

  if (error) {
    return <ErrorState error={error} title="Impossible de charger les résultats" onRetry={onRetry} />;
  }

  if (rows.length === 0) {
    return <EmptyState title={emptyTitle} description={emptyDescription} />;
  }

  return (
    <Table>
      {caption ? <TableCaption className="sr-only">{caption}</TableCaption> : null}
      <TableHeader>
        <TableRow>
          {columns.map((column) => (
            <TableHead key={column.key} className={column.headerClassName}>
              {column.sortable ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="-ml-2 h-auto gap-1 px-2 py-1 font-medium"
                  onClick={() => onSortChange?.(column.key)}
                  aria-label={`Trier par ${column.header}`}
                >
                  {column.header}
                  <SortIcon active={sort?.key === column.key} direction={sort?.direction} />
                </Button>
              ) : (
                column.header
              )}
            </TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row) => (
          <TableRow
            key={rowKey(row)}
            className={onRowClick ? "cursor-pointer" : undefined}
            tabIndex={onRowClick ? 0 : undefined}
            role={onRowClick ? "button" : undefined}
            onClick={onRowClick ? () => onRowClick(row) : undefined}
            onKeyDown={
              onRowClick
                ? (event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onRowClick(row);
                    }
                  }
                : undefined
            }
          >
            {columns.map((column) => (
              <TableCell key={column.key} className={column.className}>
                {column.cell(row)}
              </TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function SortIcon({ active, direction }: { active?: boolean; direction?: "asc" | "desc" }) {
  if (!active) return <ArrowUpDown className="size-3.5 text-muted-foreground" aria-hidden="true" />;
  return direction === "asc" ? (
    <ArrowUp className="size-3.5" aria-hidden="true" />
  ) : (
    <ArrowDown className="size-3.5" aria-hidden="true" />
  );
}
