# ============================================================
# backend/services/poultry_scheduler.py
# KrashiMitra — keeps /farm/poultry's egg rates current.
#
# Own singleton, like the mandi, weather, GSC and mill schedulers.
#
# 09:20 IST. NECC declares the day's rate in the morning and it is the number
# a poultry farmer wants before he sells, so this runs early — and off the
# hour, away from the mandi sweep (23:11) and the GSC sweep (05:30), so two
# jobs never wake the Neon compute at the same minute.
#
# ONE REQUEST A DAY. The sheet is a whole month, so a single GET refreshes
# every zone and also picks up any day NECC revised after publishing it. The
# only time this makes more than one request is the first boot on an empty
# history, when the backfill runs once (see poultry_fetch_service).
# ============================================================

import logging

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger("krishi.poultry_scheduler")

IST = pytz.timezone("Asia/Kolkata")
scheduler = AsyncIOScheduler(timezone=IST)


def _run():
    from backend.services import poultry_fetch_service as svc
    summary = svc.fetch_and_store()
    if summary.get("ok"):
        logger.info("egg rates ok | %s | %d zones", summary["month"], summary["zones"])
    else:
        # An upstream that is down must not take the boot or the job queue
        # with it — the stored rates keep serving with their real date.
        logger.warning("egg rate refresh failed (keeping stored rates): %s",
                       summary.get("error"))


def _register_job():
    scheduler.add_job(
        func               = _run,
        trigger            = CronTrigger(hour=9, minute=20, timezone=IST),
        id                 = "poultry_egg_rates",
        name               = "NECC egg rate refresh — daily 09:20 IST",
        replace_existing   = True,
        max_instances      = 1,
        coalesce           = True,
        misfire_grace_time = 6 * 3600,
    )
    logger.info("egg rate job registered | daily @ 09:20 IST")


async def start_scheduler():
    import asyncio

    from backend.services import poultry_fetch_service as svc

    _register_job()
    scheduler.start()
    logger.info("Poultry APScheduler started | timezone=Asia/Kolkata")

    # A deploy onto an empty history should not ship pages with no numbers on
    # them, and should not wait until 09:20 either. Backfill on a genuinely
    # empty table, otherwise a single catch-up fetch — both off the event loop
    # so boot is never blocked by someone else's server.
    loop = asyncio.get_running_loop()
    if svc.history_is_empty():
        logger.info("no egg rate history — backfilling %d months once",
                    svc.BACKFILL_MONTHS)
        loop.run_in_executor(None, svc.backfill)
    else:
        loop.run_in_executor(None, svc.fetch_and_store)


async def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Poultry APScheduler stopped")
