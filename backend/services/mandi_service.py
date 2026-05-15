# ============================================================
# services/mandi_service.py
# Krishi Mitra — Mandi Price Service
# Reads from crop_mandi_price.json loaded once at startup.
# No FastAPI dependency here.
# ============================================================

import json
import os

# Load mandi prices from JSON file once at module import
_json_path = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "data",
    "crop_mandi_price.json"
)
with open(_json_path, "r") as f:
    mandi_data = json.load(f)


def get_mandi_prices(commodity: str, district: str, state: str) -> dict:
    records = mandi_data.get("records", [])

    filtered = [r for r in records if r.get("commodity", "").lower() == commodity.lower()]

    if state:
        filtered = [r for r in filtered if r.get("state", "").lower() == state.lower()]

    if district:
        filtered = [r for r in filtered if r.get("district", "").lower() == district.lower()]

    if not filtered:
        return {"commodity": commodity, "prices": [], "message": "No data found"}

    prices = [{
        "market":      r.get("market", "-"),
        "district":    r.get("district", "-"),
        "state":       r.get("state", "-"),
        "commodity":   r.get("commodity", "-"),
        "variety":     r.get("variety", "-"),
        "grade":       r.get("grade", "-"),
        "min_price":   str(r.get("min_price", "-")),
        "max_price":   str(r.get("max_price", "-")),
        "modal_price": str(r.get("modal_price", "-")),
        "date":        r.get("arrival_date", "-")
    } for r in filtered[:50]]

    return {"commodity": commodity, "prices": prices}


def get_states() -> dict:
    records = mandi_data.get("records", [])
    states  = sorted(set(r.get("state", "") for r in records if r.get("state")))
    return {"states": states}


def get_districts(state: str) -> dict:
    records   = mandi_data.get("records", [])
    filtered  = [r for r in records if r.get("state", "").lower() == state.lower()]
    districts = sorted(set(r.get("district", "") for r in filtered if r.get("district")))
    return {"districts": districts}


def get_commodities(state: str) -> dict:
    records     = mandi_data.get("records", [])
    filtered    = [r for r in records if r.get("state", "").lower() == state.lower()]
    commodities = sorted(set(r.get("commodity", "") for r in filtered if r.get("commodity")))
    return {"commodities": commodities}