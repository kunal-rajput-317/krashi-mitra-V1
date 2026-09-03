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
from urllib.parse import urljoin

import httpx

from backend.services.chatbot_service import call_ai

logger = logging.getLogger("krishi.news_auto_service")

DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "news_funnel.json"


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

    prompt = f"""
You are an expert Chief Agricultural Journalist for KrashiMitra (कृषि मित्र), India's leading digital platform for farmers.
Convert the following news/advisory into an impressive, highly engaging news post for Indian farmers.

{lang_directive}

RAW NEWS HEADLINE:
{raw_title}

RAW CONTENT:
{raw_content[:2500]}

OUTPUT IN STRICT VALID JSON FORMAT ONLY (no markdown fences, no extra text):
{{
  "title": "आकर्षक व संक्षिप्त शीर्षक (अधिकतम 70 अक्षर)",
  "excerpt": "2 वाक्यों का स्पष्ट व आसान सारांश जो किसान की भाषा में हो।",
  "full_story": "2-3 विस्तृत पैराग्राफ की पूरी रिपोर्ट जिसमें पृष्ठभूमि, किसानों को मिलने वाली सहायता, मंडी भाव या फसल पर असर, और पूरी प्रक्रिया विस्तार से लिखी हो।",
  "bullets": [
    "मुख्य फैसला / बिंदु: क्या निर्णय या घोषणा हुई।",
    "किसान लाभ / प्रभाव: किसान की जेब, फसल या मंडी पर सीधा असर।",
    "ज़रूरी कदम / सलाह: किसान को अब क्या करना चाहिए या क्या सावधानी बरतनी है।"
  ],
  "category": "mandi | yojana | weather | crop | khad | pashu | tech",
  "catLabel": "मंडी भाव | सरकारी योजना | मौसम अलर्ट | फसल सुरक्षा | खाद सलाह | डेयरी व पशु | आधुनिक तकनीक",
  "readTime": "3 मिनट"
}}
"""
    try:
        response_text, source = await call_ai(prompt, max_tokens=1500)
        cleaned = re.sub(r"^```json\s*", "", response_text.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r"^```\s*", "", cleaned.strip(), flags=re.MULTILINE)
        cleaned = cleaned.rstrip("`").strip()
        parsed = json.loads(cleaned)
    except Exception as e:
        logger.warning(f"⚠️ Gemini news generation fallback due to error: {e}")
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

    category = parsed.get("category", "crop")
    if category not in CATEGORY_LABELS:
        category = "crop"

    # Assign image
    img = DEFAULT_CATEGORY_IMAGES.get(category, "/images/articles/dhan-nursery-ropai-card.webp")

    # Organic Likes Seed: 260 to 580 likes!
    seed_likes = random.randint(260, 580)

    post_id = f"km-auto-{int(datetime.utcnow().timestamp())}-{random.randint(100, 999)}"
    
    full_story = parsed.get("full_story", "").strip()
    if not full_story or len(full_story) < 60:
        bullets_text = "\n\n".join([f"• {b}" for b in parsed.get("bullets", [])])
        full_story = f"{parsed.get('excerpt', '')}\n\n{bullets_text}"

    return {
        "id": post_id,
        "title": parsed.get("title", raw_title),
        "excerpt": parsed.get("excerpt", ""),
        "full_story": full_story,
        "bullets": parsed.get("bullets", [])[:3],
        "category": category,
        "catLabel": CATEGORY_LABELS.get(category, "🌾 कृषि न्यूज़"),
        "readTime": parsed.get("readTime", "3 मिनट"),
        "time": "आज ताज़ा",
        "image": img,
        "link": f"#story-{post_id}",
        "is_gemini_post": True,
        "language": lang_code,
        "source_url": source_url,
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
    existing_titles = set(p.get("title", "") for p in staged + data.get("published_posts", []))

    raw_stories = await fetch_external_agri_stories()
    newly_staged = []

    for story in raw_stories:
        # Check title duplication
        if any(story["title"][:20] in et for et in existing_titles):
            continue

        try:
            formatted_post = await format_agri_post_with_ai(story["title"], story["content"], story.get("url", ""))
            staged.append(formatted_post)
            newly_staged.append(formatted_post)
            existing_titles.add(formatted_post["title"])
            if len(newly_staged) >= target_count:
                break
        except Exception as e:
            logger.error(f"Error staging story: {e}")

    data["staged_posts"] = staged
    _save_data(data)
    logger.info(f"✅ Staged {len(newly_staged)} new posts into Krashi News Funnel (Daily 5 PM sweep, target: {target_count})")
    return newly_staged


# ── Smart URL Curator Tool ────────────────────────────────────

async def curate_from_url(url: str, language: str = "hi") -> dict:
    """
    Fetches an external article URL, extracts text/image using pure stdlib regex,
    and runs Gemini to create a 3-bullet news post in the selected language.
    """
    if not url or not url.startswith("http"):
        raise ValueError("मान्य वेब लिंक (URL) दर्ज करें")

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

    # Hero Image: og:image, twitter:image, or featured image
    hero_image = ""
    m_img = re.search(r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image|twitter:image:src)["\'][^>]+content=["\']([^"\']+)["\']', html_text, re.I)
    if not m_img:
        m_img = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:og:image|twitter:image|twitter:image:src)["\']', html_text, re.I)
    if m_img:
        hero_image = m_img.group(1).strip()

    if not hero_image:
        m_post_img = re.search(r'<img[^>]+src=["\']([^"\']+(?:jpg|jpeg|png|webp)[^"\']*)["\']', html_text, re.I)
        if m_post_img:
            cand = m_post_img.group(1).strip()
            if not any(ign in cand.lower() for ign in ["logo", "icon", "avatar", "advert", "banner"]):
                hero_image = cand

    if hero_image:
        hero_image = urljoin(url, hero_image)

    # Paragraphs
    p_tags = re.findall(r"<p[^>]*>(.*?)</p>", html_text, re.I | re.S)
    clean_p = [_strip_tags(p) for p in p_tags if len(_strip_tags(p)) > 30]
    full_body = "\n".join(clean_p[:8])
    combined_content = f"{meta_desc}\n{full_body}" if meta_desc else full_body

    curated = await format_agri_post_with_ai(title, combined_content, url, language=language)
    if hero_image:
        curated["image"] = hero_image
    else:
        # Contextual intelligent crop image fallback
        low = (title + " " + combined_content).lower()
        if any(k in low for k in ["धान", "rice", "paddy", "kuruvai", "कुरुवई"]):
            curated["image"] = "/images/articles/dhan-nursery-ropai-card.webp"
        elif any(k in low for k in ["गन्ना", "sugar", "cane"]):
            curated["image"] = "/images/articles/ganna-pricing-analytics-up-card.webp"
        elif any(k in low for k in ["सोलर", "solar", "कुसुम", "kusum", "योजना"]):
            curated["image"] = "/images/articles/pm-kusum-solar-pump-yojana-card.webp"
        elif any(k in low for k in ["गेहूं", "wheat", "मंडी"]):
            curated["image"] = "/images/articles/gehuu-price-analytic-up-card.webp"
        elif any(k in low for k in ["खाद", "यूरिया", "dap"]):
            curated["image"] = "/images/articles/urea-guide-up-card.webp"
        elif any(k in low for k in ["दूध", "डेयरी", "dairy"]):
            curated["image"] = "/images/articles/dairy-farming-doodh-utpadan-card.webp"
        elif any(k in low for k in ["ड्रोन", "drone", "तकनीक"]):
            curated["image"] = "/images/articles/kisan-drone-chhidkav-card.webp"

    return curated


# ── Staging Funnel Actions ────────────────────────────────────

def get_staged_posts() -> List[dict]:
    data = _load_data()
    return data.get("staged_posts", [])


def get_published_posts() -> List[dict]:
    data = _load_data()
    return data.get("published_posts", [])


def publish_post(post_id: str) -> Optional[dict]:
    """Manually publishes a staged post to the public news feed."""
    data = _load_data()
    staged = data.get("staged_posts", [])
    published = data.get("published_posts", [])

    idx = next((i for i, p in enumerate(staged) if p["id"] == post_id), None)
    if idx is None:
        return None

    target = staged.pop(idx)
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
    data = _load_data()
    staged = data.get("staged_posts", [])
    orig_len = len(staged)
    staged = [p for p in staged if p["id"] != post_id]
    if len(staged) < orig_len:
        data["staged_posts"] = staged
        _save_data(data)
        return True
    return False


def edit_staged_post(post_id: str, updates: dict) -> Optional[dict]:
    data = _load_data()
    staged = data.get("staged_posts", [])
    target = next((p for p in staged if p["id"] == post_id), None)
    if not target:
        published = data.get("published_posts", [])
        target = next((p for p in published if p["id"] == post_id), None)
    if not target:
        return None

    for k in ["title", "excerpt", "bullets", "category", "image"]:
        if k in updates:
            target[k] = updates[k]
    if "category" in updates:
        target["catLabel"] = CATEGORY_LABELS.get(updates["category"], target.get("catLabel"))

    _save_data(data)
    return target


def add_direct_post(post: dict, publish_now: bool = False) -> dict:
    """Adds a new post either to the staging queue or publishes directly."""
    data = _load_data()
    if publish_now:
        post["status"] = "published"
        post["published_at"] = datetime.utcnow().isoformat()
        post["published_by"] = "admin_direct"
        data.setdefault("published_posts", []).insert(0, post)
    else:
        post["status"] = "staged"
        data.setdefault("staged_posts", []).append(post)

    _save_data(data)
    return post


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

        if diff_days >= 5 or age_hours >= 96.0:
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
