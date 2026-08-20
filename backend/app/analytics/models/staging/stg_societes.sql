-- Modèle : analytics.stg_societes
-- Grain : 1 ligne par société (public.company).
-- Nettoyage/typage léger, aucune agrégation. Vue non matérialisée (plan.md § 3.7).
CREATE VIEW analytics.stg_societes AS
SELECT
    c.id AS company_id,
    c.siren,
    c.denomination,
    c.type_flotte,
    c.code_postal,
    c.commune,
    c.source_enrichissement,
    c.created_at
FROM public.company c;
