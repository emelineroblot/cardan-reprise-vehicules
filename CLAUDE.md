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
├── feature/pilotage-marge      (J3 — atelier, Kanban, couche analytique, dashboard)
└── feature/deploiement-supabase (bascule stockage Supabase Storage, config Vercel/Supabase)
```

## Stack

- **Backend** : Python — FastAPI + SQLAlchemy 2 (style typé) + Alembic, PostgreSQL 16 en local
  via `docker-compose.yml` (port 5433). Auth native argon2id + JWT en cookie httpOnly (pas de
  fournisseur d'identité tiers). Trois migrations à ce stade : `0001_socle` (schéma complet des
  3 jalons), `0002_analytics_refresh_log` et `0003_inspection_mission_unique` (contrainte
  `UNIQUE(mission_id)` sur `inspection` — une seule inspection par mission, corrige un doublon
  possible au rechargement de l'écran de contrôle après soumission).
- **Frontend** : Next.js — module terrain en PWA installable (caméra, stockage local, web push)
- **Base de données** : Supabase Postgres managé — connexion **Transaction pooler** (Supavisor,
  port 6543) pour l'API, **Session pooler** (port 5432) pour les migrations Alembic et
  `REFRESH MATERIALIZED VIEW ... CONCURRENTLY` (`DATABASE_URL`/`DATABASE_URL_DIRECT`, voir
  `docs/wiki/deploiement.md`). La « Direct connection » (`db.<ref>.supabase.co`) que la
  documentation Supabase met en avant n'est **pas** utilisable ici : elle ne publie qu'un
  enregistrement AAAA (IPv6) et échoue depuis tout réseau sans IPv6.
- **Stockage photos** : abstraction `PhotoStorage` (`backend/app/services/storage/`), backend
  choisi par **configuration**, jamais par une variable dédiée — `Settings.
  supabase_storage_configured` (`app/core/config.py`) décide : `SupabaseStorage`
  (`supabase.py`, appelle directement l'API REST Supabase Storage via `httpx`) si
  `SUPABASE_URL`/`SUPABASE_SERVICE_KEY` sont **toutes deux** renseignées, sinon `LocalDiskStorage`
  (`local.py`, aucune clé requise) — un clone du dépôt sans compte Supabase n'est jamais dégradé.
  La route backend réelle est `GET /api/v1/photos/file/{bucket}/{key}` (authentifiée par cookie,
  scopée comme les véhicules via `scope_vehicles`), et `PhotoRead.url` renvoyée au front porte
  toujours le préfixe **navigateur** `/api/backend/v1/photos/file/{bucket}/{key}` — **y compris
  avec le backend Supabase** (`SupabaseStorage.read_url` renvoie la même route que
  `LocalDiskStorage`, jamais une URL signée Supabase directe, pour conserver le scoping par
  véhicule) — le navigateur n'appelle jamais le backend en direct (rewrite Next, § Déploiement)
  et n'a jamais à reconstruire ce préfixe lui-même. `PhotoStorage` porte aussi
  `delete_prefix`/`list_top_level` (purge sélective du reset nocturne), implémentées par les deux
  backends — `SupabaseStorage.delete_prefix` liste récursivement puis supprime par lot (l'API
  Supabase n'a pas d'équivalent serveur d'un `rm -r` par préfixe). Deux comportements de l'API
  réelle absents de sa documentation publique, découverts en testant contre un vrai projet : voir
  `docs/wiki/pieges-projet.md` § Déploiement.
- **Notifications (J2)** : persistées en base (`notification`, chemin nominal, aucune clé
  requise) ; web push réel optionnel, activé uniquement si `VAPID_PUBLIC_KEY` et
  `VAPID_PRIVATE_KEY` sont toutes deux configurées (`backend/app/services/push.py`). Son
  absence ne dégrade jamais le parcours.
- **Atelier (J3)** : rôle unique `atelier`, `work_order`/`work_order_line`. La création d'un
  `work_order` est un effet de `POST /vehicles/{id}/transitions` vers `TRAVAUX_REQUIS` (payload
  `work_orders: [{type, description, montant_estime_cents?}]`, au moins un élément) — jamais un
  endpoint de création dédié, même principe que `mission` en J2. `work_order.state`
  (`demande|en_cours|termine|annule`) est un **mini-automate séparé** de celui du véhicule
  (`backend/app/services/work_orders.py`), piloté par `POST /work-orders/{id}/state` : un ordre
  ne peut atteindre `termine`/`annule` que s'il porte déjà au moins une ligne de coût
  (`POST /work-orders/{id}/lines`). La transition véhicule `TRAVAUX_EN_COURS -> TRAVAUX_TERMINES`
  vérifie, elle, que **tous** les ordres du véhicule sont clos avec une ligne de coût
  (`app/services/vehicles.py::build_transition_context`). Photos avant/après travaux : mêmes
  endpoints que J2 (`POST /vehicles/{id}/photos`), phase `avant_travaux`/`apres_travaux` liée à
  `work_order_id` au lieu de `inspection_id`.
- **Coûts hors atelier (J3)** : `vehicle_cost` (transport, carburant, administratif, remise en
  état externe), `POST/GET /vehicles/{id}/costs`, écriture réservée à `administrateur`.
- **Pipeline Kanban (J3)** : `GET /vehicles/pipeline-counts` (administrateur) — comptage par état
  **opérationnel et live** (lecture directe de `vehicle`, jamais un mart), pour l'écran
  interactif de manipulation du parc. Distinct de `GET /analytics/pipeline-etat`, qui sert le
  dashboard à la fraîcheur du dernier `refresh`.
- **Couche analytique** : schéma PostgreSQL dédié `analytics` (vues `stg_*` + vues matérialisées
  `mart_*`), hors Alembic (sauf `analytics.refresh_log`, seule table réelle), reconstruit par
  `backend/app/analytics/runner.py` (`build`/`refresh`) depuis `manifest.yml`. Le dashboard lit
  les marts, jamais des calculs à la volée dans l'UI. J3 ajoute 4 vues de staging
  (`stg_transitions`, `stg_missions`, `stg_travaux`, `stg_couts`) et 6 marts —
  `mart_vehicule_marge` (marge par véhicule, `marge_cents`/`marge_pct` toujours `NULL`, jamais
  `0`, quand `has_marge = false`), `mart_cycle_temps` (délai de cycle par étape), `mart_pipeline_
  etat`, `mart_refus` (`ANNULE` exclu du calcul, `REFUSE` seul y entre), `mart_travaux` (coût
  moyen réel, uniquement sur les ordres clos) et `mart_kpi_global` (tuiles du dashboard, dépend
  des 4 marts précédents — ordre de déclaration significatif dans `manifest.yml`). Endpoints de
  lecture : `GET /analytics/{marge,cycle-temps,pipeline-etat,refus,travaux,kpi-global}`, réservés
  à `administrateur`.
- **Hébergement** : Vercel (deux projets) + Supabase (Postgres managé + Storage), offres
  gratuites, hébergement UE. Marche à suivre complète, valeurs à récupérer côté Supabase et
  variables à poser côté Vercel : `docs/wiki/deploiement.md`.

## Tâche planifiée (cron)

- `backend/vercel.json` déclare un cron **quotidien** `0 3 * * *` sur
  `POST /api/v1/admin/demo-reset` : `TRUNCATE` des tables opérationnelles (liste en dur) +
  reseed (`reference` puis `demo`) + rafraîchissement des marts analytics. Authentifié par
  `Authorization: Bearer $CRON_SECRET`, comparé en temps constant côté backend. `vercel.json`
  déclare aussi `"functions": {"api/index.py": {"maxDuration": 300}}` — 300 s est le plafond
  du plan Hobby avec Fluid Compute (« enabled by default » selon la documentation Vercel
  consultée le 2026-08-21), **à vérifier sur le projet réel** avant le premier déploiement
  (Project Settings → Functions → Fluid Compute) : le chiffre historiquement associé au plan
  gratuit (60 s) est celui du modèle serverless classique, pré-Fluid Compute. Mesuré contre le
  vrai Supabase Storage : le reset écrit 583 photos, ≈ 101 s en séquentiel (tel qu'implémenté
  aujourd'hui) — tient sous 300 s, dépasserait 60 s. Détail chiffré et options non tranchées
  (parallélisation notamment) : `docs/wiki/deploiement.md` § 6. La purge des
  photos de démo (`seed/`) s'exécute **après** le commit du `TRUNCATE`+seed, jamais avant : un
  échec de seed laisse alors la base **et** le disque dans l'état de la veille (photos incluses),
  jamais l'un désynchronisé de l'autre. Purge sélective par génération (`app/seed/demo.py::
  snapshot_stale_seed_photo_prefixes`/`purge_stale_seed_photos`), pas un simple déplacement du
  `delete_prefix` — un `delete_prefix("seed/")` global après le commit effacerait aussi les
  photos que le run courant vient d'écrire.

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
