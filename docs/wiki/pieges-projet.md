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
