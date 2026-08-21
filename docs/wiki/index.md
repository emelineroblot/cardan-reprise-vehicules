---
type: wiki-index
projet: Cardan — gestion d'achat de véhicules d'occasion
maj: 2026-08-21
---

# Wiki — Cardan

Mémoire longue du projet, versionnée avec le code. Alimentée par `doc-keeper` en fin de
pipeline. Les blackboards de teams (`.agent-team/`, `.seo-team/`) sont éphémères : ce qui
compte durablement est ici.

- [architecture.md](architecture.md) — décisions structurantes et leur justification
- [pieges-projet.md](pieges-projet.md) — pièges spécifiques à ce projet
- [journal.md](journal.md) — une entrée datée par run de team

Ce wiki couvre le **pourquoi**. Le **quoi** (stack, commandes, conventions de branches) vit
dans `CLAUDE.md` et `AGENTS.md` à la racine ; les pièges technologiques réutilisables hors de
ce projet vivent dans la skill globale `stack-pitfalls`.

## Convention de références dans le code

De nombreux commentaires du code renvoient à `plan.md § X`, à `implementation.md` ou à une revue
(`review-j2-finale.md § 🟡 n°6`). Ces fichiers sont ceux du **dossier de conception**
(`.agent-team/`, `contexte/`), volontairement non versionnés : ils sont éphémères et réécrits à
chaque run de team. Leur équivalent durable et public est ici :

| Référence dans le code | Équivalent public |
|---|---|
| `plan.md § 3.7`, § 5.2, § 5.3 (couche analytique, formule de marge, automate) | [architecture.md](architecture.md) — sections correspondantes |
| `implementation.md`, `review*.md` (constats de revue, pièges rencontrés) | [pieges-projet.md](pieges-projet.md) et [journal.md](journal.md) |

Une référence introuvable n'est donc pas un lien mort : c'est une note de conception dont la
substance a été condensée dans ce wiki.
