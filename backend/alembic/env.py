import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

# ruff: noqa: F401
# Import models to register them with Base.metadata
# Use direct model imports to avoid circular dependency with repositories
import app.models.base
import app.models.compliance_case
import app.models.consistency_check
import app.models.document
import app.models.extracted_evidence
import app.models.generated_report
import app.models.review_decision
import app.models.risk_assessment
from alembic import context

# Import models and Base for autogenerate
# Import Base first to avoid circular imports
from app.db.database import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def _get_sync_url() -> str:
    """Get and normalize database URL for synchronous Alembic use.

    Converts async drivers (asyncpg) to synchronous (psycopg) for Alembic compatibility.
    Checks DATABASE_URL environment variable first, falls back to alembic.ini config.
    """
    db_url = os.getenv("DATABASE_URL") or config.get_main_option("sqlalchemy.url")

    if not db_url:
        raise ValueError(
            "No database URL configured. Set DATABASE_URL env var or sqlalchemy.url in alembic.ini"
        )

    # Normalize to postgresql+psycopg:// for synchronous use
    if "postgresql+asyncpg://" in db_url:
        db_url = db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
    elif db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)
    elif "postgresql://" in db_url and "+psycopg" not in db_url:
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://")

    return db_url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = _get_sync_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    db_url = _get_sync_url()

    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = db_url

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
