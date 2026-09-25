# ============================================================
# backend/services/mediakit.py
# The numbers a sponsor is shown on /sponsor — measured, dated, never guessed.
#
# WHY THIS EXISTS. A brand's media team asks one question first: how many
# people, and who. Answering it from a hand-typed figure in an HTML file is how
# a media kit quietly becomes a lie — the number was true in August, the page
# still says it in March, and the one thing a first-time sponsor is buying is
# our word. So the figures on /sponsor come from Search Console on a daily
# schedule, carry the window they were measured over, and go away entirely when
# they cannot be refreshed.
#
# THE RULE THIS MODULE IS BUILT AROUND: degrade to silence, never to an
# estimate. No credentials, no snapshot, an API that 403s — every one of those
# makes /sponsor render WITHOUT its numbers block and say the figures are
# available on request. A media kit that rounds up under pressure is a legal
# exposure and a dead relationship; a media kit missing a number is a phone
# call. Same rule as services/page_stats.py, for the same reason, and this
# module deliberately copies its shape rather than inventing a second one.
#
# WHY IT DOES NOT REUSE page_stats' SNAPSHOT. That one keeps /bhav crop×district
# keys and throws every other URL away (_parse_url returns None), because it
# answers "what is one crop page worth to one dealer". A sponsor is buying the
# whole site, so /articles, /naksha, /pashupalan and the rest are exactly the
# rows page_stats discards. Four extra Search Analytics calls a day is the
# cheaper fix.
#
# DEVICE AND COUNTRY ARE HERE ON PURPOSE. They are the two figures that change
# what a brand buys rather than how much they pay for it: 98%-mobile decides
# the creative, and "almost all of this is India" stops an agri exporter
# reading our 127-country long tail as an export audience. See
# [[international-pages-diaspora-not-local-farmers]] — every one of those
# queries is about India.
# ============================================================
import json
import logging
import os
import threading
import time
from datetime import date, timedelta
from pathlib import Path

logger = logging.getLogger("krishi.mediakit")

# 28 days, matching what Search Console's own UI calls "last 28 days" — so a
# sponsor who asks for a screenshot of the dashboard sees the same number the
# page quoted him.
WINDOW_DAYS = 28

# Google is still counting the most recent ~2 days. Including them would make
# the site look like it is shrinking on the one page where that matters most.
LAG_DAYS = 3

CACHE_DIR = Path(os.getenv("KM_CACHE_DIR", "cache"))
CACHE_FILE = CACHE_DIR / "mediakit.json"

# A snapshot older than this is not shown at all. page_stats serves a stale
# number because an old true impression count still helps a dealer pick a crop;
# here the number IS the pitch, and quoting a two-month-old audience to someone
# about to pay for this month's is the exact misrepresentation this module
# exists to prevent.
MAX_AGE_DAYS = 21

# Sections, in the order a sponsor should read them — biggest surface first.
# Prefix match on the URL path; the first hit wins, so keep the more specific
# prefixes above the ones they sit under.
SECTIONS: list[tuple[str, str]] = [
    ("/bhav",           "Mandi prices — crop × state × district"),
    ("/articles",       "Farming guides — dosage, disease, season"),
    ("/naksha",         "Village & district maps"),
    ("/pashupalan",     "Livestock & poultry, incl. daily egg rate"),
    ("/sarkari_yojana", "Government schemes"),
    ("/krashi_news",    "Daily agriculture news"),
    ("/ganna",          "Sugarcane — mill-wise"),
    ("/product",        "Farm inputs & equipment"),
    ("/krashi_dukan",   "Local input-shop directory"),
    ("/weather",        "Weather & rainfall"),
    ("/international",  "Outside India"),
]

_lock = threading.Lock()
_cache: dict | None = None
_loaded_at = -1.0
_DISK_TTL = 300.0        # re-read the file this often, so a refresh lands live


def _section_of(url: str) -> str | None:
    """Which section a GSC page URL belongs to, or None to leave it out of the
    breakdown. The homepage and one-off pages (/about, /pay, /login) are
    real traffic but not sellable inventory, so they count in the site total
    and not in the table."""
    try:
        path = url.split("//", 1)[-1].split("/", 1)[1]
    except IndexError:
        return None
    path = "/" + path.split("?", 1)[0].split("#", 1)[0]
    for prefix, _ in SECTIONS:
        if path == prefix or path.startswith(prefix + "/"):
            return prefix
    return None


def _load() -> dict:
    """The snapshot, from memory or disk. Never raises — an unreadable file
    means /sponsor renders without numbers, which is still a working page."""
    global _cache, _loaded_at
    now = time.time()
    if _cache is not None and (now - _loaded_at) < _DISK_TTL:
        return _cache
    data: dict = {}
    try:
        if CACHE_FILE.exists():
            data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("mediakit snapshot unreadable, showing no numbers: %s", e)
        data = {}
    with _lock:
        _cache, _loaded_at = data, now
    return data


def invalidate() -> None:
    global _cache, _loaded_at
    with _lock:
        _cache, _loaded_at = None, -1.0


def snapshot_age_days() -> int | None:
    fetched = (_load() or {}).get("fetched_on")
    if not fetched:
        return None
    try:
        return (date.today() - date.fromisoformat(fetched)).days
    except ValueError:
        return None


def stats() -> dict | None:
    """Everything /sponsor is allowed to print, or None.

    None is the important return value: it is what a missing snapshot, an
    unparseable one and an out-of-date one all collapse to, so the page has
    exactly one "we have no numbers today" branch to render and cannot
    accidentally print half a media kit.
    """
    data = _load()
    if not data or not data.get("totals"):
        return None
    age = snapshot_age_days()
    if age is None or age > MAX_AGE_DAYS:
        logger.info("mediakit snapshot is %s days old — withholding the numbers", age)
        return None
    return data


def refresh() -> dict:
    """Pull one media-kit snapshot from Search Console and write it to disk.

    Called by the daily GSC scheduler, and safe to run by hand. Returns a
    summary instead of raising: this runs unattended, and a failed refresh must
    leave yesterday's snapshot alone rather than replace it with nothing.
    """
    from backend.services import gsc_service

    if not gsc_service.configured():
        logger.info("GSC not configured — media kit not refreshed")
        return {"status": "skipped", "reason": "gsc_not_configured"}

    end = date.today() - timedelta(days=LAG_DAYS)
    start = end - timedelta(days=WINDOW_DAYS - 1)
    s, e = start.isoformat(), end.isoformat()

    def pull(dims: list[str], limit: int = 25000) -> list[dict]:
        try:
            return gsc_service.search_analytics(s, e, dims, row_limit=limit)
        except Exception as ex:
            logger.warning("media kit: %s query failed: %s", "+".join(dims), ex)
            return []

    # The date series doubles as the site total: summing it is the same figure
    # GSC's own header shows, and it gives the page a real trend to plot
    # instead of a single number a brand has to take on faith.
    days = pull(["date"], limit=400)
    if not days:
        # Indistinguishable from an auth failure at this layer, and blanking a
        # good snapshot would take /sponsor's numbers down silently.
        logger.warning("media kit refresh returned no rows — keeping the old snapshot")
        return {"status": "empty"}

    impressions = sum(int(r.get("impressions") or 0) for r in days)
    clicks = sum(int(r.get("clicks") or 0) for r in days)
    series = sorted(
        ({"d": r.get("date", ""), "i": int(r.get("impressions") or 0),
          "c": int(r.get("clicks") or 0)} for r in days),
        key=lambda r: r["d"])

    pages = pull(["page"])
    sec: dict[str, dict] = {}
    for r in pages:
        key = _section_of(r.get("page", ""))
        if not key:
            continue
        acc = sec.setdefault(key, {"i": 0, "c": 0, "urls": 0})
        acc["i"] += int(r.get("impressions") or 0)
        acc["c"] += int(r.get("clicks") or 0)
        acc["urls"] += 1

    # Share of total, not a raw count, is what these two are for — a brand
    # reads "98% mobile" and changes the creative; it does nothing with 29,412.
    def share(dim: str, top: int) -> list[dict]:
        rows = pull([dim], limit=1000)
        tot = sum(int(r.get("impressions") or 0) for r in rows) or 1
        rows.sort(key=lambda r: int(r.get("impressions") or 0), reverse=True)
        return [{"k": r.get(dim, ""), "pct": round(100.0 * int(r.get("impressions") or 0) / tot, 1)}
                for r in rows[:top]]

    payload = {
        "fetched_on":  date.today().isoformat(),
        "window_days": WINDOW_DAYS,
        "start":       s,
        "end":         e,
        "totals": {
            "impressions": impressions,
            "clicks":      clicks,
            # Recomputed from the totals rather than averaging GSC's per-day
            # ctr column — averaging a ratio across days of unequal size is
            # wrong, and on a page a sponsor may audit, visibly wrong.
            "ctr":         round(100.0 * clicks / impressions, 2) if impressions else 0.0,
            "urls":        len(pages),
            "per_day":     round(impressions / WINDOW_DAYS),
        },
        "series":   series,
        "sections": sec,
        "devices":  share("device", 4),
        "countries": share("country", 5),
    }

    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        # Write-then-rename: a reader arriving mid-write would otherwise get a
        # truncated document and log it as corruption.
        tmp = CACHE_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        tmp.replace(CACHE_FILE)
    except Exception as ex:
        logger.warning("media kit snapshot not written: %s", ex)
        return {"status": "error", "reason": str(ex)[:200]}

    invalidate()
    logger.info("📣 media kit refreshed | %s impressions, %s clicks | %s..%s",
                impressions, clicks, s, e)
    return {"status": "ok", "impressions": impressions, "clicks": clicks,
            "start": s, "end": e}
