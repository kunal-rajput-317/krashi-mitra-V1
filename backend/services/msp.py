# ============================================================
# services/msp.py
# MSP (न्यूनतम समर्थन मूल्य) lookup + "MSP से कितना ऊपर/नीचे" comparison.
#
# A mandi price on its own doesn't tell a farmer the one thing the government
# already promised him: the floor. "गेहूं ₹2,410" means nothing until you know
# MSP is ₹2,585 — that gap is the difference between selling at the mandi and
# taking the crop to a procurement centre. Agmarknet reports modal_price in
# ₹/quintal and MSP is declared in ₹/quintal, so the two subtract directly.
#
# Pure functions, no FastAPI/DB import. Rates live in data/msp_rates.json, read
# live and cached by mtime — MSP changes twice a year and must never need a
# deploy ("everything automatic").
#
# TWO GUARDS, both enforced here rather than left to discipline, because a wrong
# MSP is worse than no MSP (a farmer could sell below the floor believing he is
# above it):
#   1. verified:false  → the crop is invisible until someone confirms the figure.
#   2. season expired  → the whole season stops rendering after valid_until,
#      so a stale MSP cannot outlive its marketing season.
#
# Matching is EXACT on the alias list, never a keyword contains(). The keyword
# approach is what puts wheat's MSP on "Wheat Atta" and mustard's on "Mustard
# Oil" — the same class of bug routes/bhav.py already documents for crop names.
# ============================================================
import json
import re
from datetime import date
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "data" / "msp_rates.json"

_cache: dict | None = None
_mtime: float = -1.0
_alias_idx: dict[str, str] = {}      # normalised alias → crop key


def _norm(s: str) -> str:
    """Lowercase, collapse whitespace, drop spaces around brackets/slashes so
    'Bengal Gram (Gram) (Whole)' and 'bengal gram(gram)(whole)' are one key."""
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return re.sub(r"\s*([(),/])\s*", r"\1", s)


def _load() -> dict:
    global _cache, _mtime, _alias_idx
    try:
        m = _PATH.stat().st_mtime
    except OSError:
        return {"crops": {}, "seasons": {}}
    if _cache is None or m != _mtime:
        try:
            _cache = json.loads(_PATH.read_text(encoding="utf-8"))
        except Exception:
            _cache = {"crops": {}, "seasons": {}}
        # Rebuild the alias index with the file. Built once per edit, not per
        # request — these pages render ~14k URLs.
        idx: dict[str, str] = {}
        for key, c in (_cache.get("crops") or {}).items():
            for a in (c.get("aliases") or []):
                idx[_norm(a)] = key
            idx.setdefault(_norm(key), key)
        _alias_idx = idx
        _mtime = m
    return _cache


def _season_live(season_key: str) -> bool:
    """False once the marketing season's valid_until has passed — the automatic
    staleness guard. A missing/unparseable date reads as expired: silence beats
    an MSP we can't vouch for."""
    s = (_load().get("seasons") or {}).get(season_key) or {}
    try:
        return date.fromisoformat(s.get("valid_until", "")) >= date.today()
    except (TypeError, ValueError):
        return False


def msp_for(commodity: str) -> dict | None:
    """MSP record for an Agmarknet commodity name, or None when we have no
    confirmed, in-season figure for it. Callers can render unconditionally."""
    data = _load()
    key = _alias_idx.get(_norm(commodity))
    if not key:
        return None
    c = (data.get("crops") or {}).get(key) or {}
    try:
        msp = int(c.get("msp") or 0)
    except (TypeError, ValueError):
        return None
    if not c.get("verified") or msp <= 0:
        return None
    season_key = c.get("season", "")
    if not _season_live(season_key):
        return None
    season = (data.get("seasons") or {}).get(season_key) or {}
    return {
        "key": key,
        "hi": c.get("hi") or key,
        "msp": msp,
        "note": c.get("note", ""),
        "season_key": season_key,
        "season_label": season.get("label", ""),
        "season_short": season.get("short", season.get("label", "")),
        "source_label": data.get("source_label", ""),
        "source_url": data.get("source_url", ""),
    }


def compare(modal_per_q, msp_per_q) -> dict | None:
    """Today's price against the floor. `side` is 'above' | 'below' | 'at'
    ('at' inside ±0.5%, where the difference is noise, not a signal)."""
    try:
        modal = float(modal_per_q or 0)
        msp = float(msp_per_q or 0)
    except (TypeError, ValueError):
        return None
    if modal <= 0 or msp <= 0:
        return None
    diff = modal - msp
    pct = diff / msp * 100
    side = "at" if abs(pct) < 0.5 else ("above" if diff > 0 else "below")
    return {"diff": int(round(diff)), "abs_diff": int(round(abs(diff))),
            "pct": round(pct, 1), "side": side}


def pending() -> dict[str, list[str]]:
    """Crops held back by each guard — {'unverified': [...], 'expired': [...]}.
    Logged at boot so a season that quietly lapsed is visible, not discovered
    by a farmer seeing an empty block."""
    data = _load()
    unverified, expired = [], []
    for key, c in (data.get("crops") or {}).items():
        if not c.get("verified") or not int(c.get("msp") or 0):
            unverified.append(key)
        elif not _season_live(c.get("season", "")):
            expired.append(key)
    return {"unverified": sorted(unverified), "expired": sorted(expired)}
