# Cardan

> Outil interne de gestion d'achat de véhicules d'occasion à des flottes professionnelles.

---

## Le problème

Une entreprise rachète environ 25 véhicules par mois à des flottes professionnelles — taxis,
ambulances, sociétés de transport. Le suivi vit dans un tableur et au téléphone.

Personne ne sait dire où en est un véhicule donné. Et personne ne sait ce qu'il a réellement
rapporté, parce que les coûts d'atelier arrivent après coup et ne remontent jamais dans le tableur.

## Ce que fait Cardan

Tracer chaque véhicule de la confirmation du vendeur jusqu'à la validation d'achat, sur quatre
rôles :

- **Opératrice** — saisie de la fiche d'achat, enrichissement automatique de la société par SIRET,
  détection des doublons
- **Chauffeur** — mission sur mobile, contrôle sur place, checklist, photos guidées, fonctionne
  quand le réseau tombe
- **Atelier** — ordres de travaux, lignes de coût réel, photos avant/après
- **Administrateur** — pipeline du parc, coûts réels, et la marge par véhicule que le tableur
  ne calculait pas

## Stack

Python (FastAPI, SQLAlchemy 2, Alembic) · Next.js, PWA pour le terrain · PostgreSQL · couche
analytique séparée dans son propre schéma (vues de staging → vues matérialisées)

## Statut — les trois jalons sont livrés

| Jalon | Contenu | État |
|---|---|---|
| J1 — Socle et saisie | Modèle de données, authentification, fiche d'achat, dédoublonnage | ✅ Livré |
| J2 — Terrain | PWA chauffeur, checklist, photos guidées, mode hors ligne | ✅ Livré |
| J3 — Pilotage | Atelier, Kanban, couche analytique, tableau de bord | ✅ Livré |

### J1 — socle et saisie

- Fiche d'achat société + véhicule, avec enrichissement automatique par SIRET (API publique, sans
  clé) et repli en saisie manuelle si le service est indisponible
- Détection de doublons à deux niveaux — exacte sur le VIN et l'immatriculation, approximative sur
  société, modèle et date — avec écran d'arbitrage comparant les deux fiches côte à côte et
  détaillant les composantes du score
- Cycle de vie du véhicule en 11 états, avec historique et journal d'audit
- Liste de suivi filtrable à URL partageable

### J2 — terrain

- Application installable : missions du chauffeur, prise de rendez-vous, contrôle sur place
- Checklist interactive et parcours de 12 angles photo imposés, validés **côté serveur** — le mode
  hors ligne peut retarder l'arrivée des octets, il ne peut pas fabriquer une complétude
- Brouillon local et file d'envoi (IndexedDB), reprise automatique au retour du réseau, idempotence
  par identifiant client
- Notifications persistées en base ; le push navigateur n'est qu'une accélération optionnelle

### J3 — pilotage et marge

- Atelier : ordres de travaux issus de la transition « travaux requis », lignes de coût réel,
  photos avant/après ; un ordre ne se clôt pas sans son coût
- Coûts hors atelier (transport, carburant, administratif, remise en état externe)
- Kanban du parc, en lecture directe pour rester en phase avec les transitions
- Tableau de bord alimenté par six vues matérialisées : marge par véhicule (coûts d'atelier réels
  inclus, négative sans écrêtage, jamais affichée à zéro quand elle n'est pas calculable), délais de
  cycle, valeur immobilisée par état, taux de refus, coût des travaux
- Cloisonnement financier appliqué **côté serveur** : les montants ne sont pas seulement masqués à
  l'écran, ils ne quittent pas l'API pour les rôles qui n'y ont pas droit

## Démonstration

**→ [cardan-demo-ten.vercel.app](https://cardan-demo-ten.vercel.app)**

Quatre comptes, un par rôle, en connexion d'un clic depuis l'écran de connexion. Les données sont
fictives et générées — photos comprises, produites par le seed lui-même. Le jeu de démonstration
compte 90 véhicules répartis sur l'ensemble du cycle de vie, avec leurs missions, inspections,
photos, ordres de travaux et coûts, et comporte par construction au moins une marge négative :
un tableau de bord de marge qui n'afficherait que des chiffres flatteurs ne démontrerait rien.

La démonstration est **modifiable** : les comptes peuvent créer des fiches et faire avancer des
véhicules. Elle se réinitialise à la demande, jamais automatiquement.

## Qualité

857 tests backend exécutés contre un vrai PostgreSQL (aucun mock de base), 121 tests frontend,
4 parcours de bout en bout Playwright. L'intégration continue joue le lint, le type-check, les deux
suites, la recherche de secrets, et **échoue si les types du frontend dérivent du contrat OpenAPI**
du backend réellement démarré.

Les décisions d'architecture, leur raisonnement et les pièges rencontrés sont documentés dans
[`docs/wiki/`](docs/wiki/index.md) — y compris ceux qui restent ouverts.

---

## À propos

Application de **démonstration** construite par [Emeline Roblot](https://github.com/emelineroblot),
Data & Automation Builder pour PME.

Toutes les données présentées sont **fictives et générées**. La société « Reprise Atlantique »
n'existe pas, et aucune donnée client réelle n'est utilisée dans ce projet.
