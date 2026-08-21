"""Seed `demo` — ~90 véhicules sur 3 mois, distribution réaliste (plan.md § 4 décision D).

Déterministe (`random.Random(SEED_VERSION)` + `Faker('fr_FR')` à graine fixe), mais les **dates
sont recalculées relativement à `date.today()`** : la démo montre toujours « les 3 derniers
mois », jamais un historique qui vieillit (le détail le plus souvent raté en démo).

Les SIRET sont fictifs mais à clé de Luhn valide, et **préchargés dans `company_lookup_cache`**
avec `source='demo'` : le parcours de démo ne déclenche jamais d'appel réseau (décision B).

J3 (`SEED_VERSION` inchangée volontairement — même graine, plus de données produites par
véhicule) : chaque véhicule qui dépasse `BROUILLON` reçoit désormais l'historique **complet** de
ses transitions intermédiaires, pas seulement `BROUILLON` + état final — c'était le piège
consigné dans `docs/wiki/pieges-projet.md` (« la frise saute cinq états »), et c'est aussi ce qui
alimente `mart_cycle_temps` (sans transition `AFFECTE`/`CONTROLE_EN_COURS` horodatée, le délai de
cycle resterait NULL pour la quasi-totalité du parc). Les véhicules passés par l'atelier portent
des `work_order` (+ leurs `work_order_line`, coût réel) et une partie du parc porte des
`vehicle_cost` (coûts hors atelier) — de quoi produire un dashboard fourni et crédible dès
l'ouverture, marges variées, **au moins une négative** (garanti par construction, pas laissé au
hasard du RNG — voir `_force_at_least_one_negative_margin`).

Correctif post-J3 (`tests-j3.md` § 3 « J2 — constat matériel ») : ce module ne référençait
**jamais** `Mission`/`Inspection`/`Photo`/`Notification`, à aucun jalon — le seed écrivait
directement `vehicle.state` et l'historique des transitions sans jamais emprunter les effets de
bord que la vraie application produit (`app/services/missions.py`,
`app/services/notifications.py`, l'inspection + les photos guidées). Conséquence vérifiée en
base : 0 ligne dans les quatre tables malgré 52 véhicules dans un état post-`AFFECTE` — le module
terrain (jalon J2 entier : réception de mission, notification, rendez-vous, contrôle, photos)
était invisible pour le compte `chauffeur@cardan.demo`, alors que le Kanban administrateur
affichait ces mêmes véhicules comme affectés. `_seed_terrain_for_vehicle` (et l'extension de
`_seed_work_orders_for_vehicle` aux photos avant/après travaux) ferment ce trou, en rejouant pour
chaque véhicule les effets que `POST /vehicles/{id}/transitions` aurait produits à chaque étape
de son `path` — réutilise directement les fonctions d'effet de `app/services/missions.py`
(`create_mission`/`mark_rdv`/`start_control`/`complete_mission`/`cancel_mission`) et de
`app/services/notifications.py` (`notify_mission_assigned`), horodatage rétroactif ensuite (même
geste que `vehicle.created_at` plus bas dans ce fichier). L'inspection, elle, ne peut PAS passer
par le service `get_or_create_inspection` (garde `vehicle.state != CONTROLE_EN_COURS` — vraie
seulement en direct, ici `vehicle.state` porte déjà l'état **final** dès la construction) : elle
est construite directement, comme `WorkOrder` l'est déjà plus bas.

**Flux RNG strictement séparés** (point non négociable, cf. `_calibrate_dedup_demo_vehicle` plus
bas sur le même sujet) : toute cette génération terrain utilise `terrain_rng`, une seconde
instance `random.Random` dédiée (graine `f"{SEED_VERSION}-terrain"`), jamais le `rng` principal
qui pilote marque/modèle/état/prix de chaque véhicule. Émettre le moindre tirage terrain sur le
`rng` principal décalerait tous les véhicules suivants dans la boucle et changerait les chiffres
du tableau de bord déjà validés au centime (`tests-j3.md` § 1 : marge moyenne 258 325 centimes,
1 marge négative, etc.) — exactement le bug vécu sur le véhicule de dédoublonnage lors de l'ajout
de l'historique de transitions en J3. Les photos sont de vraies images PNG générées en mémoire
(`_synthetic_photo_bytes`, aucune dépendance, aucun binaire versionné) et écrites via
`PhotoStorage` sous le préfixe `seed/` (jamais `runtime/`, purgé par le reset nocturne après
chaque seed pour les uploads réels — réutiliser ce préfixe aurait fait disparaître les photos de
démo à la fin du reset qui vient de les créer) ; ce préfixe est lui-même purgé en tout début de
`seed_demo` pour rester idempotent sur disque, pas seulement en base.
"""

from __future__ import annotations

import hashlib
import random
import struct
import zlib
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from faker import Faker
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError
from app.models.checklist import ChecklistItemTemplate, ChecklistTemplate
from app.models.company import Company, CompanyLookupCache
from app.models.enums import (
    EtatGeneral,
    InspectionConclusion,
    PhotoAngle,
    PhotoPhase,
    RefusMotif,
    ResponseType,
    TypeFlotte,
    UploadState,
    UserRole,
    VehicleCostType,
    VehicleState,
    WorkOrderLineCategorie,
    WorkOrderState,
    WorkOrderType,
)
from app.models.inspection import Inspection, InspectionItem
from app.models.photo import Photo
from app.models.user import AppUser
from app.models.vehicle import Vehicle, VehicleStateTransition
from app.models.vehicle_cost import VehicleCost
from app.models.work_order import WorkOrder, WorkOrderLine
from app.seed.reference import DEMO_ACCOUNTS
from app.services import missions as missions_service
from app.services import notifications as notifications_service
from app.services.company_lookup.base import CompanyLookupResult
from app.services.inspections import REQUIRED_PHOTO_ANGLES
from app.services.normalize import normalize_modele
from app.services.siret import is_valid_siret
from app.services.storage.base import PhotoStorage
from app.services.storage.service import get_storage_backend
from app.services.vehicles import generate_reference

SEED_VERSION = "demo-v1"
NUM_VEHICLES = 90
NUM_COMPANIES = 12
DATE_WINDOW_DAYS = 90

# Préfixe de stockage des photos de démo — distinct de `runtime/` (uploads réels, purgé par le
# reset nocturne après le seed, `app/seed/reset.py`). Purgé APRÈS le commit du reset, jamais
# pendant `seed_demo` (voir `purge_stale_seed_photos` ci-dessous et la note dans `seed_demo`).
_PHOTO_STORAGE_PREFIX = "seed"

CATALOGUE = (
    ("Renault", "Kangoo", "essence"),
    ("Renault", "Trafic", "diesel"),
    ("Renault", "Master", "diesel"),
    ("Peugeot", "Partner", "diesel"),
    ("Peugeot", "Boxer", "diesel"),
    ("Citroën", "Berlingo", "essence"),
    ("Citroën", "Jumpy", "diesel"),
    ("Mercedes-Benz", "Vito", "diesel"),
    ("Toyota", "Proace", "hybride"),
    ("Ford", "Transit", "diesel"),
    ("Fiat", "Ducato", "diesel"),
    ("Renault", "Zoe", "electrique"),
)

# (état, poids) — somme = 100. ~15 % de refus, cohérent avec le brief.
STATE_WEIGHTS: tuple[tuple[VehicleState, int], ...] = (
    (VehicleState.BROUILLON, 10),
    (VehicleState.A_PLANIFIER, 10),
    (VehicleState.AFFECTE, 8),
    (VehicleState.RDV_PLANIFIE, 8),
    (VehicleState.CONTROLE_EN_COURS, 5),
    (VehicleState.TRAVAUX_REQUIS, 5),
    (VehicleState.TRAVAUX_EN_COURS, 5),
    (VehicleState.TRAVAUX_TERMINES, 5),
    (VehicleState.ACHAT_VALIDE, 24),
    (VehicleState.REFUSE, 15),
    (VehicleState.ANNULE, 5),
)

TYPE_FLOTTE_CHOICES = tuple(TypeFlotte)
REFUS_MOTIF_CHOICES = tuple(RefusMotif)

_WORK_ORDER_DESCRIPTIONS: dict[WorkOrderType, tuple[str, ...]] = {
    WorkOrderType.CARROSSERIE: (
        "Réparation pare-chocs avant",
        "Débosselage aile arrière droite",
        "Reprise peinture portière coulissante",
    ),
    WorkOrderType.MECANIQUE: (
        "Révision complète + vidange",
        "Remplacement plaquettes et disques de frein",
        "Contrôle et purge circuit de freinage",
    ),
    WorkOrderType.NETTOYAGE: (
        "Nettoyage intérieur complet",
        "Décontamination habitacle",
    ),
    WorkOrderType.PNEUMATIQUES: (
        "Remplacement train de pneumatiques avant",
        "Remplacement des 4 pneumatiques",
    ),
    WorkOrderType.AUTRE: (
        "Remise en état diverse avant revente",
        "Contrôle technique et corrections",
    ),
}

_LINE_LIBELLES: dict[str, tuple[str, ...]] = {
    WorkOrderLineCategorie.PIECE.value: (
        "Pièce détachée",
        "Kit de réparation",
        "Élément carrosserie",
    ),
    WorkOrderLineCategorie.MAIN_OEUVRE.value: ("Main d'œuvre atelier", "Forfait intervention"),
    WorkOrderLineCategorie.SOUS_TRAITANCE.value: (
        "Intervention sous-traitant",
        "Prestation externe",
    ),
    WorkOrderLineCategorie.CONSOMMABLE.value: ("Consommables atelier", "Produits d'entretien"),
}

_VEHICLE_COST_LIBELLES: dict[VehicleCostType, str] = {
    VehicleCostType.TRANSPORT: "Frais de convoyage complémentaire",
    VehicleCostType.CARBURANT: "Plein carburant à la prise en charge",
    VehicleCostType.ADMINISTRATIF: "Frais de carte grise / démarches",
    VehicleCostType.REMISE_EN_ETAT_EXTERNE: "Prestation de remise en état externalisée",
    VehicleCostType.AUTRE: "Frais divers",
}

# Palette de couleurs pour les photos synthétiques (`_synthetic_photo_bytes`) — purement
# cosmétique (varier les vignettes en démo), tons neutres proches d'une photo de véhicule.
_PHOTO_PALETTE: tuple[tuple[int, int, int], ...] = (
    (176, 190, 197),
    (144, 164, 174),
    (120, 144, 156),
    (96, 125, 139),
    (161, 136, 127),
    (141, 110, 99),
    (109, 76, 65),
    (84, 110, 122),
)

_RDV_CONTACT_NAMES: tuple[str, ...] = (
    "Nadia Fontaine",
    "Julien Lefèvre",
    "Sophie Bertrand",
    "Karim Haddad",
    "Isabelle Morel",
    "Thomas Girard",
    "Camille Dupuis",
    "Ahmed Belkacem",
)

_ITEM_QUALITY_GOOD = "bon"
_ITEM_QUALITY_MEDIUM = "moyen"
_ITEM_QUALITY_POOR = "mauvais"


class DemoSeedGuardError(Exception):
    """Levée quand la base contient un compte hors du référentiel de démo (garde-fou § 4-D)."""


def _generate_valid_siret(rng: random.Random) -> str:
    prefix = "".join(str(rng.randint(0, 9)) for _ in range(13))
    for check_digit in range(10):
        candidate = f"{prefix}{check_digit}"
        if is_valid_siret(candidate):
            return candidate
    raise AssertionError("aucun chiffre de clé Luhn valide trouvé — ne devrait jamais arriver")


def _assert_only_demo_accounts(db: Session, *, force: bool) -> None:
    if force:
        return
    demo_emails = {a.email for a in DEMO_ACCOUNTS}
    rogue = db.scalar(select(AppUser).where(AppUser.email.not_in(demo_emails)))
    if rogue is not None:
        raise DemoSeedGuardError(
            f"Un compte hors du référentiel de démo existe déjà ({rogue.email}). "
            "Relancer avec --force pour l'ignorer."
        )


def _get_demo_user(db: Session, role: UserRole) -> AppUser:
    account = next(a for a in DEMO_ACCOUNTS if a.role == role)
    user = db.scalar(select(AppUser).where(AppUser.email == account.email))
    if user is None:
        raise ApiError(
            "internal_error",
            f"Compte de référence manquant ({account.email}) — lancer `seed --profile "
            "reference` avant `seed --profile demo`.",
        )
    return user


def _get_default_checklist_template(db: Session) -> ChecklistTemplate:
    template = db.scalar(
        select(ChecklistTemplate)
        .where(ChecklistTemplate.is_active.is_(True))
        .order_by(ChecklistTemplate.version.desc())
    )
    if template is None:
        raise ApiError(
            "internal_error",
            "Aucun modèle de checklist actif — lancer `seed --profile reference` avant "
            "`seed --profile demo`.",
        )
    return template


def _seed_companies(
    db: Session, rng: random.Random, faker: Faker, creator: AppUser
) -> list[Company]:
    companies = []
    for _ in range(NUM_COMPANIES):
        siret = _generate_valid_siret(rng)
        denomination = faker.company()
        type_flotte = rng.choice(TYPE_FLOTTE_CHOICES)
        company = Company(
            id=uuid4(),
            siren=siret[:9],
            siret=siret,
            denomination=denomination,
            adresse_ligne1=faker.street_address(),
            code_postal=faker.postcode(),
            commune=faker.city(),
            pays="FR",
            type_flotte=type_flotte.value,
            source_enrichissement="demo",
            enriched_at=datetime.now(UTC),
            created_by_id=creator.id,
        )
        db.add(company)
        companies.append(company)

        # Préchargé dans le cache — le parcours de démo ne sort jamais sur le réseau.
        result = CompanyLookupResult(
            siret=siret,
            siren=siret[:9],
            denomination=denomination,
            forme_juridique="SARL",
            code_naf="4939A",
            libelle_naf="Transports routiers de voyageurs",
            adresse_ligne1=company.adresse_ligne1,
            code_postal=company.code_postal,
            commune=company.commune,
            tranche_effectif="12",
            date_creation="2015-01-01",
        )
        db.add(
            CompanyLookupCache(
                siret=siret,
                payload=asdict(result),
                source="demo",
                http_status=200,
                fetched_at=datetime.now(UTC),
                provider="demo",
            )
        )
    db.flush()
    return companies


def _pick_state(rng: random.Random) -> VehicleState:
    states = [s for s, _w in STATE_WEIGHTS]
    weights = [w for _s, w in STATE_WEIGHTS]
    return rng.choices(states, weights=weights, k=1)[0]


def _build_state_path(rng: random.Random, final_state: VehicleState) -> list[VehicleState]:
    """Chemin complet BROUILLON -> `final_state`, conforme au tableau des transitions
    (plan.md § 5.3) — c'est ce chemin qui est rejoué en historique (chaque maillon devient une
    ligne `vehicle_state_transition` horodatée), plus jamais le seul raccourci BROUILLON+final.
    """
    S = VehicleState
    if final_state == S.BROUILLON:
        return [S.BROUILLON]
    if final_state == S.ANNULE:
        # Annulation depuis un point aléatoire du début de parcours (plan.md § 5.3 : seuls les
        # états précoces admettent une annulation "opératrice").
        early = rng.choice([S.BROUILLON, S.A_PLANIFIER, S.AFFECTE, S.RDV_PLANIFIE])
        return [*_build_state_path(rng, early), S.ANNULE]

    base = [S.BROUILLON, S.A_PLANIFIER, S.AFFECTE, S.RDV_PLANIFIE, S.CONTROLE_EN_COURS]
    if final_state in (S.CONTROLE_EN_COURS,):
        return base
    if final_state in (S.A_PLANIFIER, S.AFFECTE, S.RDV_PLANIFIE):
        return base[: base.index(final_state) + 1]

    if final_state in (S.TRAVAUX_REQUIS,):
        return [*base, S.TRAVAUX_REQUIS]
    if final_state == S.TRAVAUX_EN_COURS:
        return [*base, S.TRAVAUX_REQUIS, S.TRAVAUX_EN_COURS]
    if final_state == S.TRAVAUX_TERMINES:
        return [*base, S.TRAVAUX_REQUIS, S.TRAVAUX_EN_COURS, S.TRAVAUX_TERMINES]

    if final_state in (S.ACHAT_VALIDE, S.REFUSE):
        # Deux chemins possibles, cohérents avec l'automate : achat/refus direct après contrôle,
        # ou après passage complet par l'atelier (~35 % du parc dans ce second cas).
        if rng.random() < 0.35:
            return [*base, S.TRAVAUX_REQUIS, S.TRAVAUX_EN_COURS, S.TRAVAUX_TERMINES, final_state]
        return [*base, final_state]

    raise AssertionError(f"état final non couvert par le seed : {final_state}")


def _spread_timestamps(
    rng: random.Random, path: list[VehicleState], date_proposition: date, today: date
) -> list[datetime]:
    """Un horodatage par maillon du `path`, strictement croissant, jamais après `today` —
    quelques heures à quelques jours entre deux étapes, cohérent avec un cycle d'achat réel."""
    start = datetime.combine(date_proposition, datetime.min.time(), tzinfo=UTC)
    now = datetime.combine(today, datetime.min.time(), tzinfo=UTC) + timedelta(hours=23)
    timestamps = [start]
    for _ in path[1:]:
        step = timedelta(hours=rng.randint(3, 60))
        candidate = timestamps[-1] + step
        timestamps.append(min(candidate, now))
    # Ré-assure la stricte croissance après l'écrêtage à `now` (deux derniers maillons collés à
    # la même date de génération, ex. un véhicule seedé "aujourd'hui même") — décale de quelques
    # minutes plutôt que de laisser deux transitions identiques (peu réaliste, sans conséquence
    # fonctionnelle mais visible dans une frise de démo).
    for i in range(1, len(timestamps)):
        if timestamps[i] <= timestamps[i - 1]:
            timestamps[i] = timestamps[i - 1] + timedelta(minutes=5)
    return timestamps


def _write_transition_history(
    db: Session,
    vehicle: Vehicle,
    path: list[VehicleState],
    timestamps: list[datetime],
    actor: AppUser,
) -> None:
    previous: VehicleState | None = None
    for state, occurred_at in zip(path, timestamps, strict=True):
        db.add(
            VehicleStateTransition(
                id=uuid4(),
                vehicle_id=vehicle.id,
                from_state=previous.value if previous is not None else None,
                to_state=state.value,
                actor_id=actor.id,
                actor_role=actor.role,
                reason="Création (seed démo)" if previous is None else "Progression (seed démo)",
                occurred_at=occurred_at,
            )
        )
        previous = state


def _synthetic_photo_bytes(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    """Génère un PNG minimal, valide et réellement décodable, entièrement en mémoire — aucune
    dépendance (Pillow n'est pas une dépendance du projet), aucun binaire téléchargé ni versionné
    (le dépôt est public). Ferme le trou documenté dans `docs/wiki/pieges-projet.md` (« une ligne
    `photo` sans fichier produit un 404 silencieux, image cassée sans erreur serveur ») : chaque
    photo de démo écrit un vrai fichier via `PhotoStorage`, pas seulement une ligne en base."""

    def _chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # RGB, 8 bits/canal
    row = bytes(rgb) * width
    raw = (b"\x00" + row) * height  # un octet de filtre (0 = aucun) par ligne
    idat = zlib.compress(raw, level=9)
    return signature + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")


def _seed_photo(
    db: Session,
    storage: PhotoStorage,
    rng: random.Random,
    *,
    bucket: str,
    vehicle: Vehicle,
    uploader: AppUser,
    angle: str,
    phase: str,
    inspection_id,
    work_order_id,
    captured_at: datetime,
) -> Photo:
    """Écrit le fichier (`storage.save`, jamais seulement la ligne en base) puis construit la
    ligne `Photo` — même ordre que le service réel `app/services/photos.py::create_photo`
    (octet avant l'insertion)."""
    width = height = 64
    content = _synthetic_photo_bytes(width, height, rgb=rng.choice(_PHOTO_PALETTE))
    checksum = hashlib.sha256(content).hexdigest()
    key = f"{_PHOTO_STORAGE_PREFIX}/{vehicle.id}/{uuid4().hex}.png"
    storage.save(bucket=bucket, key=key, content=content)

    photo = Photo(
        id=uuid4(),
        vehicle_id=vehicle.id,
        inspection_id=inspection_id,
        work_order_id=work_order_id,
        angle=angle,
        phase=phase,
        storage_bucket=bucket,
        storage_key=key,
        content_type="image/png",
        byte_size=len(content),
        width=width,
        height=height,
        checksum_sha256=checksum,
        client_uuid=uuid4(),
        upload_state=UploadState.ENVOYEE.value,
        is_placeholder=False,
        captured_at=captured_at,
        uploaded_at=captured_at,
        uploaded_by_id=uploader.id,
    )
    db.add(photo)
    return photo


def _pick_item_value(rng: random.Random, response_type: str, quality: str) -> dict:
    """Valeur plausible pour un item de checklist, biaisée par `quality` — un contrôle qui
    conclut à un refus doit porter des réponses dégradées, pas les mêmes notes qu'un achat
    direct (cohérence narrative de la démo, revue attendue de toute étude de cas)."""
    ok_probability = {"bon": 0.95, "moyen": 0.8, "mauvais": 0.45}[quality]
    note_choices = {
        "bon": (4, 4, 5, 5, 5),
        "moyen": (3, 3, 4, 4, 5),
        "mauvais": (1, 2, 2, 3, 3),
    }[quality]
    if response_type == ResponseType.OK_KO.value:
        return {"valeur_bool": rng.random() < ok_probability}
    if response_type == ResponseType.NOTE_1_5.value:
        return {"valeur_note": rng.choice(note_choices)}
    if response_type == ResponseType.TEXTE.value:
        return {"valeur_texte": None if rng.random() < 0.6 else "Rien à signaler de particulier."}
    # NUMERIQUE (kilométrage) traité à part par l'appelant — voir `_seed_terrain_for_vehicle`.
    return {}


def _seed_terrain_for_vehicle(
    db: Session,
    storage: PhotoStorage,
    terrain_rng: random.Random,
    *,
    bucket: str,
    vehicle: Vehicle,
    company: Company,
    path: list[VehicleState],
    timestamps: list[datetime],
    final_state: VehicleState,
    chauffeur: AppUser,
    operatrice: AppUser,
    checklist_template: ChecklistTemplate,
    checklist_items: list[ChecklistItemTemplate],
) -> dict[str, int]:
    """Rejoue, pour CE véhicule, les effets `mission`/`inspection`/`photo`/`notification` que la
    vraie application aurait produits à chaque maillon de `path` (plan.md § 5.3) — voir la
    docstring de module pour le contexte du trou comblé ici.

    Réutilise directement les fonctions d'effet de `app/services/missions.py` plutôt que de
    réécrire la logique d'état : c'est le même automate que celui appelé par
    `app/services/vehicles.py::transition_vehicle`. Ces fonctions posent certains champs sur
    `datetime.now(UTC)` (pensées pour un appel live) : chacun est réécrit juste après avec le
    timestamp historique réel de l'étape — même geste que `vehicle.created_at` plus bas dans ce
    module.

    L'inspection est en revanche construite directement (pas via
    `app/services/inspections.py::get_or_create_inspection`, dont la garde `vehicle.state !=
    CONTROLE_EN_COURS` suppose un appel live où cette colonne reflète l'étape en cours — ici elle
    porte déjà l'état final dès la construction du véhicule, l'historique n'existant que dans
    `vehicle_state_transition`), à l'identique de `WorkOrder` plus bas dans ce fichier.
    """
    counts = {"missions": 0, "inspections": 0, "photos": 0, "notifications": 0}
    if VehicleState.AFFECTE not in path:
        return counts

    idx_affecte = path.index(VehicleState.AFFECTE)
    mission = missions_service.create_mission(
        db, vehicle, driver_id=chauffeur.id, assigned_by_id=operatrice.id
    )
    mission.assigned_at = timestamps[idx_affecte]
    counts["missions"] += 1

    notification = notifications_service.notify_mission_assigned(
        db, driver_id=chauffeur.id, vehicle=vehicle, mission=mission
    )
    notification.created_at = timestamps[idx_affecte]
    # ~60 % des notifications d'affectation sont lues par le chauffeur dans les heures qui
    # suivent en démo (badge nouvelle mission crédible, pas 100 % lues ni 100 % non lues).
    if terrain_rng.random() < 0.6:
        notification.read_at = timestamps[idx_affecte] + timedelta(hours=terrain_rng.randint(1, 20))
    counts["notifications"] += 1

    if VehicleState.RDV_PLANIFIE in path:
        idx_rdv = path.index(VehicleState.RDV_PLANIFIE)
        missions_service.mark_rdv(
            db,
            mission,
            rdv_at=timestamps[idx_rdv],
            rdv_adresse=f"{company.adresse_ligne1}, {company.code_postal} {company.commune}",
            rdv_contact_nom=terrain_rng.choice(_RDV_CONTACT_NAMES),
            rdv_contact_telephone=f"06{terrain_rng.randint(0, 99999999):08d}",
        )

    if VehicleState.CONTROLE_EN_COURS in path:
        idx_controle = path.index(VehicleState.CONTROLE_EN_COURS)
        missions_service.start_control(db, mission)

        inspection = Inspection(
            id=uuid4(),
            vehicle_id=vehicle.id,
            mission_id=mission.id,
            driver_id=chauffeur.id,
            template_id=checklist_template.id,
            client_uuid=uuid4(),
            started_at=timestamps[idx_controle],
        )
        db.add(inspection)
        db.flush()
        counts["inspections"] += 1

        # Un contrôle dont le véhicule est encore CONTROLE_EN_COURS aujourd'hui est réellement en
        # cours : réponses/photos partielles, jamais soumis. Tout autre `final_state` a franchi
        # cette étape dans la vraie application, donc n'a pu le faire qu'avec un contrôle complet
        # (garde `inspection_submitted_with_required_angles`, `app/services/vehicles.py`) — le
        # seed doit donc produire un historique complet ici aussi, pas un raccourci.
        completed = final_state != VehicleState.CONTROLE_EN_COURS
        if completed:
            items_to_fill = checklist_items
            angles_to_capture = list(REQUIRED_PHOTO_ANGLES)
            if final_state == VehicleState.REFUSE:
                quality = _ITEM_QUALITY_POOR
                conclusion = InspectionConclusion.REFUS.value
                etat_general = EtatGeneral.MAUVAIS.value
            elif VehicleState.TRAVAUX_REQUIS in path:
                # Basé sur la présence dans `path`, pas seulement `final_state` : un véhicule
                # ACHAT_VALIDE peut être passé par l'atelier avant (branche 35 % de
                # `_build_state_path`), la conclusion du contrôle reste "travaux requis" dans ce
                # cas, cohérent avec les `work_order` réellement créés plus bas.
                quality = _ITEM_QUALITY_MEDIUM
                conclusion = InspectionConclusion.TRAVAUX_REQUIS.value
                etat_general = EtatGeneral.MOYEN.value
            else:
                quality = _ITEM_QUALITY_GOOD
                conclusion = InspectionConclusion.ACHAT_DIRECT.value
                etat_general = EtatGeneral.BON.value
        else:
            items_to_fill = terrain_rng.sample(
                checklist_items, k=max(1, int(len(checklist_items) * 0.6))
            )
            angles_to_capture = terrain_rng.sample(
                list(REQUIRED_PHOTO_ANGLES), k=max(1, int(len(REQUIRED_PHOTO_ANGLES) * 0.5))
            )
            quality = _ITEM_QUALITY_MEDIUM
            conclusion = None
            etat_general = None

        km_releve = (vehicle.kilometrage or 0) + terrain_rng.randint(-40, 120)
        for item_template in items_to_fill:
            if item_template.response_type == ResponseType.NUMERIQUE.value:
                values = {"valeur_num": Decimal(km_releve)}
            else:
                values = _pick_item_value(terrain_rng, item_template.response_type, quality)
            db.add(
                InspectionItem(
                    id=uuid4(),
                    inspection_id=inspection.id,
                    item_template_id=item_template.id,
                    **values,
                )
            )

        photo_time = timestamps[idx_controle]
        for angle in angles_to_capture:
            photo_time = photo_time + timedelta(minutes=terrain_rng.randint(2, 9))
            _seed_photo(
                db,
                storage,
                terrain_rng,
                bucket=bucket,
                vehicle=vehicle,
                uploader=chauffeur,
                angle=angle.value,
                phase=PhotoPhase.CONTROLE.value,
                inspection_id=inspection.id,
                work_order_id=None,
                captured_at=photo_time,
            )
            counts["photos"] += 1

        if completed:
            inspection.etat_general = etat_general
            inspection.conclusion = conclusion
            inspection.kilometrage_releve = km_releve
            inspection.commentaire = (
                None
                if terrain_rng.random() < 0.7
                else "Contrôle réalisé sans difficulté particulière."
            )
            idx_exit = idx_controle + 1
            exit_at = timestamps[idx_exit] if idx_exit < len(timestamps) else timestamps[-1]
            inspection.submitted_at = exit_at
            missions_service.complete_mission(db, mission)
            mission.completed_at = exit_at

    if final_state == VehicleState.ANNULE:
        # `ANNULE` n'apparaît jamais après `CONTROLE_EN_COURS` dans `_build_state_path` (seuls
        # les états précoces admettent une annulation) : ce bloc ne s'exécute donc que si la
        # mission est encore `affectee` ou `rdv_planifie` à ce stade, jamais `en_cours`/`terminee`.
        missions_service.cancel_mission(db, mission)

    return counts


def _seed_work_orders_for_vehicle(
    db: Session,
    rng: random.Random,
    vehicle: Vehicle,
    final_state: VehicleState,
    travaux_requis_at: datetime,
    creator: AppUser,
    *,
    storage: PhotoStorage,
    terrain_rng: random.Random,
    bucket: str,
) -> tuple[list[WorkOrder], int, int]:
    """Un à deux `work_order` pour un véhicule ayant transité par `TRAVAUX_REQUIS`, avec leurs
    lignes de coût réel si l'ordre est clos (garde brief J3 : un ordre `termine`/`annule` doit
    porter au moins une ligne), et leurs photos avant/après travaux (mêmes endpoints que J2,
    `phase` liée à `work_order_id` — plan.md, CLAUDE.md § Atelier). Renvoie `(work_orders,
    total_lines, total_photos)`."""
    closed = final_state in (
        VehicleState.TRAVAUX_TERMINES,
        VehicleState.ACHAT_VALIDE,
        VehicleState.REFUSE,
    )
    in_progress = final_state == VehicleState.TRAVAUX_EN_COURS

    nb_orders = rng.randint(1, 2)
    work_orders: list[WorkOrder] = []
    total_lines = 0
    total_photos = 0
    for i in range(nb_orders):
        wo_type = rng.choice(list(WorkOrderType))
        description = rng.choice(_WORK_ORDER_DESCRIPTIONS[wo_type])
        montant_estime = rng.randint(8_000, 120_000)

        if closed:
            # ~10 % annulés (pièce indisponible, renoncement) — reste clos avec une ligne de coût
            # symbolique, jamais 0 ligne (garde).
            state = (
                WorkOrderState.ANNULE.value if rng.random() < 0.10 else WorkOrderState.TERMINE.value
            )
        elif in_progress:
            state = (
                WorkOrderState.EN_COURS.value
                if i == 0
                else rng.choice([WorkOrderState.EN_COURS.value, WorkOrderState.DEMANDE.value])
            )
        else:  # final_state == TRAVAUX_REQUIS
            state = WorkOrderState.DEMANDE.value

        work_order = WorkOrder(
            id=uuid4(),
            vehicle_id=vehicle.id,
            type=wo_type.value,
            state=state,
            description=description,
            montant_estime_cents=montant_estime,
            created_by_id=creator.id,
            requested_at=travaux_requis_at,
            started_at=travaux_requis_at + timedelta(hours=4)
            if state != WorkOrderState.DEMANDE.value
            else None,
            completed_at=travaux_requis_at + timedelta(days=2)
            if state
            in (
                WorkOrderState.TERMINE.value,
                WorkOrderState.ANNULE.value,
            )
            else None,
        )
        db.add(work_order)
        db.flush()
        work_orders.append(work_order)

        # Photo « avant travaux » — dès la prise en charge par l'atelier, quel que soit l'état
        # atteint depuis (documente l'état du véhicule à l'entrée, brief J3).
        _seed_photo(
            db,
            storage,
            terrain_rng,
            bucket=bucket,
            vehicle=vehicle,
            uploader=creator,
            angle=terrain_rng.choice(list(PhotoAngle)).value,
            phase=PhotoPhase.AVANT_TRAVAUX.value,
            inspection_id=None,
            work_order_id=work_order.id,
            captured_at=travaux_requis_at,
        )
        total_photos += 1

        if state in (WorkOrderState.TERMINE.value, WorkOrderState.ANNULE.value):
            nb_lines = rng.randint(1, 3)
            for _ in range(nb_lines):
                categorie = rng.choice(list(WorkOrderLineCategorie))
                libelle = rng.choice(_LINE_LIBELLES[categorie.value])
                quantite = Decimal(rng.choice(["1", "1", "2", "0.5", "3"]))
                prix_unitaire = rng.randint(1_500, 45_000)
                db.add(
                    WorkOrderLine(
                        id=uuid4(),
                        work_order_id=work_order.id,
                        libelle=libelle,
                        categorie=categorie.value,
                        quantite=quantite,
                        prix_unitaire_cents=prix_unitaire,
                        created_at=work_order.completed_at or travaux_requis_at,
                    )
                )
                total_lines += 1

            # Photo « après travaux » — uniquement sur un ordre clos (terminé ou annulé), au
            # moment de sa clôture.
            _seed_photo(
                db,
                storage,
                terrain_rng,
                bucket=bucket,
                vehicle=vehicle,
                uploader=creator,
                angle=terrain_rng.choice(list(PhotoAngle)).value,
                phase=PhotoPhase.APRES_TRAVAUX.value,
                inspection_id=None,
                work_order_id=work_order.id,
                captured_at=work_order.completed_at or travaux_requis_at,
            )
            total_photos += 1
    db.flush()
    return work_orders, total_lines, total_photos


def _maybe_seed_vehicle_cost(
    db: Session, rng: random.Random, vehicle: Vehicle, creator: AppUser, occurred_at: datetime
) -> int:
    """~35 % du parc porte un coût hors atelier (transport, administratif...) — brief J3 :
    la marge doit intégrer autre chose que le seul atelier pour rester crédible."""
    if rng.random() >= 0.35:
        return 0
    cost_type = rng.choice(list(VehicleCostType))
    montant = rng.randint(2_000, 25_000)
    db.add(
        VehicleCost(
            id=uuid4(),
            vehicle_id=vehicle.id,
            type=cost_type.value,
            montant_cents=montant,
            commentaire=_VEHICLE_COST_LIBELLES[cost_type],
            created_by_id=creator.id,
            created_at=occurred_at,
        )
    )
    return 1


def _force_at_least_one_negative_margin(
    db: Session, rng: random.Random, candidates: list[Vehicle], creator: AppUser
) -> bool:
    """Garantit au moins une marge négative dans le jeu de démo (brief J3), sans le laisser au
    hasard du RNG : ajoute une ligne de coût hors atelier sur le véhicule `ACHAT_VALIDE` (jamais
    `REFUSE` — voir correctif ci-dessous) avec `valeur_revente_estimee_cents` la plus faible
    parmi les candidats déjà passés par l'atelier — c'est celui dont la marge naturelle est la
    plus fragile, le forçage reste donc minimal et crédible plutôt qu'arbitrairement extrême.

    Bug corrigé (revue J3, 🔴 n°2) : deux défauts distincts sur la même fonction.
    1. `candidates` acceptait `ACHAT_VALIDE` **ou** `REFUSE` — un véhicule refusé n'a, par
       définition, jamais été acheté (`prix_achat_negocie_cents IS NULL`, cohérent avec le
       correctif du 🔴 n°1) : "perdre de l'argent" n'a de sens métier que sur un achat réel.
       L'appelant (fin de la boucle principale, plus bas) ne verse donc désormais plus que les
       véhicules `ACHAT_VALIDE` dans `candidates`.
    2. Le montant forcé (`valeur_revente + un tirage 50 000-150 000`) produisait une marge
       négative d'un ordre de grandeur sans rapport avec les marges positives du jeu de démo
       (quelques milliers d'euros) — invisible dans un graphique trié par magnitude. Le montant
       est désormais calculé pour atteindre une marge négative **du même ordre que les marges
       positives affichées** (-2 000 € à -4 000 €), en repartant de la marge réellement calculée
       à ce stade (revente − achat − transport − coûts déjà engagés), pas d'une valeur arbitraire
       empilée par-dessus.
    """
    achat_valide_candidates = [v for v in candidates if v.state == VehicleState.ACHAT_VALIDE.value]
    if not achat_valide_candidates:
        return False
    target = min(achat_valide_candidates, key=lambda v: v.valeur_revente_estimee_cents or 0)

    couts_hors_atelier = (
        db.scalar(
            select(func.coalesce(func.sum(VehicleCost.montant_cents), 0)).where(
                VehicleCost.vehicle_id == target.id
            )
        )
        or 0
    )
    couts_atelier_reel = (
        db.scalar(
            select(func.coalesce(func.sum(WorkOrderLine.montant_cents), 0))
            .select_from(WorkOrderLine)
            .join(WorkOrder, WorkOrder.id == WorkOrderLine.work_order_id)
            .where(WorkOrder.vehicle_id == target.id)
        )
        or 0
    )
    marge_avant_forcage = (
        (target.valeur_revente_estimee_cents or 0)
        - (target.prix_achat_negocie_cents or 0)
        - target.frais_transport_cents
        - couts_hors_atelier
        - couts_atelier_reel
    )

    # Cible : une marge négative du même ordre que les marges positives du jeu de démo
    # (quelques milliers d'euros), pour rester visible dans un graphique trié par magnitude —
    # pas un montant arbitrairement extrême.
    marge_cible = -rng.randint(200_000, 400_000)
    montant_ligne = marge_avant_forcage - marge_cible
    # Garde-fou : `montant_cents >= 0` est une contrainte de `vehicle_cost` (plan.md § 5.1) — si
    # la marge était déjà, par coïncidence, plus négative que la cible, un tout petit surcoût
    # suffit à garantir "négative" sans viser une magnitude précise dans ce cas résiduel.
    montant_ligne = max(montant_ligne, 10_000)

    db.add(
        VehicleCost(
            id=uuid4(),
            vehicle_id=target.id,
            type=VehicleCostType.REMISE_EN_ETAT_EXTERNE.value,
            montant_cents=montant_ligne,
            commentaire="Casse moteur découverte après reprise — remise en état externalisée",
            created_by_id=creator.id,
            created_at=datetime.combine(target.date_proposition, datetime.min.time(), tzinfo=UTC),
        )
    )
    return True


# SIRET de « Benard SARL » dans le jeu de démo — identique à `DEMO_SIRET` dans
# `frontend/e2e/j1-saisie.spec.ts` (le seed s'aligne sur le test, jamais l'inverse : ce fichier
# n'est pas dans le périmètre backend).
DEDUP_DEMO_SIRET = "11951548967612"


def _calibrate_dedup_demo_vehicle(
    db: Session, companies: list[Company], today: date, operatrice: AppUser
) -> None:
    """Garantit, de façon stable et **indépendante de la position dans le flux `rng`**,
    l'existence d'un véhicule qui déclenche l'arbitrage de doublon `duplicate_probable` en démo
    — critère d'acceptation J1 du brief, exercé par `frontend/e2e/j1-saisie.spec.ts`.

    Bug vécu (signalé par dev-frontend au jalon J3, à ne plus jamais reproduire) : ce scénario
    reposait auparavant uniquement sur le hasard déterministe de la boucle ci-dessus — un
    véhicule Renault Kangoo essence pour « Benard SARL » atterrissait *par coïncidence* à un
    kilométrage proche de celui saisi par le test e2e (~120 500 km). Ajouter la moindre
    consommation de `rng` en amont dans ce module (ex. l'historique de transitions ajouté en J3)
    décale tous les tirages suivants et change ce kilométrage sans aucun signal — exactement ce
    qui s'est produit (120 279 → 143 783 km, écart passé au-delà du seuil d'exclusion dure de
    5 000 km, plan.md § 4 décision A étape 2 : la fiche a cessé d'être candidate). Cette fonction
    fixe donc les champs déterminants du score (marque/modèle/énergie/kilométrage/date de
    proposition/absence de VIN et d'immatriculation) **en dur, après coup**, sans dépendre
    d'aucun tirage `rng` — une réécriture future de la boucle ci-dessus, quelle qu'elle soit, ne
    peut plus jamais la recasser silencieusement. Même principe qui justifie `terrain_rng`
    (flux RNG séparé) pour toute la génération terrain J2 ajoutée plus haut dans ce module.

    Réutilise le premier véhicule Renault Kangoo déjà généré pour cette société s'il en existe un
    (cas du run actuel), sinon en crée un dédié — dans les deux cas le résultat exposé au test
    e2e est identique et déterministe. **Ne pas retirer ni déplacer cet appel** sans mettre à
    jour `frontend/e2e/j1-saisie.spec.ts` en conséquence.
    """
    company = next((c for c in companies if c.siret == DEDUP_DEMO_SIRET), None)
    if company is None:
        return  # SIRET introuvable — garde défensive, ne devrait jamais arriver (§ 4 décision D)

    vehicle = db.scalar(
        select(Vehicle).where(
            Vehicle.company_id == company.id,
            Vehicle.marque == "Renault",
            Vehicle.modele == "Kangoo",
        )
    )

    calibrated_date_proposition = today - timedelta(days=15)
    calibrated_created_at = datetime.combine(
        calibrated_date_proposition, datetime.min.time(), tzinfo=UTC
    )

    if vehicle is not None:
        # Bug corrigé (revue J3, 🟠 n°4) : cette branche ne réécrivait que `date_proposition`,
        # jamais `created_at`/`state_changed_at`/l'`occurred_at` de la transition `BROUILLON` —
        # le véhicule vedette de la démonstration du dédoublonnage (J1) se retrouvait "créé"
        # 41 jours avant d'avoir été "proposé" (`created_at` hérité du tirage `rng` d'origine,
        # `date_proposition` recalé sur `today - 15 j`). La branche "création" ci-dessous alignait
        # déjà les trois — celle-ci fait maintenant de même, pour rester symétrique.
        vehicle.energie = "essence"
        vehicle.kilometrage = 120_279
        vehicle.vin = None
        vehicle.vin_normalise = None
        vehicle.immatriculation = None
        vehicle.immat_normalisee = None
        vehicle.date_proposition = calibrated_date_proposition
        vehicle.created_at = calibrated_created_at
        vehicle.state_changed_at = calibrated_created_at
        brouillon_transition = db.scalar(
            select(VehicleStateTransition)
            .where(
                VehicleStateTransition.vehicle_id == vehicle.id,
                VehicleStateTransition.to_state == VehicleState.BROUILLON.value,
            )
            .order_by(VehicleStateTransition.occurred_at)
            .limit(1)
        )
        if brouillon_transition is not None:
            brouillon_transition.occurred_at = calibrated_created_at
        db.flush()
        return

    vehicle = Vehicle(
        id=uuid4(),
        reference=generate_reference(db),
        company_id=company.id,
        state=VehicleState.BROUILLON.value,
        marque="Renault",
        modele="Kangoo",
        modele_normalise=normalize_modele("Renault", "Kangoo"),
        energie="essence",
        date_proposition=calibrated_date_proposition,
        kilometrage=120_279,
        frais_transport_cents=0,
        created_by_id=operatrice.id,
        state_changed_at=calibrated_created_at,
        created_at=calibrated_created_at,
    )
    db.add(vehicle)
    db.flush()
    db.add(
        VehicleStateTransition(
            id=uuid4(),
            vehicle_id=vehicle.id,
            from_state=None,
            to_state=VehicleState.BROUILLON.value,
            actor_id=operatrice.id,
            actor_role=UserRole.OPERATRICE.value,
            reason="Création (seed démo — calibrage dédoublonnage)",
            occurred_at=calibrated_created_at,
        )
    )
    db.flush()


def snapshot_stale_seed_photo_prefixes(storage: PhotoStorage, *, bucket: str) -> list[str]:
    """Photographie, **avant** d'appeler `seed_demo`, la liste des sous-répertoires déjà présents
    sous `seed/` (un par véhicule du run précédent) — c'est cette liste, et seulement elle, que
    `purge_stale_seed_photos` supprimera une fois le nouveau run commité.

    Pourquoi pas un simple `delete_prefix(bucket=bucket, prefix="seed/")` global après coup :
    les identifiants de véhicule sont des `uuid4()` non seedés (jamais tirés du `rng`/`terrain_
    rng` déterministes, cf. docstring de module) — le run courant écrit donc ses photos sous des
    sous-répertoires **différents** de ceux du run précédent, qui cohabitent tous les deux sous
    `seed/` le temps du run (« deux générations transitoires »). Un `delete_prefix("seed/")`
    global supprimerait indifféremment l'ancienne ET la nouvelle génération. Cette fonction fige
    la liste des seuls sous-répertoires « anciens » avant que la nouvelle génération n'apparaisse,
    pour que `purge_stale_seed_photos` ne touche jamais qu'à eux."""
    return storage.list_top_level(bucket=bucket, prefix=f"{_PHOTO_STORAGE_PREFIX}/")


def purge_stale_seed_photos(
    storage: PhotoStorage, *, bucket: str, stale_prefixes: list[str]
) -> int:
    """Purge sélectivement les sous-répertoires `seed/{prefix}/` listés par `stale_prefixes`
    (capturés par `snapshot_stale_seed_photo_prefixes` **avant** le run courant) — jamais un
    `delete_prefix("seed/")` global, qui emporterait aussi les photos que le run courant vient
    d'écrire.

    À appeler par le code appelant **après** que son propre commit (TRUNCATE + seed) a réussi —
    jamais depuis `seed_demo` lui-même (correctif revue finale J3 § 🟠 n°6, voir la note dans
    `seed_demo`). Traitée comme best-effort par les appelants (`app/seed/reset.py`, `app/cli.py`) :
    un échec ne doit jamais faire échouer le seed/reset lui-même, les fichiers de la veille
    restant simplement orphelins jusqu'au prochain run réussi."""
    return sum(
        storage.delete_prefix(bucket=bucket, prefix=f"{_PHOTO_STORAGE_PREFIX}/{stale}/")
        for stale in stale_prefixes
    )


def seed_demo(
    db: Session,
    *,
    force: bool = False,
    today: date | None = None,
    storage: PhotoStorage | None = None,
) -> dict[str, int]:
    """Point d'entrée du profil `demo`. Appelé après `seed --profile reference` (mêmes comptes).

    `storage` est injectable (tests) — défaut `get_storage_backend()`, la même fabrique que le
    reste de l'application (`app/services/storage/service.py`)."""
    _assert_only_demo_accounts(db, force=force)

    today = today or date.today()
    rng = random.Random(SEED_VERSION)
    faker = Faker("fr_FR")
    faker.seed_instance(SEED_VERSION)
    # Flux RNG dédié à toute la génération terrain (mission/inspection/photo/notification) —
    # voir la docstring de module : ne jamais faire consommer un tirage terrain par `rng`.
    terrain_rng = random.Random(f"{SEED_VERSION}-terrain")

    storage = storage or get_storage_backend()
    settings = get_settings()
    bucket = settings.supabase_bucket
    # Idempotence sur disque, pas seulement en base : les nouvelles photos sont écrites sous des
    # clés `uuid4()` (aucune collision possible avec le run précédent), donc PAS de purge ici.
    # Correctif revue finale J3 § 🟠 n°6 : purger le préfixe `seed/` en tout début de fonction
    # cassait l'atomicité gagnée par `app/seed/reset.py` (TRUNCATE + seed dans la MÊME
    # transaction) — un échec de seed après cette ligne annulait le TRUNCATE en base (rollback)
    # mais pas la suppression déjà faite sur disque : la démo publique se serait retrouvée avec
    # les 583 lignes `photo` de la veille pointant vers des fichiers déjà supprimés (vignettes
    # cassées, 404 silencieux, sans aucune erreur applicative). La purge des anciennes clés se
    # fait désormais APRÈS le commit, côté appelant (`purge_stale_seed_photos`, appelée par
    # `app/seed/reset.py::run_demo_reset` et `app/cli.py::seed`), au même titre et pour la même
    # raison que la purge du préfixe `runtime/`.

    checklist_template = _get_default_checklist_template(db)
    checklist_items = list(
        db.scalars(
            select(ChecklistItemTemplate)
            .where(ChecklistItemTemplate.template_id == checklist_template.id)
            .order_by(ChecklistItemTemplate.ordre)
        ).all()
    )

    operatrice = _get_demo_user(db, UserRole.OPERATRICE)
    administrateur = _get_demo_user(db, UserRole.ADMINISTRATEUR)
    chauffeur = _get_demo_user(db, UserRole.CHAUFFEUR)
    atelier = _get_demo_user(db, UserRole.ATELIER)

    companies = _seed_companies(db, rng, faker, administrateur)

    created_vehicles = 0
    created_work_orders = 0
    created_work_order_lines = 0
    created_vehicle_costs = 0
    created_missions = 0
    created_inspections = 0
    created_photos = 0
    created_notifications = 0
    negative_margin_candidates: list[Vehicle] = []

    for _ in range(NUM_VEHICLES):
        company = rng.choice(companies)
        marque, modele, energie = rng.choice(CATALOGUE)
        final_state = _pick_state(rng)
        offset_days = rng.randint(0, DATE_WINDOW_DAYS)
        date_proposition = today - timedelta(days=offset_days)
        kilometrage = rng.randint(15000, 160000)
        prix_achat_cents = rng.randint(300_000, 2_500_000)
        # ~12 % sans valeur de revente estimée — démontre `has_marge = false` / marge affichée
        # « — » (jamais 0), la règle non négociable de la formule (plan.md § 5.2).
        has_valeur_revente = rng.random() >= 0.12
        valeur_revente_cents = (
            int(prix_achat_cents * rng.uniform(1.05, 1.35)) if has_valeur_revente else None
        )
        frais_transport_cents = rng.randint(0, 15_000)

        path = _build_state_path(rng, final_state)
        timestamps = _spread_timestamps(rng, path, date_proposition, today)

        # Un prix négocié n'a de sens qu'une fois le contrôle conclu vers un chemin d'achat
        # (REFUSE/ANNULE : jamais de prix négocié, cohérent avec l'automate qui ne l'exige à
        # aucune de leurs gardes — plan.md § 5.3).
        is_priced = final_state in (
            VehicleState.TRAVAUX_REQUIS,
            VehicleState.TRAVAUX_EN_COURS,
            VehicleState.TRAVAUX_TERMINES,
            VehicleState.ACHAT_VALIDE,
        )
        is_assigned = VehicleState.AFFECTE in path

        vehicle = Vehicle(
            id=uuid4(),
            reference=generate_reference(db),
            company_id=company.id,
            state=final_state.value,
            marque=marque,
            modele=modele,
            modele_normalise=normalize_modele(marque, modele),
            energie=energie,
            date_proposition=date_proposition,
            kilometrage=kilometrage,
            prix_achat_negocie_cents=prix_achat_cents if is_priced else None,
            valeur_revente_estimee_cents=valeur_revente_cents,
            frais_transport_cents=frais_transport_cents,
            created_by_id=rng.choice([operatrice, administrateur]).id,
            assigned_driver_id=chauffeur.id if is_assigned else None,
            state_changed_at=timestamps[-1],
            # `created_at` doit coïncider avec le premier maillon de la frise (`timestamps[0]`,
            # la transition BROUILLON), jamais le défaut `server_default=now()` de
            # `TimestampMixin` : sans cet override, la « création de la fiche » du seed a lieu à
            # l'instant réel du script, systématiquement postérieure aux transitions rétrodatées
            # de `date_proposition` — délai de cycle négatif dans `analytics.mart_cycle_temps`
            # (bug trouvé en vérifiant la démo J3 après écriture du mart, pas en le devinant).
            created_at=timestamps[0],
        )

        if final_state == VehicleState.REFUSE:
            motif = rng.choice(REFUS_MOTIF_CHOICES)
            vehicle.refus_motif = motif.value
            vehicle.refus_commentaire = f"Refus démo — {motif.value.replace('_', ' ')}"

        db.add(vehicle)
        db.flush()

        # Un seul acteur pour toute la frise, par simplicité (l'important pour la démo est la
        # présence même des maillons intermédiaires, pas l'exactitude de qui a cliqué chaque
        # bouton — voir docs/wiki/pieges-projet.md « la frise saute cinq états »).
        _write_transition_history(db, vehicle, path, timestamps, operatrice)

        terrain_counts = _seed_terrain_for_vehicle(
            db,
            storage,
            terrain_rng,
            bucket=bucket,
            vehicle=vehicle,
            company=company,
            path=path,
            timestamps=timestamps,
            final_state=final_state,
            chauffeur=chauffeur,
            operatrice=operatrice,
            checklist_template=checklist_template,
            checklist_items=checklist_items,
        )
        created_missions += terrain_counts["missions"]
        created_inspections += terrain_counts["inspections"]
        created_photos += terrain_counts["photos"]
        created_notifications += terrain_counts["notifications"]

        if VehicleState.TRAVAUX_REQUIS in path:
            travaux_idx = path.index(VehicleState.TRAVAUX_REQUIS)
            work_orders, nb_lines, nb_wo_photos = _seed_work_orders_for_vehicle(
                db,
                rng,
                vehicle,
                final_state,
                timestamps[travaux_idx],
                atelier,
                storage=storage,
                terrain_rng=terrain_rng,
                bucket=bucket,
            )
            created_work_orders += len(work_orders)
            created_work_order_lines += nb_lines
            created_photos += nb_wo_photos
            # Correctif 🔴 n°2 (revue J3) : REFUSE retiré des candidats — un véhicule refusé
            # n'a jamais été acheté, une "marge négative" dessus n'a aucun sens métier.
            if final_state == VehicleState.ACHAT_VALIDE and has_valeur_revente:
                negative_margin_candidates.append(vehicle)

        created_vehicle_costs += _maybe_seed_vehicle_cost(
            db, rng, vehicle, administrateur, timestamps[-1]
        )

        created_vehicles += 1

    # Correctif revue finale J3 § 🟠 n°5 : la valeur de retour (True si une ligne `VehicleCost`
    # a réellement été insérée) était jetée — `created_vehicle_costs` ne comptait donc jamais
    # cette ligne, alors qu'elle existe bien en base. `rows_created["vehicle_costs"]` est la
    # seule trace d'observabilité du cron nocturne en production : elle doit refléter le compte
    # réel.
    created_vehicle_costs += int(
        _force_at_least_one_negative_margin(db, rng, negative_margin_candidates, administrateur)
    )
    _calibrate_dedup_demo_vehicle(db, companies, today, operatrice)

    db.flush()
    return {
        "companies": len(companies),
        "vehicles": created_vehicles,
        "work_orders": created_work_orders,
        "work_order_lines": created_work_order_lines,
        "vehicle_costs": created_vehicle_costs,
        "missions": created_missions,
        "inspections": created_inspections,
        "photos": created_photos,
        "notifications": created_notifications,
    }
