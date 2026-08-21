-- Modèle : analytics.stg_missions
-- Grain : 1 ligne par mission (public.mission).
-- Nettoyage/typage léger, aucune agrégation.
CREATE VIEW analytics.stg_missions AS
SELECT
    m.id AS mission_id,
    m.vehicle_id,
    m.driver_id,
    m.state,
    m.assigned_at,
    m.accepted_at,
    m.completed_at,
    m.rdv_at
FROM public.mission m;
