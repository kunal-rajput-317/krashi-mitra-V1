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


async def start_scheduler():
    from backend.services.gsc_service import configured
    _register_job()
    scheduler.start()
    logger.info("🟢 GSC APScheduler started | timezone=Asia/Kolkata")
    if not configured():
        logger.info("ℹ️ GOOGLE_SEARCH_CONSOLE_CREDENTIALS_B64 not set — GSC sweep will no-op until it is")


async def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("🔴 GSC APScheduler stopped")
