---
type: journal
maj: 2026-08-20
---

# Journal des runs de team

Le plus récent en premier. Une entrée par run : ce qui a été livré, et le seul fait notable
qui mérite d'être retenu.

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
