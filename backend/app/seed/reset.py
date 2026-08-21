"""Reset nocturne — plan.md § 4 décision D. Ce que joue le cron Vercel chaque nuit.

Ordre non négociable :
1. `TRUNCATE ... RESTART IDENTITY CASCADE` sur la liste **explicite** des tables opérationnelles
   (liste en dur : on ne truncate jamais ce qu'on n'a pas nommé).
2. `seed --profile reference` puis `seed --profile demo`, dans une transaction unique — **la
   même que le TRUNCATE** (revue § 🟠 « le reset nocturne n'est pas atomique ») : le TRUNCATE
   tournait auparavant dans sa propre connexion `engine.begin()`, commitée avant même que les
   seeds ne démarrent. Un échec de seed laissait alors la base vide jusqu'à intervention
   manuelle. Tout se passe maintenant sur la session `db`, un seul `commit()` final.
3. purge du préfixe `runtime/` du backend de stockage photos (hors transaction) — sans objet en
   J1 (aucun upload réel n'existait encore, décision C) ; câblée en J2 sur l'abstraction
   `PhotoStorage` (`app/services/storage/`), best-effort : un échec de purge ne fait jamais
   échouer le reset (le statut `demo_reset_run` reste `succes`, seul un avertissement est loggué).
4. purge du préfixe `seed/` (photos de démo du run précédent), même position et même garantie
   best-effort que 3. — **après** le commit du TRUNCATE+seed, jamais avant (correctif revue
   finale J3 § 🟠 n°6, `app/seed/demo.py::purge_stale_seed_photos`) : purger avant cassait
   l'atomicité gagnée en 2., un échec de seed après la purge laissait la base revenir à son état
   de la veille alors que les fichiers avaient déjà disparu du disque.
5. `analytics build` + `refresh` (connexion autocommit séparée, après le commit ci-dessus).
6. écriture d'une ligne `demo_reset_run`.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.analytics.runner import build as analytics_build
from app.analytics.runner import refresh as analytics_refresh
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.demo import DemoResetRun
from app.seed.demo import (
    SEED_VERSION,
    purge_stale_seed_photos,
    seed_demo,
    snapshot_stale_seed_photo_prefixes,
)
from app.seed.reference import seed_reference
from app.services.storage.service import get_storage_backend

logger = logging.getLogger(__name__)

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
        settings = get_settings()
        storage = get_storage_backend()
        # Capturée AVANT le TRUNCATE+seed ci-dessous, donc avant que les nouvelles clés du run
        # courant n'apparaissent sous `seed/` : la liste des sous-répertoires du run *précédent*,
        # seule purgée après coup par `purge_stale_seed_photos` — jamais un `delete_prefix`
        # global, qui emporterait aussi les photos que ce run est sur le point d'écrire (correctif
        # revue finale J3 § 🟠 n°6, voir la docstring de `snapshot_stale_seed_photo_prefixes`).
        # Best-effort : une erreur ici ne doit jamais empêcher le reset lui-même, seulement
        # renoncer à la purge de cette passe (les fichiers de la veille resteraient orphelins
        # jusqu'au run suivant, qui les verra à nouveau dans son propre snapshot).
        try:
            stale_seed_prefixes = snapshot_stale_seed_photo_prefixes(
                storage, bucket=settings.supabase_bucket
            )
        except Exception:  # noqa: BLE001 — best-effort, ne fait jamais échouer le reset
            logger.warning("Photographie du préfixe seed/ échouée (non bloquant).", exc_info=True)
            stale_seed_prefixes = []

        # TRUNCATE + les deux seeds sur la MÊME session, un seul commit final : un échec de
        # seed annule aussi le TRUNCATE (atomicité, revue § 🟠).
        _truncate_operational_tables(db)
        reference_result = seed_reference(db)
        demo_result = seed_demo(db, force=True, storage=storage)
        db.commit()
        rows_created = {**reference_result, **demo_result}

        # analytics build/refresh — connexions autocommit séparées (§ 3.7-6).
        analytics_build()
        analytics_refresh()

        try:
            storage.delete_prefix(bucket=settings.supabase_bucket, prefix="runtime/")
        except Exception:  # noqa: BLE001 — purge best-effort, ne fait jamais échouer le reset
            logger.warning("Purge du préfixe runtime/ échouée (non bloquant).", exc_info=True)

        try:
            # Purge sélective des SEULS sous-répertoires `seed/` photographiés avant le run
            # (jamais les clés que ce run vient d'écrire) — après le commit ci-dessus, jamais
            # avant (correctif revue finale J3 § 🟠 n°6) : purger avant cassait l'atomicité
            # gagnée par le commit unique ci-dessus, un échec de seed laissant alors la base
            # revenir à son état de la veille alors que les fichiers avaient déjà disparu du
            # disque. Best-effort comme la purge `runtime/`.
            purge_stale_seed_photos(
                storage, bucket=settings.supabase_bucket, stale_prefixes=stale_seed_prefixes
            )
        except Exception:  # noqa: BLE001 — purge best-effort, ne fait jamais échouer le reset
            logger.warning("Purge du préfixe seed/ échouée (non bloquant).", exc_info=True)
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
