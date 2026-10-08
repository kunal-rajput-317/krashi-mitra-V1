# ============================================================
# backend/services/mandi_csv_import.py
# KrashiMitra — load a data.gov.in mandi CSV by hand
# ------------------------------------------------------------
# Stopgap for when api.data.gov.in is down (25 Sep 2026 onward it refused
# :443) while www.data.gov.in still publishes the same Agmarknet dataset as a
# CSV download. Same source, same licence (GODL, attribution already on the
# pages), so this is not a new data source — just a second way in.
#
# Accepts either resource's CSV:
#   • 9ef84268… "Current Daily Price … (Mandi)"         — latest day only
#   • 35985678… "Variety-wise Daily Market Prices …"    — archive, any range
# Rows go through fetch_and_store(), so history, last-seen and the snapshot
# are written exactly as an API fetch would write them.
#
#   python -m backend.services.mandi_csv_import FILE.csv [FILE2.csv ...]          # dry run
#   python -m backend.services.mandi_csv_import FILE.csv [FILE2.csv ...] --apply  # write
#
# --apply writes to whatever DATABASE_URL points at (the live Neon DB).
# ============================================================

import csv
import re
import sys
import logging
from collections import Counter

from backend.services.mandi_fetch_service import (
    _group_key, _norm, _parse_dt, fetch_and_store,
)

logger = logging.getLogger("krishi.mandi_csv_import")

# CSV header (normalised) → live-feed field. data.gov.in exports spaces as
# "_x0020_" ("Min_x0020_Price"); the archive uses "Min_Price".
FIELDS = {
    "state": "state", "district": "district", "market": "market",
    "commodity": "commodity", "variety": "variety", "grade": "grade",
    "arrival_date": "arrival_date",
    "min_price": "min_price", "max_price": "max_price", "modal_price": "modal_price",
}
REQUIRED = {"state", "market", "commodity", "arrival_date", "modal_price"}


def _key(header: str) -> str:
    h = header.strip().lstrip("﻿").lower().replace("_x0020_", "_")
    return re.sub(r"[^a-z]+", "_", h).strip("_")


class CsvError(ValueError):
    """A file that is not a mandi price CSV — shown to the admin as-is."""


def read_rows(f, name: str) -> tuple[list, Counter]:
    """Live-feed-shaped dicts from one open CSV text stream, plus a count of
    skipped rows by reason."""
    skipped: Counter = Counter()
    out = []
    reader = csv.DictReader(f)
    cols = {h: FIELDS[_key(h)] for h in (reader.fieldnames or []) if _key(h) in FIELDS}
    missing = REQUIRED - set(cols.values())
    if missing:
        raise CsvError(f"{name}: missing column(s) {sorted(missing)}; "
                       f"header was {reader.fieldnames}")
    for raw in reader:
        r = {dst: _norm(raw.get(src)) for src, dst in cols.items()}
        if not _parse_dt(r.get("arrival_date")):
            skipped["bad date"] += 1
            continue
        try:
            if float(r["modal_price"]) <= 0:
                skipped["zero price"] += 1
                continue
        except (TypeError, ValueError):
            skipped["bad price"] += 1
            continue
        out.append(r)
    return out, skipped


def load(sources: list) -> tuple[list, Counter]:
    """All files merged, one row per (mandi × crop × date).

    Each source is a path, or a (name, text stream) pair for an upload."""
    rows, seen, skipped = [], set(), Counter()
    for src in sources:
        if isinstance(src, tuple):
            recs, sk = read_rows(src[1], src[0])
        else:
            with open(src, newline="", encoding="utf-8-sig") as f:
                recs, sk = read_rows(f, src)
        skipped += sk
        for r in recs:
            rk = _group_key(r) + "|" + _parse_dt(r["arrival_date"]).isoformat()
            if rk in seen:
                skipped["duplicate"] += 1
                continue
            seen.add(rk)
            rows.append(r)
    return rows, skipped


def summary(rows: list, skipped: Counter) -> dict:
    """What the check step shows: rows per date and per state."""
    days   = Counter(_parse_dt(r["arrival_date"]) for r in rows)
    states = Counter(r["state"] for r in rows)
    return {
        "rows":    len(rows),
        "skipped": dict(skipped),
        "dates":   [{"date": d.isoformat(), "rows": n} for d, n in sorted(days.items())],
        "states":  [{"state": s, "rows": n} for s, n in states.most_common()],
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    paths = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not paths:
        print("usage: python -m backend.services.mandi_csv_import FILE.csv [FILE2.csv ...] [--apply]")
        sys.exit(2)

    try:
        rows, skipped = load(paths)
    except CsvError as e:
        sys.exit(str(e))
    sm = summary(rows, skipped)
    print(f"rows    : {sm['rows']}   skipped: {sm['skipped'] or 0}")
    print(f"dates   : {len(sm['dates'])}")
    for x in sm["dates"]:
        print(f"   {x['date']}  {x['rows']:>6}")
    print(f"states  : {len(sm['states'])}  - " +
          ", ".join(f"{x['state']} {x['rows']}" for x in sm["states"]))

    if "--apply" not in sys.argv:
        print("\nDry run - nothing written. Re-run with --apply to load.")
        sys.exit(0)
    if not rows:
        sys.exit("No usable rows - nothing to load.")
    names = ", ".join(p.replace("\\", "/").rsplit("/", 1)[-1] for p in paths)
    print(fetch_and_store(records=rows, source=f"CSV import ({names})"))
