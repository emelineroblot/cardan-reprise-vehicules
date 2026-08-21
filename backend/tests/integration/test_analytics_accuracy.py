"""Exactitude numérique du tableau de bord (brief J3 § critères d'acceptation) — le cœur de ce
jalon n'est pas « l'endpoint répond 200 » (déjà couvert par `test_analytics_endpoints.py`, écrit
en réaction au 🔴 `AmbiguousParameter`) mais « le chiffre affiché est le bon ». Un chiffre faux
est pire qu'une fonctionnalité manquante (consigne explicite de l'orchestrateur pour ce jalon).

Principe appliqué : recalculer chaque indicateur **à la main**, à partir des tables opérationnelles
brutes (`public.vehicle`, `public.vehicle_cost`, `public.work_order`/`work_order_line`,
`public.vehicle_state_transition`, `public.company`), en Python, indépendamment du SQL des
`stg_*`/`mart_*` — puis comparer au résultat réellement renvoyé par `GET /analytics/*` (HTTP, pas
la fonction interne). Ne jamais se contenter de vérifier que le mart est cohérent avec lui-même :
un mart peut être parfaitement cohérent et calculer la mauvaise formule.

Un seul `run_demo_reset()` réel pour tout le module (coûteux : ~90 véhicules, atelier, coûts,
analytics build+refresh) — fixture `module`, données lues seules ensuite dans chaque test, jamais
mutées. Nettoyage en fin de module (`TRUNCATE`), même mécanisme que `test_demo_reset.py` (§ 4
décision F : `run_demo_reset()` commite réellement, hors de la transaction-par-test).
"""

from __future__ import annotations

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.enums import UserRole
from app.seed.reset import OPERATIONAL_TABLES, run_demo_reset
from tests.conftest import login_client, make_user


def _truncate_all(engine) -> None:
    table_list = ", ".join(f"public.{name}" for name in OPERATIONAL_TABLES)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {table_list} RESTART IDENTITY CASCADE"))


@pytest.fixture(scope="module")
def demo_seeded(engine):
    result = run_demo_reset()
    assert result["status"] == "succes", result
    try:
        yield result
    finally:
        _truncate_all(engine)


def _admin_client(client: TestClient, db_session: Session) -> TestClient:
    admin = make_user(db_session, UserRole.ADMINISTRATEUR)
    return login_client(client, admin)


# ---------------------------------------------------------------------------
# Marge par véhicule — cœur de la démonstration (brief J3).
# ---------------------------------------------------------------------------


def _raw_margin_inputs(engine) -> tuple[dict, dict, dict]:
    """Relit les tables brutes indépendamment de `analytics.stg_couts`/`stg_travaux` : les
    sommes sont refaites ici, en Python, pas déléguées à une vue qui pourrait partager le même
    bug que le mart qu'on est en train de vérifier."""
    with engine.connect() as conn:
        vehicles = conn.execute(
            text(
                """
                SELECT id, prix_achat_negocie_cents, frais_transport_cents,
                       valeur_revente_estimee_cents
                FROM public.vehicle
                """
            )
        ).all()
        costs = conn.execute(
            text("SELECT vehicle_id, montant_cents FROM public.vehicle_cost")
        ).all()
        lines = conn.execute(
            text(
                """
                SELECT wo.vehicle_id, wol.montant_cents
                FROM public.work_order wo
                JOIN public.work_order_line wol ON wol.work_order_id = wo.id
                """
            )
        ).all()

    hors_atelier: dict[str, int] = defaultdict(int)
    for vehicle_id, montant_cents in costs:
        hors_atelier[str(vehicle_id)] += montant_cents

    atelier_reel: dict[str, int] = defaultdict(int)
    for vehicle_id, montant_cents in lines:
        atelier_reel[str(vehicle_id)] += montant_cents

    vehicles_by_id = {
        str(v.id): (
            v.prix_achat_negocie_cents,
            v.frais_transport_cents,
            v.valeur_revente_estimee_cents,
        )
        for v in vehicles
    }
    return vehicles_by_id, hors_atelier, atelier_reel


def test_marge_matches_hand_computed_value_for_every_vehicle(
    client: TestClient, db_session: Session, engine, demo_seeded
) -> None:
    """Recalcul indépendant de la marge de CHAQUE véhicule du jeu de démo, comparé à
    `GET /analytics/marge` — pas seulement « la formule est cohérente avec elle-même »."""
    _admin_client(client, db_session)
    response = client.get("/api/v1/analytics/marge")
    assert response.status_code == 200, response.text
    api_rows = {row["vehicle_id"]: row for row in response.json()}

    vehicles_by_id, hors_atelier, atelier_reel = _raw_margin_inputs(engine)
    assert len(vehicles_by_id) == 90, "le seed de démo doit produire 90 véhicules"
    assert len(api_rows) == 90

    checked_negative = 0
    checked_null = 0
    checked_null_no_prix_achat = 0
    for vehicle_id, (prix_achat, frais_transport, valeur_revente) in vehicles_by_id.items():
        row = api_rows[vehicle_id]
        cout_hors_atelier = hors_atelier.get(vehicle_id, 0)
        cout_atelier = atelier_reel.get(vehicle_id, 0)

        assert row["cout_hors_atelier_cents"] == cout_hors_atelier, vehicle_id
        assert row["cout_atelier_reel_cents"] == cout_atelier, vehicle_id

        # Périmètre (revue J3, 🔴 n°1 — "le bon calcul appliqué aux mauvaises lignes") : une
        # marge n'a de sens que pour un véhicule ayant un prix d'achat négocié ET une valeur de
        # revente estimée. Recalculer avec `(prix_achat or 0)` comme le faisait l'ancienne
        # version de ce test aurait continué à valider la formule bogguée — ce test recalcule
        # désormais lui aussi le PÉRIMÈTRE, pas seulement l'arithmétique une fois le périmètre
        # admis.
        if valeur_revente is None or prix_achat is None:
            assert row["has_marge"] is False, vehicle_id
            assert row["marge_cents"] is None, (
                f"véhicule {vehicle_id} sans valeur de revente estimée ou sans prix d'achat "
                f"négocié : marge_cents doit être NULL, jamais une valeur calculée à partir "
                f"d'un zéro implicite — obtenu {row['marge_cents']!r}"
            )
            assert row["marge_pct"] is None, vehicle_id
            checked_null += 1
            if valeur_revente is not None and prix_achat is None:
                checked_null_no_prix_achat += 1
            continue

        expected_marge_cents = (
            valeur_revente - prix_achat - (frais_transport or 0) - cout_hors_atelier - cout_atelier
        )
        assert row["has_marge"] is True, vehicle_id
        assert row["marge_cents"] == expected_marge_cents, (
            f"véhicule {vehicle_id} : marge recalculée à la main {expected_marge_cents}, "
            f"API renvoie {row['marge_cents']}"
        )
        if expected_marge_cents < 0:
            checked_negative += 1

        if valeur_revente == 0:
            assert row["marge_pct"] is None, vehicle_id
        else:
            expected_pct = float(
                (Decimal(expected_marge_cents) / Decimal(valeur_revente) * 100).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            )
            assert row["marge_pct"] == pytest.approx(expected_pct, abs=0.01), vehicle_id

    # Les deux règles non négociables de la formule (plan.md § 5.2) doivent être exercées
    # réellement par le jeu de démo, pas seulement possibles en théorie.
    assert checked_null > 0, "aucun véhicule sans valeur de revente estimée dans le seed"
    assert checked_negative > 0, "aucune marge négative dans le seed (garantie par construction)"
    # Le cas qui a précisément échappé à la version bogguée du mart : un véhicule avec une
    # valeur de revente estimée mais SANS prix d'achat négocié (jamais acheté) doit être présent
    # dans le seed et doit ressortir en `has_marge = False` — sinon ce test ne couvrirait le
    # périmètre que "en théorie".
    assert checked_null_no_prix_achat > 0, (
        "aucun véhicule avec valeur de revente mais sans prix d'achat dans le seed — le "
        "périmètre de la marge (bug 🔴 n°1) ne serait pas réellement exercé par ce test"
    )


def test_marge_perimeter_excludes_vehicles_never_purchased(
    client: TestClient, db_session: Session, demo_seeded
) -> None:
    """Test de PÉRIMÈTRE, pas de formule (revue J3, 🔴 n°1) : aucun véhicule qui n'a jamais été
    acheté (pas de `prix_achat_negocie_cents`) ne doit apparaître avec `has_marge = true`, quel
    que soit son état. C'est le défaut exact qui faussait la tuile « Marge moyenne » d'un facteur
    4,5 — validé ici indépendamment de `test_marge_matches_hand_computed_value_for_every_vehicle`
    pour qu'une régression future sur ce point précis ne puisse pas se noyer dans un test plus
    large."""
    _admin_client(client, db_session)
    response = client.get("/api/v1/analytics/marge")
    assert response.status_code == 200, response.text
    rows = response.json()

    never_purchased_states = {
        "BROUILLON",
        "A_PLANIFIER",
        "AFFECTE",
        "RDV_PLANIFIE",
        "CONTROLE_EN_COURS",
        "REFUSE",
        "ANNULE",
    }
    offenders = [r for r in rows if r["state"] in never_purchased_states and r["has_marge"] is True]
    assert not offenders, (
        f"{len(offenders)} véhicule(s) jamais acheté(s) affiché(s) avec une marge réelle : "
        f"{[r['reference'] for r in offenders]}"
    )
    # Le jeu de démo doit réellement contenir des véhicules dans ces états pour que l'assertion
    # ci-dessus ne soit pas vide de sens.
    assert any(r["state"] in never_purchased_states for r in rows)


def test_negative_margin_lands_on_a_purchased_vehicle(
    client: TestClient, db_session: Session, demo_seeded
) -> None:
    """Régression directe du 🔴 n°2 (revue J3) : la marge négative garantie par le seed
    (`_force_at_least_one_negative_margin`) doit porter sur un véhicule `ACHAT_VALIDE` — jamais
    `REFUSE` ("nous avons perdu de l'argent sur une voiture que nous n'avons pas achetée" est
    absurde métier)."""
    _admin_client(client, db_session)
    response = client.get("/api/v1/analytics/marge")
    assert response.status_code == 200, response.text
    rows = response.json()

    negative_rows = [r for r in rows if r["marge_cents"] is not None and r["marge_cents"] < 0]
    assert negative_rows, "aucune marge négative dans le seed (garantie par construction)"
    for row in negative_rows:
        assert row["state"] == "ACHAT_VALIDE", (
            f"marge négative sur {row['reference']} en état {row['state']!r} — une perte n'a de "
            "sens que sur un véhicule réellement acheté"
        )
        assert row["prix_achat_negocie_cents"] is not None, row["reference"]

    # La magnitude doit rester comparable aux marges positives du jeu de démo pour rester
    # visible dans un graphique trié par |marge| — pas dix fois trop petite (revue J3, 🔴 n°2).
    positive_rows = [r for r in rows if r["marge_cents"] is not None and r["marge_cents"] > 0]
    top12_abs = sorted((abs(r["marge_cents"]) for r in positive_rows), reverse=True)[:12]
    smallest_of_top12 = min(top12_abs) if top12_abs else 0
    largest_negative_abs = max(abs(r["marge_cents"]) for r in negative_rows)
    assert largest_negative_abs >= smallest_of_top12 * 0.1, (
        f"marge négative la plus forte ({largest_negative_abs} centimes) trop petite face au "
        f"top 12 des marges positives (plus petite valeur : {smallest_of_top12} centimes) pour "
        "être visible sur un graphique trié par magnitude"
    )


def test_marge_negative_is_not_clamped_to_zero(
    client: TestClient, db_session: Session, demo_seeded
) -> None:
    """Régression directe du piège classique d'un tableau de bord de marge : un `Math.max(0, …)`
    ou un `GREATEST(0, …)` quelque part masquerait silencieusement les marges négatives."""
    _admin_client(client, db_session)
    response = client.get("/api/v1/analytics/marge", params={"sort": "marge_cents"})
    assert response.status_code == 200, response.text
    rows = response.json()
    negative_rows = [r for r in rows if r["marge_cents"] is not None and r["marge_cents"] < 0]
    assert negative_rows, "aucune marge strictement négative renvoyée par l'API"
    assert rows[0]["marge_cents"] == min(
        r["marge_cents"] for r in rows if r["marge_cents"] is not None
    ), "tri ascendant par marge_cents incohérent"


def test_marge_filter_by_state_returns_only_matching_state(
    client: TestClient, db_session: Session, demo_seeded
) -> None:
    _admin_client(client, db_session)
    response = client.get("/api/v1/analytics/marge", params={"state": "ACHAT_VALIDE"})
    assert response.status_code == 200, response.text
    rows = response.json()
    assert rows, "aucun véhicule ACHAT_VALIDE dans le seed"
    assert all(r["state"] == "ACHAT_VALIDE" for r in rows)


# ---------------------------------------------------------------------------
# Délai de cycle — aucun délai négatif (régression du bug `vehicle.created_at`).
# ---------------------------------------------------------------------------


def test_cycle_temps_has_no_negative_delay(
    client: TestClient, db_session: Session, demo_seeded
) -> None:
    """Écrit pour échouer si le bug consigné dans `implementation.md` (« J3 — Backend » §
    « Bug trouvé et corrigé pendant l'implémentation ») réapparaît : `vehicle.created_at` retombé
    sur `server_default now()` au lieu du premier maillon de la frise backdatée produirait à
    nouveau des délais négatifs."""
    _admin_client(client, db_session)
    response = client.get("/api/v1/analytics/cycle-temps")
    assert response.status_code == 200, response.text
    rows = response.json()
    assert rows, "le seed de démo doit produire des véhicules"

    fields = (
        "delai_saisie_affectation_heures",
        "delai_affectation_controle_heures",
        "delai_controle_decision_heures",
        "delai_total_heures",
    )
    negative = [
        (row["vehicle_id"], field, row[field])
        for row in rows
        for field in fields
        if row[field] is not None and row[field] < 0
    ]
    assert not negative, f"délai de cycle négatif détecté (régression) : {negative}"


def test_cycle_temps_delai_total_matches_hand_computed_value(
    client: TestClient, db_session: Session, engine, demo_seeded
) -> None:
    """Recalcul indépendant du délai total (création -> décision) pour chaque véhicule ayant
    atteint une décision, à partir de `vehicle.created_at` et de l'historique brut des
    transitions — pas seulement « pas négatif », mais « la bonne valeur »."""
    _admin_client(client, db_session)
    response = client.get("/api/v1/analytics/cycle-temps")
    assert response.status_code == 200, response.text
    rows = {row["vehicle_id"]: row for row in response.json()}

    with engine.connect() as conn:
        vehicles = conn.execute(text("SELECT id, created_at FROM public.vehicle")).all()
        decisions = conn.execute(
            text(
                """
                SELECT vehicle_id, MIN(occurred_at) AS decision_at
                FROM public.vehicle_state_transition
                WHERE to_state IN ('ACHAT_VALIDE', 'REFUSE', 'ANNULE')
                GROUP BY vehicle_id
                """
            )
        ).all()
    decision_by_vehicle = {str(vehicle_id): decision_at for vehicle_id, decision_at in decisions}

    checked = 0
    for vehicle_id, created_at in vehicles:
        vehicle_id = str(vehicle_id)
        row = rows[vehicle_id]
        decision_at = decision_by_vehicle.get(vehicle_id)
        if decision_at is None:
            assert (
                row["delai_total_heures"] is None
            ), f"véhicule {vehicle_id} sans décision : delai_total_heures doit être NULL"
            continue
        expected_hours = round((decision_at - created_at).total_seconds() / 3600.0, 1)
        assert row["delai_total_heures"] == pytest.approx(expected_hours, abs=0.05), vehicle_id
        assert row["delai_total_heures"] >= 0, vehicle_id
        checked += 1

    assert checked >= 10, "trop peu de véhicules avec décision pour une vérification significative"


# ---------------------------------------------------------------------------
# Taux de refus — REFUSE compté, ANNULE exclu (numérateur ET dénominateur).
# ---------------------------------------------------------------------------


def test_refus_rate_counts_refuse_not_annule(
    client: TestClient, db_session: Session, engine, demo_seeded
) -> None:
    _admin_client(client, db_session)
    response = client.get("/api/v1/analytics/refus")
    assert response.status_code == 200, response.text
    api_rows = {(row["mois"], row["type_flotte"]): row for row in response.json()}

    with engine.connect() as conn:
        raw = conn.execute(
            text(
                """
                SELECT date_trunc('month', v.date_proposition)::date AS mois,
                       COALESCE(c.type_flotte, 'autre') AS type_flotte,
                       v.state
                FROM public.vehicle v
                JOIN public.company c ON c.id = v.company_id
                """
            )
        ).all()

    groups: dict[tuple[str, str], dict[str, int]] = defaultdict(
        lambda: {"proposes": 0, "refuses": 0, "annule": 0}
    )
    for mois, type_flotte, state in raw:
        key = (mois.isoformat(), type_flotte)
        if state != "ANNULE":
            groups[key]["proposes"] += 1
        if state == "REFUSE":
            groups[key]["refuses"] += 1
        if state == "ANNULE":
            groups[key]["annule"] += 1

    total_annule = sum(g["annule"] for g in groups.values())
    total_refuse = sum(g["refuses"] for g in groups.values())
    assert total_annule > 0, "le seed doit produire au moins un véhicule ANNULE pour ce test"
    assert total_refuse > 0, "le seed doit produire au moins un véhicule REFUSE pour ce test"

    for key, counts in groups.items():
        row = api_rows.get(key)
        if counts["proposes"] == 0:
            # Groupe entièrement composé d'ANNULE : soit absent du mart, soit présent avec
            # nb_proposes=0 et taux_refus NULL — jamais 0 (une "valeur manquante" n'est pas un
            # taux de refus nul).
            if row is not None:
                assert row["nb_proposes"] == 0
                assert row["taux_refus"] is None
            continue

        assert row is not None, f"couple {key} absent de GET /analytics/refus"
        assert row["nb_proposes"] == counts["proposes"], key
        assert row["nb_refuses"] == counts["refuses"], key
        expected_taux = round(counts["refuses"] / counts["proposes"], 4)
        assert row["taux_refus"] == pytest.approx(expected_taux, abs=1e-6), key

    # ANNULE exclu du numérateur ET du dénominateur, littéralement : la somme des `nb_proposes`
    # exposés par l'API est strictement inférieure au nombre total de véhicules (puisque des
    # ANNULE existent), et vaut exactement total - annulés.
    total_vehicles = len(raw)
    api_total_proposes = sum(row["nb_proposes"] for row in api_rows.values())
    api_total_refuses = sum(row["nb_refuses"] for row in api_rows.values())
    assert api_total_proposes == total_vehicles - total_annule
    assert api_total_proposes < total_vehicles
    assert api_total_refuses == total_refuse


# ---------------------------------------------------------------------------
# `mart_kpi_global` — cohérence avec les marts dont il dépend (pas un second calcul divergent).
# ---------------------------------------------------------------------------


def test_kpi_global_marge_moyenne_matches_marge_endpoint_average(
    client: TestClient, db_session: Session, demo_seeded
) -> None:
    """`mart_kpi_global.marge_moyenne_cents`/`nb_marges_negatives` doivent être cohérents avec le
    détail exposé par `GET /analytics/marge` — deux lectures indépendantes de la même vérité, pas
    deux calculs qui pourraient diverger silencieusement."""
    _admin_client(client, db_session)
    marge_response = client.get("/api/v1/analytics/marge")
    kpi_response = client.get("/api/v1/analytics/kpi-global")
    assert marge_response.status_code == 200, marge_response.text
    assert kpi_response.status_code == 200, kpi_response.text

    marges = [r["marge_cents"] for r in marge_response.json() if r["marge_cents"] is not None]
    assert marges, "aucun véhicule avec marge calculable dans le seed"

    kpi = kpi_response.json()
    expected_average = round(sum(marges) / len(marges))
    assert kpi["marge_moyenne_cents"] == pytest.approx(expected_average, abs=1), (
        f"marge moyenne recalculée {expected_average}, kpi-global renvoie "
        f"{kpi['marge_moyenne_cents']}"
    )
    assert kpi["nb_marges_negatives"] == sum(1 for m in marges if m < 0)


def test_kpi_global_taux_refus_matches_refus_endpoint(
    client: TestClient, db_session: Session, demo_seeded
) -> None:
    _admin_client(client, db_session)
    refus_response = client.get("/api/v1/analytics/refus")
    kpi_response = client.get("/api/v1/analytics/kpi-global")
    assert refus_response.status_code == 200, refus_response.text
    assert kpi_response.status_code == 200, kpi_response.text

    refus_rows = refus_response.json()
    total_proposes = sum(r["nb_proposes"] for r in refus_rows)
    total_refuses = sum(r["nb_refuses"] for r in refus_rows)
    expected_taux = round(total_refuses / total_proposes, 4) if total_proposes else None

    kpi = kpi_response.json()
    if expected_taux is None:
        assert kpi["taux_refus_global"] is None
    else:
        assert kpi["taux_refus_global"] == pytest.approx(expected_taux, abs=1e-4)
    assert kpi["nb_refuses"] == total_refuses
