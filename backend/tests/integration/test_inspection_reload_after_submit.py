"""Reproduction 🟠 (revue orchestrateur, `.agent-team/review-j2.md` § 5) : recharger la page
juste après avoir soumis un contrôle crée une SECONDE inspection côté serveur pour le même
véhicule et la même mission.

Cause : `get_or_create_inspection` (`app/services/inspections.py::get_or_create_inspection`)
n'est idempotent QUE par `client_uuid`. Côté front, le bootstrap
(`lib/offline/db.ts::getActiveInspectionForVehicle`) filtre `!submitted_at` — après une
soumission réussie, le brouillon local sort donc de son propre filtre, et le prochain montage
de l'écran de contrôle génère un NOUVEAU `client_uuid` (`draft.ts::getOrCreateDraft`). Ce test
reproduit uniquement la moitié backend (le seul testable en pytest) : un second
`POST /inspections` avec un `client_uuid` FRAIS, sur un véhicule resté en
`CONTROLE_EN_COURS` après soumission (c'est le cas jusqu'à la transition suivante), pour le
MÊME chauffeur et la MÊME mission active.

Attendu ROUGE tant que le service n'a pas été corrigé pour renvoyer l'inspection déjà soumise
de la mission active plutôt que d'en ouvrir une seconde (§ correction proposée par la revue :
« côté backend, renvoyer l'inspection existante de la mission plutôt que d'en ouvrir une
seconde »).
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.enums import UserRole
from app.models.inspection import Inspection
from app.models.vehicle import Vehicle
from app.seed.reference import seed_reference
from tests.conftest import login_client, make_user

TODAY = date(2026, 8, 20)


def _make_company(db_session: Session, user) -> Company:
    company = Company(
        id=uuid4(),
        siren="732829320",
        siret="73282932000074",
        denomination="Flotte Reload Test",
        adresse_ligne1="1 rue du Test",
        code_postal="75001",
        commune="Paris",
        pays="FR",
        type_flotte="taxi",
        source_enrichissement="manuel",
        created_by_id=user.id,
    )
    db_session.add(company)
    db_session.flush()
    return company


def test_reopening_the_control_screen_after_submit_creates_a_second_inspection(
    client: TestClient, db_session: Session
) -> None:
    """🟠 Repro — état final vérifié en base : 2 lignes `inspection` pour le même véhicule et
    la même mission, alors qu'une seule soumission a eu lieu."""
    from app.models.checklist import ChecklistItemTemplate

    seed_reference(db_session)
    admin = make_user(db_session, UserRole.ADMINISTRATEUR)
    chauffeur = make_user(db_session, UserRole.CHAUFFEUR)

    login_client(client, admin)
    company = _make_company(db_session, admin)
    vehicle = client.post(
        "/api/v1/vehicles",
        json={
            "company_id": str(company.id),
            "marque": "Renault",
            "modele": "Kangoo",
            "date_proposition": TODAY.isoformat(),
        },
    ).json()
    vehicle_id = vehicle["id"]

    client.post(
        f"/api/v1/vehicles/{vehicle_id}/transitions",
        json={"to_state": "A_PLANIFIER", "reason": "validation"},
    )
    client.post(
        f"/api/v1/vehicles/{vehicle_id}/transitions",
        json={"to_state": "AFFECTE", "payload": {"driver_id": str(chauffeur.id)}},
    )
    vehicle_row = db_session.get(Vehicle, vehicle_id)
    vehicle_row.state = "CONTROLE_EN_COURS"
    db_session.flush()

    login_client(client, chauffeur)

    # Premier contrôle — brouillon créé, checklist remplie, 12 angles capturés, soumis.
    first_client_uuid = str(uuid4())
    create_1 = client.post(
        "/api/v1/inspections",
        json={"client_uuid": first_client_uuid, "vehicle_id": vehicle_id},
    )
    assert create_1.status_code == 201, create_1.text
    first_inspection_id = create_1.json()["id"]

    templates = list(db_session.scalars(select(ChecklistItemTemplate)).all())
    response_by_type = {
        "ok_ko": {"valeur_bool": True},
        "note_1_5": {"valeur_note": 4},
        "texte": {"valeur_texte": "RAS"},
        "numerique": {"valeur_num": 42000},
    }
    items_payload = [
        {"item_template_id": str(t.id), **response_by_type[t.response_type]}
        for t in templates
        if t.is_required
    ]
    client.put(f"/api/v1/inspections/{first_inspection_id}/items", json={"items": items_payload})

    import hashlib
    from datetime import datetime as dt

    from app.models.enums import PhotoAngle

    for angle in PhotoAngle:
        if angle == PhotoAngle.DEFAUT:
            continue
        content = f"photo-{angle.value}".encode()
        upload = client.post(
            f"/api/v1/vehicles/{vehicle_id}/photos",
            data={
                "client_uuid": str(uuid4()),
                "angle": angle.value,
                "phase": "controle",
                "inspection_id": first_inspection_id,
                "captured_at": dt.now().isoformat(),
                "checksum_sha256": hashlib.sha256(content).hexdigest(),
                "width": "1600",
                "height": "1200",
            },
            files={"file": ("photo.jpg", content, "image/jpeg")},
        )
        assert upload.status_code == 201, upload.text

    submit = client.post(
        f"/api/v1/inspections/{first_inspection_id}/submit",
        json={"conclusion": "achat_direct", "kilometrage_releve": 42000, "etat_general": "bon"},
    )
    assert submit.status_code == 200, submit.text
    assert submit.json()["submitted_at"] is not None

    # Le véhicule reste en CONTROLE_EN_COURS jusqu'à la transition suivante (achat validé/
    # travaux requis/refus) — exactement la fenêtre où la revue situe le bug : l'utilisateur
    # n'a pas encore cliqué sur un bouton de conclusion, il a juste rechargé la page.
    vehicle_after_submit = client.get(f"/api/v1/vehicles/{vehicle_id}").json()
    assert vehicle_after_submit["state"] == "CONTROLE_EN_COURS"

    # Rechargement de page — le front génère un NOUVEAU client_uuid (getOrCreateDraft ne
    # retrouve pas le brouillon soumis, filtré par !submitted_at côté IndexedDB).
    second_client_uuid = str(uuid4())
    create_2 = client.post(
        "/api/v1/inspections",
        json={"client_uuid": second_client_uuid, "vehicle_id": vehicle_id},
    )

    all_inspections = list(
        db_session.scalars(select(Inspection).where(Inspection.vehicle_id == vehicle_id)).all()
    )

    # Comportement ATTENDU (pas encore garanti) : le backend devrait renvoyer l'inspection
    # déjà soumise de la mission active plutôt que d'en ouvrir une seconde.
    assert create_2.status_code == 200, (
        "Le backend devrait renvoyer 200 avec l'inspection déjà soumise de la mission active, "
        f"pas en créer une nouvelle. Réponse obtenue : {create_2.status_code} {create_2.text}"
    )
    assert create_2.json()["id"] == first_inspection_id, (
        "Une SECONDE inspection a été créée pour le même véhicule/la même mission — "
        f"état final en base : {len(all_inspections)} ligne(s) inspection au lieu d'une seule "
        f"({[str(i.id) for i in all_inspections]})."
    )
    assert len(all_inspections) == 1


def test_two_inspections_for_the_same_mission_violate_the_database_constraint(
    db_session: Session,
) -> None:
    """Défense en profondeur : le garde-fou applicatif (`get_or_create_inspection`) ferme la
    fenêtre en usage normal, mais pas entre deux requêtes concurrentes avec des `client_uuid`
    distincts (deux onglets, rejeu réseau agressif) qui liraient toutes deux « aucune inspection
    pour cette mission » avant qu'aucune n'ait inséré la sienne. Ce test contourne délibérément
    le service pour vérifier que la contrainte `uq_inspection_mission` (migration
    `0003_inspection_mission_unique`) existe réellement en base et ne dépend pas du code
    applicatif pour tenir."""
    from sqlalchemy.exc import IntegrityError

    from app.models.checklist import ChecklistTemplate
    from app.models.inspection import Inspection
    from app.models.mission import Mission

    seed_reference(db_session)
    admin = make_user(db_session, UserRole.ADMINISTRATEUR)
    chauffeur = make_user(db_session, UserRole.CHAUFFEUR)
    company = _make_company(db_session, admin)

    vehicle = Vehicle(
        id=uuid4(),
        reference="VH-2026-999999",
        company_id=company.id,
        marque="Renault",
        modele="Kangoo",
        date_proposition=TODAY,
        state="CONTROLE_EN_COURS",
        created_by_id=admin.id,
    )
    db_session.add(vehicle)
    db_session.flush()

    mission = Mission(
        id=uuid4(),
        vehicle_id=vehicle.id,
        driver_id=chauffeur.id,
        state="en_cours",
        assigned_by_id=admin.id,
    )
    db_session.add(mission)
    db_session.flush()

    template = db_session.scalar(
        select(ChecklistTemplate).where(ChecklistTemplate.is_active.is_(True))
    )
    assert template is not None

    first = Inspection(
        id=uuid4(),
        vehicle_id=vehicle.id,
        mission_id=mission.id,
        driver_id=chauffeur.id,
        template_id=template.id,
        client_uuid=uuid4(),
    )
    db_session.add(first)
    db_session.flush()

    second = Inspection(
        id=uuid4(),
        vehicle_id=vehicle.id,
        mission_id=mission.id,
        driver_id=chauffeur.id,
        template_id=template.id,
        client_uuid=uuid4(),
    )
    db_session.add(second)
    try:
        with pytest.raises(IntegrityError, match="uq_inspection_mission"):
            db_session.flush()
    finally:
        db_session.rollback()
