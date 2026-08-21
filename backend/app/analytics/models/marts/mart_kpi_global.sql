-- Modèle : analytics.mart_kpi_global
-- Grain : 1 ligne unique (les tuiles du dashboard, plan.md § 5.2).
-- Dépend des autres marts J3 (déclarés avant lui dans manifest.yml — build()/refresh()
-- respectent cet ordre) plutôt que de recalculer : chaque tuile reste cohérente avec l'écran de
-- détail correspondant (marge véhicule, cycle, refus, travaux) sans dupliquer la logique SQL.
-- `snapshot_key` est une clé constante (toujours 1) : `REFRESH ... CONCURRENTLY` exige un index
-- unique même sur un mart à une seule ligne.
CREATE MATERIALIZED VIEW analytics.mart_kpi_global AS
SELECT
    1 AS snapshot_key,
    (SELECT COUNT(*) FROM analytics.stg_vehicules) AS nb_vehicules_total,
    (
        SELECT COUNT(*) FROM analytics.stg_vehicules
        WHERE state NOT IN ('ACHAT_VALIDE', 'REFUSE', 'ANNULE')
    ) AS nb_vehicules_actifs,
    (SELECT COUNT(*) FROM analytics.stg_vehicules WHERE state = 'ACHAT_VALIDE')
        AS nb_achats_valides,
    (SELECT COUNT(*) FROM analytics.stg_vehicules WHERE state = 'REFUSE') AS nb_refuses,
    (
        SELECT round(SUM(nb_refuses)::numeric / NULLIF(SUM(nb_proposes), 0), 4)
        FROM analytics.mart_refus
    ) AS taux_refus_global,
    (SELECT round(AVG(marge_cents)) FROM analytics.mart_vehicule_marge WHERE has_marge)
        AS marge_moyenne_cents,
    (SELECT COUNT(*) FROM analytics.mart_vehicule_marge WHERE has_marge AND marge_cents < 0)
        AS nb_marges_negatives,
    (SELECT round(AVG(delai_total_heures), 1) FROM analytics.mart_cycle_temps)
        AS delai_cycle_moyen_heures,
    (
        SELECT round(SUM(cout_moyen_reel_cents * nb_clos) / NULLIF(SUM(nb_clos), 0))
        FROM analytics.mart_travaux
    ) AS cout_travaux_moyen_cents;

CREATE UNIQUE INDEX ix_mart_kpi_global_snapshot
    ON analytics.mart_kpi_global (snapshot_key);
