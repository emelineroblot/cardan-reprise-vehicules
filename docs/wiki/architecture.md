---
type: architecture
maj: 2026-08-20
---

# Décisions d'architecture

Chaque entrée porte la décision, son raisonnement et les options écartées. Les alternatives
sont conservées : c'est ce qui permet de rouvrir une décision sans refaire l'analyse.

## Déploiement — deux projets Vercel reliés par les rewrites Next
*Décidé le 2026-08-20 — run `socle-saisie` (J1)*

**Décision.** Un seul dépôt, deux projets Vercel : l'un enraciné sur `frontend/`, l'autre sur
`backend/`. Le navigateur n'appelle jamais le backend directement : `next.config.ts` déclare un
rewrite `/api/backend/:path*` → `${BACKEND_ORIGIN}/api/:path*`.

**Pourquoi.** Le rewrite rend l'API **same-origin** côté navigateur. C'est ce qui rend le cookie
de session `httpOnly` utilisable (un cookie tiers serait bloqué par les navigateurs) et supprime
tout besoin de CORS en production. Deux projets donnent aussi des builds, des caches et des
variables d'environnement indépendants, et le backend reste une application FastAPI ordinaire,
lançable en local avec uvicorn.

*Écarté* : un projet Next unique avec des fonctions Python dans `/api` (cohabitation fragile des
deux builders, plafond de 12 fonctions sur Hobby, backend indéveloppable hors Vercel) ; un backend
sur Render/Fly gratuit (mise en veille après 15 min, ≈ 50 s de réveil — inacceptable devant un
prospect).

**Conséquences.** Un saut réseau supplémentaire. Deux jeux de variables à maintenir. Le front ne
doit jamais appeler `BACKEND_ORIGIN` depuis le navigateur — cette variable est côté serveur
uniquement.

## ORM — SQLAlchemy 2.0 en style typé, **sync et non async**
*Décidé le 2026-08-20 — run `socle-saisie` (J1)*

**Décision.** SQLAlchemy 2.0 (`Mapped[...]` / `mapped_column`) + Alembic + psycopg 3, en mode
**synchrone**. Les endpoints FastAPI sont déclarés en `def` et exécutés dans le threadpool.

**Pourquoi.** Sur des fonctions serverless qui traitent une requête à la fois, l'async n'apporte
aucun débit : il n'y a pas de concurrence à multiplexer à l'intérieur d'une instance. En revanche
il double les pièges — sessions greenlet, `MissingGreenlet` sur objets expirés, pool asyncpg mal
marié à PgBouncer. Le coût est réel, le gain nul.

**Conséquences.** Une convention de nommage des contraintes est obligatoire dans `db/base.py`
(`ix_`, `uq_`, `ck_`, `fk_`, `pk_`) : sans elle, `alembic autogenerate` produit des noms instables
et les `downgrade` cassent. Toute reprise en async serait une refonte, pas un ajustement.

## Couche analytique — schéma `analytics`, vues `stg_*` + vues matérialisées `mart_*`
*Décidé le 2026-08-20 — run `socle-saisie` (J1)*

**Décision.** Un schéma PostgreSQL dédié `analytics`, à deux étages : des vues `stg_*` (nettoyage,
typage, dénormalisation légère, aucune agrégation, une par table source) et des vues
**matérialisées** `mart_*` (une par question métier, grain documenté en en-tête du fichier `.sql`,
index unique obligatoire). Un runner d'une centaine de lignes (`analytics/runner.py` +
`manifest.yml`) expose `build` et `refresh`. Le schéma est **hors Alembic** : Alembic ne crée que
`CREATE SCHEMA analytics` et la seule table réelle, `analytics.refresh_log`.

**Pourquoi.** Le critère du brief est « le dashboard lit les marts, jamais des calculs à la volée ».
Des vues SQL simples auraient déplacé le calcul sans construire de couche. Des marts peuplés en
Python auraient réécrit en code ce que SQL fait mieux et fait disparaître l'histoire
« modélisation ». Les vues matérialisées rendent la couche **visible** : la fraîcheur devient un
objet affiché dans l'UI (« indicateurs à jour il y a 4 min »), ce qui la démontre au lieu de la
raconter. dbt et Airflow sont hors périmètre (disproportionnés pour 25 véhicules/mois) — le runner
en est la version réduite : modèles versionnés, DAG explicite, grain documenté.

**Conséquences.** Sortir les vues d'Alembic supprime d'emblée le conflit classique
« migration ↔ vue dépendante », **au prix d'un piège symétrique** : le `downgrade()` de la
migration initiale doit commencer par `DROP SCHEMA analytics CASCADE`, sinon PostgreSQL refuse de
supprimer `public.vehicle`. `REFRESH MATERIALIZED VIEW CONCURRENTLY` ne peut pas s'exécuter dans
une transaction : le runner ouvre une connexion autocommit distincte de celle du seed. Ajouter un
mart en J3 = ajouter un fichier `.sql` et une entrée au manifeste, rien d'autre.

## Enrichissement société — `recherche-entreprises.api.gouv.fr` par défaut, INSEE Sirene en option
*Décidé le 2026-08-20 — run `socle-saisie` (J1)*

**Décision.** Un port `CompanyLookupProvider` avec trois implémentations :
`RechercheEntreprisesProvider` (défaut, **sans clé**), `SireneInseeProvider` (activé si
`INSEE_API_KEY` est présente), `DisabledProvider` (tests et démo hors ligne).

**Pourquoi.** Contrainte contradictoire : le brief impose l'API INSEE Sirene, mais le dépôt est
**public** et l'API Sirene officielle exige désormais une clé. Un contributeur qui clone le dépôt
ne pourrait pas la fournir : l'application serait cassée à la sortie de la boîte, et la démo
dépendrait d'un secret. `recherche-entreprises.api.gouv.fr` est un service public ouvert, sans
authentification, alimenté par les données Sirene, avec un périmètre plus étroit mais suffisant
(dénomination, SIREN/SIRET, NAF, adresse du siège, tranche d'effectif). Le port garde l'API
officielle branchable sans réécriture.

*Écarté* : un dump Sirene en base (40 M de lignes contre 0,5 Go de quota).

**Conséquences.** Le fallback en saisie manuelle n'est pas une dégradation, c'est un chemin
nominal : un `503` ouvre le formulaire manuel avec un bandeau neutre et
`company.source_enrichissement = 'manuel'`. Validation locale du SIRET (14 chiffres + clé de Luhn,
exception `356000000` pour La Poste) **avant tout appel réseau**. Cache 30 jours en base, un hit
périmé servant de mode dégradé (`"stale": true`).

## Garde-fou RGPD — SIRET de démo fictifs et préchargés en cache
*Décidé le 2026-08-20 — run `socle-saisie` (J1)*

**Décision.** Les 12 SIRET du jeu de démonstration sont **fictifs mais à clé de Luhn valide**, et
préchargés dans `company_lookup_cache` avec `source = 'demo'`.

**Pourquoi.** Deux problèmes réglés d'un coup. D'abord le RGPD et le dépôt public : sans ce
préchargement, une démo afficherait les données d'une **vraie** entreprise, dans une application
publique, à partir d'une donnée réelle. Ensuite la robustesse de la démo : le parcours ne déclenche
**aucun appel réseau**, donc aucune dépendance à la disponibilité d'un tiers pendant une visio.

**Conséquences.** Un SIRET de démo ne sort jamais du cache : tester le chemin réseau réel demande
un SIRET hors jeu de démo. Voir aussi le piège « société déjà existante » dans
[pieges-projet.md](pieges-projet.md).

## Dédoublonnage — deux niveaux, et l'`intake_batch` comme réponse structurelle
*Décidé le 2026-08-20 — run `socle-saisie` (J1)*

**Décision.** Deux niveaux distincts.
**Exact** : VIN et immatriculation normalisés dans des colonnes dédiées, portant un **index unique
partiel**. La collision est détectée par requête *et* garantie par la base → `409 duplicate_exact`,
blocage dur.
**Approximatif** : candidats constitués en SQL (même SIREN, `date_proposition` à ±90 jours,
`intake_batch_id` différent), **exclusions dures** avant tout scoring (VIN ou immatriculation tous
deux renseignés et différents ; écart de mise en circulation > 12 mois ; écart de kilométrage
> 5 000 km ; marque différente), puis score composite pondéré en Python (`rapidfuzz`) :
`s_modele` 0,40 · `s_date` 0,25 · `s_km` 0,20 · `s_energie` 0,15, plus un bonus `+0,05` si le
candidat est en état terminal `REFUSE`/`ANNULE`. Seuils : ≥ 0,85 bloquant, 0,70–0,85 encart non
bloquant, < 0,70 silence.

**Pourquoi.** Le vrai doublon visé par le métier est *« ce véhicule a déjà été proposé il y a
6 semaines et refusé »*. Une flotte qui vend 5 Kangoo identiques le même jour n'est pas un cas
limite : c'est le **cas nominal**. Un algorithme naïf « même société + même modèle + même date »
crie au loup 10 fois sur 10, et l'opératrice apprend à cliquer « ignorer » sans lire — l'alerte
devient nuisible. Le scoring Python a été préféré à `pg_trgm` (seuils opaques, intestables sans
base, aucune place pour des règles d'exclusion métier) et à toute approche LLM (non déterministe,
non explicable, et écartée par le brief) parce que chaque règle y est explicite, testable par table
de cas, et **explicable à l'utilisatrice** (« même modèle, 12 jours d'écart, kilométrage voisin »).

**Le point structurant : l'`intake_batch`.** L'écran « Ajouter N véhicules pour cette société »
crée un lot, et les membres d'un même lot **ne sont jamais comparés entre eux** — l'exclusion est
faite en SQL, dès la constitution des candidats, pas après coup. Le cas nominal du métier devient
donc impossible **par construction**, au lieu d'être arbitré par un seuil qu'il faudrait
constamment retoucher. Les exclusions dures sont le second filet, indépendant : dès que
l'immatriculation *ou* le kilométrage est saisi — ce que l'opératrice fait au téléphone — les
5 fiches deviennent mutuellement inéligibles.

**Conséquences.** Le verdict d'arbitrage est persisté dans `duplicate_review` (paire ordonnée
`a_id < b_id`, contrainte unique) et un `not_duplicate` est **définitif** : la paire n'est plus
jamais proposée, y compris après un `PATCH` ultérieur. Le flux d'arbitrage est en deux temps :
`POST /vehicles` avec `force_create: true` (ou `PATCH` avec `force_update: true`), puis
`POST /duplicate-reviews`. La vérification est toujours rejouée côté serveur : le front ne décide
de rien.

## Automate d'états — 11 états, table déclarative, point d'entrée unique
*Décidé le 2026-08-20 — run `socle-saisie` (J1)*

**Décision.** 11 états : `BROUILLON`, `A_PLANIFIER`, `AFFECTE`, `RDV_PLANIFIE`,
`CONTROLE_EN_COURS`, `TRAVAUX_REQUIS`, `TRAVAUX_EN_COURS`, `TRAVAUX_TERMINES`, et trois terminaux
`ACHAT_VALIDE`, `REFUSE`, `ANNULE`. L'automate est une **table de données Python**
(`TRANSITIONS: dict[tuple[State, State], Transition]`), pas une cascade de `if`. Chaque transition
porte son rôle habilité, sa garde et son effet.

**Pourquoi.** Une table se teste exhaustivement : un test paramétré balaie les combinaisons
(état, état, rôle) et vérifie que **seules** les cases déclarées passent. Une cascade de `if` ne se
teste que par les chemins qu'on a pensé à écrire.

**Trois règles structurelles.**
1. **Un état terminal est terminal** : aucune transition n'en sort. Une erreur se corrige en créant
   une nouvelle fiche — ce qui préserve l'historique, précisément ce que le tableur ne sait pas
   faire.
2. **Un seul point d'entrée** : `POST /vehicles/{id}/transitions`. Aucun endpoint ne modifie
   `state` directement, et `state` n'apparaît dans aucun corps de `PATCH`. Sans cette règle,
   l'automate n'est qu'une recommandation.
3. **Trace obligatoire** : toute transition écrit une ligne `vehicle_state_transition` **et** une
   ligne `audit_log`, dans la même transaction SQL que le changement d'état. Pas de trace = pas de
   délai de cycle calculable en J3.

**Conséquences.** `REFUSE` et `ANNULE` sont distincts et ce n'est pas cosmétique : J3 compte le
premier dans le taux de refus, pas le second. Un refus interdit sans `refus_motif` (garanti par un
`CHECK` en base). Le front ne duplique pas l'automate : `GET /vehicles/{id}/transitions` lui
renvoie `{allowed: [{to_state, label, requires_reason, requires_payload_fields}]}` et il en dérive
ses boutons — cette réponse doit donc évaluer les gardes contextuelles, pas seulement les rôles
(voir [pieges-projet.md](pieges-projet.md)).

## Authentification — native, argon2id + JWT en cookie, cloisonnement à deux étages
*Décidé le 2026-08-20 — run `socle-saisie` (J1)*

**Décision.** Auth écrite dans le backend : argon2id via `argon2-cffi` (pas `passlib`, non
maintenu), JWT HS256 de 12 h sans refresh token, déposé dans un cookie `cardan_session`
`httpOnly` + `Secure` + `SameSite=Lax`. Quatre rôles : `operatrice`, `chauffeur`,
`administrateur`, `atelier`.

**Pourquoi.** Auth.js ferait vivre la session côté front alors que l'autorisation doit vivre là où
sont les données — il faudrait de toute façon valider un jeton côté Python, donc écrire le même
code en double. Un fournisseur d'identité managé (Neon Auth, Supabase Auth) ajouterait une
dépendance externe et des clés dans un dépôt public, alors que le brief impose une seule
intégration externe. Le coût réel est d'environ 150 lignes.

**Cloisonnement, non négociable, à deux étages.** (1) *Route* : dépendance `require_roles(...)` sur
chaque endpoint → `403 forbidden_role`. (2) *Ligne* : une fonction unique `scope_vehicles(query,
user)` appliquée par **tous** les accès en lecture — `chauffeur` ne voit que les véhicules dont une
mission active lui est affectée, `atelier` ceux qui ont un ordre de travaux ouvert. Le front n'est
jamais la barrière : masquer un bouton ne protège rien. Un test d'intégration parcourt chaque
endpoint × chaque rôle.

**Conséquences.** Un chauffeur qui demande un véhicule non affecté reçoit `404`, jamais `403` :
l'existence de la ressource n'est pas révélée. La pagination compte sur la requête **déjà scopée**,
sinon le `total` renvoyé fuiterait la taille du parc. Les 4 comptes de démo ont des mots de passe
publics affichés à l'écran : assumé (données fictives, base réinitialisée chaque nuit), à ne pas
reconduire tel quel si le projet servait de base à un outil réel — pas plus que l'absence de token
CSRF, couverte ici par le seul `SameSite=Lax`.

## Contraintes d'exploitation d'un backend Python en serverless gratuit
*Décidé le 2026-08-20 — run `socle-saisie` (J1)*

**Décision.** L'hébergement gratuit (Vercel Hobby + Postgres managé en UE) n'est pas une contrainte
de déploiement : c'est une contrainte **de code**, traitée explicitement.

**Pourquoi et comment.**
- **Aucun état en mémoire entre deux requêtes.** Chaque instance de fonction est éphémère : une
  variable de module est vidée en permanence. Le cache SIRET **et** le circuit breaker du lookup
  vivent donc en base (`company_lookup_cache`, `lookup_health`), pas en mémoire. Corollaire : leur
  écriture doit être **committée pour elle-même**, indépendamment de la transaction métier — sinon
  une exception levée plus loin annule la mémorisation de l'échec et le circuit ne s'ouvre jamais.
- **PgBouncer en mode transaction** : chaîne de connexion « pooled », `QueuePool` réduit
  (`pool_size=1`, `max_overflow=2`), `pool_pre_ping=True` (la base se met à l'échelle à zéro après
  5 min : sans ping, la première requête échoue), `pool_recycle=280`, et surtout
  **`prepared_statement_cache_size=0` / `prepare_threshold=None`** : les instructions préparées ne
  survivent pas au multiplexage.
- **Une seconde chaîne, directe** (`DATABASE_URL_DIRECT`), pour les migrations et le
  `REFRESH CONCURRENTLY`.
- **Aucune migration au démarrage.** N instances concurrentes qui lancent `alembic upgrade` =
  verrous et corruption. C'est une commande manuelle ou un job CI, jouée avant le déploiement.
- **Dépendances légères** : `requirements.txt` verrouillé, sans `pandas` ni `numpy`. Les agrégats
  sont faits par PostgreSQL — c'est aussi la raison d'être de la couche analytique.
- **Double démarrage à froid** (fonction + réveil de la base). Mitigation : la page d'accueil
  publique est statique et déclenche un `GET /health` dès son chargement — tout se réveille pendant
  que le visiteur lit la page.
- **Cron quotidien uniquement** sur Hobby, authentifié par `Authorization: Bearer $CRON_SECRET`
  comparé en temps constant.

**Conséquences.** Toute future fonctionnalité qui suppose un état en mémoire (rate limiting local,
cache applicatif, verrou) doit être repensée en base ou abandonnée. Le plan Hobby est réservé à un
usage non commercial : une démo de portfolio y entre, un client réel non.

## Contrat front/back — types générés depuis l'OpenAPI, jamais retapés
*Décidé le 2026-08-20 — run `socle-saisie` (J1)*

**Décision.** `openapi-typescript` génère `frontend/src/lib/api/schema.d.ts` depuis le
`/openapi.json` du backend réel (`npm run gen:api`). Un job CI `contract-drift` démarre PostgreSQL
et le backend migré, régénère le fichier et échoue sur `git diff --exit-code`. Un client
`apiFetch<T>` enveloppe `fetch`, porte le cookie et convertit toute erreur en
`ApiError { code, message, details }`.

**Pourquoi.** Backend et frontend ont été implémentés en parallèle. Le contrat écrit dans le plan
n'a pas suffi : cinq divergences de forme sont passées inaperçues jusqu'au premier test de bout en
bout, dont une qui bloquait 100 % du parcours authentifié. Un schéma généré transforme une rupture
de contrat en erreur de compilation TypeScript, au lieu d'un bug découvert en démo.

**Conséquences.** Conventions qui découlent du contrat : `snake_case` de bout en bout, sans alias
camelCase (aucune conversion, donc aucun bug de conversion) ; champs métier en français, ressources
en anglais ; montants en **entiers de centimes** suffixés `_cents`, jamais de flottant ni de
`Decimal` sérialisé ; `timestamptz` ISO-8601 UTC, le formatage local étant une affaire de front ;
un format d'erreur unique dont le front mappe le `code`, **jamais** le `message`.
`schema.d.ts` ne se modifie pas à la main — le vérifier par idempotence (deux régénérations
consécutives doivent produire un fichier identique).

## Structure et données strictement séparées — migrations, seeds, reset nocturne
*Décidé le 2026-08-20 — run `socle-saisie` (J1)*

**Décision.** Les migrations Alembic ne portent **que** de la structure. Les données vivent dans
deux profils de seed idempotents : `reference` (4 comptes, modèles de checklist, angles photo,
upsert par `code`) et `demo` (~90 véhicules sur 3 mois). Une migration initiale `0001_socle` crée
le schéma complet des **trois** jalons.

**Pourquoi.** Mettre le jeu de démo dans des migrations rendrait chaque évolution du contenu
tributaire d'une migration de données, avec des `downgrade` ingérables. Un dump `pg_restore` serait
un binaire opaque dans un dépôt public, cassé à chaque migration. Le schéma complet d'entrée plutôt
qu'une migration par jalon : le projet est solo, la base est réinitialisée chaque nuit, et un
lecteur doit pouvoir lire le modèle d'un seul coup — les tables J2/J3 restent simplement vides
jusqu'à leur jalon.

**Conséquences.** Le seed de démo est déterministe (`Random(SEED_VERSION)` + `Faker('fr_FR')` à
graine fixe) **mais ses dates sont recalculées relativement à `date.today()`** : la démo montre
toujours « les 3 derniers mois », jamais un historique qui vieillit. C'est le détail le plus
souvent raté et le plus visible en démo — et il rend aussi les calibrages de test stables d'un
reset à l'autre. `--profile demo` refuse de s'exécuter si la base contient un utilisateur hors des
comptes de démo (sauf `--force`). Le reset nocturne (`TRUNCATE` d'une liste de tables **en dur**,
jamais découverte dynamiquement, puis les deux seeds) doit être **atomique** : truncate et seeds
dans une seule transaction. Un filet CI rejoue `alembic upgrade head` puis les deux seeds à chaque
push : seeds et migrations ne peuvent pas diverger sans que la CI vire au rouge.

## Décisions de second rang, tranchées et argumentées
*Décidé le 2026-08-20 — run `socle-saisie` (J1)*

- **`VARCHAR` + `CHECK` plutôt qu'un `ENUM` natif PostgreSQL.** Ajouter une valeur à un enum natif
  exige un `ALTER TYPE` qu'`alembic autogenerate` **ne détecte pas**, et J2/J3 ajouteront des
  états. La contrainte `CHECK` est dérivée des `StrEnum` Python : zéro divergence possible entre le
  filet SQL et la vérité fonctionnelle, qui reste dans l'automate Python.
- **Base de test : PostgreSQL réel, jamais SQLite.** Le modèle repose sur des index uniques
  partiels, du `jsonb`, des colonnes générées et des index fonctionnels — SQLite validerait un code
  qui casse en production. Une fixture de session applique `alembic upgrade head` une fois, chaque
  test tourne dans une transaction annulée.
- **Tailwind v4 + shadcn/ui (Radix).** Le code des composants est **dans le dépôt**, donc lisible
  par le destinataire du portfolio ; Radix fournit l'accessibilité et la gestion du focus, et les
  cibles tactiles sont maîtrisées pour le terrain en J2.
- **SPA authentifiée (composants clients + TanStack Query) plutôt que RSC + Server Actions.** Les
  RSC imposeraient deux chemins de données, alors que J2 a besoin d'un cache client, de mutations
  optimistes et d'un mode hors ligne. Un seul chemin de données pour les trois jalons. Aucun enjeu
  de SEO sur une application interne authentifiée ; seules la page d'accueil et `/login` restent
  statiques (elles servent au préchauffage).
- **Photos (J2) : Supabase Storage, bucket privé en région UE**, upload direct navigateur par URL
  signée — la fonction Python ne voit jamais l'octet. Vercel Blob a été écarté faute de région UE
  garantie, `bytea` faute de quota. **Le seed ne stocke aucune photo** : les véhicules de démo
  référencent un pool de visuels statiques (`is_placeholder = true`), soit 0 octet de quota
  consommé ; seules les photos prises pendant une démo occupent le bucket, et elles disparaissent
  au reset de la nuit (préfixes `demo/` conservé, `runtime/` purgé).
- **Marge : la formule est figée dès J1, appliquée en J3.** Deux règles non négociables — la marge
  **peut être négative** (aucun `GREATEST(0, …)`), et une valeur de revente absente donne
  `marge_cents = NULL` avec `has_marge = false`, l'UI affichant « — » et jamais « 0 € ». Confondre
  « pas de valeur » et « zéro » est le bug classique de tout tableau de bord de marge.
