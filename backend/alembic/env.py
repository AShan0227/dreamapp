"""Alembic environment for DreamApp.

Uses async SQLAlchemy via run_sync. The DATABASE URL comes from the
application's `settings.database_url` so we never duplicate it in two places.
Note: the URL must be a sync driver here — we strip the +asyncpg suffix so
Alembic can use the synchronous psycopg2 / sqlite connection for migrations.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make `models.*` and `config` importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings  # noqa: E402
from models.dream import Base  # noqa: E402
import models.user  # noqa: F401, E402  — register tables on Base.metadata
import models.entities  # noqa: F401, E402
import models.agent  # noqa: F401, E402
import models.knowledge_embedding  # noqa: F401, E402
import models.social  # noqa: F401, E402
import models.engagement  # noqa: F401, E402
import models.threads  # noqa: F401, E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _sync_url(url: str) -> str:
    """Convert async driver URLs to sync equivalents for Alembic."""
    return (
        url
        .replace("+asyncpg", "")
        .replace("+aiosqlite", "")
    )


target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = _sync_url(settings.database_url)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = _sync_url(settings.database_url)
    cfg = config.get_section(config.config_ini_section) or {}
    cfg["sqlalchemy.url"] = url
    connectable = engine_from_config(
        cfg, prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
