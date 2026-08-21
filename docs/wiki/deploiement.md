---
type: deploiement
maj: 2026-08-21
---

# Déploiement — Vercel (deux projets) + Supabase (Postgres + Storage)

Marche à suivre complète pour mettre la démo en ligne. Écrit pour quelqu'un qui découvre
Supabase : chaque valeur à récupérer précise l'écran exact du tableau de bord.

Rappel d'architecture (détail et raisonnement dans [architecture.md](architecture.md)) : **deux
projets Vercel** sur le même dépôt (racine `frontend/` et racine `backend/`), reliés par le
rewrite Next `/api/backend/:path*`. Le navigateur n'appelle jamais le backend en direct. La base
de données et le stockage des photos sont **tous les deux** hébergés par le même projet Supabase.

## 1. Créer le projet Supabase

1. Créer un compte / se connecter sur [supabase.com](https://supabase.com).
2. **New project** → choisir une **région UE** (ex. `eu-central-1`, Francfort — cohérent avec la
   contrainte d'hébergement UE du projet, § Hébergement du `CLAUDE.md` racine). Noter le mot de
   passe de la base généré à cette étape : c'est celui qui compose les chaînes de connexion
   Postgres ci-dessous (Supabase ne le raffiche jamais en clair après coup — un mot de passe
   perdu se régénère depuis **Project Settings → Database → Reset database password**, ce qui
   invalide l'ancien dans toutes les chaînes déjà notées).

## 2. Valeurs à récupérer dans le tableau de bord Supabase

| Variable | Où la trouver | Notes |
|---|---|---|
| `SUPABASE_URL` | **Project Settings → API → Project URL** | Forme `https://<ref>.supabase.co`. |
| `SUPABASE_SERVICE_KEY` | **Project Settings → API → Project API keys**, ligne **`service_role`** | **Jamais** la clé `anon`/publique : c'est la `service_role` qui contourne les policies RLS du bucket, nécessaire puisque c'est le *backend* qui écrit pour le compte de tous les utilisateurs, jamais le navigateur. Cette clé a tous les droits sur le projet — ne jamais l'exposer côté frontend/navigateur. |
| `SUPABASE_BUCKET` | Nom choisi à la création du bucket (§ 3) | `cardan-photos` par défaut (`app/core/config.py`), à garder tel quel sauf besoin explicite de le changer. |
| `DATABASE_URL` | **Project Settings → Database → Connection string**, onglet **Transaction pooler** | Port **6543**. C'est la chaîne que l'API utilise à chaque requête (`app/db/session.py`, `pool_size=1`) — un pooler en mode transaction, comme PgBouncer. |
| `DATABASE_URL_DIRECT` | **Project Settings → Database → Connection string**, onglet **Direct connection** | Port **5432**. Réservée à Alembic (`alembic upgrade head`) et à `REFRESH MATERIALIZED VIEW ... CONCURRENTLY` (`app/analytics/runner.py`) — un pooler en mode transaction ne supporte ni les migrations de schéma ni `CONCURRENTLY`. |

Les deux chaînes de connexion partagent le même mot de passe (§ 1) mais un hôte/port différents —
Supabase les affiche déjà complètes, avec le mot de passe à coller soi-même (`[YOUR-PASSWORD]`
dans le champ affiché).

Format attendu par SQLAlchemy/psycopg (préfixe `postgresql+psycopg://`, pas seulement
`postgresql://` que Supabase affiche par défaut — driver posé dans `pyproject.toml`) :

```
postgresql+psycopg://postgres.<ref>:<mot-de-passe>@aws-0-<region>.pooler.supabase.com:6543/postgres
postgresql+psycopg://postgres.<ref>:<mot-de-passe>@aws-0-<region>.pooler.supabase.com:5432/postgres
```

## 3. Créer le bucket de stockage — **à la main, le code ne le fait jamais**

**Storage → New bucket** dans le tableau de bord :
- Nom : la même valeur que `SUPABASE_BUCKET` (`cardan-photos` par défaut).
- **Visibilité : Private.** Le bucket ne doit **pas** être public — la lecture d'une photo passe
  systématiquement par la route backend authentifiée `GET /api/v1/photos/file/{bucket}/{key}`
  (scoping par véhicule, `scope_vehicles`), jamais par une URL Supabase directe
  (`SupabaseStorage.read_url` renvoie volontairement la même route que le disque local — voir
  [architecture.md](architecture.md) § Stockage des photos). Un bucket public rendrait cette
  route contournable par quiconque devine ou obtient un chemin d'objet, même si aucune URL
  publique n'est aujourd'hui affichée par l'application.
- Aucune policy RLS supplémentaire n'est nécessaire : le backend utilise la clé `service_role`,
  qui contourne RLS par construction.

`SupabaseStorage` (`backend/app/services/storage/supabase.py`) n'appelle jamais l'API de gestion
des buckets (créer/lister/supprimer un bucket) — seulement les opérations sur les objets d'un
bucket déjà existant. Le créer est donc un préalable strictement manuel.

⚠️ **Constat sur le projet réel utilisé pendant ce développement** : le bucket `cardan-photos`
y existe déjà et est actuellement configuré **`public: true`** — à corriger en **Private** dans
**Storage → cardan-photos → Configuration** avant le premier déploiement, pour correspondre à la
décision ci-dessus. Non corrigé par ce développement (action sur le compte Supabase, hors du
mandat de préparation du code).

## 4. Variables d'environnement à déclarer sur Vercel

### Projet backend

| Variable | Valeur |
|---|---|
| `ENVIRONMENT` | `production` (ou `preview` sur les déploiements de prévisualisation) — **à poser explicitement**, le défaut du champ reste `local` si oubliée (voir `.env.example` et le garde-fou de `app/core/config.py`). |
| `DATABASE_URL` | Chaîne **Transaction pooler** (§ 2). |
| `DATABASE_URL_DIRECT` | Chaîne **Direct connection** (§ 2). |
| `JWT_SECRET` | Valeur aléatoire forte, générée une fois (ex. `openssl rand -hex 32`) — jamais la valeur d'exemple du dépôt : l'application **refuse de démarrer** sinon (`environment != "local"`). |
| `CRON_SECRET` | Valeur aléatoire forte, distincte de `JWT_SECRET` — c'est elle qui protège `POST/GET /api/v1/admin/demo-reset` (route destructrice, `TRUNCATE` des tables opérationnelles). Vercel pose automatiquement `Authorization: Bearer $CRON_SECRET` sur l'invocation du cron déclaré dans `vercel.json` ; même valeur utilisable pour un déclenchement manuel (`curl -H "Authorization: Bearer $CRON_SECRET" ...`). |
| `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_BUCKET` | § 2 — dès que les deux premières sont renseignées, `get_storage_backend()` bascule automatiquement sur `SupabaseStorage` (aucune autre variable à poser, voir `app/services/storage/service.py`). |
| `COMPANY_LOOKUP_PROVIDER` | `recherche_entreprises` (défaut, sans clé) sauf besoin explicite du provider INSEE officiel. |
| `INSEE_API_KEY` | Optionnelle — laisser vide sauf `COMPANY_LOOKUP_PROVIDER=insee`. |
| `CORS_ORIGINS` | Sans effet en pratique (le rewrite Next rend l'appel same-origin), mais garder une valeur cohérente, ex. `["https://<domaine-frontend>.vercel.app"]`. |

`VAPID_PUBLIC_KEY`/`VAPID_PRIVATE_KEY` restent optionnelles (web push, arbitrage « notifications
en base, push strictement optionnel ») — ne les poser que si le push réel est explicitement voulu
pour la démo.

**Vercel injecte automatiquement `VERCEL=1`** sur toute exécution de la plateforme : c'est ce que
détecte `Settings.vercel` pour forcer le mode distant (secrets obligatoires, cookie `Secure`,
instructions préparées désactivées) même si `ENVIRONMENT` a été oubliée — un filet, pas une
excuse pour ne pas poser `ENVIRONMENT` explicitement.

### Projet frontend

| Variable | Valeur |
|---|---|
| `BACKEND_ORIGIN` | URL du déploiement Vercel du projet **backend** (ex. `https://cardan-backend.vercel.app`) — lue **côté serveur uniquement** par `next.config.ts`, jamais exposée au navigateur. |

## 5. Ordre des opérations pour le premier déploiement

1. Créer le projet Supabase (§ 1), récupérer les valeurs (§ 2), créer le bucket privé (§ 3).
2. Déployer le projet Vercel **backend** avec les variables d'environnement posées (§ 4) — le
   premier déploiement peut échouer/tourner sans base peuplée, c'est attendu à ce stade.
3. Jouer les migrations sur la base Supabase, **depuis un poste avec `DATABASE_URL_DIRECT`
   pointée sur Supabase** (jamais depuis une fonction serverless au démarrage, § architecture.md
   « Aucune migration au démarrage ») :
   ```bash
   cd backend
   DATABASE_URL_DIRECT="<connexion directe Supabase>" \
   DATABASE_URL="<connexion directe Supabase>" \
     .venv/Scripts/python.exe -m alembic upgrade head
   ```
   (Alembic lit `DATABASE_URL`, pas `DATABASE_URL_DIRECT`, pour se connecter — poser
   temporairement `DATABASE_URL` sur la connexion **directe** le temps de cette seule commande,
   jamais pour l'API elle-même.)
4. Premier seed, **à la main**, une fois la base migrée — deux profils dans l'ordre :
   ```bash
   .venv/Scripts/python.exe -m app.cli seed --profile reference
   .venv/Scripts/python.exe -m app.cli seed --profile demo
   ```
   (mêmes variables d'environnement Supabase que l'étape précédente + `SUPABASE_URL`/
   `SUPABASE_SERVICE_KEY` déjà dans l'environnement pour que le seed écrive les photos sur le
   bon bucket plutôt que sur le disque local).
5. Construire la couche analytique une première fois (le cron nocturne ne fait que la
   rafraîchir, `build` crée les vues/vues matérialisées) :
   ```bash
   .venv/Scripts/python.exe -m app.cli analytics build
   .venv/Scripts/python.exe -m app.cli analytics refresh
   ```
6. Déployer le projet Vercel **frontend** avec `BACKEND_ORIGIN` posée sur l'URL du backend (§ 4).
7. Vérifier `GET https://<backend>.vercel.app/api/v1/health` répond, puis ouvrir le frontend et
   se connecter avec un des comptes de démo (`app/seed/reference.py`).
8. Vérifier que le cron `demo-reset` est bien listé dans **Vercel → Project → Cron Jobs** —
   déclaré dans `backend/vercel.json`, aucune action manuelle en plus, mais Vercel n'active les
   cron jobs qu'après un déploiement en production (pas sur une preview).

## 6. Reset nocturne — tient-il dans le budget de temps de la fonction serverless ?

C'était le risque principal, non évalué, de ce déploiement. Mesuré concrètement, pas estimé —
chiffres du 2026-08-21, sur le projet Supabase déjà configuré dans `backend/.env` au moment de ce
développement.

### Ce que dit Vercel aujourd'hui sur la durée maximale (à vérifier sur le projet réel)

Documentation officielle Vercel consultée le 2026-08-21
(`vercel.com/docs/functions/configuring-functions/duration`) : **avec Fluid Compute — indiqué
« enabled by default » —, le plan Hobby a une durée de fonction par défaut ET maximale de
300 secondes (5 minutes)**, pas 60 secondes. Le chiffre de 60 s évoqué au départ de ce jalon
correspond au modèle de calcul serverless *classique* (pré-Fluid Compute), plus bas — **à vérifier
concrètement sur le projet Vercel réel d'Emeline** (Project Settings → Functions → Fluid Compute)
avant de considérer l'un ou l'autre chiffre comme acquis : Fluid Compute est le défaut des
nouveaux projets, mais un compte/projet plus ancien peut ne pas l'avoir. `backend/vercel.json`
déclare `"functions": {"api/index.py": {"maxDuration": 300}}` — la valeur maximale du plan Hobby
avec Fluid Compute ; si Fluid Compute s'avère indisponible sur le projet réel, Vercel refusera ce
déploiement avec une erreur explicite (pas un échec silencieux) et il faudra revenir sur cette
valeur en fonction du plafond réel constaté, potentiellement en appliquant une des options du
tableau ci-dessous.

### Mesures réelles

**Baseline locale (disque local, PostgreSQL local via Docker — donc latence réseau ≈ 0), CLI
`python -m app.cli demo-reset`, chronométré en conditions réelles :**

| Étape | Durée mesurée |
|---|---|
| Photographie des préfixes `seed/` de la génération précédente | ~0 s |
| `TRUNCATE` des tables opérationnelles | 0,17 s |
| `seed_reference` | 0,24 s |
| `seed_demo` (90 véhicules, missions, inspections, checklists, **583 écritures de photos**) | 9,9–10,2 s |
| `commit` | ~0 s |
| `analytics build` + `refresh` | 0,11 s |
| Purge des préfixes `runtime/` + `seed/` de la génération précédente | 0,12 s |
| **Total** | **≈ 10,5–11,7 s** |

Point important, vérifié en isolant l'écriture des photos (`storage.save` patché en no-op le
temps d'une mesure) : **l'essentiel de ces ~10 s est du travail ORM (90 véhicules avec tout leur
historique), pas de l'écriture disque** — écrire 583 petits fichiers sur disque local coûte moins
de 0,3 s au total. La question du provider de stockage ne pèse donc quasiment rien tant qu'on
reste en local ; elle devient déterminante uniquement une fois les écritures parties sur le
réseau (ci-dessous).

**Mesures réelles contre le vrai projet Supabase Storage** (40 écritures séquentielles de photos
synthétiques ~135 octets, prefixe de test créé puis intégralement nettoyé après coup) :

| Métrique | Valeur mesurée |
|---|---|
| Moyenne | 173 ms/écriture |
| Médiane | 136 ms/écriture |
| p90 | 226 ms/écriture |
| Min / max | 108 ms / 1056 ms (un seul pic, probablement une connexion froide) |

**Extrapolation à 583 écritures séquentielles (moyenne mesurée) : ≈ 101 secondes** — pour les
photos seules, sans compter le reste du reset.

**Avec parallélisation** (`ThreadPoolExecutor`, 20 workers, `httpx.Client` partagé — 120 écritures
réelles testées, 0 échec, aucun signe de limitation de débit du projet) : débit mesuré
**57,3 écritures/s**, soit **≈ 10,2 secondes pour 583 écritures** — un facteur ~10 par rapport au
séquentiel, sans aucune erreur observée à ce niveau de concurrence.

### Le total, mis bout à bout

| Scénario | Photos | Reste du reset* | Total estimé |
|---|---|---|---|
| Séquentiel (architecture actuelle telle quelle) | ~101 s (mesuré) | ~11 s (mesuré en local ; probablement un peu plus contre la base Supabase réelle, non mesuré faute de chaîne de connexion Postgres Supabase fournie à ce stade) | **≈ 112–130 s** |
| Avec parallélisation (20 workers) | ~10 s (mesuré) | ~11 s (idem) | **≈ 21–30 s** |

*« Reste du reset » = `TRUNCATE` + les deux seeds + `commit` + `analytics build/refresh` +
purges — mesuré uniquement contre PostgreSQL **local** (Docker, latence quasi nulle) faute de
chaîne de connexion Supabase fournie pendant ce développement. Le prochain smoke test post-
déploiement (§ 5) doit re-mesurer ce chiffre contre la vraie base — l'ordre de grandeur ne
devrait pas changer radicalement (quelques dizaines de requêtes SQL, pas des centaines), mais
ce n'est pas vérifié.

### Conclusion

- **Sous un plafond de 300 s (Hobby + Fluid Compute, le défaut actuel selon la documentation
  Vercel)** : l'architecture actuelle (séquentielle) passe avec une marge confortable — même le
  scénario le plus pessimiste mesuré (≈ 130 s) reste à moins de la moitié du budget.
- **Sous un plafond de 60 s (modèle classique, si Fluid Compute s'avérait indisponible sur le
  projet réel)** : l'architecture actuelle **ne passe pas** — ~101 s pour les seules photos
  dépassent déjà le budget à eux seuls. C'est le scénario qui a motivé cette mesure.

**Décision à prendre avec Emeline**, pas tranchée ici : la parallélisation (mesurée, fiable, ~10×
plus rapide, aucune erreur à 20 workers concurrents) donne une marge confortable **quel que soit**
le plafond réel — investissement faible (le point d'appel des écritures dans `app/seed/demo.py`
et `purge_stale_seed_photos`, la classe `SupabaseStorage` est déjà pensée pour être appelée
depuis plusieurs threads, `httpx.Client` partagé). Elle n'est **pas strictement nécessaire** si
Fluid Compute est bien actif sur le projet réel, mais représenterait une marge de sécurité peu
coûteuse face à la variabilité réseau (le pic à 1056 ms observé plus haut, ×583 en séquentiel,
suffirait à lui seul à menacer un plafond de 60 s).

### Options si une marge supplémentaire est voulue (aucune tranchée, aucune implémentée)

| Option | Effort | Effet mesuré/estimé | Inconvénient |
|---|---|---|---|
| **A. Réduire le nombre de photos du seed** (retour à la décision J1 d'origine : pool de visuels statiques `is_placeholder=true` pour les véhicules historiques, photos réelles seulement pour les actions live d'une démo) | Moyen — touche `app/seed/demo.py` | 0 à ~90 écritures au lieu de 583 → quasi nul | Les véhicules historiques affichent des visuels génériques, pas des photos distinctes par véhicule |
| **B. Paralléliser les écritures** (`ThreadPoolExecutor`, mesuré ci-dessus) | Faible — un point d'appel dans `app/seed/demo.py`/`purge_stale_seed_photos` | ~101 s → ~10 s (mesuré, 20 workers) | Aucun testé à ce stade ; à re-vérifier une fois en conditions de prod (région Vercel ↔ région Supabase, débit sous charge réelle) |
| **C. N'écrire que les photos manquantes** (clés de photo stables entre deux nuits au lieu de `uuid4()` régénérés, `exists()` avant `save()`) | Élevé — remanie la génération des clés et la logique de purge par génération (`snapshot_stale_seed_photo_prefixes`) | Quasi nul après la première nuit ; la première reste au coût plein | Refonte plus large, interagit avec le mécanisme de purge sélective déjà en place |
| **D1. Scinder le cron en deux étapes** (reseed DB puis upload photos, deux crons Vercel décalés de quelques minutes) | Moyen | Chaque étape reste sous n'importe quel plafond | Fenêtre de quelques minutes où la base référence des photos pas encore uploadées (404 transitoire, acceptable à 3h du matin sans trafic) |
| **D2. Passer au plan Vercel Pro** | Aucun effort code | Plafond à 800 s (voire 1800 s en bêta « extended max duration ») | **Contredit la contrainte documentée « offres gratuites » du `CLAUDE.md` racine** — coût récurrent pour un projet de portfolio |

## 7. Ce qui reste strictement manuel (le code ne peut pas le couvrir)

- Création du compte et du projet Supabase, choix de la région.
- Création (déjà faite sur le projet utilisé pendant ce développement, à vérifier sur tout
  nouveau projet) **et passage en Private** du bucket de stockage (§ 3) — vérifié absent de toute
  route de code, `SupabaseStorage` suppose le bucket déjà existant et n'agit jamais sur sa
  visibilité.
- Récupération et saisie des variables d'environnement sur les deux projets Vercel (§ 4).
- Premier `alembic upgrade head` contre la base Supabase (§ 5, étape 3) — jamais automatique,
  par choix explicite du projet (`architecture.md` « Aucune migration au démarrage »).
- Premier seed (`reference` puis `demo`, § 5, étape 4) et premier `analytics build` (§ 5,
  étape 5) — la base Supabase est vide tant que ces commandes n'ont pas été jouées une fois ; le
  cron nocturne ne fait que rejouer ce même chemin ensuite, il ne le remplace pas pour la mise en
  route initiale.
- Vérification, sur le tableau de bord Vercel du projet backend, que **Fluid Compute** est
  effectivement actif (§ 6) — condition du chiffre de 300 s retenu dans `vercel.json`.
