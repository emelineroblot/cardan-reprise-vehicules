import type { ReactNode } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { LoadingState } from "@/components/ui/loading-state";
import { ErrorState } from "@/components/ui/error-state";
import { EmptyState } from "@/components/ui/empty-state";

interface ChartCardProps {
  title: string;
  /** Identifiant stable de la carte — `data-testid` (e2e) et ancre du titre en heading
   * accessible (`role="heading"`, navigable au lecteur d'écran, `CardTitle` n'en porte pas par
   * défaut : c'est une simple div stylée du design system). */
  id?: string;
  description?: string;
  /** Légende — présente dès 2 séries (skill `dataviz` § marks-and-anatomy.md), rendue au-dessus
   * du graphique, jamais dans un tooltip qui serait la seule façon de connaître l'identité. */
  legend?: ReactNode;
  /** Le graphique lui-même. */
  chart: ReactNode;
  /** Le jumeau accessible WCAG de tout graphique — mêmes données, en tableau. */
  table: ReactNode;
  isLoading?: boolean;
  error?: unknown;
  onRetry?: () => void;
  isEmpty?: boolean;
  emptyDescription?: string;
}

/**
 * Carte de graphique standard du tableau de bord : titre, légende, bascule
 * Graphique/Tableau (le tableau est la vue jumelle accessible — jamais un graphique seul sans
 * son équivalent WCAG, skill `dataviz` § components.md « table-view toggle »), et les trois
 * états limites habituels de l'application (chargement/erreur/vide).
 */
export function ChartCard({
  title,
  id,
  description,
  legend,
  chart,
  table,
  isLoading,
  error,
  onRetry,
  isEmpty,
  emptyDescription,
}: ChartCardProps) {
  return (
    <Card data-testid={id}>
      <CardHeader>
        <CardTitle role="heading" aria-level={2}>
          {title}
        </CardTitle>
        {description ? <CardDescription>{description}</CardDescription> : null}
      </CardHeader>
      <CardContent>
        {isLoading ? <LoadingState label="Chargement des indicateurs…" /> : null}
        {error ? <ErrorState error={error} onRetry={onRetry} title="Indicateur indisponible" /> : null}
        {!isLoading && !error && isEmpty ? (
          <EmptyState title="Aucune donnée pour le moment" description={emptyDescription} />
        ) : null}
        {!isLoading && !error && !isEmpty ? (
          <Tabs defaultValue="graphique">
            <TabsList>
              <TabsTrigger value="graphique">Graphique</TabsTrigger>
              <TabsTrigger value="tableau">Tableau</TabsTrigger>
            </TabsList>
            <TabsContent value="graphique" className="flex flex-col gap-3 pt-4">
              {legend}
              <div className="relative">{chart}</div>
            </TabsContent>
            <TabsContent value="tableau" className="pt-4">
              {table}
            </TabsContent>
          </Tabs>
        ) : null}
      </CardContent>
    </Card>
  );
}

/** Puce de légende — trait de la couleur de série, jamais un carré plein à cette densité
 * (skill `dataviz` § marks-and-anatomy.md « line keys, not boxes » — appliqué aussi aux barres
 * ici pour rester cohérent à l'échelle d'une légende). */
export function LegendSwatch({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
      <span aria-hidden="true" className="h-0.5 w-3.5 rounded-full" style={{ backgroundColor: color }} />
      {label}
    </span>
  );
}

export function ChartLegend({ items }: { items: { color: string; label: string }[] }) {
  if (items.length < 2) return null;
  return (
    <div role="list" aria-label="Légende" className="flex flex-wrap gap-x-4 gap-y-1.5">
      {items.map((item) => (
        <span role="listitem" key={item.label}>
          <LegendSwatch color={item.color} label={item.label} />
        </span>
      ))}
    </div>
  );
}
