#!/usr/bin/env python3
"""
Neon migration, step 2: SCHEMA on the target.  See tools/neon/README.md.

Runs exactly the DB half of the app's startup — create_all() + init_db() —
against the new account, and nothing else.

Importing backend.main registers every model (that is why main.py imports
backend.routes.cart explicitly), but @app.on_event("startup") never fires on
import, so the weather / mandi / GSC / mill schedulers stay asleep. Booting
the real backend at the new URL instead would start all four fetching
immediately: burning the fresh CU budget on day one and writing rows into
tables that step 3 then truncates.

    python tools/neon/neon_schema.py '<target-conn>'
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def current_source_host() -> str:
    """Host of the DB the app is live on right now, read from .env."""
    env = REPO / ".env"
    if not env.exists():
        return ""
    for line in env.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("DATABASE_URL="):
            url = line.split("=", 1)[1].strip().strip('"').strip("'")
            return url.split("@")[-1].split("?")[0].split("/")[0].replace("-pooler.", ".")
    return ""


def main() -> int:
    if len(sys.argv) < 2:
        sys.exit("usage: neon_schema.py '<target-conn-str>'")

    url = sys.argv[1]
    if url == "psql":
        sys.exit("Drop the leading 'psql' — Neon's copy button includes the "
                 "program name, but this script wants only the URL.")
    if url.startswith("<") or url.endswith(">"):
        sys.exit("Drop the angle brackets — they were placeholder markers.")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if "-pooler." in url:
        url = url.replace("-pooler.", ".")
        print("note: rewrote -pooler host -> direct host")

    target_host = url.split("@")[-1].split("?")[0].split("/")[0]

    # Guard: step 3 TRUNCATEs whatever this points at. Pointing it back at the
    # live source is the one mistake in this sequence that destroys data.
    src = current_source_host()
    if src and src.split(".")[0] == target_host.split(".")[0]:
        sys.exit(f"REFUSING: {target_host} is the endpoint .env is live on. "
                 "Pass the NEW account's string.")

    # Region check. Render is region: singapore (render.yaml). A DB in another
    # region puts ~200ms+ of round trip on every query, and pool_pre_ping=True
    # means even checking out a pooled connection pays it.
    if "ap-southeast-1" not in target_host:
        print(f"\n⚠️  {target_host} is not in ap-southeast-1 (Singapore).")
        print("   Render runs in Singapore; a cross-region DB adds ~200ms+ per")
        print("   query. Neon cannot move a project after creation — recreate")
        print("   it in AWS ap-southeast-1 rather than continuing.")
        if input("   Continue anyway? [y/N] ").strip().lower() != "y":
            return 2

    # Must be set before backend.database.db is imported — it reads
    # DATABASE_URL at module scope and builds the engine immediately.
    os.environ["DATABASE_URL"] = url
    sys.path.insert(0, str(REPO))
    os.chdir(REPO)

    import backend.main  # noqa: F401  — registers every model, starts nothing
    from backend.database.db import Base, engine, init_db

    print(f"target: ...@{str(engine.url).split('@')[-1].split('?')[0]}")

    Base.metadata.create_all(bind=engine)
    print("create_all() done")
    init_db()
    print("init_db() done — triggers and column migrations in place")

    with engine.connect() as conn:
        n = conn.exec_driver_sql(
            "SELECT count(*) FROM pg_tables WHERE schemaname='public'").scalar()
        t = conn.exec_driver_sql(
            "SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal").scalar()
    print(f"\n{n} tables, {t} user triggers created. Now run neon_load.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
