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
    """A state's map page. UP keeps /map — see the module header."""
    return "/map" if key == "uttar-pradesh" else f"/naksha/{key}"


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


def _up_url_popup() -> str:
    """A one-time modal, /map only: points at /naksha/uttarpradesh — the slug
    every other state already answers to (/naksha/bihar, /naksha/punjab…), which
    /map itself never got since it kept its original pre-cluster URL.

    Self-contained (own <style>/<script>) so it can be dropped into one page's
    body without touching _NK_CSS. Remembered in localStorage exactly like the
    device-location card (frontend/location.js's km_geo) — shown once, never
    re-nagged once dismissed or followed.
    """
    return """
<div class="nk-upmove-ov" id="nk-upmove-ov" role="dialog" aria-modal="true" aria-label="नया पता उपलब्ध">
  <div class="nk-upmove-card">
    <button type="button" class="nk-upmove-x" id="nk-upmove-x" aria-label="बंद करें">✕</button>
    <div class="nk-upmove-ic">🔗</div>
    <h3>उत्तर प्रदेश के नक्शे का नया पता</h3>
    <p>यह पेज अब <b>/naksha/uttarpradesh</b> से भी खुलता है — बाकी सभी राज्यों जैसा एक जैसा
       पता। पुराना पता <b>/map</b> पहले की तरह काम करता रहेगा, कहीं टूटेगा नहीं।</p>
    <div class="nk-upmove-row">
      <a class="nk-btn primary" href="/naksha/uttarpradesh">नए पते पर जाएं →</a>
      <button type="button" class="nk-btn plain" id="nk-upmove-ok">ठीक है, समझ गया</button>
    </div>
  </div>
</div>
<style>
.nk-upmove-ov{position:fixed;inset:0;z-index:99000;display:none;align-items:center;
  justify-content:center;background:rgba(7,31,22,.55);backdrop-filter:blur(2px);padding:18px}
.nk-upmove-ov.open{display:flex}
.nk-upmove-card{position:relative;background:#fff;border-radius:18px;max-width:400px;width:100%;
  padding:28px 22px 22px;box-shadow:0 20px 60px rgba(0,0,0,.35);text-align:center;
  font-family:var(--nk-font);animation:nk-upmove-in .25s cubic-bezier(.16,1,.3,1)}
@keyframes nk-upmove-in{from{opacity:0;transform:translateY(14px) scale(.97)}to{opacity:1;transform:none}}
.nk-upmove-x{position:absolute;top:10px;right:10px;width:30px;height:30px;border:none;
  border-radius:50%;background:#f2f5f3;color:#5b675f;font-size:13px;cursor:pointer}
.nk-upmove-x:hover{background:#e6ebe8}
.nk-upmove-ic{font-size:34px;margin-bottom:8px;line-height:1}
.nk-upmove-card h3{font-size:16.5px;font-weight:800;color:var(--nk-emerald-dark);margin-bottom:8px}
.nk-upmove-card p{font-size:13px;color:var(--nk-text-mid);line-height:1.65;margin-bottom:18px}
.nk-upmove-card p b{color:var(--nk-emerald-dark);font-family:ui-monospace,monospace;font-weight:700}
.nk-upmove-row{display:flex;flex-direction:column;gap:9px}
.nk-upmove-row .nk-btn{width:100%;justify-content:center}
@media (prefers-reduced-motion: reduce){.nk-upmove-card{animation:none}}
</style>
<script>
(function(){
  var KEY='km_up_url_notice';
  try{if(localStorage.getItem(KEY))return;}catch(e){}
  var ov=document.getElementById('nk-upmove-ov');
  if(!ov)return;
  function dismiss(){
    ov.classList.remove('open');
    try{localStorage.setItem(KEY,'1');}catch(e){}
  }
  setTimeout(function(){ov.classList.add('open');},900);
  var x=document.getElementById('nk-upmove-x'); if(x)x.addEventListener('click',dismiss);
  var ok=document.getElementById('nk-upmove-ok'); if(ok)ok.addEventListener('click',dismiss);
  ov.addEventListener('click',function(e){if(e.target===ov)dismiss();});
  document.addEventListener('keydown',function(e){
    if(e.key==='Escape'&&ov.classList.contains('open'))dismiss();
  });
})();
</script>
"""


# ── page furniture ──────────────────────────────────────────────────────────

_NK_CSS = """
/* ── नक्शा cluster ──────────────────────────────────────────────
   No @import here: this block is appended to bhav.py's _CSS inside one <style>,
   and an @import that is not the first rule in a stylesheet is dropped by every
   browser — the font it named never loaded, so the pages fell back silently.
   They use the shell's own faces (loaded by _FONTS in the <head>), which is
   also what keeps a page reached from Google looking like the rest of the app. */

:root {
  --nk-font: 'DM Sans', 'Noto Sans Devanagari', -apple-system, sans-serif;
  --nk-bg-gradient: linear-gradient(135deg, #061a12 0%, #0d2f23 45%, #154534 100%);
  --nk-card-bg: rgba(255, 255, 255, 0.94);
  --nk-border-glass: rgba(45, 106, 79, 0.16);
  --nk-emerald-dark: #071f16;
  --nk-emerald-mid: #134232;
  --nk-emerald-light: #23654f;
  --nk-mint: #52b788;
  --nk-mint-glow: rgba(82, 183, 136, 0.35);
  --nk-gold: #f5b731;
  --nk-gold-light: #fff8e7;
  --nk-gold-glow: rgba(245, 183, 49, 0.38);
  --nk-text-dark: #0d1e17;
  --nk-text-mid: #2c4a3e;
  --nk-text-soft: #5b786a;
  --nk-shadow-lg: 0 20px 40px -12px rgba(7, 31, 22, 0.16);
  --nk-shadow-md: 0 10px 24px -6px rgba(7, 31, 22, 0.10);
  --nk-radius-lg: 20px;
  --nk-radius-md: 14px;
}

/* Scoped to this cluster's own blocks, not body: an !important font on <body>
   also repaints the shared header, drawer and footer, so these pages stopped
   matching every other page on the site. */
.nk-hero, .nk-sec, .nk-card, .nk-tabs-bar, .nk-scard, .nk-drow {
  font-family: var(--nk-font);
}

/* Page heading — the same plain blue title mandi.html uses, not a hero banner.
   A full-bleed dark block at the top of every one of 73 pages was louder than
   anything under it, and pushed the map itself below the fold on a phone. */
.nk-title {
  text-align: center;
  font-family: var(--nk-font);
  font-size: 22px;
  font-weight: 800;
  color: #1a56db;
  padding: 20px 16px 2px;
  line-height: 1.3;
}
.nk-title-sub {
  text-align: center;
  font-size: 13.5px;
  color: var(--nk-text-soft);
  font-weight: 600;
  margin: 0 auto 16px;
  max-width: 60ch;
}
/* The download and the state switcher sit directly under the title, one row,
   centred; they stack full-width once there is no room for two. */
.nk-controls {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  align-items: stretch;
  gap: 10px;
  margin-bottom: 18px;
}
.nk-controls .nk-btn { min-height: 46px; }
.nk-controls .nk-state-select { min-height: 46px; min-width: 240px; }
@media (max-width: 560px) {
  .nk-title { font-size: 19px; padding: 16px 12px 2px; }
  .nk-title-sub { font-size: 12.5px; }
  .nk-controls { flex-direction: column; }
  .nk-controls .nk-btn, .nk-controls .nk-state-select { width: 100%; }
}

/* Hero Section */
.nk-hero {
  background: var(--nk-bg-gradient);
  border-radius: var(--nk-radius-lg);
  padding: 34px 30px;
  margin: 16px 0 24px;
  color: #ffffff;
  box-shadow: var(--nk-shadow-lg);
  position: relative;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.12);
}
.nk-hero::before {
  content: '';
  position: absolute;
  top: -50%;
  right: -20%;
  width: 420px;
  height: 420px;
  background: radial-gradient(circle, rgba(82, 183, 136, 0.22) 0%, rgba(245, 183, 49, 0.12) 50%, rgba(0,0,0,0) 70%);
  border-radius: 50%;
  pointer-events: none;
  filter: blur(20px);
}
.nk-hero-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 16px;
  background: rgba(255, 255, 255, 0.12);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.22);
  border-radius: 999px;
  font-size: 12.5px;
  font-weight: 800;
  color: var(--nk-gold);
  letter-spacing: 0.5px;
  margin-bottom: 14px;
  text-transform: uppercase;
}
.nk-hero h1 {
  font-family: var(--nk-font);
  font-size: 34px;
  font-weight: 800;
  line-height: 1.2;
  color: #ffffff;
  letter-spacing: -0.5px;
  margin-bottom: 10px;
  text-shadow: 0 2px 10px rgba(0,0,0,0.3);
}
.nk-hero .nk-sub {
  font-size: 15.5px;
  color: rgba(255, 255, 255, 0.90);
  line-height: 1.6;
  max-width: 720px;
  font-weight: 500;
}
.nk-cta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 24px;
}
.nk-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 14px 24px;
  border-radius: var(--nk-radius-md);
  font-size: 15px;
  font-weight: 700;
  text-decoration: none;
  white-space: nowrap;
  min-height: 50px;
  transition: all 0.25s cubic-bezier(0.34, 1.56, 0.64, 1);
  border: 1.5px solid transparent;
  cursor: pointer;
  box-sizing: border-box;
}
.nk-btn.primary {
  background: linear-gradient(135deg, #f5b731 0%, #e9a825 100%);
  color: #071f16;
  box-shadow: 0 6px 20px var(--nk-gold-glow);
  border-color: #ffd269;
}
.nk-btn.primary:hover {
  transform: translateY(-3px) scale(1.02);
  box-shadow: 0 10px 28px rgba(245, 183, 49, 0.55);
}
.nk-btn.plain {
  background: #ffffff;
  color: var(--nk-emerald-mid);
  border-color: var(--nk-border-glass);
  box-shadow: var(--nk-shadow-md);
}
.nk-btn.plain:hover { border-color: var(--nk-mint); color: var(--nk-emerald-dark); }
.nk-btn.ghost {
  background: rgba(255, 255, 255, 0.12);
  color: #ffffff;
  border-color: rgba(255, 255, 255, 0.30);
  backdrop-filter: blur(8px);
}
.nk-btn.ghost:hover {
  background: rgba(255, 255, 255, 0.24);
  transform: translateY(-2px);
  border-color: rgba(255, 255, 255, 0.50);
}

/* Styled for a plain page background, not the old dark hero this was written
   for — a translucent-white pill on white ground rendered as an invisible
   control next to the download button. */
.nk-state-select {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 14px 20px;
  border-radius: var(--nk-radius-md);
  font-size: 15px;
  font-weight: 700;
  color: var(--nk-emerald-dark);
  background: #ffffff;
  border: 1.5px solid var(--nk-border-glass);
  box-shadow: var(--nk-shadow-md);
  cursor: pointer;
  min-height: 50px;
  outline: none;
  font-family: var(--nk-font);
  transition: all 0.2s ease;
  box-sizing: border-box;
}
.nk-state-select option {
  background: #ffffff;
  color: var(--nk-emerald-dark);
  font-size: 14.5px;
  font-weight: 600;
  padding: 10px;
}
.nk-state-select:hover, .nk-state-select:focus {
  border-color: var(--nk-mint);
  box-shadow: 0 4px 14px rgba(82, 183, 136, 0.22);
}

/* Hierarchical 4-Level Drilldown Bar */
.nk-level-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 18px;
  background: rgba(19, 66, 50, 0.06);
  border: 1px solid var(--nk-border-glass);
  border-radius: var(--nk-radius-md);
  margin: 12px 0 16px;
  font-size: 13.5px;
  font-weight: 700;
  overflow-x: auto;
  white-space: nowrap;
  box-shadow: inset 0 1px 3px rgba(0,0,0,0.02);
}
.nk-level-bar a {
  color: var(--nk-emerald-dark);
  text-decoration: none;
  transition: all 0.2s ease;
  padding: 2px 6px;
  border-radius: 6px;
}
.nk-level-bar a:hover {
  color: var(--nk-emerald-mid);
  background: rgba(82, 183, 136, 0.15);
}
.nk-lvl-sep {
  color: var(--nk-text-soft);
  opacity: 0.6;
  font-size: 12px;
}

/* Village & Tehsil Search — a second row that only exists once the 🔍 icon in
   the toolbar is tapped. Always-open ate a full row of every state page for a
   feature most visits never use; collapsed, the toolbar is one line. */
.nk-geo-search-box {
  display: none;
  align-items: center;
  gap: 8px;
  padding: 0 16px 12px;
  background: linear-gradient(180deg, #f4faf6 0%, #eaf4ed 100%);
  border-bottom: 1px solid var(--nk-border-glass);
}
.nk-geo-search-box.open { display: flex; }
.nk-village-input {
  flex: 1;
  min-width: 0;
  padding: 8px 12px;
  border-radius: 9px;
  border: 1.5px solid var(--nk-emerald-light);
  font-size: 13px;
  font-weight: 600;
  outline: none;
  font-family: inherit;
  background: #ffffff;
  transition: all 0.2s ease;
}
.nk-village-input:focus {
  border-color: var(--nk-gold);
  box-shadow: 0 0 0 3px rgba(245, 183, 49, 0.25);
}
.nk-village-btn {
  padding: 8px 14px;
  background: var(--nk-emerald-mid);
  color: #ffffff;
  border: none;
  border-radius: 9px;
  font-size: 12.5px;
  font-weight: 800;
  cursor: pointer;
  white-space: nowrap;
  flex-shrink: 0;
  transition: all 0.2s ease;
  box-shadow: 0 2px 6px rgba(0,0,0,0.1);
}
.nk-village-btn:hover {
  background: var(--nk-emerald-dark);
  transform: translateY(-1px);
}

/* Leaflet Layer Control Close Button */
.leaflet-control-layers {
  position: relative !important;
  border-radius: 12px !important;
  box-shadow: 0 4px 16px rgba(0,0,0,0.15) !important;
  border: 1px solid var(--nk-border-glass) !important;
}
.nk-layers-close {
  display: none;
  position: absolute;
  top: 6px;
  right: 6px;
  width: 22px;
  height: 22px;
  background: rgba(0, 0, 0, 0.12);
  color: #333333;
  border-radius: 50%;
  font-size: 12px;
  font-weight: 800;
  line-height: 22px;
  text-align: center;
  cursor: pointer;
  z-index: 9999;
  transition: all 0.2s ease;
}
.nk-layers-close:hover {
  background: var(--nk-emerald-dark);
  color: #ffffff;
}
.leaflet-control-layers-expanded .nk-layers-close {
  display: flex !important;
  align-items: center;
  justify-content: center;
}
.leaflet-control-layers-expanded {
  padding: 10px 28px 10px 12px !important;
}

/* Segmented Tabs Bar */
.nk-tabs-bar {
  display: flex;
  gap: 8px;
  background: rgba(19, 66, 50, 0.08);
  padding: 6px;
  border-radius: var(--nk-radius-md);
  margin-bottom: 20px;
  border: 1px solid var(--nk-border-glass);
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}
.nk-tab-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 10px 18px;
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
  box-shadow: 0 4px 12px rgba(7, 31, 22, 0.08);
}

/* Split Main Container */
.nk-split {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(0, 1fr);
  gap: 20px;
  align-items: start;
  /* Target of the "इंटरैक्टिव नक्शा" tab (both the in-page jump and the
     cross-page one from the जिले list). scroll-margin-top keeps the जिले tab
     from landing under the fixed header — see _header's #header-wrapper —
     without needing JS to measure it. smooth on html is scoped to this page's
     own <style>, so it doesn't touch the rest of the site. */
  scroll-margin-top: 96px;
}
html { scroll-behavior: smooth; }
@media (prefers-reduced-motion: reduce) { html { scroll-behavior: auto; } }
.nk-card {
  background: var(--nk-card-bg);
  border: 1px solid var(--nk-border-glass);
  border-radius: var(--nk-radius-lg);
  box-shadow: var(--nk-shadow-md);
  overflow: hidden;
  backdrop-filter: blur(16px);
}

/* Map toolbar — one compact row: a jila picker that takes the remaining space,
   a 🔍 icon that reveals the village/tehsil search row below it, and a ✕ that
   only appears once a district is selected. The old version spelled out
   "अपना जिला चुनें:" as a label plus a permanently-open search row — three
   stacked rows above the map on a phone, which is what pushed the actual map
   below the fold. */
.nk-map-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: linear-gradient(180deg, #f4faf6 0%, #eaf4ed 100%);
  border-bottom: 1px solid var(--nk-border-glass);
}
.nk-mt-select {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  background: #ffffff;
  border: 1.5px solid var(--nk-emerald-light);
  border-radius: 10px;
  padding: 0 4px 0 10px;
  box-shadow: inset 0 2px 4px rgba(0,0,0,0.02);
}
.nk-mt-select .nk-mt-ic { font-size: 13px; flex-shrink: 0; opacity: 0.8; }
.nk-map-select {
  flex: 1;
  min-width: 0;
  padding: 9px 4px;
  border: none;
  background: transparent;
  color: var(--nk-text-dark);
  font-size: 13.5px;
  font-weight: 700;
  outline: none;
  cursor: pointer;
}
.nk-mt-select:focus-within {
  border-color: var(--nk-gold);
  box-shadow: 0 0 0 3px rgba(245, 183, 49, 0.22);
}
.nk-mt-icon-btn {
  flex-shrink: 0;
  width: 38px;
  height: 38px;
  border-radius: 10px;
  background: #ffffff;
  border: 1.5px solid var(--nk-border-glass);
  color: var(--nk-emerald-dark);
  font-size: 15px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  transition: all 0.2s ease;
}
.nk-mt-icon-btn:hover { border-color: var(--nk-mint); background: #f4faf6; }
.nk-mt-icon-btn.active {
  background: var(--nk-emerald-dark);
  border-color: var(--nk-emerald-dark);
  color: #ffffff;
}
.nk-reset-btn { display: none; }
.nk-reset-btn:hover { background: var(--nk-emerald-dark); color: #ffffff; }

.nk-map {
  width: 100%;
  height: min(62vh, 520px);
  background: #e6f3eb;
}
.nk-cap {
  padding: 12px 18px;
  border-top: 1px solid var(--nk-border-glass);
  background: #f8fdfa;
  font-size: 13px;
  color: var(--nk-text-soft);
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}

/* District Active Glass Panel */
.nk-district-panel {
  display: none;
  padding: 18px 20px;
  background: linear-gradient(135deg, #fffcf5 0%, #fef5e4 100%);
  border-top: 2px solid var(--nk-gold);
  box-shadow: 0 -4px 16px rgba(245, 183, 49, 0.12);
  animation: nkSlideUp 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.nk-district-panel.active {
  display: block;
}
@keyframes nkSlideUp {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}
.nk-dp-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}
.nk-dp-title {
  font-size: 18px;
  font-weight: 800;
  color: var(--nk-emerald-dark);
  margin: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}
.nk-dp-badge {
  background: #fde8bc;
  color: #9c6300;
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 8px;
  font-weight: 800;
  border: 1px solid #f7d282;
  letter-spacing: 0.3px;
}
.nk-dp-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(135px, 1fr));
  gap: 10px;
}
.nk-dp-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 11px 16px;
  border-radius: 11px;
  font-size: 13.5px;
  font-weight: 800;
  text-decoration: none;
  transition: all 0.2s ease;
  box-shadow: 0 4px 10px rgba(0,0,0,0.06);
}
.nk-dp-btn:hover { transform: translateY(-2px); box-shadow: 0 6px 14px rgba(0,0,0,0.12); }
.nk-dp-btn.bhav { background: var(--nk-emerald-mid); color: #ffffff; }
.nk-dp-btn.weather { background: var(--nk-mint); color: var(--nk-emerald-dark); }
.nk-dp-btn.fasal { background: var(--nk-gold); color: var(--nk-emerald-dark); }

/* Sidebar Stats & HD Download Card */
.nk-dl { padding: 20px; }
.nk-dl h2, .nk-facts h2 { font-size: 16.5px; font-weight: 800; color: var(--nk-emerald-dark); margin-bottom: 14px; }
.nk-dl img { width: 100%; height: auto; border: 1.5px solid var(--nk-border-glass); border-radius: 14px; display: block; background: #ffffff; box-shadow: 0 4px 12px rgba(0,0,0,0.04); }
.nk-meta { font-size: 12.5px; color: var(--nk-text-soft); margin: 10px 0 14px; text-align: center; font-weight: 600; }
.nk-dl .nk-btn { width: 100%; justify-content: center; }
.nk-facts { padding: 20px; border-top: 1px solid var(--nk-border-glass); background: #fafdfc; }
.nk-facts dl { display: grid; grid-template-columns: auto 1fr; gap: 10px 14px; font-size: 14px; }
.nk-facts dt { color: var(--nk-text-soft); font-weight: 600; }
.nk-facts dd { color: var(--nk-text-dark); font-weight: 800; text-align: right; }

.nk-sec { margin: 28px 0 0; }
.nk-sec>h2 { font-family: var(--nk-font); font-size: 22px; font-weight: 800; color: var(--nk-emerald-dark); margin-bottom: 6px; letter-spacing: -0.3px; }
.nk-sec>p.nk-lede { font-size: 14px; color: var(--nk-text-mid); margin-bottom: 16px; font-weight: 500; }

/* District Chips & Responsive Cards Grid */
.nk-chips { display: flex; flex-wrap: wrap; gap: 10px; }
.nk-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: #ffffff;
  border: 1.5px solid var(--nk-border-glass);
  border-radius: 999px;
  padding: 8px 16px;
  font-size: 13.5px;
  font-weight: 700;
  color: var(--nk-emerald-dark);
  text-decoration: none;
  transition: all 0.2s cubic-bezier(0.34, 1.56, 0.64, 1);
  box-shadow: 0 2px 6px rgba(0,0,0,0.03);
}
.nk-chip:hover {
  border-color: var(--nk-mint);
  background: #eef9f3;
  transform: translateY(-2px) scale(1.03);
  box-shadow: 0 6px 16px rgba(82, 183, 136, 0.2);
}

/* min-width:0 on both: the grid is a flex child of the content column, and a
   210px track could not hold "दक्षिण कन्नड़ / Dakshina Kannada" — the row's
   content min-width won, tracks blew past the viewport and the whole page
   scrolled sideways with the district names spilling out of their own cards. */
.nk-dgrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 240px), 1fr));
  gap: 12px; width: 100%; min-width: 0; }
.nk-drow {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
  overflow: hidden;
  background: #ffffff;
  border: 1.5px solid var(--nk-border-glass);
  border-radius: 14px;
  padding: 13px 16px;
  text-decoration: none;
  color: var(--nk-text-dark);
  transition: all 0.25s cubic-bezier(0.34, 1.56, 0.64, 1);
  box-shadow: 0 2px 8px rgba(0,0,0,0.03);
}
.nk-drow:hover {
  border-color: var(--nk-mint);
  background: #eef9f3;
  transform: translateY(-3px);
  box-shadow: 0 8px 20px rgba(82, 183, 136, 0.18);
}
.nk-drow .nk-num {
  font-size: 12px;
  font-weight: 800;
  color: var(--nk-emerald-dark);
  width: 28px;
  height: 28px;
  background: linear-gradient(135deg, #e4f4eb 0%, #ccead9 100%);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.nk-drow b { font-size: 15px; font-weight: 800; color: var(--nk-emerald-dark); }
/* Hindi over English, not side by side: on one line the English spelling was
   ellipsised away on every long name (Chikkaballap…), which is exactly the
   thing this list exists to give people. */
.nk-drow .nk-dname { display: flex; flex-direction: column; gap: 1px; min-width: 0;
  text-decoration: none; color: inherit; }
.nk-drow .nk-dname:hover b { text-decoration: underline; }
.nk-drow span.nk-en { font-size: 12px; color: var(--nk-text-soft); font-weight: 600;
  line-height: 1.35; }

/* State Navigation Grid */
.nk-sgrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; width: 100%; }
.nk-scard {
  display: flex;
  align-items: center;
  gap: 12px;
  background: #ffffff;
  border: 1.5px solid var(--nk-border-glass);
  border-radius: 14px;
  padding: 14px 16px;
  text-decoration: none;
  color: var(--nk-text-dark);
  transition: all 0.25s ease;
  box-shadow: 0 2px 8px rgba(0,0,0,0.03);
}
.nk-scard:hover {
  border-color: var(--nk-mint);
  background: #f2faf5;
  transform: translateY(-3px);
  box-shadow: 0 8px 20px rgba(82, 183, 136, 0.15);
}
.nk-scard .nk-sn { display: flex; flex-direction: column; min-width: 0; }
.nk-scard b { font-size: 14.5px; font-weight: 800; color: var(--nk-emerald-dark); }
.nk-scard small { font-size: 12px; color: var(--nk-text-soft); margin-top: 2px; font-weight: 600; }
.nk-scard .nk-go { margin-left: auto; color: var(--nk-emerald-light); font-size: 18px; font-weight: 800; }

/* District Directory Banner on Map Page */
.nk-dir-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  background: linear-gradient(135deg, #071f16 0%, #134232 100%);
  border-radius: var(--nk-radius-md);
  padding: 20px 24px;
  color: #ffffff;
  margin: 28px 0 16px;
  box-shadow: var(--nk-shadow-md);
  border: 1px solid rgba(255, 255, 255, 0.12);
  flex-wrap: wrap;
}
.nk-db-info h3 {
  font-size: 18px;
  font-weight: 800;
  margin: 0 0 4px;
  color: #ffffff;
}
.nk-db-info p {
  font-size: 13.5px;
  color: rgba(255, 255, 255, 0.85);
  margin: 0;
  font-weight: 500;
}

/* Quick Metrics Row on Directory Page */
.nk-stats-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px;
  margin: 20px 0 16px;
}
.nk-stat-card {
  background: #ffffff;
  border: 1.5px solid var(--nk-border-glass);
  border-radius: var(--nk-radius-md);
  padding: 14px 16px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.03);
}
.nk-stat-card .nk-st-lbl {
  font-size: 12px;
  color: var(--nk-text-soft);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}
.nk-stat-card .nk-st-val {
  font-size: 16.5px;
  color: var(--nk-emerald-dark);
  font-weight: 800;
  margin-top: 4px;
}

.nk-drow-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
}
.nk-dact-btn {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 4px 9px;
  border-radius: 6px;
  font-size: 11.5px;
  font-weight: 700;
  text-decoration: none;
  background: var(--nk-gold-light);
  color: #8f5b00;
  border: 1px solid rgba(245, 183, 49, 0.4);
  transition: all 0.2s ease;
}
.nk-dact-btn:hover {
  background: var(--nk-gold);
  color: #071f16;
}

/* Distance badge on a village chip. Muted on purpose — the name is what is
   being chosen, the km is only the sort order made visible. */
.nk-km {
  font-size: 11px;
  font-weight: 700;
  color: var(--nk-text-soft);
  background: #f2f7f4;
  border-radius: 999px;
  padding: 2px 7px;
}

.nk-note { background: #fffbeb; border: 1.5px solid #f2e3b8; border-radius: 14px; padding: 14px 18px; font-size: 13.5px; color: #7a6320; line-height: 1.6; margin-top: 16px; font-weight: 500; }
.nk-updated { font-size: 12.5px; color: var(--nk-text-soft); margin: 24px 0 0; font-weight: 600; }
.nk-search { width: 100%; max-width: 480px; padding: 14px 18px; border: 1.5px solid var(--nk-border-glass); border-radius: 14px; font-size: 15px; font-family: inherit; background: #ffffff; margin-top: 16px; box-shadow: 0 4px 12px rgba(0,0,0,0.04); font-weight: 600; }
.nk-search:focus { outline: none; border-color: var(--nk-mint); box-shadow: 0 0 0 4px rgba(82, 183, 136, 0.22); }
.nk-empty { font-size: 14px; color: var(--nk-text-soft); padding: 10px 2px; font-weight: 600; }
.faq h3 { font-size: 16px; color: var(--nk-emerald-dark); font-weight: 800; }
.faq a { color: var(--nk-emerald-mid); font-weight: 700; }

/* Mobile First Responsive Adjustments */
@media (max-width: 768px) {
  .nk-hero { padding: 24px 20px; border-radius: 16px; }
  .nk-hero h1 { font-size: 26px; }
  .nk-hero .nk-sub { font-size: 14px; }
  .nk-cta { flex-direction: column; width: 100%; gap: 10px; }
  .nk-cta .nk-btn, .nk-cta .nk-state-select { width: 100%; justify-content: center; }
  .nk-split { grid-template-columns: 1fr; scroll-margin-top: 130px; }
  .nk-map { height: 440px; }
  /* Toolbar stays ONE row even on a phone — that's the point of the compact
     redesign. Only the padding/icon size shrink further. */
  .nk-map-toolbar { padding: 8px 10px; gap: 6px; }
  .nk-mt-select { padding: 0 2px 0 8px; }
  .nk-map-select { font-size: 13px; }
  .nk-mt-icon-btn { width: 34px; height: 34px; font-size: 14px; }
  .nk-geo-search-box { padding: 0 10px 10px; }
  /* min(100%,…): a fixed 150px minimum still produced two tracks a long
     district name could not fit in, and the row spilled out of its card. */
  .nk-dgrid { grid-template-columns: repeat(auto-fill, minmax(min(100%, 210px), 1fr)); gap: 10px; }
  .nk-sgrid { grid-template-columns: repeat(auto-fill, minmax(min(100%, 155px), 1fr)); }
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


def _tail_scripts(s: dict = None, initial: str = "") -> str:
    """map-download.js everywhere; Leaflet only where there is a map to draw.

    `initial` is a district name the map should open already selected. A district
    page passes it so the zoom is part of the rendered page rather than a
    ?district= query string — the whole point of tier 3 is that the district has
    its own URL, and a canonical that depends on a query param is not one."""
    # Inline and first: this runs while the document is still parsing, before
    # the deferred location.js executes, so the flag is set in time.
    out = ['<script>window.KM_LOC_AFTER_SCROLL=true;</script>',
           f'<script src="{_asset("map-download.js")}" defer></script>']
    if s:
        # json.dumps, not a quoted f-string slot: district names carry quotes and
        # non-ASCII, and one apostrophe would end the JS string literal.
        initial_js = json.dumps(initial, ensure_ascii=False)
        out.append('<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>')
        out.append(f"""<script>
(function(){{
  if(!window.L)return;
  var map=L.map('nk-map',{{zoomSnap:0.25}}).setView([{s['lat']},{s['lon']}],6);
  var osmLayer=L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',
    {{attribution:'© OpenStreetMap contributors',maxZoom:19}});
  var satLayer=L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}',
    {{attribution:'Tiles © Esri World Imagery',maxZoom:19}});
  var labelLayer=L.tileLayer('https://{{s}}.basemaps.cartocdn.com/rastertiles/voyager_only_labels/{{z}}/{{x}}/{{y}}{{r}}.png',
    {{attribution:'© CartoDB',maxZoom:19}});

  // Satellite is the default view — a farmer checking their own field wants
  // the real photo, not a vector sketch — with place labels on top so a bare
  // satellite tile isn't just unmarked ground. Vector stays one tap away in
  // the layer control, listed second.
  satLayer.addTo(map);
  labelLayer.addTo(map);

  L.control.layers({{
    "🛰️ सैटेलाइट फ़ील्ड व्यू (Satellite)": satLayer,
    "🗺️ नक्शा (Vector Map)": osmLayer
  }}, {{
    "🏘️ गांव व सड़क लेबल": labelLayer
  }}, {{position:'topright'}}).addTo(map);

  // Add Close (✕) button inside expanded Leaflet layer control
  setTimeout(function(){{
    var layersCtrl=document.querySelector('#nk-map .leaflet-control-layers');
    if(layersCtrl){{
      var closeBtn=document.createElement('span');
      closeBtn.className='nk-layers-close';
      closeBtn.innerHTML='✕';
      closeBtn.title='बंद करें';
      closeBtn.addEventListener('click',function(e){{
        e.stopPropagation();
        e.preventDefault();
        layersCtrl.classList.remove('leaflet-control-layers-expanded');
      }});
      layersCtrl.appendChild(closeBtn);
    }}
  }},100);

  var geojsonLayer=null, allLayers=[], districtMap={{}};
  var selectEl=document.getElementById('nk-district-select');
  var resetBtn=document.getElementById('nk-reset-btn');
  var infoCard=document.getElementById('nk-district-panel');
  var distTitle=document.getElementById('nk-dp-name');
  var bhavLink=document.getElementById('nk-dp-bhav');
  var weatherLink=document.getElementById('nk-dp-weather');
  var searchInput=document.getElementById('nk-vsearch-input');
  var searchBtn=document.getElementById('nk-vsearch-btn');
  var searchToggle=document.getElementById('nk-vsearch-toggle');
  var searchBox=document.getElementById('nk-geo-search-box');

  // The 🔍 icon reveals the village/tehsil row rather than it sitting open on
  // every visit — collapsed is what keeps the toolbar to one line.
  if(searchToggle&&searchBox){{
    searchToggle.addEventListener('click',function(){{
      var open=searchBox.classList.toggle('open');
      searchToggle.classList.toggle('active',open);
      searchToggle.setAttribute('aria-expanded',open?'true':'false');
      if(open&&searchInput)searchInput.focus();
    }});
  }}

  var currentMarker=null;
  function searchVillageOrTehsil(){{
    if(!searchInput)return;
    var q=searchInput.value.trim();
    if(!q)return;
    var fullQuery=q+', {s["hi"]}, India';
    fetch('https://nominatim.openstreetmap.org/search?format=json&q='+encodeURIComponent(fullQuery))
      .then(function(r){{return r.json();}})
      .then(function(data){{
        if(data&&data.length>0){{
          var place=data[0];
          var lat=parseFloat(place.lat);
          var lon=parseFloat(place.lon);
          if(!map.hasLayer(satLayer)){{
            map.addLayer(satLayer);
            map.addLayer(labelLayer);
          }}
          map.setView([lat,lon],13);
          if(currentMarker)map.removeLayer(currentMarker);
          currentMarker=L.marker([lat,lon]).addTo(map);
          currentMarker.bindPopup('<b>🌾 '+place.display_name+'</b>').openPopup();
          var el=document.getElementById('nk-map');
          if(el)el.scrollIntoView({{behavior:'smooth',block:'center'}});
        }}else{{
          alert('गांव या तहसील नहीं मिली: '+q);
        }}
      }}).catch(function(e){{console.error(e);}});
  }}

  if(searchBtn)searchBtn.addEventListener('click',searchVillageOrTehsil);
  if(searchInput)searchInput.addEventListener('keypress',function(e){{if(e.key==='Enter')searchVillageOrTehsil();}});

  var defaultStyle={{color:'#2d6a4f',weight:1.4,fillColor:'#52b788',fillOpacity:.30}};
  var highlightStyle={{color:'#0f2e22',weight:3,fillColor:'#e9a825',fillOpacity:.75}};
  var dimmedStyle={{color:'#2d6a4f',weight:1,fillColor:'#52b788',fillOpacity:.12}};

  function selectDistrict(name, autoScroll){{
    if(!name){{resetView();return;}}
    var foundKey=Object.keys(districtMap).find(function(k){{return k.toLowerCase()===name.toLowerCase();}});
    if(!foundKey)return;

    var item=districtMap[foundKey];
    var layer=item.layer, hiName=item.hiName, enName=item.enName;

    allLayers.forEach(function(l){{l.setStyle(dimmedStyle);}});
    layer.setStyle(highlightStyle);
    if(layer.bringToFront)layer.bringToFront();

    map.fitBounds(layer.getBounds(),{{padding:[24,24],maxZoom:11}});

    if(distTitle)distTitle.textContent=hiName+' ('+enName+')';
    /* The hrefs stay as rendered — there is no district-level भाव or मौसम page
       to point at, and the query string these lines used to build was read by
       neither route. Only the label moves with the selection. */
    if(infoCard)infoCard.classList.add('active');
    if(resetBtn)resetBtn.style.display='inline-block';
    if(selectEl&&selectEl.value!==hiName)selectEl.value=hiName;

    if(autoScroll){{
      var el=document.getElementById('nk-map');
      if(el)el.scrollIntoView({{behavior:'smooth',block:'center'}});
    }}
  }}

  function resetView(){{
    allLayers.forEach(function(l){{l.setStyle(defaultStyle);}});
    if(geojsonLayer)map.fitBounds(geojsonLayer.getBounds(),{{padding:map.getSize().x<500?[6,6]:[18,18]}});
    if(infoCard)infoCard.classList.remove('active');
    if(resetBtn)resetBtn.style.display='none';
    if(selectEl)selectEl.value='';
  }}

  if(resetBtn)resetBtn.addEventListener('click',resetView);

  fetch('/data/{s["geojson"]}').then(function(r){{return r.json();}}).then(function(g){{
    geojsonLayer=L.geoJSON(g,{{
      style:defaultStyle,
      onEachFeature:function(f,l){{
        var hiName=f.properties.district_hi||f.properties.district||'District';
        var enName=f.properties.district||hiName;
        allLayers.push(l);
        districtMap[hiName]={{layer:l,feature:f,hiName:hiName,enName:enName}};
        districtMap[enName]={{layer:l,feature:f,hiName:hiName,enName:enName}};

        l.bindTooltip(hiName,{{sticky:true}});
        l.on('click',function(){{selectDistrict(hiName,true);}});
        l.on('mouseover',function(){{
          if(selectEl&&selectEl.value!==hiName&&selectEl.value!==enName){{
            l.setStyle({{fillColor:'#e9a825',fillOpacity:.50}});
          }}
        }});
        l.on('mouseout',function(){{
          if(selectEl&&(selectEl.value===hiName||selectEl.value===enName))return;
          if(selectEl&&selectEl.value)l.setStyle(dimmedStyle);
          else l.setStyle(defaultStyle);
        }});
      }}
    }}).addTo(map);

    var fit=function(){{
      map.invalidateSize();
      if(!selectEl||!selectEl.value){{
        map.fitBounds(geojsonLayer.getBounds(),{{padding:map.getSize().x<500?[6,6]:[18,18]}});
      }}
    }};
    fit();
    setTimeout(fit,300);
    var t;window.addEventListener('resize',function(){{clearTimeout(t);t=setTimeout(fit,200);}});

    // Populate Dropdown
    if(selectEl){{
      var sortedNames=Object.keys(districtMap).filter(function(k){{return districtMap[k].hiName===k;}})
        .sort(function(a,b){{return a.localeCompare(b,'hi');}});
      sortedNames.forEach(function(hiName){{
        var opt=document.createElement('option');
        opt.value=hiName;
        opt.textContent=hiName+' ('+districtMap[hiName].enName+')';
        selectEl.appendChild(opt);
      }});
      selectEl.addEventListener('change',function(e){{selectDistrict(e.target.value,true);}});
    }}

    // A district page names its own district server-side; ?district= stays
    // supported for the links that predate tier 3 and for anything already
    // bookmarked. No autoScroll on the server-set one — the visitor asked for
    // this district by URL, so yanking the viewport on load is just jarring.
    var initial={initial_js};
    if(initial){{
      setTimeout(function(){{selectDistrict(initial,false);}},250);
    }}else{{
      var distParam=new URLSearchParams(window.location.search).get('district');
      if(distParam)setTimeout(function(){{selectDistrict(distParam,true);}},400);
    }}
  }});
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

    groups = []
    for region in _REGION_ORDER:
        keys = [k for k, s in states.items() if s["region"] == region]
        if not keys:
            continue
        groups.append(
            f'<section class="nk-sec" data-region><h2>{region}</h2>'
            f'<p class="nk-lede">{len(keys)} राज्य/केंद्र शासित प्रदेश</p>'
            f'<div class="nk-sgrid">{_state_cards(keys, states)}</div></section>')

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

    body = f"""<h1 class="nk-title">भारत के राज्यों के नक्शे</h1>
<p class="nk-title-sub">{n_states} राज्य व केंद्र शासित प्रदेश · {total_d} जिले — हिंदी में जिलेवार नक्शे, HD डाउनलोड बिल्कुल मुफ्त</p>
<div class="nk-controls">
{_dl_button(states['uttar-pradesh'], "HD नक्शा डाउनलोड करें")}
{_state_select_dropdown('uttar-pradesh', states, is_jile=False)}
</div>
<input class="nk-search" id="nk-search" type="search" autocomplete="off"
 placeholder="राज्य खोजें — जैसे बिहार, Kerala…" aria-label="राज्य खोजें">
<p class="nk-empty" id="nk-none" style="display:none">कोई राज्य नहीं मिला।</p>
{''.join(groups)}
<section class="nk-sec"><h2>नक्शों से जुड़े सवाल</h2>{faq_html}</section>
<p class="nk-updated">🕒 अंतिम अपडेट: {_hindi_date(_updated())} · सीमा-डेटा: Census of India</p>
<script>
/* Client-side filter: 36 cards are already in the HTML (crawlable), this only
   hides the ones that do not match, matching Hindi or English spelling. */
(function(){{
  var q=document.getElementById('nk-search'),none=document.getElementById('nk-none');
  if(!q)return;
  var cards=[].slice.call(document.querySelectorAll('.nk-scard'));
  var secs=[].slice.call(document.querySelectorAll('[data-region]'));
  q.addEventListener('input',function(){{
    var v=q.value.trim().toLowerCase(),hits=0;
    cards.forEach(function(c){{
      var on=!v||c.textContent.toLowerCase().indexOf(v)>-1||
             (c.getAttribute('href')||'').toLowerCase().indexOf(v)>-1;
      c.style.display=on?'':'none';if(on)hits++;
    }});
    secs.forEach(function(s){{
      s.style.display=s.querySelector('.nk-scard:not([style*="none"])')?'':'none';
    }});
    none.style.display=hits?'none':'';
  }});
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

    # Real district URLs, not ?district= on this same page. The query-string
    # version rendered the identical canonical for all 75 links, so every one of
    # them was a self-reference as far as a crawler was concerned.
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

    # Shown only on the legacy /map URL: a one-time popup pointing at the
    # slug every other state already uses. /map itself is untouched — no
    # server redirect — so the old, widely-linked URL keeps working exactly
    # as before; this only offers the new one.
    up_popup = _up_url_popup() if canon == f"{SITE}/map" else ""
    body = f"""{up_popup}<div class="nk-level-bar">
  <a href="/naksha">🇮🇳 भारत (India)</a>
  <span class="nk-lvl-sep">➔</span>
  <a href="{_url(key)}">🏛️ {escape(hi)}</a>
  <span class="nk-lvl-sep">➔</span>
  <span style="color:var(--nk-emerald-dark)">📍 जिला / 🏢 तहसील / 🌾 गांव सैटेलाइट</span>
</div>

<h1 class="nk-title">{escape(hi)} का नक्शा</h1>
<p class="nk-title-sub">{_jile(n)} · {escape(span)} · हिंदी में जिलेवार मानचित्र</p>
<div class="nk-controls">
{_dl_button(s, "HD नक्शा डाउनलोड करें")}
{_state_select_dropdown(key, states, is_jile=False)}
</div>

<div class="nk-tabs-bar">
  <a class="nk-tab-item active" href="{_url(key)}#nk-map-section">🗺️ इंटरैक्टिव नक्शा</a>
  <a class="nk-tab-item" href="{_jile_url(key)}">📋 जिलों की सूची ({n})</a>
</div>

<div class="nk-split" id="nk-map-section">
  <div class="nk-card">
    <div class="nk-map-toolbar">
      <label class="nk-mt-select" for="nk-district-select">
        <span class="nk-mt-ic">📍</span>
        <select id="nk-district-select" class="nk-map-select" aria-label="जिला चुनें">
          <option value="">{escape(hi)} का जिला चुनें</option>
        </select>
      </label>
      <button type="button" id="nk-vsearch-toggle" class="nk-mt-icon-btn"
              aria-label="गांव या तहसील खोजें" aria-expanded="false" title="गांव या तहसील खोजें">🔍</button>
      <button id="nk-reset-btn" class="nk-mt-icon-btn nk-reset-btn" aria-label="पूरा नक्शा दिखाएं" title="पूरा नक्शा दिखाएं">✕</button>
    </div>
    <div class="nk-geo-search-box" id="nk-geo-search-box">
      <input type="text" id="nk-vsearch-input" class="nk-village-input" placeholder="गांव या तहसील खोजें — जैसे मवाना, सरधना..." aria-label="गांव या तहसील खोजें">
      <button type="button" id="nk-vsearch-btn" class="nk-village-btn">खोजें</button>
    </div>
    <div id="nk-map" class="nk-map"></div>
    <div id="nk-district-panel" class="nk-district-panel">
      <div class="nk-dp-head">
        <h3 class="nk-dp-title">📍 <span id="nk-dp-name">--</span></h3>
        <span class="nk-dp-badge">जिला विशेष नक्शा</span>
      </div>
      <div class="nk-dp-grid">
        <a id="nk-dp-weather" class="nk-dp-btn weather" href="/weather">🌤️ मौसम पूर्वानुमान</a>
        <a id="nk-dp-fasal" class="nk-dp-btn fasal" href="/meri_fasal.html">🌱 फसल सलाह</a>
      </div>
    </div>
    <div class="nk-cap">🗺️ {escape(hi)} — जिले पर टैप करें या ऊपर ड्रॉपडाउन से जिला चुनें, नक्शा खुद ज़ूम होकर उस जिले की जानकारी दिखाएगा।</div>
  </div>
  <aside class="nk-card">
    <div class="nk-dl">
      <h2>⬇️ प्रिंट लायक HD नक्शा</h2>
      <img src="{_img(s, 'district-map.webp')}" width="{s['w']}" height="{s['h']}"
           loading="lazy" alt="{escape(alt)}">
      <p class="nk-meta">PNG · {s['w']}×{s['h']} px · हिंदी नाम · मुफ्त HD</p>
      {_dl_button(s, "HD डाउनलोड करें")}
    </div>
    <div class="nk-facts">
      <h2>एक नज़र में</h2>
      <dl>
        <dt>कुल जिले</dt><dd>{n}</dd>
        <dt>सबसे बड़ा जिला</dt><dd>{escape(s['big'])}</dd>
        <dt>सबसे छोटा जिला</dt><dd>{escape(s['small'])}</dd>
        <dt>उत्तर से दक्षिण</dt><dd>{escape(span)}</dd>
      </dl>
    </div>
  </aside>
</div>

<div class="nk-dir-banner">
  <div class="nk-db-info">
    <h3>📋 {escape(hi)} के सभी {n} जिलों की पूरी सूची (District Directory)</h3>
    <p>हर जिले का नाम हिंदी और अंग्रेज़ी दोनों वर्तनी में — नाम पर टैप करके उसे नक्शे में देखें।</p>
  </div>
  <a class="nk-btn primary" href="{_jile_url(key)}">पूरी जिला सूची देखें →</a>
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
{_tail_scripts(s)}"""

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

    # Each row now points at the district's own page (tier 3), not ?district= on
    # the state map. This list is the cluster's main crawl path into the tier —
    # every district in the state is reachable from one indexed page.
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
<div class="nk-controls">
{_dl_button(s, "HD नक्शा डाउनलोड करें")}
{_state_select_dropdown(key, states, is_jile=True)}
</div>

<div class="nk-tabs-bar">
  <a class="nk-tab-item" href="{_url(key)}#nk-map-section">🗺️ इंटरैक्टिव नक्शा</a>
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
    # A one- or two-district UT (दिल्ली, चंडीगढ़, लक्षद्वीप, लद्दाख, गोवा) has a
    # list page that says nothing its map page does not already say. Keep it —
    # the links stay useful — but out of the index, rather than adding five thin
    # pages that compete with the real ones.
    robots = "noindex, follow" if n < 3 else ""

    return _doc(title, desc, canon,
                _crumbs([("राज्यों के नक्शे", f"{SITE}/naksha"),
                         (f"{hi} का नक्शा", _url(key)), (f"{hi} के जिले", None)]),
                body, ld=_ld(page_ld, list_ld, crumb, faq_ld),
                og_img=_abs_img(s, "og.png"), active="map", extra_css=_NK_CSS,
                robots=robots)


# ── one district's map (tier 3) ─────────────────────────────────────────────

def _sibling_chips(key: str, s: dict, skip: str) -> str:
    """Every other district in the state, as real links. This is what turns a
    state's districts into a crawlable set: each district page links to all its
    siblings, so one entry point reaches the whole state."""
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

    # Queue the village fetch from the district page, not just the गांव page:
    # this is the page Google reaches first, so by the time a crawler follows
    # the गांव link the data is usually already on disk.
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
         f"🔍 बटन से गांव या तहसील का नाम डालकर सीधे वहीं पहुंचा जा सकता है।"),
        (f"{hi} जिले में कौन-कौन से गांव हैं?",
         (f"{hi} के {len(villages)} गांव व कस्बे इस समय दर्ज हैं — पूरी सूची “{hi} के "
          f"गांव” पेज पर है, हर गांव के अपने नक्शे के साथ।") if villages else
         (f"{hi} के गांवों की सूची तैयार हो रही है। तब तक नक्शे के 🔍 बटन से गांव या "
          f"तहसील का नाम डालकर उसे सीधे सैटेलाइट नक्शे पर देखा जा सकता है।")),
        (f"{hi} का नक्शा डाउनलोड कैसे करें?",
         f"“HD नक्शा डाउनलोड करें” बटन से {shi} का पूरा जिलेवार नक्शा (PNG) मुफ्त "
         f"डाउनलोड होता है — उसमें {hi} समेत सभी {n} जिले हिंदी नामों के साथ हैं। "
         f"नक्शा CC BY 4.0 पर है, स्रोत में KrashiMitra.in लिख दें।"),
    ])

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
<div class="nk-controls">
{_dl_button(s, f"{shi} का HD नक्शा")}
{_state_select_dropdown(key, states, is_jile=False)}
</div>

<div class="nk-tabs-bar">
  <a class="nk-tab-item active" href="{_d_url(key, dslug)}">🗺️ {escape(hi)} का नक्शा</a>
  <a class="nk-tab-item" href="{_gaon_url(key, dslug)}">🌾 गांव की सूची{f' ({len(villages)})' if villages else ''}</a>
  <a class="nk-tab-item" href="{_jile_url(key)}">📋 {escape(shi)} के जिले</a>
</div>

<div class="nk-split" id="nk-map-section">
  <div class="nk-card">
    <div class="nk-map-toolbar">
      <label class="nk-mt-select" for="nk-district-select">
        <span class="nk-mt-ic">📍</span>
        <select id="nk-district-select" class="nk-map-select" aria-label="जिला चुनें">
          <option value="">{escape(shi)} का जिला चुनें</option>
        </select>
      </label>
      <button type="button" id="nk-vsearch-toggle" class="nk-mt-icon-btn"
              aria-label="गांव या तहसील खोजें" aria-expanded="false" title="गांव या तहसील खोजें">🔍</button>
      <button id="nk-reset-btn" class="nk-mt-icon-btn nk-reset-btn" aria-label="पूरा नक्शा दिखाएं" title="पूरा नक्शा दिखाएं">✕</button>
    </div>
    <div class="nk-geo-search-box" id="nk-geo-search-box">
      <input type="text" id="nk-vsearch-input" class="nk-village-input"
             placeholder="{escape(hi)} का गांव या तहसील — जैसे {escape(villages[0]['name']) if villages else 'मवाना'}…"
             aria-label="गांव या तहसील खोजें">
      <button type="button" id="nk-vsearch-btn" class="nk-village-btn">खोजें</button>
    </div>
    <div id="nk-map" class="nk-map"></div>
    <div id="nk-district-panel" class="nk-district-panel">
      <div class="nk-dp-head">
        <h3 class="nk-dp-title">📍 <span id="nk-dp-name">{escape(hi)}</span></h3>
        <span class="nk-dp-badge">जिला विशेष नक्शा</span>
      </div>
      <div class="nk-dp-grid">
        <a id="nk-dp-weather" class="nk-dp-btn weather" href="/weather">🌤️ मौसम पूर्वानुमान</a>
        <a id="nk-dp-fasal" class="nk-dp-btn fasal" href="/meri_fasal.html">🌱 फसल सलाह</a>
      </div>
    </div>
    <div class="nk-cap">🛰️ {escape(hi)} की सीमा नक्शे पर हाइलाइट है — ज़ूम करके अपने गांव तक जाएं, या 🔍 से नाम खोजें।</div>
  </div>
  <aside class="nk-card">
    <div class="nk-dl">
      <h2>⬇️ {escape(shi)} का HD नक्शा</h2>
      <img src="{_img(s, 'district-map.webp')}" width="{s['w']}" height="{s['h']}"
           loading="lazy"
           alt="{escape(f'{shi} का नक्शा — {hi} समेत सभी {n} जिलों का हिंदी जिलेवार मानचित्र')}">
      <p class="nk-meta">PNG · {s['w']}×{s['h']} px · {escape(hi)} समेत {n} जिले</p>
      {_dl_button(s, "HD डाउनलोड करें")}
    </div>
    <div class="nk-facts">
      <h2>{escape(hi)} — एक नज़र में</h2>
      <dl>
        <dt>राज्य</dt><dd>{escape(shi)}</dd>
        <dt>अंग्रेज़ी नाम</dt><dd>{escape(en)}</dd>
        <dt>राज्य के कुल जिले</dt><dd>{n}</dd>
        <dt>दर्ज गांव/कस्बे</dt><dd>{len(villages) if villages else '—'}</dd>
      </dl>
    </div>
  </aside>
</div>

<div class="nk-dir-banner">
  <div class="nk-db-info">
    <h3>🌾 {escape(hi)} के गांव का नक्शा</h3>
    <p>{escape(v_line)}</p>
  </div>
  {v_cta}
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
{_tail_scripts(s, initial=hi)}"""

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
  if(!window.L)return;
  var lat={v['lat']}, lon={v['lon']};
  var map=L.map('nk-map',{{zoomSnap:0.25}}).setView([lat,lon],13);
  var sat=L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}',
    {{attribution:'Tiles © Esri World Imagery',maxZoom:19}}).addTo(map);
  var labels=L.tileLayer('https://{{s}}.basemaps.cartocdn.com/rastertiles/voyager_only_labels/{{z}}/{{x}}/{{y}}{{r}}.png',
    {{attribution:'© CartoDB',maxZoom:19}}).addTo(map);
  var osm=L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',
    {{attribution:'© OpenStreetMap contributors',maxZoom:19}});
  L.control.layers({{"🛰️ सैटेलाइट (Satellite)":sat,"🗺️ नक्शा (Map)":osm}},
                   {{"🏘️ गांव व सड़क लेबल":labels}},{{position:'topright'}}).addTo(map);
  L.marker([lat,lon]).addTo(map).bindPopup({label}).openPopup();
  setTimeout(function(){{map.invalidateSize();}},300);
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

<div class="nk-split" id="nk-map-section">
  <div class="nk-card">
    <div id="nk-map" class="nk-map"></div>
    <div class="nk-cap">🛰️ {escape(name_hi)} — नक्शा इसी जगह पर केंद्रित है। ज़ूम करके अपने खेत तक जाएं।</div>
  </div>
  <aside class="nk-card">
    <div class="nk-facts" style="border-top:none">
      <h2>{escape(name_hi)} — एक नज़र में</h2>
      <dl>
        <dt>प्रकार</dt><dd>{escape(kind)}</dd>
        <dt>जिला</dt><dd>{escape(dhi)}</dd>
        <dt>राज्य</dt><dd>{escape(shi)}</dd>
        <dt>अक्षांश</dt><dd>{v['lat']}° N</dd>
        <dt>देशांतर</dt><dd>{v['lon']}° E</dd>
      </dl>
    </div>
    <div class="nk-dl">
      <h2>इसी इलाके का और</h2>
      <div class="nk-cta" style="flex-direction:column;gap:9px">
        <a class="nk-btn plain" href="{_d_url(key, dslug)}">🗺️ {escape(dhi)} का नक्शा</a>
        <a class="nk-btn plain" href="{_gaon_url(key, dslug)}">🌾 {escape(dhi)} के सभी गांव</a>
        <a class="nk-btn plain" href="/weather">🌤️ {escape(dhi)} का मौसम</a>
        <a class="nk-btn plain" href="/bhav">💰 आज का मंडी भाव</a>
      </div>
    </div>
  </aside>
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


# ── routes ──────────────────────────────────────────────────────────────────

@router.get("/map", response_class=HTMLResponse)
def up_map():
    """उत्तर प्रदेश at the URL it has always had — every page's utility bar links
    here and it carries the cluster's search history."""
    return _state_page("uttar-pradesh", f"{SITE}/map")


@router.get("/naksha/{state}", response_class=HTMLResponse)
def state_map(state: str):
    # "uttarpradesh" (no hyphen) is the spelling the /map popup below links to,
    # and the one a farmer is likeliest to type from memory — both resolve to
    # the same page as the hyphenated slug.
    if state in ("uttar-pradesh", "uttarpradesh"):
        return RedirectResponse(f"{SITE}/map", status_code=301)
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
