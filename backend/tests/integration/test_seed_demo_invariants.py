"""Invariants du jeu de démo — ferme le trou signalé par `tests-j3.md` § 3 « J2 — constat
matériel » : ce défaut (0 ligne `mission`/`inspection`/`photo`/`notification` malgré 52 véhicules
dans un état post-`AFFECTE`) a survécu à trois jalons parce qu'aucun test ne regardait la
cohérence du jeu de démonstration lui-même — seulement les compteurs de lignes et les chiffres du
tableau de bord (`test_demo_reset.py`). Ce fichier teste `seed_demo` directement, pas via
`run_demo_reset()` (déjà couvert par ailleurs pour l'idempotence bout en bout) : plus rapide (pas
de TRUNCATE ni de rebuild `analytics`), et plus proche du point de défaillance réel.
"""

from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.inspection import Inspection
from app.models.mission import Mission
from app.models.photo import Photo
from app.models.vehicle import Vehicle
from app.seed.demo import seed_demo
from app.seed.reference import seed_reference
from app.services.storage.service import get_storage_backend

# États qu'un véhicule ne peut structurellement atteindre qu'en étant passé par `AFFECTE`
# (`app/seed/demo.py::_build_state_path` — jamais `ANNULE`, qui peut aussi venir de `BROUILLON`/
# `A_PLANIFIER` sans jamais avoir été affecté : l'exclure évite un faux positif sur cet état).
_POST_AFFECTE_STATES = (
    "AFFECTE",
    "RDV_PLANIFIE",
    "CONTROLE_EN_COURS",
    "TRAVAUX_REQUIS",
    "TRAVAUX_EN_COURS",
    "TRAVAUX_TERMINES",
    "ACHAT_VALIDE",
    "REFUSE",
)


def _seed(db_session: Session) -> dict[str, int]:
    seed_reference(db_session)
    return seed_demo(db_session, force=True)


def test_seed_populates_terrain_tables(db_session: Session) -> None:
    """Régression directe du gap J2 (`tests-j3.md` § 3) : les quatre tables terrain ne doivent
    plus jamais rester à 0 alors que des véhicules affectés existent — un test vert par absence
    de cas serait pire qu'un test rouge."""
    result = _seed(db_session)

    assert result["missions"] > 0
    assert result["inspections"] > 0
    assert result["photos"] > 0
    assert result["notifications"] > 0

    assert db_session.scalar(select(Mission.id).limit(1)) is not None
    assert db_session.scalar(select(Inspection.id).limit(1)) is not None
    assert db_session.scalar(select(Photo.id).limit(1)) is not None


def test_no_post_affecte_vehicle_without_mission(db_session: Session) -> None:
    """« La base raconte une histoire impossible » — un véhicule `AFFECTE` (ou plus avancé) sans
    mission ne peut pas exister dans la vraie application (la mission est un effet de la
    transition `A_PLANIFIER -> AFFECTE`, `app/services/vehicles.py::transition_vehicle`) : le
    jeu de démo ne doit jamais en montrer un."""
    _seed(db_session)

    offenders = db_session.execute(
        select(Vehicle.reference, Vehicle.state)
        .outerjoin(Mission, Mission.vehicle_id == Vehicle.id)
        .where(Vehicle.state.in_(_POST_AFFECTE_STATES), Mission.id.is_(None))
    ).all()

    assert (
        offenders == []
    ), f"{len(offenders)} véhicule(s) dans un état post-AFFECTE sans mission : {offenders}"


def test_no_controle_en_cours_vehicle_without_inspection(db_session: Session) -> None:
    """Un véhicule ne peut atteindre `CONTROLE_EN_COURS` que via la mission qui y démarre le
    contrôle (`missions_service.start_control`) — dans la vraie application, cette transition
    n'existe jamais sans qu'une inspection soit rattachée à la mission active."""
    _seed(db_session)

    offenders = db_session.execute(
        select(Vehicle.reference)
        .outerjoin(Inspection, Inspection.vehicle_id == Vehicle.id)
        .where(Vehicle.state == "CONTROLE_EN_COURS", Inspection.id.is_(None))
    ).all()

    assert offenders == [], f"véhicule(s) CONTROLE_EN_COURS sans inspection : {offenders}"


def test_no_advanced_vehicle_with_unsubmitted_inspection(db_session: Session) -> None:
    """Un véhicule qui a quitté `CONTROLE_EN_COURS` (travaux, achat, refus) n'a pu le faire, dans
    la vraie application, qu'avec une inspection **soumise** (garde
    `inspection_submitted_with_required_angles`, `app/services/vehicles.py::
    build_transition_context`) — le seed doit reproduire cette contrainte, pas seulement la
    présence d'une inspection."""
    _seed(db_session)

    advanced_states = (
        "TRAVAUX_REQUIS",
        "TRAVAUX_EN_COURS",
        "TRAVAUX_TERMINES",
        "ACHAT_VALIDE",
        "REFUSE",
    )
    offenders = db_session.execute(
        select(Vehicle.reference, Inspection.submitted_at)
        .join(Inspection, Inspection.vehicle_id == Vehicle.id)
        .where(Vehicle.state.in_(advanced_states), Inspection.submitted_at.is_(None))
    ).all()

    assert offenders == [], f"inspection(s) non soumise(s) sur véhicule avancé : {offenders}"


def test_every_photo_row_has_a_real_readable_file(db_session: Session) -> None:
    """`docs/wiki/pieges-projet.md` : une ligne `photo` sans fichier produit un 404 silencieux,
    image cassée sans erreur serveur. Vérifie le fichier réel via l'abstraction `PhotoStorage`
    (jamais un chemin disque en dur) et son intégrité (checksum, taille) — pas seulement son
    existence."""
    _seed(db_session)
    storage = get_storage_backend()

    photos = db_session.execute(
        select(Photo.storage_bucket, Photo.storage_key, Photo.checksum_sha256, Photo.byte_size)
    ).all()
    assert len(photos) > 0

    missing: list[str] = []
    corrupted: list[str] = []
    for bucket, key, checksum, byte_size in photos:
        try:
            content = storage.load(bucket=bucket, key=key)
        except FileNotFoundError:
            missing.append(f"{bucket}/{key}")
            continue
        if len(content) != byte_size or hashlib.sha256(content).hexdigest() != checksum:
            corrupted.append(f"{bucket}/{key}")

    assert missing == [], f"photo(s) sans fichier lisible via le storage : {missing}"
    assert (
        corrupted == []
    ), f"photo(s) dont le fichier ne correspond pas au checksum/taille : {corrupted}"


# Déterminisme bout en bout (deux `run_demo_reset()` consécutifs, TRUNCATE compris, comparaison
# des compteurs ET des marts analytics) : déjà couvert par
# `tests/integration/test_demo_reset.py::test_two_consecutive_resets_produce_identical_counters`
# et `..._identical_dashboard_figures`. Pas dupliqué ici — un second `seed_demo()` sans TRUNCATE
# intermédiaire (hors périmètre de ce fichier, focalisé sur la cohérence d'un seed donné)
# violerait de toute façon `uq_company_siret` (mêmes 12 SIRET régénérés par la même graine).
