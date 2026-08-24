# ============================================================
# services/index_gate.py
# Which /bhav price pages are allowed to claim a place in Google's index.
#
# The site renders ~14,000 /bhav URLs. 5,624 have ever earned an impression;
# half of those earn five or fewer and 38 clicks between the lot, while the top
# tenth carries 64% of everything. Google forms ONE opinion of a site out of
# all of it, which is why the strong pages sit at the bottom of page one rather
# than the top: 72% of impressions land at positions 4-10 and convert at 0.42%,
# against 3.03% for positions 1-3. This module withdraws the thin tail's claim
# on the index so the strong pages are judged on their own.
#
# THE SIGNAL IS FRESHNESS, AND ONLY FRESHNESS. A price page whose newest
# reading is months old is worthless to a farmer whatever else is on it, and
# the last-reported date is already in the page index (idx["dates"]) — so all
# ~14k URLs can be judged with no extra database work. Mandi count would be a
# reasonable second signal and is deliberately not used: counting rows per
# district means a query per URL.
#
# WHAT THIS IS NOT: a delete, a 404 or a redirect. These are real crop-and-
# district pages carrying real, if old, data — not duplicates to merge. They
# stay live and fully usable, and the robots value keeps `follow` so their
# links go on feeding the rest of the site. The only thing withdrawn is the
# claim on the index.
#
# SEQUENCING — this is step 1 of 3, and bhav_sitemap() is deliberately NOT
# touched. Google obeys a noindex only when it comes back and reads the page;
# dropping these URLs from the sitemap at the same time removes the main reason
# for it to revisit, leaving the noindex unread for months. Keep them in the
# sitemap until they have actually left the index, then remove them.
#
# Thresholds live in data/index_gate.json, read live and cached by mtime.
# `enabled` starts false: the verdict is still computed and reported at
# /admin/index-gate, so the blast radius is visible before anything changes for
# Google.
#
# Pure functions, no FastAPI/DB import — same contract as services/msp.py.
# ============================================================
import json
from datetime import date
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "data" / "index_gate.json"

_DEFAULT_MAX_AGE = 30
_DEFAULT_ROBOTS = "noindex, follow"

_cache: dict | None = None
_mtime: float = -1.0


def _load() -> dict:
    global _cache, _mtime
    try:
        m = _PATH.stat().st_mtime
    except OSError:
        return {}
    if _cache is None or m != _mtime:
        try:
            _cache = json.loads(_PATH.read_text(encoding="utf-8"))
        except Exception:
            _cache = {}
        _mtime = m
    return _cache or {}


def is_enabled() -> bool:
    """False until someone has looked at the split and turned it on. A missing
    or unreadable config reads as OFF — this feature's failure mode must be
    "nothing happened", never "the site quietly deindexed itself"."""
    return bool(_load().get("enabled"))


def max_age_days() -> int:
    try:
        n = int(_load().get("max_age_days", _DEFAULT_MAX_AGE))
    except (TypeError, ValueError):
        return _DEFAULT_MAX_AGE
    return n if n > 0 else _DEFAULT_MAX_AGE


def robots_value() -> str:
    v = (_load().get("robots") or "").strip()
    return v or _DEFAULT_ROBOTS


def age_days(last_iso: str, today: date | None = None) -> int | None:
    """Days since the page's newest reported price. None when there is no
    usable date — which is NOT the same as "very old"; see verdict()."""
    if not last_iso:
        return None
    try:
        d = date.fromisoformat(str(last_iso).strip()[:10])
    except (TypeError, ValueError):
        return None
    delta = ((today or date.today()) - d).days
    # A date in the future is a feed artefact, not freshness. Clamp rather than
    # return a negative that every downstream comparison would read as fresh.
    return max(delta, 0)


def verdict(last_iso: str, today: date | None = None) -> dict:
    """Should this page claim a place in the index?

    Returns {index, age_days, reason} always — never raises, and never has to
    be called defensively.

    A page with NO date at all keeps its index place. Those are pre-migration
    rows; absence of a date is not evidence of staleness, and the safe default
    is today's behaviour.
    """
    n = age_days(last_iso, today)
    if n is None:
        return {"index": True, "age_days": None, "reason": "no-date"}
    cap = max_age_days()
    if n <= cap:
        return {"index": True, "age_days": n, "reason": f"fresh ({n}d ≤ {cap}d)"}
    return {"index": False, "age_days": n, "reason": f"stale ({n}d > {cap}d)"}


def robots_for(last_iso: str, today: date | None = None) -> str:
    """The `robots` meta value for a page, or "" to leave it as it is.

    Returns "" whenever the gate is off, so wiring this into a route changes
    nothing at all until the config says otherwise. Routes can call it
    unconditionally.
    """
    if not is_enabled():
        return ""
    return "" if verdict(last_iso, today)["index"] else robots_value()


def split(dates_index: dict, today: date | None = None) -> dict:
    """Blast radius over the whole URL set, straight from idx["dates"].

    {crop_slug: {state_slug: {district_slug: "YYYY-MM-DD"}}} in, counts out —
    plus the state rollups, which are as fresh as their newest district exactly
    the way bhav_sitemap() rolls up <lastmod>. This is what /admin/index-gate
    renders so the split can be read BEFORE `enabled` is flipped.
    """
    today = today or date.today()
    out = {
        "enabled": is_enabled(),
        "max_age_days": max_age_days(),
        "robots": robots_value(),
        "district": {"index": 0, "noindex": 0, "no_date": 0},
        "state":    {"index": 0, "noindex": 0, "no_date": 0},
        "buckets":  {"0-7": 0, "8-30": 0, "31-90": 0, "91-365": 0, "365+": 0,
                     "no-date": 0},
    }
    for _cs, states in (dates_index or {}).items():
        for _ss, dists in (states or {}).items():
            newest = ""
            for _ds, d_iso in (dists or {}).items():
                newest = max(newest, d_iso or "")
                v = verdict(d_iso, today)
                if v["age_days"] is None:
                    out["district"]["no_date"] += 1
                    out["buckets"]["no-date"] += 1
                else:
                    out["district"]["index" if v["index"] else "noindex"] += 1
                    n = v["age_days"]
                    key = ("0-7" if n <= 7 else "8-30" if n <= 30 else
                           "31-90" if n <= 90 else "91-365" if n <= 365 else "365+")
                    out["buckets"][key] += 1
            sv = verdict(newest, today)
            if sv["age_days"] is None:
                out["state"]["no_date"] += 1
            else:
                out["state"]["index" if sv["index"] else "noindex"] += 1

    for scope in ("district", "state"):
        s = out[scope]
        s["total"] = s["index"] + s["noindex"] + s["no_date"]
        s["pct_noindex"] = round(100 * s["noindex"] / s["total"], 1) if s["total"] else 0.0
    return out
