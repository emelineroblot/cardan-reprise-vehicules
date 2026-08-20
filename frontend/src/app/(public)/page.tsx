import Link from "next/link";
import { CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { HealthPrewarm } from "@/components/domain/HealthPrewarm";

const POINTS = [
  "Fiche d'achat société + véhicule, avec enrichissement automatique par SIRET",
  "Détection de doublons — exacte et approximative — avec écran d'arbitrage",
  "Suivi filtrable de chaque véhicule, de la proposition à la validation d'achat",
  "Cloisonnement par rôle : opératrice, chauffeur, administrateur, atelier",
];

export default function HomePage() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center px-4 py-16">
      {/* Préchauffe le backend/la base pendant la lecture de la page (plan.md § 3.8-5). */}
      <HealthPrewarm />
      <div className="mx-auto flex max-w-2xl flex-col items-center gap-6 text-center">
        <span className="rounded-full border border-border px-3 py-1 text-xs font-medium text-muted-foreground">
          Application de démonstration — Reprise Atlantique
        </span>
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
          Cardan — piloter l&apos;achat de véhicules d&apos;occasion,
          <br className="hidden sm:block" /> sans tableur ni coups de fil perdus
        </h1>
        <p className="max-w-xl text-muted-foreground">
          Une démo cliquable : de la proposition d&apos;un véhicule par une flotte
          professionnelle jusqu&apos;à la validation d&apos;achat, avec traçabilité complète
          et détection automatique des doublons.
        </p>

        <ul className="grid gap-2 text-left text-sm text-muted-foreground sm:grid-cols-2">
          {POINTS.map((point) => (
            <li key={point} className="flex items-start gap-2">
              <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-600" aria-hidden="true" />
              <span>{point}</span>
            </li>
          ))}
        </ul>

        <Button asChild size="lg" className="mt-2">
          <Link href="/login">Voir la démo</Link>
        </Button>

        <p className="text-xs text-muted-foreground">
          Données entièrement fictives, générées et réinitialisées chaque nuit. Aucune donnée
          personnelle réelle.
        </p>
      </div>
    </div>
  );
}
