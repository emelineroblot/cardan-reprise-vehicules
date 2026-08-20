-- Modèle : analytics.mart_saisie_quotidienne
-- Grain : 1 ligne par (jour de proposition × opératrice ayant créé la fiche).
-- Contenu : volume de fiches créées — mart de fumée J1 (plan.md § 3.7-7), juste assez pour
-- prouver la chaîne de bout en bout (stg_* -> mart_*) et garantir que J3 n'aura qu'à ajouter
-- des fichiers .sql supplémentaires au manifeste.
-- Index unique obligatoire (prérequis de REFRESH MATERIALIZED VIEW CONCURRENTLY).
CREATE MATERIALIZED VIEW analytics.mart_saisie_quotidienne AS
SELECT
    v.date_proposition AS jour,
    v.created_by_id AS operatrice_id,
    u.full_name AS operatrice_nom,
    count(*) AS nb_fiches
FROM analytics.stg_vehicules v
JOIN public.app_user u ON u.id = v.created_by_id
GROUP BY v.date_proposition, v.created_by_id, u.full_name;

CREATE UNIQUE INDEX ix_mart_saisie_quotidienne_jour_operatrice
    ON analytics.mart_saisie_quotidienne (jour, operatrice_id);
