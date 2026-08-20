# Cardan — outil interne de gestion d'achat de véhicules d'occasion

Application de **démonstration** pour le portfolio d'applications métier d'Emeline Roblot.
Elle illustre le passage d'un process PME entièrement manuel (Excel + téléphone) à un outil
interne piloté, avec calcul automatique de la marge.

Société fictive de démonstration : **Reprise Atlantique** — rachat de véhicules à des flottes
professionnelles (taxis, ambulances, transport), ~25 véhicules/mois.

Brief complet : `contexte/brief-app-a-gestion-vehicules.md` (non versionné).

## Stratégie de branches — spécifique à ce projet

> ⚠️ **Ce projet déroge à la convention globale : il n'y a pas de branche `develop`.**

- **`main`** — branche unique d'intégration et de production. Elle correspond toujours à l'état
  déployé de la démo publique.
- **`feature/nom-court`** — une fonctionnalité ou un jalon = une branche, créée depuis `main`
  et mergée dans `main` une fois validée.
- On ne développe jamais directement sur `main`.

Motif de la dérogation : projet solo, sans environnement de recette distinct de la démo publique.
Une branche d'intégration intermédiaire n'apporterait rien et ralentirait les jalons.

Branches prévues :

```
main
├── feature/socle-saisie        (J1 — modèle de données, auth 3 rôles, fiche d'achat, dédoublonnage)
├── feature/pwa-terrain         (J2 — mission chauffeur, checklist, photos guidées, offline)
└── feature/pilotage-marge      (J3 — atelier, Kanban, couche analytique, dashboard)
```

## Stack

- **Backend** : Python — FastAPI + SQLAlchemy 2 (style typé) + Alembic, PostgreSQL 16 en local
  via `docker-compose.yml` (port 5433). Auth native argon2id + JWT en cookie httpOnly (pas de
  fournisseur d'identité tiers). Trois migrations à ce stade : `0001_socle` (schéma complet des
  3 jalons), `0002_analytics_refresh_log` et `0003_inspection_mission_unique` (contrainte
  `UNIQUE(mission_id)` sur `inspection` — une seule inspection par mission, corrige un doublon
  possible au rechargement de l'écran de contrôle après soumission).
- **Frontend** : Next.js — module terrain en PWA installable (caméra, stockage local, web push)
- **Base de données** : PostgreSQL managé
- **Stockage photos (J2)** : abstraction `PhotoStorage` (`backend/app/services/storage/`) —
  backend **disque local** actif aujourd'hui (`local.py`, aucune clé requise). Le disque local
  n'est pas utilisable en serverless : un fournisseur de stockage objet devra être choisi **au
  déploiement**, en implémentant une nouvelle classe et en la branchant dans `service.py`
  (aucun autre fichier à toucher). Le fournisseur n'est pas arrêté — voir
  `docs/wiki/architecture.md` § Stockage des photos. Lecture via
  `GET /api/v1/photos/file/{bucket}/{key}`, authentifiée par cookie et scopée comme les
  véhicules (`scope_vehicles`).
- **Notifications (J2)** : persistées en base (`notification`, chemin nominal, aucune clé
  requise) ; web push réel optionnel, activé uniquement si `VAPID_PUBLIC_KEY` et
  `VAPID_PRIVATE_KEY` sont toutes deux configurées (`backend/app/services/push.py`). Son
  absence ne dégrade jamais le parcours.
- **Couche analytique** : schéma PostgreSQL dédié `analytics` (vues `stg_*` + vues matérialisées
  `mart_*`), hors Alembic (sauf `analytics.refresh_log`, seule table réelle), reconstruit par
  `backend/app/analytics/runner.py` (`build`/`refresh`) depuis `manifest.yml`. Le dashboard lit
  les marts, jamais des calculs à la volée dans l'UI.
- **Hébergement** : Vercel + Postgres managé, offres gratuites, hébergement UE

## Tâche planifiée (cron)

- `backend/vercel.json` déclare un cron **quotidien** `0 3 * * *` sur
  `POST /api/v1/admin/demo-reset` : `TRUNCATE` des tables opérationnelles (liste en dur) +
  reseed (`reference` puis `demo`) + rafraîchissement des marts analytics. Authentifié par
  `Authorization: Bearer $CRON_SECRET`, comparé en temps constant côté backend.

## Règles propres au projet

- **Le dépôt est public.** Aucun secret, aucune donnée réelle, aucune référence client.
  Toutes les données de démonstration sont fictives et générées.
- **Intégration externe unique** : API INSEE Sirene (enrichissement société par SIRET), via
  `recherche-entreprises.api.gouv.fr` par défaut (sans clé) — `INSEE_API_KEY` optionnelle
  active le provider Sirene officiel. Un fallback en saisie manuelle est obligatoire — la démo
  ne doit jamais dépendre de la disponibilité d'un tiers.
- **Périmètre figé** : la liste `Won't have` du brief ne se rouvre pas en cours de jalon.
  Notamment : pas d'application native, pas de multi-tenant, pas d'orchestration Airflow.
- Les données de démo sont réinitialisées chaque nuit (cron ci-dessus).
