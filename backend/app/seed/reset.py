"""Reset nocturne — plan.md § 4 décision D. Ce que joue le cron Vercel chaque nuit.

Ordre non négociable :
1. `TRUNCATE ... RESTART IDENTITY CASCADE` sur la liste **explicite** des tables opérationnelles
   (liste en dur : on ne truncate jamais ce qu'on n'a pas nommé).
2. `seed --profile reference` puis `seed --profile demo`, dans une transaction unique — **la
   même que le TRUNCATE** (revue § 🟠 « le reset nocturne n'est pas atomique ») : le TRUNCATE
   tournait auparavant dans sa propre connexion `engine.begin()`, commitée avant même que les
   seeds ne démarrent. Un échec de seed laissait alors la base vide jusqu'à intervention
   manuelle. Tout se passe maintenant sur la session `db`, un seul `commit()` final.
3. purge du préfixe `runtime/` du bucket Supabase (hors transaction) — sans objet en J1
   (aucun upload réel n'existe encore, décision C).
4. `analytics build` + `refresh` (connexion autocommit séparée, après le commit ci-dessus).
5. écriture d'une ligne `demo_reset_run`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.analytics.runner import build as analytics_build
from app.analytics.runner import refresh as analytics_refresh
from app.db.session import SessionLocal
from app.models.demo import DemoResetRun
from app.seed.demo import SEED_VERSION, seed_demo
from app.seed.reference import seed_reference

# Liste en dur — jamais de découverte dynamique (plan.md § 4 décision D).
OPERATIONAL_TABLES = (
    "audit_log",
    "duplicate_review",
    "vehicle_state_transition",
    "notification",
    "push_subscription",
    "inspection_item",
    "inspection",
    "photo",
    "work_order_line",
    "work_order",
    "vehicle_cost",
    "mission",
    "vehicle",
    "intake_batch",
    "checklist_item_template",
    "checklist_template",
    "company_lookup_cache",
    "lookup_health",
    "company",
    "app_user",
)


def _truncate_operational_tables(db: Session) -> None:
    table_list = ", ".join(f"public.{name}" for name in OPERATIONAL_TABLES)
    db.execute(text(f"TRUNCATE {table_list} RESTART IDENTITY CASCADE"))
    db.execute(text("ALTER SEQUENCE IF EXISTS vehicle_reference_seq RESTART WITH 1"))


def run_demo_reset() -> dict:
    started_at = datetime.now(UTC)
    run_id = uuid4()
    status = "succes"
    error: str | None = None
    rows_created: dict | None = None

    db = SessionLocal()
    try:
        # TRUNCATE + les deux seeds sur la MÊME session, un seul commit final : un échec de
        # seed annule aussi le TRUNCATE (atomicité, revue § 🟠).
        _truncate_operational_tables(db)
        reference_result = seed_reference(db)
        demo_result = seed_demo(db, force=True)
        db.commit()
        rows_created = {**reference_result, **demo_result}

        # analytics build/refresh — connexions autocommit séparées (§ 3.7-6).
        analytics_build()
        analytics_refresh()
    except Exception as exc:  # noqa: BLE001 — tracé dans demo_reset_run, jamais masqué
        db.rollback()
        status = "echec"
        error = str(exc)
    finally:
        finished_at = datetime.now(UTC)
        run = DemoResetRun(
            id=run_id,
            started_at=started_at,
            finished_at=finished_at,
            status=status,
            seed_version=SEED_VERSION,
            rows_created=rows_created,
            error=error,
        )
        db.add(run)
        db.commit()
        db.close()

    if status == "echec":
        raise RuntimeError(f"Échec du reset de démo : {error}")

    return {
        "status": status,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "rows_created": rows_created,
    }
