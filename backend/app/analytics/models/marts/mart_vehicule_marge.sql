-- Modèle : analytics.mart_vehicule_marge
-- Grain : 1 ligne par véhicule.
-- Contenu : marge par véhicule — prix d'achat négocié, frais de transport, coûts hors atelier
-- (public.vehicle_cost) et coûts d'atelier RÉELS (somme des work_order_line, jamais l'estimé),
-- confrontés à la valeur de revente estimée. Cœur de la démonstration J3 (brief § critères
-- d'acceptation).
--
-- Formule figée dès J1 (plan.md § 5.2), non négociable :
--   marge_cents = valeur_revente_estimee_cents
--               - COALESCE(prix_achat_negocie_cents, 0)
--               - COALESCE(frais_transport_cents, 0)
--               - COALESCE(Σ vehicle_cost.montant_cents, 0)
--               - COALESCE(Σ work_order_line.montant_cents, 0)   -- réel, jamais l'estimé
-- Deux règles non négociables : la marge PEUT être négative (aucun GREATEST(0, …)), et
-- `valeur_revente_estimee_cents IS NULL` donne `marge_cents = NULL` avec `has_marge = false` —
-- jamais 0. Confondre "pas de valeur" et "zéro" est le bug classique d'un tableau de bord de
-- marge (docs/wiki/architecture.md § Marge, .claude/instructions/analytics-sql.instructions.md).
--
-- Bug corrigé (revue J3, 🔴 n°1 — "tuile fausse d'un facteur 4,5") : `has_marge` ne testait que
-- `valeur_revente_estimee_cents`, alors que `prix_achat_negocie_cents` passait par
-- `COALESCE(…, 0)`. Un véhicule jamais acheté (BROUILLON/A_PLANIFIER/AFFECTE/RDV_PLANIFIE/
-- CONTROLE_EN_COURS/REFUSE/ANNULE — `prix_achat_negocie_cents IS NULL` par construction de
-- l'automate, aucune de leurs gardes ne l'exige) ressortait donc avec une "marge" égale à sa
-- valeur de revente estimée diminuée de quelques frais annexes, soit ~99-100 %. Ce n'était pas
-- une erreur d'arithmétique (le calcul lui-même reste exact, vérifié au centime par
-- `test_analytics_accuracy.py`) mais une erreur de PÉRIMÈTRE : une marge n'a de sens que pour un
-- véhicule réellement acheté. `has_marge` est donc désormais la conjonction des deux valeurs
-- requises par la formule (revente **et** achat) — les deux `CASE` ci-dessous renvoient `NULL`
-- dans les deux cas, jamais une valeur calculée à partir d'un `0` implicite. Les véhicules non
-- achetés restent dans le mart avec leurs coûts déjà engagés (`cout_hors_atelier_cents`,
-- `cout_atelier_reel_cents`), simplement sans marge — exactement le même traitement que les
-- véhicules sans valeur de revente.
CREATE MATERIALIZED VIEW analytics.mart_vehicule_marge AS
WITH couts_hors_atelier AS (
    SELECT vehicle_id, SUM(montant_cents)::bigint AS montant_cents
    FROM analytics.stg_couts
    GROUP BY vehicle_id
),
couts_atelier_reels AS (
    SELECT vehicle_id, SUM(montant_reel_cents)::bigint AS montant_cents
    FROM analytics.stg_travaux
    GROUP BY vehicle_id
)
SELECT
    v.vehicle_id,
    v.reference,
    v.company_id,
    s.denomination AS company_denomination,
    v.state,
    v.state_label,
    v.marque,
    v.modele,
    v.date_proposition,
    v.prix_achat_negocie_cents,
    v.frais_transport_cents,
    v.valeur_revente_estimee_cents,
    COALESCE(cha.montant_cents, 0) AS cout_hors_atelier_cents,
    COALESCE(car.montant_cents, 0) AS cout_atelier_reel_cents,
    CASE
        WHEN v.valeur_revente_estimee_cents IS NULL OR v.prix_achat_negocie_cents IS NULL THEN NULL
        ELSE v.valeur_revente_estimee_cents
            - v.prix_achat_negocie_cents
            - COALESCE(v.frais_transport_cents, 0)
            - COALESCE(cha.montant_cents, 0)
            - COALESCE(car.montant_cents, 0)
    END AS marge_cents,
    CASE
        WHEN v.valeur_revente_estimee_cents IS NULL OR v.valeur_revente_estimee_cents = 0
            OR v.prix_achat_negocie_cents IS NULL THEN NULL
        ELSE round(
            (
                (
                    v.valeur_revente_estimee_cents
                    - v.prix_achat_negocie_cents
                    - COALESCE(v.frais_transport_cents, 0)
                    - COALESCE(cha.montant_cents, 0)
                    - COALESCE(car.montant_cents, 0)
                )::numeric / v.valeur_revente_estimee_cents
            ) * 100, 2
        )
    END AS marge_pct,
    (v.valeur_revente_estimee_cents IS NOT NULL AND v.prix_achat_negocie_cents IS NOT NULL)
        AS has_marge
FROM analytics.stg_vehicules v
JOIN analytics.stg_societes s ON s.company_id = v.company_id
LEFT JOIN couts_hors_atelier cha ON cha.vehicle_id = v.vehicle_id
LEFT JOIN couts_atelier_reels car ON car.vehicle_id = v.vehicle_id;

CREATE UNIQUE INDEX ix_mart_vehicule_marge_vehicle
    ON analytics.mart_vehicule_marge (vehicle_id);
