# ============================================================
# services/leads.py
# Lead-gen / affiliate offers shown on the high-traffic /bhav pages.
#
# A free price page monetises a farmer's visit only in ad pennies. A relevant
# service link — KCC loan, crop insurance, solar-pump subsidy — is worth far
# more per click and needs no fulfilment on our side: the click goes to a
# partner (or, for now, the official scheme page). This module just loads the
# offer config; the render + the tracked /go/<id> redirect live in routes/bhav.
#
# Config: data/lead_offers.json, read live and cached by mtime (no deploy needed
# to change offers — in line with the project's "everything automatic" rule).
# An offer is LIVE only when active:true AND it has a non-empty url, so the card
# never shows a half-configured or bogus link.
# ============================================================
import json
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "data" / "lead_offers.json"

_cache: dict | None = None
_mtime: float = -1.0


def _load() -> dict:
    global _cache, _mtime
    try:
        m = _PATH.stat().st_mtime
    except OSError:
        return {"offers": []}
    if _cache is None or m != _mtime:
        try:
            _cache = json.loads(_PATH.read_text(encoding="utf-8"))
        except Exception:
            _cache = {"offers": []}
        _mtime = m
    return _cache


def heading() -> str:
    return _load().get("heading", "किसान सेवाएं")


def sub() -> str:
    return _load().get("sub", "")


def active_offers() -> list:
    """Only the offers that are switched on AND have a destination URL."""
    return [o for o in _load().get("offers", [])
            if o.get("active") and (o.get("url") or "").strip()]


def offer_by_id(offer_id: str) -> dict | None:
    for o in active_offers():
        if o.get("id") == offer_id:
            return o
    return None
