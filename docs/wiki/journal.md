---
type: journal
maj: 2026-08-20
---

# Journal des runs de team

Le plus récent en premier. Une entrée par run : ce qui a été livré, et le seul fait notable
qui mérite d'être retenu.

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
