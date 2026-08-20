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

- **Backend** : Python
- **Frontend** : Next.js — module terrain en PWA installable (caméra, stockage local, web push)
- **Base de données** : PostgreSQL managé
- **Couche analytique** : modèles séparés (staging → marts) ; le dashboard lit les marts,
  jamais des calculs à la volée dans l'UI
- **Hébergement** : Vercel + Postgres managé, offres gratuites, hébergement UE

## Règles propres au projet

- **Le dépôt est public.** Aucun secret, aucune donnée réelle, aucune référence client.
  Toutes les données de démonstration sont fictives et générées.
- **Intégration externe unique** : API INSEE Sirene (enrichissement société par SIRET).
  Un fallback en saisie manuelle est obligatoire — la démo ne doit jamais dépendre
  de la disponibilité d'un tiers.
- **Périmètre figé** : la liste `Won't have` du brief ne se rouvre pas en cours de jalon.
  Notamment : pas d'application native, pas de multi-tenant, pas d'orchestration Airflow.
- Les données de démo sont réinitialisées chaque nuit.
