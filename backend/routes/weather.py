# ============================================================
# backend/routes/weather.py
# KrashiMitra — Weather Router
# Serves weather ENTIRELY from PostgreSQL weather_cache table.
# Zero direct OWM API calls here — scheduler handles that.
# ============================================================
# CHANGED IN THIS STEP:
#   + Full DB-first serving with stale detection
#   + Standard API response format (success/message/data)
#   + /weather/districts  — list all available UP districts
#   + /weather/refresh    — admin-only manual cache refresh
#   + /weather/status     — cache health check
# ============================================================

import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Query, Header, HTTPException
from backend.database.db import SessionLocal, WeatherCache, UP_DISTRICT_CITY_MAP
from backend.services.weather_service import refresh_all_districts, get_farming_tip

logger = logging.getLogger("krishi.weather_route")

router = APIRouter()

# Data older than this is considered stale (matches scheduler interval)
STALE_THRESHOLD_HOURS = 9   # 8h schedule + 1h grace


# ── Helper ───────────────────────────────────────────────────

def _row_to_dict(row: WeatherCache) -> dict:
    """Serialize a WeatherCache ORM row to API response dict."""
    fetched_at_ist = None
    data_age_mins  = None

    if row.fetched_at:
        # Convert UTC fetched_at → IST for display
        ist_offset    = timedelta(hours=5, minutes=30)
        fetched_at_ist = (row.fetched_at + ist_offset).strftime("%d %b %Y, %I:%M %p IST")

        # Age of data in minutes
        age_delta     = datetime.utcnow() - row.fetched_at
        data_age_mins = int(age_delta.total_seconds() / 60)

    return {
        "district":          row.district,
        "city":              row.city,
        "state":             row.state,
        "temperature":       row.temperature,
        "feels_like":        row.feels_like,
        "humidity":          row.humidity,
        "wind_speed":        row.wind_speed,
        "rainfall":          row.rainfall,
        "weather_condition": row.weather_condition,
        "icon_url":          row.icon_url,
        "farming_tip":       row.farming_tip,
        "fetched_at":        fetched_at_ist,
        "data_age_minutes":  data_age_mins,
        "is_stale":          row.is_stale,
    }


# ── GET /weather ─────────────────────────────────────────────

@router.get("/weather")
async def get_weather(district: str = Query(default="Lucknow")):
    """
    Return cached weather for a UP district.
    Reads ONLY from weather_cache table — no OWM call.

    Query param:
      district — UP district name (default: Lucknow)

    Response includes:
      - All weather fields
      - farming_tip in Hindi
      - data_age_minutes — freshness indicator
      - is_stale flag — True if last scheduler run failed for this district
    """
    db = SessionLocal()
    try:
        # ── Fuzzy district match ─────────────────────────────
        # Exact match first
        row = db.query(WeatherCache).filter(
            WeatherCache.district == district
        ).first()

        # Case-insensitive fallback
        if not row:
            row = db.query(WeatherCache).filter(
                WeatherCache.district.ilike(district)
            ).first()

        # ── District not in DB yet ───────────────────────────
        if not row:
            # Check if district is valid (known but not cached yet)
            is_known = any(
                d.lower() == district.lower()
                for d in UP_DISTRICT_CITY_MAP.keys()
            )
            if is_known:
                return {
                    "success": False,
                    "message": (
                        f"'{district}' का मौसम डेटा अभी लोड हो रहा है — "
                        "कृपया 1-2 मिनट बाद पुनः प्रयास करें।"
                    ),
                    "data": {}
                }
            else:
                return {
                    "success": False,
                    "message": (
                        f"'{district}' उत्तर प्रदेश का मान्य जिला नहीं है। "
                        "कृपया /weather/districts से जिलों की सूची देखें।"
                    ),
                    "data": {}
                }

        # ── Build response ───────────────────────────────────
        data = _row_to_dict(row)

        # Stale warning — data older than threshold
        is_time_stale = (
            row.fetched_at is not None and
            (datetime.utcnow() - row.fetched_at).total_seconds() > STALE_THRESHOLD_HOURS * 3600
        )

        if row.is_stale or is_time_stale:
            message = (
                f"⚠️ मौसम डेटा {data['data_age_minutes']} मिनट पुराना है — "
                "नवीनतम जानकारी अगले अपडेट में मिलेगी।"
            )
        else:
            message = ""

        return {
            "success": True,
            "message": message,
            "data":    data,
        }

    except Exception as e:
        logger.error(f"❌ get_weather error for {district}: {e}")
        return {
            "success": False,
            "message": "मौसम डेटा प्राप्त करने में त्रुटि हुई। कृपया पुनः प्रयास करें।",
            "data":    {}
        }
    finally:
        db.close()


# ── GET /weather/districts ───────────────────────────────────

@router.get("/weather/districts")
async def get_districts():
    """
    Return all 75 supported UP districts with their cache status.
    Useful for frontend district dropdowns and cache health display.
    """
    db = SessionLocal()
    try:
        rows = db.query(
            WeatherCache.district,
            WeatherCache.fetched_at,
            WeatherCache.is_stale,
            WeatherCache.temperature,
            WeatherCache.weather_condition,
        ).all()

        cached_map = {r.district: r for r in rows}

        districts_out = []
        for district in sorted(UP_DISTRICT_CITY_MAP.keys()):
            r = cached_map.get(district)
            districts_out.append({
                "district":          district,
                "cached":            r is not None,
                "is_stale":          r.is_stale if r else None,
                "temperature":       r.temperature if r else None,
                "weather_condition": r.weather_condition if r else None,
                "fetched_at":        (
                    (r.fetched_at + timedelta(hours=5, minutes=30))
                    .strftime("%d %b %Y, %I:%M %p IST")
                    if r and r.fetched_at else None
                ),
            })

        total_cached = sum(1 for d in districts_out if d["cached"])

        return {
            "success": True,
            "message": "",
            "data": {
                "total_districts": len(UP_DISTRICT_CITY_MAP),
                "total_cached":    total_cached,
                "districts":       districts_out,
            }
        }

    except Exception as e:
        logger.error(f"❌ get_districts error: {e}")
        return {
            "success": False,
            "message": "जिलों की सूची प्राप्त करने में त्रुटि।",
            "data":    {}
        }
    finally:
        db.close()


# ── GET /weather/status ──────────────────────────────────────

@router.get("/weather/status")
async def get_cache_status():
    """
    Cache health dashboard — total cached, stale count,
    oldest and newest entry, next scheduler run estimate.
    """
    db = SessionLocal()
    try:
        rows = db.query(WeatherCache).all()

        if not rows:
            return {
                "success": True,
                "message": "Cache is empty — scheduler has not run yet.",
                "data":    {"total_cached": 0}
            }

        total       = len(rows)
        stale_count = sum(1 for r in rows if r.is_stale)
        fetched_ats = [r.fetched_at for r in rows if r.fetched_at]

        oldest = min(fetched_ats) if fetched_ats else None
        newest = max(fetched_ats) if fetched_ats else None
        ist    = timedelta(hours=5, minutes=30)

        avg_age_mins = None
        if fetched_ats:
            now = datetime.utcnow()
            avg_age_mins = int(
                sum((now - f).total_seconds() for f in fetched_ats)
                / len(fetched_ats) / 60
            )

        return {
            "success": True,
            "message": "",
            "data": {
                "total_districts":    len(UP_DISTRICT_CITY_MAP),
                "total_cached":       total,
                "stale_count":        stale_count,
                "healthy_count":      total - stale_count,
                "avg_data_age_mins":  avg_age_mins,
                "oldest_entry_ist":   (oldest + ist).strftime("%d %b %Y, %I:%M %p IST") if oldest else None,
                "newest_entry_ist":   (newest + ist).strftime("%d %b %Y, %I:%M %p IST") if newest else None,
                "scheduler_interval": "every 8 hours",
                "api_budget":         "225 calls/day (75 districts × 3 runs)",
            }
        }

    except Exception as e:
        logger.error(f"❌ cache status error: {e}")
        return {
            "success": False,
            "message": "Cache status check failed.",
            "data":    {}
        }
    finally:
        db.close()


# ── POST /weather/refresh ─────────────────────────────────────

@router.post("/weather/refresh")
async def manual_refresh(x_admin_key: str = Header(default=None)):
    """
    Admin-only manual trigger for full cache refresh.
    Protected by X-Admin-Key header.
    Use sparingly — consumes 75 OWM API calls per trigger.

    Header:
      X-Admin-Key: <value of ADMIN_SECRET_KEY in .env>
    """
    import os
    admin_key = os.getenv("ADMIN_SECRET_KEY", "")

    if not admin_key or x_admin_key != admin_key:
        raise HTTPException(status_code=403, detail="Unauthorized")

    logger.info("🔧 Manual weather refresh triggered by admin")

    # Run in background so route returns immediately
    import asyncio
    asyncio.create_task(refresh_all_districts())

    return {
        "success": True,
        "message": "मौसम कैश रिफ्रेश शुरू हो गया — 75 जिले अपडेट हो रहे हैं।",
        "data":    {"districts_queued": len(UP_DISTRICT_CITY_MAP)}
    }