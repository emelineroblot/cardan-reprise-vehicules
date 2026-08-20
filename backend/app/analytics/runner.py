"""Runner analytics — remplace dbt en ~100 lignes (plan.md § 3.7-3).

`build()` : drop en ordre inverse, create en ordre déclaré, depuis les fichiers `.sql` versionnés
listés dans `manifest.yml`.
`refresh()` : `REFRESH MATERIALIZED VIEW CONCURRENTLY` sur chaque mart, sur une connexion
**autocommit** dédiée — cette commande ne peut pas s'exécuter dans une transaction (piège
documenté § 3.7-6), et exige l'index unique déclaré dans le manifeste.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import yaml
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import engine

MODELS_DIR = Path(__file__).parent / "models"
MANIFEST_PATH = Path(__file__).parent / "manifest.yml"


@dataclass(frozen=True)
class ModelSpec:
    name: str
    file: str
    unique_index_columns: list[str] | None = None


def load_manifest() -> tuple[list[ModelSpec], list[ModelSpec]]:
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    staging = [ModelSpec(name=m["name"], file=m["file"]) for m in raw.get("staging", [])]
    marts = [
        ModelSpec(
            name=m["name"], file=m["file"], unique_index_columns=m.get("unique_index_columns")
        )
        for m in raw.get("marts", [])
    ]
    for mart in marts:
        if not mart.unique_index_columns:
            raise ValueError(
                f"Mart '{mart.name}' sans index unique déclaré — refus par le manifeste "
                "(REFRESH CONCURRENTLY l'exige)."
            )
    return staging, marts


def build() -> None:
    """Reconstruit `analytics.stg_*` et `analytics.mart_*` à l'identique.

    Idempotent : peut être rejoué autant de fois que nécessaire (le reset nocturne l'appelle
    après chaque `TRUNCATE`).
    """
    staging, marts = load_manifest()
    all_models = staging + marts

    with engine.begin() as conn:
        # Drop en ordre inverse (les marts dépendent des vues staging).
        for model in reversed(all_models):
            kind = "MATERIALIZED VIEW" if model in marts else "VIEW"
            conn.execute(text(f"DROP {kind} IF EXISTS analytics.{model.name} CASCADE"))

        # Create en ordre déclaré.
        for model in all_models:
            sql = (MODELS_DIR / model.file).read_text(encoding="utf-8")
            conn.execute(text(sql))


def refresh() -> list[dict]:
    """`REFRESH MATERIALIZED VIEW CONCURRENTLY` sur chaque mart — connexion autocommit dédiée.

    Écrit une ligne `analytics.refresh_log` par mart, y compris en cas d'échec.
    """
    _, marts = load_manifest()
    results = []

    # Connexion autocommit distincte : REFRESH CONCURRENTLY ne peut pas tourner dans une
    # transaction (plan.md § 3.7-6, § 9).
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        for mart in marts:
            started = time.monotonic()
            status = "succes"
            error: str | None = None
            try:
                conn.execute(text(f"REFRESH MATERIALIZED VIEW CONCURRENTLY analytics.{mart.name}"))
            except Exception as exc:  # noqa: BLE001 — on trace l'échec, on ne le masque pas
                status = "echec"
                error = str(exc)
            duration_ms = int((time.monotonic() - started) * 1000)

            conn.execute(
                text(
                    "INSERT INTO analytics.refresh_log "
                    "(id, mart_name, duration_ms, status, error) "
                    "VALUES (:id, :mart_name, :duration_ms, :status, :error)"
                ),
                {
                    "id": uuid4(),
                    "mart_name": mart.name,
                    "duration_ms": duration_ms,
                    "status": status,
                    "error": error,
                },
            )
            results.append({"mart_name": mart.name, "status": status, "duration_ms": duration_ms})

    return results


def latest_refresh_status(db: Session) -> list[dict]:
    """Le dernier `refreshed_at` par mart — affiché dans l'UI (« à jour il y a 4 min »)."""
    rows = db.execute(
        text(
            "SELECT DISTINCT ON (mart_name) mart_name, refreshed_at, status, duration_ms "
            "FROM analytics.refresh_log ORDER BY mart_name, refreshed_at DESC"
        )
    ).mappings()
    return [dict(row) for row in rows]
