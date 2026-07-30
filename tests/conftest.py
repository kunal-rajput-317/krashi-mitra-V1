"""Shared test fixtures.

Environment is configured **before** any `backend.*` import, because
backend/database/db.py reads DATABASE_URL and builds the engine at module
import time — by the time a fixture runs it is already too late.

Tests run against a throwaway SQLite file rather than Postgres. The models
use no Postgres-specific column types, so the schema builds identically; the
raw-SQL repair routines in `init_db()` are Postgres-only and are skipped (see
`app` fixture).
"""

import os
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# ── Environment must be set before backend imports ───────────
_tmp_db = Path(tempfile.mkdtemp(prefix="krashimitra-test-")) / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db}"
os.environ.setdefault("JWT_SECRET", "test-secret-not-the-repo-default")
os.environ.setdefault("ADMIN_USER", "testadmin")
os.environ.setdefault("ADMIN_PASS", "test-admin-pass")
# Keep the torch/chromadb stack out of the test run entirely.
os.environ.setdefault("CACHE_SEMANTIC_ENABLED", "false")
os.environ.setdefault("RAG_ENABLED", "false")
os.environ.setdefault("AI_RESPONSE_ENABLED", "false")
# Never let a test be mistaken for a production boot.
os.environ.pop("RENDER", None)


@pytest.fixture(scope="session")
def db_engine():
    from backend.database.db import Base, engine
    from backend.routes import cart  # noqa: F401 — registers CartItem

    Base.metadata.create_all(bind=engine)
    yield engine


@pytest.fixture(scope="session")
def app(db_engine):
    """The FastAPI app with boot side-effects disabled.

    The startup handler kicks off two APScheduler jobs, an embedding-model
    warm-up, and `init_db()` (which runs Postgres-only DDL repairs). None of
    that belongs in a unit test, and the schedulers would keep the event loop
    alive after the run. TestClient only fires startup when used as a context
    manager, so simply not doing that is enough — the tables come from the
    db_engine fixture instead.
    """
    from backend.main import app as fastapi_app

    return fastapi_app


@pytest.fixture()
def client(app):
    from fastapi.testclient import TestClient

    # Deliberately NOT `with TestClient(app)` — see the `app` fixture.
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture()
def db_session(db_engine):
    """A session that rolls back whatever the test wrote."""
    from backend.database.db import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
