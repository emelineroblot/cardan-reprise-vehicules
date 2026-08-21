-- Modèle : analytics.mart_travaux
-- Grain : 1 ligne par (mois de demande × type de travaux).
-- Contenu : coût moyen des travaux (brief J3) et écart estimé/réel. Le coût moyen et l'écart ne
-- sont calculés que sur les ordres clos (`termine`/`annule`, seuls états où le coût réel est
-- garanti non nul par construction — `app/services/work_orders.py` refuse la clôture sans ligne
-- de coût) : un ordre encore `demande`/`en_cours` a un coût réel de 0 dans `stg_travaux`
-- (COALESCE), l'inclure dans une moyenne biaiserait "coût moyen" vers le bas sans le signaler.
-- `AVG(...) FILTER (...)` renvoie NULL, jamais 0, quand aucun ordre clos ce mois-là pour ce type.
CREATE MATERIALIZED VIEW analytics.mart_travaux AS
SELECT
    date_trunc('month', t.requested_at)::date AS mois,
    t.type,
    COUNT(*) AS volume,
    COUNT(*) FILTER (WHERE t.state IN ('termine', 'annule')) AS nb_clos,
    round(AVG(t.montant_reel_cents) FILTER (WHERE t.state IN ('termine', 'annule')))
        AS cout_moyen_reel_cents,
    round(
        AVG(t.montant_reel_cents - t.montant_estime_cents)
        FILTER (WHERE t.state IN ('termine', 'annule') AND t.montant_estime_cents IS NOT NULL)
    ) AS ecart_estime_reel_cents
FROM analytics.stg_travaux t
GROUP BY date_trunc('month', t.requested_at), t.type;

CREATE UNIQUE INDEX ix_mart_travaux_mois_type
    ON analytics.mart_travaux (mois, type);
