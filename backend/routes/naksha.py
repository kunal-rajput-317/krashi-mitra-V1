# ============================================================
# routes/naksha.py
# कृषि मित्र — the नक्शा cluster, server-rendered like /bhav
#
#   GET /naksha                              hub — every state/UT, by region
#   GET /naksha/{state}                      the state's map + HD download
#   GET /naksha/{state}/jile                 the state's district list
#   GET /naksha/{state}/{district}           one district's map (tier 3)
#   GET /naksha/{state}/{district}/gaon      that district's village directory
#   GET /naksha/{state}/{district}/gaon/{v}  one village's satellite map (tier 5)
#   GET /map                                 उत्तर प्रदेश's page, at its old URL
#
# Tiers 3–5 were added because the cluster used to stop at the राज्य: every
# district "link" on a state or जिले page was really `?district=…` on the same
# URL, and villages existed only inside a client-side Nominatim box. Both are
# invisible to a crawler, so the entire long tail — which is most of the actual
# search demand ("मेरठ का नक्शा", "मवाना गांव सैटेलाइट") — had nowhere to land.
# Those same links now point at real URLs; the internal linking was already
# there, it just had nothing on the other end.
#
# Village data is real or the page does not claim to be one: coordinates come
# from services/village_service.py (OpenStreetMap, clipped to the district's own
# polygon, cached on disk, filled in the background). A district whose cache has
# not landed yet renders a search-only page marked noindex, and its village URLs
# 302 to the district — never a fabricated place page.
#
# Why a route and not files: 36 states × 2 page types = 72 built HTML files,
# each a 1,200-line copy of the same shell. That is the problem /bhav already
# solved — one route, one template, data on disk — so this reuses /bhav's actual
# shell (_doc/_header/_footer) rather than a lookalike. A state added to
# make_state_maps.py appears here the moment make_naksha_data.py rewrites
# backend/data/naksha_states.json; nothing here is per-state.
#
# The data is precomputed, never derived per request: parsing 36 geojson files
# (up to 200 KB each) to count districts on every hit would make these the
# slowest pages on the site. The browser still fetches the geojson for the
# interactive map — that is the one thing that has to be the real boundaries.
#
# /map is UP's page under its original URL: it is linked from every page's
# utility bar and carries the cluster's search history, so it stays put and
# /naksha/uttar-pradesh redirects to it.
# ============================================================

import json
import math
import re
import time
from datetime import date, datetime
from html import escape
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

from backend.routes.bhav import (
    SITE, _asset, _crumb_ld, _doc, _faq, _fit, _ld,
)
from backend.services import village_service
from backend.services.village_service import slugify

router = APIRouter()

_DATA = Path(__file__).resolve().parents[1] / "data" / "naksha_states.json"
_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"

_MONTHS_HI = ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून",
              "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"]

# The states a farmer is most likely to want next, used to fill the "other
# states" row once same-region neighbours run out. Ordered by farming
# population, not alphabetically.
_POPULAR = ["uttar-pradesh", "madhya-pradesh", "maharashtra", "rajasthan",
            "bihar", "punjab", "haryana", "gujarat", "karnataka", "west-bengal"]

_REGION_ORDER = ["उत्तर भारत", "मध्य भारत", "पूर्वी भारत", "पश्चिमी भारत",
                 "दक्षिण भारत", "पूर्वोत्तर भारत"]

# Official State Land Records (भूलेख / खसरा-खतौनी) Portals
_BHULEKH = {
    "uttar-pradesh": ("https://upbhulekh.gov.in/", "UP भूलेख (खसरा-खतौनी)"),
    "madhya-pradesh": ("https://mpbhulekh.gov.in/", "MP भूलेख पोर्टल"),
    "rajasthan": ("https://apnakhata.rajasthan.gov.in/", "अपना खाता (राजस्थान)"),
    "bihar": ("http://biharbhumi.bihar.gov.in/", "बिहार भूमि पोर्टल"),
    "haryana": ("https://jamabandi.nic.in/", "जमाबंदी हरियाणा"),
    "punjab": ("https://plrs.org.in/", "PLRS पंजाब"),
    "gujarat": ("https://anyror.gujarat.gov.in/", "AnyRoR गुजरात"),
    "maharashtra": ("https://bhulekh.mahabhumi.gov.in/", "महाभूमि महाराष्ट्र"),
    "chhattisgarh": ("https://bhuiyan.cg.nic.in/", "भुइयां छत्तीसगढ़"),
    "jharkhand": ("https://jharbhoomi.jharkhand.gov.in/", "झारभूमि"),
    "uttarakhand": ("https://bhulekh.uk.gov.in/", "देवभूमि भूलेख UK"),
    "himachal-pradesh": ("https://himachal.nic.in/", "हिमभूमि HP"),
    "odisha": ("http://bhulekh.ori.nic.in/", "ओडिशा भूलेख"),
    "west-bengal": ("https://banglarbhumi.gov.in/", "बांगलार भूमि WB"),
    "andhra-pradesh": ("https://meebhoomi.ap.gov.in/", "MeeBhoomi AP"),
    "telangana": ("https://dharani.telangana.gov.in/", "धरणी पोर्टल TG"),
    "karnataka": ("https://landrecords.karnataka.gov.in/service2/", "Bhoomi कर्नाटक"),
    "tamil-nadu": ("https://eservices.tn.gov.in/eservicesnew/land/chitta.html", "Patta Chitta TN"),
}


# The abbreviation a searcher actually types. "mp map" earned 2,708 impressions
# in the 28 days to 9 Sep 2026 at position 5.2 and took FOUR clicks (0.15%) —
# the single worst title/query mismatch on the site — because the title said
# "Madhya Pradesh Map" and Google had nothing of what the reader typed to bold.
# Across all of /naksha the abbreviation queries were 4,524 impressions for MP
# and 2,900 for UP. Only states whose short form is genuinely used as a name
# are listed: the rest ("br 52 district name") are vehicle-registration
# lookups, a different question that a title cannot answer.
_ABBR = {
    "madhya-pradesh": "MP", "uttar-pradesh": "UP", "andhra-pradesh": "AP",
    "tamil-nadu": "TN", "west-bengal": "WB", "himachal-pradesh": "HP",
    "jammu-and-kashmir": "J&K", "uttarakhand": "UK", "arunachal-pradesh": "AR",
}


# ── data ────────────────────────────────────────────────────────────────────

_cache: dict = {}


def _states() -> dict:
    """The manifest, reloaded only when the file changes on disk.

    mtime-keyed rather than a plain lru_cache so a rebuild during `uvicorn
    --reload` (or a deploy that only ships new data) is picked up without a
    restart, and a hot path never re-reads a 400 KB JSON for nothing.
    """
    mtime = _DATA.stat().st_mtime
    if _cache.get("mtime") != mtime:
        _cache["mtime"] = mtime
        _cache["states"] = json.loads(_DATA.read_text(encoding="utf-8"))["states"]
        _cache["date"] = datetime.fromtimestamp(mtime).date().isoformat()
        # Derived from the manifest, so it has to die with it — a stale slug
        # index would keep serving districts a rebuild has renamed or dropped.
        _cache["didx"] = {}
    return _cache["states"]


def _updated() -> str:
    _states()
    return _cache["date"]


# ── how many districts a state has TODAY ────────────────────────────────────
# The maps are drawn on Census of India boundaries, so s["n"] is the number of
# districts ON THE MAP. Several states have created districts since, and a
# "राजस्थान में कितने जिले हैं" page that answers 33 when the state has had 41
# since Dec 2024 is a wrong answer in the title — the searcher knows it is
# wrong and does not click. backend/data/district_counts.json holds only
# counts checked against two sources; see its _comment.
_COUNTS = Path(__file__).resolve().parents[1] / "data" / "district_counts.json"
_counts_cache: dict = {}


def _district_count(key: str, s: dict) -> tuple:
    """(count, extra, unsure) for one state.

    count  — the number to answer "कितने जिले हैं" with: the checked current
             count, else the map's own count.
    extra  — districts that exist today but are not drawn separately on the
             map, each {hi, en, year}.
    unsure — sources disagree for this state: print no count as a fact.
    """
    try:
        m = _COUNTS.stat().st_mtime
        if _counts_cache.get("mtime") != m:
            _counts_cache["mtime"] = m
            _counts_cache["data"] = json.loads(_COUNTS.read_text(encoding="utf-8"))
        data = _counts_cache["data"]
    except (OSError, ValueError):
        data = {}
    row = (data.get("states") or {}).get(key)
    if row and row.get("count"):
        return int(row["count"]), list(row.get("new") or []), False
    return s["n"], [], key in (data.get("unsure") or [])


def _now_n(key: str, s: dict) -> int:
    """The count a state card or picker shows: today's checked count, else the
    map's. (Where sources disagree that is the map's own, as it always was.)"""
    return _district_count(key, s)[0]


def _extra_html(hi: str, extra: list) -> str:
    """The districts a state has today that its map does not draw on their
    own — named, dated, and said plainly, so the list and the count agree."""
    if not extra:
        return ""
    def row(d: dict) -> str:
        yr = int(d.get("year") or 0)
        made = f" · {yr} में बना" if yr >= 2012 else ""
        return (f'<div class="nk-drow"><span class="nk-num">+</span>'
                f'<span class="nk-dname"><b>{escape(d["hi"])}</b>'
                f'<span class="nk-en">{escape(d["en"])}{made}</span></span></div>')
    items = "".join(row(d) for d in extra)
    return (f'<div class="nk-extra"><h3>ये जिले नक्शे में अलग नहीं दिखते</h3>'
            f'<p class="nk-lede">नक्शा Census of India की जिला-सीमाओं पर बना है। ये जिले उसके '
            f'बाद बने या अलग हुए, इसलिए नक्शे में अपने मूल जिले के भीतर दिखते हैं:</p>'
            f'<div class="nk-dgrid">{items}</div></div>')


def _hindi_date(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{int(d)} {_MONTHS_HI[int(m) - 1]} {y}"


def _url(key: str) -> str:
    """A state's map page."""
    return f"/naksha/{key}"


def _jile_url(key: str) -> str:
    return f"/naksha/{key}/jile"


def _d_url(key: str, dslug: str) -> str:
    """One district's map. Note this is /naksha/uttar-pradesh/meerut even though
    the UP *state* page lives at /map — only the state page kept the legacy URL,
    and giving its districts a second address would split their signals."""
    return f"/naksha/{key}/{dslug}"


def _gaon_url(key: str, dslug: str) -> str:
    return f"/naksha/{key}/{dslug}/gaon"


def _v_url(key: str, dslug: str, vslug: str) -> str:
    return f"/naksha/{key}/{dslug}/gaon/{quote(vslug)}"


def _dindex(key: str) -> dict:
    """slug → district, for one state.

    Built once per manifest load and hung off the same mtime-keyed cache, so a
    rebuilt naksha_states.json invalidates it along with everything else. The
    slug is derived, not stored: it has to agree with village_service's own
    slugify() or a cached file would never be found again."""
    idx = _cache.setdefault("didx", {})
    if key not in idx:
        idx[key] = {slugify(d["en"]): d for d in _states()[key]["districts"]}
    return idx[key]


def _dhi(d: dict) -> str:
    return d["hi"]


def _abs(path: str) -> str:
    """Absolute form of an internal path.

    _url()/_jile_url() are relative because that is what an href wants. Anything
    that leaves the page — canonical, og:url, every schema @id/url/item — has to
    be absolute, or it resolves against whatever host served it (a canonical of
    http://127.0.0.1:8022/… is what caught this)."""
    return path if path.startswith("http") else f"{SITE}{path}"


def _img(s: dict, kind: str) -> str:
    """Site-relative, for markup. It must NOT be the absolute krashimitra.in URL:
    a browser ignores the `download` attribute on a cross-origin link and
    navigates to the file instead — which is exactly what the ?dl=1 landing did
    when the page was served from anywhere but the production host."""
    return f"/images/{s['prefix']}-{kind}"


def _abs_img(s: dict, kind: str) -> str:
    """Absolute, for og:image and schema — those are read off-site."""
    return f"{SITE}/images/{s['prefix']}-{kind}"


def _dl_card(s: dict, title: str, sub: str, alt: str) -> str:
    """The HD-map download card: preview picture, one line, PNG + PDF.

    The PDF button appears only where make_state_maps.py has written the file
    (an A4 page with the same branded map), so a state added before its PDF
    exists never shows a link that 404s."""
    png = _img(s, "district-map.png")
    fname = f"{s['prefix']}-{s['n']}-jile"
    has_pdf = (_FRONTEND / "images" / f"{s['prefix']}-district-map.pdf").is_file()
    pdf_btn = (f'<a class="nk-dl-banner-btn alt" href="{_img(s, "district-map.pdf")}" '
               f'download="{fname}.pdf">📄 PDF</a>' if has_pdf else "")
    return (f'<div class="nk-dl-banner">'
            f'<a class="nk-dl-prev" data-km-map-picker href="{png}" download="{fname}.png" '
            f'aria-label="{escape(title)}">'
            f'<img src="{_img(s, "district-map-800.webp")}" width="{s["w"]}" height="{s["h"]}" '
            f'loading="lazy" decoding="async" alt="{escape(alt)}"></a>'
            f'<div class="nk-dl-banner-info"><h3>{escape(title)}</h3><p>{escape(sub)}</p></div>'
            f'<div class="nk-dl-btns">'
            f'<a class="nk-dl-banner-btn" data-km-map-picker href="{png}" download="{fname}.png">'
            f'⬇️ PNG</a>{pdf_btn}</div></div>')


def _jile(n: int) -> str:
    """"1 जिला" / "22 जिले" — दिल्ली and चंडीगढ़ are single-district UTs, and
    "1 जिले" on their card is the kind of thing that reads as machine output."""
    return f"{n} जिला" if n == 1 else f"{n} जिले"





# ── page furniture ──────────────────────────────────────────────────────────

_NK_CSS = """
/* ── नक्शा cluster: Modern Mobile-First AgTech Styling ───────── */
/* districts that exist today but are not drawn on the Census-boundary map */
.nk-extra{margin-top:18px;padding-top:14px;border-top:1px dashed #d6e2da}
.nk-extra h3{font-size:15px;margin:0 0 4px;color:#14532d}
.nk-extra .nk-lede{margin-bottom:10px}
.nk-extra .nk-num{background:#fff7e0;color:#8a5a00}
:root {
  --nk-font: 'DM Sans', 'Noto Sans Devanagari', -apple-system, BlinkMacSystemFont, sans-serif;
  --nk-bg-gradient: linear-gradient(135deg, #071f16 0%, #0d2f23 45%, #154534 100%);
  --nk-emerald-dark: #071f16;
  --nk-emerald-mid: #134232;
  --nk-emerald-light: #23654f;
  --nk-mint: #52b788;
  --nk-mint-glow: rgba(82, 183, 136, 0.35);
  --nk-gold: #f5b731;
  --nk-gold-light: #fff8e7;
  --nk-gold-glow: rgba(245, 183, 49, 0.38);
  --nk-text-dark: #0f241c;
  --nk-text-mid: #2c4a3e;
  --nk-text-soft: #5b786a;
  --nk-border-glass: rgba(19, 66, 50, 0.12);
  --nk-shadow-sm: 0 2px 8px rgba(7, 31, 22, 0.06);
  --nk-shadow-md: 0 10px 24px -6px rgba(7, 31, 22, 0.12);
  --nk-shadow-lg: 0 20px 40px -12px rgba(7, 31, 22, 0.18);
  --nk-radius-lg: 20px;
  --nk-radius-md: 14px;
  --nk-radius-sm: 10px;
}

.nk-hero, .nk-sec, .nk-card, .nk-tabs-bar, .nk-scard, .nk-drow, .nk-app-map-wrap {
  font-family: var(--nk-font);
  box-sizing: border-box;
}

/* Page heading & top level drilldown */
.nk-title {
  text-align: center;
  font-family: var(--nk-font);
  font-size: 24px;
  font-weight: 800;
  color: #1a56db;
  padding: 16px 12px 2px;
  line-height: 1.3;
}
.nk-title-sub {
  text-align: center;
  font-size: 13.5px;
  color: var(--nk-text-soft);
  font-weight: 600;
  margin: 0 auto 12px;
  max-width: 60ch;
  padding: 0 12px;
}

.nk-level-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  background: rgba(19, 66, 50, 0.05);
  border: 1px solid var(--nk-border-glass);
  border-radius: var(--nk-radius-sm);
  margin: 8px 0 12px;
  font-size: 13px;
  font-weight: 700;
  overflow-x: auto;
  white-space: nowrap;
  box-sizing: border-box;
  max-width: 100%;
}
.nk-level-bar a {
  color: var(--nk-emerald-dark);
  text-decoration: none;
  padding: 2px 6px;
  border-radius: 6px;
}
.nk-level-bar a:hover { background: rgba(82, 183, 136, 0.15); }
.nk-lvl-sep { color: var(--nk-text-soft); opacity: 0.5; font-size: 11px; }

/* Tabs Bar */
.nk-tabs-bar {
  display: flex;
  gap: 8px;
  background: rgba(19, 66, 50, 0.06);
  padding: 4px;
  border-radius: var(--nk-radius-md);
  margin-bottom: 14px;
  border: 1px solid var(--nk-border-glass);
  overflow-x: auto;
  box-sizing: border-box;
  max-width: 100%;
}
.nk-tab-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 9px 16px;
  border-radius: 10px;
  font-size: 13.5px;
  font-weight: 700;
  color: var(--nk-text-mid);
  text-decoration: none;
  white-space: nowrap;
  transition: all 0.2s ease;
}
.nk-tab-item:hover, .nk-tab-item.active {
  background: #ffffff;
  color: var(--nk-emerald-dark);
  box-shadow: var(--nk-shadow-sm);
}

/* ── App Map Wrapper & Controls ── */
.nk-app-map-wrap {
  position: relative;
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
  border-radius: var(--nk-radius-lg);
  overflow: hidden;
  box-shadow: var(--nk-shadow-lg);
  border: 1.5px solid var(--nk-border-glass);
  background: #0d2f23;
  isolation: isolate;
  z-index: 10;
  scroll-margin-top: 155px;
}
#nk-map-wrap {
  scroll-margin-top: 155px;
}
.nk-app-map-wrap.is-fullscreen {
  position: fixed !important;
  inset: 0 !important;
  width: 100vw !important;
  height: 100vh !important;
  z-index: 999999 !important;
  border-radius: 0 !important;
  border: none !important;
  margin: 0 !important;
}

.nk-map {
  width: 100%;
  height: 58vh;
  min-height: 400px;
  max-height: 580px;
  background: #112d22;
}
@media (max-width: 600px) {
  .nk-map {
    height: 55vh;
    min-height: 380px;
    max-height: 480px;
  }
}
.nk-app-map-wrap.is-fullscreen .nk-map {
  height: 100vh !important;
  max-height: none !important;
  min-height: 100vh !important;
}

/* Floating Search Bar */
.nk-float-search {
  position: absolute;
  top: 12px;
  left: 12px;
  right: 58px;  /* leave room for the top-right button */
  max-width: 440px;
  z-index: 1000;
  display: flex;
  flex-direction: column;
  gap: 6px;
  box-sizing: border-box;
}
.nk-search-pill-box {
  display: flex;
  align-items: center;
  gap: 6px;
  background: rgba(255, 255, 255, 0.96);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  border: 1.5px solid rgba(19, 66, 50, 0.2);
  border-radius: 999px;
  padding: 4px 6px 4px 12px;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.22);
  transition: all 0.25s ease;
  min-width: 0;
  box-sizing: border-box;
}
.nk-search-pill-box:focus-within {
  background: #ffffff;
  border-color: var(--nk-mint);
  box-shadow: 0 10px 30px rgba(82, 183, 136, 0.35);
}
.nk-search-ic {
  font-size: 15px;
  color: var(--nk-emerald-mid);
  opacity: 0.85;
  flex-shrink: 0;
}
.nk-search-input {
  flex: 1;
  min-width: 0;
  border: none;
  background: transparent;
  font-size: 13.5px;
  font-weight: 700;
  color: var(--nk-text-dark);
  outline: none;
  font-family: inherit;
  padding: 4px 0;
}
.nk-search-input::placeholder {
  color: #7b9487;
  font-weight: 500;
}
.nk-search-clear-btn {
  display: none;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  border: none;
  background: #eef3f0;
  color: #4b6357;
  font-size: 11px;
  cursor: pointer;
  flex-shrink: 0;
}
.nk-search-clear-btn.visible { display: flex; }
.nk-search-loc-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(37, 99, 235, 0.09);
  border: 1.5px solid rgba(37, 99, 235, 0.28);
  color: #1d4ed8;
  font-size: 12px;
  font-weight: 800;
  cursor: pointer;
  white-space: nowrap;
  flex-shrink: 0;
  transition: all 0.2s ease;
}
.nk-search-loc-btn .nk-loc-text { display: none; }
@media (min-width: 540px) {
  .nk-search-loc-btn .nk-loc-text { display: inline; }
  .nk-search-loc-btn { padding: 6px 12px; }
}
.nk-search-loc-btn:hover, .nk-search-loc-btn:active, .nk-search-loc-btn.active {
  background: #2563eb;
  color: #ffffff;
  border-color: #2563eb;
  box-shadow: 0 4px 14px rgba(37, 99, 235, 0.38);
}
.nk-search-loc-btn.loading {
  pointer-events: none;
  background: #2563eb;
  color: #ffffff;
  border-color: #2563eb;
}
.nk-search-loc-btn.loading .nk-loc-icon {
  display: inline-block;
  animation: nkSpin 0.9s linear infinite;
}
@keyframes nkSpin {
  from { transform: rotate(0deg); }
  to   { transform: rotate(360deg); }
}
/* GPS FAB option loading state */
.nk-fab-opt.loading {
  pointer-events: none;
  background: var(--nk-emerald-dark);
  color: #ffffff;
}
.nk-fab-opt.loading .nk-fab-opt-ic {
  animation: nkSpin 0.9s linear infinite;
  background: rgba(255,255,255,0.18);
}
.nk-search-btn {
  padding: 7px 13px;
  border-radius: 999px;
  background: linear-gradient(135deg, #f5b731 0%, #e9a825 100%);
  color: #071f16;
  border: none;
  font-size: 12px;
  font-weight: 800;
  cursor: pointer;
  flex-shrink: 0;
  box-shadow: 0 2px 8px rgba(245, 183, 49, 0.35);
  transition: all 0.2s ease;
}
.nk-search-btn:hover { transform: scale(1.04); }

/* Instant Suggestions Dropdown */
.nk-suggestions-list {
  display: none;
  background: #ffffff;
  border-radius: 14px;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.22);
  border: 1px solid var(--nk-border-glass);
  max-height: 240px;
  overflow-y: auto;
  padding: 6px 0;
}
.nk-suggestions-list.active { display: block; }
.nk-sugg-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  font-size: 13.5px;
  font-weight: 700;
  color: var(--nk-text-dark);
  cursor: pointer;
  border-bottom: 1px solid #f2f7f4;
  transition: background 0.15s ease;
}
.nk-sugg-item:last-child { border-bottom: none; }
.nk-sugg-item:hover, .nk-sugg-item.focused {
  background: #eef8f2;
  color: var(--nk-emerald-dark);
}
.nk-sugg-item small {
  margin-left: auto;
  color: var(--nk-text-soft);
  font-size: 11.5px;
  font-weight: 600;
}

/* Quick Actions & Mandi Toggle */
.nk-search-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 2px;
}
.nk-mandi-toggle-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px 5px 10px;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1.5px solid rgba(19, 66, 50, 0.22);
  border-radius: 999px;
  color: var(--nk-emerald-dark);
  font-family: var(--nk-font);
  font-size: 12.5px;
  font-weight: 700;
  cursor: pointer;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.16);
  transition: all 0.2s cubic-bezier(0.34, 1.56, 0.64, 1);
  outline: none;
}
.nk-mandi-toggle-btn:hover {
  background: #ffffff;
  border-color: var(--nk-mint);
  transform: translateY(-1px) scale(1.03);
  box-shadow: 0 6px 18px rgba(82, 183, 136, 0.3);
}
.nk-mandi-toggle-btn.active {
  background: linear-gradient(135deg, #071f16 0%, #154534 100%);
  color: #f5b731;
  border-color: #f5b731;
  box-shadow: 0 6px 20px rgba(245, 183, 49, 0.35);
}
.nk-mandi-btn-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: #f5b731;
  color: #071f16;
  font-size: 11px;
  font-weight: 800;
  padding: 1px 6px;
  border-radius: 999px;
  margin-left: 2px;
}
.nk-mandi-toggle-btn.active .nk-mandi-btn-badge {
  background: #ffffff;
  color: #071f16;
}
.nk-mandi-toggle-btn.loading {
  opacity: 0.8;
  cursor: wait;
}

/* ── Mandi 3-Tier LOD Markers ── */
/* Tier 1: District Mandi Cluster Badge (Zoom < 9) */
.nk-mandi-cluster-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: rgba(7, 31, 22, 0.94);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border: 1.5px solid #52b788;
  border-radius: 999px;
  padding: 4px 10px;
  color: #ffffff;
  font-family: var(--nk-font);
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.45);
  cursor: pointer;
  transition: transform 0.16s ease, border-color 0.16s ease, background 0.16s ease;
  user-select: none;
}
.nk-mandi-cluster-badge:hover {
  transform: scale(1.1);
  border-color: #f5b731;
  background: #0d3827;
  z-index: 1000 !important;
}
.nk-cluster-ic {
  font-size: 13px;
  line-height: 1;
}
.nk-cluster-name {
  color: #e8f5e9;
  letter-spacing: 0.2px;
}
.nk-cluster-count {
  background: #f5b731;
  color: #1e1302;
  font-size: 11px;
  font-weight: 800;
  padding: 1px 7px;
  border-radius: 999px;
  line-height: 1.3;
}

/* Tier 2: Compact Mandi Badge (Zoom 9-11) */
.nk-mandi-compact-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  background: rgba(14, 61, 38, 0.95);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  border: 1.5px solid rgba(82, 183, 136, 0.75);
  border-radius: 999px;
  padding: 3px 9px;
  color: #d8f3dc;
  font-family: var(--nk-font);
  font-size: 11.5px;
  font-weight: 700;
  white-space: nowrap;
  box-shadow: 0 3px 12px rgba(0, 0, 0, 0.35);
  cursor: pointer;
  transition: transform 0.15s ease, background 0.15s ease;
  user-select: none;
}
.nk-mandi-compact-badge:hover {
  transform: scale(1.08);
  background: #145234;
  border-color: #52b788;
  color: #ffffff;
  z-index: 1000 !important;
}
.nk-compact-ic {
  font-size: 12px;
  line-height: 1;
}

/* Tier 3: Full Detailed Mandi Pin & Card (Zoom >= 12) */
.nk-mandi-marker-wrap {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  cursor: pointer;
  transition: transform 0.18s ease;
}
.nk-mandi-marker-wrap:hover {
  transform: scale(1.08);
  z-index: 1000 !important;
}
.nk-mandi-pin-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: #071f16;
  color: #f5b731;
  padding: 3px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 800;
  white-space: nowrap;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.35);
  border: 1.5px solid #f5b731;
  line-height: 1.2;
}
.nk-mandi-pin-icon-box {
  width: 30px;
  height: 30px;
  background: linear-gradient(135deg, #1b4d3e, #0a261c);
  border: 2px solid #ffffff;
  border-radius: 50% 50% 50% 4px;
  transform: rotate(-45deg);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.3);
  margin-top: 2px;
}
.nk-mandi-pin-icon {
  transform: rotate(45deg);
  font-size: 14px;
  line-height: 1;
}

/* Mandi Popup Card */
.nk-mandi-popup .leaflet-popup-content-wrapper {
  background: #ffffff;
  border-radius: 16px;
  padding: 0;
  overflow: hidden;
  box-shadow: 0 16px 36px rgba(7, 31, 22, 0.28);
  border: 1px solid rgba(19, 66, 50, 0.15);
}
.nk-mandi-popup .leaflet-popup-content {
  margin: 0;
  padding: 0;
  width: 270px !important;
  font-family: var(--nk-font);
}
.nk-mandi-card {
  padding: 14px 16px;
  box-sizing: border-box;
}
.nk-mandi-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  border-bottom: 1px solid #edf3ef;
  padding-bottom: 8px;
  margin-bottom: 10px;
}
.nk-mandi-card-title {
  font-size: 15px;
  font-weight: 800;
  color: #071f16;
  line-height: 1.25;
}
.nk-mandi-card-subtitle {
  font-size: 11.5px;
  color: #5b786a;
  font-weight: 600;
  margin-top: 2px;
}
.nk-mandi-card-tag {
  background: #edf8f3;
  color: #134232;
  font-size: 11px;
  font-weight: 700;
  padding: 2px 7px;
  border-radius: 6px;
  white-space: nowrap;
}
.nk-mandi-crop-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 12px;
}
.nk-mandi-crop-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 8px;
  background: #f7faf8;
  border-radius: 8px;
  font-size: 12px;
}
.nk-mandi-crop-name {
  font-weight: 700;
  color: #1a2e22;
}
.nk-mandi-crop-price {
  font-weight: 800;
  color: #0b5e3a;
  background: #e8f5ed;
  padding: 2px 6px;
  border-radius: 4px;
}
.nk-mandi-card-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-top: 10px;
}
.nk-mandi-card-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 7px 10px;
  border-radius: 8px;
  font-size: 11.5px;
  font-weight: 700;
  text-decoration: none;
  cursor: pointer;
  transition: all 0.15s ease;
  box-sizing: border-box;
}
.nk-mandi-btn-nav {
  background: #eef3fc;
  color: #1a56db;
  border: 1px solid rgba(26, 86, 219, 0.2);
}
.nk-mandi-btn-nav:hover {
  background: #1a56db;
  color: #ffffff;
}
.nk-mandi-btn-bhav {
  background: #071f16;
  color: #ffffff;
  border: 1px solid #071f16;
}
.nk-mandi-btn-bhav:hover {
  background: #134232;
  color: #f5b731;
}

/* ── Top-Right Controls: Fullscreen + Tools Speed-Dial ── */
.nk-fs-btn {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 1001;
  width: 38px;
  height: 38px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1.5px solid rgba(0, 0, 0, 0.12);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: 0 3px 12px rgba(0, 0, 0, 0.18);
  transition: all 0.18s ease;
  outline: none;
  color: #1a2e22;
}
.nk-fs-btn:hover {
  background: var(--nk-emerald-dark);
  color: #ffffff;
  border-color: var(--nk-emerald-dark);
  transform: scale(1.06);
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.26);
}
.nk-fs-btn.active {
  background: var(--nk-emerald-dark);
  color: #ffffff;
  border-color: var(--nk-mint);
}
.nk-fs-icon {
  width: 18px;
  height: 18px;
  display: block;
  pointer-events: none;
}

.nk-fab-menu {
  position: absolute;
  right: 12px;
  top: 56px;
  z-index: 1001;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
}
.nk-fab-main {
  width: 38px;
  height: 38px;
  padding: 0;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.96);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  border: 1.5px solid rgba(0, 0, 0, 0.12);
  color: #1a2e22;
  cursor: pointer;
  box-shadow: 0 3px 12px rgba(0, 0, 0, 0.18);
  transition: all 0.25s cubic-bezier(0.34, 1.56, 0.64, 1);
  outline: none;
  display: flex;
  align-items: center;
  justify-content: center;
}
.nk-fab-main:hover {
  background: var(--nk-emerald-dark);
  color: #ffffff;
  border-color: var(--nk-emerald-dark);
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.24);
  transform: scale(1.06);
}
.nk-fab-main-ic {
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.nk-fab-main-svg {
  width: 20px;
  height: 20px;
  display: block;
}
.nk-fab-main-close { display: none; font-size: 15px; font-weight: 900; }

.nk-fab-menu.open .nk-fab-main {
  background: var(--nk-emerald-dark);
  color: #ffffff;
  border-color: var(--nk-mint);
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.28);
}
.nk-fab-menu.open .nk-fab-main-ic { display: none; }
.nk-fab-menu.open .nk-fab-main-close { display: inline-block; }

/* Sub Options Stack (Roll out when open) */
.nk-fab-options {
  display: none;
  flex-direction: column;
  align-items: flex-end;
  gap: 7px;
  animation: nkFabRoll 0.22s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}
.nk-fab-menu.open .nk-fab-options {
  display: flex;
}
@keyframes nkFabRoll {
  from {
    opacity: 0;
    transform: translateY(8px) scale(0.94);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}
.nk-fab-opt {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 6px 12px 6px 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.96);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  border: 1.5px solid rgba(19, 66, 50, 0.16);
  color: var(--nk-text-dark);
  font-size: 12.5px;
  font-weight: 700;
  cursor: pointer;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.12);
  transition: all 0.18s ease;
  white-space: nowrap;
}
.nk-fab-opt:hover, .nk-fab-opt.active {
  background: var(--nk-emerald-dark);
  color: #ffffff;
  border-color: var(--nk-mint);
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.2);
  transform: translateX(-3px);
}
.nk-fab-opt.off {
  background: rgba(255, 255, 255, 0.88);
  color: #718096;
  border-color: rgba(0, 0, 0, 0.12);
}
.nk-fab-opt-ic {
  font-size: 15px;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: rgba(19, 66, 50, 0.08);
  display: flex;
  align-items: center;
  justify-content: center;
}
.nk-fab-opt:hover .nk-fab-opt-ic, .nk-fab-opt.active .nk-fab-opt-ic {
  background: rgba(255, 255, 255, 0.2);
}

/* ── "रास्ता देखें": in-map route to the nearest mandi ── */
.nk-route-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: rgba(255, 255, 255, 0.96);
  border: 1.5px solid rgba(14, 61, 38, 0.18);
  color: #0e3d26;
  font-family: inherit;
  font-size: 12.5px;
  font-weight: 800;
  padding: 7px 14px;
  border-radius: 999px;
  cursor: pointer;
  box-shadow: 0 3px 12px rgba(0, 0, 0, 0.18);
  transition: all 0.18s ease;
}
.nk-route-btn:hover, .nk-route-btn.active {
  background: #0e3d26;
  color: #ffffff;
  border-color: #0e3d26;
}
.nk-route-btn.loading { pointer-events: none; opacity: 0.85; }
.nk-route-arrow { width: 14px; height: 14px; fill: #2563eb; flex-shrink: 0; }
.nk-route-btn:hover .nk-route-arrow, .nk-route-btn.active .nk-route-arrow { fill: #8ef0b4; }
.nk-route-btn.loading .nk-route-arrow { animation: nkSpin 0.9s linear infinite; }
.nk-route-flow { pointer-events: none; }
.nk-route-flow.is-done { animation: nkRouteFade 0.45s ease-out forwards; }
@keyframes nkRouteFade { from { opacity: 0.95; } to { opacity: 0; } }
.nk-route-panel {
  position: absolute;
  left: 12px;
  top: 104px;
  z-index: 1004;
  width: 296px;
  max-width: calc(100% - 24px);
  box-sizing: border-box;
  background: rgba(7, 31, 22, 0.97);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  border: 1px solid rgba(82, 183, 136, 0.45);
  border-radius: 16px;
  padding: 12px;
  box-shadow: 0 12px 34px rgba(0, 0, 0, 0.5);
  display: none;
  animation: nkRouteSlide 0.2s ease-out;
}
.nk-route-panel.open { display: block; }
@keyframes nkRouteSlide { from { transform: translateX(-12px); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
.nk-rp-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 10px; }
.nk-rp-title { font-size: 13.5px; font-weight: 800; color: #d8f3dc; }
.nk-rp-close { background: rgba(255, 255, 255, 0.1); border: none; color: #a7f3d0; cursor: pointer; border-radius: 8px; padding: 5px 7px; line-height: 1; font-size: 13px; }
.nk-rp-close:hover { background: rgba(255, 255, 255, 0.2); color: #fff; }
.nk-rp-body { display: flex; align-items: stretch; gap: 8px; }
.nk-rp-rail { display: flex; flex-direction: column; align-items: center; padding: 13px 0 15px; }
.nk-rp-rail .nk-rp-dots { flex: 1; width: 0; border-left: 2px dotted rgba(216, 243, 220, 0.45); margin: 4px 0; }
.nk-rp-fields { flex: 1; min-width: 0; }
.nk-rp-swap-btn {
  align-self: center;
  background: rgba(255, 255, 255, 0.08);
  border: none;
  color: #95d5b2;
  cursor: pointer;
  border-radius: 999px;
  width: 30px;
  height: 30px;
  font-size: 14px;
  line-height: 1;
  flex-shrink: 0;
}
.nk-rp-swap-btn:hover { background: rgba(255, 255, 255, 0.18); color: #fff; }
.nk-rp-chip-row { display: flex; align-items: center; gap: 5px; flex-wrap: wrap; margin: 0 0 8px 19px; }
.nk-rp-chip-row .nk-rp-lbl { font-size: 10px; font-weight: 700; color: rgba(216, 243, 220, 0.6); }
.nk-rt-start { width: 15px; height: 15px; border-radius: 50%; background: #4285f4; border: 3px solid #fff; box-shadow: 0 1px 5px rgba(0, 0, 0, 0.5); box-sizing: border-box; }
.nk-rt-dest svg { filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.5)); display: block; }
.nk-rt-alt-label {
  background: #ffffff;
  color: #3c4043;
  font-size: 11px;
  font-weight: 700;
  padding: 3px 8px;
  border-radius: 999px;
  white-space: nowrap;
  box-shadow: 0 1px 6px rgba(0, 0, 0, 0.35);
  cursor: pointer;
  font-family: inherit;
}
.nk-rp-row { display: flex; align-items: center; gap: 8px; margin-bottom: 7px; }
.nk-rp-dot { width: 11px; height: 11px; border-radius: 50%; border: 2.5px solid #60a5fa; flex-shrink: 0; }
.nk-rp-dot.dest { border-radius: 50% 50% 50% 0; transform: rotate(-45deg); border-color: #8ef0b4; background: rgba(142, 240, 180, 0.25); }
.nk-rp-field { flex: 1; min-width: 0; position: relative; }
.nk-rp-input {
  width: 100%;
  box-sizing: border-box;
  background: rgba(255, 255, 255, 0.07);
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 10px;
  padding: 9px 10px;
  color: #ffffff;
  font-family: inherit;
  font-size: 12.5px;
  font-weight: 600;
  outline: none;
}
.nk-rp-input::placeholder { color: rgba(216, 243, 220, 0.5); font-weight: 500; }
.nk-rp-input:focus { border-color: rgba(82, 183, 136, 0.7); background: rgba(255, 255, 255, 0.11); }
.nk-rp-chips { display: flex; flex-wrap: wrap; gap: 5px; margin: 0 0 9px 19px; }
.nk-rp-chip {
  background: rgba(82, 183, 136, 0.16);
  border: 1px solid rgba(82, 183, 136, 0.3);
  color: #b7e4c7;
  font-family: inherit;
  font-size: 10.5px;
  font-weight: 700;
  padding: 4px 8px;
  border-radius: 999px;
  cursor: pointer;
  white-space: nowrap;
}
.nk-rp-chip:hover, .nk-rp-chip.active { background: #52b788; border-color: #52b788; color: #071f16; }
.nk-rp-swap { display: flex; justify-content: flex-end; margin: -3px 0 4px 0; }
.nk-rp-swap button { background: rgba(255, 255, 255, 0.08); border: none; color: #95d5b2; cursor: pointer; border-radius: 8px; padding: 4px 8px; font-size: 12px; line-height: 1; }
.nk-rp-swap button:hover { background: rgba(255, 255, 255, 0.18); color: #fff; }
.nk-rp-go {
  width: 100%;
  background: #2563eb;
  border: none;
  border-radius: 10px;
  color: #fff;
  font-family: inherit;
  font-size: 13px;
  font-weight: 800;
  padding: 10px;
  cursor: pointer;
  margin-top: 3px;
  transition: background 0.15s;
}
.nk-rp-go:hover { background: #1d4ed8; }
.nk-rp-go:disabled { opacity: 0.6; cursor: default; }
.nk-rp-note { font-size: 10.5px; font-weight: 600; color: #95d5b2; margin-top: 7px; line-height: 1.4; min-height: 14px; }
.nk-rp-note.err { color: #fca5a5; }
.nk-rp-sugg {
  position: absolute;
  left: 0;
  right: 0;
  top: calc(100% + 4px);
  background: #0b2b1e;
  border: 1px solid rgba(82, 183, 136, 0.35);
  border-radius: 10px;
  overflow: hidden;
  z-index: 3;
  display: none;
}
.nk-rp-sugg.active { display: block; }
.nk-rp-sugg div { padding: 8px 10px; font-size: 12px; font-weight: 600; color: #d8f3dc; cursor: pointer; }
.nk-rp-sugg div:hover { background: rgba(82, 183, 136, 0.2); color: #fff; }
/* Click-catcher for "map par chunein" — a plain overlay keeps the district and
   measure-tool handlers from firing while a point is being picked. */
.nk-pick-overlay { position: absolute; inset: 0; z-index: 1005; cursor: crosshair; display: none; background: rgba(0, 0, 0, 0.08); }
.nk-pick-overlay.active { display: block; }
.nk-pick-hint {
  position: absolute;
  top: 12px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(7, 31, 22, 0.95);
  border: 1px solid rgba(82, 183, 136, 0.5);
  color: #d8f3dc;
  font-size: 12px;
  font-weight: 700;
  padding: 8px 14px;
  border-radius: 999px;
  white-space: nowrap;
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.45);
}
@media (max-width: 560px) {
  .nk-route-panel { left: 10px; right: 10px; width: auto; top: 96px; padding: 11px; }
  .nk-rp-input { font-size: 12px; padding: 8px 9px; }
}
.nk-route-card {
  position: absolute;
  left: 12px;
  bottom: 16px;
  z-index: 1002;
  max-width: min(340px, calc(100% - 78px));
  box-sizing: border-box;
  background: rgba(7, 31, 22, 0.96);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(82, 183, 136, 0.45);
  border-radius: 14px;
  padding: 9px 12px;
  display: none;
  align-items: center;
  gap: 10px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
  animation: nkRouteUp 0.22s ease-out;
}
.nk-route-card.show { display: flex; }
@keyframes nkRouteUp { from { transform: translateY(14px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
.nk-route-card-info { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 2px; }
.nk-route-card-title { font-size: 12px; font-weight: 700; color: #d8f3dc; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.nk-route-card-title b { color: #ffffff; }
.nk-route-card-meta { font-size: 11.5px; font-weight: 600; color: #95d5b2; }
.nk-route-card-meta b { color: #8ef0b4; font-size: 13px; font-weight: 800; }
.nk-route-nav { display: inline-flex; align-items: center; gap: 4px; background: #2563eb; color: #fff; font-size: 11px; font-weight: 800; padding: 6px 10px; border-radius: 8px; text-decoration: none; white-space: nowrap; flex-shrink: 0; }
.nk-route-nav:hover { background: #1d4ed8; color: #fff; }
.nk-route-close { background: rgba(255, 255, 255, 0.1); border: none; color: #a7f3d0; cursor: pointer; padding: 6px; border-radius: 8px; display: inline-flex; flex-shrink: 0; }
.nk-route-close:hover { background: rgba(255, 255, 255, 0.2); color: #fff; }
/* The drawer is a full-width bottom sheet, so the card steps aside for it. */
.nk-bottom-drawer.active ~ .nk-route-card { display: none; }
@media (max-width: 560px) {
  .nk-route-card { left: 10px; bottom: 24px; max-width: calc(100% - 64px); padding: 8px 10px; gap: 8px; }
  .nk-route-nav { padding: 5px 8px; font-size: 10.5px; }
}

/* ── My Location Button (bottom-right standalone, icon-only) ── */
.nk-my-loc-btn {
  position: absolute;
  /* Sits in the same column as Leaflet's zoom stack, clearing it. That stack
     ends 91px above the wrap's bottom (attribution strip + its own margin),
     so anything under ~100px here lands on top of the + button. */
  bottom: 102px;
  right: 10px;
  z-index: 1001;
  width: 42px;
  height: 42px;
  padding: 0;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.98);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  border: 2px solid #2563eb;
  color: #1d4ed8;
  cursor: pointer;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
  transition: all 0.22s cubic-bezier(0.34, 1.56, 0.64, 1);
  outline: none;
  display: flex;
  align-items: center;
  justify-content: center;
}
.nk-my-loc-btn:hover {
  background: #1d4ed8;
  color: #ffffff;
  border-color: #1d4ed8;
  box-shadow: 0 6px 20px rgba(37, 99, 235, 0.4);
  transform: scale(1.08);
}
.nk-loc-svg {
  width: 22px;
  height: 22px;
  flex-shrink: 0;
  transition: transform 0.9s linear;
}
/* Hide My Location & bottom drawer when Measurement HUD is open */
.nk-app-map-wrap.is-measuring .nk-my-loc-btn,
.nk-measure-hud.active ~ .nk-my-loc-btn,
.nk-my-loc-btn.hidden {
  display: none !important;
}
.nk-my-loc-btn.loading {
  pointer-events: none;
  background: #1d4ed8;
  color: #ffffff;
  border-color: #1d4ed8;
}
/* The crosshair is radially symmetric, so spinning it reads as static — the
   ring is the part a farmer can actually see working. */
.nk-my-loc-btn.loading .nk-loc-svg {
  opacity: 0.45;
}
.nk-my-loc-btn.loading::after {
  content: '';
  position: absolute;
  inset: 3px;
  border-radius: 50%;
  border: 2px solid rgba(255, 255, 255, 0.35);
  border-top-color: #ffffff;
  animation: nkSpin 0.8s linear infinite;
  pointer-events: none;
}

@media (max-width: 560px) {
  .nk-title { font-size: 20px; padding: 10px 8px 2px; }
  .nk-title-sub { font-size: 12px; }
  .nk-float-search { top: 10px; left: 10px; right: 54px; }
  .nk-fs-btn { top: 10px; right: 10px; width: 35px; height: 35px; border-radius: 8px; }
  .nk-fs-icon { width: 16px; height: 16px; }
  .nk-fab-menu { right: 10px; top: 50px; }
  .nk-fab-main { width: 35px; height: 35px; border-radius: 8px; }
  .nk-my-loc-btn { bottom: 100px; right: 10px; width: 38px; height: 38px; }
  .nk-loc-svg { width: 19px; height: 19px; }
}

.nk-measure-hud {
  position: absolute;
  top: 68px;
  left: 12px;
  right: 58px;
  max-width: 420px;
  background: rgba(7, 31, 22, 0.95);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  color: #ffffff;
  border-radius: 14px;
  padding: 12px 14px;
  z-index: 1000;
  box-shadow: 0 12px 30px rgba(0, 0, 0, 0.35);
  border: 1px solid rgba(245, 183, 49, 0.4);
  box-sizing: border-box;
  display: none;
  animation: nkSlideDown 0.25s cubic-bezier(0.16, 1, 0.3, 1);
}
.nk-measure-hud.active { display: block; }
@keyframes nkSlideDown {
  from { opacity: 0; transform: translateY(-10px); }
  to { opacity: 1; transform: translateY(0); }
}

/* ── When Map is Fullscreen: Info Panel Positioned on Bottom ── */
.nk-app-map-wrap.is-fullscreen .nk-measure-hud {
  top: auto !important;
  bottom: 24px !important;
  left: 50% !important;
  right: auto !important;
  transform: translateX(-50%) !important;
  width: calc(100% - 32px) !important;
  max-width: 460px !important;
  margin: 0 auto !important;
  border-radius: 18px !important;
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.55), 0 0 0 1px rgba(245, 183, 49, 0.45) !important;
  animation: nkSlideUp 0.3s cubic-bezier(0.16, 1, 0.3, 1) !important;
  z-index: 2000 !important;
}

@keyframes nkSlideUp {
  from { opacity: 0; transform: translate(-50%, 20px); }
  to { opacity: 1; transform: translate(-50%, 0); }
}
.nk-mhud-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.nk-mhud-title {
  font-size: 13.5px;
  font-weight: 800;
  color: var(--nk-gold);
  display: flex;
  align-items: center;
  gap: 6px;
}
.nk-mhud-tip {
  font-size: 11.5px;
  color: rgba(255, 255, 255, 0.8);
  margin-bottom: 8px;
}
.nk-mhud-results {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 6px;
  background: rgba(255, 255, 255, 0.08);
  padding: 8px;
  border-radius: 10px;
  margin-bottom: 8px;
}
.nk-mhud-pill {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.75);
}
.nk-mhud-pill b {
  display: block;
  font-size: 15px;
  font-weight: 800;
  color: #ffffff;
  margin-top: 1px;
}
.nk-mhud-actions {
  display: flex;
  gap: 6px;
}
.nk-mhud-btn {
  flex: 1;
  padding: 6px 10px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 700;
  border: none;
  cursor: pointer;
  transition: all 0.2s ease;
}
.nk-mhud-btn.undo { background: rgba(255, 255, 255, 0.18); color: #ffffff; display: inline-flex; align-items: center; justify-content: center; gap: 3px; }
.nk-mhud-btn.undo:hover { background: rgba(255, 255, 255, 0.28); }
.nk-mhud-btn.clear { background: rgba(239, 68, 68, 0.25); color: #fca5a5; display: inline-flex; align-items: center; justify-content: center; }
.nk-mhud-btn.clear:hover { background: rgba(239, 68, 68, 0.38); }
.nk-mhud-btn.print { background: linear-gradient(135deg, #f5b731 0%, #e9a825 100%); color: #071f16; font-weight: 800; display: inline-flex; align-items: center; justify-content: center; gap: 4px; box-shadow: 0 2px 8px rgba(245, 183, 49, 0.3); }
.nk-mhud-btn.print:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(245, 183, 49, 0.45); }

/* ── Modern Bottom Sheet (Slide-Up Drawer) ── */
.nk-bottom-drawer {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  background: rgba(255, 255, 255, 0.98);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border-top: 2px solid var(--nk-gold);
  border-radius: 22px 22px 0 0;
  padding: 12px 18px 18px;
  z-index: 1000;
  box-shadow: 0 -10px 30px rgba(0, 0, 0, 0.2);
  transform: translateY(105%);
  transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1);
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.nk-bottom-drawer.active {
  transform: translateY(0);
}
.nk-drawer-handle {
  width: 42px;
  height: 4px;
  background: #cbd5e1;
  border-radius: 999px;
  margin: 0 auto 4px;
  cursor: pointer;
}
.nk-drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.nk-drawer-title-box h3 {
  font-size: 17.5px;
  font-weight: 800;
  color: var(--nk-emerald-dark);
  margin: 0;
  display: flex;
  align-items: center;
  gap: 6px;
}
.nk-drawer-title-box p {
  font-size: 12px;
  color: var(--nk-text-soft);
  margin: 2px 0 0;
  font-weight: 600;
}
.nk-drawer-close {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: none;
  background: #f1f5f3;
  color: #55695f;
  font-size: 14px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.nk-drawer-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
}
@media (min-width: 560px) {
  .nk-drawer-grid { grid-template-columns: repeat(4, 1fr); }
}
.nk-drawer-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 10px 12px;
  border-radius: 11px;
  font-size: 12.5px;
  font-weight: 700;
  text-decoration: none;
  box-shadow: 0 2px 6px rgba(0,0,0,0.04);
  transition: all 0.2s ease;
  white-space: nowrap;
}
.nk-drawer-btn:hover { transform: translateY(-2px); }
.nk-drawer-btn.bhav { background: #eef8f2; color: #166534; border: 1px solid #bbf7d0; }
.nk-drawer-btn.weather { background: #eff6ff; color: #1e40af; border: 1px solid #bfdbfe; }
.nk-drawer-btn.bhulekh { background: #fffbeb; color: #92400e; border: 1px solid #fde68a; }
.nk-drawer-btn.gaon { background: #fdf2f8; color: #9d174d; border: 1px solid #fbcfe8; }
.nk-drawer-btn.dl { background: linear-gradient(135deg, #f5b731 0%, #e9a825 100%); color: #071f16; border: 1px solid #f7d282; }

/* ── Farmer Quick Feature Cards Grid ── */
.nk-farmer-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  margin-top: 18px;
}
@media (max-width: 600px) {
  .nk-farmer-grid {
    grid-template-columns: 1fr;
    gap: 10px;
  }
}
.nk-farmer-card {
  display: flex;
  align-items: center;
  gap: 14px;
  background: #ffffff;
  border: 1.5px solid var(--nk-border-glass);
  border-radius: 16px;
  padding: 14px 16px;
  text-decoration: none;
  color: var(--nk-text-dark);
  box-shadow: var(--nk-shadow-sm);
  transition: all 0.2s ease;
}
.nk-farmer-card:hover {
  border-color: var(--nk-mint);
  transform: translateY(-2px);
  box-shadow: 0 8px 20px rgba(0,0,0,0.06);
}
.nk-farmer-card-ic {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  flex-shrink: 0;
}
.nk-farmer-card.bhulekh .nk-farmer-card-ic { background: #fef3c7; color: #b45309; }
.nk-farmer-card.weather .nk-farmer-card-ic { background: #dbeafe; color: #1d4ed8; }
.nk-farmer-card.bhav .nk-farmer-card-ic { background: #dcfce7; color: #15803d; }
.nk-farmer-card.gaon .nk-farmer-card-ic { background: #fce7f3; color: #be185d; }
.nk-farmer-card.yojana .nk-farmer-card-ic { background: #ede9fe; color: #6d28d9; }
.nk-farmer-card-body {
  flex: 1;
  min-width: 0;
}
.nk-farmer-card-title {
  font-size: 14.5px;
  font-weight: 800;
  color: var(--nk-emerald-dark);
  margin: 0 0 2px;
}
.nk-farmer-card-sub {
  font-size: 12px;
  color: var(--nk-text-soft);
  margin: 0;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.nk-farmer-card-arrow {
  color: var(--nk-text-soft);
  font-size: 16px;
  font-weight: 800;
}

/* ── Compact HD Map Download Banner ── */
.nk-dl-banner {
  display: flex;
  align-items: center;
  gap: 16px;
  background: linear-gradient(135deg, #071f16 0%, #134232 100%);
  color: #ffffff;
  border-radius: 18px;
  padding: 16px 20px;
  margin-top: 18px;
  box-shadow: var(--nk-shadow-md);
  border: 1.5px solid rgba(245, 183, 49, 0.3);
}
@media (max-width: 640px) {
  .nk-dl-banner {
    flex-direction: column;
    text-align: center;
    gap: 12px;
    padding: 16px;
  }
}
.nk-dl-banner-thumb {
  width: 64px;
  height: 64px;
  border-radius: 10px;
  object-fit: cover;
  border: 1px solid rgba(255,255,255,0.2);
  background: #ffffff;
  flex-shrink: 0;
}
.nk-dl-banner-info {
  flex: 1;
  min-width: 0;
}
.nk-dl-banner-info h3 {
  font-size: 16px;
  font-weight: 800;
  color: var(--nk-gold);
  margin: 0 0 4px;
}
.nk-dl-banner-info p {
  font-size: 12.5px;
  color: rgba(255,255,255,0.85);
  margin: 0;
}
.nk-dl-banner-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 18px;
  border-radius: 999px;
  background: linear-gradient(135deg, #f5b731 0%, #e9a825 100%);
  color: #071f16;
  font-size: 13.5px;
  font-weight: 800;
  text-decoration: none;
  white-space: nowrap;
  box-shadow: 0 4px 14px rgba(245, 183, 49, 0.4);
  transition: transform 0.2s ease;
}
.nk-dl-banner-btn:hover { transform: scale(1.04); }
/* The map itself, shown as a real picture in the download card: this <img> is
   what Google Images indexes for "mp map" / "राजस्थान का नक्शा" — a 64px thumb
   was all it had before, while the HD file sat behind a link. Kept to a card-
   sized crop so the page still has ONE big map (the interactive one). */
.nk-dl-prev { display:block; flex-shrink:0; width:120px; height:96px; border-radius:12px;
  overflow:hidden; background:#fff; border:1px solid rgba(255,255,255,0.25); }
.nk-dl-prev img { display:block; width:100%; height:100%; object-fit:cover; }
.nk-dl-btns { display:flex; flex-direction:column; gap:8px; }
.nk-dl-banner-btn.alt { background:transparent; color:#fff; box-shadow:none;
  border:1.5px solid rgba(255,255,255,0.45); justify-content:center; }
@media (max-width: 640px) {
  .nk-dl-prev { width:100%; height:150px; }
  .nk-dl-btns { display:grid; grid-template-columns:1fr 1fr; width:100%; }
  .nk-dl-btns .nk-dl-banner-btn { justify-content:center; padding:11px 10px; }
}

/* ── 4-Column Fact Metrics Bar ── */
.nk-facts-bar {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  margin-top: 18px;
}
@media (max-width: 600px) {
  .nk-facts-bar {
    grid-template-columns: repeat(2, 1fr);
  }
}
.nk-fact-box {
  background: #ffffff;
  border: 1.5px solid var(--nk-border-glass);
  border-radius: 14px;
  padding: 10px 12px;
  text-align: center;
  box-shadow: var(--nk-shadow-sm);
}
.nk-fact-box small {
  display: block;
  font-size: 11px;
  font-weight: 700;
  color: var(--nk-text-soft);
  text-transform: uppercase;
}
.nk-fact-box b {
  display: block;
  font-size: 14px;
  font-weight: 800;
  color: var(--nk-emerald-dark);
  margin-top: 2px;
}

.nk-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px 20px;
  border-radius: var(--nk-radius-md);
  font-size: 14px;
  font-weight: 700;
  text-decoration: none;
  min-height: 46px;
  transition: all 0.2s ease;
  cursor: pointer;
  box-sizing: border-box;
}
.nk-btn.primary {
  background: linear-gradient(135deg, #f5b731 0%, #e9a825 100%);
  color: #071f16;
  border: 1px solid #ffd269;
  box-shadow: 0 4px 14px var(--nk-gold-glow);
}
.nk-btn.plain {
  background: #ffffff;
  color: var(--nk-emerald-mid);
  border: 1.5px solid var(--nk-border-glass);
  box-shadow: var(--nk-shadow-sm);
}

.nk-sec { margin: 28px 0 0; }
.nk-sec>h2 { font-family: var(--nk-font); font-size: 20px; font-weight: 800; color: var(--nk-emerald-dark); margin-bottom: 6px; }
.nk-sec>p.nk-lede { font-size: 13.5px; color: var(--nk-text-mid); margin-bottom: 14px; }

/* Quick Jump Chips */
.nk-chips { display: flex; flex-wrap: wrap; gap: 8px; }
.nk-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  background: #ffffff;
  border: 1.5px solid var(--nk-border-glass);
  border-radius: 999px;
  padding: 7px 14px;
  font-size: 13px;
  font-weight: 700;
  color: var(--nk-emerald-dark);
  text-decoration: none;
  transition: all 0.2s ease;
  box-shadow: 0 2px 6px rgba(0,0,0,0.02);
}
.nk-chip:hover {
  border-color: var(--nk-mint);
  background: #eef9f3;
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(82, 183, 136, 0.18);
}
.nk-km { font-size: 11px; color: var(--nk-text-soft); background: #f2f7f4; border-radius: 999px; padding: 2px 6px; }

/* District Directory List Rows */
.nk-dgrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 240px), 1fr)); gap: 10px; width: 100%; }
.nk-drow {
  display: flex;
  align-items: center;
  gap: 10px;
  background: #ffffff;
  border: 1.5px solid var(--nk-border-glass);
  border-radius: 12px;
  padding: 10px 14px;
  text-decoration: none;
  color: var(--nk-text-dark);
  transition: all 0.2s ease;
  box-shadow: 0 2px 6px rgba(0,0,0,0.02);
}
.nk-drow:hover {
  border-color: var(--nk-mint);
  background: #eef9f3;
  transform: translateY(-2px);
}
.nk-drow .nk-num {
  font-size: 11px;
  font-weight: 800;
  color: var(--nk-emerald-dark);
  width: 24px;
  height: 24px;
  background: #e4f4eb;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.nk-drow b { font-size: 14px; font-weight: 800; color: var(--nk-emerald-dark); }
.nk-drow .nk-dname { display: flex; flex-direction: column; min-width: 0; text-decoration: none; color: inherit; }
.nk-drow span.nk-en { font-size: 11.5px; color: var(--nk-text-soft); font-weight: 600; }

.nk-sgrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 10px; width: 100%; }
.nk-scard {
  display: flex;
  align-items: center;
  gap: 10px;
  background: #ffffff;
  border: 1.5px solid var(--nk-border-glass);
  border-radius: 12px;
  padding: 12px 14px;
  text-decoration: none;
  color: var(--nk-text-dark);
  transition: all 0.2s ease;
}
.nk-scard:hover { border-color: var(--nk-mint); background: #f2faf5; transform: translateY(-2px); }
.nk-scard b { font-size: 13.5px; font-weight: 800; color: var(--nk-emerald-dark); }
.nk-scard small { font-size: 11.5px; color: var(--nk-text-soft); font-weight: 600; }
.nk-scard .nk-go { margin-left: auto; color: var(--nk-emerald-light); font-size: 16px; font-weight: 800; }

.nk-note { background: #fffbeb; border: 1.5px solid #f2e3b8; border-radius: 12px; padding: 12px 16px; font-size: 13px; color: #7a6320; line-height: 1.6; margin-top: 16px; }
.nk-updated { font-size: 12px; color: var(--nk-text-soft); margin: 20px 0 0; font-weight: 600; text-align: center; }
.nk-search { width: 100%; max-width: 480px; padding: 12px 16px; border: 1.5px solid var(--nk-border-glass); border-radius: 12px; font-size: 14px; font-family: inherit; background: #ffffff; margin-top: 14px; font-weight: 600; }

/* GPS Pulsing Dot for Locate Me */
.nk-gps-pulse {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #3b82f6;
  border: 3px solid #ffffff;
  box-shadow: 0 0 10px rgba(59, 130, 246, 0.8);
  animation: nkPulse 1.8s infinite;
}
@keyframes nkPulse {
  0% { box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.7); }
  70% { box-shadow: 0 0 0 14px rgba(59, 130, 246, 0); }
  100% { box-shadow: 0 0 0 0 rgba(59, 130, 246, 0); }
}

@media (max-width: 560px) {
  .nk-title { font-size: 20px; padding: 12px 8px 2px; }
  .nk-title-sub { font-size: 12px; }
  .nk-map { height: 68vh; min-height: 420px; }
  .nk-float-search { top: 10px; left: 10px; right: 52px; }
  .nk-fab-menu { right: 10px; top: 50px; }
  .nk-fab-main { width: 34px; height: 34px; border-radius: 8px; }
  .nk-measure-hud { top: 50px; left: 10px; right: 52px; padding: 10px 12px; }
  .nk-app-map-wrap.is-fullscreen .nk-measure-hud {
    bottom: 12px !important;
    left: 10px !important;
    right: 10px !important;
    width: auto !important;
    transform: none !important;
    max-width: none !important;
    padding: 10px 12px !important;
  }
  .nk-bottom-drawer { padding: 10px 14px 14px; }
  .nk-drawer-title-box h3 { font-size: 15.5px; }
}
"""

_LEAFLET_CSS = ('<link rel="stylesheet" '
                'href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">')


def _crumbs(trail: list) -> str:
    """Visible breadcrumb disabled on map pages per UI requirement."""
    return ""


def _state_cards(keys: list, states: dict, jile: bool = False) -> str:
    return "".join(
        f'<a class="nk-scard" href="{_jile_url(k) if jile else _url(k)}">'
        f'<span class="nk-sn"><b>{escape(states[k]["hi"])}</b>'
        f'<small>{_jile(_now_n(k, states[k]))}</small></span>'
        f'<span class="nk-go">›</span></a>' for k in keys)


def _others(key: str, states: dict) -> str:
    """Same-region neighbours first, then the biggest farming states."""
    region = states[key]["region"]
    near = [k for k, s in states.items() if s["region"] == region and k != key]
    fill = [k for k in _POPULAR if k != key and k not in near]
    return _state_cards((near + fill)[:11], states)


def _dl_button(s: dict, label: str, cls: str = "primary") -> str:
    return (f'<a class="nk-btn {cls}" data-km-map-picker '
            f'href="{_img(s, "district-map.png")}" '
            f'download="{s["prefix"]}-{s["n"]}-jile.png">⬇️ {label}</a>')


def _state_select_dropdown(current_key: str, states: dict, is_jile: bool = False) -> str:
    opts = ['<option value="">🗺️ दूसरा राज्य चुनें...</option>']
    for k, s in states.items():
        url = _jile_url(k) if is_jile else _url(k)
        sel = ' selected' if k == current_key else ''
        opts.append(f'<option value="{url}"{sel}>{escape(s["hi"])} ({_jile(_now_n(k, s))})</option>')
    return (f'<select class="nk-state-select" onchange="if(this.value) window.location.href=this.value;" aria-label="राज्य चुनें">'
            f'{"".join(opts)}</select>')


def _tail_scripts(s: dict = None, initial: str = "", state_key: str = "", dslug: str = "") -> str:
    """map-download.js everywhere; Leaflet and interactive controls where there is a map to draw."""
    out = ['<script>window.KM_LOC_AFTER_SCROLL=true;</script>',
           f'<script src="{_asset("map-download.js")}" defer></script>']
    if s:
        initial_js = json.dumps(initial, ensure_ascii=False)
        state_key_js = json.dumps(state_key or "uttar-pradesh")
        dslug_js = json.dumps(dslug)
        bhulekh_info = _BHULEKH.get(state_key, ("https://bhulekh.gov.in/", "भूलेख पोर्टल"))
        bhulekh_url_js = json.dumps(bhulekh_info[0])
        bhulekh_title_js = json.dumps(bhulekh_info[1], ensure_ascii=False)

        out.append('<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>')
        out.append(f"""<script>
(function(){{
  var mapInitialized = false;

  function initMap() {{
    if(mapInitialized) return;
    if(!window.L) {{
      var tries = 0;
      var t = setInterval(function(){{
        tries++;
        if(window.L) {{
          clearInterval(t);
          initMap();
        }} else if(tries > 80) {{
          clearInterval(t);
          console.error('Leaflet script load timed out');
        }}
      }}, 100);
      return;
    }}
    mapInitialized = true;
  var stateKey = {state_key_js};
  var districtSlug = {dslug_js};
  var bhulekhUrl = {bhulekh_url_js};
  var bhulekhTitle = {bhulekh_title_js};

  var mapWrap = document.getElementById('nk-map-wrap');
  var mapEl = document.getElementById('nk-map');
  if(!mapEl) return;

  var map = L.map('nk-map', {{
    zoomSnap: 0.25,
    zoomControl: false // Custom controls replace standard Leaflet controls
  }}).setView([{s['lat']}, {s['lon']}], 6.5);

  // Custom Zoom Control placed bottom-right
  L.control.zoom({{ position: 'bottomright' }}).addTo(map);

  // setView teleports once the jump is longer than a screen or two, which is
  // every GPS fix from a state-wide view. flyTo arcs out and back in, so the
  // farmer can see where the map went.
  function nkFlyTo(lat, lon, zoom) {{
    if(!map) return;
    var reduce = false;
    try {{ reduce = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches); }} catch(e) {{}}
    if(reduce) {{ map.setView([lat, lon], zoom); return; }}
    var km = 0;
    try {{ km = map.getCenter().distanceTo(L.latLng(lat, lon)) / 1000; }} catch(e) {{}}
    map.flyTo([lat, lon], zoom, {{ duration: Math.max(1.2, Math.min(2.6, 1 + km / 260)), easeLinearity: 0.22 }});
  }}

  // ── Tile Layers ──
  // maxNativeZoom is the deepest zoom the PROVIDER actually holds a picture for;
  // maxZoom is how far the farmer may keep zooming. Splitting them is the point:
  // over most of rural India Esri's imagery stops at z18, and a z19 request comes
  // back as a grey "Map data not yet available" card — so the last zoom step, the
  // one where you are trying to see your own खेत, used to destroy the picture.
  // Capping the REQUEST at 18 and letting Leaflet upscale keeps real imagery on
  // screen the whole way in. 20 is the ceiling because a 4x upscale still shows
  // plot edges; at 21 it is mush, which is the complaint this answers.
  // ── 3-Tier Progressive LOD Tile Layers ──
  // Tier 1: Instant Low-Poly/Low-Res Base (z=7, ~18KB, stretched across entire canvas in <150ms)
  var lowSatLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
    maxNativeZoom: 7,
    maxZoom: 20,
    zIndex: 1,
    attribution: '',
    className: 'nk-tile-low-poly'
  }});
  // Tier 2 & 3: Mid/High-Res Progressive Satellite Imagery (z=8-18)
  var satLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
    attribution: 'Tiles © Esri World Imagery',
    minZoom: 8,
    maxNativeZoom: 18,
    maxZoom: 20,
    zIndex: 2,
    updateWhenIdle: true,
    keepBuffer: 2
  }});
  var labelLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
    attribution: '© Esri',
    minZoom: 8,
    maxNativeZoom: 18,
    maxZoom: 20,
    zIndex: 3,
    updateWhenIdle: true,
    keepBuffer: 2
  }});
  // OSM serves real tiles to z19 and hard-400s at z20, so it gets its own floor.
  var osmLayer = L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
    attribution: '© OpenStreetMap contributors',
    maxNativeZoom: 19,
    maxZoom: 20,
    updateWhenIdle: true,
    keepBuffer: 2
  }});

  // Default: Low-Res Base + Satellite + Labels
  lowSatLayer.addTo(map);
  satLayer.addTo(map);
  labelLayer.addTo(map);
  var currentLayerType = 'sat'; // 'sat' or 'osm'

  // Ensure map tiles render accurately across all viewport sizes
  setTimeout(function(){{ map.invalidateSize(); }}, 100);
  setTimeout(function(){{ map.invalidateSize(); }}, 400);
  setTimeout(function(){{ map.invalidateSize(); }}, 1200);
  window.addEventListener('load', function(){{ map.invalidateSize(); }});

  // ── Location Permission Notification Banner ──
  // Show a friendly toast asking for GPS access if it hasn't been granted yet.
  // Uses the Permissions API (where available) to avoid showing it when already granted.
  (function() {{
    var TOAST_KEY = 'km_loc_perm_asked';
    // Inject toast CSS once
    var style = document.createElement('style');
    style.textContent = [
      '#nk-loc-perm-toast{{',
        'position:fixed;bottom:90px;left:50%;transform:translateX(-50%) translateY(20px);',
        'z-index:9999;display:flex;align-items:flex-start;gap:12px;',
        'background:#071f16;color:#fff;border-radius:16px;',
        'padding:14px 18px;max-width:340px;width:calc(100% - 32px);',
        'box-shadow:0 8px 32px rgba(0,0,0,0.45);border:1px solid rgba(82,183,136,0.3);',
        'font-family:inherit;opacity:0;transition:opacity .35s,transform .35s;pointer-events:none;',
      '}}',
      '#nk-loc-perm-toast.show{{opacity:1;transform:translateX(-50%) translateY(0);pointer-events:auto;}}',
      '#nk-loc-perm-toast .nk-lt-icon{{font-size:26px;line-height:1;flex-shrink:0;margin-top:2px;}}',
      '#nk-loc-perm-toast .nk-lt-body{{flex:1;min-width:0;}}',
      '#nk-loc-perm-toast .nk-lt-title{{font-size:13.5px;font-weight:800;color:#52b788;margin-bottom:3px;}}',
      '#nk-loc-perm-toast .nk-lt-msg{{font-size:12px;font-weight:600;color:rgba(255,255,255,0.85);line-height:1.45;}}',
      '#nk-loc-perm-toast .nk-lt-actions{{display:flex;gap:8px;margin-top:10px;}}',
      '#nk-loc-perm-toast .nk-lt-btn{{border:none;border-radius:8px;padding:7px 14px;font-size:12px;font-weight:800;cursor:pointer;font-family:inherit;}}',
      '#nk-loc-perm-toast .nk-lt-allow{{background:#52b788;color:#071f16;}}',
      '#nk-loc-perm-toast .nk-lt-allow:hover{{background:#40916c;}}',
      '#nk-loc-perm-toast .nk-lt-dismiss{{background:rgba(255,255,255,0.12);color:#fff;}}',
      '#nk-loc-perm-toast .nk-lt-dismiss:hover{{background:rgba(255,255,255,0.22);}}',
      '#nk-loc-perm-toast .nk-lt-close{{position:absolute;top:10px;right:12px;background:none;border:none;',
        'color:rgba(255,255,255,0.5);font-size:14px;cursor:pointer;padding:2px 4px;line-height:1;}}',
      '#nk-loc-perm-toast .nk-lt-close:hover{{color:#fff;}}'
    ].join('');
    document.head.appendChild(style);

    function showToast() {{
      if(document.getElementById('nk-loc-perm-toast')) return;
      var toast = document.createElement('div');
      toast.id = 'nk-loc-perm-toast';
      toast.innerHTML =
        '<div class="nk-lt-icon"><svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="#52b788" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="7"/><line x1="12" y1="2" x2="12" y2="5"/><line x1="12" y1="19" x2="12" y2="22"/><line x1="2" y1="12" x2="5" y2="12"/><line x1="19" y1="12" x2="22" y2="12"/><circle cx="12" cy="12" r="2.5" fill="#52b788"/></svg></div>' +
        '<div class="nk-lt-body">' +
          '<div class="nk-lt-title">लोकेशन एक्सेस दें — सटीक नक्शा के लिए</div>' +
          '<div class="nk-lt-msg">अपना खेत, गाँव या ज़मीन सटीक रूप से देखने व नापने के लिए GPS लोकेशन की अनुमति दें।</div>' +
          '<div class="nk-lt-actions">' +
            '<button class="nk-lt-btn nk-lt-allow" id="nk-lt-allow-btn">✅ लोकेशन दें</button>' +
            '<button class="nk-lt-btn nk-lt-dismiss" id="nk-lt-dismiss-btn">बाद में</button>' +
          '</div>' +
        '</div>' +
        '<button class="nk-lt-close" id="nk-lt-close-btn" aria-label="बंद करें">✕</button>';
      document.body.appendChild(toast);

      // Animate in
      requestAnimationFrame(function() {{
        requestAnimationFrame(function() {{ toast.classList.add('show'); }});
      }});

      function hide() {{
        toast.classList.remove('show');
        setTimeout(function() {{ if(toast.parentNode) toast.parentNode.removeChild(toast); }}, 400);
      }}

      document.getElementById('nk-lt-close-btn').addEventListener('click', function() {{
        localStorage.setItem(TOAST_KEY, '1');
        hide();
      }});
      document.getElementById('nk-lt-dismiss-btn').addEventListener('click', function() {{
        localStorage.setItem(TOAST_KEY, '1');
        hide();
      }});
      document.getElementById('nk-lt-allow-btn').addEventListener('click', function() {{
        localStorage.setItem(TOAST_KEY, '1');
        hide();
        // Trigger GPS locate
        var gpsBtn = document.getElementById('nk-fab-gps');
        if(gpsBtn) gpsBtn.click();
        else if(typeof locateUser === 'function') locateUser();
      }});

      // Auto-dismiss after 12s
      var autoHide = setTimeout(function() {{ hide(); }}, 12000);
      document.getElementById('nk-lt-allow-btn').addEventListener('click', function() {{ clearTimeout(autoHide); }});
    }}

    function maybeShowToast() {{
      // Don't show if user already dismissed or if permission is already granted
      if(localStorage.getItem(TOAST_KEY)) return;
      if(!navigator.geolocation) return;

      if(navigator.permissions && navigator.permissions.query) {{
        navigator.permissions.query({{ name: 'geolocation' }}).then(function(result) {{
          if(result.state === 'granted') {{
            // Already granted — no need to ask
            localStorage.setItem(TOAST_KEY, '1');
            return;
          }}
          // 'prompt' or 'denied' — show the banner
          setTimeout(showToast, 1800);
        }}).catch(function() {{
          // Permissions API not supported, show toast after delay
          setTimeout(showToast, 1800);
        }});
      }} else {{
        // Fallback for browsers without Permissions API
        setTimeout(showToast, 1800);
      }}
    }}

    maybeShowToast();
  }})();


  var fabMenu = document.getElementById('nk-fab-menu');
  var fabTrigger = document.getElementById('nk-fab-trigger');
  if(fabTrigger && fabMenu) {{
    fabTrigger.addEventListener('click', function(e){{
      e.stopPropagation();
      fabMenu.classList.toggle('open');
    }});
    document.addEventListener('click', function(e){{
      if(!fabMenu.contains(e.target)) {{
        fabMenu.classList.remove('open');
      }}
    }});
  }}

  // ── Layer Toggle (FAB) ──
  var fabLayer = document.getElementById('nk-fab-layer');
  var fabLayerIc = document.getElementById('nk-fab-layer-ic');
  var fabLayerText = document.getElementById('nk-fab-layer-text');
  if(fabLayer) {{
    fabLayer.addEventListener('click', function(){{
      if(currentLayerType === 'sat') {{
        map.removeLayer(lowSatLayer);
        map.removeLayer(satLayer);
        map.removeLayer(labelLayer);
        osmLayer.addTo(map);
        currentLayerType = 'osm';
        if(fabLayerIc) fabLayerIc.textContent = '🛰️';
        if(fabLayerText) fabLayerText.textContent = 'सैटेलाइट व्यू';
      }} else {{
        map.removeLayer(osmLayer);
        lowSatLayer.addTo(map);
        satLayer.addTo(map);
        labelLayer.addTo(map);
        currentLayerType = 'sat';
        if(fabLayerIc) fabLayerIc.textContent = '🗺️';
        if(fabLayerText) fabLayerText.textContent = 'नक्शा व्यू';
      }}
      if(fabMenu) fabMenu.classList.remove('open');
    }});
  }}

  // ── State / District Boundary Overlay Toggle (FAB) ──
  var isOverlayVisible = true;
  var fabOverlay = document.getElementById('nk-fab-overlay');
  var fabOverlayIc = document.getElementById('nk-fab-overlay-ic');
  var fabOverlayText = document.getElementById('nk-fab-overlay-text');

  function setOverlayVisibility(show) {{
    isOverlayVisible = !!show;
    if(geojsonLayer) {{
      if(isOverlayVisible) {{
        if(!map.hasLayer(geojsonLayer)) geojsonLayer.addTo(map);
      }} else {{
        if(map.hasLayer(geojsonLayer)) map.removeLayer(geojsonLayer);
      }}
    }}
    if(fabOverlay) {{
      fabOverlay.classList.toggle('off', !isOverlayVisible);
      if(fabOverlayIc) fabOverlayIc.textContent = isOverlayVisible ? '👁️' : '🕶️';
      if(fabOverlayText) fabOverlayText.textContent = isOverlayVisible ? 'सीमा छिपाएं' : 'सीमा दिखाएं';
    }}
  }}

  function toggleOverlay() {{
    if(fabMenu) fabMenu.classList.remove('open');
    setOverlayVisibility(!isOverlayVisible);
  }}

  if(fabOverlay) fabOverlay.addEventListener('click', toggleOverlay);

  // ── Fullscreen Toggle (top-right icon button) ──
  var fabFullscreen = document.getElementById('nk-fab-fullscreen');
  var fsIconExpand   = document.getElementById('nk-fs-icon-expand');
  var fsIconCollapse = document.getElementById('nk-fs-icon-collapse');

  function setFullscreen(enable) {{
    if(!mapWrap) return;
    var isFull = !!enable;
    mapWrap.classList.toggle('is-fullscreen', isFull);
    if(fabFullscreen) fabFullscreen.classList.toggle('active', isFull);
    if(fsIconExpand)   fsIconExpand.style.display   = isFull ? 'none'  : 'block';
    if(fsIconCollapse) fsIconCollapse.style.display = isFull ? 'block' : 'none';
    setTimeout(function(){{ map.invalidateSize(); }}, 250);
  }}

  if(fabFullscreen && mapWrap) {{
    fabFullscreen.addEventListener('click', function(){{
      var isNowFull = !mapWrap.classList.contains('is-fullscreen');
      setFullscreen(isNowFull);
    }});
    document.addEventListener('keydown', function(e){{
      if(e.key === 'Escape' && mapWrap.classList.contains('is-fullscreen')) {{
        setFullscreen(false);
      }}
    }});
  }}

  // ── GPS "मेरी लोकेशन / खेत" Handler ──
  var fabGps = document.getElementById('nk-fab-gps');
  var searchLocBtn = document.getElementById('nk-search-loc-btn');
  var gpsMarker = null, gpsCircle = null;

  function locateUser() {{
    if(fabMenu) fabMenu.classList.remove('open');
    if(!navigator.geolocation) {{
      alert('आपके डिवाइस या ब्राउज़र में GPS / लोकेशन की सुविधा उपलब्ध नहीं है।');
      return;
    }}
    if(fabGps) {{
      fabGps.classList.add('loading');
      var fabGpsLabel = fabGps.querySelector('.nk-my-loc-label');
      if(fabGpsLabel) fabGpsLabel.textContent = 'खोज रहे हैं';
    }}
    if(searchLocBtn) {{ searchLocBtn.classList.add('active', 'loading'); }}
    var searchLocText = searchLocBtn ? searchLocBtn.querySelector('.nk-loc-text') : null;
    if(searchLocText) searchLocText.textContent = 'खोज रहे हैं';

    navigator.geolocation.getCurrentPosition(function(pos) {{
      var lat = pos.coords.latitude;
      var lon = pos.coords.longitude;
      var acc = pos.coords.accuracy;

      if(!map.hasLayer(satLayer)) {{
        map.removeLayer(osmLayer);
        lowSatLayer.addTo(map);
        satLayer.addTo(map);
        labelLayer.addTo(map);
        currentLayerType = 'sat';
        if(fabLayerIc) fabLayerIc.textContent = '🗺️';
        if(fabLayerText) fabLayerText.textContent = 'नक्शा व्यू';
      }}

      if(gpsMarker) map.removeLayer(gpsMarker);
      if(gpsCircle) map.removeLayer(gpsCircle);

      gpsCircle = L.circle([lat, lon], {{
        radius: Math.max(acc, 15),
        color: '#2563eb',
        fillColor: '#60a5fa',
        fillOpacity: 0.22,
        weight: 1.5
      }}).addTo(map);
      
      var pulseIcon = L.divIcon({{
        className: 'nk-gps-pulse-wrap',
        html: '<div class="nk-gps-pulse"></div>',
        iconSize: [18, 18],
        iconAnchor: [9, 9]
      }});
      gpsMarker = L.marker([lat, lon], {{ icon: pulseIcon }}).addTo(map);

      nkFlyTo(lat, lon, 16);

      // Reverse geocode via BigDataCloud client API
      var rurl = 'https://api.bigdatacloud.net/data/reverse-geocode-client?latitude=' + lat + '&longitude=' + lon + '&localityLanguage=hi';
      fetch(rurl)
        .then(function(r) {{ return r.json(); }})
        .then(function(d) {{
          var placeName = d.locality || d.city || d.village || '';
          var distName = d.principalSubdivision || d.localityInfo && d.localityInfo.administrative && d.localityInfo.administrative[2] && d.localityInfo.administrative[2].name || '';
          var fullLoc = [placeName, distName].filter(Boolean).join(', ') || 'आपका खेत / स्थान';

          gpsMarker.bindPopup('<b>📍 आपका स्थान: ' + fullLoc + '</b><br>सटीकता: ±' + Math.round(acc) + ' मीटर').openPopup();

          if(searchInput && placeName) {{
            searchInput.value = fullLoc;
          }}

          // Check if detected district matches one on this state map
          var matchedKey = Object.keys(districtMap).find(function(k) {{
            return (distName && (k.toLowerCase().indexOf(distName.toLowerCase()) > -1 || distName.toLowerCase().indexOf(k.toLowerCase()) > -1)) ||
                   (placeName && (k.toLowerCase().indexOf(placeName.toLowerCase()) > -1 || placeName.toLowerCase().indexOf(k.toLowerCase()) > -1));
          }});

          if(matchedKey) {{
            selectDistrict(districtMap[matchedKey].hiName, false);
            if(drawerTitle) drawerTitle.innerHTML = '📍 ' + fullLoc;
          }} else {{
            if(drawerTitle) drawerTitle.innerHTML = '📍 ' + fullLoc;
            if(drawerSub) drawerSub.textContent = 'GPS द्वारा पहचाना गया स्थान (±' + Math.round(acc) + 'm)';
            if(bottomDrawer) bottomDrawer.classList.add('active');
            if(fabReset) fabReset.style.display = 'flex';
          }}

          // Persist in localStorage for weather, mandi, shop
          try {{
            localStorage.setItem('km_geo', JSON.stringify({{
              status: 'granted',
              lat: lat,
              lon: lon,
              location: fullLoc,
              ts: Date.now()
            }}));
            document.dispatchEvent(new CustomEvent('km:location', {{
              detail: {{ lat: lat, lon: lon, location: fullLoc }}
            }}));
          }} catch(e) {{}}
        }})
        .catch(function() {{
          gpsMarker.bindPopup('<b>📍 आपका वर्तमान स्थान (खेत)</b><br>सटीकता: ±' + Math.round(acc) + ' मीटर').openPopup();
        }})
        .finally(function() {{
          if(fabGps) {{ fabGps.classList.remove('loading'); }}
          if(searchLocBtn) {{ searchLocBtn.classList.remove('active', 'loading'); }}
          if(searchLocText) searchLocText.textContent = 'लोकेशन';
        }});

    }}, function(err) {{
      if(fabGps) {{ fabGps.classList.remove('loading'); }}
      if(searchLocBtn) {{ searchLocBtn.classList.remove('active', 'loading'); }}
      if(searchLocText) searchLocText.textContent = 'लोकेशन';
      alert('लोकेशन प्राप्त नहीं हो सकी: कृपया GPS ऑन करें और ब्राउज़र में लोकेशन अनुमति दें।');
    }}, {{ enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }});
  }}

  if(fabGps) fabGps.addEventListener('click', locateUser);
  if(searchLocBtn) searchLocBtn.addEventListener('click', locateUser);

  // ── "खेत नापो" Farm Area Measurement Tool ──
  var fabMeasure = document.getElementById('nk-fab-measure');
  var measureHud = document.getElementById('nk-measure-hud');
  var hudAcre = document.getElementById('nk-mhud-acre');
  var hudBigha = document.getElementById('nk-mhud-bigha');
  var hudHectare = document.getElementById('nk-mhud-hectare');
  var hudSqm = document.getElementById('nk-mhud-sqm');
  var btnUndo = document.getElementById('nk-mhud-undo');
  var btnClear = document.getElementById('nk-mhud-clear');
  var btnPrint = document.getElementById('nk-mhud-print');
  var btnHudClose = document.getElementById('nk-mhud-close');

  var isMeasuring = false;
  var measurePoints = [];
  var measureMarkers = [];
  var measurePolygon = null;

  function calcPolygonArea(latlngs) {{
    if(latlngs.length < 3) return 0;
    var R = 6378137; // Earth's radius in meters
    var rad = function(deg) {{ return deg * Math.PI / 180; }};
    var total = 0;
    var len = latlngs.length;
    for(var i = 0; i < len; i++) {{
      var p1 = latlngs[i];
      var p2 = latlngs[(i + 1) % len];
      total += (rad(p2.lng) - rad(p1.lng)) * (2 + Math.sin(rad(p1.lat)) + Math.sin(rad(p2.lat)));
    }}
    total = Math.abs(total * R * R / 2.0);
    return total; // in sq meters
  }}

  function updateMeasureHud() {{
    var sqm = calcPolygonArea(measurePoints);
    var acres = sqm / 4046.8564224;
    var hectares = sqm / 10000;
    // Official Standard Revenue Conversion: 1 Acre = 1.6 Pakka Bigha (2,529.3 m² / 20 Biswa)
    var bigha = acres * 1.6;

    if(hudSqm) hudSqm.textContent = Math.round(sqm).toLocaleString('en-IN') + ' m²';
    if(hudAcre) hudAcre.textContent = (acres < 0.01 ? acres.toFixed(4) : acres.toFixed(2)) + ' एकड़';
    if(hudBigha) hudBigha.textContent = (bigha < 0.01 ? bigha.toFixed(4) : bigha.toFixed(2)) + ' बीघा';
    if(hudHectare) hudHectare.textContent = (hectares < 0.01 ? hectares.toFixed(4) : hectares.toFixed(3)) + ' हे.';
  }}

  function renderMeasurePolygon() {{
    if(measurePolygon) map.removeLayer(measurePolygon);
    if(measurePoints.length >= 2) {{
      measurePolygon = L.polygon(measurePoints, {{
        color: '#f5b731',
        weight: 2.5,
        fillColor: '#ffd269',
        fillOpacity: 0.35,
        dashArray: '5, 8'
      }}).addTo(map);
    }}
    updateMeasureHud();
  }}

  function clearMeasure() {{
    measurePoints = [];
    measureMarkers.forEach(function(m){{ map.removeLayer(m); }});
    measureMarkers = [];
    if(measurePolygon) map.removeLayer(measurePolygon);
    measurePolygon = null;
    updateMeasureHud();
  }}

  function toggleMeasure() {{
    if(fabMenu) fabMenu.classList.remove('open');
    isMeasuring = !isMeasuring;
    if(mapWrap) mapWrap.classList.toggle('is-measuring', isMeasuring);
    if(fabGps) fabGps.style.display = isMeasuring ? 'none' : 'flex';
    if(fabMeasure) fabMeasure.classList.toggle('active', isMeasuring);
    if(measureHud) measureHud.classList.toggle('active', isMeasuring);
    if(isMeasuring) {{
      // 1. Automatically open map in fullscreen for optimal measuring canvas
      setFullscreen(true);
      // 2. Automatically hide state/district overlay so farmer can clearly see and measure fields
      setOverlayVisibility(false);
      // 3. Auto-switch to satellite view for precise field boundaries
      if(!map.hasLayer(satLayer)) {{
        map.removeLayer(osmLayer);
        satLayer.addTo(map);
        labelLayer.addTo(map);
        currentLayerType = 'sat';
        if(fabLayerIc) fabLayerIc.textContent = '🗺️';
        if(fabLayerText) fabLayerText.textContent = 'नक्शा व्यू';
      }}
    }} else {{
      clearMeasure();
      // Restore boundary overlay visibility when exiting measurement mode
      setOverlayVisibility(true);
      if(fabGps) fabGps.style.display = 'flex';
    }}
  }}

  function printSketchReport() {{
    if(measurePoints.length < 3) {{
      alert('कृपया खेत का नक्शा प्रिंट करने के लिए मानचित्र पर कम से कम 3 बिंदु लगाएं।');
      return;
    }}

    var sqm = calcPolygonArea(measurePoints);
    var acres = sqm / 4046.8564224;
    var hectares = sqm / 10000;
    var bigha = acres * 1.6;

    var perimeterMeters = 0;
    var len = measurePoints.length;
    for(var i = 0; i < len; i++) {{
      perimeterMeters += measurePoints[i].distanceTo(measurePoints[(i + 1) % len]);
    }}
    var perimeterFeet = perimeterMeters * 3.28084;

    var ptsData = measurePoints.map(function(p){{ return [p.lat, p.lng]; }});
    var ptsJson = JSON.stringify(ptsData);

    var now = new Date();
    var dateStr = now.toLocaleDateString('hi-IN', {{ day: 'numeric', month: 'long', year: 'numeric' }}) + ', ' + now.toLocaleTimeString('en-US', {{ hour: '2-digit', minute: '2-digit' }});

    var coordsRows = measurePoints.map(function(p, idx){{
      return '<tr><td><b>P' + (idx + 1) + '</b></td><td>' + p.lat.toFixed(6) + '° N</td><td>' + p.lng.toFixed(6) + '° E</td></tr>';
    }}).join('');

    // Generate precision SVG Cadastral Blueprint with aligned bounding box
    var lats = measurePoints.map(function(p){{ return p.lat; }});
    var lngs = measurePoints.map(function(p){{ return p.lng; }});
    var minLat = Math.min.apply(null, lats);
    var maxLat = Math.max.apply(null, lats);
    var minLng = Math.min.apply(null, lngs);
    var maxLng = Math.max.apply(null, lngs);
    var dLat = (maxLat - minLat) || 0.0001;
    var dLng = (maxLng - minLng) || 0.0001;

    // Pad bounding box for clean framing
    var padRatio = 0.28;
    var bMinLng = minLng - dLng * padRatio;
    var bMaxLng = maxLng + dLng * padRatio;
    var bMinLat = minLat - dLat * padRatio;
    var bMaxLat = maxLat + dLat * padRatio;
    var bDLng = bMaxLng - bMinLng;
    var bDLat = bMaxLat - bMinLat;

    // High-res static satellite imagery via official Esri ArcGIS export
    var satUrl = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export?bbox='
      + bMinLng.toFixed(6) + ',' + bMinLat.toFixed(6) + ','
      + bMaxLng.toFixed(6) + ',' + bMaxLat.toFixed(6)
      + '&bboxSR=4326&imageSR=4326&size=1020,510&format=png&transparent=false&f=image';

    // Map vertex coordinates precisely onto 680x340 viewport
    var svgPts = measurePoints.map(function(p){{
      var x = ((p.lng - bMinLng) / bDLng) * 680;
      var y = ((bMaxLat - p.lat) / bDLat) * 340;
      return {{ x: x, y: y, lat: p.lat, lng: p.lng }};
    }});

    var polyPointsAttr = svgPts.map(function(pt){{
      return pt.x.toFixed(1) + ',' + pt.y.toFixed(1);
    }}).join(' ');

    // Edge measurement labels (distances on each boundary line)
    var edgeLabelsSvg = '';
    for(var i = 0; i < len; i++) {{
      var pt1 = svgPts[i];
      var pt2 = svgPts[(i + 1) % len];
      var distM = measurePoints[i].distanceTo(measurePoints[(i + 1) % len]);
      var distFt = distM * 3.28084;
      var mx = (pt1.x + pt2.x) / 2;
      var my = (pt1.y + pt2.y) / 2;
      var distText = Math.round(distM) + 'm (' + Math.round(distFt) + 'ft)';
      var badgeW = Math.max(68, distText.length * 7 + 12);

      edgeLabelsSvg += '<g transform="translate(' + mx.toFixed(1) + ',' + my.toFixed(1) + ')">' +
        '<rect x="-' + (badgeW/2).toFixed(1) + '" y="-11" width="' + badgeW.toFixed(1) + '" height="22" rx="11" fill="#ffffff" stroke="#1b4332" stroke-width="1.8"/>' +
        '<text x="0" y="4" font-family="system-ui, sans-serif" font-size="10.5" font-weight="900" fill="#1b4332" text-anchor="middle">' + distText + '</text>' +
        '</g>';
    }}

    // Vertex corner pins
    var vertexPinsSvg = svgPts.map(function(pt, idx){{
      return '<g transform="translate(' + pt.x.toFixed(1) + ',' + pt.y.toFixed(1) + ')">' +
        '<circle cx="0" cy="0" r="14" fill="#f5b731" stroke="#071f16" stroke-width="2.5"/>' +
        '<text x="0" y="5" font-family="system-ui, sans-serif" font-size="11.5" font-weight="900" fill="#071f16" text-anchor="middle">P' + (idx + 1) + '</text>' +
        '</g>';
    }}).join('');

    // Transparent CAD Vector Overlay (satellite photo shows underneath)
    var cadSvg = '<svg viewBox="0 0 680 340" width="100%" height="100%" style="display:block;background:transparent;border-radius:8px;">' +
      '<defs>' +
      '<pattern id="grid" width="34" height="34" patternUnits="userSpaceOnUse">' +
      '<path d="M 34 0 L 0 0 0 34" fill="none" stroke="rgba(255,255,255,0.22)" stroke-width="1"/>' +
      '</pattern>' +
      '</defs>' +
      '<rect width="680" height="340" fill="url(#grid)"/>' +
      '<!-- Field Polygon -->' +
      '<polygon points="' + polyPointsAttr + '" fill="#ffd269" fill-opacity="0.32" stroke="#f5b731" stroke-width="3.5" stroke-dasharray="8 6"/>' +
      '<!-- Edge Measurement Badges -->' +
      edgeLabelsSvg +
      '<!-- Corner Pins -->' +
      vertexPinsSvg +
      '<!-- Compass Rose -->' +
      '<g transform="translate(635, 45)">' +
      '<circle cx="0" cy="0" r="18" fill="rgba(255,255,255,0.95)" stroke="#1b4332" stroke-width="1.5"/>' +
      '<path d="M0 -12 L4 0 L0 -3 L-4 0 Z" fill="#e53e3e"/>' +
      '<path d="M0 12 L4 0 L0 3 L-4 0 Z" fill="#4a5568"/>' +
      '<text x="0" y="-14" font-family="system-ui, sans-serif" font-size="9.5" font-weight="900" fill="#e53e3e" text-anchor="middle">N</text>' +
      '<text x="0" y="22" font-family="system-ui, sans-serif" font-size="7.5" font-weight="800" fill="#2d3748" text-anchor="middle">उत्तर</text>' +
      '</g>' +
      '<!-- Legend Box -->' +
      '<g transform="translate(18, 20)">' +
      '<rect x="0" y="0" width="205" height="26" rx="6" fill="rgba(7,31,22,0.85)" stroke="rgba(255,255,255,0.3)" stroke-width="1"/>' +
      '<circle cx="14" cy="13" r="5" fill="#f5b731"/>' +
      '<text x="26" y="17" font-family="system-ui, sans-serif" font-size="10.5" font-weight="700" fill="#ffffff">📐 खेत सीमा व भुजा नाप (CAD)</text>' +
      '</g>' +
      '</svg>';

    var reportHtml = '<!DOCTYPE html><html><head><meta charset="utf-8"><title>खेत नाप व HD उपग्रह नक्शा रिपोर्ट - KrashiMitra</title>' +
      '<style>' +
      '@page {{ size: A4 portrait; margin: 10mm; }}' +
      '* {{ -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; color-adjust: exact !important; box-sizing: border-box; }}' +
      'body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; color: #112211; background: #f0f4f2; margin: 0; padding: 14px; line-height: 1.5; }}' +
      '.rpt-print-bar {{ max-width: 740px; margin: 0 auto 12px; display: flex; justify-content: space-between; align-items: center; background: #1b4332; color: #fff; padding: 10px 18px; border-radius: 8px; }}' +
      '.rpt-print-btn {{ background: #f5b731; color: #071f16; border: none; font-size: 13.5px; font-weight: 800; padding: 8px 18px; border-radius: 6px; cursor: pointer; }}' +
      '.rpt-wrap {{ position: relative; max-width: 740px; margin: 0 auto; border: 2.5px solid #1b4332; border-radius: 14px; padding: 22px; background: #ffffff; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.08); }}' +
      '.rpt-watermark {{ position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%) rotate(-32deg); font-size: 52px; font-weight: 900; color: rgba(27, 67, 50, 0.04); white-space: nowrap; pointer-events: none; text-transform: uppercase; letter-spacing: 5px; z-index: 100; user-select: none; }}' +
      '.rpt-hdr {{ display: flex; align-items: center; justify-content: space-between; border-bottom: 2px solid #1b4332; padding-bottom: 12px; margin-bottom: 14px; position: relative; z-index: 2; }}' +
      '.rpt-logo-box {{ display: flex; align-items: center; gap: 12px; }}' +
      '.rpt-logo-box img {{ width: 50px; height: 50px; border-radius: 50%; border: 2px solid #52b788; }}' +
      '.rpt-brand-title {{ font-size: 22px; font-weight: 800; color: #1b4332; line-height: 1.1; }}' +
      '.rpt-brand-sub {{ font-size: 11px; color: #2d6a4f; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; margin-top: 2px; }}' +
      '.rpt-badge {{ background: #e8f5e9; color: #1b4332; border: 1.5px solid #b7e4c7; padding: 5px 12px; border-radius: 20px; font-size: 11.5px; font-weight: 800; text-align: right; }}' +
      '.rpt-sec-title {{ font-size: 14px; font-weight: 800; color: #1b4332; margin: 14px 0 8px; border-left: 4.5px solid #f5b731; padding-left: 8px; }}' +
      '.rpt-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 14px; position: relative; z-index: 2; }}' +
      '.rpt-card {{ background: #f8faf9; border: 1.5px solid #d8e6df; border-radius: 10px; padding: 8px; text-align: center; }}' +
      '.rpt-card small {{ display: block; font-size: 10.5px; color: #526b60; font-weight: 700; text-transform: uppercase; }}' +
      '.rpt-card b {{ display: block; font-size: 15px; color: #1b4332; margin-top: 2px; }}' +
      '#rpt-map-canvas {{ width: 100%; height: 340px; border-radius: 10px; border: 2px solid #1b4332; position: relative; z-index: 2; overflow: hidden; background: #e2ece6; box-shadow: 0 2px 8px rgba(0,0,0,0.12); margin-bottom: 12px; }}' +
      '.rpt-coords-table {{ width: 100%; border-collapse: collapse; font-size: 11px; margin-bottom: 14px; position: relative; z-index: 2; }}' +
      '.rpt-coords-table th {{ background: #eef6f1; color: #1b4332; padding: 5px 8px; border: 1px solid #d8e6df; text-align: left; font-weight: 700; }}' +
      '.rpt-coords-table td {{ padding: 5px 8px; border: 1px solid #d8e6df; color: #2d3748; }}' +
      '.rpt-meta {{ font-size: 11px; color: #475569; display: flex; justify-content: space-between; border-top: 1px dashed #cbd5e1; padding-top: 8px; margin-top: 10px; position: relative; z-index: 2; }}' +
      '.rpt-sig {{ margin-top: 26px; display: flex; justify-content: space-between; font-size: 11.5px; color: #475569; position: relative; z-index: 2; }}' +
      '.rpt-sig div {{ border-top: 1.5px solid #94a3b8; width: 190px; text-align: center; padding-top: 5px; font-weight: 700; color: #334e3e; }}' +
      '@media print {{ .rpt-print-bar {{ display: none; }} body {{ background: #fff; padding: 0; }} .rpt-wrap {{ border: 2px solid #1b4332; box-shadow: none; max-width: 100%; }} }}' +
      '</style></head><body>' +
      '<div class="rpt-print-bar">' +
      '<span>📄 KrashiMitra खेत नाप रिपोर्ट तैयार है</span>' +
      '<button class="rpt-print-btn" onclick="window.print()">🖨️ प्रिंट करें / PDF सेव करें</button>' +
      '</div>' +
      '<div class="rpt-wrap">' +
      '<div class="rpt-watermark">KrashiMitra.in • कृषि मित्र</div>' +
      '<div class="rpt-hdr">' +
      '<div class="rpt-logo-box">' +
      '<img src="https://krashimitra.in/assets/krashimitra_logo.png" alt="KrashiMitra Logo">' +
      '<div>' +
      '<div class="rpt-brand-title">KrashiMitra (कृषि मित्र)</div>' +
      '<div class="rpt-brand-sub">किसान खेत नाप व HD सैटेलाइट नक्शा रिपोर्ट</div>' +
      '</div></div>' +
      '<div class="rpt-badge"><span>🌐 krashimitra.in</span><br><small style="font-weight:600;color:#64748b">' + dateStr + '</small></div>' +
      '</div>' +
      '<div class="rpt-sec-title">१. खेत का क्षेत्रफल विवरण (Field Measurement Summary)</div>' +
      '<div class="rpt-grid">' +
      '<div class="rpt-card"><small>एकड़ (Acre)</small><b>' + (acres < 0.01 ? acres.toFixed(4) : acres.toFixed(2)) + ' एकड़</b></div>' +
      '<div class="rpt-card"><small>बीघा (Bigha)</small><b>' + (bigha < 0.01 ? bigha.toFixed(4) : bigha.toFixed(2)) + ' बीघा</b></div>' +
      '<div class="rpt-card"><small>हेक्टेयर (Hectare)</small><b>' + (hectares < 0.01 ? hectares.toFixed(4) : hectares.toFixed(3)) + ' हे.</b></div>' +
      '<div class="rpt-card"><small>वर्ग मीटर (Area m²)</small><b>' + Math.round(sqm).toLocaleString("en-IN") + ' m²</b></div>' +
      '</div>' +
      '<div class="rpt-sec-title">२. खेत का HD उपग्रह नक्शा (HD Satellite Field Map)</div>' +
      '<div style="font-size:12px;font-weight:700;color:#1b4332;margin-bottom:8px;">खेत का कुल घेरा (Perimeter): ~' + Math.round(perimeterMeters) + ' मीटर (' + Math.round(perimeterFeet) + ' फीट) · कुल कोने (Corners): ' + measurePoints.length + '</div>' +
      '<div id="rpt-map-canvas" style="position:relative;">' +
      '<img id="rpt-sat-img" src="' + satUrl + '" style="position:absolute;top:0;left:0;width:100%;height:100%;object-fit:cover;border-radius:8px;z-index:1;">' +
      '<div style="position:absolute;top:0;left:0;width:100%;height:100%;z-index:2;">' + cadSvg + '</div>' +
      '</div>' +
      '<div class="rpt-sec-title">३. कोनों के GPS निर्देशांक (Corner GPS Coordinates)</div>' +
      '<table class="rpt-coords-table">' +
      '<thead><tr><th>बिंदु (Point)</th><th>अक्षांश (Latitude)</th><th>देशांतर (Longitude)</th></tr></thead>' +
      '<tbody>' + coordsRows + '</tbody>' +
      '</table>' +
      '<div class="rpt-meta">' +
      '<div><strong>नक्शा स्रोत:</strong> KrashiMitra GPS &amp; Satellite Engine (Esri World Imagery)</div>' +
      '<div><strong>प्रमाणीकरण:</strong> डिजिटल किसान रिपोर्ट (krashimitra.in)</div>' +
      '</div>' +
      '<div class="rpt-sig">' +
      '<div>हस्ताक्षर (किसान / भू-स्वामी)</div>' +
      '<div>हस्ताक्षर (पटवारी / सर्वेक्षक)</div>' +
      '</div>' +
      '</div>' +
      '<' + 'script>' +
      'var hasPrinted = false;' +
      'function triggerPrint() {{ if(hasPrinted) return; hasPrinted = true; setTimeout(function(){{ window.print(); }}, 400); }}' +
      'window.onload = function() {{' +
      '  var img = document.getElementById("rpt-sat-img");' +
      '  if(img && (!img.complete || img.naturalWidth === 0)) {{' +
      '    img.onload = triggerPrint;' +
      '    img.onerror = triggerPrint;' +
      '    setTimeout(triggerPrint, 3000);' +
      '  }} else {{ triggerPrint(); }}' +
      '}};' +
      '<\\/script></body></html>';

    var pWin = window.open('', '_blank', 'width=800,height=900');
    if(pWin) {{
      pWin.document.open();
      pWin.document.write(reportHtml);
      pWin.document.close();
    }} else {{
      alert('कृपया प्रिंट विंडो खोलने के लिए पॉप-अप की अनुमति दें।');
    }}
  }}

  if(fabMeasure) fabMeasure.addEventListener('click', toggleMeasure);
  if(btnUndo) {{
    btnUndo.addEventListener('click', function(){{
      if(measurePoints.length > 0) {{
        measurePoints.pop();
        var lastMarker = measureMarkers.pop();
        if(lastMarker) map.removeLayer(lastMarker);
        renderMeasurePolygon();
      }}
    }});
  }}
  if(btnClear) btnClear.addEventListener('click', clearMeasure);
  if(btnPrint) btnPrint.addEventListener('click', printSketchReport);
  if(btnHudClose) btnHudClose.addEventListener('click', toggleMeasure);

  map.on('click', function(e){{
    if(!isMeasuring) return;
    var latlng = e.latlng;
    measurePoints.push(latlng);
    var marker = L.circleMarker(latlng, {{
      radius: 6,
      fillColor: '#f5b731',
      color: '#071f16',
      weight: 2,
      fillOpacity: 1
    }}).addTo(map);
    measureMarkers.push(marker);
    renderMeasurePolygon();
  }});

  // ── District GeoJSON & Bottom Drawer ──
  var geojsonLayer = null, allLayers = [], districtMap = {{}};
  var fabReset = document.getElementById('nk-fab-reset');
  var bottomDrawer = document.getElementById('nk-bottom-drawer');
  var drawerClose = document.getElementById('nk-drawer-close');
  var drawerTitle = document.getElementById('nk-drawer-title');
  var drawerSub = document.getElementById('nk-drawer-sub');
  var drawerWeather = document.getElementById('nk-drawer-weather');
  var drawerBhav = document.getElementById('nk-drawer-bhav');
  var drawerBhulekh = document.getElementById('nk-drawer-bhulekh');
  var drawerGaon = document.getElementById('nk-drawer-gaon');

  if(drawerClose && bottomDrawer) {{
    drawerClose.addEventListener('click', function(){{
      bottomDrawer.classList.remove('active');
    }});
  }}

  // Fills stay faint: the satellite imagery is the content, the overlay only frames it.
  // The selected district is an outline, never a wash — a 70% orange fill hid the
  // very fields the farmer zoomed in to see.
  var defaultStyle = {{ color: '#2d6a4f', weight: 1.4, fillColor: '#52b788', fillOpacity: 0.12, dashArray: null }};
  var highlightStyle = {{ color: '#f5b731', weight: 3, fillColor: '#f5b731', fillOpacity: 0, dashArray: null }};
  var dimmedStyle = {{ color: '#ffffff', weight: 0.8, fillColor: '#52b788', fillOpacity: 0, dashArray: null }};
  var hoverStyle = {{ fillColor: '#f5b731', fillOpacity: 0.15 }};
  var selectedLayer = null;

  function selectDistrict(name, autoScroll) {{
    if(!name) {{ resetView(); return; }}
    var foundKey = Object.keys(districtMap).find(function(k){{ return k.toLowerCase() === name.toLowerCase(); }});
    if(!foundKey) return;

    var item = districtMap[foundKey];
    var layer = item.layer, hiName = item.hiName, enName = item.enName, dslug = item.dslug;

    selectedLayer = layer;
    allLayers.forEach(function(l){{ l.setStyle(dimmedStyle); }});
    layer.setStyle(highlightStyle);
    if(layer.bringToFront) layer.bringToFront();

    map.fitBounds(layer.getBounds(), {{ padding: [30, 30], maxZoom: 11 }});

    if(drawerTitle) drawerTitle.innerHTML = '📍 ' + hiName + ' <small>(' + enName + ')</small>';
    if(drawerSub) drawerSub.textContent = hiName + ' जिला मानचित्र व सुविधाएं';
    if(drawerBhulekh) {{
      drawerBhulekh.href = bhulekhUrl;
      drawerBhulekh.innerHTML = '📄 ' + bhulekhTitle;
    }}
    if(drawerGaon) {{
      drawerGaon.href = '/naksha/' + stateKey + '/' + dslug + '/gaon';
      drawerGaon.style.display = 'inline-flex';
    }}
    if(bottomDrawer) bottomDrawer.classList.add('active');
    if(fabReset) fabReset.style.display = 'flex';

    if(autoScroll) {{
      var el = document.getElementById('nk-map-wrap');
      if(el) el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
    }}
  }}

  function resetView() {{
    selectedLayer = null;
    allLayers.forEach(function(l){{ l.setStyle(defaultStyle); }});
    if(geojsonLayer) map.fitBounds(geojsonLayer.getBounds(), {{ padding: map.getSize().x < 500 ? [8, 8] : [24, 24] }});
    if(bottomDrawer) bottomDrawer.classList.remove('active');
    if(fabReset) fabReset.style.display = 'none';
  }}

  if(fabReset) fabReset.addEventListener('click', resetView);

  // ── Unified Floating Search with Autocomplete ──
  var searchInput = document.getElementById('nk-search-input');
  var searchBtn = document.getElementById('nk-search-btn');
  var searchClear = document.getElementById('nk-search-clear-btn');
  var suggList = document.getElementById('nk-suggestions-list');

  function renderSuggestions(q) {{
    if(!suggList) return;
    q = (q || '').trim().toLowerCase();
    if(!q) {{
      suggList.classList.remove('active');
      suggList.innerHTML = '';
      if(searchClear) searchClear.classList.remove('visible');
      return;
    }}
    if(searchClear) searchClear.classList.add('visible');

    var matches = Object.keys(districtMap).filter(function(k){{
      var item = districtMap[k];
      return item.hiName === k && (item.hiName.toLowerCase().indexOf(q) > -1 || item.enName.toLowerCase().indexOf(q) > -1);
    }});

    if(matches.length === 0) {{
      suggList.innerHTML = '<div class="nk-sugg-item" style="color:var(--nk-text-soft)"><i>🔍 गांव/तहसील के लिए खोजें दबाएं...</i></div>';
      suggList.classList.add('active');
      return;
    }}

    var html = '';
    matches.slice(0, 7).forEach(function(k){{
      var item = districtMap[k];
      html += '<div class="nk-sugg-item" data-district="' + item.hiName + '">📍 <b>' + item.hiName + '</b> <small>' + item.enName + '</small></div>';
    }});
    suggList.innerHTML = html;
    suggList.classList.add('active');

    suggList.querySelectorAll('.nk-sugg-item[data-district]').forEach(function(el){{
      el.addEventListener('click', function(){{
        var dist = el.getAttribute('data-district');
        if(searchInput) searchInput.value = dist;
        suggList.classList.remove('active');
        selectDistrict(dist, true);
      }});
    }});
  }}

  if(searchInput) {{
    searchInput.addEventListener('input', function(){{ renderSuggestions(searchInput.value); }});
    searchInput.addEventListener('focus', function(){{ if(searchInput.value) renderSuggestions(searchInput.value); }});
  }}
  if(searchClear) {{
    searchClear.addEventListener('click', function(){{
      if(searchInput) searchInput.value = '';
      renderSuggestions('');
    }});
  }}
  document.addEventListener('click', function(e){{
    if(suggList && !e.target.closest('.nk-float-search')) {{
      suggList.classList.remove('active');
    }}
  }});

  // Search Village or Tehsil via Nominatim
  var currentSearchMarker = null;
  function searchVillageOrTehsil() {{
    if(!searchInput) return;
    var q = searchInput.value.trim();
    if(!q) return;
    if(suggList) suggList.classList.remove('active');

    // If matches district directly, select it
    var directMatch = Object.keys(districtMap).find(function(k){{
      return k.toLowerCase() === q.toLowerCase() || districtMap[k].enName.toLowerCase() === q.toLowerCase();
    }});
    if(directMatch) {{
      selectDistrict(districtMap[directMatch].hiName, true);
      return;
    }}

    var fullQuery = q + ', {s["hi"]}, India';
    fetch('https://nominatim.openstreetmap.org/search?format=json&q=' + encodeURIComponent(fullQuery))
      .then(function(r){{ return r.json(); }})
      .then(function(data){{
        if(data && data.length > 0) {{
          var place = data[0];
          var lat = parseFloat(place.lat);
          var lon = parseFloat(place.lon);

          if(!map.hasLayer(satLayer)) {{
            map.removeLayer(osmLayer);
            lowSatLayer.addTo(map);
            satLayer.addTo(map);
            labelLayer.addTo(map);
            currentLayerType = 'sat';
            if(fabLayer) fabLayer.innerHTML = '🗺️<span class="nk-fab-label">नक्शा व्यू</span>';
          }}

          nkFlyTo(lat, lon, 14);
          if(currentSearchMarker) map.removeLayer(currentSearchMarker);
          currentSearchMarker = L.marker([lat, lon]).addTo(map);
          currentSearchMarker.bindPopup('<b>🌾 ' + place.display_name + '</b>').openPopup();

          if(drawerTitle) drawerTitle.innerHTML = '🌾 ' + q;
          if(drawerSub) drawerSub.textContent = place.display_name;
          if(drawerGaon) drawerGaon.style.display = 'none';
          if(bottomDrawer) bottomDrawer.classList.add('active');
          if(fabReset) fabReset.style.display = 'flex';
        }} else {{
          alert('स्थान नहीं मिला: ' + q + '। कृपया वर्तनी जांचें।');
        }}
      }}).catch(function(e){{ console.error(e); }});
  }}

  if(searchBtn) searchBtn.addEventListener('click', searchVillageOrTehsil);
  if(searchInput) {{
    searchInput.addEventListener('keypress', function(e){{
      if(e.key === 'Enter') searchVillageOrTehsil();
    }});
  }}

  // ── Load GeoJSON Boundaries ──
  fetch('/data/{s["geojson"]}')
    .then(function(r){{ return r.json(); }})
    .then(function(g){{
      geojsonLayer = L.geoJSON(g, {{
        style: defaultStyle,
        onEachFeature: function(f, l) {{
          var hiName = f.properties.district_hi || f.properties.district || 'District';
          var enName = f.properties.district || hiName;
          var dslug = enName.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');

          allLayers.push(l);
          districtMap[hiName] = {{ layer: l, feature: f, hiName: hiName, enName: enName, dslug: dslug }};
          districtMap[enName] = {{ layer: l, feature: f, hiName: hiName, enName: enName, dslug: dslug }};

          l.bindTooltip(hiName, {{ sticky: true, className: 'nk-dist-tooltip' }});
          l.on('click', function(){{ selectDistrict(hiName, true); }});
          l.on('mouseover', function(){{
            if(l !== selectedLayer) l.setStyle(hoverStyle);
          }});
          l.on('mouseout', function(){{
            if(l === selectedLayer) return;
            l.setStyle(selectedLayer ? dimmedStyle : defaultStyle);
          }});
        }}
      }}).addTo(map);
      if(!isOverlayVisible) map.removeLayer(geojsonLayer);

      // 3-Tier Dynamic Boundary LOD on Zoom
      map.on('zoomend', function() {{
        var z = map.getZoom();
        if(geojsonLayer && isOverlayVisible && map.hasLayer(geojsonLayer)) {{
          // Restyle each layer, keeping the selection an outline at every zoom
          allLayers.forEach(function(l) {{
            if(l === selectedLayer) {{ l.setStyle(highlightStyle); return; }}
            if(z > 13) {{
              // High Zoom: Field & Farm view — no fill so satellite imagery is crystal clear
              l.setStyle({{ weight: 1.2, fillOpacity: 0, dashArray: '4, 6' }});
            }} else {{
              l.setStyle(selectedLayer ? dimmedStyle : defaultStyle);
            }}
          }});
        }}
      }});

      var fit = function(){{
        map.invalidateSize();
        if(geojsonLayer) map.fitBounds(geojsonLayer.getBounds(), {{ padding: map.getSize().x < 500 ? [8, 8] : [24, 24] }});
      }};
      fit();
      setTimeout(fit, 300);
      var t; window.addEventListener('resize', function(){{ clearTimeout(t); t = setTimeout(fit, 200); }});

      var initial = {initial_js};
      if(initial) {{
        setTimeout(function(){{ selectDistrict(initial, false); }}, 250);
      }} else {{
        var distParam = new URLSearchParams(window.location.search).get('district');
        if(distParam) setTimeout(function(){{ selectDistrict(distParam, true); }}, 400);
      }}
    }})
    .catch(function(err){{
      console.warn('GeoJSON boundary load deferred:', err);
      setTimeout(function(){{ map.invalidateSize(); }}, 200);
    }});

  // ── Mandi Explorer Layer ("मंडी देखें") ──
  var mandiLayerGroup = null;
  var isMandiActive = false;
  var mandiCachedData = null;
  var mandiBtn = document.getElementById('nk-mandi-toggle-btn');
  var mandiFabBtn = document.getElementById('nk-fab-mandi');
  var mandiFabText = document.getElementById('nk-fab-mandi-text');
  var mandiBadge = document.getElementById('nk-mandi-btn-count');

  function updateMandiBtnState(active, loading, count) {{
    isMandiActive = active;
    [mandiBtn, mandiFabBtn].forEach(function(b) {{
      if(!b) return;
      if(loading) b.classList.add('loading');
      else b.classList.remove('loading');
      if(active) b.classList.add('active');
      else b.classList.remove('active');
    }});
    if(mandiBtn) {{
      var txtEl = mandiBtn.querySelector('.nk-mandi-btn-text');
      if(txtEl) {{
        if(loading) txtEl.textContent = 'मंडी लोड हो रही है...';
        else if(active) txtEl.textContent = 'मंडी हटाएं';
        else txtEl.textContent = 'मंडी देखें';
      }}
    }}
    if(mandiFabText) {{
      if(loading) mandiFabText.textContent = 'लोड हो रहा है...';
      else if(active) mandiFabText.textContent = 'मंडी हटाएं' + (count ? ' (' + count + ')' : '');
      else mandiFabText.textContent = 'मंडी देखें';
    }}
    if(mandiBadge) {{
      if(active && count > 0) {{
        mandiBadge.textContent = count;
        mandiBadge.style.display = 'inline-flex';
      }} else {{
        mandiBadge.style.display = 'none';
      }}
    }}
  }}

  var mandiClusters = null;
  var mandiLODTimer = null;

  function buildDistrictClusters(mandis) {{
    var cMap = {{}};
    mandis.forEach(function(m) {{
      var d = m.district || 'अन्य';
      if (!cMap[d]) {{
        cMap[d] = {{
          district: d,
          state: m.state,
          latSum: 0,
          lonSum: 0,
          count: 0,
          mandis: []
        }};
      }}
      cMap[d].latSum += m.lat;
      cMap[d].lonSum += m.lon;
      cMap[d].count++;
      cMap[d].mandis.push(m);
    }});

    var clusters = [];
    Object.keys(cMap).forEach(function(k) {{
      var g = cMap[k];
      clusters.push({{
        district: g.district,
        state: g.state,
        lat: g.latSum / g.count,
        lon: g.lonSum / g.count,
        count: g.count,
        mandis: g.mandis
      }});
    }});
    return clusters;
  }}

  function buildMandiPopup(m) {{
    var cropsHtml = '';
    if(m.top_crops && m.top_crops.length > 0) {{
      cropsHtml = '<div class="nk-mandi-crop-list">';
      m.top_crops.forEach(function(c) {{
        cropsHtml += '<div class="nk-mandi-crop-row"><span class="nk-mandi-crop-name">' + c.crop + '</span><span class="nk-mandi-crop-price">' + c.price + '</span></div>';
      }});
      cropsHtml += '</div>';
    }}

    return '<div class="nk-mandi-card">' +
      '<div class="nk-mandi-card-head">' +
        '<div>' +
          '<div class="nk-mandi-card-title">' + m.market + '</div>' +
          '<div class="nk-mandi-card-subtitle">' + m.district + ', ' + m.state + '</div>' +
        '</div>' +
        '<span class="nk-mandi-card-tag">' + (m.is_exact ? 'सटीक केंद्र' : 'मंडी क्षेत्र') + '</span>' +
      '</div>' +
      cropsHtml +
      '<div class="nk-mandi-card-actions">' +
        '<a href="https://www.google.com/maps/dir/?api=1&destination=' + encodeURIComponent(m.nav_q || (m.market + ' mandi')) + '" target="_blank" rel="noopener" class="nk-mandi-card-btn nk-mandi-btn-nav">🧭 रास्ता देखें</a>' +
        '<a href="' + m.bhav_url + '" class="nk-mandi-card-btn nk-mandi-btn-bhav">📊 सभी भाव देखें</a>' +
      '</div>' +
    '</div>';
  }}

  function onMandiMapMove() {{
    if(!isMandiActive || !mandiCachedData) return;
    if(mandiLODTimer) clearTimeout(mandiLODTimer);
    mandiLODTimer = setTimeout(function() {{
      refreshMandiLOD();
    }}, 100);
  }}

  function refreshMandiLOD() {{
    if(!isMandiActive || !mandiCachedData) return;
    if(!mandiLayerGroup) {{
      mandiLayerGroup = L.layerGroup().addTo(map);
    }}
    mandiLayerGroup.clearLayers();

    var allMandis = mandiCachedData.mandis || [];
    if(allMandis.length === 0) return;

    var curZoom = map.getZoom();
    var isMultiDistrict = !districtSlug;
    var bounds = map.getBounds().pad(0.18);

    // TIER 1: State Macro Zoom (Zoom < 9 on multi-district view)
    if(isMultiDistrict && curZoom < 9) {{
      if(!mandiClusters) {{
        mandiClusters = buildDistrictClusters(allMandis);
      }}
      mandiClusters.forEach(function(c) {{
        if(!bounds.contains([c.lat, c.lon])) return;
        var clusterIcon = L.divIcon({{
          className: 'nk-mandi-cluster-wrap',
          html: '<div class="nk-mandi-cluster-badge" title="' + c.district + ' (' + c.count + ' मंडियां - ज़ूम करने के लिए टैप करें)">' +
                  '<span class="nk-cluster-ic">🏛️</span>' +
                  '<span class="nk-cluster-name">' + c.district + '</span>' +
                  '<span class="nk-cluster-count">' + c.count + '</span>' +
                '</div>',
          iconSize: [110, 32],
          iconAnchor: [55, 16]
        }});
        var marker = L.marker([c.lat, c.lon], {{ icon: clusterIcon }});
        marker.on('click', function() {{
          var b = L.latLngBounds(c.mandis.map(function(m) {{ return [m.lat, m.lon]; }}));
          map.fitBounds(b, {{ padding: [50, 50], maxZoom: 11 }});
        }});
        mandiLayerGroup.addLayer(marker);
      }});
      return;
    }}

    // Filter mandis within current visible viewport (Viewport Frustum Culling)
    var visibleMandis = allMandis.filter(function(m) {{
      return bounds.contains([m.lat, m.lon]);
    }});

    // If zoomed out or many visible, use Tier 2 Compact Badge; else Tier 3 Detailed
    var useCompact = (curZoom < 12);

    visibleMandis.forEach(function(m) {{
      var icon;
      if(useCompact) {{
        // TIER 2: Compact Mandi Pill
        icon = L.divIcon({{
          className: 'nk-mandi-compact-wrap',
          html: '<div class="nk-mandi-compact-badge" title="' + m.market + '">' +
                  '<span class="nk-compact-ic">🏛️</span>' +
                  '<span class="nk-compact-name">' + m.market + '</span>' +
                '</div>',
          iconSize: [110, 28],
          iconAnchor: [55, 14],
          popupAnchor: [0, -16]
        }});
      }} else {{
        // TIER 3: Detailed Live Price Badge
        var badgeText = (m.top_crops && m.top_crops.length)
          ? (m.top_crops[0].crop + ' ' + m.top_crops[0].price)
          : (m.crop_count ? (m.crop_count + ' फसलें') : 'मंडी');

        icon = L.divIcon({{
          className: 'nk-mandi-div-icon',
          html: '<div class="nk-mandi-marker-wrap">' +
                  '<div class="nk-mandi-pin-badge">🌾 ' + badgeText + '</div>' +
                  '<div class="nk-mandi-pin-icon-box"><span class="nk-mandi-pin-icon">🏛️</span></div>' +
                '</div>',
          iconSize: [120, 50],
          iconAnchor: [60, 50],
          popupAnchor: [0, -52]
        }});
      }}

      var marker = L.marker([m.lat, m.lon], {{ icon: icon }});
      marker.bindPopup(function() {{ return buildMandiPopup(m); }}, {{ className: 'nk-mandi-popup', maxWidth: 300 }});
      mandiLayerGroup.addLayer(marker);
    }});
  }}

  function toggleMandis() {{
    if(isMandiActive) {{
      isMandiActive = false;
      map.off('zoomend moveend', onMandiMapMove);
      if(mandiLayerGroup) {{
        map.removeLayer(mandiLayerGroup);
        mandiLayerGroup.clearLayers();
      }}
      updateMandiBtnState(false, false, 0);
      return;
    }}

    if(mandiCachedData) {{
      renderMandiMarkers(mandiCachedData);
      return;
    }}

    updateMandiBtnState(false, true, 0);
    var targetDslug = districtSlug || '';
    var url = '/api/naksha/mandis?state=' + encodeURIComponent(stateKey);
    if(targetDslug) url += '&district=' + encodeURIComponent(targetDslug);

    fetch(url)
      .then(function(r) {{ return r.json(); }})
      .then(function(res) {{
        if(res && res.ok && res.mandis) {{
          mandiCachedData = res;
          renderMandiMarkers(res);
        }} else {{
          updateMandiBtnState(false, false, 0);
          alert('इस क्षेत्र की मंडियां प्राप्त नहीं हो सकीं।');
        }}
      }})
      .catch(function(err) {{
        console.error('Mandi fetch error:', err);
        updateMandiBtnState(false, false, 0);
        alert('मंडी डेटा लोड करने में समस्या हुई। कृपया पुनः प्रयास करें।');
      }});
  }}

  function renderMandiMarkers(data) {{
    isMandiActive = true;
    mandiClusters = null;
    var list = data.mandis || [];
    if(list.length === 0) {{
      updateMandiBtnState(false, false, 0);
      alert('इस क्षेत्र में अभी कोई सक्रिय मंडी दर्ज नहीं है।');
      return;
    }}

    if(!mandiLayerGroup) {{
      mandiLayerGroup = L.layerGroup().addTo(map);
    }}

    refreshMandiLOD();
    map.on('zoomend moveend', onMandiMapMove);
    updateMandiBtnState(true, false, list.length);

    if(districtSlug && list.length > 0) {{
      try {{
        var groupBounds = L.latLngBounds(list.map(function(m) {{ return [m.lat, m.lon]; }}));
        if(groupBounds.isValid()) {{
          map.fitBounds(groupBounds, {{ padding: [40, 40], maxZoom: 12 }});
        }}
      }} catch(e) {{}}
    }}
  }}

  // ── "रास्ता देखें": route from the farmer to the nearest mandi ──
  // Same three-layer draw as /bhav's map: glow, road line, and a comet that
  // rides the head of the reveal once and is then discarded.
  var nkRouteGlow = null, nkRouteLine = null, nkRouteFlow = null, nkRouteRaf = null;
  var nkRouteEnds = null, nkAltLayers = [], nkRouteChoices = null;
  var routeBtn = document.getElementById('nk-route-btn');
  var routeBtnText = document.getElementById('nk-route-btn-text');
  var routeCard = document.getElementById('nk-route-card');

  function nkKm(lat1, lon1, lat2, lon2) {{
    var R = 6371;
    var dLat = (lat2 - lat1) * Math.PI / 180;
    var dLon = (lon2 - lon1) * Math.PI / 180;
    var a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
            Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
            Math.sin(dLon / 2) * Math.sin(dLon / 2);
    return R * (2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a)));
  }}

  function nkRouteBusy(on) {{
    if(!routeBtn) return;
    if(on) routeBtn.classList.add('loading');
    else routeBtn.classList.remove('loading');
    if(routeBtnText) routeBtnText.textContent = on ? 'खोज रहे हैं…' : 'रास्ता देखें';
  }}

  function nkClearRoute() {{
    if(nkRouteRaf) {{ cancelAnimationFrame(nkRouteRaf); nkRouteRaf = null; }}
    [nkRouteGlow, nkRouteLine, nkRouteFlow].forEach(function(l) {{
      if(l && map) map.removeLayer(l);
    }});
    nkRouteGlow = nkRouteLine = nkRouteFlow = null;
    nkAltLayers.forEach(function(l) {{ if(l && map) map.removeLayer(l); }});
    nkAltLayers = [];
    if(nkRouteEnds && map) {{ map.removeLayer(nkRouteEnds); nkRouteEnds = null; }}
    if(routeCard) routeCard.classList.remove('show');
    if(routeBtn) routeBtn.classList.remove('active');
  }}

  function nkPathEl(layer) {{
    if(!layer) return null;
    return layer.getElement ? layer.getElement() : (layer._path || null);
  }}

  function nkDrawRoute(coords, uLat, uLon, mLat, mLon, approx) {{
    nkClearRoute();
    nkRouteGlow = L.polyline(coords, {{
      color: '#1967d2', weight: 9, opacity: approx ? 0.5 : 0.9, lineCap: 'round', lineJoin: 'round'
    }}).addTo(map);
    nkRouteLine = L.polyline(coords, {{
      color: '#4285f4', weight: 5.5, opacity: 1,
      dashArray: approx ? '9 9' : null, lineCap: 'round', lineJoin: 'round'
    }}).addTo(map);
    nkRouteFlow = L.polyline(coords, {{
      color: '#a8c7fa', weight: 5.5, opacity: 0.95,
      className: 'nk-route-flow', lineCap: 'round', lineJoin: 'round'
    }}).addTo(map);

    // Both ends get a marker, the way a directions result always shows where
    // it starts and where it stops.
    nkRouteEnds = L.layerGroup([
      L.marker([uLat, uLon], {{ icon: L.divIcon({{ className: 'nk-rt-start-wrap', html: '<div class="nk-rt-start"></div>', iconSize: [15, 15], iconAnchor: [7, 7] }}), interactive: false }}),
      L.marker([mLat, mLon], {{ icon: L.divIcon({{ className: 'nk-rt-dest', html: '<svg width="26" height="34" viewBox="0 0 24 32"><path d="M12 0C5.4 0 0 5.4 0 12c0 8.4 12 20 12 20s12-11.6 12-20c0-6.6-5.4-12-12-12z" fill="#ea4335"/><circle cx="12" cy="12" r="4.6" fill="#fff"/></svg>', iconSize: [26, 34], iconAnchor: [13, 33] }}), interactive: false }})
    ]).addTo(map);

    var gEl = nkPathEl(nkRouteGlow), lEl = nkPathEl(nkRouteLine), fEl = nkPathEl(nkRouteFlow);
    [gEl, lEl, fEl].forEach(function(el) {{ if(el) el.style.visibility = 'hidden'; }});

    var reduceMotion = false;
    try {{ reduceMotion = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches); }} catch(e) {{}}

    function finish() {{
      nkRouteRaf = null;
      [lEl, gEl].forEach(function(el) {{
        if(!el) return;
        el.style.visibility = '';
        el.style.strokeDasharray = (el === lEl && approx) ? '9 9' : 'none';
        el.style.strokeDashoffset = '';
      }});
      if(fEl) {{
        fEl.style.visibility = '';
        if(fEl.classList) fEl.classList.add('is-done');
      }}
      setTimeout(function() {{
        if(nkRouteFlow && map) {{ map.removeLayer(nkRouteFlow); nkRouteFlow = null; }}
      }}, 500);
    }}

    // Frame by frame off the live path length: Leaflet reprojects the path on
    // every zoom step, so a CSS transition would stutter as the map settles.
    function run() {{
      var probe = fEl || lEl;
      var len0 = 0;
      try {{ len0 = probe && probe.getTotalLength ? probe.getTotalLength() : 0; }} catch(e) {{}}
      if(reduceMotion || !len0) {{ finish(); return; }}
      [gEl, lEl, fEl].forEach(function(el) {{ if(el) el.style.visibility = ''; }});
      var dur = Math.max(3000, Math.min(7000, len0 * 5.5));
      var t0 = 0;
      function frame(ts) {{
        if(!t0) t0 = ts;
        var p = Math.min(1, (ts - t0) / dur);
        var e = p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2;
        var len = len0;
        try {{ len = probe.getTotalLength() || len0; }} catch(err) {{}}
        var head = e * len;
        [lEl, gEl].forEach(function(el) {{
          if(!el) return;
          el.style.strokeDasharray = len + ' ' + len;
          el.style.strokeDashoffset = String(len - head);
        }});
        if(fEl) {{
          var tail = Math.max(34, len * 0.18);
          fEl.style.strokeDasharray = tail + ' ' + (len + tail);
          fEl.style.strokeDashoffset = String(tail - head);
        }}
        if(p < 1) nkRouteRaf = requestAnimationFrame(frame);
        else finish();
      }}
      nkRouteRaf = requestAnimationFrame(frame);
    }}

    var started = false;
    function kick() {{
      if(started) return;
      started = true;
      map.off('moveend', kick);
      requestAnimationFrame(run);
    }}
    map.on('moveend', kick);
    setTimeout(kick, 3000);

    var b = L.latLngBounds(coords);
    b.extend([uLat, uLon]);
    b.extend([mLat, mLon]);
    var opts = {{ paddingTopLeft: [40, 110], paddingBottomRight: [45, 120], maxZoom: 14 }};
    var reduceFly = false;
    try {{ reduceFly = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches); }} catch(e) {{}}
    if(reduceFly || !map.flyToBounds) map.fitBounds(b, opts);
    else {{
      opts.duration = 1.5;
      opts.easeLinearity = 0.22;
      map.flyToBounds(b, opts);
    }}
  }}

  // ── The directions panel ──
  // /bhav always routes to the mandi its page is about; here the farmer names
  // both ends, so each field carries either a resolved point or free text that
  // still has to be geocoded.
  var routePanel = document.getElementById('nk-route-panel');
  var rpFrom = document.getElementById('nk-rp-from');
  var rpTo = document.getElementById('nk-rp-to');
  var rpNote = document.getElementById('nk-rp-note');
  var rpGo = document.getElementById('nk-rp-go');
  var pickOverlay = document.getElementById('nk-pick-overlay');
  var pickHint = document.getElementById('nk-pick-hint');
  var nkFrom = null, nkTo = null, nkPickFor = null;

  function nkNote(msg, isErr) {{
    if(!rpNote) return;
    rpNote.textContent = msg || '';
    if(isErr) rpNote.classList.add('err');
    else rpNote.classList.remove('err');
  }}

  function nkPanelOpen(on) {{
    if(!routePanel) return;
    if(on) routePanel.classList.add('open');
    else {{ routePanel.classList.remove('open'); nkPickMode(null); }}
    if(routeBtn) {{
      if(on) routeBtn.classList.add('active');
      else if(!nkRouteLine) routeBtn.classList.remove('active');
    }}
  }}

  function nkSetPoint(which, lat, lon, label) {{
    var pt = {{ lat: lat, lon: lon, label: label || (lat.toFixed(4) + ', ' + lon.toFixed(4)) }};
    if(which === 'from') {{ nkFrom = pt; if(rpFrom) rpFrom.value = pt.label; }}
    else {{ nkTo = pt; if(rpTo) rpTo.value = pt.label; }}
  }}

  function nkPickMode(which) {{
    nkPickFor = which;
    if(!pickOverlay) return;
    if(which) {{
      if(pickHint) pickHint.textContent = which === 'from'
        ? 'शुरुआत की जगह नक्शे पर टैप करें'
        : 'मंज़िल नक्शे पर टैप करें';
      pickOverlay.classList.add('active');
    }} else {{
      pickOverlay.classList.remove('active');
    }}
  }}

  if(pickOverlay) pickOverlay.addEventListener('click', function(ev) {{
    if(!nkPickFor || !map) return;
    var r = map.getContainer().getBoundingClientRect();
    var ll = map.containerPointToLatLng(L.point(ev.clientX - r.left, ev.clientY - r.top));
    var which = nkPickFor;
    nkSetPoint(which, ll.lat, ll.lng, 'नक्शे पर चुनी जगह');
    nkPickMode(null);
    nkNote('');
    // Name it the way a dropped pin names itself, so the card reads as places
    fetch('https://api.bigdatacloud.net/data/reverse-geocode-client?latitude=' + ll.lat + '&longitude=' + ll.lng + '&localityLanguage=hi')
      .then(function(r) {{ return r.json(); }})
      .then(function(d) {{
        var nm = d.locality || d.city || d.principalSubdivision || '';
        if(nm) nkSetPoint(which, ll.lat, ll.lng, nm);
      }})
      .catch(function() {{}});
  }});

  // Free text is geocoded through the same Nominatim the search box uses, but
  // biased to what is on screen so "Bara" means the nearby one.
  function nkGeocode(q, cb) {{
    var url = 'https://nominatim.openstreetmap.org/search?format=json&limit=1&q=' + encodeURIComponent(q);
    try {{
      var b = map.getBounds();
      url += '&viewbox=' + b.getWest().toFixed(4) + ',' + b.getNorth().toFixed(4) + ',' +
             b.getEast().toFixed(4) + ',' + b.getSouth().toFixed(4);
    }} catch(e) {{}}
    fetch(url)
      .then(function(r) {{ return r.json(); }})
      .then(function(d) {{
        if(d && d.length) cb(parseFloat(d[0].lat), parseFloat(d[0].lon), String(d[0].display_name || q).split(',')[0]);
        else cb(null);
      }})
      .catch(function() {{ cb(null); }});
  }}

  function nkMyLocation(cb) {{
    if(gpsMarker) {{ var p = gpsMarker.getLatLng(); cb(p.lat, p.lng); return; }}
    try {{
      var stored = JSON.parse(localStorage.getItem('km_geo') || 'null');
      if(stored && stored.lat && stored.lon && (Date.now() - (stored.ts || 0) < 7 * 86400000)) {{
        cb(stored.lat, stored.lon);
        return;
      }}
    }} catch(e) {{}}
    if(!navigator.geolocation) {{ cb(null); return; }}
    if(fabGps) fabGps.classList.add('loading');
    navigator.geolocation.getCurrentPosition(function(pos) {{
      if(fabGps) fabGps.classList.remove('loading');
      cb(pos.coords.latitude, pos.coords.longitude);
    }}, function() {{
      if(fabGps) fabGps.classList.remove('loading');
      cb(null);
    }}, {{ enableHighAccuracy: false, timeout: 10000, maximumAge: 600000 }});
  }}

  function nkRouteMandis(cb) {{
    if(mandiCachedData && mandiCachedData.mandis) {{ cb(mandiCachedData.mandis); return; }}
    var url = '/api/naksha/mandis?state=' + encodeURIComponent(stateKey);
    if(districtSlug) url += '&district=' + encodeURIComponent(districtSlug);
    fetch(url)
      .then(function(r) {{ return r.json(); }})
      .then(function(res) {{
        if(res && res.ok && res.mandis && res.mandis.length) {{ mandiCachedData = res; cb(res.mandis); }}
        else cb([]);
      }})
      .catch(function() {{ cb([]); }});
  }}

  function nkNearestMandi(lat, lon, cb) {{
    nkRouteMandis(function(list) {{
      if(!list.length) {{ cb(null); return; }}
      var near = null, best = Infinity;
      list.forEach(function(m) {{
        var d = nkKm(lat, lon, m.lat, m.lon);
        if(d < best) {{ best = d; near = m; }}
      }});
      cb(near);
    }});
  }}

  // District names come from the map itself; villages and everything else fall
  // through to the geocoder on submit.
  function nkSuggest(which) {{
    var input = which === 'from' ? rpFrom : rpTo;
    var box = document.getElementById('nk-rp-' + which + '-sugg');
    if(!input || !box) return;
    var q = (input.value || '').trim().toLowerCase();
    if(q.length < 2) {{ box.classList.remove('active'); box.innerHTML = ''; return; }}
    var hits = Object.keys(districtMap).filter(function(k) {{
      var it = districtMap[k];
      return it.hiName === k && (it.hiName.toLowerCase().indexOf(q) > -1 || it.enName.toLowerCase().indexOf(q) > -1);
    }}).slice(0, 5);
    if(!hits.length) {{ box.classList.remove('active'); box.innerHTML = ''; return; }}
    box.innerHTML = hits.map(function(k) {{
      return '<div data-k="' + k + '">📍 ' + k + ' <small>' + districtMap[k].enName + '</small></div>';
    }}).join('');
    box.classList.add('active');
    box.querySelectorAll('div[data-k]').forEach(function(el) {{
      el.addEventListener('click', function() {{
        var k = el.getAttribute('data-k');
        var lyr = districtMap[k] && districtMap[k].layer;
        var c = null;
        try {{ c = lyr && lyr.getBounds ? lyr.getBounds().getCenter() : null; }} catch(e) {{}}
        if(c) nkSetPoint(which, c.lat, c.lng, k);
        else if(input) input.value = k;
        box.classList.remove('active');
      }});
    }});
  }}

  function nkResolve(which, cb) {{
    var input = which === 'from' ? rpFrom : rpTo;
    var pt = which === 'from' ? nkFrom : nkTo;
    var txt = input ? (input.value || '').trim() : '';
    if(pt && pt.label === txt) {{ cb(pt); return; }}
    if(!txt) {{ cb(null); return; }}
    nkGeocode(txt, function(lat, lon, name) {{
      if(lat === null || lat === undefined) {{ cb(null); return; }}
      var p = {{ lat: lat, lon: lon, label: name || txt }};
      if(which === 'from') nkFrom = p; else nkTo = p;
      if(input) input.value = p.label;
      cb(p);
    }});
  }}

  function nkRunRoute() {{
    nkNote('रास्ता खोजा जा रहा है…');
    if(rpGo) rpGo.disabled = true;
    nkResolve('from', function(a) {{
      if(!a) {{ if(rpGo) rpGo.disabled = false; nkNote('शुरुआत की जगह नहीं मिली — दूसरा नाम आज़माएं या नक्शे पर चुनें।', true); return; }}
      nkResolve('to', function(b) {{
        if(!b) {{ if(rpGo) rpGo.disabled = false; nkNote('मंज़िल नहीं मिली — दूसरा नाम आज़माएं या नक्शे पर चुनें।', true); return; }}
        nkDrawOsrm(a, b);
      }});
    }});
  }}

  function nkFmtMins(mins) {{
    return mins >= 60 ? (Math.floor(mins / 60) + ' घंटा ' + (mins % 60) + ' मिनट') : (mins + ' मिनट');
  }}

  function nkMins(km) {{
    var speed = km < 30 ? 32 : (km < 100 ? 44 : 54);
    return Math.round((km / speed) * 60);
  }}

  function nkFillCard(a, b, km, mins, approx) {{
    var labelEl = document.getElementById('nk-route-label');
    var nameEl = document.getElementById('nk-route-mandi');
    var distEl = document.getElementById('nk-route-dist');
    var navEl = document.getElementById('nk-route-nav');
    if(labelEl) labelEl.textContent = 'रास्ता';
    if(nameEl) nameEl.textContent = a.label + ' → ' + b.label;
    if(navEl) navEl.href = 'https://www.google.com/maps/dir/?api=1&origin=' + a.lat.toFixed(5) + ',' + a.lon.toFixed(5) +
                           '&destination=' + b.lat.toFixed(5) + ',' + b.lon.toFixed(5) + '&travelmode=driving';
    if(distEl) {{
      distEl.innerHTML = 'दूरी: <b>' + km + ' किमी</b> · लगभग ' + nkFmtMins(mins) +
                         (approx ? ' (अनुमानित)' : ' (सड़क मार्ग)');
    }}
    if(bottomDrawer) bottomDrawer.classList.remove('active');
    if(routeCard) routeCard.classList.add('show');
    if(routeBtn) routeBtn.classList.add('active');
    if(rpGo) rpGo.disabled = false;
    nkNote('');
    nkPanelOpen(false);
  }}

  // OSRM returns up to three ways round; the ones not taken stay on the map in
  // grey with their travel time, and tapping one switches to it.
  function nkSelectRoute(idx) {{
    if(!nkRouteChoices) return;
    var c = nkRouteChoices;
    c.idx = idx;
    var r = c.routes[idx];
    var coords = r.geometry.coordinates.map(function(pt) {{ return [pt[1], pt[0]]; }});
    nkDrawRoute(coords, c.a.lat, c.a.lon, c.b.lat, c.b.lon, false);
    c.routes.forEach(function(alt, i) {{
      if(i === idx) return;
      var altCoords = alt.geometry.coordinates.map(function(pt) {{ return [pt[1], pt[0]]; }});
      var line = L.polyline(altCoords, {{
        color: '#9aa0a6', weight: 5, opacity: 0.85, lineCap: 'round', lineJoin: 'round'
      }}).addTo(map);
      line.on('click', function() {{ nkSelectRoute(i); }});
      nkAltLayers.push(line);
      var mid = altCoords[Math.floor(altCoords.length / 2)];
      var altKm = alt.distance / 1000;
      var tag = L.marker(mid, {{
        icon: L.divIcon({{ className: 'nk-rt-alt-wrap', html: '<span class="nk-rt-alt-label">' + nkFmtMins(nkMins(altKm)) + ' · ' + altKm.toFixed(0) + ' किमी</span>', iconSize: null }})
      }}).addTo(map);
      tag.on('click', function() {{ nkSelectRoute(i); }});
      nkAltLayers.push(tag);
    }});
    var km = (r.distance / 1000).toFixed(1);
    nkFillCard(c.a, c.b, km, nkMins(parseFloat(km)), false);
  }}

  function nkDrawOsrm(a, b) {{
    var straight = nkKm(a.lat, a.lon, b.lat, b.lon);
    // See /bhav: full geometry is ~46x the bytes on a long haul and the extra
    // points are invisible at the zoom a long route fits into.
    var ovDetail = straight > 60 ? 'simplified' : 'full';
    var osrm = 'https://router.project-osrm.org/route/v1/driving/' +
               a.lon.toFixed(5) + ',' + a.lat.toFixed(5) + ';' +
               b.lon.toFixed(5) + ',' + b.lat.toFixed(5) +
               '?overview=' + ovDetail + '&geometries=geojson&alternatives=true';
    fetch(osrm)
      .then(function(r) {{ return r.json(); }})
      .then(function(data) {{
        var rs = (data && data.routes ? data.routes : []).filter(function(r) {{ return r && r.geometry; }});
        if(rs.length) {{
          nkRouteChoices = {{ routes: rs.slice(0, 3), idx: 0, a: a, b: b }};
          nkSelectRoute(0);
        }} else {{ nkFallback(a, b, straight); }}
      }})
      .catch(function() {{ nkFallback(a, b, straight); }});
  }}

  function nkFallback(a, b, straight) {{
    nkRouteChoices = null;
    var estKm = (straight * 1.30).toFixed(1);
    nkDrawRoute([[a.lat, a.lon], [b.lat, b.lon]], a.lat, a.lon, b.lat, b.lon, true);
    nkFillCard(a, b, estKm, nkMins(parseFloat(estKm)), true);
  }}

  if(routeBtn) routeBtn.addEventListener('click', function() {{
    var isOpen = routePanel && routePanel.classList.contains('open');
    if(isOpen) {{ nkPanelOpen(false); return; }}
    nkPanelOpen(true);
    nkNote('');
    if(rpFrom && !rpFrom.value) {{
      nkMyLocation(function(lat, lon) {{
        if(lat !== null && lat !== undefined && !rpFrom.value) nkSetPoint('from', lat, lon, 'मेरी लोकेशन');
      }});
    }}
  }});

  var rpCloseBtn = document.getElementById('nk-rp-close');
  if(rpCloseBtn) rpCloseBtn.addEventListener('click', function() {{ nkPanelOpen(false); }});
  if(rpGo) rpGo.addEventListener('click', nkRunRoute);
  if(rpFrom) {{
    rpFrom.addEventListener('input', function() {{ nkFrom = null; nkSuggest('from'); }});
    rpFrom.addEventListener('keydown', function(e) {{ if(e.key === 'Enter') nkRunRoute(); }});
  }}
  if(rpTo) {{
    rpTo.addEventListener('input', function() {{ nkTo = null; nkSuggest('to'); }});
    rpTo.addEventListener('keydown', function(e) {{ if(e.key === 'Enter') nkRunRoute(); }});
  }}

  var rpSwapBtn = document.getElementById('nk-rp-swap');
  if(rpSwapBtn) rpSwapBtn.addEventListener('click', function() {{
    var a = nkFrom, av = rpFrom ? rpFrom.value : '';
    nkFrom = nkTo; if(rpFrom) rpFrom.value = rpTo ? rpTo.value : '';
    nkTo = a; if(rpTo) rpTo.value = av;
  }});

  if(routePanel) routePanel.querySelectorAll('.nk-rp-chip').forEach(function(chip) {{
    chip.addEventListener('click', function() {{
      var pick = chip.getAttribute('data-pick');
      if(pick) {{ nkPickMode(pick); return; }}
      if(chip.getAttribute('data-from') === 'gps') {{
        nkNote('लोकेशन खोजी जा रही है…');
        nkMyLocation(function(lat, lon) {{
          if(lat === null || lat === undefined) {{ nkNote('लोकेशन नहीं मिली — नक्शे पर चुनें या जगह का नाम लिखें।', true); return; }}
          nkSetPoint('from', lat, lon, 'मेरी लोकेशन');
          nkNote('');
        }});
        return;
      }}
      if(chip.getAttribute('data-to') === 'mandi') {{
        nkNote('नजदीकी मंडी खोजी जा रही है…');
        nkResolve('from', function(a) {{
          function pick(lat, lon) {{
            nkNearestMandi(lat, lon, function(m) {{
              if(!m) {{ nkNote('इस क्षेत्र की मंडी की जानकारी अभी उपलब्ध नहीं है।', true); return; }}
              nkSetPoint('to', Number(m.lat), Number(m.lon), m.market || 'मंडी');
              nkNote('');
            }});
          }}
          if(a) pick(a.lat, a.lon);
          else nkMyLocation(function(lat, lon) {{
            if(lat === null || lat === undefined) {{ nkNote('पहले शुरुआत की जगह भरें।', true); return; }}
            nkSetPoint('from', lat, lon, 'मेरी लोकेशन');
            pick(lat, lon);
          }});
        }});
      }}
    }});
  }});

  var routeCloseBtn = document.getElementById('nk-route-close');
  if(routeCloseBtn) routeCloseBtn.addEventListener('click', nkClearRoute);

  if(mandiBtn) mandiBtn.addEventListener('click', toggleMandis);
  if(mandiFabBtn) mandiFabBtn.addEventListener('click', toggleMandis);
  }}

  if(document.readyState === 'loading') {{
    document.addEventListener('DOMContentLoaded', initMap);
  }} else {{
    initMap();
  }}
  window.addEventListener('load', initMap);
}})();
</script>""")
    return "\n".join(out)


# ── Mandi API for Interactive Naksha Map ────────────────────────────────────

_mandi_cache: dict[str, dict] = {}
_mandi_cache_ts: dict[str, float] = {}
_MANDI_CACHE_TTL = 1800.0  # 30 minutes cache


@router.get("/api/naksha/mandis")
def api_naksha_mandis(state: str = "", district: str = ""):
    """Return APMC mandis for a given state and/or district with coordinates,
    top commodities & prices, and navigation info. Fast, cached response."""
    from backend.database.db import SessionLocal, MandiPrice
    from backend.services import district_geo
    from backend.routes.bhav import _hindi_name

    cache_key = f"{(state or '').strip().lower()}|{(district or '').strip().lower()}"
    now = time.time()
    if cache_key in _mandi_cache and (now - _mandi_cache_ts.get(cache_key, 0)) < _MANDI_CACHE_TTL:
        return _mandi_cache[cache_key]

    states_meta = _states()

    # 1. Resolve State
    st_raw = (state or "").strip()
    st_slug = st_raw.lower()
    st_meta = states_meta.get(st_slug)
    if not st_meta:
        for k, v in states_meta.items():
            if v.get("en", "").lower() == st_slug or v.get("hi") == st_raw:
                st_slug = k
                st_meta = v
                break

    st_en = st_meta["en"] if st_meta else st_raw
    st_hi = st_meta["hi"] if st_meta else st_raw
    if not st_slug and st_en:
        st_slug = slugify(st_en)

    # 2. Resolve District (if provided)
    dist_en = ""
    dist_hi = ""
    dist_slug = ""
    if district:
        d_raw = district.strip()
        d_idx = _dindex(st_slug) if st_slug in states_meta else {}
        if d_raw.lower() in d_idx:
            dist_slug = d_raw.lower()
            dist_en = d_idx[dist_slug]["en"]
            dist_hi = d_idx[dist_slug]["hi"]
        else:
            for dslug, dinfo in d_idx.items():
                if dinfo["en"].lower() == d_raw.lower() or dinfo["hi"] == d_raw:
                    dist_slug = dslug
                    dist_en = dinfo["en"]
                    dist_hi = dinfo["hi"]
                    break
            if not dist_en:
                dist_en = d_raw
                dist_slug = slugify(d_raw)
                dist_hi = d_raw

    # 3. Query DB
    db = SessionLocal()
    try:
        q = db.query(
            MandiPrice.state,
            MandiPrice.district,
            MandiPrice.market,
            MandiPrice.commodity,
            MandiPrice.modal_price,
            MandiPrice.min_price,
            MandiPrice.max_price,
            MandiPrice.arrival_date,
        )
        if st_en:
            q = q.filter(MandiPrice.state.ilike(st_en))
        if dist_en:
            q = q.filter(MandiPrice.district.ilike(dist_en))
        rows = q.all()
    finally:
        db.close()

    # 4. Group by (district, market)
    by_mkt: dict = {}
    for st_val, d_val, mkt, com, modal, p_min, p_max, arr_date in rows:
        mkt = (mkt or "").strip()
        if not mkt or mkt == "-":
            continue
        d_val = (d_val or dist_en or "").strip()
        key = (d_val.lower(), mkt.lower())
        if key not in by_mkt:
            by_mkt[key] = {
                "state": st_val or st_en,
                "district": d_val,
                "market": mkt,
                "crops": {},
                "dates": set(),
            }
        slot = by_mkt[key]
        if arr_date:
            slot["dates"].add(arr_date)
        if com:
            try:
                m_num = int(float(str(modal).replace(",", "").strip())) if modal else 0
            except (ValueError, TypeError):
                m_num = 0
            if com not in slot["crops"] or (m_num and m_num > slot["crops"][com].get("modal_num", 0)):
                slot["crops"][com] = {
                    "crop_en": com,
                    "crop_hi": _hindi_name(com),
                    "modal_num": m_num,
                    "modal": f"₹{m_num:,}" if m_num else (f"₹{modal}" if modal else "—"),
                }

    # 5. Build marker list with coordinates
    mandis = []
    for (d_low, m_low), data in by_mkt.items():
        coords = district_geo.resolve_mandi_coords(data["state"], data["district"], data["market"])
        if not coords:
            continue
        lat, lon, is_exact = coords

        sorted_crops = sorted(data["crops"].values(), key=lambda c: -c["modal_num"])
        top_crops = [
            {"crop": c["crop_hi"], "price": c["modal"]}
            for c in sorted_crops[:4]
        ]

        clean_name = re.sub(
            r'(?i)\b(apmc|mandi|grain market|sub yard|upaj mandi|sub market yard|market yard|main yard|yard)\b',
            '', data["market"]
        ).strip()
        clean_name = re.sub(r'[\(\)\[\]\-]+', ' ', clean_name).strip() or data["market"]

        d_s = slugify(data["district"])
        s_s = st_slug or slugify(data["state"])
        bhav_url = f"/bhav/rajya/{s_s}/{d_s}" if s_s and d_s else "/bhav"

        nav_q = f"{data['market']}, {data['district']}, {data['state']} mandi"

        mandis.append({
            "market": data["market"],
            "name": clean_name,
            "district": data["district"],
            "state": data["state"],
            "lat": round(lat, 5),
            "lon": round(lon, 5),
            "is_exact": is_exact,
            "crop_count": len(data["crops"]),
            "top_crops": top_crops,
            "bhav_url": bhav_url,
            "nav_q": nav_q,
        })

    mandis.sort(key=lambda m: -m["crop_count"])
    result = {
        "ok": True,
        "state": st_en,
        "state_slug": st_slug,
        "district": dist_en,
        "count": len(mandis),
        "mandis": mandis,
    }
    _mandi_cache[cache_key] = result
    _mandi_cache_ts[cache_key] = now
    return result


# ── hub ─────────────────────────────────────────────────────────────────────

# Declared before /naksha/{state}: that wildcard matches any single segment,
# including this filename, and would answer the sitemap with the "state not
# found" HTML page. The builder itself lives in sitemap.py with its siblings.
@router.get("/naksha/gaon-sitemap.xml")
def gaon_sitemap():
    from fastapi.responses import Response
    from backend.routes.sitemap import build_gaon_sitemap
    return Response(build_gaon_sitemap(), media_type="application/xml",
                    headers={"Cache-Control": "public, max-age=3600"})


@router.get("/naksha", response_class=HTMLResponse)
@router.get("/naksha/", response_class=HTMLResponse)
def naksha_hub():
    states = _states()
    total_d = sum(s["n"] for s in states.values())
    n_states = len(states)

    # Build regional groups
    regions: dict[str, list] = {}
    for k, s in states.items():
        regions.setdefault(s["region"], []).append(k)

    popular_keys = [k for k in _POPULAR if k in states]

    def _state_pick_card(k: str) -> str:
        s = states[k]
        return (
            f'<a class="nk-pick-card" href="{_url(k)}" data-state="{k}" '
            f'data-hi="{escape(s["hi"])}">'
            f'<span class="nk-pick-name">{escape(s["hi"])}</span>'
            f'<span class="nk-pick-count">{_jile(_now_n(k, s))}</span>'
            f'<span class="nk-pick-arrow">›</span>'
            f'</a>'
        )

    popular_html = "".join(_state_pick_card(k) for k in popular_keys)

    region_html_parts = []
    for region in _REGION_ORDER:
        if region not in regions:
            continue
        keys = regions[region]
        cards = "".join(_state_pick_card(k) for k in keys)
        region_html_parts.append(
            f'<div class="nk-region-group" data-region="{escape(region)}">'
            f'<h3 class="nk-region-head">{escape(region)}</h3>'
            f'<div class="nk-pick-grid">{cards}</div>'
            f'</div>'
        )
    all_regions_html = "".join(region_html_parts)

    title = f"भारत के राज्यों के नक्शे – {n_states} राज्यों का जिलेवार HD मानचित्र (मुफ्त)"
    desc = (f"भारत के सभी {n_states} राज्यों और केंद्र शासित प्रदेशों के जिलेवार नक्शे "
            f"हिंदी में — कुल {total_d} जिले। हर नक्शा HD PNG में मुफ्त डाउनलोड करें "
            f"और अपना जिला ढूंढें।")

    faq_html, faq_ld = _faq([
        ("क्या ये नक्शे मुफ्त हैं?",
         "हां। हर राज्य का HD नक्शा (PNG) बिना शुल्क और बिना रजिस्ट्रेशन के डाउनलोड "
         "किया जा सकता है — प्रोजेक्ट, पढ़ाई, ऑफिस या खेती के काम के लिए।"),
        ("नक्शे में जिलों के नाम किस भाषा में हैं?",
         "सभी नक्शों में जिलों के नाम हिंदी (देवनागरी) में लिखे हैं। हर राज्य की "
         "“जिले” सूची में अंग्रेज़ी वर्तनी भी दी गई है, ताकि फॉर्म में सही नाम भरा जा सके।"),
        ("नक्शे किस डेटा पर आधारित हैं?",
         "जिला-सीमाएं Census of India के सार्वजनिक डेटा पर आधारित हैं, इसलिए हाल में "
         "बने कुछ नए जिले अलग से नहीं दिखते — वे अपने मूल जिले के भीतर हैं। जिस राज्य "
         "में ऐसा है, वहां पेज पर नोट लिखा है।"),
        ("क्या नक्शे को प्रिंट या प्रोजेक्ट में इस्तेमाल कर सकते हैं?",
         "हां। सभी नक्शे CC BY 4.0 लाइसेंस पर हैं — स्कूल प्रोजेक्ट, ऑफिस रिपोर्ट या "
         "प्रिंट में इस्तेमाल कीजिए, बस स्रोत में KrashiMitra.in लिख दें।"),
    ])

    landing_css = """
<style>
/* ── Naksha Hub Hero & Pickers ── */
.nk-land-hero {
  background: linear-gradient(135deg, var(--nk-emerald-dark) 0%, #0d3d2a 100%);
  padding: 30px 20px 24px;
  text-align: center;
  margin-bottom: 0;
}
.nk-land-hero h1 {
  font-size: 24px;
  font-weight: 900;
  color: #ffffff;
  margin: 0 0 6px;
  line-height: 1.3;
}
.nk-land-hero p {
  font-size: 13.5px;
  color: rgba(255,255,255,0.85);
  margin: 0 0 16px;
}
.nk-land-search-wrap {
  display: flex;
  gap: 8px;
  max-width: 480px;
  margin: 0 auto 12px;
  background: #ffffff;
  border-radius: 999px;
  padding: 6px 8px 6px 16px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.28);
  align-items: center;
}
.nk-land-search-wrap input {
  flex: 1;
  border: none;
  outline: none;
  font-size: 14px;
  font-weight: 600;
  color: var(--nk-text-dark);
  background: transparent;
  font-family: inherit;
}
.nk-land-search-wrap input::placeholder { color: #8aaa97; font-weight: 500; }
.nk-land-gps-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 8px 14px;
  border-radius: 999px;
  background: var(--nk-gold);
  border: none;
  color: #071f16;
  font-size: 12.5px;
  font-weight: 800;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.2s ease;
}
.nk-land-gps-btn:hover { transform: scale(1.04); background: #f0ac1a; }
.nk-land-gps-btn.loading { opacity: 0.7; pointer-events: none; }
.nk-land-gps-btn.loading .nk-land-gps-ic { display: inline-block; animation: nkSpin 0.9s linear infinite; }
.nk-land-gps-status {
  display: none;
  background: rgba(255,255,255,0.14);
  border-radius: 10px;
  padding: 8px 14px;
  font-size: 12.5px;
  color: #ffffff;
  margin: 0 auto;
  max-width: 360px;
  text-align: center;
}
.nk-land-gps-status.active { display: block; }
.nk-land-popular {
  background: #f5f9f6;
  padding: 18px 16px 14px;
  border-bottom: 1px solid var(--nk-border);
}
.nk-land-popular-title {
  font-size: 12px;
  font-weight: 800;
  color: var(--nk-text-soft);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 10px;
}
.nk-pick-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(148px, 1fr));
  gap: 8px;
}
.nk-pick-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-radius: 12px;
  background: #ffffff;
  border: 1.5px solid var(--nk-border);
  text-decoration: none;
  color: var(--nk-text-dark);
  transition: all 0.18s ease;
  gap: 4px;
}
.nk-pick-card:hover {
  border-color: var(--nk-mint);
  background: var(--nk-emerald-dark);
  color: #ffffff;
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(0,0,0,0.14);
}
.nk-pick-card.hidden { display: none; }
.nk-pick-name { font-size: 13.5px; font-weight: 800; flex: 1; }
.nk-pick-count { font-size: 11px; font-weight: 600; color: #7b9487; white-space: nowrap; }
.nk-pick-card:hover .nk-pick-count { color: rgba(255,255,255,0.7); }
.nk-pick-arrow { font-size: 16px; font-weight: 700; opacity: 0.5; }
.nk-land-regions { padding: 16px 16px 24px; }
.nk-region-group { margin-bottom: 20px; }
.nk-region-head {
  font-size: 13px;
  font-weight: 800;
  color: var(--nk-text-soft);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin: 0 0 10px;
  padding-bottom: 6px;
  border-bottom: 2px solid var(--nk-border);
}
.nk-land-noresult {
  display: none;
  text-align: center;
  padding: 24px 16px;
  color: var(--nk-text-soft);
  font-size: 14px;
}
.nk-land-noresult.active { display: block; }
@media (max-width: 480px) {
  .nk-land-hero h1 { font-size: 20px; }
  .nk-pick-grid { grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); }
}
</style>"""

    body = f"""{landing_css}

<!-- Hero Search Section -->
<div class="nk-land-hero">
  <h1>🗺️ भारत के राज्यों के डिजिटल नक्शे</h1>
  <p>{n_states} राज्य व केंद्र शासित प्रदेश · {total_d} जिले — सैटेलाइट व्यू, खेत नाप, गांव खोज व HD नक्शा डाउनलोड</p>

  <div class="nk-land-search-wrap">
    <input type="text" id="nk-land-search" placeholder="राज्य या जिला खोजें... जैसे: उत्तर प्रदेश, बिहार, राजस्थान"
           autocomplete="off" aria-label="राज्य खोजें" />
    <button type="button" class="nk-land-gps-btn" id="nk-land-gps-btn"
            title="GPS से राज्य पता करें">
      <span class="nk-land-gps-ic"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="display:inline-block;vertical-align:-2px"><circle cx="12" cy="12" r="7"/><line x1="12" y1="2" x2="12" y2="5"/><line x1="12" y1="19" x2="12" y2="22"/><line x1="2" y1="12" x2="5" y2="12"/><line x1="19" y1="12" x2="22" y2="12"/><circle cx="12" cy="12" r="2.5" fill="currentColor"/></svg></span>
      <span class="nk-land-gps-txt">मेरा राज्य</span>
    </button>
  </div>
  <div class="nk-land-gps-status" id="nk-land-gps-status">📡 आपकी लोकेशन खोजी जा रही है...</div>

  <!-- Quick Features Pill Bar -->
  <div style="display:flex; justify-content:center; flex-wrap:wrap; gap:8px; margin-top:14px;">
    <span style="background:rgba(255,255,255,0.12); border:1px solid rgba(255,255,255,0.22); color:#fff; padding:4px 12px; border-radius:20px; font-size:12px; font-weight:700;">🛰️ सैटेलाइट व्यू</span>
    <span style="background:rgba(255,255,255,0.12); border:1px solid rgba(255,255,255,0.22); color:#fff; padding:4px 12px; border-radius:20px; font-size:12px; font-weight:700;">📐 खेत नाप (Area)</span>
    <span style="background:rgba(255,255,255,0.12); border:1px solid rgba(255,255,255,0.22); color:#fff; padding:4px 12px; border-radius:20px; font-size:12px; font-weight:700;">🏡 गांव व खसरा खोज</span>
    <span style="background:rgba(255,255,255,0.12); border:1px solid rgba(255,255,255,0.22); color:#fff; padding:4px 12px; border-radius:20px; font-size:12px; font-weight:700;">📥 HD नक्शा डाउनलोड</span>
  </div>
</div>

<!-- Quick Download & State Switch Controls -->
<div class="nk-controls" style="margin: 16px auto; max-width: 760px; padding: 0 16px;">
  {_dl_button(states['uttar-pradesh'], "HD नक्शा डाउनलोड करें")}
  {_state_select_dropdown('uttar-pradesh', states, is_jile=False)}
</div>

<!-- Popular States Quick Pick -->
<div class="nk-land-popular" id="nk-land-popular">
  <div class="nk-land-popular-title">⭐ प्रमुख कृषि राज्य (Top Farming States)</div>
  <div class="nk-pick-grid">{popular_html}</div>
</div>

<!-- All States by Region -->
<div class="nk-land-regions" id="nk-land-all-regions">
  {all_regions_html}
</div>
<div class="nk-land-noresult" id="nk-land-noresult">
  कोई राज्य नहीं मिला — दूसरे शब्द आज़माएं
</div>

<section class="nk-sec" style="padding: 16px 16px 24px;">
  <h2>नक्शों से जुड़े सवाल (FAQs)</h2>
  {faq_html}
</section>

<p class="nk-updated" style="text-align:center; padding: 12px 16px; color:#64748b; font-size:12px;">
  🕒 अंतिम अपडेट: {_hindi_date(_updated())} · सीमा-डेटा: Census of India व डिजिटल सर्वे
</p>

<script>
(function() {{
  var searchInput = document.getElementById('nk-land-search');
  var allCards = document.querySelectorAll('.nk-pick-card');
  var popular = document.getElementById('nk-land-popular');
  var allRegions = document.getElementById('nk-land-all-regions');
  var noResult = document.getElementById('nk-land-noresult');
  var regionGroups = document.querySelectorAll('.nk-region-group');

  if(searchInput) {{
    searchInput.addEventListener('input', function() {{
      var q = this.value.trim().toLowerCase();
      if(!q) {{
        allCards.forEach(function(c) {{ c.classList.remove('hidden'); }});
        regionGroups.forEach(function(g) {{ g.style.display = ''; }});
        if(popular) popular.style.display = '';
        if(allRegions) allRegions.style.display = '';
        if(noResult) noResult.classList.remove('active');
        return;
      }}
      if(popular) popular.style.display = 'none';
      if(allRegions) allRegions.style.display = 'block';
      var matched = 0;
      allCards.forEach(function(c) {{
        var hi = (c.dataset.hi || '').toLowerCase();
        var st = (c.dataset.state || '').toLowerCase();
        if(hi.indexOf(q) > -1 || st.indexOf(q) > -1) {{
          c.classList.remove('hidden');
          matched++;
        }} else {{
          c.classList.add('hidden');
        }}
      }});
      regionGroups.forEach(function(g) {{
        var vis = g.querySelectorAll('.nk-pick-card:not(.hidden)').length > 0;
        g.style.display = vis ? '' : 'none';
      }});
      if(noResult) noResult.classList.toggle('active', matched === 0);
    }});
  }}

  // GPS detect state
  var gpsBtn = document.getElementById('nk-land-gps-btn');
  var gpsStatus = document.getElementById('nk-land-gps-status');
  var gpsTxt = gpsBtn ? gpsBtn.querySelector('.nk-land-gps-txt') : null;

  var stateMap = {{}};
  allCards.forEach(function(c) {{
    stateMap[(c.dataset.hi || '')] = c.href;
    stateMap[(c.dataset.state || '')] = c.href;
  }});

  if(gpsBtn) {{
    gpsBtn.addEventListener('click', function() {{
      if(!navigator.geolocation) {{
        alert('आपके डिवाइस में GPS उपलब्ध नहीं है।');
        return;
      }}
      gpsBtn.classList.add('loading');
      if(gpsTxt) gpsTxt.textContent = 'खोज रहे हैं...';
      if(gpsStatus) gpsStatus.classList.add('active');

      navigator.geolocation.getCurrentPosition(function(pos) {{
        var lat = pos.coords.latitude, lon = pos.coords.longitude;
        fetch('https://api.bigdatacloud.net/data/reverse-geocode-client?latitude=' + lat + '&longitude=' + lon + '&localityLanguage=hi')
          .then(function(r) {{ return r.json(); }})
          .then(function(d) {{
            var state = (d.principalSubdivision || '').toLowerCase()
              .replace(/\\s+/g, '-').replace(/[^a-z-]/g, '');
            var url = stateMap[state];
            if(url) {{
              if(gpsStatus) gpsStatus.textContent = '📍 ' + (d.principalSubdivision || 'आपका राज्य') + ' मिला — नक्शा खुल रहा है...';
              setTimeout(function() {{ window.location.href = url; }}, 800);
            }} else {{
              if(gpsStatus) gpsStatus.textContent = '📍 ' + (d.principalSubdivision || '') + ' — नीचे से चुनें';
              if(searchInput && d.principalSubdivision) {{
                searchInput.value = d.principalSubdivision;
                searchInput.dispatchEvent(new Event('input'));
              }}
            }}
          }})
          .catch(function() {{
            if(gpsStatus) gpsStatus.textContent = 'लोकेशन मिली पर राज्य पहचान नहीं हुई — नीचे से चुनें।';
          }})
          .finally(function() {{
            gpsBtn.classList.remove('loading');
            if(gpsTxt) gpsTxt.textContent = 'मेरा राज्य';
          }});
      }}, function() {{
        gpsBtn.classList.remove('loading');
        if(gpsTxt) gpsTxt.textContent = 'मेरा राज्य';
        if(gpsStatus) gpsStatus.classList.remove('active');
        alert('लोकेशन नहीं मिल सकी। GPS और ब्राउज़र अनुमति जांचें।');
      }}, {{ enableHighAccuracy: false, timeout: 10000 }});
    }});
  }}
}})();
</script>
{_tail_scripts()}"""

    crumb = _crumb_ld([("होम", f"{SITE}/"), ("राज्यों के नक्शे", f"{SITE}/naksha")])
    page_ld = {
        "@context": "https://schema.org", "@type": "CollectionPage",
        "@id": f"{SITE}/naksha#webpage", "url": f"{SITE}/naksha",
        "name": title, "description": desc, "inLanguage": "hi",
        "dateModified": _updated(),
        "mainEntity": {
            "@type": "ItemList", "numberOfItems": n_states,
            "itemListElement": [
                {"@type": "ListItem", "position": i, "name": f"{s['hi']} का नक्शा",
                 "url": _abs(_url(k))}
                for i, (k, s) in enumerate(states.items(), start=1)],
        },
    }
    return _doc(title, desc, f"{SITE}/naksha",
                _crumbs([("राज्यों के नक्शे", None)]), body,
                ld=_ld(page_ld, crumb, faq_ld),
                og_img=_abs_img(states["uttar-pradesh"], "og.png"),
                active="map", extra_css=_NK_CSS)


# ── one state's map ─────────────────────────────────────────────────────────

def _map_app_container(key: str, s: dict, hi: str, is_district: bool = False, dslug: str = "", dist_hi: str = "", dist_en: str = "") -> str:
    bhulekh_tuple = _BHULEKH.get(key, ("https://bhulekh.gov.in/", "भूलेख पोर्टल"))
    bhulekh_url, bhulekh_label = bhulekh_tuple[0], bhulekh_tuple[1]

    search_placeholder = f"{dist_hi} का गांव या तहसील खोजें..." if is_district else f"{hi} का जिला या गांव खोजें..."
    drawer_initial_title = f"📍 {dist_hi} <small style='font-size:13px;color:var(--nk-text-soft)'>({dist_en})</small>" if is_district else f"🏛️ {hi} <small style='font-size:13px;color:var(--nk-text-soft)'>({s['n']} जिले)</small>"
    drawer_initial_sub = f"{dist_hi} जिला मानचित्र व सुविधाएं" if is_district else "जिले पर टैप करके सुविधाएं देखें"
    
    gaon_link_style = "" if is_district else "style='display:none'"
    gaon_link_href = f"/naksha/{key}/{dslug}/gaon" if is_district else "#"

    return f"""
<div class="nk-app-map-wrap" id="nk-map-wrap">
  <!-- Floating Unified Search Bar -->
  <div class="nk-float-search">
    <div class="nk-search-pill-box">
      <span class="nk-search-ic">🔍</span>
      <input type="text" id="nk-search-input" class="nk-search-input" placeholder="{escape(search_placeholder)}" autocomplete="off" aria-label="जिला या गांव खोजें">
      <button type="button" id="nk-search-clear-btn" class="nk-search-clear-btn" aria-label="साफ करें">✕</button>
      <button type="button" id="nk-search-loc-btn" class="nk-search-loc-btn" title="आपकी लोकेशन (GPS)" aria-label="आपकी लोकेशन (GPS)">
        <span class="nk-loc-icon"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="display:inline-block;vertical-align:-2px"><circle cx="12" cy="12" r="7"/><line x1="12" y1="2" x2="12" y2="5"/><line x1="12" y1="19" x2="12" y2="22"/><line x1="2" y1="12" x2="5" y2="12"/><line x1="19" y1="12" x2="22" y2="12"/><circle cx="12" cy="12" r="2.5" fill="currentColor"/></svg></span>
        <span class="nk-loc-text">लोकेशन</span>
      </button>
      <button type="button" id="nk-search-btn" class="nk-search-btn">खोजें</button>
    </div>
    <div class="nk-search-actions">
      <button type="button" id="nk-mandi-toggle-btn" class="nk-mandi-toggle-btn" title="मंडी देखें व भाव जानें" aria-label="मंडी देखें">
        <span class="nk-mandi-btn-icon">🌾</span>
        <span class="nk-mandi-btn-text">मंडी देखें</span>
        <span class="nk-mandi-btn-badge" id="nk-mandi-btn-count" style="display:none">0</span>
      </button>
      <button type="button" id="nk-route-btn" class="nk-route-btn" title="कहाँ से कहाँ तक — रास्ता देखें" aria-label="रास्ता देखें">
        <svg class="nk-route-arrow" viewBox="0 0 24 24"><path d="M12 2L4.5 20.29l.71.71L12 18l6.79 3 .71-.71z"/></svg>
        <span id="nk-route-btn-text">रास्ता देखें</span>
      </button>
    </div>
    <div class="nk-suggestions-list" id="nk-suggestions-list"></div>
  </div>
  <!-- Fullscreen icon-only button (top-right) -->
  <button type="button" id="nk-fab-fullscreen" class="nk-fs-btn" aria-label="फुलस्क्रीन" title="फुलस्क्रीन मोड">
    <svg id="nk-fs-icon-expand" class="nk-fs-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <polyline points="15 3 21 3 21 9" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
      <polyline points="9 21 3 21 3 15" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
      <line x1="21" y1="3" x2="14" y2="10" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>
      <line x1="3" y1="21" x2="10" y2="14" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>
    </svg>
    <svg id="nk-fs-icon-collapse" class="nk-fs-icon" style="display:none" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <polyline points="4 14 10 14 10 20" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
      <polyline points="20 10 14 10 14 4" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
      <line x1="10" y1="14" x2="3" y2="21" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>
      <line x1="21" y1="3" x2="14" y2="10" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>
    </svg>
  </button>

  <!-- Floating Collapsible Tools Menu (Speed Dial) -->
  <div class="nk-fab-menu" id="nk-fab-menu">
    <button type="button" id="nk-fab-trigger" class="nk-fab-main" aria-label="नक्शा टूल्स" title="नक्शा टूल्स">
      <span class="nk-fab-main-ic">
        <svg class="nk-fab-main-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
          <polygon points="12 2 2 7 12 12 22 7 12 2"/>
          <polyline points="2 17 12 22 22 17"/>
          <polyline points="2 12 12 17 22 12"/>
        </svg>
      </span>
      <span class="nk-fab-main-close">✕</span>
    </button>

    <div class="nk-fab-options" id="nk-fab-options">
      <button type="button" id="nk-fab-mandi" class="nk-fab-opt" aria-label="मंडी देखें" title="मंडी देखें व ताजा भाव जानें">
        <span class="nk-fab-opt-ic">🌾</span>
        <span class="nk-fab-opt-label" id="nk-fab-mandi-text">मंडी देखें</span>
      </button>
      <button type="button" id="nk-fab-measure" class="nk-fab-opt" aria-label="खेत नापो (क्षेत्रफल)">
        <span class="nk-fab-opt-ic">📐</span>
        <span class="nk-fab-opt-label">खेत नापो (Area)</span>
      </button>
      <button type="button" id="nk-fab-overlay" class="nk-fab-opt" aria-label="राज्य/जिला सीमा ऑन/ऑफ" title="राज्य सीमा (Border) दिखाएं/छिपाएं">
        <span class="nk-fab-opt-ic" id="nk-fab-overlay-ic">👁️</span>
        <span class="nk-fab-opt-label" id="nk-fab-overlay-text">सीमा छिपाएं</span>
      </button>
      <button type="button" id="nk-fab-layer" class="nk-fab-opt" aria-label="सैटेलाइट / नक्शा बदलें">
        <span class="nk-fab-opt-ic" id="nk-fab-layer-ic">🗺️</span>
        <span class="nk-fab-opt-label" id="nk-fab-layer-text">नक्शा व्यू</span>
      </button>
      <button type="button" id="nk-fab-reset" class="nk-fab-opt" aria-label="पूरा नक्शा देखें" style="display:none">
        <span class="nk-fab-opt-ic">🔄</span>
        <span class="nk-fab-opt-label">पूरा नक्शा</span>
      </button>
    </div>
  </div>

  <!-- Farm Area Measure Tool HUD -->
  <div class="nk-measure-hud" id="nk-measure-hud">
    <div class="nk-mhud-head">
      <span class="nk-mhud-title">📐 खेत नापने का यंत्र (Area Calculator)</span>
      <button type="button" id="nk-mhud-close" class="nk-mhud-close-btn" style="background:none;border:none;color:rgba(255,255,255,0.7);cursor:pointer;font-size:15px;padding:0 4px;line-height:1;" title="बंद करें">✕</button>
    </div>
    <div class="nk-mhud-tip">मानचित्र पर खेत के कोनों को छूकर सीमा बनाएं:</div>
    <div class="nk-mhud-results">
      <div class="nk-mhud-pill">एकड़: <b id="nk-mhud-acre">0 एकड़</b></div>
      <div class="nk-mhud-pill">बीघा: <b id="nk-mhud-bigha">0 बीघा</b></div>
      <div class="nk-mhud-pill">हेक्टेयर: <b id="nk-mhud-hectare">0 हे.</b></div>
      <div class="nk-mhud-pill">वर्ग मीटर: <b id="nk-mhud-sqm">0 m²</b></div>
    </div>
    <div class="nk-mhud-actions">
      <button type="button" id="nk-mhud-undo" class="nk-mhud-btn undo" title="पिछला बिंदु हटाएं (Undo)" aria-label="Undo">
        <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px"><path d="M3 7v6h6"/><path d="M21 17a9 9 0 0 0-9-9 9 9 0 0 0-6 2.3L3 13"/></svg>
        <span>अनडू</span>
      </button>
      <button type="button" id="nk-mhud-clear" class="nk-mhud-btn clear" title="सभी बिंदु साफ़ करें">✕ साफ़ करें</button>
      <button type="button" id="nk-mhud-print" class="nk-mhud-btn print" title="खेत का नक्शा व नाप प्रिंट करें (Print Sketch)">
        <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px"><polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/></svg>
        <span>प्रिंट करें</span>
      </button>
    </div>
  </div>

  <!-- Interactive Leaflet Canvas -->
  <div id="nk-map" class="nk-map"></div>

  <!-- My Location Button (bottom-right standalone, icon-only) -->
  <button type="button" id="nk-fab-gps" class="nk-my-loc-btn" title="मेरी लोकेशन (GPS)" aria-label="मेरी लोकेशन (GPS)">
    <svg class="nk-loc-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg">
      <circle cx="12" cy="12" r="7"/>
      <line x1="12" y1="2" x2="12" y2="5"/>
      <line x1="12" y1="19" x2="12" y2="22"/>
      <line x1="2" y1="12" x2="5" y2="12"/>
      <line x1="19" y1="12" x2="22" y2="12"/>
      <circle cx="12" cy="12" r="2.5" fill="currentColor"/>
    </svg>
  </button>

  <!-- Slide-up Bottom Drawer -->
  <div class="nk-bottom-drawer" id="nk-bottom-drawer">
    <div class="nk-drawer-handle"></div>
    <div class="nk-drawer-header">
      <div class="nk-drawer-title-box">
        <h3 id="nk-drawer-title">{drawer_initial_title}</h3>
        <p id="nk-drawer-sub">{drawer_initial_sub}</p>
      </div>
      <button type="button" id="nk-drawer-close" class="nk-drawer-close" aria-label="बंद करें">✕</button>
    </div>
    <div class="nk-drawer-grid">
      <a id="nk-drawer-weather" class="nk-drawer-btn weather" href="/weather">🌤️ मौसम देखें</a>
      <a id="nk-drawer-bhav" class="nk-drawer-btn bhav" href="/bhav">💰 मंडी भाव</a>
      <a id="nk-drawer-bhulekh" class="nk-drawer-btn bhulekh" href="{bhulekh_url}" target="_blank" rel="noopener">📄 {escape(bhulekh_label)}</a>
      <a id="nk-drawer-gaon" class="nk-drawer-btn gaon" href="{gaon_link_href}" {gaon_link_style}>🌾 गांव सूची</a>
      <a class="nk-drawer-btn dl" data-km-map-picker href="{_img(s, 'district-map.png')}" download="{s['prefix']}-{s['n']}-jile.png">⬇️ HD डाउनलोड</a>
    </div>
  </div>

  <!-- Nearest-mandi route summary (sits under the drawer when that opens) -->
  <!-- Directions panel: /naksha routes between any two points, unlike /bhav
       where the destination is always the mandi the page is about. -->
  <div class="nk-route-panel" id="nk-route-panel">
    <div class="nk-rp-head">
      <span class="nk-rp-title">रास्ता देखें</span>
      <button type="button" class="nk-rp-close" id="nk-rp-close" aria-label="बंद करें">✕</button>
    </div>
    <div class="nk-rp-body">
      <div class="nk-rp-rail">
        <span class="nk-rp-dot"></span>
        <span class="nk-rp-dots"></span>
        <span class="nk-rp-dot dest"></span>
      </div>
      <div class="nk-rp-fields">
        <div class="nk-rp-field" style="margin-bottom:8px">
          <input type="text" id="nk-rp-from" class="nk-rp-input" placeholder="कहाँ से (शुरुआत)" autocomplete="off">
          <div class="nk-rp-sugg" id="nk-rp-from-sugg"></div>
        </div>
        <div class="nk-rp-field">
          <input type="text" id="nk-rp-to" class="nk-rp-input" placeholder="कहाँ तक (मंज़िल)" autocomplete="off">
          <div class="nk-rp-sugg" id="nk-rp-to-sugg"></div>
        </div>
      </div>
      <button type="button" class="nk-rp-swap-btn" id="nk-rp-swap" title="उलटा करें">⇅</button>
    </div>
    <div class="nk-rp-chip-row">
      <span class="nk-rp-lbl">शुरुआत:</span>
      <button type="button" class="nk-rp-chip" data-from="gps">📍 मेरी लोकेशन</button>
      <button type="button" class="nk-rp-chip" data-pick="from">🗺️ नक्शे पर</button>
    </div>
    <div class="nk-rp-chip-row">
      <span class="nk-rp-lbl">मंज़िल:</span>
      <button type="button" class="nk-rp-chip" data-to="mandi">🌾 नजदीकी मंडी</button>
      <button type="button" class="nk-rp-chip" data-pick="to">🗺️ नक्शे पर</button>
    </div>
    <button type="button" class="nk-rp-go" id="nk-rp-go">रास्ता दिखाएँ</button>
    <div class="nk-rp-note" id="nk-rp-note"></div>
  </div>

  <div class="nk-pick-overlay" id="nk-pick-overlay">
    <div class="nk-pick-hint" id="nk-pick-hint">नक्शे पर जगह टैप करें</div>
  </div>

  <div class="nk-route-card" id="nk-route-card">
    <svg viewBox="0 0 24 24" style="width:17px;height:17px;fill:#60a5fa;flex-shrink:0"><path d="M12 2L4.5 20.29l.71.71L12 18l6.79 3 .71-.71z"/></svg>
    <div class="nk-route-card-info">
      <span class="nk-route-card-title"><span id="nk-route-label">रास्ता</span>: <b id="nk-route-mandi">—</b></span>
      <span class="nk-route-card-meta" id="nk-route-dist">—</span>
    </div>
    <a id="nk-route-nav" href="#" target="_blank" rel="noopener" class="nk-route-nav" title="गूगल मैप पर रास्ता">गूगल मैप</a>
    <button type="button" id="nk-route-close" class="nk-route-close" title="रास्ता हटाएँ" aria-label="रास्ता हटाएँ">
      <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
    </button>
  </div>
</div>
"""


# ── one state's map ─────────────────────────────────────────────────────────

def _state_page(key: str, canon: str) -> HTMLResponse:
    states = _states()
    s = states[key]
    hi, n = s["hi"], s["n"]
    span = f"{s['north']} से {s['south']} तक"

    # "<State> Map" earns its place ahead of "मुफ्त डाउनलोड": these pages rank
    # 7.2 on average for the Latin spelling — better than the 8.9 they hold for
    # the Devanagari one — and still took 6 clicks from 2,034 impressions
    # (0.29%) against 0.79% from the Hindi searchers. A title with no Latin
    # word in it is not a result an "assam map" searcher recognises as theirs.
    # The abbreviation goes next to the English name, not instead of it: "mp map"
    # and "madhya pradesh map" are both real demand and only one of them is
    # served by either spelling alone.
    ab = _ABBR.get(key)
    # The title answers "how many districts" with today's checked count where
    # there is one (a searcher who knows Rajasthan has 41 skips a result saying
    # 33). Everything that describes the IMAGE keeps `n`, the map's own count.
    count, extra, unsure = _district_count(key, s)
    tn = count
    abbr_variants = [
        f"{hi} का नक्शा – {tn} जिले | {s['en']} ({ab}) Map, HD डाउनलोड",
        f"{hi} का नक्शा – {tn} जिलों का HD मानचित्र | {s['en']} ({ab}) Map",
        f"{hi} का नक्शा – {tn} जिलों का मानचित्र | {s['en']} ({ab}) Map",
        f"{hi} का नक्शा – {tn} जिले | {s['en']} ({ab}) Map, HD डाउनलोड",
        f"{hi} का नक्शा – {tn} जिले | {s['en']} ({ab}) Map",
        f"{hi} का नक्शा | {s['en']} ({ab}) Map – {tn} जिले",
    ] if ab else []
    title = _fit(
        *abbr_variants,
        f"{hi} का नक्शा – {tn} जिलों का HD मानचित्र | {s['en']} Map",
        f"{hi} का नक्शा – {tn} जिलों का मानचित्र | {s['en']} Map",
        f"{hi} का नक्शा – {tn} जिले | {s['en']} Map",
        f"{hi} का नक्शा – {tn} जिलों का HD मानचित्र | मुफ्त डाउनलोड",
        f"{hi} का नक्शा – {tn} जिलों का HD मानचित्र (मुफ्त)",
        f"{hi} का नक्शा – {tn} जिलों का HD मानचित्र")
    desc = _fit(
        f"{hi} का नक्शा हिंदी में — {span}, {'सभी जिले' if unsure else f'कुल {count} जिले'} एक ही मानचित्र में। "
        f"HD नक्शा मुफ्त डाउनलोड करें और ज़ूम करके अपना जिला देखें।",
        f"{hi} का नक्शा हिंदी में — {'सभी जिले' if unsure else f'कुल {count} जिले'} एक ही मानचित्र में। "
        f"HD नक्शा मुफ्त डाउनलोड करें और ज़ूम करके अपना जिला देखें।",
        limit=162)
    alt = (f"{hi} का नक्शा ({s['en']}{f' / {ab}' if ab else ''} Map) — "
           f"{n} जिलों के नाम हिंदी में, जिलेवार मानचित्र")

    chips = _sibling_chips(key, s, "")

    faq_html, faq_ld = _faq([
        (f"{hi} में कितने जिले हैं?",
         (f"नक्शे पर Census of India की सीमाओं के हिसाब से {hi} के {n} जिले हैं — {span}। "
          f"नए जिले बनने से संख्या बदल चुकी हो सकती है; ताज़ा संख्या राज्य सरकार की "
          f"वेबसाइट पर देखें।") if unsure else
         (f"{date.today().year} में {hi} में कुल {count} जिले हैं। नक्शे पर {n} जिले Census of "
          f"India की सीमाओं से दिखाए गए हैं; {', '.join(d['hi'] for d in extra)} बाद में बने "
          f"या अलग हुए हैं और नक्शे में अपने मूल जिले के भीतर दिखते हैं।") if extra else
         f"{hi} में {count} जिले हैं — {span}।"),
        (f"{hi} का नक्शा मुफ्त में कैसे डाउनलोड करें?",
         f"इसी पेज पर “HD नक्शा डाउनलोड करें” बटन दबाएं — {n} जिलों वाला नक्शा (PNG) "
         f"बिना किसी शुल्क और बिना रजिस्ट्रेशन के डाउनलोड हो जाता है। इसे प्रोजेक्ट, "
         f"पढ़ाई या खेती के काम में इस्तेमाल कर सकते हैं।"),
        (f"{hi} का सबसे बड़ा जिला कौन सा है?",
         f"क्षेत्रफल के हिसाब से {s['big']} सबसे बड़ा और {s['small']} सबसे छोटा जिला है "
         f"(Census of India की सीमाओं के अनुसार)।"),
        (f"क्या इस नक्शे को प्रिंट या प्रोजेक्ट में इस्तेमाल कर सकते हैं?",
         f"हां। नक्शा CC BY 4.0 लाइसेंस पर है — स्कूल प्रोजेक्ट, ऑफिस रिपोर्ट या "
         f"प्रिंट में इस्तेमाल कर सकते हैं, बस स्रोत में KrashiMitra.in लिख दें।"),
    ])

    note = f'<div class="nk-note">नोट: {escape(s["note"])}</div>' if s["note"] else ""
    map_container = _map_app_container(key, s, hi)


    bhulekh_info = _BHULEKH.get(key, ("https://upbhulekh.gov.in/", "भूलेख पोर्टल"))
    bhulekh_url = bhulekh_info[0]
    bhulekh_label = bhulekh_info[1]

    # Same honesty rule as the district page: weather only where /weather has
    # it (UP), prices at the state's own hub, schemes at the page that carries
    # the private-website notice.
    _sc = [_nk_card("bhav", _state_bhav_link(key), "💰", f"{hi} मंडी भाव",
                    "आज के फसल भाव, जिलेवार")]
    if key == "uttar-pradesh":
        _sc.append(_nk_card("weather", "/weather", "🌤️", "मौसम पूर्वानुमान",
                            "उत्तर प्रदेश के सभी जिलों का आज का मौसम"))
    else:
        _sc.append(_nk_card("yojana", "/sarkari_yojana", "📜", "सरकारी किसान योजनाएं",
                            "पात्रता, दस्तावेज़ व आधिकारिक लिंक"))
    _sc.append(_nk_card("bhulekh", bhulekh_url, "📄", bhulekh_label,
                        "खसरा-खतौनी व भू-अभिलेख नकल निकालें ↗", ext=True))
    _sc.append(_nk_card("gaon", _jile_url(key), "🌾",
                        f"{hi} के जिले" if unsure else f"{hi} के सभी {count} जिले",
                        "जिलों की सूची व गांव डायरेक्टरी"))
    state_cards = "".join(_sc)

    body = f"""<div class="nk-level-bar">
  <a href="/naksha">🇮🇳 भारत (India)</a>
  <span class="nk-lvl-sep">➔</span>
  <a href="{_url(key)}">🏛️ {escape(hi)}</a>
  <span class="nk-lvl-sep">➔</span>
  <span style="color:var(--nk-emerald-dark)">📍 जिला / 🏢 तहसील / 🌾 गांव सैटेलाइट</span>
</div>

<h1 class="nk-title">{escape(hi)} का नक्शा</h1>
<p class="nk-title-sub">{_jile(n) + " (नक्शे पर)" if unsure else _jile(count)} · {escape(span)} · हिंदी में जिलेवार मानचित्र व सैटेलाइट व्यू</p>

<div class="nk-tabs-bar">
  <a class="nk-tab-item active" href="{_url(key)}#nk-map-wrap">🗺️ इंटरैक्टिव नक्शा</a>
  <a class="nk-tab-item" href="{_jile_url(key)}">📋 जिलों की सूची{"" if unsure else f" ({count})"}</a>
</div>

{map_container}

<!-- 4 Farmer Quick Action Cards -->
<div class="nk-farmer-grid">{state_cards}</div>

<!-- Compact HD Map Download Banner -->
{_dl_card(s, f"⬇️ {hi} का HD नक्शा — मुफ्त डाउनलोड",
          "सभी जिलों के नाम हिंदी में · प्रिंट के लिए PNG या A4 PDF",
          alt)}

<!-- 4 Fact Metric Boxes -->
<div class="nk-facts-bar">
  <div class="nk-fact-box">
    <small>{"नक्शे पर जिले" if unsure else "कुल जिले"}</small>
    <b>{_jile(n) if unsure else _jile(count)}</b>
  </div>
  <div class="nk-fact-box">
    <small>सबसे बड़ा जिला</small>
    <b>{escape(s['big'])}</b>
  </div>
  <div class="nk-fact-box">
    <small>सबसे छोटा जिला</small>
    <b>{escape(s['small'])}</b>
  </div>
  <div class="nk-fact-box">
    <small>उत्तर से दक्षिण विस्तार</small>
    <b>{escape(span)}</b>
  </div>
</div>

<section class="nk-sec">
  <h2>{escape(hi)} के जिले (Quick Jump)</h2>
  <p class="nk-lede">नक्शे पर तुरंत देखने के लिए किसी भी जिले पर टैप करें या पूरी सूची के लिए <a href="{_jile_url(key)}">{escape(hi)} के जिले</a> देखें:</p>
  <div class="nk-chips">{chips}</div>
</section>

<section class="nk-sec"><h2>{escape(hi)} के नक्शे से जुड़े सवाल</h2>{faq_html}</section>

<section class="nk-sec">
  <h2>दूसरे राज्यों के नक्शे</h2>
  <p class="nk-lede">हर नक्शा हिंदी में, जिलेवार, और मुफ्त HD डाउनलोड के साथ —
    <a href="/naksha">सभी {len(states)} राज्य देखें →</a></p>
  <div class="nk-sgrid">{_others(key, states)}</div>
</section>

{note}
<p class="nk-updated">🕒 अंतिम अपडेट: {_hindi_date(_updated())} · सीमा-डेटा: Census of India</p>
{_tail_scripts(s, state_key=key)}"""

    crumb = _crumb_ld([("होम", f"{SITE}/"), ("राज्यों के नक्शे", f"{SITE}/naksha"),
                       (f"{hi} का नक्शा", _abs(canon))])
    page_ld = {
        "@context": "https://schema.org", "@type": "WebPage",
        "@id": f"{canon}#webpage", "url": canon, "name": title,
        "description": desc, "inLanguage": "hi", "dateModified": _updated(),
        "primaryImageOfPage": {"@id": f"{canon}#mapimage"},
        "about": {"@type": "Place", "name": s["en"],
                  "geo": {"@type": "GeoCoordinates",
                          "latitude": s["lat"], "longitude": s["lon"]}},
        "significantLink": [_abs(_jile_url(key)), f"{SITE}/naksha"],
    }
    img_ld = {
        "@context": "https://schema.org", "@type": "ImageObject",
        "@id": f"{canon}#mapimage",
        "contentUrl": _abs_img(s, "district-map.png"),
        "url": _abs_img(s, "district-map.png"),
        "width": s["w"], "height": s["h"],
        "name": f"{hi} का नक्शा — {n} जिलों का जिलेवार मानचित्र",
        "description": f"{hi} के सभी {n} जिलों का हिंदी नक्शा, मुफ्त HD डाउनलोड। "
                       f"सीमा-डेटा: Census of India।",
        "inLanguage": "hi", "encodingFormat": "image/png",
        "creditText": "KrashiMitra.in",
        "license": "https://creativecommons.org/licenses/by/4.0/",
        "acquireLicensePage": f"{SITE}/about",
    }
    return _doc(title, desc, canon,
                _crumbs([("राज्यों के नक्शे", f"{SITE}/naksha"),
                         (f"{hi} का नक्शा", None)]),
                body, ld=_ld(page_ld, img_ld, crumb, faq_ld),
                og_img=_abs_img(s, "og.png"), active="map",
                extra_css=_NK_CSS, head_extra=_LEAFLET_CSS)


# ── one state's districts ───────────────────────────────────────────────────

def _jile_page(key: str) -> HTMLResponse:
    states = _states()
    s = states[key]
    hi, n = s["hi"], s["n"]
    span = f"{s['north']} से {s['south']} तक"
    canon = _abs(_jile_url(key))

    # These pages rank 6-10 for the question itself — "गुजरात में कितने जिले हैं",
    # "arunachal pradesh mein kitne jile hain", "ap me kitne jile hai" — and took
    # zero clicks in the 28 days to 9 Sep 2026. The count was in the old title
    # but buried mid-phrase behind "सभी", while "(हिंदी + English)" spent eight
    # characters on something no one searches for. Lead with the question and
    # put the number where the answer goes; carry the Latin spelling so the
    # romanised half of the same query has something to bold.
    ab = _ABBR.get(key)
    en = s["en"]
    # `n` stays the MAP's count (it is what the drawn list and the image hold);
    # `count` is the answer to the question this page ranks for. Where the two
    # differ, the page says why — see _district_count and _extra_html.
    count, extra, unsure = _district_count(key, s)
    yr = date.today().year
    if unsure:
        # Sources disagree on this state's current count: no number goes in the
        # title as a fact. The list below is still the map's, and says so.
        title = _fit(
            f"{hi} में कितने जिले हैं? जिलों की पूरी सूची | {en} District List",
            f"{hi} में कितने जिले हैं? पूरी सूची | {en} District List",
            f"{hi} के जिले – पूरी सूची | {en} Districts")
    else:
        title = _fit(
            f"{hi} में कितने जिले हैं {yr}? {count} जिलों की सूची | {en} Districts",
            f"{hi} में कितने जिले हैं? {count} जिलों की पूरी सूची | {en} Districts",
            f"{hi} में कितने जिले हैं? {count} जिलों की सूची | {en} Districts",
            f"{hi} में कितने जिले हैं? {count} जिलों की पूरी सूची",
            f"{hi} के {count} जिले – पूरी सूची | {en} Districts",
            f"{hi} के जिले – सभी {count} जिलों की सूची",
            f"{hi} के {count} जिले – पूरी सूची")
    # The description opens with the bare number, so the answer survives even
    # when Google rewrites the title into its own question format.
    _new_names = ", ".join(d["hi"] for d in extra[:3])
    if unsure:
        desc = _fit(
            f"{hi} के जिलों की सूची हिंदी और अंग्रेज़ी नामों के साथ, {span} — नक्शे पर "
            f"{n} जिले (Census सीमाएं)। नए जिले बने हों तो राज्य सरकार की साइट देखें।",
            f"{hi} के जिलों की सूची हिंदी और अंग्रेज़ी नामों के साथ — नक्शे पर {n} जिले "
            f"(Census सीमाएं)। साथ में HD नक्शा, मुफ्त डाउनलोड।",
            limit=162)
    else:
        desc = _fit(
            *([f"{hi} में कुल {count} जिले हैं ({en} has {count} districts) — "
               f"{_new_names} समेत सभी जिलों की सूची हिंदी और अंग्रेज़ी में। साथ में HD नक्शा।"]
              if extra else []),
            f"{hi} में कुल {count} जिले हैं ({en} has {count} districts) — पूरी सूची हिंदी और "
            f"अंग्रेज़ी दोनों नामों के साथ, {span}। साथ में HD नक्शा, मुफ्त डाउनलोड।",
            f"{hi} में कुल {count} जिले हैं ({en} has {count} districts) — पूरी सूची हिंदी और "
            f"अंग्रेज़ी दोनों नामों के साथ। साथ में HD नक्शा, मुफ्त डाउनलोड।",
            f"{hi} में कुल {count} जिले हैं — पूरी सूची हिंदी और अंग्रेज़ी दोनों नामों के साथ। "
            f"साथ में HD नक्शा — मुफ्त डाउनलोड।",
            limit=162)

    rows = "".join(
        f'<div class="nk-drow">'
        f'<span class="nk-num">{i}</span>'
        f'<a class="nk-dname" href="{_d_url(key, slugify(d["en"]))}" '
        f'title="{escape(d["hi"])} का नक्शा">'
        f'<b>{escape(d["hi"])}</b>'
        f'<span class="nk-en">{escape(d["en"])}</span></a>'
        f'<span class="nk-drow-actions">'
        f'<a class="nk-dact-btn" href="{_gaon_url(key, slugify(d["en"]))}" '
        f'title="{escape(d["hi"])} के गांव">🌾 गांव</a></span>'
        f'</div>'
        for i, d in enumerate(s["districts"], start=1))

    if unsure:
        _count_ans = (f"नक्शे पर Census of India की जिला-सीमाओं के हिसाब से {hi} के {n} जिले "
                      f"दिखाए गए हैं। नए जिले बनने से यह संख्या बदल चुकी हो सकती है — ताज़ा "
                      f"संख्या {hi} सरकार की आधिकारिक वेबसाइट पर देखें।")
    elif extra:
        _count_ans = (f"{yr} में {hi} में कुल {count} जिले हैं। इनमें से {n} नक्शे पर Census of "
                      f"India की सीमाओं से दिखाए गए हैं; "
                      f"{', '.join(d['hi'] for d in extra)} नक्शे में अलग नहीं दिखते — वे अपने "
                      f"मूल जिले के भीतर हैं। सभी {count} नाम ऊपर सूची में हैं।")
    else:
        _count_ans = (f"{hi} में {count} जिले हैं। ऊपर दी गई सूची में सभी {count} नाम हिंदी "
                      f"और अंग्रेज़ी दोनों में हैं।")
    faq_html, faq_ld = _faq([
        (f"{hi} में कितने जिले हैं?", _count_ans),
        (f"{hi} का सबसे बड़ा जिला कौन सा है?",
         f"क्षेत्रफल के हिसाब से {s['big']} सबसे बड़ा जिला है और {s['small']} सबसे छोटा। "
         f"यह तुलना Census of India की जिला-सीमाओं से निकाली गई है।"),
        (f"{hi} के जिलों का नक्शा कहां मिलेगा?",
         f"{hi} का नक्शा पेज पर पूरा जिलेवार मानचित्र है — इंटरैक्टिव भी और मुफ्त HD "
         f"डाउनलोड भी।"),
        (f"किसी एक जिले को नक्शे में कैसे देखें?",
         f"ऊपर सूची में जिले के नाम पर टैप करें — {hi} का नक्शा खुलेगा और वही जिला "
         f"हाइलाइट होकर ज़ूम हो जाएगा।"),
    ])

    note = f'<div class="nk-note">नोट: {escape(s["note"])}</div>' if s["note"] else ""

    body = f"""<div class="nk-level-bar">
  <a href="/naksha">🇮🇳 भारत (India)</a>
  <span class="nk-lvl-sep">➔</span>
  <a href="{_url(key)}">🏛️ {escape(hi)}</a>
  <span class="nk-lvl-sep">➔</span>
  <span style="color:var(--nk-emerald-dark)">📋 जिलों की सूची{"" if unsure else f" ({count})"}</span>
</div>

<h1 class="nk-title">{escape(hi)} में कितने जिले हैं?</h1>
<p class="nk-title-sub">{"नक्शे पर " + _jile(n) + " (Census सीमाएं)" if unsure else f"{yr} में कुल {_jile(count)}"} — हिंदी और अंग्रेज़ी नामों के साथ · {escape(span)}</p>

<div class="nk-tabs-bar">
  <a class="nk-tab-item" href="{_url(key)}#nk-map-wrap">🗺️ इंटरैक्टिव नक्शा</a>
  <a class="nk-tab-item active" href="{_jile_url(key)}">📋 जिलों की सूची{"" if unsure else f" ({count})"}</a>
</div>

<div class="nk-stats-row">
  <div class="nk-stat-card">
    <div class="nk-st-lbl">📊 {"नक्शे पर जिले" if unsure else "कुल जिले"}</div>
    <div class="nk-st-val">{_jile(n) if unsure else _jile(count)}</div>
  </div>
  <div class="nk-stat-card">
    <div class="nk-st-lbl">📐 सबसे बड़ा जिला</div>
    <div class="nk-st-val">{escape(s['big'])}</div>
  </div>
  <div class="nk-stat-card">
    <div class="nk-st-lbl">📏 सबसे छोटा जिला</div>
    <div class="nk-st-val">{escape(s['small'])}</div>
  </div>
</div>

<section class="nk-sec">
  <h2>{escape(hi)} के {"जिलों" if unsure else f"सभी {count} जिलों"} की सूची</h2>
  <p class="nk-lede">हिंदी या अंग्रेज़ी में जिला खोजें — नक्शा देखने के लिए जिले के नाम पर क्लिक करें:</p>
  <input class="nk-search" id="nk-dsearch" type="search" autocomplete="off"
   placeholder="जिला खोजें — जैसे मेरठ, Meerut…" aria-label="जिला खोजें" style="margin-bottom:16px;">
  <p class="nk-empty" id="nk-dnone" style="display:none">कोई जिला नहीं मिला।</p>
  <div class="nk-dgrid">{rows}</div>
  {_extra_html(hi, extra)}
  <div class="nk-cta" style="margin-top:18px">
    <a class="nk-btn plain" href="{_url(key)}">🗺️ {escape(hi)} का पूरा नक्शा देखें</a>
    <a class="nk-btn plain" href="/naksha">🧭 सभी राज्यों के नक्शे</a>
  </div>
</section>

<section class="nk-sec"><h2>{escape(hi)} के जिलों से जुड़े सवाल</h2>{faq_html}</section>

<section class="nk-sec">
  <h2>दूसरे राज्यों के जिले</h2>
  <p class="nk-lede">हर राज्य की पूरी जिला-सूची, नक्शे के साथ —
    <a href="/naksha">सभी {len(states)} राज्य देखें →</a></p>
  <div class="nk-sgrid">{_state_cards(
        [k for k in ([x for x, y in states.items()
                      if y["region"] == s["region"] and x != key]
                     + [p for p in _POPULAR if p != key])][:11], states, jile=True)}</div>
</section>

{note}
<p class="nk-updated">🕒 अंतिम अपडेट: {_hindi_date(_updated())} · सीमा-डेटा: Census of India</p>
<script>
(function(){{
  var q=document.getElementById('nk-dsearch'),none=document.getElementById('nk-dnone');
  if(!q)return;
  var rows=[].slice.call(document.querySelectorAll('.nk-drow'));
  q.addEventListener('input',function(){{
    var v=q.value.trim().toLowerCase(),hits=0;
    rows.forEach(function(r){{
      var on=!v||r.textContent.toLowerCase().indexOf(v)>-1||
             (r.getAttribute('href')||'').toLowerCase().indexOf(v)>-1;
      r.style.display=on?'':'none';if(on)hits++;
    }});
    if(none)none.style.display=hits?'none':'';
  }});
}})();
</script>
{_tail_scripts()}"""

    crumb = _crumb_ld([("होम", f"{SITE}/"), ("राज्यों के नक्शे", f"{SITE}/naksha"),
                       (f"{hi} का नक्शा", _abs(_url(key))), (f"{hi} के जिले", canon)])
    page_ld = {
        "@context": "https://schema.org", "@type": "WebPage",
        "@id": f"{canon}#webpage", "url": canon, "name": title,
        "description": desc, "inLanguage": "hi", "dateModified": _updated(),
        "about": {"@type": "Place", "name": s["en"]},
        "significantLink": [_abs(_url(key)), f"{SITE}/naksha"],
    }
    list_ld = {
        "@context": "https://schema.org", "@type": "ItemList",
        "@id": f"{canon}#districts", "name": f"{hi} के {count} जिले",
        "numberOfItems": n + len(extra),
        "itemListOrder": "https://schema.org/ItemListOrderAscending",
        "itemListElement": [
            {"@type": "ListItem", "position": i,
             "item": {"@type": "AdministrativeArea", "name": d["hi"],
                      "alternateName": d["en"]}}
            for i, d in enumerate(list(s["districts"]) + extra, start=1)],
    }
    robots = "noindex, follow" if n < 3 else ""

    return _doc(title, desc, canon,
                _crumbs([("राज्यों के नक्शे", f"{SITE}/naksha"),
                         (f"{hi} का नक्शा", _url(key)), (f"{hi} के जिले", None)]),
                body, ld=_ld(page_ld, list_ld, crumb, faq_ld),
                og_img=_abs_img(s, "og.png"), active="map", extra_css=_NK_CSS,
                robots=robots)


# ── one district's map (tier 3) ─────────────────────────────────────────────

def _sibling_chips(key: str, s: dict, skip: str) -> str:
    return "".join(
        f'<a class="nk-chip" href="{_d_url(key, slugify(d["en"]))}">📍 {escape(d["hi"])}</a>'
        for d in s["districts"] if slugify(d["en"]) != skip)


# Scheme links go to /sarkari_yojana, which carries the "KrashiMitra एक निजी
# वेबसाइट है" notice LEGAL_RULES §1/§3 require on scheme pages. The per-state
# scheme articles (mahadbt, tarbandi, MP kisan kalyan) do not carry it yet, so
# ~780 district pages must not start sending traffic to them until they do.


def _nk_card(cls: str, href: str, ic: str, title: str, sub: str, ext: bool = False) -> str:
    """One quick-link card on the state and district map pages."""
    tgt = ' target="_blank" rel="noopener"' if ext else ""
    return (f'<a class="nk-farmer-card {cls}" href="{href}"{tgt}>'
            f'<div class="nk-farmer-card-ic">{ic}</div>'
            f'<div class="nk-farmer-card-body">'
            f'<div class="nk-farmer-card-title">{escape(title)}</div>'
            f'<div class="nk-farmer-card-sub">{escape(sub)}</div></div>'
            f'<div class="nk-farmer-card-arrow">➔</div></a>')


def _state_bhav_link(key: str) -> str:
    """The state's own price hub when the mandi feed has it, else /bhav."""
    try:
        from backend.routes import bhav as _bhav
        if _bhav._dists_in_state(_bhav._get_index(), key):
            return f"/bhav/rajya/{key}"
    except Exception:
        pass
    return "/bhav"


def _district_bhav_link(key: str, dslug: str) -> tuple:
    """(href, sub-line) for "<district> मंडी भाव".

    The card used to point at /bhav, the all-India hub — two picks away from
    the district it was named after. Now: the district's own price board when
    the mandi feed knows this district under the same name, else the state's,
    else the hub. Names can differ between Census (the map) and Agmarknet
    (the prices) — Hoshangabad/Narmadapuram — and a guessed link must never
    404, so only a slug the price index actually holds is linked.
    """
    try:
        from backend.routes import bhav as _bhav
        idx = _bhav._get_index()
        if dslug in _bhav._dists_in_state(idx, key):
            return f"/bhav/rajya/{key}/{dslug}", "इस जिले की मंडियों में आज के सभी फसल भाव"
        if _bhav._dists_in_state(idx, key):
            return f"/bhav/rajya/{key}", "राज्य की मंडियों में आज के फसल भाव"
    except Exception:
        pass
    return "/bhav", "देशभर की मंडियों में आज के फसल भाव"


def _district_page(key: str, dslug: str) -> HTMLResponse:
    states = _states()
    s = states[key]
    d = _dindex(key)[dslug]
    hi, en, shi = d["hi"], d["en"], s["hi"]
    canon = _abs(_d_url(key, dslug))
    n = s["n"]
    count, _extra, unsure = _district_count(key, s)
    # "<state> के 55 जिलों में से एक" — the state's count today, not the map's.
    of_n = f"{shi} का एक जिला" if unsure else f"{shi} के {count} जिलों में से एक"

    village_service.request(key, dslug, {"geojson": s["geojson"], "en": en, "hi": hi})
    villages = village_service.load(key, dslug) or []

    # Same split as the state page above, and the one title on this route that
    # was still a single f-string rather than a _fit ladder. The English name
    # was already in the description ("Ahmedabad district map") and only ever
    # in the description — which is why "ahmedabad map" sat at position 4.7
    # with no clicks at all.
    title = _fit(
        f"{hi} का नक्शा – {shi} | {en} District Map, गांव व सैटेलाइट व्यू",
        f"{hi} का नक्शा – {shi} | {en} District Map, सैटेलाइट व्यू",
        f"{hi} का नक्शा – {shi} | {en} District Map",
        f"{hi} का नक्शा – {shi} | {en} Map",
        f"{hi} का नक्शा – {shi} | जिला मानचित्र, गांव व सैटेलाइट व्यू",
        f"{hi} का नक्शा – {shi} | जिला मानचित्र",
        f"{hi} का नक्शा – {shi}")
    # The title above went through a _fit ladder on 2026-09-06; this description
    # was left behind as a single f-string and has been over budget ever since.
    # Measured 2026-09-12 against production: 10 of 10 sampled district pages
    # rendered 190-221 chars against Google's 162, so every one of them was cut
    # mid-sentence — on 768 sitemap URLs carrying 216k impressions at 0.63%.
    # Same rule as the title: pick a whole shorter sentence, never a slice.
    desc = _fit(
        f"{hi} जिले का नक्शा ({en} district map) — {of_n}। "
        f"सैटेलाइट व्यू में अपना गांव और तहसील देखें, और {shi} का पूरा HD नक्शा "
        f"मुफ्त डाउनलोड करें।",
        f"{hi} जिले का नक्शा ({en} district map) — {of_n}। "
        f"सैटेलाइट व्यू में गांव व तहसील देखें, HD नक्शा मुफ्त डाउनलोड करें।",
        f"{hi} का नक्शा ({en} district map) — {of_n}। "
        f"सैटेलाइट व्यू में गांव व तहसील देखें, HD नक्शा मुफ्त डाउनलोड।",
        f"{hi} जिले का नक्शा ({en} district map), {shi}। सैटेलाइट व्यू में गांव व "
        f"तहसील देखें, HD नक्शा मुफ्त डाउनलोड करें।",
        f"{hi} जिले का नक्शा ({en} district map) — सैटेलाइट व्यू, गांव व तहसील, "
        f"HD नक्शा मुफ्त डाउनलोड।",
        f"{hi} का नक्शा ({en} district map) — सैटेलाइट व्यू व HD डाउनलोड।",
        limit=162)

    v_line = (f"इस जिले के {len(villages)} गांव व कस्बे सूची में दर्ज हैं।"
              if villages else
              "गांव व तहसील नाम से खोजें — नक्शा सीधे वहीं ज़ूम हो जाएगा।")
    v_cta = (f'<a class="nk-btn primary" href="{_gaon_url(key, dslug)}">'
             f'{hi} के गांवों की सूची देखें →</a>' if villages else
             f'<a class="nk-btn plain" href="{_gaon_url(key, dslug)}">'
             f'गांव खोजें →</a>')

    faq_html, faq_ld = _faq([
        (f"{hi} जिला किस राज्य में है?",
         f"{hi} ({en}) {shi} का एक जिला है। "
         + ("" if unsure else f"{shi} में कुल {count} जिले हैं, और ") + f"इस पेज पर "
         f"{hi} की सीमा पूरे राज्य के नक्शे में हाइलाइट करके दिखाई गई है।"),
        (f"{hi} जिले का सैटेलाइट नक्शा कैसे देखें?",
         f"ऊपर का नक्शा डिफ़ॉल्ट रूप से सैटेलाइट व्यू में ही खुलता है — असली खेत, "
         f"सड़कें और बस्तियां दिखती हैं। ज़ूम करके अपना खेत तक पहचाना जा सकता है, और "
         f"GPS व 🔍 बटन से गांव या खेत तक सीधे पहुंचा जा सकता है।"),
        (f"{hi} जिले में कौन-कौन से गांव हैं?",
         (f"{hi} के {len(villages)} गांव व कस्बे इस समय दर्ज हैं — पूरी सूची “{hi} के "
          f"गांव” पेज पर है, हर गांव के अपने नक्शे के साथ।") if villages else
         (f"{hi} के गांवों की सूची तैयार हो रही है। तब तक नक्शे के खोज बॉक्स से गांव या "
          f"तहसील का नाम डालकर उसे सीधे सैटेलाइट नक्शे पर देखा जा सकता है।")),
        (f"{hi} का नक्शा डाउनलोड कैसे करें?",
         f"“HD नक्शा डाउनलोड करें” बटन से {shi} का पूरा जिलेवार नक्शा (PNG) मुफ्त "
         f"डाउनलोड होता है — उसमें {hi} समेत सभी {n} जिले हिंदी नामों के साथ हैं। "
         f"नक्शा CC BY 4.0 पर है, स्रोत में KrashiMitra.in लिख दें।"),
    ])

    bhulekh_info = _BHULEKH.get(key, ("https://upbhulekh.gov.in/", "भूलेख पोर्टल"))
    bhulekh_url = bhulekh_info[0]
    bhulekh_label = bhulekh_info[1]

    map_container = _map_app_container(
        key, s, shi, is_district=True, dslug=dslug, dist_hi=hi, dist_en=en
    )

    # Four cards, 2×2 on a phone. Weather is only offered where /weather has
    # it (Uttar Pradesh's districts) and says so; elsewhere that slot goes to
    # the state's schemes rather than promising a forecast we do not have.
    _card = _nk_card

    bhav_href, bhav_sub = _district_bhav_link(key, dslug)
    scheme_href, scheme_name = "/sarkari_yojana", "सरकारी किसान योजनाएं"
    cards = [_card("bhav", bhav_href, "💰", f"{hi} मंडी भाव", bhav_sub)]
    if key == "uttar-pradesh":
        cards.append(_card("weather", "/weather", "🌤️", "मौसम पूर्वानुमान",
                           "उत्तर प्रदेश के सभी जिलों का आज का मौसम"))
    cards.append(_card("yojana", scheme_href, "📜", scheme_name,
                       "पात्रता, दस्तावेज़ व आधिकारिक लिंक"))
    cards.append(_card("bhulekh", bhulekh_url, "📄", f"{hi} भूलेख (खसरा-खतौनी)",
                       "आधिकारिक भू-अभिलेख पोर्टल ↗", ext=True))
    if key != "uttar-pradesh":
        cards.append(_card("gaon", _gaon_url(key, dslug), "🌾", f"{hi} के गांव व कस्बे",
                           f"सैटेलाइट नक्शा व {len(villages) if villages else 'सभी'} गांव खोजें"))
    link_cards = "".join(cards)

    body = f"""<div class="nk-level-bar">
  <a href="/naksha">🇮🇳 भारत (India)</a>
  <span class="nk-lvl-sep">➔</span>
  <a href="{_url(key)}">🏛️ {escape(shi)}</a>
  <span class="nk-lvl-sep">➔</span>
  <a href="{_jile_url(key)}">📋 जिले{"" if unsure else f" ({count})"}</a>
  <span class="nk-lvl-sep">➔</span>
  <span style="color:var(--nk-emerald-dark)">📍 {escape(hi)}</span>
</div>

<h1 class="nk-title">{escape(hi)} का नक्शा</h1>
<p class="nk-title-sub">{escape(en)} district, {escape(shi)} · सैटेलाइट व्यू · गांव व तहसील खोज</p>

<div class="nk-tabs-bar">
  <a class="nk-tab-item active" href="{_d_url(key, dslug)}">🗺️ {escape(hi)} का नक्शा</a>
  <a class="nk-tab-item" href="{_gaon_url(key, dslug)}">🌾 गांव की सूची{f' ({len(villages)})' if villages else ''}</a>
  <a class="nk-tab-item" href="{_jile_url(key)}">📋 {escape(shi)} के जिले</a>
</div>

{map_container}

<!-- District quick links: this district's prices first, then the rest -->
<div class="nk-farmer-grid">{link_cards}</div>

<!-- Compact HD Map Download Banner -->
{_dl_card(s, f"⬇️ {shi} का HD नक्शा",
          f"{hi} समेत सभी जिलों के नाम हिंदी में · PNG या A4 PDF, मुफ्त",
          f"{shi} का नक्शा ({s['en']} Map) — {hi} समेत {n} जिलों का हिंदी जिलेवार मानचित्र")}

<!-- 4 Fact Metric Boxes -->
<div class="nk-facts-bar">
  <div class="nk-fact-box">
    <small>जिला</small>
    <b>{escape(hi)}</b>
  </div>
  <div class="nk-fact-box">
    <small>राज्य</small>
    <b>{escape(shi)}</b>
  </div>
  <div class="nk-fact-box">
    <small>अंग्रेज़ी नाम</small>
    <b>{escape(en)}</b>
  </div>
  <div class="nk-fact-box">
    <small>दर्ज गांव / कस्बे</small>
    <b>{len(villages) if villages else '—'}</b>
  </div>
</div>

<section class="nk-sec"><h2>{escape(hi)} के नक्शे से जुड़े सवाल</h2>{faq_html}</section>

<section class="nk-sec">
  <h2>{escape(shi)} के दूसरे जिले</h2>
  <p class="nk-lede">हर जिले का अपना नक्शा, सैटेलाइट व्यू और गांव सूची —
    <a href="{_jile_url(key)}">{escape(shi)} के सभी {n} जिले देखें →</a></p>
  <div class="nk-chips">{_sibling_chips(key, s, dslug)}</div>
</section>

<section class="nk-sec">
  <h2>दूसरे राज्यों के नक्शे</h2>
  <p class="nk-lede">हर नक्शा हिंदी में, जिलेवार, मुफ्त HD डाउनलोड के साथ —
    <a href="/naksha">सभी {len(states)} राज्य देखें →</a></p>
  <div class="nk-sgrid">{_others(key, states)}</div>
</section>

<p class="nk-updated">🕒 अंतिम अपडेट: {_hindi_date(_updated())} · जिला-सीमा: Census of India · गांव-बिंदु: OpenStreetMap</p>
{_tail_scripts(s, initial=hi, state_key=key, dslug=dslug)}"""


    crumb = _crumb_ld([("होम", f"{SITE}/"), ("राज्यों के नक्शे", f"{SITE}/naksha"),
                       (f"{shi} का नक्शा", _abs(_url(key))),
                       (f"{shi} के जिले", _abs(_jile_url(key))),
                       (f"{hi} का नक्शा", canon)])
    page_ld = {
        "@context": "https://schema.org", "@type": "WebPage",
        "@id": f"{canon}#webpage", "url": canon, "name": title,
        "description": desc, "inLanguage": "hi", "dateModified": _updated(),
        "about": {"@id": f"{canon}#place"},
        "significantLink": [_abs(_gaon_url(key, dslug)), _abs(_url(key)),
                            _abs(_jile_url(key))],
    }
    place_ld = {
        "@context": "https://schema.org", "@type": "AdministrativeArea",
        "@id": f"{canon}#place", "name": hi, "alternateName": en,
        "url": canon,
        "containedInPlace": {"@type": "AdministrativeArea", "name": s["en"],
                             "alternateName": s["hi"], "url": _abs(_url(key))},
        "additionalType": "https://www.wikidata.org/wiki/Q1149652",
    }
    return _doc(title, desc, canon,
                _crumbs([("राज्यों के नक्शे", f"{SITE}/naksha"),
                         (f"{shi} का नक्शा", _url(key)), (f"{hi} का नक्शा", None)]),
                body, ld=_ld(page_ld, place_ld, crumb, faq_ld),
                og_img=_abs_img(s, "og.png"), active="map",
                extra_css=_NK_CSS, head_extra=_LEAFLET_CSS)


# ── one district's villages (tier 4) ────────────────────────────────────────

_PLACE_HI = {"city": "शहर", "town": "कस्बा", "village": "गांव", "hamlet": "टोला"}


def _gaon_page(key: str, dslug: str) -> HTMLResponse:
    states = _states()
    s = states[key]
    d = _dindex(key)[dslug]
    hi, en, shi = d["hi"], d["en"], s["hi"]
    canon = _abs(_gaon_url(key, dslug))

    village_service.request(key, dslug, {"geojson": s["geojson"], "en": en, "hi": hi})
    villages = village_service.load(key, dslug) or []
    n_v = len(villages)

    if n_v:
        title = f"{hi} के गांव – {n_v} गांव व कस्बों की सूची और नक्शा ({shi})"
        desc = (f"{hi} जिले ({shi}) के {n_v} गांव व कस्बे — हर नाम पर टैप करके उस गांव "
                f"का सैटेलाइट नक्शा देखें। गांव की स्थिति, निर्देशांक और आसपास के गांव, "
                f"सब एक जगह।")
    else:
        title = f"{hi} के गांव का नक्शा – सैटेलाइट व्यू ({shi})"
        desc = (f"{hi} जिले ({shi}) में अपने गांव या तहसील का सैटेलाइट नक्शा देखें — "
                f"नाम डालिए, नक्शा सीधे वहीं ज़ूम हो जाएगा।")

    # The sub-line carries the English spelling only where it differs from the
    # Hindi one — most OSM places have no name:hi, and echoing the same string
    # twice is what a broken template looks like.
    def _row(i: int, v: dict) -> str:
        primary = v["hi"] or v["name"]
        sub = " · ".join(x for x in (v["name"] if v["hi"] else "",
                                     _PLACE_HI.get(v["place"], "")
                                     if v["place"] != "village" else "") if x)
        return (f'<div class="nk-drow"><span class="nk-num">{i}</span>'
                f'<a class="nk-dname" href="{_v_url(key, dslug, v["slug"])}" '
                f'title="{escape(primary)} का नक्शा"><b>{escape(primary)}</b>'
                + (f'<span class="nk-en">{escape(sub)}</span>' if sub else "")
                + '</a></div>')

    rows = "".join(_row(i, v) for i, v in enumerate(villages, start=1))

    pending = "" if n_v else f"""<div class="nk-note">
{escape(hi)} के गांवों की सूची अभी तैयार हो रही है — OpenStreetMap से जिले की सीमा के
भीतर पड़ने वाले गांव जोड़े जा रहे हैं। तब तक नीचे नाम डालकर कोई भी गांव या तहसील
सीधे सैटेलाइट नक्शे पर देखी जा सकती है।</div>"""

    faq_html, faq_ld = _faq([
        (f"{hi} जिले में कितने गांव हैं?",
         (f"इस पेज पर {hi} के {n_v} गांव, कस्बे और शहर दर्ज हैं — ये वे बस्तियां हैं जो "
          f"OpenStreetMap में नाम के साथ मौजूद हैं और {hi} की जिला-सीमा के भीतर पड़ती हैं। "
          f"राजस्व रिकॉर्ड के मजरे-टोले इससे ज़्यादा हो सकते हैं।") if n_v else
         (f"{hi} के गांवों की सूची तैयार हो रही है। तब तक ऊपर खोज बॉक्स में गांव का नाम "
          f"डालकर उसका सैटेलाइट नक्शा देखा जा सकता है।")),
        (f"अपने गांव का नक्शा कैसे देखें?",
         f"ऊपर की सूची में गांव के नाम पर टैप करें — उस गांव का अपना पेज खुलेगा जिसमें "
         f"सैटेलाइट नक्शा उसी जगह पर केंद्रित होगा। नाम सूची में न मिले तो खोज बॉक्स में "
         f"लिखकर सीधे नक्शे पर खोजा जा सकता है।"),
        (f"क्या इसमें खेत की सीमा (खसरा/खतौनी) दिखती है?",
         f"नहीं। यहां सैटेलाइट तस्वीर और गांव की स्थिति दिखती है, राजस्व नक्शा नहीं। "
         f"खसरा-खतौनी या भू-नक्शा के लिए अपने राज्य के राजस्व विभाग का पोर्टल देखें।"),
        (f"गांव की जानकारी कहां से आती है?",
         f"गांव के नाम और निर्देशांक OpenStreetMap (ODbL) से हैं, और जिले की सीमा "
         f"Census of India के डेटा से — गांव को जिले में तभी गिना जाता है जब वह उस "
         f"सीमा के भीतर पड़ता हो।"),
    ])

    body = f"""<div class="nk-level-bar">
  <a href="/naksha">🇮🇳 भारत (India)</a>
  <span class="nk-lvl-sep">➔</span>
  <a href="{_url(key)}">🏛️ {escape(shi)}</a>
  <span class="nk-lvl-sep">➔</span>
  <a href="{_d_url(key, dslug)}">📍 {escape(hi)}</a>
  <span class="nk-lvl-sep">➔</span>
  <span style="color:var(--nk-emerald-dark)">🌾 गांव</span>
</div>

<h1 class="nk-title">{escape(hi)} के गांव</h1>
<p class="nk-title-sub">{escape(shi)} · {f'{n_v} गांव व कस्बे' if n_v else 'गांव व तहसील खोज'} · हर गांव का अपना सैटेलाइट नक्शा</p>

<div class="nk-tabs-bar">
  <a class="nk-tab-item" href="{_d_url(key, dslug)}">🗺️ {escape(hi)} का नक्शा</a>
  <a class="nk-tab-item active" href="{_gaon_url(key, dslug)}">🌾 गांव की सूची{f' ({n_v})' if n_v else ''}</a>
  <a class="nk-tab-item" href="{_jile_url(key)}">📋 {escape(shi)} के जिले</a>
</div>

{pending}

<section class="nk-sec">
  <h2>{escape(hi)} के गांव, कस्बे और शहर</h2>
  <p class="nk-lede">गांव का नाम हिंदी या अंग्रेज़ी में खोजें — नक्शा देखने के लिए नाम पर टैप करें:</p>
  <input class="nk-search" id="nk-vlist-search" type="search" autocomplete="off"
   placeholder="गांव खोजें — जैसे {escape(villages[0]['name']) if villages else 'मवाना, Mawana'}…"
   aria-label="गांव खोजें" style="margin-bottom:16px;">
  <p class="nk-empty" id="nk-vlist-none" style="display:none">इस सूची में यह गांव नहीं मिला — नीचे नक्शे पर खोजें।</p>
  <div class="nk-dgrid">{rows}</div>
  <div class="nk-cta" style="margin-top:18px">
    <a class="nk-btn plain" href="{_d_url(key, dslug)}">🗺️ {escape(hi)} का पूरा नक्शा</a>
    <a class="nk-btn plain" href="{_jile_url(key)}">📋 {escape(shi)} के सभी जिले</a>
  </div>
</section>

<section class="nk-sec"><h2>{escape(hi)} के गांवों से जुड़े सवाल</h2>{faq_html}</section>

<section class="nk-sec">
  <h2>{escape(shi)} के दूसरे जिले</h2>
  <p class="nk-lede">हर जिले की अपनी गांव-सूची और सैटेलाइट नक्शा:</p>
  <div class="nk-chips">{_sibling_chips(key, s, dslug)}</div>
</section>

<p class="nk-updated">🕒 अंतिम अपडेट: {_hindi_date(_updated())} · गांव-बिंदु: OpenStreetMap (ODbL) · जिला-सीमा: Census of India</p>
<script>
(function(){{
  var q=document.getElementById('nk-vlist-search'),none=document.getElementById('nk-vlist-none');
  if(!q)return;
  var rows=[].slice.call(document.querySelectorAll('.nk-drow'));
  q.addEventListener('input',function(){{
    var v=q.value.trim().toLowerCase(),hits=0;
    rows.forEach(function(r){{
      var on=!v||r.textContent.toLowerCase().indexOf(v)>-1;
      r.style.display=on?'':'none';if(on)hits++;
    }});
    if(none)none.style.display=hits?'none':'';
  }});
}})();
</script>
{_tail_scripts()}"""

    crumb = _crumb_ld([("होम", f"{SITE}/"), ("राज्यों के नक्शे", f"{SITE}/naksha"),
                       (f"{shi} का नक्शा", _abs(_url(key))),
                       (f"{hi} का नक्शा", _abs(_d_url(key, dslug))),
                       (f"{hi} के गांव", canon)])
    page_ld = {
        "@context": "https://schema.org", "@type": "CollectionPage",
        "@id": f"{canon}#webpage", "url": canon, "name": title,
        "description": desc, "inLanguage": "hi", "dateModified": _updated(),
        "about": {"@type": "AdministrativeArea", "name": hi, "alternateName": en,
                  "url": _abs(_d_url(key, dslug))},
    }
    blocks = [page_ld, crumb, faq_ld]
    if villages:
        blocks.insert(1, {
            "@context": "https://schema.org", "@type": "ItemList",
            "@id": f"{canon}#villages", "name": f"{hi} के गांव",
            "numberOfItems": n_v,
            "itemListOrder": "https://schema.org/ItemListOrderAscending",
            "itemListElement": [
                {"@type": "ListItem", "position": i,
                 "url": _abs(_v_url(key, dslug, v["slug"])),
                 "name": v["hi"] or v["name"]}
                for i, v in enumerate(villages, start=1)],
        })

    # No villages yet means no unique content — the search box is on every other
    # page in the cluster. Keep the page (the links work, and it is what queues
    # the fetch) but out of the index until it has something of its own to say.
    robots = "" if n_v else "noindex, follow"
    return _doc(title, desc, canon,
                _crumbs([("राज्यों के नक्शे", f"{SITE}/naksha"),
                         (f"{hi} का नक्शा", _d_url(key, dslug)),
                         (f"{hi} के गांव", None)]),
                body, ld=_ld(*blocks), og_img=_abs_img(s, "og.png"),
                active="map", extra_css=_NK_CSS, robots=robots)


# ── one village (tier 5) ────────────────────────────────────────────────────

def _km(a: dict, b: dict) -> float:
    """Great-circle km. Used only to rank a village's neighbours, so the sphere
    approximation is far below the precision anyone reads off the page."""
    p = math.pi / 180
    dlat, dlon = (b["lat"] - a["lat"]) * p, (b["lon"] - a["lon"]) * p
    h = (math.sin(dlat / 2) ** 2
         + math.cos(a["lat"] * p) * math.cos(b["lat"] * p) * math.sin(dlon / 2) ** 2)
    return 2 * 6371 * math.asin(math.sqrt(h))


def _village_scripts(v: dict, label: str) -> str:
    """A village map is one marker on satellite tiles — no geojson, no district
    layer, no dropdown. Loading the state's boundary file (up to 200 KB) to draw
    a single pin is the kind of thing that makes these pages fail CWV on a 3G
    phone, which is most of the audience."""
    return f"""<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
(function(){{
  var done = false;
  function init(){{
    if(done) return;
    if(!window.L) {{
      var tries = 0;
      var t = setInterval(function(){{
        tries++;
        if(window.L) {{
          clearInterval(t);
          init();
        }} else if(tries > 80) {{
          clearInterval(t);
          console.error('Leaflet load timed out');
        }}
      }}, 100);
      return;
    }}
    done = true;
    var lat={v['lat']}, lon={v['lon']};
    var map=L.map('nk-map',{{zoomSnap:0.25}}).setView([lat,lon],13);
    // See _tail_scripts: request no deeper than the provider has a picture,
    // then let Leaflet upscale, so zooming in never lands on Esri's grey card.
    var sat=L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}',
      {{attribution:'Tiles © Esri World Imagery',maxNativeZoom:18,maxZoom:20}}).addTo(map);
    var labels=L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{{z}}/{{y}}/{{x}}',
      {{attribution:'© Esri',maxNativeZoom:18,maxZoom:20}}).addTo(map);
    var osm=L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',
      {{attribution:'© OpenStreetMap contributors',maxNativeZoom:19,maxZoom:20}});
    L.control.layers({{"🛰️ सैटेलाइट (Satellite)":sat,"🗺️ नक्शा (Map)":osm}},
                     {{"🏘️ गांव व सड़क लेबल":labels}},{{position:'topright'}}).addTo(map);
    L.marker([lat,lon]).addTo(map).bindPopup({label}).openPopup();
    setTimeout(function(){{map.invalidateSize();}},100);
    setTimeout(function(){{map.invalidateSize();}},400);
    setTimeout(function(){{map.invalidateSize();}},1200);
  }}

  if(document.readyState === 'loading') {{
    document.addEventListener('DOMContentLoaded', init);
  }} else {{
    init();
  }}
  window.addEventListener('load', init);
}})();
</script>"""


def _village_page(key: str, dslug: str, v: dict, villages: list) -> HTMLResponse:
    states = _states()
    s = states[key]
    d = _dindex(key)[dslug]
    dhi, shi = d["hi"], s["hi"]
    name_en = v["name"]
    name_hi = v["hi"] or name_en
    # OSM carries name:hi for only some places. Where it is missing the English
    # name IS the name — printing "Mawana (Mawana)" reads as a template leaking,
    # so the bilingual form only appears when there really are two spellings.
    both = f"{name_hi} ({name_en})" if v["hi"] else name_hi
    kind = _PLACE_HI.get(v["place"], "गांव")
    canon = _abs(_v_url(key, dslug, v["slug"]))

    near = sorted((x for x in villages if x["slug"] != v["slug"]),
                  key=lambda x: _km(v, x))[:12]

    title = f"{name_hi} का नक्शा – {dhi}, {shi} | गांव सैटेलाइट व्यू"
    desc = (f"{both} — {dhi} जिला, {shi} का {kind}। सैटेलाइट नक्शे में खेत, सड़क और "
            f"बस्ती देखें। निर्देशांक {v['lat']}, {v['lon']}। आसपास के गांवों के "
            f"नक्शे भी इसी पेज से।")

    near_chips = "".join(
        f'<a class="nk-chip" href="{_v_url(key, dslug, x["slug"])}">'
        f'📍 {escape(x["hi"] or x["name"])} <span class="nk-km">{_km(v, x):.0f} km</span></a>'
        for x in near)

    faq_html, faq_ld = _faq([
        (f"{name_hi} किस जिले और राज्य में है?",
         f"{both} {shi} राज्य के {dhi} जिले में है। इसके निर्देशांक "
         f"{v['lat']}° N, {v['lon']}° E हैं।"),
        (f"{name_hi} का सैटेलाइट नक्शा कैसे देखें?",
         f"इस पेज का नक्शा सैटेलाइट व्यू में ही खुलता है और {name_hi} पर केंद्रित है — "
         f"ज़ूम करके खेत, रास्ते और घर तक पहचाने जा सकते हैं। ऊपर दाईं ओर के बटन से "
         f"सामान्य नक्शा भी चुना जा सकता है।"),
        (f"{name_hi} के पास कौन से गांव हैं?",
         (f"सबसे नज़दीक {', '.join((x['hi'] or x['name']) for x in near[:5])} हैं — "
          f"पूरी सूची नीचे “आसपास के गांव” में है, हर एक के अपने नक्शे के साथ।")
         if near else
         f"{dhi} जिले के बाकी गांवों की सूची “{dhi} के गांव” पेज पर है।"),
        (f"क्या यहां {name_hi} का भू-नक्शा या खसरा मिलेगा?",
         f"नहीं। यह सैटेलाइट और स्थान का नक्शा है, राजस्व नक्शा नहीं। खसरा-खतौनी या "
         f"भू-नक्शा के लिए {shi} के राजस्व विभाग का आधिकारिक पोर्टल देखें।"),
    ])

    body = f"""<div class="nk-level-bar">
  <a href="/naksha">🇮🇳 भारत</a>
  <span class="nk-lvl-sep">➔</span>
  <a href="{_url(key)}">🏛️ {escape(shi)}</a>
  <span class="nk-lvl-sep">➔</span>
  <a href="{_d_url(key, dslug)}">📍 {escape(dhi)}</a>
  <span class="nk-lvl-sep">➔</span>
  <a href="{_gaon_url(key, dslug)}">🌾 गांव</a>
  <span class="nk-lvl-sep">➔</span>
  <span style="color:var(--nk-emerald-dark)">{escape(name_hi)}</span>
</div>

<h1 class="nk-title">{escape(name_hi)} का नक्शा</h1>
<p class="nk-title-sub">{escape(name_en + " · ") if v["hi"] else ""}{escape(kind)} · {escape(dhi)} जिला, {escape(shi)} · सैटेलाइट व्यू</p>

<div class="nk-tabs-bar">
  <a class="nk-tab-item active" href="{_v_url(key, dslug, v['slug'])}">📍 {escape(name_hi)} का नक्शा</a>
  <a class="nk-tab-item" href="{_gaon_url(key, dslug)}">🌾 {escape(dhi)} के सभी गांव</a>
  <a class="nk-tab-item" href="{_d_url(key, dslug)}">🗺️ {escape(dhi)} का नक्शा</a>
</div>

<div class="nk-app-map-wrap" id="nk-map-wrap" style="height:62vh;min-height:380px;">
  <div id="nk-map" class="nk-map"></div>
</div>

<div class="nk-side-card">
  <div class="nk-side-grid">
    <div>
      <h3 style="font-size:16.5px;font-weight:800;color:var(--nk-emerald-dark);margin:0 0 12px">📍 {escape(name_hi)} — एक नज़र में</h3>
      <dl class="nk-facts-list">
        <dt>प्रकार</dt><dd>{escape(kind)}</dd>
        <dt>जिला</dt><dd>{escape(dhi)}</dd>
        <dt>राज्य</dt><dd>{escape(shi)}</dd>
        <dt>अक्षांश</dt><dd>{v['lat']}° N</dd>
        <dt>देशांतर</dt><dd>{v['lon']}° E</dd>
      </dl>
    </div>
    <div>
      <h3 style="font-size:16.5px;font-weight:800;color:var(--nk-emerald-dark);margin:0 0 12px">⚡ त्वरित सुविधाएं</h3>
      <div style="display:flex;flex-direction:column;gap:8px">
        <a class="nk-btn plain" href="{_d_url(key, dslug)}">🗺️ {escape(dhi)} का पूरा नक्शा</a>
        <a class="nk-btn plain" href="{_gaon_url(key, dslug)}">🌾 {escape(dhi)} के सभी गांव</a>
        <a class="nk-btn plain" href="/weather">🌤️ {escape(dhi)} का मौसम</a>
        <a class="nk-btn plain" href="/bhav">💰 आज का मंडी भाव</a>
      </div>
    </div>
  </div>
</div>

<section class="nk-sec">
  <h2>{escape(name_hi)} के आसपास के गांव</h2>
  <p class="nk-lede">सीधी दूरी के हिसाब से सबसे नज़दीक — किसी भी नाम पर टैप करके उसका नक्शा देखें:</p>
  <div class="nk-chips">{near_chips or '<p class="nk-empty">आसपास का कोई और गांव अभी दर्ज नहीं है।</p>'}</div>
</section>

<section class="nk-sec"><h2>{escape(name_hi)} से जुड़े सवाल</h2>{faq_html}</section>

<p class="nk-updated">🕒 अंतिम अपडेट: {_hindi_date(_updated())} · स्थान-डेटा: OpenStreetMap (ODbL) · जिला-सीमा: Census of India</p>
{_village_scripts(v, json.dumps(f"<b>🌾 {name_hi}</b><br>{dhi}, {shi}", ensure_ascii=False))}"""

    crumb = _crumb_ld([("होम", f"{SITE}/"), ("राज्यों के नक्शे", f"{SITE}/naksha"),
                       (f"{shi} का नक्शा", _abs(_url(key))),
                       (f"{dhi} का नक्शा", _abs(_d_url(key, dslug))),
                       (f"{dhi} के गांव", _abs(_gaon_url(key, dslug))),
                       (f"{name_hi} का नक्शा", canon)])
    page_ld = {
        "@context": "https://schema.org", "@type": "WebPage",
        "@id": f"{canon}#webpage", "url": canon, "name": title,
        "description": desc, "inLanguage": "hi", "dateModified": _updated(),
        "about": {"@id": f"{canon}#place"},
    }
    place_ld = {
        "@context": "https://schema.org", "@type": "Place",
        "@id": f"{canon}#place", "name": name_hi,
        # Only when there are genuinely two spellings — alternateName echoing
        # name is noise a validator flags and a rich result never uses.
        **({"alternateName": name_en} if v["hi"] else {}),
        "url": canon,
        "geo": {"@type": "GeoCoordinates", "latitude": v["lat"],
                "longitude": v["lon"], "addressCountry": "IN"},
        "address": {"@type": "PostalAddress", "addressLocality": name_en,
                    "addressRegion": s["en"], "addressCountry": "IN"},
        "containedInPlace": {"@type": "AdministrativeArea", "name": dhi,
                             "alternateName": d["en"],
                             "url": _abs(_d_url(key, dslug))},
    }
    return _doc(title, desc, canon,
                _crumbs([("राज्यों के नक्शे", f"{SITE}/naksha"),
                         (f"{dhi} के गांव", _gaon_url(key, dslug)),
                         (name_hi, None)]),
                body, ld=_ld(page_ld, place_ld, crumb, faq_ld),
                og_img=_abs_img(s, "og.png"), active="map",
                extra_css=_NK_CSS, head_extra=_LEAFLET_CSS)



# ── /map landing page — state selection hub ─────────────────────────────────

def _map_landing_page() -> HTMLResponse:
    """A clean funnel landing page: farmer picks their state first."""
    states = _states()

    # Build regional groups
    regions: dict[str, list] = {}
    for k, s in states.items():
        regions.setdefault(s["region"], []).append(k)

    # Popular farming states row (top quick picks)
    popular_keys = [k for k in _POPULAR if k in states]

    def _state_pick_card(k: str) -> str:
        s = states[k]
        return (
            f'<a class="nk-pick-card" href="{_url(k)}" data-state="{k}" '
            f'data-hi="{escape(s["hi"])}">'
            f'<span class="nk-pick-name">{escape(s["hi"])}</span>'
            f'<span class="nk-pick-count">{_jile(_now_n(k, s))}</span>'
            f'<span class="nk-pick-arrow">›</span>'
            f'</a>'
        )

    popular_html = "".join(_state_pick_card(k) for k in popular_keys)

    region_html_parts = []
    for region in _REGION_ORDER:
        if region not in regions:
            continue
        keys = regions[region]
        cards = "".join(_state_pick_card(k) for k in keys)
        region_html_parts.append(
            f'<div class="nk-region-group" data-region="{escape(region)}">'
            f'<h3 class="nk-region-head">{escape(region)}</h3>'
            f'<div class="nk-pick-grid">{cards}</div>'
            f'</div>'
        )
    all_regions_html = "".join(region_html_parts)

    landing_css = """
<style>
/* ── Map Landing Hub ── */
.nk-land-hero {
  background: linear-gradient(135deg, var(--nk-emerald-dark) 0%, #0d3d2a 100%);
  padding: 28px 20px 22px;
  text-align: center;
  margin-bottom: 0;
}
.nk-land-hero h1 {
  font-size: 24px;
  font-weight: 900;
  color: #ffffff;
  margin: 0 0 6px;
  line-height: 1.3;
}
.nk-land-hero p {
  font-size: 13.5px;
  color: rgba(255,255,255,0.78);
  margin: 0 0 18px;
}
/* Search box */
.nk-land-search-wrap {
  display: flex;
  gap: 8px;
  max-width: 480px;
  margin: 0 auto 14px;
  background: #ffffff;
  border-radius: 999px;
  padding: 6px 8px 6px 16px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.28);
  align-items: center;
}
.nk-land-search-wrap input {
  flex: 1;
  border: none;
  outline: none;
  font-size: 14px;
  font-weight: 600;
  color: var(--nk-text-dark);
  background: transparent;
  font-family: inherit;
}
.nk-land-search-wrap input::placeholder { color: #8aaa97; font-weight: 500; }
.nk-land-gps-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 8px 14px;
  border-radius: 999px;
  background: var(--nk-gold);
  border: none;
  color: #071f16;
  font-size: 12.5px;
  font-weight: 800;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.2s ease;
}
.nk-land-gps-btn:hover { transform: scale(1.04); background: #f0ac1a; }
.nk-land-gps-btn.loading { opacity: 0.7; pointer-events: none; }
.nk-land-gps-btn.loading .nk-land-gps-ic { display: inline-block; animation: nkSpin 0.9s linear infinite; }
/* GPS status bar */
.nk-land-gps-status {
  display: none;
  background: rgba(255,255,255,0.14);
  border-radius: 10px;
  padding: 8px 14px;
  font-size: 12.5px;
  color: #ffffff;
  margin: 0 auto;
  max-width: 360px;
  text-align: center;
}
.nk-land-gps-status.active { display: block; }
/* Popular quick picks */
.nk-land-popular {
  background: #f5f9f6;
  padding: 18px 16px 14px;
  border-bottom: 1px solid var(--nk-border);
}
.nk-land-popular-title {
  font-size: 12px;
  font-weight: 800;
  color: var(--nk-text-soft);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 10px;
}
/* State pick card */
.nk-pick-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(148px, 1fr));
  gap: 8px;
}
.nk-pick-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-radius: 12px;
  background: #ffffff;
  border: 1.5px solid var(--nk-border);
  text-decoration: none;
  color: var(--nk-text-dark);
  transition: all 0.18s ease;
  gap: 4px;
}
.nk-pick-card:hover {
  border-color: var(--nk-mint);
  background: var(--nk-emerald-dark);
  color: #ffffff;
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(0,0,0,0.14);
}
.nk-pick-card.hidden { display: none; }
.nk-pick-name { font-size: 13.5px; font-weight: 800; flex: 1; }
.nk-pick-count { font-size: 11px; font-weight: 600; color: #7b9487; white-space: nowrap; }
.nk-pick-card:hover .nk-pick-count { color: rgba(255,255,255,0.7); }
.nk-pick-arrow { font-size: 16px; font-weight: 700; opacity: 0.5; }
/* Regional sections */
.nk-land-regions { padding: 16px 16px 24px; }
.nk-region-group { margin-bottom: 20px; }
.nk-region-head {
  font-size: 13px;
  font-weight: 800;
  color: var(--nk-text-soft);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin: 0 0 10px;
  padding-bottom: 6px;
  border-bottom: 2px solid var(--nk-border);
}
/* No results message */
.nk-land-noresult {
  display: none;
  text-align: center;
  padding: 24px 16px;
  color: var(--nk-text-soft);
  font-size: 14px;
}
.nk-land-noresult.active { display: block; }
@media (max-width: 480px) {
  .nk-land-hero h1 { font-size: 20px; }
  .nk-pick-grid { grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); }
}
</style>"""

    body = f"""{landing_css}

<!-- Hero Search Section -->
<div class="nk-land-hero">
  <h1>🗺️ भारत का नक्शा</h1>
  <p>अपना राज्य चुनें — जिले, गांव और खेत सैटेलाइट व्यू में देखें</p>

  <div class="nk-land-search-wrap">
    <input type="text" id="nk-land-search" placeholder="राज्य खोजें... जैसे: उत्तर प्रदेश, राजस्थान"
           autocomplete="off" aria-label="राज्य खोजें" />
    <button type="button" class="nk-land-gps-btn" id="nk-land-gps-btn"
            title="GPS से राज्य पता करें">
      <span class="nk-land-gps-ic"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="display:inline-block;vertical-align:-2px"><circle cx="12" cy="12" r="7"/><line x1="12" y1="2" x2="12" y2="5"/><line x1="12" y1="19" x2="12" y2="22"/><line x1="2" y1="12" x2="5" y2="12"/><line x1="19" y1="12" x2="22" y2="12"/><circle cx="12" cy="12" r="2.5" fill="currentColor"/></svg></span>
      <span class="nk-land-gps-txt">मेरा राज्य</span>
    </button>
  </div>
  <div class="nk-land-gps-status" id="nk-land-gps-status">📡 आपकी लोकेशन खोजी जा रही है...</div>
</div>

<!-- Popular States Quick Pick -->
<div class="nk-land-popular" id="nk-land-popular">
  <div class="nk-land-popular-title">⭐ प्रमुख कृषि राज्य</div>
  <div class="nk-pick-grid">{popular_html}</div>
</div>

<!-- All States by Region -->
<div class="nk-land-regions" id="nk-land-all-regions">
  {all_regions_html}
</div>
<div class="nk-land-noresult" id="nk-land-noresult">
  कोई राज्य नहीं मिला — दूसरे शब्द आज़माएं
</div>

<script>
(function() {{
  var searchInput = document.getElementById('nk-land-search');
  var allCards = document.querySelectorAll('.nk-pick-card');
  var popular = document.getElementById('nk-land-popular');
  var allRegions = document.getElementById('nk-land-all-regions');
  var noResult = document.getElementById('nk-land-noresult');
  var regionGroups = document.querySelectorAll('.nk-region-group');

  if(searchInput) {{
    searchInput.addEventListener('input', function() {{
      var q = this.value.trim();
      if(!q) {{
        allCards.forEach(function(c) {{ c.classList.remove('hidden'); }});
        regionGroups.forEach(function(g) {{ g.style.display = ''; }});
        if(popular) popular.style.display = '';
        if(allRegions) allRegions.style.display = '';
        if(noResult) noResult.classList.remove('active');
        return;
      }}
      if(popular) popular.style.display = 'none';
      if(allRegions) allRegions.style.display = 'block';
      var matched = 0;
      allCards.forEach(function(c) {{
        var hi = (c.dataset.hi || '').toLowerCase();
        var st = (c.dataset.state || '').toLowerCase();
        if(hi.indexOf(q) > -1 || st.indexOf(q.toLowerCase()) > -1) {{
          c.classList.remove('hidden');
          matched++;
        }} else {{
          c.classList.add('hidden');
        }}
      }});
      regionGroups.forEach(function(g) {{
        var vis = g.querySelectorAll('.nk-pick-card:not(.hidden)').length > 0;
        g.style.display = vis ? '' : 'none';
      }});
      if(noResult) noResult.classList.toggle('active', matched === 0);
    }});
  }}

  // GPS detect state
  var gpsBtn = document.getElementById('nk-land-gps-btn');
  var gpsStatus = document.getElementById('nk-land-gps-status');
  var gpsTxt = gpsBtn ? gpsBtn.querySelector('.nk-land-gps-txt') : null;
  var gpsIc = gpsBtn ? gpsBtn.querySelector('.nk-land-gps-ic') : null;

  // State-to-URL mapping for GPS redirect
  var stateMap = {{}};
  allCards.forEach(function(c) {{
    stateMap[(c.dataset.hi || '')] = c.href;
    stateMap[(c.dataset.state || '')] = c.href;
  }});

  if(gpsBtn) {{
    gpsBtn.addEventListener('click', function() {{
      if(!navigator.geolocation) {{
        alert('आपके डिवाइस में GPS उपलब्ध नहीं है।');
        return;
      }}
      gpsBtn.classList.add('loading');
      if(gpsTxt) gpsTxt.textContent = 'खोज रहे हैं...';
      if(gpsStatus) gpsStatus.classList.add('active');

      navigator.geolocation.getCurrentPosition(function(pos) {{
        var lat = pos.coords.latitude, lon = pos.coords.longitude;
        fetch('https://api.bigdatacloud.net/data/reverse-geocode-client?latitude=' + lat + '&longitude=' + lon + '&localityLanguage=hi')
          .then(function(r) {{ return r.json(); }})
          .then(function(d) {{
            var state = (d.principalSubdivision || '').toLowerCase()
              .replace(/\s+/g, '-').replace(/[^a-z-]/g, '');
            // Try direct state slug match
            var url = stateMap[state];
            if(url) {{
              if(gpsStatus) gpsStatus.textContent = '📍 ' + (d.principalSubdivision || 'आपका राज्य') + ' मिला — नक्शा खुल रहा है...';
              setTimeout(function() {{ window.location.href = url; }}, 800);
            }} else {{
              if(gpsStatus) gpsStatus.textContent = '📍 ' + (d.principalSubdivision || '') + ' — नीचे से चुनें';
              if(searchInput && d.principalSubdivision) {{
                searchInput.value = d.principalSubdivision;
                searchInput.dispatchEvent(new Event('input'));
              }}
            }}
          }})
          .catch(function() {{
            if(gpsStatus) gpsStatus.textContent = 'लोकेशन मिली पर राज्य पहचान नहीं हुई — नीचे से चुनें।';
          }})
          .finally(function() {{
            gpsBtn.classList.remove('loading');
            if(gpsTxt) gpsTxt.textContent = 'मेरा राज्य';
          }});
      }}, function() {{
        gpsBtn.classList.remove('loading');
        if(gpsTxt) gpsTxt.textContent = 'मेरा राज्य';
        if(gpsStatus) gpsStatus.classList.remove('active');
        alert('लोकेशन नहीं मिल सकी। GPS और ब्राउज़र अनुमति जांचें।');
      }}, {{ enableHighAccuracy: false, timeout: 10000 }});
    }});
  }}
}})();
</script>"""

    return _doc(
        "भारत का नक्शा — राज्य चुनें | कृषि मित्र",
        "भारत के सभी राज्यों के जिलेवार नक्शे — सैटेलाइट व्यू, गांव खोज और खेत नापने का यंत्र। अपना राज्य चुनें।",
        f"{SITE}/map",
        _crumbs([]),
        body,
        active="map",
        extra_css=_NK_CSS,
    )


# ── routes ──────────────────────────────────────────────────────────────────

_MAP_TOOL_CSS = """
.km-map-tool-bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:4px 0 10px}
.km-map-tool-bar h1{font-size:17px;margin:0;flex:1 1 auto;color:var(--nk-emerald-dark)}
.km-map-tool-bar .nk-state-select{max-width:220px}
.km-map-tool-bar a{font-size:13px;font-weight:600;white-space:nowrap}
.km-map-tool .nk-map{height:calc(100dvh - 230px);min-height:420px;max-height:none}
"""


def _map_tool_page(key: str) -> HTMLResponse:
    """/map — the minimal entry to the maps category: the same interactive map
    and features as /naksha/{state}, with nothing around it. Same map code as
    the नक्शा cluster (_map_app_container + _tail_scripts), never a fork.

    noindex: /naksha is the content tree that ranks; this is a tool page whose
    map would otherwise compete with /naksha/{state} for the same queries.
    """
    states = _states()
    s = states[key]
    hi = s["hi"]
    opts = "".join(
        f'<option value="{k}"{" selected" if k == key else ""}>{escape(v["hi"])}</option>'
        for k, v in states.items())
    # The farmer's state is remembered, so /map opens on it next time.
    body = f"""<div class="km-map-tool">
<div class="km-map-tool-bar">
  <h1>🗺️ {escape(hi)} का नक्शा</h1>
  <select class="nk-state-select" id="km-map-state" aria-label="राज्य चुनें">{opts}</select>
  <a href="{_url(key)}">जिले व जानकारी →</a>
</div>
{_map_app_container(key, s, hi)}
</div>
<script>
(function(){{
  var KEY = {json.dumps(key)};
  var sel = document.getElementById('km-map-state');
  var hasParam = /[?&]state=/.test(location.search);
  try {{
    var saved = localStorage.getItem('km_map_state');
    if(!hasParam && saved && saved !== KEY) {{ location.replace('/map?state=' + encodeURIComponent(saved)); return; }}
    localStorage.setItem('km_map_state', KEY);
  }} catch(e) {{}}
  if(sel) sel.addEventListener('change', function(){{
    try {{ localStorage.setItem('km_map_state', sel.value); }} catch(e) {{}}
    location.href = '/map?state=' + encodeURIComponent(sel.value);
  }});
}})();
</script>
{_tail_scripts(s, state_key=key)}"""
    return _doc(f"{hi} का नक्शा — कृषि मानचित्र",
                f"{hi} का इंटरैक्टिव सैटेलाइट नक्शा — जिला व गांव खोजें, मंडी और रास्ता देखें।",
                f"{SITE}/map", "", body, active="map",
                extra_css=_NK_CSS + _MAP_TOOL_CSS, head_extra=_LEAFLET_CSS,
                robots="noindex, follow", journey=False)


@router.get("/map", response_class=HTMLResponse)
def map_tool(state: str = "uttar-pradesh"):
    """The standalone map tool. Not a redirect: /map and /naksha serve
    different use cases — see _map_tool_page."""
    state = "uttar-pradesh" if state == "uttarpradesh" else state.lower()
    if state not in _states():
        state = "uttar-pradesh"
    return _map_tool_page(state)


@router.get("/naksha/{state}", response_class=HTMLResponse)
def state_map(state: str):
    # "uttarpradesh" (no hyphen) is the spelling a farmer is likeliest to type
    # from memory — both resolve to
    # the same page as the hyphenated slug.
    if state in ("uttar-pradesh", "uttarpradesh"):
        return _state_page("uttar-pradesh", f"{SITE}/naksha/uttar-pradesh")
    if state not in _states():
        return _unknown(state)
    return _state_page(state, f"{SITE}/naksha/{state}")


@router.get("/naksha/{state}/jile", response_class=HTMLResponse)
def state_districts(state: str):
    if state == "uttarpradesh":
        return RedirectResponse(f"{SITE}/naksha/uttar-pradesh/jile", status_code=301)
    if state not in _states():
        return _unknown(state)
    return _jile_page(state)


# Declared AFTER /jile: both are three segments, and FastAPI takes the first
# route that matches, so a literal must be registered before the wildcard that
# would also swallow it.
def _resolve(state: str, district: str):
    """Normalise a (state, district) pair to its canonical spelling.

    Returns (state, dslug, response) where a non-None response is what the route
    must return instead of rendering — a 301 to the canonical URL, or the
    not-found page. Every tier-3+ route funnels through this so "uttarpradesh"
    and "MEERUT" resolve identically at all three depths: serving 200 on a
    non-canonical spelling and relying on the canonical tag alone leaves a
    second crawlable URL for every district we have.
    """
    canonical_state = "uttar-pradesh" if state == "uttarpradesh" else state
    if canonical_state not in _states():
        return state, "", _unknown(state)
    dslug = district.lower()
    if dslug not in _dindex(canonical_state):
        return canonical_state, dslug, _unknown_district(canonical_state, district)
    if (canonical_state, dslug) != (state, district):
        return canonical_state, dslug, None      # caller builds its own target
    return canonical_state, dslug, None


def _redirected(canonical: tuple, raw: tuple, target: str):
    """301 iff any path segment came in under a non-canonical spelling."""
    if canonical != raw:
        return RedirectResponse(_abs(target), status_code=301)
    return None


@router.get("/naksha/{state}/{district}", response_class=HTMLResponse)
def district_map(state: str, district: str):
    st, dslug, resp = _resolve(state, district)
    if resp is not None:
        return resp
    return (_redirected((st, dslug), (state, district), _d_url(st, dslug))
            or _district_page(st, dslug))


@router.get("/naksha/{state}/{district}/gaon", response_class=HTMLResponse)
def district_villages(state: str, district: str):
    st, dslug, resp = _resolve(state, district)
    if resp is not None:
        return resp
    return (_redirected((st, dslug), (state, district), _gaon_url(st, dslug))
            or _gaon_page(st, dslug))


@router.get("/naksha/{state}/{district}/gaon/{village}", response_class=HTMLResponse)
def village_map(state: str, district: str, village: str):
    st, dslug, resp = _resolve(state, district)
    if resp is not None:
        return resp
    villages = village_service.load(st, dslug) or []
    vslug = village.lower()
    hit = next((v for v in villages if v["slug"].lower() == vslug), None)
    if not hit:
        # Either the cache has not landed yet or this village was never in it.
        # Send the visitor one level up rather than inventing a place page —
        # 302, not 301, because the same URL becomes real once the fetch runs.
        return RedirectResponse(_abs(_gaon_url(st, dslug)), status_code=302)
    return (_redirected((st, dslug, hit["slug"]), (state, district, village),
                        _v_url(st, dslug, hit["slug"]))
            or _village_page(st, dslug, hit, villages))


def _unknown_district(state: str, district: str) -> HTMLResponse:
    """A district we do not have gets the state's real list, not a dead end."""
    states = _states()
    s = states[state]
    body = f"""<h1 class="nk-title">यह जिला नहीं मिला</h1>
<p class="nk-title-sub">“{escape(district)}” नाम का कोई जिला {escape(s['hi'])} में हमारे पास नहीं है —
नीचे से अपना जिला चुनें।</p>
<section class="nk-sec"><h2>{escape(s['hi'])} के सभी {s['n']} जिले</h2>
<div class="nk-chips">{_sibling_chips(state, s, '')}</div>
<div class="nk-cta" style="margin-top:18px">
  <a class="nk-btn plain" href="{_url(state)}">🗺️ {escape(s['hi'])} का नक्शा</a>
  <a class="nk-btn plain" href="/naksha">🧭 सभी राज्यों के नक्शे</a>
</div></section>"""
    return _doc(f"जिला नहीं मिला — {s['hi']} | कृषि मित्र",
                f"{s['hi']} के सभी {s['n']} जिलों की सूची और नक्शे।",
                _abs(_jile_url(state)),
                _crumbs([("राज्यों के नक्शे", f"{SITE}/naksha")]),
                body, active="map", extra_css=_NK_CSS, robots="noindex, follow")


def _unknown(state: str) -> HTMLResponse:
    """A state we do not have (a typo, an old link, a renamed UT) gets the list
    of the ones we do — not a dead end. noindex so it never competes."""
    states = _states()
    body = f"""<div class="nk-hero">
<h1>यह नक्शा उपलब्ध नहीं है</h1>
<p class="nk-sub">“{escape(state)}” नाम का कोई राज्य हमारे पास नहीं है — नीचे से अपना राज्य चुनें।</p>
</div>
<section class="nk-sec"><h2>सभी राज्यों के नक्शे</h2>
<div class="nk-sgrid">{_state_cards(list(states), states)}</div></section>"""
    return _doc("नक्शा नहीं मिला | कृषि मित्र",
                "यह राज्य उपलब्ध नहीं है — सभी उपलब्ध राज्यों के नक्शे देखें।",
                f"{SITE}/naksha", _crumbs([("राज्यों के नक्शे", f"{SITE}/naksha")]),
                body, active="map", extra_css=_NK_CSS, robots="noindex, follow")
