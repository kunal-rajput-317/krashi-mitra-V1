# ============================================================
# routes/bhav.py
# Krishi Mitra — SEO price pages ("aaj ka mandi bhav")
#
# The crawlable front door to the mandi data. mandi.html renders every price
# client-side from /shop/mandi and keeps its state in query params, so it can
# never rank for "गेहूं का भाव मेरठ" — Googlebot sees an empty shell. These
# server-rendered pages are what search lands on; mandi.html is the in-app
# experience. Same data, two doors. Reached via the Netlify proxy /bhav/* →
# backend (200-rewrite), so the public URL stays krashimitra.in/bhav/...
#
# Four tiers, each matching a search a farmer actually types:
#   /bhav                           → crop grid              "आज का मंडी भाव"
#   /bhav/{crop}                    → states for that crop   "गन्ने का भाव"
#   /bhav/{crop}/{state}            → districts in a state   "UP में गन्ने का भाव"
#   /bhav/{crop}/{state}/{district} → the prices             "बरेली गन्ना भाव"
#
# WHY THE STATE IS IN THE URL. Four district names exist in two states each
# (bilaspur, hamirpur, pratapgarh, balrampur), so the old two-level
# /bhav/{crop}/{district} silently merged both states' rows onto one page while
# the heading claimed a single district — /bhav/wheat/pratapgarh served
# Rajasthan AND Uttar Pradesh mandis together. Scoping the leaf by state fixes
# that. It also makes the middle tier resolvable at all: `chandigarh` and
# `pondicherry` are both state AND district names, so /bhav/{crop}/{x} on its
# own is ambiguous. Legacy two-level URLs 301 to the canonical four-level one
# (see bhav_crop_or_state), so every link already out in the wild still works.
#
# Pages exist ONLY for combos present in the mandi_prices snapshot, so we never
# publish thin/empty doorway pages, and every hub carries real derived content
# (ranges, top-paying mandis) rather than being a bare grid of links.
# ============================================================

import json as _json
import re
import time
from datetime import date
from html import escape
from urllib.parse import quote, urlencode

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from backend.database.db import SessionLocal, MandiPrice
from backend.services.mandi_service import get_mandi_prices, _row_to_dict
from backend.routes.share import _crop_image, _HI_CROP_EN, _TILES

router = APIRouter()

SITE = "https://krashimitra.in"

# English commodity keyword → Hindi display name (reverse of share.py's
# _HI_CROP_EN, plus data.gov spellings that differ from the chip names).
_EN_HI = {en: hi for hi, en in _HI_CROP_EN.items()}
_EN_HI.update({
    "soyabean": "सोयाबीन", "bengal gram": "चना", "gram": "चना",
    "green gram": "मूंग", "black gram": "उड़द", "red gram": "अरहर",
    "tur": "अरहर", "arhar dal": "अरहर", "masur": "मसूर", "lentil": "मसूर",
    "rice": "चावल", "dhan": "धान", "maize": "मक्का", "corn": "मक्का",
    "mustard": "सरसों", "rapeseed": "सरसों", "garlic": "लहसुन",
    "chilly": "मिर्च", "chilli": "मिर्च", "dry chillies": "सूखी मिर्च",
    "turmeric": "हल्दी", "ginger": "अदरक", "banana": "केला",
    "tomato": "टमाटर", "brinjal": "बैंगन", "cauliflower": "फूलगोभी",
    "cabbage": "पत्तागोभी", "bajra": "बाजरा", "pearl millet": "बाजरा",
    "jowar": "ज्वार", "sorghum": "ज्वार", "barley": "जौ", "jau": "जौ",
    "sugarcane": "गन्ना", "cotton": "कपास", "groundnut": "मूंगफली",
    "peas": "मटर", "green peas": "हरी मटर", "apple": "सेब",
    "mango": "आम", "lemon": "नींबू", "coriander": "धनिया",
})

# Exact names for the Agmarknet variants. These are checked BEFORE the keyword
# fallback below, because that fallback is a blunt instrument: without these,
# "Sweet Potato" reads आलू, "Mustard Oil" reads सरसों and "Wheat Atta" reads गेहूं —
# a page confidently titled with the wrong crop.
_EN_HI.update({
    "wheat atta": "गेहूं आटा",
    "paddy(common)": "धान", "paddy(basmati)": "बासमती धान",
    "broken rice": "टुकड़ा चावल", "beaten rice": "चिवड़ा (पोहा)",
    "onion green": "हरी प्याज",
    "sweet potato": "शकरकंद",
    "sweet corn": "स्वीट कॉर्न", "baby corn": "बेबी कॉर्न",
    "mustard oil": "सरसों तेल",
    "cotton seed": "बिनौला (कपास बीज)",
    "turnip": "शलजम", "peach": "आड़ू", "pear(marasebu)": "नाशपाती",
    "cowpea(veg)": "लोबिया", "cowpea(lobia/karamani)": "लोबिया",
    "green chilli": "हरी मिर्च", "chili red": "लाल मिर्च",
    "ginger(green)": "अदरक", "ginger(dry)": "सोंठ",
    "turmeric(raw)": "कच्ची हल्दी",
    "bengal gram(gram)(whole)": "चना", "bengal gram dal(chana dal)": "चना दाल",
    "green gram(moong)(whole)": "मूंग", "green gram dal(moong dal)": "मूंग दाल",
    "black gram(urd beans)(whole)": "उड़द", "black gram dal(urd dal)": "उड़द दाल",
    "red gram/arhar/tur(whole)": "अरहर",
    "red gram split/arhar dal/tur dal": "अरहर दाल",
    "lentil(masur)(whole)": "मसूर", "masur dal": "मसूर दाल",
    "kabuli chana(chickpeas-white)": "काबुली चना",
    "gram raw(chholia)": "छोलिया", "kulthi(horse gram)": "कुल्थी",
    "groundnut pods(raw)": "मूंगफली (कच्ची)", "groundnut(split)": "मूंगफली दाना",
    "field pea": "मटर", "peas wet": "हरी मटर", "peas(dry)": "सूखी मटर",
    "white peas": "सफेद मटर",
    "pea pod/pea cod/हरी मटर": "हरी मटर",
    "pegeon pea(arhar fali)": "अरहर फली",
})

# Agmarknet spells a few of these its own way ("Chattisgarh", "Uttrakhand") —
# key on exactly what the feed sends, not the correct spelling.
_HI_STATES = {
    "Uttar Pradesh": "उत्तर प्रदेश", "Madhya Pradesh": "मध्य प्रदेश",
    "Maharashtra": "महाराष्ट्र", "Rajasthan": "राजस्थान", "Punjab": "पंजाब",
    "Haryana": "हरियाणा", "Bihar": "बिहार", "Gujarat": "गुजरात",
    "Karnataka": "कर्नाटक", "Tamil Nadu": "तमिलनाडु",
    # The feed sends "Keralam" and "Uttarakhand"; the older spellings are kept
    # alongside them in case Agmarknet reverts (it has changed these before).
    "Kerala": "केरल", "Keralam": "केरल",
    "Uttrakhand": "उत्तराखंड", "Uttarakhand": "उत्तराखंड",
    "West Bengal": "पश्चिम बंगाल", "Odisha": "ओडिशा", "Telangana": "तेलंगाना",
    "Andhra Pradesh": "आंध्र प्रदेश", "Chattisgarh": "छत्तीसगढ़",
    "Jharkhand": "झारखंड", "Assam": "असम",
    "Himachal Pradesh": "हिमाचल प्रदेश", "Goa": "गोवा", "Tripura": "त्रिपुरा",
    "Manipur": "मणिपुर", "Meghalaya": "मेघालय", "Nagaland": "नागालैंड",
    "Mizoram": "मिजोरम", "Sikkim": "सिक्किम", "Arunachal Pradesh": "अरुणाचल प्रदेश",
    "Chandigarh": "चंडीगढ़", "Pondicherry": "पुडुचेरी", "NCT of Delhi": "दिल्ली",
    "Jammu and Kashmir": "जम्मू और कश्मीर", "Andaman and Nicobar": "अंडमान निकोबार",
}

_HI_MONTHS = ["जनवरी", "फरवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई",
              "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"]


def _kw_in(text: str, keyword: str) -> bool:
    """Whole-word keyword match. A plain `keyword in text` is what made "Turnip"
    match the "tur" (अरहर) keyword and "Peach"/"Pear" match "pea" — so a turnip page
    was titled "अरहर का भाव". The boundary keeps "Wheat(Desi)" → गेहूं working while
    refusing to match a keyword that merely sits inside a longer word."""
    return re.search(rf"\b{re.escape(keyword)}\b", text) is not None


def _hindi_name(commodity: str) -> str:
    """Best-effort Hindi display name; falls back to the English name."""
    cl = (commodity or "").lower()
    if cl in _EN_HI:                        # exact name (incl. the variants above)
        return _EN_HI[cl]
    for en, hi in _EN_HI.items():           # whole-word match: "Wheat(Desi)" → गेहूं
        if _kw_in(cl, en):
            return hi
    return commodity


def _hindi_state(state: str) -> str:
    return _HI_STATES.get(state, state)


def _slugify(text: str) -> str:
    """'Sri Ganganagar' → 'sri-ganganagar'; 'Bengal Gram(Gram)' → 'bengal-gram-gram'."""
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower())
    return s.strip("-")


def _state_svg_slug(state: str) -> str:
    """'Uttar Pradesh' → 'uttar_pradesh' — matches the SVG filename in state_map_svgs/.
    Handles Agmarknet's non-standard spellings ('Keralam', 'Chattisgarh', etc.)
    by normalising them to the correct lowercase filename."""
    _OVERRIDES = {
        "Keralam":             "kerala",
        "Kerala":              "kerala",
        "Uttrakhand":          "uttarakhand",
        "Uttarakhand":         "uttarakhand",
        "Chattisgarh":         "chhattisgarh",
        "Chhattisgarh":        "chhattisgarh",
        "NCT of Delhi":        "delhi",
        "Jammu and Kashmir":   "jammu_and_kashmir",
        "Andaman and Nicobar": "andaman_and_nicobar",
        "Pondicherry":         "puducherry",
    }
    if state in _OVERRIDES:
        return _OVERRIDES[state]
    return re.sub(r"[^a-z0-9]+", "_", state.lower()).strip("_")


def _hindi_date(d: date) -> str:
    return f"{d.day} {_HI_MONTHS[d.month - 1]} {d.year}"


def _num(v) -> float | None:
    try:
        n = float(str(v).replace(",", ""))
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


def _rupee(v) -> str:
    """'2606.43' → '₹2,606'. Agmarknet reports fractional paise that mean nothing
    to a farmer quoting a rate."""
    n = _num(v)
    return f"₹{round(n):,}" if n else f"₹{escape(str(v))}"


def _hindi_data_date(s: str) -> str:
    """'11/07/2026' → '11 जुलाई'; anything unparseable passes through."""
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", (s or "").strip())
    if not m:
        return s or "-"
    day, month = int(m.group(1)), int(m.group(2))
    return f"{day} {_HI_MONTHS[month - 1]}" if 1 <= month <= 12 else s


# Agmarknet's commodity list carries a few non-crop items (livestock, fuel).
# They keep their own pages if someone lands on one, but they are never
# surfaced as "crops" in the hub, the sitemap, or the related-crop chips.
_NON_CROP = {"firewood", "wood", "coconut coir", "cock", "hen"}


def _is_crop(commodity: str) -> bool:
    return (commodity or "").strip().lower() not in _NON_CROP


def _tile_rank(commodity: str) -> int:
    """Position in _TILES — the same crop order as the app's mandi grid, so the hub
    opens on गेहूं/धान rather than whatever sorts first alphabetically.

    The MOST SPECIFIC keyword wins, not the first tile that matches. "Green
    Gram(Moong)(Whole)" matches both the generic "gram" (चना) tile and its own
    "green gram" (मूंग) tile; first-match handed मूंग and उड़द to the चना tile, where
    they lost to Bengal Gram and dropped off the hub entirely. Likewise "Red
    gram/Arhar/Tur(whole)" landed on चना, leaving the अरहर tile to be won by
    "Pegeon Pea(Arhar Fali)" — a 2-state vegetable standing in for a major pulse."""
    cl = (commodity or "").lower()
    best_rank, best_len = len(_TILES), 0
    for i, (keys, _file, _h) in enumerate(_TILES):
        for k in keys:
            if _kw_in(cl, k) and len(k) > best_len:
                best_rank, best_len = i, len(k)
    return best_rank


def _has_photo(commodity: str) -> bool:
    cl = (commodity or "").lower()
    return any(any(_kw_in(cl, k) for k in keys) for keys, _file, _h in _TILES)


def _mandis(n: int) -> str:
    return f"{n} मंडी" if n == 1 else f"{n} मंडियां"


def _mandis_gen(n: int) -> str:
    """Genitive: '1 मंडी की रिपोर्ट' but '5 मंडियों की रिपोर्ट'."""
    return f"{n} मंडी" if n == 1 else f"{n} मंडियों"


# ── Slug index ───────────────────────────────────────────────
# Built from SELECT DISTINCT on the snapshot; refreshed every 6h (the feed moves
# once a day). Powers all four tiers, the sitemap and the legacy 301s.
#   crops:   c_slug → commodity
#   states:  c_slug → { s_slug → state }
#   dists:   c_slug → { s_slug → { d_slug → district } }
#   legacy:  c_slug → { d_slug → [s_slug, ...] }   — resolves the old 2-level URLs
_index: dict = {}
_index_ts: float = 0.0
_INDEX_TTL = 6 * 3600


def _get_index() -> dict:
    global _index, _index_ts
    if _index and (time.time() - _index_ts) < _INDEX_TTL:
        return _index
    db = SessionLocal()
    try:
        rows = (db.query(MandiPrice.commodity, MandiPrice.state, MandiPrice.district)
                  .filter(MandiPrice.commodity.isnot(None),
                          MandiPrice.state.isnot(None),
                          MandiPrice.district.isnot(None))
                  .distinct().all())
    finally:
        db.close()

    crops, states, dists, legacy = {}, {}, {}, {}
    for commodity, state, district in rows:
        cs, ss, ds = _slugify(commodity), _slugify(state), _slugify(district)
        if not (cs and ss and ds):
            continue
        crops[cs] = commodity
        states.setdefault(cs, {})[ss] = state
        dists.setdefault(cs, {}).setdefault(ss, {})[ds] = district
        legacy.setdefault(cs, {}).setdefault(ds, [])
        if ss not in legacy[cs][ds]:
            legacy[cs][ds].append(ss)

    if crops:                   # keep the stale index if the DB comes back empty
        _index = {"crops": crops, "states": states, "dists": dists, "legacy": legacy}
        _index_ts = time.time()
    return _index


def _rows_for(commodity: str, state: str = "", district: str = "") -> list:
    """Every matching row — NOT get_mandi_prices(), which caps at 50 rows when a
    commodity is given. That cap is fine for the app's district view but silently
    truncates these pages: Uttar Pradesh alone has 68 wheat districts, so a 50-row
    sample left most district tiles priceless, skewed the state average, and — worst
    — computed "the highest-paying mandi" from an arbitrary subset, which could miss
    the actual best mandi. The aggregates here must see the whole state/country."""
    db = SessionLocal()
    try:
        q = db.query(MandiPrice)
        if commodity:
            q = q.filter(MandiPrice.commodity.ilike(commodity))
        if state:
            q = q.filter(MandiPrice.state.ilike(state))
        if district:
            q = q.filter(MandiPrice.district.ilike(district))
        rows = q.all()
    finally:
        db.close()

    if rows:
        return [_row_to_dict(r) for r in rows]
    # DB empty (fresh deploy) → fall back to the service's JSON seed path
    data = get_mandi_prices(commodity, district, state)
    return (data or {}).get("prices") or []


def _stats(prices: list) -> dict:
    """Average/min/max modal price, plus a mandi count that counts mandis rather
    than rows (one mandi can report several varieties)."""
    modals = [v for v in (_num(p.get("modal_price")) for p in prices) if v]
    mins   = [v for v in (_num(p.get("min_price"))   for p in prices) if v]
    maxs   = [v for v in (_num(p.get("max_price"))   for p in prices) if v]
    n = len({p.get("market") for p in prices if p.get("market")}) or len(prices)
    return {
        "avg": round(sum(modals) / len(modals)) if modals else None,
        "lo":  round(min(mins)) if mins else None,
        "hi":  round(max(maxs)) if maxs else None,
        "n":   n,
    }


def _crop_chip(href: str, label: str, commodity: str) -> str:
    """Link chip carrying the crop's photo — a farmer scanning the page can find
    his crop by sight, without reading every label."""
    thumb = (f'<img src="{escape(_crop_image(commodity, 330))}" alt="" loading="lazy" width="28" height="28">'
             if _has_photo(commodity) else '<span class="ico">🌾</span>')
    return f'<a class="chip" href="{href}">{thumb}{escape(label)}</a>'


def _related_links(c_slug: str, s_slug: str, d_slug: str,
                   commodity: str, district: str) -> str:
    """Same crop in other districts of THIS state + other crops in this district.

    Staying inside the state is the point: a farmer on the Bijnor wheat page cares
    what Meerut is paying, not Pune. Other states are reachable from the crop tier,
    so the internal linking that makes these pages rank is kept without the noise."""
    idx = _get_index()
    hi = _hindi_name(commodity)

    same_crop = [(ds, dn) for ds, dn
                 in sorted(idx["dists"].get(c_slug, {}).get(s_slug, {}).items(),
                           key=lambda kv: kv[1])
                 if ds != d_slug][:12]
    same_dist = sorted(
        ((cs, cn) for cs, cn in idx["crops"].items()
         if cs != c_slug and _is_crop(cn)
         and d_slug in idx["dists"].get(cs, {}).get(s_slug, {})),
        key=lambda x: (_tile_rank(x[1]), _hindi_name(x[1])))[:10]

    out = []
    if same_crop:
        chips = "".join(
            f'<a class="chip" href="/bhav/{c_slug}/{s_slug}/{ds}">'
            f'<span class="ico">📍</span>{escape(dn)}</a>' for ds, dn in same_crop)
        out.append(f'<h2>अन्य मंडियों में {escape(hi)} का भाव</h2><div class="chips">{chips}</div>')
    if same_dist:
        chips = "".join(
            _crop_chip(f"/bhav/{cs}/{s_slug}/{d_slug}", _hindi_name(cn), cn)
            for cs, cn in same_dist)
        out.append(f'<h2>{escape(district)} मंडी में अन्य फसलों के भाव</h2><div class="chips">{chips}</div>')
    return "\n".join(out)


# Design tokens mirror frontend/index.html + mandi.html so a farmer arriving from
# Google on /bhav lands on something that is visibly the same product as the app.
_CSS = """
:root{--green-dark:#1a3c2e;--green-mid:#2d6a4f;--green-light:#52b788;--green-pale:#d8f3dc;
--amber:#e9a825;--cream:#f5f7f4;--white:#fff;--text-dark:#1a2e23;--text-mid:#4a5a52;
--text-soft:#7c8983;--border:#e5e9e6;--shadow-sm:0 2px 10px rgba(26,60,46,.05);
--shadow-md:0 8px 28px rgba(26,60,46,.10);--radius-sm:12px;--radius-md:18px;
--font-serif:'Noto Serif Devanagari','Playfair Display',serif;
--font-body:'DM Sans','Noto Sans Devanagari',sans-serif}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:var(--font-body);background:var(--cream);color:var(--text-dark);line-height:1.6}
img{max-width:100%}
.wrap{max-width:980px;margin:0 auto;padding:0 20px 30px}

/* ── site header — same pre-topbar/topbar/main-header/blue-bar stack as
   mandi.html, so a page reached from Google reads as the same product as the
   app instead of a stripped-down doorway ── */
.header-wrapper{position:fixed;top:0;left:0;right:0;z-index:200;
transition:transform .28s cubic-bezier(.4,0,.2,1)}
.pre-topbar{background:var(--amber);color:#1a2e1e;display:flex;align-items:center;justify-content:center;
gap:10px;padding:7px 16px;font-size:13px;font-weight:600;text-align:center}
.pre-topbar-helpline{display:inline-flex;align-items:center;gap:6px;color:inherit;text-decoration:none;opacity:.9}
.pre-topbar-helpline:hover{opacity:1;text-decoration:underline}
.pre-topbar-phone-icon{display:inline-flex;align-items:center;justify-content:center;width:19px;height:19px;font-size:10px}

.top-utility-bar{background:var(--white);border-bottom:1px solid var(--border);padding:6px 0;font-size:12px}
.top-utility-inner{max-width:1280px;margin:0 auto;display:flex;justify-content:space-between;align-items:center;padding:0 80px}
.top-utility-left,.top-utility-right{display:flex;align-items:center;gap:12px}
.top-utility-link{color:var(--text-mid);text-decoration:none;font-weight:600}
.top-utility-link:hover{color:var(--green-mid)}
.top-utility-divider{color:var(--border)}
.top-utility-helpline{display:inline-flex;align-items:center;gap:6px;color:var(--green-dark);font-weight:700;text-decoration:none}
.top-utility-helpline:hover{opacity:.8;text-decoration:underline}

.main-header{position:sticky;top:0;z-index:100;background:var(--white);
border-bottom:1px solid var(--border);box-shadow:0 1px 3px rgba(26,60,46,.05)}
/* hamburger sits left of the logo (natural DOM order); nav centers itself
in the space between the logo and the avatar on the right */
.main-header-inner{max-width:1280px;margin:0 auto;padding:10px 80px;display:grid;
grid-template-columns:auto auto 1fr auto;column-gap:28px;align-items:center}
.header-left-group{display:flex;align-items:center;gap:14px}
.header-logo-link{display:flex;align-items:center;gap:8px;text-decoration:none}
.header-logo-circle{width:38px;height:38px;border-radius:50%;object-fit:cover;box-shadow:0 0 0 3px var(--green-pale)}
.header-logo-text{font-family:var(--font-serif);font-size:19px;font-weight:800;color:var(--green-dark)}
.hamburger-btn{background:none;border:none;font-size:22px;cursor:pointer;color:var(--text-dark);padding:4px;
display:flex;align-items:center;justify-content:center;border-radius:4px}
.hamburger-btn:hover{background:var(--cream)}
.header-nav{display:flex;align-items:center;gap:24px;justify-self:center}
.header-nav-link{font-size:14px;font-weight:700;color:var(--text-dark);text-decoration:none;
padding:6px 0;border-bottom:2px solid transparent;white-space:nowrap}
.header-nav-link:hover{color:var(--green-mid)}
.header-nav-link.active{color:var(--green-mid);border-bottom-color:var(--green-mid)}
.header-right-group{display:flex;align-items:center;gap:12px}
.header-avatar-btn{width:32px;height:32px;border-radius:50%;background:var(--cream);border:1px solid var(--border);
font-size:14px;display:flex;align-items:center;justify-content:center;text-decoration:none;overflow:hidden}
.header-avatar-btn img{width:100%;height:100%;object-fit:cover;border-radius:50%;display:block}

/* header language picker — same control the app pages show */
.km-hlang{position:relative}
.km-hlang-btn{display:flex;align-items:center;gap:5px;background:var(--cream);border:1px solid var(--border);
border-radius:16px;padding:5px 10px;cursor:pointer;font-family:var(--font-body);font-size:12.5px;font-weight:700;color:var(--text-dark);line-height:1}
.km-hlang-btn:hover{border-color:var(--green-light)}
.km-hlang-caret{font-size:9px;color:var(--text-soft)}
.km-hlang-menu{display:none;position:absolute;top:calc(100% + 6px);right:0;min-width:150px;background:var(--white);
border:1px solid var(--border);border-radius:12px;box-shadow:0 8px 24px rgba(20,40,30,.14);padding:5px;z-index:120;flex-direction:column;gap:2px}
.km-hlang-menu.open{display:flex}
.km-hlang-menu button{display:flex;align-items:center;gap:8px;text-align:left;background:none;border:none;border-radius:8px;
padding:8px 10px;font-family:var(--font-body);font-size:13px;font-weight:600;color:var(--text-dark);cursor:pointer}
.km-hlang-menu button:hover{background:var(--cream)}
.km-hlang-menu button.active{background:var(--green-pale);color:var(--green-dark);font-weight:800}
.km-hlang-code{display:inline-flex;align-items:center;justify-content:center;min-width:24px;height:20px;padding:0 4px;
border-radius:6px;background:var(--green-pale);color:var(--green-dark);font-size:11px;font-weight:800}

/* mobile hamburger drawer */
.sidebar-drawer-overlay{display:none;position:fixed;inset:0;background:rgba(15,23,20,.5);z-index:4000}
.sidebar-drawer-overlay.open{display:flex}
.sidebar-drawer{width:280px;max-width:84vw;background:var(--white);height:100%;box-shadow:6px 0 28px rgba(0,0,0,.18);
display:flex;flex-direction:column;animation:km-slide-right .2s cubic-bezier(.16,1,.3,1)}
@keyframes km-slide-right{from{transform:translateX(-100%)}to{transform:translateX(0)}}
.sidebar-drawer-header{padding:18px 16px 12px 20px;display:flex;align-items:center;justify-content:space-between}
.sidebar-drawer-title{font-size:17px;font-weight:800;color:var(--text-dark)}
.sidebar-drawer-close{background:var(--cream);border:none;font-size:15px;cursor:pointer;color:var(--text-mid);
width:32px;height:32px;border-radius:50%}
.sidebar-drawer-links{flex:1;padding:6px 12px;display:flex;flex-direction:column;gap:2px;overflow-y:auto}
.sidebar-drawer-link{display:flex;align-items:center;gap:13px;min-height:44px;padding:10px 12px;
font-size:14px;font-weight:700;color:var(--text-dark);text-decoration:none;border-radius:10px;border-left:3px solid transparent}
.sidebar-drawer-link-icon{font-size:18px;width:20px;text-align:center}
.sidebar-drawer-link:hover{background:var(--cream)}
.sidebar-drawer-link.active{background:var(--green-pale);color:var(--green-dark);border-left-color:var(--green-dark)}

/* full-page nav loading overlay — shown the instant a crop/state/district
tile or a hub-selector pick is clicked, since that's a real page load, not
an in-page swap; it needs its own visible "something is happening" moment */
.km-nav-loading{position:fixed;inset:0;background:rgba(245,247,244,.75);
z-index:9999;display:none;align-items:center;justify-content:center}
.km-nav-loading.show{display:flex}
.km-nav-spinner{width:38px;height:38px;border:4px solid var(--green-pale);
border-top-color:var(--green-mid);border-radius:50%;animation:km-nav-spin .7s linear infinite}
@keyframes km-nav-spin{to{transform:rotate(360deg)}}

/* blue commodity quick-nav — real <a href> crop links, not mandi.html's JS
   buttons, since Googlebot must see them without executing JS */
.commodity-navbar{background:#17268c}
.cnav-inner{display:flex;align-items:stretch;padding:0 20px;overflow-x:auto;scrollbar-width:none}
.cnav-inner::-webkit-scrollbar{display:none}
.cnav-item{color:rgba(255,255,255,.9);font-size:13px;font-weight:600;text-decoration:none;
padding:11px 14px;white-space:nowrap;display:inline-block}
.cnav-item:hover{background:rgba(255,255,255,.09);color:#fff}

@media(max-width:1024px){
.top-utility-bar{display:none}
/* Same three-slot phone header as mandi.html: hamburger pinned far-left,
logo centered in the space between, avatar far-right. Without the explicit
order/flex the grid collapses to a plain flex row and all three bunch up on
the left with dead space to the right. */
.main-header-inner{display:flex;gap:14px;padding:10px 12px;align-items:center}
.main-header-inner>.hamburger-btn{order:1;flex:0 0 auto}
.main-header-inner>.header-left-group{order:2;flex:1 1 auto;display:flex;justify-content:center}
.main-header-inner>.header-right-group{order:3;flex:0 0 auto}
.main-header .header-nav{display:none}
.header-logo-text{font-size:17px}
.commodity-navbar{position:static}
}

/* ── breadcrumbs ── */
.crumbs{max-width:980px;margin:0 auto;padding:12px 20px 0;font-size:12px;color:var(--text-soft)}
.crumbs a{color:var(--green-mid);text-decoration:none;font-weight:600}
.crumbs a:hover{text-decoration:underline}

/* ── hero (crop photo) ── */
.hero{position:relative;margin:12px 0 16px;border-radius:var(--radius-md);overflow:hidden;
border:1px solid var(--border);box-shadow:var(--shadow-sm);background:linear-gradient(120deg,var(--green-dark),var(--green-mid))}
.hero-img{width:100%;height:200px;object-fit:cover;display:block}
.hero-body{position:absolute;inset:0;display:flex;flex-direction:column;justify-content:flex-end;
padding:18px 20px;background:linear-gradient(180deg,rgba(26,60,46,.10) 0%,rgba(26,60,46,.55) 55%,rgba(26,60,46,.90) 100%)}
.hero.nophoto{min-height:150px}
.hero.nophoto .hero-body{position:static;min-height:150px}
h1{font-family:var(--font-serif);font-size:25px;font-weight:700;color:var(--white);line-height:1.3}
.hero-sub{font-size:12.5px;color:rgba(255,255,255,.82);margin-top:6px;font-weight:500}
.hero-pill{position:absolute;top:14px;right:14px;display:inline-flex;align-items:center;gap:6px;
background:rgba(255,255,255,.16);border:1px solid rgba(255,255,255,.28);color:var(--white);
font-size:11px;font-weight:700;padding:5px 11px;border-radius:20px}
.hero-dot{width:7px;height:7px;border-radius:50%;background:#6ee7a8}

/* ── controls: change crop / state / mandi without leaving the page ── */
.ctl{display:flex;gap:10px;margin:14px 0;flex-wrap:wrap}
.ctl-f{position:relative;flex:1;min-width:150px;display:flex;flex-direction:column;gap:4px;
background:var(--white);border:1px solid var(--border);border-radius:var(--radius-sm);
padding:8px 12px;box-shadow:var(--shadow-sm)}
.ctl-f span{font-size:10.5px;font-weight:700;color:var(--text-soft);
text-transform:uppercase;letter-spacing:.4px}
.ctl-f select{appearance:none;border:0;background:transparent;width:100%;
font-family:var(--font-body);font-size:15px;font-weight:700;color:var(--green-dark);
padding-right:18px;cursor:pointer;outline:none;
background-image:linear-gradient(45deg,transparent 50%,var(--green-mid) 50%),
linear-gradient(135deg,var(--green-mid) 50%,transparent 50%);
background-position:right 6px top 9px,right 1px top 9px;
background-size:5px 5px,5px 5px;background-repeat:no-repeat}
/* type-to-filter fields (hub quick-jump) — same look as .ctl-f select above */
.ctl-f input{border:0;background:transparent;width:100%;min-width:0;
font-family:var(--font-body);font-size:15px;font-weight:700;color:var(--green-dark);outline:none}
.ctl-f input::placeholder{color:var(--text-soft);font-weight:600;font-size:13px}
.ctl-input-row{display:flex;align-items:center;gap:6px}
/* simple flat 2D mic icon — same look as mandi.html's .mn-mic-btn, no filled
circle, just an outline glyph that lights up on hover/while listening */
.ctl-mic{flex-shrink:0;background:none;border:none;padding:4px;cursor:pointer;
color:var(--text-mid);opacity:.6;border-radius:50%;line-height:1;
display:flex;align-items:center;justify-content:center;transition:opacity .15s,background .15s}
.ctl-mic:hover{opacity:1;background:var(--cream)}
.ctl-mic.listening{opacity:1;color:#e53935;animation:ctl-mic-pulse .7s ease-in-out infinite alternate}
@keyframes ctl-mic-pulse{from{opacity:.7}to{opacity:1}}
/* type-then-pick results list — must select a real match to proceed, same
UX contract as mandi.html's .mn-combo-list (no navigating on free-typed text) */
.ctl-list{position:absolute;top:calc(100% + 4px);left:0;right:0;background:var(--white);
border:1px solid var(--border);border-radius:var(--radius-sm);box-shadow:var(--shadow-md);
max-height:220px;overflow-y:auto;z-index:50;display:none;list-style:none;margin:0;padding:4px}
.ctl-list.open{display:block}
.ctl-list li{padding:9px 12px;font-size:14px;color:var(--text-dark);cursor:pointer;border-radius:8px}
.ctl-list li:hover,.ctl-list li.focused{background:var(--green-pale);color:var(--green-dark)}
.ctl-list .ctl-no-results{color:var(--text-soft);cursor:default}
.ctl-list .ctl-no-results:hover{background:none}
/* Phone widths: 3×150px min-width fields don't fit two-plus-a-sliver on one
line without the third getting clipped at the screen edge — stack one per
row instead of relying on flex-wrap to break the line cleanly. */
@media(max-width:640px){
.ctl{flex-direction:column}
.ctl-f{min-width:0;width:100%}
}

/* ── the answer: the number the farmer came for, first ── */
.answer{position:relative;overflow:hidden;border-radius:var(--radius-md);
background:linear-gradient(120deg,var(--green-dark),var(--green-mid));
color:var(--white);padding:22px 24px;box-shadow:var(--shadow-md)}
.answer-photo{position:absolute;top:0;right:0;width:42%;height:100%;object-fit:cover;
opacity:.5;-webkit-mask-image:linear-gradient(90deg,transparent,#000 65%);
mask-image:linear-gradient(90deg,transparent,#000 65%)}
.answer-in{position:relative;z-index:1;max-width:640px}
.answer h1{font-size:23px}
.answer-sub{font-size:12.5px;color:rgba(255,255,255,.78);margin-top:5px;font-weight:500}
.answer-price{display:flex;align-items:baseline;flex-wrap:wrap;gap:12px;margin-top:16px}
.answer-rupee{font-size:46px;font-weight:700;letter-spacing:-1.5px;line-height:1}
.answer-rupee small{font-size:15px;font-weight:600;letter-spacing:0;
color:rgba(255,255,255,.72);margin-left:3px}
.answer-delta{font-size:13px;font-weight:700;padding:5px 12px;border-radius:20px;
background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.22)}
.answer-delta.up{color:#8ef0b4}
.answer-delta.dn{color:#ffb3a7}
.answer-range{display:flex;flex-wrap:wrap;gap:22px;margin-top:18px;
border-top:1px solid rgba(255,255,255,.16);padding-top:14px}
.answer-range div span{display:block;font-size:10.5px;font-weight:700;
color:rgba(255,255,255,.62);text-transform:uppercase;letter-spacing:.4px}
.answer-range div b{font-size:17px;font-weight:700}
/* WhatsApp share pill inside the price card — mirrors mandi.html's share action */
.answer-share{display:inline-flex;align-items:center;gap:8px;margin-top:16px;
background:#25d366;color:#fff;border:none;cursor:pointer;font-family:var(--font-body);
font-size:14px;font-weight:700;padding:11px 20px;border-radius:24px;
box-shadow:0 2px 10px rgba(0,0,0,.18);transition:background .15s,transform .15s}
.answer-share:hover{background:#1eb958;transform:translateY(-1px)}
.answer-share:active{transform:translateY(0)}
.answer-share svg{width:18px;height:18px;flex-shrink:0}
@media(max-width:640px){.answer-photo{opacity:.22;width:100%;
-webkit-mask-image:linear-gradient(90deg,transparent,#000 90%);
mask-image:linear-gradient(90deg,transparent,#000 90%)}
.answer-rupee{font-size:38px}h1{font-size:20px}.answer h1{font-size:20px}}

/* ── "sell here instead": the one thing a price table never tells you ── */
.better{background:var(--white);border:1px solid var(--border);border-left:4px solid var(--amber);
border-radius:var(--radius-md);padding:15px 18px;box-shadow:var(--shadow-sm);margin-top:16px}
.better h2{margin:0 0 4px}
.better-sub{font-size:11.5px;color:var(--text-soft);margin-bottom:10px}
.better ul{list-style:none;margin-top:10px}
.better li{display:block;padding:0;border:none;margin-bottom:10px}
.better li:last-child{margin-bottom:0}
.better-mandi-card {
  background: var(--white);
  border: 1px solid var(--border);
  border-radius: 16px;
  box-shadow: 0 2px 10px rgba(26,60,46,.04);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 18px;
  text-decoration: none;
  color: inherit;
  transition: all 0.2s ease;
  border-right: 5px solid var(--green-mid);
  width: 100%;
  max-width: 480px;
}
.better-mandi-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 18px rgba(26,60,46,.08);
  border-color: var(--green-light);
}
.bmc-details {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.bmc-market {
  font-size: 15px;
  font-weight: 700;
  color: var(--green-dark);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.bmc-meta {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--text-soft);
}
.bmc-action {
  font-size: 13px;
  font-weight: 700;
  color: var(--green-mid);
  white-space: nowrap;
  margin-left: 12px;
}
.better.flat{border-left-color:var(--green-light)}
.better-message {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--text-mid);
  margin-top: 6px;
  line-height: 1.5;
}

/* ── trend chart ── */
.card-w{background:var(--white);border:1px solid var(--border);border-radius:var(--radius-md);
padding:16px 18px;box-shadow:var(--shadow-sm);margin-top:16px}
.card-w-h{display:flex;align-items:baseline;justify-content:space-between;gap:10px;margin-bottom:6px}
.card-w-h h2{margin:0}
.card-w-h em{font-style:normal;font-size:11.5px;font-weight:600;color:var(--text-soft)}
svg.chart{display:block;width:100%;height:auto}

/* ── mandi-wise cards ── */
.mkts{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:12px}
.mkt{background:var(--white);border:1px solid var(--border);border-radius:var(--radius-sm);
padding:13px 15px;box-shadow:var(--shadow-sm)}
.mkt-name{font-size:14px;font-weight:700;color:var(--text-dark)}
.mkt-var{font-size:11px;font-weight:600;color:var(--text-soft);margin-top:1px}
.mkt-price{display:flex;align-items:center;gap:8px;margin:9px 0 7px}
.mkt-price b{font-size:21px;font-weight:700;color:var(--green-dark);letter-spacing:-.4px}
.mkt-price small{font-size:11px;font-weight:600;color:var(--text-soft)}
.mkt-foot{display:flex;align-items:center;justify-content:space-between;gap:8px;
border-top:1px solid var(--border);padding-top:8px}
.mkt-range{font-size:11.5px;color:var(--text-mid);font-weight:600}
.up{color:#1b7a3d;font-size:11.5px;font-weight:700}
.dn{color:#c0392b;font-size:11.5px;font-weight:700}
svg.spark{vertical-align:middle;flex-shrink:0}
.note{font-size:11.5px;color:var(--text-soft);margin-top:10px}

/* ── CTAs ── */
.cta-row{display:flex;gap:10px;flex-wrap:wrap;margin:18px 0}
.btn{display:inline-flex;align-items:center;gap:8px;font-family:var(--font-body);font-size:14px;
font-weight:700;padding:12px 22px;border-radius:26px;text-decoration:none;transition:background .15s,transform .15s}
.btn:hover{transform:translateY(-1px)}
.btn-app{background:var(--green-mid);color:var(--white);box-shadow:var(--shadow-sm)}
.btn-app:hover{background:var(--green-dark)}
.btn-wa{background:#25d366;color:var(--white);box-shadow:var(--shadow-sm)}
.btn-wa:hover{background:#1eb958}

/* on-page search — same look as shop.html's search bar: icon inset at the
left of a rounded input. Still a plain GET form (no JS) so it works and is
crawlable without the app's JS bundle — the icon doubles as the submit. */
.hub-filter-row{display:flex;align-items:center;gap:10px;margin:18px 0;flex-wrap:wrap}
.hub-search{position:relative;flex:1;min-width:220px}
.hub-search input{width:100%;padding:10px 16px 10px 38px;border-radius:12px;
border:1.5px solid var(--border);background:var(--white);font-family:var(--font-body);
font-size:14px;color:var(--text-dark);outline:none;box-shadow:var(--shadow-sm);
transition:border-color .15s}
.hub-search input:focus{border-color:var(--green-mid)}
.hub-search input::placeholder{color:var(--text-soft)}
.hub-search button{position:absolute;left:12px;top:50%;transform:translateY(-50%);
background:none;border:0;cursor:pointer;font-size:15px;padding:0;color:var(--text-mid);
opacity:.6;display:flex;align-items:center}
.hub-search button:hover{opacity:1}
.hub-filter-btn{display:inline-flex;align-items:center;gap:5px;background:var(--white);
border:1.5px solid var(--border);border-radius:20px;padding:8px 16px;font-size:13px;
font-weight:600;color:var(--text-mid);text-decoration:none;transition:all .18s;
box-shadow:var(--shadow-sm);white-space:nowrap}
.hub-filter-btn:hover{border-color:var(--green-light);color:var(--green-mid)}

/* ── headings, chips, FAQ ── */
h2{font-family:var(--font-serif);font-size:18px;font-weight:700;color:var(--green-dark);margin:24px 0 10px}
.chips{display:flex;flex-wrap:wrap;gap:8px}
.chip{display:inline-flex;align-items:center;gap:8px;background:var(--white);border:1px solid var(--border);
border-radius:26px;padding:5px 15px 5px 5px;text-decoration:none;color:var(--text-dark);
font-size:13px;font-weight:600;box-shadow:var(--shadow-sm);transition:border-color .15s,color .15s}
.chip:hover{border-color:var(--green-light);color:var(--green-dark)}
.chip img{width:28px;height:28px;border-radius:50%;object-fit:cover;flex-shrink:0}
.chip .ico{width:28px;height:28px;border-radius:50%;background:var(--green-pale);
display:grid;place-items:center;font-size:13px;flex-shrink:0}
.faq{background:var(--white);border:1px solid var(--border);border-radius:var(--radius-sm);
padding:14px 16px;margin:8px 0;box-shadow:var(--shadow-sm)}
.faq h3{font-size:14px;font-weight:700;color:var(--text-dark);margin-bottom:4px}
.faq p{font-size:13px;color:var(--text-mid)}

/* ── crop cards (hub) ── */
.crop-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:16px;margin-top:16px}
.crop-card{background:var(--white);border:1px solid var(--border);border-radius:var(--radius-md);
overflow:hidden;box-shadow:var(--shadow-sm);text-decoration:none;color:inherit;display:block;
transition:transform .15s,box-shadow .15s,border-color .15s}
.crop-card:hover{transform:translateY(-2px);box-shadow:var(--shadow-md);border-color:var(--green-light)}
.crop-card-photo{position:relative;height:120px;background:linear-gradient(120deg,var(--green-dark),var(--green-mid))}
.crop-card-photo img{width:100%;height:120px;object-fit:cover;display:block}
.crop-card-name{position:absolute;left:0;right:0;bottom:0;padding:16px 14px 10px;
background:linear-gradient(180deg,rgba(26,60,46,0),rgba(26,60,46,.85));
font-family:var(--font-serif);font-size:17px;font-weight:700;color:var(--white)}
.crop-card-en{display:block;font-family:var(--font-body);font-size:11px;font-weight:600;
color:rgba(255,255,255,.72);margin-top:1px}
/* no photo for this crop → compact band instead of an empty slab of green */
.crop-card-photo.noimg{height:auto;padding:12px 14px}
.crop-card-photo.noimg .crop-card-name{position:static;padding:0;background:none}
.crop-card-body{padding:12px 14px 14px;display:flex;align-items:baseline;justify-content:space-between;gap:8px}
.crop-card-body .lbl{font-size:10.5px;font-weight:700;color:var(--text-soft);
text-transform:uppercase;letter-spacing:.4px}
.crop-card-body .rate{font-size:15px;font-weight:700;color:var(--green-dark);white-space:nowrap}
.dlinks{display:flex;flex-wrap:wrap;gap:5px}
.dlinks a{font-size:12px;font-weight:600;color:var(--green-mid);text-decoration:none;
background:var(--cream);border:1px solid var(--border);border-radius:14px;padding:3px 10px}
.dlinks a:hover{background:var(--green-pale);color:var(--green-dark)}

/* ── state place-cards — premium map card layout ── */
.place-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
  margin-top: 16px;
}
@media (max-width: 900px) {
  .place-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
@media (max-width: 600px) {
  .place-grid {
    grid-template-columns: 1fr;
  }
}

.place {
  background: var(--white);
  border: 1.5px solid var(--border);
  border-radius: 16px;
  box-shadow: 0 4px 12px rgba(26,60,46,.04);
  text-decoration: none;
  color: inherit;
  display: flex;
  align-items: stretch;
  overflow: hidden;
  padding: 0;
  transition: transform .2s, box-shadow .2s, border-color .2s;
  min-height: 120px;
  border-right: 6px solid var(--green-mid);
}
.place:hover {
  transform: translateY(-3px);
  box-shadow: 0 8px 24px rgba(26,60,46,.1);
  border-color: var(--green-light);
}

/* Left panel: map + watercolor blob + separator */
.place-map-panel {
  flex-shrink: 0;
  width: 42%;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 10px;
  border-right: 1.5px dotted #cdd8cd;
}
.place-map-blob {
  position: absolute;
  inset: 0;
  background: radial-gradient(circle, rgba(139,195,74,0.3) 0%, rgba(205,220,57,0.15) 50%, transparent 75%);
  pointer-events: none;
}
.place-map-svg {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 100px;
  height: 80px;
  object-fit: contain;
  filter: drop-shadow(0 4px 6px rgba(0,0,0,0.06));
}

/* Right panel: info */
.place-info {
  flex: 1;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 5px;
  position: relative;
  min-width: 0;
}

/* Leaf Watermark in Background */
.place-deco-svg {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 50px;
  height: 50px;
  pointer-events: none;
}

.place-n {
  font-family: var(--font-serif);
  font-size: 18px;
  font-weight: 700;
  color: #1a3c2e;
  line-height: 1.1;
}

/* Divider with Leaf Ornament */
.place-divider-wrap {
  display: flex;
  align-items: center;
  gap: 5px;
  margin: 1px 0;
}
.place-line {
  height: 1.5px;
  background: var(--green-light);
  flex: 1;
  max-width: 35px;
}
.place-ornament {
  font-size: 10px;
  line-height: 1;
  color: var(--green-mid);
}

.place-en {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--text-soft);
  margin-top: -2px;
}

/* District box with custom circle pin */
.place-dist-box {
  display: flex;
  align-items: center;
  gap: 8px;
  background: #f3f9f4;
  border: 1px solid #e2f0e5;
  border-radius: 10px;
  padding: 4px 8px;
  width: fit-content;
  margin: 1px 0;
}
.place-dist-pin-wrap {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: #eaf2ec;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.place-dist-pin {
  display: flex;
  align-items: center;
  justify-content: center;
}
.place-dist-text {
  display: flex;
  align-items: baseline;
  gap: 4px;
  line-height: 1;
}
.place-dist-num {
  font-size: 13.5px;
  font-weight: 800;
  color: #1a3c2e;
}
.place-dist-lbl {
  font-size: 10.5px;
  font-weight: 600;
  color: #4a5a52;
}

/* Segmented button pill */
.place-btn-pill {
  display: flex;
  align-items: center;
  background: var(--white);
  border: 1.5px solid #d0dfd4;
  border-radius: 12px;
  overflow: hidden;
  width: 100%;
  max-width: 145px;
  height: 28px;
  margin-top: 3px;
  transition: all 0.2s ease;
}
.place-btn-left {
  padding: 0 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--green-mid);
  font-size: 11px;
}
.place-btn-divider {
  width: 1px;
  height: 14px;
  background: #d0dfd4;
}
.place-btn-right {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 8px;
  font-size: 11.5px;
  font-weight: 700;
  color: #1a3c2e;
}
.place:hover .place-btn-pill {
  border-color: var(--green-mid);
  background: #f3f9f4;
}
.place:hover .place-btn-divider {
  background: var(--green-mid);
}
.place-btn-arrow {
  transition: transform 0.2s;
}
.place:hover .place-btn-arrow {
  transform: translateX(3px);
}

/* ── site footer ── */
.km-footer{background:var(--green-dark);color:rgba(255,255,255,.7);margin-top:32px;padding:24px 20px}
.km-footer-inner{max-width:980px;margin:0 auto;display:flex;flex-wrap:wrap;gap:14px;
justify-content:space-between;align-items:center;font-size:12.5px}
.km-footer-brand{font-family:var(--font-serif);font-size:15px;font-weight:700;color:var(--white)}
.km-footer-nav{display:flex;flex-wrap:wrap;gap:14px}
.km-footer a{color:rgba(255,255,255,.85);text-decoration:none;font-weight:600}
.km-footer a:hover{color:var(--white);text-decoration:underline}
.km-footer-note{width:100%;font-size:11.5px;color:rgba(255,255,255,.55);
border-top:1px solid rgba(255,255,255,.12);padding-top:12px}
"""

_FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
          '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
          '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
          'family=DM+Sans:wght@400;500;700&family=Noto+Serif+Devanagari:wght@600;700&display=swap">')

_ICON = f'<link rel="icon" href="{SITE}/assets/krashimitra_logo.png" type="image/png">'


_NAV_ITEMS = [("bhav", f"{SITE}/bhav", "मंडी भाव"),
              ("bazar", f"{SITE}/krashi_bajar", "कृषि बाज़ार"),
              ("weather", f"{SITE}/weather", "मौसम देखें"),
              ("shop", f"{SITE}/product/", "कृषि दुकान")]

_DRAWER_ITEMS = [("home", f"{SITE}/", "🏠", "मुख्य"),
                  ("weather", f"{SITE}/weather", "🌤️", "मौसम"),
                  ("mandi", f"{SITE}/mandi", "🏪", "मंडी भाव"),
                  ("bhav", f"{SITE}/bhav", "📈", "सभी भाव सूची"),
                  ("bazar", f"{SITE}/krashi_bajar", "🧺", "कृषि बाज़ार"),
                  ("shop", f"{SITE}/shop", "🛒", "दुकान"),
                  ("khoj", f"{SITE}/khoj", "🔍", "कृषि खोज"),
                  ("map", f"{SITE}/map", "🗺️", "कृषि मानचित्र"),
                  ("articles", f"{SITE}/articles/", "📰", "कृषि लेख"),
                  ("yojana", f"{SITE}/sarkari_yojana", "🏛️", "सरकारी योजना"),
                  ("chat", f"{SITE}/chat", "💬", "AI सहायता")]

_NAVBAR_CROPS_N = 10  # top N by _TILES rank — same curated set mandi.html shows


def _quicknav() -> str:
    """The blue bar's crop links, built from the live DB index rather than a
    hardcoded list, so a crop that drops out of the feed never links to a 404 —
    and every one of the ~10,000 /bhav + /product pages carries this many real
    <a href> links into the /bhav tree (see the JS-only-link indexation gap
    this was built to close)."""
    idx = _get_index()
    # Several DB commodities can share one _TILES rank (Wheat + Wheat Atta both
    # land on the wheat tile) — one slot per rank, keeping whichever commodity
    # is reported across the most states as the canonical, non-niche one.
    by_rank: dict[int, tuple[str, str, int]] = {}
    for cs, cn in idx.get("crops", {}).items():
        if not _is_crop(cn):
            continue
        r = _tile_rank(cn)
        if r >= _NAVBAR_CROPS_N:
            continue
        n_states = len(idx.get("states", {}).get(cs, {}))
        if r not in by_rank or n_states > by_rank[r][2]:
            by_rank[r] = (cs, cn, n_states)
    ranked = [by_rank[r][:2] for r in sorted(by_rank)]
    items = "".join(
        f'<a class="cnav-item" href="/bhav/{cs}">{escape(_hindi_name(cn))} की कीमत</a>'
        for cs, cn in ranked)
    return f"""<div class="commodity-navbar"><div class="cnav-inner">
<a class="cnav-item" href="{SITE}/bhav">बाज़ार भाव</a>{items}
</div></div>"""


def _header(active: str = "") -> str:
    """Same pre-topbar/topbar/main-header/blue-bar stack as mandi.html, so a
    page reached from Google reads as the same product as the app, not a
    stripped-down doorway. Hamburger drawer uses a couple of inline onclick
    handlers rather than the app's JS bundle — these pages must stay light."""
    nav = "".join(
        f'<a class="header-nav-link{" active" if key == active else ""}" href="{href}">{label}</a>'
        for key, href, label in _NAV_ITEMS)
    drawer = "".join(
        f'<a href="{href}" class="sidebar-drawer-link{" active" if key == active else ""}">'
        f'<span class="sidebar-drawer-link-icon">{icon}</span><span>{label}</span></a>'
        for key, href, icon, label in _DRAWER_ITEMS)
    return f"""<div class="header-wrapper" id="header-wrapper">
<div class="pre-topbar">
<a href="tel:+919870951001" class="pre-topbar-helpline"><span class="pre-topbar-phone-icon">📞</span> कृषिमित्र हेल्पलाइन: +91 9870951001</a>
</div>
<div class="top-utility-bar"><div class="top-utility-inner">
<div class="top-utility-left">
<a href="{SITE}/" class="top-utility-link">मुख्य</a><span class="top-utility-divider">|</span>
<a href="{SITE}/map" class="top-utility-link">कृषि मानचित्र</a><span class="top-utility-divider">|</span>
<a href="{SITE}/articles/" class="top-utility-link">कृषि समाचार</a><span class="top-utility-divider">|</span>
<a href="{SITE}/sarkari_yojana" class="top-utility-link">सरकारी योजना</a>
</div>
<div class="top-utility-right">
<a href="tel:+919870951001" class="top-utility-helpline"><span class="pre-topbar-phone-icon">📞</span> कृषिमित्र हेल्पलाइन: +91 9870951001</a>
<span class="top-utility-divider">|</span>
<a href="{SITE}/chat" class="top-utility-link">संपर्क</a>
</div>
</div></div>
<header class="main-header"><div class="main-header-inner">
<button class="hamburger-btn" onclick="document.getElementById('km-drawer').classList.add('open')" aria-label="Menu">☰</button>
<div class="header-left-group">
<a class="header-logo-link" href="{SITE}/">
<img src="{SITE}/assets/krashimitra_logo.png" alt="कृषि मित्र" class="header-logo-circle" width="38" height="38">
<span class="header-logo-text">कृषि मित्र</span></a>
</div>
<nav class="header-nav">{nav}</nav>
<div class="header-right-group">
<div class="km-hlang" id="km-hlang">
<button class="km-hlang-btn" type="button" aria-label="भाषा"><span class="km-hlang-cur">हिं</span><span class="km-hlang-caret">▾</span></button>
<div class="km-hlang-menu">
<button data-lang="hi"><span class="km-hlang-code">हिं</span>हिंदी</button>
<button data-lang="en"><span class="km-hlang-code">EN</span>English</button>
<button data-lang="kn"><span class="km-hlang-code">ಕ</span>ಕನ್ನಡ</button>
</div>
</div>
<a href="{SITE}/login" class="header-avatar-btn" id="header-avatar-btn">👤</a></div>
</div></header>
{_quicknav()}
</div><!-- /.header-wrapper -->
<div class="sidebar-drawer-overlay" id="km-drawer" onclick="this.classList.remove('open')">
<div class="sidebar-drawer" onclick="event.stopPropagation()">
<div class="sidebar-drawer-header"><span class="sidebar-drawer-title">मेनु</span>
<button class="sidebar-drawer-close" onclick="document.getElementById('km-drawer').classList.remove('open')" aria-label="Close menu">✕</button></div>
<div class="sidebar-drawer-links">{drawer}</div>
</div></div>
<div class="km-nav-loading" id="km-nav-loading" aria-hidden="true"><div class="km-nav-spinner"></div></div>
<script>
/* Instant feedback on any internal navigation — picking a crop/state/district
tile, a hub-selector suggestion, or any other same-page link — since the
click itself only *starts* a real page load; without this the farmer sees
nothing happen for however long that takes. */
(function(){{
var ov=document.getElementById('km-nav-loading');
window.kmShowLoading=function(){{if(ov)ov.classList.add('show');}};
document.addEventListener('click',function(e){{
var a=e.target.closest('a');
if(!a||!a.href)return;
if(a.target&&a.target!=='_self')return;
var url;
try{{url=new URL(a.href,location.href);}}catch(err){{return;}}
if(url.origin!==location.origin)return;
if(url.pathname===location.pathname&&url.hash)return; // in-page anchor jump
window.kmShowLoading();
}},true);
}})();
</script>
<script src="/api-config.js"></script>
<script src="/drawer-menu.js" defer></script>
<script src="/bottomnav.js" defer></script>
<div class="topbar-spacer" id="topbar-spacer"></div>
<script src="/header-scroll.js"></script>"""


def _footer() -> str:
    return f"""<footer class="km-footer"><div class="km-footer-inner">
<div class="km-footer-brand">🌾 कृषि मित्र</div>
<nav class="km-footer-nav">
<a href="{SITE}/">होम</a>
<a href="{SITE}/mandi">मंडी ऐप</a>
<a href="{SITE}/bhav">सभी भाव</a>
<a href="{SITE}/weather">मौसम</a>
<a href="{SITE}/chat">AI सहायक</a>
</nav>
<div class="km-footer-note">भाव भारत सरकार के data.gov.in (Agmarknet) से रोज़ अपडेट होते हैं।
बेचने से पहले अपनी मंडी में भाव ज़रूर पुष्टि करें।</div>
</div></footer>"""


def _doc(title: str, desc: str, canon: str, crumbs: str, body: str,
         ld: str = "", og_img: str = "", active: str = "bhav",
         extra_css: str = "") -> HTMLResponse:
    """One page shell for all four tiers — head, header, crumbs, body, footer.
    `active` defaults to "bhav" for this module's own pages; other SEO routes
    (e.g. product.py) that reuse this shell pass their own nav key/"" so they
    don't show up with भाव wrongly highlighted. `extra_css` lets those callers
    layer on rules of their own without duplicating the tokens/header/footer —
    _CSS here is this module's own, so a caller's local override of a same-named
    variable is invisible to this closure; extra_css is the only way in."""
    og = og_img or f"{SITE}/images/og-banner.webp"
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="hi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title>
<meta name="description" content="{escape(desc)}">
<link rel="canonical" href="{canon}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="कृषि मित्र (KrashiMitra)">
<meta property="og:title" content="{escape(title)}">
<meta property="og:description" content="{escape(desc)}">
<meta property="og:image" content="{escape(og)}">
<meta property="og:url" content="{canon}">
<meta property="og:locale" content="hi_IN">
<meta name="twitter:card" content="summary_large_image">
{_ICON}
{_FONTS}
{ld}
<style>{_CSS}{extra_css}</style>
</head>
<body>
{_header(active)}
<nav class="crumbs">{crumbs}</nav>
<div class="wrap">
{body}
</div>
{_footer()}
</body>
</html>""", headers={"Cache-Control": "public, max-age=3600"})


def _faq(faqs: list[tuple[str, str]]) -> tuple[str, dict]:
    """Visible markup AND the JSON-LD come from this ONE list, so the two can never
    drift apart (a past bug on other pages: 3 declared, 8 shown)."""
    html = "\n".join(
        f'<div class="faq"><h3>{escape(q)}</h3><p>{escape(a)}</p></div>' for q, a in faqs)
    ld = {"@context": "https://schema.org", "@type": "FAQPage",
          "mainEntity": [{"@type": "Question", "name": q,
                          "acceptedAnswer": {"@type": "Answer", "text": a}}
                         for q, a in faqs]}
    return html, ld


def _crumb_ld(trail: list[tuple[str, str]]) -> dict:
    return {"@context": "https://schema.org", "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": i + 1, "name": n, "item": u}
                for i, (n, u) in enumerate(trail)]}


def _ld(*blocks) -> str:
    return "\n".join(
        f'<script type="application/ld+json">{_json.dumps(b, ensure_ascii=False)}</script>'
        for b in blocks)


def _not_found() -> HTMLResponse:
    """A crop can drop out of the feed (mandi stops reporting) while Google still
    holds the URL — send that farmer into the app instead of a dead end."""
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="hi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>यह भाव पेज उपलब्ध नहीं है | कृषि मित्र</title>
<meta name="robots" content="noindex">
{_ICON}
{_FONTS}
<style>{_CSS}</style>
</head>
<body>
{_header("bhav")}
<div class="wrap">
<div class="hero nophoto">
<div class="hero-body">
<h1>यह भाव पेज अभी उपलब्ध नहीं है</h1>
<p class="hero-sub">हो सकता है इस मंडी ने हाल में इस फसल की रिपोर्ट न भेजी हो।</p>
</div>
</div>
<div class="cta-row">
<a class="btn btn-app" href="{SITE}/bhav">सभी मंडी भाव देखें</a>
<a class="btn btn-wa" href="{SITE}/mandi" style="background:var(--green-dark)">📊 मंडी ऐप खोलें</a>
</div>
</div>
{_footer()}
</body>
</html>""", status_code=404)


def _app_url(commodity: str, district: str = "", state: str = "") -> str:
    """Deep link into the mandi app on the SAME crop/district/state the farmer is reading.
    State matters: mandi.html filters districts within the selected state, so without it
    the district filter silently misses."""
    params = {"commodity": commodity}
    if district and district != "-":
        params["district"] = district
    if state and state != "-":
        params["state"] = state
    return f"{SITE}/mandi?{urlencode(params)}"


def _switchers(c_slug: str, s_slug: str, d_slug: str) -> str:
    """Change crop / state / mandi without leaving the page.

    Every option is a combo that really exists in the snapshot — the crop list is
    scoped to this district, the district list to this crop AND state — so a switch
    can never land on a 404. Without JS the selects do nothing, which is why the
    chip links below stay: they are the crawlable, no-JS path to the same pages."""
    idx = _get_index()

    crops = sorted(
        ((cs, cn) for cs, cn in idx["crops"].items()
         if _is_crop(cn) and d_slug in idx["dists"].get(cs, {}).get(s_slug, {})),
        key=lambda x: (_tile_rank(x[1]), _hindi_name(x[1])))
    states = sorted(idx["states"].get(c_slug, {}).items(), key=lambda kv: kv[1])
    dists  = sorted(idx["dists"].get(c_slug, {}).get(s_slug, {}).items(),
                    key=lambda kv: kv[1])

    crop_opts = "".join(
        f'<option value="/bhav/{cs}/{s_slug}/{d_slug}"{" selected" if cs == c_slug else ""}>'
        f'{escape(_hindi_name(cn))}</option>' for cs, cn in crops)
    # Switching state can't keep the district, so it lands on the state tier.
    state_opts = "".join(
        f'<option value="/bhav/{c_slug}/{ss}"{" selected" if ss == s_slug else ""}>'
        f'{escape(_hindi_state(sn))}</option>' for ss, sn in states)
    dist_opts = "".join(
        f'<option value="/bhav/{c_slug}/{s_slug}/{ds}"{" selected" if ds == d_slug else ""}>'
        f'{escape(dn)}</option>' for ds, dn in dists)

    return f"""<div class="ctl">
<label class="ctl-f"><span>फसल</span>
<select onchange="if(this.value)location.href=this.value" aria-label="फसल चुनें">{crop_opts}</select></label>
<label class="ctl-f"><span>राज्य</span>
<select onchange="if(this.value)location.href=this.value" aria-label="राज्य चुनें">{state_opts}</select></label>
<label class="ctl-f"><span>मंडी / जिला</span>
<select onchange="if(this.value)location.href=this.value" aria-label="जिला चुनें">{dist_opts}</select></label>
</div>"""


def _hub_selector(cs: str, ss: str, ds: str, idx: dict,
                   known_crop: bool = False, known_state: bool = False) -> str:
    """Same crop/state/district quick-jump as _switchers(), but a type-or-speak
    <input list=datalist> instead of a plain <select> — the hub's district list
    can run to 60+ entries, too many to scan by scrolling on a first visit.
    Kept separate from _switchers() (used on tier-4 pages, where each field is
    already resolved, not picked from scratch) so that one keeps its plain,
    no-JS-safe <select> untouched.

    फसल's options go to /bhav/{crop} (tier 2), NOT /bhav/{crop}/{ss}/{ds} — the
    seed state/district are one crop's, and most other crops aren't reported in
    that exact district, so combining them would 404 for most choices. राज्य and
    मंडी/जिला stay scoped to the seed crop (idx only ever holds real combos), so
    picking those two always lands on a real page.

    known_crop/known_state: on tier-2/3 pages cs/ss are the REAL crop/state the
    URL is already on (not just a scoring seed like on the hub), so those fields
    should show it as picked rather than an empty "चुनें" placeholder — this is
    what tells a visitor the field they're looking at already matches the page."""
    cur_crop = _hindi_name(idx["crops"].get(cs, "")) if known_crop else ""
    cur_state = _hindi_state(idx["states"].get(cs, {}).get(ss, "")) if known_state else ""

    crops = sorted(
        ((c, cn) for c, cn in idx["crops"].items() if _is_crop(cn)),
        key=lambda x: (_tile_rank(x[1]), _hindi_name(x[1])))
    states = sorted(idx["states"].get(cs, {}).items(), key=lambda kv: kv[1])
    dists = sorted(idx["dists"].get(cs, {}).get(ss, {}).items(), key=lambda kv: kv[1])

    crop_map = {_hindi_name(cn): f"/bhav/{c}" for c, cn in crops}
    state_map = {_hindi_state(sn): f"/bhav/{cs}/{s}" for s, sn in states}
    dist_map = {dn: f"/bhav/{cs}/{ss}/{d}" for d, dn in dists}
    # English synonyms, keyed by the same Hindi label used above, purely for
    # search — so typing "wheat" finds गेहूं just like typing "गेहूं" does.
    # The Hindi label stays the one thing that's shown, stored and navigated on.
    crop_alt = {_hindi_name(cn): cn for c, cn in crops}
    state_alt = {_hindi_state(sn): sn for s, sn in states}

    _MIC_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" '
                'fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" '
                'stroke-linejoin="round"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/>'
                '<path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/>'
                '<line x1="8" y1="23" x2="16" y2="23"/></svg>')

    def _field(label: str, list_id: str, placeholder: str, m: dict,
               alt_var: str = "null", value: str = "") -> str:
        var = list_id.replace("-", "_")
        inp_id = f"{list_id}-i"
        # data-valid marks a prefilled field as a real pick, not free-typed text —
        # kmComboBlur()/kmComboReject() only wipe fields WITHOUT that flag, so an
        # already-known crop/state stays shown instead of vanishing on first blur.
        val_attr = f'value="{escape(value)}" data-valid="1" ' if value else ""
        return f"""<label class="ctl-f"><span>{label}</span>
<div class="ctl-input-row">
<input id="{inp_id}" {val_attr}autocomplete="off" placeholder="{escape(placeholder)}"
aria-label="{escape(placeholder)}"
oninput="kmComboFilter('{inp_id}',window.{var},{alt_var})"
onfocus="kmComboOpen('{inp_id}',window.{var},{alt_var})"
onkeydown="kmComboKeydown(event,'{inp_id}',window.{var},{alt_var})"
onblur="kmComboBlur('{inp_id}')">
<button type="button" class="ctl-mic" onclick="kmVoice('{inp_id}','{var}')" aria-label="आवाज़ से {escape(label)} खोजें">{_MIC_SVG}</button>
</div>
<ul class="ctl-list" id="{inp_id}-list" role="listbox"></ul></label>"""

    fields = (_field("फसल", "dl-hub-crop", "फसल चुनें", crop_map, "window.dl_hub_crop_alt", cur_crop)
              + _field("राज्य", "dl-hub-state", "राज्य चुनें", state_map, "window.dl_hub_state_alt", cur_state)
              + _field("मंडी / जिला", "dl-hub-dist", "मंडी / जिला चुनें", dist_map))

    maps_js = "".join(
        f'window.{var}={_json.dumps(m, ensure_ascii=False)};'
        for var, m in (("dl_hub_crop", crop_map), ("dl_hub_state", state_map),
                       ("dl_hub_dist", dist_map), ("dl_hub_crop_alt", crop_alt),
                       ("dl_hub_state_alt", state_alt)))

    return f"""<div class="ctl">{fields}</div>
<script>
{maps_js}
/* Type-then-pick: filtering never navigates by itself — only clicking (or
Enter-ing) a real suggestion does, so a random typed word just sits there
instead of silently doing nothing or jumping to a wrong page. */
function kmComboFilter(id,map,alt){{
var input=document.getElementById(id),list=document.getElementById(id+'-list');
if(!input||!list)return;
delete input.dataset.valid;                 // any typing invalidates the last pick
var q=input.value.trim().toLowerCase();
var keys=Object.keys(map||{{}});
var matches=q?keys.filter(function(k){{
var hi=k.toLowerCase(),en=((alt&&alt[k])||'').toLowerCase();
return hi.indexOf(q)!==-1||en.indexOf(q)!==-1;
}}):keys;
list.innerHTML=matches.length
?matches.slice(0,40).map(function(k){{return '<li role="option">'+k+'</li>';}}).join('')
:'<li class="ctl-no-results">कोई परिणाम नहीं मिला</li>';
Array.prototype.forEach.call(list.children,function(li){{
if(li.classList.contains('ctl-no-results'))return;
li.addEventListener('mousedown',function(e){{e.preventDefault();kmComboSelect(id,li.textContent,map);}});
}});
list.classList.add('open');
}}
function kmComboOpen(id,map,alt){{
var list=document.getElementById(id+'-list');
if(!list)return;
if(!list.children.length)kmComboFilter(id,map,alt);
list.classList.add('open');
}}
function kmComboSelect(id,label,map){{
var input=document.getElementById(id),list=document.getElementById(id+'-list');
if(input){{input.value=label;input.dataset.valid='1';}}
if(list)list.classList.remove('open');
if(map&&map[label]){{if(window.kmShowLoading)window.kmShowLoading();location.href=map[label];}}
}}
/* Govt-site style: a free-typed word never sticks in the box — only a value
actually picked from the shown results does. Anything else gets wiped the
moment the user leaves the field (Enter with nothing highlighted, Escape,
or clicking away) instead of sitting there looking like a valid answer. */
function kmComboReject(id){{
var input=document.getElementById(id);
if(input&&!input.dataset.valid)input.value='';
}}
function kmComboKeydown(e,id,map,alt){{
var list=document.getElementById(id+'-list');
if(!list)return;
if(!list.classList.contains('open')){{kmComboOpen(id,map,alt);return;}}
var items=Array.prototype.filter.call(list.children,function(li){{return !li.classList.contains('ctl-no-results');}});
var idx=items.findIndex(function(li){{return li.classList.contains('focused');}});
if(e.key==='ArrowDown'){{e.preventDefault();if(idx>=0)items[idx].classList.remove('focused');idx=(idx+1)%items.length;if(items[idx])items[idx].classList.add('focused');}}
else if(e.key==='ArrowUp'){{e.preventDefault();if(idx>=0)items[idx].classList.remove('focused');idx=(idx-1+items.length)%items.length;if(items[idx])items[idx].classList.add('focused');}}
else if(e.key==='Enter'){{e.preventDefault();var f=items[idx];if(f)kmComboSelect(id,f.textContent,map);else kmComboReject(id);}}
else if(e.key==='Escape'){{list.classList.remove('open');kmComboReject(id);}}
}}
function kmComboBlur(id){{
var list=document.getElementById(id+'-list');
setTimeout(function(){{if(list)list.classList.remove('open');kmComboReject(id);}},120);
}}
function kmCtlFuzzy(v,map){{
if(map[v])return map[v];
var best=null,bestLen=1e9;
for(var k in map){{if(k.indexOf(v)!==-1&&k.length<bestLen){{best=k;bestLen=k.length;}}}}
return best?map[best]:null;
}}
function kmVoice(inputId,mapVar){{
var SR=window.SpeechRecognition||window.webkitSpeechRecognition;
if(!SR){{alert('आपके ब्राउज़र में आवाज़ खोज उपलब्ध नहीं है');return;}}
var rec=new SR();rec.lang='hi-IN';
var btn=document.querySelector('[onclick="kmVoice(\\''+inputId+'\\',\\''+mapVar+'\\')"]');
if(btn)btn.classList.add('listening');
rec.onresult=function(e){{
var text=(e.results[0][0].transcript||'').trim();
var el=document.getElementById(inputId);
el.value=text;
kmComboFilter(inputId,window[mapVar]);
var url=kmCtlFuzzy(text,window[mapVar]);
if(url){{if(window.kmShowLoading)window.kmShowLoading();location.href=url;}}else el.focus();
}};
rec.onend=function(){{if(btn)btn.classList.remove('listening');}};
rec.start();
}}
</script>"""


def _chart(vals: list[float]) -> str:
    """Full-width 7-day trend chart. The old page buried this in a 64px table cell —
    it is the one thing a farmer cannot get from a Google snippet, so it leads.

    Under 3 points there is no trend to show, only a big box with a straight line in
    it, so the chart is dropped entirely and the per-mandi sparkline carries the move.
    Markets report irregularly, so short series are common, not an edge case."""
    if len(vals) < 3:
        return ""
    w, h = 600, 150
    pad_l, pad_r, pad_t, pad_b = 46, 12, 16, 24
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    n = len(vals)

    def x(i): return pad_l + i * (w - pad_l - pad_r) / (n - 1)
    def y(v): return pad_t + (1 - (v - lo) / span) * (h - pad_t - pad_b)

    pts  = [(x(i), y(v)) for i, v in enumerate(vals)]
    line = " ".join(f"{px:.1f},{py:.1f}" for px, py in pts)
    area = (f"M{pts[0][0]:.1f},{h - pad_b:.1f} "
            + " ".join(f"L{px:.1f},{py:.1f}" for px, py in pts)
            + f" L{pts[-1][0]:.1f},{h - pad_b:.1f} Z")
    rising = vals[-1] >= vals[0]
    col    = "#1b7a3d" if rising else "#c0392b"
    dots   = "".join(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3" fill="{col}"/>'
                     for px, py in pts)
    # Gridlines at the high, mid and low of the series, each labelled with its rupee
    # value — without them the line shows a shape but never says how much money it means.
    rows = []
    for f, v in ((0, hi), (0.5, (hi + lo) / 2), (1, lo)):
        gy = pad_t + f * (h - pad_t - pad_b)
        rows.append(
            f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{w - pad_r}" y2="{gy:.1f}" '
            f'stroke="#e5e9e6" stroke-width="1"/>'
            f'<text x="{pad_l - 6}" y="{gy + 3.5:.1f}" font-size="10" fill="#7c8983" '
            f'text-anchor="end">₹{round(v):,}</text>')
    grid = "".join(rows)

    return f"""<svg class="chart" viewBox="0 0 {w} {h}" role="img"
 aria-label="पिछले {n} दिनों का भाव रुझान">
<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
<stop offset="0" stop-color="{col}" stop-opacity=".18"/>
<stop offset="1" stop-color="{col}" stop-opacity="0"/></linearGradient></defs>
{grid}
<path d="{area}" fill="url(#g)"/>
<polyline points="{line}" fill="none" stroke="{col}" stroke-width="2.5"
 stroke-linecap="round" stroke-linejoin="round"/>
{dots}
<circle cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="5.5" fill="{col}"
 stroke="#fff" stroke-width="2.5"/>
<text x="{pad_l}" y="{h - 7}" font-size="11" fill="#7c8983">{n} दिन पहले</text>
<text x="{w - pad_r}" y="{h - 7}" font-size="11" fill="#7c8983" text-anchor="end">आज</text>
</svg>"""


def _sparkline(points: list[str]) -> str:
    """Inline SVG sparkline from the row's 7-day modal history."""
    vals = [v for v in (_num(p) for p in points) if v is not None]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    w, h = 64, 18
    step = w / (len(vals) - 1)
    pts = " ".join(f"{i * step:.1f},{h - 2 - (v - lo) / span * (h - 4):.1f}"
                   for i, v in enumerate(vals))
    color = "#1b7a3d" if vals[-1] >= vals[0] else "#c0392b"
    return (f'<svg class="spark" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'<polyline fill="none" stroke="{color}" stroke-width="1.5" points="{pts}"/></svg>')


def _avg_by(rows: list, key: str) -> dict:
    """{state|district → average modal price} — powers the price on every tile."""
    buckets: dict[str, list] = {}
    for r in rows:
        k, m = r.get(key), _num(r.get("modal_price"))
        if k and m:
            buckets.setdefault(k, []).append(m)
    return {k: round(sum(v) / len(v)) for k, v in buckets.items() if v}


# ════════════════════════════════════════════════════════════
# /find — site search across mandi crops + shop products
#
# The header search box lives in _header(), so it's on every /bhav AND
# /product page (both render through that one function) — a plain GET
# form, works with no JS, crawlable. Deliberately noindex: unbounded ?q=
# values would otherwise mint endless thin duplicate pages in the index;
# the real crop/product pages linked from the results are what should rank.
# ════════════════════════════════════════════════════════════
_FIND_LIMIT = 24


def _find_crop_card(cs: str, cn: str, hi: str) -> str:
    has_photo = _has_photo(cn)
    photo = (f'<img src="{escape(_crop_image(cn, 500))}" alt="{escape(hi)}" '
             f'loading="lazy" width="240" height="120">' if has_photo else "")
    en = f'<span class="crop-card-en">{escape(cn)}</span>' if hi != cn else ""
    return f"""<a class="crop-card" href="/bhav/{cs}">
<div class="crop-card-photo{'' if has_photo else ' noimg'}">{photo}
<h2 class="crop-card-name">{escape(hi)}{en}</h2></div>
<div class="crop-card-body"><span class="lbl">मंडी भाव</span><span class="rate">भाव देखें →</span>
</div></a>"""


def _find_product_card(p: dict) -> str:
    return f"""<a class="crop-card" href="/product/{p['slug']}">
<div class="crop-card-photo"><img src="{escape(p['img'])}" alt="{escape(p['name_hi'])}"
loading="lazy" width="240" height="120">
<h2 class="crop-card-name">{escape(p['name_hi'])}<span class="crop-card-en">{escape(p['name_en'])}</span></h2></div>
<div class="crop-card-body"><span class="lbl">{escape(p['unit_hi'])}</span><span class="rate">₹{p['price']}</span>
</div></a>"""


@router.get("/find", response_class=HTMLResponse)
def find(q: str = ""):
    from backend.routes.product import _get_products  # lazy: product.py imports bhav at module load, so the reverse import must happen after both modules are ready

    query = q.strip().lower()
    idx = _get_index()

    crop_hits = []
    if query:
        for cs, cn in idx.get("crops", {}).items():
            if not _is_crop(cn):
                continue
            hi = _hindi_name(cn)
            if query in cn.lower() or query in hi.lower() or query in cs:
                crop_hits.append((cs, cn, hi))
        crop_hits.sort(key=lambda x: _tile_rank(x[1]))
        crop_hits = crop_hits[:_FIND_LIMIT]

    product_hits = []
    if query:
        for p in _get_products():
            if (query in p["name_hi"].lower() or query in p["name_en"].lower()
                    or query in p["slug"]):
                product_hits.append(p)
        product_hits = product_hits[:_FIND_LIMIT]

    sections = []
    if crop_hits:
        sections.append(
            f'<h2>मंडी भाव ({len(crop_hits)})</h2>'
            f'<div class="crop-grid">{"".join(_find_crop_card(*c) for c in crop_hits)}</div>')
    if product_hits:
        sections.append(
            f'<h2>दुकान के उत्पाद ({len(product_hits)})</h2>'
            f'<div class="crop-grid">{"".join(_find_product_card(p) for p in product_hits)}</div>')

    if not query:
        heading = "फसल या उत्पाद खोजें"
        sub = 'फसल का नाम (जैसे गेहूं, प्याज) या उत्पाद का नाम (जैसे DAP, नीम तेल) लिखकर खोजें।'
    elif not crop_hits and not product_hits:
        heading = f'"{escape(q)}" के लिए कोई परिणाम नहीं मिला'
        sub = ('<div class="cta-row">'
               f'<a class="btn btn-app" href="{SITE}/bhav">सभी मंडी भाव देखें</a>'
               f'<a class="btn btn-wa" style="background:var(--green-dark)" href="{SITE}/product/">सभी उत्पाद देखें</a>'
               '</div>')
    else:
        heading = f'"{escape(q)}" के लिए परिणाम'
        sub = ""

    body = f"""<div class="hero nophoto">
<div class="hero-body">
<h1>{heading}</h1>
<p class="hero-sub">{sub}</p>
</div>
</div>
{"".join(sections)}"""

    title = f'{escape(q)} खोज परिणाम | कृषि मित्र' if query else 'फसल या उत्पाद खोजें | कृषि मित्र'
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="hi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<meta name="robots" content="noindex, follow">
{_ICON}
{_FONTS}
<style>{_CSS}</style>
</head>
<body>
{_header("")}
<nav class="crumbs"><a href="{SITE}/">कृषि मित्र</a> › खोज</nav>
<div class="wrap">
{body}
</div>
{_footer()}
</body>
</html>""", headers={"Cache-Control": "no-store"})


# ════════════════════════════════════════════════════════════
# /bhav/sitemap.xml — every tier
# ════════════════════════════════════════════════════════════
@router.get("/bhav/sitemap.xml")
def bhav_sitemap():
    idx = _get_index()
    today = date.today().isoformat()
    urls = [f"{SITE}/bhav"]
    for cs, cn in sorted(idx.get("crops", {}).items()):
        if not _is_crop(cn):
            continue
        urls.append(f"{SITE}/bhav/{cs}")
        for ss in sorted(idx["states"].get(cs, {})):
            urls.append(f"{SITE}/bhav/{cs}/{ss}")
            for ds in sorted(idx["dists"].get(cs, {}).get(ss, {})):
                urls.append(f"{SITE}/bhav/{cs}/{ss}/{ds}")
    body = "\n".join(
        f"  <url><loc>{u}</loc><lastmod>{today}</lastmod>"
        f"<changefreq>daily</changefreq></url>" for u in urls)
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
           f'{body}\n</urlset>')
    return Response(content=xml, media_type="application/xml",
                    headers={"Cache-Control": "public, max-age=3600"})


# ════════════════════════════════════════════════════════════
# TIER 1 — /bhav : pick a crop
# ════════════════════════════════════════════════════════════
@router.get("/bhav/", response_class=HTMLResponse)
@router.get("/bhav", response_class=HTMLResponse)
def bhav_hub():
    idx = _get_index()
    crops = {cs: cn for cs, cn in idx.get("crops", {}).items() if _is_crop(cn)}
    today_hi = _hindi_date(date.today())

    if not crops:
        return _doc("आज का मंडी भाव | कृषि मित्र", "मंडी भाव लोड हो रहे हैं।",
                    f"{SITE}/bhav", f'<a href="{SITE}/">कृषि मित्र</a> › मंडी भाव',
                    '<div class="hero nophoto"><div class="hero-body">'
                    '<h1>डेटा लोड हो रहा है</h1></div></div>')

    # Staples the farmer actually searches for lead the page as photo cards; the long
    # tail follows as chips. (Plain sorting opened the hub on "Ajwan, Akarkara, Almond".)
    #
    # ONE card per crop tile. Agmarknet lists many variants of the same crop — Wheat
    # AND Wheat Atta, Paddy(Common) AND Rice AND Broken Rice AND Beaten Rice — all of
    # which resolve to the same photo and (before the exact-name table above) the same
    # Hindi label, so the grid opened with five near-identical cards in a row. The
    # variant with the widest coverage represents the tile; the rest stay crawlable in
    # the chip list below and keep their own pages.
    featured, seen_tiles = [], {}
    for cs, cn in crops.items():
        rank = _tile_rank(cn)
        if rank >= len(_TILES):
            continue
        n = len(idx["states"].get(cs, {}))
        if rank not in seen_tiles or n > seen_tiles[rank][2]:
            seen_tiles[rank] = (cs, cn, n)
    featured = [seen_tiles[r] for r in sorted(seen_tiles)]
    featured_slugs = {cs for cs, _, _ in featured}

    cards = []
    for cs, cn, n_states in featured:
        hi = _hindi_name(cn)
        has_photo = _has_photo(cn)
        photo = (f'<img src="{escape(_crop_image(cn, 500))}" alt="{escape(hi)}" '
                 f'loading="lazy" width="240" height="120">' if has_photo else "")
        en = f'<span class="crop-card-en">{escape(cn)}</span>' if hi != cn else ""
        cards.append(f"""<a class="crop-card" href="/bhav/{cs}">
<div class="crop-card-photo{'' if has_photo else ' noimg'}">{photo}
<h2 class="crop-card-name">{escape(hi)}{en}</h2></div>
<div class="crop-card-body">
<span class="lbl">{n_states} राज्य</span><span class="rate">भाव देखें →</span>
</div></a>""")

    # Long tail — every other crop, still one crawlable link each.
    rest = sorted(((cs, cn) for cs, cn in crops.items() if cs not in featured_slugs),
                  key=lambda kv: _hindi_name(kv[1]))
    rest_html = ""
    if rest:
        chips = "".join(_crop_chip(f"/bhav/{cs}", _hindi_name(cn), cn) for cs, cn in rest)
        rest_html = (f'<h2>अन्य फसलें ({len(rest)})</h2>'
                     f'<div class="chips">{chips}</div>')

    faqs = [
        ("मंडी भाव रोज़ कब अपडेट होता है?",
         "भाव हर सुबह भारत सरकार के data.gov.in (Agmarknet) फीड से अपने आप अपडेट होते हैं। "
         "जिन मंडियों की रिपोर्ट उस दिन नहीं आती, उनका पिछला उपलब्ध भाव दिखता है।"),
        ("अपनी मंडी का भाव कैसे देखें?",
         "पहले अपनी फसल चुनें, फिर राज्य, फिर जिला — उस जिले की सभी मंडियों का न्यूनतम, "
         "अधिकतम और मॉडल भाव प्रति क्विंटल दिख जाएगा।"),
    ]
    faq_html, faq_ld = _faq(faqs)
    ld = _ld(faq_ld, _crumb_ld([("कृषि मित्र", f"{SITE}/"), ("मंडी भाव", f"{SITE}/bhav")]))

    title = f"आज का मंडी भाव {date.today().year} — सभी फसलों के ताजा रेट | कृषि मित्र"
    desc = (f"{today_hi}: गेहूं, धान, गन्ना, प्याज, आलू समेत {len(crops)} फसलों का ताजा मंडी भाव। "
            f"फसल चुनें, फिर राज्य और जिला — आज का रेट देखें। रोज़ अपडेट (data.gov.in)।")

    # Quick-jump seed for the hub's crop/state/district selector — the widest-covered
    # crop (same tile already picked for the featured grid above), its most-covered
    # state, and any real district there. _hub_selector() re-derives every option
    # list from this triple, so any valid starting point works; there is no "no
    # selection" state to seed it with since the hub itself isn't scoped to one crop.
    seed_cs = featured[0][0] if featured else next(iter(crops), "")
    seed_states = idx["states"].get(seed_cs, {})
    seed_ss = (max(seed_states, key=lambda s: len(idx["dists"].get(seed_cs, {}).get(s, {})))
               if seed_states else "")
    seed_dists = idx["dists"].get(seed_cs, {}).get(seed_ss, {})
    seed_ds = sorted(seed_dists, key=lambda d: seed_dists[d])[0] if seed_dists else ""

    body = f"""<div class="hero nophoto">
<div class="hero-body">
<h1>आज का मंडी भाव — अपनी फसल चुनें</h1>
<p class="hero-sub">📅 {today_hi} · {len(crops)} फसलें · रोज़ सुबह अपडेट · स्रोत: data.gov.in (Agmarknet)</p>
</div>
</div>
<div class="cta-row">
<a class="btn btn-app" href="{SITE}/mandi">📊 मंडी ऐप खोलें — ट्रेंड चार्ट व तुलना</a>
</div>
{_hub_selector(seed_cs, seed_ss, seed_ds, idx)}
<h2>प्रमुख फसलें</h2>
<div class="crop-grid">{"".join(cards)}</div>
{rest_html}
<h2>अक्सर पूछे जाने वाले सवाल</h2>
{faq_html}"""
    return _doc(title, desc, f"{SITE}/bhav",
                f'<a href="{SITE}/">कृषि मित्र</a> › मंडी भाव', body, ld)


# ════════════════════════════════════════════════════════════
# TIER 2 — /bhav/{crop} : pick a state
# ════════════════════════════════════════════════════════════
@router.get("/bhav/{c_slug}", response_class=HTMLResponse)
def bhav_crop(c_slug: str):
    idx = _get_index()
    cs = c_slug.lower()
    commodity = idx.get("crops", {}).get(cs)
    if not commodity:
        return _not_found()

    hi = _hindi_name(commodity)
    today_hi = _hindi_date(date.today())
    canon = f"{SITE}/bhav/{cs}"
    state_map = idx["states"].get(cs, {})

    rows = _rows_for(commodity)             # national picture
    st = _stats(rows)

    # No prices on this tier — only /bhav/{crop}/{state}/{district} shows the
    # actual rupee figure. A state/district-level number here would answer the
    # question before the click, so a farmer never reaches the specific page
    # that's meant to rank and convert. This page is purely "pick your state".
    cards = []
    for ss, sn in sorted(state_map.items(), key=lambda kv: kv[1]):
        n = len(idx["dists"].get(cs, {}).get(ss, {}))
        svg_slug = _state_svg_slug(sn)
        svg_src  = f"/images/state_map_svgs/{svg_slug}.svg"
        cards.append(f"""<a class="place" href="/bhav/{cs}/{ss}">
<div class="place-map-panel">
  <div class="place-map-blob"></div>
  <img class="place-map-svg" src="{escape(svg_src)}" alt="{escape(sn)} नक्शा" loading="lazy"
    onerror="this.closest('.place-map-panel').style.display='none'">
</div>
<div class="place-info">
  <svg class="place-deco-svg" viewBox="0 0 100 100" fill="none" stroke="#2d6a4f" stroke-opacity="0.07" stroke-width="2.5" stroke-linecap="round">
    <path d="M10,90 Q40,80 70,30 Q80,15 90,10 M35,70 Q20,55 15,60 Q10,65 25,75 M50,53 Q38,38 30,40 Q22,42 40,58 M60,40 Q75,32 80,38 Q85,44 68,50" />
  </svg>
  <div class="place-n">{escape(_hindi_state(sn))}</div>
  <div class="place-divider-wrap">
    <div class="place-line"></div>
    <span class="place-ornament">🌿</span>
    <div class="place-line"></div>
  </div>
  <div class="place-en">{escape(sn)}</div>
  <div class="place-dist-box">
    <div class="place-dist-pin-wrap">
      <svg class="place-dist-pin" viewBox="0 0 24 24" width="18" height="18" fill="#1a3c2e">
        <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z" />
      </svg>
    </div>
    <div class="place-dist-text">
      <span class="place-dist-num">{n}</span>
      <span class="place-dist-lbl">जिले</span>
    </div>
  </div>
  <div class="place-btn-pill">
    <div class="place-btn-left">📈</div>
    <div class="place-btn-divider"></div>
    <div class="place-btn-right">
      <span>भाव देखें</span>
      <span class="place-btn-arrow">→</span>
    </div>
  </div>
</div>
</a>""")

    # The highest-paying mandi in the country today — the reason to read this page
    # rather than bounce back to Google. Names the market as a hook but withholds
    # the number, same reasoning as the cards above.
    best = max((r for r in rows if _num(r.get("modal_price"))),
               key=lambda r: _num(r["modal_price"]), default=None)
    best_html = ""
    if best:
        b_state = best.get("state", "")
        b_dist = best.get("district", "")
        best_html = f"""<section class="better">
<h2>🏆 आज देश में सबसे ज्यादा {escape(hi)} भाव</h2>
<p class="better-sub">आज के मॉडल भाव के आधार पर</p>
<ul><li>
<a class="better-mandi-card" href="/bhav/{cs}/{_slugify(b_state)}/{_slugify(b_dist)}">
  <div class="bmc-details">
    <span class="bmc-market">{escape(best.get('market','-'))}</span>
    <span class="bmc-meta">{escape(b_dist)}, {escape(_hindi_state(b_state))}</span>
  </div>
  <span class="bmc-action">भाव देखें →</span>
</a></li></ul></section>"""

    photo = (f'<img class="answer-photo" src="{escape(_crop_image(commodity, 960))}" '
             f'alt="" aria-hidden="true" width="420" height="200">'
             if _has_photo(commodity) else "")

    faqs = [
        (f"आज {hi} का भाव क्या है?",
         f"{hi} का भाव हर राज्य और मंडी में अलग-अलग होता है। सटीक भाव जानने के लिए नीचे अपना राज्य चुनें, "
         f"फिर जिला चुनें — वहां आज का पूरा भाव दिख जाएगा।"),
        (f"{hi} सबसे महंगा किस मंडी में बिक रहा है?",
         (f"आज सबसे ज्यादा भाव {best.get('market','-')} ({best.get('district','-')}, "
          f"{_hindi_state(best.get('state',''))}) में मिल रहा है — सटीक भाव देखने के लिए उस जिले का पेज खोलें।"
          if best else "मंडीवार भाव देखने के लिए अपना राज्य चुनें।")),
    ]
    faq_html, faq_ld = _faq(faqs)
    ld = _ld(faq_ld, _crumb_ld([("कृषि मित्र", f"{SITE}/"), ("मंडी भाव", f"{SITE}/bhav"),
                                (hi, canon)]))

    # Seed state/district for the quick-jump selector below — same idea as the
    # hub's own seed, just scoped to this tier's already-known crop.
    seed_ss = (max(state_map, key=lambda s: len(idx["dists"].get(cs, {}).get(s, {})))
               if state_map else "")
    seed_dists = idx["dists"].get(cs, {}).get(seed_ss, {})
    seed_ds = sorted(seed_dists, key=lambda d: seed_dists[d])[0] if seed_dists else ""

    title = f"{hi} का भाव आज — {commodity} Price Today सभी राज्य | कृषि मित्र"
    desc = (f"{today_hi}: {hi} ({commodity}) का ताजा मंडी भाव — "
            + (f"औसत ₹{st['avg']:,}/क्विंटल। " if st["avg"] else "")
            + f"{len(state_map)} राज्यों की मंडियों के रेट। राज्य चुनकर अपने जिले का भाव देखें।")

    body = f"""<section class="answer">
{photo}
<div class="answer-in">
<h1>आज का {escape(hi)} भाव — राज्य चुनें</h1>
<p class="answer-sub">📅 {today_hi} · {_mandis_gen(st['n'])} की सरकारी रिपोर्ट · अपना राज्य चुनकर भाव देखें</p>
<div class="answer-range">
<div><span>राज्य</span><b>{len(state_map)}</b></div>
<div><span>मंडियां</span><b>{st['n']}</b></div>
</div>
</div>
</section>
{_hub_selector(cs, seed_ss, seed_ds, idx, known_crop=True)}
{best_html}
<h2>राज्य के अनुसार {escape(hi)} का भाव</h2>
<div class="place-grid">{"".join(cards)}</div>
<div class="cta-row">
<a class="btn btn-app" href="{_app_url(commodity)}">📊 ऐप में {escape(hi)} की तुलना देखें</a>
</div>
<h2>अक्सर पूछे जाने वाले सवाल</h2>
{faq_html}"""
    crumbs = (f'<a href="{SITE}/">कृषि मित्र</a> › <a href="{SITE}/bhav">मंडी भाव</a> › {escape(hi)}')
    return _doc(title, desc, canon, crumbs, body, ld, _crop_image(commodity, 960))


# ════════════════════════════════════════════════════════════
# TIER 3 — /bhav/{crop}/{state} : pick a district
#          …and the 301s for the retired two-level URLs.
#
# This shares its URL shape with the old /bhav/{crop}/{district}, so one handler
# decides: state slug → render the state page; district slug → 301 to the
# canonical four-level URL. `chandigarh` / `pondicherry` are both, and resolve as
# states (their district pages still live at /bhav/{crop}/chandigarh/chandigarh).
# ════════════════════════════════════════════════════════════
@router.get("/bhav/{c_slug}/{x_slug}", response_class=HTMLResponse)
def bhav_crop_or_state(c_slug: str, x_slug: str):
    idx = _get_index()
    cs, xs = c_slug.lower(), x_slug.lower()
    commodity = idx.get("crops", {}).get(cs)
    if not commodity:
        return _not_found()

    if xs in idx["states"].get(cs, {}):
        return _state_page(idx, cs, commodity, xs)

    owners = idx["legacy"].get(cs, {}).get(xs)
    if owners:                              # legacy /bhav/{crop}/{district}
        return RedirectResponse(f"/bhav/{cs}/{owners[0]}/{xs}", status_code=301)

    return _not_found()


def _state_page(idx: dict, cs: str, commodity: str, ss: str) -> HTMLResponse:
    state = idx["states"][cs][ss]
    hi, hi_state = _hindi_name(commodity), _hindi_state(state)
    today_hi = _hindi_date(date.today())
    canon = f"{SITE}/bhav/{cs}/{ss}"

    rows = _rows_for(commodity, state=state)
    st = _stats(rows)
    dist_map = idx["dists"].get(cs, {}).get(ss, {})

    # No prices on this tier either — same reasoning as bhav_crop above: only
    # the district-level page (/bhav/{crop}/{state}/{district}) shows a number.
    cards = []
    for ds, dn in sorted(dist_map.items(), key=lambda kv: kv[1]):
        cards.append(f"""<a class="place" href="/bhav/{cs}/{ss}/{ds}">
<div class="place-n">{escape(dn)}</div>
<div class="place-r">भाव देखें →</div>
</a>""")

    # Top-paying mandis in this state — names the market as a hook, withholds
    # the number so the click still has to happen.
    top = sorted((r for r in rows if _num(r.get("modal_price"))),
                 key=lambda r: _num(r["modal_price"]), reverse=True)[:5]
    top_html = ""
    if top:
        items = "".join(
            f'<li><a class="better-mandi-card" href="/bhav/{cs}/{ss}/{_slugify(r.get("district",""))}">'
            f'  <div class="bmc-details">'
            f'    <span class="bmc-market">{escape(r.get("market","-"))}</span>'
            f'    <span class="bmc-meta">{escape(r.get("district","-"))}</span>'
            f'  </div>'
            f'  <span class="bmc-action">भाव देखें →</span>'
            f'</a></li>'
            for r in top)
        top_html = f"""<section class="better">
<h2>🏆 {escape(hi_state)} में आज सबसे ज्यादा {escape(hi)} भाव</h2>
<p class="better-sub">भेजने से पहले मंडी की दूरी और भाड़ा ज़रूर जोड़ें</p>
<ul>{items}</ul></section>"""

    photo = (f'<img class="answer-photo" src="{escape(_crop_image(commodity, 960))}" '
             f'alt="" aria-hidden="true" width="420" height="200">'
             if _has_photo(commodity) else "")

    faqs = [
        (f"आज {hi_state} में {hi} का भाव क्या है?",
         f"{hi_state} की मंडियों में {hi} का भाव जिले के अनुसार अलग-अलग है। सटीक भाव जानने के लिए "
         f"नीचे अपना जिला चुनें — वहां आज का पूरा भाव दिख जाएगा।"),
        (f"{hi_state} में {hi} सबसे महंगा कहां बिक रहा है?",
         (f"आज {top[0].get('market','-')} ({top[0].get('district','-')}) मंडी में सबसे ज्यादा भाव मिल रहा है — "
          f"सटीक भाव देखने के लिए उस जिले का पेज खोलें।"
          if top else "जिलेवार भाव के लिए नीचे अपना जिला चुनें।")),
    ]
    faq_html, faq_ld = _faq(faqs)
    ld = _ld(faq_ld, _crumb_ld([
        ("कृषि मित्र", f"{SITE}/"), ("मंडी भाव", f"{SITE}/bhav"),
        (hi, f"{SITE}/bhav/{cs}"), (hi_state, canon)]))

    title = f"{hi_state} में {hi} का भाव आज — {commodity} Price {state} | कृषि मित्र"
    desc = (f"{today_hi}: {hi_state} की मंडियों में {hi} का ताजा भाव — "
            + (f"औसत ₹{st['avg']:,}/क्विंटल। " if st["avg"] else "")
            + f"{len(dist_map)} जिलों के रेट और सबसे ज्यादा भाव देने वाली मंडियां। रोज़ अपडेट।")

    body = f"""<section class="answer">
{photo}
<div class="answer-in">
<h1>{escape(hi_state)} में {escape(hi)} का भाव आज</h1>
<p class="answer-sub">📅 {today_hi} · {_mandis_gen(st['n'])} की सरकारी रिपोर्ट · अपना जिला चुनकर भाव देखें</p>
<div class="answer-range">
<div><span>जिले</span><b>{len(dist_map)}</b></div>
<div><span>मंडियां</span><b>{st['n']}</b></div>
</div>
</div>
</section>
{_hub_selector(cs, ss, "", idx, known_crop=True, known_state=True)}
{top_html}
<h2>जिले के अनुसार {escape(hi)} का भाव</h2>
<div class="place-grid">{"".join(cards)}</div>
<div class="cta-row">
<a class="btn btn-app" href="{_app_url(commodity, state=state)}">📊 ऐप में तुलना देखें</a>
</div>
<h2>अक्सर पूछे जाने वाले सवाल</h2>
{faq_html}"""
    crumbs = (f'<a href="{SITE}/">कृषि मित्र</a> › <a href="{SITE}/bhav">मंडी भाव</a> › '
              f'<a href="{SITE}/bhav/{cs}">{escape(hi)}</a> › {escape(hi_state)}')
    return _doc(title, desc, canon, crumbs, body, ld, _crop_image(commodity, 960))


# ════════════════════════════════════════════════════════════
# TIER 4 — /bhav/{crop}/{state}/{district} : the prices
# ════════════════════════════════════════════════════════════
@router.get("/bhav/{c_slug}/{s_slug}/{d_slug}", response_class=HTMLResponse)
def bhav_page(c_slug: str, s_slug: str, d_slug: str):
    idx = _get_index()
    cs, ss, ds = c_slug.lower(), s_slug.lower(), d_slug.lower()

    commodity = idx.get("crops", {}).get(cs)
    state     = idx.get("states", {}).get(cs, {}).get(ss)
    district  = idx.get("dists", {}).get(cs, {}).get(ss, {}).get(ds)
    if not (commodity and state and district):
        return _not_found()

    # Scoped by STATE as well as district. Without the state, the four district
    # names shared by two states (pratapgarh, bilaspur, hamirpur, balrampur)
    # pulled both states' mandis onto one page under a single district heading.
    prices = _rows_for(commodity, state=state, district=district)
    if not prices:                      # snapshot aged out since the index was built
        return _not_found()

    hi, hi_state = _hindi_name(commodity), _hindi_state(state)
    today_hi  = _hindi_date(date.today())
    data_date = prices[0].get("date", "-")
    canon     = f"{SITE}/bhav/{cs}/{ss}/{ds}"
    st = _stats(prices)

    # ── mandi-wise cards ──
    cards_html = []
    for p in prices:
        arrow = ""
        try:
            pct = float(p.get("change_pct"))
            if pct:
                cls  = "up" if pct > 0 else "dn"
                sym  = "▲" if pct > 0 else "▼"
                sign = "+" if pct > 0 else ""
                arrow = f'<span class="{cls}">{sym}{sign}{pct:g}%</span>'
        except (TypeError, ValueError):
            pass
        variety = p.get("variety") or ""
        cards_html.append(f"""<article class="mkt">
<div class="mkt-name">{escape(p.get('market', '-'))}</div>
<div class="mkt-var">{escape(variety) if variety and variety != '-' else '—'}</div>
<div class="mkt-price"><b>{_rupee(p.get('modal_price'))}</b><small>/क्विंटल</small>{arrow}</div>
<div class="mkt-foot">
<span class="mkt-range">{_rupee(p.get('min_price'))} – {_rupee(p.get('max_price'))}</span>
{_sparkline(p.get('spark') or [])}
</div>
</article>""")
    mkt_cards = "\n".join(cards_html)

    # ── overall day-on-day move, averaged over the mandis that reported one ──
    pcts = []
    for p in prices:
        try:
            v = float(p.get("change_pct"))
            if v:
                pcts.append(v)
        except (TypeError, ValueError):
            pass
    avg_pct = round(sum(pcts) / len(pcts), 1) if pcts else None
    if avg_pct:
        d_cls  = "up" if avg_pct > 0 else "dn"
        d_sym  = "▲" if avg_pct > 0 else "▼"
        d_sign = "+" if avg_pct > 0 else ""
        delta_html = (f'<div class="answer-delta {d_cls}">'
                      f'{d_sym} {d_sign}{avg_pct:g}% कल से</div>')
    else:
        delta_html = '<div class="answer-delta">— कल जैसा</div>'

    # ── THE DECISION LAYER ──────────────────────────────────
    # A price table says what today's rate is; it never says whether to sell here.
    # These are the districts in the SAME state paying more for this crop today.
    # There is no lat/long in the feed, so this is deliberately "same state, better
    # price" — an honest claim — rather than a fabricated distance in km.
    better_html = ""
    if st["avg"]:
        state_rows = _rows_for(commodity, state=state)
        d_avg = _avg_by(state_rows, "district")
        gains = sorted(((dn, avg, avg - st["avg"]) for dn, avg in d_avg.items()
                        if dn != district and avg > st["avg"]),
                       key=lambda x: x[2], reverse=True)[:5]
        if gains:
            items = "".join(
                f'<li><a class="better-mandi-card" href="/bhav/{cs}/{ss}/{_slugify(dn)}">'
                f'  <div class="bmc-details">'
                f'    <span class="bmc-market">{escape(dn)}</span>'
                f'    <span class="bmc-meta">{escape(hi_state)}</span>'
                f'  </div>'
                f'  <span class="bmc-action">₹{avg:,} <small>(+₹{diff:,} ज्यादा)</small></span>'
                f'</a></li>'
                for dn, avg, diff in gains)
            better_html = f"""<section class="better">
<h2>💰 {escape(hi_state)} में इन जिलों में {escape(hi)} का भाव ज्यादा है</h2>
<p class="better-sub">{escape(district)} के औसत ₹{st['avg']:,}/क्विंटल से तुलना ·
भेजने से पहले मंडी की दूरी और भाड़ा ज़रूर जोड़ें</p>
<ul>{items}</ul></section>"""
        else:
            better_html = f"""<section class="better flat">
<h2>✅ {escape(district)} में भाव सबसे अच्छा है</h2>
<p class="better-sub">आज के मॉडल भाव के आधार पर</p>
<p class="better-message">{escape(hi_state)} के किसी और जिले में {escape(hi)} का इससे बेहतर भाव नहीं मिल रहा।</p>
</section>"""

    # ── chart series: the mandi with the longest history speaks for the district ──
    sparks = [[v for v in (_num(x) for x in (p.get("spark") or [])) if v] for p in prices]
    series = max(sparks, key=len) if sparks else []
    chart_svg = _chart(series)
    chart_html = (f"""<section class="card-w">
<div class="card-w-h"><h2>{escape(hi)} का {len(series)}-दिन रुझान</h2><em>{escape(district)} · ₹/क्विंटल</em></div>
{chart_svg}
</section>""" if chart_svg else "")

    price_txt = (f"औसतन ₹{st['avg']:,} प्रति क्विंटल (₹{st['lo']:,} से ₹{st['hi']:,} तक)"
                 if st["avg"] and st["lo"] and st["hi"] else "नीचे मंडीवार भाव देखें")
    faqs = [
        (f"आज {district} में {hi} का भाव क्या है?",
         f"{today_hi} को {district} ({hi_state}) की मंडियों में {hi} का भाव {price_txt} है। "
         f"यह भाव {_mandis_gen(st['n'])} की सरकारी रिपोर्ट पर आधारित है।"),
        (f"{district} में {hi} का न्यूनतम और अधिकतम रेट कितना है?",
         (f"आज {district} में {hi} का न्यूनतम भाव ₹{st['lo']:,} और अधिकतम भाव "
          f"₹{st['hi']:,} प्रति क्विंटल दर्ज हुआ है।"
          if st["lo"] and st["hi"] else "मंडीवार न्यूनतम/अधिकतम भाव नीचे दिए गए हैं।")),
        ("यह भाव कब और कहां से अपडेट होता है?",
         "भाव रोज़ सुबह भारत सरकार के data.gov.in (Agmarknet) से अपडेट होते हैं। "
         "जिन मंडियों की रिपोर्ट आज नहीं आई, उनका पिछला भाव दिखता है।"),
    ]
    faq_html, faq_ld = _faq(faqs)
    ld = _ld(faq_ld, _crumb_ld([
        ("कृषि मित्र", f"{SITE}/"), ("मंडी भाव", f"{SITE}/bhav"),
        (hi, f"{SITE}/bhav/{cs}"), (hi_state, f"{SITE}/bhav/{cs}/{ss}"),
        (district, canon)]))

    title = f"{hi} का भाव आज {district} मंडी में — {commodity} Price {district} | कृषि मित्र"
    desc  = (f"{today_hi}: {district} ({hi_state}) में {hi} का ताजा मंडी भाव — "
             + (f"औसत ₹{st['avg']:,}/क्विंटल। " if st["avg"] else "")
             + f"{_mandis_gen(st['n'])} के रेट, कल से तुलना और 7-दिन का रुझान। रोज़ अपडेट।")

    # WhatsApp share — same behaviour as mandi.html's shareMandiPrice(): share the
    # /share/mandi deep link (WhatsApp unfurls it into one rich preview card with the
    # crop photo + rate as OG tags) via the native share sheet, falling back to wa.me.
    share_url = f"{SITE}/share/mandi?" + urlencode(
        [(k, v) for k, v in (("state", state), ("commodity", commodity),
                             ("district", district)) if v])
    # Exactly mandi.html's shareMandiPrice() caption format: crop name alone in bold
    # (district lives in the preview card + URL, not the caption), then rate, delta,
    # and the same "👉 ताजा भाव देखें 👇" call to action.
    share_caption = (f"🌾 *{hi}*"
                     + (f" — 💰 ₹{st['avg']:,}/क्विंटल" if st["avg"] else "")
                     + ((f" (📈 +{avg_pct:g}%)" if avg_pct > 0 else f" (📉 {avg_pct:g}%)")
                        if avg_pct else "")
                     + "\n👉 ताजा भाव देखें 👇")
    share_cfg = _json.dumps({"caption": share_caption, "url": share_url}, ensure_ascii=False)
    _WA_GLYPH = ('<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">'
                 '<path d="M12.04 2c-5.46 0-9.91 4.45-9.91 9.91 0 1.75.46 3.45 1.32 4.95L2 22l5.25-1.38'
                 'c1.45.79 3.08 1.21 4.79 1.21h.01c5.46 0 9.9-4.45 9.9-9.91 0-2.65-1.03-5.14-2.9-7.01'
                 'A9.816 9.816 0 0 0 12.04 2zm5.52 14.03c-.25.7-1.45 1.34-2.01 1.4-.54.06-1.03.29-3.42-.71'
                 '-2.9-1.17-4.75-4.14-4.9-4.33-.14-.19-1.16-1.54-1.16-2.94 0-1.4.73-2.09.99-2.37.26-.29'
                 '.57-.36.76-.36.19 0 .38 0 .55.01.18.01.42-.07.66.5.25.58.83 2 .9 2.15.07.14.12.31.02.5'
                 '-.09.19-.14.31-.28.47-.14.17-.29.37-.42.5-.14.14-.28.29-.12.57.16.28.72 1.18 1.54 1.91'
                 '1.06.94 1.95 1.24 2.23 1.38.28.14.44.12.6-.07.16-.19.69-.8.87-1.08.18-.28.36-.23.6-.14'
                 '.25.09 1.57.74 1.84.88.28.14.46.2.53.32.07.11.07.66-.18 1.36z"/></svg>')

    answer_photo = (f'<img class="answer-photo" src="{escape(_crop_image(commodity, 960))}" '
                    f'alt="" aria-hidden="true" width="420" height="200">'
                    if _has_photo(commodity) else "")
    lead = f"₹{st['avg']:,}" if st["avg"] else "—"

    body = f"""<section class="answer">
{answer_photo}
<div class="answer-in">
<h1>आज का {escape(hi)} भाव — {escape(district)} मंडी</h1>
<p class="answer-sub">📅 {today_hi} · {escape(hi_state)} · {_mandis_gen(st['n'])} की सरकारी रिपोर्ट · {escape(_hindi_data_date(data_date))} तक</p>
<div class="answer-price">
<div class="answer-rupee">{lead}<small>/क्विंटल</small></div>
{delta_html}
</div>
<div class="answer-range">
<div><span>न्यूनतम</span><b>{f"₹{st['lo']:,}" if st['lo'] else '—'}</b></div>
<div><span>अधिकतम</span><b>{f"₹{st['hi']:,}" if st['hi'] else '—'}</b></div>
<div><span>{'मंडी' if st['n'] == 1 else 'मंडियां'}</span><b>{st['n']}</b></div>
</div>
<button class="answer-share" type="button" onclick="shareBhav()">{_WA_GLYPH} WhatsApp पर भेजें</button>
</div>
</section>
<script>
(function(){{
  var CFG={share_cfg};
  window.shareBhav=async function(){{
    if(navigator.share){{
      try{{await navigator.share({{text:CFG.caption,url:CFG.url}});return;}}
      catch(err){{if(err&&err.name==='AbortError')return;}}
    }}
    window.open('https://wa.me/?text='+encodeURIComponent(CFG.caption+'\\n'+CFG.url),'_blank');
  }};
}})();
</script>

{_switchers(cs, ss, ds)}

{better_html}

{chart_html}

<section class="card-w">
<div class="card-w-h"><h2>मंडीवार भाव</h2><em>▲▼ = कल के मुकाबले</em></div>
<div class="mkts">
{mkt_cards}
</div>
</section>
<p class="note">सभी भाव ₹ प्रति क्विंटल · मॉडल भाव (सबसे ज़्यादा कारोबार वाला रेट)।</p>

<div class="cta-row">
<a class="btn btn-app" href="{_app_url(commodity, district, state)}">📊 ऐप में {escape(hi)} की तुलना देखें</a>
<button class="btn btn-wa" type="button" onclick="shareBhav()">📲 WhatsApp पर भाव भेजें</button>
</div>

<h2>अक्सर पूछे जाने वाले सवाल</h2>
{faq_html}
{_related_links(cs, ss, ds, commodity, district)}"""

    crumbs = (f'<a href="{SITE}/">कृषि मित्र</a> › <a href="{SITE}/bhav">मंडी भाव</a> › '
              f'<a href="{SITE}/bhav/{cs}">{escape(hi)}</a> › '
              f'<a href="{SITE}/bhav/{cs}/{ss}">{escape(hi_state)}</a> › {escape(district)}')
    return _doc(title, desc, canon, crumbs, body, ld, _crop_image(commodity, 960))
