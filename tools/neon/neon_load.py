#!/usr/bin/env python3
"""
Neon migration, step 3: LOAD.  See tools/neon/README.md.

Replays tools/neon/dump/ into the target over COPY. Destructive (TRUNCATEs
each carried table first), so it refuses to run without --yes. All-or-nothing:
any error rolls the whole thing back and the target is left untouched.

Run neon_schema.py first — this preflights the schema and bails with
instructions if it is missing.

    python tools/neon/neon_load.py '<target-conn>' --dry-run
    python tools/neon/neon_load.py '<target-conn>' --yes
"""
from __future__ import annotations

import csv
import gzip
import io
import json
import sys
from pathlib import Path

import psycopg2

OUT = Path(__file__).resolve().parent / "dump"


def normalise(url: str) -> str:
    if url == "psql":
        sys.exit("Drop the leading 'psql' — pass only the URL.")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if "-pooler." in url:
        url = url.replace("-pooler.", ".")
        print("  note: rewrote -pooler host -> direct host for COPY")
    if "sslmode" not in url:
        url += ("&" if "?" in url else "?") + "sslmode=require"
    return url


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    if not args:
        sys.exit("usage: neon_load.py '<target-conn-str>' [--dry-run|--yes]")
    if "--yes" not in flags and "--dry-run" not in flags:
        sys.exit("refusing to run: pass --dry-run to inspect, or --yes to load.")

    dry = "--dry-run" in flags
    url = normalise(args[0])

    mpath = OUT / "manifest.json"
    if not mpath.exists():
        sys.exit(f"No dump found at {OUT}. Run neon_dump.py first.")
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    order: list[str] = manifest["order"]
    tables: dict = manifest["tables"]

    print(f"target: ...@{url.split('@')[-1].split('?')[0]}")
    print(f"dump:   {manifest['dumped_at']} from {manifest['source_host']}")
    print(f"{len(order)} tables, {sum(t['rows'] for t in tables.values()):,} rows\n")

    conn = psycopg2.connect(url, connect_timeout=30)
    conn.autocommit = False
    cur = conn.cursor()

    # ── Preflight ────────────────────────────────────────────────────────
    cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")
    present = {r[0] for r in cur.fetchall()}
    absent = [t for t in order if t not in present]
    if absent:
        print("TARGET SCHEMA INCOMPLETE — missing:")
        for t in absent:
            print(f"    {t}")
        print("\nFix: python tools/neon/neon_schema.py '<target-conn>'")
        return 2

    plan = []
    for t in order:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position",
            (t,),
        )
        target_cols = [r[0] for r in cur.fetchall()]
        src_cols = tables[t]["columns"]
        usable = [c for c in src_cols if c in target_cols]
        dropped = [c for c in src_cols if c not in target_cols]
        added = [c for c in target_cols if c not in src_cols]
        plan.append((t, usable))
        note = ""
        if dropped:
            note += f"  DROPPED(not in target): {','.join(dropped)}"
        if added:
            note += f"  DEFAULTED(new in target): {','.join(added)}"
        print(f"  {t:<22} {tables[t]['rows']:>8,} rows{note}")

    cur.execute("SELECT count(*) FROM users")
    print(f"\ntarget currently holds {cur.fetchone()[0]} users")

    if dry:
        conn.rollback()
        print("\n--dry-run: nothing written.")
        return 0

    # ── Load ─────────────────────────────────────────────────────────────
    # session_replication_role=replica suppresses FK checks AND the user
    # triggers (trg_ensure_user_profile et al) that would otherwise fabricate
    # profile rows mid-load and then collide, or reject unverified users.
    # neon_superuser can normally set it; fall back to per-table DISABLE
    # TRIGGER USER, which any table owner may do.
    replica_mode = True
    try:
        cur.execute("SET session_replication_role = replica")
        print("\ntriggers+FKs suppressed via session_replication_role=replica")
    except psycopg2.Error as exc:
        conn.rollback()
        replica_mode = False
        print(f"\nsession_replication_role unavailable ({exc.pgcode}); "
              "falling back to per-table DISABLE TRIGGER USER")
        for t in order:
            cur.execute(f'ALTER TABLE "{t}" DISABLE TRIGGER USER')

    try:
        for t in reversed(order):
            cur.execute(f'TRUNCATE TABLE "{t}" CASCADE')
        print(f"truncated {len(order)} tables")

        loaded = 0
        for t, usable in plan:
            data = gzip.decompress((OUT / f"{t}.csv.gz").read_bytes())
            if not data:
                print(f"  -- {t:<22}        0 rows")
                continue
            src_cols = tables[t]["columns"]
            if usable != src_cols:
                keep = [src_cols.index(c) for c in usable]
                buf = io.StringIO()
                w = csv.writer(buf, lineterminator="\n")
                for row in csv.reader(io.StringIO(data.decode("utf-8"))):
                    w.writerow([row[i] for i in keep])
                payload = io.BytesIO(buf.getvalue().encode("utf-8"))
            else:
                payload = io.BytesIO(data)

            collist = ", ".join(f'"{c}"' for c in usable)
            cur.copy_expert(f'COPY "{t}" ({collist}) FROM STDIN WITH (FORMAT csv)',
                            payload)
            print(f"  ok {t:<22} {tables[t]['rows']:>8,} rows")
            loaded += tables[t]["rows"]

        # Sequences last, so nothing inserted above bumps them afterwards.
        fixed = 0
        for seq, info in manifest.get("sequences", {}).items():
            if "last_value" not in info:
                continue
            cur.execute("SELECT 1 FROM information_schema.sequences "
                        "WHERE sequence_schema='public' AND sequence_name=%s", (seq,))
            if cur.fetchone():
                cur.execute("SELECT setval(%s, %s, %s)",
                            (seq, info["last_value"], info["is_called"]))
                fixed += 1

        if not replica_mode:
            for t in order:
                cur.execute(f'ALTER TABLE "{t}" ENABLE TRIGGER USER')

        conn.commit()
        print(f"\ncommitted: {loaded:,} rows, {fixed} sequences reset")

    except Exception:
        conn.rollback()
        print("\nROLLED BACK — target unchanged.")
        raise

    # ── Verify ───────────────────────────────────────────────────────────
    conn.autocommit = True
    bad = []
    for t in order:
        cur.execute(f'SELECT count(*) FROM "{t}"')
        got = cur.fetchone()[0]
        want = tables[t]["rows"]
        if got != want:
            bad.append((t, want, got))
    if bad:
        print("\nROW COUNT MISMATCH:")
        for t, want, got in bad:
            print(f"    {t}: expected {want:,}, found {got:,}")
        return 1
    print("verified: every table matches the dump manifest")

    cur.close()
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
