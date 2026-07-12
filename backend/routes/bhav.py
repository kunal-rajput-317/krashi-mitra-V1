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

/* ── site header (same white sticky bar as the app) ── */
.km-header{position:sticky;top:0;z-index:50;background:var(--white);
border-bottom:1px solid var(--border);box-shadow:0 1px 3px rgba(26,60,46,.05)}
.km-header-inner{max-width:1280px;margin:0 auto;padding:9px 20px;display:flex;align-items:center;gap:14px}
.km-logo{display:flex;align-items:center;gap:10px;text-decoration:none;flex-shrink:0}
.km-logo img{width:38px;height:38px;border-radius:50%;object-fit:cover;box-shadow:0 0 0 3px var(--green-pale)}
.km-logo-text{display:flex;flex-direction:column}
.km-logo-title{font-family:var(--font-serif);font-size:19px;font-weight:700;color:var(--green-dark);line-height:1.15}
.km-logo-tag{font-size:9px;font-weight:600;color:var(--text-soft);line-height:1.6}
.km-nav{margin-left:auto;display:flex;align-items:center;gap:2px}
.km-nav a{font-size:13px;font-weight:600;color:var(--text-mid);text-decoration:none;
padding:7px 11px;border-radius:9px;transition:background .15s,color .15s;white-space:nowrap}
.km-nav a:hover{background:var(--green-pale);color:var(--green-dark)}
.km-nav a.on{background:var(--green-pale);color:var(--green-dark)}
@media(max-width:700px){.km-logo-tag{display:none}.km-nav a{padding:7px 8px;font-size:12.5px}
.km-nav a.hide-sm{display:none}}

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
.ctl-f{flex:1;min-width:150px;display:flex;flex-direction:column;gap:4px;
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
@media(max-width:640px){.answer-photo{opacity:.22;width:100%;
-webkit-mask-image:linear-gradient(90deg,transparent,#000 90%);
mask-image:linear-gradient(90deg,transparent,#000 90%)}
.answer-rupee{font-size:38px}h1{font-size:20px}.answer h1{font-size:20px}}

/* ── "sell here instead": the one thing a price table never tells you ── */
.better{background:var(--white);border:1px solid var(--border);border-left:4px solid var(--amber);
border-radius:var(--radius-md);padding:15px 18px;box-shadow:var(--shadow-sm);margin-top:16px}
.better h2{margin:0 0 4px}
.better-sub{font-size:11.5px;color:var(--text-soft);margin-bottom:10px}
.better ul{list-style:none}
.better li{display:flex;align-items:center;justify-content:space-between;gap:12px;
padding:9px 0;border-bottom:1px dashed var(--border);font-size:13.5px}
.better li:last-child{border-bottom:0}
.better li a{color:var(--green-dark);text-decoration:none;font-weight:700}
.better li a:hover{text-decoration:underline}
.better .place small{display:block;font-size:11px;font-weight:600;color:var(--text-soft)}
.better .gain{font-size:15px;font-weight:700;color:#1b7a3d;white-space:nowrap;text-align:right}
.better .gain small{display:block;font-size:11px;font-weight:600;color:var(--text-soft)}
.better.flat{border-left-color:var(--green-light)}

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

/* ── place cards (states / districts) ── */
.place-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:12px;margin-top:12px}
.place{background:var(--white);border:1px solid var(--border);border-radius:var(--radius-sm);
padding:13px 15px;box-shadow:var(--shadow-sm);text-decoration:none;color:inherit;display:block;
transition:transform .15s,box-shadow .15s,border-color .15s}
.place:hover{transform:translateY(-2px);box-shadow:var(--shadow-md);border-color:var(--green-light)}
.place-n{font-size:14.5px;font-weight:700;color:var(--text-dark)}
.place-en{font-size:11px;font-weight:600;color:var(--text-soft);margin-top:1px}
.place-r{font-size:17px;font-weight:700;color:var(--green-dark);margin-top:8px;letter-spacing:-.3px}
.place-r small{font-size:11px;font-weight:600;color:var(--text-soft);margin-left:2px}
.place-s{font-size:11px;font-weight:600;color:var(--text-soft);margin-top:2px}

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


def _header(active: str = "") -> str:
    """The app's white sticky header, so /bhav reads as the same site."""
    items = [("home", f"{SITE}/", "मुख्य", ""),
             ("mandi", f"{SITE}/mandi", "मंडी", ""),
             ("bhav", f"{SITE}/bhav", "भाव", ""),
             ("weather", f"{SITE}/weather", "मौसम", " hide-sm"),
             ("articles", f"{SITE}/articles/", "लेख", " hide-sm"),
             ("chat", f"{SITE}/chat", "सहायता", " hide-sm")]
    nav = "".join(
        f'<a class="{("on " if key == active else "")}{small.strip()}" href="{href}">{label}</a>'
        for key, href, label, small in items)
    return f"""<header class="km-header"><div class="km-header-inner">
<a class="km-logo" href="{SITE}/">
<img src="{SITE}/assets/krashimitra_logo.png" alt="कृषि मित्र" width="38" height="38">
<span class="km-logo-text"><span class="km-logo-title">कृषि मित्र</span>
<span class="km-logo-tag">किसान का डिजिटल साथी</span></span></a>
<nav class="km-nav">{nav}</nav>
</div></header>"""


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
         ld: str = "", og_img: str = "") -> HTMLResponse:
    """One page shell for all four tiers — head, header, crumbs, body, footer."""
    og = og_img or f"{SITE}/images/og-banner.jpg"
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
<style>{_CSS}</style>
</head>
<body>
{_header("bhav")}
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

    body = f"""<div class="hero nophoto">
<div class="hero-body">
<h1>आज का मंडी भाव — अपनी फसल चुनें</h1>
<p class="hero-sub">📅 {today_hi} · {len(crops)} फसलें · रोज़ सुबह अपडेट · स्रोत: data.gov.in (Agmarknet)</p>
</div>
</div>
<div class="cta-row">
<a class="btn btn-app" href="{SITE}/mandi">📊 मंडी ऐप खोलें — ट्रेंड चार्ट व तुलना</a>
</div>
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
    state_avg = _avg_by(rows, "state")

    cards = []
    for ss, sn in sorted(state_map.items(), key=lambda kv: kv[1]):
        avg = state_avg.get(sn)
        n = len(idx["dists"].get(cs, {}).get(ss, {}))
        rate = (f'<div class="place-r">₹{avg:,}<small>/क्विंटल</small></div>'
                if avg else '<div class="place-r">भाव देखें →</div>')
        cards.append(f"""<a class="place" href="/bhav/{cs}/{ss}">
<div class="place-n">{escape(_hindi_state(sn))}</div>
<div class="place-en">{escape(sn)}</div>
{rate}
<div class="place-s">{n} जिले</div>
</a>""")

    # The highest-paying mandi in the country today — the reason to read this page
    # rather than bounce back to Google.
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
<span class="place"><a href="/bhav/{cs}/{_slugify(b_state)}/{_slugify(b_dist)}">{escape(best.get('market','-'))}</a>
<small>{escape(b_dist)}, {escape(_hindi_state(b_state))}</small></span>
<span class="gain">{_rupee(best.get('modal_price'))}<small>/क्विंटल</small></span>
</li></ul></section>"""

    lead = f"₹{st['avg']:,}" if st["avg"] else "—"
    photo = (f'<img class="answer-photo" src="{escape(_crop_image(commodity, 960))}" '
             f'alt="" aria-hidden="true" width="420" height="200">'
             if _has_photo(commodity) else "")

    faqs = [
        (f"आज {hi} का भाव क्या है?",
         (f"{today_hi} को देशभर की मंडियों में {hi} का औसत भाव ₹{st['avg']:,} प्रति क्विंटल है "
          f"(₹{st['lo']:,} से ₹{st['hi']:,} तक)। नीचे अपना राज्य चुनकर जिले का भाव देखें।"
          if st["avg"] and st["lo"] and st["hi"]
          else f"{hi} का राज्यवार भाव नीचे दिया गया है — अपना राज्य चुनें।")),
        (f"{hi} सबसे महंगा किस मंडी में बिक रहा है?",
         (f"आज सबसे ज्यादा भाव {best.get('market','-')} ({best.get('district','-')}, "
          f"{_hindi_state(best.get('state',''))}) में {_rupee(best.get('modal_price'))} प्रति क्विंटल दर्ज हुआ है।"
          if best else "मंडीवार भाव देखने के लिए अपना राज्य चुनें।")),
    ]
    faq_html, faq_ld = _faq(faqs)
    ld = _ld(faq_ld, _crumb_ld([("कृषि मित्र", f"{SITE}/"), ("मंडी भाव", f"{SITE}/bhav"),
                                (hi, canon)]))

    title = f"{hi} का भाव आज — {commodity} Price Today सभी राज्य | कृषि मित्र"
    desc = (f"{today_hi}: {hi} ({commodity}) का ताजा मंडी भाव — "
            + (f"औसत ₹{st['avg']:,}/क्विंटल। " if st["avg"] else "")
            + f"{len(state_map)} राज्यों की मंडियों के रेट। राज्य चुनकर अपने जिले का भाव देखें।")

    body = f"""<section class="answer">
{photo}
<div class="answer-in">
<h1>आज का {escape(hi)} भाव — राज्य चुनें</h1>
<p class="answer-sub">📅 {today_hi} · {_mandis_gen(st['n'])} की सरकारी रिपोर्ट · पूरे भारत का औसत</p>
<div class="answer-price">
<div class="answer-rupee">{lead}<small>/क्विंटल</small></div>
</div>
<div class="answer-range">
<div><span>न्यूनतम</span><b>{f"₹{st['lo']:,}" if st['lo'] else '—'}</b></div>
<div><span>अधिकतम</span><b>{f"₹{st['hi']:,}" if st['hi'] else '—'}</b></div>
<div><span>राज्य</span><b>{len(state_map)}</b></div>
</div>
</div>
</section>
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
    dist_avg = _avg_by(rows, "district")

    cards = []
    for ds, dn in sorted(dist_map.items(), key=lambda kv: kv[1]):
        avg = dist_avg.get(dn)
        rate = (f'<div class="place-r">₹{avg:,}<small>/क्विंटल</small></div>'
                if avg else '<div class="place-r">भाव देखें →</div>')
        cards.append(f"""<a class="place" href="/bhav/{cs}/{ss}/{ds}">
<div class="place-n">{escape(dn)}</div>
{rate}
</a>""")

    # Top-paying mandis in this state — the money question, answered up front.
    top = sorted((r for r in rows if _num(r.get("modal_price"))),
                 key=lambda r: _num(r["modal_price"]), reverse=True)[:5]
    top_html = ""
    if top:
        items = "".join(
            f'<li><span class="place"><a href="/bhav/{cs}/{ss}/{_slugify(r.get("district",""))}">'
            f'{escape(r.get("market","-"))}</a><small>{escape(r.get("district","-"))}</small></span>'
            f'<span class="gain">{_rupee(r.get("modal_price"))}<small>/क्विंटल</small></span></li>'
            for r in top)
        top_html = f"""<section class="better">
<h2>🏆 {escape(hi_state)} में आज सबसे ज्यादा {escape(hi)} भाव</h2>
<p class="better-sub">भेजने से पहले मंडी की दूरी और भाड़ा ज़रूर जोड़ें</p>
<ul>{items}</ul></section>"""

    lead = f"₹{st['avg']:,}" if st["avg"] else "—"
    photo = (f'<img class="answer-photo" src="{escape(_crop_image(commodity, 960))}" '
             f'alt="" aria-hidden="true" width="420" height="200">'
             if _has_photo(commodity) else "")

    faqs = [
        (f"आज {hi_state} में {hi} का भाव क्या है?",
         (f"{today_hi} को {hi_state} की मंडियों में {hi} का औसत भाव ₹{st['avg']:,} प्रति क्विंटल है "
          f"(₹{st['lo']:,} से ₹{st['hi']:,} तक), {_mandis_gen(st['n'])} की रिपोर्ट के आधार पर।"
          if st["avg"] and st["lo"] and st["hi"]
          else f"{hi_state} में {hi} का जिलेवार भाव नीचे दिया गया है।")),
        (f"{hi_state} में {hi} सबसे महंगा कहां बिक रहा है?",
         (f"आज {top[0].get('market','-')} ({top[0].get('district','-')}) मंडी में सबसे ज्यादा "
          f"{_rupee(top[0].get('modal_price'))} प्रति क्विंटल भाव मिल रहा है।"
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
<p class="answer-sub">📅 {today_hi} · {_mandis_gen(st['n'])} की सरकारी रिपोर्ट</p>
<div class="answer-price">
<div class="answer-rupee">{lead}<small>/क्विंटल</small></div>
</div>
<div class="answer-range">
<div><span>न्यूनतम</span><b>{f"₹{st['lo']:,}" if st['lo'] else '—'}</b></div>
<div><span>अधिकतम</span><b>{f"₹{st['hi']:,}" if st['hi'] else '—'}</b></div>
<div><span>जिले</span><b>{len(dist_map)}</b></div>
</div>
</div>
</section>
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
                f'<li><span class="place">'
                f'<a href="/bhav/{cs}/{ss}/{_slugify(dn)}">{escape(dn)}</a>'
                f'<small>{escape(hi_state)}</small></span>'
                f'<span class="gain">₹{avg:,}<small>+₹{diff:,} ज्यादा</small></span></li>'
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
<ul><li><span class="place">{escape(hi_state)} के किसी और जिले में {escape(hi)} का
इससे बेहतर भाव नहीं मिल रहा।</span></li></ul></section>"""

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

    wa_text = quote(f"आज {district} में {hi} का भाव"
                    + (f" — औसत ₹{st['avg']:,}/क्विंटल" if st["avg"] else "")
                    + f" ({today_hi})\n{canon}")

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
</div>
</section>

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
<a class="btn btn-wa" href="https://wa.me/?text={wa_text}">📲 WhatsApp पर भाव भेजें</a>
</div>

<h2>अक्सर पूछे जाने वाले सवाल</h2>
{faq_html}
{_related_links(cs, ss, ds, commodity, district)}"""

    crumbs = (f'<a href="{SITE}/">कृषि मित्र</a> › <a href="{SITE}/bhav">मंडी भाव</a> › '
              f'<a href="{SITE}/bhav/{cs}">{escape(hi)}</a> › '
              f'<a href="{SITE}/bhav/{cs}/{ss}">{escape(hi_state)}</a> › {escape(district)}')
    return _doc(title, desc, canon, crumbs, body, ld, _crop_image(commodity, 960))
