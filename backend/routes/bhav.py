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
# Pages exist ONLY for combos that reported within the mandi_price_history
# window (~30 days), so we never publish thin/empty doorway pages, and every
# hub carries real derived content (ranges, top-paying mandis) rather than
# being a bare grid of links. A district that ages out of the ~7-day snapshot
# keeps serving its last reported day from history — a URL Google indexed
# must not start 404ing just because a market skipped a week.
# ============================================================

import calendar
import json as _json
import os
import re
import statistics
import time
from datetime import date, datetime, timedelta
from email.utils import formatdate
from functools import lru_cache
from html import escape
from urllib.parse import quote, urlencode, urlparse

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy import func

from backend.database.db import (SessionLocal, BazarPost, CropAppeal, MandiPrice,
                                 MandiLastSeen, MandiPriceHistory, User, UserProfile,
                                 acct)
from backend.services.mandi_service import get_mandi_prices, _row_to_dict
from backend.services import (
    affiliate, buyers, crop_types, district_geo, ecosystem, freight,
    index_gate, lead_clicks, leads, legal, msp, placements,
    rental as rental_svc, state_lang, wa_channels as _wa_channels,
)
# services/sponsors.py is gitignored while /sponsor is held back pending a
# hand-check of its figures. None means no sponsor slot renders anywhere and
# /go/s/ sends people home — which is this site's state today anyway, since the
# registry ships empty. Drop the guard when the page ships.
try:
    from backend.services import sponsors
except ImportError:
    sponsors = None
from backend.routes import bazar
from backend.routes.share import (_crop_image, _HI_CROP_EN, _TILES,
                                  _STAPLE_TILES_N)

import logging
logger = logging.getLogger("krishi.bhav")

_FRONTEND_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "frontend")


def _asset(name: str) -> str:
    """'/name?v=<mtime>' — the file's modified-time busts the browser cache the
    instant the asset changes, so a shipped JS/CSS update never runs against a
    stale cached copy (the classic 'new HTML calls a param the old script ignores'
    bug). Automatic — no version string to bump by hand. Bare path if unstattable."""
    rel = name.lstrip("/")
    try:
        return f"/{rel}?v={int(os.path.getmtime(os.path.join(_FRONTEND_DIR, rel)))}"
    except OSError:
        return f"/{rel}"

router = APIRouter()

SITE = "https://krashimitra.in"

# ── AdSense placement lives in frontend/ads.js, not here. This module renders
# ~14k pages and product.py reuses the same shell, so a hard-coded unit could
# only ever be "one slot, same spot, every page" — which is exactly what it was
# (a single unit below the content, the lowest-earning position on the site's
# highest-traffic pages). ads.js reads the rendered page instead and places
# units by content rules: below the fold, below the CTA, spaced, capped, lazy,
# and self-collapsing when unfilled. Loaded from _header() below. ──

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

# The long tail, filled in from Search Console rather than from a dictionary.
# _hindi_name falls back to the raw Agmarknet string, so a crop missing from the
# tables above was titled in English on all four tiers — "Sugar का भाव आज Mumbai
# मंडी में" for a farmer who searched "साखर भाव आज". 215 of the 323 commodities
# that earned an impression in the 28 days to 3 Sep 2026 had no Hindi name, and
# they converted at 0.54% against 0.74% for the ones that did: same template,
# same positions, the crop word was the only difference. Sugar alone was 10,740
# impressions at 0.22%.
#
# Ordering is load-bearing — the fallback scan below returns the FIRST keyword
# that matches, so a specific name has to be inserted before the general one it
# contains: "guar seed" before "guar", "elephant yam" before "yam", "methi
# seeds" before "methi", "cluster beans"/"french beans" before "beans". The
# same rule is why "sugar beet" is listed even though the feed has never sent
# it: "sugar" now resolves to चीनी, and a beet titled "चीनी" is the Turnip →
# अरहर bug again.
#
# Only names that are certain are here. A crop whose Hindi name could not be
# established (Gulli, Kakada, Chena, Buttery) keeps its English title, because
# a confidently wrong crop name costs more than an English one.
_EN_HI.update({
    # specific-before-general (see note above)
    "guar seed": "ग्वार बीज", "cluster beans": "ग्वार",
    "elephant yam": "सूरन (जिमीकंद)",
    "methi seeds": "मेथी दाना",
    "french beans": "फ्रेंच बीन्स",
    "sugar beet": "चुकंदर",
    "rab": "राब (तरल गुड़)",

    # the volume: >300 impressions/month each
    "sugar": "चीनी", "mentha oil": "मेंथा तेल",
    "khandsari": "खांडसारी (देसी खांड)",
    "wood": "लकड़ी", "firewood": "जलाऊ लकड़ी",
    "guar": "ग्वार",
    "cucumbar": "खीरा", "cucumber": "खीरा",
    "jaggery": "गुड़", "jute": "जूट", "ragi": "रागी",
    "tinda": "टिंडा", "makhana": "मखाना",
    "pointed gourd": "परवल", "methi": "मेथी",
    "fish": "मछली", "mahua": "महुआ", "pineapple": "अनानास",
    "almond": "बादाम", "taramira": "तारामीरा",
    "cummin seed": "जीरा", "cumin": "जीरा",
    "little gourd": "कुंदरू", "amla": "आंवला",
    "beetroot": "चुकंदर", "colacasia": "अरबी", "kiwi": "कीवी",

    # the tail — smaller, but the same defect
    "gokhru": "गोखरू", "arecanut": "सुपारी", "betelnuts": "सुपारी",
    "dhaincha": "ढैंचा", "chiaseeds": "चिया बीज",
    "linseed": "अलसी", "kutki": "कुटकी", "kodo millet": "कोदो",
    "quinoa": "क्विनोआ", "soanf": "सौंफ", "sponge gourd": "नेनुआ",
    "cherry": "चेरी", "maida": "मैदा", "dal mix": "मिक्स दाल",
    "chicory": "कासनी", "tobacco": "तंबाकू", "yam": "रतालू",
    "ajwan": "अजवाइन", "castor seed": "अरंडी", "niger seed": "रामतिल",
    "long melon": "ककड़ी", "mashrooms": "मशरूम", "mushroom": "मशरूम",
    "ghee": "घी", "water melon": "तरबूज", "watermelon": "तरबूज",
    "rajgir": "राजगीरा", "plum": "आलूबुखारा",
    "asalia": "हलीम (चंद्रशूर)", "chandrashoor": "चंद्रशूर",
    "teora": "खेसारी (लाख)",
    "ridge gourd": "तोरई", "water chestnut": "सिंघाड़ा",
    "walnut": "अखरोट", "cloves": "लौंग", "bay leaf": "तेजपत्ता",
    "asparagus": "शतावरी", "apricot": "खुबानी", "tamarind": "इमली",
    "blueberry": "ब्लूबेरी", "cashewnuts": "काजू",
    "pepper garbled": "काली मिर्च", "pepper ungarbled": "काली मिर्च",
    "tube rose": "रजनीगंधा", "tulip": "ट्यूलिप",
    "heena": "मेहंदी", "mahedi": "मेहंदी", "nagarmotha": "नागरमोथा",
    "harrah": "हरड़", "karanja seeds": "करंज बीज", "gond": "गोंद",
    "amranthas": "चौलाई", "amaranthus": "चौलाई",
    "field bean": "सेम", "beans": "सेम",
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

# Axis labels for the 12-month seasonality chart. Written out rather than
# sliced from _HI_MONTHS: Devanagari is not one grapheme per character, so
# "अप्रैल"[:3] cuts mid-cluster and renders as the broken "अप्".
_HI_MON_SHORT = ["जन", "फर", "मार्च", "अप्रैल", "मई", "जून", "जुला",
                 "अग", "सित", "अक्टू", "नव", "दिस"]


def _kw_in(text: str, keyword: str) -> bool:
    """Whole-word keyword match. A plain `keyword in text` is what made "Turnip"
    match the "tur" (अरहर) keyword and "Peach"/"Pear" match "pea" — so a turnip page
    was titled "अरहर का भाव". The boundary keeps "Wheat(Desi)" → गेहूं working while
    refusing to match a keyword that merely sits inside a longer word."""
    return re.search(rf"\b{re.escape(keyword)}\b", text) is not None


@lru_cache(maxsize=2048)
def _hindi_name(commodity: str) -> str:
    """Best-effort Hindi display name; falls back to the English name.

    Cached — the fallback path below is a full scan of _EN_HI (115 entries)
    with a regex search per entry, and ~3/4 of the ~320 distinct commodities in
    the index miss the fast exact-match branch and hit it. It's called once per
    crop inside a sort key on every tier-2/3/4 page render, so uncached this
    was measured at ~200ms/page even on a fast dev machine — the domain here
    is a few hundred fixed strings, so a cache turns every repeat call after
    the first (i.e. almost all of them) into a dict lookup."""
    cl = (commodity or "").lower()
    if cl in _EN_HI:                        # exact name (incl. the variants above)
        return _EN_HI[cl]
    for en, hi in _EN_HI.items():           # whole-word match: "Wheat(Desi)" → गेहूं
        if _kw_in(cl, en):
            return hi
    return commodity


def _hindi_state(state: str) -> str:
    return _HI_STATES.get(state, state)


# ── Hindi district names ─────────────────────────────────────
# Measured, not assumed. Over the 28 days to 3 Sep 2026, district pages whose
# searcher spelled the district in Latin ("sehore mandi lahsun bhav") clicked at
# 0.97%; the ones who spelled it in Devanagari ("सीहोर मंडी लहसुन भाव आज का")
# clicked at 0.36% — at the SAME average position, 7.7 to 7.7. Position was not
# the variable. The title was: it said "Sehore", and 17,618 of the 25,168
# attributed impressions came from people who had typed सीहोर.
#
# The names themselves already existed — naksha_states.json carries {hi, en} for
# all 737 districts, built for the map pages — so this is a lookup that /bhav
# never did, not new data.
#
# The two feeds disagree on spelling (Agmarknet sends "Pillibhit", "Bulandshahar",
# "Khiri (Lakhimpur)"), so names are folded onto a loose key: brackets dropped,
# doubled vowels collapsed, aspirates flattened, h removed. That is deliberately
# aggressive, which makes a false MATCH the risk worth guarding — labelling
# Bilaspur "बालाघाट" is the Turnip → अरहर bug with a place name. So the builder
# drops any key two different districts in one state fold onto, and an unmatched
# district keeps its Latin name. Wrong is worse than English; English is what
# the page said yesterday.
_NAKSHA_STATE_KEY = {
    "chattisgarh": "chhattisgarh", "keralam": "kerala", "nct-of-delhi": "delhi",
    "uttrakhand": "uttarakhand", "pondicherry": "puducherry",
    "andaman-and-nicobar": "andaman-and-nicobar-islands",
}

# Districts Agmarknet names differently enough that the fold cannot reach them —
# renamed cities (Gurgaon → गुरुग्राम, Bengaluru, Ahilyanagar), districts sent as
# their headquarters town (Chhapra for Saran, Orai for Jalaun, Narnaul for
# Mahendragarh), and the bare "Kanpur"/"Lakhimpur" the census splits in two.
_HI_DIST_ALIAS = {
    ("uttar-pradesh", "kanpur"): "कानपुर",
    ("uttar-pradesh", "khiri-lakhimpur"): "लखीमपुर खीरी",
    ("uttar-pradesh", "lakhimpur"): "लखीमपुर खीरी",
    ("uttar-pradesh", "badaun"): "बदायूं",
    ("uttar-pradesh", "mau-maunathbhanjan"): "मऊ",
    ("uttar-pradesh", "kannuj"): "कन्नौज",
    ("uttar-pradesh", "jalaun-orai"): "जालौन",
    ("haryana", "gurgaon"): "गुरुग्राम",
    ("haryana", "mahendragarh-narnaul"): "महेंद्रगढ़",
    ("karnataka", "bengaluru"): "बेंगलुरु",
    ("maharashtra", "ahilyanagar"): "अहिल्यानगर",
    ("maharashtra", "amarawati"): "अमरावती",
    ("bihar", "chhapra"): "छपरा",
    ("bihar", "east-champaran-motihari"): "पूर्वी चंपारण",
    ("rajasthan", "swai-madhopur"): "सवाई माधोपुर",
    ("punjab", "mohali"): "मोहाली",
    ("madhya-pradesh", "badwani"): "बड़वानी",
    ("gujarat", "vadodara-baroda"): "वडोदरा",
    ("gujarat", "banaskanth"): "बनासकांठा",
    ("gujarat", "junagarh"): "जूनागढ़",
    ("rajasthan", "deeg"): "डीग",
    ("rajasthan", "beawar"): "ब्यावर",
    ("punjab", "nawanshahr"): "नवांशहर",
    ("punjab", "ropar-rupnagar"): "रूपनगर",
    ("punjab", "ferozpur"): "फिरोजपुर",
    ("karnataka", "bengaluru-south"): "बेंगलुरु दक्षिण",
    ("maharashtra", "dharashiv"): "धाराशिव",
    ("keralam", "kozhikode-calicut"): "कोझिकोड",
}


def _dist_key(name: str) -> str:
    """Fold one district name to a key both feeds' spellings land on."""
    s = re.sub(r"\(.*?\)", " ", name or "").lower()
    s = re.sub(r"[^a-z]+", "", s)
    for a, b in (("ee", "i"), ("oo", "u"), ("aa", "a"), ("bh", "b"), ("dh", "d"),
                 ("kh", "k"), ("gh", "g"), ("ph", "f"), ("th", "t"), ("sh", "s"),
                 ("z", "j"), ("w", "v"), ("y", "i")):
        s = s.replace(a, b)
    # Doubled letters last: it is what joins "Pillibhit" to "Pilibhit" and
    # "Raebarelli" to "Rae Bareli". Checked against all 737 districts — no two
    # in one state collide on it, so it costs nothing to fold.
    return re.sub(r"(.)\1+", r"\1", s.replace("h", ""))


@lru_cache(maxsize=1)
def _dist_hi_map() -> dict:
    """(state slug, folded district key) → Hindi name, from naksha_states.json.

    Ambiguous keys are dropped rather than guessed at — see the note above."""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "naksha_states.json")
    try:
        with open(path, encoding="utf-8") as fh:
            states = _json.load(fh).get("states", {})
    except (OSError, ValueError):
        logger.warning("naksha_states.json unreadable — districts stay in Latin")
        return {}

    out, dropped = {}, set()
    for s_key, st in states.items():
        for d in st.get("districts", []):
            k = (s_key, _dist_key(d.get("en", "")))
            if not k[1]:
                continue
            if k in out and out[k] != d.get("hi"):
                dropped.add(k)                  # two districts, one key — unusable
            out[k] = d.get("hi", "")
    for k in dropped:
        out.pop(k, None)
    return out


def _hindi_district(state: str, district: str) -> str:
    """Hindi name for a district, or the name unchanged when there is no match."""
    if not district:
        return district
    ss = _slugify(state)
    ss = _NAKSHA_STATE_KEY.get(ss, ss)
    alias = _HI_DIST_ALIAS.get((_slugify(state), _slugify(district)))
    if alias:
        return alias
    return _dist_hi_map().get((ss, _dist_key(district))) or district


def _en_short(commodity: str) -> str:
    """The English display name for a <title>, kept short enough to survive the SERP.

    Agmarknet ships slash-joined synonym lists — "Red Gram Split/Arhar Dal/Tur
    Dal" is one commodity, not three. Dropped verbatim into a title that already
    carries the Hindi name, a state and a district, it pushed the longest titles
    past 120 characters, so Google cut them mid-word. The first variant is the
    portal's primary name, so it is the one worth keeping.

    Only top-level slashes split: "Ridge Gourd(Permal/Hybrid Gourd)" is one name
    whose slash sits inside the bracket, and cutting there leaves the unbalanced
    "Ridge Gourd(Permal". The English name has to survive intact because it is
    what separates the 13 commodity groups that share a Hindi name (Pumpkin,
    Sweet Pumpkin and White Pumpkin are all कद्दू) — drop it and those pages
    would collide on one title."""
    name, depth = (commodity or "").strip(), 0
    for i, ch in enumerate(name):
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        elif ch == "/" and depth == 0:
            return name[:i].strip()
    return name


def _title_names(commodity: str) -> tuple[str, str, bool]:
    """(Hindi name, English name, they-are-the-same) for a <title>/description.

    _hindi_name falls back to the English string for a crop it has no entry for,
    so the bilingual templates printed one long name twice — "Other green and
    fresh vegetables का भाव — Other green and fresh vegetables Price" was 80
    characters of which half was a repeat. When there is no real translation,
    both slots collapse to the short English name and the caller's last _fit
    variant drops the now-redundant English clause."""
    en = _en_short(commodity)
    hi = _hindi_name(commodity)
    return (en, en, True) if hi == commodity else (hi, en, False)


def _ambiguous_district(idx: dict, c_slug: str, d_slug: str) -> bool:
    """True when this district name also exists in another state for this crop.

    Balrampur is in both UP and Chhattisgarh; Bilaspur in HP and Chhattisgarh;
    Hamirpur in UP and HP; Pratapgarh in UP and Rajasthan. A district-only
    <title> makes those two pages byte-identical, which is the one snippet
    defect that needs no traffic data to call a bug: Google folds duplicate
    titles together, and a farmer who does see both cannot tell which is his.

    Reads the index's own legacy map (district slug → states it appears in),
    which is already built for the tier-3 redirects, so this costs a dict
    lookup rather than a second pass over 14k combinations.
    """
    return len(idx.get("legacy", {}).get(c_slug, {}).get(d_slug, ())) > 1


def _fit(*variants: str, limit: int = 68) -> str:
    """The first variant that survives Google's SERP window (68 title, 162 desc).

    Crop, state and district names vary hugely in length ("आम" vs "बिनौला (कपास
    बीज)", "गोवा" vs "जम्मू और कश्मीर", "Bah" vs "Khairagarh Chhuikhadan
    Gandai"), so no single template fits all ~14k pages. Order the variants
    richest first: the connective words are dropped for the long combinations,
    while the crop, the place and the English name — the parts that actually
    rank — are present in every variant. Choosing a whole shorter sentence beats
    slicing the long one, which cuts mid-word."""
    for v in variants:
        if len(v) <= limit:
            return v
    return min(variants, key=len)


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


def _row_date_iso(s: str) -> str:
    """'11/07/2026' → '2026-07-11', so rendered rows can be compared and
    ordered by date. Anything unparseable sorts first (empty string)."""
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", (s or "").strip())
    return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}" if m else ""


def _newest_row_date(prices: list) -> str:
    """The newest 'DD/MM/YYYY' among rendered rows, or '-' if none parse."""
    best_iso, best_raw = "", "-"
    for p in prices:
        raw = p.get("date") or ""
        iso = _row_date_iso(raw)
        if iso and iso > best_iso:
            best_iso, best_raw = iso, raw
    return best_raw


def _fresh_iso(idx: dict, cs: str, ss: str, ds: str) -> str:
    """The same 'YYYY-MM-DD' idx["dates"] already gives /bhav/sitemap.xml's
    <lastmod> for this exact URL — reused here (not reparsed from `prices`) so
    a page's dateModified can never disagree with its own sitemap entry."""
    return idx.get("dates", {}).get(cs, {}).get(ss, {}).get(ds, "")


def _fresh_iso_state(idx: dict, cs: str, ss: str) -> str:
    """The newest reported date anywhere in one crop×state — the same rollup
    /bhav/sitemap.xml uses for a state's <lastmod> ("a state page is as fresh
    as its newest district"). Kept next to _fresh_iso so the two can never
    drift into disagreeing about what freshness means."""
    return max((idx.get("dates", {}).get(cs, {}).get(ss, {}) or {}).values(),
               default="")


def _as_of_hi(fresh_iso: str) -> str:
    """The date to print NEXT TO A PRICE — the date that price was reported,
    not today's.

    data.gov.in does not report every mandi every day: on 2026-08-05 roughly a
    quarter of district pages carried prices four or more days old, the worst
    seventeen days old. Every one of those pages still opened its own meta
    description with `_hindi_date(date.today())`, so the snippet Google showed
    read "5 अगस्त 2026: ... का ताजा भाव — औसत ₹800/क्विंटल" above a number last
    reported on 19 जुलाई. The page's dateModified said 19 जुलाई at the same
    time, so the page contradicted itself, and a farmer who clicked got
    seventeen-day-old prices under today's date.

    Falls back to today only when the page has no reported date at all, which
    is the one case where today is the honest answer (nothing claims
    otherwise).
    """
    try:
        return _hindi_date(date.fromisoformat(fresh_iso))
    except (TypeError, ValueError):
        return _hindi_date(date.today())


def _fresh_iso_crop(idx: dict, cs: str) -> str:
    """The newest reported date anywhere in one crop — the same rollup
    /bhav/sitemap.xml uses for a crop's <lastmod> ("a crop is as fresh as its
    newest state"). Completes the _fresh_iso/_fresh_iso_state pair so all
    three tiers date themselves from the same numbers the sitemap publishes."""
    return max((d for s_map in (idx.get("dates", {}).get(cs) or {}).values()
                for d in s_map.values()), default="")


def _fresh_iso_place(idx: dict, ss: str, ds: str = "") -> str:
    """The newest reported date anywhere in one state (or one district of it),
    across EVERY crop — the crop-less counterpart of _fresh_iso_state, for the
    /bhav/rajya place hubs, which have no single crop to date themselves from.

    Rolled up exactly the way /bhav/sitemap.xml rolls up a place hub's
    <lastmod> (same _is_crop filter, same max over idx["dates"]), for the
    reason given on _fresh_iso: a page's dateModified must never disagree with
    its own sitemap entry."""
    best = ""
    for cs, cn in idx.get("crops", {}).items():
        if not _is_crop(cn):
            continue
        d_map = idx.get("dates", {}).get(cs, {}).get(ss, {}) or {}
        got = d_map.get(ds, "") if ds else max(d_map.values(), default="")
        if got > best:
            best = got
    return best


# A price reported yesterday is the NORMAL case, not a fault: Agmarknet's live
# resource is wiped overnight and the 08:00 IST fetch legitimately rebuilds the
# snapshot from yesterday's archived day (see mandi_fetch_service). Saying
# "1 दिन पुराना" on half the site every morning would train farmers to ignore
# the badge, so it stays quiet for one day and speaks from two.
_AGE_QUIET_DAYS = 1


def _age_days(fresh_iso: str) -> int | None:
    """Calendar days between a page's newest reported price and today.
    None when the page carries no reported date at all."""
    try:
        return (date.today() - date.fromisoformat(fresh_iso)).days
    except (TypeError, ValueError):
        return None


def _age_note(fresh_iso: str) -> str:
    """The plain-Hindi "how old is this number", or "" while it is current.

    Carrying a quiet mandi's last known price forward is deliberate — a farmer
    wants a number, not a blank page — but nothing on tiers 2 and 3 ever said
    the number was carried. Those tiers dated themselves from the CLOCK
    (`_hindi_date(date.today())`) while the real date sat unused two lines away
    in idx["dates"], so on 4 Sep 2026 /bhav/cardamom/keralam printed
    "📅 4 सितंबर 2026 · ताजा भाव" over prices last reported on 17 अगस्त.

    This is the common case, not a corner: Agmarknet reports ~18k of the ~34k
    mandi×crop pairs the snapshot holds, so on that same day only 926 of 1,859
    crop×state combos had a price from today and 140 were over a week old.
    """
    n = _age_days(fresh_iso)
    return "" if n is None or n <= _AGE_QUIET_DAYS else f"{n} दिन पुराना भाव"


def _age_badge(fresh_iso: str) -> str:
    """_age_note as the amber pill the tier pages print beside their date."""
    note = _age_note(fresh_iso)
    return f'<span class="stale-pill">⏳ {note}</span>' if note else ""


# Agmarknet's commodity list carries a few non-crop items (livestock, fuel).
# They keep their own pages if someone lands on one, but they are never
# surfaced as "crops" in the hub, the sitemap, or the related-crop chips.
_NON_CROP = {"firewood", "wood", "coconut coir", "cock", "hen"}


@lru_cache(maxsize=2048)
def _is_crop(commodity: str) -> bool:
    return (commodity or "").strip().lower() not in _NON_CROP


@lru_cache(maxsize=2048)
def _tile_rank(commodity: str) -> int:
    """Position in _TILES — the same crop order as the app's mandi grid, so the hub
    opens on गेहूं/धान rather than whatever sorts first alphabetically.

    The MOST SPECIFIC keyword wins, not the first tile that matches. "Green
    Gram(Moong)(Whole)" matches both the generic "gram" (चना) tile and its own
    "green gram" (मूंग) tile; first-match handed मूंग and उड़द to the चना tile, where
    they lost to Bengal Gram and dropped off the hub entirely. Likewise "Red
    gram/Arhar/Tur(whole)" landed on चना, leaving the अरहर tile to be won by
    "Pegeon Pea(Arhar Fali)" — a 2-state vegetable standing in for a major pulse.

    Cached — this is the single most expensive call in the whole module: an
    UNCONDITIONAL scan of all 233 tiles × ~300 total keywords, one regex search
    each, every single time (it can't short-circuit — it wants the longest,
    not the first, match). It's called once per crop inside a sort key on
    every tier-2/3/4 page render (~320 distinct commodities), which alone
    measured at ~190ms/page on a fast dev machine — enough on its own to
    explain multi-second page loads on Render's constrained free-tier CPU.
    Safe to cache: pure function of a string over the fixed, static _TILES
    table, same reasoning as _hindi_name() above."""
    cl = (commodity or "").lower()
    best_rank, best_len = len(_TILES), 0
    for i, (keys, _file, _h) in enumerate(_TILES):
        for k in keys:
            if _kw_in(cl, k) and len(k) > best_len:
                best_rank, best_len = i, len(k)
    return best_rank


@lru_cache(maxsize=2048)
def _has_photo(commodity: str) -> bool:
    cl = (commodity or "").lower()
    return any(any(_kw_in(cl, k) for k in keys) for keys, _file, _h in _TILES)


def _mandis(n: int) -> str:
    return f"{n} मंडी" if n == 1 else f"{n} मंडियां"


def _mandis_gen(n: int) -> str:
    """Genitive: '1 मंडी की रिपोर्ट' but '5 मंडियों की रिपोर्ट'."""
    return f"{n} मंडी" if n == 1 else f"{n} मंडियों"


# ── Slug index ───────────────────────────────────────────────
# Built from a GROUP BY on the ~30-day history (snapshot only as a fresh-deploy
# fallback); refreshed every 6h (the feed moves once a day). Powers all four
# tiers, the sitemap and the legacy 301s. History rather than the snapshot on
# purpose: the snapshot ages a market out after ~7 unrefreshed days, which made
# URLs flap out of the sitemap — and 404 — while Google still had them indexed.
#   crops:   c_slug → commodity (LAST raw spelling seen — see raws)
#   raws:    c_slug → { every raw commodity spelling that maps to this slug };
#            crops[cs] alone loses all but one, which is how row lookups used
#            to miss and 404 pages the sitemap itself advertised
#   states:  c_slug → { s_slug → state }
#   dists:   c_slug → { s_slug → { d_slug → district } }
#   legacy:  c_slug → { d_slug → [s_slug, ...] }   — resolves the old 2-level URLs
#   dates:   c_slug → { s_slug → { d_slug → "YYYY-MM-DD" } } — newest arrival_dt
#            for that combo, i.e. the last day this page's data actually moved.
#            Feeds the sitemap <lastmod>: a district that stopped reporting
#            keeps its old date instead of claiming "today".
_index: dict = {}
_index_ts: float = 0.0
_INDEX_TTL = 6 * 3600

_IST_OFFSET = timedelta(hours=5, minutes=30)  # fetched_at is naive UTC


def _get_index() -> dict:
    global _index, _index_ts
    if _index and (time.time() - _index_ts) < _INDEX_TTL:
        return _index
    db = SessionLocal()
    try:
        # Read from mandi_last_seen, NOT from history: history is trimmed to
        # MANDI_HISTORY_DAYS, so a district that went quiet longer ago than that
        # would vanish from this index — and with it the /bhav URLs the sitemap
        # advertises. last_seen keeps one permanent row per combination, so the
        # URL set only ever grows. (~12k groups vs a group-by over 179k rows.)
        rows = [(c, s, d, dt.isoformat() if dt else "")
                for c, s, d, dt in
                (db.query(MandiLastSeen.commodity, MandiLastSeen.state,
                          MandiLastSeen.district,
                          func.max(MandiLastSeen.arrival_dt))
                   .filter(MandiLastSeen.commodity.isnot(None),
                           MandiLastSeen.state.isnot(None),
                           MandiLastSeen.district.isnot(None))
                   .group_by(MandiLastSeen.commodity, MandiLastSeen.state,
                             MandiLastSeen.district)
                   .all())]
        if not rows:            # fresh deploy before the first fetch has run
            rows = [(c, s, d, (f + _IST_OFFSET).date().isoformat() if f else "")
                    for c, s, d, f in
                    (db.query(MandiPrice.commodity, MandiPrice.state,
                              MandiPrice.district, func.max(MandiPrice.fetched_at))
                       .filter(MandiPrice.commodity.isnot(None),
                               MandiPrice.state.isnot(None),
                               MandiPrice.district.isnot(None))
                       .group_by(MandiPrice.commodity, MandiPrice.state,
                                 MandiPrice.district)
                       .all())]
    finally:
        db.close()

    crops, states, dists, legacy, dates, raws = {}, {}, {}, {}, {}, {}
    for commodity, state, district, d_iso in rows:
        cs, ss, ds = _slugify(commodity), _slugify(state), _slugify(district)
        if not (cs and ss and ds):
            continue
        crops[cs] = commodity
        raws.setdefault(cs, set()).add(commodity)
        states.setdefault(cs, {})[ss] = state
        dists.setdefault(cs, {}).setdefault(ss, {})[ds] = district
        legacy.setdefault(cs, {}).setdefault(ds, [])
        if ss not in legacy[cs][ds]:
            legacy[cs][ds].append(ss)
        if d_iso:
            slot = dates.setdefault(cs, {}).setdefault(ss, {})
            # slugify can merge two raw combos onto one slug → keep the newest
            if d_iso > slot.get(ds, ""):
                slot[ds] = d_iso

    if crops:                   # keep the stale index if the DB comes back empty
        _index = {"crops": crops, "states": states, "dists": dists,
                  "legacy": legacy, "dates": dates, "raws": raws}
        _index_ts = time.time()
    return _index


def _rows_for(commodity: str, state: str = "", district: str = "") -> list:
    """Every matching row — NOT get_mandi_prices(), which caps at 50 rows when a
    commodity is given. That cap is fine for the app's district view but silently
    truncates these pages: Uttar Pradesh alone has 68 wheat districts, so a 50-row
    sample left most district tiles priceless, skewed the state average, and — worst
    — computed "the highest-paying mandi" from an arbitrary subset, which could miss
    the actual best mandi. The aggregates here must see the whole state/country.

    func.lower(col) == value.lower(), NOT .ilike(value) — this is THE query every
    tier-4 page load (and every tier2/3/4-extras lazy fetch) depends on, and it's
    exactly what mandi_prices_csd_lower_idx (db.py) exists to serve. Postgres will
    NOT match a `lower(col)` expression index against an ILIKE predicate — even a
    plain literal with no wildcards — only against a literal `lower(col) = ...`
    clause. Written as .ilike(), this was a full table scan on every request no
    matter how the index was defined."""
    db = SessionLocal()
    try:
        q = db.query(MandiPrice)
        if commodity:
            q = q.filter(func.lower(MandiPrice.commodity) == commodity.lower())
        if state:
            q = q.filter(func.lower(MandiPrice.state) == state.lower())
        if district:
            q = q.filter(func.lower(MandiPrice.district) == district.lower())
        rows = q.all()
    finally:
        db.close()

    if rows:
        return [_row_to_dict(r) for r in rows]
    # DB empty (fresh deploy) → fall back to the service's JSON seed path
    data = get_mandi_prices(commodity, district, state)
    return (data or {}).get("prices") or []


def _hist_to_dict(h) -> dict:
    """Render a history OR last-seen row. Both carry the same columns; neither
    carries a delta/spark, so the page simply skips the arrow and sparkline,
    and everything else renders the same."""
    return {
        "market":           h.market or "-",
        "district":         h.district or "-",
        "state":            h.state or "-",
        "commodity":        h.commodity or "-",
        "variety":          h.variety or "-",
        "grade":            h.grade or "-",
        "min_price":        str(h.min_price or "-"),
        "max_price":        str(h.max_price or "-"),
        "modal_price":      str(h.modal_price or "-"),
        "prev_modal_price": None,
        "change_pct":       None,
        "spark":            [],
        "date":             h.arrival_date or "-",
    }


def _rows_for_district(idx: dict, cs: str, ss: str, ds: str) -> list:
    """Slug-space rescue for the tier-3 page, tried when _rows_for() comes back
    empty for a combo the index says exists.

    _rows_for compares raw strings, but the index keeps only the LAST raw
    spelling per slug — when Agmarknet ships two spellings that collapse onto
    one slug, the stored triple matches zero rows and a URL the sitemap itself
    advertises used to 404. So: query the snapshot by EVERY raw spelling of
    the crop and compare state/district as slugs — the same space the sitemap
    is built in. If the combo has aged out of the snapshot entirely, serve the
    last price we ever saw (mandi_last_seen) under its real arrival date, so an
    indexed URL keeps answering FOREVER instead of bouncing Google (or a
    farmer) off a 404. This used to read mandi_price_history and so only held
    for the retention window; last_seen has no window."""
    names = sorted(idx.get("raws", {}).get(cs) or {idx["crops"][cs]})
    db = SessionLocal()
    try:
        snap = db.query(MandiPrice).filter(MandiPrice.commodity.in_(names)).all()
        snap = [r for r in snap
                if _slugify(r.state) == ss and _slugify(r.district) == ds]
        if snap:
            return [_row_to_dict(r) for r in snap]

        seen = (db.query(MandiLastSeen)
                  .filter(MandiLastSeen.commodity.in_(names),
                          MandiLastSeen.state.ilike(idx["states"][cs][ss]),
                          MandiLastSeen.district.ilike(idx["dists"][cs][ss][ds]))
                  .order_by(MandiLastSeen.arrival_dt.desc())
                  .limit(500)
                  .all())
        seen = [h for h in seen
                if _slugify(h.state) == ss and _slugify(h.district) == ds]
        if not seen:
            return []
        # Serve one day's worth — the newest this district ever reported — so
        # the page shows a coherent set of mandis rather than a mix of dates.
        dated = [h for h in seen if h.arrival_dt]
        if not dated:
            return [_hist_to_dict(h) for h in seen]
        newest = max(h.arrival_dt for h in dated)
        return [_hist_to_dict(h) for h in dated if h.arrival_dt == newest]
    finally:
        db.close()


# ── the district trend line ──────────────────────────────────
# How far back the chart looks, in CALENDAR days. Deliberately days and not
# data points — see _district_series. Capped below mandi_price_history's
# ~15-day retention so the window is always fully covered by real rows.
CHART_DAYS = 10


def _mkt_ident(commodity, market, variety, grade) -> tuple:
    """The identity of one priced line-item, lowercased, with the renderer's '-'
    placeholder read back as the empty string it stands for.

    This is what joins a rendered snapshot row to its own rows in
    mandi_price_history. It is deliberately NOT the md5 group_key those tables
    share: group_key cannot be recomputed from a rendered row, because
    _row_to_dict turns a missing variety/grade into '-' while _group_key hashed
    the same field as ''. Two rows that are the same line-item would hash apart.
    """
    def n(v):
        s = ("" if v is None else str(v)).strip().lower()
        return "" if s == "-" else s
    return (n(commodity), n(market), n(variety), n(grade))


def _district_series(prices: list, end_iso: str, today_avg) -> list[int]:
    """The district's own average modal price, one point per calendar day.

    This used to be `max(sparks, key=len)` — the single mandi+variety with the
    longest run of reports, drawn under a heading naming the whole district.
    Three separate untruths came out of that, all visible on Bijnor wheat on
    6 Aug 2026:

      * the line ended at ₹2,650 (Bijnaur APMC's "Other" variety) while the
        price panel directly above it read ₹2,615 (the district average), so
        the page contradicted itself in the two places a farmer actually looks;
      * `spark` holds the last ~8 REPORTS, not the last 8 days, so a mandi that
        trades twice a week drew a "4-दिन रुझान" spanning a fortnight, and the
        axis label counted points rather than days on top of that;
      * ties in `max(..., key=len)` broke on list order, so which single mandi
        got to speak for the district changed with the row ordering.

    So instead: read this district's history, bucket it by arrival date, and
    average across the SAME line-items the page lists — one value per item per
    day. A day an item did not report carries its previous rate forward, which
    is exactly what the snapshot itself does ("जिन मंडियों की रिपोर्ट आज नहीं
    आई, उनका पिछला भाव दिखता है"), and days before its first report carry the
    first rate backward. Both fills exist for the same reason: the set of
    mandis behind every point must be identical, or the line moves when the
    *composition* changes rather than when a price does.

    The last point is then forced to the panel's own average, so the chart, the
    headline and the sell-signal can never disagree again.

    Returns [] when the history is too thin to draw anything honest — fewer
    than two reporting days, or a span under three days. The per-mandi
    sparklines on the cards still carry the movement in that case.

    One extra district-scoped query per tier-4 render, served by
    mandi_history_csd_dt_idx (commodity, state, district, arrival_dt DESC).
    """
    latest, order = {}, []
    for p in prices:
        m = _num(p.get("modal_price"))
        if not m:
            continue
        k = _mkt_ident(p.get("commodity"), p.get("market"),
                       p.get("variety"), p.get("grade"))
        if k not in latest:
            order.append(k)
        latest[k] = m
    if not latest or not today_avg:
        return []
    try:
        end = date.fromisoformat(end_iso)
    except (TypeError, ValueError):
        return []                       # no reported date → nothing to date a chart by

    state    = prices[0].get("state") or ""
    district = prices[0].get("district") or ""
    names    = sorted({p.get("commodity") for p in prices if p.get("commodity")})

    db = SessionLocal()
    try:
        rows = (db.query(MandiPriceHistory.commodity, MandiPriceHistory.market,
                         MandiPriceHistory.variety, MandiPriceHistory.grade,
                         MandiPriceHistory.arrival_dt, MandiPriceHistory.modal_price)
                  .filter(MandiPriceHistory.commodity.in_(names),
                          MandiPriceHistory.state == state,
                          MandiPriceHistory.district == district,
                          MandiPriceHistory.arrival_dt >= end - timedelta(days=CHART_DAYS - 1),
                          MandiPriceHistory.arrival_dt <= end)
                  .all())
    except Exception as exc:
        logger.warning("district trend query failed (%s, %s): %s", district, state, exc)
        return []
    finally:
        db.close()

    seen: dict[tuple, dict] = {}
    for com, mkt, var, grd, dt, modal in rows:
        k, m = _mkt_ident(com, mkt, var, grd), _num(modal)
        if dt and m and k in latest:
            seen.setdefault(k, {})[dt] = m

    obs = {d for hist in seen.values() for d in hist}
    if len(obs) < 2:
        return []                       # a single reporting day is not a trend
    start = min(obs)                    # start where the data does — never pad
    span  = (end - start).days          # a flat lead-in onto the front of the line
    if span < 2:
        return []                       # _chart needs three points to say anything

    days = [start + timedelta(days=i) for i in range(span + 1)]
    cols = []
    for k in order:
        hist = seen.get(k) or {}
        col  = [hist.get(d) for d in days]
        col[-1] = latest[k]             # the snapshot IS the rate its card shows
        carry = None
        for i, v in enumerate(col):     # forward-fill: didn't report → last rate holds
            if v is None:
                col[i] = carry
            else:
                carry = v
        carry = None
        for i in range(len(col) - 1, -1, -1):   # backward-fill the lead-in, so the
            if col[i] is None:                  # same mandis sit behind every point
                col[i] = carry
            else:
                carry = col[i]
        cols.append(col)

    series = []
    for i in range(len(days)):
        vals = [c[i] for c in cols if c[i]]
        series.append(round(sum(vals) / len(vals)) if vals else None)
    if any(v is None for v in series):
        return []
    series[-1] = today_avg              # the chart ends on the number in the panel
    return series


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


def _sell_signal(series: list, today_avg, avg_pct) -> str:
    """A compact 'sell today or wait?' strip that sits INSIDE the green price
    panel, right by the rate.

    Compares today's average modal against this district's own recent daily
    average and its day-on-day move. It is a *read of the past*, not a forecast —
    the copy states the fact and gives a gentle, non-speculative nudge, never a
    price prediction. Renders nothing when the history is too thin (<3 days) to
    say anything honest. Pure compute on data already in memory.

    `series` MUST be the district-wide series from _district_series, on the same
    basis as `today_avg`. It used to be one mandi+variety's spark while
    today_avg was the district average, so the strip printed "4-दिन औसत ₹2,651"
    (one variety at one mandi) next to a headline of ₹2,615 (four rows across
    three mandis) and picked its 🟢/🟡/🔵 verdict by comparing the two.
    """
    hist = [v for v in series if v]
    if len(hist) < 3 or not today_avg:
        return ""                       # too little history to be honest
    n_days   = len(hist)
    week_avg = round(sum(hist) / n_days)
    diff_pct = ((today_avg - week_avg) / week_avg * 100) if week_avg else 0

    move = (f" · कल से {'+' if avg_pct > 0 else ''}{avg_pct:g}%") if avg_pct else ""

    if diff_pct >= 2.5:
        lvl, emoji, head = "good", "🟢", "बेचने के लिए अच्छा दिन"
        sub = f"{n_days}-दिन औसत ₹{week_avg:,} से ऊपर{move}"
    elif diff_pct <= -2.5:
        lvl, emoji, head = "wait", "🔵", "भाव औसत से नीचे"
        sub = f"{n_days}-दिन औसत ₹{week_avg:,} से नीचे · नीचे ऊँचे भाव वाली मंडी देखें"
    else:
        lvl, emoji, head = "hold", "🟡", "भाव सामान्य के आसपास"
        sub = f"{n_days}-दिन औसत ₹{week_avg:,} के करीब · जल्दी न हो तो नज़र रखें"

    return (f'<div class="answer-signal {lvl}">'
            f'<span class="as-dot">{emoji}</span>'
            f'<span class="as-txt"><b>{head}</b><span class="as-sub">{sub}</span></span>'
            f'</div>')


# ── 🔔 mandi price alert toggle (web push) ───────────────────
# Kept as a plain (non-f) string so the JS braces need no escaping.
_BELL_JS = """
var b=document.getElementById('bhav-bell');
if(!b)return;
var txt=b.querySelector('.bb-txt'),busy=false,KEY='',keyReq=null;
/* The bell shipped blind: with one subscriber on the whole site there was no way
   to tell "nobody taps it" from "everybody taps it and drops at the next step".
   Every exit from the funnel now reports itself, tagged with the crop and mandi
   the farmer was actually looking at when he tried. */
function tr(n,x){try{x=x||{};x.commodity=T.commodity;x.state=T.state;x.district=T.district;
 if(window.kmTrack)window.kmTrack(n,x);}catch(e){}}
/* Web push needs all three. The bell is shown either way — a farmer should always
   be able to SEE that bhav alerts exist, which is the whole point of putting it on
   a page SEO traffic lands on. This flag only decides what a tap can do. */
var PUSH_OK=('serviceWorker' in navigator)&&('PushManager' in window)&&('Notification' in window);
function key(s){var p='='.repeat((4-s.length%4)%4),x=(s+p).replace(/-/g,'+').replace(/_/g,'/'),
 r=atob(x),a=new Uint8Array(r.length);for(var i=0;i<r.length;i++)a[i]=r.charCodeAt(i);return a;}
function paint(on){b.classList.toggle('on',!!on);if(!on)b.classList.remove('ringing');
 b.setAttribute('aria-pressed',on?'true':'false');
 if(txt)txt.textContent=on?'अलर्ट चालू':'भाव अलर्ट';
 b.title=on?'इस मंडी की सूचना बंद करें':'इस मंडी के भाव की सूचना पाएं';}
function ring(){b.classList.remove('ringing');void b.offsetWidth;b.classList.add('ringing');}
function qs(ep){return '?endpoint='+encodeURIComponent(ep||'')+'&commodity='+encodeURIComponent(T.commodity)
 +'&state='+encodeURIComponent(T.state)+'&district='+encodeURIComponent(T.district);}
/* An alert belongs to an account, so every call carries the token — that is what
   lets a farmer see his अलर्ट चालू on a phone he has never subscribed from. */
function tok(){var t=localStorage.getItem('krishi_token');
 return (t&&t!=='null'&&t!=='undefined')?t:null;}
function hdr(json){var h=json?{'Content-Type':'application/json'}:{},t=tok();
 if(t)h['Authorization']='Bearer '+t;return h;}
/* The VAPID key is fetched, never baked in — this HTML is edge-cached and served
   to everyone alike. Memoised, and retried on click rather than once at load: a
   page that opened against a cold (or suspended) backend must not leave the bell
   permanently dead until the farmer reloads.

   One silent retry after a pause, not zero: Render's free tier sleeps when idle
   and can take longer to wake than the first request waits around for, so a tap
   that lands on a cold instance used to fail outright with "अभी उपलब्ध नहीं है"
   even though the backend was merely slow, not actually down — the very next
   tap would have worked. Waiting once turns that into no error at all for the
   common case, at the cost of a few extra seconds only when it truly is down. */
function fetchKey(){
 return fetch('/alerts/vapid-key').then(function(r){return r.json();}).then(function(j){
  return (j&&j.data&&j.data.enabled)?j.data.key:'';
 }).catch(function(){return '';});
}
function ensureKey(){
 if(KEY)return Promise.resolve(KEY);
 if(keyReq)return keyReq;
 keyReq=fetchKey().then(function(k){
  if(k)return k;
  return new Promise(function(res){setTimeout(res,5000);}).then(fetchKey);
 }).then(function(k){KEY=k;if(!k)keyReq=null;return k;});
 return keyReq;
}
/* Hydrate the on/off state: the button is rendered identically for everyone, so
   only the client can know whether this account already has the alert on. */
if(PUSH_OK){
 /* Pre-register the SW now (SEO visitors land here without one) so a click
    doesn't pay install+activate latency before it can subscribe. */
 navigator.serviceWorker.register('/sw.js').catch(function(){});
 ensureKey();
 navigator.serviceWorker.getRegistration().then(function(reg){
  return (reg&&reg.pushManager)?reg.pushManager.getSubscription():null;
 }).then(function(s){
  /* Ask even with no local subscription: a signed-in farmer's alert lives on
     his account, and this may be a device he has never turned it on from. */
  if(!s&&!tok())return;
  return fetch('/alerts/mandi/status'+qs(s&&s.endpoint),{headers:hdr(false)})
   .then(function(r){return r.json();})
   .then(function(d){paint(d&&d.data&&d.data.subscribed);})
   .then(resume);
 }).catch(function(){});
}
/* Turning the bell ON no longer needs a login — see routes/alerts.py for why the
   gate came off. This is now only the recovery path for a token that expired
   mid-session, where the server has already answered 401. */
function gate(){
 if(tok())return true;
 tr('bhav_alert_login_required');
 if(window.KMRequireLogin)window.KMRequireLogin({
  title:'भाव अलर्ट के लिए लॉगिन करें',
  text:'लॉगिन करने पर यह अलर्ट आपके खाते से जुड़ जाएगा — फ़ोन बदलने या ब्राउज़र साफ़ करने पर भी भाव की सूचना आती रहेगी।',
  resume:'bhav-alert'});
 else location.href='/login.html';
 return false;
}
/* The alert is ON before this runs, and stays on whatever he does with it — the
   tip only tells him what an account would add. Shown once a month at most.

   The wording has to stay honest about what login actually buys. It does NOT
   make notifications appear on a new phone by itself: a push subscription is
   per-browser, so a new device still has to grant permission once. What it does
   buy is that /auth/claim-guest moves this row onto the account, so his alert
   list is not lost with the browser data. Promise that and nothing more. */
var TIPKEY='km_alert_login_tip';
function loginTip(){
 if(tok())return;
 try{if(Date.now()-(+localStorage.getItem(TIPKEY)||0)<30*24*3600*1000)return;}catch(e){}
 var host=b.parentNode;
 if(!host||host.querySelector('.bell-tip'))return;
 try{localStorage.setItem(TIPKEY,String(Date.now()));}catch(e){}
 var d=document.createElement('div');
 d.className='bell-tip';d.setAttribute('role','status');
 d.innerHTML='<b>🔔 अलर्ट चालू हो गया</b>'+
  'अभी यह सिर्फ़ इसी ब्राउज़र में सेव है — ब्राउज़र का डेटा साफ़ हुआ तो मिट जाएगा। '+
  'लॉगिन कर लें, अलर्ट आपके खाते में सुरक्षित रहेगा।'+
  '<div class="bell-tip-row"><a class="bell-tip-go">लॉगिन करें</a>'+
  '<button class="bell-tip-no" type="button">बाद में</button></div>';
 host.appendChild(d);
 var a=d.querySelector('.bell-tip-go');
 /* No ?do= — the alert is already on, and a resume would only race the bell's
    own hydration after the redirect. finishLogin() calls /auth/claim-guest with
    this browser's endpoint, which is what actually adopts the row. */
 a.href='/login.html?next='+encodeURIComponent(location.pathname+location.search);
 a.onclick=function(){tr('bhav_alert_login_tip_click');};
 requestAnimationFrame(function(){d.classList.add('in');});
 tr('bhav_alert_login_tip_shown');
 function bye(){if(!d.parentNode)return;d.classList.remove('in');
  setTimeout(function(){if(d.parentNode)d.parentNode.removeChild(d);},220);}
 d.querySelector('.bell-tip-no').onclick=function(){tr('bhav_alert_login_tip_dismissed');bye();};
 setTimeout(bye,15000);
}
/* Came back from login with ?do=bhav-alert — finish what he originally tapped,
   instead of making him find the bell again. */
function resume(){
 if(!PUSH_OK||!window.KMTakeResume)return;
 if(window.KMTakeResume()!=='bhav-alert'||b.classList.contains('on'))return;
 /* Safari refuses Notification.requestPermission() outside a user gesture, and
    this runs on load after a redirect. Complete silently only when permission
    was already granted; otherwise put the bell on screen and shake it, so the
    one tap that is still required is obvious. */
 if(Notification.permission==='granted'){window.toggleBhavAlert();return;}
 try{b.scrollIntoView({block:'center',behavior:'smooth'});}catch(e){}
 ring();
}
function go(){
 return Promise.resolve(Notification.requestPermission()).then(function(p){
  tr('bhav_alert_permission',{outcome:p});
  if(p!=='granted')throw new Error('सूचना की अनुमति नहीं मिली — ब्राउज़र सेटिंग में चालू करें।');
  return navigator.serviceWorker.register('/sw.js');
 }).then(function(){return navigator.serviceWorker.ready;}).then(function(reg){
  return reg.pushManager.getSubscription().then(function(s){
   return s||reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:key(KEY)});
  });
 }).then(function(s){
  var j=s.toJSON();
  return fetch('/alerts/mandi',{method:'POST',headers:hdr(true),
   body:JSON.stringify({subscription:{endpoint:j.endpoint,keys:j.keys},commodity:T.commodity,
   state:T.state,district:T.district,user_agent:navigator.userAgent})});
 }).then(function(r){
  /* Token expired between page load and click — re-ask rather than blaming push.
     Flagged quiet: the login popup is already on screen, an alert on top of it
     would just be noise. */
  if(r.status===401){gate();var q=new Error('login');q.quiet=true;throw q;}
  if(!r.ok)throw new Error('सूचना चालू नहीं हो सकी।');
  tr('bhav_alert_on',{account:tok()?'yes':'no'});
  paint(true);ring();loginTip();});
}
function off(){
 return navigator.serviceWorker.getRegistration().then(function(reg){
  return reg&&reg.pushManager?reg.pushManager.getSubscription():null;
 }).then(function(s){
  return fetch('/alerts/mandi/off',{method:'POST',headers:hdr(true),
   body:JSON.stringify({endpoint:(s&&s.endpoint)||'',commodity:T.commodity,state:T.state,
   district:T.district})}).then(function(){tr('bhav_alert_off');paint(false);});
 });
}
/* The bell is always on screen, so every reason a tap can fail has to answer back
   in words. Silence was acceptable while the button hid itself; it isn't now. */
window.toggleBhavAlert=function(){
 if(busy)return;
 tr('bhav_alert_tap',{action:b.classList.contains('on')?'off':'on',
                      account:tok()?'yes':'no'});
 function done(e){if(e&&!e.quiet)alert(e.message||'सूचना चालू नहीं हो सकी।');
  busy=false;b.classList.remove('loading');}
 if(b.classList.contains('on')){
  busy=true;b.classList.add('loading');
  off().then(function(){done();},done);return;
 }
 /* Browser can't do push at all — say so plainly rather than starting a flow
    that would dead-end at the last step. */
 if(!PUSH_OK){tr('bhav_alert_unsupported');
  alert('इस ब्राउज़र में सूचना की सुविधा नहीं है — Chrome में यह पेज खोलें।');return;}
 /* No login check. The farmer reading this page arrived from a search a minute
    ago; the browser's own permission dialog is the only thing he should have to
    answer to get a price alert. If he signs in later, /auth/claim-guest moves
    this alert onto the account. */
 busy=true;b.classList.add('loading');
 ensureKey().then(function(k){
  if(!k)throw new Error('भाव अलर्ट अभी उपलब्ध नहीं है — थोड़ी देर बाद फिर कोशिश करें।');
  return go();
 }).then(function(){done();},done);
};
"""

_BELL_SVG = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
             'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
             '<path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>'
             '<path d="M13.7 21a2 2 0 0 1-3.4 0"/></svg>')


def _alert_bell(commodity: str, state: str = "", district: str = "") -> str:
    """🔔 "notify me when this mandi's bhav changes" toggle for the answer panel.

    Always rendered visible. The feature only earns signups if a farmer can see it
    exists, and these pages are where SEO traffic lands — so the bell advertises
    itself to logged-out visitors, and a logged-out tap now switches the alert on
    for real. Login used to be the gate; see routes/alerts.py for why it came off
    (one subscriber sitewide) and what still binds an alert to an account.

    /bhav HTML is edge-cached and served to everyone alike, so the on/off state is
    never rendered server-side — the client hydrates it after load. Because the
    button no longer hides itself when push is unavailable, every failure path in
    _BELL_JS now has to explain itself in words."""
    target = _json.dumps({"commodity": commodity or "",
                          "state":     state or "",
                          "district":  district or ""}, ensure_ascii=False)
    return ('<button class="bhav-bell" id="bhav-bell" type="button" aria-pressed="false" '
            'onclick="toggleBhavAlert()" title="इस मंडी के भाव की सूचना पाएं">'
            f'{_BELL_SVG}<span class="bb-txt">भाव अलर्ट</span></button>'
            f'<script>(function(){{var T={target};{_BELL_JS}}})();</script>')


_WA_ICON = ('<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">'
            '<path d="M12.04 2c-5.46 0-9.91 4.45-9.91 9.91 0 1.75.46 3.45 1.32 4.95L2 22l5.25-1.38'
            'c1.45.79 3.08 1.21 4.79 1.21h.01c5.46 0 9.9-4.45 9.9-9.91 0-2.65-1.03-5.14-2.9-7.01'
            'A9.816 9.816 0 0 0 12.04 2zm5.52 14.03c-.25.7-1.45 1.34-2.01 1.4-.54.06-1.03.29-3.42-.71'
            '-2.9-1.17-4.75-4.14-4.9-4.33-.14-.19-1.16-1.54-1.16-2.94 0-1.4.73-2.09.99-2.37.26-.29'
            '.57-.36.76-.36.19 0 .38 0 .55.01.18.01.42-.07.66.5.25.58.83 2 .9 2.15.07.14.12.31.02.5'
            '-.09.19-.14.31-.28.47-.14.17-.29.37-.42.5-.14.14-.28.29-.12.57.16.28.72 1.18 1.54 1.91'
            '1.06.94 1.95 1.24 2.23 1.38.28.14.44.12.6-.07.16-.19.69-.8.87-1.08.18-.28.36-.23.6-.14'
            '.25.09 1.57.74 1.84.88.28.14.46.2.53.32.07.11.07.66-.18 1.36z"/></svg>')

# The number is the published helpline (see _header) — one number, already on
# every page, so a farmer who messages it reaches somewhere that is actually
# staffed rather than a broadcast address nobody reads.
_WA_NUMBER = "919870951001"


def _next_update() -> str:
    """The one line that gives a finished page a tomorrow.

    A price page answers the question completely and then has nothing left to
    say, which is exactly why a farmer reads it once and never comes back — the
    number was useful, the site was incidental. Naming when the next number
    lands turns a finished answer into an appointment, and points at the two
    ways to keep it without having to remember us.

    The hours are the real cron in services/mandi_scheduler.py (IST 8, 10, 13,
    16, 20 and 23:11). If that schedule changes, change this sentence with it —
    a promised update that does not arrive is worse than no promise."""
    return ('<p class="next-up">🕗 <b>कल का भाव</b> कल सुबह 8 बजे से — '
            'दिन भर अपडेट होता रहता है। भाव बदलते ही पता चले, '
            'इसके लिए ऊपर 🔔 दबाएं या नीचे WhatsApp चुनें।</p>')


def _wa_click(event: str, payload: dict) -> str:
    """An onclick= attribute for kmTrack that survives being an HTML attribute.

    The payload is JSON, so it carries double quotes, and the attribute is
    double-quoted — written raw, the browser ended the attribute at the first
    quote inside it and the rest of the call became stray markup. Every value
    here is a crop, a district or a state name, so escaping the whole JS with
    quote=True is enough: the browser HTML-decodes an attribute before the JS
    engine ever sees it."""
    js = f"try{{kmTrack('{event}',{_json.dumps(payload, ensure_ascii=False)})}}catch(e){{}}"
    return f'onclick="{escape(js, quote=True)}"'


def _wa_daily(hi: str, district: str, state: str = "") -> str:
    """The return channel that asks for no account, no email and no notification
    permission — the state's WhatsApp channel, or a message to us if it has none.

    Web push is the better mechanism on paper and the worse one in this market:
    it needs a permission dialog, dies with the browser profile, and never
    reaches an iPhone that has not installed the site. WhatsApp is where these
    farmers already are.

    This began as "message us and we'll send you this mandi's bhav daily" — a
    list worked by hand, per farmer, per day, which cannot grow past the person
    working it, and a request that is never answered should never have been
    advertised. A channel inverts that: the farmer joins in one tap, we post
    once, and the whole state gets the number. State-wise because a Raisen
    farmer will not read Punjab's rates, and one national channel would have to
    post 36 states' prices to serve anybody — the fastest way to be muted.

    Links come from services/wa_channels (data/wa_channels.json). A state with
    no channel yet keeps the old message-us card: never invite a farmer into a
    room that does not exist.

    rel=nofollow because this is a contact action, not a link Google should
    follow or pass weight through."""
    chan = _wa_channels.channel_for(state) if state else None
    if chan:
        click = _wa_click("wa_channel_click", {"state": state, "channel": chan["name"]})
        return (f'<div class="wa-daily">'
                f'<span class="wa-daily-ic">{_WA_ICON}</span>'
                f'<div class="wa-daily-t"><b>{escape(_hindi_state(state))} का भाव WhatsApp चैनल पर</b>'
                f'<span>{escape(chan["name"])} — रोज़ भाव, फ्री। बिना ऐप, बिना लॉगिन।</span></div>'
                f'<a class="wa-daily-go" href="{escape(chan["url"])}" '
                f'target="_blank" rel="nofollow noopener" {click}>जुड़ें</a></div>')

    msg = quote(f"नमस्ते! मुझे {district} मंडी का {hi} भाव रोज़ WhatsApp पर चाहिए।")
    return (f'<div class="wa-daily">'
            f'<span class="wa-daily-ic">{_WA_ICON}</span>'
            f'<div class="wa-daily-t"><b>रोज़ का भाव WhatsApp पर</b>'
            f'<span>{escape(district)} मंडी का {escape(hi)} भाव — बिना ऐप, बिना लॉगिन।</span></div>'
            f'<a class="wa-daily-go" href="https://wa.me/{_WA_NUMBER}?text={msg}" '
            f'target="_blank" rel="nofollow noopener" '
            f'{_wa_click("wa_daily_click", {"commodity": hi, "district": district})}>'
            f'भेजें</a></div>')


def _crop_chip(href: str, label: str, commodity: str) -> str:
    """Link chip carrying the crop's photo — a farmer scanning the page can find
    his crop by sight, without reading every label."""
    thumb = (f'<img src="{escape(_crop_image(commodity, 330))}" alt="" loading="lazy" width="28" height="28">'
             if _has_photo(commodity) else '<span class="ico">🌾</span>')
    return f'<a class="chip" href="{href}">{thumb}{escape(label)}</a>'


def _state_card(href: str, state: str, count: int, count_lbl: str) -> str:
    """One state tile — SVG map panel + Hindi/English name + a count pill. Used
    for the states-of-a-crop grid on /bhav/{crop} (count = जिले) and the
    'राज्य के आधार पर' tab on the /bhav hub (count = फसलें)."""
    svg_slug = _state_svg_slug(state)
    svg_src  = f"/images/state_map_svgs/{svg_slug}.svg"
    dname = escape(f"{_hindi_state(state)} {state}".lower())
    return f"""<a class="place" href="{href}" data-name="{dname}">
<div class="place-map-panel">
  <div class="place-map-blob"></div>
  <img class="place-map-svg" src="{escape(svg_src)}" alt="{escape(state)} नक्शा" loading="lazy"
    onerror="this.closest('.place-map-panel').style.display='none'">
</div>
<div class="place-info">
  <svg class="place-deco-svg" viewBox="0 0 100 100" fill="none" stroke="#2d6a4f" stroke-opacity="0.07" stroke-width="2.5" stroke-linecap="round">
    <path d="M10,90 Q40,80 70,30 Q80,15 90,10 M35,70 Q20,55 15,60 Q10,65 25,75 M50,53 Q38,38 30,40 Q22,42 40,58 M60,40 Q75,32 80,38 Q85,44 68,50" />
  </svg>
  <div class="place-n">{escape(_hindi_state(state))}</div>
  <div class="place-divider-wrap">
    <div class="place-line"></div>
    <span class="place-ornament"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#2d6a4f" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10Z"/><path d="M2 21c0-3 1.85-5.36 5.08-6C9.5 14.52 12 13 13 12"/></svg></span>
    <div class="place-line"></div>
  </div>
  <div class="place-en">{escape(state)}</div>
  <div class="place-dist-box">
    <div class="place-dist-pin-wrap">
      <svg class="place-dist-pin" viewBox="0 0 24 24" width="18" height="18" fill="#1a3c2e">
        <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z" />
      </svg>
    </div>
    <div class="place-dist-text">
      <span class="place-dist-num">{count}</span>
      <span class="place-dist-lbl">{count_lbl}</span>
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
</a>"""


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
        # …and the way out of the 10-chip cap: the district hub lists every crop
        # this mandi reports. Also the only internal link those hubs get from the
        # deep pages, which is where the crawler already spends its budget.
        n_all = len(_crops_in(idx, s_slug, d_slug))
        chips += (f'<a class="chip" href="/bhav/rajya/{s_slug}/{d_slug}">'
                  f'<span class="ico">🗂️</span>सभी {n_all} फसलें</a>')
        out.append(f'<h2>{escape(district)} मंडी में अन्य फसलों के भाव</h2><div class="chips">{chips}</div>')
    return "\n".join(out)


# Design tokens mirror frontend/index.html + mandi.html so a farmer arriving from
# Google on /bhav lands on something that is visibly the same product as the app.
_CSS = """
:root{--green-dark:#1a3c2e;--green-mid:#2d6a4f;--green-light:#52b788;--green-pale:#d8f3dc;
--amber:#e9a825;--sky:#2e86de;--cream:#f5f7f4;--white:#fff;--text-dark:#1a2e23;--text-mid:#4a5a52;
--text-soft:#7c8983;--border:#e5e9e6;--shadow-sm:0 2px 10px rgba(26,60,46,.05);
--shadow-md:0 8px 28px rgba(26,60,46,.10);--radius-sm:12px;--radius-md:18px;
--font-serif:'Noto Serif Devanagari','Playfair Display',serif;
--font-body:'DM Sans','Noto Sans Devanagari',sans-serif}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:var(--font-body);background:var(--cream);color:var(--text-dark);line-height:1.6}
img{max-width:100%}
/* content column aligns to the header/utility-bar grid (max-width:1280px + 80px
   side padding), so the heading, tabs, search and tiles line up with the logo/nav
   above instead of sitting indented in a narrower 980px box */
.wrap{max-width:1280px;margin:0 auto;padding:18px 80px 30px}

/* ── site header — same pre-topbar/topbar/main-header/blue-bar stack as
   mandi.html, so a page reached from Google reads as the same product as the
   app instead of a stripped-down doorway ── */
.header-wrapper{position:fixed;top:0;left:0;right:0;z-index:2000;
transition:transform .28s cubic-bezier(.4,0,.2,1)}
.topbar-spacer{height:137px;flex-shrink:0}
@media(max-width:1024px){.topbar-spacer{height:88px}}
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
/* keep content flush with the header, which drops to 12px side padding here */
.wrap{padding:14px 12px 30px}
.crumbs{padding:12px 12px 0}
}

/* ── breadcrumbs ── */
.crumbs{max-width:1280px;margin:0 auto;padding:12px 80px 0;font-size:12px;color:var(--text-soft)}
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
.ctl-loc{flex-shrink:0;background:none;border:none;padding:4px;cursor:pointer;
color:var(--text-mid);opacity:.6;border-radius:50%;line-height:1;
display:flex;align-items:center;justify-content:center;transition:opacity .15s,background .15s,color .15s,transform .1s}
.ctl-loc:hover{opacity:1;background:var(--cream);color:var(--green-mid)}
.ctl-loc:active{transform:scale(0.85)}
.ctl-loc.loading{opacity:1!important;pointer-events:none;background:rgba(37,99,235,0.12);border-radius:50%}
.ctl-loc.loading svg{animation:bmSpin .8s linear infinite;color:#2563eb}
.ctl-loc.active{color:#2563eb;opacity:1;background:rgba(37,99,235,0.1)}
@keyframes bmSpin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}
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
/* The stale pill again, this time on the dark green price panel — the light
   amber fill from the tier-2/3 rule is invisible there. */
.answer-sub .stale-pill{background:rgba(255,196,84,.18);border-color:rgba(255,196,84,.45);color:#ffd489}
/* Date stamp on a mandi card whose price is older than the newest on the page.
   A district's cards routinely span several days (Nashik onion: 49 rows over
   4 days) and used to be rendered identically, so a carried-forward rate was
   indistinguishable from one reported this morning. */
.mkt-date{display:block;margin-top:3px;font-size:11px;font-weight:600;color:#8a5a00}
.answer-lead{font-size:13.5px;color:rgba(255,255,255,.92);margin-top:12px;line-height:1.65;max-width:600px}
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
/* "get tomorrow's bhav on WhatsApp" — a RETURN channel, not the share pill
   above it. Deliberately its own band under the price card so the two are never
   read as the same button: one sends this price out, this one brings the farmer
   back. WhatsApp is where this audience already is, and unlike web push it
   costs no permission dialog and survives a cleared browser. */
/* Shown only AFTER a guest's alert is already switched on — never before, and
   never as a condition of anything. Anchored under the bell rather than in a
   corner because that is where he just tapped, and because the two floating
   cards (GPS, install) already compete for the bottom of the screen. */
.bell-tip{position:absolute;top:58px;right:14px;z-index:4;
width:min(258px,calc(100% - 28px));padding:12px 13px;border-radius:13px;
background:rgba(8,32,18,.96);border:1px solid rgba(255,255,255,.18);
box-shadow:0 10px 26px rgba(0,0,0,.34);color:#dcefe3;font-size:12.2px;line-height:1.5;
opacity:0;transform:translateY(-6px);transition:opacity .2s ease,transform .2s ease}
.bell-tip.in{opacity:1;transform:none}
.bell-tip b{display:block;color:#fff;font-size:13px;font-weight:800;margin-bottom:3px}
.bell-tip-row{display:flex;gap:8px;margin-top:11px}
.bell-tip-go{flex:1 1 auto;text-align:center;background:var(--amber);color:#3a2c05;
text-decoration:none;font-size:12.5px;font-weight:800;padding:8px 10px;border-radius:9px}
.bell-tip-no{flex:0 0 auto;background:transparent;border:1px solid rgba(255,255,255,.25);
color:#c4dbcd;font-family:inherit;font-size:12.5px;font-weight:700;padding:8px 12px;
border-radius:9px;cursor:pointer}
/* the appointment line — see _next_update() for why a price page needs one */
.next-up{margin:14px 0 0;padding:10px 13px;border-radius:11px;
background:rgba(255,255,255,.10);border:1px solid rgba(255,255,255,.16);
color:rgba(255,255,255,.88);font-size:12.5px;line-height:1.55}
.next-up b{color:#fff;font-weight:800}
.wa-daily{display:flex;align-items:center;gap:12px;margin:14px 0 0;
padding:13px 15px;border-radius:14px;background:#f2fbf5;border:1px solid #cfeeda}
.wa-daily-ic{flex:0 0 auto;width:38px;height:38px;border-radius:50%;background:#25d366;
color:#fff;display:flex;align-items:center;justify-content:center}
.wa-daily-ic svg{width:21px;height:21px}
.wa-daily-t{flex:1 1 auto;min-width:0}
.wa-daily-t b{display:block;font-size:14.5px;font-weight:800;color:#14361f;line-height:1.3}
.wa-daily-t span{display:block;font-size:12px;color:#4d6b58;line-height:1.4;margin-top:2px}
.wa-daily-go{flex:0 0 auto;background:#25d366;color:#fff;text-decoration:none;
font-size:13.5px;font-weight:800;padding:10px 16px;border-radius:11px;white-space:nowrap}
.wa-daily-go:hover{background:#1eb958}
@media(max-width:400px){.wa-daily{gap:9px;padding:11px 12px}
.wa-daily-t b{font-size:13.5px}.wa-daily-go{padding:9px 13px;font-size:13px}}
@media(max-width:640px){.answer-photo{opacity:.22;width:100%;
-webkit-mask-image:linear-gradient(90deg,transparent,#000 90%);
mask-image:linear-gradient(90deg,transparent,#000 90%)}
.answer-rupee{font-size:38px}h1{font-size:20px}.answer h1{font-size:20px}}

/* ── "sell here instead": the one thing a price table never tells you ── */
/* sell-or-wait strip — lives INSIDE the green answer panel, by the rate */
.answer-signal{display:flex;gap:10px;align-items:center;margin-top:14px;max-width:600px;
padding:10px 14px;border-radius:12px;background:rgba(255,255,255,.10);
border:1px solid rgba(255,255,255,.20);border-left:4px solid rgba(255,255,255,.6)}
.answer-signal.good{border-left-color:#87cefa;background:rgba(135,206,250,.22)}
.answer-signal.hold{border-left-color:var(--amber);background:rgba(233,168,37,.20)}
.answer-signal.wait{border-left-color:#7fc4f5;background:rgba(46,134,222,.22)}
/* 🔔 "notify me about this mandi" toggle — pinned top-right of the green panel,
   above the crop photo. Always visible, including to logged-out visitors: the
   tap is what asks for a login. */
.bhav-bell{position:absolute;top:14px;right:14px;z-index:3;display:inline-flex;align-items:center;
gap:7px;padding:8px 13px;border-radius:999px;border:1.5px solid rgba(255,255,255,.34);
background:rgba(0,0,0,.24);color:#fff;font-family:inherit;font-size:12.5px;font-weight:700;
cursor:pointer;-webkit-backdrop-filter:blur(4px);backdrop-filter:blur(4px);
transition:background .15s,border-color .15s,color .15s}
.bhav-bell:hover{background:rgba(0,0,0,.38)}
.bhav-bell svg{width:16px;height:16px;flex-shrink:0;transform-origin:50% 3px}
.bhav-bell.on{background:var(--amber);border-color:var(--amber);color:#3a2c05}
/* immediate feedback while the subscribe round-trip is in flight */
.bhav-bell.loading{cursor:progress}
.bhav-bell.loading svg{animation:bhav-bell-pulse .7s ease-in-out infinite}
/* one-shot swing when the alert is confirmed on */
.bhav-bell.ringing svg{animation:bhav-bell-ring .7s ease}
/* keep nudging — a periodic ring every few seconds — until it's switched on */
.bhav-bell:not(.on):not(.loading) svg{animation:bhav-bell-idle 3.2s ease-in-out infinite}
.bhav-bell[hidden]{display:none}
@keyframes bhav-bell-pulse{0%,100%{transform:scale(1);opacity:.65}50%{transform:scale(1.22);opacity:1}}
@keyframes bhav-bell-ring{0%,100%{transform:rotate(0)}12%{transform:rotate(17deg)}24%{transform:rotate(-14deg)}
36%{transform:rotate(10deg)}48%{transform:rotate(-7deg)}60%{transform:rotate(4deg)}72%{transform:rotate(-2deg)}}
@keyframes bhav-bell-idle{0%{transform:rotate(0)}4%{transform:rotate(14deg)}8%{transform:rotate(-12deg)}
12%{transform:rotate(9deg)}16%{transform:rotate(-6deg)}20%{transform:rotate(3deg)}24%,100%{transform:rotate(0)}}
@media(prefers-reduced-motion:reduce){.bhav-bell.loading svg,.bhav-bell.ringing svg,
.bhav-bell:not(.on):not(.loading) svg{animation:none}}
@media(max-width:560px){.bhav-bell{padding:9px;top:10px;right:10px}.bhav-bell .bb-txt{display:none}}
.as-dot{font-size:17px;line-height:1;flex-shrink:0}
.as-txt{display:flex;flex-direction:column;min-width:0}
.as-txt b{font-size:14px;font-weight:800;color:#fff;letter-spacing:-.2px}
.as-sub{font-size:11.5px;color:rgba(255,255,255,.82);margin-top:2px;line-height:1.45}
/* net-price calculator button — sits beside the WhatsApp share / in a cta-row.
   Amber so it reads on BOTH the dark green answer panel and light action rows. */
.answer-actions{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:16px}
.answer-actions .answer-share{margin-top:0}
.btn-np{background:var(--amber);color:#3a2c00;box-shadow:var(--shadow-sm)}
.btn-np:hover{background:#d69a1f}
/* "खरीदें/बेचें" — the third action on the green panel. WhatsApp owns green and
   the net-price button owns amber, so this takes sea blue: the one hue that
   separates cleanly from both against the dark green. Deliberately NOT the
   palette's --sky (#2e86de) — white on that is 3.4:1, under the 4.5:1 AA needs
   at 14px. #0077b6 is the nearest sea blue that passes (4.9:1). Geometry mirrors
   .answer-share exactly (11px/20px, no border) so the two pills sit level. */
.answer-appeal{display:inline-flex;align-items:center;gap:8px;cursor:pointer;
font-family:var(--font-body);font-size:14px;font-weight:700;color:#fff;border:none;
padding:11px 20px;border-radius:24px;background:#0077b6;
box-shadow:0 2px 10px rgba(0,0,0,.18);transition:background .15s,transform .15s}
.answer-appeal:hover{background:#01659c;transform:translateY(-1px)}
.answer-appeal:active{transform:translateY(0)}
/* किसान सेवाएं — lead-gen / affiliate service links (loan/insurance/solar) */
.lead-gen{margin:26px 0 8px;border:1px solid var(--border);border-radius:var(--radius-md);
background:var(--white);box-shadow:var(--shadow-sm);padding:16px 16px 14px}
.lead-gen>h2{margin:0 0 3px;font-size:17px}
.lead-sub{font-size:12.5px;color:var(--text-mid);margin:0 0 12px;line-height:1.5}
.lead-list{display:flex;flex-direction:column;gap:9px}
.lead-card{display:flex;align-items:center;gap:12px;text-decoration:none;color:inherit;
background:var(--cream);border:1px solid var(--border);border-radius:13px;padding:11px 13px}
.lead-card:active{background:var(--green-pale)}
.lead-ic{font-size:22px;line-height:1;flex:0 0 auto}
.lead-tx{display:flex;flex-direction:column;min-width:0;flex:1}
.lead-tx b{font-size:14px;color:var(--text-dark);line-height:1.35}
.lead-tx small{font-size:11.5px;color:var(--text-mid);margin-top:2px;line-height:1.45}
.lead-cta{font-size:12px;font-weight:700;color:var(--green-mid);white-space:nowrap;flex:0 0 auto}
.lead-fine{font-size:11px;color:var(--text-soft);line-height:1.5;margin:11px 0 0}
/* ── MSP — the government floor, read against today's mandi price. Deliberately
   a calm white card, not a green/red alarm: below-MSP is common and normal, and
   shouting it would make the block noise a farmer learns to skip. The left rule
   carries the verdict; amber (not red) marks "below". ── */
.msp-box{margin:16px 0;background:var(--white);border:1px solid var(--border);
border-left:4px solid var(--text-soft);border-radius:var(--radius-md);
padding:14px 16px;box-shadow:var(--shadow-sm)}
.msp-box.above{border-left-color:var(--green-mid)}
.msp-box.below{border-left-color:var(--amber)}
.msp-box.at{border-left-color:var(--sky)}
.msp-top{display:flex;align-items:center;gap:11px;flex-wrap:wrap}
.msp-ic{font-size:21px;line-height:1;flex:0 0 auto}
.msp-lbl{display:flex;flex-direction:column;min-width:0;flex:1}
.msp-lbl b{font-size:14.5px;font-weight:800;color:var(--text-dark);line-height:1.35}
.msp-lbl em{font-style:normal;font-size:11.5px;color:var(--text-soft);margin-top:2px}
.msp-val{font-size:22px;font-weight:800;color:var(--green-dark);letter-spacing:-.5px;
white-space:nowrap;flex:0 0 auto}
.msp-val small{font-size:11px;font-weight:600;color:var(--text-soft);margin-left:2px}
.msp-cmp{font-size:13.5px;color:var(--text-mid);line-height:1.55;margin-top:10px;
padding-top:10px;border-top:1px dashed var(--border)}
.msp-cmp b{color:var(--text-dark);font-weight:800}
.msp-box.above .msp-cmp b{color:var(--green-mid)}
/* --amber on white is 2.1:1 — unreadable as text. This is the darkened amber
   that keeps the "below" cue while passing AA (4.6:1). */
.msp-box.below .msp-cmp b{color:#9a6407}
.msp-fine{font-size:11px;color:var(--text-soft);line-height:1.5;margin-top:8px}
.msp-fine a{color:var(--text-soft);text-decoration:underline}
@media(max-width:560px){.msp-val{font-size:20px}}
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
  color: var(--green-dark);
  white-space: nowrap;
  margin-left: 12px;
}
.bmc-delta{color:var(--sky)}
.bmc-delta.up,.bmc-delta.dn{font-size:13.5px;font-weight:800}
.bmc-delta.up{color:#1b7a3d}
.bmc-delta.dn{color:#c0392b}
.better.flat{border-left-color:var(--green-light)}
.better-message {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--text-mid);
  margin-top: 6px;
  line-height: 1.5;
}
.better-low{margin-top:14px;padding-top:14px;border-top:1px dashed var(--border)}
.better-low-h{font-size:12.5px;font-weight:700;color:#c0392b;margin-bottom:8px}
.better-mandi-card.low{border-right-color:#c0392b}
.better-mandi-card.low:hover{border-color:#e88b7d}
.better-mandi-card.low .bmc-action{color:#c0392b}

/* ── trend chart ── */
.card-w{background:var(--white);border:1px solid var(--border);border-radius:var(--radius-md);
padding:16px 18px;box-shadow:var(--shadow-sm);margin-top:16px}
.card-w-h{display:flex;align-items:baseline;justify-content:space-between;gap:10px;margin-bottom:6px}
.card-w-h h2{margin:0}
.card-w-h em{font-style:normal;font-size:11.5px;font-weight:600;color:var(--text-soft)}
svg.chart{display:block;width:100%;height:auto}

/* ── multi-year seasonality panel (पिछले साल इसी समय) ── */
.season-facts{list-style:none;margin:12px 0 0;padding:0}
.season-facts li{display:flex;align-items:baseline;justify-content:space-between;gap:10px;
padding:9px 0;border-bottom:1px dashed var(--border);font-size:13.5px}
.season-facts li:last-child{border-bottom:none}
.sl-k{color:var(--text-soft);font-size:12.5px}
.sl-v{font-weight:700;color:var(--text-mid);white-space:nowrap}
.sl-v.up{color:#1b7a3d}
.sl-v.dn{color:#c0392b}
.sl-d{font-style:normal;font-size:11.5px;font-weight:600;margin-left:6px}
.sl-d.up{color:#1b7a3d}
.sl-d.dn{color:#c0392b}
.sl-d.flat{color:var(--text-soft)}
.season-note{font-size:11.5px;color:var(--text-soft);margin-top:10px;line-height:1.6}
@media(max-width:420px){
.season-facts li{flex-direction:column;gap:2px}
.sl-v{white-space:normal}
}

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
/* AI-citable lead paragraph — sits on the cream page below the trend chart */
.lead-out{font-size:14px;color:var(--text-mid);line-height:1.7;max-width:680px;margin-top:20px;
padding:14px 18px;background:var(--white);border:1px solid var(--border);
border-left:4px solid var(--sky);border-radius:var(--radius-sm)}

/* ── CTAs ── */
.cta-row{display:flex;gap:10px;flex-wrap:wrap;margin:18px 0}
.btn{display:inline-flex;align-items:center;gap:8px;font-family:var(--font-body);font-size:14px;
font-weight:700;padding:12px 22px;border-radius:26px;text-decoration:none;transition:background .15s,transform .15s}
.btn:hover{transform:translateY(-1px)}
.btn-app{background:var(--green-mid);color:var(--white);box-shadow:var(--shadow-sm)}
.btn-app:hover{background:var(--green-dark)}
.btn-wa{background:#25d366;color:var(--white);box-shadow:var(--shadow-sm)}
.btn-wa:hover{background:#1eb958}
/* "कौन खरीदेगा" — outlined, because it sits beside two filled buttons in the
   same row and a third solid colour would turn the row into a traffic light. */
.btn-kh{background:var(--white);color:var(--green-dark);
border:1.5px solid var(--green-light);box-shadow:var(--shadow-sm)}
.btn-kh:hover{background:var(--green-pale);border-color:var(--green-mid)}

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

/* ── simple centered page heading (matches mandi.html's .mandi-page-heading) ── */
.mandi-page-heading{text-align:center;font-family:var(--font-body);font-size:22px;
font-weight:800;color:#1a56db;padding:10px 16px 4px}
.mandi-page-sub{text-align:center;font-size:12.5px;color:var(--text-soft);font-weight:500;margin:0 auto 14px}
/* "N दिन पुराना भाव" — see _age_note. Amber, not red: a carried-forward price
   is the honest best answer we have, not an error. Sits inline with the 📅 date
   on tiers 2/3 and inside the dark price panel on tier 4, so it is declared
   once here and restyled for the dark panel next to .answer-sub. */
.stale-pill{display:inline-block;margin-left:6px;padding:1px 7px;border-radius:999px;
  background:#fdf0d5;color:#8a5a00;border:1px solid #f0d9a8;font-size:11.5px;font-weight:700;
  white-space:nowrap;vertical-align:middle}
@media(max-width:640px){.mandi-page-heading{font-size:18px;padding:8px 12px 4px}}

/* ── फसल / राज्य tab switcher + commodity grid — ported 1:1 from mandi.html
   (.shop-tabs / .ctile-search-row / .shop-section-title / .commodity-grid /
   .ctile) so the /bhav hub reads pixel-for-pixel like the app landing ── */
.bhav-tabs{display:flex;gap:0;background:#e6efe9;border-radius:12px;padding:4px;margin:16px 0 20px}
.bhav-tab-btn{flex:1;padding:10px 16px;border:none;border-radius:9px;background:transparent;
font-size:13px;font-weight:600;color:var(--text-mid);cursor:pointer;font-family:var(--font-body);
transition:all .2s;white-space:nowrap;display:flex;align-items:center;justify-content:center;gap:6px}
.bhav-tab-btn.active{background:var(--white);color:var(--green-dark);box-shadow:0 2px 8px rgba(26,60,46,.12);font-weight:700}
.bhav-pane[hidden]{display:none}
@media(max-width:640px){.bhav-tab-btn{font-size:13px;padding:10px 8px;min-height:44px}}

.mandi-toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:16px}
.ctile-search-row{display:flex;align-items:center;gap:8px;background:var(--cream);
border:1.5px solid var(--border);border-radius:var(--radius-sm);padding:9px 12px;
min-height:42px;flex:1;min-width:190px;transition:border-color .2s,background .2s}
.ctile-search-row:focus-within{border-color:var(--green-light);background:#fff}
.ctile-search-row>.cs-icon{font-size:14px;opacity:.7;flex-shrink:0}
.ctile-search-row input{flex:1;border:none;outline:none;background:transparent;
font-size:13px;color:var(--text-dark);min-width:0;font-family:var(--font-body)}
.ctile-search-row input::placeholder{color:var(--text-soft)}
.mn-mic-btn{background:none;border:none;padding:2px 3px;cursor:pointer;font-size:14px;
flex-shrink:0;opacity:.55;line-height:1;border-radius:50%;color:var(--text-mid);
transition:opacity .15s,background .15s}
.mn-mic-btn:hover{opacity:1;background:#e8ede9}
.mn-mic-btn.listening{opacity:1;animation:mn-mic-pulse .7s ease-in-out infinite alternate}
@keyframes mn-mic-pulse{from{opacity:.7}to{opacity:1;color:#e53935}}
.mn-loc-btn{background:none;border:none;padding:2px 3px;cursor:pointer;font-size:14px;
flex-shrink:0;opacity:.55;line-height:1;border-radius:50%;color:var(--text-mid);
transition:opacity .15s,background .15s,color .15s,transform .1s;display:inline-flex;align-items:center;justify-content:center}
.mn-loc-btn:hover{opacity:1;background:#e8ede9;color:var(--green-mid)}
.mn-loc-btn:active{transform:scale(0.85)}
.mn-loc-btn.loading{opacity:1!important;pointer-events:none;background:rgba(37,99,235,0.12);border-radius:50%}
.mn-loc-btn.loading svg{animation:bmSpin .8s linear infinite;color:#2563eb}
.mn-loc-btn.active{color:#2563eb;opacity:1;background:rgba(37,99,235,0.1)}
.bhav-crop-loc-banner{display:flex;align-items:center;gap:10px;background:#eff6ff;border:1px solid #bfdbfe;color:#1e40af;padding:8px 14px;border-radius:10px;font-size:12.5px;font-weight:600;margin-bottom:14px;flex-wrap:wrap}
.bhav-crop-loc-banner b{color:#1e3a8a}
.bhav-crop-loc-banner .bcl-icon{display:inline-flex;color:#2563eb}
.bhav-crop-loc-banner .bcl-link{margin-left:auto;color:#1d4ed8;text-decoration:none;font-weight:700}
.bhav-crop-loc-banner .bcl-link:hover{text-decoration:underline}

.shop-section-title{font-family:var(--font-serif);font-size:19px;color:var(--text-dark);
margin-bottom:14px;display:flex;align-items:center;gap:8px;padding-left:12px;
border-left:3px solid var(--amber)}

.commodity-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px 18px}
@media(max-width:640px){.commodity-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
.ctile{position:relative;display:flex;flex-direction:row;align-items:center;gap:12px;
background:transparent;border:none;border-radius:12px;padding:7px 8px;cursor:pointer;
text-align:left;text-decoration:none;color:inherit;font-family:var(--font-body);
transition:background .15s;-webkit-tap-highlight-color:transparent}
.ctile:hover{background:#f1f8f3}
.ctile:active{background:#e6efe9}
.ctile-imgwrap{position:relative;width:70px;height:54px;flex-shrink:0;border-radius:9px;
overflow:hidden;background:linear-gradient(135deg,#eef6f0,#dcede2);
display:flex;align-items:center;justify-content:center;box-shadow:0 1px 4px rgba(26,60,46,.12)}
.ctile-img{width:100%;height:100%;object-fit:cover;display:block}
.ctile-emoji{font-size:30px;line-height:1}
.ctile-body{min-width:0;flex:1}
.ctile-name{font-size:14px;font-weight:600;color:var(--text-dark);line-height:1.3;word-break:break-word}
.ctile-name b{font-weight:800}

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

/* ── district picker — compact single-row cards (not the rich map card) ── */
.dcard-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-top: 16px;
}
@media (max-width: 900px) { .dcard-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 600px) { .dcard-grid { grid-template-columns: 1fr; } }
.dcard {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  background: var(--white);
  border: 1.5px solid var(--border);
  border-right: 5px solid var(--green-mid);
  border-radius: 14px;
  padding: 14px 16px;
  text-decoration: none;
  color: inherit;
  box-shadow: 0 2px 10px rgba(26,60,46,.04);
  transition: transform .2s, box-shadow .2s, border-color .2s;
}
.dcard:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 18px rgba(26,60,46,.08);
  border-color: var(--green-light);
}
.dcard-n {
  font-size: 15px;
  font-weight: 700;
  color: var(--green-dark);
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.dcard-r {
  font-size: 13px;
  font-weight: 700;
  color: var(--green-mid);
  white-space: nowrap;
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

# The "आगे क्या करें" strip's own sheet, appended so it reaches the <head> once
# per page instead of riding inline in the body on ~14,000 URLs. It is scoped
# entirely under .km-journey and declares literal colours rather than this
# module's CSS variables, because the same block is rendered into the static
# article pages, which never load this stylesheet — see services/ecosystem.CSS.
_CSS += ecosystem.CSS

_FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
          '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
          '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
          'family=DM+Sans:wght@400;500;700'
          '&family=Noto+Serif+Devanagari:wght@600;700'
          '&family=Noto+Sans+Devanagari:wght@400;600;700&display=swap">')

# The loading skeletons (.km-sk) live in frontend/km-skeleton.css so the server
# pages and the static pages share ONE definition of the shimmer instead of the
# four private copies they had. It rides in _FONTS because that constant is what
# every server section already puts in its <head> — product.py, rental.py,
# naksha.py and poultry.py all import it — and because a lazy panel paints its
# skeleton on first paint, before the deferred drawer-menu.js could inject it.
_FONTS += f'<link rel="stylesheet" href="{_asset("km-skeleton.css")}">'

_ICON = f'<link rel="icon" href="{SITE}/assets/krashimitra_logo.png" type="image/png">'

# ── Add-to-home-screen ──────────────────────────────────────────────────────
# Nearly all organic traffic lands HERE, not on index.html — a farmer arrives on
# /bhav/{crop}/{state}/{district} straight from Google. The manifest used to be
# linked only from the static frontend pages, which meant the one return channel
# that costs him nothing (no account, no email, no notification permission) was
# unavailable on every single entry page: Chrome will not offer to install a
# document that declares no manifest, so the install banner sitting in
# index.html could only ever be seen by someone who was already coming back.
#
# The icon on his home screen is the whole point. It is the only thing that
# survives him closing the tab, and unlike the 🔔 bell it asks for nothing.
_PWA = ('<link rel="manifest" href="/manifest.json">'
        '<meta name="theme-color" content="#1b5e20">'
        '<link rel="apple-touch-icon" href="/assets/logo-192.png">'
        '<meta name="mobile-web-app-capable" content="yes">'
        '<meta name="apple-mobile-web-app-title" content="कृषि मित्र">')

# The install card itself. Deliberately NOT rendered in the server HTML: it is
# built by script only after Chrome fires beforeinstallprompt, which it does
# only when the page is genuinely installable AND not already installed — so
# the card can never advertise something that would dead-end. Building it late
# also keeps it out of the edge-cached markup and out of the LCP path, and
# fixed positioning means it can never shift the prices under a reader's thumb.
#
# It waits for a sign the visitor actually stayed. Someone who bounced in four
# seconds does not want an icon on his home screen, and asking him teaches him
# to dismiss us; 15 seconds or a scroll into the price table is the filter.
_INSTALL_JS = """<script>
(function(){
 var SNOOZE='km_pwa_snooze', ev=null, card=null, engaged=false, shown=false;

 function tr(n,x){try{if(window.kmTrack)window.kmTrack(n,x||{});}catch(e){}}

 /* Already running as an installed app — nothing to offer. */
 function standalone(){
  try{return window.matchMedia('(display-mode: standalone)').matches
       ||window.navigator.standalone===true;}catch(e){return false;}
 }
 /* "अभी नहीं" is an answer, not an invitation to ask again tomorrow. */
 function snoozed(){
  try{return Date.now()-(+localStorage.getItem(SNOOZE)||0) < 30*24*3600*1000;}
  catch(e){return false;}
 }
 function snooze(){try{localStorage.setItem(SNOOZE,String(Date.now()));}catch(e){}}

 function close(why){
  if(!card)return;
  card.classList.remove('in');
  setTimeout(function(){if(card&&card.parentNode)card.parentNode.removeChild(card);card=null;},220);
  if(why)tr('pwa_prompt_dismissed',{how:why});
 }

 /* location.js may already be asking for GPS on this very page, from the same
    corner and at a higher z-index — two asks at once is both rude and, because
    that card covers this one, literally unclickable. Wait it out and take our
    turn after he has answered it; never stack. */
 function otherAskOpen(){return !!document.getElementById('km-loc-card');}

 /* The GPS card can also arrive AFTER ours — location.js shows it about 1.5s in,
    and a farmer who scrolls straight down beats it to the corner. Stand down if
    it does, and come back once he has dealt with it. Withdrawing is not a
    dismissal, so it must not burn the snooze. */
 function watch(){
  if(!card)return;
  if(otherAskOpen()){shown=false;close('');setTimeout(build,3000);return;}
  setTimeout(watch,1000);
 }

 function build(){
  if(card||shown||standalone()||snoozed()||!ev)return;
  if(otherAskOpen()){setTimeout(build,2000);return;}
  shown=true;
  var st=document.createElement('style');
  st.textContent=
   '.km-pwa{position:fixed;left:10px;right:10px;z-index:3499;'+
   'bottom:calc(16px + env(safe-area-inset-bottom));'+
   'display:flex;align-items:center;gap:11px;'+
   'padding:12px 12px 12px 13px;border-radius:16px;'+
   'background:#fff;border:1px solid #d7e6da;'+
   'box-shadow:0 10px 30px rgba(20,60,35,.20);'+
   'font-family:inherit;opacity:0;transform:translateY(14px);'+
   'transition:opacity .22s ease,transform .22s ease}'+
   'body.km-has-bn .km-pwa{bottom:calc(74px + env(safe-area-inset-bottom))}'+
   '.km-pwa.in{opacity:1;transform:none}'+
   '.km-pwa img{width:42px;height:42px;border-radius:11px;flex:0 0 auto}'+
   '.km-pwa-t{flex:1 1 auto;min-width:0}'+
   '.km-pwa-t b{display:block;font-size:14px;font-weight:800;color:#14361f;line-height:1.25}'+
   '.km-pwa-t span{display:block;font-size:11.5px;color:#5d7466;line-height:1.35;margin-top:2px}'+
   '.km-pwa-go{flex:0 0 auto;border:0;cursor:pointer;font-family:inherit;'+
   'font-size:13.5px;font-weight:800;color:#fff;background:#1b5e20;'+
   'padding:10px 15px;border-radius:11px}'+
   '.km-pwa-x{position:absolute;top:-9px;right:-3px;width:26px;height:26px;'+
   'border-radius:50%;border:1px solid #d7e6da;background:#fff;color:#7b8f81;'+
   'font-size:15px;line-height:1;cursor:pointer;padding:0}'+
   '@media(min-width:721px){.km-pwa{left:auto;right:20px;width:370px}}';
  document.head.appendChild(st);

  card=document.createElement('div');
  card.className='km-pwa';
  card.setAttribute('role','dialog');
  card.setAttribute('aria-label','कृषि मित्र ऐप जोड़ें');
  card.innerHTML=
   '<button class="km-pwa-x" type="button" aria-label="बंद करें">&times;</button>'+
   '<img src="/assets/logo-192.png" alt="" width="42" height="42">'+
   '<div class="km-pwa-t"><b>भाव रोज़ बदलता है</b>'+
   '<span>कृषि मित्र फ़ोन में जोड़ें — एक टैप में आज का भाव।</span></div>'+
   '<button class="km-pwa-go" type="button">जोड़ें</button>';
  document.body.appendChild(card);
  requestAnimationFrame(function(){if(card)card.classList.add('in');});
  tr('pwa_prompt_shown',{});
  /* First look is quick — the GPS card arrives on its own timer and a full
     second of the two overlapping reads as a glitch. */
  setTimeout(watch,250);

  card.querySelector('.km-pwa-x').onclick=function(){snooze();close('close');};
  card.querySelector('.km-pwa-go').onclick=function(){
   if(!ev){close('');return;}
   tr('pwa_prompt_tap',{});
   var e=ev;ev=null;close('');
   e.prompt();
   Promise.resolve(e.userChoice).then(function(r){
    var out=(r&&r.outcome)||'unknown';
    tr(out==='accepted'?'pwa_prompt_accepted':'pwa_prompt_declined',{outcome:out});
    /* Declined at the browser's own dialog — do not come back next visit. */
    if(out!=='accepted')snooze();
   }).catch(function(){});
  };
 }

 function engage(){if(engaged)return;engaged=true;build();}

 window.addEventListener('beforeinstallprompt',function(e){
  e.preventDefault();ev=e;
  tr('pwa_installable',{});
  if(engaged)build();
 });
 window.addEventListener('appinstalled',function(){tr('pwa_installed',{});close('');});

 setTimeout(engage,15000);
 window.addEventListener('scroll',function(){
  if(window.scrollY>window.innerHeight*0.6)engage();
 },{passive:true});
})();
</script>"""

# GA4 + Clarity. The server-rendered clusters (/bhav, /product, /naksha) are
# proxied under krashimitra.in, so the root-relative path resolves there; the
# backend also mounts frontend/ at "/", so it works on the origin domain too.
_ANALYTICS = '<script src="/analytics.js"></script>'


# The SSR twin of the shared shell's nav. /krashi_news is here because the
# news hub was reachable from the static pages' drawer but from NONE of the
# ~14k server-rendered /bhav pages — which are ~85% of the site's search
# traffic. Every farmer the site actually has was on a page that did not
# know the news section existed.
_NAV_ITEMS = [("bhav", f"{SITE}/bhav", "मंडी भाव"),
              ("news", f"{SITE}/krashi_news", "कृषि समाचार"),
              ("bazar", f"{SITE}/krashi_bajar", "कृषि बाज़ार"),
              ("weather", f"{SITE}/weather", "मौसम देखें"),
              ("shop", f"{SITE}/product/", "कृषि दुकान")]

_DRAWER_ITEMS = [("home", f"{SITE}/", "🏠", "मुख्य"),
                  ("weather", f"{SITE}/weather", "🌤️", "मौसम"),
                  ("mandi", f"{SITE}/bhav", "🏪", "मंडी भाव"),
                  ("bhav", f"{SITE}/bhav", "📈", "सभी भाव सूची"),
                  ("bazar", f"{SITE}/krashi_bajar", "🧺", "कृषि बाज़ार"),
                  ("shop", f"{SITE}/shop", "🛒", "दुकान"),
                  ("rental", f"{SITE}/rental", "⚙️", "किराये की मशीन"),
                  ("poultry", f"{SITE}/pashupalan/anda-rate", "🥚", "अंडे का रेट"),
                  ("khoj", f"{SITE}/khoj", "🔍", "कृषि खोज"),
                  ("map", f"{SITE}/naksha", "🗺️", "कृषि मानचित्र"),
                  ("naksha", f"{SITE}/naksha", "📐", "खेत नापें"),
                  ("news", f"{SITE}/krashi_news", "📢", "कृषि समाचार"),
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


def _header(active: str = "", quicknav: str | None = None) -> str:
    """Same pre-topbar/topbar/main-header/blue-bar stack as mandi.html, so a
    page reached from Google reads as the same product as the app, not a
    stripped-down doorway. Hamburger drawer uses a couple of inline onclick
    handlers rather than the app's JS bundle — these pages must stay light.

    `quicknav` replaces the blue bar's contents for a caller whose section is
    not the mandi tree. The bar is the one navigation strip on these pages that
    is ABOUT something, so a section that borrows this shell and leaves it
    alone ends up advertising गेहूं/धान/प्याज on top of an egg rate — which is
    what /pashupalan did until it passed its own. Default None keeps the crop
    links, so every existing caller renders byte-identical."""
    nav = "".join(
        f'<a class="header-nav-link{" active" if key == active else ""}" href="{href}">{label}</a>'
        for key, href, label in _NAV_ITEMS)
    drawer = "".join(
        f'<a href="{href}" class="sidebar-drawer-link{" active" if key == active else ""}">'
        f'<span class="sidebar-drawer-link-icon">{icon}</span><span>{label}</span></a>'
        for key, href, icon, label in _DRAWER_ITEMS)
    return f"""<div class="header-wrapper" id="header-wrapper">
<div class="pre-topbar">
<a href="mailto:krashimitra038@gmail.com" class="pre-topbar-helpline" title="कृषिमित्र से ईमेल पर संपर्क करें"><span class="pre-topbar-phone-icon"><svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor" aria-hidden="true"><path d="M20 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"/></svg></span> कृषिमित्र ईमेल: krashimitra038@gmail.com</a>
</div>
<div class="top-utility-bar"><div class="top-utility-inner">
<div class="top-utility-left">
<a href="{SITE}/" class="top-utility-link">मुख्य</a><span class="top-utility-divider">|</span>
<a href="{SITE}/map" class="top-utility-link">कृषि मानचित्र</a><span class="top-utility-divider">|</span>
<a href="{SITE}/articles/" class="top-utility-link">कृषि समाचार</a><span class="top-utility-divider">|</span>
<a href="{SITE}/sarkari_yojana" class="top-utility-link">सरकारी योजना</a>
</div>
<div class="top-utility-right">
<a href="https://wa.me/919870951001" target="_blank" rel="noopener" class="top-utility-helpline" title="कृषिमित्र हेल्पलाइन — व्हाट्सऐप पर मैसेज करें"><span class="pre-topbar-phone-icon"><svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor" aria-hidden="true"><path d="M12.04 2c-5.46 0-9.91 4.45-9.91 9.91 0 1.75.46 3.45 1.32 4.95L2 22l5.25-1.38c1.45.79 3.08 1.21 4.79 1.21h.01c5.46 0 9.9-4.45 9.9-9.91 0-2.65-1.03-5.14-2.9-7.01A9.816 9.816 0 0 0 12.04 2zm0 18.15h-.01c-1.5 0-2.97-.4-4.25-1.16l-.3-.18-3.12.82.83-3.04-.2-.31a8.196 8.196 0 0 1-1.26-4.37c0-4.54 3.7-8.24 8.25-8.24 2.2 0 4.27.86 5.83 2.42a8.19 8.19 0 0 1 2.41 5.83c0 4.55-3.7 8.24-8.24 8.24zm4.52-6.16c-.25-.12-1.47-.72-1.69-.81-.23-.08-.39-.12-.56.13-.17.25-.64.81-.78.97-.14.17-.29.19-.54.06-.25-.12-1.05-.39-1.99-1.23-.74-.66-1.23-1.47-1.38-1.72-.14-.25-.02-.38.11-.51.11-.11.25-.29.37-.43.12-.14.17-.25.25-.41.08-.17.04-.31-.02-.43-.06-.12-.56-1.34-.76-1.84-.2-.48-.41-.42-.56-.42-.14-.01-.31-.01-.48-.01-.17 0-.43.06-.66.31-.23.25-.86.85-.86 2.07 0 1.22.89 2.4 1.01 2.57.12.17 1.75 2.67 4.23 3.74.59.26 1.05.41 1.41.52.59.19 1.13.16 1.56.1.48-.07 1.47-.6 1.67-1.18.21-.58.21-1.08.14-1.18-.06-.11-.23-.17-.48-.29z"/></svg></span> कृषिमित्र हेल्पलाइन: +91 9870951001</a>
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
{_quicknav() if quicknav is None else quicknav}
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
window.kmHideLoading=function(){{if(ov)ov.classList.remove('show');}};
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
/* Clear the spinner whenever the page is (re)shown. On a Back/Forward
navigation the browser restores this page from its bfcache with the DOM
exactly as we left it — mid-navigation, so the overlay is still .show and
the spinner is stuck on. pageshow fires for both fresh loads and bfcache
restores, so the returning page always comes back clean. */
window.addEventListener('pageshow',window.kmHideLoading);
}})();
</script>
<script src="{_asset('api-config.js')}"></script>
<script src="{_asset('drawer-menu.js')}" defer></script>
<script src="{_asset('bottomnav.js')}" defer></script>
<script src="{_asset('location.js')}" defer></script>
<script src="{_asset('bhav-nearest.js')}" defer></script>
<script src="{_asset('ads.js')}" defer></script>
<script src="{_asset('km-social.js')}" defer></script>
<script src="{_asset('km-journey.js')}" defer></script>
<div class="topbar-spacer" id="topbar-spacer"></div>
<script src="{_asset('header-scroll.js')}"></script>"""


_FOOTER_NOTE = ("भाव भारत सरकार के data.gov.in (Agmarknet) से रोज़ अपडेट होते हैं।\n"
                "बेचने से पहले अपनी मंडी में भाव ज़रूर पुष्टि करें।")


def _footer(note: str = "") -> str:
    """`note` overrides the standing Agmarknet line for callers where it is not
    true. It is correct for anything priced off the mandi feed, and false for a
    page that is not: cane is bought by mills at an administered price, so on
    /ganna the default would claim a daily Agmarknet update for a number that
    changes once a season, and send the farmer to a mandi that never trades his
    crop. Default keeps every existing caller byte-identical."""
    # Second nav row: the widest-covered crop hubs, derived from the live
    # index. Every one of the ~14k server pages carries these links, so the
    # long tail of district pages continuously votes for the head-term pages
    # ("प्याज का भाव") that need the authority. Deduped by Hindi name — bajra
    # alone arrives under two Agmarknet spellings.
    idx = _get_index()
    tops = sorted(((len(idx["states"].get(cs, {})), cs, cn)
                   for cs, cn in idx.get("crops", {}).items() if _is_crop(cn)),
                  key=lambda t: -t[0])
    seen, crop_links = set(), []
    for _, cs, cn in tops:
        hi = _hindi_name(cn)
        if hi in seen:
            continue
        seen.add(hi)
        crop_links.append(f'<a href="{SITE}/bhav/{cs}">{escape(hi)} का भाव</a>')
        if len(crop_links) == 8:
            break
    crops_nav = ("<nav class=\"km-footer-nav km-footer-crops\">\n"
                 + "\n".join(crop_links) + "\n</nav>") if crop_links else ""
    return f"""<footer class="km-footer"><div class="km-footer-inner">
<div class="km-footer-brand">🌾 कृषि मित्र</div>
<nav class="km-footer-nav">
<a href="{SITE}/">होम</a>
<a href="{SITE}/bhav">सभी भाव</a>
<a href="{SITE}/pashupalan">पशुपालन</a>
<a href="{SITE}/weather">मौसम</a>
<a href="{SITE}/chat">AI सहायक</a>
{f'<a href="{SITE}/sponsor">विज्ञापन दें</a>' if sponsors else ''}
<a href="{SITE}/donate">सहयोग करें</a>
</nav>
{crops_nav}
<div class="km-footer-note">{escape(note or _FOOTER_NOTE)}</div>
</div></footer>"""


# The edge caches these only when the origin opts in. The header used to be
# Netlify-CDN-Cache-Control, which Cloudflare ignores — so from the 16 Sep 2026
# move to Cloudflare → Render until this line changed, every /bhav page was a
# cache miss and Render paid for all 14k of them against a 5 GB/mo cap.
# CDN-Cache-Control is the vendor-neutral spelling and both honour it.
#
# 1 h at the edge (prices move ~5x/day, fetched 08/10/13/16/20 IST) plus a day
# of stale-while-revalidate keeps Googlebot crawling 14k URLs off Render's
# cold-start latency — crawl speed caps how fast the tree gets indexed.
# Browsers get 5 min so a farmer refreshing still sees fresh numbers quickly.
# Was 30 min until 25 Sep 2026: every edge refresh is a full page billed to
# Render's 5 GB/month, which was on course to run out a third time.
_CACHE_HEADERS = {
    "Cache-Control": "public, max-age=300",
    "CDN-Cache-Control":
        "public, max-age=3600, stale-while-revalidate=86400",
}
# Pages _doc renders for other sections (/naksha, /ganna, /sawal, /product,
# /pashupalan…) carry no mandi price that moves during the day, so the edge
# may hold them 3 h — a third of the origin refreshes for the same traffic.
_CACHE_HEADERS_SLOW = {
    "Cache-Control": "public, max-age=300",
    "CDN-Cache-Control":
        "public, max-age=10800, stale-while-revalidate=86400",
}


def _journey(canon: str, crop: str, lang: str, robots: str) -> str:
    """The "आगे क्या करें" strip — services/ecosystem.py, rendered here so that
    every section using this shell is in the ecosystem by default.

    THIS IS THE WHOLE POINT OF PUTTING IT IN _doc(). /product, /ganna, /rental,
    /naksha, /sawal, /pashupalan and /krashi_dukan all render through this
    function; none of them had a single link out to any of the others. A future
    section gets the strip the day it ships, without a line of its own — and
    opting OUT is the thing that takes an argument, which is the right way
    round for a defect whose cause was "nobody remembered to add the links".

    The names matter more than the URL: ecosystem.py refuses to print a step it
    cannot label in the reader's script, so a district we hand over as the slug
    "bijnor" silently degrades to the generic wording. This is the one place
    that holds both the index (slug → the feed's spelling) and the Hindi/Marathi
    tables, so it resolves them here rather than making each caller do it.

    A NOFOLLOW page gets nothing, and nofollow is the right test rather than
    noindex. "noindex, follow" is the site saying keep this URL out of the
    index but do follow its links — an empty dealer directory or a credits
    page, which is precisely where a reader most needs somewhere to go next.
    "noindex, nofollow" is the UPI collect page: a transaction, where an
    onward menu is a distraction from the one thing the page is for.
    """
    if "nofollow" in (robots or ""):
        return ""
    try:
        ctx = ecosystem.parse(canon, crop=crop, lang=lang)
        if ctx.crop:
            idx = _get_index()
            commodity = idx.get("crops", {}).get(ctx.crop, "")
            if commodity:
                ctx.crop_hi = state_lang.crop(_hindi_name(commodity), lang)
            state = idx.get("states", {}).get(ctx.crop, {}).get(ctx.state, "")
            district = (idx.get("dists", {}).get(ctx.crop, {})
                        .get(ctx.state, {}).get(ctx.district, ""))
        else:
            # A place-only page (/bhav/rajya/…, /naksha/…, /ganna/…) — the slug
            # → spelling map lives per crop, so read the names off any crop
            # that reports from there rather than not naming the place at all.
            state = district = ""
            idx = _get_index()
            for cs in idx.get("dists", {}):
                names = idx["dists"][cs].get(ctx.state, {})
                if ctx.district in names:
                    state = idx["states"][cs][ctx.state]
                    district = names[ctx.district]
                    break
        if state:
            ctx.state_hi = _hindi_state(state)
        if district:
            ctx.district_hi = state_lang.district(
                _hindi_district(state, district), lang)
        # with_css=False: the sheet rides in _CSS, in the <head>, once. The
        # article builder takes the other branch — a static page has no shared
        # stylesheet of ours to append to.
        return ecosystem.journey_html(ctx, with_css=False)
    except Exception:                       # never turn a working page into a 500
        logger.warning("[journey] strip skipped for %s", canon, exc_info=True)
        return ""


def _sponsor_strip(canon: str) -> str:
    """The paid slot, placed once per page between the content and the "आगे
    क्या करें" strip.

    WHY HERE AND NOWHERE ELSE. It is below everything the farmer came for and
    below the page's own call to action, which is the same rule frontend/ads.js
    follows and for a better reason: a sponsor card that outranks the price
    table costs us the trust the sponsorship is priced on. One slot per page,
    never two — services/sponsors.py already caps one live sponsor per
    category, and stacking categories would turn the bottom of ~14k pages into
    an ad stack.

    Returns "" when nobody is paying, which is every page today. An unsold slot
    renders nothing at all — no label, no reserved box, no gap.
    """
    if sponsors is None:
        return ""
    try:
        path = "/" + canon.split("//", 1)[-1].split("/", 1)[1]
    except IndexError:
        path = "/"
    return sponsors.card_html(path.split("?", 1)[0])


def _doc(title: str, desc: str, canon: str, crumbs: str, body: str,
         ld: str = "", og_img: str = "", active: str = "bhav",
         extra_css: str = "", robots: str = "", head_extra: str = "",
         updated: str = "", footer_note: str = "", crop: str = "",
         lang: str = "hi", quicknav: str | None = None,
         journey: bool = True) -> HTMLResponse:
    """One page shell for all four tiers — head, header, crumbs, body, footer.
    `active` defaults to "bhav" for this module's own pages; other SEO routes
    (e.g. product.py) that reuse this shell pass their own nav key/"" so they
    don't show up with भाव wrongly highlighted. `extra_css` lets those callers
    layer on rules of their own without duplicating the tokens/header/footer —
    _CSS here is this module's own, so a caller's local override of a same-named
    variable is invisible to this closure; extra_css is the only way in.
    `robots` is for pages that must not be indexed *in some states* — the buyer
    directory with no listings yet. Empty (the default) emits no tag at all, so
    every existing caller keeps the current indexable behaviour.
    `head_extra` is raw <head> markup for a caller that needs more than CSS —
    naksha.py's map pages pull in the Leaflet stylesheet, which cannot ride in
    extra_css because @import is only valid at the top of a sheet.
    `updated` is the real "YYYY-MM-DD" the page's numbers were last reported —
    NEVER today's date, NEVER server-render time. A page whose FAQ states a
    specific "आज का भाव ₹X" only stays honest as long as Google's cached copy
    is recent; without a dateModified/Last-Modified signal Google has nothing
    to judge that by and can serve a weeks-old snippet as if it were today's
    (see docs — the "13 Jul" Bareilly wheat snippet still live on 2 Aug). Pass
    "" (the default) for pages with no per-page number to go stale — omitting
    the signal costs nothing; a wrong one costs trust in every date after it.
    `footer_note` replaces the footer's standing "prices update daily from
    Agmarknet" line for a caller where that is not true — see _footer.
    `crop` is the crop SLUG (not the display name) for a page about one crop.
    It only stamps data-crop-type/data-layout on <body> — the crop's sale
    cadence, from services/crop_types.py. Nothing reads those yet; they exist
    so the perishable/storable layouts can diverge later without a URL change,
    and so "which layout does this crop get" is answerable by looking at the
    page. Callers with no single crop (the hub, the state pages, /find) pass
    nothing and get no attributes at all.
    `quicknav` is raw markup replacing the blue bar's crop links, for a caller
    whose section is not the mandi tree — see _header. Default None keeps them.
    `lang` is the page's own language code from services/state_lang, and it
    reaches only <html lang> and og:locale. Any caller that rendered its title
    in that language must pass it: a Marathi title on a page still declaring
    lang="hi" tells Google the two disagree, and the tag is believed over the
    prose. Default "hi" leaves every other caller byte-identical.
    `journey` is the "आगे क्या करें" strip — services/ecosystem.py, ON by
    default, because the defect it fixes is every section forgetting to link to
    every other one and a default of False would reproduce it for the next
    section built. Pass False only where an onward menu is genuinely wrong for
    the page. A noindex page opts itself out — see _journey."""
    og = og_img or f"{SITE}/images/og-banner.webp"
    # Resolved here rather than at each call site so all four crop tiers are
    # guaranteed to agree — a page whose type differs from its sibling tier's
    # would be worse than no marker.
    body_attrs = ""
    if crop:
        _ct = crop_types.crop_type(crop)
        body_attrs = (f' data-crop-type="{escape(_ct, quote=True)}"'
                      f' data-layout="{escape(crop_types.type_meta(_ct)["layout"], quote=True)}"')
    # /bhav pages (active=="bhav") ship NO visible breadcrumb — the trail lives
    # only as BreadcrumbList JSON-LD in `ld` (still feeds SERP breadcrumbs).
    # Reused callers (e.g. product.py, active=="shop") keep their visible one.
    crumbs_nav = (f'<nav class="crumbs">{crumbs}</nav>'
                  if (crumbs and active != "bhav") else "")
    base_headers = _CACHE_HEADERS if active == "bhav" else _CACHE_HEADERS_SLOW
    date_ld, headers = "", base_headers
    if updated:
        date_ld = _ld({"@context": "https://schema.org", "@type": "WebPage",
                        "@id": canon, "url": canon, "dateModified": updated})
        y, m, d = (int(x) for x in updated.split("-"))
        headers = {**base_headers,
                   "Last-Modified": formatdate(
                       calendar.timegm(date(y, m, d).timetuple()), usegmt=True)}
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="{state_lang.html_lang(lang)}">
<head>
{_ANALYTICS}
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title>
<meta name="description" content="{escape(desc)}">
<link rel="canonical" href="{canon}">
{f'<meta name="robots" content="{escape(robots)}">' if robots else ''}
<meta property="og:type" content="website">
<meta property="og:site_name" content="कृषि मित्र (KrashiMitra)">
<meta property="og:title" content="{escape(title)}">
<meta property="og:description" content="{escape(desc)}">
<meta property="og:image" content="{escape(og)}">
<meta property="og:url" content="{canon}">
<meta property="og:locale" content="{state_lang.og_locale(lang)}">
<meta name="twitter:card" content="summary_large_image">
{_ICON}
{_PWA}
{_FONTS}
{head_extra}
{ld}
{date_ld}
<style>{_CSS}{sponsors.CSS if sponsors else ""}{extra_css}</style>
</head>
<body{body_attrs}>
{_header(active, quicknav)}
{crumbs_nav}
<div class="wrap">
{body}
{_sponsor_strip(canon)}
{_journey(canon, crop, lang, robots) if journey else ''}
</div>
{_footer(footer_note)}
{_INSTALL_JS}
</body>
</html>""", headers=headers)


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


def _nf_alternatives(idx: dict | None, cs: str, ss: str) -> str:
    """What to offer when a crop×place combination does not exist.

    Agmarknet covers a crop in the states that actually trade it, so plenty of
    plausible URLs have no data and never will: /bhav/wheat/keralam,
    /bhav/apple/bihar, /bhav/cardamom/uttar-pradesh. Those stay 404 on purpose
    — publishing an empty page for every crop×state pair would add ~10,000
    thin URLs to an index we decided on 23 Aug 2026 to PRUNE, not grow.

    But 404 is a status code, not an excuse for a dead end. The old page said
    only "यह भाव पेज अभी उपलब्ध नहीं है" and linked the hub, so a farmer who
    asked for wheat in Kerala had to start over and guess again. When we know
    the crop, we know exactly which states do report it; when we know the
    place, we know which crops it reports. Show that.
    """
    if not idx:
        return ""
    crops = idx.get("crops", {})
    blocks = []

    commodity = crops.get(cs)
    if commodity:
        hi = _hindi_name(commodity)
        states = sorted(idx.get("states", {}).get(cs, {}).items(), key=lambda kv: kv[1])
        if states:
            cards = "".join(
                _state_card(f"/bhav/{cs}/{s}", sn,
                            len(idx.get("dists", {}).get(cs, {}).get(s, {})), "जिले")
                for s, sn in states)
            blocks.append(
                f'<h2>{escape(hi)} का भाव इन {len(states)} राज्यों में मिलता है</h2>'
                f'<div class="place-grid">{cards}</div>')

    # The place half. `ss` is only a real state slug when some crop reports it,
    # which is exactly what _states_all knows — a typo'd slug simply yields
    # nothing here and the crop block above still carries the page.
    state_name = _state_name(idx, ss) if ss else ""
    if state_name:
        here = sorted(_crops_in(idx, ss, "").items(),
                      key=lambda kv: (_tile_rank(kv[1]), _hindi_name(kv[1])))[:36]
        if here:
            chips = "".join(
                _crop_chip(f"/bhav/{c}/{ss}", _hindi_name(cn), cn) for c, cn in here)
            blocks.append(
                f'<h2>{escape(_hindi_state(state_name))} की मंडियों में ये फसलें बिक रही हैं</h2>'
                f'<div class="chips">{chips}</div>')

    return "\n".join(blocks)


def _not_found(idx: dict | None = None, cs: str = "", ss: str = "") -> HTMLResponse:
    """A crop can drop out of the feed (mandi stops reporting) while Google still
    holds the URL — send that farmer into the app instead of a dead end.

    Pass `idx` plus whatever of the URL resolved (`cs` crop slug, `ss` state
    slug) and the page lists the real alternatives — see _nf_alternatives.
    Still a 404: the URL genuinely has no data, and we are not adding it to the
    index. It just stops being a dead end for the farmer who reached it."""
    alts = _nf_alternatives(idx, cs, ss)
    sub = ("हो सकता है इस मंडी ने हाल में इस फसल की रिपोर्ट न भेजी हो। नीचे से चुनें —"
           if alts else
           "हो सकता है इस मंडी ने हाल में इस फसल की रिपोर्ट न भेजी हो।")
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="hi">
<head>
{_ANALYTICS}
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
<p class="hero-sub">{sub}</p>
</div>
</div>
{alts}
<div class="cta-row">
<a class="btn btn-app" href="{SITE}/bhav">सभी मंडी भाव देखें</a>
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
                    key=lambda kv: _hindi_district(s_slug, kv[1]))

    crop_opts = "".join(
        f'<option value="/bhav/{cs}/{s_slug}/{d_slug}"{" selected" if cs == c_slug else ""}>'
        f'{escape(_hindi_name(cn))}</option>' for cs, cn in crops)
    # Switching state can't keep the district, so it lands on the state tier.
    state_opts = "".join(
        f'<option value="/bhav/{c_slug}/{ss}"{" selected" if ss == s_slug else ""}>'
        f'{escape(_hindi_state(sn))}</option>' for ss, sn in states)
    dist_opts = "".join(
        f'<option value="/bhav/{c_slug}/{s_slug}/{ds}"{" selected" if ds == d_slug else ""}>'
        f'{escape(_hindi_district(s_slug, dn))}</option>' for ds, dn in dists)

    return f"""<div class="ctl">
<label class="ctl-f"><span>फसल</span>
<select onchange="if(this.value)location.href=this.value" aria-label="फसल चुनें">{crop_opts}</select></label>
<label class="ctl-f"><span>राज्य</span>
<select onchange="if(this.value)location.href=this.value" aria-label="राज्य चुनें">{state_opts}</select></label>
<label class="ctl-f"><span>मंडी / जिला</span>
<select onchange="if(this.value)location.href=this.value" aria-label="जिला चुनें">{dist_opts}</select></label>
</div>"""


def _state_name(idx: dict, ss: str) -> str:
    """Display spelling of a state slug, from whichever crop reports it. The
    place hubs (/bhav/rajya/…) have no crop to look it up under."""
    for smap in idx.get("states", {}).values():
        if ss in smap:
            return smap[ss]
    return ""


def _dist_name(idx: dict, ss: str, ds: str) -> str:
    for dmap in idx.get("dists", {}).values():
        hit = dmap.get(ss, {}).get(ds)
        if hit:
            return hit
    return ""


# ── आज का भाव, जगह के हिसाब से — the number ON the place hubs ────
#
# The place hubs used to be the only pages under /bhav that carried no price
# at all: every crop card said "भाव देखें →" and the farmer had to guess which
# of 105 crops was worth a tap. That was survivable while the hubs were only a
# crawl path — it stopped being survivable the day the WhatsApp channel post
# started linking here. The post prints five prices under "अपनी मंडी का भाव
# यहाँ 👇", and the page it pointed at printed none; a follower who tapped it
# landed on a picker and two more taps from the number he had just been shown.
#
# THE ARITHMETIC IS DELIBERATELY services/wa_post._crop_lines': the plain mean
# of every row's modal price for that crop in that place. The channel post and
# this page are then one calculation over one snapshot and cannot disagree —
# which is the invariant wa_post's own file header exists to protect. Anything
# cleverer here (trimmed means, distinct-market weighting) would make the post
# wrong instead of making the page better.
#
# Python, not SQL AVG(): mandi_prices.modal_price is a String column carrying
# whatever Agmarknet sent, commas and blanks included, so _num decides what is
# a number — the same gate every other price on the site passes through.
#
# One grouped read per place, TTL-cached under the 30-minute edge cache the
# hubs already ship with (_CACHE_HEADERS), because Netlify serves ~all of this
# traffic from the edge and Render's free tier is the thing being protected.
_place_rates: dict = {}
_PLACE_RATES_TTL = 900


def _rates_in(idx: dict, ss: str, ds: str = "") -> dict:
    """{crop slug → {avg, mandis}} for every crop reported in one state, or in
    one district of it. Empty dict when the place has nothing priced — every
    caller must keep working without a number, because a crop can be in the
    index (it reported once, so its URL exists forever) and absent from
    today's snapshot."""
    key = (ss, ds)
    now = time.time()
    hit = _place_rates.get(key)
    if hit and (now - hit[0]) < _PLACE_RATES_TTL:
        return hit[1]

    sn, dn = _state_name(idx, ss), (_dist_name(idx, ss, ds) if ds else "")
    if not sn or (ds and not dn):
        return {}

    db = SessionLocal()
    try:
        q = (db.query(MandiPrice.commodity, MandiPrice.market, MandiPrice.modal_price)
               .filter(MandiPrice.state.ilike(sn)))
        if dn:
            q = q.filter(MandiPrice.district.ilike(dn))
        rows = q.all()
    finally:
        db.close()

    agg: dict = {}
    for commodity, market, modal in rows:
        m = _num(modal)
        if not (commodity and m and _is_crop(commodity)):
            continue
        # Slugified, because the card being labelled is keyed by slug and
        # several raw spellings collapse onto one (see idx["raws"]) — keeping
        # them apart here would print one of three कद्दू prices at random.
        slot = agg.setdefault(_slugify(commodity), {"modals": [], "mandis": set()})
        slot["modals"].append(m)
        slot["mandis"].add(market or "")

    out = {cs: {"avg": round(sum(v["modals"]) / len(v["modals"])),
                "mandis": len([m for m in v["mandis"] if m]) or len(v["modals"])}
           for cs, v in agg.items() if v["modals"]}
    _place_rates[key] = (now, out)
    return out


def _crops_in(idx: dict, ss: str = "", ds: str = "") -> dict:
    """{crop slug → commodity} actually reported in one district (ss+ds), one
    state (ss), or anywhere (neither). Membership is what makes a place-scoped
    crop link safe: every crop here really has a page at that place."""
    out = {}
    for c, cn in idx.get("crops", {}).items():
        if not _is_crop(cn):
            continue
        if ds:
            if ds not in idx.get("dists", {}).get(c, {}).get(ss, {}):
                continue
        elif ss:
            if ss not in idx.get("states", {}).get(c, {}):
                continue
        out[c] = cn
    return out


def _states_all(idx: dict) -> dict:
    """{state slug → state} across every crop — the crop-less state list."""
    out = {}
    for c, smap in idx.get("states", {}).items():
        if _is_crop(idx.get("crops", {}).get(c, "")):
            out.update(smap)
    return out


def _dists_in_state(idx: dict, ss: str) -> dict:
    """{district slug → district} reporting ANY crop in one state."""
    out = {}
    for c, smap in idx.get("dists", {}).items():
        if _is_crop(idx.get("crops", {}).get(c, "")):
            out.update(smap.get(ss, {}))
    return out


def _hub_selector(cs: str, ss: str, ds: str, idx: dict,
                   known_crop: bool = False, known_state: bool = False,
                   known_dist: bool = False, show_crop: bool = True) -> str:
    """Same crop/state/district quick-jump as _switchers(), but a type-or-speak
    <input list=datalist> instead of a plain <select> — the hub's district list
    can run to 60+ entries, too many to scan by scrolling on a first visit.
    Kept separate from _switchers() (used on tier-4 pages, where each field is
    already resolved, not picked from scratch) so that one keeps its plain,
    no-JS-safe <select> untouched.

    known_crop/known_state/known_dist say which parts of the URL are REAL, and
    that is what every destination is built from. A field the page has not
    resolved must never be borrowed from a seed: /bhav/rajya/{state} seeds cs
    with the state's widest-covered crop purely for ranking, and pointing the
    जिला options at /bhav/{seed}/{ss}/{ds} sent a farmer who picked Bijnor on
    the Uttar Pradesh hub straight into WHEAT prices he never asked for.

    So, by what is known:
      crop known   → राज्य/जिला stay inside that crop's tree (tier 2/3)
      crop unknown → they go to the crop-less place hubs, /bhav/rajya/…, which
                     ask for the crop instead of guessing one
      place known  → फसल carries it: /bhav/{crop}/{ss}[/{ds}]
    Each list is the real membership from idx (crops reported in that place,
    districts that report anything there), so no combination can 404."""
    cur_crop = _hindi_name(idx["crops"].get(cs, "")) if known_crop else ""
    cur_state = _hindi_state(_state_name(idx, ss)) if known_state else ""
    raw_dist = _dist_name(idx, ss, ds) if known_dist else ""
    cur_dist = _hindi_district(ss, raw_dist) if raw_dist else ""

    crops = sorted(
        _crops_in(idx, ss if known_state else "", ds if known_dist else "").items(),
        key=lambda x: (_tile_rank(x[1]), _hindi_name(x[1])))
    if known_crop:
        states = sorted(idx["states"].get(cs, {}).items(), key=lambda kv: kv[1])
        dists = sorted(idx["dists"].get(cs, {}).get(ss, {}).items(),
                       key=lambda kv: _hindi_district(ss, kv[1]))
    else:
        states = sorted(_states_all(idx).items(), key=lambda kv: kv[1])
        dists = sorted(_dists_in_state(idx, ss).items(),
                       key=lambda kv: _hindi_district(ss, kv[1]))

    place = (f"/{ss}/{ds}" if known_dist else f"/{ss}") if known_state else ""
    crop_map = {_hindi_name(cn): f"/bhav/{c}{place}" for c, cn in crops}
    state_map = ({_hindi_state(sn): f"/bhav/{cs}/{s}" for s, sn in states} if known_crop
                 else {_hindi_state(sn): f"/bhav/rajya/{s}" for s, sn in states})

    dist_map = {}
    dist_alt = {}
    for d, dn in dists:
        hi_d = _hindi_district(ss, dn)
        label = hi_d
        if label in dist_map:
            label = f"{hi_d} ({dn})"
        dist_map[label] = f"/bhav/{cs}/{ss}/{d}" if known_crop else f"/bhav/rajya/{ss}/{d}"
        dist_alt[label] = f"{dn} {d} {d.replace('-', ' ')}".strip()

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
               alt_var: str = "null", value: str = "", has_loc: bool = False) -> str:
        var = list_id.replace("-", "_")
        inp_id = f"{list_id}-i"
        loc_id = f"{list_id}-loc"
        # data-valid marks a prefilled field as a real pick, not free-typed text —
        # kmComboBlur()/kmComboReject() only wipe fields WITHOUT that flag, so an
        # already-known crop/state stays shown instead of vanishing on first blur.
        val_attr = f'value="{escape(value)}" data-valid="1" ' if value else ""
        loc_btn = (f'<button type="button" class="ctl-loc" id="{loc_id}" '
                   f'onclick="kmLoc(\'{inp_id}\',\'{var}\')" '
                   f'title="मेरी लोकेशन से चुनें" aria-label="मेरी लोकेशन">'
                   f'{_LOC_SVG_HTML}</button>') if has_loc else ""
        return f"""<label class="ctl-f"><span>{label}</span>
<div class="ctl-input-row">
<input id="{inp_id}" {val_attr}autocomplete="off" placeholder="{escape(placeholder)}"
aria-label="{escape(placeholder)}"
oninput="kmComboFilter('{inp_id}',window.{var},{alt_var})"
onfocus="kmComboOpen('{inp_id}',window.{var},{alt_var})"
onkeydown="kmComboKeydown(event,'{inp_id}',window.{var},{alt_var})"
onblur="kmComboBlur('{inp_id}')">
{loc_btn}
<button type="button" class="ctl-mic" onclick="kmVoice('{inp_id}','{var}')" aria-label="आवाज़ से {escape(label)} खोजें">{_MIC_SVG}</button>
</div>
<ul class="ctl-list" id="{inp_id}-list" role="listbox"></ul></label>"""

    fl = []
    if show_crop:
        fl.append(_field("फसल", "dl-hub-crop", "फसल चुनें", crop_map, "window.dl_hub_crop_alt", cur_crop, has_loc=False))
    fl.append(_field("राज्य", "dl-hub-state", "राज्य चुनें", state_map, "window.dl_hub_state_alt", cur_state, has_loc=True))
    fl.append(_field("मंडी / जिला", "dl-hub-dist", "मंडी / जिला चुनें", dist_map, "window.dl_hub_dist_alt", cur_dist, has_loc=True))
    fields = "".join(fl)

    maps_js = "".join(
        f'window.{var}={_json.dumps(m, ensure_ascii=False)};'
        for var, m in (("dl_hub_crop", crop_map), ("dl_hub_state", state_map),
                       ("dl_hub_dist", dist_map), ("dl_hub_crop_alt", crop_alt),
                       ("dl_hub_state_alt", state_alt), ("dl_hub_dist_alt", dist_alt)))

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
?matches.slice(0,80).map(function(k){{return '<li role="option">'+k+'</li>';}}).join('')
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
function kmLoc(inputId,mapVar){{
var btn=document.getElementById(inputId.replace(/-i$/, '-loc'));
if(!navigator.geolocation){{setPinMode(true, 'लोकेशन उपलब्ध नहीं — नक्शे पर अपनी जगह टैप करें');return;}}
if(btn){{btn.classList.remove('active');btn.classList.add('loading');}}

function _applyLoc(lat,lon){{
var url='https://api.bigdatacloud.net/data/reverse-geocode-client?latitude='+lat+'&longitude='+lon+'&localityLanguage=hi';
fetch(url).then(function(res){{return res.json();}}).then(function(d){{
if(btn){{btn.classList.remove('loading');btn.classList.add('active');}}
var state=(d.principalSubdivision||'').trim();
var city=(d.city||d.locality||'').trim();
var admin=[];
if(d.localityInfo&&Array.isArray(d.localityInfo.administrative)){{
d.localityInfo.administrative.forEach(function(a){{
if(a&&a.name){{var cl=a.name.replace(/\\s*(District|Division|जिला|जिल्हा|मण्डल)\\s*/gi,'').trim();if(cl)admin.push(cl);}}
}});
}}
var map=window[mapVar]||{{}};
var alt=window[mapVar+'_alt']||{{}};
var matchedKey=null;
var cands=[city].concat(admin).concat([state]).filter(Boolean);
for(var i=0;i<cands.length;i++){{
var c=cands[i];
if(map[c]){{matchedKey=c;break;}}
var cLow=c.toLowerCase();
for(var k in map){{
var kLow=k.toLowerCase(),altVal=((alt&&alt[k])||'').toLowerCase();
if(kLow===cLow||kLow.indexOf(cLow)!==-1||cLow.indexOf(kLow)!==-1||altVal===cLow||altVal.indexOf(cLow)!==-1){{matchedKey=k;break;}}
}}
if(matchedKey)break;
}}
var el=document.getElementById(inputId);
if(matchedKey){{
kmComboSelect(inputId,matchedKey,map);
}}else{{
var fill=city||admin[0]||state||'';
if(el&&fill){{el.value=fill;el.dataset.valid='1';kmComboFilter(inputId,map);el.focus();}}
}}
}}).catch(function(){{if(btn)btn.classList.remove('loading');}});
}}

try{{
var stored=JSON.parse(localStorage.getItem('km_geo')||'null');
if(stored&&stored.lat&&stored.lon&&(Date.now()-(stored.ts||0)<7*86400000)){{
setTimeout(function(){{_applyLoc(stored.lat,stored.lon);}},300);
return;
}}
}}catch(_){{}}

navigator.geolocation.getCurrentPosition(function(pos){{
try{{
localStorage.setItem('km_geo',JSON.stringify({{
status:'granted',lat:+pos.coords.latitude.toFixed(5),lon:+pos.coords.longitude.toFixed(5),ts:Date.now()
}}));
}}catch(_){{}}
_applyLoc(pos.coords.latitude,pos.coords.longitude);
}},function(){{if(btn)btn.classList.remove('loading');}},{{enableHighAccuracy:false,timeout:10000,maximumAge:600000}});
}}
</script>"""


def _axis_band(lo: float, hi: float) -> tuple[float, float]:
    """A drawable (lo, hi) for a price axis, given the range the data actually has.

    A flat series is normal, not an edge case — a mandi that reports the same
    modal price three days running is a mandi where nothing happened. But
    `span = (hi - lo) or 1` turned that into a chart which lied twice over:
    every point mapped to the bottom of the plot, so a steady price looked like
    it had collapsed, and all three gridlines rounded to the same rupee value.
    /bhav/wheat/uttar-pradesh/meerut shipped as a flat line on the floor under
    an axis reading ₹2,636 / ₹2,636 / ₹2,636.

    So the axis gets a minimum height, centred on the data: the labels come out
    distinct and a flat line is drawn flat, through the middle, where it
    belongs. The floor is 2% of the price or ₹4, whichever is larger — 2% keeps
    three labels a rupee apart at any price level a mandi quotes, and the ₹4
    covers the cheap per-kg crops where 2% rounds away to nothing.

    Widening also fixes the quieter half of the same problem: the old axis
    rescaled to whatever range it was handed, so a ₹6 wobble on a ₹2,600 crop
    was stretched to full chart height and read as a cliff. Under this floor a
    0.2% drift now looks like the 0.2% drift it is. Anything moving more than
    2% is untouched — real moves still fill the chart.
    """
    floor = max(hi * 0.02, 4.0)
    if hi - lo >= floor:
        return lo, hi
    mid = (hi + lo) / 2
    return mid - floor / 2, mid + floor / 2


def _trend_colour(vals: list[float]) -> str:
    """Green up, red down, neutral for a price that did not move.

    Flat used to take the up-colour off a `>=`, which put a rising green on a
    chart whose whole message is that nothing rose."""
    if vals[-1] > vals[0]:
        return "#1b7a3d"
    if vals[-1] < vals[0]:
        return "#c0392b"
    return "#5f7368"


def _chart(vals: list[float]) -> str:
    """Full-width daily trend chart. The old page buried this in a 64px table cell —
    it is the one thing a farmer cannot get from a Google snippet, so it leads.

    `vals` is one point per CALENDAR day, oldest first (see _district_series), so
    the x-axis can name a real number of days. It used to be one mandi's last N
    *reports* labelled "{N} दिन पहले", which was wrong twice over: the points
    were not daily, and N points span N-1 days even when they are.

    Under 3 points there is no trend to show, only a big box with a straight line in
    it, so the chart is dropped entirely and the per-mandi sparkline carries the move.
    Markets report irregularly, so short series are common, not an edge case."""
    if len(vals) < 3:
        return ""
    w, h = 600, 150
    pad_l, pad_r, pad_t, pad_b = 46, 12, 16, 24
    lo, hi = _axis_band(min(vals), max(vals))
    span = hi - lo
    n = len(vals)

    def x(i): return pad_l + i * (w - pad_l - pad_r) / (n - 1)
    def y(v): return pad_t + (1 - (v - lo) / span) * (h - pad_t - pad_b)

    pts  = [(x(i), y(v)) for i, v in enumerate(vals)]
    line = " ".join(f"{px:.1f},{py:.1f}" for px, py in pts)
    area = (f"M{pts[0][0]:.1f},{h - pad_b:.1f} "
            + " ".join(f"L{px:.1f},{py:.1f}" for px, py in pts)
            + f" L{pts[-1][0]:.1f},{h - pad_b:.1f} Z")
    col    = _trend_colour(vals)
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
<text x="{pad_l}" y="{h - 7}" font-size="11" fill="#7c8983">{n - 1} दिन पहले</text>
<text x="{w - pad_r}" y="{h - 7}" font-size="11" fill="#7c8983" text-anchor="end">आज</text>
</svg>"""


def _sparkline(points: list[str]) -> str:
    """Inline SVG sparkline from the row's 7-day modal history."""
    vals = [v for v in (_num(p) for p in points) if v is not None]
    if len(vals) < 2:
        return ""
    # Same rule as _chart: an unchanged week is a flat line through the middle
    # of the box, not one pinned to its floor.
    lo, hi = _axis_band(min(vals), max(vals))
    span = hi - lo
    w, h = 64, 18
    step = w / (len(vals) - 1)
    pts = " ".join(f"{i * step:.1f},{h - 2 - (v - lo) / span * (h - 4):.1f}"
                   for i, v in enumerate(vals))
    color = _trend_colour(vals)
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


def _median_by(rows: list, key: str) -> dict:
    """{state|district → MEDIAN modal price}. Median, not mean, so one Agmarknet
    unit-error row (an occasional ₹40k 'wheat' line) can't skew a district's
    representative price — the mean version once produced a phantom cross-district
    delta of '+₹5,242 ज्यादा' on a ₹2,449 crop. Used by the district page's
    'other districts' comparison, where outlier immunity matters most."""
    buckets: dict[str, list] = {}
    for r in rows:
        k, m = r.get(key), _num(r.get("modal_price"))
        if k and m:
            buckets.setdefault(k, []).append(m)
    return {k: round(statistics.median(v)) for k, v in buckets.items() if v}


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

    title = (f'{escape(q)} — खोज परिणाम, मंडी भाव व कृषि जानकारी' if query
             else 'फसल या उत्पाद खोजें — मंडी भाव, खाद-बीज व लेख')
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="hi">
<head>
{_ANALYTICS}
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
    # <lastmod> is the newest arrival date for the URL's slice of the history
    # (idx["dates"]), NOT date.today(): stamping every URL "today" on every
    # request taught Google to distrust the whole field — 100% of pages
    # claiming daily change is indistinguishable from noise, and it wastes
    # recrawl budget on districts that stopped reporting weeks ago. Rollups:
    # a state page is as fresh as its newest district, a crop as its newest
    # state. A combo with no date (pre-migration rows) omits <lastmod> —
    # a missing lastmod costs nothing, a false one costs trust in all of them.
    idx = _get_index()
    dates = idx.get("dates", {})
    urls = []          # (url, lastmod-or-"")
    site_last = ""
    # Buyer-directory URLs join the sitemap ONLY where listings exist. Empty
    # ones render noindex, so submitting them would just spend crawl budget on
    # pages we have already told Google to ignore. Skipped entirely while the
    # directory is unseeded (the common case today).
    has_buyers = bool(buyers.live_places()) or bool(_kharidar_places())
    for cs, cn in sorted(idx.get("crops", {}).items()):
        if not _is_crop(cn):
            continue
        crop_last = ""
        crop_urls = []
        for ss in sorted(idx["states"].get(cs, {})):
            d_dates = dates.get(cs, {}).get(ss, {})
            state_name = idx["states"][cs][ss]
            state_last = ""
            state_urls = []
            for ds in sorted(idx["dists"].get(cs, {}).get(ss, {})):
                d_last = d_dates.get(ds, "")
                state_last = max(state_last, d_last)
                state_urls.append((f"{SITE}/bhav/{cs}/{ss}/{ds}", d_last))
                if has_buyers and _has_kharidar(
                        cs, state_name, idx["dists"][cs][ss][ds]):
                    state_urls.append(
                        (f"{SITE}/bhav/{cs}/{ss}/{ds}/kharidar", d_last))
            crop_last = max(crop_last, state_last)
            crop_urls.append((f"{SITE}/bhav/{cs}/{ss}", state_last))
            crop_urls.extend(state_urls)
        site_last = max(site_last, crop_last)
        urls.append((f"{SITE}/bhav/{cs}", crop_last))
        urls.extend(crop_urls)
    # Place hubs — /bhav/rajya/{state} (the hub's "राज्य के आधार पर" destination)
    # and /bhav/rajya/{state}/{district} under it. lastmod = newest arrival
    # across EVERY crop reported in that place; a place with only dateless rows
    # still ships (lastmod omitted) so its link is found.
    state_last, all_state_slugs = {}, set()
    dist_last, dists_by_state = {}, {}
    for cs, cn in idx.get("crops", {}).items():
        if not _is_crop(cn):
            continue
        all_state_slugs |= set(idx["states"].get(cs, {}))
        for ss, d_map in idx["dists"].get(cs, {}).items():
            dists_by_state.setdefault(ss, set()).update(d_map)
        for ss, d_map in dates.get(cs, {}).items():
            for ds, d_last in d_map.items():
                if not d_last:
                    continue
                if d_last > state_last.get(ss, ""):
                    state_last[ss] = d_last
                if d_last > dist_last.get((ss, ds), ""):
                    dist_last[(ss, ds)] = d_last
    for ss in sorted(all_state_slugs):
        urls.append((f"{SITE}/bhav/rajya/{ss}", state_last.get(ss, "")))
        for ds in sorted(dists_by_state.get(ss, ())):
            urls.append((f"{SITE}/bhav/rajya/{ss}/{ds}", dist_last.get((ss, ds), "")))
    urls.insert(0, (f"{SITE}/bhav/net-price", ""))   # net-price calculator hub
    urls.insert(0, (f"{SITE}/bhav", site_last))
    body = "\n".join(
        f"  <url><loc>{u}</loc>"
        + (f"<lastmod>{lm}</lastmod>" if lm else "")
        + "<changefreq>daily</changefreq></url>" for u, lm in urls)
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
           f'{body}\n</urlset>')
    return Response(content=xml, media_type="application/xml",
                    headers={"Cache-Control": "public, max-age=3600",
                             "CDN-Cache-Control":
                                 "public, durable, max-age=3600, "
                                 "stale-while-revalidate=86400"})


# Progressive-enhancement toggle for the फसल/राज्य tabs on the hub. Both panes
# are in the DOM (state pane ships [hidden]); this only flips visibility, so with
# JS off both grids stay visible and every link crawlable. No braces-in-f-string
# headaches — kept out of the body f-string as its own constant.
_HUB_TAB_JS = """<script>
(function(){
  var tabs=document.querySelectorAll('.bhav-tab-btn');
  // Keep the address bar in step with the active tab so the by-state view is
  // shareable/bookmarkable: by-crop → clean /bhav, by-state → /bhav?tab=state.
  // replaceState (like the app) = no back-button spam; canonical stays /bhav.
  function syncUrl(n){
    history.replaceState(null,'', window.location.pathname + (n==='state'?'?tab=state':''));
  }
  function sel(n,skipUrl){
    document.querySelectorAll('.bhav-pane').forEach(function(p){p.hidden=(p.dataset.pane!==n);});
    tabs.forEach(function(b){b.classList.toggle('active', b.dataset.pane===n);});
    if(!skipUrl){syncUrl(n);}
  }
  tabs.forEach(function(b){b.addEventListener('click',function(){sel(b.dataset.pane);});});
  // deep-link: /bhav?tab=state opens the by-state tab on load (URL untouched)
  try{
    if(new URLSearchParams(window.location.search).get('tab')==='state'){sel('state',true);}
  }catch(_){}
})();
function bhavFilterTiles(){
  var i=document.getElementById('bhav-tile-search');
  var q=(i&&i.value||'').trim().toLowerCase();
  document.querySelectorAll('#bhav-commodity-grid .ctile').forEach(function(t){
    t.style.display=(!q||(t.dataset.name||'').indexOf(q)>=0)?'':'none';
  });
  document.querySelectorAll('#bhav-crop-tail .chip').forEach(function(c){
    c.style.display=(!q||c.textContent.toLowerCase().indexOf(q)>=0)?'':'none';
  });
}
function bhavFilterStates(){
  var i=document.getElementById('bhav-state-search');
  var q=(i&&i.value||'').trim().toLowerCase();
  document.querySelectorAll('#bhav-state-grid .place').forEach(function(t){
    t.style.display=(!q||(t.dataset.name||'').indexOf(q)>=0)?'':'none';
  });
}
function _bhavVoice(inputId,micId,after){
  var SR=window.SpeechRecognition||window.webkitSpeechRecognition;
  if(!SR){return;}
  var mic=document.getElementById(micId);
  var r=new SR();r.lang='hi-IN';r.interimResults=false;r.maxAlternatives=1;
  if(mic){mic.classList.add('listening');}
  r.onresult=function(e){
    var i=document.getElementById(inputId);
    if(i){i.value=e.results[0][0].transcript;after();}
  };
  r.onend=function(){if(mic){mic.classList.remove('listening');}};
  r.onerror=function(){if(mic){mic.classList.remove('listening');}};
  try{r.start();}catch(_){}
}
function bhavTileVoice(){_bhavVoice('bhav-tile-search','bhav-tile-mic',bhavFilterTiles);}
function bhavStateVoice(){_bhavVoice('bhav-state-search','bhav-state-mic',bhavFilterStates);}
function bhavHubLocation(tab){
  var btn = document.getElementById(tab === 'state' ? 'bhav-state-loc' : 'bhav-tile-loc') || document.getElementById('bhav-state-loc');
  if(!navigator.geolocation){
    setPinMode(true, 'लोकेशन उपलब्ध नहीं — नक्शे पर अपनी जगह टैप करें');
    return;
  }
  if(btn){ btn.classList.remove('active'); btn.classList.add('loading'); }

  function _resolveHub(lat, lon){
    var url = 'https://api.bigdatacloud.net/data/reverse-geocode-client?latitude=' + lat + '&longitude=' + lon + '&localityLanguage=hi';
    fetch(url)
      .then(function(res){ return res.json(); })
      .then(function(d){
        if(btn){ btn.classList.remove('loading'); btn.classList.add('active'); }
        var state = (d.principalSubdivision || '').trim();
        var sBox = document.getElementById('bhav-state-search');
        if(sBox && state){
          sBox.value = state;
          bhavFilterStates();
          var sLow = state.toLowerCase();
          var card = document.querySelector('#bhav-state-grid .place[data-name*="' + sLow + '"]');
          if(card){
            try { card.scrollIntoView({behavior:'smooth', block:'center'}); } catch(_){}
            card.style.transition = 'box-shadow 0.3s ease, border-color 0.3s ease';
            card.style.boxShadow = '0 0 0 3px #2563eb';
            setTimeout(function(){ card.style.boxShadow = ''; }, 2500);
          }
        }
        var stateTabBtn = document.querySelector('.bhav-tab-btn[data-pane="state"]');
        if(stateTabBtn && !stateTabBtn.classList.contains('active')) stateTabBtn.click();
      })
      .catch(function(){
        if(btn){ btn.classList.remove('loading'); }
      });
  }

  try {
    var stored = JSON.parse(localStorage.getItem('km_geo') || 'null');
    if(stored && stored.lat && stored.lon && (Date.now() - (stored.ts || 0) < 7 * 86400000)){
      setTimeout(function(){ _resolveHub(stored.lat, stored.lon); }, 300);
      return;
    }
  } catch(_){}

  navigator.geolocation.getCurrentPosition(function(pos){
    try {
      localStorage.setItem('km_geo', JSON.stringify({
        status: 'granted',
        lat: +pos.coords.latitude.toFixed(5),
        lon: +pos.coords.longitude.toFixed(5),
        ts: Date.now()
      }));
    } catch(_){}
    _resolveHub(pos.coords.latitude, pos.coords.longitude);
  }, function(){
    if(btn){ btn.classList.remove('loading'); }
  }, {enableHighAccuracy: false, timeout: 10000, maximumAge: 600000});
}
</script>"""


# Reusable mic icon — same glyph the app's search boxes use.
_MIC_SVG_HTML = ('<svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" '
                 'fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" '
                 'stroke-linejoin="round"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/>'
                 '<path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/>'
                 '<line x1="8" y1="23" x2="16" y2="23"/></svg>')

# Reusable location icon — clean target/crosshairs pin glyph, strictly no emojis.
_LOC_SVG_HTML = ('<svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" '
                 'fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" '
                 'stroke-linejoin="round"><circle cx="12" cy="12" r="7"/>'
                 '<line x1="12" y1="2" x2="12" y2="5"/><line x1="12" y1="19" x2="12" y2="22"/>'
                 '<line x1="2" y1="12" x2="5" y2="12"/><line x1="19" y1="12" x2="22" y2="12"/>'
                 '<circle cx="12" cy="12" r="2.5" fill="currentColor"/></svg>')


# Reusable search glass icon — clean SVG, strictly no emojis.
_SEARCH_SVG_HTML = ('<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" '
                    'fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" '
                    'stroke-linejoin="round"><circle cx="11" cy="11" r="8"/>'
                    '<line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>')


def _tier_head(h1: str, sub: str) -> str:
    """Clean blue centered heading + a dated freshness line — the SAME top the
    /bhav hub uses, so the tier-2/3 picker pages continue that layout instead of
    the old green hero/answer box. `h1`/`sub` are already escaped by the caller."""
    return (f'<h1 class="mandi-page-heading">{h1}</h1>\n'
            f'<p class="mandi-page-sub">{sub}</p>')


def _tier_search(grid_id: str, placeholder: str, has_loc: bool | None = None) -> str:
    """The app's 🔍+loc+mic search box that live-filters the picker grid with id
    `grid_id`. Every item in that grid must carry data-name (Hindi + English).
    Location button is ONLY shown for place searches (State / District), never for Crops.
    """
    if has_loc is None:
        has_loc = ("जिला" in placeholder or "राज्य" in placeholder)
    loc_btn = (f'<button class="mn-loc-btn" id="{grid_id}-loc" type="button" '
               f'onmousedown="event.preventDefault()" onclick="bhavGridLocation(\'{grid_id}\')" '
               f'title="मेरी लोकेशन से खोजें" aria-label="मेरी लोकेशन">{_LOC_SVG_HTML}</button>\n'
               if has_loc else "")
    return f"""<div class="mandi-toolbar">
<div class="ctile-search-row">
<span class="cs-icon">{_SEARCH_SVG_HTML}</span>
<input id="{grid_id}-search" type="text" autocomplete="off" placeholder="{escape(placeholder)}" oninput="bhavGridFilter('{grid_id}')" />
{loc_btn}<button class="mn-mic-btn" id="{grid_id}-mic" type="button" onmousedown="event.preventDefault()" onclick="bhavGridVoice('{grid_id}')" title="बोलकर खोजें">{_MIC_SVG_HTML}</button>
</div>
</div>"""


# Generic grid filter + voice + location for the tier picker pages.
_TIER_SEARCH_JS = """<script>
function bhavGridFilter(gid){
  var box=document.getElementById(gid+'-search');
  var q=(box&&box.value||'').trim().toLowerCase();
  document.querySelectorAll('#'+gid+' [data-name]').forEach(function(el){
    el.style.display=(!q||(el.dataset.name||'').indexOf(q)>=0)?'':'none';
  });
}
function bhavGridVoice(gid){
  var SR=window.SpeechRecognition||window.webkitSpeechRecognition;
  if(!SR){return;}
  var mic=document.getElementById(gid+'-mic');
  var r=new SR();r.lang='hi-IN';r.interimResults=false;r.maxAlternatives=1;
  if(mic){mic.classList.add('listening');}
  r.onresult=function(e){
    var i=document.getElementById(gid+'-search');
    if(i){i.value=e.results[0][0].transcript;bhavGridFilter(gid);}
  };
  r.onend=function(){if(mic){mic.classList.remove('listening');}};
  r.onerror=function(){if(mic){mic.classList.remove('listening');}};
  try{r.start();}catch(_){}
}
function bhavGridLocation(gid){
  var btn = document.getElementById(gid + '-loc');
  if(!navigator.geolocation){
    setPinMode(true, 'लोकेशन उपलब्ध नहीं — नक्शे पर अपनी जगह टैप करें');
    return;
  }
  if(btn){ btn.classList.remove('active'); btn.classList.add('loading'); }

  function _resolveGrid(lat, lon){
    var url = 'https://api.bigdatacloud.net/data/reverse-geocode-client?latitude=' + lat + '&longitude=' + lon + '&localityLanguage=hi';
    fetch(url)
      .then(function(res){ return res.json(); })
      .then(function(d){
        if(btn){ btn.classList.remove('loading'); btn.classList.add('active'); }
        var state = (d.principalSubdivision || '').trim();
        var city = (d.city || d.locality || '').trim();
        var adminList = [];
        if(d.localityInfo && Array.isArray(d.localityInfo.administrative)){
          d.localityInfo.administrative.forEach(function(a){
            if(a && a.name){
              var clean = a.name.replace(/\\s*(District|Division|जिला|जिल्हा|मण्डल)\\s*/gi,'').trim();
              if(clean) adminList.push(clean);
            }
          });
        }
        var box = document.getElementById(gid + '-search');
        if(!box) return;

        var items = document.querySelectorAll('#' + gid + ' [data-name]');
        var matchedText = '';
        var matchedEl = null;

        var candidates = [city].concat(adminList).concat([state]).filter(Boolean);
        for(var c = 0; c < candidates.length; c++){
          var cLow = candidates[c].toLowerCase();
          for(var i = 0; i < items.length; i++){
            var dn = (items[i].dataset.name || '').toLowerCase();
            if(dn.indexOf(cLow) >= 0){
              matchedText = candidates[c];
              matchedEl = items[i];
              break;
            }
          }
          if(matchedEl) break;
        }

        if(matchedText){
          box.value = matchedText;
          bhavGridFilter(gid);
          if(matchedEl){
            try { matchedEl.scrollIntoView({behavior:'smooth', block:'center'}); } catch(_){}
            matchedEl.style.transition = 'box-shadow 0.3s ease, border-color 0.3s ease';
            matchedEl.style.boxShadow = '0 0 0 3px #2563eb';
            setTimeout(function(){ matchedEl.style.boxShadow = ''; }, 2500);
          }
        } else if(city || adminList[0] || state){
          box.value = city || adminList[0] || state;
          bhavGridFilter(gid);
        }
      })
      .catch(function(){
        if(btn){ btn.classList.remove('loading'); }
      });
  }

  try {
    var stored = JSON.parse(localStorage.getItem('km_geo') || 'null');
    if(stored && stored.lat && stored.lon && (Date.now() - (stored.ts || 0) < 7 * 86400000)){
      setTimeout(function(){ _resolveGrid(stored.lat, stored.lon); }, 300);
      return;
    }
  } catch(_){}

  navigator.geolocation.getCurrentPosition(function(pos){
    try {
      localStorage.setItem('km_geo', JSON.stringify({
        status: 'granted',
        lat: +pos.coords.latitude.toFixed(5),
        lon: +pos.coords.longitude.toFixed(5),
        ts: Date.now()
      }));
    } catch(_){}
    _resolveGrid(pos.coords.latitude, pos.coords.longitude);
  }, function(){
    if(btn){ btn.classList.remove('loading'); }
  }, {enableHighAccuracy: false, timeout: 10000, maximumAge: 600000});
}
</script>"""


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
        # The cold-index branch. It fires whenever the slug index is empty —
        # a cold cache, or the DB unreachable, which this site has had happen
        # (see the Neon read-only episodes) — and it used to answer with the
        # title "आज का मंडी भाव | कृषि मित्र" and the description "मंडी भाव लोड
        # हो रहे हैं।". If Googlebot took its snapshot during one of those
        # minutes, the site's second-biggest page sat in the SERP advertising
        # that it was still loading. The page genuinely has no data to show,
        # but the snippet describes what the page is *for*, which does not
        # depend on the index being warm.
        return _doc(_fit(f"आज का मंडी भाव {date.today().year} — सभी फसलों के ताजा रेट "
                         f"| Mandi Bhav Today",
                         f"आज का मंडी भाव {date.today().year} — सभी फसलों के ताजा रेट"),
                    "गेहूं, धान, गन्ना, प्याज, आलू समेत सैकड़ों फसलों का आज का मंडी भाव "
                    "(mandi bhav today) — फसल, राज्य और जिला चुनकर देखें। रोज़ अपडेट।",
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
    # Staples only. This gate is _STAPLE_TILES_N, not len(_TILES): the long-tail
    # photo rows exist so niche crops get a picture on their own page and in the
    # chip list below — promoting all ~230 of them into this grid would bury the
    # crops the farmer actually came for under four screens of cards.
    featured, seen_tiles = [], {}
    for cs, cn in crops.items():
        rank = _tile_rank(cn)
        if rank >= _STAPLE_TILES_N:
            continue
        n = len(idx["states"].get(cs, {}))
        if rank not in seen_tiles or n > seen_tiles[rank][2]:
            seen_tiles[rank] = (cs, cn, n)
    featured = [seen_tiles[r] for r in sorted(seen_tiles)]

    # Photo-left "फ़सल की कीमत" tiles — the exact commodity-grid look of the app's
    # mandi.html landing, but each tile is a real crawlable <a href="/bhav/{crop}">
    # (the app uses a JS-only <button>), so this keeps the server-rendered link
    # that the whole /bhav tree exists to give Google. data-name feeds the client
    # search filter (matches the Hindi label OR the English commodity name).
    tiles = []
    for cs, cn, _n_states in featured:
        hi = _hindi_name(cn)
        img = (f'<img class="ctile-img" src="{escape(_crop_image(cn, 200))}" '
               f'alt="{escape(hi)}" loading="lazy" width="70" height="54">'
               if _has_photo(cn) else '<span class="ctile-emoji">🌾</span>')
        dname = escape(f"{hi} {cn}".lower())
        tiles.append(f"""<a class="ctile" href="/bhav/{cs}" data-name="{dname}" title="{escape(hi)} की कीमत">
<div class="ctile-imgwrap">{img}</div>
<div class="ctile-body"><div class="ctile-name"><b>{escape(hi)}</b> की कीमत</div></div>
</a>""")

    faqs = [
        ("मंडी भाव रोज़ कब अपडेट होता है?",
         "भाव हर सुबह भारत सरकार के data.gov.in (Agmarknet) फीड से अपने आप अपडेट होते हैं। "
         "जिन मंडियों की रिपोर्ट उस दिन नहीं आती, उनका पिछला उपलब्ध भाव दिखता है।"),
        ("अपनी मंडी का भाव कैसे देखें?",
         "पहले अपनी फसल चुनें, फिर राज्य, फिर जिला — उस जिले की सभी मंडियों का न्यूनतम, "
         "अधिकतम और मॉडल भाव प्रति क्विंटल दिख जाएगा।"),
        ("राज्य के हिसाब से सभी फसलों का भाव कैसे देखें?",
         "ऊपर 'राज्य के आधार पर' टैब चुनें, फिर अपना राज्य चुनें — उस राज्य की मंडियों में "
         "मिलने वाली सभी फसलों के आज के भाव एक जगह दिख जाएंगे।"),
    ]
    faq_html, faq_ld = _faq(faqs)
    ld = _ld(faq_ld, _crumb_ld([("कृषि मित्र", f"{SITE}/"), ("मंडी भाव", f"{SITE}/bhav")]))

    # The tier-3 and tier-4 templates were taught to carry both spellings on
    # 2026-09-06; this hub was missed and still had no Latin character in it at
    # all. It is the site's second-biggest page — 16,957 impressions at
    # position 7.4 in the 28 days to 9 Sep 2026 — and the single query "bhav"
    # is 1,900 of them at position 9.6 for FOUR clicks (0.21%), against 2-6%
    # from the same phrase typed in Devanagari. Nothing the romanised searcher
    # typed appeared anywhere in the result.
    title = _fit(
        f"आज का मंडी भाव {date.today().year} — सभी फसलों के ताजा रेट | Mandi Bhav Today",
        f"आज का मंडी भाव {date.today().year} — सभी फसलों के रेट | Mandi Bhav Today",
        f"आज का मंडी भाव {date.today().year} | Mandi Bhav Today — सभी फसलों के रेट",
        f"आज का मंडी भाव {date.today().year} — सभी फसलों के ताजा रेट")
    desc = _fit(
        f"{today_hi}: गेहूं, धान, गन्ना, प्याज, आलू समेत {len(crops)} फसलों का आज का "
        f"मंडी भाव (mandi bhav today)। फसल, राज्य और जिला चुनें — रोज़ अपडेट।",
        f"{today_hi}: गेहूं, धान, प्याज, आलू समेत {len(crops)} फसलों का आज का मंडी भाव "
        f"(mandi bhav today)। फसल, राज्य व जिला चुनें — रोज़ अपडेट।",
        f"{today_hi}: गेहूं, धान, गन्ना, प्याज, आलू समेत {len(crops)} फसलों का ताजा मंडी भाव। "
        f"फसल चुनें, फिर राज्य और जिला — आज का रेट देखें। रोज़ अपडेट (data.gov.in)।",
        limit=162)

    body = f"""<h1 class="mandi-page-heading">कृषि मंडी भाव</h1>
<div class="bhav-tabs" role="tablist">
<button class="bhav-tab-btn active" type="button" data-pane="crop" role="tab">फसल के आधार पर</button>
<button class="bhav-tab-btn" type="button" data-pane="state" role="tab">राज्य के आधार पर</button>
</div>
<div class="bhav-pane" data-pane="crop">
<div class="mandi-toolbar">
<div class="ctile-search-row">
<span class="cs-icon">{_SEARCH_SVG_HTML}</span>
<input id="bhav-tile-search" type="text" autocomplete="off" placeholder="फसल खोजें... (गेहूं, प्याज, आलू)" oninput="bhavFilterTiles()" />
<button class="mn-mic-btn" id="bhav-tile-mic" type="button" onmousedown="event.preventDefault()" onclick="bhavTileVoice()" title="बोलकर खोजें">{_MIC_SVG_HTML}</button>
</div>
</div>
<div class="shop-section-title"><span>आज के भाव — अपनी फसल चुनें</span></div>
<div class="commodity-grid" id="bhav-commodity-grid">{"".join(tiles)}</div>
{_lazy_div('bhav-crop-tail', 'tiles')}
</div>
<div class="bhav-pane" data-pane="state" hidden>
<div class="mandi-toolbar">
<div class="ctile-search-row">
<span class="cs-icon">{_SEARCH_SVG_HTML}</span>
<input id="bhav-state-search" type="text" autocomplete="off" placeholder="राज्य खोजें... (उत्तर प्रदेश, बिहार)" oninput="bhavFilterStates()" />
<button class="mn-loc-btn" id="bhav-state-loc" type="button" onmousedown="event.preventDefault()" onclick="bhavHubLocation('state')" title="मेरी लोकेशन से खोजें" aria-label="मेरी लोकेशन">{_LOC_SVG_HTML}</button>
<button class="mn-mic-btn" id="bhav-state-mic" type="button" onmousedown="event.preventDefault()" onclick="bhavStateVoice()" title="बोलकर खोजें">{_MIC_SVG_HTML}</button>
</div>
</div>
<div class="shop-section-title"><span>राज्य चुनें — सभी फसलों के भाव देखें</span></div>
<div class="place-grid" id="bhav-state-grid">{_lazy_skel("tiles")}</div>
</div>
{_dukan_pitch()}
<h2>अक्सर पूछे जाने वाले सवाल</h2>
{faq_html}
{_HUB_TAB_JS}
{_lazy_script([('/bhav/api/hub-rest', 'bhav-crop-tail'), ('/bhav/api/hub-states', 'bhav-state-grid')])}"""
    return _doc(title, desc, f"{SITE}/bhav", "", body, ld,
                extra_css=_LAZY_CSS + _DKP_CSS)


# ════════════════════════════════════════════════════════════
# STATE HUB — /bhav/rajya/{state} : all crops reported in ONE state
#
# The destination for the hub's "राज्य के आधार पर" tab. The crop-scoped tree
# (/bhav/{crop}/{state}) never had an "all crops in this state" page, so this
# fills that gap with real server-rendered, crawlable crop cards that link into
# the existing crop×state pages. Registered ABOVE /bhav/{c_slug}/{x_slug} (TIER 3)
# so "rajya" isn't swallowed as a crop slug.
#
# Picking a district here goes DOWN this same crop-less path (/bhav/rajya/{state}
# /{district}), never sideways into some crop's tree — see _hub_selector.
# ════════════════════════════════════════════════════════════
@router.get("/bhav/rajya/{state}", response_class=HTMLResponse)
def bhav_state_hub(state: str):
    idx = _get_index()
    ss = state.lower()

    crops_here = _crops_in(idx, ss)
    if not crops_here:
        return _not_found(idx, "", ss)

    # Canonical display spelling of the state (from any crop that reports it).
    sn = _state_name(idx, ss)
    hi_state = _hindi_state(sn)
    canon = f"{SITE}/bhav/rajya/{ss}"

    # Dated by the DATA, not the clock — see _as_of_hi. This page had nothing
    # to date while it carried no price; now that every card shows one, it
    # falls under the same rule as tiers 2-4, and `today_hi` is deliberately
    # not defined here so the old mismatch cannot be typed back in.
    fresh = _fresh_iso_place(idx, ss)
    as_of_hi = _as_of_hi(fresh)

    # Every district reporting anything in this state — an honest size cue AND
    # the जिला grid below (no per-crop DB round-trips, so cheap enough for a
    # shared cached page).
    dists_here = _dists_in_state(idx, ss)
    n_dist = len(dists_here)

    # Staples first (same ranking as the hub grid), long tail after — one
    # crawlable crop card each, linking into the existing crop×state page.
    # Today's state average per crop, so the page the channel post links to
    # opens on the same numbers the post just printed — see _rates_in.
    rates = _rates_in(idx, ss)

    ordered = sorted(crops_here.items(),
                     key=lambda kv: (_tile_rank(kv[1]), _hindi_name(kv[1])))
    cards = []
    for c, cn in ordered:
        hi = _hindi_name(cn)
        c_dist = len(idx["dists"].get(c, {}).get(ss, {}))
        has_photo = _has_photo(cn)
        photo = (f'<img src="{escape(_crop_image(cn, 500))}" alt="{escape(hi)}" '
                 f'loading="lazy" width="240" height="120">' if has_photo else "")
        en = f'<span class="crop-card-en">{escape(cn)}</span>' if hi != cn else ""
        r = rates.get(c)
        rate = _rupee(r["avg"]) if r else "भाव देखें →"
        cards.append(f"""<a class="crop-card" href="/bhav/{c}/{ss}" data-name="{escape(f'{hi} {cn}'.lower())}">
<div class="crop-card-photo{'' if has_photo else ' noimg'}">{photo}
<h2 class="crop-card-name">{escape(hi)}{en}</h2></div>
<div class="crop-card-body">
<span class="lbl">{c_dist} जिले</span><span class="rate">{rate}</span>
</div></a>""")

    # One crawlable link per district → the district hub, which asks for the
    # crop. The selector's जिला field goes to the same place; this grid is the
    # no-JS path and the only way Google reaches those pages by link.
    dcards = "".join(
        f'<a class="dcard" href="/bhav/rajya/{ss}/{ds}" data-name="{escape(f"{_hindi_district(ss, dn)} {dn} {ds}".lower())}">'
        f'<span class="dcard-n">{escape(_hindi_district(ss, dn))}</span>'
        f'<span class="dcard-r">भाव देखें →</span></a>'
        for ds, dn in sorted(dists_here.items(), key=lambda kv: _hindi_district(ss, kv[1])))

    faqs = [
        (f"{hi_state} में आज कौन-कौन सी फसलों का भाव मिलता है?",
         f"{as_of_hi} को {hi_state} की मंडियों में {len(crops_here)} फसलों के ताजा भाव सरकारी "
         f"रिपोर्ट (data.gov.in / Agmarknet) में दर्ज हैं। नीचे अपनी फसल चुनकर जिलेवार भाव देखें।"),
        (f"{hi_state} में अपनी फसल का भाव कैसे देखें?",
         f"नीचे अपनी फसल चुनें — फिर {hi_state} के सभी जिलों की मंडियों का न्यूनतम, अधिकतम और "
         f"मॉडल भाव प्रति क्विंटल दिख जाएगा।"),
        (f"अपने जिले की मंडी में आज किन-किन फसलों का भाव है, यह कैसे देखें?",
         f"नीचे 'जिला चुनें' में अपना जिला चुनें — उस जिले की मंडियों में आज जिन फसलों का भाव "
         f"दर्ज हुआ है, उन सबकी सूची एक जगह खुल जाएगी। वहां से अपनी फसल चुनकर पूरा रेट देखें।"),
    ]
    faq_html, faq_ld = _faq(faqs)
    ld = _ld(faq_ld, _crumb_ld([
        ("कृषि मित्र", f"{SITE}/"), ("मंडी भाव", f"{SITE}/bhav"), (hi_state, canon)]))

    title = f"{hi_state} मंडी भाव आज — सभी फसलों के ताजा रेट {date.today().year}"
    desc = (f"{as_of_hi}: {hi_state} की मंडियों में {len(crops_here)} फसलों का ताजा मंडी भाव — "
            f"गेहूं, धान, प्याज समेत। फसल चुनकर अपने जिले का रेट देखें। रोज़ अपडेट (data.gov.in)।")

    answer_lead = (f'<p class="lead-out">{as_of_hi} को {escape(hi_state)} के {n_dist} जिलों की मंडियों में '
                   f'{len(crops_here)} फसलों का भाव भारत सरकार के Agmarknet (data.gov.in) पोर्टल पर '
                   f'दर्ज हुआ। नीचे अपनी फसल चुनकर जिलेवार पूरा भाव देखें।</p>')


    # State-language pass — services/state_lang.py. `sn` is the feed's spelling,
    # which is what lang_for keys on.
    lang = state_lang.lang_for(sn)
    as_of_loc = as_of_hi
    try:
        _d = date.fromisoformat(fresh)
        as_of_loc = state_lang.date_str(_d.day, _d.month, _d.year, lang, as_of_hi)
    except (TypeError, ValueError):
        pass
    _lv = {"state": hi_state, "state_en": sn, "n": len(crops_here),
           "n_dist": n_dist, "year": date.today().year, "date": as_of_loc}
    _lt = state_lang.variants("titles", "state_all", lang, _lv)
    if _lt:
        title = _fit(*_lt)
    _ldc = state_lang.variants("descs", "state_all", lang, _lv)
    if _ldc:
        desc = _fit(*_ldc, limit=162)
    head_h1 = escape(state_lang.h1("state_all", lang, _lv,
                                   f"{hi_state} में आज के मंडी भाव — फसल चुनें"))
    _lf = state_lang.faqs("state_all", lang, _lv)
    if _lf:
        faq_html, faq_ld = _faq(_lf)
        ld = _ld(faq_ld, _crumb_ld([
            ("कृषि मित्र", f"{SITE}/"),
            (state_lang.word("bhav", lang, "मंडी भाव"), f"{SITE}/bhav"),
            (hi_state, canon)]))

    head_sub = (f"📅 {as_of_hi} · {len(crops_here)} फसलें · {n_dist} जिले · "
                f"औसत भाव ₹/क्विंटल · स्रोत: data.gov.in (Agmarknet)"
                f"{_age_badge(fresh)}")
    body = f"""{_tier_head(head_h1, head_sub)}
<div class="cta-row">
<a class="btn btn-app" href="{SITE}/bhav">← सभी राज्य</a>
</div>
{_hub_selector("", ss, "", idx, known_state=True, show_crop=False)}
<h2>{escape(hi_state)} में फसल चुनें</h2>
{_tier_search('tier-grid', 'फसल खोजें... (गेहूं, प्याज, आलू)')}
<div class="crop-grid" id="tier-grid">{"".join(cards)}</div>
{answer_lead}
<h2>{escape(hi_state)} में जिला चुनें</h2>
<p class="lead-out">अपना जिला चुनें — उस जिले की मंडियों में आज जिन फसलों का भाव दर्ज हुआ है, सब एक जगह दिखेंगी।</p>
{_tier_search('dist-grid', 'जिला खोजें...')}
<div class="dcard-grid" id="dist-grid">{dcards}</div>
<h2>अक्सर पूछे जाने वाले सवाल</h2>
{faq_html}
{_TIER_SEARCH_JS}"""
    crumbs = (f'<a href="{SITE}/">कृषि मित्र</a> › <a href="{SITE}/bhav">मंडी भाव</a> › {escape(hi_state)}')
    return _doc(title, desc, canon, crumbs, body, ld, lang=lang, updated=fresh)


# ════════════════════════════════════════════════════════════
# DISTRICT HUB — /bhav/rajya/{state}/{district} : all crops in ONE district
#
# The other half of the crop-less path. A farmer who picks his state and then
# his mandi has said WHERE, not WHAT — so this asks for the crop instead of
# assuming one (picking a district used to drop him on the state's widest crop,
# usually wheat). It is also the page "<जिला> मंडी भाव" is actually searched
# for, which no crop-scoped URL could ever answer.
# ════════════════════════════════════════════════════════════
@router.get("/bhav/rajya/{state}/{district}", response_class=HTMLResponse)
def bhav_district_hub(state: str, district: str):
    idx = _get_index()
    ss, ds = state.lower(), district.lower()

    crops_here = _crops_in(idx, ss, ds)
    if not crops_here:
        return _not_found(idx, "", ss)

    dn = _dist_name(idx, ss, ds)
    sn = _state_name(idx, ss)
    # Same split as the crop district pages: Hindi everywhere the page speaks
    # Hindi, and the Latin spelling kept in the <title> beside it, because the
    # two spellings are two different searches — see _hindi_district.
    dn_hi = _hindi_district(sn, dn)
    hi_state = _hindi_state(sn)
    canon = f"{SITE}/bhav/rajya/{ss}/{ds}"

    # Dated by the DATA, not the clock — same rule and same reason as the
    # state hub above. `today_hi` is deliberately not defined here.
    fresh = _fresh_iso_place(idx, ss, ds)
    as_of_hi = _as_of_hi(fresh)

    # Today's district average per crop — same reason as the state hub above.
    rates = _rates_in(idx, ss, ds)

    ordered = sorted(crops_here.items(),
                     key=lambda kv: (_tile_rank(kv[1]), _hindi_name(kv[1])))
    cards = []
    for c, cn in ordered:
        hi = _hindi_name(cn)
        has_photo = _has_photo(cn)
        photo = (f'<img src="{escape(_crop_image(cn, 500))}" alt="{escape(hi)}" '
                 f'loading="lazy" width="240" height="120">' if has_photo else "")
        en = f'<span class="crop-card-en">{escape(cn)}</span>' if hi != cn else ""
        r = rates.get(c)
        rate = _rupee(r["avg"]) if r else "भाव देखें →"
        cards.append(f"""<a class="crop-card" href="/bhav/{c}/{ss}/{ds}" data-name="{escape(f'{hi} {cn}'.lower())}">
<div class="crop-card-photo{'' if has_photo else ' noimg'}">{photo}
<h2 class="crop-card-name">{escape(hi)}{en}</h2></div>
<div class="crop-card-body">
<span class="lbl">{escape(dn_hi)}</span><span class="rate">{rate}</span>
</div></a>""")

    faqs = [
        (f"{dn_hi} मंडी में आज किन फसलों का भाव है?",
         f"{as_of_hi} को {dn_hi} ({hi_state}) की मंडियों में {len(crops_here)} फसलों के भाव सरकारी "
         f"रिपोर्ट (data.gov.in / Agmarknet) में दर्ज हैं। नीचे अपनी फसल चुनकर आज का पूरा भाव देखें।"),
        (f"{dn_hi} मंडी का आज का भाव कैसे देखें?",
         f"नीचे अपनी फसल चुनें — {dn_hi} की मंडियों का आज का न्यूनतम, अधिकतम और मॉडल भाव "
         f"प्रति क्विंटल दिख जाएगा, साथ में पिछले दिनों का रुझान भी।"),
    ]
    faq_html, faq_ld = _faq(faqs)
    ld = _ld(faq_ld, _crumb_ld([
        ("कृषि मित्र", f"{SITE}/"), ("मंडी भाव", f"{SITE}/bhav"),
        (hi_state, f"{SITE}/bhav/rajya/{ss}"), (dn_hi, canon)]))

    # ── CTR-optimised title (§2.2): district name + top crops ──
    # The farmer searching "मेरठ मंडी भाव" sees his actual crops in the result.
    _top_crops = ", ".join(_hindi_name(cn) for _, cn in ordered[:4])
    title = _fit(*(([f"{dn_hi} मंडी भाव आज — {dn} Mandi Bhav {date.today().year}",
                     f"{dn_hi} मंडी भाव आज — {dn} Mandi Bhav"] if dn_hi != dn else []) + [
                 f"{dn_hi} मंडी भाव आज — {_top_crops} का नेट रेट",
                 f"{dn_hi} मंडी भाव आज — सभी फसलों के ताजा रेट {date.today().year}",
                 f"{dn_hi} मंडी भाव आज — सभी फसलों के ताजा रेट",
                 f"{dn_hi} मंडी भाव आज — {hi_state}",
                 f"{dn_hi} मंडी भाव आज"]))
    # ── CTR-optimised meta (§2.2): trend + net-bhav CTA ──
    desc = _fit(
        f"{as_of_hi} अपडेट: {dn_hi} ({hi_state}) की मंडियों में {len(crops_here)} फसलों "
        f"का ताजा भाव + पिछले दिनों का रुझान। भाड़ा घटाकर नेट भाव देखें और सबसे ज़्यादा कमाई वाली मंडी चुनें।",
        f"{as_of_hi}: {dn_hi} ({hi_state}) की मंडियों में {len(crops_here)} फसलों का ताजा भाव — "
        f"अपनी फसल चुनकर आज का न्यूनतम, अधिकतम और मॉडल रेट देखें। रोज़ अपडेट (data.gov.in)।",
        f"{as_of_hi}: {dn_hi} की मंडियों में {len(crops_here)} फसलों का ताजा मंडी भाव — "
        f"फसल चुनकर आज का रेट देखें। रोज़ अपडेट (data.gov.in)।",
        limit=162)

    answer_lead = (f'<p class="lead-out">{as_of_hi} को {escape(dn_hi)} ({escape(hi_state)}) की मंडियों में '
                   f'{len(crops_here)} फसलों का भाव भारत सरकार के Agmarknet (data.gov.in) पोर्टल पर '
                   f'दर्ज हुआ। नीचे अपनी फसल चुनकर उस फसल का पूरा भाव देखें।</p>')

    # State-language pass — services/state_lang.py. This page carries no crop
    # name, so it is the cheapest of the five: place, count and date only.
    # `sn`, not `state` — the path segment here is the URL slug ("maharashtra"),
    # and lang_for keys on the feed's own spelling the way _HI_STATES does.
    lang = state_lang.lang_for(sn)
    as_of_loc = as_of_hi
    try:
        _d = date.fromisoformat(fresh)
        as_of_loc = state_lang.date_str(_d.day, _d.month, _d.year, lang, as_of_hi)
    except (TypeError, ValueError):
        pass
    _lv = {"district": state_lang.district(dn_hi, lang), "district_en": dn,
           "en_d": dn if dn_hi != dn else "",
           "state": hi_state, "state_en": sn, "n": len(crops_here),
           "year": date.today().year, "date": as_of_loc}
    _lt = state_lang.variants("titles", "district_all", lang, _lv)
    if _lt:
        title = _fit(*_lt)
    _ldc = state_lang.variants("descs", "district_all", lang, _lv)
    if _ldc:
        desc = _fit(*_ldc, limit=162)
    head_h1 = escape(state_lang.h1("district_all", lang, _lv,
                                   f"{dn_hi} मंडी भाव आज — फसल चुनें"))
    _lf = state_lang.faqs("district_all", lang, _lv)
    if _lf:
        faq_html, faq_ld = _faq(_lf)
        ld = _ld(faq_ld, _crumb_ld([
            ("कृषि मित्र", f"{SITE}/"),
            (state_lang.word("bhav", lang, "मंडी भाव"), f"{SITE}/bhav"),
            (hi_state, f"{SITE}/bhav/rajya/{ss}"), (dn_hi, canon)]))
    head_sub = (f"📅 {as_of_hi} · {escape(hi_state)} · {len(crops_here)} फसलें · "
                f"औसत भाव ₹/क्विंटल · स्रोत: data.gov.in (Agmarknet)"
                f"{_age_badge(fresh)}")
    hub_map_html = _district_hub_satellite_map_html(state=sn, district=dn,
                                                    s_slug=ss, d_slug=ds, d_hi=dn_hi)
    body = f"""{_tier_head(head_h1, head_sub)}
<div class="cta-row">
<a class="btn btn-app" href="{SITE}/bhav/rajya/{ss}">← {escape(hi_state)} के सभी जिले</a>
</div>
{_hub_selector("", ss, ds, idx, known_state=True, known_dist=True, show_crop=False)}
{hub_map_html}
<h2>{escape(dn_hi)} में फसल चुनें</h2>
{_tier_search('tier-grid', 'फसल खोजें... (गेहूं, प्याज, आलू)')}
<div class="crop-grid" id="tier-grid">{"".join(cards)}</div>
{answer_lead}
{_dukan_pitch(dn_hi)}
<h2>अक्सर पूछे जाने वाले सवाल</h2>
{faq_html}
{_TIER_SEARCH_JS}"""
    crumbs = (f'<a href="{SITE}/">कृषि मित्र</a> › <a href="{SITE}/bhav">मंडी भाव</a> › '
              f'<a href="{SITE}/bhav/rajya/{ss}">{escape(hi_state)}</a> › {escape(dn_hi)}')
    hub_head = (
        '<link rel="dns-prefetch" href="https://server.arcgisonline.com">'
        '<link rel="dns-prefetch" href="https://unpkg.com">'
        '<link rel="preconnect" href="https://server.arcgisonline.com">'
        '<link rel="preconnect" href="https://unpkg.com">'
        '<link rel="preload" as="script" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js">'
        f'{_LEAFLET_CSS}'
        if hub_map_html else ""
    )
    return _doc(title, desc, canon, crumbs, body, ld, extra_css=_DKP_CSS + _BHAV_MAP_CSS,
                head_extra=hub_head, lang=lang, updated=fresh)


# ════════════════════════════════════════════════════════════
# NEAREST-MANDI personalisation (client-side swap on tier 2 & 3)
#
# The /bhav pages are one cached HTML shared by every visitor, so the server
# can't know a farmer's location at render time — it always ships the
# highest-price "best rate" panel as the no-JS fallback. bhav-nearest.js reads
# the device location (localStorage km_geo) and calls this to replace that
# panel with the NEAREST mandi instead. state="" → nationwide (tier 2);
# state=<slug> → within that state (tier 3). Registered ABOVE /bhav/{c_slug}
# so "nearest" isn't swallowed as a crop slug.
# ════════════════════════════════════════════════════════════
def _fmt_km(km: float) -> str:
    return "1 किमी से कम" if km < 1 else f"{round(km):,} किमी"


def _lead_gen_html() -> str:
    """A tasteful 'किसान सेवाएं' card of relevant service links (loan / insurance /
    solar). Renders nothing until an offer is switched on with a real URL, so it
    can ship dormant and light up the moment an affiliate partner exists. Each
    link routes through /go/<id> for one-place URL swaps + click measurement.
    Placed low on the page (below the answer) so it never competes with the
    price or hurts LCP — a service lead is worth far more than the ad it sits by."""
    offers = leads.active_offers()
    if not offers:
        return ""
    cards = []
    for o in offers:
        # 'gov' = informational (nofollow); a paid partner link is 'sponsored'.
        rel = "nofollow" if o.get("partner") == "gov" else "nofollow sponsored"
        cards.append(
            f'<a class="lead-card" href="/go/{escape(o.get("id",""))}" '
            f'data-lead="{escape(o.get("id",""))}" rel="{rel}" target="_blank">'
            f'<span class="lead-ic">{escape(o.get("icon","•"))}</span>'
            f'<span class="lead-tx"><b>{escape(o.get("title",""))}</b>'
            f'<small>{escape(o.get("desc",""))}</small></span>'
            f'<span class="lead-cta">{escape(o.get("cta","देखें"))} →</span></a>')
    # Fire a GA4 event on click (GA is loaded site-wide); guarded so a page
    # without gtag never errors. Bound once — this block renders once per page.
    script = ("<script>document.querySelectorAll('.lead-card').forEach(function(a){"
              "a.addEventListener('click',function(){try{gtag('event','lead_click',"
              "{offer_id:a.getAttribute('data-lead')});}catch(e){}});});</script>")
    sub = escape(leads.sub())
    return (f'<section class="lead-gen"><h2>🧑‍🌾 {escape(leads.heading())}</h2>'
            + (f'<p class="lead-sub">{sub}</p>' if sub else "")
            + f'<div class="lead-list">{"".join(cards)}</div>'
            '<p class="lead-fine">यह जानकारी सुविधा के लिए दी गई है। योजना की पात्रता और '
            'शर्तें संबंधित पोर्टल पर देखें।</p>'
            + script + '</section>')


def _kheti_saman_html(cs: str, hi: str = "") -> str:
    """The affiliate shelf: four products that match what this farmer is about
    to do, each linked through the tracked /go/p/ hop.

    WHY THIS SITS ON A PRICE PAGE. The Amazon program lived on /product for
    months — 94 catalogue pages nobody searches for by name — while the pages
    that carry the traffic offered a farmer nothing he could act on but a
    government scheme link that pays us nothing. This moves the one program
    that can actually earn onto the one surface that has readers.

    WHY IT IS NOT A SHOP. Nothing here claims we sell, stock, ship or price
    anything: no rupee figure, no MRP, no discount, no availability. The
    catalogue's price is an editorial estimate, and printing it beside an
    outbound link would be a number the farmer checks against Amazon's real
    one three seconds later — a claim we would have to defend, for no gain,
    since the destination shows the true price anyway. The card says what the
    thing is and where the link goes, and stops.

    WHY EMOJI AND NOT THE PRODUCT PHOTO. A photo shelf converts better — when
    the photo is of the product. PRODUCTS reuses a handful of real pack shots
    as placeholders across the catalogue, so 19 of the 24 items this shelf can
    surface carry a picture of something else: the tarpaulin shows a drip kit,
    the storage bags show a branded cattle-feed sack that belongs to another
    company. On /product that has been wrong on 94 quiet pages; putting it on
    every district page would be wrong at traffic, and a farmer who taps a
    photo and lands on a different object stops trusting the block above it
    too. Every row in PRODUCTS carries a hand-picked `emoji` that IS accurate,
    so the shelf uses that and reads as a list rather than a storefront. Swap
    this for .dp-card photos the day the catalogue has its own photography.

    Placed low on the page for the same reason _lead_gen_html is: it must never
    compete with the price or cost the page its LCP. Selection is
    services/affiliate.py and is deterministic, so this renders identically
    into cached HTML for every farmer on the page.
    """
    picks = affiliate.for_crop(cs)
    if not picks:
        return ""
    cards = []
    for p in picks:
        net = affiliate.network_for(p)
        if not net:
            continue
        cards.append(
            f'<a class="lead-card" href="{affiliate.go_url(p["slug"], net)}" '
            f'data-affil="{escape(p["slug"])}" target="_blank" rel="nofollow sponsored">'
            f'<span class="lead-ic">{escape(p.get("emoji", "•"))}</span>'
            f'<span class="lead-tx"><b>{escape(p.get("name_hi", ""))}</b>'
            f'<small>{escape(p.get("unit_hi", ""))}</small></span>'
            f'<span class="lead-cta">{escape(net.capitalize())} पर देखें →</span></a>')
    if not cards:
        return ""
    # Same GA4 pattern as the किसान-सेवा card, and the same guard: a page that
    # somehow loads without gtag must not throw on every tap. Scoped to
    # [data-affil] so it binds these rows and not the service-offer rows, which
    # fire their own event with a different name.
    script = ("<script>document.querySelectorAll('.lead-card[data-affil]').forEach(function(a){"
              "a.addEventListener('click',function(){try{gtag('event','affiliate_click',"
              "{product_id:a.getAttribute('data-affil')});}catch(e){}});});</script>")
    sub = (f'{escape(hi)} बेचने और रखने में काम आने वाला सामान।' if hi
           else 'खेती में रोज़ काम आने वाला सामान।')
    return (f'<section class="lead-gen"><h2>🛒 ज़रूरी खेती का सामान</h2>'
            f'<p class="lead-sub">{sub}</p>'
            f'<div class="lead-list">{"".join(cards)}</div>'
            f'<p class="lead-fine">{escape(affiliate.AFFILIATE_NOTE)}</p>'
            f'<p class="lead-fine">{escape(legal.SHELF_CAUTION)}</p>'
            + script + '</section>')


def _district_from_referer(ref: str) -> str | None:
    """Pull the district slug out of the /bhav page a click came from.

    Offers render on /bhav/<crop>/<state>/<district>[/...], so the page URL is
    the only thing that knows where the farmer was — the offer config is
    national. Best-effort by design: a missing or odd Referer just means the
    row carries no district, never that the click is lost.
    """
    if not ref:
        return None
    try:
        parts = [p for p in urlparse(ref).path.strip("/").split("/") if p]
    except Exception:
        return None
    return parts[3] if len(parts) >= 4 and parts[0] == "bhav" else None


@router.get("/go/{offer_id}")
def lead_redirect(offer_id: str, request: Request, background: BackgroundTasks):
    """Tracked outbound hop for a किसान-सेवा offer → the partner/scheme URL.

    The click is persisted (services/lead_clicks.py) on top of the client GA
    event, but *after* the 302 — a background task, so a sleeping Neon compute
    can never sit between a farmer and the scheme page. Unknown/inactive id
    falls back to /bhav rather than erroring."""
    o = leads.offer_by_id(offer_id)
    if o:
        ref = request.headers.get("referer", "")
        logger.info("lead_click offer=%s cat=%s", offer_id, o.get("category", "-"))
        background.add_task(
            lead_clicks.record, "offer", offer_id,
            label      = o.get("title"),
            category   = o.get("category"),
            district   = _district_from_referer(ref),
            referer    = ref,
            user_agent = request.headers.get("user-agent"),
        )
        return RedirectResponse(o["url"], status_code=302)
    return RedirectResponse("/bhav", status_code=302)


@router.get("/go/s/{sponsor_id}")
def sponsor_redirect(sponsor_id: str, request: Request, background: BackgroundTasks):
    """Tracked outbound hop for a site sponsor → the brand's landing page.

    Its own path segment rather than a row in lead_offers, because the two are
    different products with different money behind them: an offer is ours to
    swap at will, a sponsor's destination is contractual. Same shape otherwise
    — record after the 302, so a sleeping Neon compute never sits between a
    farmer and the page he tapped.

    THIS COUNT IS WHAT WE INVOICE AGAINST, so it only ever counts real taps: an
    unknown or expired id redirects home and records nothing rather than
    inventing a click on a sponsorship that has ended.
    """
    row = next((s for s in sponsors.active() if s.get("id") == sponsor_id), None)         if sponsors else None
    if not row:
        return RedirectResponse("/", status_code=302)
    ref = request.headers.get("referer", "")
    logger.info("sponsor_click id=%s cat=%s", sponsor_id, row.get("category", "-"))
    background.add_task(
        lead_clicks.record, "sponsor", sponsor_id,
        label      = row.get("name"),
        category   = row.get("category"),
        district   = _district_from_referer(ref),
        referer    = ref,
        user_agent = request.headers.get("user-agent"),
    )
    return RedirectResponse(row["url"], status_code=302)


def _net_price_cta(hi: str, cs: str = "", state: str = "", district: str = "") -> str:
    """Compact button linking into the net-price calculator — sits beside the
    WhatsApp share button (answer panel) or in a cta-row. No rupee figures, so
    it's safe in the cached SEO HTML and passes link equity to the hub that owns
    the 'कौन सी मंडी में बेचें / नेट भाव' query space.

    Carries the crop the farmer is viewing as a query param so the calculator
    opens pre-selected. On a district page we also pass that district's centroid
    (state/district → lat,lon) so the page can seed the location and rank nearby
    mandis without waiting for a GPS grant. The params are read client-side
    (bhav-netprice.js), so the cached /bhav/net-price HTML stays identical for
    every visitor — cache-safe."""
    q = f"?crop={quote(cs)}" if cs else ""
    if cs and state and district:
        c = district_geo.coord_for(state, district)
        if c:
            q += f"&lat={c[0]}&lon={c[1]}&place={quote(district)}"
    return (f'<a class="btn btn-np" href="/bhav/net-price{q}">'
            f'🚜 {escape(hi)} — भाड़ा जोड़कर नेट भाव देखें</a>')


# The two feed grains, and the one page on this site that is ABOUT what they
# are fed to. /pashupalan already links out to both of these crop hubs, and
# nothing linked back — so the only route into the egg-rate section was the
# sitemap and the hamburger drawer, which is how its 34 zone pages spent their
# first fortnight earning zero impressions.
#
# Tier 2 only. Repeating this on the ~2,000 maize district pages underneath
# would be link spam, and the crop hub is the page in that tree that actually
# ranks.
_FEED_CROPS = {"maize": "मक्का", "soyabean": "सोयाबीन"}


def _poultry_cta(cs: str) -> str:
    """Egg-rate link for a feed grain. Empty for every other crop, so the
    cta-row on the other ~200 crop hubs is byte-identical to before."""
    if cs not in _FEED_CROPS:
        return ""
    return (f'<a class="btn btn-kh" href="{SITE}/pashupalan/anda-rate">'
            f'🥚 {_FEED_CROPS[cs]} खिलाने वाले — आज का अंडा रेट</a>')


# ── MSP — the floor the price table never shows ──────────────
# "गेहूं ₹2,410" is only half an answer; the half that decides what a farmer
# does is that MSP is ₹2,585. Tier 4 has a real district average, so it gets
# the comparison; tiers 2/3 show the figure alone (which is what "गेहूं का MSP
# कितना है" actually asks for). Renders nothing when services/msp.py has no
# confirmed, in-season number — see the two guards documented there.

def _msp_html(commodity: str, avg=None) -> str:
    m = msp.msp_for(commodity)
    if not m:
        return ""
    cmp_ = msp.compare(avg, m["msp"]) if avg else None

    if not cmp_:
        tone, line = "flat", ""
    elif cmp_["side"] == "above":
        tone = "above"
        line = (f'आज का औसत मंडी भाव MSP से <b>₹{cmp_["abs_diff"]:,} '
                f'({cmp_["pct"]:g}%) ऊपर</b> है — मंडी में समर्थन मूल्य से बेहतर दाम मिल रहा है।')
    elif cmp_["side"] == "below":
        tone = "below"
        line = (f'आज का औसत मंडी भाव MSP से <b>₹{cmp_["abs_diff"]:,} '
                f'({abs(cmp_["pct"]):g}%) नीचे</b> है — आपकी फसल की सरकारी खरीद चल रही हो तो '
                f'क्रय केंद्र पर MSP का विकल्प भी देख लें।')
    else:
        tone = "at"
        line = 'आज का औसत मंडी भाव MSP के लगभग बराबर है।'

    note = f' {escape(m["note"])}' if m.get("note") else ""
    src = (f'<a href="{escape(m["source_url"])}" rel="nofollow" target="_blank">'
           f'{escape(m["source_label"])}</a>' if m.get("source_url")
           else escape(m.get("source_label", "")))
    return (f'<section class="msp-box {tone}">'
            f'<div class="msp-top">'
            f'<span class="msp-ic">🏛️</span>'
            f'<span class="msp-lbl"><b>MSP — {escape(m["hi"])} का न्यूनतम समर्थन मूल्य</b>'
            f'<em>{escape(m["season_label"])}</em></span>'
            f'<span class="msp-val">₹{m["msp"]:,}<small>/क्विंटल</small></span>'
            f'</div>'
            + (f'<p class="msp-cmp">{line}</p>' if line else "")
            + f'<p class="msp-fine">MSP वह न्यूनतम दाम है जिस पर सरकार यह फसल खरीदती है।{note} '
              f'स्रोत: {src}</p>'
              '</section>')


def _msp_faqs(commodity: str, avg=None, place: str = "") -> list:
    """FAQ pairs for the MSP block. Fed into the SAME `faqs` list the page
    renders from, so the visible Q&A and the FAQPage JSON-LD cannot drift."""
    m = msp.msp_for(commodity)
    if not m:
        return []
    hi = m["hi"]
    out = [(f"{hi} का MSP (न्यूनतम समर्थन मूल्य) कितना है?",
            f"{m['season_label']} के लिए {hi} का न्यूनतम समर्थन मूल्य "
            f"₹{m['msp']:,} प्रति क्विंटल है। "
            + (m["note"] + " " if m.get("note") else "")
            + f"यह भारत सरकार (CACP) द्वारा घोषित दर है।")]
    cmp_ = msp.compare(avg, m["msp"]) if avg else None
    if cmp_ and place:
        if cmp_["side"] == "above":
            ans = (f"{place} में {hi} का आज का औसत मंडी भाव ₹{int(avg):,} प्रति क्विंटल है, "
                   f"जो MSP ₹{m['msp']:,} से ₹{cmp_['abs_diff']:,} अधिक है।")
        elif cmp_["side"] == "below":
            ans = (f"{place} में {hi} का आज का औसत मंडी भाव ₹{int(avg):,} प्रति क्विंटल है, "
                   f"जो MSP ₹{m['msp']:,} से ₹{cmp_['abs_diff']:,} कम है। "
                   f"सरकारी खरीद चालू होने पर क्रय केंद्र पर MSP पर बेचा जा सकता है।")
        else:
            ans = (f"{place} में {hi} का आज का औसत मंडी भाव ₹{int(avg):,} प्रति क्विंटल है, "
                   f"जो MSP ₹{m['msp']:,} के लगभग बराबर है।")
        out.append((f"{place} में {hi} का भाव MSP से ऊपर है या नीचे?", ans))
    return out


# ── "बेचना है / खरीदना है" — the two doors out of a price page ──

# A district page ends on a number, and the farmer's next sentence is one of
# two: "मुझे बेचना है" or "मुझे खरीदना है". Both of those live on Krashi Bazar,
# so this panel is a chooser and nothing else — it names the two intents in the
# farmer's own words and hands him to the feed that can act on them.
#
# It used to be a whole flow inside this modal: a crop composer that posted to
# /bazar/posts, a browser for the district's own listings, and a /appeal/crop
# lead form for when that district turned out to be empty. On a feed this young
# the empty branch is what nearly everyone met — a form, and then a promise to
# call back. Two links into the real marketplace beat a form that answers
# nobody today. /appeal/crop still exists and still holds the rows it collected;
# nothing under /bhav writes to it any more.

# Where each intent goes. `mode=sell` opens Krashi Bazar's "मेरी फसल बेचें" tab,
# which already owns the login gate, the profile/phone check and the composer —
# so none of those are duplicated on this side.
_BAZAR_BUY  = "/krashi_bajar.html"
_BAZAR_SELL = "/krashi_bajar.html?mode=sell"

_APPEAL_CSS = """
.btn-appeal{background:var(--green-dark);color:#fff;box-shadow:var(--shadow-sm)}
.btn-appeal:hover{background:var(--green-mid)}
/* Above the page's floating furniture, not merely above the page: the device
   location opt-in card (location.js) parks itself at the bottom of the screen
   at z-index 99998, which is exactly where this sheet opens. At 10000 it landed
   squarely on top of the बेचना है row. */
.ap-ov{position:fixed;inset:0;z-index:100000;background:rgba(16,32,25,.55);
display:flex;align-items:flex-end;justify-content:center;padding:0;
-webkit-backdrop-filter:blur(2px);backdrop-filter:blur(2px)}
.ap-ov[hidden]{display:none}
.ap-box{position:relative;width:100%;max-width:520px;background:var(--white);
border-radius:20px 20px 0 0;padding:22px 18px 20px;
box-shadow:var(--shadow-md);animation:ap-up .22s ease}
@keyframes ap-up{from{transform:translateY(24px);opacity:.4}to{transform:none;opacity:1}}
@media(min-width:600px){.ap-ov{align-items:center;padding:20px}
.ap-box{border-radius:var(--radius-md)}}
.ap-box h2{margin:0 0 4px;font-size:19px;line-height:1.35;color:var(--green-dark);padding-right:34px}
.ap-sub{margin:0 0 15px;font-size:13px;color:var(--text-soft);line-height:1.5}
.ap-x{position:absolute;top:12px;right:12px;width:34px;height:34px;border:0;border-radius:50%;
background:var(--cream);color:var(--text-mid);font-size:21px;line-height:1;cursor:pointer}
.ap-x:hover{background:var(--border)}
/* The whole box is these two rows. Anchors rather than buttons, because each
   one is now a plain navigation to Krashi Bazar and has to behave like the link
   it is — long-press, middle-click, open in a new tab. */
.ap-pick{display:flex;flex-direction:column;gap:11px;margin-bottom:4px}
.ap-pick a{display:flex;align-items:center;gap:13px;width:100%;text-align:left;
text-decoration:none;color:inherit;padding:15px 16px;border:1.5px solid var(--border);
border-radius:14px;background:var(--white);transition:border-color .15s,background .15s}
.ap-pick a:hover{border-color:var(--green-mid);background:var(--green-pale)}
.ap-pick .ap-pi{font-size:26px;line-height:1;flex:0 0 auto}
.ap-pick .ap-pt{display:flex;flex-direction:column;min-width:0}
.ap-pick b{font-size:16px;font-weight:800;color:var(--green-dark)}
.ap-pick small{font-size:12px;color:var(--text-soft);margin-top:2px;line-height:1.45}
"""

# Plain string, not an f-string — the JS braces would need doubling otherwise.
_APPEAL_JS = """
var ov=document.getElementById('ap-ov');
if(!ov)return;
window.openCropAppeal=function(){
 ov.hidden=false;document.body.style.overflow='hidden';
};
window.closeCropAppeal=function(){
 ov.hidden=true;document.body.style.overflow='';
};
ov.addEventListener('click',function(e){if(e.target===ov)window.closeCropAppeal();});
document.addEventListener('keydown',function(e){
 if(e.key==='Escape'&&!ov.hidden)window.closeCropAppeal();});
"""


def _appeal_block(hi: str, state: str, district: str) -> str:
    """🤝 "बेचना है / खरीदना है" chooser — the panel behind the tier-4 buttons.

    Two links, no form and no login wall. Whichever door he takes, Krashi Bazar
    is where the rules live (posting needs a profile and a reachable number;
    browsing needs nothing at all), so a gate here would only mean being told no
    twice.

    Identical markup for every visitor — /bhav HTML is edge-cached, so nothing
    user-specific may be rendered server-side. There is nothing left to hydrate
    beyond opening and closing the box."""
    return f"""<div class="ap-ov" id="ap-ov" hidden>
<div class="ap-box" role="dialog" aria-modal="true" aria-labelledby="ap-t">
<button class="ap-x" type="button" onclick="closeCropAppeal()" aria-label="बंद करें">&times;</button>
<h2 id="ap-t">{escape(hi)} बेचना है या खरीदना है?</h2>
<p class="ap-sub">📍 {escape(district)}, {escape(_hindi_state(state))} · नीचे से चुनें।</p>
<div class="ap-pick">
<a href="{_BAZAR_SELL}">
<span class="ap-pi" aria-hidden="true">🌾</span>
<span class="ap-pt"><b>बेचना है</b><small>कृषि बाज़ार पर अपनी फसल की पोस्ट डालें — मात्रा, भाव और फोटो के साथ। खरीदार सीधे आपको फोन करेंगे।</small></span></a>
<a href="{_BAZAR_BUY}">
<span class="ap-pi" aria-hidden="true">🛒</span>
<span class="ap-pt"><b>खरीदना है</b><small>कृषि बाज़ार में किसानों और व्यापारियों की बिकाऊ फसल देखें — फोटो, मात्रा और भाव के साथ।</small></span></a>
</div>
</div>
</div>
<script>(function(){{{_APPEAL_JS}}})();</script>"""


def _nearest_panel_html(cs: str, hi: str, row: dict, dist_km: float) -> str:
    """Inner markup for the .better panel when a nearest mandi is found —
    mirrors the highest-price card so the swapped-in panel looks native."""
    ss, ds = _slugify(row.get("state", "")), _slugify(row.get("district", ""))
    dist = _fmt_km(dist_km)
    return (
        f'<h2>📍 आपके सबसे नज़दीकी {escape(hi)} मंडी</h2>'
        f'<p class="better-sub">आपके स्थान से करीब {dist} · भेजने से पहले भाड़ा ज़रूर जोड़ें</p>'
        f'<ul><li>'
        f'<a class="better-mandi-card" href="/bhav/{cs}/{ss}/{ds}">'
        f'<div class="bmc-details">'
        f'<span class="bmc-market">{escape(row.get("market", "-"))}</span>'
        f'<span class="bmc-meta">{escape(row.get("district", "-"))}, '
        f'{escape(_hindi_state(row.get("state", "")))} · {dist}</span>'
        f'</div>'
        f'<span class="bmc-action">भाव देखें →</span>'
        f'</a></li></ul>'
    )


@router.get("/bhav/nearest")
def bhav_nearest(crop: str, lat: float, lon: float, state: str = ""):
    idx = _get_index()
    cs = (crop or "").lower()
    commodity = idx.get("crops", {}).get(cs)
    if not commodity or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return JSONResponse({"ok": False}, headers={"Cache-Control": "no-store"})

    state_name = ""
    if state:                                   # tier 3 — scope to this state
        state_name = idx.get("states", {}).get(cs, {}).get(state.lower(), "")
        if not state_name:
            return JSONResponse({"ok": False}, headers={"Cache-Control": "no-store"})

    rows = [r for r in _rows_for(commodity, state=state_name)
            if _num(r.get("modal_price"))]
    res = district_geo.nearest(rows, lat, lon, lambda r: _num(r.get("modal_price")))
    if not res:
        return JSONResponse({"ok": False}, headers={"Cache-Control": "no-store"})

    row, dist_km = res
    html = _nearest_panel_html(cs, _hindi_name(commodity), row, dist_km)
    return JSONResponse({"ok": True, "html": html}, headers={"Cache-Control": "no-store"})


# ════════════════════════════════════════════════════════════
# NET PRICE AFTER TRANSPORT — "आपके पास सबसे अच्छा दाम"
#
# A price table shows the mandi RATE; it never shows what a farmer actually
# pockets after paying to cart the crop there. A farther mandi quoting a higher
# rate can net LESS than the one next door. This ranks the nearby mandis for a
# crop by NET भाव = modal − freight(distance, vehicle, quantity), using the same
# district centroids as the nearest-mandi panel and the freight estimates in
# freight_rates.json. Personalised + no-store, so it never enters the cached
# SEO HTML; the crawlable /bhav/net-price page hosts the explainer that ranks.
# ════════════════════════════════════════════════════════════
def _net_rank(commodity: str, lat: float, lon: float, qty: float,
              tier: str, limit: int = 6) -> list:
    """Best-net mandi per nearby district for a crop, ranked by net ₹/quintal.

    One entry per district (its highest-modal market), so the list spreads
    across places instead of filling up with same-district markets that share a
    centroid. Only districts with a known centroid within the freight radius are
    considered — the rest are silently skipped (the page degrades to a prompt)."""
    radius = freight.max_radius_km()
    best_by_dist: dict = {}          # (state, district) → row with max modal
    for r in _rows_for(commodity):
        modal = _num(r.get("modal_price"))
        if not modal:
            continue
        key = (r.get("state", ""), r.get("district", ""))
        cur = best_by_dist.get(key)
        if cur is None or modal > _num(cur.get("modal_price")):
            best_by_dist[key] = r

    ranked = []
    for (state, district), r in best_by_dist.items():
        c = district_geo.coord_for(state, district)
        if not c:
            continue
        dist_km = district_geo.haversine_km(lat, lon, c[0], c[1])
        if dist_km > radius:
            continue
        br = freight.net_price(_num(r.get("modal_price")), dist_km, tier, qty)
        m_coords = district_geo.resolve_mandi_coords(state, district, r.get("market", "-")) or (c[0], c[1], False)
        ranked.append({
            "market":   r.get("market", "-"),
            "district": district,
            "state":    state,
            "ss":       _slugify(state),
            "ds":       _slugify(district),
            "lat":      m_coords[0],
            "lon":      m_coords[1],
            **br,
        })
    ranked.sort(key=lambda x: (x["net_per_q"], -x["distance_km"]), reverse=True)
    return ranked[:limit]


def _money(n) -> str:
    """Compact ₹ for possibly-large totals — Indian लाख/करोड़ so a big number
    reads as '₹4.91 करोड़', not a wall of digits. Small values keep plain
    grouping (₹9,780)."""
    n = round(n)
    if abs(n) >= 10_000_000:
        return "₹" + f"{n / 10_000_000:.2f}".rstrip("0").rstrip(".") + " करोड़"
    if abs(n) >= 100_000:
        return "₹" + f"{n / 100_000:.2f}".rstrip("0").rstrip(".") + " लाख"
    return f"₹{n:,}"


def _net_price_html(cs: str, hi: str, ranked: list, qty: float, tier: str,
                    haul: str = "") -> str:
    """Results list for the net-price calculator. Highest net first; the nearest
    mandi is tagged so the farmer sees when 'closest' and 'best net' differ."""
    if not ranked:
        return ('<p class="np-empty">आपके स्थान के '
                f'{round(freight.max_radius_km())} किमी के भीतर इस फसल की कोई मंडी '
                'नहीं मिली जिसकी लोकेशन हमारे पास हो। थोड़ी देर बाद फिर देखें।</p>')

    nearest_ds = min(ranked, key=lambda x: x["distance_km"])["ds"]
    best = ranked[0]
    cards = []
    for i, m in enumerate(ranked):
        top = " best" if i == 0 else ""
        near = ('<span class="np-tag near">📍 सबसे पास</span>'
                if m["ds"] == nearest_ds else "")
        rank = "🥇" if i == 0 else f"{i + 1}"
        net_cls = "pos" if m["net_per_q"] >= 0 else "neg"
        cards.append(
            f'<a class="np-card{top}" href="/bhav/{cs}/{m["ss"]}/{m["ds"]}">'
            f'<span class="np-rank">{rank}</span>'
            f'<span class="np-body">'
            f'<span class="np-mkt">{escape(m["market"])}{near}</span>'
            f'<span class="np-sub">{escape(m["district"])}, {escape(_hindi_state(m["state"]))}'
            f' · {_fmt_km(m["distance_km"])} · भाड़ा ~₹{m["freight_per_q"]:,}/क्विं.</span>'
            f'</span>'
            f'<span class="np-net {net_cls}"><b>₹{m["net_per_q"]:,}</b>'
            f'<small>नेट/क्विं.</small><s>₹{m["modal"]:,}</s></span>'
            f'</a>')

    # One honest takeaway: does the best-net mandi beat the closest one? Plus the
    # concrete money — the total across the farmer's quantity, not just ₹/quintal.
    nearest = next(m for m in ranked if m["ds"] == nearest_ds)
    qn = int(qty) if float(qty).is_integer() else round(qty, 1)
    # The net भाव — the answer — pulled out as a big figure on the right.
    net_fig = (f'<div class="np-take-fig"><b>₹{best["net_per_q"]:,}</b>'
               '<small>नेट भाव/क्विंटल</small></div>')
    if best["ds"] == nearest_ds:
        total = round(best["net_per_q"] * qty)
        main = (f'✅ आपके सबसे पास वाली मंडी <b>{escape(best["market"])}</b> '
                f'({escape(best["district"])}) ही भाड़ा जोड़ने के बाद सबसे अच्छा नेट भाव दे रही है।')
        chips = f'<span>{qn} क्विंटल पर ≈ <b>{_money(total)}</b></span>'
    else:
        gain = best["net_per_q"] - nearest["net_per_q"]
        total_gain = round(gain * qty)
        main = (f'💡 भाड़ा जोड़ने के बाद <b>{escape(best["market"])}</b> '
                f'({escape(best["district"])}) में सबसे ज्यादा पैसा मिलेगा।')
        chips = (f'<span>सबसे पास वाली मंडी से <b>₹{gain:,}/क्विंटल</b> ज्यादा</span>'
                 f'<span>आपकी {qn} क्विंटल उपज पर करीब <b>{_money(total_gain)}</b> ज्यादा</span>')
    take = (f'<div class="np-take"><div class="np-take-body">'
            f'<div class="np-take-main">{main}</div>'
            f'<div class="np-take-info">{chips}</div></div>'
            f'{net_fig}</div>')
    map_bar = ('<div class="np-map-bar">'
               '<button id="np-map-toggle" class="np-map-toggle-btn" type="button" onclick="if(window.toggleNpMap)window.toggleNpMap();">'
               '<svg class="bm-icon" viewBox="0 0 24 24"><path d="M20.5 3l-.16.03L15 5.1 9 3 3.36 4.9c-.21.07-.36.25-.36.48V20.5c0 .28.22.5.5.5l.16-.03L9 18.9l6 2.1 5.64-1.9c.21-.07.36-.25.36-.48V3.5c0-.28-.22-.5-.5-.5zM15 19l-6-2.11V5l6 2.11V19z"/></svg>'
               ' नक्शे पर देखें (Satellite Map)</button>'
               '</div>'
               '<div id="np-map-container" class="np-map-container" style="display:none">'
               '<div id="np-map-canvas" class="bhav-map-canvas" style="height:350px;border-radius:12px;overflow:hidden"></div>'
               '</div>')

    return (f'{take}'
            f'{map_bar}'
            f'<div class="np-list">{"".join(cards)}</div>'
            f'{haul}'
            '<p class="np-fine">भाड़ा सिर्फ अनुमान है — असली खर्च डीज़ल, रास्ते और '
            'ट्रांसपोर्टर पर निर्भर करता है। भाव सरकारी Agmarknet रिपोर्ट से।</p>')


# ════════════════════════════════════════════════════════════
# AND WHO WILL ACTUALLY HAUL IT — the /rental supply, under the answer
#
# The freight figure above is an estimate of a trip NOBODY HAS BOOKED. This is
# the half that makes it bookable: every vehicle in the picker is also a machine
# in the /rental registry (freight_rates.json names it per tier), so the owners
# listed there can be ranked from the same lat/lon the mandis were ranked from.
# It is the one screen on the site where a farmer has already decided to move
# produce AND told us in what — spending that intent on a dead-end number was
# the waste.
#
# WE DO NOT BROKER THE TRIP — no cut of it, no matching, no promise a vehicle
# turns up. A per-trip commission needs both sides of one district on one day
# and stops being collectable the first time the two swap numbers; the moment we
# guaranteed the trip we would own the dispute. The money here is the owner's
# monthly listing fee, which /rental already sells, bills and expires.
#
# ORDERING IS DISTANCE AND NOTHING ELSE, inherited from services/rental.py
# rather than re-decided. That is the rule that section refuses to sell, and a
# panel that quietly re-sorted by who paid would break it from the outside.
# ════════════════════════════════════════════════════════════
def _haul_html(tier: str, lat: float, lon: float, limit: int = 3) -> str:
    """Owners of the vehicle the farmer just picked, nearest to him first.

    With no owner listed this still renders ONE line into /rental instead of
    nothing: that page answers what the haul should cost and routes to a
    government CHC, and a farmer who has just been shown ~₹X/क्विंटल of freight
    is precisely the reader who needs it. (Contrast services/rental.py's
    _owners_block, which renders nothing — it is already on that page.)

    Every failure — no slug for the tier, a machine dropped from the registry, a
    database that is down — returns "" and costs the calculator nothing. The
    net भाव is the answer this endpoint owes; this panel is a bonus and must
    never be able to take the answer down with it.
    """
    slug = freight.rental_slug(tier)
    item = rental_svc.by_slug(slug) if slug else None
    if not item:
        return ""
    name = escape(item.get("name_hi") or "")
    icon = escape(item.get("emoji") or "🚚")

    offers, db = [], None
    try:
        db = SessionLocal()
        offers = rental_svc.sort_by_distance(
            rental_svc.offers_for_equipment(db, slug), lat, lon)[:limit]
    except Exception:
        logger.warning("net-price: haulier lookup failed", exc_info=True)
    finally:
        if db is not None:
            db.close()

    if not offers:
        # "Nobody is listed" and "we could not look" deliberately land on the
        # same line, because the line promises only what /rental keeps with or
        # without a database — what this haul should cost, and the government
        # CHC route. It never says no owner exists, which is precisely what a
        # failed lookup does not know.
        return (f'<a class="np-haul-lone" href="/rental/{escape(slug)}">'
                f'<span>{icon} <b>{name}</b> का किराया कितना होना चाहिए, और '
                f'किराये पर कहाँ से लें</span>'
                f'<span class="np-haul-go">देखें →</span></a>')

    rows = []
    for o in offers:
        # Hindi state name, as the mandi cards above already render it — one
        # results list must not mix "Uttar Pradesh" with "उत्तर प्रदेश".
        bits = [x for x in (o["district"], _hindi_state(o["state"])) if x]
        if o.get("distance_km") is not None:
            bits.append(_fmt_km(o["distance_km"]))
        if o["kind_label"]:
            bits.append(o["kind_label"])
        rows.append(
            f'<a class="np-haul-row" '
            f'href="/rental/{escape(slug)}/{escape(o["provider_slug"])}">'
            f'<span class="np-haul-main">'
            f'<span class="np-haul-name">{escape(o["provider_name"])}</span>'
            f'<span class="np-haul-where">📍 {escape(" · ".join(bits))}</span>'
            f'</span>'
            f'<span class="np-haul-rate"><b>₹{o["rate"]:,}</b>'
            f'<span>{escape(o["rate_unit_hi"])}</span></span>'
            f'</a>')

    return (f'<div class="np-haul">'
            f'<div class="np-haul-head">{icon} यह माल ले जाने के लिए <b>{name}</b> '
            f'किराये पर देने वाले — आपके सबसे पास वाले पहले</div>'
            f'{"".join(rows)}'
            f'<a class="np-haul-all" href="/rental/{escape(slug)}">'
            f'सभी मालिक व किराये की सही रेंज देखें →</a></div>')


@router.get("/bhav/net-price-calc")
def bhav_net_price(crop: str, lat: float, lon: float,
                   qty: float = 20.0, tier: str = ""):
    """JSON for the net-price calculator — ranked nearby mandis by net ₹/quintal.
    Personalised, no-store; the crawlable page is /bhav/net-price."""
    idx = _get_index()
    commodity = idx.get("crops", {}).get((crop or "").lower())
    if not commodity or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return JSONResponse({"ok": False}, headers={"Cache-Control": "no-store"})
    tier = tier if tier in freight.tiers() else freight.default_tier()
    qty = min(max(float(qty or 1), 1.0), 100000.0)     # clamp to sane range
    ranked = _net_rank(commodity, lat, lon, qty, tier)
    # Only under a real answer — a farmer told there is no mandi within reach
    # has no trip to hire a vehicle for.
    haul = _haul_html(tier, lat, lon) if ranked else ""
    html = _net_price_html((crop or "").lower(), _hindi_name(commodity),
                           ranked, qty, tier, haul)
    return JSONResponse({"ok": True, "html": html, "count": len(ranked),
                         "mandis": ranked, "user_lat": lat, "user_lon": lon},
                        headers={"Cache-Control": "no-store"})


# ── crawlable calculator page: owns the "कौन सी मंडी में बेचें / नेट भाव" query ──
_NP_CSS = """
.np-hero{background:linear-gradient(135deg,var(--green-dark),var(--green-mid));color:#fff;
border-radius:var(--radius-md);padding:26px 20px 24px;margin:8px 0 18px}
.np-hero h1{color:#fff;margin:0 0 10px;font-size:23px;line-height:1.3}
.np-lede{color:rgba(255,255,255,.92);font-size:14.5px;line-height:1.6;margin:0;max-width:640px}
.np-more{display:none;background:none;border:0;font:inherit;font-weight:700;font-size:13px;
text-decoration:underline;cursor:pointer;padding:2px 0}
.np-lede-wrap .np-more{margin-top:8px;color:#fff}
.np-ex-more{margin-top:6px;color:var(--green-mid)}
.np-calc{background:var(--white);border:1px solid var(--border);border-radius:var(--radius-md);
box-shadow:var(--shadow-sm);padding:18px 16px;margin:0 0 22px}
.np-controls{display:grid;grid-template-columns:1fr 1fr;gap:12px}
/* mobile: shrink the hero, collapse the lede to 1 line behind "और देखें",
   stack the quantity/vehicle controls so the long vehicle label has room */
@media(max-width:640px){
.np-hero{padding:20px 16px 18px;border-radius:14px}
.np-hero h1{font-size:20px}
.np-lede{font-size:14px}
.np-lede-wrap.clamp:not(.open) .np-lede{display:-webkit-box;-webkit-line-clamp:1;
-webkit-box-orient:vertical;overflow:hidden}
.np-lede-wrap.clamp .np-more{display:inline-block}
.np-controls{grid-template-columns:1fr;gap:11px}
.np-calc{padding:15px 13px}
}
.np-field{display:flex;flex-direction:column;gap:5px;min-width:0}
.np-field.wide{grid-column:1/-1}
.np-field label{font-size:12.5px;font-weight:700;color:var(--text-soft)}
.np-field select,.np-field input{width:100%;font:inherit;font-size:15px;padding:11px 12px;
border:1.5px solid var(--border);border-radius:12px;background:var(--white);color:var(--text-dark);
-webkit-appearance:none;appearance:none}
.np-field select:focus,.np-field input:focus{outline:none;border-color:var(--green-mid)}
.np-locrow{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:14px}
.np-locbtn{border:0;background:var(--green-dark);color:#fff;font:inherit;font-weight:700;
font-size:14px;padding:11px 16px;border-radius:12px;cursor:pointer}
.np-locbtn:active{background:var(--green-mid)}
.np-locstatus{font-size:13px;color:var(--text-soft);flex:1;min-width:140px}
.np-results{margin-top:6px;position:relative;min-height:64px}
/* "calculating…" overlay while a recalculation is in flight (aria-busy) */
.np-results[aria-busy="true"]::before{content:"";position:absolute;inset:0;z-index:2;
background:rgba(245,247,244,.66);border-radius:12px;backdrop-filter:blur(1px)}
.np-results[aria-busy="true"]::after{content:"";position:absolute;left:50%;top:24px;
width:30px;height:30px;margin-left:-15px;z-index:3;border-radius:50%;
border:3px solid #cfe6d5;border-top-color:var(--green-mid);
animation:np-spin .7s linear infinite}
@keyframes np-spin{to{transform:rotate(360deg)}}
.np-take{display:flex;gap:14px;align-items:center;background:#e7f2fc;
border-left:4px solid var(--sky);border-radius:14px;padding:16px 18px;margin:16px 0 14px}
.np-take-body{flex:1;min-width:0}
.np-take-main{font-size:15px;line-height:1.6;color:#114b7d}
.np-take-info{display:flex;flex-wrap:wrap;gap:9px;margin-top:12px}
.np-take-info span{background:rgba(255,255,255,.82);border:1px solid #bcdcf6;border-radius:22px;
padding:7px 13px;font-size:13px;color:#114b7d;line-height:1.3}
.np-take-info b{font-weight:800}
.np-take-fig{flex:0 0 auto;display:flex;flex-direction:column;align-items:flex-end;text-align:right;
padding-left:14px;border-left:1px solid #bcdcf6}
.np-take-fig b{font-size:28px;font-weight:800;color:#114b7d;line-height:1.05;white-space:nowrap}
.np-take-fig small{font-size:11px;color:var(--sky);margin-top:3px;white-space:nowrap}
/* mobile: stack the takeaway — net price as a headline row on top, then the
   message and chips full-width, so nothing gets squeezed into a narrow column */
@media(max-width:560px){
.np-take{flex-direction:column;align-items:stretch;gap:11px;padding:14px 15px}
.np-take-fig{order:-1;flex-direction:row;align-items:baseline;justify-content:flex-start;
gap:8px;text-align:left;padding:0 0 11px;border-left:0;border-bottom:1px solid #bcdcf6}
.np-take-fig b{font-size:25px}
.np-take-fig small{margin-top:0}
.np-take-main{font-size:14px}
.np-take-info{margin-top:0}
}
.np-list{display:flex;flex-direction:column;gap:9px}
.np-card{display:flex;align-items:center;gap:12px;text-decoration:none;color:inherit;
background:var(--white);border:1px solid var(--border);border-radius:14px;padding:12px 14px}
.np-card.best{border-color:var(--green-mid);box-shadow:0 0 0 2px rgba(45,106,79,.14)}
.np-rank{font-size:17px;font-weight:800;color:var(--green-mid);flex:0 0 22px;text-align:center}
.np-body{display:flex;flex-direction:column;min-width:0;flex:1}
.np-mkt{font-weight:800;font-size:15px;color:var(--text-dark);display:flex;align-items:center;gap:7px;flex-wrap:wrap}
.np-sub{font-size:12px;color:var(--text-soft);margin-top:2px;line-height:1.45}
.np-tag{font-size:10.5px;font-weight:700;padding:2px 7px;border-radius:20px;white-space:nowrap}
.np-tag.near{background:#e7f0ff;color:#1a5bb8}
.np-net{display:flex;flex-direction:column;align-items:flex-end;text-align:right;flex:0 0 auto}
.np-net b{font-size:18px;font-weight:800;color:var(--green-dark);line-height:1.1}
.np-net.neg b{color:#b3341f}
.np-net small{font-size:10px;color:var(--text-soft)}
.np-net s{font-size:11px;color:var(--text-soft);opacity:.75}
.np-fine{font-size:11.5px;color:var(--text-soft);line-height:1.5;margin:12px 0 0}
.np-empty{font-size:14px;color:var(--text-soft);line-height:1.6;padding:14px 4px}
.np-hint{font-size:13.5px;color:var(--text-soft);line-height:1.6;padding:8px 4px}
.np-ex{background:var(--white);border:1px solid var(--border);border-radius:var(--radius-md);
padding:6px 16px 10px;margin:8px 0}
.np-ex h2{font-size:16px;margin:12px 0 6px}
.np-ex p{font-size:13.5px;line-height:1.7;color:var(--text-mid)}
.np-steps{list-style:none;counter-reset:s;margin:6px 0;padding:0;display:flex;flex-direction:column;gap:9px}
.np-steps li{counter-increment:s;position:relative;padding-left:34px;font-size:13.5px;
line-height:1.55;color:var(--text-dark)}
.np-steps li::before{content:counter(s);position:absolute;left:0;top:-1px;width:24px;height:24px;
border-radius:50%;background:var(--green-pale);color:var(--green-dark);font-weight:800;font-size:12.5px;
display:flex;align-items:center;justify-content:center}
/* ── who will haul it: the /rental owners of the chosen vehicle ── */
.np-haul{margin-top:14px;background:var(--white);border:1px solid var(--border);
border-radius:14px;padding:13px 14px 11px}
.np-haul-head{font-size:13px;color:var(--text-mid);line-height:1.5;padding-bottom:10px}
.np-haul-head b{color:var(--text-dark);font-weight:800}
.np-haul-row{display:flex;align-items:center;gap:12px;text-decoration:none;color:inherit;
padding:10px 0;border-top:1px solid var(--border)}
.np-haul-main{display:flex;flex-direction:column;min-width:0;flex:1}
.np-haul-name{font-weight:700;font-size:14px;color:var(--text-dark);line-height:1.3}
.np-haul-where{font-size:11.5px;color:var(--text-soft);margin-top:2px;line-height:1.45}
.np-haul-rate{display:flex;flex-direction:column;align-items:flex-end;text-align:right;flex:0 0 auto}
.np-haul-rate b{font-size:16px;font-weight:800;color:var(--green-dark);line-height:1.1}
.np-haul-rate span{font-size:10.5px;color:var(--text-soft);margin-top:2px}
.np-haul-all{display:inline-block;margin-top:10px;font-size:12.5px;font-weight:700;
color:var(--green-dark);text-decoration:none}
/* no owner listed yet — /rental still answers what the haul should cost */
.np-haul-lone{display:flex;align-items:center;justify-content:space-between;gap:12px;
margin-top:14px;background:var(--green-pale);border:1px solid var(--green-light);
border-radius:14px;padding:12px 14px;text-decoration:none;color:var(--text-dark);
font-size:13.5px;line-height:1.45}
.np-haul-lone b{font-weight:800}
.np-haul-go{font-weight:800;color:var(--green-dark);white-space:nowrap}
@media(max-width:420px){.np-net b{font-size:16px}.np-mkt{font-size:14px}}
@media(max-width:640px){
.np-ex{padding:4px 14px 10px}
.np-ex h2{font-size:15px}
.np-ex-body{position:relative;max-height:118px;overflow:hidden}
.np-ex-body.open{max-height:none}
.np-ex-body:not(.open)::after{content:"";position:absolute;left:0;right:0;bottom:0;height:44px;
background:linear-gradient(rgba(255,255,255,0),var(--white))}
.np-ex .np-ex-more{display:inline-block}
}
"""


@router.get("/bhav/net-price", response_class=HTMLResponse)
def bhav_net_price_page():
    idx = _get_index()
    today_hi = _hindi_date(date.today())
    canon = f"{SITE}/bhav/net-price"

    # Crop dropdown — staples (app tile order) first, then the rest alphabetical.
    crops = {cs: cn for cs, cn in idx.get("crops", {}).items() if _is_crop(cn)}
    ordered = sorted(crops.items(), key=lambda kv: (_tile_rank(kv[1]), _hindi_name(kv[1])))
    default_cs = "wheat" if "wheat" in crops else (ordered[0][0] if ordered else "")
    opts = []
    for cs, cn in ordered:
        hi = _hindi_name(cn)
        label = hi if hi == cn else f"{hi} ({cn})"
        sel = " selected" if cs == default_cs else ""
        opts.append(f'<option value="{escape(cs)}"{sel}>{escape(label)}</option>')
    crop_options = "".join(opts)

    tier_opts = "".join(
        f'<option value="{escape(k)}"{" selected" if k == freight.default_tier() else ""}>'
        f'{escape(t.get("label", k))} — {escape(t.get("hint", ""))}</option>'
        for k, t in freight.tiers().items())

    faqs = [
        ("नेट भाव (net price) क्या होता है?",
         "नेट भाव वह रकम है जो मंडी का भाव पाने के बाद, फसल वहाँ तक ले जाने का भाड़ा घटाकर, "
         "असल में आपकी जेब में आती है। नेट भाव = मंडी का मॉडल भाव − प्रति क्विंटल भाड़ा। "
         "दूर की एक मंडी ऊँचा रेट दिखाकर भी, भाड़ा जोड़ने के बाद पास की मंडी से कम दे सकती है।"),
        ("कौन सी मंडी में बेचना फायदेमंद है — पास वाली या ऊँचे भाव वाली?",
         "हमेशा नेट भाव देखिए, सिर्फ रेट नहीं। यह कैलकुलेटर आपके स्थान के आस-पास की मंडियों को "
         "भाड़ा घटाकर मिलने वाले नेट भाव के हिसाब से क्रम में लगाता है, ताकि आप देख सकें कि "
         "असल में सबसे ज्यादा पैसा कहाँ मिलेगा।"),
        ("भाड़ा कैसे जोड़ा जाता है?",
         "भाड़ा दूरी, वाहन (ट्रैक्टर-ट्रॉली / मिनी-ट्रक / ट्रक) और मात्रा पर निर्भर करता है — "
         "ज्यादा माल भरने पर प्रति क्विंटल भाड़ा कम पड़ता है, इसलिए दूर की ऊँचे भाव वाली मंडी भी "
         "फायदेमंद हो सकती है। यहाँ दिखाया भाड़ा एक अनुमान है; असली खर्च डीज़ल और ट्रांसपोर्टर पर निर्भर है।"),
        ("भाव का स्रोत क्या है?",
         "सभी मंडी भाव भारत सरकार के Agmarknet (data.gov.in) पोर्टल की रोज़ाना रिपोर्ट से लिए जाते हैं। "
         "भाड़ा हमारा अनुमान है, मंडी भाव सरकारी आँकड़ा है।"),
    ]
    faq_html, faq_ld = _faq(faqs)
    crumb_ld = _crumb_ld([("कृषि मित्र", f"{SITE}/"),
                          ("मंडी भाव", f"{SITE}/bhav"),
                          ("नेट भाव कैलकुलेटर", canon)])
    ld = _ld(faq_ld, crumb_ld)

    body = f"""<section class="np-hero">
<h1>भाड़ा जोड़कर सबसे अच्छा दाम — कौन सी मंडी में बेचें?</h1>
<div class="np-lede-wrap" id="np-lede-wrap">
<p class="np-lede">मंडी का ऊँचा रेट देखकर मत चलिए — जो <b>नेट भाव</b> (भाड़ा घटाकर) आपकी जेब में आए, वही असली है।
अपनी फसल, मात्रा और वाहन चुनिए; यह कैलकुलेटर आपके आस-पास की मंडियों को भाड़ा जोड़ने के बाद
मिलने वाले नेट भाव के हिसाब से क्रम में लगा देगा।</p>
<button type="button" class="np-more" id="np-lede-more" aria-expanded="false" hidden>और देखें</button>
</div>
</section>

<section class="np-calc">
<div class="np-controls">
<div class="np-field wide">
<label for="np-crop">फसल</label>
<select id="np-crop">{crop_options}</select>
</div>
<div class="np-field">
<label for="np-qty">मात्रा (क्विंटल)</label>
<input id="np-qty" type="number" inputmode="numeric" min="1" step="1" value="20">
</div>
<div class="np-field">
<label for="np-tier">वाहन</label>
<select id="np-tier">{tier_opts}</select>
</div>
</div>
<div class="np-locrow">
<button type="button" class="np-locbtn" id="np-loc-btn">📍 मेरी लोकेशन इस्तेमाल करें</button>
<span class="np-locstatus" id="np-loc-status">नज़दीकी मंडियाँ दिखाने के लिए अपनी लोकेशन चालू करें।</span>
</div>
<div class="np-results" id="np-results">
<p class="np-hint">ऊपर 📍 दबाकर अपनी लोकेशन चालू करते ही, आपके आस-पास की मंडियाँ नेट भाव के हिसाब से यहाँ दिखेंगी।</p>
</div>
</section>

<section class="np-ex">
<div class="np-ex-body" id="np-ex-body">
<h2>नेट भाव क्यों मायने रखता है</h2>
<p>मान लीजिए आपके जिले की मंडी गेहूँ का भाव ₹2,400/क्विंटल दे रही है, और 60 किमी दूर की एक मंडी
₹2,520 दिखा रही है। रेट देखकर लगेगा दूर वाली बेहतर है — पर वहाँ तक 20 क्विंटल ले जाने का भाड़ा
यदि ₹90/क्विंटल पड़े, तो नेट भाव सिर्फ ₹2,430 बचता है। बड़ा माल भरने पर वही भाड़ा घटकर प्रति
क्विंटल कम हो जाता है और दूर की मंडी फायदेमंद हो जाती है। इसीलिए <b>बेचने से पहले हमेशा भाड़ा
जोड़कर नेट भाव देखना चाहिए</b> — यही यह कैलकुलेटर करता है।</p>
<h2>इसका इस्तेमाल कैसे करें</h2>
<ol class="np-steps">
<li>अपनी <b>फसल</b> चुनिए।</li>
<li>कितने <b>क्विंटल</b> बेचने हैं, वह भरिए।</li>
<li><b>वाहन</b> चुनिए — पास के लिए ट्रैक्टर-ट्रॉली, दूर के लिए ट्रक।</li>
<li>📍 <b>लोकेशन</b> चालू कीजिए — आपके {round(freight.max_radius_km())} किमी के दायरे की मंडियाँ
नेट भाव के क्रम में दिख जाएँगी, सबसे ऊपर वह जहाँ सबसे ज्यादा पैसा मिलेगा।</li>
</ol>
</div>
<button type="button" class="np-more np-ex-more" id="np-ex-more" aria-expanded="false" hidden>और देखें</button>
</section>

<h2>अक्सर पूछे जाने वाले सवाल</h2>
{faq_html}
<script src="{_asset('bhav-netprice.js')}" defer></script>"""

    crumbs = (f'<a href="{SITE}/">कृषि मित्र</a> › '
              f'<a href="{SITE}/bhav">मंडी भाव</a> › नेट भाव कैलकुलेटर')
    # ── CTR-optimised title/meta (§2.3) ──
    desc = ("दूर की मंडी का ऊँचा रेट धोखा दे सकता है। ट्रांसपोर्ट, टोल और समय "
            "घटाकर 2 मिनट में असली नेट भाव निकालें — कौन सी मंडी लाभदायक, तुरंत देखें।")
    return _doc("मंडी नेट भाव कैलकुलेटर — भाड़ा घटाकर असली रेट, कौन सी मंडी लाभदायक?",
                desc, canon, crumbs, body, ld, extra_css=_NP_CSS + _BHAV_MAP_CSS)


# ════════════════════════════════════════════════════════════
# LAZY-LOAD API — serve heavy sections as JSON + HTML fragments
#
# The page renders instantly with the structure the farmer needs
# (cards, selectors). Heavy DB queries (national aggregates,
# full-state comparison) are fetched client-side AFTER the page
# is visible — eliminating the 504 timeout on Render/Netlify.
# ════════════════════════════════════════════════════════════
# Two grey bars stood in for every lazy panel on the site — for a grid of
# crop tiles, for a table of district prices, for the seasonality card alike.
# What arrives is never that shape, so the page jumped when it landed and the
# wait told the farmer nothing about what he was waiting for. Each panel now
# names its own shape, and the blocks are .km-sk (frontend/km-skeleton.css).
def _lazy_skel(shape: str = "text") -> str:
    """The skeleton a lazy panel waits behind, in the shape of its content."""
    if shape == "tiles":          # a grid of crop / place tiles
        tile = ('<div class="lz-tile"><div class="km-sk lz-tile-img"></div>'
                '<div class="lz-tile-txt"><div class="km-sk km-sk-line"></div>'
                '<div class="km-sk km-sk-line sm" style="width:58%"></div></div></div>')
        inner = f'<div class="lz-tiles">{tile * 6}</div>'
    elif shape == "rows":         # a list of district / mandi rows
        row = ('<div class="lz-row"><div class="km-sk km-sk-line" style="width:42%"></div>'
               '<div class="km-sk km-sk-line" style="width:74px"></div></div>')
        inner = f'<div class="lz-rows">{row * 5}</div>'
    elif shape == "card":         # one panel with a heading and a body block
        inner = ('<div class="lz-card"><div class="km-sk km-sk-line lg" style="width:52%"></div>'
                 '<div class="km-sk" style="height:96px;margin-top:12px;border-radius:10px"></div>'
                 '<div class="km-sk km-sk-line sm" style="width:64%;margin-top:11px"></div></div>')
    else:                         # a paragraph of text
        inner = ('<div class="lz-card"><div class="km-sk km-sk-line"></div>'
                 '<div class="km-sk km-sk-line" style="width:88%;margin-top:9px"></div>'
                 '<div class="km-sk km-sk-line" style="width:60%;margin-top:9px"></div></div>')
    return (f'<div class="lazy-skel" role="status" aria-live="polite">'
            f'<span class="km-sk-label">लोड हो रहा है…</span>{inner}</div>')


_LAZY_SKEL = _lazy_skel("text")   # kept for callers that want the plain shape
_LAZY_CSS = """
.lazy-skel{padding:18px 16px}
.lz-tiles{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px 18px}
@media(max-width:900px){.lz-tiles{grid-template-columns:repeat(2,minmax(0,1fr))}}
.lz-tile{display:flex;align-items:center;gap:12px;padding:8px 0}
.lz-tile-img{width:70px;height:54px;border-radius:9px;flex-shrink:0}
.lz-tile-txt{flex:1;min-width:0;display:flex;flex-direction:column;gap:7px}
.lz-rows{display:flex;flex-direction:column;gap:14px}
.lz-row{display:flex;align-items:center;justify-content:space-between;gap:12px}
.lz-card{padding:2px 0}
"""


def _lazy_div(div_id: str, shape: str = "text") -> str:
    """Placeholder div with skeleton that JS will fill from the lazy API."""
    return f'<div id="{div_id}">{_lazy_skel(shape)}</div>'


def _lazy_script(pairs: list) -> str:
    """Emit a tiny <script> that fetches each (url, target_div_id) pair after
    DOMContentLoaded and swaps in the returned HTML. Fires all fetches in
    parallel so they appear as fast as the DB can answer."""
    fetches = "".join(
        f"fetch('{url}').then(r=>r.json()).then(d=>{{if(d.ok){{var e=document.getElementById('{did}');if(e)e.outerHTML=d.html;}}}}).catch(()=>{{}});"
        for url, did in pairs
    )
    return f'<script>document.addEventListener("DOMContentLoaded",function(){{{fetches}}});</script>'


_LEAFLET_CSS = '<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">'

_BHAV_MAP_CSS = """
.bhav-map-sec{background:var(--white);border:1px solid var(--border);border-radius:var(--radius-md);overflow:hidden;margin:26px 0;box-shadow:var(--shadow-sm);position:relative;isolation:isolate;z-index:10}
.bhav-map-head{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:16px 20px;border-bottom:1px solid var(--border);background:var(--white)}
.bhav-map-head-left{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.bhav-map-head h2{font-size:17px;font-weight:700;color:var(--text-dark);margin:0;line-height:1.3}
.bhav-map-pill{display:inline-flex;align-items:center;padding:3px 10px;background:var(--green-pale);color:var(--green-dark);border-radius:20px;font-size:12px;font-weight:700;letter-spacing:0.2px}
.bhav-map-sub-note{font-size:12.5px;color:var(--text-soft);font-weight:500}
@media(max-width:768px){.bhav-map-sub-note{display:none}}
.bhav-map-wrap{position:relative;width:100%;height:420px;background:#0d1d13;overflow:hidden}
@media(max-width:640px){.bhav-map-wrap{height:330px}.bhav-map-head{padding:12px 16px}}
.bhav-map-canvas{width:100%;height:100%;z-index:1;background:#0d1d13}
.bhav-map-canvas .leaflet-container,.bhav-map-canvas .leaflet-tile-container{background:#0d1d13!important}
.bhav-map-ctrls{position:absolute;top:14px;left:14px;right:14px;z-index:20;display:flex;align-items:flex-start;justify-content:space-between;gap:10px;pointer-events:none}
.bhav-map-ctrls-left,.bhav-map-ctrls-right{display:flex;align-items:flex-start;gap:8px;pointer-events:auto}
.bhav-map-v-stack{display:flex;flex-direction:column;align-items:flex-end;gap:8px}
.bhav-map-v-row{display:flex;align-items:flex-start;gap:8px}
.bhav-map-more-wrap{position:relative;display:flex;justify-content:flex-end}
.bhav-map-menu{position:absolute;top:calc(100% + 8px);right:0;min-width:212px;background:rgba(14,32,22,.97);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);border:1px solid rgba(82,183,136,.35);border-radius:14px;padding:6px;box-shadow:0 10px 30px rgba(0,0,0,.5);z-index:40;display:flex;flex-direction:column;gap:2px;animation:bmSlideUp .18s ease-out}
.bhav-map-menu[hidden]{display:none}
.bhav-map-menu button{display:flex;align-items:center;gap:9px;width:100%;background:transparent;border:none;color:#d8f3dc;font-family:inherit;font-size:13px;font-weight:600;padding:9px 11px;border-radius:10px;cursor:pointer;line-height:1.25;white-space:nowrap}
.bhav-map-menu button:hover{background:rgba(82,183,136,.18);color:#fff}
.bhav-map-menu button .bm-icon{width:16px;height:16px;fill:#95d5b2}
@media(max-width:480px){.bhav-map-menu{min-width:188px}.bhav-map-menu button{font-size:12px;padding:8px 10px}}
.bhav-map-btn-group{display:inline-flex;align-items:center;background:rgba(238,240,242,.95);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);border:1px solid rgba(255,255,255,.6);border-radius:18px;overflow:hidden;padding:4px;box-shadow:0 4px 16px rgba(0,0,0,.22);gap:3px}
.bhav-map-tab{background:transparent;border:none;color:#1e293b;padding:7px 16px;border-radius:14px;cursor:pointer;transition:all .18s ease;font-family:inherit;display:inline-flex;align-items:center;gap:8px;line-height:1.2;min-height:44px}
.bhav-map-tab.active{background:#0e3d26;color:#fff;box-shadow:0 2px 8px rgba(0,0,0,.35)}
.bm-tab-svg{width:22px;height:22px;flex-shrink:0;stroke:currentColor}
.bhav-tab-txt{display:inline-block;text-align:left;font-size:12.5px;font-weight:700;line-height:1.15;max-width:72px;white-space:normal}
@media(max-width:480px){
  .bhav-map-ctrls{top:10px;left:10px;right:10px;gap:6px}
  .bhav-map-tab{padding:5px 10px;gap:6px;min-height:38px}
  .bm-tab-svg{width:18px;height:18px}
  .bhav-tab-txt{font-size:11px;max-width:62px}
}
.bhav-map-btn{position:relative;display:inline-flex;align-items:center;justify-content:center;gap:7px;background:#0e3d26;backdrop-filter:blur(8px);color:#fff;border:1px solid rgba(82,183,136,.35);border-radius:14px;padding:8px 14px;font-size:13px;font-weight:700;text-decoration:none;cursor:pointer;transition:all .18s ease;font-family:inherit;line-height:1.2;box-shadow:0 4px 14px rgba(0,0,0,.3);pointer-events:auto}
.bhav-map-btn:hover{background:#145234;border-color:rgba(82,183,136,.6);color:#fff;box-shadow:0 6px 18px rgba(0,0,0,.4)}
.bhav-map-btn-naksha{height:44px;box-sizing:border-box}
@media(max-width:480px){.bhav-map-btn-naksha{padding:6px 10px;font-size:11.5px;height:38px;white-space:nowrap}}
.bhav-map-btn-route{position:absolute;bottom:16px;left:14px;z-index:22;background:#0e3d26;border:1px solid rgba(82,183,136,.4);border-radius:14px;padding:10px 18px;font-size:13.5px;font-weight:700;box-shadow:0 6px 20px rgba(0,0,0,.45);height:44px;box-sizing:border-box}
.bhav-map-btn-route:hover{background:#145234;transform:translateY(-1px)}
.bhav-map-btn-route.loading{opacity:.85;pointer-events:none}
@media(max-width:480px){.bhav-map-btn-route{bottom:36px;left:10px;padding:8px 14px;font-size:12px;height:40px}}
.bhav-map-btn-loc{position:absolute;bottom:20px;right:68px;z-index:22;width:44px;height:44px;border-radius:14px;box-sizing:border-box}
@media(max-width:480px){.bhav-map-btn-loc{bottom:116px;right:10px;width:40px;height:40px;border-radius:12px}}
.bm-icon{width:14px;height:14px;display:inline-block;vertical-align:middle;fill:currentColor;flex-shrink:0}
.bhav-map-skel{position:absolute;inset:0;background:radial-gradient(circle at center,#153224 0%,#0a1710 100%);display:flex;flex-direction:column;align-items:center;justify-content:center;color:#95d5b2;z-index:2;cursor:pointer;transition:opacity .3s ease}
.bhav-map-skel.hidden{opacity:0;pointer-events:none}
.bhav-map-skel-icon{width:44px;height:44px;stroke:currentColor;fill:none;stroke-width:1.5;margin-bottom:10px;opacity:.85}
.bhav-map-skel-txt{font-size:14px;font-weight:600;color:#e8f5e9}
.bhav-map-skel-sub{font-size:12px;color:#a3b899;margin-top:4px}
.bhav-mandi-pin{cursor:pointer;position:relative}
.bhav-mandi-pin:hover{z-index:99999!important}
.bhav-mandi-pin-inner{display:inline-flex;flex-direction:column;align-items:center;transform:translate(-50%,-100%);position:relative;transition:transform .18s cubic-bezier(.2,0,0,1)}
.bhav-pin-card{display:flex;align-items:center;gap:6px;background:#132d20;color:#fff;border:1.5px solid #52b788;border-radius:18px;padding:4px 10px;box-shadow:0 3px 12px rgba(0,0,0,.45);white-space:nowrap;font-size:12px;font-weight:600;line-height:1.2;transition:transform .15s ease,box-shadow .15s ease}
.bhav-mandi-pin:hover .bhav-pin-card{transform:scale(1.05);box-shadow:0 6px 18px rgba(0,0,0,.6)}
.bhav-pin-name{color:#d8f3dc}
.bhav-pin-price{background:#52b788;color:#0b1d13;font-weight:800;padding:2px 6px;border-radius:10px;font-size:11px}
.bhav-pin-top .bhav-pin-card{background:#2a1c02;border-color:#f59e0b;box-shadow:0 3px 14px rgba(245,158,11,.45)}
.bhav-pin-top .bhav-pin-name{color:#fef3c7}
.bhav-pin-top .bhav-pin-price{background:#f59e0b;color:#1e1302}
.bhav-pin-tag{font-size:9px;font-weight:800;background:#f59e0b;color:#1e1302;padding:1px 5px;border-radius:6px;letter-spacing:0.3px}
.bhav-pin-arrow{width:0;height:0;border-left:6px solid transparent;border-right:6px solid transparent;border-top:7px solid #52b788;margin-top:-1px}
.bhav-pin-top .bhav-pin-arrow{border-top-color:#f59e0b}
.bhav-pin-stem{position:absolute;left:50%;top:100%;width:2px;background:#52b788;transform:translateX(-50%);pointer-events:none;opacity:0.9;border-radius:1px;box-shadow:0 0 3px rgba(0,0,0,.5);z-index:1}
.bhav-pin-top .bhav-pin-stem{background:#f59e0b}
.bhav-pin-stem .bhav-pin-dot{position:absolute;left:50%;bottom:-3px;width:6px;height:6px;border-radius:50%;background:#52b788;border:1.5px solid #fff;transform:translateX(-50%);box-shadow:0 0 4px rgba(0,0,0,.6)}
.bhav-pin-top .bhav-pin-stem .bhav-pin-dot{background:#f59e0b}
.bhav-user-pin{width:16px;height:16px;background:#2563eb;border:2.5px solid #fff;border-radius:50%;box-shadow:0 0 0 4px rgba(37,99,235,.35);position:relative;animation:bmPulse 2s infinite}
@keyframes bmPulse{0%{box-shadow:0 0 0 0 rgba(37,99,235,.6)}70%{box-shadow:0 0 0 12px rgba(37,99,235,0)}100%{box-shadow:0 0 0 0 rgba(37,99,235,0)}}
.bhav-popup{font-family:var(--font-body);padding:2px;min-width:180px}
.bhav-popup-title{font-size:14px;font-weight:700;color:#14351f;margin-bottom:4px;display:flex;align-items:center;justify-content:space-between;gap:6px}
.bhav-popup-tag{font-size:10px;padding:2px 6px;background:#d8f3dc;color:#1b4332;border-radius:4px;font-weight:700}
.bhav-popup-price{font-size:18px;font-weight:800;color:#1b4332;margin:4px 0 2px}
.bhav-popup-price small{font-size:12px;font-weight:500;color:#556b2f}
.bhav-popup-range{font-size:12px;color:#5a6b61;margin-bottom:6px}
.bhav-popup-date{font-size:11px;color:#7c8983;margin-bottom:8px;display:flex;align-items:center;gap:4px}
.bhav-popup-dist{font-size:11px;color:#1e40af;font-weight:600;background:#eff6ff;padding:2px 6px;border-radius:4px;display:inline-block;margin-bottom:8px}
.bhav-popup-actions{display:flex;gap:8px;margin-top:8px}
.bhav-popup-btn{flex:1;display:inline-flex;align-items:center;justify-content:center;gap:5px;padding:7px 10px;font-size:12px;font-weight:700;border-radius:6px;text-decoration:none;border:none;cursor:pointer;font-family:inherit}
.bhav-popup-btn-nav{background:#166534;color:#fff}
.bhav-popup-btn-nav:hover{background:#14532d;color:#fff}
.bhav-popup-btn-gmap{background:#2563eb;color:#fff}
.bhav-popup-btn-gmap:hover{background:#1d4ed8;color:#fff}
.bhav-popup-btn-bazar{background:#f3f4f6;color:#1f2937}
.bhav-popup-btn-bazar:hover{background:#e5e7eb;color:#111827}
.np-map-bar{margin:12px 0 6px;display:flex;justify-content:flex-end}
.np-map-toggle-btn{display:inline-flex;align-items:center;gap:6px;background:var(--cream);border:1px solid var(--border);color:var(--text-dark);padding:6px 14px;border-radius:8px;font-size:12.5px;font-weight:700;cursor:pointer;transition:all .15s}
.np-map-toggle-btn:hover{background:var(--green-pale);color:var(--green-dark);border-color:var(--green-light)}
.np-map-container{margin:10px 0 16px;border:1px solid var(--border);border-radius:12px;overflow:hidden}
.answer-range{align-items:center}
@media(max-width:480px){.answer-range{gap:14px}}
@media(max-width:360px){.answer-range{gap:10px}}
.answer-map-btn{margin-left:auto;display:inline-flex;align-items:center;gap:7px;position:relative;overflow:hidden;background:linear-gradient(135deg,rgba(16,185,129,.32) 0%,rgba(5,150,105,.22) 50%,rgba(6,78,59,.78) 100%),rgba(10,35,24,.75);border:1.5px solid rgba(110,231,183,.65);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);color:#fff;font-family:var(--font-body);font-size:13px;font-weight:700;padding:7px 14px;border-radius:9999px;cursor:pointer;line-height:1.2;transition:all .2s cubic-bezier(.34,1.56,.64,1);box-shadow:0 4px 14px rgba(0,0,0,.25),0 0 16px rgba(16,185,129,.25),inset 0 1px 0 rgba(255,255,255,.35);white-space:nowrap;min-height:38px;touch-action:manipulation}
.answer-map-btn::after{content:'';position:absolute;top:-60%;left:-60%;width:40%;height:220%;background:linear-gradient(90deg,transparent,rgba(255,255,255,.32),transparent);transform:rotate(25deg);animation:ambSheen 4.5s cubic-bezier(.4,0,.2,1) infinite;pointer-events:none}
@keyframes ambSheen{0%,65%{left:-70%}82%,100%{left:150%}}
.answer-map-btn:hover{background:linear-gradient(135deg,rgba(16,185,129,.45) 0%,rgba(5,150,105,.32) 50%,rgba(6,78,59,.88) 100%),rgba(10,35,24,.85);border-color:#6ee7b7;transform:translateY(-2px) scale(1.02);box-shadow:0 6px 20px rgba(0,0,0,.35),0 0 22px rgba(52,211,153,.45),inset 0 1px 0 rgba(255,255,255,.5)}
.answer-map-btn:active{transform:translateY(0) scale(.98);box-shadow:0 2px 8px rgba(0,0,0,.35),0 0 10px rgba(16,185,129,.3)}
.answer-map-btn .amb-radar{position:relative;display:inline-flex;width:8px;height:8px;flex-shrink:0}
.answer-map-btn .amb-ping{position:absolute;inset:-3px;border-radius:50%;background:#34d399;opacity:.75;animation:ambPing 2s cubic-bezier(0,0,.2,1) infinite}
.answer-map-btn .amb-dot{position:relative;width:8px;height:8px;border-radius:50%;background:#34d399;box-shadow:0 0 6px #34d399}
@keyframes ambPing{70%,100%{transform:scale(2.2);opacity:0}}
.answer-map-btn .bm-icon{width:15px;height:15px;stroke:#a7f3d0;color:#a7f3d0;flex-shrink:0;transition:transform .2s ease}
.answer-map-btn:hover .bm-icon{transform:rotate(-6deg) scale(1.1);stroke:#fff;color:#fff}
.answer-map-btn .amb-txt{color:#fff;font-weight:700;letter-spacing:.2px;text-shadow:0 1px 2px rgba(0,0,0,.35)}
.answer-map-btn .amb-badge{display:inline-flex;align-items:center;padding:2px 6px;font-size:10px;font-weight:800;letter-spacing:.4px;background:rgba(52,211,153,.22);border:1px solid rgba(110,231,183,.5);color:#d1fae5;border-radius:6px;line-height:1.1;transition:all .18s ease}
.answer-map-btn:hover .amb-badge{background:rgba(52,211,153,.35);border-color:#6ee7b7;color:#fff}
.answer-map-btn .amb-arrow{width:13px;height:13px;stroke:#a7f3d0;flex-shrink:0;transition:transform .2s ease,stroke .2s ease;margin-left:-2px}
.answer-map-btn:hover .amb-arrow{transform:translateX(3px);stroke:#fff}
@media(max-width:480px){.answer-map-btn{padding:6px 11px;font-size:12px;gap:5px;min-height:34px}.answer-map-btn .amb-badge{font-size:9px;padding:1px 4px}}
@media(max-width:360px){.answer-map-btn .amb-badge,.answer-map-btn .amb-arrow{display:none}.answer-map-btn{padding:5px 9px;font-size:11.5px;gap:4px}}
.bhav-map-btn-icon{width:42px;height:42px;padding:0!important;display:inline-flex;align-items:center;justify-content:center;background:#183324;border:1px solid rgba(82,183,136,.25);border-radius:12px;line-height:1;flex-shrink:0}
.bhav-map-btn-icon:hover{background:#204230;border-color:rgba(82,183,136,.5)}
.bhav-map-btn-icon.active{background:#2563eb;border-color:#60a5fa;color:#fff}
.bhav-map-btn-icon.loading svg{opacity:.5}
.bhav-map-btn-icon.loading::after{content:'';position:absolute;inset:4px;border-radius:50%;border:2px solid rgba(255,255,255,.22);border-top-color:#8ef0b4;animation:bmSpin .8s linear infinite;pointer-events:none}
.bhav-map-btn-icon .bm-icon{width:19px;height:19px}
.bm-icon-stroke{fill:none;stroke:currentColor;stroke-width:2.2;stroke-linecap:round;stroke-linejoin:round}
@media(max-width:480px){.bhav-map-btn-icon{width:38px;height:38px;border-radius:10px}}
@keyframes bmSpin{100%{transform:rotate(360deg)}}
.bhav-map-sec.is-fullscreen{position:fixed!important;inset:0!important;z-index:999999!important;width:100vw!important;height:100vh!important;margin:0!important;border-radius:0!important;border:none!important}
.bhav-map-sec.is-fullscreen .bhav-map-head{padding:10px 16px;background:var(--white)}
.bhav-map-sec.is-fullscreen .bhav-map-wrap{height:calc(100vh - 54px)!important}
@media(max-width:640px){.bhav-map-sec.is-fullscreen .bhav-map-wrap{height:calc(100vh - 48px)!important}}
.bhav-map-route-card{position:absolute;bottom:26px;left:14px;max-width:calc(100% - 158px);box-sizing:border-box;background:rgba(14,61,38,.96);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);border:1px solid rgba(82,183,136,.5);border-radius:14px;padding:9px 14px;display:flex;align-items:center;justify-content:space-between;gap:10px;z-index:35;box-shadow:0 8px 24px rgba(0,0,0,.5);animation:bmSlideUp .25s ease-out}
@keyframes bmSlideUp{from{transform:translateY(16px);opacity:0}to{transform:translateY(0);opacity:1}}
.bhav-route-flow{pointer-events:none}
.bhav-route-flow.is-done{animation:bhavRouteFlow .45s ease-out forwards}
@keyframes bhavRouteFlow{from{opacity:.95}to{opacity:0}}
.bhav-route-main{display:flex;align-items:center;gap:10px;min-width:0;flex:1}
.bhav-route-main svg{width:18px;height:18px;fill:#60a5fa;flex-shrink:0}
.bhav-route-info{display:flex;flex-direction:column;min-width:0;gap:2px}
.bhav-route-title{font-size:12px;line-height:1.3;color:#d8f3dc;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bhav-route-title b{color:#fff;font-weight:700}
.bhav-route-meta{font-size:12px;line-height:1.35;color:#95d5b2;font-weight:500}
.bhav-route-meta b{color:#8ef0b4;font-size:13.5px;font-weight:800}
.bhav-route-meta small{color:#cbd5e1;font-size:11px;font-weight:500;margin-left:4px}
.bhav-route-nav-btn{display:inline-flex;align-items:center;gap:5px;background:#2563eb;color:#fff;font-size:11.5px;font-weight:700;padding:6px 12px;border-radius:8px;text-decoration:none;white-space:nowrap;transition:background .15s;flex-shrink:0}
.bhav-route-nav-btn:hover{background:#1d4ed8;color:#fff}
.bhav-route-close-btn{background:rgba(255,255,255,.08);border:none;color:#a7f3d0;cursor:pointer;padding:6px;display:inline-flex;align-items:center;justify-content:center;border-radius:6px;transition:all .15s;flex-shrink:0}
.bhav-route-close-btn:hover{background:rgba(255,255,255,.15);color:#fff}
.bhav-map-canvas .leaflet-control-zoom{border:none!important;border-radius:14px!important;overflow:hidden!important;box-shadow:0 4px 16px rgba(0,0,0,.35)!important;margin:0 14px 20px 0!important}
@media(max-width:480px){.bhav-map-canvas .leaflet-control-zoom{margin:0 10px 36px 0!important}}
.bhav-map-canvas .leaflet-control-zoom a{background:#ffffff!important;color:#111827!important;width:44px!important;height:38px!important;line-height:38px!important;font-size:22px!important;font-weight:600!important;border:none!important;border-bottom:1px solid #e5e7eb!important;display:flex!important;align-items:center!important;justify-content:center!important;transition:background .15s ease!important}
@media(max-width:480px){.bhav-map-canvas .leaflet-control-zoom a{width:40px!important;height:34px!important;font-size:20px!important}}
.bhav-map-canvas .leaflet-control-zoom a:last-child{border-bottom:none!important}
.bhav-map-canvas .leaflet-control-zoom a:hover{background:#f3f4f6!important;color:#000!important}
.bhav-map-canvas .leaflet-control-attribution{background:rgba(243,244,246,.9)!important;backdrop-filter:blur(6px)!important;border-radius:8px!important;padding:2px 8px!important;font-size:10px!important;color:#374151!important;margin:0 14px 8px 0!important;box-shadow:0 2px 8px rgba(0,0,0,.15)!important}
.bhav-map-canvas .leaflet-control-attribution a{color:#1d4ed8!important;text-decoration:none!important}
@media(max-width:480px){.bhav-map-canvas .leaflet-control-attribution{display:none!important}}
@media(max-width:520px){
  .bhav-map-route-card{bottom:36px;left:10px;max-width:calc(100% - 76px);padding:8px 10px;gap:6px}
  .bhav-route-title{font-size:11px}
  .bhav-route-meta{font-size:11px;line-height:1.35}
  .bhav-route-meta b{font-size:12.5px}
  .bhav-route-nav-btn{padding:5px 8px;font-size:10.5px}
}
"""


def _bhav_map_script(map_id: str, markers_json: str, center_lat: float, center_lon: float) -> str:
    js_id = map_id.replace('-', '_')
    return f"""<script>
(function(){{
  var mapId = "{map_id}";
  var jsId = "{js_id}";
  var markers = {markers_json};
  var center = [{center_lat}, {center_lon}];
  var map = null, lowSatLayer = null, satLayer = null, labelLayer = null, osmLayer = null, markerObjs = [];
  var userMarker = null;
  var routeGlowLayer = null, routeLineLayer = null, routeFlowLayer = null, routeAnimRaf = null;
  var initialized = false;

  function loadAsset(u, isCss) {{
    return new Promise(function(res, rej) {{
      if (isCss) {{
        if (document.querySelector('link[href="' + u + '"]')) return res();
        var l = document.createElement('link');
        l.rel = 'stylesheet'; l.href = u;
        l.onload = res; l.onerror = rej;
        document.head.appendChild(l);
      }} else {{
        if (window.L || document.querySelector('script[src="' + u + '"]')) return res();
        var s = document.createElement('script');
        s.src = u; s.async = true;
        s.onload = res; s.onerror = rej;
        document.head.appendChild(s);
      }}
    }});
  }}

  function ensureLeaflet() {{
    if (window.L) return Promise.resolve();
    return Promise.all([
      loadAsset('https://unpkg.com/leaflet@1.9.4/dist/leaflet.css', true),
      loadAsset('https://unpkg.com/leaflet@1.9.4/dist/leaflet.js', false)
    ]);
  }}

  function initMap() {{
    if (initialized) return;
    initialized = true;
    var skel = document.getElementById(mapId + '-skel');
    if (skel) skel.classList.add('hidden');

    var mapEl = document.getElementById(mapId + '-canvas');
    if (!mapEl) return;

    map = L.map(mapEl, {{zoomControl: false, zoomSnap: 0.25}}).setView(center, 11);
    L.control.zoom({{position: 'bottomright'}}).addTo(map);

    // Tier 1: Instant Low-Poly/Low-Res Base (z=7, ~18KB, stretched across entire canvas in <150ms)
    lowSatLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
      maxNativeZoom: 7, maxZoom: 20, zIndex: 1, attribution: ''
    }});

    // Tier 2 & 3: Mid/High-Res Progressive Satellite Imagery (z=8-18)
    satLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
      attribution: 'Tiles © Esri World Imagery', minZoom: 8, maxNativeZoom: 18, maxZoom: 20,
      zIndex: 2, updateWhenIdle: true, updateWhenZooming: false, keepBuffer: 1
    }});
    satLayer.on('tileerror', function(e) {{
      if (e.tile && !e.tile._retried) {{
        e.tile._retried = true;
        setTimeout(function() {{ e.tile.src = e.url; }}, 800);
      }}
    }});
    labelLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
      attribution: '© Esri', minZoom: 8, maxNativeZoom: 18, maxZoom: 20,
      zIndex: 3, updateWhenIdle: true, updateWhenZooming: false, keepBuffer: 1
    }});
    osmLayer = L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
      attribution: '© OpenStreetMap contributors', maxNativeZoom: 19, maxZoom: 20,
      updateWhenIdle: true, keepBuffer: 2
    }});

    // The LOD tiers have to be staged, not stacked. Added together, the four
    // z7 tiles queue behind ~20 full-res ones over the browser's six
    // connections, so the "instant" base arrives last and the canvas sits
    // black — which is the whole delay the tiers were meant to remove.
    lowSatLayer.addTo(map);
    var hiResAdded = false, labelsAdded = false;
    function stillSatellite() {{
      return !(osmLayer && map && map.hasLayer(osmLayer));
    }}
    function addLabelTier() {{
      if (labelsAdded || !map || !stillSatellite()) return;
      labelsAdded = true;
      labelLayer.addTo(map);
    }}
    function addHiResTier() {{
      if (hiResAdded || !map || !stillSatellite()) return;
      hiResAdded = true;
      satLayer.addTo(map);
      satLayer.once('load', addLabelTier);
      setTimeout(addLabelTier, 2200);
    }}
    lowSatLayer.once('load', addHiResTier);
    setTimeout(addHiResTier, 500);

    markerObjs = [];
    var bounds = L.latLngBounds([]);
    markers.forEach(function(m, i) {{
      var pos = [m.lat, m.lon];
      bounds.extend(pos);

      var pinHtml = '<div class="bhav-mandi-pin-inner" id="' + mapId + '-pin-inner-' + i + '">' +
        '<div class="bhav-pin-card">' +
        (m.is_top ? '<span class="bhav-pin-tag">उच्चतम भाव</span>' : '') +
        '<span class="bhav-pin-name">' + m.name + '</span>' +
        '<span class="bhav-pin-price">' + m.price + '</span>' +
        '</div><div class="bhav-pin-arrow"></div>' +
        '<div class="bhav-pin-stem" id="' + mapId + '-pin-stem-' + i + '" style="display:none">' +
        '<div class="bhav-pin-dot"></div>' +
        '</div>' +
        '</div>';

      var icon = L.divIcon({{
        className: 'bhav-mandi-pin' + (m.is_top ? ' bhav-pin-top' : ''),
        html: pinHtml,
        iconSize: null,
        iconAnchor: null
      }});

      var popHtml = '<div class="bhav-popup">' +
        '<div class="bhav-popup-title"><span>' + m.market + '</span>' +
        (m.is_top ? '<span class="bhav-popup-tag">उच्चतम भाव</span>' : '') + '</div>' +
        '<div class="bhav-popup-price">' + m.price + (m.price.indexOf('₹') === 0 ? ' <small>/क्विंटल</small>' : '') + '</div>' +
        (m.min_price && m.min_price !== '—' && m.max_price && m.max_price !== '—' ?
          '<div class="bhav-popup-range">न्यूनतम ' + m.min_price + ' — अधिकतम ' + m.max_price + '</div>' : '') +
        (m.date ? '<div class="bhav-popup-date">' +
          '<svg class="bm-icon" style="width:12px;height:12px" viewBox="0 0 24 24"><path d="M19 4h-1V2h-2v2H8V2H6v2H5c-1.11 0-1.99.9-1.99 2L3 20a2 2 0 0 0 2 2h14c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 16H5V10h14v10zM5 8V6h14v2H5z"/></svg> रिपोर्ट: ' + m.date + '</div>' : '') +
        (m.is_exact === false ? '<div class="bhav-popup-approx">⚠️ <b>मंडी की जगह अनुमानित</b><br>जगह अनुमानित है — गूगल मैप पर मंडी का नाम खोजें</div>' : '') +
        '<div id="' + mapId + '-dist-' + i + '" class="bhav-popup-dist" style="display:none"></div>' +
        '<div class="bhav-popup-actions">' +
        '<button type="button" id="' + mapId + '-pop-btn-' + i + '" onclick="' + jsId + '_showPathTo(' + i + ')" class="bhav-popup-btn bhav-popup-btn-nav">' +
        '<svg class="bm-icon" viewBox="0 0 24 24"><path d="M12 2L4.5 20.29l.71.71L12 18l6.79 3 .71-.71z"/></svg> रास्ता देखें</button>' +
        '<button type="button" onclick="if(window.openCropAppeal)openCropAppeal();else window.location.href=\\'/bazar\\';" class="bhav-popup-btn bhav-popup-btn-bazar">फसल बेचें / खरीदें</button>' +
        '</div></div>';

      var mObj = L.marker(pos, {{icon: icon}}).addTo(map).bindPopup(popHtml);
      markerObjs.push({{
        marker: mObj,
        data: m,
        idx: i,
        pos: pos,
        is_top: m.is_top,
        price_num: m.price_num || 0
      }});
    }});

    function restackMarkers() {{
      if (!map || markerObjs.length <= 1) return;

      var pts = markerObjs.map(function(item) {{
        var pt = map.latLngToContainerPoint(item.pos);
        return {{
          idx: item.idx,
          x: pt.x,
          y: pt.y,
          is_top: item.is_top,
          price_num: item.price_num
        }};
      }});

      var visited = new Uint8Array(pts.length);
      var clusters = [];

      for (var i = 0; i < pts.length; i++) {{
        if (visited[i]) continue;
        var cluster = [pts[i]];
        visited[i] = 1;
        var added = true;
        while (added) {{
          added = false;
          for (var j = 0; j < pts.length; j++) {{
            if (visited[j]) continue;
            for (var k = 0; k < cluster.length; k++) {{
              var dx = Math.abs(pts[j].x - cluster[k].x);
              var dy = Math.abs(pts[j].y - cluster[k].y);
              if (dx < 140 && dy < 34) {{
                visited[j] = 1;
                cluster.push(pts[j]);
                added = true;
                break;
              }}
            }}
          }}
        }}
        clusters.push(cluster);
      }}

      clusters.forEach(function(cluster) {{
        if (cluster.length === 1) {{
          var single = cluster[0];
          var innerEl = document.getElementById(mapId + '-pin-inner-' + single.idx);
          var stemEl = document.getElementById(mapId + '-pin-stem-' + single.idx);
          if (innerEl) {{
            innerEl.style.transform = 'translate(-50%, -100%)';
            innerEl.style.zIndex = single.is_top ? '100' : '10';
          }}
          if (stemEl) stemEl.style.display = 'none';
          return;
        }}

        cluster.sort(function(a, b) {{
          if (a.is_top && !b.is_top) return 1;
          if (!a.is_top && b.is_top) return -1;
          return a.price_num - b.price_num;
        }});

        var curTop = cluster[0].y - 32;
        for (var s = 0; s < cluster.length; s++) {{
          var item = cluster[s];
          var innerEl = document.getElementById(mapId + '-pin-inner-' + item.idx);
          var stemEl = document.getElementById(mapId + '-pin-stem-' + item.idx);

          if (s === 0) {{
            if (innerEl) {{
              innerEl.style.transform = 'translate(-50%, -100%)';
              innerEl.style.zIndex = item.is_top ? '100' : '10';
            }}
            if (stemEl) stemEl.style.display = 'none';
            curTop = item.y - 32;
          }} else {{
            var targetBottom = curTop - 5;
            var yShift = Math.max(s * 34, Math.round(item.y - targetBottom));
            curTop = item.y - yShift - 32;

            if (innerEl) {{
              innerEl.style.transform = 'translate(-50%, calc(-100% - ' + yShift + 'px))';
              innerEl.style.zIndex = (item.is_top ? 200 : 50) + s;
            }}
            if (stemEl) {{
              stemEl.style.display = 'block';
              stemEl.style.height = (yShift + 1) + 'px';
            }}
          }}
        }}
      }});
    }}

    if (markers.length > 1) {{
      map.fitBounds(bounds, {{padding: [45, 45], maxZoom: 13}});
    }} else if (markers.length === 1) {{
      map.setView([markers[0].lat, markers[0].lon], 12);
    }}

    map.on('zoomend', restackMarkers);
    map.on('moveend', restackMarkers);
    map.on('click', function(e) {{
      if (!pinMode) return;
      placeUserMarker(e.latlng.lat, e.latlng.lng);
      setPinMode(false);
      updateUserPos(e.latlng.lat, e.latlng.lng);
    }});
    window.addEventListener('resize', function() {{ if (map) {{ map.invalidateSize(); restackMarkers(); }} }});
    setTimeout(function(){{ map && map.invalidateSize(); restackMarkers(); }}, 80);
    setTimeout(function(){{ map && map.invalidateSize(); restackMarkers(); }}, 300);
    setTimeout(function(){{ map && map.invalidateSize(); restackMarkers(); }}, 800);
    setTimeout(function(){{ map && map.invalidateSize(); restackMarkers(); }}, 1500);
  }}

  var setLayerFn = function(type) {{
    if (!map) return;
    var btnSat = document.getElementById(mapId + '-tab-sat');
    var btnOsm = document.getElementById(mapId + '-tab-osm');
    if (type === 'sat') {{
      if (osmLayer) map.removeLayer(osmLayer);
      if (lowSatLayer && !map.hasLayer(lowSatLayer)) map.addLayer(lowSatLayer);
      if (satLayer && !map.hasLayer(satLayer)) map.addLayer(satLayer);
      if (labelLayer && !map.hasLayer(labelLayer)) map.addLayer(labelLayer);
      if (btnSat) btnSat.classList.add('active');
      if (btnOsm) btnOsm.classList.remove('active');
    }} else {{
      if (lowSatLayer) map.removeLayer(lowSatLayer);
      if (satLayer) map.removeLayer(satLayer);
      if (labelLayer) map.removeLayer(labelLayer);
      if (osmLayer && !map.hasLayer(osmLayer)) map.addLayer(osmLayer);
      if (btnOsm) btnOsm.classList.add('active');
      if (btnSat) btnSat.classList.remove('active');
    }}
  }};
  window[jsId + '_setLayer'] = setLayerFn;
  window[mapId + '_setLayer'] = setLayerFn;

  function haversineKm(lat1, lon1, lat2, lon2) {{
    var R = 6371;
    var dLat = (lat2 - lat1) * Math.PI / 180;
    var dLon = (lon2 - lon1) * Math.PI / 180;
    var a = Math.sin(dLat/2) * Math.sin(dLat/2) +
            Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
            Math.sin(dLon/2) * Math.sin(dLon/2);
    return R * (2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a)));
  }}

  function renderRoute(coords, uLat, uLon, mLat, mLon, approx) {{
    if (!map) return;
    if (routeAnimRaf) {{ cancelAnimationFrame(routeAnimRaf); routeAnimRaf = null; }}
    if (routeGlowLayer && map) map.removeLayer(routeGlowLayer);
    if (routeLineLayer && map) map.removeLayer(routeLineLayer);
    if (routeFlowLayer && map) map.removeLayer(routeFlowLayer);

    // Deep blue background glow
    routeGlowLayer = L.polyline(coords, {{
      color: '#1d4ed8', weight: 8, opacity: approx ? 0.3 : 0.45, lineCap: 'round', lineJoin: 'round'
    }}).addTo(map);

    // Solid blue road path
    routeLineLayer = L.polyline(coords, {{
      color: approx ? '#3b82f6' : '#2563eb', weight: 4.5, opacity: 0.95,
      dashArray: approx ? '9 9' : null, lineCap: 'round', lineJoin: 'round'
    }}).addTo(map);

    // One-time flow animation: a bright comet rides the head of the draw, from
    // the user's point to the mandi, then fades out and is discarded.
    routeFlowLayer = L.polyline(coords, {{
      color: '#93c5fd', weight: 5.5, opacity: 0.95,
      className: 'bhav-route-flow', lineCap: 'round', lineJoin: 'round'
    }}).addTo(map);

    function pathEl(layer) {{
      if (!layer) return null;
      return layer.getElement ? layer.getElement() : (layer._path || null);
    }}
    function eachEl(fn) {{
      [pathEl(routeGlowLayer), pathEl(routeLineLayer), pathEl(routeFlowLayer)].forEach(function(el) {{
        if (el) fn(el);
      }});
    }}

    // Hidden until the fitBounds zoom has settled — a reveal that runs while
    // Leaflet is still reprojecting the path reads as a stutter.
    eachEl(function(el) {{ el.style.visibility = 'hidden'; }});

    var reduceMotion = false;
    try {{
      reduceMotion = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    }} catch (_) {{}}

    function finishFlow() {{
      routeAnimRaf = null;
      var lEl = pathEl(routeLineLayer), gEl = pathEl(routeGlowLayer);
      [lEl, gEl].forEach(function(el) {{
        if (!el) return;
        el.style.visibility = '';
        el.style.strokeDasharray = (el === lEl && approx) ? '9 9' : 'none';
        el.style.strokeDashoffset = '';
      }});
      var fEl = pathEl(routeFlowLayer);
      if (fEl) {{
        fEl.style.visibility = '';
        if (fEl.classList) fEl.classList.add('is-done');
        else fEl.style.opacity = '0';
      }}
      setTimeout(function() {{
        if (routeFlowLayer && map) {{
          map.removeLayer(routeFlowLayer);
          routeFlowLayer = null;
        }}
      }}, 500);
    }}

    // Driven frame by frame off the live path length rather than by a CSS
    // transition, so a reprojection mid-flight can never leave a stale dash
    // pattern on screen.
    function runFlow() {{
      var lEl = pathEl(routeLineLayer), gEl = pathEl(routeGlowLayer), fEl = pathEl(routeFlowLayer);
      var probe = fEl || lEl;
      var len0 = 0;
      try {{ len0 = probe && probe.getTotalLength ? probe.getTotalLength() : 0; }} catch (_) {{}}
      if (reduceMotion || !len0) {{ finishFlow(); return; }}
      eachEl(function(el) {{ el.style.visibility = ''; }});
      var dur = Math.max(3000, Math.min(7000, len0 * 5.5));
      var t0 = 0;
      function frame(ts) {{
        if (!t0) t0 = ts;
        var p = Math.min(1, (ts - t0) / dur);
        var e = p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2;
        var len = len0;
        try {{ len = probe.getTotalLength() || len0; }} catch (_) {{}}
        var head = e * len;
        [lEl, gEl].forEach(function(el) {{
          if (!el) return;
          el.style.strokeDasharray = len + ' ' + len;
          el.style.strokeDashoffset = String(len - head);
        }});
        if (fEl) {{
          var tail = Math.max(34, len * 0.18);
          fEl.style.strokeDasharray = tail + ' ' + (len + tail);
          fEl.style.strokeDashoffset = String(tail - head);
        }}
        if (p < 1) routeAnimRaf = requestAnimationFrame(frame);
        else finishFlow();
      }}
      routeAnimRaf = requestAnimationFrame(frame);
    }}

    var flowStarted = false;
    function kickFlow() {{
      if (flowStarted) return;
      flowStarted = true;
      map.off('moveend', kickFlow);
      if (window.requestAnimationFrame) requestAnimationFrame(runFlow);
      else setTimeout(runFlow, 30);
    }}
    map.on('moveend', kickFlow);
    setTimeout(kickFlow, 3000);

    var routeBounds = L.latLngBounds(coords);
    routeBounds.extend([uLat, uLon]);
    routeBounds.extend([mLat, mLon]);
    // fitBounds teleports when the jump is long; the flight shows the farmer
    // the map travelling from where they are to the mandi.
    var fitOpts = {{paddingTopLeft: [40, 75], paddingBottomRight: [45, 135], maxZoom: 14}};
    if (reduceMotion || !map.flyToBounds) {{
      map.fitBounds(routeBounds, fitOpts);
    }} else {{
      fitOpts.duration = 1.5;
      fitOpts.easeLinearity = 0.22;
      map.flyToBounds(routeBounds, fitOpts);
    }}
  }}

  var activeMandi = null, activeMandiIdx = null, pickedExplicitly = false;
  var pinMode = false;

  function setPinMode(on, msg) {{
    pinMode = !!on;
    var canvas = document.getElementById(mapId + '-canvas');
    if (canvas) canvas.style.cursor = pinMode ? 'crosshair' : '';
    var hint = document.getElementById(mapId + '-pin-hint');
    if (pinMode && !hint && canvas && canvas.parentNode) {{
      hint = document.createElement('div');
      hint.id = mapId + '-pin-hint';
      hint.className = 'bhav-map-pin-hint';
      canvas.parentNode.appendChild(hint);
    }}
    if (hint) {{
      if (msg) hint.textContent = msg;
      else if (!hint.textContent) hint.textContent = 'नक्शे पर अपनी जगह टैप करें';
      hint.style.display = pinMode ? 'block' : 'none';
    }}
  }}

  function placeUserMarker(uLat, uLon) {{
    if (!map) return;
    if (userMarker) map.removeLayer(userMarker);
    var uIcon = L.divIcon({{
      className: 'bhav-user-pin-wrap',
      html: '<div class="bhav-user-pin" title="पिन खिसकाएं"></div>',
      iconSize: [20, 20],
      iconAnchor: [10, 10]
    }});
    userMarker = L.marker([uLat, uLon], {{icon: uIcon, draggable: true}}).addTo(map)
      .bindPopup('<div style="font-weight:700;font-size:12px;color:#1e40af;text-align:center;">आपकी लोकेशन<div style="font-size:11px;font-weight:500;color:#64748b;margin-top:2px;">(पिन खींचकर सही जगह रख सकते हैं)</div></div>');

    userMarker.on('dragend', function(e) {{
      var p = e.target.getLatLng();
      updateUserPos(p.lat, p.lng);
    }});



    var locBtn = document.getElementById(mapId + '-btn-loc');
    if (locBtn) {{
      locBtn.classList.remove('loading');
      locBtn.classList.add('active');
      locBtn.title = 'आपकी लोकेशन मिली (पिन को खिसका भी सकते हैं)';
    }}
  }}

  function findAndDrawShortestPath(uLat, uLon, targetMandi, straightDist) {{
    var routeCard = document.getElementById(mapId + '-route-card');
    var routeDistEl = document.getElementById(mapId + '-route-dist');
    var routeMandiEl = document.getElementById(mapId + '-route-mandi');
    var routeNavEl = document.getElementById(mapId + '-route-nav');
    var routeBtn = document.getElementById(mapId + '-btn-route');

    if (routeBtn) {{
      routeBtn.classList.remove('loading');
      routeBtn.innerHTML = '<svg class="bm-icon" viewBox="0 0 24 24"><path d="M12 2L4.5 20.29l.71.71L12 18l6.79 3 .71-.71z"/></svg> रास्ता देखें';
    }}

    var destLat = Number(targetMandi.lat);
    var destLon = Number(targetMandi.lon);

    var isExact = targetMandi.is_exact !== false;
    var navQ = targetMandi.nav_q || targetMandi.market || targetMandi.name || '';
    var navDest = (isExact || !navQ)
      ? destLat.toFixed(5) + ',' + destLon.toFixed(5)
      : encodeURIComponent(navQ);
    var navUrl = 'https://www.google.com/maps/dir/?api=1&origin=' +
                 Number(uLat).toFixed(5) + ',' + Number(uLon).toFixed(5) +
                 '&destination=' + navDest +
                 '&travelmode=driving';

    if (routeMandiEl) routeMandiEl.textContent = targetMandi.market || targetMandi.name;
    var routeLabelEl = document.getElementById(mapId + '-route-label');
    if (routeLabelEl) routeLabelEl.textContent = pickedExplicitly ? 'चुनी गई मंडी' : 'नजदीकी मंडी';
    if (routeNavEl) {{
      routeNavEl.href = navUrl;
      routeNavEl.innerHTML = '<svg class="bm-icon" viewBox="0 0 24 24"><path d="M12 2L4.5 20.29l.71.71L12 18l6.79 3 .71-.71z"/></svg> गूगल मैप पर देखें';
      routeNavEl.title = 'Google Maps में रास्ता खोलें';
    }}
    if (routeCard) routeCard.style.display = 'flex';
    if (routeBtn) routeBtn.style.display = 'none';

    if (activeMandiIdx !== null) {{
      var popBtn = document.getElementById(mapId + '-pop-btn-' + activeMandiIdx);
      if (popBtn) {{
        popBtn.outerHTML = '<a href="' + navUrl + '" target="_blank" rel="noopener" class="bhav-popup-btn bhav-popup-btn-nav bhav-popup-btn-gmap" id="' + mapId + '-pop-btn-' + activeMandiIdx + '"><svg class="bm-icon" viewBox="0 0 24 24"><path d="M12 2L4.5 20.29l.71.71L12 18l6.79 3 .71-.71z"/></svg> गूगल मैप पर देखें</a>';
      }}
    }}

    var fallbackCoords = [[uLat, uLon], [destLat, destLon]];
    // Geometry detail costs real bytes on a rural connection: a 493km route is
    // 69KB at overview=full vs 1.5KB simplified. Past ~60km the map is zoomed
    // out far enough that the extra points cannot be seen, so only short hauls
    // ask for them.
    var ovDetail = straightDist > 60 ? 'simplified' : 'full';
    var osrmUrl = 'https://router.project-osrm.org/route/v1/driving/' +
                  Number(uLon).toFixed(5) + ',' + Number(uLat).toFixed(5) + ';' +
                  Number(destLon).toFixed(5) + ',' + Number(destLat).toFixed(5) +
                  '?overview=' + ovDetail + '&geometries=geojson';

    fetch(osrmUrl)
      .then(function(res) {{ return res.json(); }})
      .then(function(data) {{
        if (data && data.routes && data.routes.length > 0 && data.routes[0].geometry) {{
          var roadCoords = data.routes[0].geometry.coordinates.map(function(pt) {{
            return [pt[1], pt[0]];
          }});
          var roadKm = (data.routes[0].distance / 1000).toFixed(1);
          var roadKmNum = parseFloat(roadKm);
          var speedKmH = roadKmNum < 30 ? 32 : (roadKmNum < 100 ? 44 : 54);
          var durationMin = Math.round((roadKmNum / speedKmH) * 60);
          if (routeDistEl) {{
            var timeTxt = durationMin >= 60 ?
              Math.floor(durationMin / 60) + ' घंटा ' + (durationMin % 60) + ' मिनट' :
              durationMin + ' मिनट';
            var apxNote = (!isExact) ? ' <small style="color:#fde047">· जगह अनुमानित</small>' : '';
            routeDistEl.innerHTML = roadKm + ' किमी <small>· लगभग ' + timeTxt + ' (सड़क मार्ग)' + apxNote + '</small>';
          }}
          renderRoute(roadCoords, uLat, uLon, destLat, destLon, false);
        }} else {{
          var estRoadKm = (straightDist * 1.30).toFixed(1);
          var estSpeedKmH = straightDist < 30 ? 32 : (straightDist < 100 ? 44 : 54);
          var estMin = Math.round((parseFloat(estRoadKm) / estSpeedKmH) * 60);
          var estTimeTxt = estMin >= 60 ?
            Math.floor(estMin / 60) + ' घंटा ' + (estMin % 60) + ' मिनट' :
            estMin + ' मिनट';
          if (routeDistEl) {{
            routeDistEl.innerHTML = estRoadKm + ' किमी <small>· लगभग ' + estTimeTxt + ' (अनुमानित)</small>';
          }}
          renderRoute(fallbackCoords, uLat, uLon, destLat, destLon, true);
        }}
      }})
      .catch(function() {{
        var estRoadKm = (straightDist * 1.30).toFixed(1);
        if (routeDistEl) {{
          routeDistEl.textContent = estRoadKm + ' किमी (अनुमानित)';
        }}
        renderRoute(fallbackCoords, uLat, uLon, destLat, destLon, true);
      }});
  }}

  function showPathTo(idx) {{
    if (!markers || markers.length === 0) return;
    var targetMandi = null;
    var targetIdx = null;

    if (typeof idx === 'number' && markers[idx]) {{
      targetIdx = idx;
      targetMandi = markers[idx];
    }} else if (activeMandi && activeMandiIdx !== null) {{
      targetMandi = activeMandi;
      targetIdx = activeMandiIdx;
    }} else if (markers.length === 1) {{
      targetIdx = 0;
      targetMandi = markers[0];
    }} else if (userMarker) {{
      var p = userMarker.getLatLng();
      var nearest = null, nearDist = Infinity, nIdx = 0;
      markers.forEach(function(m, i) {{
        var d = haversineKm(p.lat, p.lng, m.lat, m.lon);
        if (d < nearDist) {{ nearDist = d; nearest = m; nIdx = i; }}
      }});
      targetMandi = nearest || markers[0];
      targetIdx = nIdx;
    }} else {{
      targetIdx = 0;
      targetMandi = markers[0];
    }}

    activeMandi = targetMandi;
    activeMandiIdx = targetIdx;

    var routeBtn = document.getElementById(mapId + '-btn-route');
    var popBtn = targetIdx !== null ? document.getElementById(mapId + '-pop-btn-' + targetIdx) : null;

    function _setRouteBtnLoading(isLoading) {{
      if (routeBtn) {{
        if (isLoading) {{
          routeBtn.classList.add('loading');
          routeBtn.innerHTML = '<svg class="bm-icon" style="animation:bmSpin 0.8s linear infinite" viewBox="0 0 24 24"><circle cx="12" cy="12" r="7"/><line x1="12" y1="2" x2="12" y2="5"/><line x1="12" y1="19" x2="12" y2="22"/><line x1="2" y1="12" x2="5" y2="12"/><line x1="19" y1="12" x2="22" y2="12"/></svg> खोज रहे हैं…';
        }} else {{
          routeBtn.classList.remove('loading');
          routeBtn.innerHTML = '<svg class="bm-icon bm-arrow-icon" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L4 20l8-4 8 4z"/></svg> रास्ता देखें';
        }}
      }}
    }}

    if (userMarker) {{
      var pos = userMarker.getLatLng();
      var d = haversineKm(pos.lat, pos.lng, activeMandi.lat, activeMandi.lon);
      findAndDrawShortestPath(pos.lat, pos.lng, activeMandi, d);
    }} else {{
      try {{
        var stored = JSON.parse(localStorage.getItem('km_geo') || 'null');
        if (stored && stored.lat && stored.lon && (Date.now() - (stored.ts || 0) < 7 * 86400000)) {{
          placeUserMarker(stored.lat, stored.lon);
          if (typeof idx !== 'number' && markers.length > 1) {{
            var nStored = null, nDistStored = Infinity, nIStored = 0;
            markers.forEach(function(m, i) {{
              var ds = haversineKm(stored.lat, stored.lon, m.lat, m.lon);
              if (ds < nDistStored) {{ nDistStored = ds; nStored = m; nIStored = i; }}
            }});
            if (nStored) {{
              activeMandi = nStored;
              activeMandiIdx = nIStored;
            }}
          }}
          var d2 = haversineKm(stored.lat, stored.lon, activeMandi.lat, activeMandi.lon);
          findAndDrawShortestPath(stored.lat, stored.lon, activeMandi, d2);
          return;
        }}
      }} catch (_) {{}}

      if (!navigator.geolocation) {{
        setPinMode(true, 'लोकेशन उपलब्ध नहीं — नक्शे पर अपनी जगह टैप करें');
        return;
      }}

      _setRouteBtnLoading(true);
      if (popBtn) {{
        popBtn.innerHTML = '<svg class="bm-icon" style="animation:bmSpin 0.8s linear infinite" viewBox="0 0 24 24"><circle cx="12" cy="12" r="7"/><line x1="12" y1="2" x2="12" y2="5"/><line x1="12" y1="19" x2="12" y2="22"/><line x1="2" y1="12" x2="5" y2="12"/><line x1="19" y1="12" x2="22" y2="12"/></svg> लोकेशन मिल रही है…';
      }}

      navigator.geolocation.getCurrentPosition(function(pos) {{
        _setRouteBtnLoading(false);
        var uLat = pos.coords.latitude;
        var uLon = pos.coords.longitude;
        try {{
          localStorage.setItem('km_geo', JSON.stringify({{
            status: 'granted',
            lat: +uLat.toFixed(5),
            lon: +uLon.toFixed(5),
            ts: Date.now()
          }}));
        }} catch (_) {{}}
        placeUserMarker(uLat, uLon);
        if (typeof idx !== 'number' && markers.length > 1) {{
          var nLive = null, nDistLive = Infinity, nILive = 0;
          markers.forEach(function(m, i) {{
            var dl = haversineKm(uLat, uLon, m.lat, m.lon);
            if (dl < nDistLive) {{ nDistLive = dl; nLive = m; nILive = i; }}
          }});
          if (nLive) {{
            activeMandi = nLive;
            activeMandiIdx = nILive;
          }}
        }}
        var d3 = haversineKm(uLat, uLon, activeMandi.lat, activeMandi.lon);
        setLocBtnBusy(false);
        findAndDrawShortestPath(uLat, uLon, activeMandi, d3);
      }}, function() {{
        _setRouteBtnLoading(false);
        if (popBtn) {{
          popBtn.innerHTML = '<svg class="bm-icon" viewBox="0 0 24 24"><path d="M12 2L4.5 20.29l.71.71L12 18l6.79 3 .71-.71z"/></svg> रास्ता देखें';
        }}
        setPinMode(true, 'लोकेशन नहीं मिली — नक्शे पर अपनी जगह टैप करें');
        setLocBtnBusy(false);
      }}, {{ enableHighAccuracy: false, timeout: 10000, maximumAge: 600000 }});
    }}
  }}
  window[jsId + '_showPathTo'] = showPathTo;
  window[mapId + '_showPathTo'] = showPathTo;

  function updateUserPos(lat, lon) {{
    var nearest = null;
    var nearestDist = Infinity;
    markers.forEach(function(m, i) {{
      var d = haversineKm(lat, lon, m.lat, m.lon);
      if (d < nearestDist) {{
        nearestDist = d;
        nearest = m;
      }}
      var distEl = document.getElementById(mapId + '-dist-' + i);
      if (distEl) {{
        distEl.textContent = (m.is_exact === false ? 'लगभग ' : '') + d.toFixed(1) + ' किमी दूर';
        distEl.style.display = 'inline-block';
      }}
    }});

    var targetMandi = activeMandi || nearest;
    var targetDist = activeMandi ? haversineKm(lat, lon, activeMandi.lat, activeMandi.lon) : nearestDist;
    if (targetMandi) {{
      findAndDrawShortestPath(lat, lon, targetMandi, targetDist);
    }}
  }}

  function setLocBtnBusy(on) {{
    var b = document.getElementById(mapId + '-btn-loc');
    if (!b) return;
    if (on) b.classList.add('loading');
    else b.classList.remove('loading');
    b.title = on ? 'लोकेशन खोजी जा रही है…' : 'मेरी लोकेशन खोजें';
  }}

  var getLocFn = function() {{
    if (!map) return;
    var locBtn = document.getElementById(mapId + '-btn-loc');
    setLocBtnBusy(true);

    function _handlePos(uLat, uLon) {{
      setLocBtnBusy(false);
      placeUserMarker(uLat, uLon);
      updateUserPos(uLat, uLon);
    }}

    try {{
      var stored = JSON.parse(localStorage.getItem('km_geo') || 'null');
      if (stored && stored.lat && stored.lon && (Date.now() - (stored.ts || 0) < 7 * 86400000)) {{
        setTimeout(function() {{ _handlePos(stored.lat, stored.lon); }}, 300);
        return;
      }}
    }} catch (_) {{}}

    if (!navigator.geolocation) {{
      setPinMode(true, 'लोकेशन उपलब्ध नहीं — नक्शे पर अपनी जगह टैप करें');
      setLocBtnBusy(false);
      return;
    }}

    navigator.geolocation.getCurrentPosition(function(pos) {{
      var uLat = pos.coords.latitude;
      var uLon = pos.coords.longitude;
      try {{
        localStorage.setItem('km_geo', JSON.stringify({{
          status: 'granted',
          lat: +uLat.toFixed(5),
          lon: +uLon.toFixed(5),
          ts: Date.now()
        }}));
      }} catch (_) {{}}
      _handlePos(uLat, uLon);
    }}, function(err) {{
      setLocBtnBusy(false);
    }}, {{ enableHighAccuracy: false, timeout: 10000, maximumAge: 600000 }});
  }};
  window[jsId + '_getLoc'] = getLocFn;
  window[mapId + '_getLoc'] = getLocFn;

  var toggleFsFn = function() {{
    var sec = document.getElementById(mapId + '-sec');
    if (!sec) return;
    var isFs = sec.classList.toggle('is-fullscreen');
    var fsIcon = document.getElementById(mapId + '-fs-icon');
    var fsBtn = document.getElementById(mapId + '-btn-fs');
    if (fsIcon) {{
      if (isFs) {{
        // The glyph is stroke-drawn via .bm-icon-stroke; plain <line>s over
        // the fill-only .bm-icon alone used to render an empty button.
        fsIcon.innerHTML = '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>';
        if (fsBtn) {{
          fsBtn.title = 'फुल स्क्रीन बंद करें (Esc)';
          fsBtn.setAttribute('aria-label', 'फुल स्क्रीन बंद करें');
        }}
      }} else {{
        fsIcon.innerHTML = '<polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/>';
        if (fsBtn) {{
          fsBtn.title = 'फुल स्क्रीन (Full Screen)';
          fsBtn.setAttribute('aria-label', 'फुल स्क्रीन');
        }}
      }}
    }}
    if (isFs) {{
      if (sec.requestFullscreen) {{
        sec.requestFullscreen().catch(function(){{}});
      }} else if (sec.webkitRequestFullscreen) {{
        sec.webkitRequestFullscreen();
      }}
    }} else {{
      if (document.fullscreenElement && document.exitFullscreen) {{
        document.exitFullscreen().catch(function(){{}});
      }} else if (document.webkitFullscreenElement && document.webkitExitFullscreen) {{
        document.webkitExitFullscreen();
      }}
    }}
    setTimeout(function() {{ if (map) map.invalidateSize(); }}, 180);
  }};
  window[jsId + '_toggleFs'] = toggleFsFn;
  window[mapId + '_toggleFs'] = toggleFsFn;

  var hideRouteFn = function() {{
    var rc = document.getElementById(mapId + '-route-card');
    if (rc) rc.style.display = 'none';
    var rb = document.getElementById(mapId + '-btn-route');
    if (rb) rb.style.display = 'inline-flex';
    if (routeGlowLayer && map) map.removeLayer(routeGlowLayer);
    if (routeLineLayer && map) map.removeLayer(routeLineLayer);
    if (routeFlowLayer && map) map.removeLayer(routeFlowLayer);
  }};
  window[jsId + '_hideRoute'] = hideRouteFn;
  window[mapId + '_hideRoute'] = hideRouteFn;

  var resetViewFn = function() {{
    if (!map) return;
    if (markerObjs.length > 1) {{
      var b = L.latLngBounds(markerObjs.map(function(m){{ return m.pos; }}));
      map.fitBounds(b, {{padding: [50, 50], maxZoom: 13}});
    }} else if (markerObjs.length === 1) {{
      map.setView(markerObjs[0].pos, 12);
    }} else {{
      map.setView(center, 11);
    }}
  }};
  window[jsId + '_resetView'] = resetViewFn;
  window[mapId + '_resetView'] = resetViewFn;

  function closeMapMenu() {{
    var m = document.getElementById(mapId + '-menu');
    if (m) m.hidden = true;
    var b = document.getElementById(mapId + '-btn-more');
    if (b) {{
      b.classList.remove('active');
      b.setAttribute('aria-expanded', 'false');
    }}
  }}

  var toggleMenuFn = function(ev) {{
    if (ev && ev.stopPropagation) ev.stopPropagation();
    var m = document.getElementById(mapId + '-menu');
    if (!m) return;
    var willOpen = !!m.hidden;
    m.hidden = !willOpen;
    var b = document.getElementById(mapId + '-btn-more');
    if (b) {{
      if (willOpen) b.classList.add('active');
      else b.classList.remove('active');
      b.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
    }}
  }};
  window[jsId + '_toggleMenu'] = toggleMenuFn;
  window[mapId + '_toggleMenu'] = toggleMenuFn;

  // Every item needs the map alive, and the map is lazy — so each one loads it
  // first instead of quietly doing nothing on a cold section.
  var menuActFn = function(what) {{
    closeMapMenu();
    if (typeof loadMapFn === 'function') loadMapFn();
    if (what === 'reset') resetViewFn();
    else if (what === 'hide') hideRouteFn();
    else if (what === 'pin') setPinMode(true, 'नक्शे पर अपनी जगह टैप करें');
  }};
  window[jsId + '_menuAct'] = menuActFn;
  window[mapId + '_menuAct'] = menuActFn;

  document.addEventListener('click', function(ev) {{
    var m = document.getElementById(mapId + '-menu');
    if (!m || m.hidden) return;
    if (m.contains(ev.target)) return;
    var b = document.getElementById(mapId + '-btn-more');
    if (b && b.contains(ev.target)) return;
    closeMapMenu();
  }});
  document.addEventListener('keydown', function(ev) {{
    if (ev.key === 'Escape' || ev.keyCode === 27) closeMapMenu();
  }});

  function handleFsExit() {{
    var sec = document.getElementById(mapId + '-sec');
    if (!sec) return;
    var isFsActive = !!(document.fullscreenElement || document.webkitFullscreenElement);
    if (!isFsActive && sec.classList.contains('is-fullscreen')) {{
      sec.classList.remove('is-fullscreen');
      var fsIcon = document.getElementById(mapId + '-fs-icon');
      var fsBtn = document.getElementById(mapId + '-btn-fs');
      if (fsIcon) {{
        fsIcon.innerHTML = '<polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/>';
      }}
      if (fsBtn) {{
        fsBtn.title = 'फुल स्क्रीन (Full Screen)';
        fsBtn.setAttribute('aria-label', 'फुल स्क्रीन');
      }}
      if (map) map.invalidateSize();
    }}
  }}
  document.addEventListener('fullscreenchange', handleFsExit);
  document.addEventListener('webkitfullscreenchange', handleFsExit);
  document.addEventListener('keydown', function(e) {{
    if (e.key === 'Escape' || e.key === 'Esc' || e.keyCode === 27) {{
      var sec = document.getElementById(mapId + '-sec');
      if (sec && sec.classList.contains('is-fullscreen')) {{
        toggleFsFn();
      }}
    }}
  }});

  var loadMapFn = function() {{
    ensureLeaflet().then(initMap);
  }};
  window['load_' + jsId] = loadMapFn;
  window['load_' + mapId] = loadMapFn;
  if (mapId === 'bhav-map') {{
    window.load_bhav_map = loadMapFn;
  }}

  window.scrollToBhavMap = function() {{
    loadMapFn();
    var sec = document.getElementById(mapId + '-sec') || document.getElementById('bhav-map-sec') || document.getElementById('bhav-hub-map-sec');
    if (sec) {{
      sec.scrollIntoView({{behavior: 'smooth', block: 'start'}});
    }}
  }};

  function setupObserver() {{
    var sec = document.getElementById(mapId + '-sec');
    if (!sec) return;
    if ('IntersectionObserver' in window) {{
      var obs = new IntersectionObserver(function(entries) {{
        if (entries[0].isIntersecting) {{
          obs.disconnect();
          loadMapFn();
        }}
      }}, {{rootMargin: '350px'}});
      obs.observe(sec);
    }} else {{
      loadMapFn();
    }}
  }}

  if (document.readyState === 'loading') {{
    document.addEventListener('DOMContentLoaded', setupObserver);
  }} else {{
    setupObserver();
  }}
}})();
</script>"""


def _mandi_nav_query(market: str, district: str, state: str) -> str:
    parts = [(market or "").strip(), (district or "").strip(), (state or "").strip()]
    label = ", ".join(x for x in parts if x)
    return f"{label} mandi" if label else ""


def _markers_script_json(markers: list) -> str:
    return (_json.dumps(markers, ensure_ascii=False)
            .replace('<', '\\u003c').replace('>', '\\u003e'))


def _mandi_satellite_map_html(state: str, district: str, prices: list,
                              commodity: str, crop_hi: str, s_slug: str,
                              d_slug: str, d_hi: str) -> str:
    by_market = {}
    for p in prices:
        mkt = (p.get("market") or "").strip()
        if not mkt or mkt == "-":
            continue
        cur = by_market.get(mkt)
        p_modal = _num(p.get("modal_price"))
        if cur is None or (p_modal and p_modal > _num(cur.get("modal_price"))):
            by_market[mkt] = p

    if not by_market:
        return ""

    top_price = 0
    for p in by_market.values():
        m_val = _num(p.get("modal_price"))
        if m_val and m_val > top_price:
            top_price = m_val

    markers = []
    for mkt, p in by_market.items():
        coords = district_geo.resolve_mandi_coords(state, district, mkt)
        if not coords:
            continue
        lat, lon, is_exact = coords
        modal_val = _num(p.get("modal_price"))
        min_val = _num(p.get("min_price"))
        max_val = _num(p.get("max_price"))
        dt = p.get("date") or ""
        is_top = bool(modal_val and modal_val >= top_price and top_price > 0)

        clean_name = re.sub(r'(?i)\b(apmc|mandi|grain market|sub yard|upaj mandi|sub market yard|market yard|main yard|yard)\b', '', mkt).strip()
        clean_name = re.sub(r'[\(\)\[\]\-]+', ' ', clean_name).strip() or mkt

        markers.append({
            "market": mkt,
            "name": clean_name,
            "lat": lat,
            "lon": lon,
            "is_exact": is_exact,
            "nav_q": _mandi_nav_query(mkt, district, state),
            "price": f"₹{modal_val:,}" if modal_val else "—",
            "price_num": modal_val or 0,
            "min_price": f"₹{min_val:,}" if min_val else "—",
            "max_price": f"₹{max_val:,}" if max_val else "—",
            "variety": p.get("variety") or "",
            "date": _hindi_data_date(dt) if dt else "",
            "is_top": is_top,
        })

    if not markers:
        return ""

    map_id = "bhav-map"
    js_id = map_id.replace('-', '_')
    center_lat = round(sum(m["lat"] for m in markers) / len(markers), 5)
    center_lon = round(sum(m["lon"] for m in markers) / len(markers), 5)
    markers_json = _markers_script_json(markers)

    mandi_cnt = len(markers)
    cnt_txt = f"{mandi_cnt} मंडी दर्ज" if mandi_cnt == 1 else f"{mandi_cnt} मंडियां दर्ज"
    naksha_link = f"/naksha/{quote(s_slug)}/{quote(d_slug)}" if s_slug and d_slug else "/naksha"

    html = f"""<section class="bhav-map-sec" id="{map_id}-sec">
  <div class="bhav-map-head">
    <div class="bhav-map-head-left">
      <h2>{escape(d_hi)} मंडी उपग्रह नक्शा (Satellite View)</h2>
      <span class="bhav-map-pill">{cnt_txt}</span>
    </div>
    <div class="bhav-map-sub-note">उपग्रह चित्र पर मंडी यार्ड देखें और रास्ता निकालें</div>
  </div>
  <div class="bhav-map-wrap">
    <div class="bhav-map-skel" id="{map_id}-skel" onclick="if(window['load_{js_id}'])window['load_{js_id}']();">
      <svg class="bhav-map-skel-icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 3v18M3 12h18M12 12l6-6"/></svg>
      <span class="bhav-map-skel-txt">उपग्रह नक्शा लोड हो रहा है…</span>
      <span class="bhav-map-skel-sub">नक्शा देखने के लिए क्लिक करें</span>
    </div>
    <div class="bhav-map-ctrls">
      <div class="bhav-map-ctrls-left">
        <div class="bhav-map-btn-group">
          <button type="button" class="bhav-map-tab active" id="{map_id}-tab-sat" onclick="{js_id}_setLayer('sat')">
            <svg class="bm-tab-svg" viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M13 7 9 3 5 7l4 4"/><path d="m17 11 4 4-4 4-4-4"/><path d="m8 12 4 4 6-6-4-4Z"/><path d="m16 8 3-3"/><path d="M9 21a6 6 0 0 0-6-6"/></svg>
            <span class="bhav-tab-txt">सैटेलाइट<br>(Satellite)</span>
          </button>
          <button type="button" class="bhav-map-tab" id="{map_id}-tab-osm" onclick="{js_id}_setLayer('osm')">
            <svg class="bm-tab-svg" viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14.1 5.55a2 2 0 0 0 1.79 0l3.66-1.83A1 1 0 0 1 21 4.62v12.76a1 1 0 0 1-.55.9l-4.56 2.27a2 2 0 0 1-1.79 0L9.9 18.45a2 2 0 0 0-1.79 0l-3.66 1.83A1 1 0 0 1 3 19.38V6.62a1 1 0 0 1 .55-.9L8.1 3.45a2 2 0 0 1 1.79 0z"/><path d="M15 5.76v15"/><path d="M9 3.24v15"/></svg>
            <span class="bhav-tab-txt">नक्शा<br>(Roads)</span>
          </button>
        </div>
      </div>
      <div class="bhav-map-ctrls-right">
        <div class="bhav-map-v-stack">
          <div class="bhav-map-v-row">
            <a href="{naksha_link}" target="_blank" rel="noopener" class="bhav-map-btn bhav-map-btn-naksha">
              <svg class="bm-icon" viewBox="0 0 24 24"><path d="M19 19H5V5h7V3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7h-2v7zM14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3h-7z"/></svg>
              पूरा नक्शा देखें
            </a>
            <button type="button" class="bhav-map-btn bhav-map-btn-icon" id="{map_id}-btn-fs" onclick="{js_id}_toggleFs()" title="फुल स्क्रीन (Full Screen)" aria-label="फुल स्क्रीन">
              <svg class="bm-icon bm-icon-stroke" id="{map_id}-fs-icon" viewBox="0 0 24 24"><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/></svg>
            </button>
          </div>
          <div class="bhav-map-more-wrap">
            <button type="button" class="bhav-map-btn bhav-map-btn-icon" id="{map_id}-btn-more" onclick="{js_id}_toggleMenu(event)" title="और विकल्प" aria-label="और विकल्प" aria-haspopup="true" aria-expanded="false">
              <svg class="bm-icon bm-icon-stroke" viewBox="0 0 24 24"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>
            </button>
            <div class="bhav-map-menu" id="{map_id}-menu" role="menu" hidden>
              <button type="button" role="menuitem" onclick="{js_id}_menuAct('reset')">
                <svg class="bm-icon" viewBox="0 0 24 24"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5A2.5 2.5 0 1 1 12 6.5a2.5 2.5 0 0 1 0 5z"/></svg>
                सभी मंडी दिखाएँ
              </button>
              <button type="button" role="menuitem" onclick="{js_id}_menuAct('pin')">
                <svg class="bm-icon" viewBox="0 0 24 24"><path d="M20.5 3 3.5 10.5l7 2.9 2.9 7L20.5 3z"/></svg>
                नक्शे पर अपनी जगह चुनें
              </button>
              <button type="button" role="menuitem" onclick="{js_id}_menuAct('hide')">
                <svg class="bm-icon" viewBox="0 0 24 24"><path d="M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
                रास्ता हटाएँ
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
    <button type="button" class="bhav-map-btn bhav-map-btn-route" id="{map_id}-btn-route" onclick="{js_id}_showPathTo()" title="मंडी का रास्ता देखें" aria-label="रास्ता देखें">
      <svg class="bm-icon" viewBox="0 0 24 24"><path d="M12 2L4.5 20.29l.71.71L12 18l6.79 3 .71-.71z"/></svg>
      रास्ता देखें
    </button>
    <button type="button" class="bhav-map-btn bhav-map-btn-icon bhav-map-btn-loc" id="{map_id}-btn-loc" onclick="{js_id}_getLoc()" title="मेरी लोकेशन खोजें" aria-label="मेरी लोकेशन">
      <svg class="bm-icon" viewBox="0 0 24 24"><path d="M12 8c-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4-1.79-4-4-4zm8.94 3A8.994 8.994 0 0 0 13 3.06V1h-2v2.06A8.994 8.994 0 0 0 3.06 11H1v2h2.06A8.994 8.994 0 0 0 11 20.94V23h2v-2.06A8.994 8.994 0 0 0 20.94 13H23v-2h-2.06zM12 19c-3.87 0-7-3.13-7-7s3.13-7 7-7 7 3.13 7 7-3.13 7-7 7z"/></svg>
    </button>
    <div id="{map_id}-route-card" class="bhav-map-route-card" style="display:none;">
      <div class="bhav-route-main">
        <svg class="bm-icon" viewBox="0 0 24 24"><path d="M12 2L4.5 20.29l.71.71L12 18l6.79 3 .71-.71z"/></svg>
        <div class="bhav-route-info">
          <span class="bhav-route-title"><span id="{map_id}-route-label">नजदीकी मंडी</span>: <b id="{map_id}-route-mandi">—</b></span>
          <span class="bhav-route-meta">दूरी: <b id="{map_id}-route-dist">—</b></span>
        </div>
      </div>
      <a id="{map_id}-route-nav" href="#" target="_blank" rel="noopener" class="bhav-route-nav-btn" title="गूगल मैप पर रास्ता देखें">
        <svg class="bm-icon" viewBox="0 0 24 24"><path d="M12 2L4.5 20.29l.71.71L12 18l6.79 3 .71-.71z"/></svg>
        गूगल मैप पर देखें
      </a>
      <button type="button" class="bhav-route-close-btn" onclick="{js_id}_hideRoute()" title="रास्ता हटाएँ" aria-label="रास्ता हटाएँ">
        <svg class="bm-icon" viewBox="0 0 24 24"><path d="M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
      </button>
    </div>
    <div id="{map_id}-canvas" class="bhav-map-canvas"></div>
  </div>
</section>
{_bhav_map_script(map_id, markers_json, center_lat, center_lon)}"""
    return html


def _mandis_in_district(state_name: str, dist_name: str) -> list[dict]:
    db = SessionLocal()
    try:
        rows = (db.query(MandiPrice.market, MandiPrice.commodity, MandiPrice.modal_price)
                .filter(MandiPrice.state.ilike(state_name))
                .filter(MandiPrice.district.ilike(dist_name))
                .all())
    finally:
        db.close()

    by_mkt: dict = {}
    for mkt, com, modal in rows:
        mkt = (mkt or "").strip()
        if not mkt or mkt == "-":
            continue
        slot = by_mkt.setdefault(mkt, {"crops": set(), "modals": []})
        if com and _is_crop(com):
            slot["crops"].add(com)
        m = _num(modal)
        if m:
            slot["modals"].append(m)

    out = []
    for mkt, v in by_mkt.items():
        coords = district_geo.resolve_mandi_coords(state_name, dist_name, mkt)
        if not coords:
            continue
        lat, lon, is_exact = coords
        clean_name = re.sub(r'(?i)\b(apmc|mandi|grain market|sub yard|upaj mandi|sub market yard|market yard|main yard|yard)\b', '', mkt).strip()
        clean_name = re.sub(r'[\(\)\[\]\-]+', ' ', clean_name).strip() or mkt
        crop_count = len(v["crops"])

        out.append({
            "market": mkt,
            "name": clean_name,
            "lat": lat,
            "lon": lon,
            "is_exact": is_exact,
            "crop_count": crop_count,
            "price": f"{crop_count} फसलें" if crop_count else "सक्रिय मंडी",
            "price_num": crop_count,
            "min_price": "—",
            "max_price": "—",
            "date": "",
            "is_top": False,
        })
    return out


def _district_hub_satellite_map_html(state: str, district: str,
                                     s_slug: str, d_slug: str, d_hi: str) -> str:
    markers = _mandis_in_district(state, district)
    if not markers:
        coords = district_geo.coord_for(state, district)
        if not coords:
            return ""
        markers = [{
            "market": f"{d_hi} मंडी",
            "name": d_hi,
            "lat": coords[0],
            "lon": coords[1],
            "is_exact": False,
            "crop_count": 0,
            "price": "सक्रिय मंडी",
            "price_num": 0,
            "min_price": "—",
            "max_price": "—",
            "date": "",
            "is_top": False,
        }]

    map_id = "bhav-hub-map"
    js_id = map_id.replace('-', '_')
    center_lat = round(sum(m["lat"] for m in markers) / len(markers), 5)
    center_lon = round(sum(m["lon"] for m in markers) / len(markers), 5)
    markers_json = _markers_script_json(markers)

    mandi_cnt = len(markers)
    cnt_txt = f"{mandi_cnt} मंडी दर्ज" if mandi_cnt == 1 else f"{mandi_cnt} मंडियां दर्ज"
    naksha_link = f"/naksha/{quote(s_slug)}/{quote(d_slug)}" if s_slug and d_slug else "/naksha"

    html = f"""<section class="bhav-map-sec" id="{map_id}-sec">
  <div class="bhav-map-head">
    <div class="bhav-map-head-left">
      <h2>{escape(d_hi)} जिले की मंडियां — उपग्रह नक्शा (Satellite View)</h2>
      <span class="bhav-map-pill">{cnt_txt}</span>
    </div>
    <div class="bhav-map-sub-note">उपग्रह चित्र पर मंडी यार्ड देखें और रास्ता निकालें</div>
  </div>
  <div class="bhav-map-wrap">
    <div class="bhav-map-skel" id="{map_id}-skel" onclick="if(window['load_{js_id}'])window['load_{js_id}']();">
      <svg class="bhav-map-skel-icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 3v18M3 12h18M12 12l6-6"/></svg>
      <span class="bhav-map-skel-txt">उपग्रह नक्शा लोड हो रहा है…</span>
      <span class="bhav-map-skel-sub">नक्शा देखने के लिए क्लिक करें</span>
    </div>
    <div class="bhav-map-ctrls">
      <div class="bhav-map-ctrls-left">
        <div class="bhav-map-btn-group">
          <button type="button" class="bhav-map-tab active" id="{map_id}-tab-sat" onclick="{js_id}_setLayer('sat')">
            <svg class="bm-tab-svg" viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M13 7 9 3 5 7l4 4"/><path d="m17 11 4 4-4 4-4-4"/><path d="m8 12 4 4 6-6-4-4Z"/><path d="m16 8 3-3"/><path d="M9 21a6 6 0 0 0-6-6"/></svg>
            <span class="bhav-tab-txt">सैटेलाइट<br>(Satellite)</span>
          </button>
          <button type="button" class="bhav-map-tab" id="{map_id}-tab-osm" onclick="{js_id}_setLayer('osm')">
            <svg class="bm-tab-svg" viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14.1 5.55a2 2 0 0 0 1.79 0l3.66-1.83A1 1 0 0 1 21 4.62v12.76a1 1 0 0 1-.55.9l-4.56 2.27a2 2 0 0 1-1.79 0L9.9 18.45a2 2 0 0 0-1.79 0l-3.66 1.83A1 1 0 0 1 3 19.38V6.62a1 1 0 0 1 .55-.9L8.1 3.45a2 2 0 0 1 1.79 0z"/><path d="M15 5.76v15"/><path d="M9 3.24v15"/></svg>
            <span class="bhav-tab-txt">नक्शा<br>(Roads)</span>
          </button>
        </div>
      </div>
      <div class="bhav-map-ctrls-right">
        <div class="bhav-map-v-stack">
          <div class="bhav-map-v-row">
            <a href="{naksha_link}" target="_blank" rel="noopener" class="bhav-map-btn bhav-map-btn-naksha">
              <svg class="bm-icon" viewBox="0 0 24 24"><path d="M19 19H5V5h7V3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7h-2v7zM14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3h-7z"/></svg>
              पूरा नक्शा देखें
            </a>
            <button type="button" class="bhav-map-btn bhav-map-btn-icon" id="{map_id}-btn-fs" onclick="{js_id}_toggleFs()" title="फुल स्क्रीन (Full Screen)" aria-label="फुल स्क्रीन">
              <svg class="bm-icon bm-icon-stroke" id="{map_id}-fs-icon" viewBox="0 0 24 24"><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/></svg>
            </button>
          </div>
          <div class="bhav-map-more-wrap">
            <button type="button" class="bhav-map-btn bhav-map-btn-icon" id="{map_id}-btn-more" onclick="{js_id}_toggleMenu(event)" title="और विकल्प" aria-label="और विकल्प" aria-haspopup="true" aria-expanded="false">
              <svg class="bm-icon bm-icon-stroke" viewBox="0 0 24 24"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>
            </button>
            <div class="bhav-map-menu" id="{map_id}-menu" role="menu" hidden>
              <button type="button" role="menuitem" onclick="{js_id}_menuAct('reset')">
                <svg class="bm-icon" viewBox="0 0 24 24"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5A2.5 2.5 0 1 1 12 6.5a2.5 2.5 0 0 1 0 5z"/></svg>
                सभी मंडी दिखाएँ
              </button>
              <button type="button" role="menuitem" onclick="{js_id}_menuAct('pin')">
                <svg class="bm-icon" viewBox="0 0 24 24"><path d="M20.5 3 3.5 10.5l7 2.9 2.9 7L20.5 3z"/></svg>
                नक्शे पर अपनी जगह चुनें
              </button>
              <button type="button" role="menuitem" onclick="{js_id}_menuAct('hide')">
                <svg class="bm-icon" viewBox="0 0 24 24"><path d="M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
                रास्ता हटाएँ
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
    <button type="button" class="bhav-map-btn bhav-map-btn-route" id="{map_id}-btn-route" onclick="{js_id}_showPathTo()" title="मंडी का रास्ता देखें" aria-label="रास्ता देखें">
      <svg class="bm-icon" viewBox="0 0 24 24"><path d="M12 2L4.5 20.29l.71.71L12 18l6.79 3 .71-.71z"/></svg>
      रास्ता देखें
    </button>
    <button type="button" class="bhav-map-btn bhav-map-btn-icon bhav-map-btn-loc" id="{map_id}-btn-loc" onclick="{js_id}_getLoc()" title="मेरी लोकेशन खोजें" aria-label="मेरी लोकेशन">
      <svg class="bm-icon" viewBox="0 0 24 24"><path d="M12 8c-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4-1.79-4-4-4zm8.94 3A8.994 8.994 0 0 0 13 3.06V1h-2v2.06A8.994 8.994 0 0 0 3.06 11H1v2h2.06A8.994 8.994 0 0 0 11 20.94V23h2v-2.06A8.994 8.994 0 0 0 20.94 13H23v-2h-2.06zM12 19c-3.87 0-7-3.13-7-7s3.13-7 7-7 7 3.13 7 7-3.13 7-7 7z"/></svg>
    </button>
    <div id="{map_id}-route-card" class="bhav-map-route-card" style="display:none;">
      <div class="bhav-route-main">
        <svg class="bm-icon" viewBox="0 0 24 24"><path d="M12 2L4.5 20.29l.71.71L12 18l6.79 3 .71-.71z"/></svg>
        <div class="bhav-route-info">
          <span class="bhav-route-title"><span id="{map_id}-route-label">नजदीकी मंडी</span>: <b id="{map_id}-route-mandi">—</b></span>
          <span class="bhav-route-meta">दूरी: <b id="{map_id}-route-dist">—</b></span>
        </div>
      </div>
      <a id="{map_id}-route-nav" href="#" target="_blank" rel="noopener" class="bhav-route-nav-btn" title="गूगल मैप पर रास्ता देखें">
        <svg class="bm-icon" viewBox="0 0 24 24"><path d="M12 2L4.5 20.29l.71.71L12 18l6.79 3 .71-.71z"/></svg>
        गूगल मैप पर देखें
      </a>
      <button type="button" class="bhav-route-close-btn" onclick="{js_id}_hideRoute()" title="रास्ता हटाएँ" aria-label="रास्ता हटाएँ">
        <svg class="bm-icon" viewBox="0 0 24 24"><path d="M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
      </button>
    </div>
    <div id="{map_id}-canvas" class="bhav-map-canvas"></div>
  </div>
</section>
{_bhav_map_script(map_id, markers_json, center_lat, center_lon)}"""
    return html


@router.get("/bhav/api/hub-rest")
def _api_hub_rest():
    """Lazy: long-tail crop chips for the main /bhav page."""
    idx = _get_index()
    crops = {cs: cn for cs, cn in idx.get("crops", {}).items() if _is_crop(cn)}
    featured, seen_tiles = [], {}
    for cs, cn in crops.items():
        rank = _tile_rank(cn)
        if rank >= _STAPLE_TILES_N:
            continue
        n = len(idx["states"].get(cs, {}))
        if rank not in seen_tiles or n > seen_tiles[rank][2]:
            seen_tiles[rank] = (cs, cn, n)
    featured_slugs = {cs for cs, _, _ in [seen_tiles[r] for r in sorted(seen_tiles)]}
    rest = sorted(((cs, cn) for cs, cn in crops.items() if cs not in featured_slugs),
                  key=lambda kv: _hindi_name(kv[1]))
    if not rest:
        return JSONResponse({"ok": True, "html": '<div id="bhav-crop-tail"></div>'})
    chips = "".join(_crop_chip(f"/bhav/{cs}", _hindi_name(cn), cn) for cs, cn in rest)
    html = f'<div id="bhav-crop-tail"><h2>अन्य फसलें ({len(rest)})</h2><div class="chips">{chips}</div></div>'
    return JSONResponse({"ok": True, "html": html},
                        headers={"Cache-Control": "public, max-age=3600",
                                 "CDN-Cache-Control": "public, max-age=86400"})


@router.get("/bhav/api/hub-states")
def _api_hub_states():
    """Lazy: state map cards for the main /bhav page."""
    idx = _get_index()
    state_names, state_crops = {}, {}
    for c, smap in idx["states"].items():
        if not _is_crop(idx["crops"].get(c, "")):
            continue
        for s, sname in smap.items():
            state_names.setdefault(s, sname)
            state_crops.setdefault(s, set()).add(c)
    state_cards = "".join(
        _state_card(f"/bhav/rajya/{s}", state_names[s], len(state_crops[s]), "फसलें")
        for s in sorted(state_names, key=lambda s: state_names[s]))
    html = f'<div class="place-grid" id="bhav-state-grid">{state_cards}</div>'
    return JSONResponse({"ok": True, "html": html},
                        headers={"Cache-Control": "public, max-age=3600",
                                 "CDN-Cache-Control": "public, max-age=86400"})


@router.get("/bhav/api/places")
def _api_places():
    """{state: [district, …]} — the place names this site actually knows.

    Serves the Krashi Bazar composer's राज्य / ज़िला pickers. It reads the same
    cached mandi index every /bhav page is built from, so a district a farmer
    picks for his listing is spelled exactly the way bazar.place_posts() will
    later look for it. A hand-maintained list would be a second spelling of
    ~700 district names, and the one that drifts is the one that silently drops
    his listing off the district page it was collected for.

    Unioned across crops: the pickers ask "where is he", not "where is this
    crop traded", and a farmer whose district only trades one commodity still
    has to be able to name it.
    """
    idx = _get_index()
    places: dict = {}
    for cs, smap in idx.get("states", {}).items():
        for ss, sname in smap.items():
            places.setdefault(sname, set()).update(
                idx.get("dists", {}).get(cs, {}).get(ss, {}).values())
    # Pairs, not objects: ~700 districts × a {"n": …, "hi": …} wrapper is a few
    # KB of punctuation on a page a farmer opens on a 2G phone. Each entry is
    # [what we store, what he reads] — the English name is the one the district
    # page is keyed on, and the Hindi one exists because a form that asks a
    # Hindi reader to find "Muzaffarnagar" in a list of 75 is a form he closes.
    out = [{"n": sname, "hi": _hindi_state(sname),
            "d": [[d, _hindi_district(sname, d)] for d in sorted(dists)]}
           for sname, dists in sorted(places.items()) if dists]
    return JSONResponse(
        {"ok": True, "places": out},
        headers={"Cache-Control": "public, max-age=3600",
                 "CDN-Cache-Control": "public, max-age=86400"})


@router.get("/bhav/api/tier2-extras/{c_slug}")
def _api_tier2_extras(c_slug: str):
    """Lazy: best mandi nationwide + stats + answer_lead for tier 2."""
    idx = _get_index()
    cs = c_slug.lower()
    commodity = idx.get("crops", {}).get(cs)
    if not commodity:
        return JSONResponse({"ok": False})

    hi = _hindi_name(commodity)
    today_hi = _hindi_date(date.today())
    state_map = idx["states"].get(cs, {})

    rows = _rows_for(commodity)
    st = _stats(rows)

    # Best mandi nationwide
    best = max((r for r in rows if _num(r.get("modal_price"))),
               key=lambda r: _num(r["modal_price"]), default=None)
    best_html = ""
    if best:
        b_state = best.get("state", "")
        b_dist = best.get("district", "")
        best_html = (f'<section class="better" id="km-near-panel" data-crop="{cs}">'
            f'<h2>🏆 आज देश में सबसे ज्यादा {escape(hi)} भाव</h2>'
            f'<p class="better-sub">आज के मॉडल भाव के आधार पर</p>'
            f'<ul><li><a class="better-mandi-card" href="/bhav/{cs}/{_slugify(b_state)}/{_slugify(b_dist)}">'
            f'<div class="bmc-details"><span class="bmc-market">{escape(best.get("market","-"))}</span>'
            f'<span class="bmc-meta">{escape(b_dist)}, {escape(_hindi_state(b_state))}</span></div>'
            f'<span class="bmc-action">भाव देखें →</span></a></li></ul></section>')

    # Answer lead
    lead_avg = f" — देशभर का औसत मॉडल भाव ₹{st['avg']:,} प्रति क्विंटल" if st["avg"] else ""
    lead_best = (f" आज सबसे ऊंचा भाव {escape(best.get('market', '-'))} "
                 f"({escape(best.get('district', '-'))}, {escape(_hindi_state(best.get('state', '')))}) "
                 f"मंडी में दर्ज हुआ।" if best else "")
    answer_lead = (f'<p class="lead-out">{today_hi} को {escape(hi)} ({escape(commodity)}) का भाव देश के '
                   f'{len(state_map)} राज्यों की {_mandis_gen(st["n"])} से भारत सरकार के Agmarknet '
                   f'(data.gov.in) पोर्टल पर दर्ज हुआ{lead_avg}।{lead_best}</p>')

    html = best_html + answer_lead
    return JSONResponse({"ok": True, "html": html},
                        headers={"Cache-Control": "public, max-age=300",
                                 "CDN-Cache-Control": "public, max-age=600"})


@router.get("/bhav/api/tier3-extras/{c_slug}/{s_slug}")
def _api_tier3_extras(c_slug: str, s_slug: str):
    """Lazy: top mandis + stats + answer_lead for tier 3."""
    idx = _get_index()
    cs, ss = c_slug.lower(), s_slug.lower()
    commodity = idx.get("crops", {}).get(cs)
    state = idx.get("states", {}).get(cs, {}).get(ss)
    if not (commodity and state):
        return JSONResponse({"ok": False})

    hi, hi_state = _hindi_name(commodity), _hindi_state(state)
    today_hi = _hindi_date(date.today())
    dist_map = idx["dists"].get(cs, {}).get(ss, {})

    rows = _rows_for(commodity, state=state)
    st = _stats(rows)

    # Top-paying mandis
    priced = [r for r in rows if _num(r.get("modal_price"))]
    top = sorted(priced, key=lambda r: _num(r["modal_price"]), reverse=True)[:5]
    top_html = ""
    if top:
        items = "".join(
            f'<li><a class="better-mandi-card" href="/bhav/{cs}/{ss}/{_slugify(r.get("district",""))}">'
            f'<div class="bmc-details"><span class="bmc-market">{escape(r.get("market","-"))}</span>'
            f'<span class="bmc-meta">{escape(r.get("district","-"))}</span></div>'
            f'<span class="bmc-action">भाव देखें →</span></a></li>'
            for r in top)
        low = min(priced, key=lambda r: _num(r["modal_price"]))
        low_html = ""
        if _num(low["modal_price"]) < _num(top[0]["modal_price"]):
            low_html = (
                '<div class="better-low">'
                f'<p class="better-low-h">📉 आज सबसे कम {escape(hi)} भाव इस मंडी में</p>'
                f'<a class="better-mandi-card low" href="/bhav/{cs}/{ss}/{_slugify(low.get("district",""))}">'
                '<div class="bmc-details">'
                f'<span class="bmc-market">{escape(low.get("market","-"))}</span>'
                f'<span class="bmc-meta">{escape(low.get("district","-"))}</span>'
                '</div><span class="bmc-action">भाव देखें →</span></a></div>')
        top_html = (f'<section class="better" id="km-near-panel" data-crop="{cs}" data-state="{ss}">'
                    f'<h2>🏆 {escape(hi_state)} में आज सबसे ज्यादा {escape(hi)} भाव</h2>'
                    f'<p class="better-sub">भेजने से पहले मंडी की दूरी और भाड़ा ज़रूर जोड़ें</p>'
                    f'<ul>{items}</ul>{low_html}</section>')

    # Answer lead
    lead_avg = f" — राज्य का औसत मॉडल भाव ₹{st['avg']:,} प्रति क्विंटल" if st["avg"] else ""
    answer_lead = (f'<p class="lead-out">{today_hi} को {escape(hi_state)} के {len(dist_map)} जिलों की '
                   f'{_mandis_gen(st["n"])} में {escape(hi)} का भाव सरकारी रिपोर्ट (भारत सरकार का Agmarknet '
                   f'पोर्टल) में दर्ज हुआ{lead_avg}। नीचे अपना जिला चुनकर मंडीवार पूरा भाव देखें।</p>')

    html = top_html + answer_lead
    return JSONResponse({"ok": True, "html": html},
                        headers={"Cache-Control": "public, max-age=300",
                                 "CDN-Cache-Control": "public, max-age=600"})


@router.get("/bhav/api/tier4-extras/{c_slug}/{s_slug}/{d_slug}")
def _api_tier4_extras(c_slug: str, s_slug: str, d_slug: str):
    """Lazy: comparison panel for tier 4 (the #1 cause of 504s)."""
    idx = _get_index()
    cs, ss, ds = c_slug.lower(), s_slug.lower(), d_slug.lower()
    commodity = idx.get("crops", {}).get(cs)
    state = idx.get("states", {}).get(cs, {}).get(ss)
    district = idx.get("dists", {}).get(cs, {}).get(ss, {}).get(ds)
    if not (commodity and state and district):
        return JSONResponse({"ok": False})

    hi, hi_state = _hindi_name(commodity), _hindi_state(state)

    rows = _rows_for(commodity, state=state)
    st = _stats(rows)
    med = _median_by(rows, "district")
    here = med.get(district) or st["avg"]
    better_html = ""
    if here:
        others = sorted(((dn, m - here) for dn, m in med.items() if dn != district),
                        key=lambda x: x[1], reverse=True)
        highers = [(dn, d) for dn, d in others if d > 0][:5]
        lowers = [(dn, d) for dn, d in others if d < 0][-3:][::-1]

        def _cmp_card(dn: str, diff: int, low: bool = False) -> str:
            arrow, sign, cls = ("▼", "−", "dn") if low else ("▲", "+", "up")
            return (
                f'<li><a class="better-mandi-card{" low" if low else ""}" '
                f'href="/bhav/{cs}/{ss}/{_slugify(dn)}">'
                f'<div class="bmc-details">'
                f'<span class="bmc-market">{escape(dn)}</span>'
                f'<span class="bmc-meta">{escape(hi_state)}</span>'
                f'</div><span class="bmc-action">'
                f'<span class="bmc-delta {cls}">{arrow} {sign}₹{abs(diff):,}</span> '
                f'<small>देखें →</small></span></a></li>')

        if highers or lowers:
            hi_block = (f'<ul>{"".join(_cmp_card(dn, d) for dn, d in highers)}</ul>' if highers
                        else f'<p class="better-message">🏆 {escape(hi_state)} के किसी और जिले में '
                             f'{escape(hi)} का इससे ज्यादा भाव नहीं मिल रहा — यहां भाव सबसे ऊंचा है।</p>')
            lo_block = (f'<div class="better-low"><p class="better-low-h">'
                        f'📉 इन जिलों में {escape(hi)} का भाव कम है</p>'
                        f'<ul>{"".join(_cmp_card(dn, d, low=True) for dn, d in lowers)}</ul></div>'
                        if lowers else "")
            better_html = (f'<section class="better">'
                f'<h2>📊 {escape(hi_state)} के अन्य जिलों में {escape(hi)} का भाव — तुलना</h2>'
                f'<p class="better-sub">{escape(district)} के भाव ₹{here:,}/क्विंटल से तुलना · '
                f'भेजने से पहले मंडी की दूरी और भाड़ा ज़रूर जोड़ें</p>'
                f'{hi_block}{lo_block}</section>')

    return JSONResponse({"ok": True, "html": better_html or ""},
                        headers={"Cache-Control": "public, max-age=300",
                                 "CDN-Cache-Control": "public, max-age=600"})


# ── seasonality (पिछले साल इसी समय / कब बेचें) ────────────────

def _season_chart(by_month: dict, now_m: int, best_m: int, worst_m: int) -> str:
    """12-bar calendar of the multi-year median, current month highlighted.

    A line chart would imply a continuous series; this is twelve independent
    medians, so bars are the honest form. Values are labelled only on the
    peak, the trough and the current month — labelling all twelve turns the
    chart into a wall of numbers on a 390px screen.
    """
    if len(by_month) < 6:
        return ""
    w, h = 600, 190
    pad_l, pad_r, pad_t, pad_b = 10, 10, 26, 34
    plot_h = h - pad_t - pad_b
    hi = max(by_month.values())
    lo = min(by_month.values())
    # Baseline at 80% of the trough so short bars still read as bars, not slivers.
    base = lo * 0.8 or 1
    span = (hi - base) or 1
    slot = (w - pad_l - pad_r) / 12
    bw   = slot * 0.62

    bars = []
    for m in range(1, 13):
        v = by_month.get(m)
        cx = pad_l + (m - 0.5) * slot
        if not v:
            bars.append(f'<text x="{cx:.1f}" y="{pad_t + plot_h - 4:.1f}" font-size="9" '
                        f'fill="#c9d0cb" text-anchor="middle">·</text>')
            continue
        bh = max(3.0, (v - base) / span * plot_h)
        by = pad_t + plot_h - bh
        if m == now_m:
            col, op = "#b8860b", "1"          # this month — amber, the reader's anchor
        elif m == best_m:
            col, op = "#1b7a3d", "1"          # seasonal peak — green
        elif m == worst_m:
            col, op = "#c0392b", ".85"        # seasonal trough — red
        else:
            col, op = "#8fae9c", ".65"
        bars.append(f'<rect x="{cx - bw / 2:.1f}" y="{by:.1f}" width="{bw:.1f}" '
                    f'height="{bh:.1f}" rx="3" fill="{col}" opacity="{op}"/>')
        if m in (now_m, best_m, worst_m):
            bars.append(f'<text x="{cx:.1f}" y="{by - 5:.1f}" font-size="10.5" '
                        f'fill="{col}" text-anchor="middle" font-weight="600">'
                        f'₹{v:,}</text>')
        bars.append(f'<text x="{cx:.1f}" y="{h - 12:.1f}" font-size="10" '
                    f'fill="{"#2c3e35" if m == now_m else "#7c8983"}" '
                    f'text-anchor="middle">{escape(_HI_MON_SHORT[m - 1])}</text>')

    return (f'<svg class="chart season-chart" viewBox="0 0 {w} {h}" role="img" '
            f'aria-label="महीने के हिसाब से भाव का रुझान">'
            f'<line x1="{pad_l}" y1="{pad_t + plot_h:.1f}" x2="{w - pad_r}" '
            f'y2="{pad_t + plot_h:.1f}" stroke="#e5e9e6" stroke-width="1"/>'
            f'{"".join(bars)}</svg>')


@router.get("/bhav/api/season/{c_slug}/{s_slug}/{d_slug}")
def _api_season(c_slug: str, s_slug: str, d_slug: str):
    """Lazy: the multi-year seasonality panel for tier 4.

    Reads ONLY our own mandi_price_monthly summary — never data.gov. On a
    miss it queues the slice for the background drain and renders nothing,
    so a page view can never wait on (or spend quota at) an external API.
    """
    from backend.services.mandi_season_service import get_summary, enqueue

    idx = _get_index()
    cs, ss, ds = c_slug.lower(), s_slug.lower(), d_slug.lower()
    commodity = idx.get("crops", {}).get(cs)
    state = idx.get("states", {}).get(cs, {}).get(ss)
    district = idx.get("dists", {}).get(cs, {}).get(ss, {}).get(ds)
    if not (commodity and state and district):
        return JSONResponse({"ok": False})

    try:
        summary = get_summary(state, district, commodity)
    except Exception:
        summary = None                       # DB hiccup must not break the page

    if not summary:
        try:
            enqueue(state, district, commodity)
        except Exception:
            pass
        # ok:True + empty html so the skeleton clears instead of shimmering forever
        return JSONResponse({"ok": True, "html": ""},
                            headers={"Cache-Control": "public, max-age=120"})

    hi = _hindi_name(commodity)
    today = date.today()
    by_month = summary["by_month"]
    best, worst = summary["best"], summary["worst"]
    years = summary["years"]

    chart = _season_chart(by_month, today.month,
                          best[0] if best else 0, worst[0] if worst else 0)

    # "पिछले साल इसी महीने" — the single most concrete line on the page
    ly_html = ""
    if summary["last_year"]:
        ly = summary["last_year"]["median"]
        rows_now = _rows_for(commodity, state=state, district=district)
        now_avg = _stats(rows_now)["avg"]
        if now_avg and ly:
            diff = (now_avg - ly) / ly * 100
            if abs(diff) < 1:
                cls, note = "flat", "आज लगभग उतना ही"
            elif diff > 0:
                cls, note = "up", f"▲ आज {abs(diff):.0f}% ज्यादा"
            else:
                cls, note = "dn", f"▼ आज {abs(diff):.0f}% कम"
            ly_html = (f'<li class="season-ly"><span class="sl-k">पिछले साल '
                       f'{escape(_HI_MONTHS[today.month - 1])} में</span>'
                       f'<span class="sl-v">₹{ly:,} '
                       f'<em class="sl-d {cls}">{note}</em></span></li>')
        elif ly:
            ly_html = (f'<li class="season-ly"><span class="sl-k">पिछले साल '
                       f'{escape(_HI_MONTHS[today.month - 1])} में</span>'
                       f'<span class="sl-v">₹{ly:,}</span></li>')

    peak_html = trough_html = ""
    if best and worst and best[0] != worst[0]:
        peak_html = (f'<li><span class="sl-k">सबसे ऊंचा भाव आमतौर पर</span>'
                     f'<span class="sl-v up">{escape(_HI_MONTHS[best[0] - 1])} — ₹{best[1]:,}</span></li>')
        trough_html = (f'<li><span class="sl-k">सबसे कम भाव आमतौर पर</span>'
                       f'<span class="sl-v dn">{escape(_HI_MONTHS[worst[0] - 1])} — ₹{worst[1]:,}</span></li>')

    if not (ly_html or peak_html):
        return JSONResponse({"ok": True, "html": ""})

    html = (f'<section class="card-w season">'
            f'<div class="card-w-h"><h2>📅 {escape(district)} में {escape(hi)} — '
            f'पिछले {years} साल का रुझान</h2>'
            f'<em>महीनेवार औसत · ₹/क्विंटल</em></div>'
            f'{chart}'
            f'<ul class="season-facts">{ly_html}{peak_html}{trough_html}</ul>'
            f'<p class="season-note">यह पिछले {years} साल के सरकारी रिकॉर्ड '
            f'(Agmarknet) का औसत है — आगे के भाव का अनुमान नहीं। हर साल मौसम, '
            f'आवक और मांग से भाव बदलता है।</p>'
            f'</section>')

    return JSONResponse({"ok": True, "html": html},
                        headers={"Cache-Control": "public, max-age=3600",
                                 "CDN-Cache-Control": "public, max-age=21600"})


# ════════════════════════════════════════════════════════════
# TIER 2 — /bhav/{crop} : pick a state
#
# FAST PATH: state cards come from the cached _get_index() —
# no DB query at all. Heavy content (best mandi nationwide,
# stats, answer_lead) is lazy-loaded via /bhav/api/tier2-extras.
# ════════════════════════════════════════════════════════════
@router.get("/bhav/{c_slug}", response_class=HTMLResponse)
def bhav_crop(c_slug: str):
    idx = _get_index()
    cs = c_slug.lower()
    commodity = idx.get("crops", {}).get(cs)
    if not commodity:
        return _not_found()

    hi = _hindi_name(commodity)
    # Dated by the DATA, not the clock — see _age_note. `today_hi` is
    # deliberately gone from this function so a future edit cannot bring the
    # mismatch back; tier 4 dropped it for the same reason on 2 Aug 2026.
    fresh_iso = _fresh_iso_crop(idx, cs)
    as_of_hi  = _as_of_hi(fresh_iso)
    canon = f"{SITE}/bhav/{cs}"
    state_map = idx["states"].get(cs, {})

    # State cards — purely from the cached index, no DB hit.
    cards = []
    for ss, sn in sorted(state_map.items(), key=lambda kv: kv[1]):
        n = len(idx["dists"].get(cs, {}).get(ss, {}))
        cards.append(_state_card(f"/bhav/{cs}/{ss}", sn, n, "जिले"))

    faqs = [
        (f"आज {hi} का भाव क्या है?",
         f"{hi} का भाव हर राज्य और मंडी में अलग-अलग होता है। सटीक भाव जानने के लिए नीचे अपना राज्य चुनें, "
         f"फिर जिला चुनें — वहां आज का पूरा भाव दिख जाएगा।"),
        (f"{hi} सबसे महंगा किस मंडी में बिक रहा है?",
         "मंडीवार भाव देखने के लिए अपना राज्य चुनें।"),
    ] + _msp_faqs(commodity)
    faq_html, faq_ld = _faq(faqs)
    ld = _ld(faq_ld, _crumb_ld([("कृषि मित्र", f"{SITE}/"), ("मंडी भाव", f"{SITE}/bhav"),
                                (hi, canon)]))

    # No state in the URL yet, so the जिला field has to be seeded from one:
    # the state where this crop is reported in the most districts.
    seed_ss = (max(state_map, key=lambda s: len(idx["dists"].get(cs, {}).get(s, {})))
               if state_map else "")

    t_hi, t_en, _same = _title_names(commodity)
    title = _fit(
        f"{t_hi} का भाव आज — {t_en} Price Today सभी राज्य",
        f"{t_hi} का भाव आज — {t_en} Price Today",
        f"{t_hi} का भाव आज — सभी राज्य")
    desc = _fit(
        f"{as_of_hi}: {t_hi} ({t_en}) का ताजा मंडी भाव — "
        f"{len(state_map)} राज्यों की मंडियों के रेट। राज्य चुनकर अपने जिले का भाव देखें।",
        f"{as_of_hi}: {t_hi} का ताजा मंडी भाव — "
        f"{len(state_map)} राज्यों की मंडियों के रेट। राज्य चुनकर अपने जिले का भाव देखें।",
        limit=162)

    head_h1 = f"आज का {escape(hi)} भाव — राज्य चुनें"
    head_sub = (f"📅 {as_of_hi} · {len(state_map)} राज्य · स्रोत: data.gov.in (Agmarknet)"
                f"{_age_badge(fresh_iso)}")
    body = f"""{_tier_head(head_h1, head_sub)}
{_hub_selector(cs, seed_ss, "", idx, known_crop=True)}
{_msp_html(commodity)}
{_dukan_pitch()}
{_lazy_div('bhav-lazy-t2', 'rows')}
<h2>राज्य के अनुसार {escape(hi)} का भाव</h2>
{_tier_search('tier-grid', 'राज्य खोजें... (उत्तर प्रदेश, बिहार)')}
<div class="place-grid" id="tier-grid">{"".join(cards)}</div>
<div class="cta-row">
{_net_price_cta(hi, cs)}
{_poultry_cta(cs)}
</div>
<h2>अक्सर पूछे जाने वाले सवाल</h2>
{faq_html}
{_TIER_SEARCH_JS}
{_lazy_script([('/bhav/api/tier2-extras/{cs}'.format(cs=cs), 'bhav-lazy-t2')])}"""
    crumbs = (f'<a href="{SITE}/">कृषि मित्र</a> › <a href="{SITE}/bhav">मंडी भाव</a> › {escape(hi)}')
    return _doc(title, desc, canon, crumbs, body, ld, _crop_image(commodity, 960),
                extra_css=_LAZY_CSS + _DKP_CSS, crop=cs)


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

    # The commonest miss on the whole tree: a real crop in a state that does not
    # report it (/bhav/wheat/keralam). Both halves are known, so both lists are
    # offered — this crop's real states, and this state's real crops.
    return _not_found(idx, cs, xs)


def _state_page(idx: dict, cs: str, commodity: str, ss: str) -> HTMLResponse:
    """Tier 3 — pick a district. FAST PATH: district cards come from the
    cached index. Heavy content (top mandis, stats) is lazy-loaded."""
    state = idx["states"][cs][ss]
    hi, hi_state = _hindi_name(commodity), _hindi_state(state)
    # Dated by the DATA, not the clock. This page used to open
    # "📅 4 सितंबर 2026 · ताजा भाव" over Cardamom prices last reported in Kerala
    # on 17 अगस्त — the honest date was already being computed one line down
    # for the robots gate and thrown away. See _age_note.
    fresh_iso = _fresh_iso_state(idx, cs, ss)
    as_of_hi  = _as_of_hi(fresh_iso)
    canon = f"{SITE}/bhav/{cs}/{ss}"
    dist_map = idx["dists"].get(cs, {}).get(ss, {})

    # District cards — purely from the cached index, no DB hit.
    cards = []
    for ds, dn in sorted(dist_map.items(), key=lambda kv: _hindi_district(ss, kv[1])):
        dn_hi = _hindi_district(ss, dn)
        cards.append(f"""<a class="dcard" href="/bhav/{cs}/{ss}/{ds}" data-name="{escape(f'{dn_hi} {dn} {ds}'.lower())}">
<span class="dcard-n">{escape(dn_hi)}</span>
<span class="dcard-r">भाव देखें →</span>
</a>""")

    faqs = [
        (f"आज {hi_state} में {hi} का भाव क्या है?",
         f"{hi_state} की मंडियों में {hi} का भाव जिले के अनुसार अलग-अलग है। यहां की सबसे नई सरकारी "
         f"रिपोर्ट {as_of_hi} की है। सटीक भाव जानने के लिए "
         f"नीचे अपना जिला चुनें — वहां पूरा भाव दिख जाएगा।"),
        (f"{hi_state} में {hi} सबसे महंगा कहां बिक रहा है?",
         "जिलेवार भाव के लिए नीचे अपना जिला चुनें।"),
    ] + _msp_faqs(commodity)
    faq_html, faq_ld = _faq(faqs)
    ld = _ld(faq_ld, _crumb_ld([
        ("कृषि मित्र", f"{SITE}/"), ("मंडी भाव", f"{SITE}/bhav"),
        (hi, f"{SITE}/bhav/{cs}"), (hi_state, canon)]))

    t_hi, t_en, _same = _title_names(commodity)
    title = _fit(
        f"{hi_state} में {t_hi} का भाव आज — {t_en} Price {state}",
        f"{hi_state} में {t_hi} का भाव आज — {t_en} Price",
        f"{hi_state} में {t_hi} का भाव आज")
    desc = (f"{as_of_hi}: {hi_state} की मंडियों में {hi} का ताजा भाव — "
            f"{len(dist_map)} जिलों के रेट और सबसे ज्यादा भाव देने वाली मंडियां। रोज़ अपडेट।")


    # State-language pass — see the same block on the district page below and
    # services/state_lang.py. Hindi is built first and kept wherever the JSON
    # says nothing, so this can only ever add a wording, never remove one.
    lang = state_lang.lang_for(state)
    hi_loc = state_lang.crop(hi, lang)
    as_of_loc = as_of_hi
    try:
        _d = date.fromisoformat(fresh_iso)
        as_of_loc = state_lang.date_str(_d.day, _d.month, _d.year, lang, as_of_hi)
    except (TypeError, ValueError):
        pass
    _lv = {"crop": state_lang.crop(t_hi, lang), "en": t_en, "state": hi_state,
           "state_en": state, "date": as_of_loc, "n_dist": len(dist_map)}
    _lt = state_lang.variants("titles", "crop_state", lang, _lv)
    if _lt:
        title = _fit(*_lt)
    _ldc = state_lang.variants("descs", "crop_state", lang, _lv)
    if _ldc:
        desc = _fit(*_ldc, limit=162)
    _lfq = {**_lv, "crop": hi_loc}
    head_h1 = escape(state_lang.h1("crop_state", lang, _lfq,
                                   f"{hi_state} में {hi} का भाव आज"))
    _lf = state_lang.faqs("crop_state", lang, _lfq)
    if _lf:
        faqs = _lf + _msp_faqs(commodity)
        faq_html, faq_ld = _faq(faqs)
        ld = _ld(faq_ld, _crumb_ld([
            ("कृषि मित्र", f"{SITE}/"),
            (state_lang.word("bhav", lang, "मंडी भाव"), f"{SITE}/bhav"),
            (hi_loc, f"{SITE}/bhav/{cs}"), (hi_state, canon)]))
    head_sub = (f"📅 {as_of_hi} · {len(dist_map)} जिले · स्रोत: data.gov.in (Agmarknet)"
                f"{_age_badge(fresh_iso)}")
    body = f"""{_tier_head(head_h1, head_sub)}
{_hub_selector(cs, ss, "", idx, known_crop=True, known_state=True)}
{_msp_html(commodity)}
{_dukan_pitch(hi_state)}
{_dealer_teaser_html(cs, ss, state, "")}
{_lazy_div('bhav-lazy-t3', 'rows')}
<h2>जिले के अनुसार {escape(hi)} का भाव</h2>
{_tier_search('tier-grid', 'जिला खोजें...')}
<div class="dcard-grid" id="tier-grid">{"".join(cards)}</div>
<div class="cta-row">
{_net_price_cta(hi, cs)}
</div>
<h2>अक्सर पूछे जाने वाले सवाल</h2>
{faq_html}
{_TIER_SEARCH_JS}
{_lazy_script([('/bhav/api/tier3-extras/{cs}/{ss}'.format(cs=cs, ss=ss), 'bhav-lazy-t3')])}"""
    crumbs = (f'<a href="{SITE}/">कृषि मित्र</a> › <a href="{SITE}/bhav">मंडी भाव</a> › '
              f'<a href="{SITE}/bhav/{cs}">{escape(hi)}</a> › {escape(hi_state)}')
    return _doc(title, desc, canon, crumbs, body, ld, _crop_image(commodity, 960),
                extra_css=_LAZY_CSS + _BP_CSS + _DKP_CSS + _PRODUCT_CSS,
                crop=cs, lang=lang,
                robots=index_gate.robots_for(fresh_iso))


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
        return _not_found(idx, cs, ss)

    # Scoped by STATE as well as district. Without the state, the four district
    # names shared by two states (pratapgarh, bilaspur, hamirpur, balrampur)
    # pulled both states' mandis onto one page under a single district heading.
    prices = _rows_for(commodity, state=state, district=district)
    if not prices:                      # raw-name miss or aged-out snapshot
        prices = _rows_for_district(idx, cs, ss, ds)
    if not prices:                      # never reported within the history window
        return _not_found(idx, cs, ss)

    hi, hi_state = _hindi_name(commodity), _hindi_state(state)
    # Devanagari name where one is known, the Latin name where it is not — see
    # _hindi_district. Every Hindi sentence on this page uses d_hi; the <title>
    # and the breadcrumb keep the Latin name too, because Latin-spelled queries
    # are the half that already converts.
    d_hi = _hindi_district(state, district)
    # The NEWEST date among the rows actually rendered, not prices[0]'s — row
    # order is whatever Postgres returned. A district's rows routinely span
    # several days (Nashik onion on 4 Sep 2026: 49 rows across 4 dates), so
    # prices[0] made the "… तक" in the header a coin toss that could contradict
    # the as_of date printed beside it in the same line.
    data_date = _newest_row_date(prices)
    fresh_iso = _fresh_iso(idx, cs, ss, ds)
    # Every sentence on this page that sits next to a price is dated by the
    # price, not by the clock — see _as_of_hi. `today_hi` is deliberately not
    # defined here any more so a future edit cannot reintroduce the mismatch.
    as_of_hi  = _as_of_hi(fresh_iso)
    canon     = f"{SITE}/bhav/{cs}/{ss}/{ds}"
    st = _stats(prices)

    # ── mandi-wise cards ──
    # Cards are dated INDIVIDUALLY where they disagree with the page's headline
    # date. The snapshot carries a quiet mandi's last price forward, so this
    # list mixes days as a matter of course — Meerut wheat on 4 Sep 2026 was 2
    # rows from 2 सितंबर and 8 from 31 अगस्त, rendered identically. A farmer
    # comparing two mandis was comparing two different days without being told.
    newest_iso = _row_date_iso(data_date)
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
        row_iso = _row_date_iso(p.get("date") or "")
        stamp = (f'<span class="mkt-date">📅 {escape(_hindi_data_date(p.get("date") or ""))} '
                 f'का भाव</span>'
                 if row_iso and newest_iso and row_iso < newest_iso else "")
        cards_html.append(f"""<article class="mkt">
<div class="mkt-name">{escape(p.get('market', '-'))}</div>
<div class="mkt-var">{escape(variety) if variety and variety != '-' else '—'}{stamp}</div>
<div class="mkt-price"><b>{_rupee(p.get('modal_price'))}</b><small>/क्विंटल</small>{arrow}</div>
<div class="mkt-foot">
<span class="mkt-range">{_rupee(p.get('min_price'))} – {_rupee(p.get('max_price'))}</span>
{_sparkline(p.get('spark') or [])}
</div>
</article>""")
    mkt_cards = "\n".join(cards_html)

    # ── the district's daily average, one point per calendar day ──
    # Everything below that quotes a trend reads THIS: the headline delta, the
    # sell-signal and the chart. They used to be computed three different ways
    # off three different row sets and openly disagreed on the page.
    series = _district_series(prices, fresh_iso, st["avg"])

    # ── overall day-on-day move ──
    # Yesterday's district average vs today's, on the same carry-forward basis
    # as the headline itself, so "कल से" is literally what it measures. The old
    # number was the unweighted mean of the per-mandi change_pct values, which
    # (a) silently dropped every mandi with no previous price, (b) averaged
    # percentages against different base dates — a mandi's "prev" can be a week
    # old — so "कल से" was often not from yesterday, and (c) could not be
    # reconciled with either the chart or the headline.
    avg_pct = None
    if len(series) >= 2 and series[-2]:
        avg_pct = round((series[-1] - series[-2]) / series[-2] * 100, 1)
    if avg_pct is None:
        # No usable history (the mandi_last_seen rescue path) — fall back to the
        # per-row deltas, which are all such a page has.
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
    # Comparison against other districts is LAZY-LOADED via
    # /bhav/api/tier4-extras — this was the #1 cause of 504s because it
    # re-fetched the entire state's rows on every district page load.
    # Now the price panel renders instantly; the comparison appears shortly after.
    better_html = _lazy_div('bhav-lazy-t4', 'rows')

    # ── multi-year seasonality (पिछले साल इसी समय / कब बेचें) ──
    # Also lazy, and for a second reason beyond speed: on the first ever view
    # of a district+crop the summary does not exist yet, so the endpoint
    # queues it for the background drain and returns nothing. The page must
    # never wait on that.
    season_html = _lazy_div('bhav-lazy-season', 'card')

    # ── the trend chart, drawn from the district series built above ──
    # sell-or-wait read, from the same history the chart draws (no forecast made)
    signal_html = _sell_signal(series, st["avg"], avg_pct)
    chart_svg = _chart(series)
    chart_html = (f"""<section class="card-w">
<div class="card-w-h"><h2>{escape(hi)} का {len(series)}-दिन रुझान</h2><em>{escape(d_hi)} · ₹/क्विंटल</em></div>
{chart_svg}
</section>""" if chart_svg else "")

    price_txt = (f"औसतन ₹{st['avg']:,} प्रति क्विंटल (₹{st['lo']:,} से ₹{st['hi']:,} तक)"
                 if st["avg"] and st["lo"] and st["hi"] else "नीचे मंडीवार भाव देखें")
    faqs = [
        (f"आज {d_hi} में {hi} का भाव क्या है?",
         f"{as_of_hi} को {d_hi} ({hi_state}) की मंडियों में {hi} का भाव {price_txt} है। "
         f"यह भाव {_mandis_gen(st['n'])} की सरकारी रिपोर्ट पर आधारित है।"),
        (f"{d_hi} में {hi} का न्यूनतम और अधिकतम रेट कितना है?",
         (f"{as_of_hi} को {d_hi} में {hi} का न्यूनतम भाव ₹{st['lo']:,} और अधिकतम भाव "
          f"₹{st['hi']:,} प्रति क्विंटल दर्ज हुआ है।"
          if st["lo"] and st["hi"] else "मंडीवार न्यूनतम/अधिकतम भाव नीचे दिए गए हैं।")),
        ("यह भाव कब और कहां से अपडेट होता है?",
         "भाव रोज़ सुबह भारत सरकार के data.gov.in (Agmarknet) से अपडेट होते हैं। "
         "जिन मंडियों की रिपोर्ट आज नहीं आई, उनका पिछला भाव दिखता है।"),
    ]
    # MSP pairs stay in Hindi even on a Marathi page, and that is a known seam,
    # not an oversight: they are built inside services/msp.py against the MSP
    # table's own wording, and translating them means translating that module
    # too. The premise of this whole change is that Hindi is understood here and
    # merely not SEARCHED in — so a Hindi MSP answer below a Marathi one costs
    # polish, while a missing MSP answer would cost a farmer the floor price.
    msp_faqs = _msp_faqs(commodity, st["avg"], d_hi)

    # ── The page's own language, decided by the state it is about ──────────
    # Everywhere but Maharashtra this resolves to "hi" and every line from here
    # down behaves exactly as it did. There, `बाजार भाव` and `गहू` replace
    # `मंडी भाव` and `गेहूं` — the words that state's farmers actually type, and
    # the reason those queries rank at position 6-10 and take no clicks. The
    # Hindi copy above is still built first and still stands wherever the JSON
    # defines nothing, so the fallback is the old behaviour itself rather than a
    # promise about it. See services/state_lang.py.
    lang = state_lang.lang_for(state)
    hi_loc = state_lang.crop(hi, lang)
    # The reported date in the page's own month names. It leads the meta
    # description, so a Hindi "सितंबर" on a Marathi page is the tell a reader
    # sees before anything else.
    as_of_loc = as_of_hi
    try:
        _d = date.fromisoformat(fresh_iso)
        as_of_loc = state_lang.date_str(_d.day, _d.month, _d.year, lang, as_of_hi)
    except (TypeError, ValueError):
        pass
    # {lo}/{hi} are passed only when this district really reported both — the
    # min/max FAQ is then dropped whole rather than answered vaguely.
    d_loc = state_lang.district(d_hi, lang)
    _lfq = {"crop": hi_loc, "district": d_loc, "district_en": district,
            "state": hi_state, "date": as_of_loc, "n": st["n"],
            "price": state_lang.fill(
                "price_avg" if (st["avg"] and st["lo"] and st["hi"]) else "price_none",
                lang, {"avg": f"{st['avg']:,}" if st["avg"] else "",
                       "lo": f"{st['lo']:,}" if st["lo"] else "",
                       "hi": f"{st['hi']:,}" if st["hi"] else ""})}
    if st["lo"] and st["hi"]:
        _lfq["lo"], _lfq["hi"] = f"{st['lo']:,}", f"{st['hi']:,}"
    _lf = state_lang.faqs("crop_district", lang, _lfq)
    faqs = (_lf or faqs) + msp_faqs

    faq_html, faq_ld = _faq(faqs)
    ld = _ld(faq_ld, _crumb_ld([
        ("कृषि मित्र", f"{SITE}/"),
        (state_lang.word("bhav", lang, "मंडी भाव"), f"{SITE}/bhav"),
        (hi_loc, f"{SITE}/bhav/{cs}"), (hi_state, f"{SITE}/bhav/{cs}/{ss}"),
        (d_hi, canon)]))

    t_hi, t_en, same = _title_names(commodity)
    # The state joins the title ONLY where the district name is shared with
    # another state — see _ambiguous_district. The other ~98% keep the shorter,
    # punchier version, because a title that spends 14 characters disambiguating
    # something that was never ambiguous is just a worse title.
    place = f"{d_hi}, {hi_state}" if _ambiguous_district(idx, cs, ds) else d_hi
    # The two halves of the title used to carry the same token — "Sehore" twice —
    # so the second was dropped as waste. Now the Hindi clause spells the district
    # सीहोर and the English clause spells it Sehore, and they are two different
    # queries: 0.36% CTR from the searchers who typed Devanagari, 0.97% from the
    # ones who typed Latin, at the same average position. Where no Hindi name is
    # known the two collapse back to one string and the richest variant is simply
    # not offered, which is the old behaviour exactly.
    en_d = "" if d_hi == district else district
    # NO RUPEE FIGURE IN THE TITLE. Tried 19 Sep 2026 ("Variant A",
    # price-in-title) and reverted 21 Sep, because the claim cannot be kept
    # true. Measured that day over the whole index: of 11,403 crop×district
    # pages, ZERO carried a price from the current day — median age 2 days,
    # 16.4% of them 4-7 days old. The figure used was st["hi"], which is
    # round(max(maxs)): the highest max across every mandi in the district and
    # the most volatile number on the page. Live example from production,
    # /bhav/garlic/madhya-pradesh/sehore: the title read "भाव आज … ₹15,001/क्वि
    # तक" while the page itself said 19 सितंबर and a modal of ₹10,478.
    #
    # Google then caches a title for days to weeks on top of that, so there is
    # no refresh cadence that can rescue it — the 13 Jul Bareilly snippet was
    # still being served on 2 Aug. A farmer who clicks ₹15,001 and finds
    # ₹10,478 has been misled by us, which is both the legal exposure rule and
    # the one asset the whole site sells.
    #
    # "आज का भाव" WITHOUT a number is fine and stays: it names what the page is
    # for, and makes no claim about a figure. The meta description carries the
    # real date ("19 सितंबर 2026 अपडेट") and may quote numbers, because it is
    # regenerated with the page and shown beside that date.
    #
    # (This revert first landed in 3c31404 and was undone by accident in
    # 7629f06 the same morning; restored here.)
    title = _fit(*(
        # No real Hindi name for this commodity: t_hi IS t_en, so a bilingual
        # template would print one long string twice.
        (([f"{t_hi} का भाव आज {place} मंडी में — {en_d} Mandi"] if en_d else []) + [
         f"{t_hi} का भाव आज {place} मंडी में",
         f"{place} में {t_hi} का भाव आज",
         f"{t_hi} भाव — {place}",
         f"{t_hi} भाव — {district}"]
        if same else
        # The English name owns the "<crop> price today" query space, so it is
        # the last thing to go, not the first: every variant that still fits
        # keeps it, and only the final fallbacks give it up.
        ([f"{t_hi} का भाव आज {place} मंडी में — {t_en} Price {en_d}"] if en_d else []) + [
         f"{t_hi} का भाव आज {place} मंडी में — {t_en} Price Today",
         f"{t_hi} का भाव आज {place} मंडी में — {t_en} Price",
         f"{t_hi} का भाव आज {place} — {t_en} Price",
         f"{place} में {t_hi} भाव — {t_en}",
         f"{place} में {t_hi} का भाव आज",
         f"{t_hi} का भाव — {district}"])))

    # Same `lang` resolved above the FAQs. `t_hi` rather than `hi` here: the
    # title falls back to the English name for the ~13 commodity groups with no
    # Hindi one, and crop() returns those unchanged, so the English name stays.
    # `place` rebuilt on the local spelling — it is the district name plus the
    # state only where two states share it, so it must move with the district.
    place_loc = f"{d_loc}, {hi_state}" if _ambiguous_district(idx, cs, ds) else d_loc
    _lv = {"crop": state_lang.crop(t_hi, lang), "en": t_en, "place": place_loc,
           "district": d_loc, "district_en": district, "en_d": en_d,
           "state": hi_state, "state_en": state, "date": as_of_loc,
           "n": st["n"]}
    _lt = state_lang.variants("titles", "crop_district", lang, _lv)
    if _lt:
        title = _fit(*_lt)

    _avg = f"औसत ₹{st['avg']:,}/क्विंटल। " if st["avg"] else ""
    # About a third of titles are too long to hold both spellings of the
    # district, and the one dropped is the Latin one — which is the half of
    # this page's searchers that ALREADY converts (0.97% against 0.36%). So
    # where the title had to give it up, the description picks it up: between
    # the two, every district page names itself in both scripts.
    d_both = d_hi if (d_hi == district or district in title) else f"{d_hi} ({district})"
    # One bracket, not two: "आगरा (Agra, उत्तर प्रदेश)", never "आगरा (Agra) (उत्तर प्रदेश)".
    d_state = (f"{d_hi} ({hi_state})" if d_both == d_hi
               else f"{d_hi} ({district}, {hi_state})")
    # ── CTR-optimised meta description ──
    # Number + benefit + freshness signal + soft CTA. The MSP mention and
    # "रोज़ सुबह अपडेट" are the hooks the old description was missing.
    desc  = _fit(
        f"{as_of_hi} अपडेट: {d_state} में {hi} का ताजा भाव — {_avg}"
        f"{_mandis_gen(st['n'])} के रेट, MSP तुलना और नेट भाव। रोज़ सुबह अपडेट।",
        f"{as_of_hi}: {d_state} में {hi} का ताजा भाव — {_avg}"
        f"{_mandis_gen(st['n'])} के रेट, कल से तुलना और भाव का रुझान। रोज़ अपडेट।",
        f"{as_of_hi}: {d_both} में {hi} का ताजा भाव — {_avg}"
        f"{_mandis_gen(st['n'])} के रेट और भाव का रुझान।",
        f"{as_of_hi}: {d_hi} में {hi} का ताजा भाव — {_avg}"
        f"{_mandis_gen(st['n'])} के रेट और भाव का रुझान।",
        limit=162)

    # Same override as the title, and it has to move with it: a Marathi title
    # over a Hindi snippet is a mismatched pair in one SERP result.
    _lv["avg"] = f"सरासरी ₹{st['avg']:,}/क्विंटल. " if st["avg"] else ""
    _ld_ = state_lang.variants("descs", "crop_district", lang, _lv)
    if _ld_:
        desc = _fit(*_ld_, limit=162)

    # WhatsApp share — share THIS bhav page's own URL, not the /share/mandi deep
    # link (which unfurls the same preview but bounces the recipient into the mandi
    # app, away from the page the sender was actually looking at). This page already
    # carries the rich OG tags — the crop photo (og:image, set in the _doc call below)
    # plus a price-in-the-title — so WhatsApp still unfurls one rich preview card, and
    # the tap lands right back on this bhav page. Native share sheet, wa.me fallback.
    share_url = canon
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

    # AI-citable lead — this tier already shows every number, so the sentence can
    # carry them all: date, place, average, range, source. One quotable passage.
    lead_range = (f" (न्यूनतम ₹{st['lo']:,} — अधिकतम ₹{st['hi']:,})"
                  if st["lo"] and st["hi"] else "")
    answer_lead = ((f'<p class="lead-out">{as_of_hi} को {escape(d_hi)} ({escape(hi_state)}) की '
                    f'{_mandis_gen(st["n"])} में {escape(hi)} का औसत मॉडल भाव ₹{st["avg"]:,} प्रति क्विंटल '
                    f'दर्ज हुआ{lead_range}। स्रोत: भारत सरकार का Agmarknet (data.gov.in) पोर्टल, '
                    f'{escape(_hindi_data_date(data_date))} तक।</p>')
                   if st["avg"] else "")

    # Only link the buyer directory when that district actually has live
    # listings — an empty directory page is a dead end for the farmer and a
    # thin-content liability for the whole /bhav tree.
    kharidar_cta = (
        f'<a class="btn btn-kh" href="/bhav/{cs}/{ss}/{ds}/kharidar">'
        f'🧾 {escape(d_hi)} में {escape(hi)} कौन खरीदेगा?</a>'
        if _has_kharidar(cs, state, district) else "")

    # The headline moves with the title or neither should: a Marathi result that
    # wins the click and opens onto "आज का गेहूं भाव" has spent the click telling
    # the farmer he is in the wrong place. `hi` rather than `t_hi` — this is the
    # visible name, which keeps the Hindi word even where the title had to fall
    # back to English to fit.
    page_h1 = state_lang.h1("crop_district", lang, {**_lv, "crop": hi_loc},
                            f"आज का {hi} भाव — {d_hi} मंडी")

    map_html = _mandi_satellite_map_html(state=state, district=district,
                                         prices=prices, commodity=commodity,
                                         crop_hi=hi, s_slug=ss, d_slug=ds, d_hi=d_hi)

    hero_map_btn = (
        '<button class="answer-map-btn" type="button" onclick="scrollToBhavMap()" title="मंडी उपग्रह नक्शा देखें">'
        '<span class="amb-radar" aria-hidden="true"><span class="amb-ping"></span><span class="amb-dot"></span></span>'
        '<svg class="bm-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="3 6 9 3 15 6 21 3 21 18 15 21 9 18 3 21"/><line x1="9" y1="3" x2="9" y2="18"/><line x1="15" y1="6" x2="15" y2="21"/></svg>'
        '<span class="amb-txt">नक्शा देखें</span>'
        '<span class="amb-badge">उपग्रह</span>'
        '<svg class="amb-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M12 5l7 7-7 7"/></svg>'
        '</button>'
        if map_html else ""
    )

    body = f"""<section class="answer">
{answer_photo}
{_alert_bell(commodity, state, district)}
<div class="answer-in">
<h1>{escape(page_h1)}</h1>
<p class="answer-sub">📅 {as_of_hi} · {escape(hi_state)} · {_mandis_gen(st['n'])} की सरकारी रिपोर्ट{_age_badge(fresh_iso)}</p>
<div class="answer-price">
<div class="answer-rupee">{lead}<small>/क्विंटल</small></div>
{delta_html}
</div>
<div class="answer-range">
<div><span>न्यूनतम</span><b>{f"₹{st['lo']:,}" if st['lo'] else '—'}</b></div>
<div><span>अधिकतम</span><b>{f"₹{st['hi']:,}" if st['hi'] else '—'}</b></div>
<div><span>{'मंडी' if st['n'] == 1 else 'मंडियां'}</span><b>{st['n']}</b></div>
{hero_map_btn}
</div>
{signal_html}
<div class="answer-actions">
<button class="answer-share" type="button" onclick="shareBhav()">{_WA_GLYPH} WhatsApp पर भेजें</button>
<button class="answer-appeal" type="button" onclick="openCropAppeal()">🤝 खरीदें/बेचें</button>
{_net_price_cta(hi, cs, state, district)}
</div>
{_next_update()}
{_wa_daily(hi, district, state)}
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
  window.scrollToBhavMap=function(){{
    if(window.load_bhav_map)window.load_bhav_map();
    var el=document.getElementById('bhav-map-sec');
    if(el)el.scrollIntoView({{behavior:'smooth',block:'start'}});
  }};
}})();
</script>

{_switchers(cs, ss, ds)}

{_msp_html(commodity, st["avg"])}

{_dukan_pitch(district)}

{better_html}

{chart_html}

{season_html}

{answer_lead}

{map_html}

<section class="card-w">
<div class="card-w-h"><h2>मंडीवार भाव</h2><em>▲▼ = कल के मुकाबले</em></div>
<div class="mkts">
{mkt_cards}
</div>
</section>
<p class="note">सभी भाव ₹ प्रति क्विंटल · मॉडल भाव (सबसे ज़्यादा कारोबार वाला रेट)।</p>

{_dealer_teaser_html(cs, ss, state, ds)}

<div class="cta-row">
<button class="btn btn-wa" type="button" onclick="shareBhav()">📲 WhatsApp पर भाव भेजें</button>
<button class="btn btn-appeal" type="button" onclick="openCropAppeal()">🤝 {escape(hi)} बेचना/खरीदना है?</button>
{kharidar_cta}
</div>
{_appeal_block(hi, state, district)}

<h2>अक्सर पूछे जाने वाले सवाल</h2>
{faq_html}
{_kheti_saman_html(cs, hi)}
{_lead_gen_html()}
{_related_links(cs, ss, ds, commodity, district)}
{_lazy_script([('/bhav/api/tier4-extras/{cs}/{ss}/{ds}'.format(cs=cs, ss=ss, ds=ds), 'bhav-lazy-t4'),
               ('/bhav/api/season/{cs}/{ss}/{ds}'.format(cs=cs, ss=ss, ds=ds), 'bhav-lazy-season')])}"""

    map_head = (
        '<link rel="dns-prefetch" href="https://server.arcgisonline.com">'
        '<link rel="dns-prefetch" href="https://unpkg.com">'
        '<link rel="preconnect" href="https://server.arcgisonline.com">'
        '<link rel="preconnect" href="https://unpkg.com">'
        '<link rel="preload" as="script" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js">'
        f'{_LEAFLET_CSS}'
        if map_html else ""
    )
    crumbs = (f'<a href="{SITE}/">कृषि मित्र</a> › <a href="{SITE}/bhav">मंडी भाव</a> › '
              f'<a href="{SITE}/bhav/{cs}">{escape(hi)}</a> › '
              f'<a href="{SITE}/bhav/{cs}/{ss}">{escape(hi_state)}</a> › {escape(d_hi)}')
    return _doc(title, desc, canon, crumbs, body, ld, _crop_image(commodity, 960),
                head_extra=map_head,
                # _BP_CSS + _PRODUCT_CSS are new here: the district page now
                # carries the paid dealer panel too (the metered product), which
                # it never used to.
                extra_css=_LAZY_CSS + _APPEAL_CSS + _DKP_CSS + _BP_CSS + _PRODUCT_CSS + _BHAV_MAP_CSS,
                updated=fresh_iso, crop=cs, lang=lang,
                robots=index_gate.robots_for(fresh_iso))


# ════════════════════════════════════════════════════════════
# TIER 4b — /bhav/{crop}/{state}/{district}/kharidar : who will buy it
#
# The price pages answer "कितने का है"; this one answers the question that
# actually moves money — "अब बेचूं किसे?". It is deliberately a TEMPLATE with a
# hand-seeded JSON behind it (services/buyers.py), not a marketplace: we never
# touch the produce, hold payment, or take counterparty risk. We match, and the
# listing/featured slot is what a trader or dealer pays for.
#
# The empty state is the important one, because every district starts empty:
# the page still renders (a dealer who lands on it can ask to be listed) but it
# ships noindex, so ~14k thin directory pages can never enter the index and drag
# the /bhav tree down with them. It joins the sitemap only once it has listings.
#
# Four segments, so it can never collide with the three-segment tier-4 route.
# ════════════════════════════════════════════════════════════

_KH_CSS = """
.kh-note{background:var(--green-pale);border:1px solid #bfe3c8;border-radius:var(--radius-md);
padding:13px 16px;font-size:13.5px;color:var(--green-dark);line-height:1.6;margin:16px 0}
.kh-note b{font-weight:800}
.kh-h{font-size:15px;margin:22px 0 0;color:var(--text-mid);font-weight:800}
.kh-list{display:flex;flex-direction:column;gap:12px;margin:12px 0 0}
/* Krashi Bazar rows read as a quieter second tier than the verified dealers
   above them — same card, amber-free, no call button. */
.kh-bz{border-left-color:var(--sky)}
.kh-meta{font-size:13px;font-weight:800;color:var(--green-dark);margin-top:9px}
.kh-bzbtn{background:var(--cream);color:var(--green-dark);
border:1.5px solid var(--border)}
.kh-bzbtn:hover{background:var(--green-pale);border-color:var(--green-light)}
.kh-card{background:var(--white);border:1px solid var(--border);border-radius:var(--radius-md);
box-shadow:var(--shadow-sm);padding:15px 17px;border-left:4px solid var(--green-light)}
.kh-card.feat{border-left-color:var(--amber);background:#fffdf6}
.kh-head{display:flex;align-items:flex-start;gap:11px;flex-wrap:wrap}
.kh-ic{font-size:22px;line-height:1.2;flex:0 0 auto}
.kh-id{display:flex;flex-direction:column;min-width:0;flex:1}
.kh-name{font-size:16px;font-weight:800;color:var(--text-dark);line-height:1.35;
display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.kh-kind{font-size:12px;color:var(--text-soft);margin-top:3px}
.kh-tick{display:inline-flex;align-items:center;gap:4px;font-size:11px;font-weight:800;
color:var(--green-mid);background:var(--green-pale);border-radius:999px;padding:2px 8px}
.kh-feat-tag{font-size:10.5px;font-weight:800;color:#7a5200;background:rgba(233,168,37,.25);
border-radius:999px;padding:2px 8px;letter-spacing:.2px}
.kh-crops{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}
.kh-crop{font-size:11.5px;font-weight:700;color:var(--green-dark);background:var(--cream);
border:1px solid var(--border);border-radius:999px;padding:3px 10px}
.kh-desc{font-size:13px;color:var(--text-mid);line-height:1.55;margin-top:9px}
/* Two equal columns, not wrapped pills: these are the only two things a farmer
   can DO on this card, and at 390px the wrapped version put WhatsApp on its own
   second line at a random width. */
.kh-acts{display:grid;grid-template-columns:1fr 1fr;gap:9px;margin-top:13px}
/* A dealer with only a phone (or only WhatsApp) gets one full-width button.
   Set from Python rather than :has(), which older Android WebViews ignore —
   and a lone half-width button is exactly the ragged look this replaced. */
.kh-acts.one{grid-template-columns:1fr}
.kh-btn{display:inline-flex;align-items:center;justify-content:center;gap:7px;
text-decoration:none;font-size:13.5px;font-weight:700;padding:11px 12px;
border-radius:22px;transition:transform .15s,background .15s}
.kh-btn:hover{transform:translateY(-1px)}
.kh-call{background:var(--green-dark);color:#fff}
.kh-call:hover{background:var(--green-mid)}
.kh-wa{background:#25d366;color:#fff}
.kh-wa:hover{background:#1eb958}
.kh-empty{background:var(--white);border:1px dashed var(--border);border-radius:var(--radius-md);
padding:22px 18px;text-align:center;margin:16px 0;box-shadow:var(--shadow-sm)}
.kh-empty h2{font-size:17px;margin:0 0 7px}
.kh-empty p{font-size:13.5px;color:var(--text-mid);line-height:1.6;margin:0 auto;max-width:520px}
/* The supply side. Deliberately a quieter card than .kh-join (which is the
   pitch to a dealer, in full green): this one sits mid-page and must not read
   as an ad — it is the farmer's own next step. */
.kh-sell{margin-top:22px;background:var(--white);border:1px solid var(--border);
border-left:4px solid var(--amber);border-radius:var(--radius-md);
padding:18px 20px;box-shadow:var(--shadow-sm)}
.kh-sell h2{font-size:17px;margin:0 0 6px;color:var(--green-dark)}
.kh-sell p{font-size:13.5px;line-height:1.6;color:var(--text-mid);margin:0 0 13px}
.kh-sell-n{font-size:13px;color:var(--green-dark);background:var(--green-pale);
border-radius:var(--radius-sm);padding:9px 12px;margin:0 0 13px!important}
.kh-sell-n b{font-weight:800}
.kh-sell-btn{display:inline-flex;align-items:center;gap:8px;border:0;cursor:pointer;
text-decoration:none;background:var(--green-dark);color:#fff;font:inherit;font-size:14px;
font-weight:800;padding:11px 20px;border-radius:24px;transition:background .15s,transform .15s}
.kh-sell-btn:hover{background:var(--green-mid);transform:translateY(-1px)}
.kh-join{margin-top:22px;background:var(--green-dark);color:#fff;border-radius:var(--radius-md);
padding:18px 20px;box-shadow:var(--shadow-md)}
.kh-join h2{font-size:17px;margin:0 0 6px;color:#fff}
.kh-join p{font-size:13px;line-height:1.6;color:rgba(255,255,255,.86);margin:0 0 13px}
.kh-join a{display:inline-flex;align-items:center;gap:8px;background:var(--amber);color:#3a2c00;
text-decoration:none;font-size:14px;font-weight:800;padding:11px 20px;border-radius:24px}
/* The WhatsApp hop is the fallback, so it reads as secondary next to the form. */
.kh-join-wa{background:transparent!important;color:rgba(255,255,255,.9)!important;
border:1.5px solid rgba(255,255,255,.35);font-weight:700!important;margin-left:8px}
@media(max-width:480px){.kh-join a{display:flex;justify-content:center}
.kh-join-wa{margin:9px 0 0}}
.kh-fine{font-size:11px;color:var(--text-soft);line-height:1.55;margin-top:14px}
"""


# ── /dukanlisting: the Tier-3 (crop+state) paid-dealer panel ──
# Deliberately its own small CSS block, not a reuse of _KH_CSS: .kh-btn/.kh-call
# /.kh-wa exist to style a tel:/wa.me action, and this panel must never grow
# one — see services/buyers.py::for_bhav_panel's docstring on why contact
# details stay one click away, on the existing /kharidar page, rather than
# inline here.
_BP_CSS = """
.bp-wrap{margin:16px 0;background:var(--white);border:1px solid var(--border);
border-radius:var(--radius-md);box-shadow:var(--shadow-sm);padding:16px 18px}
.bp-h{margin:0 0 12px}
.bp-h h2{font-size:15.5px;margin:0;color:var(--green-dark)}
.bp-sub{font-size:11.5px;color:var(--text-soft);margin:2px 0 0}
/* The farmer's side of the deal. The dealer agrees to terms before he pays;
   the farmer never signs anything, so the one caution he gets has to be where
   the phone number is — not only in a policy page nobody opens. */
.bp-warn{font-size:11.5px;line-height:1.6;color:var(--text-soft);margin:11px 0 0;
padding:9px 11px;background:var(--cream);border:1px solid var(--border);
border-radius:var(--radius-sm)}
.bp-warn a{color:var(--text-soft);text-decoration:underline}
.bp-list{display:flex;flex-direction:column;gap:10px}
.bp-card{display:flex;align-items:flex-start;gap:10px;border:1px solid var(--border);
border-radius:var(--radius-sm);padding:11px 13px;background:var(--cream)}
.bp-ic{font-size:19px;line-height:1.3;flex:0 0 auto}
.bp-body{min-width:0;flex:1}
.bp-name{font-size:14.5px;font-weight:800;color:var(--text-dark);display:flex;
align-items:center;gap:6px;flex-wrap:wrap}
.bp-tick{font-size:10.5px;font-weight:800;color:var(--green-mid);
background:var(--green-pale);border-radius:999px;padding:1px 7px}
.bp-kind{font-size:11.5px;color:var(--text-soft);margin-top:2px}
.bp-crops{display:flex;gap:5px;flex-wrap:wrap;margin-top:7px}
.bp-crop{font-size:11px;font-weight:700;color:var(--green-dark);background:var(--white);
border:1px solid var(--border);border-radius:999px;padding:2px 8px}
.bp-link{display:inline-block;margin-top:8px;font-size:12.5px;font-weight:700;
color:var(--green-dark);text-decoration:none}
.bp-link:hover{text-decoration:underline}
.bp-cta{display:block;text-align:center;margin-top:13px;font-size:12px;
color:var(--text-soft);text-decoration:none}
.bp-cta:hover{color:var(--green-dark)}
"""

# Its own block rather than part of _BP_CSS: the pitch renders on tiers 2 and 4
# too, which carry no dealer panel and would otherwise ship the panel's styles
# for nothing — or, worse, render the pitch unstyled because someone added it to
# a page and forgot the CSS came bundled with something unrelated.
_PRODUCT_CSS = """
/* A paying dealer's catalogue, as a shelf you swipe — not a grid.
   Field-for-field the same object routes/product.py::_hub_card() renders, so a
   dealer's item and a KrashiMitra item look like the same kind of thing to a
   farmer: one design language, one discount calculation.

   WHY A STRIP. As a grid, every extra product added a whole 104px-tall row: a
   dealer with six items owned about 1,100px of a phone screen, and the dealer
   below him was never seen. The strip is a fixed ~200px however many he lists,
   which is what makes "list more products" safe to encourage. Photos also stay
   large, and the photo is the part a shopkeeper is actually paying for.

   The cost, accepted: prices are harder to compare across a swipe than down a
   list, and a dealer with one product looks sparse. Both get better as the
   catalogue fills, which is the direction we want him pushed anyway. */
.dp-shelf{display:flex;gap:9px;overflow-x:auto;margin-top:11px;padding-bottom:3px;
scrollbar-width:none;-webkit-overflow-scrolling:touch;scroll-snap-type:x proximity}
.dp-shelf::-webkit-scrollbar{display:none}
.dp-card{flex:0 0 118px;scroll-snap-align:start;background:var(--white);
border:1px solid var(--border);border-radius:11px;overflow:hidden;
box-shadow:var(--shadow-sm);text-decoration:none;color:inherit}
/* A shelf with one or two items on it looks half-stocked at a fixed 118px —
   the one thing a swipe strip is worse at than a grid. Widen them to fill the
   row instead; from three up, the part-visible third card is the cue that
   there is more to swipe to. */
.dp-shelf>.dp-card:only-child{flex-basis:62%}
.dp-shelf>.dp-card:first-child:nth-last-child(2),
.dp-shelf>.dp-card:first-child:nth-last-child(2)~.dp-card{flex-basis:calc(50% - 5px)}
.dp-photo{position:relative;height:80px;background:var(--cream);
display:flex;align-items:center;justify-content:center;overflow:hidden}
/* cover, not contain: at 118px a letterboxed pack shot is mostly empty box.
   The upload already fits the whole product inside a 480² frame
   (routes/admin.py::upload_product_image), so there is padding to crop into. */
.dp-photo img{width:100%;height:100%;object-fit:cover;display:block}
.dp-photo .dp-ph{font-size:30px;line-height:1}
.dp-badge{position:absolute;top:5px;left:5px;background:var(--amber);color:#fff;
font-size:9px;font-weight:700;padding:1px 7px;border-radius:9px;
box-shadow:0 1px 4px rgba(0,0,0,.15)}
.dp-body{padding:7px 9px 9px}
/* Two lines then ellipsis: a long name must not make one card taller than the
   rest of the shelf. */
.dp-name{font-size:11.5px;font-weight:700;color:var(--text-dark);line-height:1.28;
display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.dp-en{display:none}
.dp-price{display:flex;align-items:baseline;gap:4px;flex-wrap:wrap;margin-top:4px}
.dp-price b{font-size:14px;font-weight:800;color:var(--green-dark)}
.dp-price .dp-mrp{font-size:10px;color:var(--text-soft);text-decoration:line-through}
.dp-price .dp-off{font-size:9.5px;font-weight:700;color:#c0392b}
.dp-unit{font-size:10px;color:var(--text-soft);margin-top:1px}
@media(min-width:721px){
.dp-card{flex-basis:140px}
.dp-photo{height:96px}
.dp-name{font-size:12.5px}
.dp-en{display:block;font-size:10px;font-weight:600;color:var(--text-soft);margin-top:1px}
.dp-price b{font-size:15px}
}
"""


def _product_cards(products: list, limit: int = 4) -> str:
    """A dealer's catalogue as a swipeable shelf. "" when he has listed nothing,
    so a dealer with no products renders exactly as he did before.

    `limit` is now about honesty rather than height — the strip costs the same
    vertical space at 2 items or 12 — so it stays, but generously: the kharidar
    page passes 8, and a farmer who has decided to ring someone wants the whole
    stock list.
    """
    items = [p for p in (products or []) if p.get("active", True)][:limit]
    if not items:
        return ""
    out = []
    for p in items:
        pid = int(p.get("id") or 0)
        # Root-relative on purpose, and it only works because _redirects proxies
        # /dukanlisting/product-image/* to the backend — on krashimitra.in this
        # page is itself a proxy of the Render host, so an unproxied path here
        # asks Netlify for a file it does not have and the photo silently
        # vanishes. That is exactly how it shipped broken once.
        photo = (f'<img src="/dukanlisting/product-image/{pid}.webp?v={p.get("v", 0)}" '
                 f'alt="{escape(p.get("name_hi", ""))}" loading="lazy" '
                 f'decoding="async" width="118" height="80">'
                 if p.get("has_image") else '<span class="dp-ph">📦</span>')
        badge = (f'<span class="dp-badge">{escape(p["badge"])}</span>'
                 if p.get("badge") else "")
        # Only strike an MRP through when it actually beats the price —
        # dealer_products.off_pct returns 0 otherwise, and "0% off" next to an
        # unchanged number reads as a lie about a saving.
        mrp = (f'<span class="dp-mrp">₹{p["mrp"]}</span>' if p.get("off") else "")
        off = (f'<span class="dp-off">{p["off"]}% off</span>' if p.get("off") else "")
        en = (f'<span class="dp-en">{escape(p["name_en"])}</span>'
              if p.get("name_en") else "")
        unit = (f'<div class="dp-unit">{escape(p["unit_hi"])}</div>'
                if p.get("unit_hi") else "")
        out.append(f"""<div class="dp-card">
<div class="dp-photo">{badge}{photo}</div>
<div class="dp-body">
<div class="dp-name">{escape(p.get('name_hi', ''))}</div>{en}
<div class="dp-price"><b>₹{p.get('price', 0)}</b>{mrp}{off}</div>
{unit}
</div>
</div>""")
    return f'<div class="dp-shelf">{"".join(out)}</div>'


# The sample card's photo. A real photograph, not the drawn bag that was here
# before: the block's whole claim is "your product will look like this", and a
# cartoon undersells the thing being sold.
#
# Served from frontend/images/ — root-relative, which resolves on both hosts
# (Netlify serves frontend/ at the root on krashimitra.in; main.py mounts the
# same directory at "/" on the Render domain). Deliberately no brand on the
# pack: this is our sample, printed next to a price we invented, so it must not
# put a real manufacturer's name behind that number.
#
# Cropped to 240px square (~15 KB) rather than reusing the 1200px original —
# it renders at 72–100px and this block is on ~10,000 pages.
_PACK_IMG = (
    '<img src="/images/seeds/wheat-seed-hd2967-card.webp" '
    'alt="नमूना प्रोडक्ट फोटो — गेहूं बीज" '
    'width="240" height="240" loading="lazy" decoding="async">'
)


_DKP_CSS = """
/* DEALER PROMO — the server twin of frontend/dukan-promo.js (.kmdp-*),
   rendered into the ~10,000 SEO pages. Same classes, same layout, same copy;
   change one and change the other.

   It teaches rather than advertises: most people who see it have never heard
   of the feature, and the one-line amber strip this replaced named a price
   without ever saying what you got for it. The sample product card is the
   load-bearing part — it is the thing being sold, so showing one beats any
   sentence about it.

   The block now sits directly under the MSP card, above the mandi table the
   farmer came for, and 98% of this traffic is a phone. So the PHONE layout is
   the real one and it is built to stay small: the sample card floats as a
   104px thumbnail with the copy wrapping around it, which costs about a third
   of a screen instead of a screenful. The two-column desktop version below is
   the variant, not the other way round.

   Still amber, so that to the farmer who is most of this traffic it reads as
   "not for you" at a glance. */
.kmdp{margin:16px 0;padding:15px;box-sizing:border-box;
background:linear-gradient(135deg,#fffdf6 0%,#fdf6e3 100%);
border:1px solid #f0dfae;border-radius:var(--radius-md);
box-shadow:0 2px 14px rgba(120,95,20,.07)}
.kmdp-eyebrow{display:inline-flex;align-items:center;gap:6px;margin-bottom:8px;
background:rgba(233,168,37,.18);border:1px solid rgba(233,168,37,.42);
color:#7a5200;font-size:11px;font-weight:800;padding:3px 10px;border-radius:20px}
.kmdp-demo{float:right;width:104px;margin:0 0 10px 12px;text-align:center}
.kmdp-h{font-size:16px;font-weight:800;line-height:1.35;
color:var(--green-dark);margin:0 0 5px}
.kmdp-p{font-size:12.5px;line-height:1.55;color:#5b4a1e;margin:0 0 9px}
.kmdp-list{list-style:none;padding:0;margin:0 0 12px;display:grid;gap:5px}
/* The ✓ is positioned, not a flex item: as flex, the <b> lead and the rest of
   the sentence became two columns and every line broke mid-phrase. */
.kmdp-list li{position:relative;padding-left:23px;font-size:12px;
line-height:1.45;color:var(--text-mid)}
.kmdp-list li::before{content:'✓';position:absolute;left:0;top:1px;
width:16px;height:16px;border-radius:50%;
background:var(--green-mid);color:#fff;font-size:9.5px;font-weight:800;
display:flex;align-items:center;justify-content:center}
.kmdp-list b{color:var(--green-dark);font-weight:700}
/* clear:both so the button never tucks beside the float and loses half its width */
.kmdp-cta{display:flex;align-items:center;justify-content:center;gap:8px;clear:both;
background:var(--green-dark);color:#fff;text-decoration:none;font-size:14px;
font-weight:800;padding:11px 20px;border-radius:24px;box-sizing:border-box}
.kmdp-cta:hover{background:var(--green-mid)}
.kmdp-fine{display:block;margin-top:8px;font-size:11px;color:#8a7a4e;text-align:center}
.kmdp-card{background:var(--white);border:1px solid var(--border);border-radius:12px;
overflow:hidden;box-shadow:0 3px 12px rgba(20,40,30,.12)}
.kmdp-photo{position:relative;height:72px;background:#f6f3e9;display:flex;
align-items:center;justify-content:center;overflow:hidden}
/* contain, exactly like .dp-photo img on the real card: a pack shot that gets
   centre-cropped loses its label, so the sample must not crop either. */
.kmdp-photo img{max-height:100%;max-width:100%;object-fit:contain;display:block}
.kmdp-badge{position:absolute;top:5px;left:5px;background:var(--amber);color:#fff;
font-size:9px;font-weight:700;padding:1px 7px;border-radius:10px}
.kmdp-cbody{padding:7px 8px 9px;text-align:left}
.kmdp-cname{font-size:11.5px;font-weight:700;color:var(--text-dark);line-height:1.3}
.kmdp-cen{display:block;font-size:9px;font-weight:600;color:var(--text-soft);margin-top:1px}
.kmdp-cprice{display:flex;align-items:baseline;gap:4px;flex-wrap:wrap;margin-top:5px}
.kmdp-cprice b{font-size:14px;font-weight:800;color:var(--green-mid)}
.kmdp-cmrp{font-size:10px;color:var(--text-soft);text-decoration:line-through}
.kmdp-coff{font-size:9.5px;font-weight:700;color:#c0392b}
.kmdp-cunit{font-size:10px;color:var(--text-soft);margin-top:2px}
.kmdp-cap{font-size:10px;color:#8a7a4e;margin:5px 0 0;line-height:1.35}
@media(min-width:721px){
.kmdp{margin:22px 0;padding:18px 20px}
.kmdp-in{display:flex;gap:20px;align-items:center}
.kmdp-body{flex:1;min-width:0}
/* order:2 keeps the card on the right where the copy reads first; the markup
   leads with it because the phone float needs it before the text it wraps. */
.kmdp-demo{float:none;flex:none;width:166px;margin:0;order:2}
.kmdp-h{font-size:17px;margin-bottom:6px}
.kmdp-p{font-size:13px;line-height:1.6;margin-bottom:11px}
.kmdp-list{gap:5px;margin-bottom:14px}
.kmdp-list li{font-size:12.5px;line-height:1.5}
.kmdp-cta{display:inline-flex;padding:10px 20px}
.kmdp-fine{text-align:left}
.kmdp-photo{height:100px}
.kmdp-cname{font-size:12.5px}
.kmdp-cprice b{font-size:15.5px}
.kmdp-cap{font-size:11px;margin-top:8px}}
"""


def _dukan_pitch(where: str = "") -> str:
    """The supply-side ask: "you sell this — show it here".

    One function for every /bhav tier so the price and the copy live in exactly
    one place, and the server twin of frontend/dukan-promo.js so a trader sees
    the same block whichever page he lands on.

    Before this, /dukanlisting was reachable from the bhav tree only through
    surfaces that require a paying dealer to already exist (the Tier-3 panel
    renders nothing when empty; the kharidar page is gated by _has_kharidar and
    ships noindex until a district has a listing). With zero dealers that is a
    closed loop: the acquisition page was invisible on the highest-traffic
    surface the site has, which is also the one place a trader is definitely
    standing.

    `where` names the place when we have one — "Hardoi के किसान" outperforms
    "हजारों किसान" because a trader recognises his own district.

    The hook is the farmer's NEXT question, not our price: he has just read
    today's rate, and what follows it is "खाद-बीज कहां से लूं?". That is the
    moment this block interrupts, which is why it now sits directly under the
    MSP card on every tier rather than down by the footer.
    """
    line = (f'{escape(where)} के किसान रोज़ यहां अपना भाव देखते हैं'
            if where else 'हर दिन हजारों किसान यहां अपने जिले का भाव देखते हैं')
    return f"""<aside class="kmdp">
<span class="kmdp-eyebrow">🏪 दुकानदारों के लिए</span>
<div class="kmdp-in">
<div class="kmdp-demo">
<div class="kmdp-card">
<div class="kmdp-photo"><span class="kmdp-badge">बीज</span>{_PACK_IMG}</div>
<div class="kmdp-cbody">
<div class="kmdp-cname">गेहूं बीज HD-2967</div>
<span class="kmdp-cen">Wheat Seeds HD-2967</span>
<div class="kmdp-cprice"><b>₹280</b><span class="kmdp-cmrp">₹350</span><span class="kmdp-coff">20% off</span></div>
<div class="kmdp-cunit">5 kg बैग</div>
</div>
</div>
<p class="kmdp-cap">↑ ऐसा दिखेगा आपका प्रोडक्ट</p>
</div>
<div class="kmdp-body">
<h2 class="kmdp-h">अपनी दुकान किसानों तक पहुंचाएं</h2>
<p class="kmdp-p">{line} — और भाव देखने के बाद उनका अगला सवाल होता है
“खाद-बीज कहां से लूं?”। आपके प्रोडक्ट ठीक उसी जगह, इसी तरह दिखेंगे।</p>
<ul class="kmdp-list">
<li><b>नाम, आपकी कीमत, MRP और छूट</b> — बिल्कुल दुकान जैसा कार्ड</li>
<li><b>कोई कमीशन नहीं</b> — किसान सीधे आपको फोन करता है</li>
<li><b>₹199 जिला + ₹50 प्रति फसल</b> — प्रति सीज़न (3 महीने) · जितने पेज, उतना पैसा</li>
</ul>
<a class="kmdp-cta" href="/dukanlisting">अपनी दुकान लिस्ट करें →</a>
<span class="kmdp-fine">व्यापारी · आढ़तिया · खाद-बीज डीलर · FPO · मिल</span>
</div>
</div>
</aside>"""


def _dealer_teaser_html(cs: str, ss: str, state: str, ds: str = "") -> str:
    """The paid dealer panel: up to 3 shops, name and products only, never a
    phone number.

    Serves BOTH products, told apart by `ds`:
        ds == ""   the state page  /bhav/{crop}/{state}          ₹999/month
        ds != ""   a district page /bhav/{crop}/{state}/{dist}   ₹199+₹50/crop

    Who appears is services/placements.py — one row per (page, slot), so the
    two pages are genuinely separate inventory and a dealer can hold rank 1 on
    his district while somebody else holds rank 1 on the state. It used to be
    one `bhav_rank` column shared across a whole state, which could express
    neither.

    A farmer who wants the number clicks "पूरी जानकारी..." through to the full
    /kharidar page for that dealer's own district — still krashimitra.in, never
    off-site, which is the whole point of withholding it here rather than
    building a separate contact-request flow.
    """
    rows = placements.for_page(cs, ss, ds)
    if not rows:
        # Nothing to show, and nothing to say either: _dukan_pitch already runs
        # directly under the MSP card on this page, so the empty-directory ask
        # it used to make from here would now be the same block twice.
        return ""

    cards = []
    for b in rows:
        label, emoji = buyers.kind_label(b.get("kind"))
        tick = '<span class="bp-tick">✓ सत्यापित</span>' if b.get("verified") else ""
        crops = "".join(f'<span class="bp-crop">{escape(_hindi_name(c))}</span>'
                        for c in (b.get("commodities") or [])[:5])
        if not b.get("commodities"):
            crops = '<span class="bp-crop">सभी फसलें</span>'
        district = b.get("district") or ""
        # NOT `ds` — that is the page we are rendering, and this is the dealer's
        # own district, which is where his full card with the phone number lives.
        his_ds = _slugify(district)
        link = f"/bhav/{cs}/{ss}/{his_ds}/kharidar" if his_ds else f"/bhav/{cs}/{ss}"
        # His catalogue, if he has typed one. Prices are the whole reason a
        # farmer reads this block, so they sit above the "see contact" link
        # rather than behind it — the number is what stays one click away.
        products = _product_cards(b.get("products"), limit=4)
        cards.append(f"""<div class="bp-card">
<span class="bp-ic">{emoji}</span>
<div class="bp-body">
<div class="bp-name">{escape(b.get('name', ''))}{tick}</div>
<div class="bp-kind">{escape(label)} · {escape(district)}</div>
<div class="bp-crops">{crops}</div>
{products}
<a class="bp-link" href="{link}">पूरी जानकारी व संपर्क नंबर देखें →</a>
</div>
</div>""")

    # Named after the page it is on, not after the dealer's own district: on a
    # district page "Bijnor में सत्यापित दुकानें" is the whole promise, and on
    # the state page naming the state is what makes three shops feel chosen
    # rather than arbitrary.
    where = escape(_hindi_state(state))
    if ds:
        here = _get_index().get("dists", {}).get(cs, {}).get(ss, {}).get(ds, "")
        where = escape(here or ds)
    return f"""<section class="bp-wrap">
<div class="bp-h"><h2>{where} में सत्यापित दुकानें</h2><p class="bp-sub">इनके प्रोडक्ट और भाव — सीधे दुकानदार से</p></div>
<div class="bp-list">{"".join(cards)}</div>
<p class="bp-warn">ये दुकानें भुगतान करके यहां लिस्ट हैं — यह हमारी सिफ़ारिश नहीं है।
हमने सिर्फ फोन करके इनकी पहचान जांची है, माल या व्यवहार की नहीं। सौदा करने से पहले
सामान खुद देख लें, पक्की रसीद लें और अग्रिम भुगतान में सावधानी रखें।
<a href="/terms#dealer-terms">शर्तें</a></p>
<a class="bp-cta" href="/dukanlisting">अपनी दुकान यहां लिस्ट करें →</a>
</section>"""


# Which places have a live Krashi Bazar buy post, cached briefly. The tier-4
# page and the sitemap both need this ~14,000 times per render pass; one query
# every few minutes answers all of them. Short TTL, not the index's 6h: a new
# buy post should surface the खरीदार link on price pages the same session, not
# tomorrow. The kharidar page itself always queries live, so what a farmer sees
# once he lands there is never stale.
_KH_PLACES_TTL = 300
_kh_places: set | None = None
_kh_places_at: float = 0.0


def _kharidar_places() -> set:
    global _kh_places, _kh_places_at
    now = time.time()
    if _kh_places is not None and now - _kh_places_at < _KH_PLACES_TTL:
        return _kh_places
    db = SessionLocal()
    try:
        _kh_places = bazar.place_keys(db, "buy")
    except Exception as e:
        logger.warning("kharidar place keys failed: %s", e)
        _kh_places = _kh_places or set()
    finally:
        db.close()
    _kh_places_at = now
    return _kh_places


def _has_kharidar(cs: str, state: str, district: str) -> bool:
    """True when /bhav/{crop}/{state}/{district}/kharidar has something on it —
    a seeded dealer or a Bazar buy post. Gates both the price-page link and the
    sitemap entry, so neither can point at a page we render noindex."""
    if buyers.has_any(cs, state, district):
        return True
    key = (cs.strip().lower(),
           " ".join((state or "").split()).lower(),
           " ".join((district or "").split()).lower())
    return key in _kharidar_places()


def _bazar_slice(post_type: str, cs: str, state: str, district: str,
                 limit: int = 20) -> list:
    """This district's slice of the Krashi Bazar feed, as plain dicts.

    The kharidar page is a SUBSET of /krashi_bajar — same rows, narrowed to one
    crop and one district — so it goes through bazar.place_posts rather than
    writing a second query that could drift from the feed's own definition of
    "active". Dicts, not ORM objects: the session closes before the template
    renders and detached instances would raise on attribute access.
    """
    db = SessionLocal()
    try:
        rows = bazar.place_posts(db, post_type, cs, state, district, limit)
        out = []
        for p in rows:
            author = bazar._author_info(
                db.query(User).filter(User.id == p.users_id).first(),
                db.query(UserProfile).filter(UserProfile.user_id == acct(p.users_id)).first())
            out.append({
                "id": p.id, "text": p.text or "", "price": p.price,
                "quantity": p.quantity, "unit": p.unit or "क्विंटल",
                "created_at": p.created_at, "name": author.get("name") or "किसान",
                "verified": author.get("verified"), "location": p.location or "",
            })
        return out
    except Exception as e:
        # A price page must never 500 because the social feed had a bad day.
        logger.warning("bazar slice failed (%s/%s/%s): %s", cs, state, district, e)
        return []
    finally:
        db.close()


def _sell_intent(commodity: str, cs: str, state: str, district: str,
                 days: int = 60) -> int:
    """How many farmers have asked to SELL this crop in this district lately.

    This is the number the खरीदार page is actually selling. A dealer does not
    pay ₹500 for a listing on a directory; he pays because "इस जिले में 14
    किसानों ने गेहूं बेचने के लिए कहा है" is a queue with his name on it. The
    click that follows is what lead_clicks counts — this is the supply behind it.

    Two sources, because the ask moved. It used to arrive only as a crop_appeals
    row from the form this page carried; the बेचना है door now goes straight to
    Krashi Bazar, so new supply lands as an active sell post instead. Counting
    only the old table would have let this line decay to zero over 60 days while
    the supply behind it was growing.

    A count, never the rows: names and numbers belong to the farmers who typed
    them, and a public page listing who has grain sitting at home is not
    something we would want done to us. 60 days because a farmer who wrote in
    last month is still holding the crop; a harvest does not move on a 30-day
    boundary.
    """
    if not (commodity and district):
        return 0
    db = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(days=days)
        n = (db.query(func.count(CropAppeal.id))
               .filter(CropAppeal.kind == "sell",
                       CropAppeal.commodity == commodity,
                       CropAppeal.district == district,
                       CropAppeal.created_at >= cutoff)
               .scalar() or 0)
        if cs:
            # Same place-matching as bazar.place_posts, so this count and the
            # listings the page shows can never disagree about which rows are
            # "in this district".
            q = (db.query(func.count(BazarPost.id))
                   .filter(BazarPost.post_type == "sell",
                           BazarPost.status == "active",
                           func.lower(BazarPost.crop_slug) == bazar._norm_place(cs),
                           func.lower(BazarPost.district) == bazar._norm_place(district),
                           BazarPost.created_at >= cutoff))
            if state:
                q = q.filter(func.lower(BazarPost.state) == bazar._norm_place(state))
            n += q.scalar() or 0
        return n
    except Exception as e:
        # Same rule as the bazar slice: the page must not 500 over a side panel.
        logger.warning("sell intent failed (%s/%s): %s", commodity, district, e)
        return 0
    finally:
        db.close()


def _bazar_card(p: dict, hi: str) -> str:
    """One Krashi Bazar 'खरीदना है' post rendered as a buyer card.

    No phone number and no direct call button: unlike a seeded dealer, this
    person never agreed to have their number published on an indexable page.
    The contact route is their Bazar post, where our existing offer/comment flow
    already gates contact behind a login."""
    bits = []
    if p.get("quantity"):
        bits.append(f'{int(p["quantity"]):,} {escape(p.get("unit") or "क्विंटल")}')
    if p.get("price"):
        bits.append(f'₹{int(p["price"]):,} तक')
    meta = " · ".join(bits)
    when = _hindi_date(p["created_at"].date()) if p.get("created_at") else ""
    tick = '<span class="kh-tick">✓ सत्यापित</span>' if p.get("verified") else ""
    return (f'<article class="kh-card kh-bz">'
            f'<div class="kh-head"><span class="kh-ic">🛒</span>'
            f'<span class="kh-id">'
            f'<span class="kh-name">{escape(p.get("name",""))}{tick}</span>'
            f'<span class="kh-kind">खरीदना है'
            + (f' · {escape(p["location"])}' if p.get("location") else "")
            + (f' · {escape(when)}' if when else "")
            + '</span></span></div>'
            + (f'<div class="kh-meta">{meta}</div>' if meta else "")
            + (f'<p class="kh-desc">{escape(p["text"][:240])}</p>' if p.get("text") else "")
            + f'<div class="kh-acts">'
              f'<a class="kh-btn kh-bzbtn" href="/krashi_bajar.html?post={p["id"]}">'
              f'कृषि बाज़ार में देखें →</a></div>'
              '</article>')


def _buyer_card(b: dict, c_slug: str) -> str:
    """One listing. Phone is a plain tel: (a redirect can't help a dialler);
    WhatsApp routes through /kharidar/go/<id> so the click is measurable — the
    number we'd have to quote before charging anyone per lead."""
    label, emoji = buyers.kind_label(b.get("kind"))
    tel, wa = buyers.phone_of(b), buyers.wa_of(b)
    bid = escape(b.get("id", ""))

    tick = ('<span class="kh-tick">✓ सत्यापित</span>' if b.get("verified") else "")
    feat = ('<span class="kh-feat-tag">प्रमुख</span>' if b.get("featured") else "")
    where = " · ".join(x for x in [escape(b.get("market") or ""),
                                   escape(b.get("district") or "")] if x)
    since = (f" · {escape(str(b.get('since')))} से" if b.get("since") else "")

    crops = "".join(f'<span class="kh-crop">{escape(_hindi_name(c))}</span>'
                    for c in (b.get("commodities") or [])[:6])
    if not b.get("commodities"):
        crops = '<span class="kh-crop">सभी फसलें</span>'

    acts = []
    if tel:
        acts.append(f'<a class="kh-btn kh-call" href="tel:{escape(tel)}" '
                    f'data-kh="{bid}" data-kh-ch="call">📞 कॉल करें</a>')
    if wa:
        # Just "WhatsApp": the button is half a phone wide now, and the brand
        # name alone is unambiguous — "पर बात करें" only cost it a second line.
        acts.append(f'<a class="kh-btn kh-wa" href="/kharidar/go/{bid}" '
                    f'data-kh="{bid}" data-kh-ch="wa" rel="nofollow" target="_blank">'
                    f'WhatsApp</a>')

    return (f'<article class="kh-card{" feat" if b.get("featured") else ""}">'
            f'<div class="kh-head"><span class="kh-ic">{emoji}</span>'
            f'<span class="kh-id">'
            f'<span class="kh-name">{escape(b.get("name",""))}{tick}{feat}</span>'
            f'<span class="kh-kind">{escape(label)}{" · " + where if where else ""}{since}</span>'
            f'</span></div>'
            f'<div class="kh-crops">{crops}</div>'
            # `description` — the dealer's own blurb. Was `note`, which is the
            # admin's private call log (dealers.py::log_call appends to it), so
            # "[04 Aug] wants a discount" was being published to farmers under
            # the dealer's own name. `note` is no longer in the public dict.
            + (f'<p class="kh-desc">{escape(b.get("description"))}</p>'
               if b.get("description") else "")
            # The full catalogue here — this is the page a farmer lands on when
            # he has decided to ring someone, so more of it is useful.
            + _product_cards(b.get("products"), limit=8)
            + f'<div class="kh-acts{" one" if len(acts) == 1 else ""}">'
            f'{"".join(acts)}</div>'
            '</article>')


_KH_JS = ("<script>document.querySelectorAll('[data-kh]').forEach(function(a){"
          "a.addEventListener('click',function(){try{gtag('event','buyer_click',"
          "{buyer_id:a.getAttribute('data-kh'),channel:a.getAttribute('data-kh-ch')});}"
          "catch(e){}});});</script>")


@router.get("/kharidar/go/{buyer_id}")
def kharidar_redirect(buyer_id: str, request: Request, background: BackgroundTasks):
    """Tracked hop to a listing's WhatsApp. The click is persisted to lead_clicks
    on top of the GA event, so lead volume is provable from our own data when it
    comes time to price a listing — that number is the whole pitch. Recorded in
    the background, after the redirect. Unknown id falls back to /bhav."""
    b = buyers.by_id(buyer_id)
    if not b:
        return RedirectResponse("/bhav", status_code=302)
    num = re.sub(r"\D", "", buyers.wa_of(b))
    logger.info("buyer_click id=%s district=%s", buyer_id, b.get("district", "-"))
    if not num:
        return RedirectResponse("/bhav", status_code=302)
    background.add_task(
        lead_clicks.record, "buyer", buyer_id,
        label      = b.get("name"),
        category   = b.get("kind"),
        district   = b.get("district"),
        referer    = request.headers.get("referer", ""),
        user_agent = request.headers.get("user-agent"),
    )
    return RedirectResponse(f"https://wa.me/{num}", status_code=302)


@router.get("/bhav/{c_slug}/{s_slug}/{d_slug}/kharidar", response_class=HTMLResponse)
def bhav_kharidar(c_slug: str, s_slug: str, d_slug: str):
    idx = _get_index()
    cs, ss, ds = c_slug.lower(), s_slug.lower(), d_slug.lower()

    commodity = idx.get("crops", {}).get(cs)
    state     = idx.get("states", {}).get(cs, {}).get(ss)
    district  = idx.get("dists", {}).get(cs, {}).get(ss, {}).get(ds)
    if not (commodity and state and district):
        return _not_found(idx, cs, ss)

    hi, hi_state = _hindi_name(commodity), _hindi_state(state)
    canon = f"{SITE}/bhav/{cs}/{ss}/{ds}/kharidar"
    price_url = f"/bhav/{cs}/{ss}/{ds}"

    # Today's price is the context the whole page hangs on — a buyer list means
    # nothing without the number the farmer should be holding out for.
    prices = _rows_for(commodity, state=state, district=district) \
        or _rows_for_district(idx, cs, ss, ds)
    st = _stats(prices) if prices else {"avg": None, "lo": None, "hi": None, "n": 0}
    fresh_iso = _fresh_iso(idx, cs, ss, ds)
    as_of_hi  = _as_of_hi(fresh_iso)   # dates the price below, not the visit

    # Two sources, one page: hand-verified dealers we sell listings to, and the
    # district's slice of Krashi Bazar. Dealers pin above because they are the
    # paid slot AND the only entries someone has actually spoken to.
    rows = buyers.for_place(cs, state, district)
    bz = _bazar_slice("buy", cs, state, district)
    total = len(rows) + len(bz)

    price_note = (
        f'<div class="kh-note">📊 {as_of_hi} को {escape(district)} में <b>{escape(hi)}</b> का औसत मंडी भाव '
        f'<b>₹{st["avg"]:,}/क्विंटल</b> था — सौदा करने से पहले यही दाम ध्यान में रखें। '
        f'<a href="{price_url}">मंडीवार भाव देखें →</a></div>'
        if st["avg"] else
        f'<div class="kh-note">📊 <a href="{price_url}">{escape(district)} में {escape(hi)} '
        f'का आज का भाव देखें →</a></div>')

    # Supply-side acquisition: this page IS the pitch to a trader/dealer, and
    # WhatsApp is the only channel they will actually use. The prefilled message
    # names the district and crop so we know which slot they want.
    join_msg = quote(f"नमस्ते, मुझे कृषि मित्र पर {district} ({state}) में "
                     f"{hi} खरीदार के रूप में अपना नाम जोड़वाना है।")
    # The other half of the page. Everything above answers "who will buy it";
    # this is "I have it" — and it now goes where that sentence can actually be
    # acted on. The in-page composer this used to open is gone: Krashi Bazar's
    # seller tab is the same post, with the photo picker, the login gate and the
    # farmer's own listings around it.
    n_sell = _sell_intent(commodity, cs, state, district)
    intent_line = (
        f'<p class="kh-sell-n">🌾 पिछले दो महीनों में <b>{n_sell} किसानों</b> ने '
        f'{escape(district)} में {escape(hi)} बेचने के लिए कहा है।</p>'
        if n_sell else "")
    # An empty district must not be told his crop is going in front of buyers
    # that are not there. Both wordings are the same promise, honestly sized.
    sell_sub = (f'यह ऊपर दिए {escape(district)} के खरीदारों और कृषि बाज़ार, '
                f'दोनों तक पहुंचेगी।' if total else
                f'यह कृषि बाज़ार पर दिख जाएगी, और {escape(district)} में खरीदार '
                f'जुड़ते ही सबसे पहले यही सूची उन्हें दिखाई जाएगी।')
    sell_cta = (
        f'<section class="kh-sell"><h2>🌾 आपको {escape(hi)} बेचना है?</h2>'
        f'<p>कृषि बाज़ार पर अपनी फसल की पोस्ट डालें — मात्रा, भाव और फोटो के साथ। '
        f'{sell_sub}</p>'
        f'{intent_line}'
        f'<a class="kh-sell-btn" href="{_BAZAR_SELL}">'
        f'कृषि बाज़ार पर फसल डालें →</a></section>')

    # Two doors, because a trader browsing at 11pm will not wait for a reply and
    # a trader standing in a mandi will not fill a form. The form is primary: it
    # lands in the admin queue as a row (database/db.py::Buyer) instead of a
    # message someone has to transcribe before it can be acted on.
    join = (f'<section class="kh-join"><h2>🧾 आप {escape(hi)} खरीदते हैं?</h2>'
            f'<p>अपने प्रोडक्ट इसी पेज पर दिखाएं — नाम, आपकी कीमत, MRP और छूट के साथ, '
            f'बिल्कुल ऊपर वाले कार्ड की तरह। शुरुआती ऑफर: ₹199 जिला + ₹50 प्रति फसल प्रति सीज़न, '
            f'हर अतिरिक्त जिला +₹50। '
            f'हम कॉल करके पुष्टि के बाद ही लिस्टिंग लाइव करते हैं।</p>'
            f'<a href="{SITE}/dukanlisting">अपनी दुकान लिस्ट करें →</a>'
            f'<a class="kh-join-wa" href="https://wa.me/919870951001?text={join_msg}" '
            f'rel="nofollow" target="_blank">या WhatsApp पर बात करें</a></section>')

    if total:
        parts = []
        if rows:
            parts.append('<h2 class="kh-h">सत्यापित खरीदार / डीलर</h2>'
                         f'<div class="kh-list">'
                         f'{"".join(_buyer_card(b, cs) for b in rows)}</div>')
        if bz:
            parts.append('<h2 class="kh-h">कृषि बाज़ार से — इसी जिले की मांग</h2>'
                         f'<div class="kh-list">'
                         f'{"".join(_bazar_card(p, hi) for p in bz)}</div>')
        listing = "".join(parts)
        robots = ""
        n_txt = f"{total} खरीदार"
        item_ld = {"@context": "https://schema.org", "@type": "ItemList",
                   "name": f"{hi} खरीदार — {district} ({state})",
                   "numberOfItems": total,
                   "itemListElement": [
                       {"@type": "ListItem", "position": i + 1, "name": n}
                       for i, n in enumerate([b.get("name", "") for b in rows]
                                             + [p.get("name", "") for p in bz])]}
    else:
        listing = ('<div class="kh-empty"><h2>अभी इस जिले में कोई खरीदार नहीं जुड़ा</h2>'
                   '<p>हम व्यापारियों और डीलरों से बात करके ही उन्हें यहां जोड़ते हैं — '
                   'बिना जांचे कोई नंबर नहीं दिखाते। कृषि बाज़ार पर इस जिले में अभी कोई '
                   'खरीद की मांग भी नहीं आई है। नीचे अपनी फसल की जानकारी डालें — '
                   'खरीदार आने पर वहीं दिखेगी।</p></div>')
        # Not indexable until it has something to say. This is the guard that
        # keeps a 14k-page programmatic surface from becoming 14k thin pages.
        robots = "noindex,follow"
        n_txt = "खरीदार सूची"
        item_ld = None

    faqs = [
        (f"{district} में {hi} कौन खरीदता है?",
         (f"{district} ({hi_state}) में {hi} खरीदने वाले {total} खरीदार कृषि मित्र पर "
          f"सूचीबद्ध हैं — सत्यापित व्यापारी/डीलर और कृषि बाज़ार पर आई खरीद की मांग।"
          if total else
          f"{district} में {hi} आमतौर पर स्थानीय मंडी के आढ़तिया और व्यापारी खरीदते हैं। "
          f"कृषि मित्र इस जिले के सत्यापित खरीदारों की सूची तैयार कर रहा है।")),
        (f"बेचने से पहले {hi} का सही भाव कैसे पता करें?",
         (f"आज {district} में {hi} का औसत मंडी भाव ₹{st['avg']:,} प्रति क्विंटल है "
          if st["avg"] else "")
         + "किसी भी सौदे से पहले उस दिन का सरकारी मंडी भाव देख लें, और भाड़ा घटाकर "
           "नेट भाव निकालें — दूर की ऊंचे भाव वाली मंडी भाड़े के बाद कम बैठ सकती है।"),
        ("क्या कृषि मित्र खुद फसल खरीदता है?",
         "नहीं। कृषि मित्र सिर्फ किसान और खरीदार को जोड़ता है — न फसल खरीदता है, "
         "न पैसे का लेन-देन करता है। सौदा, तौल और भुगतान की शर्तें आपस में तय करें।"),
    ]
    faq_html, faq_ld = _faq(faqs)
    ld_blocks = [faq_ld, _crumb_ld([
        ("कृषि मित्र", f"{SITE}/"), ("मंडी भाव", f"{SITE}/bhav"),
        (hi, f"{SITE}/bhav/{cs}"), (hi_state, f"{SITE}/bhav/{cs}/{ss}"),
        (district, f"{SITE}{price_url}"), (f"{hi} खरीदार", canon)])]
    if item_ld:
        ld_blocks.insert(0, item_ld)
    ld = _ld(*ld_blocks)

    t_hi, _t_en, _same = _title_names(commodity)
    # Same shared-district-name collision as the price page above it.
    kh_place = f"{district}, {hi_state}" if _ambiguous_district(idx, cs, ds) else district
    title = _fit(
        f"{kh_place} मंडी में {t_hi} कौन खरीदेगा — खरीदार और भाव",
        f"{kh_place} में {t_hi} कौन खरीदेगा — खरीदार",
        f"{kh_place} में {t_hi} कौन खरीदेगा",
        f"{district} में {t_hi} कौन खरीदेगा",
        # Last resort for the commodities with no Hindi name, where t_hi is a
        # 30-character English phrase and the sentence form cannot fit at all.
        f"{t_hi} खरीदार — {district}")
    desc = _fit(
        f"{district} ({hi_state}) में {t_hi} खरीदने वाले सत्यापित व्यापारी और डीलर — "
        f"नाम, फसल और सीधा संपर्क। आज का मंडी भाव भी साथ में।",
        f"{district} में {t_hi} खरीदने वाले सत्यापित व्यापारी और डीलर — "
        f"नाम, फसल और सीधा संपर्क। आज का मंडी भाव भी साथ में।",
        limit=162)

    # State-language pass — services/state_lang.py. Included for consistency
    # rather than for traffic: with buyers.json still holding one inactive row,
    # every one of these pages is noindex today, so this is what makes the
    # Marathi wording already correct on the day a district is seeded.
    lang = state_lang.lang_for(state)
    _lv = {"crop": state_lang.crop(t_hi, lang), "place": kh_place,
           "district": district, "district_en": district, "state": hi_state,
           "state_en": state}
    _lt = state_lang.variants("titles", "kharidar", lang, _lv)
    if _lt:
        title = _fit(*_lt)
    _ldc = state_lang.variants("descs", "kharidar", lang, _lv)
    if _ldc:
        desc = _fit(*_ldc, limit=162)
    kh_h1 = state_lang.h1("kharidar", lang,
                          {**_lv, "crop": state_lang.crop(hi, lang)},
                          f"{district} में {hi} कौन खरीदेगा?")

    body = f"""{_tier_head(escape(kh_h1),
                           f"📅 {as_of_hi} · {escape(hi_state)} · {n_txt}")}
{price_note}
{listing}
{sell_cta}
<div class="cta-row">
<a class="btn btn-app" href="{price_url}">📊 {escape(district)} का {escape(hi)} भाव</a>
{_net_price_cta(hi, cs, state, district)}
</div>
{join}
<h2>अक्सर पूछे जाने वाले सवाल</h2>
{faq_html}
<p class="kh-fine">कृषि मित्र यहां दी गई फर्मों का प्रतिनिधि नहीं है और किसी सौदे, तौल,
गुणवत्ता या भुगतान की गारंटी नहीं देता। सौदा करने से पहले खुद संतुष्ट हो लें।</p>
{_lead_gen_html()}
{_KH_JS}"""

    crumbs = (f'<a href="{SITE}/">कृषि मित्र</a> › <a href="{SITE}/bhav">मंडी भाव</a> › '
              f'<a href="{SITE}/bhav/{cs}">{escape(hi)}</a> › '
              f'<a href="{SITE}/bhav/{cs}/{ss}">{escape(hi_state)}</a> › '
              f'<a href="{SITE}{price_url}">{escape(district)}</a> › खरीदार')
    return _doc(title, desc, canon, crumbs, body, ld, _crop_image(commodity, 960),
                extra_css=_KH_CSS + _PRODUCT_CSS, robots=robots,
                updated=fresh_iso if st["avg"] else "", crop=cs, lang=lang)
