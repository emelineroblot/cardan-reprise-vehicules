-- Modèle : analytics.mart_pipeline_etat
-- Grain : 1 ligne par état du véhicule (public.vehicle.state, 11 valeurs possibles — les états
-- absents du parc à l'instant du dernier REFRESH ne produisent simplement aucune ligne, le
-- Kanban lui-même complète les colonnes vides côté API opérationnelle, jamais depuis ce mart :
-- il lit `vehicle` en direct, voir `app/api/v1/vehicles.py::pipeline_counts`).
-- Contenu : nombre de véhicules et valeur immobilisée (achat + transport, hors coûts atelier non
-- encore engagés) par état — vue d'ensemble du pipeline pour le dashboard.
CREATE MATERIALIZED VIEW analytics.mart_pipeline_etat AS
SELECT
    v.state,
    COUNT(*) AS nb_vehicules,
    SUM(COALESCE(v.prix_achat_negocie_cents, 0) + v.frais_transport_cents)::bigint
        AS valeur_immobilisee_cents
FROM analytics.stg_vehicules v
GROUP BY v.state;

CREATE UNIQUE INDEX ix_mart_pipeline_etat_state
    ON analytics.mart_pipeline_etat (state);
