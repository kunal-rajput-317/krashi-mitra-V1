# ============================================================
# backend/services/ganna_mill_scheduler.py
# KrashiMitra — keeps the /ganna district pages' mill register current.
#
# Own singleton, like gsc_scheduler and weather_scheduler. Weekly rather than
# daily: a state's sugar-mill register changes when a factory is registered or
# wound up, which is a handful of rows a year. Fetching it every morning would
# be 365 requests to a state government's server to catch maybe three edits.
#
# The refresh is a no-op while the cache is under 30 days old, so a restarting
# dyno does not re-fetch — and if the cache is missing entirely (fresh deploy,
# wiped disk) the first tick fills it. Nothing here blocks a request: the
# district pages read the cache file, and no cache means they 302 to the state
# page until this job lands one.
# ============================================================

import logging

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger("krishi.ganna_mill_scheduler")

IST = pytz.timezone("Asia/Kolkata")
scheduler = AsyncIOScheduler(timezone=IST)


def _run():
    from backend.services import ganna_mill_service as svc
    try:
        payload = svc.refresh()
        logger.info("🏭 mill register ok | %d mills | fetched %s",
                    len(payload.get("mills", [])), payload.get("fetched", "?"))
    except Exception as e:
        # A source that moved or a state site that is down must not take the
        # boot down with it — the previous cache keeps serving.
        logger.warning("⚠️ mill register refresh failed (keeping cache): %s", e)


def _register_job():
    scheduler.add_job(
        func               = _run,
        # 04:10 IST Sunday — off the mandi sweep (23:11) and the GSC sweep
        # (05:30), and on the quietest night of the week for a govt server.
        trigger            = CronTrigger(day_of_week="sun", hour=4, minute=10,
                                         timezone=IST),
        id                 = "ganna_mill_register",
        name               = "Sugar-mill register refresh — weekly Sun 04:10 IST",
        replace_existing   = True,
        max_instances      = 1,
        coalesce           = True,
        misfire_grace_time = 6 * 3600,
    )
    logger.info("📅 mill register job registered | Sundays @ 04:10 IST")


async def start_scheduler():
    from backend.services import ganna_mill_service as svc

    _register_job()
    scheduler.start()
    logger.info("🟢 Mill register APScheduler started | timezone=Asia/Kolkata")
    # A deploy onto an empty disk should not wait until Sunday for the district
    # pages to exist. Only fires when there is genuinely nothing cached.
    if not svc.load():
        import asyncio
        logger.info("ℹ️ no mill register cached — fetching once now")
        asyncio.get_running_loop().run_in_executor(None, _run)


async def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("🔴 Mill register APScheduler stopped")
