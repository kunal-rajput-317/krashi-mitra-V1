# ============================================================
# backend/services/sync_log_service.py
# KrashiMitra — Data Sync Log
# ------------------------------------------------------------
# Small helper around the `sync_log` table. Every mandi / weather
# fetch records one row here (source, status, rows, duration) so
# the admin panel can show *when* data was last pulled and whether
# it succeeded — a silently-stale feed becomes visible at a glance.
# ============================================================

import logging
from datetime import datetime, timedelta

from backend.database.db import SessionLocal, SyncLog

logger = logging.getLogger("krishi.sync_log")

# Keep the table flat — one line per run, few runs per day, but trim
# anything older than this so it never grows unbounded.
KEEP_ROWS_PER_SOURCE = 200

IST = timedelta(hours=5, minutes=30)


def record_sync(
    source: str,
    status: str,
    rows: int = 0,
    detail: str = "",
    started_at: datetime | None = None,
) -> None:
    """
    Insert one sync-log row. Never raises — logging failures must not break
    the fetch that just succeeded. `started_at` (UTC) drives duration_ms.
    """
    finished = datetime.utcnow()
    duration_ms = None
    if started_at is not None:
        duration_ms = max(0, int((finished - started_at).total_seconds() * 1000))

    db = SessionLocal()
    try:
        db.add(SyncLog(
            source      = source,
            status      = status,
            rows        = int(rows or 0),
            detail      = (detail or "")[:500],
            duration_ms = duration_ms,
            started_at  = started_at,
            finished_at = finished,
        ))
        db.commit()
        _trim(db, source)
    except Exception as e:
        db.rollback()
        logger.error(f"⚠️  Could not record sync log ({source}/{status}): {e}")
    finally:
        db.close()


def _trim(db, source: str) -> None:
    """Drop the oldest rows for a source beyond KEEP_ROWS_PER_SOURCE."""
    try:
        ids = [
            r.id for r in db.query(SyncLog.id)
            .filter(SyncLog.source == source)
            .order_by(SyncLog.finished_at.desc())
            .offset(KEEP_ROWS_PER_SOURCE)
            .all()
        ]
        if ids:
            db.query(SyncLog).filter(SyncLog.id.in_(ids)).delete(synchronize_session=False)
            db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"⚠️  Sync-log trim failed for {source}: {e}")


def _fmt_ist(dt: datetime | None) -> str | None:
    return (dt + IST).strftime("%d %b %Y, %I:%M %p IST") if dt else None


def _age_str(dt: datetime | None) -> str | None:
    """Human 'x min/hours ago' relative to now (UTC)."""
    if not dt:
        return None
    secs = (datetime.utcnow() - dt).total_seconds()
    if secs < 60:
        return "just now"
    mins = int(secs / 60)
    if mins < 60:
        return f"{mins} min ago"
    hours = mins / 60
    if hours < 24:
        return f"{hours:.1f} hr ago"
    return f"{hours / 24:.1f} days ago"


def _row_to_dict(r: SyncLog) -> dict:
    return {
        "id":          r.id,
        "source":      r.source,
        "status":      r.status,
        "rows":        r.rows,
        "detail":      r.detail,
        "duration_ms": r.duration_ms,
        "started_at":  _fmt_ist(r.started_at),
        "finished_at": _fmt_ist(r.finished_at),
        "age":         _age_str(r.finished_at),
    }


def get_recent(limit: int = 40, source: str | None = None) -> list[dict]:
    """Most-recent-first list of sync runs, optionally filtered by source."""
    db = SessionLocal()
    try:
        q = db.query(SyncLog)
        if source:
            q = q.filter(SyncLog.source == source)
        rows = q.order_by(SyncLog.finished_at.desc()).limit(limit).all()
        return [_row_to_dict(r) for r in rows]
    finally:
        db.close()


def get_summary() -> dict:
    """Latest run per source — powers the admin 'last synced' indicators."""
    db = SessionLocal()
    try:
        summary = {}
        for source in ("mandi", "weather"):
            last = (
                db.query(SyncLog)
                .filter(SyncLog.source == source)
                .order_by(SyncLog.finished_at.desc())
                .first()
            )
            summary[source] = _row_to_dict(last) if last else None
        return summary
    finally:
        db.close()
