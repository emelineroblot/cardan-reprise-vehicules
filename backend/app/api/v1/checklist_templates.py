"""`/checklist-templates/*` — référentiel de checklist, brief J2 (« checklist interactive »).

Manque signalé par dev-backend en revue de contrat, tranché par l'orchestrateur : sans cet
endpoint, dev-frontend ne peut pas rendre le formulaire de contrôle (le référentiel n'est
autrement accessible que via les réponses déjà posées d'une inspection existante, `GET
/inspections/{id}`, ce qui ne fonctionne pas avant la première réponse). Lecture seule, ouverte
à tout rôle authentifié — donnée de référence sans caractère sensible, au même titre que `GET
/vehicles/{id}/transitions`.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.core.errors import ApiError
from app.db.session import get_db
from app.models.checklist import ChecklistTemplate
from app.models.user import AppUser
from app.schemas.checklist import ChecklistTemplateBrief, ChecklistTemplateRead

router = APIRouter()


@router.get("", response_model=list[ChecklistTemplateBrief])
def list_checklist_templates(
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
    is_active: bool = True,
) -> list[ChecklistTemplate]:
    """Sans les items (volumétrie dérisoire — quelques modèles) : le détail se récupère par
    `GET /checklist-templates/{id}`, typiquement à partir du `template_id` renvoyé par
    `POST /inspections` / `GET /inspections/{id}`."""
    stmt = (
        select(ChecklistTemplate)
        .where(ChecklistTemplate.is_active.is_(is_active))
        .order_by(ChecklistTemplate.code, ChecklistTemplate.version.desc())
    )
    return list(db.scalars(stmt).all())


@router.get("/{template_id}", response_model=ChecklistTemplateRead)
def get_checklist_template(
    template_id: UUID,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> ChecklistTemplate:
    template = db.scalar(
        select(ChecklistTemplate)
        .where(ChecklistTemplate.id == template_id)
        .options(selectinload(ChecklistTemplate.items))
    )
    if template is None:
        raise ApiError("not_found", "Modèle de checklist introuvable.")
    return template
