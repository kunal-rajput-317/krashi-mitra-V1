"""The Book must be readable when everything else is down.

The Book is served by the admin panel, which runs on Render — so the document
that explains how to recover Render is behind Render. tools/book.py is the copy
that has no such dependency: it reads backend/data/krashimitra_book.json off
the disk with nothing but the standard library.

That only holds if it keeps holding. A JSON typo, an import of something from
backend/, or a Devanagari character meeting a cp1252 Windows console would each
turn the emergency manual into a traceback on the one day it matters. These
tests are cheap insurance against exactly that.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
BOOK = REPO / "backend" / "data" / "krashimitra_book.json"
READER = REPO / "tools" / "book.py"


def run(*args):
    """Run the reader the way a person would, with a cp1252-hostile console."""
    return subprocess.run(
        [sys.executable, str(READER), *args],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8", timeout=60,
    )


def test_book_json_is_valid():
    """A typo here silently breaks both the panel and the offline reader."""
    data = json.loads(BOOK.read_text(encoding="utf-8"))
    assert data.get("sections"), "the Book has no sections"
    for s in data["sections"]:
        assert s.get("key"), "a section has no key"
        for e in s.get("entries", []):
            assert e.get("id"), f"an entry in {s['key']} has no id"
            assert e.get("title"), f"{s['key']}/{e.get('id')} has no title"


def test_reader_runs_and_prints_the_book():
    r = run()
    assert r.returncode == 0, f"reader failed:\n{r.stderr}"
    assert "commands" in r.stdout, "the contents page lists no sections"


def test_reader_opens_a_section_and_searches():
    assert "preflight" in run("commands").stdout
    hit = run("render")
    assert hit.returncode == 0 and hit.stdout.strip(), "search returned nothing"


def test_reader_needs_nothing_but_the_standard_library():
    """No backend import, no third-party dependency, or it dies in an outage."""
    src = READER.read_text(encoding="utf-8")
    for bad in ("from backend", "import backend", "import requests",
                "import fastapi", "sqlalchemy"):
        assert bad not in src, (
            f"tools/book.py references {bad!r}. The offline reader must not "
            "depend on anything that can be down or missing."
        )


def test_the_recovery_commands_are_actually_in_the_book():
    """The Book has to name the tools that fix the outages it describes."""
    text = BOOK.read_text(encoding="utf-8")
    for cmd in ("tools/preflight.py", "tools/book.py", "tools/set_backend_origin.py"):
        assert cmd in text, f"the Book never mentions {cmd}"


def test_book_hardcodes_no_backend_host():
    """The Book went stale once by naming the Render host in its own pages.

    config/backend-origin.txt is the only place that URL may live. A literal
    here means the recovery instructions point at a dead service the next time
    Render renames — which has now happened three times.
    """
    data = json.loads(BOOK.read_text(encoding="utf-8"))
    blob = json.dumps(data, ensure_ascii=False)
    import re
    hosts = set(re.findall(r"https://krashi-mitra[a-z0-9-]*\.onrender\.com", blob))
    assert not hosts, (
        f"the Book names a backend host directly: {hosts}. Point at "
        "config/backend-origin.txt or `set_backend_origin.py --check` instead."
    )
