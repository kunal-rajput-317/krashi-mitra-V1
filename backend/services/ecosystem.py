# ============================================================
# services/ecosystem.py
# The link graph — "where does this farmer go next?"
#
# THE DEFECT THIS FIXES: every section of this site is a cul-de-sac. A /bhav
# district page links to /bhav. An article links to articles and to /bhav. The
# ~14,000 server-rendered pages that carry ~85% of the search traffic offered a
# reader exactly one onward move inside the thing he was already looking at,
# and the only route to /pashupalan, /rental, /ganna, /sawal or /naksha was the
# hamburger drawer — a menu nobody opens. Measured on 21 Aug 2026: ~200 new
# visitors a day against 10-20 returning. A farmer who arrives on one page,
# reads the one number he came for and leaves has met one page, not a product.
#
# THE MODEL: a page is not a destination, it is a position. Position is
# (section, crop, place, topic) — this module turns that into the next few
# honest moves, each one landing in a DIFFERENT section, each one carrying the
# crop and the place forward so the move after it is specific too:
#
#   /bhav/wheat/uttar-pradesh/bijnor  →  गेहूं में खाद कब और कितनी (article)
#     →  अंडे का रेट / किराये पर थ्रेशर / बिजनौर का नक्शा  →  …
#
# WHY THIS IS ONE MODULE AND NOT A BLOCK OF MARKUP PER SECTION
# -----------------------------------------------------------
# The instruction this was built to satisfy is "make it apply to every section
# built in future". A hand-written strip at the bottom of bhav.py would be a
# strip at the bottom of bhav.py; the next section would ship without one and
# nobody would notice for a month. So the graph is data, the rendering is one
# function, and BOTH page shells call it:
#
#   • bhav.py `_doc()` — the shell behind /bhav, /product, /ganna, /rental,
#     /naksha, /sawal, /pashupalan, /krashi_dukan, /pay, /credits.
#     A future section that renders through _doc() is in the ecosystem the day
#     it ships, with no line of its own. That is the whole design.
#   • tools/article_builder.py — the 176 static article pages and every one
#     written after them.
#
# A new section joins by adding one row to SECTIONS and (optionally) one
# provider function. tests/test_ecosystem.py fails if a live section is missing
# from SECTIONS, so "we forgot" is a red test rather than a silent dead end.
#
# HONESTY RULES, because a dead or lying link is worse than no link:
#   • Never link to a URL this module cannot show exists. Where depth cannot be
#     verified cheaply, it offers the hub — a real page — not a guessed slug.
#   • Never offer the section the reader is already in (`ctx.section`), nor one
#     the page already links to prominently (`ctx.have`).
#   • Never print a language the page is not written in. Hindi copy is the
#     fallback for Devanagari readers (see services/state_lang on why that is
#     safe for Marathi); for Tamil and Kannada a missing string drops the step
#     rather than showing Hindi under a Tamil heading.
#   • /weather serves UP districts only, so it is offered to UP and to readers
#     whose state we do not know — never to a Karnataka page.
#
# WHY THE SAME PAGE ALWAYS SHOWS THE SAME STEPS, AND NEIGHBOURING PAGES DO NOT
# ---------------------------------------------------------------------------
# Ties are broken by a hash of (this page, that target). Deterministic, so a
# crawler sees the same block on every visit and the strip is not churn; but
# different from URL to URL, so 14,000 pages do not all vote for the same four
# addresses and the block does not read as boilerplate.
#
# Pure functions. No FastAPI import, no DB import at module level — same
# contract as services/crop_types.py and services/state_lang.py, so the article
# builder can import it from the command line without booting the app. The one
# guarantee: nothing here raises. Every lookup that could fail is wrapped, and
# the failure mode is a shorter strip, never a 500 on a page that was working.
# ============================================================
from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass
from html import escape
from pathlib import Path

SITE = "https://krashimitra.in"

_ROOT = Path(__file__).resolve().parents[2]
_ARTICLES_DIR = _ROOT / "frontend" / "articles"


# ── the sections ───────────────────────────────────────────────────────────
#
# id → (hub URL, icon). The icon is a small real photo, not an emoji — one
# 96px WebP per section in frontend/images/journey/, cut from photos already
# credited on /articles/credits. The id is what ctx.section holds and what a provider
# registers under; `hub` is the always-safe destination for that section.
# ADD A ROW HERE WHEN A SECTION SHIPS — tests/test_ecosystem.py checks that
# every section the app serves is represented.

def _img(section_id: str) -> str:
    return f"/images/journey/{section_id}.webp"


@dataclass(frozen=True)
class Section:
    id: str
    hub: str
    icon: str


SECTIONS: dict[str, Section] = {s.id: s for s in (
    Section("bhav",       "/bhav",           _img("bhav")),
    Section("articles",   "/articles/",      _img("articles")),
    Section("sawal",      "/sawal",          _img("sawal")),
    Section("pashupalan", "/pashupalan",     _img("pashupalan")),
    Section("ganna",      "/ganna",          _img("ganna")),
    Section("rental",     "/rental",         _img("rental")),
    Section("shop",       "/product/",       _img("shop")),
    Section("dukan",      "/krashi_dukan",   _img("dukan")),
    Section("naksha",     "/naksha",         _img("naksha")),
    Section("weather",    "/weather",        _img("weather")),
    Section("news",       "/krashi_news",    _img("news")),
    Section("yojana",     "/sarkari_yojana", _img("yojana")),
    Section("fasal",      "/meri_fasal",     _img("fasal")),
    Section("bazar",      "/krashi_bajar",   _img("bazar")),
    Section("khoj",       "/khoj",           _img("khoj")),
    Section("chat",       "/chat",           _img("chat")),
)}


# ── crop families ──────────────────────────────────────────────────────────
#
# Agmarknet spells one crop several ways ("Wheat", "Wheat Atta", "Paddy(Dhan)
# (Common)"), and each section keys its own content differently: /sawal uses
# `gehu`, the crop calendar uses `wheat`, articles link the /bhav slug. The
# family is the join. Matching is on hyphen-delimited tokens, not raw
# substrings, because "lentil" contains "til" and "custard-apple" contains
# "apple" — and first match wins, so the specific rows sit above the general.
#
# A crop with no family resolves to "" and simply gets each section's hub
# instead of a deep link. That is the intended behaviour for the long tail:
# a new commodity in the feed must never produce a guessed URL.

_FAMILIES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    # (family, Hindi name, slug tokens that identify it)
    ("ganna",    "गन्ना",    ("sugarcane", "ganna", "jaggery", "gur")),
    ("gehu",     "गेहूं",    ("wheat", "gehu", "atta")),
    ("dhan",     "धान",      ("paddy", "dhan", "rice")),
    ("sarson",   "सरसों",    ("mustard", "sarson", "rape", "rapeseed")),
    ("aloo",     "आलू",      ("potato", "aloo")),
    ("chana",    "चना",      ("bengal", "chana", "kabuli")),
    ("makka",    "मक्का",    ("maize", "makka", "corn")),
    ("kapas",    "कपास",     ("cotton", "kapas")),
    ("soyabean", "सोयाबीन",  ("soyabean", "soybean")),
    ("arhar",    "अरहर",     ("arhar", "tur", "pegeon", "pigeon")),
    ("moong",    "मूंग",     ("moong", "mung")),
    ("urad",     "उड़द",     ("urd", "urad")),
    ("masur",    "मसूर",     ("masur", "lentil")),
    ("bajra",    "बाजरा",    ("bajra",)),
    ("jowar",    "ज्वार",    ("jowar", "sorghum")),
    ("ragi",     "रागी",     ("ragi",)),
    ("mungfali", "मूंगफली",  ("groundnut", "mungfali", "peanut")),
    ("til",      "तिल",      ("sesamum", "sesame", "til", "gingelly")),
    ("tamatar",  "टमाटर",    ("tomato",)),
    ("pyaj",     "प्याज",    ("onion", "pyaj")),
    ("mirch",    "मिर्च",    ("chillies", "chilli", "chilly", "mirch")),
    ("baingan",  "बैंगन",    ("brinjal", "baingan")),
    ("bhindi",   "भिंडी",    ("bhindi", "okra")),
    ("haldi",    "हल्दी",    ("turmeric",)),
    ("adrak",    "अदरक",     ("ginger",)),
    ("lahsun",   "लहसुन",    ("garlic",)),
    ("aam",      "आम",       ("mango",)),
    ("kela",     "केला",     ("banana",)),
    ("angur",    "अंगूर",    ("grapes",)),
    ("anar",     "अनार",     ("pomegranate",)),
    ("nariyal",  "नारियल",   ("coconut", "copra")),
)

_FAMILY_HI = {f: hi for f, hi, _ in _FAMILIES}

# family → /sawal crop key (services/kcc_service.CROPS). Only the families the
# Kisan Call Centre feed actually files answers under.
_SAWAL_KEY = {
    "gehu": "gehu", "dhan": "dhan", "ganna": "ganna", "sarson": "sarson",
    "aloo": "aloo", "chana": "chana", "makka": "makka", "kapas": "kapas",
    "soyabean": "soyabean", "arhar": "arhar", "moong": "moong", "urad": "urad",
    "bajra": "bajra", "jowar": "jowar", "mungfali": "mungfali", "til": "til",
    "tamatar": "tamatar", "pyaj": "pyaj", "mirch": "mirch",
    "baingan": "baingan", "bhindi": "bhindi", "aam": "aam",
}

# family → backend/data/crop_stages.json key (मेरी फसल crop calendar).
_CALENDAR_KEY = {
    "gehu": "wheat", "dhan": "paddy", "ganna": "sugarcane", "sarson": "mustard",
    "makka": "maize", "aloo": "potato", "pyaj": "onion", "tamatar": "tomato",
    "chana": "gram", "soyabean": "soybean",
}

# family → the machine that crop is actually hired for. A wheat grower hires a
# thresher; offering him a paddy transplanter is noise dressed as help.
_EQUIPMENT = {
    "gehu":     ("thresher", "थ्रेशर"),
    "dhan":     ("paddy-transplanter", "धान रोपाई मशीन"),
    "ganna":    ("tractor-trolley", "ट्रैक्टर ट्रॉली"),
    "aloo":     ("rotavator", "रोटावेटर"),
    "kapas":    ("power-sprayer", "पावर स्प्रेयर"),
    "makka":    ("thresher", "थ्रेशर"),
    "soyabean": ("combine-harvester", "कंबाइन हार्वेस्टर"),
    "sarson":   ("thresher", "थ्रेशर"),
}

# The states /weather actually serves. The page is UP-only by design (the site
# is a national mandi product with UP weather) — linking a Karnataka reader to
# it spends his click to show him someone else's forecast.
_WEATHER_STATES = {"uttar-pradesh", "uttarpradesh"}


def _tokens(slug: str) -> set:
    return set(re.split(r"[-_\s]+", (slug or "").strip().lower())) - {""}


def family(crop_slug: str) -> str:
    """Crop family for a /bhav commodity slug, or "" when nothing matches."""
    toks = _tokens(crop_slug)
    if not toks:
        return ""
    for fam, _hi, needles in _FAMILIES:
        if toks & set(needles):
            return fam
    return ""


def family_hi(fam: str) -> str:
    return _FAMILY_HI.get(fam, "")


def _in_script(text: str, lang: str) -> bool:
    """True when `text` is written in the script the page is written in.

    A URL slug is Latin ("bijnor"), a caller's Hindi name is not ("बिजनौर"), and
    the difference is invisible at the call site — `district_hi or district` is
    the natural thing to write and it silently ships "bijnor का नक्शा" onto a
    Hindi page whenever the caller had no Hindi name to give. This site has
    already measured what a wrong-script label costs on a title; it costs the
    same inside a link. So the check lives here, once, and a step that cannot
    name the place in the reader's script falls back to naming the section.
    """
    if not text:
        return False
    blocks = {"ta": (0x0B80, 0x0BFF), "kn": (0x0C80, 0x0CFF),
              "en": (0x0041, 0x024F)}
    lo, hi = blocks.get(lang, (0x0900, 0x097F))     # default: Devanagari
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    return sum(1 for c in letters if lo <= ord(c) <= hi) / len(letters) >= 0.6


# ── topics ─────────────────────────────────────────────────────────────────
#
# `articleSection` is free-form and 43 spellings deep across the 176 live
# articles ("खाद", "खाद व उर्वरक", "खाद और पोषण", "खाद प्रबंधन"). Folding it
# onto a small vocabulary here is what lets a fertiliser article find the
# fertiliser shop — in every one of its spellings, and in the next one too.

_TOPIC_WORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("pashu",  ("पशु", "दूध", "मुर्गी", "बकरी", "मछली", "मधुमक्खी", "dairy", "poultry")),
    ("yojana", ("योजना", "सरकारी", "अनुदान", "सब्सिडी", "ಯೋಜನೆ", "திட்ட")),
    ("khad",   ("खाद", "उर्वरक", "पोषण", "यूरिया", "पोषक")),
    ("keet",   ("कीट", "इल्ली", "सुंडी", "खरपतवार")),
    ("rog",    ("रोग", "फफूंद", "झुलसा", "विषाणु")),
    ("mandi",  ("मंडी", "भाव", "बिक्री", "बाज़ार", "बाजार", "ಮಾರುಕಟ್ಟೆ", "சந்தை")),
    ("mausam", ("मौसम", "आपदा", "बाढ़", "पाला", "weather")),
    ("ganna",  ("गन्ना", "चीनी")),
    ("ped",    ("पेड़", "वानिकी", "लकड़ी")),
    ("bag",    ("बागवानी", "फल", "सब्ज", "ತೋಟಗಾರಿಕೆ")),
    ("yantra", ("यंत्र", "मशीन", "तकनीक", "ड्रोन", "ट्रैक्टर")),
    ("jaivik", ("जैविक", "प्राकृतिक")),
    ("kheti",  ("खेती", "फसल", "गाइड", "मार्गदर्शिका", "ಬೆಳೆ", "வேளாண்", "பயிர்")),
)


def topics(*texts: str) -> tuple:
    """Canonical topic tags for any free-text label (an articleSection, a
    category name, a page heading). Order follows _TOPIC_WORDS, so the most
    actionable tag lands first and a provider can read topics[0] as "what this
    page is mostly about"."""
    blob = " ".join(t for t in texts if t)
    if not blob:
        return ()
    return tuple(tag for tag, words in _TOPIC_WORDS if any(w in blob for w in words))


# ── the context a page occupies ────────────────────────────────────────────

@dataclass
class Ctx:
    """Where the reader is standing. Every field is optional: the strip gets
    less specific as fields go missing, and never wrong."""
    section: str = ""
    crop: str = ""            # /bhav commodity slug, known to resolve
    crop_hi: str = ""
    state: str = ""           # state slug
    state_hi: str = ""
    district: str = ""        # district slug
    district_hi: str = ""
    topics: tuple = ()
    lang: str = "hi"
    canon: str = ""
    have: frozenset = frozenset()   # sections this page already links well
    # Which crop this page is about when there is no /bhav slug to prove it.
    # /ganna is the case: the section is unambiguously about गन्ना, but cane is
    # bought by mills at an administered rate, so asserting a /bhav/sugarcane
    # URL from the path would be a guessed address for a number that does not
    # move daily. The family gets to be known without the price page being
    # claimed — /sawal/ganna and the cane articles still resolve.
    fam_hint: str = ""

    @property
    def fam(self) -> str:
        return family(self.crop) or self.fam_hint

    @property
    def crop_name(self) -> str:
        """Hindi crop name for copy — the caller's, or the family's."""
        return self.crop_hi or family_hi(self.fam)


# Path prefix → section id. Longest first, so /bhav/rajya is still bhav and
# /pashupalan/anda-rate is still pashupalan.
_PREFIX = (
    ("/articles", "articles"), ("/krashi_news", "news"), ("/news", "news"),
    ("/krashi_dukan", "dukan"), ("/krashi_bajar", "bazar"),
    ("/pashupalan", "pashupalan"), ("/farm", "pashupalan"),
    ("/sarkari_yojana", "yojana"), ("/meri_fasal", "fasal"),
    ("/crop-calendar", "fasal"), ("/product", "shop"),
    ("/rental", "rental"), ("/naksha", "naksha"), ("/map", "naksha"),
    ("/weather", "weather"), ("/ganna", "ganna"), ("/sawal", "sawal"),
    ("/bhav", "bhav"), ("/khoj", "khoj"), ("/chat", "chat"),
)

# What each section is inherently about, for the pages whose path carries no
# crop. These are the tags a page would have declared if it were an article.
_SECTION_TOPICS = {
    "pashupalan": ("pashu",),
    "rental":     ("yantra",),
    "shop":       ("khad",),
    "dukan":      ("khad",),
    "ganna":      ("ganna",),
    "yojana":     ("yojana",),
    "weather":    ("mausam",),
    "sawal":      ("kheti",),
    "bhav":       ("mandi",),
}


def parse(canon: str, **over) -> Ctx:
    """URL → Ctx. One parser for the whole site, so a new section gets its
    position read correctly by adding a row to _PREFIX rather than by teaching
    every caller to build a context by hand. Keyword arguments override what
    the path implies — a caller that knows the Hindi names, the language or the
    topics should always pass them."""
    path = re.sub(r"^https?://[^/]+", "", canon or "").split("?", 1)[0]
    path = "/" + path.strip("/")
    parts = [p for p in path.split("/") if p]
    ctx = Ctx(canon=canon or "")

    for prefix, sec in _PREFIX:
        if path == prefix or path.startswith(prefix + "/"):
            ctx.section = sec
            break

    rest = parts[1:]
    if ctx.section == "bhav" and rest:
        # /bhav/rajya/{state}/{district} is the place hub; every other shape is
        # /bhav/{crop}[/{state}[/{district}]].
        if rest[0] == "rajya":
            ctx.state = rest[1] if len(rest) > 1 else ""
            ctx.district = rest[2] if len(rest) > 2 else ""
        else:
            ctx.crop = rest[0]
            ctx.state = rest[1] if len(rest) > 1 else ""
            ctx.district = rest[2] if len(rest) > 2 else ""
    elif ctx.section == "ganna":
        ctx.fam_hint = "ganna"
        ctx.state = rest[0] if len(rest) > 0 else ""
        ctx.district = rest[1] if len(rest) > 1 else ""
    elif ctx.section == "naksha" and rest:
        ctx.state = rest[0]
        # /naksha/{state}/jile and /naksha/{state}/{district}/gaon are listing
        # pages, not places — their second segment is a word, not a district.
        if len(rest) > 1 and rest[1] not in ("jile", "gaon"):
            ctx.district = rest[1]

    # What a section is about when the path does not say. Without this a
    # /pashupalan page has no topic, so the article provider has no pool to
    # draw from and offers the articles hub — the generic link this whole
    # module exists to stop shipping.
    ctx.topics = ctx.topics or _SECTION_TOPICS.get(ctx.section, ())

    for k, v in over.items():
        if v:
            setattr(ctx, k, v)
    if not isinstance(ctx.have, frozenset):
        ctx.have = frozenset(ctx.have or ())
    if not isinstance(ctx.topics, tuple):
        ctx.topics = tuple(ctx.topics or ())
    return ctx


# ── one onward move ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Step:
    section: str
    href: str
    title: str
    why: str = ""
    icon: str = ""
    score: int = 0
    # A place-shaped template ("/bhav/wheat/{state}/{district}") that
    # km-journey.js may substitute once the reader's own district is known.
    # The rendered href stays the safe, crawlable one — see the JS.
    place_tpl: str = ""


# ── copy ───────────────────────────────────────────────────────────────────
#
# Hindi is complete. Marathi inherits Hindi where untranslated — a Marathi
# reader reads Hindi, the same argument (and the same script) as
# services/state_lang.crop() — and real Marathi wording can be added to
# backend/data/state_lang.json under `words` as "journey_<key>" with no deploy.
# Tamil and Kannada do NOT inherit: a Hindi line under a Tamil heading is the
# script mismatch this site measured a 2.7x CTR penalty on. A missing ta/kn
# string drops the line, and a missing title drops the whole step.
#
# A `why` line says what the reader GETS at the far end. It must never make a
# claim about where a number comes from. This strip is printed on every section,
# so a line reading "updated daily from Agmarknet" — true of /bhav — also lands
# on /rental, whose footer note was deliberately rewritten because tractor hire
# comes from no feed and no mandi quotes it. Provenance belongs on the page that
# owns the number. tests/test_rental_rate_claims.py holds this line.

_COPY: dict = {
    "hi": {
        "h":              "आगे क्या करें",
        "sub":            "इसी से जुड़े अगले कदम — एक टैप में",
        "bhav.t":         "{crop} का आज का मंडी भाव",
        "bhav.w":         "राज्य और ज़िले के हिसाब से आज के रेट",
        "bhav_place.t":   "{place} मंडी के आज के भाव",
        "bhav_place.w":   "इस मंडी में जो भी फसल बिकी, सबके रेट एक जगह",
        "bhav_hub.t":     "सभी फसलों के मंडी भाव",
        "bhav_hub.w":     "हर फसल के आज के रेट — राज्य और ज़िले के हिसाब से",
        "article.w":      "पूरी जानकारी — आसान हिंदी में",
        "articles_hub.t": "कृषि लेख और गाइड",
        "articles_hub.w": "खेती, खाद, कीट-रोग और योजनाओं की पूरी जानकारी",
        "sawal.t":        "{crop} पर किसानों के सवाल-जवाब",
        "sawal.w":        "किसान कॉल सेंटर (भारत सरकार) के असली जवाब",
        "sawal_hub.t":    "किसानों के असली सवाल",
        "sawal_hub.w":    "किसान कॉल सेंटर के जवाब — फसल के हिसाब से",
        "pashu.t":        "अंडे का आज का रेट",
        "pashu.w":        "NECC रेट रोज़ — खेती के साथ दूसरी आमदनी",
        "pashu_hub.t":    "पशुपालन — दूध, मुर्गी, बकरी",
        "pashu_hub.w":    "खेती के साथ की कमाई, और रोज़ का अंडा रेट",
        "ganna.t":        "गन्ना मिल रेट और भुगतान",
        "ganna.w":        "मिल के हिसाब से रेट — SAP, FRP और पर्ची",
        "rental.t":       "किराये पर {eq}",
        "rental.w":       "अपने इलाके में मालिक और किराया देखें",
        "rental_hub.t":   "किराये पर कृषि यंत्र",
        "rental_hub.w":   "ट्रैक्टर, थ्रेशर, रोटावेटर — किराया और मालिक",
        "shop.t":         "खाद-बीज और दवा के दाम",
        "shop.w":         "पैक साइज़ के साथ रेट — और पास की दुकान",
        "dukan.t":        "कृषि दुकान डायरेक्टरी",
        "dukan.w":        "आपके इलाके की दुकानें और उनके अपने रेट",
        "naksha.t":       "{place} का नक्शा",
        "naksha.w":       "गाँव-वार नक्शा देखें और खेत नापें",
        "naksha_hub.t":   "खेत नापें और नक्शा देखें",
        "naksha_hub.w":   "ज़मीन का रकबा नापें — बीघा, एकड़, हेक्टेयर",
        "weather.t":      "आज और कल का मौसम",
        "weather.w":      "छिड़काव और सिंचाई का सही दिन चुनें",
        "news.t":         "आज की कृषि खबरें",
        "news.w":         "MSP, मौसम, योजना — रोज़ की अपडेट",
        "yojana.t":       "सरकारी योजनाएँ",
        "yojana.w":       "पात्रता, कागज़ और आवेदन का तरीका",
        "fasal.t":        "{crop} का फसल कैलेंडर",
        "fasal.w":        "बुवाई से कटाई तक — कब क्या करना है",
        "fasal_hub.t":    "मेरी फसल — कैलेंडर",
        "fasal_hub.w":    "बुवाई की तारीख डालें, अगला काम याद दिलाएँगे",
        "bazar.t":        "कृषि बाज़ार",
        "bazar.w":        "किसानों की खरीद-बिक्री की पोस्ट",
        "khoj.t":         "कृषि खोज",
        "khoj.w":         "अपनी फसल की समस्या खोजें",
        "chat.t":         "AI कृषि सहायक",
        "chat.w":         "फसल की फोटो भेजें — तुरंत पहचान और इलाज",
    },
    "en": {
        "h":              "What to do next",
        "sub":            "Related next steps — one tap away",
        "bhav.t":         "Today's mandi price for {crop}",
        "bhav.w":         "State- and district-wise rates, updated daily",
        "bhav_hub.t":     "Mandi prices for every crop",
        "bhav_hub.w":     "Today's rates for every crop, state and district wise",
        "articles_hub.t": "Farming guides and articles",
        "articles_hub.w": "Crops, fertiliser, pests, diseases and schemes",
        "pashu_hub.t":    "Livestock — dairy, poultry, goats",
        "pashu_hub.w":    "Income alongside the farm, and today's egg rate",
        "rental_hub.t":   "Farm machinery on hire",
        "rental_hub.w":   "Tractor, thresher, rotavator — rates and owners",
        "shop.t":         "Fertiliser, seed and pesticide prices",
        "shop.w":         "Rates by pack size, and the shop nearest you",
        "naksha_hub.t":   "Measure your field, see the map",
        "naksha_hub.w":   "Area in bigha, acre and hectare",
        "news.t":         "Today's farming news",
        "news.w":         "MSP, weather and schemes — updated daily",
        "yojana.t":       "Government schemes",
        "yojana.w":       "Eligibility, documents and how to apply",
        "weather.t":      "Weather today and tomorrow",
        "weather.w":      "Pick the right day to spray or irrigate",
        "chat.t":         "AI farming assistant",
        "chat.w":         "Send a photo of the crop — instant diagnosis",
    },
    "kn": {
        "h":              "ಮುಂದೇನು ಮಾಡಬೇಕು",
        "sub":            "ಇದಕ್ಕೆ ಸಂಬಂಧಿಸಿದ ಮುಂದಿನ ಹೆಜ್ಜೆಗಳು",
        "bhav.t":         "{crop} ಇಂದಿನ ಮಾರುಕಟ್ಟೆ ದರ",
        "bhav.w":         "ರಾಜ್ಯ ಮತ್ತು ಜಿಲ್ಲೆವಾರು ಇಂದಿನ ದರ",
        "bhav_hub.t":     "ಎಲ್ಲಾ ಬೆಳೆಗಳ ಮಾರುಕಟ್ಟೆ ದರ",
        "bhav_hub.w":     "ಪ್ರತಿ ಬೆಳೆಯ ಇಂದಿನ ದರ — ರಾಜ್ಯ ಮತ್ತು ಜಿಲ್ಲೆವಾರು",
        "articles_hub.t": "ಕೃಷಿ ಲೇಖನಗಳು",
        "articles_hub.w": "ಬೆಳೆ, ಗೊಬ್ಬರ, ಕೀಟ-ರೋಗ ಮತ್ತು ಯೋಜನೆಗಳ ಮಾಹಿತಿ",
        "pashu_hub.t":    "ಪಶುಪಾಲನೆ — ಹಾಲು, ಕೋಳಿ, ಮೇಕೆ",
        "pashu_hub.w":    "ಕೃಷಿಯ ಜೊತೆಗೆ ಹೆಚ್ಚುವರಿ ಆದಾಯ",
        "rental_hub.t":   "ಬಾಡಿಗೆಗೆ ಕೃಷಿ ಯಂತ್ರಗಳು",
        "rental_hub.w":   "ಟ್ರ್ಯಾಕ್ಟರ್, ಥ್ರೆಷರ್, ರೋಟವೇಟರ್ — ಬಾಡಿಗೆ ದರ",
        "shop.t":         "ಗೊಬ್ಬರ-ಬೀಜ ಮತ್ತು ಔಷಧಿ ದರ",
        "shop.w":         "ಪ್ಯಾಕ್ ಗಾತ್ರದ ಸಹಿತ ದರ",
        "naksha_hub.t":   "ಜಮೀನು ಅಳತೆ ಮತ್ತು ನಕ್ಷೆ",
        "naksha_hub.w":   "ಎಕರೆ, ಗುಂಟೆ, ಹೆಕ್ಟೇರ್‌ನಲ್ಲಿ ಅಳತೆ",
        "news.t":         "ಇಂದಿನ ಕೃಷಿ ಸುದ್ದಿ",
        "news.w":         "MSP, ಹವಾಮಾನ, ಯೋಜನೆ — ಪ್ರತಿದಿನ",
        "yojana.t":       "ಸರ್ಕಾರಿ ಯೋಜನೆಗಳು",
        "yojana.w":       "ಅರ್ಹತೆ, ದಾಖಲೆ ಮತ್ತು ಅರ್ಜಿ ವಿಧಾನ",
        "chat.t":         "AI ಕೃಷಿ ಸಹಾಯಕ",
        "chat.w":         "ಬೆಳೆಯ ಫೋಟೋ ಕಳುಹಿಸಿ — ತಕ್ಷಣ ಪರಿಹಾರ",
    },
    "ta": {
        "h":              "அடுத்து என்ன செய்யலாம்",
        "sub":            "இதனுடன் தொடர்புடைய அடுத்த படிகள்",
        "bhav.t":         "{crop} இன்றைய சந்தை விலை",
        "bhav.w":         "மாநிலம் மற்றும் மாவட்ட வாரியாக இன்றைய விலை",
        "bhav_hub.t":     "அனைத்துப் பயிர்களின் சந்தை விலை",
        "bhav_hub.w":     "ஒவ்வொரு பயிரின் இன்றைய விலை — மாநிலம், மாவட்ட வாரியாக",
        "articles_hub.t": "வேளாண் கட்டுரைகள்",
        "articles_hub.w": "பயிர், உரம், பூச்சி-நோய் மற்றும் திட்டத் தகவல்",
        "pashu_hub.t":    "கால்நடை வளர்ப்பு — பால், கோழி, ஆடு",
        "pashu_hub.w":    "விவசாயத்துடன் கூடுதல் வருமானம்",
        "rental_hub.t":   "வாடகைக்கு வேளாண் இயந்திரங்கள்",
        "rental_hub.w":   "டிராக்டர், திரஷர், ரொட்டவேட்டர் — வாடகை விவரம்",
        "shop.t":         "உரம்-விதை மற்றும் மருந்து விலை",
        "shop.w":         "பேக் அளவுடன் விலை",
        "naksha_hub.t":   "நிலம் அளவிடு, வரைபடம் பார்",
        "naksha_hub.w":   "ஏக்கர், சென்ட், ஹெக்டேரில் அளவிடுங்கள்",
        "news.t":         "இன்றைய வேளாண் செய்திகள்",
        "news.w":         "MSP, வானிலை, திட்டம் — தினசரி",
        "yojana.t":       "அரசுத் திட்டங்கள்",
        "yojana.w":       "தகுதி, ஆவணம் மற்றும் விண்ணப்ப முறை",
        "chat.t":         "AI வேளாண் உதவியாளர்",
        "chat.w":         "பயிரின் புகைப்படத்தை அனுப்புங்கள் — உடனடி தீர்வு",
    },
}

# Languages that may fall back to the Hindi table. Devanagari only — see the
# script-mismatch note above.
_INHERITS_HI = {"hi", "mr"}


def _t(key: str, lang: str, loc: dict = None, **vals) -> str:
    """One string of copy. Resolution order: the caller's own locale table (the
    article builder already keeps ta/kn copy there), then state_lang.json's
    `words` (Marathi, editable with no deploy), then this module's table for
    the language, then Hindi — but only for languages that may inherit it."""
    raw = ""
    if loc:
        raw = loc.get("journey_" + key) or ""
    if not raw and lang and lang not in _INHERITS_HI:
        raw = _COPY.get(lang, {}).get(key, "")
    if not raw:
        try:
            from backend.services import state_lang
            raw = state_lang.word("journey_" + key, lang, "")
        except Exception:
            raw = ""
    if not raw:
        raw = _COPY.get(lang, {}).get(key, "")
    if not raw and lang in _INHERITS_HI:
        raw = _COPY["hi"].get(key, "")
    if not raw:
        return ""
    try:
        out = raw.format(**vals)
    except (KeyError, IndexError, ValueError):
        return ""
    return " ".join(out.split()).strip(" —-·,")


def _step(ctx: Ctx, section: str, href: str, key: str, score: int,
          loc: dict = None, place_tpl: str = "", **vals):
    """A step, or None when it cannot be labelled honestly in this language.

    Two refusals, both structural rather than left to each provider to
    remember: no title in the reader's language, and any substituted value that
    is missing or written in the wrong script. The second is the one that bites
    — `district_hi or district` is the natural thing to write at a call site
    and it quietly ships "bijnor का नक्शा" onto a Hindi page. A provider that
    hits either refusal falls through to its hub step, which names the section
    instead of the place and is always sayable.
    """
    for val in vals.values():
        if not _in_script(str(val), ctx.lang):
            return None
    title = _t(key + ".t", ctx.lang, loc, **vals)
    if not title:
        return None
    sec = SECTIONS.get(section)
    return Step(section=section, href=href, title=title,
                why=_t(key + ".w", ctx.lang, loc, **vals),
                icon=sec.icon if sec else "", score=score,
                place_tpl=place_tpl)


# ── cheap, guarded lookups into the rest of the app ────────────────────────
#
# Everything below can fail — the DB can be read-only, a JSON file can be
# mid-write, a module can be missing in a test. Each returns an empty answer on
# failure, which costs one step and never a page.

_TTL = 6 * 3600
_cache: dict = {}

# Lookups that have failed since import. On a page render this is noise — the
# strip is one step shorter and the page is fine. In a BUILD it matters: the
# article strip is baked into a file, so running the builder with no reachable
# database would silently rewrite 122 articles without their /sawal links and
# commit the result. tools/article_builder.py reads this and says so.
_FAILED: set = set()


def degraded() -> set:
    """Which cross-section lookups could not be answered. Empty is the healthy
    case. A caller that WRITES the strip to disk should check this."""
    return set(_FAILED)


def _cached(key: str, fn):
    hit = _cache.get(key)
    now = time.time()
    if hit and now - hit[0] < _TTL:
        return hit[1]
    try:
        val = fn()
    except Exception:
        # Remember the failure briefly so a broken lookup is not retried on
        # every one of 14,000 page renders.
        _FAILED.add(key)
        val = hit[1] if hit else None
        _cache[key] = (now - _TTL + 300, val)
        return val
    _FAILED.discard(key)
    _cache[key] = (now, val)
    return val


def _sawal_crops() -> frozenset:
    """The /sawal crop keys that have enough answers to have a page. Anything
    else would be a link to the not-found page."""
    def load():
        from backend.services.kcc_service import crops_with_qa
        return frozenset(k for k, _hi, _n in crops_with_qa())
    return _cached("sawal", load) or frozenset()


def _naksha_has(state: str, district: str) -> bool:
    def load():
        from backend.routes import naksha
        return {s: frozenset(naksha._dindex(s)) for s in naksha._states()}
    idx = _cached("naksha", load) or {}
    if state not in idx:
        return False
    return (not district) or district in idx[state]


def _rental_has(slug: str) -> bool:
    def load():
        from backend.services import rental
        return frozenset(e["slug"] for e in rental.equipment())
    return slug in (_cached("rental", load) or frozenset())


# ── the article index ──────────────────────────────────────────────────────
#
# Derived entirely from the built pages, so an article joins the graph the
# moment it is written and nothing has to be re-run or kept in sync by hand.
# Its crops come from the /bhav chips the author already verified; its topic
# from its own articleSection; its language from its own <html lang>.

_ART_RE = {
    "title": re.compile(r"<title>(.*?)</title>", re.S),
    "lang":  re.compile(r'<html[^>]*\blang="([a-z-]+)"'),
    "sect":  re.compile(r'"articleSection"\s*:\s*"([^"]+)"'),
    "bhav":  re.compile(r"/bhav/([a-z0-9-]+)"),
    "head":  re.compile(r'"headline"\s*:\s*"([^"]+)"'),
    # The article's own price-chip strip. Those slugs are the author's
    # statement of what the article is about, and tools/article_builder.py
    # requires each one to resolve. Every OTHER /bhav link on the page comes
    # from the related-articles cards, which are about something else — count
    # those and a mustard article files itself under wheat.
    "chips": re.compile(r'<section class="bhav-links".*?</section>', re.S),
}

_art_cache: dict = {"stamp": None, "by_crop": {}, "by_topic": {}, "all": []}


@dataclass(frozen=True)
class Art:
    slug: str
    title: str
    lang: str
    topic: str
    crops: frozenset


def _scan_articles() -> dict:
    by_crop: dict = {}
    by_topic: dict = {}
    every: list = []
    for path in sorted(_ARTICLES_DIR.glob("*.html")):
        if path.name == "index.html":
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        # headline first: it is the schema's own short form, with no SERP
        # padding and no site suffix, which is what reads best as link text.
        m = _ART_RE["head"].search(text) or _ART_RE["title"].search(text)
        title = " ".join(m.group(1).split()) if m else ""
        if not title:
            continue
        lm = _ART_RE["lang"].search(text)
        sm = _ART_RE["sect"].search(text)
        tags = topics(sm.group(1) if sm else "", title)
        chips = _ART_RE["chips"].search(text)
        crops = frozenset(_ART_RE["bhav"].findall(
            chips.group(0) if chips else "")) - {"rajya"}
        art = Art(slug=path.stem.lower(), title=title,
                  lang=(lm.group(1) if lm else "hi").split("-")[0],
                  topic=tags[0] if tags else "", crops=crops)
        every.append(art)
        for c in crops:
            by_crop.setdefault(c, []).append(art)
            fam = family(c)
            if fam:
                by_crop.setdefault("fam:" + fam, []).append(art)
        for t in tags:
            by_topic.setdefault(t, []).append(art)
    return {"by_crop": by_crop, "by_topic": by_topic, "all": every}


def articles() -> dict:
    """{by_crop, by_topic, all}, rebuilt when any article file's mtime moves —
    the same self-healing contract routes/articles.py uses for card dates."""
    try:
        stamp = tuple(sorted((p.name, p.stat().st_mtime)
                             for p in _ARTICLES_DIR.glob("*.html")))
    except OSError:
        return _art_cache
    if stamp != _art_cache["stamp"]:
        try:
            scanned = _scan_articles()
        except Exception:
            return _art_cache
        if scanned["all"]:
            _art_cache.update(stamp=stamp, **scanned)
    return _art_cache


def _jitter(*parts: str) -> int:
    return int(hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()[:8], 16)


def _pick_article(ctx: Ctx):
    """The most relevant article this page is not already on, in the reader's
    own language. Crop beats topic: a Bijnor wheat page owes its reader a wheat
    article, not a good article about something else."""
    idx = articles()
    here = ""
    if ctx.section == "articles":
        here = (ctx.canon.rstrip("/").rsplit("/", 1)[-1] or "").lower()
    pools = []
    if ctx.crop:
        pools.append(idx["by_crop"].get(ctx.crop, []))
    if ctx.fam:
        pools.append(idx["by_crop"].get("fam:" + ctx.fam, []))
    for t in ctx.topics:
        pools.append(idx["by_topic"].get(t, []))
    seen, ranked = set(), []
    for pool in pools:
        for a in pool:
            if a.slug == here or a.slug in seen or a.lang != ctx.lang:
                continue
            seen.add(a.slug)
            ranked.append(a)
    if not ranked:
        return None
    # A chip is not a subject. Most articles list गेहूं का भाव among their price
    # chips whatever they are about, so the crop pool alone would answer a wheat
    # page with "MP ई-उपार्जन पंजीयन" as readily as with a wheat guide. An
    # article that NAMES the crop in its own headline is about the crop; prefer
    # those, and keep the rest as the fallback pool rather than dropping them.
    name = ctx.crop_name
    subject = [a for a in ranked if name and name in a.title]
    # Stable per page, different between pages — the same rule the strip uses
    # for ties, so neighbouring crop pages do not all promote one article.
    return min(subject or ranked, key=lambda a: _jitter(ctx.canon, a.slug))


# ── the providers ──────────────────────────────────────────────────────────
#
# A provider answers one question: "given where this reader is standing, what
# can MY section offer him, and why?" It returns steps, or nothing. It never
# checks which section the reader came from — next_steps() does that once, for
# everyone, so a new provider cannot forget to.
#
# TO ADD A SECTION: append a row to SECTIONS above and a function here,
# decorated with @provider("<id>"). Nothing else in the codebase changes.

_PROVIDERS: list = []


def provider(section: str):
    def deco(fn):
        _PROVIDERS.append((section, fn))
        return fn
    return deco


@provider("bhav")
def _p_bhav(ctx, loc):
    # Every branch falls through to the hub, which is always nameable and
    # always resolves — the deep link is an upgrade, never a requirement.
    hub = _step(ctx, "bhav", f"{SITE}/bhav", "bhav_hub", 60, loc,
                place_tpl="/bhav/rajya/{state}/{district}")
    if ctx.crop:
        deep = _step(ctx, "bhav", f"{SITE}/bhav/{ctx.crop}", "bhav", 90, loc,
                     place_tpl="/bhav/" + ctx.crop + "/{state}/{district}",
                     crop=ctx.crop_name)
        return [deep or hub]
    if ctx.state and ctx.district:
        deep = _step(ctx, "bhav", f"{SITE}/bhav/rajya/{ctx.state}/{ctx.district}",
                     "bhav_place", 88, loc, place=ctx.district_hi)
        return [deep or hub]
    return [hub]


@provider("articles")
def _p_articles(ctx, loc):
    art = _pick_article(ctx)
    if art is None:
        return [_step(ctx, "articles", f"{SITE}/articles/", "articles_hub", 55, loc)]
    # The article's own headline IS the link text — it is already the sentence
    # the farmer would have searched, and no generated label beats that.
    return [Step("articles", f"{SITE}/articles/{art.slug}", art.title,
                 _t("article.w", ctx.lang, loc), SECTIONS["articles"].icon, 86)]


@provider("sawal")
def _p_sawal(ctx, loc):
    # The /sawal hub 404s when no crop has enough Kisan Call Centre answers to
    # publish — routes/sawal.py returns the not-found page rather than an empty
    # grid. So an empty section must not be advertised AT ALL: offering its hub
    # would put a dead link on every page of the site the day that table is
    # emptied. Same rule as the deep links, one level up.
    published = _sawal_crops()
    if not published:
        return []
    hub = _step(ctx, "sawal", f"{SITE}/sawal", "sawal_hub", 40, loc)
    key = _SAWAL_KEY.get(ctx.fam, "")
    if key and key in published:
        return [_step(ctx, "sawal", f"{SITE}/sawal/{key}", "sawal", 78, loc,
                      crop=ctx.crop_name) or hub]
    return [hub]


@provider("pashupalan")
def _p_pashupalan(ctx, loc):
    # The deep page when the reader is already on livestock; otherwise the hub,
    # framed as what it actually is for a crop farmer — the second income. This
    # is the /bhav → /articles → /pashupalan hop the section was cut off from.
    if "pashu" in ctx.topics:
        return [_step(ctx, "pashupalan", f"{SITE}/pashupalan/anda-rate",
                      "pashu", 80, loc)]
    return [_step(ctx, "pashupalan", f"{SITE}/pashupalan", "pashu_hub", 52, loc)]


@provider("ganna")
def _p_ganna(ctx, loc):
    if ctx.fam == "ganna" or "ganna" in ctx.topics:
        return [_step(ctx, "ganna", f"{SITE}/ganna", "ganna", 84, loc)]
    return []


@provider("rental")
def _p_rental(ctx, loc):
    hub = _step(ctx, "rental", f"{SITE}/rental", "rental_hub", 48, loc)
    eq = _EQUIPMENT.get(ctx.fam)
    if not eq and ({"keet", "rog"} & set(ctx.topics)):
        eq = ("power-sprayer", "पावर स्प्रेयर")
    # The equipment name in the label is Hindi, so _step refuses the deep link
    # for a Tamil or Kannada reader and the hub is what ships.
    if eq and _rental_has(eq[0]):
        return [_step(ctx, "rental", f"{SITE}/rental/{eq[0]}", "rental", 74,
                      loc, eq=eq[1]) or hub]
    return [hub]


@provider("shop")
def _p_shop(ctx, loc):
    score = 70 if ({"khad", "keet", "rog"} & set(ctx.topics)) else 44
    return [_step(ctx, "shop", f"{SITE}/product/", "shop", score, loc)]


@provider("dukan")
def _p_dukan(ctx, loc):
    return [_step(ctx, "dukan", f"{SITE}/krashi_dukan", "dukan", 38, loc)]


@provider("naksha")
def _p_naksha(ctx, loc):
    if ctx.state and _naksha_has(ctx.state, ctx.district):
        href = f"{SITE}/naksha/{ctx.state}"
        if ctx.district:
            href += f"/{ctx.district}"
        # The deep URL is correct even when the place cannot be named in the
        # reader's script — so keep the address and fall back to the wording
        # that names the section instead of the district.
        return [_step(ctx, "naksha", href, "naksha", 72, loc,
                      place=ctx.district_hi if ctx.district else ctx.state_hi)
                or _step(ctx, "naksha", href, "naksha_hub", 58, loc)]
    return [_step(ctx, "naksha", f"{SITE}/naksha", "naksha_hub", 42, loc,
                  place_tpl="/naksha/{state}/{district}")]


@provider("weather")
def _p_weather(ctx, loc):
    # UP-only page. Offered where it is true, and to a reader whose state we do
    # not know — never to one we know it is wrong for.
    if ctx.state and ctx.state not in _WEATHER_STATES:
        return []
    score = 76 if ({"mausam", "keet"} & set(ctx.topics)) else 50
    return [_step(ctx, "weather", f"{SITE}/weather", "weather", score, loc)]


@provider("news")
def _p_news(ctx, loc):
    return [_step(ctx, "news", f"{SITE}/krashi_news", "news", 46, loc)]


@provider("yojana")
def _p_yojana(ctx, loc):
    score = 82 if "yojana" in ctx.topics else 45
    return [_step(ctx, "yojana", f"{SITE}/sarkari_yojana", "yojana", score, loc)]


@provider("fasal")
def _p_fasal(ctx, loc):
    hub = _step(ctx, "fasal", f"{SITE}/meri_fasal", "fasal_hub", 36, loc)
    key = _CALENDAR_KEY.get(ctx.fam, "")
    if key:
        return [_step(ctx, "fasal", f"{SITE}/meri_fasal?crop={key}", "fasal",
                      68, loc, crop=ctx.crop_name) or hub]
    return [hub]


@provider("bazar")
def _p_bazar(ctx, loc):
    return [_step(ctx, "bazar", f"{SITE}/krashi_bajar", "bazar", 34, loc)]


@provider("khoj")
def _p_khoj(ctx, loc):
    return [_step(ctx, "khoj", f"{SITE}/khoj", "khoj", 32, loc)]


@provider("chat")
def _p_chat(ctx, loc):
    score = 66 if ({"keet", "rog"} & set(ctx.topics)) else 40
    return [_step(ctx, "chat", f"{SITE}/chat", "chat", score, loc)]


# ── the ranking ────────────────────────────────────────────────────────────

def next_steps(ctx: Ctx, n: int = 4, loc: dict = None) -> list:
    """The reader's next `n` moves, each one in a different section.

    ONE STEP PER SECTION is the rule that makes this an ecosystem rather than a
    link list: four links into four parts of the site is a map of the product;
    four links into /bhav is what the page already had.
    """
    best: dict = {}
    for section, fn in _PROVIDERS:
        if section == ctx.section or section in ctx.have:
            continue
        try:
            steps = fn(ctx, loc) or []
        except Exception:
            continue
        for s in steps:
            if s is None or not s.href:
                continue
            cur = best.get(s.section)
            if cur is None or s.score > cur.score:
                best[s.section] = s
    return sorted(best.values(),
                  key=lambda s: (-s.score, _jitter(ctx.canon, s.href)))[:n]


# ── the markup ─────────────────────────────────────────────────────────────
#
# Self-contained: every colour is literal, nothing depends on a CSS variable
# that exists in one shell and not the other, and the whole sheet is scoped
# under .km-journey so it cannot touch a page it is dropped into. One block of
# CSS, two shells, no twin to drift.
#
# Layout is one column under 560px — 98% of this audience is on a phone, and a
# full-width row with the icon on the left is a bigger tap target and a longer
# readable line than two cramped tiles.

CSS = """
.km-journey{margin:30px 0 6px;font-family:inherit}
.km-journey-h{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin:0 0 12px}
.km-journey-h strong{font-size:17px;font-weight:700;color:#1a3c2e;letter-spacing:.2px}
.km-journey-h span{font-size:12.5px;color:#7c8983}
.km-journey-grid{display:grid;grid-template-columns:1fr;gap:10px}
.km-journey-card{display:flex;align-items:center;gap:12px;padding:13px 15px;
background:#fff;border:1px solid #e5e9e6;border-left:3px solid #52b788;
border-radius:12px;text-decoration:none;color:#1a2e23;
box-shadow:0 1px 4px rgba(26,60,46,.05);
transition:transform .15s,box-shadow .15s,border-color .15s}
.km-journey-card:hover,.km-journey-card:focus{transform:translateY(-2px);
border-color:#52b788;box-shadow:0 6px 18px rgba(26,60,46,.12)}
.km-journey-ico{flex:0 0 44px;width:44px;height:44px;border-radius:50%;
background:#d8f3dc;overflow:hidden;box-shadow:0 0 0 2px #fff,0 0 0 3px #d8f3dc}
.km-journey-ico img{display:block;width:100%;height:100%;object-fit:cover}
.km-journey-txt{min-width:0;flex:1}
.km-journey-t{display:block;font-size:14.5px;font-weight:700;line-height:1.45;color:#1a3c2e}
.km-journey-w{display:block;margin-top:2px;font-size:12px;line-height:1.5;color:#6b7b73}
.km-journey-go{flex:0 0 auto;font-size:17px;color:#52b788;font-weight:700}
@media(min-width:560px){.km-journey-grid{grid-template-columns:1fr 1fr}}
@media(min-width:1000px){.km-journey-grid{grid-template-columns:repeat(4,1fr)}
.km-journey-card{flex-direction:column;align-items:flex-start;gap:9px;padding:16px}
.km-journey-go{display:none}}
"""


def _ico(src: str) -> str:
    if not src:
        return ""
    return (f'<img src="{escape(src, quote=True)}" alt="" width="44" height="44"'
            f' loading="lazy" decoding="async">')


def journey_html(ctx: Ctx, n: int = 4, loc: dict = None,
                 with_css: bool = True) -> str:
    """The strip. Empty string when there is nothing honest to offer, so a
    caller can always interpolate it unconditionally.

    Every link is a real server-rendered <a href> to a URL that resolves — the
    JS-only-link indexation gap this site has already paid for once is not
    being reopened for the sake of personalisation. km-journey.js may rewrite
    an href carrying data-km-place, and only ever to a deeper page of the same
    section, after the page has been served.
    """
    steps = next_steps(ctx, n, loc)
    if not steps:
        return ""
    head = _t("h", ctx.lang, loc) or _COPY["hi"]["h"]
    sub = _t("sub", ctx.lang, loc)
    cards = []
    for s in steps:
        tpl = (f' data-km-place="{escape(s.place_tpl, quote=True)}"'
               if s.place_tpl else "")
        why = f'<span class="km-journey-w">{escape(s.why)}</span>' if s.why else ""
        cards.append(
            f'<a class="km-journey-card" href="{escape(s.href, quote=True)}"'
            f' data-km-step="{escape(s.section, quote=True)}"{tpl}>'
            f'<span class="km-journey-ico" aria-hidden="true">{_ico(s.icon)}</span>'
            f'<span class="km-journey-txt">'
            f'<span class="km-journey-t">{escape(s.title)}</span>{why}</span>'
            f'<span class="km-journey-go" aria-hidden="true">&rsaquo;</span></a>')
    style = f"<style>{CSS}</style>" if with_css else ""
    sub_html = f"<span>{escape(sub)}</span>" if sub else ""
    return (f'{style}<nav class="km-journey" aria-label="{escape(head, quote=True)}">'
            f'<div class="km-journey-h"><strong>{escape(head)}</strong>'
            f'{sub_html}</div>'
            f'<div class="km-journey-grid">{"".join(cards)}</div></nav>')
