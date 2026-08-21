---
type: architecture
maj: 2026-08-21
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
  signée — la fonction Python ne voit jamais l'octet. **→ Révisée le 2026-08-20 (J2)** : J2 livre
  une abstraction `PhotoStorage` sur disque local, l'octet transitant par le backend ; le stockage
  objet reste la cible du déploiement. Voir « Stockage des photos » plus bas. Vercel Blob a été écarté faute de région UE
  garantie, `bytea` faute de quota. **→ Non appliquée telle quelle par le seed final (constat au
  déploiement, 2026-08-21)** : `app/seed/demo.py` écrit en réalité 583 photos réelles et
  distinctes par génération (`is_placeholder = false`), pas un pool de visuels statiques — chaque
  reset nocturne les réécrit en totalité. C'est ce volume, écrit séquentiellement vers un stockage
  réseau, qui a motivé la mesure du budget de temps du reset au déploiement ; revenir au pool
  statique décrit ici reste une option non tranchée pour réduire ce volume — voir
  [deploiement.md](deploiement.md) § 6, option A. **La visibilité « bucket privé » ci-dessus a,
  elle aussi, été revue au déploiement (2026-08-21)** : le bucket réel est `public: true`,
  décision assumée pour cette démonstration (photos synthétiques, détruites chaque nuit — voir
  [deploiement.md](deploiement.md) § 3 pour le raisonnement complet et la condition qui rendrait
  un bucket privé de nouveau obligatoire).
- **Marge : la formule est figée dès J1, appliquée en J3.** Deux règles non négociables — la marge
  **peut être négative** (aucun `GREATEST(0, …)`), et une valeur de revente absente donne
  `marge_cents = NULL` avec `has_marge = false`, l'UI affichant « — » et jamais « 0 € ». Confondre
  « pas de valeur » et « zéro » est le bug classique de tout tableau de bord de marge.

## Moteur hors ligne du module terrain — brouillon local, file d'envoi, idempotence par `client_uuid`
*Décidé le 2026-08-20 — run `pwa-terrain` (J2)*

**Décision.** Le contrôle terrain s'écrit **d'abord en local** (IndexedDB : un brouillon
d'inspection par véhicule, un store `photos` portant les blobs compressés), jamais directement sur
le réseau. Un moteur de synchronisation monté dans le layout applicatif rejoue la file **au premier
plan** : minuteur de 20 s, évènement `online`, après chaque écriture locale, et bouton « Réessayer »
— uniquement si l'onglet est visible. Chaque objet naît côté client avec un `client_uuid` ;
`POST /inspections` et `POST /vehicles/{id}/photos` sont **idempotents par ce `client_uuid`** côté
serveur, garanti par une contrainte d'unicité en base et non par la seule lecture applicative. Le
rejeu ne repose sur Background Sync à aucun moment.

**Pourquoi.** Le critère d'acceptation est « couper le réseau en plein contrôle ne perd aucune
saisie, et la reprise renvoie les photos en attente ». Une écriture réseau optimiste avec repli
local aurait laissé deux sources de vérité ; l'écriture locale d'abord n'en laisse qu'une, et la
synchronisation devient un **rejeu**, pas une devinette. L'identifiant généré côté client est ce qui
rend ce rejeu sûr : quand la réponse de la première tentative s'est perdue, le client ne peut pas
savoir si le serveur a reçu — seul un identifiant qu'il a lui-même choisi permet au serveur de
répondre « je l'ai déjà ». Background Sync a été écarté comme garantie unique : il aurait masqué le
fait que le rejeu au premier plan doit de toute façon être correct.

**Conséquences.** Quatre règles qui tiennent tout l'édifice, et qui ont chacune coûté un bug réel
dans ce jalon :
- **Relire l'état frais juste avant toute écriture réseau**, et n'effacer un marqueur `_dirty` que
  si le contenu relu est identique à ce qui vient d'être envoyé. Sinon une saisie faite pendant
  l'`await` est perdue **côté serveur** alors que l'écran local paraît complet.
- **L'atomicité vient de la transaction IndexedDB** (lecture + écriture dans la même transaction
  `readwrite`), jamais d'un verrou tenu dans une variable de module : IndexedDB est partagé par
  toute l'origine, un verrou JS ne protège que l'onglet courant (PWA installée + onglet navigateur
  = deux moteurs concurrents).
- **L'éligibilité d'un brouillon à un tick dérive de l'état réel de la file**, photos `queued`/
  `failed` comprises — pas des seuls marqueurs du brouillon. Une file sans déclencheur propre ne
  part jamais.
- **L'état du brouillon est un état d'appareil**, tenu en `useState` + relecture explicite après
  chaque écriture, hors TanStack Query — qui reste réservé aux caches de réponses serveur (listes
  véhicules, missions, notifications). Corollaire : purge des photos `sent` après confirmation de
  soumission et `navigator.storage.persist()` au montage, sinon les blobs (200-400 Ko pièce)
  s'accumulent véhicule après véhicule jusqu'au `QuotaExceededError`.

## Stockage des photos — abstraction `PhotoStorage`, disque local aujourd'hui, stockage objet au déploiement
*Décidé le 2026-08-20 — run `pwa-terrain` (J2). Révise la décision de second rang du 2026-08-20 (J1)
« Photos : Supabase Storage, upload direct navigateur par URL signée ».*

**→ Bascule réalisée le 2026-08-21 (run `déploiement-supabase`).** Le pari a tenu : brancher
Supabase Storage a coûté exactement une classe (`SupabaseStorage`, `backend/app/services/storage/
supabase.py`) et un branchement dans `get_storage_backend()` (choisi par configuration — présence
de `SUPABASE_URL`/`SUPABASE_SERVICE_KEY` — jamais une variable dédiée), **aucun autre fichier**
n'a changé. Le fournisseur retenu est bien Supabase (parmi d'autres options possibles, cf.
« Garder le choix du fournisseur ouvert » ci-dessous — jamais formellement comparé à des
alternatives, la décision a été prise directement par Emeline). `PhotoStorage` avait grandi entre
J2/J3 (`delete_prefix`, `list_top_level` pour la purge sélective du reset nocturne) : les deux
sont implémentées. Un point n'a **pas** bougé, par choix explicite et non une simplification
oubliée : `read_url` continue de renvoyer la même route backend authentifiée que
`LocalDiskStorage` (jamais une URL signée Supabase directe), pour conserver le scoping par
véhicule évoqué dans les conséquences ci-dessous — cette bascule-là (vers une URL signée) reste
un travail futur possible, pas fait ici. Deux comportements réels de l'API Supabase Storage,
absents de sa documentation publique, ont été découverts en testant contre un vrai projet plutôt
qu'en lisant la doc — voir [pieges-projet.md](pieges-projet.md) § Déploiement.

**Décision.** Les octets ne sont jamais manipulés directement par le code métier : un port
`PhotoStorage` (interface), une implémentation `LocalDiskStorage` (active aujourd'hui, sous
`backend/var/`, gitignorée) et une fabrique `get_storage_backend()` qui est **le seul point de
bascule**. `PhotoRead.url` porte une URL de forme stable, consommée telle quelle par le front et
**jamais reconstruite** par lui ; l'implémentation locale y renvoie une route backend authentifiée
par cookie, une implémentation objet y renverra une URL signée. Le checksum SHA-256 est recalculé et
comparé côté serveur, jamais seulement transmis.

**Pourquoi.** Deux raisons, dans cet ordre.

**1. Ne pas interrompre le développement.** Brancher Supabase pendant J2 supposait de créer un
projet, d'en récupérer les clés et de les transmettre au pipeline : une interruption dans un travail
explicitement délégué, et des secrets à manipuler dans le contexte d'un dépôt public. Le disque local
permet à J2 d'avancer sans rien de tout cela.

**2. Garder le choix du fournisseur ouvert jusqu'à la mise en ligne** — c'est le point qui compte le
plus pour qui reprend ce projet. Ce n'est **pas** « Supabase, plus tard » : l'abstraction existe
précisément pour que le fournisseur de stockage soit choisi **au déploiement, sur des critères de
déploiement** (région, quota, coût, latence, dépendance acceptable). La décision J1 (Supabase
Storage, upload direct navigateur par URL signée) n'est donc plus acquise — elle redevient une option
à réévaluer parmi d'autres, et non un simple travail restant à faire.

En appui, deux faits qui n'ont pas motivé la décision mais la confirment : le disque local est
**inutilisable en serverless** (chaque invocation est éphémère, § « Contraintes d'exploitation »),
donc la bascule vers un stockage objet est un **prérequis de déploiement** et non une amélioration
optionnelle ; et n'exiger ni compte externe ni secret rend le dépôt public clonable et démontrable
tel quel. L'abstraction fait que ce prérequis coûte une classe et un branchement, pas une réécriture :
la seule différence de comportement observable est la nature de l'URL, déjà cachée derrière un champ
de contrat stable.

**Conséquences.** Aucun module n'importe l'implémentation directement, tout passe par la fabrique :
c'est cette propriété qu'il faut préserver. Le passage par le backend pour servir l'octet a un effet
de bord positif conservé aujourd'hui — scoping par véhicule, un chauffeur ne peut pas lire la photo
d'un véhicule qui n'est pas le sien — qu'une URL signée ne donnera pas gratuitement : à retraiter au
moment de la bascule. Voir aussi le piège de préfixe d'URL dans [pieges-projet.md](pieges-projet.md).

## Notifications — persistées en base comme chemin nominal, web push strictement optionnel
*Décidé le 2026-08-20 — run `pwa-terrain` (J2)*

**Décision.** Une notification est **une ligne en base**, écrite dans la même transaction que
l'affectation de mission. La pastille et la liste ne dépendent d'aucune clé, d'aucune permission
navigateur, d'aucun service tiers. Le web push est un **bonus** : il n'est proposé que si
`GET /notifications/push-public-key` renvoie `enabled: true`, ce qui n'est vrai que si des clés
VAPID existent côté serveur. L'envoi push a lieu **après** le `commit` métier, de façon synchrone
mais bornée par un délai maximal court, et un abonnement n'est désactivé que sur un `404`/`410`.

**Pourquoi.** Une démonstration ne doit jamais dépendre d'une autorisation navigateur : un refus de
permission, un navigateur non compatible ou une clé absente rendrait le critère « le chauffeur
reçoit une notification à l'affectation » inobservable devant un prospect. En persistant d'abord, le
critère est tenu **par construction** ; le push n'ajoute que l'immédiateté. L'ordre inverse
(notifier puis persister) aurait fait dépendre une affectation déjà actée d'un canal externe. La
disponibilité du push est un **fait serveur** : le front l'interroge à l'exécution plutôt que de
dupliquer une variable d'environnement, qui se désynchroniserait au premier déploiement.

**Conséquences.** L'envoi reste synchrone dans la requête HTTP, contre l'intuition : sur une
fonction serverless, rien ne garantit que le processus survive à l'envoi de la réponse, donc une
tâche de fond aurait rendu le taux de livraison non déterministe et l'échec invisible. Le pire cas
est borné par le délai maximal (3 s) multiplié par le nombre d'abonnements actifs du destinataire —
acceptable en mono-appareil, à revoir (parallélisation ou budget global) si le multi-appareil
devient réel. `send_web_push` renvoie une issue à trois valeurs
(`sent`/`failed_transient`/`failed_permanent`) et non un booléen : tout futur appelant doit traiter
les trois. Le chemin push réellement activé n'a jamais été exercé en conditions réelles, faute de
clés VAPID en local.

## Une inspection par mission — contrainte totale en base, portée `mission_id` et non `vehicle_id`
*Décidé le 2026-08-20 — run `pwa-terrain` (J2)*

**Décision.** `UNIQUE(mission_id)` sur `inspection` (contrainte **totale**, pas un index partiel),
migration `0003`, doublée d'une garde applicative : `POST /inspections` renvoie l'inspection déjà
existante de la mission — soumise ou non — au lieu d'en créer une seconde.

**Pourquoi.** L'idempotence par `client_uuid` seule ne suffisait pas : un rechargement d'écran juste
après soumission fait naître un `client_uuid` neuf, et le véhicule restant en `CONTROLE_EN_COURS`
jusqu'à la transition suivante, les préconditions serveur étaient toujours satisfaites — une seconde
inspection orpheline se créait sans le moindre signal. La portée **par véhicule** a été écartée après
vérification du tableau des transitions : aucune transition ne fait repasser un véhicule par
`CONTROLE_EN_COURS` pour une même mission, mais un véhicule **réaffecté** obtient une nouvelle
mission et peut légitimement porter une inspection par mission historique. `mission_id` est donc la
portée exacte, et un index partiel aurait dû encoder la même règle en moins lisible. Renvoyer
l'existante plutôt qu'un `409` a été préféré parce que le front n'a alors aucune branche
supplémentaire à écrire : il reçoit la donnée qu'il demandait.

**Conséquences.** La contrainte ne fait pas que protéger, elle **diagnostique** : posée, elle a
immédiatement révélé une course frontend jusque-là invisible (deux créations de brouillon
simultanées au montage, donc deux `client_uuid`), qui produisait auparavant une ligne orpheline
muette. Argument durable en faveur de la défense en profondeur sur tout `get_or_create`. La
migration `0003` embarque un nettoyage de données — doublons produits par le bug, enfants supprimés
d'abord faute de `ON DELETE CASCADE` — **non réversible dans son `downgrade`**, assumé.

## Parcours photo — 12 angles imposés, plafond de 30, validés côté serveur
*Décidé le 2026-08-20 — run `pwa-terrain` (J2)*

**Décision.** Les 12 angles obligatoires et le plafond de 30 photos par véhicule sont des règles
**serveur**. `POST /inspections/{id}/submit` refuse en `409 inspection_incomplete` avec le détail
(`missing_items`, `missing_angles`) et ne compte que les photos réellement reçues
(`upload_state = 'envoyee'`) ; le dépassement du plafond répond `409 photo_quota_exceeded`. Le front
**dérive** son parcours de `GET /vehicles/{id}/photos/required-angles`, il ne recopie pas la liste
(un repli d'affichage local existe, purement cosmétique, le temps du premier succès réseau).

**Pourquoi.** Même principe qu'en J1 avec `GET /vehicles/{id}/transitions` : une règle métier
dupliquée dans les deux couches diverge, et c'est la couche cliente qui ment. L'enjeu est ici plus
fort qu'un bouton mal affiché — un contrôle validé avec un angle manquant est un dossier
inexploitable. Valider côté serveur signifie aussi que le mode hors ligne ne peut pas devenir un
contournement : la file peut retarder l'arrivée des octets, elle ne peut pas fabriquer une
complétude. Le checksum recalculé côté serveur relève de la même logique — une photo tronquée par
une coupure en cours d'envoi est refusée, pas stockée corrompue.

**Conséquences.** L'interface ne peut afficher qu'un **pré-contrôle** : le bouton de soumission est
désactivé avec la liste de ce qui manque, mais le refus serveur reste possible et doit être affiché
tel quel. Le plafond serveur porte sur le **véhicule, toutes phases confondues**, alors que l'écran
ne compte que l'inspection courante — voir [pieges-projet.md](pieges-projet.md). L'angle `defaut`
est le seul répétable ; les phases atelier (`avant_travaux`, `apres_travaux`) sont explicitement
refusées en J2 et s'ouvriront en J3 par ajout, pas par révision.

## Décisions de second rang — J2
*Décidé le 2026-08-20 — run `pwa-terrain` (J2)*

- **`mission` reste en lecture seule côté API.** Création, prise de rendez-vous, clôture et
  annulation sont des **effets** de `POST /vehicles/{id}/transitions`, jamais des endpoints propres.
  Prolonge le principe J1 « un seul point d'entrée » : aucune divergence possible entre l'état d'un
  véhicule et celui de sa mission.
- **L'inspection est créée par le client, pas par la transition `RDV_PLANIFIE → CONTROLE_EN_COURS`.**
  Lu littéralement, le plan associait la création à la transition ; un effet serveur aurait imposé
  un aller-retour réseau synchrone à l'instant précis où le chauffeur commence son contrôle — soit
  le moment que le mode hors ligne doit protéger. Le `client_uuid` doit naître côté client.
- **Le référentiel de checklist est exposé en liste + détail** (`/checklist-templates`), pas en
  « modèle actif » implicite : une notion de modèle courant casserait au premier versionnement, et
  une inspection doit pouvoir référencer un modèle désactivé. Ouvert à tout rôle authentifié (donnée
  de référence, non sensible).
- **Caméra par `<input capture="environment">`, pas `getUserMedia`.** Le flux vidéo live donne une
  mise en cadre plus fine mais dépend des permissions et des particularités de chaque navigateur
  mobile ; la capture déléguée à l'application caméra du système est robuste sur des appareils non
  maîtrisés à l'avance — exactement le contexte d'une démonstration.

## Atelier — les ordres de travaux naissent d'une transition, et vivent sur leur propre automate
*Décidé le 2026-08-21 — run `pilotage-marge` (J3)*

**Décision.** Un `work_order` est créé exclusivement comme **effet** de
`POST /vehicles/{id}/transitions` vers `TRAVAUX_REQUIS` (payload `work_orders`, liste non vide) —
il n'existe aucun endpoint de création. Son cycle de vie propre
(`demande → en_cours|annule`, `en_cours → termine|annule`) est un **mini-automate séparé**, table
de données Python dans `services/work_orders.py`, piloté par `POST /work-orders/{id}/state`. La
garde « clos ⇒ au moins une ligne de coût » s'applique à l'ordre ; la transition véhicule
`TRAVAUX_EN_COURS → TRAVAUX_TERMINES` vérifie, elle, que **tous** les ordres du véhicule sont clos
**avec** une ligne. `work_order_line.montant_cents` est une colonne `GENERATED` côté base, jamais
calculée en Python ni côté client.

**Pourquoi.** Prolonge le principe posé en J1 pour `mission` : un seul point d'entrée décide quand
un véhicule entre en travaux, donc aucune divergence possible entre l'état du véhicule et celui de
ses ordres. *Écarté* : un `POST /vehicles/{id}/work-orders` dédié (deux responsabilités concurrentes
pour la même décision) ; généraliser `state_machine.py` à plusieurs entités (sur-ingénierie pour
deux transitions utiles, sans rôle ni contexte propres).

**Conséquences.** Le front n'a **rien à dériver** pour ce sous-automate : aucun
`GET /work-orders/{id}/transitions` n'existe, la table de transitions est donc recopiée côté client
(`lib/workOrders/automate.ts`) — seule dérogation assumée à la règle « les actions viennent de
l'API ». Le serveur reste l'arbitre (`409`). La garde « clos ⇒ ≥ 1 ligne » vaut aussi pour
`annule` : annuler un ordre créé par erreur est un cul-de-sac, voir
[pieges-projet.md](pieges-projet.md).

## Marge — la formule est figée depuis J1, le périmètre est la vraie décision
*Décidé le 2026-08-21 — run `pilotage-marge` (J3)*

**Décision.** `marge_cents = valeur_revente_estimee − prix_achat_negocie − frais_transport −
Σ vehicle_cost − Σ work_order_line.montant_cents` (coûts d'atelier **réels**, jamais l'estimé), et
`has_marge` est la **conjonction** « valeur de revente renseignée **et** prix d'achat renseigné ».
Les deux `CASE` renvoient `NULL` — jamais `0` — dès que l'une manque ; l'interface affiche « — » et
ne recalcule rien. Une marge négative traverse toute la chaîne sans écrêtage.

**Pourquoi.** La formule était figée et vérifiée au centime. Le défaut était ailleurs : un
`COALESCE(prix_achat, 0)` faisait entrer dans l'indicateur 59 véhicules **jamais achetés**,
ressortis à ~99 % de marge, et la tuile affichait 12 264 € au lieu de 2 583 €. Un modèle peut être
parfaitement cohérent avec lui-même et parfaitement faux quand son périmètre l'est. *Écarté* :
conserver une « marge prévisionnelle » sur les véhicules non achetés en restreignant seulement les
tuiles — deux notions de marge dans le même mart, et un écran qui aurait dû expliquer laquelle il
montre.

**Conséquences.** Le périmètre se teste **séparément** de l'arithmétique, et le test asserte que le
jeu de données contient réellement le cas limite (`checked_null_no_prix_achat > 0`), sinon il serait
vert par absence de cas. Tout libellé d'écran qui explique l'exclusion doit citer les deux causes :
la légende a survécu au correctif et affirmait le contraire du tableau situé dans la même carte.

## Kanban opérationnel et pipeline analytique — deux lectures volontairement distinctes
*Décidé le 2026-08-21 — run `pilotage-marge` (J3)*

**Décision.** `GET /vehicles/pipeline-counts` (Kanban) lit `vehicle` en direct et renvoie
**toujours les 11 états**, même à zéro. `GET /analytics/pipeline-etat` (tableau de bord) lit le
mart, à la fraîcheur du dernier `refresh`. Les deux ne partagent aucune clé de cache côté client.

**Pourquoi.** Le Kanban est un écran de **manipulation** : déplacer une carte puis la voir revenir
dans son ancienne colonne jusqu'au prochain refresh serait un bug perçu. Le tableau de bord est un
écran de **pilotage** : sa valeur de démonstration tient précisément à ce que la fraîcheur y soit
visible et assumée (« indicateurs à jour il y a 4 min »).

**Conséquences.** Deux endpoints qui se ressemblent — un futur excès de DRY les fusionnerait et
réintroduirait la latence dans le Kanban. Le bouton « Actualiser les indicateurs » est le seul
moyen de faire apparaître un véhicule tout juste créé dans le tableau de bord ; c'est volontaire et
exercé par le parcours de bout en bout.

## Cloisonnement financier — la barrière est au contenu de la réponse, pas seulement à la ressource
*Décidé le 2026-08-21 — run `pilotage-marge` (J3)*

**Décision.** Deux traitements distincts selon la nature du besoin. (1) `prix_achat_negocie_cents`,
`valeur_revente_estimee_cents` et `frais_transport_cents` sont **rédigés** (mis à `None` après
construction explicite du schéma) pour tout rôle hors `{operatrice, administrateur}`, sur les trois
endpoints qui sérialisent un véhicule — liste, détail, réponse de transition. (2) Les ordres de
travaux et les coûts passent d'« authentifié » à `require_roles("atelier", "operatrice",
"administrateur")` : un `403` avant même le scope. Le périmètre de l'atelier (`scope_vehicles`) est
par ailleurs élargi à l'état `TRAVAUX_EN_COURS`, en plus des véhicules portant un ordre non clos.

**Pourquoi.** Le contrôle portait sur l'**accès à la ressource**, jamais sur le **contenu** de la
réponse : un chauffeur recevait les ingrédients de la marge sur 70 véhicules, et masquer les blocs
côté interface ne protège rien contre un appel direct. Rédiger plutôt que dupliquer le schéma :
chauffeur et atelier ont un besoin légitime de tous les **autres** champs de la fiche ; un second
schéma pour trois champs en moins aurait doublé la surface à maintenir. À l'inverse, le chauffeur
n'a aucun besoin de la ressource « ordre de travaux » — un `403` y est le traitement correct.
L'élargissement du périmètre atelier corrige un cul-de-sac réel : en clôturant son dernier ordre,
l'atelier sortait de son propre périmètre **avant** d'avoir pu déclencher la transition véhicule
que cette clôture venait de débloquer.

**Conséquences.** `frais_transport_cents` devient `int | None` au contrat — le front doit passer par
un formateur défensif, sinon « interdit » s'affiche comme `0 €`. Les tests de cloisonnement lisent
le **corps** de la réponse, et son texte brut, jamais le seul code de statut, et portent un
contraste pour détecter un correctif trop large. Une divergence reste ouverte sur les coûts hors
atelier (backend plus permissif que l'écran) : voir [pieges-projet.md](pieges-projet.md).

## Jeu de démonstration — le seed rejoue les effets de l'application, il ne pose pas des états
*Décidé le 2026-08-21 — run `pilotage-marge` (J3)*

**Décision.** Pour chaque véhicule, le seed reconstitue la **frise complète** de son historique
d'états (horodatée, rétrodatée jusqu'à 90 jours) puis rejoue les effets que chaque étape aurait
produits dans l'application réelle : `mission`, `notification`, `inspection` et ses réponses de
checklist, `photo` (12 angles imposés, avant/après travaux — de vrais fichiers PNG générés en
mémoire), `work_order`, `work_order_line`, `vehicle_cost`. Les tirages terrain utilisent un flux
`random.Random` **dédié**. Au moins une marge négative est garantie **par construction**, sur un
véhicule `ACHAT_VALIDE`, calibrée à l'ordre de grandeur des marges positives. Le véhicule vedette du
dédoublonnage est fixé en dur après la boucle, hors de tout tirage aléatoire.

**Pourquoi.** Un jeu de démonstration qui pose des états sans leurs effets fabrique des situations
que la production ne peut pas produire : 52 véhicules affectés et **zéro mission**, soit le jalon J2
entier invisible en démonstration — non détecté pendant trois jalons, parce qu'aucun test ne
regardait la cohérence du jeu de démo lui-même. Le flux aléatoire séparé est la contrainte non
négociable : un seul tirage terrain sur le flux principal décalerait tous les véhicules suivants et
déplacerait les chiffres du tableau de bord. Laisser la marge négative au hasard du tirage rendrait
un critère d'acceptation non déterministe malgré la graine fixe.

**Conséquences.** Cinq tests d'invariants (`test_seed_demo_invariants.py`) traitent le jeu de démo
comme un livrable : aucun véhicule post-`AFFECTE` sans mission, aucune inspection soumise sans ses
12 angles, aucune ligne `photo` sans fichier réellement lisible. Les 9 chiffres du tableau de bord
sont figés dans `test_demo_reset.py` — les déplacer est une décision, pas un ajustement. La purge
disque des photos de seed est **sélective par génération** (photographie des préfixes avant le seed,
purge après le commit) : voir [pieges-projet.md](pieges-projet.md).

## Décisions de second rang — J3
*Décidé le 2026-08-21 — run `pilotage-marge` (J3)*

- **L'atelier est une section de la fiche véhicule, pas un écran dédié.** Le contrat n'expose aucun
  `GET /work-orders` global, et `scope_vehicles` limite déjà l'atelier à ses véhicules : un écran
  séparé aurait dupliqué `/vehicules` avec un filtre équivalent.
- **Kanban sans glisser-déposer.** Déplacer une carte reste un `POST /vehicles/{id}/transitions`
  ordinaire, déclenché depuis la fiche. Un drag & drop natif aurait dupliqué la logique de gardes
  déjà dérivée de l'API, avec une parité clavier et lecteur d'écran coûteuse, pour un gain
  d'ergonomie marginal sur 90 véhicules. Chaque colonne affiche un aperçu de six véhicules — ce que
  « lisible d'un coup d'œil » demandait réellement.
- **Les photos d'atelier ne passent pas par la file hors ligne.** Le moteur de J2 répond à un besoin
  précis (contrôle en extérieur, réseau incertain) ; l'atelier travaille connecté. Les fonctions
  pures de compression et de checksum sont réutilisées telles quelles, la machinerie de file ne
  l'est pas.
- **Les trois graphiques à barres sont en HTML/CSS, pas en SVG.** Un `viewBox` étroit combiné à
  `preserveAspectRatio="none"` rendait les échelles x et y indépendantes : tout le contenu
  vectoriel, texte compris, était étiré d'un facteur ~3,4 sur un écran de bureau. Des barres n'ont
  pas besoin d'un repère vectoriel ; seul le graphique en lignes reste en SVG, avec un
  `aspect-ratio` CSS identique à son `viewBox` et ses libellés sortis en calque HTML.
- **Le tableau est le jumeau accessible de chaque graphique**, pas une vue secondaire : aucune
  valeur n'est lisible uniquement au survol, et un écart estimé/réel se lit en icône **et** en
  libellé, jamais par la couleur seule.
