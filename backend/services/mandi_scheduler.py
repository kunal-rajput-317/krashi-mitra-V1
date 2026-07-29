# ============================================================
# backend/services/mandi_scheduler.py
# KrashiMitra — Mandi Price Scheduler
# APScheduler — daily fetch from data.gov.in into PostgreSQL.
# Mirrors the weather_scheduler pattern (separate singleton).
# ============================================================

import logging
import pytz
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron      import CronTrigger
from apscheduler.triggers.interval  import IntervalTrigger
from apscheduler.triggers.combining import OrTrigger
from apscheduler.events             import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR

logger = logging.getLogger("krishi.mandi_scheduler")

IST = pytz.timezone("Asia/Kolkata")

# Module-level singleton — one mandi scheduler for the whole app
scheduler = AsyncIOScheduler(timezone=IST)


def _on_job_executed(event):
    logger.info(f"✅ Mandi job done | id={event.job_id}")

def _on_job_error(event):
    logger.error(f"❌ Mandi job FAILED | id={event.job_id} | error={event.exception}")

scheduler.add_listener(_on_job_executed, EVENT_JOB_EXECUTED)
scheduler.add_listener(_on_job_error,    EVENT_JOB_ERROR)


STALE_AFTER_HOURS = 20  # < 24 so a daily-ish refresh window is never missed


def _snapshot_stale_reason():
    """Return why the snapshot needs a refresh ('empty' / 'stale Xh'), or None if fresh."""
    from datetime import timedelta, timezone as _tz
    from sqlalchemy import func
    from backend.database.db import SessionLocal, MandiPrice

    db = SessionLocal()
    try:
        newest = db.query(func.max(MandiPrice.fetched_at)).scalar()
    finally:
        db.close()

    if newest is None:
        return "snapshot empty"
    if newest.tzinfo is None:  # column stores naive UTC
        newest = newest.replace(tzinfo=_tz.utc)
    age = datetime.now(_tz.utc) - newest
    if age > timedelta(hours=STALE_AFTER_HOURS):
        return f"snapshot stale ({age.total_seconds() / 3600:.1f}h old)"
    return None


def _refresh_if_stale():
    """
    Trigger an immediate fetch when the snapshot is empty or stale.
    Routes through the registered job (job.modify) instead of calling
    fetch_and_store directly so max_instances=1 still prevents overlap
    with the daily cron run.
    """
    try:
        reason = _snapshot_stale_reason()
        if not reason:
            return False
        job = scheduler.get_job("mandi_price_refresh")
        if job:
            now_ist = datetime.now(IST)
            job.modify(next_run_time=now_ist)
            logger.info(f"⚡ {reason} — immediate fetch at {now_ist:%H:%M:%S IST}")
        return True
    except Exception as e:
        logger.error(f"Mandi staleness check failed: {e}")
        return False


def _fetch_and_notify():
    """fetch_and_store + IndexNow ping. When a fetch actually stored rows,
    every /bhav page's content changed — tell Bing/Yandex/etc. so the 1300+
    price pages recrawl within hours instead of weeks (Google doesn't do
    IndexNow; it gets the same freshness via /bhav/sitemap.xml lastmod).
    The ping is best-effort and must never fail the fetch itself."""
    from backend.services.mandi_fetch_service import fetch_and_store

    summary = fetch_and_store()
    try:
        if summary.get("fetched"):
            from backend.utils.indexnow import ping_bhav
            ping_bhav()
    except Exception as e:
        logger.error(f"IndexNow ping failed (non-fatal): {e}")

    # Keep the /bhav "nearest mandi" centroids complete as new districts appear
    # in the feed. Best-effort and bounded; must never fail the fetch itself.
    try:
        from backend.services.district_geo import backfill_missing
        backfill_missing()
    except Exception as e:
        logger.error(f"district centroid backfill failed (non-fatal): {e}")

    # 🔔 Push today's bhav to farmers who turned the bell on for a crop+mandi.
    # Prices have just been merged, so this is the moment the alert is true.
    # Best-effort and bounded; a push outage must never fail the fetch.
    try:
        from backend.services.push_service import run_mandi_alerts
        run_mandi_alerts()
    except Exception as e:
        logger.error(f"mandi push alerts failed (non-fatal): {e}")

    # 📅 Build a few of the seasonality summaries that /bhav pages asked for.
    # Deliberately ridden along here rather than given its own timer: this
    # job already has the DB awake, and an independent schedule would add
    # exactly the round-the-clock Neon traffic the staleness watchdog was
    # widened to 3h to avoid. Best-effort and bounded (DRAIN_BATCH slices).
    try:
        from backend.services.mandi_season_service import drain_queue
        drain_queue()
    except Exception as e:
        logger.error(f"season summary drain failed (non-fatal): {e}")

    # 🌾 Harvest a couple of crops' किसान कॉल सेंटर Q&A for /sawal. Rides here
    # for the same reason as the seasonality drain: the DB is already awake.
    # The crop list is fixed and small, so this finishes within a day or two
    # and then does nothing but a single cheap status query per run.
    try:
        from backend.services.kcc_service import drain_queue as kcc_drain
        kcc_drain()
    except Exception as e:
        logger.error(f"KCC Q&A drain failed (non-fatal): {e}")

    return summary


def _archive_daily():
    """Export the previous day's mandi rows from the DB into repo2 as CSV.
    Best-effort and idempotent (self-heals missed days); must never raise —
    the archive is downstream of, and must not endanger, the price fetch."""
    try:
        from backend.services.mandi_archive_service import run_archive
        return run_archive()
    except Exception as e:
        logger.error(f"Mandi daily archive failed (non-fatal): {e}")
        return None


def _register_job():
    """
    Register the mandi refresh job. data.gov wipes the daily feed overnight
    and refills it as mandis report through the day (2 rows at 06:30 IST,
    ~half by ~09:30, ~10k by 11:30, full ~18k by evening). Six runs/day:
      08:00 IST — today's early reporters start flowing in
      10:00 IST — late-morning top-up
      13:00 IST — feed mostly full
      16:00 IST — afternoon top-up
      20:00 IST — evening sweep — most mandis have reported by now
      23:11 IST — final end-of-day sweep before the overnight wipe, so pre-dawn
                  users always see yesterday's complete final prices
    (23:11 fires at :11, so it can't share the :00 cron above — the two
    schedules are OR-combined into this one job.)
    All runs are idempotent AND safe at any feed level: the snapshot is
    MERGED per market identity (never wholesale-deleted), history dedupes by
    row_key, and the sparse guard rejects near-empty results.
    Every successful fetch also pings IndexNow (see _fetch_and_notify);
    _refresh_if_stale routes through this same job, so the watchdog path
    pings too.
    """
    scheduler.add_job(
        func               = _fetch_and_notify,
        trigger            = OrTrigger([
            CronTrigger(hour="8,10,13,16,20", minute=0,  timezone=IST),
            CronTrigger(hour=23,              minute=11, timezone=IST),
        ]),
        id                 = "mandi_price_refresh",
        name               = "Nationwide Mandi Prices — Daily 08/10/13/16/20h + 23:11 IST",
        replace_existing   = True,
        max_instances      = 1,
        coalesce           = True,
        misfire_grace_time = None,   # run whenever noticed, however late (laptop/instance slept)
    )

    # Watchdog: the 06:30 cron is routinely missed when the host is asleep at
    # that moment, and a startup-only catch-up leaves data stale for days when
    # the process stays alive. Re-check staleness periodically instead.
    #
    # Interval is 3h, not 30 min, because this check is the app's ONLY
    # round-the-clock database traffic: at 30 min it kept Neon's compute awake
    # 24/7 (~730 compute-hours/month against a ~192h free allowance), which
    # quota-blocked the database late every month and took the whole site down
    # with it. At 3h the DB idles between the six scheduled fetches instead.
    # Detection stays well inside STALE_AFTER_HOURS (20h), so a genuinely stale
    # snapshot is still caught long before a user could notice it.
    scheduler.add_job(
        func               = _refresh_if_stale,
        trigger            = IntervalTrigger(hours=3),
        id                 = "mandi_stale_watchdog",
        name               = "Mandi Snapshot Staleness Watchdog — every 3 hours",
        replace_existing   = True,
        max_instances      = 1,
        coalesce           = True,
    )
    # Daily archive: at 04:00 IST data.gov has been wiped for the new day and
    # yesterday's 20:00 sweep is the complete final record, so "yesterday" is
    # safe & complete to export to repo2. Self-healing, so misfires just catch
    # up. misfire_grace_time=None: run whenever noticed if the host was asleep.
    scheduler.add_job(
        func               = _archive_daily,
        trigger            = CronTrigger(hour=4, minute=0, timezone=IST),
        id                 = "mandi_daily_archive",
        name               = "Mandi Daily Archive → repo2 CSV — 04:00 IST",
        replace_existing   = True,
        max_instances      = 1,
        coalesce           = True,
        misfire_grace_time = None,
    )

    logger.info("📅 Mandi jobs registered | daily @ 08/10/13/16/20h + 23:11 IST + 3-hourly staleness watchdog + archive @ 04h IST")


async def start_scheduler():
    """
    Start the scheduler and run an immediate staleness catch-up. The
    watchdog job repeats that check every 3 hours so a missed cron
    (sleeping laptop, spun-down free-tier instance) can't leave the
    snapshot days old. Called from FastAPI startup.
    """
    _register_job()
    scheduler.start()
    logger.info("🟢 Mandi APScheduler started | timezone=Asia/Kolkata")

    # Probe the data.gov key on boot so a 403 shows up immediately in the logs
    # (instead of only when the daily/watchdog fetch quietly fails).
    from backend.services.mandi_fetch_service import check_api_key
    check_api_key()

    if not _refresh_if_stale():
        logger.info("Mandi snapshot fresh — next scheduled fetch at 08/10/13/16/20h IST")

    # Boot catch-up for the archive. The 04:00 cron is routinely missed on a
    # spun-down free-tier instance (a process restart forgets the misfire), so
    # a one-off run ~30s after boot exports any DB day not yet in repo2. Runs
    # off the startup path (non-blocking) and self-heals within the 30-day window.
    from datetime import timedelta as _td
    scheduler.add_job(
        func         = _archive_daily,
        trigger      = "date",
        run_date     = datetime.now(IST) + _td(seconds=30),
        id           = "mandi_archive_catchup",
        name         = "Mandi Archive — boot catch-up",
        replace_existing = True,
    )


async def stop_scheduler():
    """Graceful shutdown. Called from FastAPI teardown."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("🔴 Mandi APScheduler stopped")
