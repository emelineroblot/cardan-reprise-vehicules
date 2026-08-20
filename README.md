# Cardan

> Outil interne de gestion d'achat de véhicules d'occasion à des flottes professionnelles.

🚧 **En construction.** Ce dépôt est mis à jour au fil du développement.

---

## Le problème

Une entreprise rachète environ 25 véhicules par mois à des flottes professionnelles — taxis,
ambulances, sociétés de transport. Le suivi vit dans un tableur et au téléphone.

Personne ne sait dire où en est un véhicule donné. Et personne ne sait ce qu'il a réellement
rapporté, parce que les coûts d'atelier arrivent après coup et ne remontent jamais dans le tableur.

## Ce que fait Cardan

Tracer chaque véhicule de la confirmation du vendeur jusqu'à la validation d'achat, sur trois rôles :

- **Opératrice** — saisie de la fiche d'achat, enrichissement automatique de la société par SIRET,
  détection des doublons
- **Chauffeur** — mission sur mobile, contrôle sur place, checklist, photos guidées, fonctionne
  quand le réseau tombe
- **Administrateur** — pipeline du parc, coûts réels d'atelier, et la marge par véhicule que
  le tableur ne calculait pas

## Stack

Python · Next.js (PWA pour le terrain) · PostgreSQL · couche analytique séparée (staging → marts)

## Statut

| Jalon | Contenu | État |
|---|---|---|
| J1 — Socle et saisie | Modèle de données, authentification, fiche d'achat, dédoublonnage | À venir |
| J2 — Terrain | PWA chauffeur, checklist, photos guidées, brouillon hors ligne | À venir |
| J3 — Pilotage | Atelier, pipeline, couche analytique, tableau de bord | À venir |

---

## À propos

Application de **démonstration** construite par [Emeline Roblot](https://github.com/emelineroblot),
Data & Automation Builder pour PME.

Toutes les données présentées sont **fictives et générées**. La société « Reprise Atlantique »
n'existe pas, et aucune donnée client réelle n'est utilisée dans ce projet.
