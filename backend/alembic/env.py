from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

# Importer tous les modèles pour qu'autogenerate voie le schéma complet.
import app.models  # noqa: F401
from alembic import context
from app.core.config import get_settings
from app.db.base import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Les migrations utilisent la chaîne DIRECTE (pas le pooler PgBouncer) — plan.md § 3.8.
settings = get_settings()
_migration_url = settings.database_url_direct or settings.database_url
config.set_main_option("sqlalchemy.url", _migration_url)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # `analytics.refresh_log` vit hors du schéma par défaut (`public`) — sans ceci,
        # autogenerate ne reflète que `public` et propose de recréer les tables d'un autre
        # schéma qui existent déjà (faux positif constaté à la revue).
        include_schemas=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
