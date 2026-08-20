-- Modèle : analytics.stg_vehicules
-- Grain : 1 ligne par véhicule (public.vehicle).
-- Nettoyage/typage léger + traduction des états en libellé lisible (plan.md § 3.7).
-- Aucune agrégation, aucun calcul de marge ici (réservé aux marts de J3).
CREATE VIEW analytics.stg_vehicules AS
SELECT
    v.id AS vehicle_id,
    v.reference,
    v.company_id,
    v.state,
    CASE v.state
        WHEN 'BROUILLON' THEN 'Brouillon'
        WHEN 'A_PLANIFIER' THEN 'À planifier'
        WHEN 'AFFECTE' THEN 'Affecté'
        WHEN 'RDV_PLANIFIE' THEN 'Rendez-vous planifié'
        WHEN 'CONTROLE_EN_COURS' THEN 'Contrôle en cours'
        WHEN 'TRAVAUX_REQUIS' THEN 'Travaux requis'
        WHEN 'TRAVAUX_EN_COURS' THEN 'Travaux en cours'
        WHEN 'TRAVAUX_TERMINES' THEN 'Travaux terminés'
        WHEN 'ACHAT_VALIDE' THEN 'Achat validé'
        WHEN 'REFUSE' THEN 'Refusé'
        WHEN 'ANNULE' THEN 'Annulé'
        ELSE v.state
    END AS state_label,
    v.marque,
    v.modele,
    v.date_proposition,
    v.created_by_id,
    v.assigned_driver_id,
    v.kilometrage,
    v.prix_achat_negocie_cents,
    v.valeur_revente_estimee_cents,
    v.frais_transport_cents,
    v.refus_motif,
    v.created_at
FROM public.vehicle v;
