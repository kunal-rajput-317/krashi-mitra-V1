# ============================================================
# services/ganna_mill_service.py
# कृषि मित्र — the sugar-mill directory behind /ganna's district pages.
#
# There is no free national mill directory. data.gov.in has nothing below the
# state level, OpenStreetMap has twelve named sugar mills in the whole country,
# and ISMA's 642-mill Atlas is a paid publication. What does exist is one state
# register at a time, each in its own shape, so this grows one adapter per
# state rather than one clever generic scraper.
#
# Maharashtra is the first: the Sugar Commissionerate publishes its register as
# HTML tables, one per district, at mahasugar.in.
#
# WHAT THIS SOURCE IS, EXACTLY
# ----------------------------
# Every table on that page is headed "सहकारी साखर कारखान्याचे नाव व पत्ता" — it
# is the CO-OPERATIVE register. Maharashtra also has roughly as many purely
# private mills, and they are not on it. Callers must say so; a district page
# that presents this as "the mills near you" is wrong by omission, and the
# farmer it misleads is the one whose mill is missing.
#
# The page's own numbers do not reconcile — the headline says 208 factories,
# the region tabs sum to 224, and the tables hold 234 rows — so this module
# never publishes a total. It publishes the rows it can actually validate and
# lets the caller count those.
#
# TWO PARSING TRAPS, both found the hard way:
#   * The HTML carries commented-out rows. Left in, Solapur came out with 68
#     mills instead of 50, eighteen of them invisible on the real page. Comments
#     are stripped before anything else.
#   * Row width is not constant — 184 rows have 17 cells, 50 have 18. Only the
#     leading columns (serial, name, registration, capacity) are reliably
#     positioned, so only those are read. The ownership/status columns further
#     right shift between districts and are deliberately NOT extracted; a
#     mis-shifted column would print "closed" against a running mill.
#
# Fetching is never done from a request path. The cache on disk is the only
# thing a page reads, and a missing cache makes the district pages 302 to the
# state page rather than render an empty list — the same call village_service
# makes for a district whose village cache has not landed.
# ============================================================

import html
import json
import logging
import re
import time
from pathlib import Path

import requests

log = logging.getLogger(__name__)

SOURCE_URL = "https://mahasugar.in/sugar-factories-en.php"
SOURCE_NAME = "साखर आयुक्तालय, महाराष्ट्र"

_CACHE = Path(__file__).resolve().parents[2] / "cache" / "ganna_mills_maharashtra.json"
_MAX_AGE = 30 * 24 * 3600          # cane registers change at most once a season

# mahasugar.in 406s a bare curl; it wants a browser-shaped request.
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,mr;q=0.8",
    "Referer": "https://mahasugar.in/index-en.php",
}

# The register writes districts in Marathi. Devanagari reads fine to a Hindi
# speaker so the display name is kept verbatim; only the URL slug is mapped.
# Renamed districts keep the register's own spelling as the label and the
# familiar name in the slug, so an old bookmark and a new one land together.
_DISTRICTS = {
    "कोल्हापूर": "kolhapur", "रत्नागिरी": "ratnagiri", "सांगली": "sangli",
    "पुणे": "pune", "सातारा": "satara", "सोलापूर": "solapur",
    "उस्मानाबाद": "osmanabad", "अहिल्यानगर": "ahilyanagar", "नाशिक": "nashik",
    "छ. संभाजीनगर": "chhatrapati-sambhajinagar", "जालना": "jalna", "बीड": "beed",
    "धुळे": "dhule", "नंदुरबार": "nandurbar", "जळगांव": "jalgaon",
    "नांदेड": "nanded", "हिंगोली": "hingoli", "परभणी": "parbhani",
    "लातूर": "latur", "अमरावती": "amravati", "बुलढाणा": "buldhana",
    "अकोला": "akola", "यवतमाळ": "yavatmal", "नागपूर": "nagpur",
    "भंडारा": "bhandara", "वर्धा": "wardha",
}

_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S)
_DIST_H = re.compile(r"(<h3[^>]*>\s*[^<]*?जिल्हा[^<]*?</h3>)")


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def _cells(row: str) -> list[str]:
    return [_text(c) for c in _CELL.findall(row)]


def parse(page: str) -> tuple[list[dict], list[str]]:
    """(mills, rejects). Rejects are kept so a source change is visible in the
    logs instead of silently shrinking the directory."""
    # Strip comments FIRST — see the header note about Solapur's phantom rows.
    page = re.sub(r"<!--.*?-->", "", page, flags=re.S)
    mills, rejects = [], []

    parts = _DIST_H.split(page)
    for i in range(1, len(parts), 2):
        label = _text(parts[i]).replace("जिल्हा", "").replace(":-", "").strip()
        slug = _DISTRICTS.get(label)
        if not slug:
            rejects.append(f"unknown district heading: {label!r}")
            continue
        # Only the first table after the heading belongs to this district.
        table = parts[i + 1].split("</table>")[0]
        for row in _ROW.findall(table):
            c = _cells(row)
            if len(c) < 4 or not re.fullmatch(r"\d+", c[0] or ""):
                continue                       # header rows, spacers
            name, tcd_raw = c[1], c[3]
            tcd = int(tcd_raw.replace(",", "")) if re.fullmatch(r"[\d,]+", tcd_raw or "") else 0
            if len(name) < 8:
                rejects.append(f"{slug}: implausible name {name!r}")
                continue
            mills.append({
                "slug": _mill_slug(name, slug),
                "name": name,
                "district": label,
                "district_slug": slug,
                "tcd": tcd,
                "registered": c[2] if re.fullmatch(r"[\d\-/]{6,12}", c[2] or "") else "",
            })

    # A mill name repeated inside one district means the page grew a second
    # table we merged by accident — refuse rather than publish duplicates.
    seen, unique = set(), []
    for m in mills:
        key = (m["district_slug"], m["slug"])
        if key in seen:
            rejects.append(f"duplicate {key}")
            continue
        seen.add(key)
        unique.append(m)
    return unique, rejects


def _mill_slug(name: str, district_slug: str) -> str:
    """A stable, URL-safe id for a Devanagari mill name.

    The names are Marathi, so there is no ASCII to slugify. Transliterating
    would invent spellings that no farmer searches and that change if the
    transliteration table changes; a short hash of the name is stable, opaque
    and honest about being an id. Prefixed with the district so a URL still
    reads as a place."""
    import hashlib
    h = hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]
    return f"{district_slug}-{h}"


def refresh(force: bool = False) -> dict:
    """Fetch, parse and cache. Returns the payload. Never called from a request
    path — the scheduler and the seeding script are the only callers."""
    if not force and fresh():
        return load()
    log.info("[ganna-mills] fetching %s", SOURCE_URL)
    r = requests.get(SOURCE_URL, headers=_HEADERS, timeout=45)
    r.raise_for_status()
    mills, rejects = parse(r.text)
    if len(mills) < 150:
        # The register has ~230 rows. A sudden collapse means the markup moved,
        # and half a directory is worse than yesterday's whole one.
        raise ValueError(f"only {len(mills)} mills parsed — refusing to overwrite cache")
    payload = {
        "state": "maharashtra",
        "scope": "cooperative",
        "source": SOURCE_NAME,
        "source_url": SOURCE_URL,
        "fetched": time.strftime("%Y-%m-%d"),
        "mills": mills,
    }
    _CACHE.parent.mkdir(parents=True, exist_ok=True)
    _CACHE.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    log.info("[ganna-mills] cached %d mills, %d rejects", len(mills), len(rejects))
    for msg in rejects[:10]:
        log.warning("[ganna-mills] reject: %s", msg)
    return payload


def fresh() -> bool:
    try:
        return (time.time() - _CACHE.stat().st_mtime) < _MAX_AGE
    except OSError:
        return False


_mem: dict = {"mtime": None, "data": None}


def load() -> dict:
    """Cached payload, or {} when nothing has landed yet. Re-reads only when the
    file changes, so a page hit costs a stat() rather than a JSON parse."""
    try:
        mtime = _CACHE.stat().st_mtime
    except OSError:
        return {}
    if _mem["mtime"] != mtime:
        try:
            _mem["data"] = json.loads(_CACHE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        _mem["mtime"] = mtime
    return _mem["data"] or {}


def by_district(state_slug: str) -> dict[str, list[dict]]:
    """{district_slug: [mill, ...]} for a state, biggest mill first."""
    data = load()
    if not data or data.get("state") != state_slug:
        return {}
    out: dict[str, list[dict]] = {}
    for m in data.get("mills", []):
        out.setdefault(m["district_slug"], []).append(m)
    for mills in out.values():
        mills.sort(key=lambda m: (-m["tcd"], m["name"]))
    return out


def meta(state_slug: str) -> dict:
    data = load()
    return data if data.get("state") == state_slug else {}
