---
type: pieges
maj: 2026-08-21
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
- ✅ **Corrigé (2026-08-21) — était :** `open_work_orders` sélectionnait **tous** les work orders et
  non les seuls ouverts, et `all_work_orders_closed_with_cost_line` ne vérifiait jamais la présence
  d'une ligne de coût : deux noms qui mentaient, sans effet tant qu'aucun work order n'existait
  (J1/J2). `build_transition_context` (`app/services/vehicles.py`) vérifie désormais réellement
  `state ∈ (termine, annule)` **et** `work_orders_service.has_cost_line(...)` pour chaque ordre.
  Leçon conservée : une garde dont l'objet n'existe pas encore ne peut être ni vraie ni fausse —
  elle est simplement **non exercée**, et le nom de sa variable est alors la seule documentation
  disponible. Relire ces gardes au jalon qui matérialise leur objet, pas avant. *(2026-08-21)*

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

- ✅ **Corrigé (2026-08-21) — `PhotoRead.url` est désormais utilisable tel quel dans un `<img src>`,
  ne jamais reconstruire de préfixe côté front.** Était : `read_url` du stockage local renvoyait
  `/api/v1/photos/file/{bucket}/{key}`, une route **backend**, alors que le navigateur passe
  obligatoirement par le proxy Next `/api/backend/v1/...` (cf. architecture § « Déploiement »).
  Aucun composant ne consommait ce champ en J2, donc rien ne cassait et aucun test ne le voyait —
  le premier écran photo de J3 aurait pris un 404 silencieux. Corrigé côté serveur
  (`app/services/storage/local.py`, préfixe constant `_BROWSER_PREFIX`), jamais côté client : un
  préfixe codé en dur dans le front recasserait à la bascule vers un stockage objet, dont les URL
  signées sont absolues. Deux leçons conservées : un champ que **personne ne consomme encore** ne
  peut pas être validé par la suite de tests, et c'est un test **unitaire** — pas d'intégration —
  qui a attrapé le double `/api` de la première version, l'intégration parlant au backend sans
  passer par le rewrite Next. *(2026-08-21)*
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
- ✅ **Corrigé (2026-08-21), à ne pas rouvrir sans relire `_seed_terrain_for_vehicle`
  (`app/seed/demo.py`) :** le seed J1/J2/J3 ne référençait **jamais** `Mission`/`Inspection`/
  `Photo`/`Notification`, à aucun jalon — `assigned_driver_id` était posé sur le véhicule sans
  créer la ligne `mission` correspondante, `GET /missions` du chauffeur de démo restait **vide**
  malgré 52 véhicules affectés dans le Kanban admin (`tests-j3.md` § 3, vérifié en HTTP réel). Le
  seed rejoue désormais, pour chaque véhicule, les effets `mission`/`inspection`/`photo` (angles
  de contrôle **et** avant/après travaux, vrais fichiers PNG via `PhotoStorage`)/`notification`
  qu'aurait produits chaque étape de son historique — sur un flux `random.Random` **dédié**
  (`terrain_rng`), jamais celui qui pilote marque/modèle/état/prix (`rng`) : le voir survivre à
  trois jalons a montré qu'aucun test ne regardait la cohérence du jeu de démo lui-même, d'où les
  cinq tests dédiés dans `tests/integration/test_seed_demo_invariants.py` (aucun véhicule
  post-`AFFECTE` sans mission, aucun `CONTROLE_EN_COURS` sans inspection, aucune `photo` sans
  fichier réellement lisible). Une démo du module terrain peut donc à nouveau s'appuyer sur
  l'état seedé — plus besoin de passer par une affectation faite en direct dans l'UI.
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
- **Deux préfixes de stockage photo distincts, à ne jamais confondre** :
  `runtime/{vehicle_id}/...` (uploads réels via `POST /vehicles/{id}/photos`, purgé par
  `app/seed/reset.py` **après** chaque seed) et `seed/{vehicle_id}/...` (photos générées par
  `app/seed/demo.py`, purgées **par le seed lui-même en tout début d'exécution**, pour rester
  idempotentes sur disque). Écrire une photo de seed sous `runtime/` la ferait disparaître dès la
  fin du reset qui vient de la créer — le seed doit toujours écrire sous `seed/`, jamais l'inverse.
  *(2026-08-21)*

## Pilotage, atelier et couche analytique (J3)

- 🔴 **`has_marge` est une conjonction : valeur de revente estimée **et** prix d'achat négocié
  renseignés.** Ne jamais réintroduire un `COALESCE(prix_achat_negocie_cents, 0)` dans
  `mart_vehicule_marge.sql` : un véhicule jamais acheté ressort alors avec ~99 % de marge, et la
  tuile « Marge moyenne » est faussée d'un facteur 4,5 (12 264 € affichés contre 2 583 € réels).
  Corollaire de rédaction : tout texte d'écran qui explique l'exclusion doit citer **les deux**
  causes (pas encore acheté, ou sans valeur de revente) — sur 67 véhicules exclus, 59 le sont pour
  la première. *(2026-08-21)*
- **Le véhicule vedette du dédoublonnage (`VH-2026-000087`, Renault Kangoo, Benard SARL) est
  calibré en dur après la boucle du seed** (`_calibrate_dedup_demo_vehicle`), hors de tout tirage
  `rng`. Il l'a payé une fois : la réécriture du seed J3 a décalé sa position dans le flux aléatoire
  et son kilométrage est passé de 120 279 à 143 783 km, au-delà du seuil d'exclusion dure de
  5 000 km — `j1-saisie.spec.ts` ne voyait plus aucun candidat. Ne jamais rebrancher ces champs
  (marque, modèle, énergie, kilométrage, absence de VIN/immat, date de proposition) sur `rng`.
  *(2026-08-21)*
- **Le seed terrain tire sur un flux `random.Random` dédié (`terrain_rng`), jamais sur le `rng`
  principal.** Un seul tirage terrain sur le flux principal décale tous les véhicules suivants et
  déplace les 9 chiffres du tableau de bord — que
  `test_demo_reset.py::test_mart_kpi_global_matches_known_reference_values` fige désormais. Un écart
  sur ce test n'est pas forcément une régression : c'est un **déplacement à documenter**, à trancher
  avant de mettre les valeurs à jour (une étude de cas cite ces chiffres). *(2026-08-21)*
- 🔴 **La purge disque des photos de seed se fait par snapshot avant / purge sélective après le
  commit.** `delete_prefix(prefix="seed/")` supprime tout le sous-arbre : appelé après le commit,
  il efface la génération que le run vient d'écrire (les clés sont des `uuid4()`, jamais
  recouvrantes) ; appelé avant, il casse l'atomicité du reset nocturne et laisse la démo publique
  avec 583 vignettes cassées en cas d'échec du seed. D'où
  `snapshot_stale_seed_photo_prefixes` (avant `seed_demo`) + `purge_stale_seed_photos` (après le
  commit). Toute nouvelle implémentation de `PhotoStorage` doit fournir `list_top_level`.
  *(2026-08-21)*
- **`GET /vehicles/pipeline-counts` (Kanban, live) et `GET /analytics/pipeline-etat` (dashboard,
  mart) sont volontairement deux endpoints distincts.** Les fusionner par excès de DRY remettrait
  le Kanban en retard sur ses propres transitions jusqu'au prochain `refresh`. Leurs clés TanStack
  Query sont également disjointes côté front, pour qu'aucune invalidation ne traverse. *(2026-08-21)*
- **Annuler un ordre de travaux exige une ligne de coût, comme le clore.** `demande → annule` est
  donc un cul-de-sac pour un ordre créé par erreur : l'atelier doit d'abord saisir un coût
  (éventuellement 0 €) sur des travaux qu'il n'a pas faits. La règle vient du brief (« terminé ou
  annulé ⇒ au moins une ligne ») — dette assumée, à rouvrir avec le produit, pas en contournant la
  garde. *(2026-08-21)*
- **`taux_refus_global` = refusés / tous les véhicules non `ANNULE`**, dossiers encore en cours
  compris : 18 % affichés là où le ratio sur dossiers tranchés vaut 50 % (16/32). Ce n'est pas
  faux, c'est ambigu — la tuile est posée à côté d'« Achats validés 16 · Refusés 16 » et la
  division se fait de tête. Arbitrage éditorial non tranché : renommer la tuile, ou ajouter
  `nb_decides`/`taux_refus_decides` au mart. *(2026-08-21)*
- **Divergence non tranchée sur les coûts hors atelier :** l'API les ouvre en lecture à
  `atelier|operatrice|administrateur`, l'interface ne monte `VehicleCostsPanel` que pour
  `operatrice|administrateur`. Puisque « le front n'est jamais la barrière », c'est la règle
  backend qui fait foi — un compte `atelier` lit ces montants en appel direct. Les deux positions
  se défendent, l'absence de décision non. *(2026-08-21)*
- **Le périmètre du chauffeur repose sur `assigned_driver_id`, jamais sur une mission active** —
  contrairement à ce qu'annonce la docstring de `scope_vehicles`. `assigned_driver_id` n'étant
  jamais purgé à la clôture, un chauffeur voit 70 véhicules, `REFUSE` et `ANNULE` compris. Sans
  conséquence de confidentialité depuis la rédaction des champs financiers, mais c'est un
  commentaire faux dans une fonction de sécurité — donc une revue future s'appuiera dessus. À
  trancher : corriger le commentaire, ou purger l'affectation à la clôture. *(2026-08-21)*
- **Deux petits défauts connus, sans effet aujourd'hui :** `VehiclePatch.frais_transport_cents`
  accepte `null` alors que la colonne est `NOT NULL` (un `PATCH {"frais_transport_cents": null}`
  produit une `IntegrityError`, donc un 500 — antérieur à J3) ; et `get_kpi_global` renvoie `{}`
  sur un mart vide, ce que `KpiGlobalRead` rejette en `ResponseValidationError` — la branche
  défensive provoque le plantage qu'elle prétend éviter (cas inatteignable, le mart produisant
  toujours une ligne). *(2026-08-21)*
