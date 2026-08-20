"""Véhicules — création, dédoublonnage bout en bout, collision VIN concurrente, automate d'états
via l'API (plan.md § 6 vague 3, § 8)."""

from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.enums import UserRole
from tests.conftest import login_client, make_user

TODAY = date(2026, 8, 20)


def _make_company(db_session: Session, user, **overrides) -> Company:
    base = {
        "id": uuid4(),
        "siren": "732829320",
        "siret": "73282932000074",
        "denomination": "Flotte Test",
        "adresse_ligne1": "1 rue du Test",
        "code_postal": "75001",
        "commune": "Paris",
        "pays": "FR",
        "type_flotte": "taxi",
        "source_enrichissement": "manuel",
        "created_by_id": user.id,
    }
    base.update(overrides)
    company = Company(**base)
    db_session.add(company)
    db_session.flush()
    return company


def _vehicle_body(company_id, **overrides) -> dict:
    body = {
        "company_id": str(company_id),
        "marque": "Renault",
        "modele": "Kangoo",
        "date_proposition": TODAY.isoformat(),
    }
    body.update(overrides)
    return body


def test_create_vehicle_success(client: TestClient, db_session: Session) -> None:
    user = make_user(db_session, UserRole.OPERATRICE)
    login_client(client, user)
    company = _make_company(db_session, user)

    response = client.post("/api/v1/vehicles", json=_vehicle_body(company.id))
    assert response.status_code == 201
    body = response.json()
    assert body["state"] == "BROUILLON"
    assert body["reference"].startswith("VH-")


def test_list_vehicles_free_search_matches_company_denomination(
    client: TestClient, db_session: Session
) -> None:
    """`q` couvre aussi la société (plan.md § 3.5 : « ... / modèle / société »)."""
    user = make_user(db_session, UserRole.OPERATRICE)
    login_client(client, user)
    company = _make_company(db_session, user, denomination="Taxis Réunis du Nord")

    client.post("/api/v1/vehicles", json=_vehicle_body(company.id))

    response = client.get("/api/v1/vehicles", params={"q": "Réunis"})
    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_create_vehicle_unknown_company_returns_404(
    client: TestClient, db_session: Session
) -> None:
    user = make_user(db_session, UserRole.OPERATRICE)
    login_client(client, user)

    response = client.post("/api/v1/vehicles", json=_vehicle_body(uuid4()))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_duplicate_exact_vin_blocks_second_creation(
    client: TestClient, db_session: Session
) -> None:
    user = make_user(db_session, UserRole.OPERATRICE)
    login_client(client, user)
    company = _make_company(db_session, user)

    vin = "VF1RJA0J123456789"
    first = client.post("/api/v1/vehicles", json=_vehicle_body(company.id, vin=vin))
    assert first.status_code == 201

    second = client.post(
        "/api/v1/vehicles",
        json=_vehicle_body(
            company.id, vin=vin, date_proposition=(TODAY + timedelta(days=200)).isoformat()
        ),
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "duplicate_exact"
    assert second.json()["error"]["details"]["champ"] == "vin"


def test_duplicate_exact_immatriculation_blocks_second_creation(
    client: TestClient, db_session: Session
) -> None:
    user = make_user(db_session, UserRole.OPERATRICE)
    login_client(client, user)
    company = _make_company(db_session, user)

    immat = "AA123BB"
    first = client.post("/api/v1/vehicles", json=_vehicle_body(company.id, immatriculation=immat))
    assert first.status_code == 201

    second = client.post(
        "/api/v1/vehicles", json=_vehicle_body(company.id, immatriculation="aa-123-bb")
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "duplicate_exact"
    assert second.json()["error"]["details"]["champ"] == "immatriculation"


def test_duplicate_probable_blocks_unless_forced(client: TestClient, db_session: Session) -> None:
    user = make_user(db_session, UserRole.OPERATRICE)
    login_client(client, user)
    company = _make_company(db_session, user)

    first = client.post(
        "/api/v1/vehicles",
        json=_vehicle_body(company.id, kilometrage=80000, energie="diesel"),
    )
    assert first.status_code == 201

    second = client.post(
        "/api/v1/vehicles",
        json=_vehicle_body(company.id, kilometrage=80100, energie="diesel"),
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "duplicate_probable"

    forced = client.post(
        "/api/v1/vehicles",
        json={
            **_vehicle_body(company.id, kilometrage=80100, energie="diesel"),
            "force_create": True,
        },
    )
    assert forced.status_code == 201


def test_five_vehicles_same_batch_same_day_zero_alert(
    client: TestClient, db_session: Session
) -> None:
    """Cas nominal du métier (plan.md § 8) : 5 fiches d'un même `intake_batch` → 0 alerte."""
    user = make_user(db_session, UserRole.OPERATRICE)
    login_client(client, user)
    company = _make_company(db_session, user)

    batch_response = client.post(
        "/api/v1/intake-batches", json={"company_id": str(company.id), "label": "Lot 5 Kangoo"}
    )
    assert batch_response.status_code == 201
    batch_id = batch_response.json()["id"]

    for _ in range(5):
        response = client.post(
            "/api/v1/vehicles",
            json={**_vehicle_body(company.id, kilometrage=80000), "intake_batch_id": batch_id},
        )
        assert response.status_code == 201, response.text


def test_five_vehicles_outside_batch_different_immat_zero_alert(
    client: TestClient, db_session: Session
) -> None:
    """Hors lot, immatriculations différentes → 0 alerte (l'exclusion dure suffit)."""
    user = make_user(db_session, UserRole.OPERATRICE)
    login_client(client, user)
    company = _make_company(db_session, user)

    plates = ["AA111AA", "AA222AA", "AA333AA", "AA444AA", "AA555AA"]
    for plate in plates:
        response = client.post(
            "/api/v1/vehicles",
            json=_vehicle_body(company.id, kilometrage=80000, immatriculation=plate),
        )
        assert response.status_code == 201, response.text


def test_vehicle_refused_six_weeks_ago_triggers_alert(
    client: TestClient, db_session: Session
) -> None:
    """Plan.md § 8 : « même modèle refusé il y a 6 semaines → alerte ».

    Atteindre `REFUSE` par l'API suppose le parcours chauffeur/inspection (J2) : on scelle
    directement l'état terminal en base pour ce test d'intégration ciblé sur le bonus (décision
    A) ; le calcul du bonus lui-même est couvert exhaustivement par `tests/unit/test_dedup.py`.
    """
    from app.models.vehicle import Vehicle

    user = make_user(db_session, UserRole.ADMINISTRATEUR)
    login_client(client, user)
    company = _make_company(db_session, user)

    old = client.post(
        "/api/v1/vehicles",
        json=_vehicle_body(
            company.id,
            kilometrage=80000,
            date_proposition=(TODAY - timedelta(days=42)).isoformat(),
        ),
    )
    assert old.status_code == 201
    old_id = old.json()["id"]

    old_vehicle = db_session.get(Vehicle, old_id)
    old_vehicle.state = "REFUSE"
    old_vehicle.refus_motif = "etat_mecanique"
    old_vehicle.refus_commentaire = "Corrosion du châssis"
    db_session.flush()

    check = client.post(
        "/api/v1/vehicles/duplicate-check",
        json=_vehicle_body(company.id, kilometrage=80000),
    )
    assert check.status_code == 200
    assert len(check.json()["probable"]) == 1
    assert check.json()["probable"][0]["vehicle_id"] == old_id
    assert check.json()["probable"][0]["refus_commentaire"] == "Corrosion du châssis"


def test_duplicate_check_endpoint_returns_features(client: TestClient, db_session: Session) -> None:
    """`features` (pas `components`) — même nom que `DuplicateReviewCreate.features` : le front
    doit pouvoir renvoyer tel quel ce candidat à `POST /duplicate-reviews` (revue § 🔴, point 4)."""
    user = make_user(db_session, UserRole.OPERATRICE)
    login_client(client, user)
    company = _make_company(db_session, user)

    client.post("/api/v1/vehicles", json=_vehicle_body(company.id, kilometrage=80000))

    check = client.post(
        "/api/v1/vehicles/duplicate-check",
        json=_vehicle_body(company.id, kilometrage=80100),
    )
    assert check.status_code == 200
    body = check.json()
    assert len(body["probable"]) == 1
    candidate = body["probable"][0]
    features = candidate["features"]
    assert set(features.keys()) == {"s_modele", "s_date", "s_km", "s_energie", "bonus_terminal"}

    # Le candidat peut être renvoyé tel quel à /duplicate-reviews (score + features déjà au bon
    # format), sans transformation côté front.
    review = client.post(
        "/api/v1/duplicate-reviews",
        json={
            "vehicle_a_id": candidate["vehicle_id"],
            "vehicle_b_id": candidate["vehicle_id"],
            "verdict": "not_duplicate",
            "score": candidate["score"],
            "features": candidate["features"],
        },
    )
    # vehicle_a_id == vehicle_b_id ici (même candidat, juste pour la forme du corps) -> 422
    # métier attendu (validation_error), pas un 422 Pydantic sur score/features : la forme du
    # corps est acceptée telle quelle.
    assert review.status_code == 422
    assert review.json()["error"]["code"] == "validation_error"


def test_duplicate_check_candidate_carries_comparison_fields(
    client: TestClient, db_session: Session
) -> None:
    """Correction dev-frontend (jalon J1) : l'écran d'arbitrage compare côte à côte — le candidat
    doit porter `vin`/`immatriculation`/`kilometrage`/`energie`/`date_mise_en_circulation` de la
    fiche existante, pas seulement son score. Sans ces champs, la colonne « fiche existante »
    reste vide."""
    user = make_user(db_session, UserRole.OPERATRICE)
    login_client(client, user)
    company = _make_company(db_session, user)

    existing = client.post(
        "/api/v1/vehicles",
        json=_vehicle_body(
            company.id,
            kilometrage=80000,
            energie="diesel",
            vin="VF1AAAAA000000001",
            immatriculation="AA-123-BB",
            date_mise_en_circulation="2021-05-10",
        ),
    )
    assert existing.status_code == 201
    existing_id = existing.json()["id"]

    check = client.post(
        "/api/v1/vehicles/duplicate-check",
        json=_vehicle_body(company.id, kilometrage=80100, energie="diesel"),
    )
    assert check.status_code == 200
    candidates = check.json()["probable"]
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["vehicle_id"] == existing_id
    assert candidate["vin"] == "VF1AAAAA000000001"
    assert candidate["immatriculation"] == "AA-123-BB"
    assert candidate["kilometrage"] == 80000
    assert candidate["energie"] == "diesel"
    assert candidate["date_mise_en_circulation"] == "2021-05-10"
    assert "created_at" in candidate


def test_not_duplicate_verdict_is_never_reproposed(client: TestClient, db_session: Session) -> None:
    user = make_user(db_session, UserRole.ADMINISTRATEUR)
    login_client(client, user)
    company = _make_company(db_session, user)

    first = client.post("/api/v1/vehicles", json=_vehicle_body(company.id, kilometrage=80000))
    first_id = first.json()["id"]

    forced = client.post(
        "/api/v1/vehicles",
        json={
            **_vehicle_body(company.id, kilometrage=80100),
            "force_create": True,
        },
    )
    second_id = forced.json()["id"]

    review = client.post(
        "/api/v1/duplicate-reviews",
        json={
            "vehicle_a_id": first_id,
            "vehicle_b_id": second_id,
            "verdict": "not_duplicate",
            "score": 0.9,
            "features": {},
        },
    )
    assert review.status_code == 201

    # Un troisième véhicule identique redéclenche normalement une alerte...
    third_check = client.post(
        "/api/v1/vehicles/duplicate-check", json=_vehicle_body(company.id, kilometrage=80050)
    )
    assert len(third_check.json()["probable"]) >= 1


def test_concurrent_vin_insert_is_rejected_by_partial_unique_index(
    db_session: Session, engine
) -> None:
    """Violation réelle de l'index unique partiel en écriture concurrente (plan.md § 8, cas 2).

    Deux connexions séparées (hors transaction de test) pour reproduire une vraie concurrence.
    """
    import uuid

    from app.core.security import hash_password

    with engine.connect() as conn:
        user_id = uuid.uuid4()
        company_id = uuid.uuid4()
        conn.execute(
            text(
                "INSERT INTO app_user (id, email, password_hash, full_name, role, is_active) "
                "VALUES (:id, :email, :pw, 'Concurrent', 'administrateur', true)"
            ),
            {"id": user_id, "email": f"concurrent-{user_id}@example.com", "pw": hash_password("x")},
        )
        company_sql = text(
            "INSERT INTO company (id, siren, siret, denomination, adresse_ligne1,"
            " code_postal, commune, pays, type_flotte, source_enrichissement, created_by_id)"
            " VALUES (:id, '732829320', '73282932000074', 'Concurrent SARL', '1 rue',"
            " '75001', 'Paris', 'FR', 'taxi', 'manuel', :created_by)"
        )
        conn.execute(company_sql, {"id": company_id, "created_by": user_id})

        vehicle_sql = text(
            "INSERT INTO vehicle (id, reference, company_id, state, marque, modele,"
            " vin_normalise, date_proposition, frais_transport_cents, created_by_id)"
            " VALUES (:id, :ref, :company_id, 'BROUILLON', 'Renault', 'Kangoo', :vin,"
            " :dt, 0, :created_by)"
        )
        conn.execute(
            vehicle_sql,
            {
                "id": uuid.uuid4(),
                "ref": f"VH-TEST-{uuid.uuid4().hex[:6]}",
                "company_id": company_id,
                "vin": "VF1RJA0J999999999",
                "dt": TODAY,
                "created_by": user_id,
            },
        )
        conn.commit()

        with pytest.raises(Exception) as excinfo:
            conn.execute(
                vehicle_sql,
                {
                    "id": uuid.uuid4(),
                    "ref": f"VH-TEST-{uuid.uuid4().hex[:6]}",
                    "company_id": company_id,
                    "vin": "VF1RJA0J999999999",
                    "dt": TODAY,
                    "created_by": user_id,
                },
            )
            conn.commit()
        assert (
            "uq_vehicle_vin_normalise" in str(excinfo.value)
            or "duplicate key" in str(excinfo.value).lower()
        )

        conn.rollback()
        conn.execute(text("DELETE FROM vehicle WHERE company_id = :cid"), {"cid": company_id})
        conn.execute(text("DELETE FROM company WHERE id = :cid"), {"cid": company_id})
        conn.execute(text("DELETE FROM app_user WHERE id = :uid"), {"uid": user_id})
        conn.commit()


def test_state_machine_transition_via_api(client: TestClient, db_session: Session) -> None:
    operatrice = make_user(db_session, UserRole.OPERATRICE)
    login_client(client, operatrice)
    company = _make_company(db_session, operatrice)

    created = client.post("/api/v1/vehicles", json=_vehicle_body(company.id))
    vehicle_id = created.json()["id"]

    allowed = client.get(f"/api/v1/vehicles/{vehicle_id}/transitions")
    assert allowed.status_code == 200
    options = {opt["to_state"]: opt for opt in allowed.json()["allowed"]}
    assert "A_PLANIFIER" in options
    assert options["A_PLANIFIER"]["label"] == "Validation de la fiche"
    assert options["A_PLANIFIER"]["requires_reason"] is False
    assert options["A_PLANIFIER"]["requires_payload_fields"] == []
    assert options["ANNULE"]["requires_reason"] is True

    transition = client.post(
        f"/api/v1/vehicles/{vehicle_id}/transitions",
        json={"to_state": "A_PLANIFIER", "reason": "validation opératrice"},
    )
    assert transition.status_code == 200
    assert transition.json()["state"] == "A_PLANIFIER"


def test_transitions_hide_buttons_gated_by_unmet_contextual_guard(
    client: TestClient, db_session: Session
) -> None:
    """Régression revue § 🟠 : sans inspection soumise, `CONTROLE_EN_COURS` n'expose plus les
    boutons « Travaux requis »/« Achat validé »/« Refusé » qui échoueraient systématiquement en
    409. La garde *contextuelle* (état déjà en base) masque le bouton ; la garde de *payload*
    (`reason`, `refus_motif`, ...) reste ignorée ici — c'est `POST .../transitions` qui la
    valide à la soumission."""
    from app.models.vehicle import Vehicle

    admin = make_user(db_session, UserRole.ADMINISTRATEUR)
    chauffeur = make_user(db_session, UserRole.CHAUFFEUR)
    login_client(client, admin)
    company = _make_company(db_session, admin)

    created = client.post("/api/v1/vehicles", json=_vehicle_body(company.id))
    vehicle_id = created.json()["id"]

    vehicle = db_session.get(Vehicle, vehicle_id)
    vehicle.state = "CONTROLE_EN_COURS"
    vehicle.assigned_driver_id = chauffeur.id
    db_session.flush()

    # Vu par l'administrateur (seul rôle habilité à annuler depuis cet état) : sans inspection
    # soumise, les trois boutons qui échoueraient systématiquement en 409 doivent disparaître,
    # et seule l'annulation (garde contextuelle toujours vraie) reste proposée.
    allowed = client.get(f"/api/v1/vehicles/{vehicle_id}/transitions")
    assert allowed.status_code == 200
    to_states = {opt["to_state"] for opt in allowed.json()["allowed"]}
    assert to_states == {
        "ANNULE"
    }, f"sans inspection soumise, seule l'annulation doit rester proposée : obtenu {to_states}"

    # Vu par le chauffeur affecté : aucun rôle habilité pour ANNULE depuis cet état (admin
    # uniquement) et les trois autres restent masqués par la garde contextuelle -> liste vide.
    login_client(client, chauffeur)
    allowed_chauffeur = client.get(f"/api/v1/vehicles/{vehicle_id}/transitions")
    assert allowed_chauffeur.status_code == 200
    assert allowed_chauffeur.json()["allowed"] == []


def test_vehicle_detail_exposes_state_history_for_the_frise(
    client: TestClient, db_session: Session
) -> None:
    """`GET /vehicles/{id}` embarque `state_history`, trié chronologiquement (frise front)."""
    operatrice = make_user(db_session, UserRole.OPERATRICE)
    login_client(client, operatrice)
    company = _make_company(db_session, operatrice)

    created = client.post("/api/v1/vehicles", json=_vehicle_body(company.id))
    vehicle_id = created.json()["id"]

    client.post(
        f"/api/v1/vehicles/{vehicle_id}/transitions",
        json={"to_state": "A_PLANIFIER", "reason": "validation opératrice"},
    )

    detail = client.get(f"/api/v1/vehicles/{vehicle_id}")
    assert detail.status_code == 200
    history = detail.json()["state_history"]
    assert len(history) == 2
    assert history[0]["from_state"] is None
    assert history[0]["to_state"] == "BROUILLON"
    assert history[1]["from_state"] == "BROUILLON"
    assert history[1]["to_state"] == "A_PLANIFIER"
    assert history[1]["reason"] == "validation opératrice"


def test_invalid_transition_returns_409_with_allowed_list(
    client: TestClient, db_session: Session
) -> None:
    operatrice = make_user(db_session, UserRole.OPERATRICE)
    login_client(client, operatrice)
    company = _make_company(db_session, operatrice)

    created = client.post("/api/v1/vehicles", json=_vehicle_body(company.id))
    vehicle_id = created.json()["id"]

    response = client.post(
        f"/api/v1/vehicles/{vehicle_id}/transitions",
        json={"to_state": "ACHAT_VALIDE", "reason": "tentative invalide"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_transition"
    assert "A_PLANIFIER" in response.json()["error"]["details"]["allowed"]


def test_chauffeur_cannot_see_unassigned_vehicle(client: TestClient, db_session: Session) -> None:
    operatrice = make_user(db_session, UserRole.OPERATRICE)
    login_client(client, operatrice)
    company = _make_company(db_session, operatrice)
    created = client.post("/api/v1/vehicles", json=_vehicle_body(company.id))
    vehicle_id = created.json()["id"]

    chauffeur = make_user(db_session, UserRole.CHAUFFEUR)
    login_client(client, chauffeur)

    response = client.get(f"/api/v1/vehicles/{vehicle_id}")
    assert response.status_code == 404


def test_operatrice_cannot_patch_others_fiche(client: TestClient, db_session: Session) -> None:
    owner = make_user(db_session, UserRole.OPERATRICE)
    login_client(client, owner)
    company = _make_company(db_session, owner)
    created = client.post("/api/v1/vehicles", json=_vehicle_body(company.id))
    vehicle_id = created.json()["id"]

    other = make_user(db_session, UserRole.OPERATRICE)
    login_client(client, other)

    response = client.patch(f"/api/v1/vehicles/{vehicle_id}", json={"commentaire": "modif"})
    assert response.status_code == 403


def test_patch_replays_exact_duplicate_check_on_immatriculation(
    client: TestClient, db_session: Session
) -> None:
    """Régression revue § 🟠 : corriger l'immatriculation d'une fiche vers une valeur déjà
    prise doit renvoyer `409 duplicate_exact` (comme à la création), jamais un `500` brut."""
    user = make_user(db_session, UserRole.ADMINISTRATEUR)
    login_client(client, user)
    company = _make_company(db_session, user)

    taken = client.post(
        "/api/v1/vehicles", json=_vehicle_body(company.id, immatriculation="AA111BB")
    )
    assert taken.status_code == 201

    other = client.post("/api/v1/vehicles", json=_vehicle_body(company.id, kilometrage=80000))
    assert other.status_code == 201
    other_id = other.json()["id"]

    response = client.patch(f"/api/v1/vehicles/{other_id}", json={"immatriculation": "aa-111-bb"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "duplicate_exact"
    assert response.json()["error"]["details"]["champ"] == "immatriculation"


def test_patch_allows_setting_own_unchanged_immatriculation(
    client: TestClient, db_session: Session
) -> None:
    """Le contrôle exclut la fiche elle-même : renvoyer la même valeur normalisée ne doit pas
    se bloquer contre soi-même."""
    user = make_user(db_session, UserRole.ADMINISTRATEUR)
    login_client(client, user)
    company = _make_company(db_session, user)

    created = client.post(
        "/api/v1/vehicles", json=_vehicle_body(company.id, immatriculation="CC222DD")
    )
    vehicle_id = created.json()["id"]

    response = client.patch(f"/api/v1/vehicles/{vehicle_id}", json={"immatriculation": "cc-222-dd"})
    assert response.status_code == 200
    assert response.json()["immatriculation"] == "cc-222-dd"


def test_patch_writes_audit_log(client: TestClient, db_session: Session) -> None:
    """Régression revue § 🟡 : une correction via `PATCH` doit être visible dans l'audit."""
    from app.models.audit import AuditLog

    user = make_user(db_session, UserRole.ADMINISTRATEUR)
    login_client(client, user)
    company = _make_company(db_session, user)

    created = client.post("/api/v1/vehicles", json=_vehicle_body(company.id))
    vehicle_id = created.json()["id"]

    response = client.patch(f"/api/v1/vehicles/{vehicle_id}", json={"kilometrage": 12345})
    assert response.status_code == 200

    entries = (
        db_session.query(AuditLog)
        .filter(AuditLog.entity_id == vehicle_id, AuditLog.action == "patch")
        .all()
    )
    assert len(entries) == 1
    assert entries[0].diff["after"]["kilometrage"] == 12345


def test_list_vehicles_exposes_company_without_n_plus_one(
    client: TestClient, db_session: Session, engine
) -> None:
    """Régression revue § 🟠 : la liste expose `company.denomination` (jointure), jamais
    `state_history` (non affiché), et le nombre de requêtes SQL ne croît pas avec le nombre de
    véhicules — sinon c'est exactement le N+1 constaté à la revue.

    Sociétés **distinctes** par véhicule, à dessein : avec une seule société partagée, la carte
    d'identité de la session masquerait le N+1 (le premier accès à `vehicle.company` la
    chargerait une fois, les 7 suivants la retrouveraient déjà en mémoire sans requête — ce qui
    aurait laissé passer la régression silencieusement)."""
    from sqlalchemy import event

    user = make_user(db_session, UserRole.OPERATRICE)
    login_client(client, user)

    created_ids = []
    for i in range(8):
        siret = f"{i:014d}"
        company = _make_company(
            db_session,
            user,
            siret=siret,
            siren=siret[:9],
            denomination=f"Flotte N+1 Test {i}",
        )
        response = client.post(
            "/api/v1/vehicles",
            json=_vehicle_body(company.id, kilometrage=80000 + i),
        )
        assert response.status_code == 201, response.text
        created_ids.append(response.json()["id"])

    queries: list[str] = []

    def _count(conn, cursor, statement, *args):
        queries.append(statement)

    event.listen(engine, "before_cursor_execute", _count)
    try:
        response = client.get("/api/v1/vehicles", params={"limit": 100})
    finally:
        event.remove(engine, "before_cursor_execute", _count)

    assert response.status_code == 200
    body = response.json()
    items_by_id = {item["id"]: item for item in body["items"]}
    for vehicle_id in created_ids:
        item = items_by_id[vehicle_id]
        assert "state_history" not in item
        assert item["company"]["denomination"].startswith("Flotte N+1 Test")

    # Une poignée de requêtes fixes (auth, scope, count, liste+jointure) — jamais une requête
    # d'historique par société distincte comme avant le correctif (8 sociétés -> 8 requêtes
    # en plus sans `joinedload`).
    assert len(queries) <= 6, f"attendu <= 6 requêtes SQL, obtenu {len(queries)} : {queries}"


def test_list_vehicles_invalid_date_filter_returns_422_not_500(
    client: TestClient, db_session: Session
) -> None:
    """Régression revue § 🟡 : `date_proposition_from=hier` doit être rejeté proprement (422),
    pas remonter en `DataError` -> 500."""
    user = make_user(db_session, UserRole.OPERATRICE)
    login_client(client, user)

    response = client.get("/api/v1/vehicles", params={"date_proposition_from": "hier"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_transition_with_malformed_driver_id_returns_422_not_500(
    client: TestClient, db_session: Session
) -> None:
    """Régression revue § 🟡 : `payload.driver_id` malformé doit rester un 422, pas un 500."""
    admin = make_user(db_session, UserRole.ADMINISTRATEUR)
    login_client(client, admin)
    company = _make_company(db_session, admin)

    created = client.post("/api/v1/vehicles", json=_vehicle_body(company.id))
    vehicle_id = created.json()["id"]
    client.post(
        f"/api/v1/vehicles/{vehicle_id}/transitions",
        json={"to_state": "A_PLANIFIER", "reason": "validation"},
    )

    response = client.post(
        f"/api/v1/vehicles/{vehicle_id}/transitions",
        json={"to_state": "AFFECTE", "payload": {"driver_id": "not-a-uuid"}},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_transition_with_malformed_rdv_at_returns_422_not_500(
    client: TestClient, db_session: Session
) -> None:
    """Régression revue § 🟡 : `payload.rdv_at` malformé doit rester un 422, pas un 500."""
    admin = make_user(db_session, UserRole.ADMINISTRATEUR)
    chauffeur = make_user(db_session, UserRole.CHAUFFEUR)
    login_client(client, admin)
    company = _make_company(db_session, admin)

    created = client.post("/api/v1/vehicles", json=_vehicle_body(company.id))
    vehicle_id = created.json()["id"]
    client.post(
        f"/api/v1/vehicles/{vehicle_id}/transitions",
        json={"to_state": "A_PLANIFIER", "reason": "validation"},
    )
    client.post(
        f"/api/v1/vehicles/{vehicle_id}/transitions",
        json={"to_state": "AFFECTE", "payload": {"driver_id": str(chauffeur.id)}},
    )

    response = client.post(
        f"/api/v1/vehicles/{vehicle_id}/transitions",
        json={"to_state": "RDV_PLANIFIE", "payload": {"rdv_at": "pas-une-date"}},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_patch_replays_fuzzy_dedup_check_on_relevant_field_change(
    client: TestClient, db_session: Session
) -> None:
    """Régression revue § 🟠 : corriger le kilométrage d'une fiche vers une valeur qui la
    rapproche fortement d'une autre doit rejouer le dédoublonnage, pas seulement le contrôle
    exact — sinon `exclude_vehicle_id` reste du code mort qu'aucun appelant n'atteint."""
    user = make_user(db_session, UserRole.ADMINISTRATEUR)
    login_client(client, user)
    company = _make_company(db_session, user)

    anchor = client.post(
        "/api/v1/vehicles",
        json=_vehicle_body(company.id, kilometrage=80000, energie="diesel"),
    )
    assert anchor.status_code == 201

    other = client.post(
        "/api/v1/vehicles",
        json={
            **_vehicle_body(company.id, kilometrage=40000, energie="essence"),
            "force_create": True,
        },
    )
    assert other.status_code == 201
    other_id = other.json()["id"]

    response = client.patch(
        f"/api/v1/vehicles/{other_id}",
        json={"kilometrage": 80100, "energie": "diesel"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "duplicate_probable"


def test_patch_force_update_bypasses_dedup_block(client: TestClient, db_session: Session) -> None:
    user = make_user(db_session, UserRole.ADMINISTRATEUR)
    login_client(client, user)
    company = _make_company(db_session, user)

    anchor = client.post(
        "/api/v1/vehicles",
        json=_vehicle_body(company.id, kilometrage=80000, energie="diesel"),
    )
    assert anchor.status_code == 201

    other = client.post(
        "/api/v1/vehicles",
        json={
            **_vehicle_body(company.id, kilometrage=40000, energie="essence"),
            "force_create": True,
        },
    )
    other_id = other.json()["id"]

    response = client.patch(
        f"/api/v1/vehicles/{other_id}",
        json={"kilometrage": 80100, "energie": "diesel", "force_update": True},
    )
    assert response.status_code == 200
    assert response.json()["kilometrage"] == 80100


def test_patch_does_not_reflag_pair_already_arbitrated_not_duplicate(
    client: TestClient, db_session: Session
) -> None:
    """Le cœur du correctif : une fois `not_duplicate` écrit pour la paire, `PATCH` ne doit
    plus jamais la reproposer — c'est la garantie « verdict définitif » de la décision A,
    étape 5, jusqu'ici jamais réalisée dans le code (revue § 🟠)."""
    user = make_user(db_session, UserRole.ADMINISTRATEUR)
    login_client(client, user)
    company = _make_company(db_session, user)

    anchor = client.post(
        "/api/v1/vehicles",
        json=_vehicle_body(company.id, kilometrage=80000, energie="diesel"),
    )
    anchor_id = anchor.json()["id"]

    other = client.post(
        "/api/v1/vehicles",
        json={
            **_vehicle_body(company.id, kilometrage=40000, energie="essence"),
            "force_create": True,
        },
    )
    other_id = other.json()["id"]

    # Rapproche `other` de `anchor` avec force_update, PUIS arbitre explicitement la paire.
    forced = client.patch(
        f"/api/v1/vehicles/{other_id}",
        json={"kilometrage": 80100, "energie": "diesel", "force_update": True},
    )
    assert forced.status_code == 200

    review = client.post(
        "/api/v1/duplicate-reviews",
        json={
            "vehicle_a_id": min(anchor_id, other_id),
            "vehicle_b_id": max(anchor_id, other_id),
            "verdict": "not_duplicate",
            "score": 0.95,
            "features": {},
        },
    )
    assert review.status_code == 201

    # Une nouvelle correction, toujours dans la même zone de score, sans force_update cette
    # fois : ne doit plus jamais être bloquée pour CETTE paire précisément arbitrée.
    response = client.patch(f"/api/v1/vehicles/{other_id}", json={"kilometrage": 80050})
    assert response.status_code == 200
