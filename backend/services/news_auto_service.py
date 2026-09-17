# ============================================================
# backend/services/news_auto_service.py
# KrashiMitra — AI News Auto-Pilot & 3-4 Day Funnel Engine
#
# Funnel Lifecycle:
#   Days 1-3 : Gemini gathers agri updates across all categories & stages drafts
#   Day 4    : Manual Review Window in Admin Panel (/admin)
#   Day 5    : Watchdog auto-publishes unreviewed staged posts to public feed
# ============================================================

import html
import json
import logging
import os
import random
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote
import base64

import httpx

from backend.config import get_setting
from backend.services.chatbot_service import call_ai

logger = logging.getLogger("krishi.news_auto_service")

DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "news_funnel.json"
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
ARTICLES_IMAGE_DIR = FRONTEND_DIR / "images" / "articles"
NEWS_DATA_FILE = FRONTEND_DIR / "krashi_news_data.js"


def _parse_iso_dt(val: Optional[str]) -> datetime:
    """Safely parse ISO datetime string to naive UTC datetime, avoiding tz subtract errors."""
    if not val:
        return datetime.utcnow()
    try:
        clean = str(val).replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean)
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        return datetime.utcnow()

DEFAULT_CATEGORY_IMAGES = {
    "mandi":   "/images/articles/gehuu-price-analytic-up-card.webp",
    "yojana":  "/images/articles/pm-kusum-solar-pump-yojana-card.webp",
    "weather": "/images/articles/karnataka-monsoon-card.webp",
    "crop":    "/images/articles/dhan-nursery-ropai-card.webp",
    "khad":    "/images/articles/urea-guide-up-card.webp",
    "pashu":   "/images/articles/dairy-farming-doodh-utpadan-card.webp",
    "tech":    "/images/articles/kisan-drone-chhidkav-card.webp",
}

# ============================================================
# Cover images: ours, or none
# ------------------------------------------------------------
# A news post never carries the source publisher's photograph. Their
# og:image is their copyright — reproducing it on an AdSense-carrying
# site is a licence breach whichever way the link is written, and
# hotlinking it also breaks the card the day they rename the file.
# (On 2026-09-04 an audit found exactly this live: two published posts
# pulled photos from someone else's server, one of them a portrait of a
# named public figure who had nothing to do with the story.)
#
# So the cover always comes from the ~190 card images we fetched,
# licence-checked, self-hosted and credited on /articles/credits. This
# table is what makes that a real choice rather than a stand-in: it maps
# what the story is ABOUT to the photograph of that crop or subject we
# already own. Only when nothing matches does the category default
# apply, and even that rotates deterministically per post — five stories
# in a row must not all wear the same solar-pump photo, which is what
# the old nine-branch if/elif chain (copied into three functions)
# produced.
#
# Adding a row: the slug must be an existing frontend/images/articles/
# <slug>-card.webp, i.e. an image already credited. _own() drops any row
# whose file is missing, so a typo degrades to the category default
# instead of a broken image.
# ============================================================

# (keywords, article slug whose card art we own). First match wins, so the
# specific rows sit above the general ones.
_IMAGE_KEYWORDS: List[Tuple[Tuple[str, ...], str]] = [
    # -- field crops -------------------------------------------------
    (("गेहूं", "गेहूँ", "wheat", "gehun", "gehu"),                "gehuu-price-analytic-up"),
    (("धान", "चावल", "paddy", "rice", "dhan", "कुरुवई", "samba"), "dhan-nursery-ropai"),
    (("गन्ना", "गन्ने", "sugarcane", "sugar", "cane", "चीनी मिल"), "ganna-guide-up"),
    (("सरसों", "सरसो", "mustard", "sarso", "रतुआ"),               "sarso-guide-up"),
    (("चना", "चने", "gram", "chana"),                             "chana-unnat-kheti"),
    (("मसूर", "lentil", "masoor"),                                "masoor-ki-kheti"),
    (("मटर", "pea", "matar"),                                     "matar-ki-kheti"),
    (("जौ", "barley", "जई", "oat"),                               "jau-ki-kheti"),
    (("मक्का", "maize", "corn", "makka"),                         "makka-guide-up"),
    (("बाजरा", "bajra", "millet", "ज्वार", "jowar"),              "bajra-jogiya-rog-rajasthan"),
    (("रागी", "ragi", "finger millet"),                           "ragi-guide-karnataka"),
    (("सोयाबीन", "soya", "soybean"),                              "soyabean-MP-guide"),
    (("कपास", "cotton", "नरमा", "kapas"),                         "kapas-ki-kheti-guide"),
    (("मूंगफली", "groundnut", "peanut", "moongfali"),             "moongfali-guide-rajisthan"),
    (("आलू", "potato", "aloo"),                                   "potato_guide_up"),
    (("प्याज", "कांदा", "onion", "kanda"),                        "kanda-chal-anudan-yojana"),
    (("टमाटर", "tomato"),                                         "tomato-guide-karnataka"),
    (("मिर्च", "chilli", "chili", "मिरची"),                       "chilli-guide-karnataka"),
    (("हल्दी", "turmeric", "haldi"),                              "haldi-kheti-erode-tamil-nadu"),
    (("अदरक", "ginger", "adrak"),                                 "adrak-haldi-kand-sadan"),
    # -- horticulture ------------------------------------------------
    (("आम ", "mango", "आम्र"),                                    "aam-utpadan-up"),
    (("केला", "banana", "kela"),                                  "kela-kheti-tamil-nadu"),
    (("अंगूर", "grape", "द्राक्ष"),                               "grapes-maharastra"),
    (("अनार", "pomegranate", "डाळिंब"),                           "anaar-maharastra"),
    (("सेब", "apple", "बागवानी"),                                 "apple-kashmir"),
    (("नारियल", "coconut", "नारळ"),                               "nariyal-kheti-tamil-nadu"),
    (("कॉफी", "coffee", "कॉफ़ी"),                                 "coffee-guide-karnataka"),
    # -- inputs ------------------------------------------------------
    (("dap", "डीएपी"),                                            "DAP-guide-up"),
    (("यूरिया", "urea", "खाद", "उर्वरक", "fertilizer", "नैनो"),   "urea-guide-up"),
    (("जैविक", "organic", "गोबर", "कम्पोस्ट", "vermi"),           "jaivik-khad"),
    (("खरपतवार", "weed", "नींदा", "herbicide"),                   "kharpatwarnashi-guide"),
    (("कीट", "इल्ली", "सुंडी", "रोग", "pest", "disease",
      "कीटनाशक", "फफूंद", "blight", "झुलसा"),                     "keet-niyantran"),
    # -- water, weather, land ----------------------------------------
    (("सोलर", "solar", "कुसुम", "kusum", "पंप", "pump"),          "pm-kusum-solar-pump-yojana"),
    (("मौसम", "बारिश", "मानसून", "weather", "monsoon", "rain",
      "ओलावृष्टि", "पाला", "तापमान", "सूखा", "बाढ़"),             "mausam-guide"),
    (("तारबंदी", "फेंसिंग", "fencing", "नीलगाय", "आवारा"),        "tarbandi-yojana-subsidy"),
    # -- livestock ---------------------------------------------------
    (("चारा", "बरसीम", "नेपियर", "fodder"),                       "hara-chara-napier-berseem"),
    (("दूध", "डेयरी", "dairy", "गाय", "भैंस", "milk", "पशु"),     "dairy-farming-doodh-utpadan"),
    (("मुर्गी", "अंडा", "poultry", "murgi", "चूजा"),              "murgi-palan-guide"),
    (("बकरी", "goat", "bakri"),                                   "bakri-palan-guide"),
    (("मछली", "fish", "मत्स्य"),                                  "machhli-palan-guide"),
    # -- money, schemes, tech ----------------------------------------
    (("बीमा", "insurance", "मुआवजा", "क्षतिपूर्ति"),              "pm-fasal-bima-yojana-2026"),
    (("kcc", "क्रेडिट कार्ड", "लोन", "loan", "कर्ज", "ऋण"),       "kisan-credit-card"),
    (("fpo", "उत्पादक संगठन", "समूह"),                            "fpo-kisan-utpadak-sangathan"),
    (("किसान आईडी", "agristack", "farmer id", "पहचान पत्र",
      "डिजिटल"),                                                  "kisan-pehchan-patra-agristack"),
    (("ड्रोन", "drone", "तकनीक", "मशीन", "यंत्र"),                "kisan-drone-chhidkav"),
    (("मंडी", "apmc", "नीलामी", "e-nam", "enam", "भाव", "msp"),   "vashi-apmc-mandi-guide"),
]

# Category defaults, several per category so consecutive posts differ.
_CATEGORY_POOL: Dict[str, Tuple[str, ...]] = {
    "mandi":   ("gehuu-price-analytic-up", "vashi-apmc-mandi-guide", "ganna-pricing-analytics-up"),
    "yojana":  ("pm-fasal-bima-yojana-2026", "pm-kusum-solar-pump-yojana", "kisan-credit-card"),
    "weather": ("mausam-guide", "karnataka-monsoon"),
    "crop":    ("dhan-nursery-ropai", "keet-niyantran", "makka-guide-up"),
    "khad":    ("urea-guide-up", "DAP-guide-up", "jaivik-khad"),
    "pashu":   ("dairy-farming-doodh-utpadan", "murgi-palan-guide", "hara-chara-napier-berseem"),
    "tech":    ("kisan-drone-chhidkav", "kisan-pehchan-patra-agristack"),
}


def _own(slug: str) -> Optional[str]:
    """The served path for one of our card images, or None if it is not there."""
    if (ARTICLES_IMAGE_DIR / f"{slug}-card.webp").is_file():
        return f"/images/articles/{slug}-card.webp"
    return None


def _stable_index(seed: str, n: int) -> int:
    """A per-post index that never moves — the same post keeps the same photo."""
    h = 0
    for ch in seed:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return h % max(n, 1)


def pick_our_image(
    text: str,
    category: str = "crop",
    seed: str = "",
    avoid: Optional[List[str]] = None,
) -> str:
    """Choose a self-hosted cover for a story from what the story is about.

    The fallback for when the model declines to choose, or names a slug
    that is not ours. `text` is anything descriptive — title, excerpt,
    source body. `seed` is any stable per-post string (its id) so two
    posts in the same category that both fall through to the default
    still differ. `avoid` is the covers the newest posts already use;
    honoured for the category default, but never for a keyword match —
    a wheat story wants the wheat photograph even if the last post used
    it, and a wrong picture is worse than a repeated one.
    """
    low = (text or "").lower()
    for keys, slug in _IMAGE_KEYWORDS:
        if any(k in low for k in keys):
            path = _own(slug)
            if path:
                return path

    avoid_set = set(avoid or [])
    pool = [p for p in (_own(s) for s in _CATEGORY_POOL.get(category, ())) if p]
    if not pool:
        pool = [p for p in (_own(s) for s in _CATEGORY_POOL["crop"]) if p]
    unused = [p for p in pool if p not in avoid_set]
    pool = unused or pool          # everything used? then repeating is fine
    if pool:
        return pool[_stable_index(seed or low, len(pool))]
    return "/images/og-banner.webp"


# ------------------------------------------------------------
# Letting Gemini choose the cover
# ------------------------------------------------------------
# pick_our_image() below is keyword matching, and keywords only reach as
# far as the words someone thought to list: a story about "पाले से बचाव"
# or "मिट्टी की जाँच" matches no row and lands on the category default,
# so consecutive stories wear the same photograph. The model already
# reads the whole story to write it — it is in a far better position to
# say which photograph pictures it.
#
# So the prompt carries our own library and the post asks for a slug
# back. Two things make that safe:
#
#   • The library IS the constraint. Gemini never supplies a URL, only
#     picks a row from a list built by scanning frontend/images/articles
#     — every entry already fetched, licence-checked and credited. A
#     slug that is not in the catalogue is discarded, so a hallucinated
#     or invented filename falls through to pick_our_image() instead of
#     reaching a reader.
#   • Covers used by the last few posts are removed from the list before
#     the model sees it, which is what actually stops the repeats: the
#     model cannot pick what it is not shown.
#
# The catalogue is built by reading the <title> of each card's article,
# so a new article published tomorrow is offered to the model tomorrow
# with no list to maintain and no rebuild step.
# ------------------------------------------------------------

ARTICLES_DIR = FRONTEND_DIR / "articles"

# How many recent covers to withhold from the model. Roughly a screen of
# the feed: far enough back that a reader scrolling the hub never sees
# the same photograph twice, short enough that the library never empties.
_AVOID_RECENT = 15

_catalogue_cache: Dict[str, object] = {"stamp": None, "items": {}}


def _card_subject(slug: str) -> str:
    """What the card for `slug` is a photograph of, from its article title."""
    path = ARTICLES_DIR / f"{slug}.html"
    if not path.is_file():
        return ""
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as fh:
            head = fh.read(4096)
    except OSError:
        return ""
    m = re.search(r"<title[^>]*>(.*?)</title>", head, re.I | re.S)
    if not m:
        return ""
    subject = html.unescape(_strip_tags(m.group(1)))
    # Titles are written for search results ("गेहूं में दीमक का इलाज —
    # कौन सी दवा"); the half before the dash is the subject.
    subject = re.split(r"\s+[—–|]\s+", subject)[0].strip()
    return subject[:70]


def image_catalogue() -> Dict[str, str]:
    """Every cover we may publish: slug → what it shows.

    Rebuilt when the image directory changes, so an image added by a
    fetch tool becomes available to the model without a restart.
    """
    try:
        stamp = ARTICLES_IMAGE_DIR.stat().st_mtime if ARTICLES_IMAGE_DIR.is_dir() else 0
    except OSError:
        stamp = 0
    if _catalogue_cache["stamp"] == stamp and _catalogue_cache["items"]:
        return _catalogue_cache["items"]  # type: ignore[return-value]

    items: Dict[str, str] = {}
    if ARTICLES_IMAGE_DIR.is_dir():
        for f in sorted(ARTICLES_IMAGE_DIR.glob("*-card.webp")):
            slug = f.name[: -len("-card.webp")]
            subject = _card_subject(slug)
            if subject:          # no article, no way to say what it shows
                items[slug] = subject

    _catalogue_cache["stamp"] = stamp
    _catalogue_cache["items"] = items
    logger.info(f"🖼️ Cover library: {len(items)} self-hosted images available")
    return items


def recently_used_covers(limit: int = _AVOID_RECENT) -> List[str]:
    """The covers of the newest posts, newest first.

    Published posts are prepended as they go live, so slicing the front
    of the list is slicing the top of the feed.
    """
    try:
        data = _load_data()
    except Exception:
        return []
    posts = (data.get("published_posts") or []) + (data.get("staged_posts") or [])
    seen: List[str] = []
    for p in posts[:limit]:
        img = (p.get("image") or "").strip()
        if img and img not in seen:
            seen.append(img)
    return seen


def cover_library_prompt(avoid: Optional[List[str]] = None) -> str:
    """The library, as the model sees it — minus what the feed just used."""
    avoid_set = set(avoid or [])
    rows = [
        f"- {slug} : {subject}"
        for slug, subject in image_catalogue().items()
        if f"/images/articles/{slug}-card.webp" not in avoid_set
    ]
    return "\n".join(rows)


def cover_from_slug(slug: str) -> Optional[str]:
    """The served path for a slug the model returned, or None if it is not ours.

    This is the check that makes handing the choice to a model safe: a
    slug it invented, a filename from someone else's site, or a full URL
    all fail the catalogue lookup and get discarded.
    """
    slug = (slug or "").strip().strip("/")
    if not slug or slug not in image_catalogue():
        return None
    return _own(slug)


CATEGORY_LABELS = {
    "mandi":   "🏪 मंडी व भाव",
    "yojana":  "🏛️ सरकारी योजना",
    "weather": "🌤️ मौसम व अलर्ट",
    "crop":    "🌾 फसल व कीट",
    "khad":    "🧪 खाद व पोषण",
    "pashu":   "🐄 पशुपालन व डेयरी",
    "tech":    "🚜 आधुनिक तकनीक",
}


def _strip_tags(text: str) -> str:
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", " ", text)
    return html.unescape(clean).strip()


# ── Master Articles & Deduplication Engine ─────────────────────

_MASTER_CACHE = {"articles": [], "mtime": 0}


def _load_master_articles() -> List[dict]:
    """Reads and caches 55+ master articles from krashi_news_data.js for duplicate checks."""
    if not NEWS_DATA_FILE.exists():
        return []
    try:
        mt = NEWS_DATA_FILE.stat().st_mtime
        if _MASTER_CACHE["articles"] and _MASTER_CACHE["mtime"] == mt:
            return _MASTER_CACHE["articles"]
        text = NEWS_DATA_FILE.read_text(encoding="utf-8", errors="ignore")
        chunks = text.split("id: '")
        items = []
        for c in chunks[1:]:
            obj = {}
            id_val = c.split("'", 1)[0]
            obj["id"] = id_val
            for f in ("slug", "title", "excerpt", "category", "catLabel", "time", "readTime", "image", "link"):
                m = re.search(rf"\b{f}:\s*['\"]([^'\"]*)['\"]", c)
                if m:
                    obj[f] = m.group(1)
            if obj.get("title"):
                items.append(obj)
        _MASTER_CACHE["articles"] = items
        _MASTER_CACHE["mtime"] = mt
        return items
    except Exception as e:
        logger.warning(f"Error loading master articles for deduplication: {e}")
        return _MASTER_CACHE.get("articles", [])


STOP_WORDS = {
    "का", "के", "की", "में", "से", "पर", "और", "व", "ने", "को", "है", "हैं",
    "लिए", "अब", "हुए", "गए", "गई", "हुआ", "हुई", "नया", "नए", "नई", "तक",
    "भी", "तो", "या", "इस", "इन", "ये", "वह", "वे", "था", "थे", "थी",
    "कर", "रहा", "रहे", "रही", "हो", "सकते", "सकता", "सकती", "बड़ा", "बड़ी",
    "दाम", "भाव", "मिला", "मिली", "मिले", "जाएगा", "जाएगी", "किया", "किए",
    "the", "a", "an", "in", "on", "for", "and", "to", "of", "is", "are",
    "with", "by", "at", "new", "latest", "update", "news"
}


def _extract_keywords(text: str) -> set:
    if not text:
        return set()
    cleaned = re.sub(r"[^\w\s\u0900-\u097f]", " ", text.lower())
    words = [w.strip() for w in cleaned.split() if len(w.strip()) >= 2]
    return {w for w in words if w not in STOP_WORDS}


def _normalize_url(url: str) -> str:
    if not url:
        return ""
    clean = re.sub(r"[?&](?:utm_[^&]+|oc=\d+|ref=[^&]+|fbclid=[^&]+|gclid=[^&]+)", "", url, flags=re.I)
    clean = clean.rstrip("?&/").lower()
    clean = re.sub(r"^https?://", "", clean)
    return clean.strip()


def _calc_token_overlap(kw1: set, kw2: set) -> float:
    if not kw1 or not kw2:
        return 0.0
    inter = len(kw1 & kw2)
    return inter / min(len(kw1), len(kw2))


def is_duplicate_story(title: str, url: str = "", content: str = "") -> Tuple[bool, str]:
    """
    Multi-barrier duplicate check against:
    1. Staged posts
    2. Published posts
    3. Seen URLs history
    4. Master 55+ articles in krashi_news_data.js
    Returns (is_duplicate: bool, reason: str)
    """
    if not title and not url:
        return False, ""

    data = _load_data()
    staged = data.get("staged_posts", [])
    published = data.get("published_posts", [])
    seen_urls = set(data.get("seen_urls", []))
    all_current = staged + published

    # 1. Exact / Normalized URL Matching
    norm_u = _normalize_url(url)
    if norm_u:
        if norm_u in seen_urls:
            return True, "यह समाचार लिंक (URL) पहले ही संसाधित हो चुका है"
        for p in all_current:
            p_u = _normalize_url(p.get("source_url") or p.get("link") or "")
            if p_u and (p_u == norm_u or norm_u in p_u or p_u in norm_u):
                return True, f"समान लिंक पहले से मौजूद है: '{p.get('title', '')[:40]}'"

    # 2. Title Exact / Normalized Substring Matching
    if title:
        norm_t = re.sub(r"[^\w\u0900-\u097f]", "", title.lower())
        if len(norm_t) > 6:
            for p in all_current:
                existing_t = re.sub(r"[^\w\u0900-\u097f]", "", p.get("title", "").lower())
                if existing_t and (norm_t == existing_t or (len(norm_t) > 15 and norm_t in existing_t) or (len(existing_t) > 15 and existing_t in norm_t)):
                    return True, f"समान शीर्षक का लेख पहले से मौजूद है: '{p.get('title', '')[:45]}'"

        # 3. Token Overlap Matching against Active & Master Articles
        in_kw = _extract_keywords(title + " " + (content[:200] if content else ""))
        if len(in_kw) >= 3:
            # Check active posts
            for p in all_current:
                p_kw = _extract_keywords(p.get("title", "") + " " + p.get("excerpt", ""))
                overlap = _calc_token_overlap(in_kw, p_kw)
                if overlap >= 0.58:
                    return True, f"समान विषय का लेख पहले से मौजूद है: '{p.get('title', '')[:45]}' (साम्यता: {int(overlap*100)}%)"

            # Check master articles
            masters = _load_master_articles()
            for m in masters:
                m_kw = _extract_keywords(m.get("title", "") + " " + m.get("excerpt", ""))
                overlap = _calc_token_overlap(in_kw, m_kw)
                if overlap >= 0.65:
                    return True, f"यह विषय मास्टर समाचार में पहले से शामिल है: '{m.get('title', '')[:45]}'"

    return False, ""


def get_recent_headlines(limit: int = 30) -> List[str]:
    """Returns the most recent unique headlines from published, staged, and master datasets."""
    data = _load_data()
    titles = []
    seen = set()
    for p in data.get("published_posts", []) + data.get("staged_posts", []):
        t = p.get("title", "").strip()
        if t and t not in seen:
            seen.add(t)
            titles.append(t)
    masters = _load_master_articles()
    for m in masters:
        t = m.get("title", "").strip()
        if t and t not in seen:
            seen.add(t)
            titles.append(t)
    return titles[:limit]


# ── Gemini AI Agricultural Image Generation ───────────────────

async def generate_ai_agri_image(
    title: str,
    category: str = "crop",
    custom_prompt: Optional[str] = None,
    post_id: Optional[str] = None
) -> dict:
    """
    Generates a relevant, cinematic agricultural cover image:
    1. Synthesizes an ultra-realistic photography prompt using Gemini.
    2. Generates the image via Google Imagen 3 or Pollinations Flux.
    3. Persists it locally under frontend/images/articles/ and returns permanent URL.
    4. Seamless contextual fallback if offline.
    """
    # The admin switch, checked before anything is spent. Off returns the
    # same owned photograph step 4 below falls back to — so the caller gets a
    # real cover either way and nothing downstream has to know the difference.
    # Gated here rather than at the route, because the auto-pilot reaches this
    # function without passing through one.
    if not get_setting("news_ai_enabled", True):
        logger.info("📴 कृषि न्यूज़ AI is switched OFF — using our own library cover")
        return {
            "success": True,
            "image_url": pick_our_image(f"{title} {category}", category,
                                        seed=post_id or title),
            "prompt_used": "",
            "source": "switched_off",
        }

    images_dir = ARTICLES_IMAGE_DIR
    images_dir.mkdir(parents=True, exist_ok=True)
    safe_slug = re.sub(r'[^a-zA-Z0-9_-]', '', (post_id or 'ai-post'))[:22]
    ts = int(datetime.utcnow().timestamp())
    filename = f"ai_gen_{safe_slug}_{ts}.webp"
    out_path = images_dir / filename

    # 1. Synthesize Prompt with Gemini
    ai_prompt = (custom_prompt or "").strip()
    if not ai_prompt or len(ai_prompt) < 10:
        craft_prompt = f"""You are a professional visual prompt director for KrashiMitra, an Indian agricultural portal.
Create an English image generation prompt for this Hindi agricultural news:
Headline: "{title}"
Category: "{category}"

Requirements:
- Authentic Indian farmland, crops, farmers, or modern agricultural setup.
- Realistic professional photography, 4K resolution, natural morning or golden hour lighting, 16:9 cinematic framing.
- Absolutely NO text, NO words, NO letters, NO watermarks, NO artificial logos.

HARD PROHIBITIONS (the headline may name a real person or a company — never
let that reach the image):
- NEVER depict a real, identifiable or named person. No politicians, no
  ministers, no officials, no celebrities, no likeness of anyone named in the
  headline. Generic, non-identifiable farmers only, and prefer wide shots,
  from behind, or hands-and-crop framing over recognisable faces.
- NEVER include a brand, trademark, company logo, vehicle badge, product
  packaging, government emblem, seal, flag or uniform.
- NEVER depict distress, disaster, injury, protest, violence or a damaged
  or dead animal. This is an ad-supported page read by anxious people.
- Describe a SCENE (crop, field, machinery, soil, market produce), never an
  event involving named parties.
- Output ONLY the prompt string (25-35 words), nothing else."""
        try:
            raw_craft, _ = await call_ai(craft_prompt, max_tokens=100)
            cleaned = raw_craft.strip().replace('"', '').replace('\n', ' ')
            if len(cleaned) >= 12 and not any(bad in cleaned.lower() for bad in ["i cannot", "sorry", "unavailable"]):
                ai_prompt = cleaned
        except Exception as e:
            logger.warning(f"Error synthesizing prompt with Gemini: {e}")

    if not ai_prompt or len(ai_prompt) < 10:
        ai_prompt = f"Photorealistic 4k photo of thriving {category} agricultural field in rural India, bright natural sunlight, lush green crops, cinematic 16:9 ratio"

    # 2. Try Google Imagen 3 via configured GEMINI_API_KEY
    from backend.services.chatbot_service import gemini_keys
    for env_k, api_k in gemini_keys():
        try:
            imagen_url = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-002:predict?key={api_k}"
            payload = {
                "instances": [{"prompt": ai_prompt}],
                "parameters": {"sampleCount": 1, "aspectRatio": "16:9"}
            }
            async with httpx.AsyncClient(timeout=22.0) as client:
                resp = await client.post(imagen_url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    preds = data.get("predictions", [])
                    if preds and "bytesBase64Encoded" in preds[0]:
                        img_bytes = base64.b64decode(preds[0]["bytesBase64Encoded"])
                        out_path.write_bytes(img_bytes)
                        logger.info(f"✅ Generated AI image via Google Imagen 3: {filename}")
                        return {
                            "success": True,
                            "image_url": f"/images/articles/{filename}",
                            "prompt_used": ai_prompt,
                            "source": "google_imagen_3"
                        }
        except Exception as e:
            logger.warning(f"Imagen 3 try on {env_k} error: {e}")

    # 3. Try Pollinations AI Flux engine
    try:
        encoded_p = quote(ai_prompt)
        seed = random.randint(1000, 999999)
        poll_url = f"https://image.pollinations.ai/prompt/{encoded_p}?width=800&height=450&model=flux&nologo=true&seed={seed}"
        async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as client:
            resp = await client.get(poll_url, headers={"User-Agent": "Mozilla/5.0 KrashiMitra/2.0"})
            if resp.status_code == 200 and len(resp.content) > 6000:
                out_path.write_bytes(resp.content)
                logger.info(f"✅ Generated AI image via Pollinations Flux: {filename}")
                return {
                    "success": True,
                    "image_url": f"/images/articles/{filename}",
                    "prompt_used": ai_prompt,
                    "source": "pollinations_flux"
                }
    except Exception as e:
        logger.warning(f"Pollinations generation error: {e}")

    # 4. Neither generator answered — fall back to the photograph we own
    # that matches this headline, rather than to one fixed image.
    fallback_img = pick_our_image(f"{title} {category}", category, seed=post_id or title)

    return {
        "success": True,
        "image_url": fallback_img,
        "prompt_used": ai_prompt,
        "source": "curated_contextual"
    }


def _load_data() -> dict:
    if not DATA_FILE.exists():
        initial = {
            "current_cycle": 1,
            "cycle_start_date": datetime.utcnow().isoformat(),
            "staged_posts": [],
            "published_posts": [],
        }
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        DATA_FILE.write_text(json.dumps(initial, ensure_ascii=False, indent=2), encoding="utf-8")
        return initial
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"⚠️ Error reading news_funnel.json: {e}")
        return {"current_cycle": 1, "cycle_start_date": datetime.utcnow().isoformat(), "staged_posts": [], "published_posts": []}


def _save_data(data: dict) -> bool:
    try:
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception as e:
        logger.error(f"❌ Error saving news_funnel.json: {e}")
        return False


def get_current_cycle_info() -> dict:
    """Calculates current cycle day (1 to 5+) and current funnel stage."""
    data = _load_data()
    start_dt = _parse_iso_dt(data.get("cycle_start_date"))
    diff_days = (datetime.utcnow() - start_dt).days + 1
    cycle_day = max(1, diff_days)

    if cycle_day in (1, 2, 3):
        stage_name = "दिन 1-3: AI एकत्रीकरण व ड्राफ्टिंग (Staging)"
        stage_desc = "Gemini प्रतिदिन शाम 5:00 बजे 2-3 ताज़ा कृषि समाचार खोजकर फ़नल में ड्राफ्ट करता है।"
        action_needed = False
    elif cycle_day == 4:
        stage_name = "दिन 4: समीक्षा अवधि (Manual Review Window)"
        stage_desc = "आपके रिव्यू के लिए ड्राफ्ट तैयार हैं। 'Approve & Push' पर क्लिक करें या संपादित करें।"
        action_needed = True
    else:
        stage_name = "दिन 5: स्वतः प्रकाशन (Auto-Publish Fallback)"
        stage_desc = "दिन 4 पर अप्रूव न होने पर सभी ड्राफ्ट स्वतः लाइव न्यूज़ में पुश किए जा रहे हैं।"
        action_needed = False

    return {
        "current_cycle": data.get("current_cycle", 1),
        "cycle_day": cycle_day,
        "stage_name": stage_name,
        "stage_desc": stage_desc,
        "action_needed": action_needed,
        "staged_count": len(data.get("staged_posts", [])),
        "published_count": len(data.get("published_posts", [])),
        "cycle_start_date": start_dt.strftime("%d %b %Y"),
    }


# ── AI Formatting with Gemini ─────────────────────────────────

# ── What the generator must never do ─────────────────────────
# The model is handed a HEADLINE and an RSS SUMMARY — often under 300
# characters — and was previously asked for "2-3 detailed paragraphs
# covering the background and the full process". There is only one way to
# satisfy that from a snippet: invent. That is how a subsidy percentage, an
# application deadline or an eligibility rule that exists nowhere in the
# source ends up on a page a farmer acts on.
#
# These rules are the fix at the root. The on-page disclosure in
# routes/news_page.py (_AI_DISCLOSURE) tells the reader the text is machine
# written; this stops the machine writing the dangerous parts in the first
# place. The two are a pair — do not remove either believing the other
# covers it.
#
# The ordering matters: the hard prohibitions come LAST in the prompt,
# closest to the output contract, because that is the instruction the model
# is most likely to still be honouring when it starts generating.
_EDITORIAL_RULES = """
════════════════════════════════════════════════════════════
ABSOLUTE RULES — these override every other instruction above.
Breaking any one of them makes the output unusable.
════════════════════════════════════════════════════════════

1. NEVER INVENT A FACT OR A NUMBER.
   Percentages, rupee amounts, subsidy rates, dates, deadlines, quantities,
   eligibility conditions, application steps, phone numbers and mandi prices
   may appear in your output ONLY if they appear in the RAW CONTENT above.
   If the raw content does not give a number, write the sentence WITHOUT one
   and tell the reader to check the official portal for the exact figure.
   Never estimate, never infer "typically", never fill a gap with a
   plausible value. A farmer will act on these numbers.

2. IF THE SOURCE IS THIN, WRITE LESS.
   A short, accurate story is correct. Padding to reach a length by adding
   invented background, process detail or benefits is the single worst
   failure you can produce here. full_story may be ONE short paragraph if
   that is all the source supports.

3. NAMED PEOPLE.
   Do not name, describe or characterise any private individual. A public
   official, minister or organisation may be named ONLY if the raw content
   names them, and ONLY for what the raw content actually says they did or
   said. Never allege wrongdoing, corruption, arrest, failure or misconduct
   by any named person, company, department or brand — even if the source
   hints at it. Never attribute a quote to anyone.

4. NO GUARANTEES OR PROMISES.
   Never state or imply that a farmer is guaranteed a profit, a yield, a
   price, an approval, a loan or a payout. Use "पात्र किसानों को" /
   "आवेदन करने पर" framing, never "आपको मिलेगा".

5. NO PRESCRIPTIVE CHEMICAL, MEDICAL OR VETERINARY INSTRUCTION.
   Do not give pesticide, herbicide, fertiliser or medicine dosages,
   spray concentrations, mixing ratios or brand-name product
   recommendations. Point the reader to their कृषि विज्ञान केंद्र, block
   agriculture officer or a qualified veterinarian instead.

6. NEVER IMPERSONATE AUTHORITY.
   You are writing for KrashiMitra, a private information website. Never
   write as though this is a government notice, an official circular, or an
   announcement issued by any department. Never use a government emblem,
   seal or letterhead phrasing. Never say "सरकार ने कृषि मित्र के माध्यम से".

7. WRITE ORIGINAL PROSE.
   Do not reproduce sentences from the raw content word for word. Restate
   the facts in your own simple Hindi. You are summarising a news report,
   not republishing it.

8. ATTRIBUTE CLAIMS THAT ARE NOT YOURS.
   Where a claim comes from the source, mark it: "रिपोर्ट के अनुसार",
   "सरकारी घोषणा के अनुसार", "मीडिया रिपोर्ट्स के मुताबिक". Never present a
   sourced claim as an established fact verified by KrashiMitra.

9. NO POLITICS, RELIGION, CASTE OR ALARM.
   No party praise or criticism, no political framing of a scheme, no
   religious or caste references, and no sensational or frightening
   language ("तबाही", "बर्बाद हो जाएंगे") — the site carries advertising
   and serves anxious people making money decisions.

10. NO CONTACT DETAILS OR OUTBOUND LINKS.
    Never put a phone number, WhatsApp number, bank account, UPI id, email
    or third-party URL in any field. Refer to "आधिकारिक पोर्टल" generically.

11. EVERY STORY ENDS BY SENDING THE READER TO VERIFY.
    The third bullet must always tell the farmer to confirm the details
    with the relevant government department, official portal or their
    nearest कृषि कार्यालय before acting.
"""


async def format_agri_post_with_ai(raw_title: str, raw_content: str, source_url: str = "", language: str = "hi") -> dict:
    """
    Uses Gemini to transform raw press releases, news text, or web articles into
    a high-impact, farmer-friendly news post with 3 key takeaway bullets in the selected language.
    """
    lang_code = (language or "hi").lower().strip()
    if lang_code in ["en", "english"]:
        lang_directive = """
TARGET LANGUAGE: ENGLISH
Write the entire output in clean, engaging, farmer-friendly English.
All fields (title, excerpt, full_story, bullets, catLabel) MUST BE IN ENGLISH.
"""
        default_title = raw_title[:75] if raw_title else "KrashiMitra Agriculture News Bulletin"
        default_excerpt = (raw_content[:180] + "...") if raw_content else "Latest government advisory and agricultural guidelines for farmers."
        default_bullets = [
            f"Key Announcement: {raw_title[:60] if raw_title else 'Latest Agriculture Update'}",
            "Farmer Benefit: Direct financial or productivity advantage for cultivators.",
            "Action Needed: Verify details with local agriculture extension centers or portal."
        ]
    elif lang_code in ["hinglish", "roman"]:
        lang_directive = """
TARGET LANGUAGE: HINGLISH (Conversational Hindi written in English/Roman alphabet, e.g. "Kisano ke liye nayi yojana shuru hui hai...")
Write the entire output in natural, simple Hinglish so farmers comfortable with Roman script can easily read it.
All fields (title, excerpt, full_story, bullets, catLabel) MUST BE IN HINGLISH.
"""
        default_title = "Krashi Mitra Taaza Samachar Bulletin"
        default_excerpt = "Kisano ke liye taaza sarkari nirdesh aur kheti salah."
        default_bullets = [
            f"Mukhya Bindu: {raw_title[:60] if raw_title else 'Kheti Badi Update'}",
            "Kisan Labh: Faslo ki acchi upaj aur samay par sarkari sahayata ki jankari.",
            "Zaroori Kadam: Nazdeeki krishi seva kendra ya portal par details check karein."
        ]
    else:
        lang_code = "hi"
        lang_directive = """
TARGET LANGUAGE: STRICT PURE HINDI (DEVANAGARI SCRIPT - देवनागरी हिंदी)
CRITICAL INSTRUCTION: Even if the RAW NEWS HEADLINE or RAW CONTENT is in English or any other language, you MUST TRANSLATE and WRITE THE ENTIRE RESPONSE IN PURE, FLUENT, NATURAL DEVANAGARI HINDI (हिंदी).
Under NO CIRCUMSTANCES should the title, excerpt, bullets, or full_story remain in English! Translate all official terms, names, and numbers into clear Hindi for Indian farmers.
"""
        default_title = "कृषि मित्र ताज़ा समाचार बुलेटिन"
        default_excerpt = "किसानों के लिए ताज़ा सरकारी दिशा-निर्देश, फसल सुरक्षा और कृषि सलाह।"
        default_bullets = [
            "मुख्य बिंदु: किसानों के लिए ताज़ा महत्वपूर्ण सरकारी निर्णय व कृषि अपडेट।",
            "किसान लाभ: फसलों की बेहतर पैदावार, समय पर आर्थिक अनुदान व सुरक्षा।",
            "ज़रूरी कदम: नजदीकी कृषि रक्षा इकाई अथवा आधिकारिक पोर्टल पर जानकारी सत्यापित करें।"
        ]

    recent_headlines = get_recent_headlines(limit=25)
    headlines_formatted = "\n".join([f"- {h}" for h in recent_headlines]) if recent_headlines else "None"

    # The cover library, minus what the newest posts already wear — see
    # the note above image_catalogue(). Choosing from a list is what
    # keeps the photograph both ours and non-repeating.
    avoid_covers = recently_used_covers()
    cover_library = cover_library_prompt(avoid_covers)

    prompt = f"""
You are an expert Chief Agricultural Journalist for KrashiMitra (कृषि मित्र), India's leading digital platform for farmers.
Convert the following news/advisory into an impressive, highly engaging news post for Indian farmers.

{lang_directive}

ACTIVE RECENT HEADLINES ON KRASHIMITRA (CRITICAL: DO NOT REPLICATE OR DUPLICATE THESE TOPICS):
{headlines_formatted}

CRITICAL ANTI-DUPLICATION RULE:
If the given raw news covers the EXACT SAME agricultural scheme, announcement, crop policy, or specific news story already represented in the active headlines above, respond STRICTLY with:
{{"duplicate": true, "reason": "Already published or staged on KrashiMitra"}}

RAW NEWS HEADLINE:
{raw_title}

RAW CONTENT:
{raw_content[:2500]}

{_EDITORIAL_RULES}

COVER PHOTOGRAPH — CHOOSE ONE FROM THIS LIBRARY:
KrashiMitra may NEVER republish the source website's photograph, so the cover
must come from our own picture library, listed below as "slug : what it shows".
Return the slug of the ONE picture that best shows what THIS story is about —
the crop, animal, input, machine or scheme at the centre of it. Judge by
subject, not by mood: a story about wheat irrigation wants a wheat picture.
Return "" for image_slug if nothing in the list genuinely fits — a wrong
picture is worse than a generic one. Never invent a slug, a filename or a URL;
anything not in this list is discarded.

LIBRARY:
{cover_library}

OUTPUT IN STRICT VALID JSON FORMAT ONLY (no markdown fences, no extra text):
{{
  "title": "आकर्षक व संक्षिप्त शीर्षक (अधिकतम 70 अक्षर)",
  "excerpt": "2 वाक्यों का स्पष्ट व आसान सारांश जो किसान की भाषा में हो।",
  "full_story": "1-3 पैराग्राफ, केवल उतना ही जितना RAW CONTENT वास्तव में बताता है। स्रोत में जो तथ्य नहीं है उसे कभी न जोड़ें — स्रोत छोटा हो तो कहानी भी छोटी रखें।",
  "bullets": [
    "मुख्य फैसला / बिंदु: क्या निर्णय या घोषणा हुई।",
    "किसान लाभ / प्रभाव: किसान की जेब, फसल या मंडी पर सीधा असर।",
    "ज़रूरी कदम: किसान संबंधित सरकारी विभाग या आधिकारिक पोर्टल पर जानकारी की पुष्टि करें (यह बुलेट हमेशा सत्यापन की सलाह दे)।"
  ],
  "category": "mandi | yojana | weather | crop | khad | pashu | tech",
  "catLabel": "मंडी भाव | सरकारी योजना | मौसम अलर्ट | फसल सुरक्षा | खाद सलाह | डेयरी व पशु | आधुनिक तकनीक",
  "readTime": "3 मिनट",
  "image_slug": "ऊपर दी गई LIBRARY में से चुना हुआ एक slug, या \"\" अगर कोई सही न बैठे"
}}
"""
    # The admin switch (config.news_ai_enabled). Off means we never call a
    # model here — we take the SAME path the pipeline already takes when
    # Gemini errors, which is the one below: source text as written, category
    # by keyword, cover from our own library. So "off" is a road already
    # driven and tested, not a second code path that only runs when the bill
    # arrives.
    parsed = None
    if not get_setting("news_ai_enabled", True):
        logger.info("📴 कृषि न्यूज़ AI is switched OFF — building the post from "
                    "the source text, no model call")
    else:
        try:
            response_text, source = await call_ai(prompt, max_tokens=1500)
            cleaned = re.sub(r"^```json\s*", "", response_text.strip(), flags=re.MULTILINE)
            cleaned = re.sub(r"^```\s*", "", cleaned.strip(), flags=re.MULTILINE)
            cleaned = cleaned.rstrip("`").strip()
            parsed = json.loads(cleaned)
            if parsed.get("duplicate") is True:
                logger.info(f"🚫 Gemini flagged story as duplicate: {parsed.get('reason')}")
                return None
        except Exception as e:
            logger.warning(f"⚠️ Gemini news generation fallback due to error: {e}")
            parsed = None

    if parsed is None:
        cat = "crop"
        lowered = (raw_title + " " + raw_content).lower()
        if any(w in lowered for w in ["भाव", "मंडी", "msp", "दाम", "rate", "price"]):
            cat = "mandi"
        elif any(w in lowered for w in ["योजना", "सब्सिडी", "अनुदान", "किस्त", "scheme", "package", "subsidy"]):
            cat = "yojana"
        elif any(w in lowered for w in ["मौसम", "बारिश", "ओलावृष्टि", "तापमान", "weather", "monsoon", "rain"]):
            cat = "weather"
        elif any(w in lowered for w in ["खाद", "यूरिया", "dap", "उर्वरक", "fertilizer"]):
            cat = "khad"
        elif any(w in lowered for w in ["गाय", "भैंस", "दूध", "डेयरी", "पशु", "dairy", "cattle"]):
            cat = "pashu"

        has_devanagari = any('\u0900' <= ch <= '\u097f' for ch in raw_title)
        if lang_code == "hi" and not has_devanagari:
            # Smart contextual Devanagari translation fallback for English inputs
            title_fallback = f"{CATEGORY_LABELS.get(cat, 'कृषि समाचार')}: किसानों के लिए नया सरकारी अपडेट व दिशानिर्देश"
            excerpt_fallback = "सरकार द्वारा किसानों की सहायता, फसल सुरक्षा और अनुदान संबंधी नए दिशा-निर्देश जारी किए गए हैं।"
            story_fallback = f"{excerpt_fallback}\n\nयह निर्णय किसानों की लागत कम करने और समय पर सहायता उपलब्ध कराने के उद्देश्य से लिया गया है। नजदीकी कृषि विभाग या ऑनलाइन पोर्टल पर पात्रता की जांच करें।"
        else:
            title_fallback = raw_title[:75] if raw_title else default_title
            excerpt_fallback = (raw_content[:180] + "...") if raw_content else default_excerpt
            story_fallback = (raw_content[:900] + "...") if raw_content else default_excerpt

        parsed = {
            "title": title_fallback,
            "excerpt": excerpt_fallback,
            "full_story": story_fallback,
            "bullets": default_bullets,
            "category": cat,
            "catLabel": CATEGORY_LABELS.get(cat, "🌾 कृषि न्यूज़"),
            "readTime": "3 मिनट"
        }

    final_title = parsed.get("title", raw_title).strip()
    is_dup, reason = is_duplicate_story(final_title, url=source_url, content=parsed.get("excerpt", ""))
    if is_dup:
        logger.info(f"🚫 Formatted post rejected by duplicate check: '{final_title[:45]}' ({reason})")
        return None

    category = parsed.get("category", "crop")
    if category not in CATEGORY_LABELS:
        category = "crop"

    post_id = f"km-auto-{int(datetime.utcnow().timestamp())}-{random.randint(100, 999)}"

    # Cover: the picture Gemini chose out of our own library, if it named
    # one that is really ours; keyword matching otherwise. Never the source
    # publisher's photograph — see image_catalogue().
    img = cover_from_slug(parsed.get("image_slug", "")) or pick_our_image(
        f"{final_title} {raw_title} {parsed.get('excerpt', '')}",
        category,
        seed=post_id,
        avoid=avoid_covers,
    )

    # Organic Likes Seed: 260 to 580 likes!
    seed_likes = random.randint(260, 580)

    
    full_story = parsed.get("full_story", "").strip()
    if not full_story or len(full_story) < 60:
        bullets_text = "\n\n".join([f"• {b}" for b in parsed.get("bullets", [])])
        full_story = f"{parsed.get('excerpt', '')}\n\n{bullets_text}"

    return {
        "id": post_id,
        "title": final_title,
        "excerpt": parsed.get("excerpt", ""),
        "full_story": full_story,
        "bullets": parsed.get("bullets", [])[:3],
        "category": category,
        "catLabel": CATEGORY_LABELS.get(category, "🌾 कृषि न्यूज़"),
        "readTime": parsed.get("readTime", "3 मिनट"),
        "time": "आज ताज़ा",
        "image": img,
        "link": f"#story-{post_id}",
        # "auto-pilot post", not "a model wrote this" — it pairs with the
        # km-auto- id prefix everywhere it is read, and stays True when the
        # AI switch is off and the text came straight from the source.
        "is_gemini_post": True,
        "language": lang_code,
        "source_url": source_url,
        # Kept so review_flags() can tell an invented figure from a reported
        # one. Truncated: it is a comparison corpus, not an archive.
        "source_raw": f"{raw_title} {raw_content}"[:2500],
        "seed_likes": seed_likes,
        "comment_count": 0,  # Strictly 0 initially as instructed!
        "status": "staged",
        "created_at": datetime.utcnow().isoformat(),
    }


# ── RSS & Web Harvester ───────────────────────────────────────

async def fetch_external_agri_stories() -> List[dict]:
    """
    Fetches real agricultural stories from official PIB & Google News India Kisan feeds.
    """
    feeds = [
        # Google News Agriculture India (Hindi)
        "https://news.google.com/rss/search?q=%E0%A4%95%E0%A5%83%E0%A4%B7%E0%A4%BF+%E0%A4%95%E0%A4%BF%E0%A4%B8%E0%A4%BE%E0%A4%A8+%E0%A4%AB%E0%A4%B8%E0%A4%B2+%E0%A4%AE%E0%A4%82%E0%A4%A1%E0%A5%80+%E0%A4%AF%E0%A5%8B%E0%A4%9C%E0%A4%A8%E0%A4%BE&hl=hi&gl=IN&ceid=IN:hi",
        # PIB Agriculture Feed
        "https://archive.pib.gov.in/rss/RssAgriculture.aspx",
    ]

    stories = []
    async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
        for url in feeds:
            try:
                resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0 KrashiMitra/2.0"})
                if resp.status_code == 200 and resp.text:
                    root = ET.fromstring(resp.text)
                    items = root.findall(".//item")
                    for it in items[:6]:
                        t = it.findtext("title") or ""
                        d = it.findtext("description") or ""
                        l = it.findtext("link") or ""
                        # Strip HTML from description
                        clean_d = _strip_tags(d)
                        if t and len(t) > 10:
                            stories.append({"title": t.strip(), "content": clean_d, "url": l})
            except Exception as e:
                logger.warning(f"Feed error from {url}: {e}")
                continue

    # Fallback curated seasonal topics if internet is unreachable
    if not stories:
        stories = [
            {
                "title": "रबी फसलों में सिंचाई व यूरिया प्रबंधन: कृषि वैज्ञानिकों ने जारी की नई एडवाइज़री",
                "content": "गेहूं और सरसों की फसलों में इस समय सही नमी और संतुलित नाइट्रोजन का प्रयोग उपज को 20% तक बढ़ा सकता है। वैज्ञानिकों ने नैनो यूरिया छिड़काव की सलाह दी है।",
                "url": ""
            },
            {
                "title": "पीएम कुसुम योजना 2026: खेतों में सोलर पंप लगाने के लिए 60% अनुदान का नया चरण शुरू",
                "content": "किसानों को बिजली कटौती से मुक्ति दिलाने के लिए सौर ऊर्जा से चलने वाले कृषि पंपों के लिए ऑनलाइन पोर्टल पर आवेदन प्रक्रिया पुनः खोली गई है।",
                "url": ""
            }
        ]

    return stories


async def run_discovery_and_stage(target_count: int = 3, check_cycle: bool = False) -> List[dict]:
    """
    Day 1-3 workflow: Collects fresh agri news once a day at 5:00 PM IST,
    uses Gemini to format them into impressive cards with 3 takeaway bullets,
    and stages nearly 2 to 3 posts per day.
    """
    data = _load_data()

    if check_cycle:
        start_dt = _parse_iso_dt(data.get("cycle_start_date"))
        cycle_day = max(1, (datetime.utcnow() - start_dt).days + 1)
        if cycle_day > 3:
            logger.info(f"ℹ️ Current cycle is on Day {cycle_day} (Review/Fallback phase). Skipping daily 5 PM discovery.")
            return []

    staged = data.get("staged_posts", [])
    raw_stories = await fetch_external_agri_stories()
    newly_staged = []

    for story in raw_stories:
        s_title = story.get("title", "")
        s_url = story.get("url", "")
        s_content = story.get("content", "")

        is_dup, reason = is_duplicate_story(s_title, url=s_url, content=s_content)
        if is_dup:
            logger.info(f"⏭️ Skipping duplicate raw story: '{s_title[:45]}' ({reason})")
            continue

        try:
            formatted_post = await format_agri_post_with_ai(s_title, s_content, s_url)
            if not formatted_post:
                continue

            gen_title = formatted_post.get("title", "")
            is_dup_gen, reason_gen = is_duplicate_story(gen_title, url=s_url)
            if is_dup_gen:
                logger.info(f"⏭️ Skipping duplicate AI-generated post: '{gen_title[:45]}' ({reason_gen})")
                continue

            staged.append(formatted_post)
            newly_staged.append(formatted_post)
            if s_url:
                norm_u = _normalize_url(s_url)
                if norm_u and norm_u not in data.setdefault("seen_urls", []):
                    data["seen_urls"].append(norm_u)

            if len(newly_staged) >= target_count:
                break
        except Exception as e:
            logger.error(f"Error staging story: {e}")

    data["staged_posts"] = staged
    _save_data(data)
    logger.info(f"✅ Staged {len(newly_staged)} new distinct posts into Krashi News Funnel (target: {target_count})")
    return newly_staged


# ── Smart URL Curator Tool ────────────────────────────────────

async def curate_from_url(url: str, language: str = "hi") -> dict:
    """
    Fetches an external article URL, extracts text/image using pure stdlib regex,
    and runs Gemini to create a 3-bullet news post in the selected language with deduplication.
    """
    if not url or not url.startswith("http"):
        raise ValueError("मान्य वेब लिंक (URL) दर्ज करें")

    is_dup_u, reason_u = is_duplicate_story("", url=url)
    if is_dup_u:
        raise ValueError(f"यह वेब लिंक पहले से फ़नल या लाइव वेबसाइट में मौजूद है ({reason_u})")

    async with httpx.AsyncClient(timeout=14, follow_redirects=True) as client:
        resp = await client.get(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        })
        resp.raise_for_status()

    html_text = resp.text

    # Title
    m_title = re.search(r"<title[^>]*>(.*?)</title>", html_text, re.I | re.S)
    title = html.unescape(m_title.group(1).strip()) if m_title else ""

    # Meta Description
    m_desc = re.search(r'<meta[^>]+(?:name=["\']description["\']|property=["\']og:description["\'])[^>]+content=["\']([^"\']+)["\']', html_text, re.I)
    if not m_desc:
        m_desc = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:name=["\']description["\']|property=["\']og:description["\'])', html_text, re.I)
    meta_desc = html.unescape(m_desc.group(1).strip()) if m_desc else ""

    # No hero image is taken from the page. The publisher's photograph is
    # theirs; what we render is our own — see pick_our_image.

    # Paragraphs
    p_tags = re.findall(r"<p[^>]*>(.*?)</p>", html_text, re.I | re.S)
    clean_p = [_strip_tags(p) for p in p_tags if len(_strip_tags(p)) > 30]
    full_body = "\n".join(clean_p[:8])
    combined_content = f"{meta_desc}\n{full_body}" if meta_desc else full_body

    is_dup_t, reason_t = is_duplicate_story(title, url=url, content=combined_content)
    if is_dup_t:
        raise ValueError(f"यह समाचार पहले से मौजूद है ({reason_t})")

    curated = await format_agri_post_with_ai(title, combined_content, url, language=language)
    if not curated:
        raise ValueError("Gemini ने पाया कि यह विषय पहले से ही फ़नल या वेबसाइट पर प्रकाशित खबरों में मौजूद है (Duplicate topic blocked by AI).")
    # format_agri_post_with_ai already chose a cover from our library. This
    # is the belt to that braces: whatever reaches a post here is one of
    # ours, never something lifted off the page we just fetched.
    if not str(curated.get("image", "")).startswith("/images/"):
        curated["image"] = pick_our_image(
            f"{curated.get('title', '')} {title} {combined_content}",
            curated.get("category") or "crop",
            seed=curated.get("id") or title,
            avoid=recently_used_covers(),
        )

    return curated


# ── Staging Funnel Actions ────────────────────────────────────

def get_staged_posts() -> List[dict]:
    data = _load_data()
    return data.get("staged_posts", [])


def get_published_posts() -> List[dict]:
    data = _load_data()
    return data.get("published_posts", [])


def _freeze_slug(post: dict) -> None:
    """Pin the address a post is published at, once, at publish time.

    A story page's URL is derived from its title (news_page._story_slug) and
    nothing ever stored it. So editing the title of a LIVE post silently moved
    its page: the indexed URL, the sitemap entry and every WhatsApp-shared link
    started 404ing, with no redirect left behind. _story_slug prefers a stored
    slug, so pinning it here keeps the title editable and the address still.

    Only auto-pilot posts need one — a master story's card points at the
    /articles/ page it already has, through `link`.
    """
    if post.get("slug"):
        return

    link = (post.get("link") or "").strip()
    if link and not link.startswith("#") and not link.startswith("/#"):
        return  # already has a real page somewhere else

    try:
        from backend.routes.news_page import _slugify
    except Exception as e:  # pragma: no cover — import guard
        logger.warning(f"⚠️ slug helper unavailable, URL not pinned: {e}")
        return

    s = _slugify(post.get("title") or "")
    if s:
        post["slug"] = s


def publish_post(post_id: str) -> Optional[dict]:
    """Manually publishes a staged post to the public news feed."""
    data = _load_data()
    staged = data.get("staged_posts", [])
    published = data.get("published_posts", [])

    idx = next((i for i, p in enumerate(staged) if p["id"] == post_id), None)
    if idx is None:
        return None

    target = staged.pop(idx)
    _freeze_slug(target)
    target["status"] = "published"
    target["published_at"] = datetime.utcnow().isoformat()
    target["published_by"] = "manual_admin"

    # Prepend to published list
    published.insert(0, target)
    data["staged_posts"] = staged
    data["published_posts"] = published
    _save_data(data)
    logger.info(f"🚀 Published news post: {target.get('title')}")
    return target


def publish_all_staged() -> int:
    """Publishes all currently staged posts in 1 click."""
    data = _load_data()
    staged = data.get("staged_posts", [])
    published = data.get("published_posts", [])

    count = len(staged)
    now_iso = datetime.utcnow().isoformat()

    for p in staged:
        _freeze_slug(p)
        p["status"] = "published"
        p["published_at"] = now_iso
        p["published_by"] = "manual_admin_bulk"
        published.insert(0, p)

    data["staged_posts"] = []
    data["published_posts"] = published
    # Reset cycle
    data["current_cycle"] = data.get("current_cycle", 1) + 1
    data["cycle_start_date"] = now_iso
    _save_data(data)
    logger.info(f"🚀 Bulk published {count} staged posts!")
    return count


def discard_post(post_id: str) -> bool:
    """Discards a post from either staged funnel drafts OR published feed."""
    data = _load_data()
    staged = data.get("staged_posts", [])
    orig_len_staged = len(staged)
    staged = [p for p in staged if p.get("id") != post_id]
    if len(staged) < orig_len_staged:
        data["staged_posts"] = staged
        _save_data(data)
        logger.info(f"🗑️ Discarded staged draft: {post_id}")
        return True

    published = data.get("published_posts", [])
    orig_len_pub = len(published)
    published = [p for p in published if p.get("id") != post_id]
    if len(published) < orig_len_pub:
        data["published_posts"] = published
        _save_data(data)
        logger.info(f"🗑️ Removed published post: {post_id}")
        return True

    return False


def edit_staged_post(post_id: str, updates: dict) -> Optional[dict]:
    """Edits any field of a staged draft or live published post."""
    data = _load_data()
    staged = data.get("staged_posts", [])
    target = next((p for p in staged if p.get("id") == post_id), None)
    if not target:
        published = data.get("published_posts", [])
        target = next((p for p in published if p.get("id") == post_id), None)
    if not target:
        return None

    allowed_keys = [
        "title", "excerpt", "full_story", "bullets", "category",
        "image", "seed_likes", "time", "readTime"
    ]
    for k in allowed_keys:
        if k in updates and updates[k] is not None:
            if k == "seed_likes":
                try:
                    target[k] = int(updates[k])
                except (ValueError, TypeError):
                    pass
            elif k == "bullets" and isinstance(updates[k], list):
                target[k] = [str(b).strip() for b in updates[k] if str(b).strip()]
            else:
                target[k] = updates[k]

    if "category" in updates and updates["category"] in CATEGORY_LABELS:
        target["catLabel"] = CATEGORY_LABELS[updates["category"]]

    target["updated_at"] = datetime.utcnow().isoformat()
    _save_data(data)
    logger.info(f"✏️ Successfully updated post: {post_id} - '{target.get('title')[:40]}'")
    return target


def add_direct_post(post: dict, publish_now: bool = False) -> dict:
    """Adds a new post either to the staging queue or publishes directly, preventing duplicates."""
    p_title = post.get("title", "")
    p_url = post.get("source_url", "")
    is_dup, reason = is_duplicate_story(p_title, url=p_url)
    if is_dup:
        raise ValueError(f"डुप्लीकेट पोस्ट अस्वीकृत: {reason}")

    data = _load_data()
    if publish_now:
        _freeze_slug(post)
        post["status"] = "published"
        post["published_at"] = datetime.utcnow().isoformat()
        post["published_by"] = "admin_direct"
        data.setdefault("published_posts", []).insert(0, post)
    else:
        post["status"] = "staged"
        data.setdefault("staged_posts", []).append(post)

    if p_url:
        norm_u = _normalize_url(p_url)
        if norm_u and norm_u not in data.setdefault("seen_urls", []):
            data["seen_urls"].append(norm_u)

    _save_data(data)
    return post


# ── Pre-publication review gate ──────────────────────────────
# _EDITORIAL_RULES tells the model what not to write. This checks whether it
# listened, because a prompt is a request and not a guarantee.
#
# It exists because of the Day 5 watchdog below: a staged post that nobody
# reviews publishes ITSELF after 96 hours. That is the path by which an
# invented subsidy percentage or an allegation against a named person
# reaches farmers with no human ever having read it. So a post that trips
# any check here is never auto-published — it stays staged until a person
# approves it by hand. Manual publishing is deliberately still allowed:
# the flags are advice to a human, not a veto over one.
#
# The strongest check by far is FABRICATED FIGURES. Every number in the
# generated story is compared against the raw source text the story was
# built from (stored as `source_raw` at generation time). A rupee amount or
# a percentage that appears in our copy but nowhere in the source did not
# come from the news — it came from the model.
_CONTACT_RE = re.compile(
    r"(?:\+?91[\-\s]?)?[6-9]\d{9}"          # Indian mobile number
    r"|[\w.\-]+@[\w\-]+\.[a-z]{2,}"          # email / UPI handle
    r"|https?://|www\.",                     # bare link
    re.I)

# "गारंटी", "100% मिलेगा" — promises of an outcome we cannot make.
_GUARANTEE_WORDS = ("गारंटी", "गारन्टी", "निश्चित लाभ", "पक्का मिलेगा",
                    "जरूर मिलेगा", "ज़रूर मिलेगा", "100% लाभ", "गारंटीड")

# Allegations against a named party — defamation exposure.
_ALLEGATION_WORDS = ("घोटाला", "भ्रष्टाचार", "गिरफ्तार", "धोखाधड़ी", "फर्जीवाड़ा",
                     "आरोपी", "जालसाजी", "रिश्वत", "अवैध वसूली")

# Dosage / chemical prescription.
_DOSAGE_RE = re.compile(
    r"\d+\s*(?:मिली|ml|ग्राम|gram|gm|किलो|लीटर|litre|liter)\s*(?:प्रति|/|per)\s*"
    r"(?:लीटर|एकड़|हेक्टेयर|बीघा|acre|hectare|litre)", re.I)

_POLITICAL_WORDS = ("भाजपा", "बीजेपी", "कांग्रेस", "सपा", "बसपा", "आप पार्टी",
                    "विपक्ष", "चुनाव प्रचार")

# ₹1,20,000 / 60% / 2.5 लाख — the shapes a claim-bearing figure takes.
_NUMBER_RE = re.compile(r"\d[\d,]*\.?\d*\s*(?:%|प्रतिशत|लाख|करोड़|हज़ार|हजार)?")


def _numbers(text: str) -> set:
    """Comparable numeric tokens in `text`, punctuation-normalised."""
    out = set()
    for m in _NUMBER_RE.findall(text or ""):
        n = m.replace(",", "").strip()
        n = re.sub(r"\s+", "", n)
        digits = re.sub(r"[^\d.]", "", n)
        # Single digits and years carry no claim; "3 योजनाएं" or "2026" is noise.
        if digits and len(digits.rstrip(".")) >= 2 and not re.fullmatch(r"(19|20)\d{2}", digits):
            out.add(digits.rstrip("."))
    return out


def review_flags(post: dict) -> list:
    """Reasons this post should not publish unreviewed. Empty list = clean."""
    flags = []
    body = " ".join([
        str(post.get("title") or ""), str(post.get("excerpt") or ""),
        str(post.get("full_story") or ""), " ".join(post.get("bullets") or []),
    ])

    if _CONTACT_RE.search(body):
        flags.append("इसमें फ़ोन नंबर, ईमेल या लिंक है")
    if any(w in body for w in _GUARANTEE_WORDS):
        flags.append("इसमें लाभ की गारंटी जैसा दावा है")
    if any(w in body for w in _ALLEGATION_WORDS):
        flags.append("इसमें किसी पर आरोप/अपराध का ज़िक्र है")
    if _DOSAGE_RE.search(body):
        flags.append("इसमें दवा/रसायन की मात्रा बताई गई है")
    if any(w in body for w in _POLITICAL_WORDS):
        flags.append("इसमें राजनीतिक दल का ज़िक्र है")

    # The fabrication check. Only meaningful when we kept the source text.
    raw = str(post.get("source_raw") or "")
    if raw:
        invented = _numbers(body) - _numbers(raw)
        if invented:
            shown = ", ".join(sorted(invented)[:5])
            flags.append(f"स्रोत में न होने वाले आंकड़े: {shown}")

    return flags


# ── Day 5 Auto-Push Fallback Engine ───────────────────────────

def check_and_run_day5_fallback() -> List[dict]:
    """
    Day 5 Rule:
    If posts are unapproved on Day 4, the watchdog automatically promotes them
    to 'published' on Day 5 so the public news stream never gets stale!
    """
    data = _load_data()
    staged = data.get("staged_posts", [])
    published = data.get("published_posts", [])

    if not staged:
        return []

    start_dt = _parse_iso_dt(data.get("cycle_start_date"))
    diff_days = (datetime.utcnow() - start_dt).days + 1
    auto_published = []

    # If cycle day >= 5 (or any post is older than 96 hours)
    now = datetime.utcnow()
    remaining_staged = []

    for p in staged:
        created_dt = _parse_iso_dt(p.get("created_at", data.get("cycle_start_date")))
        age_hours = (now - created_dt).total_seconds() / 3600.0

        due = diff_days >= 5 or age_hours >= 96.0
        flags = review_flags(p) if due else []
        if flags:
            # Never auto-publish something that tripped a check. It stays
            # staged for a human — see review_flags() for why this gate
            # exists at all.
            p["review_flags"] = flags
            p["held_for_review"] = True
            logger.warning(f"🛑 Held from auto-publish ({p.get('title','')[:50]}): {flags}")
            remaining_staged.append(p)
            continue
        if due:
            _freeze_slug(p)
            p["status"] = "published"
            p["published_at"] = now.isoformat()
            p["published_by"] = "auto_pilot_day5_fallback"
            published.insert(0, p)
            auto_published.append(p)
        else:
            remaining_staged.append(p)

    if auto_published:
        data["staged_posts"] = remaining_staged
        data["published_posts"] = published
        # Start new cycle
        data["current_cycle"] = data.get("current_cycle", 1) + 1
        data["cycle_start_date"] = now.isoformat()
        _save_data(data)
        logger.info(f"⚡ [Day 5 Fallback] Auto-published {len(auto_published)} unreviewed posts to public feed!")

    return auto_published
