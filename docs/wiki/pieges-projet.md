---
type: pieges
maj: 2026-08-20
---

# Pièges spécifiques à ce projet

Constats vérifiés en conditions réelles sur Cardan. Les pièges valables hors de ce projet
vivent dans la skill globale `stack-pitfalls`, pas ici.

## Données de démonstration

- **Tout SIRET du jeu de démo appartient déjà à une société en base** — le seed ne précharge un
  SIRET dans `company_lookup_cache` que parce qu'il a déjà des véhicules. Rechercher un SIRET de
  démo puis « Valider cette société » déclenche donc systématiquement un `409 conflict` sur
  `POST /companies` → le parcours de saisie doit traiter ce cas comme **nominal** (récupérer la
  société existante via `details.company_id` et la réutiliser), pas comme une erreur. Vaut pour
  les deux chemins de création : confirmation de lookup **et** saisie manuelle. *(2026-08-20)*
- **Un SIRET de démo ne sort jamais sur le réseau** (précaché avec `source = 'demo'`) → tester le
  provider réel exige un SIRET hors jeu de démo. *(2026-08-20)*
- **Le seed n'écrit que deux lignes d'historique par véhicule** (`BROUILLON` puis l'état final) →
  la frise d'une fiche en `TRAVAUX_EN_COURS` saute cinq états. C'est exactement l'argument « qui a
  fait quoi, quand » qu'on vient démontrer face au tableur → à enrichir avant toute démo qui insiste
  sur la traçabilité. *(2026-08-20)*
- **Toute valeur en dur dans un test e2e doit être vérifiée en base**, pas inventée à clé de Luhn
  valide : un placeholder plausible ne déclenche ni le cache de démo, ni le score de dédoublonnage
  attendu. Le calibrage reste stable d'un reset à l'autre parce que les dates du seed sont
  relatives à `date.today()`. *(2026-08-20)*

## Dédoublonnage

- **Le score bascule sous le seuil bloquant dès qu'un kilométrage manque** — le cas cible « même
  modèle refusé il y a 6 semaines » atteint 0,933 (bloquant) avec deux kilométrages proches, mais
  retombe à 0,833 (simple encart, non bloquant) si l'un manque, ce qui est fréquent lors d'une
  prise au téléphone. `s_km` neutre vaut 0,5 → envisager 0,6, ou appliquer le bonus terminal avant
  le seuil. Toute retouche des poids doit ajouter la variante « sans kilométrage » à la table de
  cas. *(2026-08-20)*
- **Normaliser par liste blanche, jamais par liste noire.** `normalize_immatriculation` ne retirait
  qu'espaces et tirets : `AA-123-BB.` normalisait en `AA123BB.`, échappait à l'index unique partiel
  et donc au doublon exact. Corrigé en liste blanche alphanumérique, comme le VIN. Vaut pour toute
  colonne normalisée qui porte une contrainte d'unicité. *(2026-08-20)*
- **Un candidat de `duplicate-check` porte trois dates distinctes** —
  `date_mise_en_circulation`, `date_proposition` et `created_at` (création de la **fiche**) → ne
  pas les confondre à l'affichage. *(2026-08-20)*
- **Passer un `intake_batch_id` au `duplicate-check` avant que le lot n'existe est sans effet au
  premier envoi**, mais après un envoi partiellement échoué les contrôles au blur compareront les
  membres du lot entre eux — exactement ce que le lot est censé empêcher. *(2026-08-20)*

## Automate d'états

- **La liste des transitions permises doit évaluer les gardes contextuelles, pas seulement les
  rôles.** Le front en dérive fidèlement ses boutons : une garde ignorée produit des actions qui
  échouent toujours en `409`. En J1 aucune `inspection` n'existe, donc un véhicule de démo en
  `CONTROLE_EN_COURS` affichait trois boutons morts. Distinguer les gardes **contextuelles** (état
  en base → masquer le bouton) des gardes **de payload** (`reason`, `rdv_at`, `refus_motif` →
  alimenter `requires_payload_fields`). *(2026-08-20)*
- **Dette assumée : `_guard_saisie_complete` est un no-op.** `BROUILLON → A_PLANIFIER` passe donc
  sur une fiche dont le dédoublonnage n'a jamais été arbitré, contrairement au tableau des
  transitions. Corriger exige de faire transiter l'état d'arbitrage dans le `TransitionContext`.
  *(2026-08-20)*
- **Dette assumée, à reprendre avant J3 :** `open_work_orders` sélectionne **tous** les work orders
  et non les seuls ouverts, et `all_work_orders_closed_with_cost_line` ne vérifie jamais la
  présence d'une ligne de coût. Sans effet en J1 (aucun work order n'existe), mais le nom de la
  variable et celui du champ mentent tous les deux. *(2026-08-20)*

## Exploitation

- **Le reset nocturne doit être atomique.** Le `TRUNCATE` tournait dans son propre `engine.begin()`,
  donc committé avant le démarrage des seeds : un échec de seed à 3 h laissait la démo publique
  avec une **base vide** jusqu'à intervention manuelle. Truncate + seeds sur la même session, un
  seul commit final ; `analytics build/refresh` reste hors transaction. *(2026-08-20)*
- **`.claude/instructions/*.md` est gitignoré** : les conventions durables écrites là
  (`analytics-sql`, `tests`) ne sont pas versionnées et n'apparaissent pas dans le dépôt public.
  À acter consciemment — ce qui doit survivre au clone va dans `docs/`. *(2026-08-20)*
- **Le panneau « fiche existante » de l'écran d'arbitrage dépend entièrement du contrat de
  `duplicate-check`** : tout champ non exposé par le candidat s'affiche « — » sans qu'aucune erreur
  ne le signale. Les six champs de comparaison (VIN, immatriculation, kilométrage, énergie,
  date de mise en circulation, `created_at`) ont été ajoutés en fin de J1 pour cette raison.
  *(2026-08-20)*

## Module terrain / PWA (J2)

> 🔴 **À LIRE AVANT D'OUVRIR J3** — la première puce ci-dessous est une bombe à retardement posée en
> J2 : elle n'a aucun effet aujourd'hui et casse le premier écran J3 qui affiche une photo.

- 🔴 **AVANT LE PREMIER ÉCRAN PHOTO DE J3 : `PhotoRead.url` est inutilisable tel quel depuis le
  navigateur.** `read_url` du stockage local renvoie `/api/v1/photos/file/{bucket}/{key}`, alors que
  le navigateur passe **obligatoirement** par le proxy Next `/api/backend/v1/...` (le front n'appelle
  jamais le backend en direct, cf. architecture § « Déploiement »). Aucun composant ne consomme
  encore ce champ — `sync.ts` le stocke sans jamais le lire — donc rien ne casse aujourd'hui et
  aucun test ne le verra. **Le premier écran J3 qui affichera une photo avant/après prendra un
  404 silencieux (image cassée, aucune erreur applicative).** À trancher **avant** d'écrire cet
  écran, pas en le déboguant : soit `read_url` renvoie une URL préfixée pour le navigateur, soit le
  front reçoit la règle de préfixage — mais jamais en la codant en dur côté client, ce qui
  recasserait à la bascule vers un stockage objet (les URL signées, elles, sont absolues).
  *(2026-08-20)*
- **Le plafond de 30 photos est compté par VÉHICULE toutes phases confondues côté serveur, alors que
  l'écran de contrôle ne compte que l'inspection courante** — un chauffeur peut donc recevoir un
  `409 photo_quota_exceeded` sans que l'interface l'ait annoncé (véhicule déjà photographié lors
  d'une mission précédente, ou photos atelier en J3). Toute UI de quota doit interroger le compte
  serveur, pas le sien. *(2026-08-20)*
- **`upload_state = 'envoyee'` est la seule preuve qu'une photo compte** : la complétude des angles
  est calculée sur ce seul état. Une photo présente dans la file locale, visible à l'écran, ne rend
  pas l'inspection soumissible. C'est voulu — ne jamais « aider » l'utilisateur en comptant les
  photos en attente. *(2026-08-20)*
- **`LocalDiskStorage` ne doit jamais rester le backend actif en déploiement** (état perdu entre
  invocations serverless) : la bascule vers un stockage objet est un prérequis de déploiement, pas
  une amélioration. Symétriquement, si des clés VAPID sont posées en production, `requirements.txt`
  doit être régénéré avec l'extra `webpush`, sinon le push échoue à chaque envoi. *(2026-08-20)*
- **Le seed J1 pose `assigned_driver_id` sur des véhicules sans créer la ligne `mission`
  correspondante** → la liste `GET /missions` du chauffeur de démo est **vide** alors que les fiches
  véhicules affichent bien un chauffeur. Une démo du module terrain doit passer par une affectation
  faite en direct dans l'UI, jamais s'appuyer sur l'état seedé. *(2026-08-20)*
- **La PWA installée démarre sur `/vehicules` (`start_url` + redirection du middleware), pas sur
  `/missions`** — chaque lancement pose le chauffeur sur la liste globale avec ses colonnes
  financières, alors que `homeRouteForRole("chauffeur")` dit `/missions`. Pas d'écran d'erreur (les
  4 rôles y ont accès), donc invisible aux tests. *(2026-08-20)*
- **`_scoped_inspection` scope sur `Vehicle.assigned_driver_id`, jamais sur `Inspection.driver_id`** :
  après une réaffectation, le nouveau chauffeur peut modifier et soumettre l'inspection commencée par
  le précédent. Défendable (le véhicule est désormais le sien) mais **non intentionnel** — à acter ou
  à corriger explicitement, pas à laisser en l'état par inertie. *(2026-08-20)*
- **`GET .../required-angles` scope le véhicule mais ne vérifie pas que `inspection_id` lui
  appartient**, contrairement à `create_photo` qui le fait. Fuite mineure (12 libellés d'angle), mais
  l'incohérence entre deux endpoints du même module est le vrai piège : on croit la règle appliquée
  partout. *(2026-08-20)*
- **L'upload photo n'a aucune borne de taille côté serveur et fait confiance au `content_type`
  déclaré par le client.** Couplé au repli de compression, qui renvoie le fichier d'origine avec son
  type d'origine quand `createImageBitmap` échoue : un HEIC part en `image/heic` → `422`, une photo
  iPhone de 8 Mo dépasse la limite de corps de la plateforme → `413`. Borner côté client avant la
  mise en file **et** côté serveur avant la lecture. *(2026-08-20)*
- **`mission.state = "acceptee"` n'est jamais posé** : la colonne et la valeur d'enum existent depuis
  J1, mais aucune transition de l'automate ne prévoit d'accusé de réception du chauffeur. Dette
  assumée, à trancher en J3 avec le pipeline admin — ne pas rouvrir l'automate pour ça avant.
  *(2026-08-20)*
- **La migration `0003` nettoie des données et ne le défait pas** (`downgrade` non symétrique) : elle
  supprime les doublons d'inspection produits par le bug, enfants d'abord faute d'`ON DELETE
  CASCADE`. Assumé — mais tout `downgrade` jusqu'à `0002` perd ce nettoyage sans rien restaurer.
  *(2026-08-20)*
- **La navigation hors ligne s'arrête à `hors-ligne.html`** : la coquille applicative n'est pas mise
  en cache, donc un démarrage à froid de la PWA sans réseau ne permet pas de revenir à l'écran de
  contrôle. Aucune donnée n'est perdue (IndexedDB intact). « Mode hors ligne complet » est
  explicitement hors périmètre — à savoir avant une démo, à traiter le jour où ce n'est plus une
  démo. *(2026-08-20)*
