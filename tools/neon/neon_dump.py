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
    python tools/neon/neon_dump.py '<conn>' --only=mandi_prices,shop_products
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
# EVERY public table is carried, except the few in SKIP. It used to be the
# other way round — a hand-kept CARRY list — and that list went stale: the
# 27 Sep 2026 move silently left shop_products, seller_verifications (paid
# नीला टिक members), news likes/comments and bazar_comment_likes behind,
# because those tables were added after the list was written. A new table is
# now carried unless someone decides otherwise.
#
# Load order is worked out from the source's own foreign keys (parents first),
# so it can't go stale either.
#
# SKIP holds only data that is safe to lose AND refills itself. The mandi
# snapshot and history are NOT skipped any more: they refill only when
# data.gov.in is up, and on 27 Sep it was down all night, so /bhav showed no
# prices at all after the move.
SKIP = [
    "weather_cache", "weather_history",   # weather job refills within the hour
    "sync_log",                           # a log of the OLD database's runs
]


def load_order(cur, tables: set[str]) -> list[str]:
    """`tables` sorted so every FK parent comes before its children."""
    cur.execute("""
        SELECT c.conrelid::regclass::text, c.confrelid::regclass::text
        FROM pg_constraint c
        WHERE c.contype = 'f' AND c.connamespace = 'public'::regnamespace
    """)
    parents: dict[str, set[str]] = {t: set() for t in tables}
    for child, parent in cur.fetchall():
        child, parent = child.strip('"'), parent.strip('"')
        if child in tables and parent in tables and child != parent:
            parents[child].add(parent)
    order: list[str] = []
    done: set[str] = set()
    while len(order) < len(tables):
        ready = sorted(t for t in tables if t not in done and parents[t] <= done)
        if not ready:          # an FK cycle — append the rest; replica mode copes
            ready = sorted(t for t in tables if t not in done)
        for t in ready:
            order.append(t)
            done.add(t)
    return order


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
    if argv:
        return normalise(argv[0])
    env = REPO / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("DATABASE_URL="):
                return normalise(line.split("=", 1)[1].strip().strip('"').strip("'"))
    if os.getenv("DATABASE_URL"):
        return normalise(os.environ["DATABASE_URL"])
    sys.exit("No source connection string (.env DATABASE_URL, env, or argv[1]).")


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    only = {t.strip() for a in sys.argv[1:] if a.startswith("--only=")
            for t in a.split("=", 1)[1].split(",") if t.strip()}
    url = source_url(args)
    OUT.mkdir(parents=True, exist_ok=True)

    safe = url.split("@")[-1].split("?")[0]
    print(f"source: ...@{safe}")
    print(f"output: {OUT}\n")

    conn = psycopg2.connect(url, connect_timeout=90)
    conn.set_session(readonly=True, autocommit=True)
    cur = conn.cursor()

    cur.execute("SELECT current_database(), "
                "pg_size_pretty(pg_database_size(current_database()))")
    dbname, dbsize = cur.fetchone()
    print(f"database {dbname} ({dbsize})\n")

    cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")
    present = {r[0] for r in cur.fetchall()}
    wanted = (only or present) - set(SKIP)
    carry = load_order(cur, wanted & present)

    manifest: dict[str, object] = {
        "dumped_at": datetime.now(timezone.utc).isoformat(),
        "source_host": safe,
        "database": dbname,
        "database_size": dbsize,
        "order": [],
        "tables": {},
        "skipped_by_design": SKIP,
        "only": sorted(only),
        "missing": sorted(wanted - present),
    }

    total = 0
    for table in carry:
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
