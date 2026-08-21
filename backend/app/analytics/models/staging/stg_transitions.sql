-- Modèle : analytics.stg_transitions
-- Grain : 1 ligne par transition d'état (public.vehicle_state_transition).
-- Nettoyage/typage léger, aucune agrégation — source du délai de cycle (mart_cycle_temps, J3).
CREATE VIEW analytics.stg_transitions AS
SELECT
    t.id AS transition_id,
    t.vehicle_id,
    t.from_state,
    t.to_state,
    t.actor_id,
    t.actor_role,
    t.occurred_at
FROM public.vehicle_state_transition t;
