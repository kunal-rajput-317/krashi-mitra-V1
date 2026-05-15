# ============================================================
# services/weather_context_service.py
# KrashiMitra — Weather Context for Search
#
# Reads WeatherCache (already populated by scheduler every 8h).
# Returns structured alerts + risk scores to enrich search results.
# No OWM API calls here — DB only.
# ============================================================

import logging
from typing import Optional
from datetime import datetime, timedelta

from backend.database.db import SessionLocal, WeatherCache

logger = logging.getLogger("krishi.weather_context")


# ── How stale is "too stale" to show ────────────────────────
MAX_STALE_HOURS = 24   # show data up to 24h old, then skip


# ── Weather condition → disease/topic risk map ───────────────
# Each rule: (condition_fn, affected_types, alert_hindi, alert_en, severity)
# severity: "high" | "medium" | "info"

WEATHER_RULES = [
    # ── Fungal / blast disease risk (high humidity) ──────────
    {
        "id":       "high_humidity_fungal",
        "check":    lambda w: w.humidity is not None and w.humidity >= 80,
        "types":    ["disease"],                      # show on disease result cards
        "keywords": ["फफूंद", "blast", "jhonka", "blight", "jhulsa",
                     "rust", "ratua", "gerui", "fungal", "rot", "sadan"],
        "alert":    "⚠️ नमी {humidity}% — फफूंद और झुलसा रोग का खतरा बढ़ा है",
        "alert_en": "⚠️ Humidity {humidity}% — High risk of fungal & blight diseases",
        "severity": "high",
        "banner":   True,
    },
    # ── Very high humidity — any crop alert ─────────────────
    {
        "id":       "very_high_humidity",
        "check":    lambda w: w.humidity is not None and w.humidity >= 88,
        "types":    ["disease", "fertilizer", "sowing"],
        "keywords": [],                               # matches all results
        "alert":    "🍄 अत्यधिक नमी ({humidity}%) — सभी फसलों में रोग निगरानी करें",
        "alert_en": "🍄 Extreme humidity ({humidity}%) — Monitor all crops for disease",
        "severity": "high",
        "banner":   True,
    },
    # ── Active rainfall — no spraying ───────────────────────
    {
        "id":       "rainfall_no_spray",
        "check":    lambda w: w.rainfall is not None and w.rainfall > 0,
        "types":    ["disease", "fertilizer"],
        "keywords": [],
        "alert":    "🌧️ बारिश हो रही है ({rainfall}mm) — आज कीटनाशक / खाद छिड़काव न करें",
        "alert_en": "🌧️ Rainfall active ({rainfall}mm) — Avoid spraying today",
        "severity": "high",
        "banner":   True,
    },
    # ── High wind — no spraying ──────────────────────────────
    {
        "id":       "high_wind_no_spray",
        "check":    lambda w: w.wind_speed is not None and w.wind_speed >= 20,
        "types":    ["disease", "fertilizer"],
        "keywords": [],
        "alert":    "💨 तेज़ हवा ({wind_speed} m/s) — छिड़काव और खाद डालने से बचें",
        "alert_en": "💨 Strong wind ({wind_speed} m/s) — Avoid spray & fertilizer application",
        "severity": "medium",
        "banner":   True,
    },
    # ── Frost risk — protect crops ───────────────────────────
    {
        "id":       "frost_risk",
        "check":    lambda w: w.temperature is not None and w.temperature <= 5,
        "types":    ["disease", "sowing", "fertilizer"],
        "keywords": [],
        "alert":    "🥶 पाले का खतरा ({temp}°C) — फसलों को रात में ढकें, सिंचाई करें",
        "alert_en": "🥶 Frost risk ({temp}°C) — Cover crops at night, irrigate",
        "severity": "high",
        "banner":   True,
    },
    # ── Cold weather — sowing timing alert ──────────────────
    {
        "id":       "cold_sowing",
        "check":    lambda w: w.temperature is not None and 5 < w.temperature <= 12,
        "types":    ["sowing"],
        "keywords": ["बुवाई", "sowing", "buwai", "lagana"],
        "alert":    "❄️ ठंड अधिक है ({temp}°C) — बुवाई में देरी उचित, पाले से सावधान",
        "alert_en": "❄️ Cold weather ({temp}°C) — Delay sowing, watch for frost",
        "severity": "medium",
        "banner":   False,
    },
    # ── Extreme heat — irrigation alert ─────────────────────
    {
        "id":       "extreme_heat",
        "check":    lambda w: w.temperature is not None and w.temperature >= 40,
        "types":    ["sowing", "fertilizer"],
        "keywords": [],
        "alert":    "🔥 अत्यधिक गर्मी ({temp}°C) — सिंचाई बढ़ाएं, दोपहर में खेत न जाएं",
        "alert_en": "🔥 Extreme heat ({temp}°C) — Increase irrigation, avoid midday fieldwork",
        "severity": "high",
        "banner":   True,
    },
    # ── High heat — fertilizer timing ───────────────────────
    {
        "id":       "high_heat_fertilizer",
        "check":    lambda w: w.temperature is not None and 35 <= w.temperature < 40,
        "types":    ["fertilizer"],
        "keywords": ["urea", "यूरिया", "khad", "खाद"],
        "alert":    "🌡️ गर्मी ({temp}°C) — सुबह जल्दी या शाम को खाद डालें",
        "alert_en": "🌡️ Hot ({temp}°C) — Apply fertilizer early morning or evening",
        "severity": "medium",
        "banner":   False,
    },
    # ── Good weather — positive confirmation ────────────────
    {
        "id":       "good_weather",
        "check":    lambda w: (
            w.temperature is not None and 18 <= w.temperature <= 32
            and w.humidity is not None and w.humidity < 75
            and (w.rainfall or 0) == 0
            and (w.wind_speed or 0) < 15
        ),
        "types":    ["sowing", "fertilizer"],
        "keywords": [],
        "alert":    "✅ खेती के लिए अच्छा मौसम ({temp}°C, नमी {humidity}%) — आज काम करें",
        "alert_en": "✅ Good farming weather ({temp}°C, {humidity}% humidity) — Good day to work",
        "severity": "info",
        "banner":   False,
    },
]


def _format_alert(template: str, weather) -> str:
    """Fill placeholders in alert template with real weather values."""
    return (template
        .replace("{humidity}",   str(weather.humidity or "—"))
        .replace("{temp}",       str(round(weather.temperature, 1)) if weather.temperature else "—")
        .replace("{rainfall}",   str(round(weather.rainfall, 1)) if weather.rainfall else "0")
        .replace("{wind_speed}", str(round(weather.wind_speed, 1)) if weather.wind_speed else "—")
    )


def _is_fresh(weather: WeatherCache) -> bool:
    """Return True if cached weather data is recent enough to use."""
    if not weather.fetched_at:
        return False
    age = datetime.utcnow() - weather.fetched_at
    return age < timedelta(hours=MAX_STALE_HOURS)


def get_weather_context(district: str) -> Optional[dict]:
    """
    Fetch weather for a district from DB cache.
    Returns structured context dict, or None if unavailable.

    Return shape:
    {
        "district":    "Meerut",
        "temperature": 28.5,
        "humidity":    85,
        "rainfall":    0.0,
        "wind_speed":  12.3,
        "condition":   "Haze",
        "farming_tip": "...",
        "is_stale":    False,
        "banner_alerts": [...],   # shown at top of results
        "rules":         [...],   # full rule list for per-card matching
    }
    """
    if not district or not district.strip():
        return None

    db = SessionLocal()
    try:
        # Normalize district name (strip village suffix if present)
        # Frontend sends "Meerut district" or "Meerut" — handle both
        clean_district = district.strip()
        for suffix in [" district", " District", " जिला"]:
            if clean_district.endswith(suffix):
                clean_district = clean_district[: -len(suffix)].strip()
        # Also strip village prefix: "Hapur village, Meerut district" → "Meerut"
        if "," in clean_district:
            clean_district = clean_district.split(",")[-1].strip()

        row = db.query(WeatherCache).filter(
            WeatherCache.district == clean_district
        ).first()

        if not row:
            logger.debug(f"No weather cache row for district: {clean_district!r}")
            return None

        if not _is_fresh(row):
            logger.debug(f"Weather data too stale for {clean_district}")
            return None

        # ── Evaluate all rules against current weather ───────
        banner_alerts = []
        active_rules  = []

        for rule in WEATHER_RULES:
            try:
                if rule["check"](row):
                    formatted = _format_alert(rule["alert"], row)
                    rule_hit = {
                        "id":       rule["id"],
                        "alert":    formatted,
                        "types":    rule["types"],
                        "keywords": rule["keywords"],
                        "severity": rule["severity"],
                    }
                    active_rules.append(rule_hit)
                    if rule.get("banner"):
                        banner_alerts.append({
                            "text":     formatted,
                            "severity": rule["severity"],
                        })
            except Exception as e:
                logger.warning(f"Rule {rule['id']} evaluation error: {e}")

        # Deduplicate banners — keep highest severity per message
        seen = set()
        unique_banners = []
        for b in banner_alerts:
            key = b["text"][:40]
            if key not in seen:
                seen.add(key)
                unique_banners.append(b)

        return {
            "district":    row.district,
            "temperature": row.temperature,
            "humidity":    row.humidity,
            "rainfall":    row.rainfall or 0.0,
            "wind_speed":  row.wind_speed,
            "condition":   row.weather_condition,
            "farming_tip": row.farming_tip,
            "is_stale":    row.is_stale,
            "banner_alerts": unique_banners[:3],   # max 3 banners
            "rules":         active_rules,
        }

    except Exception as e:
        logger.error(f"get_weather_context error for {district!r}: {e}")
        return None
    finally:
        db.close()


def attach_weather_to_results(results: list, weather_ctx: Optional[dict]) -> list:
    """
    For each result, check if any active weather rule applies to it.
    Attach a 'weather_alert' field to matching results.
    Non-matching results get weather_alert = None.
    """
    if not weather_ctx or not results:
        for r in results:
            r["weather_alert"] = None
        return results

    active_rules = weather_ctx.get("rules", [])

    for result in results:
        result_type = result.get("type", "general")
        # Combine all text fields for keyword matching
        result_text = " ".join(filter(None, [
            result.get("name", ""),
            result.get("name_en", ""),
            " ".join(result.get("keywords", [])),
            result.get("symptoms", ""),
        ])).lower()

        matched_alert = None
        matched_severity = None

        for rule in active_rules:
            # Check result type matches rule's target types
            if result_type not in rule["types"]:
                continue

            # If rule has no keywords — applies to all results of that type
            rule_keywords = rule.get("keywords", [])
            if not rule_keywords:
                matched_alert    = rule["alert"]
                matched_severity = rule["severity"]
                break

            # Check if any rule keyword appears in result text
            for kw in rule_keywords:
                if kw.lower() in result_text:
                    matched_alert    = rule["alert"]
                    matched_severity = rule["severity"]
                    break

            if matched_alert:
                break

        result["weather_alert"]          = matched_alert
        result["weather_alert_severity"] = matched_severity

    return results