# ============================================================
# backend/services/weather_scheduler.py
# KrashiMitra — Weather Cache Scheduler
# APScheduler — runs every 8 hours (225 OWM calls/day ✅)
# ============================================================
# FIX IN THIS VERSION:
#   + Immediate first-run uses clean datetime import (no hack)
#   + Uses asynccontextmanager-safe AsyncIOScheduler
#   + Logs clearly so you can confirm it's running in terminal
# ============================================================

import logging
import pytz
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval  import IntervalTrigger
from apscheduler.events             import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR

logger = logging.getLogger("krishi.weather_scheduler")
logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s  [%(name)s]  %(levelname)s — %(message)s",
    datefmt = "%Y-%m-%d %H:%M:%S",
)

IST = pytz.timezone("Asia/Kolkata")

# Module-level singleton — one scheduler for the whole app
scheduler = AsyncIOScheduler(timezone=IST)


# ── Event listeners ──────────────────────────────────────────

def _on_job_executed(event):
    logger.info(f"✅ Job done     | id={event.job_id}")

def _on_job_error(event):
    logger.error(f"❌ Job FAILED   | id={event.job_id} | error={event.exception}")

scheduler.add_listener(_on_job_executed, EVENT_JOB_EXECUTED)
scheduler.add_listener(_on_job_error,    EVENT_JOB_ERROR)


# ── Job registration ─────────────────────────────────────────

def _register_job():
    """Register the weather refresh job. Called once at startup."""
    from backend.services.weather_service import refresh_all_districts

    scheduler.add_job(
        func               = refresh_all_districts,
        trigger            = IntervalTrigger(hours=8, timezone=IST),
        id                 = "weather_cache_refresh",
        name               = "UP Weather Cache — 8h Refresh",
        replace_existing   = True,
        max_instances      = 1,
        misfire_grace_time = 60 * 15,
    )
    logger.info(
        "📅 Weather job registered | interval=8h | districts=75 | "
        "budget=225 calls/day | max_instances=1"
    )


# ── Public API ───────────────────────────────────────────────

async def start_scheduler():
    """
    Start the scheduler and fire an immediate first fetch
    so weather_cache is populated before the first user request.
    Called from FastAPI lifespan startup.
    """
    _register_job()
    scheduler.start()
    logger.info("🟢 APScheduler started | timezone=Asia/Kolkata")

    # Trigger immediately by setting next_run_time to NOW
    job = scheduler.get_job("weather_cache_refresh")
    if job:
        now_ist = datetime.now(IST)
        job.modify(next_run_time=now_ist)
        logger.info(f"⚡ Immediate first fetch triggered at {now_ist.strftime('%H:%M:%S IST')}")


async def stop_scheduler():
    """Graceful shutdown. Called from FastAPI lifespan teardown."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("🔴 APScheduler stopped")