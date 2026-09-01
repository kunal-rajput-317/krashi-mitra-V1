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
from datetime import datetime
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


def _jile(n: int) -> str:
    """"1 जिला" / "22 जिले" — दिल्ली and चंडीगढ़ are single-district UTs, and
    "1 जिले" on their card is the kind of thing that reads as machine output."""
    return f"{n} जिला" if n == 1 else f"{n} जिले"





# ── page furniture ──────────────────────────────────────────────────────────

_NK_CSS = """
/* ── नक्शा cluster: Modern Mobile-First AgTech Styling ───────── */
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

/* ── My Location Button (bottom-right standalone, icon-only) ── */
.nk-my-loc-btn {
  position: absolute;
  bottom: 80px;
  right: 12px;
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
.nk-my-loc-btn.loading .nk-loc-svg {
  animation: nkSpin 0.9s linear infinite;
}

@media (max-width: 560px) {
  .nk-title { font-size: 20px; padding: 10px 8px 2px; }
  .nk-title-sub { font-size: 12px; }
  .nk-float-search { top: 10px; left: 10px; right: 54px; }
  .nk-fs-btn { top: 10px; right: 10px; width: 35px; height: 35px; border-radius: 8px; }
  .nk-fs-icon { width: 16px; height: 16px; }
  .nk-fab-menu { right: 10px; top: 50px; }
  .nk-fab-main { width: 35px; height: 35px; border-radius: 8px; }
  .nk-my-loc-btn { bottom: 75px; right: 10px; width: 38px; height: 38px; }
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
        f'<small>{_jile(states[k]["n"])}</small></span>'
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
        opts.append(f'<option value="{url}"{sel}>{escape(s["hi"])} ({_jile(s["n"])})</option>')
    return (f'<select class="nk-state-select" onchange="if(this.value) window.location.href=this.value;" aria-label="राज्य चुनें">'
            f'{"".join(opts)}</select>')


def _tail_scripts(s: dict = None, initial: str = "", state_key: str = "") -> str:
    """map-download.js everywhere; Leaflet and interactive controls where there is a map to draw."""
    out = ['<script>window.KM_LOC_AFTER_SCROLL=true;</script>',
           f'<script src="{_asset("map-download.js")}" defer></script>']
    if s:
        initial_js = json.dumps(initial, ensure_ascii=False)
        state_key_js = json.dumps(state_key or "uttar-pradesh")
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

  // ── Tile Layers ──
  var satLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
    attribution: 'Tiles © Esri World Imagery',
    maxZoom: 19
  }});
  var labelLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
    attribution: '© Esri',
    maxZoom: 19
  }});
  var osmLayer = L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
    attribution: '© OpenStreetMap contributors',
    maxZoom: 19
  }});

  // Default: Satellite + Labels
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
        '<div class="nk-lt-icon">📍</div>' +
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
        map.removeLayer(satLayer);
        map.removeLayer(labelLayer);
        osmLayer.addTo(map);
        currentLayerType = 'osm';
        if(fabLayerIc) fabLayerIc.textContent = '🛰️';
        if(fabLayerText) fabLayerText.textContent = 'सैटेलाइट व्यू';
      }} else {{
        map.removeLayer(osmLayer);
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

      map.setView([lat, lon], 16, {{ animate: true }});

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

  var defaultStyle = {{ color: '#2d6a4f', weight: 1.4, fillColor: '#52b788', fillOpacity: 0.28 }};
  var highlightStyle = {{ color: '#f5b731', weight: 3.5, fillColor: '#e9a825', fillOpacity: 0.70 }};
  var dimmedStyle = {{ color: '#2d6a4f', weight: 1, fillColor: '#52b788', fillOpacity: 0.10 }};

  function selectDistrict(name, autoScroll) {{
    if(!name) {{ resetView(); return; }}
    var foundKey = Object.keys(districtMap).find(function(k){{ return k.toLowerCase() === name.toLowerCase(); }});
    if(!foundKey) return;

    var item = districtMap[foundKey];
    var layer = item.layer, hiName = item.hiName, enName = item.enName, dslug = item.dslug;

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
            satLayer.addTo(map);
            labelLayer.addTo(map);
            currentLayerType = 'sat';
            if(fabLayer) fabLayer.innerHTML = '🗺️<span class="nk-fab-label">नक्शा व्यू</span>';
          }}

          map.setView([lat, lon], 14, {{ animate: true }});
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
            l.setStyle({{ fillColor: '#e9a825', fillOpacity: 0.55 }});
          }});
          l.on('mouseout', function(){{
            l.setStyle(defaultStyle);
          }});
        }}
      }}).addTo(map);
      if(!isOverlayVisible) map.removeLayer(geojsonLayer);

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
            f'<span class="nk-pick-count">{_jile(s["n"])}</span>'
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
      <span class="nk-land-gps-ic">📍</span>
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
        <span class="nk-loc-icon">📍</span>
        <span class="nk-loc-text">लोकेशन</span>
      </button>
      <button type="button" id="nk-search-btn" class="nk-search-btn">खोजें</button>
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
    <svg class="nk-loc-svg" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="12" cy="12" r="3.5" fill="currentColor"/>
      <circle cx="12" cy="12" r="7" stroke="currentColor" stroke-width="2" fill="none" stroke-dasharray="3 2"/>
      <line x1="12" y1="2" x2="12" y2="5.5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
      <line x1="12" y1="18.5" x2="12" y2="22" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
      <line x1="2" y1="12" x2="5.5" y2="12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
      <line x1="18.5" y1="12" x2="22" y2="12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
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
</div>
"""


# ── one state's map ─────────────────────────────────────────────────────────

def _state_page(key: str, canon: str) -> HTMLResponse:
    states = _states()
    s = states[key]
    hi, n = s["hi"], s["n"]
    span = f"{s['north']} से {s['south']} तक"

    title = _fit(
        f"{hi} का नक्शा – {n} जिलों का HD मानचित्र | मुफ्त डाउनलोड",
        f"{hi} का नक्शा – {n} जिलों का HD मानचित्र (मुफ्त)",
        f"{hi} का नक्शा – {n} जिलों का HD मानचित्र")
    desc = _fit(
        f"{hi} का नक्शा हिंदी में — {span}, सभी {n} जिले एक ही मानचित्र में। "
        f"HD नक्शा मुफ्त डाउनलोड करें और ज़ूम करके अपना जिला देखें।",
        f"{hi} का नक्शा हिंदी में — सभी {n} जिले एक ही मानचित्र में। "
        f"HD नक्शा मुफ्त डाउनलोड करें और ज़ूम करके अपना जिला देखें।",
        limit=162)
    alt = f"{hi} का नक्शा — {hi} के {n} जिलों का हिंदी जिलेवार मानचित्र ({span})"

    chips = _sibling_chips(key, s, "")

    faq_html, faq_ld = _faq([
        (f"{hi} में कितने जिले हैं?",
         f"Census of India की जिला-सीमाओं के अनुसार {hi} में {n} जिले हैं — {span}।"),
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

    body = f"""<div class="nk-level-bar">
  <a href="/naksha">🇮🇳 भारत (India)</a>
  <span class="nk-lvl-sep">➔</span>
  <a href="{_url(key)}">🏛️ {escape(hi)}</a>
  <span class="nk-lvl-sep">➔</span>
  <span style="color:var(--nk-emerald-dark)">📍 जिला / 🏢 तहसील / 🌾 गांव सैटेलाइट</span>
</div>

<h1 class="nk-title">{escape(hi)} का नक्शा</h1>
<p class="nk-title-sub">{_jile(n)} · {escape(span)} · हिंदी में जिलेवार मानचित्र व सैटेलाइट व्यू</p>

<div class="nk-tabs-bar">
  <a class="nk-tab-item active" href="{_url(key)}#nk-map-wrap">🗺️ इंटरैक्टिव नक्शा</a>
  <a class="nk-tab-item" href="{_jile_url(key)}">📋 जिलों की सूची ({n})</a>
</div>

{map_container}

<!-- 4 Farmer Quick Action Cards -->
<div class="nk-farmer-grid">
  <a class="nk-farmer-card bhulekh" href="{bhulekh_url}" target="_blank" rel="noopener">
    <div class="nk-farmer-card-ic">📄</div>
    <div class="nk-farmer-card-body">
      <div class="nk-farmer-card-title">{escape(bhulekh_label)}</div>
      <div class="nk-farmer-card-sub">खसरा-खतौनी व भू-अभिलेख नकल निकालें ↗</div>
    </div>
    <div class="nk-farmer-card-arrow">➔</div>
  </a>

  <a class="nk-farmer-card weather" href="/weather">
    <div class="nk-farmer-card-ic">🌤️</div>
    <div class="nk-farmer-card-body">
      <div class="nk-farmer-card-title">{escape(hi)} मौसम व बारिश</div>
      <div class="nk-farmer-card-sub">7 दिनों का लाइव मौसम पूर्वानुमान</div>
    </div>
    <div class="nk-farmer-card-arrow">➔</div>
  </a>

  <a class="nk-farmer-card bhav" href="/bhav">
    <div class="nk-farmer-card-ic">💰</div>
    <div class="nk-farmer-card-body">
      <div class="nk-farmer-card-title">आज का मंडी भाव</div>
      <div class="nk-farmer-card-sub">प्रमुख फसलों के दैनिक ताजा मंडी रेट</div>
    </div>
    <div class="nk-farmer-card-arrow">➔</div>
  </a>

  <a class="nk-farmer-card gaon" href="{_jile_url(key)}">
    <div class="nk-farmer-card-ic">🌾</div>
    <div class="nk-farmer-card-body">
      <div class="nk-farmer-card-title">{escape(hi)} के सभी {n} जिले</div>
      <div class="nk-farmer-card-sub">जिलों की सूची व गांव डायरेक्टरी</div>
    </div>
    <div class="nk-farmer-card-arrow">➔</div>
  </a>
</div>

<!-- Compact HD Map Download Banner -->
<div class="nk-dl-banner">
  <img src="{_img(s, 'district-map.webp')}" class="nk-dl-banner-thumb" width="64" height="64" loading="lazy" alt="{escape(alt)}">
  <div class="nk-dl-banner-info">
    <h3>⬇️ {escape(hi)} का HD प्रिंट नक्शा डाउनलोड करें</h3>
    <p>सभी {n} जिले हिंदी में · हाई-क्वालिटी PNG प्रिंट नक्शा ({s['w']}×{s['h']} px) · बिल्कुल मुफ्त</p>
  </div>
  <a class="nk-dl-banner-btn" data-km-map-picker href="{_img(s, 'district-map.png')}" download="{s['prefix']}-{s['n']}-jile.png">
    ⬇️ मुफ्त डाउनलोड
  </a>
</div>

<!-- 4 Fact Metric Boxes -->
<div class="nk-facts-bar">
  <div class="nk-fact-box">
    <small>कुल जिले</small>
    <b>{n} जिले</b>
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

    title = _fit(
        f"{hi} के जिले – सभी {n} जिलों की सूची (हिंदी + English)",
        f"{hi} के जिले – सभी {n} जिलों की सूची")
    desc = _fit(
        f"{hi} में कुल {n} जिले हैं — पूरी सूची हिंदी और अंग्रेज़ी दोनों नामों के "
        f"साथ, {span}। साथ में {hi} का HD नक्शा — मुफ्त डाउनलोड।",
        f"{hi} में कुल {n} जिले हैं — पूरी सूची हिंदी और अंग्रेज़ी दोनों नामों के साथ। "
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

    faq_html, faq_ld = _faq([
        (f"{hi} में कितने जिले हैं?",
         f"Census of India की जिला-सीमाओं के अनुसार {hi} में {n} जिले हैं। ऊपर दी गई "
         f"सूची में सभी {n} नाम हिंदी और अंग्रेज़ी दोनों में हैं।"),
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
  <span style="color:var(--nk-emerald-dark)">📋 जिलों की सूची ({n})</span>
</div>

<h1 class="nk-title">{escape(hi)} के जिले</h1>
<p class="nk-title-sub">सभी {_jile(n)} — हिंदी और अंग्रेज़ी नामों के साथ · {escape(span)}</p>

<div class="nk-tabs-bar">
  <a class="nk-tab-item" href="{_url(key)}#nk-map-wrap">🗺️ इंटरैक्टिव नक्शा</a>
  <a class="nk-tab-item active" href="{_jile_url(key)}">📋 जिलों की सूची ({n})</a>
</div>

<div class="nk-stats-row">
  <div class="nk-stat-card">
    <div class="nk-st-lbl">📊 कुल जिले</div>
    <div class="nk-st-val">{n} जिले</div>
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
  <h2>{escape(hi)} के सभी {n} जिलों की निर्देशिका</h2>
  <p class="nk-lede">हिंदी या अंग्रेज़ी में जिला खोजें — नक्शा देखने के लिए जिले के नाम पर क्लिक करें:</p>
  <input class="nk-search" id="nk-dsearch" type="search" autocomplete="off"
   placeholder="जिला खोजें — जैसे मेरठ, Meerut…" aria-label="जिला खोजें" style="margin-bottom:16px;">
  <p class="nk-empty" id="nk-dnone" style="display:none">कोई जिला नहीं मिला।</p>
  <div class="nk-dgrid">{rows}</div>
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
        "@id": f"{canon}#districts", "name": f"{hi} के {n} जिले",
        "numberOfItems": n,
        "itemListOrder": "https://schema.org/ItemListOrderAscending",
        "itemListElement": [
            {"@type": "ListItem", "position": i,
             "item": {"@type": "AdministrativeArea", "name": d["hi"],
                      "alternateName": d["en"]}}
            for i, d in enumerate(s["districts"], start=1)],
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


def _district_page(key: str, dslug: str) -> HTMLResponse:
    states = _states()
    s = states[key]
    d = _dindex(key)[dslug]
    hi, en, shi = d["hi"], d["en"], s["hi"]
    canon = _abs(_d_url(key, dslug))
    n = s["n"]

    village_service.request(key, dslug, {"geojson": s["geojson"], "en": en, "hi": hi})
    villages = village_service.load(key, dslug) or []

    title = f"{hi} का नक्शा – {shi} | जिला मानचित्र, गांव व सैटेलाइट व्यू"
    desc = (f"{hi} जिले का नक्शा ({en} district map) — {shi} के {n} जिलों में से एक। "
            f"सैटेलाइट व्यू में अपना गांव और तहसील देखें, जिले की सीमा नक्शे पर "
            f"हाइलाइट, और {shi} का पूरा HD नक्शा मुफ्त डाउनलोड करें।")

    v_line = (f"इस जिले के {len(villages)} गांव व कस्बे सूची में दर्ज हैं।"
              if villages else
              "गांव व तहसील नाम से खोजें — नक्शा सीधे वहीं ज़ूम हो जाएगा।")
    v_cta = (f'<a class="nk-btn primary" href="{_gaon_url(key, dslug)}">'
             f'{hi} के गांवों की सूची देखें →</a>' if villages else
             f'<a class="nk-btn plain" href="{_gaon_url(key, dslug)}">'
             f'गांव खोजें →</a>')

    faq_html, faq_ld = _faq([
        (f"{hi} जिला किस राज्य में है?",
         f"{hi} ({en}) {shi} का एक जिला है। {shi} में कुल {n} जिले हैं, और इस पेज पर "
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

    body = f"""<div class="nk-level-bar">
  <a href="/naksha">🇮🇳 भारत (India)</a>
  <span class="nk-lvl-sep">➔</span>
  <a href="{_url(key)}">🏛️ {escape(shi)}</a>
  <span class="nk-lvl-sep">➔</span>
  <a href="{_jile_url(key)}">📋 जिले ({n})</a>
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

<!-- 4 District Farmer Quick Action Cards -->
<div class="nk-farmer-grid">
  <a class="nk-farmer-card bhulekh" href="{bhulekh_url}" target="_blank" rel="noopener">
    <div class="nk-farmer-card-ic">📄</div>
    <div class="nk-farmer-card-body">
      <div class="nk-farmer-card-title">{escape(hi)} भूलेख (खसरा-खतौनी)</div>
      <div class="nk-farmer-card-sub">आधिकारिक भू-अभिलेख व जमीन नकल ↗</div>
    </div>
    <div class="nk-farmer-card-arrow">➔</div>
  </a>

  <a class="nk-farmer-card weather" href="/weather">
    <div class="nk-farmer-card-ic">🌤️</div>
    <div class="nk-farmer-card-body">
      <div class="nk-farmer-card-title">{escape(hi)} मौसम पूर्वानुमान</div>
      <div class="nk-farmer-card-sub">आज का तापमान, हवा व बारिश अलर्ट</div>
    </div>
    <div class="nk-farmer-card-arrow">➔</div>
  </a>

  <a class="nk-farmer-card bhav" href="/bhav">
    <div class="nk-farmer-card-ic">💰</div>
    <div class="nk-farmer-card-body">
      <div class="nk-farmer-card-title">{escape(hi)} मंडी भाव</div>
      <div class="nk-farmer-card-sub">निकटतम मंडियों में आज के फसल दाम</div>
    </div>
    <div class="nk-farmer-card-arrow">➔</div>
  </a>

  <a class="nk-farmer-card gaon" href="{_gaon_url(key, dslug)}">
    <div class="nk-farmer-card-ic">🌾</div>
    <div class="nk-farmer-card-body">
      <div class="nk-farmer-card-title">{escape(hi)} के गांव व कस्बे</div>
      <div class="nk-farmer-card-sub">सैटेलाइट नक्शा व {len(villages) if villages else 'सभी'} गांव खोजें</div>
    </div>
    <div class="nk-farmer-card-arrow">➔</div>
  </a>
</div>

<!-- Compact HD Map Download Banner -->
<div class="nk-dl-banner">
  <img src="{_img(s, 'district-map.webp')}" class="nk-dl-banner-thumb" width="64" height="64" loading="lazy" alt="{escape(f'{shi} का नक्शा — {hi} समेत सभी {n} जिलों का हिंदी जिलेवार मानचित्र')}">
  <div class="nk-dl-banner-info">
    <h3>⬇️ {escape(shi)} का HD प्रिंट नक्शा</h3>
    <p>{escape(hi)} समेत सभी {n} जिले हिंदी में · मुफ्त HD PNG डाउनलोड</p>
  </div>
  <a class="nk-dl-banner-btn" data-km-map-picker href="{_img(s, 'district-map.png')}" download="{s['prefix']}-{s['n']}-jile.png">
    ⬇️ मुफ्त डाउनलोड
  </a>
</div>

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
{_tail_scripts(s, initial=hi, state_key=key)}"""


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
    var sat=L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}',
      {{attribution:'Tiles © Esri World Imagery',maxZoom:19}}).addTo(map);
    var labels=L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{{z}}/{{y}}/{{x}}',
      {{attribution:'© Esri',maxZoom:19}}).addTo(map);
    var osm=L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',
      {{attribution:'© OpenStreetMap contributors',maxZoom:19}});
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
            f'<span class="nk-pick-count">{_jile(s["n"])}</span>'
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
      <span class="nk-land-gps-ic">📍</span>
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

@router.get("/map", response_class=HTMLResponse)
def up_map():
    """Legacy redirect from /map to /naksha/uttar-pradesh."""
    return RedirectResponse(f"{SITE}/naksha/uttar-pradesh", status_code=301)


@router.get("/naksha/{state}", response_class=HTMLResponse)
def state_map(state: str):
    # "uttarpradesh" (no hyphen) is the spelling the /map popup below links to,
    # and the one a farmer is likeliest to type from memory — both resolve to
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
