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
    Start the scheduler. Fires an immediate first fetch ONLY when the
    snapshot table is empty (avoids hammering the API on every restart;
    nationwide fetch is ~10k rows). Called from FastAPI startup.
    """
    _register_job()
    scheduler.start()
    logger.info("🟢 Mandi APScheduler started | timezone=Asia/Kolkata")

    try:
        from backend.database.db import SessionLocal, MandiPrice
        db = SessionLocal()
        try:
            empty = db.query(MandiPrice).count() == 0
        finally:
            db.close()

        if empty:
            job = scheduler.get_job("mandi_price_refresh")
            if job:
                now_ist = datetime.now(IST)
                job.modify(next_run_time=now_ist)
                logger.info(f"⚡ Snapshot empty — immediate first fetch at {now_ist:%H:%M:%S IST}")
    except Exception as e:
        logger.error(f"Could not check/trigger first mandi fetch: {e}")


async def stop_scheduler():
    """Graceful shutdown. Called from FastAPI teardown."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("🔴 Mandi APScheduler stopped")
