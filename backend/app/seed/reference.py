"""Seed `reference` — 4 comptes de démo, checklists et items (plan.md § 4 décision D).

Idempotent (upsert par `code`/`email`), rejouable après chaque migration. Le référentiel
n'est pas versionné par Alembic : il évolue à chaque jalon, et un upsert idempotent bat une
chaîne de migrations de données.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.checklist import ChecklistItemTemplate, ChecklistTemplate
from app.models.enums import ChecklistCategorie, ResponseType, UserRole
from app.models.user import AppUser

# Mots de passe publics et affichés sur l'écran de connexion — données fictives, base
# réinitialisée chaque nuit, aucune donnée personnelle (plan.md § 3.4).
DEMO_PASSWORD = "demo1234"  # aligné sur frontend/src/lib/auth/demo-accounts.ts (déjà écrit)


@dataclass(frozen=True)
class DemoAccount:
    email: str
    full_name: str
    role: UserRole
    telephone: str | None = None


DEMO_ACCOUNTS: tuple[DemoAccount, ...] = (
    DemoAccount("operatrice@cardan.demo", "Claire Dubois", UserRole.OPERATRICE, "0601020304"),
    DemoAccount("chauffeur@cardan.demo", "Karim Benali", UserRole.CHAUFFEUR, "0601020305"),
    DemoAccount(
        "administrateur@cardan.demo", "Sophie Marchand", UserRole.ADMINISTRATEUR, "0601020306"
    ),
    DemoAccount("atelier@cardan.demo", "Yanis Perrot", UserRole.ATELIER, "0601020307"),
)

CHECKLIST_CONTROLE_CODE = "controle_standard"

CHECKLIST_ITEMS: tuple[tuple[str, str, ChecklistCategorie, int, bool, ResponseType], ...] = (
    (
        "carrosserie_generale",
        "État général de la carrosserie",
        ChecklistCategorie.EXTERIEUR,
        1,
        True,
        ResponseType.NOTE_1_5,
    ),
    (
        "pare_brise",
        "Pare-brise sans impact",
        ChecklistCategorie.EXTERIEUR,
        2,
        True,
        ResponseType.OK_KO,
    ),
    (
        "pneus",
        "État des pneumatiques",
        ChecklistCategorie.EXTERIEUR,
        3,
        True,
        ResponseType.NOTE_1_5,
    ),
    (
        "interieur_proprete",
        "Propreté intérieure",
        ChecklistCategorie.INTERIEUR,
        4,
        True,
        ResponseType.NOTE_1_5,
    ),
    (
        "sellerie",
        "État de la sellerie",
        ChecklistCategorie.INTERIEUR,
        5,
        True,
        ResponseType.NOTE_1_5,
    ),
    (
        "demarrage",
        "Démarrage sans anomalie",
        ChecklistCategorie.MECANIQUE,
        6,
        True,
        ResponseType.OK_KO,
    ),
    (
        "niveaux",
        "Niveaux (huile, liquide de refroidissement)",
        ChecklistCategorie.MECANIQUE,
        7,
        True,
        ResponseType.OK_KO,
    ),
    (
        "freinage",
        "Freinage sans bruit ni vibration",
        ChecklistCategorie.MECANIQUE,
        8,
        True,
        ResponseType.OK_KO,
    ),
    (
        "carte_grise",
        "Carte grise présente",
        ChecklistCategorie.DOCUMENTS,
        9,
        True,
        ResponseType.OK_KO,
    ),
    (
        "controle_technique",
        "Contrôle technique à jour",
        ChecklistCategorie.DOCUMENTS,
        10,
        True,
        ResponseType.OK_KO,
    ),
    (
        "kilometrage_releve",
        "Kilométrage relevé au compteur",
        ChecklistCategorie.DOCUMENTS,
        11,
        True,
        ResponseType.NUMERIQUE,
    ),
    (
        "triangle_gilet",
        "Triangle et gilet présents",
        ChecklistCategorie.SECURITE,
        12,
        False,
        ResponseType.OK_KO,
    ),
    (
        "extincteur",
        "Extincteur présent (le cas échéant)",
        ChecklistCategorie.SECURITE,
        13,
        False,
        ResponseType.OK_KO,
    ),
    (
        "commentaire_libre",
        "Observations libres du chauffeur",
        ChecklistCategorie.MECANIQUE,
        14,
        False,
        ResponseType.TEXTE,
    ),
)


def seed_accounts(db: Session) -> int:
    created_or_updated = 0
    for account in DEMO_ACCOUNTS:
        user = db.scalar(select(AppUser).where(AppUser.email == account.email))
        if user is None:
            user = AppUser(
                id=uuid4(),
                email=account.email,
                password_hash=hash_password(DEMO_PASSWORD),
                full_name=account.full_name,
                role=account.role.value,
                telephone=account.telephone,
                is_active=True,
            )
            db.add(user)
        else:
            user.full_name = account.full_name
            user.role = account.role.value
            user.telephone = account.telephone
            user.is_active = True
            user.password_hash = hash_password(DEMO_PASSWORD)
        created_or_updated += 1
    db.flush()
    return created_or_updated


def seed_checklist(db: Session) -> int:
    template = db.scalar(
        select(ChecklistTemplate).where(ChecklistTemplate.code == CHECKLIST_CONTROLE_CODE)
    )
    if template is None:
        template = ChecklistTemplate(
            id=uuid4(),
            code=CHECKLIST_CONTROLE_CODE,
            libelle="Contrôle standard sur place",
            version=1,
            is_active=True,
        )
        db.add(template)
        db.flush()

    count = 0
    for code, libelle, categorie, ordre, is_required, response_type in CHECKLIST_ITEMS:
        item = db.scalar(
            select(ChecklistItemTemplate).where(
                ChecklistItemTemplate.template_id == template.id,
                ChecklistItemTemplate.code == code,
            )
        )
        if item is None:
            item = ChecklistItemTemplate(
                id=uuid4(),
                template_id=template.id,
                code=code,
                libelle=libelle,
                categorie=categorie.value,
                ordre=ordre,
                is_required=is_required,
                response_type=response_type.value,
            )
            db.add(item)
        else:
            item.libelle = libelle
            item.categorie = categorie.value
            item.ordre = ordre
            item.is_required = is_required
            item.response_type = response_type.value
        count += 1
    db.flush()
    return count


def seed_reference(db: Session) -> dict[str, int]:
    """Point d'entrée du profil `reference` — idempotent, appelé par le CLI et par le reset."""
    accounts = seed_accounts(db)
    items = seed_checklist(db)
    return {"accounts": accounts, "checklist_items": items}
