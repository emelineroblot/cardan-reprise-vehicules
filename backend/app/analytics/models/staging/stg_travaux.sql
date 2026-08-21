-- Modèle : analytics.stg_travaux
-- Grain : 1 ligne par ordre de travaux (public.work_order), coût réel = somme de ses lignes.
-- Coût réel toujours agrégé ici (jamais à la volée dans un mart) : `montant_reel_cents` vaut 0,
-- pas NULL, quand aucune ligne n'existe encore (COALESCE) — un ordre encore "demande" a
-- légitimement 0 ligne, ce n'est pas une valeur manquante au sens de la marge (§ formule figée
-- en J1 : NULL réservé à "aucune valeur estimée", jamais à "pas encore de coût réel").
CREATE VIEW analytics.stg_travaux AS
SELECT
    wo.id AS work_order_id,
    wo.vehicle_id,
    wo.type,
    wo.state,
    wo.montant_estime_cents,
    wo.requested_at,
    wo.started_at,
    wo.completed_at,
    COALESCE(SUM(wol.montant_cents), 0)::bigint AS montant_reel_cents,
    COUNT(wol.id) AS nb_lignes
FROM public.work_order wo
LEFT JOIN public.work_order_line wol ON wol.work_order_id = wo.id
GROUP BY wo.id, wo.vehicle_id, wo.type, wo.state, wo.montant_estime_cents,
         wo.requested_at, wo.started_at, wo.completed_at;
