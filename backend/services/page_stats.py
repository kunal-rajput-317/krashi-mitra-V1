# ============================================================
# backend/services/page_stats.py
# How much search traffic each /bhav page actually got, per crop×district.
#
# WHY THIS EXISTS. Listings are sold per crop page. Without this, a dealer
# picking crops is guessing, and so are we: he pays ₹50 for a page that may
# have been seen 475 times last month or zero times, and only finds out which
# after a season of nothing. That is the churn conversation the whole rate card
# dies on. So the number goes in front of him BEFORE he picks, and the pages
# worth nothing stop being sold — which is a better outcome than pricing them
# cleverly.
#
# IMPRESSIONS, NOT CLICKS. Both are available; impressions are shown. A top
# page does ~475 impressions and ~5 clicks in 28 days, and "5" reads as a
# reason not to buy while being no more true — the dealer is buying visibility
# on a page, and an impression is exactly that page appearing in a farmer's
# search results. `clicks` is carried in the payload anyway so the admin panel
# can quote the harder number on a renewal call.
#
# NEVER CALLS GOOGLE FROM A REQUEST. The Search Analytics API takes seconds and
# is quota-limited; a dealer opening a crop picker must not pay for that, and a
# hundred of them must not exhaust the day's quota. One daily refresh writes a
# whole-site snapshot to disk, and every read is served from memory.
#
# DEGRADES TO SILENCE, NEVER TO A GUESS. No credentials, no snapshot, an API
# that 403s — every one of those returns "no number for this page", and the
# picker renders without the line. It must never fall back to an estimate: a
# made-up impression count is a false claim about our own inventory, printed
# next to a price.
# ============================================================
import json
import logging
import os
import threading
import time
from datetime import date, timedelta
from pathlib import Path

logger = logging.getLogger("krishi.page_stats")

# 28 days, matching what Search Console's own UI calls "last 28 days" — the
# window the owner sees when he cross-checks a number a dealer was quoted.
WINDOW_DAYS = 28

# Google is still counting the most recent ~2 days; including them would make
# every page look like it is declining.
LAG_DAYS = 3

CACHE_DIR = Path(os.getenv("KM_CACHE_DIR", "cache"))
CACHE_FILE = CACHE_DIR / "page_stats.json"

# A snapshot older than this is stale enough that the numbers would misrepresent
# the season. Served anyway — an old true number beats no number — but flagged
# so the picker and the admin panel can say when it is from.
STALE_AFTER_DAYS = 10

_lock = threading.Lock()
_cache: dict | None = None
_loaded_at = -1.0
_DISK_TTL = 300.0        # re-read the file this often, so a refresh lands live


def _key(crop: str, state: str, district: str = "") -> str:
    """Same slug spelling as a /bhav URL, which is what the GSC rows carry."""
    parts = [(crop or "").strip().lower(), (state or "").strip().lower(),
             (district or "").strip().lower()]
    return "/".join(p for p in parts if p)


def _parse_url(url: str) -> str | None:
    """A GSC page URL → our crop/state/district key, or None if it is not a
    /bhav price page. Sub-pages (/kharidar) are folded away rather than counted
    as their own inventory: nothing is sold on them separately."""
    if "/bhav/" not in url:
        return None
    tail = url.split("/bhav/", 1)[1].split("?")[0].split("#")[0]
    seg = [s for s in tail.strip("/").split("/") if s]
    if seg and seg[-1] == "kharidar":
        seg = seg[:-1]
    if not 1 <= len(seg) <= 3:
        return None
    return "/".join(s.lower() for s in seg)


# ── reading ─────────────────────────────────────────────────────────────────

def _load() -> dict:
    """The snapshot, from memory or disk. Never raises: a missing or corrupt
    file means the picker shows no numbers, which is a working page."""
    global _cache, _loaded_at
    now = time.time()
    if _cache is not None and (now - _loaded_at) < _DISK_TTL:
        return _cache
    data: dict = {}
    try:
        if CACHE_FILE.exists():
            data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("page_stats snapshot unreadable, showing no numbers: %s", e)
        data = {}
    with _lock:
        _cache, _loaded_at = data, now
    return data


def invalidate() -> None:
    global _cache, _loaded_at
    with _lock:
        _cache, _loaded_at = None, -1.0


def snapshot_age_days() -> int | None:
    """How old the numbers are, or None if there are none."""
    fetched = (_load() or {}).get("fetched_on")
    if not fetched:
        return None
    try:
        return (date.today() - date.fromisoformat(fetched)).days
    except ValueError:
        return None


def is_stale() -> bool:
    age = snapshot_age_days()
    return age is None or age > STALE_AFTER_DAYS


def for_page(crop: str, state: str, district: str = "") -> dict | None:
    """{impressions, clicks} for one page, or None if we have no data at all.

    ABSENT FROM A SNAPSHOT MEANS ZERO, NOT UNKNOWN. Search Analytics only
    returns rows for URLs that got at least one impression, so a page missing
    from a snapshot we successfully took is a page Google showed to nobody —
    and that is the single most useful thing the picker can tell a dealer.
    Reporting it as "no data" would blank the number on ~90% of crops and hide
    exactly the ones he should not spend ₹50 on.

    None is reserved for the genuinely unknown: no snapshot has ever been
    taken (no credentials, first boot, a refresh that failed). Then the picker
    shows nothing rather than claiming every page is dead.
    """
    snap = _load() or {}
    rows = snap.get("pages")
    if not rows:
        return None                    # no snapshot — we truly do not know
    hit = rows.get(_key(crop, state, district))
    if hit is None:
        return {"impressions": 0, "clicks": 0}
    return {"impressions": hit.get("i", 0), "clicks": hit.get("c", 0)}


def have_data() -> bool:
    """Whether any snapshot exists. The one check a caller needs before deciding
    if a blank number means "dead page" or "we have not looked yet"."""
    return bool((_load() or {}).get("pages"))


def for_district(state: str, district: str, crops: list[str]) -> dict:
    """{crop_slug: {impressions, clicks} | None} for a whole crop picker in one
    call — the shape the /dukanlisting crop list needs, without a lookup per
    checkbox."""
    return {c: for_page(c, state, district) for c in crops}


def zero_pages(pairs: list[tuple]) -> list[tuple]:
    """Which of these (crop, state, district) pages Google showed to nobody.

    The admin's pre-sale check: selling a slot on one of these is taking money
    for an empty room. Returns nothing at all when no snapshot exists, rather
    than flagging every page as dead on a box that has never had credentials.
    """
    if not have_data():
        return []
    out = []
    for crop, state, district in pairs:
        s = for_page(crop, state, district)
        if s is not None and s["impressions"] == 0:
            out.append((crop, state, district))
    return out


# ── writing ─────────────────────────────────────────────────────────────────

def refresh() -> dict:
    """Pull one whole-site snapshot from Search Console and write it to disk.

    Called by the daily scheduler, and safe to call by hand. Returns a summary
    rather than raising — this runs unattended, and a failed refresh must leave
    yesterday's snapshot in place rather than replacing it with nothing.
    """
    from backend.services import gsc_service

    if not gsc_service.configured():
        logger.info("GSC not configured — page stats not refreshed")
        return {"status": "skipped", "reason": "gsc_not_configured"}

    end = date.today() - timedelta(days=LAG_DAYS)
    start = end - timedelta(days=WINDOW_DAYS - 1)
    try:
        rows = gsc_service.search_analytics(
            start.isoformat(), end.isoformat(), ["page"], row_limit=25000)
    except Exception as e:
        logger.warning("page stats refresh failed, keeping the old snapshot: %s", e)
        return {"status": "error", "reason": str(e)[:200]}

    if not rows:
        # An empty result is indistinguishable from an auth failure at this
        # layer, and overwriting a good snapshot with {} would silently blank
        # every number on the site. Keep what we have.
        logger.warning("page stats refresh returned no rows — keeping the old snapshot")
        return {"status": "empty", "pages": 0}

    pages: dict[str, dict] = {}
    for r in rows:
        key = _parse_url(r.get("page", ""))
        if not key:
            continue
        acc = pages.setdefault(key, {"i": 0, "c": 0})
        acc["i"] += int(r.get("impressions") or 0)
        acc["c"] += int(r.get("clicks") or 0)

    payload = {
        "fetched_on":  date.today().isoformat(),
        "window_days": WINDOW_DAYS,
        "start":       start.isoformat(),
        "end":         end.isoformat(),
        "pages":       pages,
    }
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        # Write-then-rename: a reader hitting the file mid-write would otherwise
        # get a truncated JSON document and log it as corruption.
        tmp = CACHE_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        tmp.replace(CACHE_FILE)
    except Exception as e:
        logger.warning("page stats snapshot not written: %s", e)
        return {"status": "error", "reason": str(e)[:200]}

    invalidate()
    logger.info("📊 page stats refreshed | %d pages | %s..%s",
                len(pages), start, end)
    return {"status": "ok", "pages": len(pages),
            "start": start.isoformat(), "end": end.isoformat()}
