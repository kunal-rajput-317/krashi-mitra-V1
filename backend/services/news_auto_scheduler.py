# ============================================================
# backend/services/news_auto_scheduler.py
# KrashiMitra — AI News Auto-Pilot Scheduler
#
# Daily AI Ingestion (Days 1-3) + Day 5 Auto-Push Watchdog
# Timezone: Asia/Kolkata (IST)
# ============================================================

import asyncio
import logging
from datetime import datetime
import pytz

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR

from backend.services.news_auto_service import (
    run_discovery_and_stage,
    check_and_run_day5_fallback,
)

logger = logging.getLogger("krishi.news_scheduler")

IST = pytz.timezone("Asia/Kolkata")

scheduler = AsyncIOScheduler(timezone=IST)


def _on_job_executed(event):
    logger.info(f"✅ News Auto-Pilot job executed | id={event.job_id}")


def _on_job_error(event):
    logger.error(f"❌ News Auto-Pilot job failed | id={event.job_id} | error={event.exception}")


scheduler.add_listener(_on_job_executed, EVENT_JOB_EXECUTED)
scheduler.add_listener(_on_job_error, EVENT_JOB_ERROR)


async def _scheduled_daily_discovery():
    """Daily 5:00 PM IST sweep: Ingests agri news and stages 2-3 drafts during Days 1 to 3."""
    logger.info("🌆 Running daily 5:00 PM IST AI news discovery sweep (Days 1-3)...")
    try:
        new_items = await run_discovery_and_stage(target_count=3, check_cycle=True)
        logger.info(f"📰 Auto-staged {len(new_items)} articles for current cycle.")
    except Exception as e:
        logger.error(f"Error in 5:00 PM news discovery: {e}")


def _scheduled_day5_watchdog():
    """Runs every 3 hours to check if any staged batch has reached Day 5."""
    try:
        auto_pushed = check_and_run_day5_fallback()
        if auto_pushed:
            logger.info(f"⚡ Watchdog auto-published {len(auto_pushed)} posts reaching Day 5.")
    except Exception as e:
        logger.error(f"Error in Day 5 watchdog: {e}")


async def start_scheduler():
    """Starts the news auto-pilot scheduler and performs startup checks."""
    if scheduler.running:
        logger.info("ℹ️ News Auto-Pilot scheduler is already running.")
        return

    # 1. Daily discovery at 5:00 PM IST (Days 1-3, 2-3 posts per day)
    scheduler.add_job(
        _scheduled_daily_discovery,
        trigger=CronTrigger(hour=17, minute=0, timezone=IST),
        id="news_daily_5pm_discovery",
        name="Daily 17:00 IST AI News Discovery & Staging (Days 1-3, 2-3 posts)",
        replace_existing=True,
    )

    # 2. Watchdog: check Day 5 fallback every 3 hours
    scheduler.add_job(
        _scheduled_day5_watchdog,
        trigger=IntervalTrigger(hours=3),
        id="news_day5_watchdog",
        name="Day 5 Auto-Push Fallback Watchdog",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("🚀 News Auto-Pilot scheduler started (Daily 17:00 IST discovery [2-3 posts] + 3h Day 5 watchdog)")

    # Immediate non-blocking check for any aged posts on boot
    try:
        _scheduled_day5_watchdog()
    except Exception as e:
        logger.warning(f"Initial news watchdog check error (non-fatal): {e}")
