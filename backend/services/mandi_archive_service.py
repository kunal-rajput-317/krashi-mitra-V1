# ============================================================
# backend/services/mandi_archive_service.py
# KrashiMitra — Daily Mandi Archive → repo2 (CSV)
# ------------------------------------------------------------
# Neon only keeps MANDI_HISTORY_DAYS (=30) of history. Before those rows
# age out they are exported, one CSV file per day, into a separate GitHub
# data repo (repo2) so the full history survives forever and can feed
# seasonality pages + offline model training.
#
# Scheduled at 04:00 IST (see mandi_scheduler): at that hour data.gov has
# been wiped for the new day and the previous day's 20:00 sweep is the
# complete final record, so "yesterday" is safe and complete to archive.
#
# Idempotent + self-healing: each run archives every day still present in
# the DB (≤ yesterday) that isn't already in repo2 — so a missed 04:00 run
# (spun-down free-tier instance) is caught up on the next run, and re-runs
# never duplicate. Nothing is ever pushed unless repo2 + a token are
# configured (see backend/utils/github_archive).
#
# Runnable manually for the first push / testing:
#   python -m backend.services.mandi_archive_service
# ============================================================

import csv
import gzip
import io
import logging
import os
from datetime import datetime, timedelta

import pytz
from sqlalchemy import text

from backend.database.db import SessionLocal
from backend.utils import github_archive

logger = logging.getLogger("krishi.mandi_archive")

IST = pytz.timezone("Asia/Kolkata")

# Fixed column order — the canonical schema for repo2 (see docs/MANDI-TASKS.md).
# `date` is the ISO arrival date; prices are as data.gov reports them (₹/quintal).
CSV_COLUMNS = [
    "date", "state", "district", "market",
    "commodity", "variety", "grade",
    "min_price", "max_price", "modal_price",
]

ARCHIVE_DIR  = os.getenv("MANDI_ARCHIVE_DIR", "data").strip("/")
# Plain CSV by default so files render as browsable tables on GitHub; flip to
# "true" to gzip (~5× smaller) once size matters — the loader just checks the
# extension.
GZIP = os.getenv("MANDI_ARCHIVE_GZIP", "false").lower() == "true"


def _repo_path(d) -> str:
    """data/2026/07/2026-07-16.csv[.gz] — sortable, one immutable file per day."""
    ext = "csv.gz" if GZIP else "csv"
    return f"{ARCHIVE_DIR}/{d:%Y}/{d:%m}/{d:%Y-%m-%d}.{ext}"


def _rows_for_date(db, d) -> list:
    """All history rows whose arrival_dt == d, in a stable order."""
    sql = text(
        """
        SELECT arrival_dt, state, district, market,
               commodity, variety, grade,
               min_price, max_price, modal_price
          FROM mandi_price_history
         WHERE arrival_dt = :d
         ORDER BY state, district, market, commodity, variety, grade
        """
    )
    return list(db.execute(sql, {"d": d}))


def _csv_bytes(rows) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(CSV_COLUMNS)
    for r in rows:
        arrival_dt = r[0]
        w.writerow([
            arrival_dt.isoformat() if arrival_dt else "",
            *[("" if v is None else str(v)) for v in r[1:]],
        ])
    data = buf.getvalue().encode("utf-8")
    return gzip.compress(data) if GZIP else data


def _archivable_dates(db, upto) -> list:
    """Distinct arrival_dt present in the DB, up to and including `upto`."""
    sql = text(
        """
        SELECT DISTINCT arrival_dt
          FROM mandi_price_history
         WHERE arrival_dt IS NOT NULL AND arrival_dt <= :upto
         ORDER BY arrival_dt
        """
    )
    return [row[0] for row in db.execute(sql, {"upto": upto})]


def archive_date(db, d):
    """Export one day to repo2 if it isn't there yet. Returns
    (action, row_count) where action is github_archive.upsert_file's result
    ('created'/'exists'/...) or 'empty'."""
    rows = _rows_for_date(db, d)
    if not rows:
        return "empty", 0
    path = _repo_path(d)
    msg = f"archive: mandi prices {d:%Y-%m-%d} ({len(rows)} rows)"
    return github_archive.upsert_file(path, _csv_bytes(rows), msg), len(rows)


def _repo_name() -> str:
    """The bare repo name for user-facing messages (e.g. 'mandi-bhav-repo')."""
    return (os.getenv("MANDI_ARCHIVE_REPO", "").split("/")[-1] or "mandi-bhav-repo")


def run_archive() -> dict:
    """Archive every DB day (≤ yesterday IST) not already in repo2.
    Best-effort and idempotent — safe to call from the 04:00 cron, a boot
    catch-up, or by hand. Records the outcome in the admin Data Sync Log when
    something is actually pushed (or a push fails). Never raises."""
    if not github_archive.is_configured():
        logger.info("Mandi archive: repo2 not configured (MANDI_ARCHIVE_REPO/TOKEN) — skipping")
        return {"configured": False}

    started    = datetime.utcnow()
    yesterday  = datetime.now(IST).date() - timedelta(days=1)
    summary = {"configured": True, "created": [], "created_rows": 0, "existed": 0, "errors": []}

    db = SessionLocal()
    try:
        for d in _archivable_dates(db, yesterday):
            action, n = archive_date(db, d)
            if action == "created":
                summary["created"].append(d.isoformat())
                summary["created_rows"] += n
            elif action == "exists":
                summary["existed"] += 1
            elif action != "empty":
                summary["errors"].append(f"{d.isoformat()}:{action}")
    finally:
        db.close()

    logger.info(
        f"📦 Mandi archive done | new={len(summary['created'])} "
        f"existing={summary['existed']} errors={len(summary['errors'])}"
    )
    _record_outcome(summary, started)
    return summary


def _record_outcome(summary: dict, started) -> None:
    """Write one Data Sync Log row so the admin panel shows archive activity.
    Only logs when something was pushed or a push failed — a no-op catch-up
    (everything already archived) is left silent so boot restarts don't spam
    the log. Never raises."""
    created = summary["created"]
    errors  = summary["errors"]
    if not created and not errors:
        return
    try:
        from backend.services.sync_log_service import record_sync
        repo = _repo_name()
        if created and errors:
            record_sync("archive", "partial", summary["created_rows"],
                        f"Committed & pushed {len(created)} day(s) to {repo}; "
                        f"{len(errors)} failed ({errors[0]})", started_at=started)
        elif errors:
            record_sync("archive", "failed", 0,
                        f"Push to {repo} failed: {errors[0]}", started_at=started)
        else:
            days = len(created)
            span = created[0] if days == 1 else f"{created[0]} to {created[-1]}"
            record_sync("archive", "success", summary["created_rows"],
                        f"Successfully committed & pushed to {repo} — "
                        f"{days} day(s) ({span}), {summary['created_rows']} rows",
                        started_at=started)
    except Exception as e:
        logger.error(f"Archive sync-log record failed (non-fatal): {e}")


def archive_health(days: int = 35) -> dict:
    """Compare the DB's day window against what's actually in repo2 and flag
    gaps — so a silently-stopped archive becomes visible. For each distinct
    arrival_dt in the DB (≤ yesterday, most recent `days`), report whether its
    file exists in repo2. Uses directory listings (1 call per involved month),
    not one-call-per-day. Never raises.

    Returns: configured, checked_ok, db_days, archived, missing[], missing_count,
    last_archived_date, last_db_date, oldest_db_date."""
    if not github_archive.is_configured():
        return {"configured": False}

    yesterday = datetime.now(IST).date() - timedelta(days=1)
    db = SessionLocal()
    try:
        db_days = _archivable_dates(db, yesterday)
    finally:
        db.close()
    db_days = db_days[-days:]  # most recent window

    if not db_days:
        return {"configured": True, "checked_ok": True, "db_days": 0,
                "archived": 0, "missing": [], "missing_count": 0,
                "last_archived_date": None, "last_db_date": None, "oldest_db_date": None}

    # One listing per (year, month) touched by the window.
    month_names: dict = {}
    checked_ok = True
    for (y, m) in sorted({(d.year, d.month) for d in db_days}):
        names = github_archive.list_dir(f"{ARCHIVE_DIR}/{y:04d}/{m:02d}")
        if names is None:            # API error — don't cry "missing"
            checked_ok = False
            names = set()
        month_names[(y, m)] = names

    def _present(d) -> bool:
        names = month_names.get((d.year, d.month), set())
        # accept either extension so a mid-flight GZIP flip doesn't false-alarm
        return f"{d:%Y-%m-%d}.csv" in names or f"{d:%Y-%m-%d}.csv.gz" in names

    present = [d for d in db_days if _present(d)]
    missing = [d for d in db_days if not _present(d)]

    return {
        "configured":         True,
        "checked_ok":         checked_ok,   # False ⇒ couldn't reach repo2, numbers unreliable
        "db_days":            len(db_days),
        "archived":           len(present),
        "missing":            [d.isoformat() for d in missing],
        "missing_count":      len(missing),
        "last_archived_date": present[-1].isoformat() if present else None,
        "last_db_date":       db_days[-1].isoformat(),
        "oldest_db_date":     db_days[0].isoformat(),
    }


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    print(run_archive())
