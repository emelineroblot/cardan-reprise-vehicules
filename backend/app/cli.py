"""CLI opérationnel — `python -m app.cli ...` (plan.md § 7).

Commandes : `seed --profile reference|demo`, `demo-reset`, `analytics build|refresh`.
"""

from __future__ import annotations

import typer

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.seed.reference import seed_reference

app = typer.Typer(help="CLI opérationnel Cardan.")


@app.command()
def seed(
    profile: str = typer.Option(..., "--profile", help="reference | demo"),
    force: bool = typer.Option(False, "--force", help="Ignore le garde-fou anti-production."),
) -> None:
    """Charge un profil de données : `reference` (idempotent) ou `demo` (~90 véhicules)."""
    db = SessionLocal()
    try:
        if profile == "reference":
            result = seed_reference(db)
            db.commit()
            typer.echo(f"Référentiel chargé : {result}")
        elif profile == "demo":
            from app.seed.demo import (
                purge_stale_seed_photos,
                seed_demo,
                snapshot_stale_seed_photo_prefixes,
            )
            from app.services.storage.service import get_storage_backend

            storage = get_storage_backend()
            bucket = get_settings().supabase_bucket
            # Capturée AVANT seed_demo, purgée APRÈS le commit ci-dessous — même raison et même
            # mécanisme qu'`app/seed/reset.py::run_demo_reset` (voir la docstring de
            # `snapshot_stale_seed_photo_prefixes`/`purge_stale_seed_photos` : un `delete_prefix`
            # global emporterait aussi les photos que ce run vient d'écrire).
            stale_seed_prefixes = snapshot_stale_seed_photo_prefixes(storage, bucket=bucket)
            result = seed_demo(db, force=force, storage=storage)
            db.commit()
            purge_stale_seed_photos(storage, bucket=bucket, stale_prefixes=stale_seed_prefixes)
            typer.echo(f"Jeu de démo chargé : {result}")
        else:
            typer.echo(f"Profil inconnu : {profile}", err=True)
            raise typer.Exit(code=1)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@app.command(name="demo-reset")
def demo_reset() -> None:
    """Rejoue localement ce que déclenche le cron nocturne (plan.md § 4 décision D)."""
    from app.seed.reset import run_demo_reset

    result = run_demo_reset()
    typer.echo(f"Reset terminé : {result}")


analytics_app = typer.Typer(help="Construction et rafraîchissement du schéma analytics.")
app.add_typer(analytics_app, name="analytics")


@analytics_app.command()
def build() -> None:
    """(Re)crée `analytics.stg_*` et `analytics.mart_*` depuis les fichiers `.sql` versionnés."""
    from app.analytics.runner import build as run_build

    run_build()
    typer.echo("Schéma analytics reconstruit.")


@analytics_app.command()
def refresh() -> None:
    """`REFRESH MATERIALIZED VIEW CONCURRENTLY` sur chaque mart (connexion autocommit)."""
    from app.analytics.runner import refresh as run_refresh

    run_refresh()
    typer.echo("Marts rafraîchis.")


if __name__ == "__main__":
    app()
