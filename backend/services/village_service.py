# ============================================================
# services/village_service.py
# गांव-स्तर का डेटा — हर जिले के गांव/कस्बे, OpenStreetMap से, अपने-आप।
#
# Why this exists: /naksha stopped at the जिला. The queries farmers and students
# actually type are one level below that ("मवाना गांव का नक्शा", "सरधना
# सैटेलाइट व्यू"), and a client-side Nominatim box answers them without ever
# minting a URL — so none of it was crawlable.
#
# Where the data comes from: Overpass (OpenStreetMap) `place=village|town|city`
# nodes inside the district's own polygon. The polygon is the one already on
# disk in frontend/data/*.geojson (the same file the interactive map draws), so
# a village is only claimed for a district if it geometrically falls in it —
# no name-matching against OSM's admin boundaries, which for Indian districts
# are inconsistent and frequently stale.
#
# How it stays automatic (see the standing rule: no manual regen steps): the
# first request for a district's गांव page queues that district; a single
# background worker drains the queue one district at a time and writes
# backend/data/villages/<state>--<district>.json. Nothing here ever runs on the
# request path — an Overpass round-trip is 5–40s. The cache is disposable: on a
# fresh deploy the directory is empty and refills itself from real traffic.
#
# The one hard rule: a district with no cache yet renders a search-only page
# that is noindex. We never publish a village URL we cannot back with a real
# coordinate.
# ============================================================

from __future__ import annotations

import json
import logging
import re
import threading
import time
import unicodedata
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

_BASE = Path(__file__).resolve().parents[1]
CACHE_DIR = _BASE / "data" / "villages"
_GEOJSON_DIR = _BASE.parent / "frontend" / "data"

# Mirrors, tried in order. Overpass instances go down or rate-limit
# individually; a district that fails on all of them is retried on the next
# page view rather than being marked permanently dead.
_MIRRORS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.osm.ch/api/interpreter",
)

_UA = "KrashiMitra/1.0 (+https://krashimitra.in; village map pages)"

# place=hamlet is deliberately excluded: it roughly triples the row count while
# adding the least-searched, least-verifiable names, and a 4,000-link directory
# page is worse for both farmers and crawlers than a 900-link one.
_PLACES = "city|town|village"

# Per district. Sorted by settlement rank first, so if a district really does
# exceed this the names that get dropped are the smallest ones.
MAX_VILLAGES = 900

_GAP_SECONDS = 6.0      # between Overpass calls, per their usage policy
_TIMEOUT = 120

_queue: list[tuple[str, str]] = []
_queued: set[tuple[str, str]] = set()
_lock = threading.Lock()
# An explicit flag, not _worker.is_alive(): a thread that has just decided the
# queue is empty is still "alive" for a moment afterwards, and an enqueue
# landing in that window would see a live worker, skip starting one, and strand
# the item forever. The flag is only ever set and cleared under _lock, in the
# same critical sections that decide to exit and to enqueue.
_running = False


# ── slugs ───────────────────────────────────────────────────────────────────

def slugify(name: str) -> str:
    """URL slug from a Latin or Devanagari name.

    Devanagari has no useful ASCII fold, so a name that slugs to nothing keeps
    its own script (FastAPI and every browser handle percent-encoded UTF-8
    paths fine, and a Hindi-script URL is what the Hindi query matches anyway).
    """
    ascii_ = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "-", ascii_.lower()).strip("-")
    if s:
        return s
    return re.sub(r"[\s/]+", "-", name.strip()).strip("-")


# ── cache ───────────────────────────────────────────────────────────────────

def _path(state_key: str, dslug: str) -> Path:
    return CACHE_DIR / f"{state_key}--{dslug}.json"


def load(state_key: str, dslug: str) -> list[dict] | None:
    """Cached villages, or None if this district has never been fetched."""
    p = _path(state_key, dslug)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))["villages"]
    except Exception:
        return None


def cached_districts() -> list[tuple[str, str]]:
    """(state_key, district_slug) for every district with data on disk —
    the sitemap's source of truth for which village URLs actually exist."""
    if not CACHE_DIR.is_dir():
        return []
    out = []
    for p in sorted(CACHE_DIR.glob("*--*.json")):
        state, _, dslug = p.stem.partition("--")
        if state and dslug:
            out.append((state, dslug))
    return out


# ── geometry ────────────────────────────────────────────────────────────────

def _rings(geom: dict) -> list:
    if geom["type"] == "Polygon":
        return geom["coordinates"]
    if geom["type"] == "MultiPolygon":
        return [r for poly in geom["coordinates"] for r in poly]
    return []


def _bbox(rings: list) -> tuple[float, float, float, float]:
    xs = [c[0] for r in rings for c in r]
    ys = [c[1] for r in rings for c in r]
    return min(ys), min(xs), max(ys), max(xs)   # south, west, north, east


def _inside(lat: float, lon: float, rings: list) -> bool:
    """Even-odd ray casting across every ring at once — holes fall out of the
    parity rule for free, so an enclave inside a district is correctly excluded."""
    hit = False
    for ring in rings:
        n = len(ring)
        j = n - 1
        for i in range(n):
            xi, yi = ring[i][0], ring[i][1]
            xj, yj = ring[j][0], ring[j][1]
            if (yi > lat) != (yj > lat):
                if lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
                    hit = not hit
            j = i
    return hit


def _norm(s: str) -> str:
    """Fold spelling noise only — NOT the script. An earlier `[^a-z0-9]` strip
    collapsed every Devanagari name to "", so the first feature with a Hindi
    name matched every district and Meerut was served Amroha's polygon."""
    return re.sub(r"[\s._'’\-/()]+", "", (s or "").strip().lower())


def _district_rings(geojson_name: str, en: str, hi: str) -> list | None:
    f = _GEOJSON_DIR / geojson_name
    if not f.is_file():
        return None
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return None
    want_en, want_hi = _norm(en), _norm(hi)
    for feat in data.get("features", []):
        p = feat.get("properties") or {}
        got_en, got_hi = _norm(p.get("district", "")), _norm(p.get("district_hi", ""))
        if (want_en and got_en == want_en) or (want_hi and got_hi == want_hi):
            return _rings(feat.get("geometry") or {})
    return None


# ── fetch ───────────────────────────────────────────────────────────────────

_RANK = {"city": 0, "town": 1, "village": 2}


def _overpass(south: float, west: float, north: float, east: float) -> list[dict]:
    q = (f'[out:json][timeout:90];'
         f'node["place"~"^({_PLACES})$"]({south},{west},{north},{east});'
         f'out body;')
    for url in _MIRRORS:
        try:
            r = requests.post(url, data={"data": q},
                              headers={"User-Agent": _UA}, timeout=_TIMEOUT)
            if r.status_code != 200:
                logger.debug(f"overpass {url} → {r.status_code}")
                continue
            return r.json().get("elements", [])
        except Exception as e:
            logger.debug(f"overpass {url} failed: {e}")
    return []


def build(state_key: str, dslug: str, meta: dict) -> dict:
    """Fetch + clip + persist one district. `meta` carries the state's geojson
    filename and the district's own hi/en names."""
    started = time.time()
    rings = _district_rings(meta["geojson"], meta["en"], meta["hi"])
    if not rings:
        logger.info(f"🏘️ no polygon for {dslug} in {meta['geojson']}")
        return {"ok": False, "reason": "no-polygon"}

    south, west, north, east = _bbox(rings)
    elements = _overpass(south, west, north, east)
    if not elements:
        return {"ok": False, "reason": "overpass-empty"}

    seen: set[str] = set()
    rows: list[dict] = []
    for el in elements:
        name = (el.get("tags") or {}).get("name")
        lat, lon = el.get("lat"), el.get("lon")
        if not name or lat is None or lon is None:
            continue
        if not _inside(lat, lon, rings):
            continue
        slug = slugify(name)
        if not slug or slug in seen:
            continue
        seen.add(slug)
        tags = el["tags"]
        rows.append({
            "name": name,
            "hi": tags.get("name:hi") or "",
            "slug": slug,
            "lat": round(lat, 5),
            "lon": round(lon, 5),
            "place": tags.get("place", "village"),
        })

    rows.sort(key=lambda v: (_RANK.get(v["place"], 3), v["name"].lower()))
    rows = rows[:MAX_VILLAGES]

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _path(state_key, dslug).write_text(
        json.dumps({"state": state_key, "district": dslug,
                    "built": time.strftime("%Y-%m-%d"), "villages": rows},
                   ensure_ascii=False),
        encoding="utf-8")
    logger.info(f"🏘️ {state_key}/{dslug}: {len(rows)} villages "
                f"({time.time() - started:.1f}s)")
    return {"ok": True, "villages": len(rows)}


# ── queue ───────────────────────────────────────────────────────────────────

def request(state_key: str, dslug: str, meta: dict) -> None:
    """Register interest in a district. Idempotent, never raises, returns at
    once — the page that called it renders without waiting."""
    key = (state_key, dslug)
    with _lock:
        if key in _queued or _path(*key).is_file():
            return
        _queued.add(key)
        _queue.append(key)
        _META[key] = meta
        _start()


_META: dict[tuple[str, str], dict] = {}


def _start() -> None:
    """Caller must hold _lock."""
    global _running
    if _running:
        return
    _running = True
    threading.Thread(target=_drain, name="village-fetch", daemon=True).start()


def _drain() -> None:
    global _running
    while True:
        with _lock:
            if not _queue:
                _running = False        # cleared under the same lock an
                return                  # enqueue must take to start us again
            key = _queue.pop(0)
            meta = _META.pop(key, None)
        try:
            if meta:
                build(key[0], key[1], meta)
        except Exception as e:
            # A district that fails every mirror simply has no file, so the next
            # view of its page re-queues it. Nothing to mark, nothing to reset.
            logger.warning(f"village build failed for {key}: {e}")
        finally:
            with _lock:
                _queued.discard(key)
        time.sleep(_GAP_SECONDS)
