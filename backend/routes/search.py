# ============================================================
# routes/search.py
# Krishi Mitra — Agriculture Search Router
# Thin FastAPI layer. All logic lives in services/.
# ============================================================
# CHANGED:
#   + district param added
#   + weather_context fetched and attached to response
#   + weather_context_service imported
# ============================================================

from fastapi import APIRouter
from backend.services.search_service          import search_agriculture
from backend.services.weather_context_service import (
    get_weather_context,
    attach_weather_to_results,
)

router = APIRouter()


@router.get("/search")
def search(
    q:        str = "",
    crop:     str = "",
    lang:     str = "hindi",
    district: str = "",          # e.g. "Meerut" or "Meerut district"
):
    """
    Search local agriculture data + enrich with live weather context.

    q        — Hindi or English query string
    crop     — optional crop filter (gehu, dhaan, ganna, sarson, aloo)
    lang     — response language hint (hindi / english)
    district — UP district name for weather context (optional)
    """
    if not q.strip():
        return {"results": [], "query": q, "total": 0, "weather_context": None}

    # 1. Keyword search
    results = search_agriculture(q.strip(), crop.strip(), lang.strip())

    # 2. Weather context (DB read — no API call)
    weather_ctx = get_weather_context(district) if district.strip() else None

    # 3. Attach per-card weather alerts
    results = attach_weather_to_results(results, weather_ctx)

    # 4. Strip internal 'rules' key before sending to client
    client_weather = None
    if weather_ctx:
        client_weather = {
            "district":      weather_ctx["district"],
            "temperature":   weather_ctx["temperature"],
            "humidity":      weather_ctx["humidity"],
            "rainfall":      weather_ctx["rainfall"],
            "wind_speed":    weather_ctx["wind_speed"],
            "condition":     weather_ctx["condition"],
            "farming_tip":   weather_ctx["farming_tip"],
            "is_stale":      weather_ctx["is_stale"],
            "banner_alerts": weather_ctx["banner_alerts"],
        }

    return {
        "results":         results,
        "query":           q,
        "total":           len(results),
        "weather_context": client_weather,
    }