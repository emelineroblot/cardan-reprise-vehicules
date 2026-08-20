"""Seed `demo` — ~90 véhicules sur 3 mois, distribution réaliste (plan.md § 4 décision D).

Déterministe (`random.Random(SEED_VERSION)` + `Faker('fr_FR')` à graine fixe), mais les **dates
sont recalculées relativement à `date.today()`** : la démo montre toujours « les 3 derniers
mois », jamais un historique qui vieillit (le détail le plus souvent raté en démo).

Les SIRET sont fictifs mais à clé de Luhn valide, et **préchargés dans `company_lookup_cache`**
avec `source='demo'` : le parcours de démo ne déclenche jamais d'appel réseau (décision B).
"""

from __future__ import annotations

import random
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from faker import Faker
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.company import Company, CompanyLookupCache
from app.models.enums import (
    RefusMotif,
    TypeFlotte,
    UserRole,
    VehicleState,
)
from app.models.user import AppUser
from app.models.vehicle import Vehicle, VehicleStateTransition
from app.seed.reference import DEMO_ACCOUNTS
from app.services.company_lookup.base import CompanyLookupResult
from app.services.normalize import normalize_modele
from app.services.siret import is_valid_siret
from app.services.vehicles import generate_reference

SEED_VERSION = "demo-v1"
NUM_VEHICLES = 90
NUM_COMPANIES = 12
DATE_WINDOW_DAYS = 90

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


def seed_demo(db: Session, *, force: bool = False, today: date | None = None) -> dict[str, int]:
    """Point d'entrée du profil `demo`. Appelé après `seed --profile reference` (mêmes comptes)."""
    _assert_only_demo_accounts(db, force=force)

    today = today or date.today()
    rng = random.Random(SEED_VERSION)
    faker = Faker("fr_FR")
    faker.seed_instance(SEED_VERSION)

    operatrice = _get_demo_user(db, UserRole.OPERATRICE)
    administrateur = _get_demo_user(db, UserRole.ADMINISTRATEUR)
    chauffeur = _get_demo_user(db, UserRole.CHAUFFEUR)

    companies = _seed_companies(db, rng, faker, administrateur)

    created_vehicles = 0
    for _ in range(NUM_VEHICLES):
        company = rng.choice(companies)
        marque, modele, energie = rng.choice(CATALOGUE)
        state = _pick_state(rng)
        offset_days = rng.randint(0, DATE_WINDOW_DAYS)
        date_proposition = today - timedelta(days=offset_days)
        kilometrage = rng.randint(15000, 160000)
        prix_achat_cents = rng.randint(300_000, 2_500_000)
        valeur_revente_cents = int(prix_achat_cents * rng.uniform(1.05, 1.35))
        frais_transport_cents = rng.randint(0, 15_000)

        is_terminal_active = state in (
            VehicleState.ACHAT_VALIDE,
            VehicleState.TRAVAUX_TERMINES,
            VehicleState.TRAVAUX_EN_COURS,
        )
        is_assigned = state not in (VehicleState.BROUILLON,)

        vehicle = Vehicle(
            id=uuid4(),
            reference=generate_reference(db),
            company_id=company.id,
            state=state.value,
            marque=marque,
            modele=modele,
            modele_normalise=normalize_modele(marque, modele),
            energie=energie,
            date_proposition=date_proposition,
            kilometrage=kilometrage,
            prix_achat_negocie_cents=prix_achat_cents if is_terminal_active else None,
            valeur_revente_estimee_cents=valeur_revente_cents,
            frais_transport_cents=frais_transport_cents,
            created_by_id=rng.choice([operatrice, administrateur]).id,
            assigned_driver_id=chauffeur.id if is_assigned else None,
            state_changed_at=datetime.combine(date_proposition, datetime.min.time(), tzinfo=UTC),
        )

        if state == VehicleState.REFUSE:
            motif = rng.choice(REFUS_MOTIF_CHOICES)
            vehicle.refus_motif = motif.value
            vehicle.refus_commentaire = f"Refus démo — {motif.value.replace('_', ' ')}"

        db.add(vehicle)
        db.flush()

        db.add(
            VehicleStateTransition(
                id=uuid4(),
                vehicle_id=vehicle.id,
                from_state=None,
                to_state=VehicleState.BROUILLON.value,
                actor_id=vehicle.created_by_id,
                actor_role=UserRole.OPERATRICE.value,
                reason="Création (seed démo)",
                occurred_at=vehicle.state_changed_at,
            )
        )
        if state != VehicleState.BROUILLON:
            db.add(
                VehicleStateTransition(
                    id=uuid4(),
                    vehicle_id=vehicle.id,
                    from_state=VehicleState.BROUILLON.value,
                    to_state=state.value,
                    actor_id=vehicle.created_by_id,
                    actor_role=UserRole.OPERATRICE.value,
                    reason="Progression (seed démo)",
                    occurred_at=vehicle.state_changed_at,
                )
            )

        created_vehicles += 1

    db.flush()
    return {"companies": len(companies), "vehicles": created_vehicles}
