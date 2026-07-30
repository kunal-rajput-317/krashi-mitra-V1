"""Alembic environment for KrashiMitra.

Two things this does differently from the stock template:

1. DATABASE_URL comes from the environment, not alembic.ini — one source of
   truth shared with the app, and no connection string in the repo.
2. Every model module is imported before `target_metadata` is read. SQLAlchemy
   only knows about a table once its class has been imported, so a model that
   lives outside database/db.py (routes/cart.py::CartItem) would otherwise be
   invisible to autogenerate — and the first migration would cheerfully
   propose DROP TABLE carts.
"""

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Repo root on sys.path so `import backend...` works when alembic is invoked
# from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── Import every model module so Base.metadata is complete ───
from backend.database.db import Base  # noqa: E402
from backend.routes import cart  # noqa: E402,F401  (registers CartItem)

target_metadata = Base.metadata


def _database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Alembic reads the same variable the app "
            "does — export it or put it in .env before running migrations."
        )
    # Render/Heroku hand out postgres:// which SQLAlchemy 2.x rejects; db.py
    # performs the same rewrite, so mirror it here.
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting — for reviewing a migration."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = _database_url()

    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Without these, a changed column type or default is silently
            # skipped by autogenerate and the migration looks like a no-op.
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
