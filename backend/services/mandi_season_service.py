# ============================================================
# backend/services/mandi_season_service.py
# KrashiMitra — Mandi Seasonality (पिछले साल इसी समय / कब बेचें)
# ------------------------------------------------------------
# The live data.gov resource only ever holds TODAY, and
# mandi_price_history is trimmed to MANDI_HISTORY_DAYS (30) because
# Neon's free tier cannot hold more. So "पिछले साल इसी महीने भाव
# क्या था?" is unanswerable from our own tables.
#
# data.gov's archive resource (see ARCHIVE_RESOURCE_ID in
# mandi_fetch_service) holds the same Agmarknet feed back to 2001.
# This service turns it into a small permanent summary:
#
#   fetch archive rows for one (state, district, commodity)
#     → median/min/max modal price per calendar month
#     → store ONLY that (≈60 rows for 5 years) and drop the raw rows
#
# Sizing: ~10k (district × crop) pairs exist nationwide, so raw
# history for all of them would be ~150M rows — impossible. The
# monthly summary for the same coverage is ~600k rows (~40 MB).
#
# Old months never change, so a slice is built once and kept.
#
# Flow (nothing ever calls data.gov from a web request):
#   /bhav page → get_summary() → miss → enqueue() → page renders without
#   the block → drain_queue() runs after the daily price fetch → next
#   view has it.
#
# Manual run:  python -m backend.services.mandi_season_service --drain 5
#              python -m backend.services.mandi_season_service \
#                  --build "Uttar Pradesh" Kanpur Wheat
# ============================================================

import os
import time
import hashlib
import logging
import statistics
from datetime import datetime, date

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.database.db import (
    SessionLocal, MandiPriceMonthly, MandiSeasonSlice,
)
from backend.services.mandi_fetch_service import (
    _get_page, _norm, _parse_dt, API_KEY,
    ARCHIVE_ENDPOINT, ARCHIVE_STATE_FIELD, PAGE_LIMIT, STATE_DELAY,
)

logger = logging.getLogger("krishi.mandi_season")

# How many years of history a summary covers. 5 gives a stable seasonal
# median without making the fetch long: the archive is sorted newest-first,
# so we stop as soon as we cross the cutoff.
SEASON_YEARS = int(os.getenv("MANDI_SEASON_YEARS", "5"))

# Pages of 5000 rows per slice. A district+crop is ~600 rows/year, so 3
# pages covers 5 years for even the busiest pair; the cutoff usually stops
# us sooner. This is the hard ceiling on one slice's cost to data.gov.
SEASON_MAX_PAGES = int(os.getenv("MANDI_SEASON_MAX_PAGES", "3"))

# A month needs at least this many daily rows before its median is
# published — one stray report is not a monthly price.
MIN_ROWS_PER_MONTH = int(os.getenv("MANDI_SEASON_MIN_MONTH_ROWS", "3"))

# Slices built per drain. Each costs up to SEASON_MAX_PAGES calls (~3s), and
# the drain rides along after the price fetch, so keep the batch modest.
DRAIN_BATCH = int(os.getenv("MANDI_SEASON_DRAIN_BATCH", "8"))

MAX_ATTEMPTS = 3          # give up on a slice that keeps failing

ARCHIVE_DISTRICT_FIELD  = "filters[District]"
ARCHIVE_COMMODITY_FIELD = "filters[Commodity]"

HI_MONTHS = ["", "जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून",
             "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"]


def slice_key(state: str, district: str, commodity: str) -> str:
    raw = "|".join([_norm(state).lower(), _norm(district).lower(),
                    _norm(commodity).lower()])
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


# ── Build one slice ──────────────────────────────────────────

def _fetch_slice_rows(state: str, district: str, commodity: str) -> list:
    """
    Archive rows for one (state, district, commodity), newest first, stopping
    at the SEASON_YEARS cutoff or SEASON_MAX_PAGES — whichever comes first.
    Returns [(date, modal_price_float)].
    """
    cutoff = date.today().replace(year=date.today().year - SEASON_YEARS)
    out, offset = [], 0

    for _page in range(SEASON_MAX_PAGES):
        params = {
            "api-key": API_KEY,
            "format":  "json",
            "limit":   PAGE_LIMIT,
            "offset":  offset,
            ARCHIVE_STATE_FIELD:     state,
            ARCHIVE_DISTRICT_FIELD:  district,
            ARCHIVE_COMMODITY_FIELD: commodity,
            "sort[Arrival_Date]":    "desc",
        }
        recs = _get_page(params, f"[season {commodity}/{district}] offset={offset}",
                         endpoint=ARCHIVE_ENDPOINT)
        if not recs:
            break

        crossed = False
        for r in recs:
            d = _parse_dt(_norm(r.get("Arrival_Date")))
            if not d:
                continue
            if d < cutoff:
                crossed = True          # sorted desc → everything after is older
                continue
            try:
                modal = float(_norm(r.get("Modal_Price")))
            except (TypeError, ValueError):
                continue
            if modal > 0:
                out.append((d, modal))

        if crossed or len(recs) < PAGE_LIMIT:
            break
        offset += PAGE_LIMIT
        time.sleep(STATE_DELAY)

    return out


def _aggregate(pairs: list) -> list:
    """[(date, modal)] → one summary dict per calendar month."""
    buckets: dict[str, list] = {}
    for d, modal in pairs:
        buckets.setdefault(f"{d.year:04d}-{d.month:02d}", []).append(modal)

    months = []
    for ym, vals in sorted(buckets.items()):
        if len(vals) < MIN_ROWS_PER_MONTH:
            continue
        y, m = ym.split("-")
        months.append({
            "ym":           ym,
            "year":         int(y),
            "month":        int(m),
            "median_modal": round(statistics.median(vals)),
            "min_modal":    round(min(vals)),
            "max_modal":    round(max(vals)),
            "n_rows":       len(vals),
        })
    return months


def build_slice(state: str, district: str, commodity: str) -> dict:
    """
    Fetch → aggregate → store one slice. Safe to re-run: months upsert by
    row_key. Returns a small summary dict.
    """
    key = slice_key(state, district, commodity)
    started = time.time()

    pairs  = _fetch_slice_rows(state, district, commodity)
    months = _aggregate(pairs)

    db = SessionLocal()
    try:
        if months:
            now = datetime.utcnow()
            rows = [{
                "state": state, "district": district, "commodity": commodity,
                "slice_key": key, "row_key": f"{key}|{m['ym']}",
                "built_at": now, **m,
            } for m in months]
            stmt = pg_insert(MandiPriceMonthly.__table__).values(rows)
            # A month can gain rows after we first saw it (the current month
            # especially), so refresh the aggregate rather than skipping it.
            stmt = stmt.on_conflict_do_update(
                index_elements=["row_key"],
                set_={
                    "median_modal": stmt.excluded.median_modal,
                    "min_modal":    stmt.excluded.min_modal,
                    "max_modal":    stmt.excluded.max_modal,
                    "n_rows":       stmt.excluded.n_rows,
                    "built_at":     stmt.excluded.built_at,
                },
            )
            db.execute(stmt)

        status = "done" if months else "empty"
        db.execute(
            text("""UPDATE mandi_season_slices
                       SET status = :st, months = :mo, rows_seen = :rs,
                           built_at = :bt, attempts = attempts + 1, note = :nt
                     WHERE slice_key = :k"""),
            {"st": status, "mo": len(months), "rs": len(pairs),
             "bt": datetime.utcnow(), "k": key,
             "nt": None if months else "archive returned no usable rows"},
        )
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"season build failed for {commodity}/{district}: {e}")
        db.execute(
            text("""UPDATE mandi_season_slices
                       SET status = 'error', attempts = attempts + 1, note = :nt
                     WHERE slice_key = :k"""),
            {"nt": str(e)[:200], "k": key},
        )
        db.commit()
        db.close()
        return {"ok": False, "error": str(e)[:200]}
    finally:
        db.close()

    logger.info(f"📅 season slice {commodity}/{district}, {state}: "
                f"{len(pairs)} rows → {len(months)} months "
                f"({time.time() - started:.1f}s)")
    return {"ok": True, "rows": len(pairs), "months": len(months),
            "state": state, "district": district, "commodity": commodity}


# ── Queue ────────────────────────────────────────────────────

def enqueue(state: str, district: str, commodity: str) -> None:
    """
    Register interest in a slice. Cheap and idempotent — a repeat view just
    bumps `hits`, which is also the drain order (most-wanted pages first).
    Never raises: a queueing failure must not break the page.
    """
    if not (state and district and commodity):
        return
    key = slice_key(state, district, commodity)
    db = SessionLocal()
    try:
        stmt = pg_insert(MandiSeasonSlice.__table__).values(
            slice_key=key, state=state, district=district, commodity=commodity,
            status="queued", hits=1, requested_at=datetime.utcnow(),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["slice_key"],
            set_={"hits": MandiSeasonSlice.__table__.c.hits + 1},
        )
        db.execute(stmt)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.debug(f"season enqueue skipped for {commodity}/{district}: {e}")
    finally:
        db.close()


def drain_queue(limit: int = DRAIN_BATCH) -> dict:
    """
    Build the most-requested pending slices. Called after the daily price
    fetch so it adds no new database wake-ups of its own (Neon's free compute
    allowance is the binding constraint — see mandi_scheduler's watchdog note).
    """
    db = SessionLocal()
    try:
        pending = db.execute(
            text("""SELECT state, district, commodity
                      FROM mandi_season_slices
                     WHERE status IN ('queued', 'error')
                       AND attempts < :max
                  ORDER BY hits DESC, requested_at ASC
                     LIMIT :lim"""),
            {"max": MAX_ATTEMPTS, "lim": limit},
        ).fetchall()
    finally:
        db.close()

    if not pending:
        return {"built": 0, "pending": 0}

    built = 0
    for st, di, co in pending:
        try:
            if build_slice(st, di, co).get("ok"):
                built += 1
        except Exception as e:                    # never let one slice stop the drain
            logger.error(f"season drain error on {co}/{di}: {e}")
        time.sleep(STATE_DELAY)

    logger.info(f"📅 season drain: built {built}/{len(pending)} slice(s)")
    return {"built": built, "pending": len(pending)}


# ── Read ─────────────────────────────────────────────────────

def get_summary(state: str, district: str, commodity: str) -> dict | None:
    """
    The seasonality read for one (state, district, commodity), or None when
    the slice has not been built yet (caller should enqueue and render
    nothing). Pure DB — never touches data.gov.

    Returns:
      by_month  {1..12: median across years}   — the seasonal shape
      best/worst month (number, median)
      last_year {"ym", "median"} for the current calendar month
      years     how many distinct years the summary covers
    """
    key = slice_key(state, district, commodity)
    db = SessionLocal()
    try:
        rows = db.execute(
            text("""SELECT ym, year, month, median_modal, n_rows
                      FROM mandi_price_monthly
                     WHERE slice_key = :k
                  ORDER BY ym"""),
            {"k": key},
        ).fetchall()
    finally:
        db.close()

    if not rows:
        return None

    per_month: dict[int, list] = {}
    for _ym, _y, m, med, _n in rows:
        if m and med:
            per_month.setdefault(int(m), []).append(float(med))
    if not per_month:
        return None

    by_month = {m: round(statistics.median(v)) for m, v in per_month.items()}
    today    = date.today()

    # "पिछले साल इसी महीने" — same calendar month, previous year
    ly_ym  = f"{today.year - 1:04d}-{today.month:02d}"
    ly_med = next((int(med) for ym, _y, _m, med, _n in rows
                   if ym == ly_ym and med), None)

    # Seasonal high/low are only meaningful once most of the year is covered.
    best = worst = None
    if len(by_month) >= 6:
        best  = max(by_month.items(), key=lambda kv: kv[1])
        worst = min(by_month.items(), key=lambda kv: kv[1])

    return {
        "by_month":   by_month,
        "best":       best,
        "worst":      worst,
        "this_month": by_month.get(today.month),
        "last_year":  {"ym": ly_ym, "median": ly_med} if ly_med else None,
        "years":      len({r[1] for r in rows if r[1]}),
        "months":     len(rows),
    }


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)
    argv = sys.argv[1:]

    if "--build" in argv:
        i = argv.index("--build")
        state, district, commodity = argv[i + 1], argv[i + 2], argv[i + 3]
        print(build_slice(state, district, commodity))
        print(get_summary(state, district, commodity))
    elif "--summary" in argv:
        i = argv.index("--summary")
        print(get_summary(argv[i + 1], argv[i + 2], argv[i + 3]))
    else:
        n = 5
        if "--drain" in argv:
            j = argv.index("--drain")
            if len(argv) > j + 1 and argv[j + 1].isdigit():
                n = int(argv[j + 1])
        print(drain_queue(n))
