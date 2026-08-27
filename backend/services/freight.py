# ============================================================
# services/freight.py
# Honest freight-cost estimates for "net price after transport".
#
# A mandi price table never tells a farmer the ONE thing that decides where he
# actually earns more: what it costs to cart the crop there. A farther mandi
# quoting a higher rate can net LESS than the mandi next door once freight is
# paid. This module turns a distance (km) + vehicle tier + quantity (quintal)
# into an estimated ₹/quintal freight, so the caller can rank mandis by
# NET भाव = modal − freight.
#
# Pure functions, no FastAPI/DB import. Rates live in data/freight_rates.json
# (read live, cached by mtime) so they can be tuned without a deploy — in line
# with the project's "everything automatic, no manual re-run" rule. These are
# deliberately labelled ESTIMATES, never quotes.
# ============================================================
import json
import math
from pathlib import Path

_RATES_PATH = Path(__file__).resolve().parents[1] / "data" / "freight_rates.json"

_rates: dict | None = None
_rates_mtime: float = -1.0

# Fallback used only if the JSON is missing/broken, so the calculator never
# hard-fails — mirrors the shape of freight_rates.json.
_FALLBACK = {
    "default_tier": "trolley",
    "max_radius_km": 150,
    "tiers": {
        "trolley": {"label": "ट्रैक्टर-ट्रॉली", "hint": "पास की मंडी",
                    "rental_slug": "tractor-trolley",
                    "fixed_inr": 200, "per_km_inr": 15, "capacity_q": 25},
        "mini":    {"label": "मिनी-ट्रक", "hint": "मध्यम दूरी",
                    "rental_slug": "mini-truck",
                    "fixed_inr": 400, "per_km_inr": 22, "capacity_q": 40},
        "truck":   {"label": "ट्रक", "hint": "दूर की मंडी",
                    "rental_slug": "truck",
                    "fixed_inr": 1200, "per_km_inr": 40, "capacity_q": 120},
    },
}


def load_rates() -> dict:
    """freight_rates.json as a dict, reloaded only when the file changes."""
    global _rates, _rates_mtime
    try:
        m = _RATES_PATH.stat().st_mtime
    except OSError:
        return _FALLBACK
    if _rates is None or m != _rates_mtime:
        try:
            data = json.loads(_RATES_PATH.read_text(encoding="utf-8"))
            # A JSON with no usable tiers is worse than the fallback.
            _rates = data if data.get("tiers") else _FALLBACK
        except Exception:
            _rates = _FALLBACK
        _rates_mtime = m
    return _rates


def default_tier() -> str:
    return load_rates().get("default_tier", "trolley")


def max_radius_km() -> float:
    try:
        return float(load_rates().get("max_radius_km", 150))
    except (TypeError, ValueError):
        return 150.0


def tiers() -> dict:
    """{key: {label, hint, ...}} — for building the vehicle selector."""
    return load_rates().get("tiers", _FALLBACK["tiers"])


def rental_slug(tier: str) -> str:
    """The /rental machine that IS this vehicle tier, or "" when none is named.

    The mapping lives in freight_rates.json beside the tier it describes, so a
    renamed machine is one data edit and never a deploy. "" is a normal answer,
    not an error: a tier nobody hires out yet simply shows no owners, exactly as
    a machine with no listings shows none on /rental.
    """
    return str(_tier_cfg(tier).get("rental_slug") or "").strip().lower()


def _tier_cfg(tier: str) -> dict:
    t = load_rates().get("tiers", {})
    return t.get(tier) or t.get(default_tier()) or next(iter(_FALLBACK["tiers"].values()))


def freight_per_q(distance_km: float, tier: str, qty_q: float) -> int:
    """Estimated freight in ₹ per quintal for a one-way haul.

    Model: a vehicle is HIRED for the trip — cost = fixed + per_km·distance —
    and that trip cost is spread over the quintals it carries. A load bigger
    than one vehicle needs more trips (ceil), so the per-quintal cost stops
    falling once the vehicle is full. This is why quantity matters: a bigger
    load spreads the hire and makes a farther, higher-paying mandi worth it.
    Returns a non-negative integer ₹/quintal.
    """
    cfg = _tier_cfg(tier)
    d = max(0.0, float(distance_km or 0))
    qty = max(1.0, float(qty_q or 1))
    cap = max(1.0, float(cfg.get("capacity_q", 25)))
    trip = float(cfg.get("fixed_inr", 200)) + float(cfg.get("per_km_inr", 15)) * d
    trips = math.ceil(qty / cap)
    return int(round(trips * trip / qty))


def net_price(modal_per_q: float, distance_km: float, tier: str, qty_q: float) -> dict:
    """modal − freight, as a small breakdown dict for one mandi."""
    modal = float(modal_per_q or 0)
    fr = freight_per_q(distance_km, tier, qty_q)
    return {
        "modal": int(round(modal)),
        "freight_per_q": fr,
        "net_per_q": int(round(modal - fr)),
        "distance_km": round(float(distance_km or 0), 1),
    }
