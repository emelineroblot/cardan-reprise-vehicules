-- Modèle : analytics.stg_couts
-- Grain : 1 ligne par coût hors atelier (public.vehicle_cost).
-- Nettoyage/typage léger, aucune agrégation.
CREATE VIEW analytics.stg_couts AS
SELECT
    c.id AS cost_id,
    c.vehicle_id,
    c.type,
    c.montant_cents,
    c.created_at
FROM public.vehicle_cost c;
