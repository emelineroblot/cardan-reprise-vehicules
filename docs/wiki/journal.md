---
type: journal
maj: 2026-08-21
---

# Journal des runs de team

Le plus récent en premier. Une entrée par run : ce qui a été livré, et le seul fait notable
qui mérite d'être retenu.

## 2026-08-21 — J3 `feature/pilotage-marge`

Livré : l'atelier (ordres de travaux sur mini-automate propre, lignes de coût `GENERATED`, photos
avant/après), les coûts hors atelier, le Kanban administrateur, la couche analytique du jalon
(4 vues de staging, 6 marts dont `mart_vehicule_marge`) et le tableau de bord. Deux chantiers non
prévus s'y sont ajoutés : le cloisonnement financier côté serveur, et un jeu de démonstration qui
rejoue enfin les effets terrain (70 missions, 48 inspections, 583 photos) — absents depuis J1.

Le fait à retenir : **la formule de marge était juste au centime, et le chiffre affiché était faux
d'un facteur 4,5.** Un `COALESCE(prix_achat, 0)` faisait entrer dans l'indicateur 59 véhicules
jamais achetés, à ~99 % de marge. Le test d'exactitude ne pouvait pas le voir : il recalculait
l'attendu avec la même expression fautive. C'est la quatrième variante d'un défaut qui aura traversé
les trois jalons — un test écrit à partir du code valide le code, pas le besoin — et ce qui l'a
trouvé, à chaque fois, c'est le recalcul à la main contre la base réelle et l'appel HTTP sur le
chemin réel. Second enseignement, découvert en fin de course : la correction littérale d'une revue
(déplacer la purge des photos après le commit) effaçait les fichiers que le seed venait d'écrire —
seule l'exécution réelle l'a montré.

Blackboard d'origine : `.agent-team/` (éphémère, écrasé au run suivant).
Détail : [architecture.md](architecture.md) — voir « Marge », « Cloisonnement financier », « Atelier »,
« Kanban opérationnel et pipeline analytique » et « Jeu de démonstration ».

## 2026-08-20 — J2 `feature/pwa-terrain`

Livré : le module terrain chauffeur en PWA installable — missions en lecture seule alimentées par
les effets de l'automate véhicule, inspection avec checklist interactive et complétude obligatoire,
parcours de 12 angles photo imposés plafonné à 30, notifications persistées en base avec web push
optionnel, moteur hors ligne (brouillon IndexedDB + file d'envoi, idempotence par `client_uuid`), et
la dette J1 du sélecteur de chauffeur fermée.

Le fait à retenir : **le contrat d'API figé a effectivement supprimé les divergences de forme de J1,
mais tout le coût s'est déplacé sur la concurrence purement frontend.** Six occurrences d'un même
défaut — une valeur lue, un `await` réseau, puis la valeur périmée réutilisée pour écrire ou effacer
un marqueur `_dirty` — dont la plus grave perdait des réponses de checklist **côté serveur** avec un
brouillon local d'apparence complète. Deuxième leçon du jalon : le parcours e2e « hors ligne » était
vert par accident (il remplissait la checklist pendant la coupure, ce qui amorçait le rejeu des
photos), et six exécutions vertes consécutives ne prouvaient rien.

Blackboard d'origine : `.agent-team/` (éphémère, écrasé au run suivant).
Détail : [architecture.md](architecture.md) — voir « Moteur hors ligne du module terrain »,
« Stockage des photos », « Notifications » et « Une inspection par mission ».

## 2026-08-20 — J1 `feature/socle-saisie`

Livré : le modèle de données complet des trois jalons (22 tables, migration unique `0001_socle`),
l'authentification native à 4 rôles avec cloisonnement route + ligne, la fiche d'achat société et
véhicule, l'enrichissement par SIRET avec fallback manuel, le dédoublonnage à deux niveaux et son
écran d'arbitrage, l'automate d'états à 11 états, la couche analytique (schéma `analytics`, runner,
un mart de fumée) et le jeu de démonstration réinitialisé chaque nuit.

Le fait à retenir : **backend et frontend ont été implémentés en parallèle sur la foi d'un contrat
écrit en prose, et ont produit cinq divergences de forme invisibles jusqu'au premier test de bout
en bout** — dont une qui bloquait 100 % du parcours authentifié. Le garde-fou prévu (types générés
depuis l'OpenAPI, CI qui échoue sur dérive) était le seul livrable du jalon non implémenté au
moment de la revue. Il l'est désormais : le job CI `contract-drift` est le filet à ne jamais
retirer en J2/J3.

Blackboard d'origine : `.agent-team/` (éphémère, écrasé au run suivant).
Détail : [architecture.md](architecture.md) — voir « Contrat front/back », « Dédoublonnage » et
« Contraintes d'exploitation d'un backend Python en serverless gratuit ».
