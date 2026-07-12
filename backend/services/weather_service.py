# ============================================================
# backend/services/weather_service.py
# KrashiMitra — Weather Service
# ============================================================
# CHANGED IN THIS STEP:
#   + refresh_all_districts()  — called by scheduler every 8h
#   + _fetch_and_upsert()      — fetches ONE district from OWM
#                                and upserts into weather_cache
#   + get_farming_tip()        — unchanged, kept here
#   + fetch_weather()          — now reads from DB only (stub;
#                                fully wired in Response 5)
# NO direct OWM calls happen during user requests.
# ============================================================

import os
import logging
import asyncio
import httpx

from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from backend.database.db import (
    SessionLocal,
    WeatherCache,
    WeatherHistory,
    UP_DISTRICT_CITY_MAP,
    UP_DISTRICT_COORDS,
)
from backend.services.sync_log_service import record_sync

logger = logging.getLogger("krishi.weather_service")


# ── Farming Tip Logic (unchanged) ───────────────────────────

def get_farming_tip(temp: float, humidity: float, wind: float, desc: str) -> str:
    """Return a farming tip based on current weather conditions."""
    desc_lower = desc.lower()
    if "rain" in desc_lower or "drizzle" in desc_lower:
        return "🌧️ बारिश की संभावना — आज कीटनाशक छिड़काव न करें।"
    elif "storm" in desc_lower or "thunder" in desc_lower:
        return "⛈️ आंधी-तूफान — खेत में काम न करें, सुरक्षित रहें।"
    elif "snow" in desc_lower:
        return "❄️ बर्फबारी — फसलों को ढकें, पाले से बचाएं।"
    elif temp > 42:
        return "🔥 अत्यधिक गर्मी — सिंचाई दोगुनी करें, दोपहर में काम न करें।"
    elif temp > 35:
        return "🌡️ बहुत गर्म — सिंचाई की आवृत्ति बढ़ाएं।"
    elif temp < 5:
        return "🥶 पाले का खतरा — फसलों को रात में ढकें।"
    elif temp < 10:
        return "🧊 ठंड अधिक — फसलों को पाले से बचाएं।"
    elif humidity > 85:
        return "💧 अधिक नमी — फफूंद रोग का खतरा, निगरानी रखें।"
    elif humidity > 75:
        return "🍄 उच्च आर्द्रता — फसल में फंगस की जांच करें।"
    elif wind > 30:
        return "💨 तेज़ हवाएं — खाद और स्प्रे छिड़काव न करें।"
    elif wind > 20:
        return "🌬️ हवा तेज़ है — उर्वरक छिड़काव से बचें।"
    else:
        return "✅ खेती के लिए अच्छा मौसम — सामान्य कार्य जारी रखें।"


# ── Single District Fetch + DB Upsert ───────────────────────

async def _fetch_and_upsert(
    district: str,
    city: str,
    api_key: str,
    client: httpx.AsyncClient,
    db: Session,
) -> bool:
    """
    Fetch weather for ONE district from OWM, by the district HQ's
    coordinates (see UP_DISTRICT_COORDS). `city` is only the human
    label stored on the row.
    Upsert result into weather_cache table.
    Returns True on success, False on failure.
    Marks row as stale on failure so old data is still served.
    """
    coords = UP_DISTRICT_COORDS.get(district)
    if not coords:
        logger.error(f"❌ No coordinates for district: {district}")
        _mark_stale(district, db)
        return False

    lat, lon = coords
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "lat":   lat,
        "lon":   lon,
        "appid": api_key,
        "units": "metric",
    }

    try:
        res  = await client.get(url, params=params, timeout=12)
        data = res.json()

        if data.get("cod") != 200:
            logger.warning(
                f"⚠️  OWM rejected {district} ({lat},{lon}) — "
                f"cod={data.get('cod')} {data.get('message', '')}"
            )
            # Mark existing row stale if present
            _mark_stale(district, db)
            return False

        # Parse OWM response
        temp      = data["main"]["temp"]
        feels     = data["main"]["feels_like"]
        humidity  = data["main"]["humidity"]
        wind      = data["wind"]["speed"]
        desc      = data["weather"][0]["description"].title()
        icon_code = data["weather"][0]["icon"]
        icon_url  = f"https://openweathermap.org/img/wn/{icon_code}@2x.png"
        # rainfall key only present when it actually rains
        rainfall  = data.get("rain", {}).get("1h", 0.0)

        tip = get_farming_tip(temp, humidity, wind, desc)
        now = datetime.utcnow()

        # ── Upsert: update if row exists, insert if not ──────
        row = db.query(WeatherCache).filter(
            WeatherCache.district == district
        ).first()

        if row:
            row.city              = city
            row.temperature       = temp
            row.feels_like        = feels
            row.humidity          = humidity
            row.wind_speed        = wind
            row.rainfall          = rainfall
            row.weather_condition = desc
            row.icon_url          = icon_url
            row.farming_tip       = tip
            row.fetched_at        = now
            row.updated_at        = now
            row.is_stale          = False
        else:
            row = WeatherCache(
                district          = district,
                city              = city,
                state             = "Uttar Pradesh",
                temperature       = temp,
                feels_like        = feels,
                humidity          = humidity,
                wind_speed        = wind,
                rainfall          = rainfall,
                weather_condition = desc,
                icon_url          = icon_url,
                farming_tip       = tip,
                fetched_at        = now,
                updated_at        = now,
                is_stale          = False,
            )
            db.add(row)

        # Record this fetch in the rolling 7-day history
        db.add(WeatherHistory(
            district          = district,
            city              = city,
            state             = "Uttar Pradesh",
            temperature       = temp,
            feels_like        = feels,
            humidity          = humidity,
            wind_speed        = wind,
            rainfall          = rainfall,
            weather_condition = desc,
            icon_url          = icon_url,
            farming_tip       = tip,
            fetched_at        = now,
        ))

        db.commit()
        logger.info(f"✅ Cached: {district:<25} {temp}°C  {desc}")
        return True

    except httpx.TimeoutException:
        logger.error(f"⏱️  Timeout fetching {district} ({city})")
        _mark_stale(district, db)
        return False

    except Exception as e:
        logger.error(f"❌ Error fetching {district}: {e}")
        _mark_stale(district, db)
        return False


def _mark_stale(district: str, db: Session):
    """Mark a district row as stale so the route can warn users."""
    try:
        row = db.query(WeatherCache).filter(
            WeatherCache.district == district
        ).first()
        if row:
            row.is_stale  = True
            row.updated_at = datetime.utcnow()
            db.commit()
    except Exception as e:
        logger.error(f"⚠️  Could not mark stale for {district}: {e}")


# ── History Purge ───────────────────────────────────────────

def purge_old_history(db: Session) -> int:
    """Delete weather_history rows older than 7 days. Returns deleted count."""
    cutoff = datetime.utcnow() - timedelta(days=7)
    deleted = (
        db.query(WeatherHistory)
        .filter(WeatherHistory.fetched_at < cutoff)
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted


# ── Scheduler Entry Point ────────────────────────────────────

async def refresh_all_districts():
    """
    Called by APScheduler every 8 hours.
    Fetches weather for ALL 75 UP districts in batches.
    Uses ONE shared httpx.AsyncClient for connection pooling.

    Batching strategy:
      - 75 districts split into batches of 10
      - 1 second sleep between batches
      - avoids hammering OWM with 75 simultaneous requests
      - total wall-clock time: ~15-20 seconds per full cycle
    """
    start_time = datetime.utcnow()

    api_key = os.getenv("OPENWEATHER_API_KEY", "")
    if not api_key:
        logger.error("❌ OPENWEATHER_API_KEY not set — skipping weather refresh")
        record_sync("weather", "failed", 0,
                    "OPENWEATHER_API_KEY not set — refresh skipped", start_time)
        return

    districts = list(UP_DISTRICT_CITY_MAP.items())   # list of (district, city)
    total     = len(districts)
    batch_size = 10

    logger.info(f"🌦️  Starting weather refresh — {total} districts in batches of {batch_size}")

    success_count = 0
    fail_count    = 0

    db = SessionLocal()
    try:
        async with httpx.AsyncClient() as client:
            for i in range(0, total, batch_size):
                batch = districts[i : i + batch_size]

                # Fire all requests in this batch concurrently
                results = await asyncio.gather(*[
                    _fetch_and_upsert(district, city, api_key, client, db)
                    for district, city in batch
                ])

                success_count += sum(results)
                fail_count    += results.count(False)

                # Polite delay between batches (not needed for correctness,
                # but good practice with free OWM plan)
                if i + batch_size < total:
                    await asyncio.sleep(1)

        deleted = purge_old_history(db)
        if deleted:
            logger.info(f"🗑️  Purged {deleted} history rows older than 7 days")

    except Exception as e:
        logger.error(f"❌ Weather refresh crashed: {e}")
        record_sync("weather", "failed", success_count,
                    f"refresh crashed after {success_count}/{total}: {e}", start_time)
        raise
    finally:
        db.close()

    elapsed = (datetime.utcnow() - start_time).seconds
    logger.info(
        f"🏁 Weather refresh complete — "
        f"✅ {success_count} ok | ❌ {fail_count} failed | "
        f"⏱️  {elapsed}s elapsed"
    )

    # Record this run so the admin panel shows when weather last synced.
    status = "success" if fail_count == 0 else ("partial" if success_count else "failed")
    record_sync(
        "weather", status, success_count,
        f"{success_count}/{total} districts updated"
        + (f", {fail_count} failed" if fail_count else ""),
        start_time,
    )


# ── DB-first fetch (used by route — fully wired in Response 5) ──

async def fetch_weather(district: str) -> dict:
    """
    Serve weather entirely from DB — no OWM call.
    Fully implemented in Response 5 (weather.py route update).
    This stub preserves compatibility so the app stays runnable.
    """
    db = SessionLocal()
    try:
        row = db.query(WeatherCache).filter(
            WeatherCache.district == district
        ).first()

        if not row:
            return {
                "success": False,
                "message": f"'{district}' का मौसम डेटा अभी उपलब्ध नहीं — कृपया कुछ देर बाद पुनः प्रयास करें।",
                "data":    {}
            }

        return {
            "success": True,
            "message": "stale" if row.is_stale else "",
            "data": {
                "district":         row.district,
                "temperature":      row.temperature,
                "feels_like":       row.feels_like,
                "humidity":         row.humidity,
                "wind_speed":       row.wind_speed,
                "rainfall":         row.rainfall,
                "weather_condition":row.weather_condition,
                "icon_url":         row.icon_url,
                "farming_tip":      row.farming_tip,
                "fetched_at":       row.fetched_at.isoformat() if row.fetched_at else None,
                "is_stale":         row.is_stale,
            }
        }
    finally:
        db.close()