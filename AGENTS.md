# AGENTS.md — Cardan

Contexte portable pour tout agent de code travaillant sur ce dépôt.
Le détail projet (motivations, périmètre figé, jalons) vit dans `CLAUDE.md` — **une seule source
de vérité, ce fichier n'en est que le résumé portable.**

## Le projet en deux lignes

Outil interne de gestion d'achat de véhicules d'occasion rachetés à des flottes professionnelles.
Application de **démonstration** : toutes les données sont fictives et générées.

## Stack

| Couche | Technologie |
|---|---|
| Backend | Python |
| Frontend | Next.js — module terrain en PWA installable |
| Base de données | PostgreSQL |
| Analytique | Modèles séparés (staging → marts), lus par le dashboard |

## Stratégie de branches

**Pas de branche `develop` sur ce projet.** `main` unique + `feature/nom-court` créées depuis `main`
et mergées dans `main` après validation. On ne développe jamais directement sur `main`.

## Garde-fous non négociables

- **Dépôt public** : aucun secret, aucune clé, aucune donnée réelle, aucune référence client.
- **Données de démonstration fictives et générées** uniquement.
- **API INSEE Sirene** est la seule intégration externe, et elle doit toujours avoir un fallback
  en saisie manuelle : la démo ne dépend jamais de la disponibilité d'un tiers.
- **Périmètre figé** — hors périmètre définitif : application native, multi-tenant, module de
  revente ou de facturation, orchestration Airflow.
- Secrets via `.env` (gitignoré), jamais en dur.

## Commandes

_À compléter par l'architecte au premier jalon (build, test, lint, migrations, seed)._

## Conventions par type de fichier

Les règles ciblées par stack vivent dans `.claude/instructions/*.instructions.md`
(`python-backend`, `nextjs-frontend`) et s'appliquent selon le glob `applyTo` du fichier touché.
