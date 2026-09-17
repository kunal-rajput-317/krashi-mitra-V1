# ============================================================
# backend/services/gsc_scheduler.py
# KrashiMitra — daily Google Search Console staleness sweep.
# Own singleton (mirrors mandi_scheduler / weather_scheduler) — small,
# infrequent, and independent of the mandi fetch cadence.
# ============================================================

import logging

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger("krishi.gsc_scheduler")

IST = pytz.timezone("Asia/Kolkata")
scheduler = AsyncIOScheduler(timezone=IST)


def _mediakit():
    """services/mediakit.py, or None while /sponsor is held back (gitignored).
    Its absence must be a no-op, never a boot failure — this job's main purpose
    is the recrawl sweep and the page-stats snapshot."""
    try:
        from backend.services import mediakit
        return mediakit
    except ImportError:
        return None


def _run():
    from backend.services import page_stats
    from backend.services.gsc_service import configured, run_stale_check
    if not configured():
        logger.info("GSC credentials not configured — skipping stale check")
        return
    run_stale_check()
    # Same credentials, same daily window, one more call: the per-page
    # impression snapshot the /dukanlisting crop picker quotes. Deliberately
    # after the recrawl sweep and in its own try — a Search Analytics failure
    # must not cost us the recrawl requests, which are the job's main purpose.
    try:
        page_stats.refresh()
    except Exception as e:
        logger.warning("page stats refresh raised, continuing: %s", e)
    # And the whole-site figures /sponsor quotes to a brand. Last and in its
    # own try for the same reason, plus one of its own: this is the only job
    # on the box that keeps the media kit honest, and services/mediakit.py
    # withholds every number once the snapshot passes MAX_AGE_DAYS. So a run
    # that dies here must not be able to take the recrawl sweep with it — the
    # failure mode is a /sponsor page with no numbers, never a stale claim.
    mk = _mediakit()
    if mk:
        try:
            mk.refresh()
        except Exception as e:
            logger.warning("media kit refresh raised, continuing: %s", e)


def _register_job():
    scheduler.add_job(
        func               = _run,
        # 05:30 IST — after the 23:11 mandi sweep has long settled and idx["dates"]
        # reflects yesterday's final prices, before the day's own 08:00 fetch.
        trigger            = CronTrigger(hour=5, minute=30, timezone=IST),
        id                 = "gsc_stale_check",
        name               = "GSC staleness sweep + page-stats snapshot — daily 05:30 IST",
        replace_existing   = True,
        max_instances      = 1,
        coalesce           = True,
        misfire_grace_time = 3600,
    )
    logger.info("📅 GSC job registered | daily @ 05:30 IST")


def _seed_mediakit():
    """One media-kit pull at boot, ONLY when there is no snapshot on disk.

    Render's filesystem does not survive a redeploy, so cache/mediakit.json is
    gone every time the service ships. Without this, /sponsor would spend the
    hours between a deploy and the next 05:30 sweep telling a brand that its
    numbers are "available on request" — the one page where looking unfinished
    costs actual money.

    Guarded on absence rather than run unconditionally: a restart loop must not
    turn into a Search Analytics quota problem, and a snapshot written this
    morning is still the right one this afternoon.
    """
    mk = _mediakit()
    if not mk or mk.CACHE_FILE.exists():
        return
    try:
        mk.refresh()
    except Exception as e:
        logger.warning("media kit seed failed, /sponsor will ask for a refresh: %s", e)


async def start_scheduler():
    from backend.services.gsc_service import configured
    _register_job()
    scheduler.start()
    logger.info("🟢 GSC APScheduler started | timezone=Asia/Kolkata")
    if not configured():
        logger.info("ℹ️ GOOGLE_SEARCH_CONSOLE_CREDENTIALS_B64 not set — GSC sweep will no-op until it is")
        return
    # Off the event loop: four Search Analytics calls take seconds and must not
    # hold up the port Render is waiting on.
    scheduler.add_job(func=_seed_mediakit, id="mediakit_seed",
                      name="Media-kit snapshot seed (once, if missing)",
                      replace_existing=True, max_instances=1)


async def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("🔴 GSC APScheduler stopped")
