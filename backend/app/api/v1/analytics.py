"""`POST /analytics/refresh`, `GET /analytics/status` — plan.md § 6 vague 4.

`GET /analytics/{marge,cycle-temps,pipeline-etat,refus,travaux,kpi-global}` — lecture des marts
J3 (plan.md § 5.2, brief J3). Chaque endpoint est une lecture directe d'un `mart_*` (`SELECT`
brut, schéma `analytics` hors ORM par construction — § 3.7-4) : aucun calcul de marge, de délai
ou de taux n'a lieu ici ni côté front, seulement des filtres/tris sur des colonnes déjà
matérialisées. Réservés à l'administrateur — le dashboard de pilotage est un écran admin (brief
J3 « Administration »).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.analytics.runner import latest_refresh_status, refresh
from app.api.deps import require_roles
from app.db.session import get_db
from app.models.user import AppUser
from app.schemas.analytics import (
    CycleTempsRead,
    KpiGlobalRead,
    PipelineEtatRead,
    RefusRead,
    TravauxRead,
    VehiculeMargeRead,
)

router = APIRouter()

_ADMIN_ONLY = ("administrateur",)


@router.post("/refresh")
def refresh_analytics(
    user: AppUser = Depends(require_roles(*_ADMIN_ONLY)),
) -> dict:
    """Câblé sur le bouton « Actualiser les indicateurs » du dashboard (plan.md § 3.7-5)."""
    results = refresh()
    return {"results": results}


@router.get("/status")
def analytics_status(
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_roles(*_ADMIN_ONLY)),
) -> dict:
    return {"marts": latest_refresh_status(db)}


@router.get("/marge", response_model=list[VehiculeMargeRead])
def get_marge(
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_roles(*_ADMIN_ONLY)),
    state: str | None = None,
    sort: str = "-marge_cents",
) -> list[dict]:
    """`GET /analytics/marge` — marge par véhicule (brief J3, cœur de la démonstration).

    `sort` accepte `marge_cents`/`-marge_cents`/`date_proposition`/`-date_proposition` ; toute
    autre valeur retombe sur `-marge_cents`. Les lignes sans valeur estimée (`has_marge = false`,
    `marge_cents = NULL`) sont placées en fin de tri (`NULLS LAST`), jamais mêlées aux marges
    réellement nulles ou négatives.

    Bug corrigé (revue dev-frontend J3, 🔴 bloquant) : `WHERE (:state IS NULL OR state = :state)`
    levait systématiquement `psycopg.errors.AmbiguousParameter` (« could not determine data type
    of parameter $1 ») — psycopg 3 en protocole étendu prépare la requête une fois pour son texte
    SQL et doit fixer le type de chaque `$n` à la préparation, indépendamment de la valeur liée
    ensuite ; `$1 IS NULL` ne contraint aucun type, donc l'échec se produisait **avec et sans**
    filtre `state` (vérifié : reproduit hors HTTP dans les deux cas avant correctif). La clause
    `WHERE state = :state` n'est désormais émise que lorsque `state` est effectivement fourni —
    chaque forme de requête a alors une signature de paramètres non ambiguë, sans caster ni lier
    de type explicitement (inutile une fois l'ambiguïté structurelle supprimée).
    """
    sort_columns = {"marge_cents": "marge_cents", "date_proposition": "date_proposition"}
    sort_key = sort.lstrip("-")
    column = sort_columns.get(sort_key, "marge_cents")
    direction = "DESC" if sort.startswith("-") or sort_key not in sort_columns else "ASC"

    where_clause = ""
    params: dict[str, str] = {}
    if state is not None:
        where_clause = "WHERE state = :state"
        params["state"] = state

    query = f"""
        SELECT * FROM analytics.mart_vehicule_marge
        {where_clause}
        ORDER BY {column} {direction} NULLS LAST
    """  # noqa: S608 — `column`/`direction`/`where_clause` viennent de listes blanches fixes
    # ci-dessus, jamais d'une entrée utilisateur interpolée directement (seul `:state`, quand
    # présent, est un paramètre lié).
    rows = db.execute(text(query), params).mappings().all()
    return [dict(row) for row in rows]


@router.get("/cycle-temps", response_model=list[CycleTempsRead])
def get_cycle_temps(
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_roles(*_ADMIN_ONLY)),
) -> list[dict]:
    """`GET /analytics/cycle-temps` — délai de cycle par véhicule (brief J3), de la création de
    la fiche à la décision d'achat/refus/annulation."""
    rows = (
        db.execute(text("SELECT * FROM analytics.mart_cycle_temps ORDER BY vehicle_id"))
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


@router.get("/pipeline-etat", response_model=list[PipelineEtatRead])
def get_pipeline_etat(
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_roles(*_ADMIN_ONLY)),
) -> list[dict]:
    """`GET /analytics/pipeline-etat` — vue d'ensemble analytique du pipeline (valeur immobilisée
    par état). Distinct de `GET /vehicles/pipeline-counts` (opérationnel, live, sert le Kanban
    manipulable) : celui-ci sert le dashboard, à la fraîcheur du dernier `refresh`."""
    rows = (
        db.execute(text("SELECT * FROM analytics.mart_pipeline_etat ORDER BY state"))
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


@router.get("/refus", response_model=list[RefusRead])
def get_refus(
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_roles(*_ADMIN_ONLY)),
) -> list[dict]:
    """`GET /analytics/refus` — taux de refus par mois × type de flotte (brief J3)."""
    rows = (
        db.execute(text("SELECT * FROM analytics.mart_refus ORDER BY mois, type_flotte"))
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


@router.get("/travaux", response_model=list[TravauxRead])
def get_travaux(
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_roles(*_ADMIN_ONLY)),
) -> list[dict]:
    """`GET /analytics/travaux` — coût moyen des travaux par mois × type (brief J3)."""
    rows = (
        db.execute(text("SELECT * FROM analytics.mart_travaux ORDER BY mois, type"))
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


@router.get("/kpi-global", response_model=KpiGlobalRead)
def get_kpi_global(
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_roles(*_ADMIN_ONLY)),
) -> dict:
    """`GET /analytics/kpi-global` — les tuiles du dashboard (plan.md § 5.2)."""
    row = db.execute(text("SELECT * FROM analytics.mart_kpi_global")).mappings().first()
    return dict(row) if row is not None else {}
