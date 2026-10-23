"""An AI coding tool never connects to the live database — utils/ai_db_guard.py.

What is pinned:
  * under an AI tool, a remote database URL is refused and a local one
    (SQLite, localhost) is allowed, so the test suite still runs;
  * outside an AI tool (Render, the owner's own terminal) nothing changes;
  * the refusal never prints the URL, which carries the password;
  * every place in the repo that opens a database connection calls the guard
    first — a new connector without it fails here.
"""
import re
from pathlib import Path

import pytest

from backend.utils import ai_db_guard
from backend.utils.ai_db_guard import LiveDatabaseBlocked, refuse_live_db_for_ai

LIVE = "postgresql://km_user:s3cret-pass@ep-example-123.ap-southeast-1.aws.neon.tech/neondb"


@pytest.fixture()
def as_ai(monkeypatch):
    for k in ai_db_guard.AI_MARKERS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("CLAUDECODE", "1")


@pytest.fixture()
def as_human(monkeypatch):
    for k in ai_db_guard.AI_MARKERS:
        monkeypatch.delenv(k, raising=False)


def test_ai_is_refused_the_live_database(as_ai):
    with pytest.raises(LiveDatabaseBlocked) as e:
        refuse_live_db_for_ai(LIVE)
    assert "s3cret-pass" not in str(e.value) and "neon.tech" not in str(e.value)


@pytest.mark.parametrize("url", ["sqlite:///tmp/test.db",
                                 "postgresql://u:p@localhost:5432/km",
                                 "postgresql://u:p@127.0.0.1/km"])
def test_ai_may_use_a_local_database(as_ai, url):
    refuse_live_db_for_ai(url)


def test_any_ai_marker_counts(monkeypatch, as_human):
    monkeypatch.setenv("KM_AI_AGENT", "1")
    with pytest.raises(LiveDatabaseBlocked):
        refuse_live_db_for_ai(LIVE)


def test_people_and_render_are_not_affected(as_human):
    refuse_live_db_for_ai(LIVE)


_CONNECT = re.compile(r"\b(create_engine|psycopg2\.connect)\(")
_SKIP = {"tests", "scratch", ".venv", "venv", "node_modules", "__pycache__"}


def test_every_database_connector_calls_the_guard(repo_root):
    """db.py covers everything that imports it (app, migrations, preflight,
    neon_schema). Anything that connects on its own must call the guard too."""
    missing = []
    for path in Path(repo_root).rglob("*.py"):
        if _SKIP & set(path.relative_to(repo_root).parts):
            continue
        src = path.read_text(encoding="utf-8", errors="ignore")
        if _CONNECT.search(src) and "refuse_live_db_for_ai(" not in src:
            missing.append(str(path.relative_to(repo_root)))
    assert not missing, f"connects without the AI guard: {missing}"
