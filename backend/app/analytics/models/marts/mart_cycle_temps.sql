-- Modèle : analytics.mart_cycle_temps
-- Grain : 1 ligne par véhicule.
-- Contenu : délai de cycle (brief J3) — de la création de la fiche à la validation d'achat,
-- décomposé par étape à partir de l'historique réel des transitions (public.vehicle_state_
-- transition, plan.md § 5.3 : "pas de trace = pas de délai de cycle calculable en J3"). Chaque
-- délai est NULL tant que l'étape suivante n'a pas été atteinte — jamais 0 (même convention que
-- la marge : une étape non franchie est une valeur manquante, pas une durée nulle).
--
-- Bug corrigé (revue J3, 🟠 n°3 — "la donnée est corrigée, la cause ne l'est pas") : le point de
-- départ du cycle était `public.vehicle.created_at`, colonne à `server_default now()`. Le seed
-- J3 avait aligné cette colonne sur la première transition rétrodatée pour faire disparaître le
-- symptôme (délais négatifs), mais le mart continuait de dépendre d'une colonne posée par le
-- SGBD au moment de l'INSERT — n'importe quelle future écriture (seed ou service applicatif) qui
-- oublierait cet alignement réintroduirait des délais négatifs sans qu'aucune défense n'existe
-- ici. La source de vérité du début de cycle est l'historique lui-même
-- (`vehicle_state_transition`, déjà la source de `affecte_at`/`controle_at`/`decision_at`
-- ci-dessous) : `saisie_at` est désormais la première transition vers `BROUILLON` de CE
-- véhicule, avec repli sur `v.created_at` seulement si — cas qui ne devrait jamais se produire,
-- l'automate écrit toujours cette transition à la création — aucune n'existe. Le mart devient
-- ainsi auto-cohérent : il ne peut plus contredire son propre historique.
CREATE MATERIALIZED VIEW analytics.mart_cycle_temps AS
WITH premieres_etapes AS (
    SELECT
        vehicle_id,
        MIN(occurred_at) FILTER (WHERE to_state = 'BROUILLON') AS saisie_at,
        MIN(occurred_at) FILTER (WHERE to_state = 'AFFECTE') AS affecte_at,
        MIN(occurred_at) FILTER (WHERE to_state = 'CONTROLE_EN_COURS') AS controle_at,
        MIN(occurred_at) FILTER (
            WHERE to_state IN ('ACHAT_VALIDE', 'REFUSE', 'ANNULE')
        ) AS decision_at
    FROM analytics.stg_transitions
    GROUP BY vehicle_id
)
SELECT
    v.vehicle_id,
    v.reference,
    v.state,
    v.marque,
    v.modele,
    v.created_at,
    COALESCE(e.saisie_at, v.created_at) AS saisie_at,
    e.affecte_at,
    e.controle_at,
    e.decision_at,
    round(
        EXTRACT(EPOCH FROM (e.affecte_at - COALESCE(e.saisie_at, v.created_at))) / 3600.0, 1
    ) AS delai_saisie_affectation_heures,
    round(EXTRACT(EPOCH FROM (e.controle_at - e.affecte_at)) / 3600.0, 1)
        AS delai_affectation_controle_heures,
    round(EXTRACT(EPOCH FROM (e.decision_at - e.controle_at)) / 3600.0, 1)
        AS delai_controle_decision_heures,
    round(
        EXTRACT(EPOCH FROM (e.decision_at - COALESCE(e.saisie_at, v.created_at))) / 3600.0, 1
    ) AS delai_total_heures
FROM analytics.stg_vehicules v
LEFT JOIN premieres_etapes e ON e.vehicle_id = v.vehicle_id;

CREATE UNIQUE INDEX ix_mart_cycle_temps_vehicle
    ON analytics.mart_cycle_temps (vehicle_id);
