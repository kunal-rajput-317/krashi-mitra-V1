#!/usr/bin/env python3
"""
Neon migration, step 1: DUMP.  See tools/neon/README.md.

Streams every table we carry between Neon accounts into gzipped CSV using
psycopg2's COPY. Deliberately does NOT use pg_dump — there is no pg_dump on
this machine (C:\\Program Files\\PostgreSQL\\18 has a data dir but no bin),
and pg_restore --disable-triggers would fail anyway because Neon roles are
not superuser.

Read-only against the source. Safe to re-run; overwrites its own output.

    python tools/neon/neon_dump.py             # source = .env DATABASE_URL
    python tools/neon/neon_dump.py '<conn>'    # or an explicit source
"""
from __future__ import annotations

import gzip
import io
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg2

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "dump"

# ── Scope ────────────────────────────────────────────────────────────────
# Ordered parents-first; the load side replays this order so foreign keys
# resolve. backend/database/db.py declares ~16 FKs with ondelete CASCADE /
# SET NULL, so order is NOT free (an older note claiming otherwise was wrong).
CARRY = [
    "users",                 # parent of nearly everything below
    "user_profiles",
    "chat_history",
    "crop_calendar",
    "push_subscriptions",    # parent of a mandi_alerts FK
    "mandi_alerts",
    "bazar_posts",           # parent of likes/comments
    "bazar_likes",
    "bazar_comments",
    "bazar_follows",
    "orders",
    "carts",
    "crop_appeals",
    "admin_tasks",
    # dukan / revenue — none of this regenerates
    "buyers",
    "dealer_products",
    "dealer_placements",
    "lead_clicks",
    # Seasonality rollups. MUST be carried: accumulated slowly off the
    # data.gov archive by a lazy queue, NOT a scheduled feed. They are ~98%
    # of the payload, and dropping them guts /bhav's "पिछले N साल का रुझान"
    # panel for weeks. An older note filed these under "skip" — that was wrong.
    "mandi_price_monthly",
    "mandi_season_slices",
    # large one-off import, not a scheduled feed
    "kcc_qa",
    "kcc_crop_builds",
]

# Left behind on purpose: schedulers refill these within a day, and they are
# the bulk of the storage. Skipping them is how the new account starts small
# instead of inheriting a near-full 0.5GB branch.
SKIP = [
    "weather_cache", "weather_history",
    "mandi_prices", "mandi_last_seen", "mandi_price_history",
    "sync_log",
]


def normalise(url: str) -> str:
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    # Always use the DIRECT endpoint. The -pooler host is PgBouncer in
    # transaction mode and will not hold a COPY stream open reliably.
    if "-pooler." in url:
        url = url.replace("-pooler.", ".")
        print("  note: rewrote -pooler host -> direct host for COPY")
    if "sslmode" not in url:
        url += ("&" if "?" in url else "?") + "sslmode=require"
    return url


def source_url(argv: list[str]) -> str:
    if len(argv) > 1:
        return normalise(argv[1])
    env = REPO / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("DATABASE_URL="):
                return normalise(line.split("=", 1)[1].strip().strip('"').strip("'"))
    if os.getenv("DATABASE_URL"):
        return normalise(os.environ["DATABASE_URL"])
    sys.exit("No source connection string (.env DATABASE_URL, env, or argv[1]).")


def main() -> int:
    url = source_url(sys.argv)
    OUT.mkdir(parents=True, exist_ok=True)

    safe = url.split("@")[-1].split("?")[0]
    print(f"source: ...@{safe}")
    print(f"output: {OUT}\n")

    conn = psycopg2.connect(url, connect_timeout=30)
    conn.set_session(readonly=True, autocommit=True)
    cur = conn.cursor()

    cur.execute("SELECT current_database(), "
                "pg_size_pretty(pg_database_size(current_database()))")
    dbname, dbsize = cur.fetchone()
    print(f"database {dbname} ({dbsize})\n")

    cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")
    present = {r[0] for r in cur.fetchall()}

    manifest: dict[str, object] = {
        "dumped_at": datetime.now(timezone.utc).isoformat(),
        "source_host": safe,
        "database": dbname,
        "database_size": dbsize,
        "order": [],
        "tables": {},
        "skipped_by_design": SKIP,
        "missing": [],
    }

    total = 0
    for table in CARRY:
        if table not in present:
            print(f"  !  {table:<22} not in source — skipped")
            manifest["missing"].append(table)
            continue

        cur.execute(f'SELECT count(*) FROM "{table}"')
        rows = cur.fetchone()[0]

        # Record column order: create_all() on the new DB may emit a different
        # physical order, and a positional COPY would then shear the data.
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position",
            (table,),
        )
        cols = [r[0] for r in cur.fetchall()]
        collist = ", ".join(f'"{c}"' for c in cols)

        buf = io.BytesIO()
        cur.copy_expert(
            f'COPY (SELECT {collist} FROM "{table}") TO STDOUT WITH (FORMAT csv)', buf
        )
        raw = buf.getvalue()
        path = OUT / f"{table}.csv.gz"
        with gzip.open(path, "wb") as fh:
            fh.write(raw)

        manifest["order"].append(table)
        manifest["tables"][table] = {
            "rows": rows, "columns": cols,
            "bytes_csv": len(raw), "bytes_gz": path.stat().st_size,
        }
        total += rows
        print(f"  ok {table:<22} {rows:>8,} rows  {path.stat().st_size/1024:>8.1f} KB gz")

    # Sequence positions — pg_dump --data-only would have carried setval()
    # calls; doing it explicitly means CSV can restore them too.
    cur.execute("SELECT sequence_name FROM information_schema.sequences "
                "WHERE sequence_schema = 'public'")
    seqs = {}
    for (seq,) in cur.fetchall():
        try:
            cur.execute(f'SELECT last_value, is_called FROM "{seq}"')
            last, called = cur.fetchone()
            seqs[seq] = {"last_value": int(last), "is_called": bool(called)}
        except Exception as exc:                       # noqa: BLE001
            seqs[seq] = {"error": str(exc)[:120]}
    manifest["sequences"] = seqs

    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    cur.close()
    conn.close()

    print(f"\n{total:,} rows across {len(manifest['order'])} tables")
    print(f"manifest: {OUT / 'manifest.json'}")
    if manifest["missing"]:
        print(f"missing from source: {', '.join(manifest['missing'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
