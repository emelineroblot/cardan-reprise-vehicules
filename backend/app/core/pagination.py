"""Pagination `limit`/`offset` — plan.md § 3.5.

Enveloppe stable : `{ "items": [...], "total": 128, "limit": 25, "offset": 0 }`.
"""

from __future__ import annotations

from typing import Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

T = TypeVar("T")

DEFAULT_LIMIT = 25
MAX_LIMIT = 100


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class PageParams(BaseModel):
    limit: int = DEFAULT_LIMIT
    offset: int = 0


def page_params(
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
) -> PageParams:
    return PageParams(limit=limit, offset=offset)


def paginate(db: Session, stmt: Select, params: PageParams) -> tuple[list, int]:
    """Exécute `stmt` avec limit/offset et renvoie `(items, total)`.

    `total` est calculé via une sous-requête de comptage sur le `stmt` fourni (avant limit/offset).
    """
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = list(db.execute(stmt.limit(params.limit).offset(params.offset)).scalars().all())
    return items, total
