# ============================================================
# backend/services/db_health_service.py
# KrashiMitra — "can the database still accept writes?" canary
# ------------------------------------------------------------
# Neon flips a compute to read-only when the branch passes its storage cap
# (neon.max_cluster_size, 512MB on Free). Reads keep working perfectly, so
# every page, every price and the whole SEO surface look healthy while signup,
# orders, appeals, dealer rows and lead clicks all 500. The Neon dashboard
# still says "All OK" — the *service* is fine, only the quota is not.
#
# The only way to know is to try a write. So:
#
#   UPDATE sync_log SET id = id WHERE false
#
# Postgres refuses any INSERT/UPDATE/DELETE in a read-only transaction at
# executor start, before it looks at the predicate — so this raises SQLSTATE
# 25006 exactly when writes are refused, and on a healthy database it touches
# no rows, writes no WAL and leaves no trace. A dedicated canary table would
# cost storage on the very budget we are protecting; a temp table would NOT
# work, because read-only transactions still permit writes to temp tables.
#
# Runnable manually:  python -m backend.services.db_health_service
# ============================================================
import logging
import os

from sqlalchemy import text

from backend.database.db import engine, is_read_only_error

logger = logging.getLogger("krishi.db_health")

# Warn while there is still room to act, not once writes have already stopped.
WARN_PCT = int(os.getenv("DB_STORAGE_WARN_PCT", "75"))

# Where the "writes have stopped" mail goes. Falls back to the Resend sender
# identity so a half-configured env still reaches somebody.
ALERT_EMAIL = (os.getenv("DB_ALERT_EMAIL")
               or os.getenv("ALERT_EMAIL")
               or os.getenv("RESEND_FROM_EMAIL")
               or "").strip()

_last_state: bool | None = None      # so we mail on the transition, not every run


def _pretty(n: int | None) -> str:
    if not n:
        return "—"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} GB"


def check() -> dict:
    """Probe writability + storage. Never raises — this is a health check."""
    out = {
        "writable": False, "reason": "", "size_bytes": 0, "size_pretty": "—",
        "limit_bytes": 0, "limit_pretty": "—", "pct_used": 0, "warn": False,
    }
    try:
        with engine.connect() as conn:
            # Storage first: it still works when writes don't, and it is the
            # number that explains *why* writes stopped.
            try:
                size = conn.execute(
                    text("SELECT pg_database_size(current_database())")).scalar() or 0
                out["size_bytes"] = int(size)
                out["size_pretty"] = _pretty(int(size))
            except Exception:
                pass
            try:
                # e.g. '512MB' — Neon's per-branch cap. NOTE this cap measures
                # BRANCH storage (live data + retained change history), so the
                # logical size above is a floor, not the real usage. Treat the
                # percentage as optimistic.
                raw = str(conn.execute(text("SHOW neon.max_cluster_size")).scalar() or "")
                mb = int("".join(ch for ch in raw if ch.isdigit()) or 0)
                if mb:
                    out["limit_bytes"] = mb * 1024 * 1024
                    out["limit_pretty"] = f"{mb} MB"
                    if out["size_bytes"]:
                        out["pct_used"] = round(out["size_bytes"] * 100 / out["limit_bytes"])
            except Exception:
                pass

        # The actual test — on its own connection. The reads above autobegin a
        # transaction on `conn`, and a nested begin() on the same connection is
        # a SQLAlchemy error, which would look exactly like a read-only failure.
        try:
            with engine.begin() as wconn:
                wconn.execute(text("UPDATE sync_log SET id = id WHERE false"))
            out["writable"] = True
        except Exception as e:
            out["writable"] = False
            out["reason"] = ("Database is read-only — Neon storage cap reached"
                             if is_read_only_error(e) else str(e)[:200])
    except Exception as e:
        out["reason"] = f"Could not reach the database: {str(e)[:200]}"

    out["warn"] = bool(out["pct_used"] and out["pct_used"] >= WARN_PCT)
    return out


def _mail(subject: str, body: str) -> None:
    if not ALERT_EMAIL:
        logger.warning("DB alert not sent — set DB_ALERT_EMAIL (or ALERT_EMAIL)")
        return
    try:
        from backend.utils.auth_utils import _send_with_resend
        if _send_with_resend(ALERT_EMAIL, subject, body):
            logger.info(f"📧 DB alert mailed to {ALERT_EMAIL}")
        else:
            logger.warning("DB alert email failed to send")
    except Exception as e:
        logger.warning(f"DB alert email failed: {e}")


def run_check(alert: bool = True) -> dict:
    """Scheduled entry point. Mails on the healthy→read-only transition (and
    once on recovery), never on every run — an alert that fires every 3 hours
    stops being read."""
    global _last_state
    st = check()

    if st["writable"]:
        if _last_state is False:
            logger.info("✅ Database accepts writes again")
            if alert:
                _mail("KrashiMitra: database writes are working again",
                      f"Writes recovered.\n\nStorage: {st['size_pretty']} of "
                      f"{st['limit_pretty']} ({st['pct_used']}%).")
        elif st["warn"]:
            logger.warning(f"⚠️  DB storage at {st['pct_used']}% "
                           f"({st['size_pretty']} of {st['limit_pretty']})")
    else:
        logger.error(f"🛑 DATABASE IS NOT ACCEPTING WRITES — {st['reason']}")
        if alert and _last_state is not False:
            _mail("KrashiMitra: the database has stopped accepting writes",
                  "Every page still loads, but nothing can be saved — no signups, "
                  "no orders, no dealer entries, no checklist ticks.\n\n"
                  f"Reason: {st['reason']}\n"
                  f"Storage: {st['size_pretty']} of {st['limit_pretty']} "
                  f"({st['pct_used']}% of the logical size — the real branch usage "
                  "is higher because the cap also counts change history).\n\n"
                  "Fix: lower MANDI_HISTORY_DAYS, or upgrade the Neon plan.")

    _last_state = st["writable"]
    return st


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import json
    print(json.dumps(run_check(alert=False), indent=2))
