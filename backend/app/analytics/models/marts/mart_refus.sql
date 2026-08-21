-- Modèle : analytics.mart_refus
-- Grain : 1 ligne par (mois de proposition × type de flotte).
-- Contenu : taux de refus (brief J3) — "un véhicule refusé sort du pipeline mais reste compté
-- dans le taux de refus ; REFUSE et ANNULE sont distincts, seul le premier y entre" (plan.md
-- § 5.3). `ANNULE` (vendeur rétracté, doublon confirmé) est donc exclu du dénominateur ET du
-- numérateur — ce n'est ni un achat ni un refus métier, c'est une fiche qui n'aurait pas dû être
-- comparée. `taux_refus` reste NULL (jamais 0) quand aucun véhicule proposé ce mois-là pour ce
-- type de flotte n'a encore atteint un état comptabilisable.
CREATE MATERIALIZED VIEW analytics.mart_refus AS
SELECT
    date_trunc('month', v.date_proposition)::date AS mois,
    COALESCE(s.type_flotte, 'autre') AS type_flotte,
    COUNT(*) FILTER (WHERE v.state <> 'ANNULE') AS nb_proposes,
    COUNT(*) FILTER (WHERE v.state = 'REFUSE') AS nb_refuses,
    CASE
        WHEN COUNT(*) FILTER (WHERE v.state <> 'ANNULE') = 0 THEN NULL
        ELSE round(
            COUNT(*) FILTER (WHERE v.state = 'REFUSE')::numeric
            / COUNT(*) FILTER (WHERE v.state <> 'ANNULE'), 4
        )
    END AS taux_refus
FROM analytics.stg_vehicules v
JOIN analytics.stg_societes s ON s.company_id = v.company_id
GROUP BY date_trunc('month', v.date_proposition), COALESCE(s.type_flotte, 'autre');

CREATE UNIQUE INDEX ix_mart_refus_mois_type_flotte
    ON analytics.mart_refus (mois, type_flotte);
