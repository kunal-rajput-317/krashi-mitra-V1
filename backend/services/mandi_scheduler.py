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


def _register_job():
    """Register the daily mandi refresh job. data.gov updates ~once a day."""
    from backend.services.mandi_fetch_service import fetch_and_store

    scheduler.add_job(
        func               = fetch_and_store,
        trigger            = CronTrigger(hour=6, minute=30, timezone=IST),
        id                 = "mandi_price_refresh",
        name               = "Nationwide Mandi Prices — Daily 06:30 IST",
        replace_existing   = True,
        max_instances      = 1,
        misfire_grace_time = 60 * 60,   # 1h grace if app was down at 06:30
    )
    logger.info("📅 Mandi job registered | daily @ 06:30 IST | scope=nationwide")


async def start_scheduler():
    """
    Start the scheduler. Fires an immediate fetch when the snapshot table
    is empty OR stale (newest fetched_at older than STALE_AFTER_HOURS).
    The staleness catch-up matters on free-tier hosting: the instance
    sleeps/restarts, so the 06:30 IST cron (1h misfire grace) is often
    missed entirely — without this, data silently stays days old.
    Called from FastAPI startup.
    """
    _register_job()
    scheduler.start()
    logger.info("🟢 Mandi APScheduler started | timezone=Asia/Kolkata")

    STALE_AFTER_HOURS = 20  # < 24 so a daily-ish restart still refreshes

    try:
        from datetime import timedelta, timezone as _tz
        from sqlalchemy import func
        from backend.database.db import SessionLocal, MandiPrice

        db = SessionLocal()
        try:
            newest = db.query(func.max(MandiPrice.fetched_at)).scalar()
        finally:
            db.close()

        reason = None
        if newest is None:
            reason = "snapshot empty"
        else:
            if newest.tzinfo is None:  # column stores naive UTC
                newest = newest.replace(tzinfo=_tz.utc)
            age = datetime.now(_tz.utc) - newest
            if age > timedelta(hours=STALE_AFTER_HOURS):
                reason = f"snapshot stale ({age.total_seconds() / 3600:.1f}h old)"

        if reason:
            job = scheduler.get_job("mandi_price_refresh")
            if job:
                now_ist = datetime.now(IST)
                job.modify(next_run_time=now_ist)
                logger.info(f"⚡ {reason} — immediate fetch at {now_ist:%H:%M:%S IST}")
        else:
            logger.info("Mandi snapshot fresh — next fetch at daily 06:30 IST")
    except Exception as e:
        logger.error(f"Could not check/trigger first mandi fetch: {e}")


async def stop_scheduler():
    """Graceful shutdown. Called from FastAPI teardown."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("🔴 Mandi APScheduler stopped")
