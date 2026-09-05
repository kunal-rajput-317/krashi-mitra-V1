# ============================================================
# backend/routes/news_page.py
# KrashiMitra — Server-Side Rendered (SSR) Krashi News Hub
# Renders directly via FastAPI HTMLResponse (like /bhav)
# ============================================================

import json
import logging
import os
import re
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from backend.services.news_auto_service import get_published_posts

logger = logging.getLogger("krishi.news_page_ssr")

router = APIRouter(tags=["Krashi News SSR"])

SITE = "https://krashimitra.in"
_ANALYTICS = '<script src="/analytics.js"></script>'
_FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400..700;1,9..40,400..700&family=Noto+Sans+Devanagari:wght@400;500;600;700;800&family=Noto+Serif+Devanagari:wght@600;700;800&family=Sora:wght@400;600;700;800&display=swap" rel="stylesheet">'
)
_ICON = f'<link rel="icon" href="{SITE}/assets/krashimitra_logo.png" type="image/png">'

_BASE_RESET_CSS = """
:root{--green-dark:#1a3c2e;--green-mid:#2d6a4f;--green-light:#52b788;--green-pale:#d8f3dc;
--amber:#e9a825;--sky:#2e86de;--cream:#f5f7f4;--white:#fff;--text-dark:#1a2e23;--text-mid:#4a5a52;
--text-soft:#7c8983;--border:#e5e9e6;--shadow-sm:0 2px 10px rgba(26,60,46,.05);
--shadow-md:0 8px 28px rgba(26,60,46,.10);--radius-sm:12px;--radius-md:18px;
--font-serif:'Noto Serif Devanagari','Playfair Display',serif;
--font-body:'DM Sans','Noto Sans Devanagari',sans-serif}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:var(--font-body);background:var(--cream);color:var(--text-dark);line-height:1.6}
img{max-width:100%}
.header-wrapper{position:fixed;top:0;left:0;right:0;z-index:200;transition:transform .28s cubic-bezier(.4,0,.2,1)}
.pre-topbar{background:var(--amber);color:#1a2e1e;display:flex;align-items:center;justify-content:center;gap:10px;padding:7px 16px;font-size:13px;font-weight:600;text-align:center}
.pre-topbar-helpline{display:inline-flex;align-items:center;gap:6px;color:inherit;text-decoration:none;opacity:.9}
.pre-topbar-helpline:hover{opacity:1;text-decoration:underline}
.pre-topbar-phone-icon{display:inline-flex;align-items:center;justify-content:center;width:19px;height:19px;font-size:10px}
.top-utility-bar{background:var(--white);border-bottom:1px solid var(--border);padding:6px 0;font-size:12px}
.top-utility-inner{max-width:1280px;margin:0 auto;display:flex;justify-content:space-between;align-items:center;padding:0 40px}
@media(max-width:768px){.top-utility-bar{display:none!important}}
.topbar-spacer{height:135px}
@media(max-width:768px){.topbar-spacer{height:88px!important}}
.crumbs{max-width:1240px;margin:0 auto;padding:12px 24px 0;box-sizing:border-box;font-size:13px;color:var(--text-soft)}
@media(max-width:768px){.crumbs{padding:8px 14px 0!important;font-size:11.5px}}
.top-utility-left,.top-utility-right{display:flex;align-items:center;gap:12px}
.top-utility-link{color:var(--text-mid);text-decoration:none;font-weight:600}
.top-utility-link:hover{color:var(--green-mid)}
.top-utility-divider{color:var(--border)}
.top-utility-helpline{display:inline-flex;align-items:center;gap:6px;color:var(--green-dark);font-weight:700;text-decoration:none}
.top-utility-helpline:hover{opacity:.8;text-decoration:underline}
.main-header{background:var(--white);border-bottom:1px solid var(--border);padding:10px 0}
.main-header-inner{max-width:1280px;margin:0 auto;display:flex;align-items:center;justify-content:space-between;padding:0 40px;gap:16px}
@media(max-width:768px){.main-header-inner{padding:0 14px}}
.header-left-group{display:flex;align-items:center;gap:12px}
.header-logo-link{display:flex;align-items:center;gap:10px;text-decoration:none;color:var(--green-dark)}
.header-logo-circle{width:38px;height:38px;border-radius:50%;object-fit:contain}
.header-logo-text{font-family:var(--font-serif);font-size:22px;font-weight:700;color:var(--green-dark)}
.header-nav{display:flex;align-items:center;gap:6px}
@media(max-width:880px){.header-nav{display:none}}
.header-nav-link{padding:8px 14px;border-radius:20px;font-size:13.5px;font-weight:600;color:var(--text-mid);text-decoration:none;transition:background .15s,color .15s}
.header-nav-link:hover{background:var(--green-pale);color:var(--green-dark)}
.header-nav-link.active{background:var(--green-dark);color:var(--white)}
.header-right-group{display:flex;align-items:center;gap:10px}
.hamburger-btn{display:none;background:none;border:none;font-size:22px;color:var(--text-dark);cursor:pointer;padding:4px 8px}
@media(max-width:880px){.hamburger-btn{display:inline-flex}}
.km-hlang{position:relative}
.km-hlang-btn{background:var(--cream);border:1px solid var(--border);border-radius:16px;padding:5px 10px;font-size:12px;font-weight:700;cursor:pointer;display:flex;align-items:center;gap:4px;color:var(--text-dark)}
.km-hlang-menu{display:none;position:absolute;top:100%;right:0;margin-top:4px;background:var(--white);border:1px solid var(--border);border-radius:8px;box-shadow:var(--shadow-md);z-index:300;min-width:110px;overflow:hidden}
.km-hlang.open .km-hlang-menu{display:block}
.km-hlang-menu button{width:100%;text-align:left;background:none;border:none;padding:8px 12px;font-size:12px;font-weight:600;cursor:pointer;color:var(--text-dark);display:flex;align-items:center;gap:6px}
.km-hlang-menu button:hover{background:var(--green-pale)}
.header-avatar-btn{width:34px;height:34px;border-radius:50%;background:var(--green-pale);color:var(--green-dark);display:inline-flex;align-items:center;justify-content:center;text-decoration:none;font-size:16px}
.sidebar-drawer-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:999;backdrop-filter:blur(3px)}
.sidebar-drawer-overlay.open{display:block}
.sidebar-drawer{position:fixed;top:0;left:0;bottom:0;width:280px;background:var(--white);z-index:1000;box-shadow:var(--shadow-md);display:flex;flex-direction:column}
.sidebar-drawer-header{display:flex;align-items:center;justify-content:space-between;padding:16px 20px;border-bottom:1px solid var(--border)}
.sidebar-drawer-title{font-size:18px;font-weight:700;color:var(--green-dark)}
.sidebar-drawer-close{background:none;border:none;font-size:22px;cursor:pointer;color:var(--text-mid)}
.sidebar-drawer-links{flex:1;overflow-y:auto;padding:12px 14px;display:flex;flex-direction:column;gap:4px}
.sidebar-drawer-link{display:flex;align-items:center;gap:12px;padding:10px 14px;border-radius:8px;text-decoration:none;color:var(--text-dark);font-weight:600;font-size:14px;transition:background .15s}
.sidebar-drawer-link:hover{background:var(--green-pale);color:var(--green-dark)}
.sidebar-drawer-link.active{background:var(--green-dark);color:var(--white)}
.crumbs{font-size:13px;color:var(--text-soft)}
.crumbs a{color:var(--green-mid);text-decoration:none;font-weight:600}
.crumbs a:hover{text-decoration:underline}
.crumbs .current{color:var(--text-dark);font-weight:700}
.km-footer{background:#0f172a;color:#f8fafc;padding:36px 20px 24px;margin-top:60px}
.km-footer-inner{max-width:1240px;margin:0 auto;display:flex;flex-direction:column;align-items:center;text-align:center;gap:16px}
.km-footer-brand{font-size:22px;font-weight:800;color:#22c55e}
.km-footer-nav{display:flex;gap:18px;flex-wrap:wrap;justify-content:center}
.km-footer-nav a{color:#94a3b8;text-decoration:none;font-size:13.5px;font-weight:600}
.km-footer-nav a:hover{color:#fff}
.km-footer-note{font-size:12px;color:#64748b;margin-top:8px}
"""

def _calc_seed_likes(news_id: str) -> int:
    h = 0
    for ch in str(news_id):
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return 12 + (h % 34)

_FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
_NEWS_DATA_FILE = _FRONTEND_DIR / "krashi_news_data.js"

# Cache for master articles from krashi_news_data.js
_articles_cache = {"stamp": None, "articles": []}

_CACHE_HEADERS = {
    "Cache-Control": "public, max-age=300",
    "Netlify-CDN-Cache-Control": "public, durable, max-age=1800, stale-while-revalidate=86400",
}


def _load_master_articles() -> List[dict]:
    """Fast linear parser for window.KRASHI_NEWS_ARTICLES with in-memory caching."""
    if _articles_cache["articles"]:
        return _articles_cache["articles"]
    try:
        if not _NEWS_DATA_FILE.is_file():
            return []
        text = _NEWS_DATA_FILE.read_text(encoding="utf-8", errors="ignore")
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
        _articles_cache["articles"] = items
        return items
    except Exception as e:
        logger.warning(f"Error reading master news articles: {e}")
        return _articles_cache.get("articles", [])


# ============================================================
# Per-story URLs
# ------------------------------------------------------------
# The hub renders every story with onclick="openStoryReader(id)" and
# href="#", so until now the whole section lived at ONE address. Googlebot
# does not run those handlers: it saw a single page whose content changed
# under it every time the auto-pilot published, and could not rank a single
# story. A news section earns its traffic from stories ("गेहूं MSP 2026
# बढ़ा"), never from the word "न्यूज़" — so each story needs its own URL.
#
# Master articles already carry `slug` and a `link` into /articles/<slug>;
# those keep pointing at the real article page, which is the stronger URL.
# Auto-pilot posts have the body (`full_story` + `bullets`) but no slug at
# all, so one is derived from the title here and served at
# /krashi_news/<slug>.
#
# The slug is transliterated Devanagari, not percent-encoded Devanagari:
# it survives a WhatsApp paste intact (the site's main sharing surface),
# it matches the lowercase-ASCII convention every other URL on the site
# uses, and ~40% of the site's search impressions are already romanised
# Hindi typed exactly this way. Derivation is deterministic — the same
# title always yields the same slug — so a link shared today still
# resolves after a restart, with no slug column to migrate.
# ============================================================

# Devanagari → Latin. Consonants carry an inherent 'a' which a matra
# replaces and a halant (्) suppresses; that rule is what makes the output
# readable rather than a run of consonants.
_DEV_VOWELS = {
    "अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo",
    "ऋ": "ri", "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au", "ऑ": "o",
}
_DEV_MATRAS = {
    "ा": "aa", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo", "ृ": "ri",
    "े": "e", "ै": "ai", "ो": "o", "ौ": "au", "ॉ": "o",
}
_DEV_CONS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n",
    "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "n",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "व": "v", "ळ": "l",
    "श": "sh", "ष": "sh", "स": "s", "ह": "h",
    "क़": "q", "ख़": "kh", "ग़": "g", "ज़": "z", "ड़": "r", "ढ़": "rh",
    "फ़": "f", "य़": "y",
}
_DEV_DIGITS = {"०": "0", "१": "1", "२": "2", "३": "3", "४": "4",
               "५": "5", "६": "6", "७": "7", "८": "8", "९": "9"}
_HALANT = "्"
_NASALS = {"ं": "n", "ँ": "n", "ः": "h"}


def _translit(text: str) -> str:
    """'गेहूं का भाव' → 'gehoon kaa bhaav'. Best-effort and lossy by design —
    the output is a URL slug, not a reversible romanisation."""
    out = []
    chars = list(text or "")
    i = 0
    while i < len(chars):
        ch = chars[i]
        nxt = chars[i + 1] if i + 1 < len(chars) else ""
        # Nukta forms arrive as two code points (ज + ़); fold them first.
        if nxt == "़" and (ch + nxt) in _DEV_CONS:
            ch, i = ch + nxt, i + 1
            nxt = chars[i + 1] if i + 1 < len(chars) else ""
        if ch in _DEV_CONS:
            out.append(_DEV_CONS[ch])
            if nxt == _HALANT:
                i += 2               # halant: no inherent vowel
                continue
            if nxt in _DEV_MATRAS:
                out.append(_DEV_MATRAS[nxt])
                i += 2
                continue
            out.append("a")          # inherent vowel
            i += 1
            continue
        if ch in _DEV_VOWELS:
            out.append(_DEV_VOWELS[ch])
        elif ch in _NASALS:
            out.append(_NASALS[ch])
        elif ch in _DEV_DIGITS:
            out.append(_DEV_DIGITS[ch])
        elif ch in _DEV_MATRAS:
            out.append(_DEV_MATRAS[ch])   # stray matra, no base consonant
        elif ch == "़":
            pass                          # bare nukta
        else:
            out.append(ch)
        i += 1
    return "".join(out)


_SLUG_MAX = 70


def _slugify(text: str) -> str:
    """Transliterate, then reduce to the site's lowercase-ASCII slug form."""
    s = _translit(text or "").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    if len(s) > _SLUG_MAX:                     # cut on a word boundary
        s = s[:_SLUG_MAX].rsplit("-", 1)[0]
    return s.strip("-")


def _story_slug(item: dict) -> str:
    """The slug a story is addressed by. Stored `slug` wins so a master
    article keeps the slug its /articles/ page already uses."""
    if item.get("slug"):
        return str(item["slug"]).strip("/")
    s = _slugify(item.get("title") or "")
    if s:
        return s
    # No title worth slugging — fall back to the id, which is always unique.
    return re.sub(r"[^a-z0-9-]+", "-", str(item.get("id") or "khabar").lower()).strip("-")


def _story_url(item: dict) -> str:
    """Where a story card should point.

    A master article already HAS a full page at /articles/<slug> — that page
    is longer, older and better linked, so the card points there and the
    news hub feeds it rather than competing with it. Auto-pilot posts have
    no such page, so they get one here.
    """
    link = (item.get("link") or "").strip()
    # Auto-pilot posts ship link="#story-<id>" — an in-page anchor for the
    # modal, not an address. Anything anchor-shaped is not a page.
    if link.startswith("#") or link.startswith("/#"):
        link = ""
    if link.startswith("http"):
        return link
    if link:
        return "/" + link.lstrip("/")
    return f"/krashi_news/{_story_slug(item)}"


# ── Images must be ours ──────────────────────────────────────
# A story's `image` can arrive as a third-party URL (the admin image
# updater accepts a pasted link, and two published posts were hotlinking
# upload.wikimedia.org). Rendering one is three separate problems at once:
#
#   1. Licence. Wikimedia Commons files are mostly CC-BY-SA, which REQUIRES
#      visible author + licence credit. We display none, so every such
#      render is a licence breach.
#   2. Personality rights. One live post illustrated a Tamil Nadu paddy
#      compensation story with a portrait of a named public figure who has
#      nothing to do with it — a photo of a real person implying an
#      involvement that does not exist.
#   3. Hotlinking. It serves someone else's bandwidth from our pages,
#      against Wikimedia's policy, and the image dies whenever they move it.
#
# So the rule is structural rather than editorial: only a same-origin path
# is ever rendered. Anything external falls back to our own category art.
# That way a bad paste in the admin panel cannot reach a reader, and no
# future story can reintroduce the problem by accident.
_FALLBACK_IMAGE = "/images/og-banner.webp"


def _safe_image(story: dict) -> str:
    """The image to render for `story` — guaranteed to be one of ours."""
    img = (story.get("image") or "").strip()
    if img and not img.startswith("http") and not img.startswith("//"):
        return img if img.startswith("/") else "/" + img
    try:
        from backend.services.news_auto_service import DEFAULT_CATEGORY_IMAGES
        return DEFAULT_CATEGORY_IMAGES.get(story.get("category") or "", _FALLBACK_IMAGE)
    except Exception:
        return _FALLBACK_IMAGE


def _client_stories(stories: List[dict]) -> List[dict]:
    """The story list handed to the browser as window.KRASHI_ALL_NEWS.

    Every client-side consumer — the modal reader, the share sheet, the
    audio player — reads `image` straight off this payload, so sanitising
    it server-side here is what stops a hotlinked third-party image from
    reaching a reader through the modal after _safe_image already kept it
    out of the server-rendered card. Copies, never mutation: the master
    article list is cached in memory and shared across requests.

    `url` is added so client code has the story's real address without
    having to re-derive the slug in JavaScript.
    """
    out = []
    for s in stories:
        c = dict(s)
        c["image"] = _safe_image(s)
        c["url"] = _story_url(s)
        out.append(c)
    return out


def _is_auto_post(item: dict) -> bool:
    return str(item.get("id") or "").startswith("km-auto-") or bool(item.get("is_gemini_post"))


def _all_stories() -> List[dict]:
    """Auto-pilot posts first (they are the fresh ones), then the master
    dataset, de-duplicated by id. The hub and every story page read the
    same list, so a card and its page can never disagree."""
    stories: List[dict] = []
    seen = set()
    for p in get_published_posts():
        if p.get("id") and p["id"] not in seen:
            seen.add(p["id"])
            stories.append(p)
    for m in _load_master_articles():
        if m.get("id") and m["id"] not in seen:
            seen.add(m["id"])
            stories.append(m)
    return stories


def _find_story(slug: str) -> Optional[dict]:
    """Resolve /krashi_news/<slug>. Slug first, then id, so an older link
    built on the raw id keeps working."""
    want = (slug or "").strip("/").lower()
    if not want:
        return None
    stories = _all_stories()
    for s in stories:
        if _story_slug(s).lower() == want:
            return s
    for s in stories:
        if str(s.get("id") or "").lower() == want:
            return s
    return None


NEWS_EXTRA_CSS = """
/* ── Minimal Editorial Krashi News Theme (matches /bhav style) ── */
:root {
  --news-dark:   #1a3c2e;
  --news-green:  #2d6a4f;
  --news-accent: #15803d;
  --news-bg:     #f8faf8;
  --news-card:   #ffffff;
  --news-border: #e2e8e4;
  --news-text:   #1e293b;
  --news-muted:  #64748b;
  --news-light:  #94a3b8;
}

/* Page Frame */
.page-container {
  max-width: 1240px;
  margin: 0 auto;
  padding: 16px 24px 60px;
  box-sizing: border-box;
}
@media (max-width: 768px) {
  .page-container { padding: 12px 14px 40px; }
}

/* Header Title */
.news-header-title-row {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  margin-bottom: 20px;
  padding-bottom: 14px;
  border-bottom: 1.5px solid var(--news-border);
  gap: 6px;
}
.news-page-title-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  flex-wrap: wrap;
}
.news-page-title {
  font-family: 'Noto Serif Devanagari', 'Sora', Georgia, serif;
  font-size: 26px;
  font-weight: 800;
  color: #0284c7;
  margin: 0;
  display: inline-flex;
  align-items: center;
}
.news-count-pill {
  background: #e0f2fe;
  color: #0369a1;
  border: 1px solid #bae6fd;
  font-size: 12px;
  font-weight: 700;
  padding: 3px 10px;
  border-radius: 12px;
}
.news-page-date {
  font-size: 12.5px;
  color: var(--news-muted);
  font-weight: 600;
  text-align: center;
}

/* ── Editorial Spotlight (Lead + Top List) ── */
.spotlight-grid {
  display: grid;
  grid-template-columns: 1.7fr 1fr;
  gap: 24px;
  margin-bottom: 30px;
}
@media (max-width: 960px) {
  .spotlight-grid { grid-template-columns: 1fr; }
}
.lead-story {
  background: var(--news-card);
  border: 1.5px solid #111827;
  border-radius: 12px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  text-decoration: none;
  color: inherit;
  box-shadow: 0 2px 8px rgba(0,0,0,0.07);
  transition: box-shadow 0.2s, transform 0.15s;
}
.lead-story:hover {
  box-shadow: 0 8px 24px rgba(0,0,0,0.12);
  transform: translateY(-2px);
  border-color: #000000;
}
.recent-posts-tab-card {
  background: var(--news-card);
  border: 1.5px solid #111827;
  border-radius: 12px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  box-shadow: 0 2px 8px rgba(0,0,0,0.07);
  position: relative;
  transition: box-shadow 0.2s, border-color 0.2s;
}
.recent-posts-tab-card:hover {
  box-shadow: 0 8px 24px rgba(0,0,0,0.12);
  border-color: #000000;
}
.recent-tab-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  background: #f8fafc;
  border-bottom: 1.5px solid var(--border);
  gap: 12px;
  flex-wrap: wrap;
}
.recent-tab-title-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
}
.recent-tab-badge {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 13px;
  font-weight: 800;
  color: var(--text-dark);
  letter-spacing: 0.01em;
}
.recent-badge-sub {
  font-size: 11px;
  font-weight: 700;
  color: var(--text-soft);
}
.recent-live-dot {
  width: 8px;
  height: 8px;
  background: #16a34a;
  border-radius: 50%;
  display: inline-block;
  box-shadow: 0 0 0 0 rgba(22, 163, 74, 0.7);
  animation: recentPulseDot 1.8s infinite;
}
@keyframes recentPulseDot {
  0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(22, 163, 74, 0.7); }
  70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(22, 163, 74, 0); }
  100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(22, 163, 74, 0); }
}
.recent-tab-nav {
  display: flex;
  align-items: center;
  gap: 10px;
}
.recent-tab-pills {
  display: flex;
  align-items: center;
  gap: 6px;
}
.recent-tab-pill {
  border: 1px solid var(--border);
  background: #ffffff;
  color: var(--text-soft);
  font-size: 11.5px;
  font-weight: 700;
  padding: 4px 10px;
  border-radius: 14px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
  user-select: none;
}
.recent-tab-pill .pill-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #94a3b8;
  transition: background 0.2s;
}
.recent-tab-pill:hover {
  border-color: var(--green-mid);
  color: var(--green-mid);
}
.recent-tab-pill.active {
  background: var(--green-dark);
  border-color: var(--green-dark);
  color: #ffffff;
  box-shadow: 0 1px 4px rgba(26, 60, 46, 0.2);
}
.recent-tab-pill.active .pill-dot {
  background: #4ade80;
}
.recent-arrow-btns {
  display: flex;
  align-items: center;
  gap: 4px;
}
.recent-arrow-btn {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  border: 1px solid var(--border);
  background: #ffffff;
  color: var(--text-dark);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.15s ease;
  user-select: none;
  padding: 0;
}
.recent-arrow-btn:hover {
  background: #f1f5f9;
  border-color: #94a3b8;
  color: #000;
}
.recent-slider-viewport {
  width: 100%;
  overflow: hidden;
  position: relative;
  flex: 1;
  display: flex;
  flex-direction: column;
}
.recent-slider-track {
  display: flex;
  width: 100%;
  will-change: transform;
  transition: transform 0.45s cubic-bezier(0.25, 1, 0.5, 1);
}
.recent-slide {
  min-width: 100%;
  width: 100%;
  flex-shrink: 0;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  background: #ffffff;
}
.recent-slide-meta-badge {
  position: absolute;
  top: 12px;
  right: 14px;
  z-index: 2;
}
.recent-post-number-tag {
  background: rgba(15, 23, 42, 0.78);
  color: #ffffff;
  font-size: 11px;
  font-weight: 700;
  padding: 3px 9px;
  border-radius: 12px;
  backdrop-filter: blur(4px);
  letter-spacing: 0.02em;
}
.recent-progress-bar-wrap {
  width: 100%;
  height: 3px;
  background: #e2e8f0;
  position: relative;
  overflow: hidden;
}
.recent-progress-bar {
  height: 100%;
  width: 100%;
  background: var(--green-mid);
  transform-origin: left;
  transform: scaleX(0);
  will-change: transform;
}
.lead-media {
  position: relative;
  height: 280px;
  background: #e2e8f0;
  overflow: hidden;
}
.lead-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.3s ease;
}
.lead-story:hover .lead-img { transform: scale(1.02); }
.lead-tag {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  background: #fef2f2;
  color: #dc2626;
  font-size: 11.5px;
  font-weight: 800;
  padding: 4px 10px;
  border-radius: 6px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 8px;
}
.lead-body {
  padding: 20px 22px 18px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  flex: 1;
}
.lead-title {
  font-family: 'Noto Serif Devanagari', 'Sora', Georgia, serif;
  font-size: 20px;
  font-weight: 800;
  color: #0f172a;
  line-height: 1.35;
  margin: 0 0 10px;
}
.lead-excerpt {
  color: #475569;
  font-size: 13.5px;
  line-height: 1.6;
  margin: 0 0 16px;
}
.lead-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-top: 1px solid var(--news-border);
  padding-top: 14px;
  gap: 12px;
  flex-wrap: wrap;
}

/* Trending Sidebar Box */
.trending-box {
  background: var(--news-card);
  border: 1.5px solid var(--news-border);
  border-radius: 12px;
  padding: 18px;
  display: flex;
  flex-direction: column;
}
.trending-box-title {
  font-size: 15px;
  font-weight: 800;
  color: var(--news-dark);
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--news-border);
}
.trending-item {
  display: flex;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid #f1f5f9;
  text-decoration: none;
  color: inherit;
}
.trending-item:last-child { border-bottom: none; }
.trending-idx {
  font-family: 'Sora', sans-serif;
  font-size: 20px;
  font-weight: 800;
  color: #cbd5e1;
  line-height: 1;
}
.trending-item:hover .trending-idx { color: #16a34a; }
.trending-info { flex: 1; }
.trending-item-title {
  font-size: 13.5px;
  font-weight: 700;
  color: #1e293b;
  line-height: 1.4;
  margin-bottom: 4px;
}
.trending-item-meta {
  font-size: 11.5px;
  color: var(--news-muted);
}

/* ── Filter & Search Card ── */
.news-filter-card {
  background: #ffffff;
  border: 1.5px solid var(--news-border);
  border-radius: 12px;
  padding: 14px 18px;
  margin-bottom: 24px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}
.news-search-row {
  display: flex;
  align-items: center;
  gap: 10px;
  background: #f8fafc;
  border: 1.5px solid var(--news-border);
  border-radius: 8px;
  padding: 0 14px;
  height: 44px;
  margin-bottom: 12px;
}
.news-search-row:focus-within {
  border-color: #16a34a;
  background: #fff;
  box-shadow: 0 0 0 3px rgba(22,163,74,0.1);
}
.news-search-input {
  flex: 1;
  border: none;
  background: transparent;
  font-size: 14px;
  color: #1e293b;
  outline: none;
  font-family: inherit;
}
.news-cats-scroll {
  display: flex;
  align-items: center;
  gap: 8px;
  overflow-x: auto;
  scrollbar-width: none;
  padding-bottom: 4px;
}
.news-cats-scroll::-webkit-scrollbar { display: none; }
.news-chip {
  padding: 7px 14px;
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 700;
  color: #334155;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.15s ease;
  user-select: none;
}
.news-chip:hover {
  background: #e2e8f0;
}
.news-chip.active {
  background: #15803d;
  color: #ffffff;
  border-color: #15803d;
}

/* ── 3-Tier Mobile Optimized News Grid ── */
.news-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 20px;
}
.news-card {
  background: #ffffff;
  border: 1.5px solid var(--news-border);
  border-radius: 12px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  transition: transform 0.15s, box-shadow 0.2s, border-color 0.2s;
}
.news-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 18px rgba(0,0,0,0.10);
  border-color: #cbd5e1;
}

/* Tier 1: Info Row */
.news-card-info {
  padding: 14px 16px 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.card-category-pill {
  font-size: 11.5px;
  font-weight: 800;
  padding: 3px 8px;
  border-radius: 4px;
  background: #f1f5f9;
  color: #1e293b;
}
.card-time-badge {
  font-size: 11.5px;
  color: var(--news-muted);
  font-weight: 600;
}
.news-card-title {
  padding: 0 16px 8px;
  font-size: 16px;
  font-weight: 800;
  color: #0f172a;
  line-height: 1.4;
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.news-card-excerpt {
  padding: 0 16px 12px;
  font-size: 13px;
  color: #475569;
  line-height: 1.5;
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* Tier 2: Media */
.news-card-media {
  height: 175px;
  background: #f1f5f9;
  overflow: hidden;
  cursor: pointer;
  position: relative;
}
.news-card-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.3s;
}
.news-card:hover .news-card-img { transform: scale(1.03); }

/* Tier 3: Action Row */
.news-card-actions {
  padding: 10px 14px;
  border-top: 1px solid #f1f5f9;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fafafa;
  margin-top: auto;
}
.card-action-group {
  display: flex;
  align-items: center;
  gap: 12px;
}
.action-btn {
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 4px 6px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  font-weight: 700;
  color: #475569;
  border-radius: 6px;
  transition: background 0.15s, color 0.15s;
}
.action-btn:hover {
  background: #f1f5f9;
  color: #0f172a;
}
.action-btn.liked {
  color: #688a24;
}
.action-btn.liked svg {
  fill: #688a24;
  stroke: #688a24;
}
.card-read-link {
  font-size: 12.5px;
  font-weight: 700;
  color: #15803d;
  text-decoration: none;
}
.card-read-link:hover {
  text-decoration: underline;
}

/* Modals */
.km-modal-overlay {
  display: none;
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.6);
  backdrop-filter: blur(4px);
  z-index: 9999;
  align-items: center;
  justify-content: center;
  padding: 16px;
}
.km-modal-overlay.open { display: flex; }
.km-modal-box {
  background: #ffffff;
  border-radius: 12px;
  max-width: 680px;
  width: 100%;
  max-height: 90vh;
  overflow-y: auto;
  box-shadow: 0 10px 30px rgba(0,0,0,0.2);
  padding: 24px;
  position: relative;
}
.km-modal-close {
  position: absolute;
  top: 16px;
  right: 16px;
  background: #f1f5f9;
  border: none;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  cursor: pointer;
  font-size: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
}
/* ── Audio Bulletin Digest Strip & Voice Controls ── */
.bulletin-strip {
  background: #ffffff;
  border: 1.5px solid var(--news-border, #cbd5e1);
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.05);
  padding: 10px 16px;
  margin-bottom: 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  box-sizing: border-box;
  width: 100%;
  max-width: 100%;
  overflow: hidden;
}
.bulletin-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1 1 240px;
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
}
.bulletin-icon {
  font-size: 22px;
  flex-shrink: 0;
}
.bulletin-text-group {
  min-width: 0;
  flex: 1;
  overflow: hidden;
}
.bulletin-heading {
  font-size: 13.5px;
  font-weight: 700;
  color: #0f172a;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.bulletin-sub {
  font-size: 11.5px;
  color: #64748b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.bulletin-equalizer {
  display: inline-flex;
  align-items: flex-end;
  gap: 3px;
  height: 18px;
  padding: 0 4px;
  flex-shrink: 0;
}
.eq-bar {
  width: 3px;
  background: #15803d;
  border-radius: 2px;
  animation: eqPulse 1s ease-in-out infinite alternate;
}
.eq-1 { height: 6px; animation-delay: 0.1s; }
.eq-2 { height: 16px; animation-delay: 0.35s; }
.eq-3 { height: 9px; animation-delay: 0.5s; }
.eq-4 { height: 17px; animation-delay: 0.2s; }
.eq-5 { height: 7px; animation-delay: 0.4s; }
@keyframes eqPulse {
  0% { height: 4px; }
  100% { height: 18px; }
}
.bulletin-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.bulletin-settings-group {
  display: flex;
  align-items: center;
  gap: 8px;
}
.bulletin-select {
  background: #f8faf8;
  border: 1px solid #cbd5e1;
  border-radius: 16px;
  padding: 5px 10px;
  font-size: 12px;
  font-weight: 600;
  color: #0f172a;
  font-family: inherit;
  outline: none;
  cursor: pointer;
  max-width: 190px;
  text-overflow: ellipsis;
  overflow: hidden;
  white-space: nowrap;
  transition: border-color 0.15s;
}
.bulletin-select:focus { border-color: #15803d; }
.btn-bulletin-play {
  background: #15803d;
  color: #ffffff;
  border: none;
  padding: 7px 16px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
  flex-shrink: 0;
  transition: background 0.15s;
}
.btn-bulletin-play:hover { background: #1a3c2e; }

@media (max-width: 960px) {
  .bulletin-strip {
    display: grid;
    grid-template-columns: 1fr auto;
    grid-template-areas:
      "left play"
      "settings settings";
    gap: 8px 10px;
    padding: 9px 12px;
    margin-bottom: 20px;
    border: 1.5px solid var(--news-border, #cbd5e1);
    border-radius: 12px;
  }
  .bulletin-left {
    grid-area: left;
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
  }
  .bulletin-icon {
    font-size: 20px;
  }
  .bulletin-heading {
    font-size: 13px;
    font-weight: 700;
    color: #0f172a;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .bulletin-sub {
    font-size: 11px;
    color: #64748b;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    margin-top: 1px;
  }
  .bulletin-controls {
    display: contents;
  }
  .btn-bulletin-play {
    grid-area: play;
    align-self: center;
    padding: 6px 14px;
    font-size: 12px;
    border-radius: 20px;
    height: 32px;
    white-space: nowrap;
    gap: 5px;
  }
  .bulletin-settings-group {
    grid-area: settings;
    display: flex;
    align-items: center;
    gap: 6px;
    width: 100%;
    border-top: 1px dashed #e2e8f0;
    padding-top: 6px;
  }
  .bulletin-select {
    flex: 1 1 50%;
    max-width: none;
    height: 28px;
    padding: 2px 8px;
    font-size: 11.5px;
    border-radius: 6px;
    background: #f8fafc;
  }
}
@media (max-width: 480px) {
  .bulletin-strip {
    padding: 8px 10px;
    gap: 6px 8px;
  }
  .bulletin-heading {
    font-size: 12.5px;
  }
  .bulletin-sub {
    display: none;
  }
  .btn-bulletin-play {
    padding: 5px 12px;
    font-size: 11.5px;
    height: 30px;
  }
  .bulletin-select {
    font-size: 11px;
    height: 26px;
    padding: 2px 6px;
  }
}

/* ── Mobile Layout Polish (98% Audience) ── */
@media (max-width: 768px) {
  .page-container {
    padding: 8px 12px 85px !important;
  }
  .news-header-title-row {
    margin-bottom: 10px;
    padding-bottom: 8px;
    gap: 4px;
  }
  .news-page-title {
    font-size: 20px;
  }
  .news-count-pill {
    font-size: 11px;
    padding: 2px 8px;
  }
  .news-page-date {
    font-size: 11px;
  }
  .spotlight-grid {
    gap: 14px;
    margin-bottom: 14px;
  }
  .recent-posts-tab-card {
    border-radius: 12px;
  }
  .recent-tab-header {
    padding: 8px 12px;
    gap: 8px;
  }
  .recent-tab-badge {
    font-size: 12px;
  }
  .recent-badge-sub {
    font-size: 10px;
  }
  .recent-tab-pills {
    gap: 4px;
  }
  .recent-tab-pill {
    padding: 3px 8px;
    font-size: 11px;
    border-radius: 12px;
  }
  .recent-arrow-btns {
    gap: 3px;
  }
  .recent-arrow-btn {
    width: 24px;
    height: 24px;
  }
  .lead-media {
    height: auto !important;
    aspect-ratio: 16 / 9 !important;
    max-height: 205px !important;
    width: 100% !important;
    background: #f1f5f9;
  }
  .lead-img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }
  .lead-body {
    padding: 12px 14px 10px !important;
  }
  .lead-tag {
    font-size: 10.5px;
    padding: 2px 7px;
    margin-bottom: 5px;
  }
  .lead-title {
    font-size: 15.5px !important;
    line-height: 1.35 !important;
    margin: 0 0 6px !important;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .lead-excerpt {
    font-size: 12px !important;
    line-height: 1.45 !important;
    margin: 0 0 10px !important;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .lead-footer {
    padding-top: 8px;
    gap: 8px;
  }
  .lead-footer .action-btn {
    padding: 4px 8px !important;
    font-size: 11px;
  }
  .card-read-link {
    font-size: 11.5px;
  }
  .trending-box {
    padding: 12px 14px;
  }
  .trending-box-title {
    font-size: 13.5px;
    margin-bottom: 8px;
    padding-bottom: 6px;
  }
  .trending-item {
    padding: 7px 0;
    gap: 10px;
  }
  .trending-idx {
    font-size: 16px;
  }
  .trending-item-title {
    font-size: 12.5px;
    line-height: 1.35;
    margin-bottom: 2px;
  }
  .trending-item-meta {
    font-size: 10.5px;
  }
  .news-filter-card {
    padding: 10px 12px;
    margin-bottom: 14px;
  }
  .news-search-row {
    height: 38px;
    padding: 0 10px;
    margin-bottom: 8px;
  }
  .news-search-input {
    font-size: 13px;
  }
  .news-chip {
    padding: 5px 11px;
    font-size: 11.5px;
  }
}

/* ── Story page (/krashi_news/<slug>) ──────────────────────────
   Built mobile-first: 98% of readers are on a ~390px phone, so the
   measure, type scale and tap targets are set there and the desktop
   look is the min-width variant. */
.story-page { max-width: 760px; }
.story-article { background: var(--news-card); border: 1px solid var(--news-border);
  border-radius: 16px; padding: 20px 18px 24px; }
.story-tagrow { display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  margin-bottom: 10px; }
.story-cat { background: #15803d; color: #fff; font-size: 12px; font-weight: 700;
  padding: 4px 10px; border-radius: 999px; }
.story-meta { font-size: 12.5px; color: var(--news-muted); font-weight: 600; }
.story-title { font-family: var(--font-serif); font-size: 26px; line-height: 1.32;
  font-weight: 800; color: var(--news-dark); margin: 0 0 10px; }
.story-standfirst { font-size: 16px; line-height: 1.65; color: var(--news-muted);
  font-weight: 500; margin-bottom: 16px; }
.story-figure { margin: 0 0 18px; }
.story-figure img { width: 100%; height: auto; border-radius: 12px; display: block;
  background: var(--news-bg); }
.story-h2 { font-family: var(--font-serif); font-size: 19px; font-weight: 800;
  color: var(--news-dark); margin: 22px 0 10px; }
.story-keypoints { background: var(--news-bg); border: 1px solid var(--news-border);
  border-radius: 12px; padding: 14px 16px; margin-bottom: 18px; }
.story-keypoints .story-h2 { margin-top: 0; }
.story-keypoint-list { margin: 0; padding-left: 20px; }
.story-keypoint-list li { font-size: 15px; line-height: 1.6; color: var(--news-text);
  margin-bottom: 8px; }
.story-keypoint-list li:last-child { margin-bottom: 0; }
.story-body { font-size: 16.5px; line-height: 1.85; color: var(--news-text); }
.story-para { margin-bottom: 16px; }
.story-source { font-size: 13.5px; color: var(--news-muted); margin: 18px 0 0;
  padding-top: 12px; border-top: 1px dashed var(--news-border); }
.story-source a { color: var(--news-accent); font-weight: 700; }

/* The disclosure is deliberately visible, not a faint footnote: a farmer
   deciding whether to act on a subsidy figure has to see it. */
.story-disclosure { display: block; margin: 16px 0 0; padding: 12px 14px;
  background: #fffbeb; border: 1px solid #fde68a; border-left: 4px solid #e9a825;
  border-radius: 10px; font-size: 13px; line-height: 1.65; color: #713f12; }
.story-disclosure strong { color: #78350f; }

.story-actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  margin-top: 20px; padding-top: 16px; border-top: 1px solid var(--news-border); }
.story-cta { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 18px; }
.story-cta-btn { display: inline-block; background: var(--news-dark); color: #fff;
  text-decoration: none; font-weight: 700; font-size: 14.5px; padding: 11px 18px;
  border-radius: 999px; }
.story-cta-btn.ghost { background: transparent; color: var(--news-dark);
  border: 1.5px solid var(--news-border); }
.story-rel { margin-top: 30px; }
.story-rel-grid { display: grid; grid-template-columns: 1fr; gap: 10px; }
.story-rel-card { display: flex; flex-direction: column; gap: 6px; padding: 14px 16px;
  background: var(--news-card); border: 1px solid var(--news-border);
  border-radius: 12px; text-decoration: none; }
.story-rel-tag { font-size: 11.5px; font-weight: 700; color: var(--news-accent);
  text-transform: uppercase; letter-spacing: .3px; }
.story-rel-title { font-size: 15px; font-weight: 700; line-height: 1.5;
  color: var(--news-text); }
.story-rel-card:hover { border-color: var(--news-accent); }

@media (min-width: 721px) {
  .story-article { padding: 32px 36px 36px; }
  .story-title { font-size: 34px; }
  .story-rel-grid { grid-template-columns: 1fr 1fr; gap: 14px; }
}
"""


def _news_header() -> str:
    """Header stack matching /bhav with zero database dependencies."""
    nav_links = [
        (f"{SITE}/bhav", "मंडी भाव", False),
        (f"{SITE}/krashi_bajar", "कृषि बाज़ार", False),
        (f"{SITE}/weather", "मौसम देखें", False),
        (f"{SITE}/krashi_news", "कृषि समाचार", True),
        (f"{SITE}/product/", "कृषि दुकान", False),
    ]
    nav_html = "".join(
        f'<a class="header-nav-link{" active" if is_act else ""}" href="{u}">{lbl}</a>'
        for u, lbl, is_act in nav_links
    )
    drawer_links = [
        (f"{SITE}/", "🏠", "मुख्य पेज"),
        (f"{SITE}/weather", "🌤️", "मौसम पूर्वानुमान"),
        (f"{SITE}/bhav", "🏪", "मंडी भाव"),
        (f"{SITE}/krashi_bajar", "🧺", "कृषि बाज़ार"),
        (f"{SITE}/product/", "🛒", "कृषि दुकान"),
        (f"{SITE}/map", "🗺️", "कृषि मानचित्र"),
        (f"{SITE}/krashi_news", "📰", "कृषि समाचार"),
        (f"{SITE}/sarkari_yojana", "🏛️", "सरकारी योजनाएं"),
        (f"{SITE}/chat", "💬", "AI सहायक"),
    ]
    drawer_html = "".join(
        f'<a href="{u}" class="sidebar-drawer-link{" active" if is_act else ""}">'
        f'<span class="sidebar-drawer-link-icon">{ic}</span><span>{lbl}</span></a>'
        for u, ic, lbl in drawer_links
        for is_act in [u.endswith("/krashi_news")]
    )
    return f"""<div class="header-wrapper" id="header-wrapper">
<div class="pre-topbar">
<a href="https://wa.me/919870951001" target="_blank" rel="noopener" class="pre-topbar-helpline" title="कृषिमित्र हेल्पलाइन — व्हाट्सऐप पर मैसेज करें"><span class="pre-topbar-phone-icon"><svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor" aria-hidden="true"><path d="M12.04 2c-5.46 0-9.91 4.45-9.91 9.91 0 1.75.46 3.45 1.32 4.95L2 22l5.25-1.38c1.45.79 3.08 1.21 4.79 1.21h.01c5.46 0 9.9-4.45 9.9-9.91 0-2.65-1.03-5.14-2.9-7.01A9.816 9.816 0 0 0 12.04 2zm0 18.15h-.01c-1.5 0-2.97-.4-4.25-1.16l-.3-.18-3.12.82.83-3.04-.2-.31a8.196 8.196 0 0 1-1.26-4.37c0-4.54 3.7-8.24 8.25-8.24 2.2 0 4.27.86 5.83 2.42a8.19 8.19 0 0 1 2.41 5.83c0 4.55-3.7 8.24-8.24 8.24zm4.52-6.16c-.25-.12-1.47-.72-1.69-.81-.23-.08-.39-.12-.56.13-.17.25-.64.81-.78.97-.14.17-.29.19-.54.06-.25-.12-1.05-.39-1.99-1.23-.74-.66-1.23-1.47-1.38-1.72-.14-.25-.02-.38.11-.51.11-.11.25-.29.37-.43.12-.14.17-.25.25-.41.08-.17.04-.31-.02-.43-.06-.12-.56-1.34-.76-1.84-.2-.48-.41-.42-.56-.42-.14-.01-.31-.01-.48-.01-.17 0-.43.06-.66.31-.23.25-.86.85-.86 2.07 0 1.22.89 2.4 1.01 2.57.12.17 1.75 2.67 4.23 3.74.59.26 1.05.41 1.41.52.59.19 1.13.16 1.56.1.48-.07 1.47-.6 1.67-1.18.21-.58.21-1.08.14-1.18-.06-.11-.23-.17-.48-.29z"/></svg></span> कृषिमित्र हेल्पलाइन: +91 9870951001</a>
</div>
<div class="top-utility-bar"><div class="top-utility-inner">
<div class="top-utility-left">
<a href="{SITE}/" class="top-utility-link">मुख्य</a><span class="top-utility-divider">|</span>
<a href="{SITE}/map" class="top-utility-link">कृषि मानचित्र</a><span class="top-utility-divider">|</span>
<a href="{SITE}/krashi_news" class="top-utility-link" style="color:#15803d;font-weight:700;">कृषि समाचार</a><span class="top-utility-divider">|</span>
<a href="{SITE}/sarkari_yojana" class="top-utility-link">सरकारी योजना</a>
</div>
<div class="top-utility-right">
<a href="https://wa.me/919870951001" target="_blank" rel="noopener" class="top-utility-helpline" title="कृषिमित्र हेल्पलाइन"><span class="pre-topbar-phone-icon"><svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor" aria-hidden="true"><path d="M12.04 2c-5.46 0-9.91 4.45-9.91 9.91 0 1.75.46 3.45 1.32 4.95L2 22l5.25-1.38c1.45.79 3.08 1.21 4.79 1.21h.01c5.46 0 9.9-4.45 9.9-9.91 0-2.65-1.03-5.14-2.9-7.01A9.816 9.816 0 0 0 12.04 2zm0 18.15h-.01c-1.5 0-2.97-.4-4.25-1.16l-.3-.18-3.12.82.83-3.04-.2-.31a8.196 8.196 0 0 1-1.26-4.37c0-4.54 3.7-8.24 8.25-8.24 2.2 0 4.27.86 5.83 2.42a8.19 8.19 0 0 1 2.41 5.83c0 4.55-3.7 8.24-8.24 8.24zm4.52-6.16c-.25-.12-1.47-.72-1.69-.81-.23-.08-.39-.12-.56.13-.17.25-.64.81-.78.97-.14.17-.29.19-.54.06-.25-.12-1.05-.39-1.99-1.23-.74-.66-1.23-1.47-1.38-1.72-.14-.25-.02-.38.11-.51.11-.11.25-.29.37-.43.12-.14.17-.25.25-.41.08-.17.04-.31-.02-.43-.06-.12-.56-1.34-.76-1.84-.2-.48-.41-.42-.56-.42-.14-.01-.31-.01-.48-.01-.17 0-.43.06-.66.31-.23.25-.86.85-.86 2.07 0 1.22.89 2.4 1.01 2.57.12.17 1.75 2.67 4.23 3.74.59.26 1.05.41 1.41.52.59.19 1.13.16 1.56.1.48-.07 1.47-.6 1.67-1.18.21-.58.21-1.08.14-1.18-.06-.11-.23-.17-.48-.29z"/></svg></span> कृषिमित्र हेल्पलाइन</a>
<span class="top-utility-divider">|</span>
<a href="{SITE}/chat" class="top-utility-link">संपर्क</a>
</div>
</div></div>
<header class="main-header"><div class="main-header-inner">
<button class="hamburger-btn" onclick="document.getElementById('km-drawer').classList.add('open')" aria-label="Menu">&#9776;</button>
<div class="header-left-group">
<a class="header-logo-link" href="{SITE}/">
<img src="{SITE}/assets/krashimitra_logo.png" alt="कृषि मित्र" class="header-logo-circle" width="38" height="38">
<span class="header-logo-text">कृषि मित्र</span></a>
</div>
<nav class="header-nav">{nav_html}</nav>
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
</div><!-- /.header-wrapper -->
<div class="sidebar-drawer-overlay" id="km-drawer" onclick="this.classList.remove('open')">
<div class="sidebar-drawer" onclick="event.stopPropagation()">
<div class="sidebar-drawer-header"><span class="sidebar-drawer-title">मेनु</span>
<button class="sidebar-drawer-close" onclick="document.getElementById('km-drawer').classList.remove('open')" aria-label="Close menu">✕</button></div>
<div class="sidebar-drawer-links">{drawer_html}</div>
</div></div>
<div class="topbar-spacer" id="topbar-spacer"></div>
"""


def _news_footer() -> str:
    return f"""<footer class="km-footer"><div class="km-footer-inner">
<div class="km-footer-brand">🌾 कृषि मित्र</div>
<nav class="km-footer-nav">
<a href="{SITE}/">होम</a>
<a href="{SITE}/bhav">मंडी भाव</a>
<a href="{SITE}/weather">मौसम</a>
<a href="{SITE}/krashi_news">कृषि समाचार</a>
<a href="{SITE}/chat">AI सहायक</a>
<a href="{SITE}/donate">सहयोग करें</a>
</nav>
<div class="km-footer-note">ताज़ा कृषि समाचार, मंडी विश्लेषण एवं सरकारी योजनाएं — कृषि मित्र © {datetime.now().year}</div>
</div></footer>"""


def _news_doc(title: str, desc: str, body: str, ld: str = "",
              canon: str = "", og: str = "", og_type: str = "website",
              crumbs: str = "", published: str = "", modified: str = "") -> HTMLResponse:
    """The shared news shell. Defaults render the hub exactly as before;
    a story page passes its own canonical, image and article timestamps."""
    canon = canon or f"{SITE}/krashi_news"
    og = og or f"{SITE}/images/og-banner.webp"
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="hi">
<head>
{_ANALYTICS}
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title>
<meta name="description" content="{escape(desc)}">
<link rel="canonical" href="{canon}">
<meta property="og:type" content="{og_type}">
<meta property="og:site_name" content="कृषि मित्र (KrashiMitra)">
<meta property="og:title" content="{escape(title)}">
<meta property="og:description" content="{escape(desc)}">
<meta property="og:image" content="{escape(og)}">
<meta property="og:url" content="{canon}">
<meta property="og:locale" content="hi_IN">
<meta name="twitter:card" content="summary_large_image">
{f'<meta property="article:published_time" content="{escape(published)}">' if published else ''}{f'<meta property="article:modified_time" content="{escape(modified)}">' if modified else ''}
<link rel="manifest" href="/manifest.json">
<meta name="theme-color" content="#1a3c2e">
{_ICON}
{_FONTS}
{f'<script type="application/ld+json">{ld}</script>' if ld else ''}
<style>{_BASE_RESET_CSS}{NEWS_EXTRA_CSS}</style>
</head>
<body>
{_news_header()}
{crumbs or f'<nav class="crumbs"><a href="{SITE}/">कृषि मित्र</a> › <span class="current">कृषि समाचार</span></nav>'}
{body}
{_news_footer()}
<script src="/api-config.js"></script>
<script src="/drawer-menu.js" defer></script>
<script src="/bottomnav.js" defer></script>
<script src="/header-scroll.js" defer></script>
</body>
</html>""", headers=_CACHE_HEADERS)


# ── SERP copy budgets ────────────────────────────────────────
# Same limits the article builder enforces (memory: serp-length-budgets):
# Google truncates titles past ~68 chars and descriptions past ~162, and a
# "| KrashiMitra" suffix spends characters on a brand nobody searches for.
# A news headline is already the keyword, so it becomes the title nearly
# verbatim.
_TITLE_MAX = 68
_DESC_MAX = 162


def _fit(text: str, limit: int) -> str:
    """Trim to `limit` on a word boundary."""
    t = " ".join((text or "").split())
    if len(t) <= limit:
        return t
    cut = t[:limit - 1]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" ,.।:;-") + "…"


def _story_body_paras(story: dict) -> List[str]:
    """The story text as paragraphs. `full_story` arrives as one blob from
    the generator; a 30-line wall of Devanagari on a 390px phone is unread,
    so an over-long blob is split on sentence ends (। ! ?) as well."""
    raw = (story.get("full_story") or story.get("excerpt") or "").strip()
    if not raw:
        return []
    out = []
    for para in [x.strip() for x in re.split(r"\n\s*\n", raw) if x.strip()]:
        if len(para) <= 420:
            out.append(para)
            continue
        buf = ""
        for s in re.split(r"(?<=[।!?])\s+", para):
            if len(buf) + len(s) > 380 and buf:
                out.append(buf.strip())
                buf = s
            else:
                buf = (buf + " " + s).strip()
        if buf:
            out.append(buf.strip())
    return out


def _related_stories(story: dict, limit: int = 6) -> List[dict]:
    """Same category first, then anything else recent. A story page with no
    way onward is a dead end; this is what turns one story into a session."""
    sid = story.get("id")
    cat = story.get("category")
    same, other = [], []
    for s in _all_stories():
        if s.get("id") == sid:
            continue
        (same if s.get("category") == cat else other).append(s)
    return (same + other)[:limit]


# ── Publishing disclosure ────────────────────────────────────
# This section republishes agricultural news that an AI has rewritten from
# a source headline and RSS summary. Three things therefore appear on every
# story, and none of them is decoration:
#
#   • The source is named and linked (rel="nofollow noopener"). Only the
#     headline and the feed's own summary are ever ingested — never the
#     body of someone else's article — and crediting the outlet is both
#     the honest thing and the thing that keeps aggregation defensible.
#   • The AI's involvement is stated plainly. The generator EXPANDS a short
#     summary into full paragraphs, which means specifics (subsidy
#     percentages, dates, eligibility) can be produced that were never in
#     the source. A farmer must not mistake that for verified reporting.
#   • Readers are told to confirm on the official portal before acting.
#     This is the one that actually protects a farmer, and it is why the
#     notice sits with the story rather than in a footer nobody opens.
#
# Do not remove or soften these. They are the difference between an
# aggregator and a publisher making unverified financial claims about
# government schemes to people who act on them.
_AI_DISCLOSURE = (
    '<aside class="story-disclosure">'
    '<strong>ज़रूरी सूचना:</strong> यह समाचार सार्वजनिक समाचार स्रोतों की हेडलाइन व सारांश से '
    'AI की सहायता से हिंदी में तैयार किया गया है। यह मूल पत्रकारिता नहीं है। '
    'योजना, सब्सिडी, तारीख या भाव से जुड़ा कोई भी फैसला लेने से पहले कृपया संबंधित '
    'सरकारी विभाग या आधिकारिक पोर्टल पर जानकारी की पुष्टि अवश्य करें। '
    'कृषि मित्र किसी भी निर्णय के परिणाम के लिए उत्तरदायी नहीं है।'
    '</aside>'
)


@router.get("/krashi_news/{slug}", response_class=HTMLResponse)
def krashi_news_story(slug: str, request: Request):
    """One published story, at its own address.

    Only auto-pilot posts are served here. A master article's card points at
    its /articles/<slug> page instead (see _story_url), so this route never
    creates a second URL for content that already has a page — the duplicate
    that would cost both of them their ranking.
    """
    story = _find_story(slug)
    if not story:
        return _news_not_found(slug)

    # A master article lives at /articles/<slug>. If one is reached here,
    # send the reader — and the link equity — to the real page.
    target = _story_url(story)
    if not target.startswith("/krashi_news/"):
        return RedirectResponse(target, status_code=301)

    canonical_slug = _story_slug(story)
    if canonical_slug.lower() != (slug or "").strip("/").lower():
        # Reached by raw id or a stale slug: one address per story.
        return RedirectResponse("/krashi_news/" + canonical_slug, status_code=301)

    sid = escape(str(story.get("id") or ""))
    title = (story.get("title") or "कृषि समाचार").strip()
    excerpt = (story.get("excerpt") or "").strip()
    cat_label = story.get("catLabel") or "कृषि समाचार"
    read_time = story.get("readTime") or "3 मिनट"
    published_at = str(story.get("published_at") or story.get("created_at") or "")

    img = _safe_image(story)
    og_img = SITE + img

    canon = SITE + "/krashi_news/" + canonical_slug
    seo_title = _fit(title, _TITLE_MAX)
    seo_desc = _fit(excerpt or title, _DESC_MAX)

    bullets = [b for b in (story.get("bullets") or []) if str(b).strip()]
    bullets_html = ""
    if bullets:
        items = "".join("<li>" + escape(str(b)) + "</li>" for b in bullets)
        bullets_html = ('<div class="story-keypoints"><h2 class="story-h2">एक नज़र में</h2>'
                        '<ul class="story-keypoint-list">' + items + '</ul></div>')

    paras = _story_body_paras(story)
    body_html = "".join('<p class="story-para">' + escape(x) + '</p>' for x in paras)
    if not body_html:
        body_html = '<p class="story-para">' + escape(excerpt) + '</p>'

    source_url = (story.get("source_url") or "").strip()
    source_html = ""
    if source_url.startswith("http"):
        try:
            host = re.sub(r"^www\.", "", source_url.split("/")[2])
        except Exception:
            host = "मूल स्रोत"
        source_html = ('<p class="story-source">स्रोत: <a href="' + escape(source_url) +
                       '" rel="nofollow noopener" target="_blank">' + escape(host) +
                       ' पर मूल खबर पढ़ें ↗</a></p>')

    rel = _related_stories(story)
    rel_html = ""
    if rel:
        cards = "".join(
            '<a class="story-rel-card" href="' + escape(_story_url(r)) + '">'
            '<span class="story-rel-tag">' + escape(r.get("catLabel") or "समाचार") + '</span>'
            '<span class="story-rel-title">' + escape(r.get("title") or "") + '</span></a>'
            for r in rel)
        rel_html = ('<section class="story-rel"><h2 class="story-h2">और पढ़ें</h2>'
                    '<div class="story-rel-grid">' + cards + '</div></section>')

    likes = int(story.get("seed_likes") or _calc_seed_likes(story.get("id") or ""))
    comments = int(story.get("comment_count") or 0)

    disp_date = ""
    if published_at:
        try:
            disp_date = datetime.fromisoformat(published_at.replace("Z", "")).strftime("%d-%m-%Y")
        except Exception:
            disp_date = ""

    # Organization, never a fabricated human byline — the story is machine
    # written and the schema must not claim otherwise.
    ld = json.dumps({
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": _fit(title, 110),
        "description": seo_desc,
        "image": [og_img],
        "datePublished": published_at or None,
        "dateModified": published_at or None,
        "inLanguage": "hi-IN",
        "isAccessibleForFree": True,
        "mainEntityOfPage": {"@type": "WebPage", "@id": canon},
        "articleSection": cat_label,
        "author": {"@type": "Organization", "name": "कृषि मित्र (KrashiMitra)", "url": SITE},
        "publisher": {"@type": "Organization", "name": "कृषि मित्र (KrashiMitra)", "url": SITE,
                      "logo": {"@type": "ImageObject",
                               "url": SITE + "/assets/krashimitra_logo.png"}},
    }, ensure_ascii=False)

    crumb_ld = json.dumps({
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "कृषि मित्र", "item": SITE},
            {"@type": "ListItem", "position": 2, "name": "कृषि न्यूज़", "item": SITE + "/krashi_news"},
            {"@type": "ListItem", "position": 3, "name": _fit(title, 80), "item": canon},
        ]}, ensure_ascii=False)

    crumbs = ('<nav class="crumbs"><a href="' + SITE + '/">कृषि मित्र</a> › '
              '<a href="' + SITE + '/krashi_news">कृषि न्यूज़</a> › '
              '<span class="current">' + escape(_fit(title, 46)) + '</span></nav>')

    title_js = escape(title).replace("'", "&#39;")
    meta_line = escape(read_time) + ((" · " + disp_date) if disp_date else "")

    body = """
<main class="page-container story-page">
  <article class="story-article">
    <div class="story-tagrow">
      <span class="story-cat">""" + escape(cat_label) + """</span>
      <span class="story-meta">⏱️ """ + meta_line + """</span>
    </div>
    <h1 class="story-title">""" + escape(title) + """</h1>
    """ + ('<p class="story-standfirst">' + escape(excerpt) + '</p>' if excerpt else '') + """
    <figure class="story-figure">
      <img src=\"""" + escape(img) + """\" alt=\"""" + escape(_fit(title, 90)) + """\"
           width="1200" height="675" fetchpriority="high"
           onerror="this.src='/images/og-banner.webp'; this.onerror=null;">
    </figure>
    """ + bullets_html + """
    <div class="story-body">""" + body_html + """</div>
    """ + source_html + _AI_DISCLOSURE + """
    <div class="story-actions">
      <button class="action-btn" id="btn-audio-""" + sid + """" onclick="playNewsAudio(this, '""" + sid + """')"
              style="background:#e0f2fe;color:#0369a1;padding:8px 14px;border-radius:20px;">
        <span>▶️ खबर सुनें</span>
      </button>
      <button class="action-btn" id=\"""" + sid + """-like-btn" onclick="toggleLike('""" + sid + """', this)" title="पसंद करें">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/></svg>
        <span class="like-count" id=\"""" + sid + """-like-count">""" + str(likes) + """</span>
      </button>
      <button class="action-btn" onclick="openCommentDrawer('""" + sid + """')" title="किसान चर्चा">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
        <span class="comment-count" id=\"""" + sid + """-comment-count">""" + str(comments) + """</span>
      </button>
      <button class="action-btn" onclick="openShareMenu('""" + sid + """', '""" + title_js + """')" title="शेयर करें">
        <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>
      </button>
    </div>
    <div class="story-cta">
      <a class="story-cta-btn" href=\"""" + SITE + """/bhav">आज का मंडी भाव देखें →</a>
      <a class="story-cta-btn ghost" href=\"""" + SITE + """/krashi_news">सभी कृषि समाचार</a>
    </div>
  </article>
  """ + rel_html + """
</main>
<script type="application/ld+json">""" + crumb_ld + """</script>
"""
    return _news_doc(seo_title, seo_desc, body, ld, canon=canon, og=og_img,
                     og_type="article", crumbs=crumbs,
                     published=published_at, modified=published_at)


def _news_not_found(slug: str) -> HTMLResponse:
    """A missing story still gets the shell and a way onward — but it also
    gets a real 404 status, so Google drops the URL instead of indexing a
    soft error. (Memory: the static host answers 200 for missing files;
    this is exactly the trap that hides.)"""
    recent = _all_stories()[:8]
    items = "".join(
        '<a class="story-rel-card" href="' + escape(_story_url(r)) + '">'
        '<span class="story-rel-tag">' + escape(r.get("catLabel") or "समाचार") + '</span>'
        '<span class="story-rel-title">' + escape(r.get("title") or "") + '</span></a>'
        for r in recent)
    body = """
<main class="page-container story-page">
  <article class="story-article">
    <h1 class="story-title">यह खबर अब उपलब्ध नहीं है</h1>
    <p class="story-standfirst">हो सकता है यह खबर हटा दी गई हो या लिंक बदल गया हो।
       नीचे आज की ताज़ा कृषि खबरें पढ़ें।</p>
    <div class="story-cta">
      <a class="story-cta-btn" href=\"""" + SITE + """/krashi_news">सभी कृषि समाचार</a>
      <a class="story-cta-btn ghost" href=\"""" + SITE + """/bhav">आज का मंडी भाव</a>
    </div>
  </article>
  <section class="story-rel"><h2 class="story-h2">ताज़ा खबरें</h2>
    <div class="story-rel-grid">""" + items + """</div>
  </section>
</main>"""
    res = _news_doc("यह खबर अब उपलब्ध नहीं है",
                    "यह कृषि समाचार अब उपलब्ध नहीं है। ताज़ा मंडी भाव और कृषि खबरें कृषि मित्र पर पढ़ें।",
                    body, canon=SITE + "/krashi_news")
    res.status_code = 404
    return res


def _generate_article_card_html(item: dict, live_likes: int, live_comments: int) -> str:
    """Renders a single news card with 3-tier mobile layout."""
    item_id = escape(item.get("id") or "")
    title = escape(item.get("title") or "")
    excerpt = escape(item.get("excerpt") or "")
    category = escape(item.get("category") or "all")
    cat_label = escape(item.get("catLabel") or "समाचार")
    time_str = escape(item.get("time") or "आज ताज़ा")
    read_time = escape(item.get("readTime") or "3 मिनट")
    img_url = escape(_safe_image(item))

    # A real, crawlable address for the story. The modal reader stays exactly
    # as it was on the image and headline — this is the link Googlebot follows
    # and the one a reader who wants the whole story lands on.
    story_href = escape(_story_url(item))
    is_auto = str(item_id).startswith("km-auto-") or item.get("is_gemini_post")
    badge_html = f'<span class="card-category-pill" style="background:#15803d;color:#fff;">⚡ ताज़ा खबर</span>' if is_auto else f'<span class="card-category-pill">{cat_label}</span>'
    click_action = f"openStoryReader('{item_id}'); return false;"

    return f"""
<article class="news-card" data-cat="{category}" data-id="{item_id}">
  <div class="news-card-info">
    <div>{badge_html}</div>
    <div class="card-time-badge">⏱️ {read_time} · {time_str}</div>
  </div>
  <div class="news-card-media" onclick="{click_action}">
    <img src="{img_url}" alt="{title}" class="news-card-img" loading="lazy" width="340" height="175">
  </div>
  <h3 class="news-card-title" onclick="{click_action}" style="cursor:pointer;">{title}</h3>
  <p class="news-card-excerpt">{excerpt}</p>
  <div class="news-card-actions">
    <div class="card-action-group">
      <button class="action-btn like-btn" onclick="toggleLike('{item_id}', this)" title="पसंद करें">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/></svg>
        <span class="like-count">{live_likes}</span>
      </button>
      <button class="action-btn comment-btn" onclick="openCommentDrawer('{item_id}')" title="टिप्पणी करें">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
        <span class="comment-count">{live_comments}</span>
      </button>
      <button class="action-btn share-btn" onclick="openShareMenu('{item_id}', '{title}')" title="शेयर करें">
        <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>
      </button>
    </div>
    <a href="{story_href}" class="card-read-link">विस्तार से पढ़ें →</a>
  </div>
</article>
"""


@router.get("/krashi_news", response_class=HTMLResponse)
@router.get("/krashi_news.html", response_class=HTMLResponse)
@router.get("/news", response_class=HTMLResponse)
def krashi_news_hub(request: Request):
    """
    FastAPI Server-Side Rendered (SSR) Krashi News Hub.
    Matches /bhav's server-rendered architecture with sub-20ms first paint,
    pre-rendered Googlebot markup, and live sync with news_funnel.json & PostgreSQL.
    """
    # 1. Fetch published auto-pilot posts
    published_auto = get_published_posts()

    # 2. Fetch master articles dataset
    master_articles = _load_master_articles()

    # Combine: published auto-pilot news leads at the top
    all_stories = []
    seen_ids = set()

    for p in published_auto:
        if p.get("id") and p["id"] not in seen_ids:
            seen_ids.add(p["id"])
            all_stories.append(p)

    for m in master_articles:
        if m.get("id") and m["id"] not in seen_ids:
            seen_ids.add(m["id"])
            all_stories.append(m)

    if not all_stories:
        lead_story = {
            "id": "news-lead",
            "title": "गन्ने का मूल्य विश्लेषण 2026: SAP, FRP व चीनी मिलों के नए भुगतान नियम",
            "excerpt": "उत्तर प्रदेश, महाराष्ट्र व हरियाणा में नई खरीद दर और अनिवार्य भुगतान नियम।",
            "image": "/images/articles/ganna-pricing-analytics-up-card.webp",
            "category": "mandi",
        }
        grid_stories = []
    else:
        lead_story = all_stories[0]
        grid_stories = all_stories[1:]

    lead_id_val = lead_story.get("id", "news-lead")

    # 3. Compute instant in-memory metrics (hydrated via /api/news/social/batch client-side)
    db_likes = {}
    db_comments = {}
    for s in all_stories:
        sid = s.get("id")
        if sid:
            db_likes[sid] = _calc_seed_likes(sid)
            db_comments[sid] = int(s.get("comment_count") or 0)

    lead_id = lead_story.get("id", "news-lead")
    lead_likes = db_likes.get(lead_id, _calc_seed_likes(lead_id))
    lead_comments = db_comments.get(lead_id, 0)
    lead_img = _safe_image(lead_story)

    lead_title_esc = escape(lead_story.get("title") or "")
    lead_excerpt_esc = escape(lead_story.get("excerpt") or "")
    lead_click = f"openStoryReader('{escape(lead_id)}'); return false;"

    # Prepare Top 3 Stories for Recent Posts Tab Slider
    top3_stories = all_stories[:3] if len(all_stories) >= 3 else (all_stories + [lead_story] * (3 - len(all_stories)))
    recent_slides_html = ""
    for idx, s in enumerate(top3_stories):
        sid = s.get("id", f"news-{idx}")
        s_likes = db_likes.get(sid, _calc_seed_likes(sid))
        s_comm = db_comments.get(sid, 0)
        s_img = _safe_image(s)
        s_title = escape(s.get("title") or "")
        s_excerpt = escape(s.get("excerpt") or "")
        s_cat = escape(s.get("catLabel") or "कृषि समाचार")
        s_click = f"openStoryReader('{escape(sid)}'); return false;"
        s_href = escape(_story_url(s))
        fp_attr = 'fetchpriority="high"' if idx == 0 else 'decoding="async"'
        recent_slides_html += f"""
        <article class="recent-slide" data-index="{idx}" data-news-id="{escape(sid)}">
          <div class="lead-media" onclick="{s_click}" style="cursor:pointer;">
            <img src="{escape(s_img)}" alt="{s_title}" class="lead-img" width="600" height="338" {fp_attr} onerror="this.src='/images/og-banner.webp'; this.onerror=null;">
            <div class="recent-slide-meta-badge">
              <span class="recent-post-number-tag">पोस्ट {idx + 1} · ताज़ा</span>
            </div>
          </div>
          <div class="lead-body">
            <div>
              <div><span class="lead-tag">🔥 {s_cat}</span></div>
              <h2 class="lead-title" onclick="{s_click}" style="cursor:pointer;">{s_title}</h2>
              <p class="lead-excerpt">{s_excerpt}</p>
            </div>
            <div class="lead-footer">
              <button class="action-btn" id="btn-audio-{escape(sid)}" onclick="playNewsAudio(this, '{escape(sid)}')" style="background:#e0f2fe;color:#0369a1;padding:6px 12px;border-radius:20px;">
                <span>▶️ खबर सुनें</span>
              </button>
              <div style="display:flex;align-items:center;gap:14px;">
                <button class="action-btn" id="{escape(sid)}-like-btn" onclick="toggleLike('{escape(sid)}', this)" title="पसंद करें">
                  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/></svg>
                  <span class="like-count" id="{escape(sid)}-like-count">{s_likes}</span>
                </button>
                <button class="action-btn" onclick="openCommentDrawer('{escape(sid)}')" title="किसान चर्चा">
                  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                  <span class="comment-count" id="{escape(sid)}-comment-count">{s_comm}</span>
                </button>
                <button class="action-btn" onclick="openShareMenu('{escape(sid)}', '{s_title}')" title="शेयर">
                  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>
                </button>
                <a href="{s_href}" class="card-read-link">विस्तार से पढ़ें →</a>
              </div>
            </div>
          </div>
        </article>"""

    if top3_stories:
        s0 = top3_stories[0]
        sid0 = s0.get("id", "news-0")
        s0_likes = db_likes.get(sid0, _calc_seed_likes(sid0))
        s0_comm = db_comments.get(sid0, 0)
        s0_img = _safe_image(s0)
        s0_title = escape(s0.get("title") or "")
        s0_excerpt = escape(s0.get("excerpt") or "")
        s0_cat = escape(s0.get("catLabel") or "कृषि समाचार")
        s0_click = f"openStoryReader('{escape(sid0)}'); return false;"
        s0_href = escape(_story_url(s0))
        recent_slides_html += f"""
        <article class="recent-slide clone" data-index="3" data-news-id="{escape(sid0)}" aria-hidden="true">
          <div class="lead-media" onclick="{s0_click}" style="cursor:pointer;">
            <img src="{escape(s0_img)}" alt="{s0_title}" class="lead-img" width="600" height="338" decoding="async" onerror="this.src='/images/og-banner.webp'; this.onerror=null;">
            <div class="recent-slide-meta-badge">
              <span class="recent-post-number-tag">पोस्ट 1 · ताज़ा</span>
            </div>
          </div>
          <div class="lead-body">
            <div>
              <div><span class="lead-tag">🔥 {s0_cat}</span></div>
              <h2 class="lead-title" onclick="{s0_click}" style="cursor:pointer;">{s0_title}</h2>
              <p class="lead-excerpt">{s0_excerpt}</p>
            </div>
            <div class="lead-footer">
              <button class="action-btn" onclick="playNewsAudio(this, '{escape(sid0)}')" style="background:#e0f2fe;color:#0369a1;padding:6px 12px;border-radius:20px;">
                <span>▶️ खबर सुनें</span>
              </button>
              <div style="display:flex;align-items:center;gap:14px;">
                <button class="action-btn" onclick="toggleLike('{escape(sid0)}', this)" title="पसंद करें">
                  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/></svg>
                  <span class="like-count">{s0_likes}</span>
                </button>
                <button class="action-btn" onclick="openCommentDrawer('{escape(sid0)}')" title="किसान चर्चा">
                  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                  <span class="comment-count">{s0_comm}</span>
                </button>
                <button class="action-btn" onclick="openShareMenu('{escape(sid0)}', '{s0_title}')" title="शेयर">
                  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>
                </button>
                <a href="{s0_href}" class="card-read-link">विस्तार से पढ़ें →</a>
              </div>
            </div>
          </div>
        </article>"""

    # Trending list (items 2 to 5)
    trending_items_html = ""
    for idx, s in enumerate(grid_stories[:4], 1):
        t_title = escape(s.get("title") or "")
        t_id = escape(s.get("id") or "")
        t_time = escape(s.get("time") or "आज")
        t_click = f"openStoryReader('{t_id}'); return false;"
        trending_items_html += f"""
<a href="#" class="trending-item" onclick="{t_click}">
  <div class="trending-idx">0{idx}</div>
  <div class="trending-info">
    <div class="trending-item-title">{t_title}</div>
    <div class="trending-item-meta">⏱️ {t_time} · कृषि विश्लेषण</div>
  </div>
</a>"""

    # Grid items
    grid_cards_html = ""
    for s in grid_stories:
        s_id = s.get("id", "")
        s_likes = db_likes.get(s_id, _calc_seed_likes(s_id))
        s_comm = db_comments.get(s_id, 0)
        grid_cards_html += _generate_article_card_html(s, s_likes, s_comm)

    # SEO Structured Data
    ld_items = [
        {"@type": "ListItem", "position": i + 1, "name": s.get("title"), "url": f"{SITE}/krashi_news?story={s.get('id')}"}
        for i, s in enumerate(all_stories[:25])
    ]
    schema_org = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": "कृषि समाचार — ताज़ा खबरें, मंडी विश्लेषण व सरकारी योजनाएं",
        "url": f"{SITE}/krashi_news",
        "mainEntity": {
            "@type": "ItemList",
            "itemListElement": ld_items,
        },
    }
    ld_json = json.dumps(schema_org, ensure_ascii=False)

    now_hi = datetime.now().strftime("%d %B %Y")

    body_html = f"""
<div class="page-container">
  <!-- Page Header -->
  <div class="news-header-title-row">
    <div class="news-page-title-wrap">
      <h1 class="news-page-title">📰 कृषि समाचार</h1>
      <span class="news-count-pill" id="news-count-badge">{len(all_stories)}+ खबरें</span>
    </div>
    <div class="news-page-date">आज ताज़ा · {now_hi} · KrashiMitra Auto-Pilot &amp; Editorial</div>
  </div>

  <!-- Editorial Spotlight (Top 3 Recent Posts Slider & Trending) -->
  <div class="spotlight-grid">
    <!-- Recent Posts Tab Card (Top 3 News Sliding Carousel) -->
    <div class="recent-posts-tab-card" id="recent-posts-tab-card">
      <div class="recent-tab-header">
        <div class="recent-tab-title-wrap">
          <span class="recent-tab-badge">
            <span class="recent-live-dot" aria-hidden="true"></span>
            ताज़ा खबरें <span class="recent-badge-sub">(Recent Posts)</span>
          </span>
        </div>
        <div class="recent-tab-nav">
          <div class="recent-tab-pills" id="recent-tab-pills" role="tablist" aria-label="ताज़ा समाचार स्लाइड">
            <button type="button" class="recent-tab-pill active" data-slide="0" onclick="goToRecentSlide(0)" role="tab" aria-selected="true" title="पोस्ट 1"><span class="pill-dot"></span> 1</button>
            <button type="button" class="recent-tab-pill" data-slide="1" onclick="goToRecentSlide(1)" role="tab" aria-selected="false" title="पोस्ट 2"><span class="pill-dot"></span> 2</button>
            <button type="button" class="recent-tab-pill" data-slide="2" onclick="goToRecentSlide(2)" role="tab" aria-selected="false" title="पोस्ट 3"><span class="pill-dot"></span> 3</button>
          </div>
          <div class="recent-arrow-btns">
            <button type="button" class="recent-arrow-btn" onclick="prevRecentSlide()" title="पिछला समाचार" aria-label="पिछला समाचार">
              <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
            </button>
            <button type="button" class="recent-arrow-btn" onclick="nextRecentSlide()" title="अगला समाचार" aria-label="अगला समाचार">
              <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
            </button>
          </div>
        </div>
      </div>
      <div class="recent-slider-viewport" id="recent-slider-viewport" onmouseenter="pauseRecentSlider()" onmouseleave="resumeRecentSlider()">
        <div class="recent-slider-track" id="recent-slider-track">
          {recent_slides_html}
        </div>
        <div class="recent-progress-bar-wrap">
          <div class="recent-progress-bar" id="recent-progress-bar"></div>
        </div>
      </div>
    </div>

    <aside class="trending-box">
      <div class="trending-box-title">
        <span>⚡ शीर्ष सुर्खियां (Trending)</span>
      </div>
      <div class="trending-list">
        {trending_items_html}
      </div>
    </aside>
  </div>

  <!-- Audio Bulletin Digest Strip & Voice Controls -->
  <div class="bulletin-strip" id="audio-bulletin-section">
    <div class="bulletin-left">
      <span class="bulletin-icon">📻</span>
      <div class="bulletin-text-group">
        <div class="bulletin-heading" id="bulletin-main-title">2-मिनट दैनिक कृषि बुलेटिन</div>
        <div class="bulletin-sub" id="bulletin-sub-text">आज की सभी प्रमुख कृषि खबरें और बाज़ार रिपोर्ट एक साथ सुनें</div>
      </div>
      <div class="bulletin-equalizer" id="bulletin-equalizer" style="display:none;">
        <span class="eq-bar eq-1"></span>
        <span class="eq-bar eq-2"></span>
        <span class="eq-bar eq-3"></span>
        <span class="eq-bar eq-4"></span>
        <span class="eq-bar eq-5"></span>
      </div>
    </div>
    <div class="bulletin-controls">
      <div class="bulletin-settings-group">
        <select class="bulletin-select" id="voice-select" onchange="onVoiceChange(this.value)" title="समाचार वाचक की आवाज़ चुनें">
          <option value="swara">👩 स्वाति (नेचुरल न्यूज़ एंकर)</option>
          <option value="madhur">👨 मधुर (आकाशवाणी बुलेटिन)</option>
          <option value="google">✨ गूगल हिन्दी (क्लियर वॉइस)</option>
          <option value="auto">🌐 डिवाइस डिफ़ॉल्ट</option>
        </select>
        <select class="bulletin-select" id="speed-select" onchange="onSpeedChange(this.value)" title="बोलने की गति">
          <option value="0.88">0.9x गति (शांत)</option>
          <option value="0.96" selected>1.0x गति (सामान्य)</option>
          <option value="1.1">1.1x गति (तेज़)</option>
        </select>
      </div>
      <button class="btn-bulletin-play" id="btn-daily-bulletin" onclick="toggleDailyBulletin(this)">
        <span id="adb-play-icon">▶️</span>
        <span id="adb-play-text">पूरा बुलेटिन सुनें</span>
      </button>
    </div>
  </div>

  <!-- Filter & Search Card -->
  <div class="news-filter-card">
    <div class="news-search-row">
      <span style="font-size:16px;opacity:0.6;">🔍</span>
      <input type="text" id="news-search-input" class="news-search-input" placeholder="समाचार में खोजें… जैसे: धान पैकेज, आलू सब्सिडी, गेहूं MSP" oninput="handleClientSearch(this.value)">
    </div>
    <div class="news-cats-scroll" id="news-cats-bar">
      <div class="news-chip active" onclick="filterCategory(this, 'all')">🌿 सभी (All)</div>
      <div class="news-chip" onclick="filterCategory(this, 'yojana')">🏛️ सरकारी योजना</div>
      <div class="news-chip" onclick="filterCategory(this, 'mandi')">🏪 मंडी व भाव</div>
      <div class="news-chip" onclick="filterCategory(this, 'weather')">🌦️ मौसम अलर्ट</div>
      <div class="news-chip" onclick="filterCategory(this, 'khad')">🧪 उर्वरक सलाह</div>
      <div class="news-chip" onclick="filterCategory(this, 'keet')">🐛 कीट प्रबंधन</div>
    </div>
  </div>

  <!-- News Cards Grid -->
  <div class="news-grid" id="news-grid-container">
    {grid_cards_html}
  </div>
</div>

<!-- Story Reader Modal -->
<div class="km-modal-overlay" id="km-reader-modal" onclick="closeReaderModal(event)">
  <div class="km-modal-box" onclick="event.stopPropagation()">
    <button class="km-modal-close" onclick="closeReaderModal()">✕</button>
    <div id="reader-modal-body">
      <div style="font-size:12px;font-weight:700;color:#15803d;margin-bottom:6px;" id="reader-cat-tag">🏛️ सरकारी योजना</div>
      <h2 style="font-size:22px;color:#0f172a;line-height:1.35;margin:0 0 12px;" id="reader-title">समाचार शीर्षक</h2>
      <img id="reader-img" alt="" style="width:100%;max-height:280px;object-fit:cover;border-radius:8px;margin-bottom:14px;">
      <div style="background:#f0fdf4;border-left:4px solid #16a34a;padding:12px 14px;border-radius:4px;margin-bottom:16px;" id="reader-bullets-box">
        <div style="font-weight:800;color:#166534;font-size:13px;margin-bottom:6px;">⚡ मुख्य 3 बातें (Takeaways):</div>
        <div id="reader-bullets" style="font-size:13px;line-height:1.6;color:#14532d;"></div>
      </div>
      <div id="reader-full-text" style="font-size:14px;line-height:1.7;color:#334155;margin-bottom:20px;white-space:pre-line;"></div>
      <div style="border-top:1px solid #e2e8f0;padding-top:14px;display:flex;gap:10px;">
        <button onclick="playReaderStoryAudio()" class="action-btn" style="background:#e0f2fe;color:#0369a1;padding:8px 16px;border-radius:6px;">▶️ पूरी खबर सुनें</button>
        <button onclick="openCommentDrawer(currentStoryId)" class="action-btn" style="background:#f1f5f9;padding:8px 16px;border-radius:6px;">💬 किसान चर्चा देखें</button>
      </div>
    </div>
  </div>
</div>

<!-- Comments Drawer Modal -->
<div class="km-modal-overlay" id="km-comment-modal" onclick="closeCommentDrawer(event)">
  <div class="km-modal-box" onclick="event.stopPropagation()">
    <button class="km-modal-close" onclick="closeCommentDrawer()">✕</button>
    <h3 style="margin-top:0;font-size:18px;color:#0f172a;">💬 किसान चर्चा व टिप्पणियां</h3>
    <div id="comment-list-container" style="max-height:300px;overflow-y:auto;margin-bottom:16px;border:1px solid #e2e8f0;border-radius:8px;padding:12px;"></div>
    <form onsubmit="submitFarmerComment(event)">
      <input type="text" id="comment-author-input" placeholder="आपका नाम व जिला/गाँव (उदा. रामपाल, मेरठ)" style="width:100%;box-sizing:border-box;padding:10px;border:1px solid #cbd5e1;border-radius:6px;margin-bottom:8px;font-family:inherit;">
      <textarea id="comment-text-input" placeholder="अपनी राय या अनुभव लिखें…" rows="3" style="width:100%;box-sizing:border-box;padding:10px;border:1px solid #cbd5e1;border-radius:6px;margin-bottom:10px;font-family:inherit;" required></textarea>
      <button type="submit" style="background:#15803d;color:#fff;border:none;padding:10px 20px;border-radius:6px;font-weight:700;cursor:pointer;">टिप्पणी पोस्ट करें</button>
    </form>
  </div>
</div>

<!-- Embedded Master Dataset for Instant Client Search & Modals -->
<script>
window.KRASHI_ALL_NEWS = {json.dumps(_client_stories(all_stories), ensure_ascii=False)};
let currentStoryId = null;
let activeCommentNewsId = null;

function getApiBase() {{
  if (window.KRASHIMITRA_API_BASE) {{
    if (window.KRASHIMITRA_API_BASE.includes(':5500') || window.KRASHIMITRA_API_BASE.includes(':3000')) return 'http://localhost:8000';
    return window.KRASHIMITRA_API_BASE;
  }}
  if (location.hostname === 'localhost' || location.hostname === '127.0.0.1') return 'http://localhost:8000';
  return '';
}}

function ensureLoggedIn(opts) {{
  if (window.KMRequireLogin) return window.KMRequireLogin(opts);
  const token = localStorage.getItem("krishi_token");
  if (token && token !== "null" && token !== "undefined") return true;
  if (window.KMShowLoginGate) {{ window.KMShowLoginGate(opts); return false; }}
  window.location.href = "/login?next=" + encodeURIComponent(window.location.pathname);
  return false;
}}

function filterCategory(btn, cat) {{
  document.querySelectorAll('.news-chip').forEach(c => c.classList.remove('active'));
  btn.classList.add('active');
  const cards = document.querySelectorAll('.news-card');
  cards.forEach(c => {{
    if (cat === 'all' || c.getAttribute('data-cat') === cat) {{
      c.style.display = '';
    }} else {{
      c.style.display = 'none';
    }}
  }});
}}

function handleClientSearch(val) {{
  const query = (val || '').trim().toLowerCase();
  const cards = document.querySelectorAll('.news-card');
  cards.forEach(c => {{
    const title = (c.querySelector('.news-card-title')?.textContent || '').toLowerCase();
    const excerpt = (c.querySelector('.news-card-excerpt')?.textContent || '').toLowerCase();
    if (!query || title.includes(query) || excerpt.includes(query)) {{
      c.style.display = '';
    }} else {{
      c.style.display = 'none';
    }}
  }});
}}

function openStoryReader(id) {{
  const story = window.KRASHI_ALL_NEWS.find(s => s.id === id);
  if (!story) return;
  currentStoryId = id;
  document.getElementById('reader-title').textContent = story.title;
  document.getElementById('reader-cat-tag').textContent = story.catLabel || 'कृषि समाचार';
  document.getElementById('reader-img').src = story.image || '/images/og-banner.jpg';
  
  const bulletsBox = document.getElementById('reader-bullets');
  const bullets = story.bullets || [story.excerpt];
  bulletsBox.innerHTML = bullets.map((b, i) => `<div>${{i+1}}. ${{b}}</div>`).join('');
  
  document.getElementById('reader-full-text').textContent = story.full_story || story.excerpt || '';
  document.getElementById('km-reader-modal').classList.add('open');
}}

function closeReaderModal() {{
  document.getElementById('km-reader-modal').classList.remove('open');
  if ('speechSynthesis' in window) window.speechSynthesis.cancel();
}}

function openCommentDrawer(id) {{
  if (!ensureLoggedIn({{ title: "कमेंट करने के लिए लॉगिन करें", text: "किसान चर्चा में भाग लेने के लिए कृपया लॉगिन करें।" }})) return;
  activeCommentNewsId = id;
  const list = document.getElementById('comment-list-container');
  list.innerHTML = '<div style="color:#64748b;font-size:13px;">टिप्पणियां लोड हो रही हैं…</div>';
  document.getElementById('km-comment-modal').classList.add('open');
  
  fetch(getApiBase() + '/api/news/' + encodeURIComponent(id) + '/social')
    .then(r => r.json())
    .then(d => {{
      if (d && d.comments && d.comments.length) {{
        list.innerHTML = d.comments.map(c => `
          <div style="border-bottom:1px solid #f1f5f9;padding:6px 0;font-size:13px;">
            <b>🌾 ${{c.author_name}}</b>: ${{c.comment_text}}
          </div>
        `).join('');
      }} else {{
        list.innerHTML = '<div style="color:#64748b;font-size:13px;">अभी कोई टिप्पणी नहीं है। पहली टिप्पणी दें! ✍️</div>';
      }}
    }}).catch(() => {{ list.innerHTML = '<div style="color:#ef4444;font-size:13px;">टिप्पणियां लोड करने में विफल।</div>'; }});
}}

function closeCommentDrawer() {{
  document.getElementById('km-comment-modal').classList.remove('open');
}}

function submitFarmerComment(e) {{
  e.preventDefault();
  if (!ensureLoggedIn({{ title: "टिप्पणी दर्ज करने के लिए लॉगिन करें", text: "टिप्पणी दर्ज करने के लिए कृपया लॉगिन करें।" }})) return;
  const id = activeCommentNewsId || currentStoryId;
  if (!id) return;
  
  const nameInp = document.getElementById('comment-author-input');
  const textInp = document.getElementById('comment-text-input');
  const author = nameInp.value.trim() || 'किसान भाई';
  const text = textInp.value.trim();
  if (!text) return;
  
  const token = localStorage.getItem('krishi_token');
  fetch(getApiBase() + '/api/news/' + encodeURIComponent(id) + '/comment', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token }},
    body: JSON.stringify({{ author_name: author, comment_text: text }})
  }}).then(r => {{
    if (r.status === 401 || r.status === 403) {{
      ensureLoggedIn({{ title: "लॉगिन करें", text: "कृपया दोबारा लॉगिन करें।" }});
      return;
    }}
    return r.json();
  }}).then(res => {{
    if (res && res.success) {{
      textInp.value = '';
      alert('✓ आपकी टिप्पणी प्रकाशित कर दी गई!');
      openCommentDrawer(id);
    }}
  }}).catch(() => alert('त्रुटि'));
}}

function toggleLike(id, btn) {{
  if (!ensureLoggedIn({{ title: "लाइक करने के लिए लॉगिन करें", text: "समाचार को पसंद करने के लिए कृपया लॉगिन करें।" }})) return;
  const token = localStorage.getItem('krishi_token');
  const countEl = btn.querySelector('.like-count');
  
  fetch(getApiBase() + '/api/news/' + encodeURIComponent(id) + '/like', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token }},
    body: JSON.stringify({{ is_liked: true }})
  }}).then(r => r.json()).then(res => {{
    if (res && res.success && res.total_likes) {{
      btn.classList.add('liked');
      if (countEl) countEl.textContent = res.total_likes;
    }}
  }}).catch(() => {{}});
}}

// ── Studio-Grade Natural Voice & Audio Engine ──
var availableVoices = [];
var activeVoice = null;
var currentVoicePref = 'swara';
try {{ currentVoicePref = localStorage.getItem('km_news_voice') || 'swara'; }} catch(e) {{}}
var currentRatePref = 0.96;
try {{ currentRatePref = parseFloat(localStorage.getItem('km_news_speed') || '0.96'); }} catch(e) {{}}
var activeSpeechId = null;
var isBulletinPlaying = false;
var bulletinIndex = 0;

function initSpeechEngine() {{
  if (!('speechSynthesis' in window)) return;
  function populate() {{
    availableVoices = window.speechSynthesis.getVoices() || [];
    pickBestVoice();
  }}
  populate();
  if (window.speechSynthesis.onvoiceschanged !== undefined) {{
    window.speechSynthesis.onvoiceschanged = populate;
  }}
  var vs = document.getElementById('voice-select');
  if (vs) vs.value = currentVoicePref;
  var ss = document.getElementById('speed-select');
  if (ss) ss.value = String(currentRatePref);
}}

function pickBestVoice() {{
  if (!availableVoices || !availableVoices.length) return;
  var hiVoices = availableVoices.filter(function (v) {{
    var l = (v.lang || '').toLowerCase();
    var n = (v.name || '').toLowerCase();
    return l.indexOf('hi') === 0 || l.indexOf('hi-in') !== -1 || l.indexOf('hi_in') !== -1 || n.indexOf('hindi') !== -1;
  }});
  if (!hiVoices.length) {{
    hiVoices = availableVoices.filter(function (v) {{
      return (v.lang || '').toLowerCase().indexOf('in') !== -1;
    }});
  }}

  if (currentVoicePref === 'swara') {{
    activeVoice = hiVoices.find(function (v) {{
      var n = v.name.toLowerCase();
      return (n.indexOf('swara') !== -1 && n.indexOf('natural') !== -1) || n.indexOf('swara online') !== -1;
    }}) || hiVoices.find(function (v) {{
      return v.name.toLowerCase().indexOf('google') !== -1;
    }}) || hiVoices.find(function (v) {{
      return v.name.toLowerCase().indexOf('swara') !== -1;
    }}) || hiVoices[0] || availableVoices[0];
  }} else if (currentVoicePref === 'madhur') {{
    activeVoice = hiVoices.find(function (v) {{
      var n = v.name.toLowerCase();
      return (n.indexOf('madhur') !== -1 && n.indexOf('natural') !== -1) || n.indexOf('madhur online') !== -1;
    }}) || hiVoices.find(function (v) {{
      return v.name.toLowerCase().indexOf('madhur') !== -1;
    }}) || hiVoices[1] || hiVoices[0] || availableVoices[0];
  }} else if (currentVoicePref === 'google') {{
    activeVoice = hiVoices.find(function (v) {{
      return v.name.toLowerCase().indexOf('google') !== -1;
    }}) || hiVoices[0] || availableVoices[0];
  }} else {{
    activeVoice = hiVoices.find(function (v) {{
      return v.name.toLowerCase().indexOf('natural') !== -1;
    }}) || hiVoices.find(function (v) {{
      return v.name.toLowerCase().indexOf('google') !== -1;
    }}) || hiVoices[0] || availableVoices[0];
  }}
}}

function onVoiceChange(val) {{
  currentVoicePref = val;
  try {{ localStorage.setItem('km_news_voice', val); }} catch(e) {{}}
  pickBestVoice();
  restartCurrentSpeech();
}}

function onSpeedChange(val) {{
  currentRatePref = parseFloat(val) || 0.96;
  try {{ localStorage.setItem('km_news_speed', val); }} catch(e) {{}}
  restartCurrentSpeech();
}}

function restartCurrentSpeech() {{
  if (window.speechSynthesis && window.speechSynthesis.speaking) {{
    if (isBulletinPlaying) {{
      window.speechSynthesis.cancel();
      playNextBulletinStory();
    }} else if (activeSpeechId) {{
      var currId = activeSpeechId;
      window.speechSynthesis.cancel();
      playNewsAudio(null, currId);
    }}
  }}
}}

function cleanNewsForSpeech(raw) {{
  if (!raw) return '';
  var t = raw;
  t = t.replace(/\\bMSP\\b/g, 'न्यूनतम समर्थन मूल्य एमएसपी');
  t = t.replace(/\\bFRP\\b/g, 'उचित और लाभकारी मूल्य');
  t = t.replace(/\\bSAP\\b/g, 'राज्य परामर्श मूल्य');
  t = t.replace(/\\bDAP\\b/g, 'डीएपी खाद');
  t = t.replace(/\\bNPK\\b/g, 'एनपीके खाद');
  t = t.replace(/\\bKCC\\b/g, 'किसान क्रेडिट कार्ड');
  t = t.replace(/\\bPM-KUSUM\\b|\\bPM KUSUM\\b/g, 'पीएम कुसुम योजना');
  t = t.replace(/\\bPMFBY\\b/g, 'प्रधानमंत्री फसल बीमा योजना');
  t = t.replace(/\\be-NAM\\b|\\beNAM\\b/g, 'ई-नाम राष्ट्रीय कृषि बाजार');
  t = t.replace(/\\bAPMC\\b/g, 'कृषि उपज मंडी');
  t = t.replace(/\\bNLM\\b/g, 'राष्ट्रीय पशुधन मिशन');
  t = t.replace(/\\bDBW\\b/g, 'डीबीडब्ल्यू');
  t = t.replace(/\\bLSD\\b/g, 'लंपी स्किन रोग');
  t = t.replace(/\\bTR4\\b/g, 'टीआर चार');
  t = t.replace(/\\bBLB\\b/g, 'बीएलबी झुलसा रोग');
  t = t.replace(/₹\\s*([0-9,]+)/g, '$1 रुपये ');
  t = t.replace(/([0-9]+)-([0-9]+)%/g, '$1 से $2 प्रतिशत ');
  t = t.replace(/([0-9]+)%/g, '$1 प्रतिशत ');
  t = t.replace(/([0-9]+)वीं/g, '$1 वीं');
  t = t.replace(/([:;—–])/g, '। ');
  t = t.replace(/[\\u{{1F300}}-\\u{{1F6FF}}\\u{{1F900}}-\\u{{1F9FF}}\\u{{2600}}-\\u{{26FF}}\\u{{2700}}-\\u{{27BF}}]/gu, '');
  t = t.replace(/https?:\\/\\/\\S+/g, '');
  t = t.replace(/\\s+/g, ' ').trim();
  return t;
}}

function playNewsAudio(btn, id) {{
  var story = (window.KRASHI_ALL_NEWS || []).find(function(s) {{ return s.id === id; }});
  if (!story || !('speechSynthesis' in window)) return;

  if (window.speechSynthesis.speaking && activeSpeechId === id) {{
    window.speechSynthesis.cancel();
    activeSpeechId = null;
    updateAudioButtonsUi();
    if (window.recentSlider && window.recentSlider.isInViewport && !document.hidden) {{
      window.recentSlider.resume();
    }}
    return;
  }}

  window.speechSynthesis.cancel();
  activeSpeechId = id;
  updateAudioButtonsUi();
  if (window.recentSlider) window.recentSlider.pause();

  pickBestVoice();

  var cleanText = cleanNewsForSpeech(story.title + '। ' + (story.excerpt || ''));
  var utter = new SpeechSynthesisUtterance(cleanText);
  utter.lang = 'hi-IN';
  if (activeVoice) utter.voice = activeVoice;
  utter.rate = currentRatePref;
  utter.pitch = 1.0;

  utter.onend = function () {{
    activeSpeechId = null;
    updateAudioButtonsUi();
    if (window.recentSlider && window.recentSlider.isInViewport && !document.hidden) {{
      window.recentSlider.resume();
    }}
  }};
  utter.onerror = function () {{
    activeSpeechId = null;
    updateAudioButtonsUi();
    if (window.recentSlider && window.recentSlider.isInViewport && !document.hidden) {{
      window.recentSlider.resume();
    }}
  }};

  window.speechSynthesis.speak(utter);
}}

function playReaderStoryAudio() {{
  if (!currentStoryId) return;
  playNewsAudio(null, currentStoryId);
}}

function toggleDailyBulletin(btn) {{
  if (!('speechSynthesis' in window)) {{
    alert('आपके डिवाइस में आवाज़ (TTS) सपोर्ट उपलब्ध नहीं है।');
    return;
  }}

  var icon = document.getElementById('adb-play-icon');
  var text = document.getElementById('adb-play-text');
  var mainTitle = document.getElementById('bulletin-main-title');
  var subText = document.getElementById('bulletin-sub-text');

  if (isBulletinPlaying) {{
    window.speechSynthesis.cancel();
    isBulletinPlaying = false;
    if (icon) icon.textContent = '▶️';
    if (text) text.textContent = 'पूरा बुलेटिन सुनें';
    if (mainTitle) mainTitle.textContent = '2-मिनट दैनिक कृषि बुलेटिन';
    if (subText) subText.textContent = 'आज की सभी प्रमुख कृषि खबरें और बाज़ार रिपोर्ट एक साथ सुनें';
    activeSpeechId = null;
    updateAudioButtonsUi();
    return;
  }}

  window.speechSynthesis.cancel();
  isBulletinPlaying = true;
  bulletinIndex = 0;
  if (icon) icon.textContent = '⏹️';
  if (text) text.textContent = 'बुलेटिन रोकें';

  playNextBulletinStory();
}}

function playNextBulletinStory() {{
  var newsList = window.KRASHI_ALL_NEWS || [];
  var icon = document.getElementById('adb-play-icon');
  var text = document.getElementById('adb-play-text');
  var mainTitle = document.getElementById('bulletin-main-title');
  var subText = document.getElementById('bulletin-sub-text');

  if (!isBulletinPlaying || bulletinIndex >= Math.min(10, newsList.length)) {{
    isBulletinPlaying = false;
    if (icon) icon.textContent = '▶️';
    if (text) text.textContent = 'पूरा बुलेटिन सुनें';
    if (mainTitle) mainTitle.textContent = '2-मिनट दैनिक कृषि बुलेटिन';
    if (subText) subText.textContent = 'आज की सभी प्रमुख कृषि खबरें और बाज़ार रिपोर्ट एक साथ सुनें';
    activeSpeechId = null;
    updateAudioButtonsUi();
    return;
  }}

  var item = newsList[bulletinIndex];
  activeSpeechId = item.id;
  updateAudioButtonsUi();

  pickBestVoice();

  if (mainTitle) mainTitle.textContent = '📻 बुलेटिन समाचार (' + (bulletinIndex + 1) + '/10): ' + (item.catLabel || 'कृषि');
  if (subText) subText.textContent = item.title;

  var intro = (bulletinIndex === 0)
    ? 'नमस्ते किसान भाइयों! कृषि मित्र दैनिक बुलेटिन में आपका स्वागत है। पहली मुख्य खबर। '
    : 'अगली खबर। ';
  var textToSpeak = cleanNewsForSpeech(intro + item.title + '। ' + (item.excerpt || ''));

  var utter = new SpeechSynthesisUtterance(textToSpeak);
  utter.lang = 'hi-IN';
  if (activeVoice) utter.voice = activeVoice;
  utter.rate = currentRatePref;
  utter.pitch = 1.0;

  utter.onend = function () {{
    bulletinIndex++;
    if (isBulletinPlaying) {{
      setTimeout(playNextBulletinStory, 600);
    }}
  }};
  utter.onerror = function () {{
    isBulletinPlaying = false;
    activeSpeechId = null;
    updateAudioButtonsUi();
  }};

  window.speechSynthesis.speak(utter);
}}

function updateAudioButtonsUi() {{
  var eq = document.getElementById('bulletin-equalizer');
  if (eq) {{
    eq.style.display = (isBulletinPlaying || activeSpeechId) ? 'inline-flex' : 'none';
  }}
}}

function openShareMenu(id, title) {{
  const url = window.location.origin + '/krashi_news?story=' + encodeURIComponent(id);
  if (navigator.share) {{
    navigator.share({{ title: title, url: url }});
  }} else {{
    prompt('शेयर करने के लिए लिंक कॉपी करें:', url);
  }}
}}

const recentSlider = {{
  currentIndex: 0,
  totalSlides: 3,
  slideDuration: 3000,
  slideTimer: null,
  startTime: 0,
  remainingTime: 3000,
  isPaused: false,
  isInViewport: true,
  track: null,
  pills: [],
  progressBar: null,
  observer: null,

  init: function() {{
    this.track = document.getElementById('recent-slider-track');
    this.progressBar = document.getElementById('recent-progress-bar');
    this.pills = Array.from(document.querySelectorAll('#recent-tab-pills .recent-tab-pill'));
    if (!this.track) return;

    var self = this;

    // Continuous Left Loop: When transition ends on clone (index 3), instantly jump back to index 0
    this.track.addEventListener('transitionend', function(e) {{
      if (e.target !== self.track) return;
      if (self.currentIndex === self.totalSlides) {{
        self.track.style.transition = 'none';
        self.currentIndex = 0;
        self.track.style.transform = 'translate3d(0%, 0, 0)';
        void self.track.offsetHeight;
        self.track.style.transition = 'transform 0.42s cubic-bezier(0.25, 1, 0.5, 1)';
        self.updatePills(0);
      }}
    }});

    // Directional touch gestures (prioritize fluid native vertical scrolling on mobile)
    var viewport = document.getElementById('recent-slider-viewport');
    if (viewport) {{
      var touchStartX = 0;
      var touchStartY = 0;
      var touchStartTime = 0;

      viewport.addEventListener('touchstart', function(e) {{
        if (e.touches && e.touches[0]) {{
          touchStartX = e.touches[0].clientX;
          touchStartY = e.touches[0].clientY;
          touchStartTime = Date.now();
          self.pause();
        }}
      }}, {{ passive: true }});

      viewport.addEventListener('touchend', function(e) {{
        if (e.changedTouches && e.changedTouches[0]) {{
          var diffX = e.changedTouches[0].clientX - touchStartX;
          var diffY = e.changedTouches[0].clientY - touchStartY;
          var touchElapsed = Date.now() - touchStartTime;

          // Only trigger slide navigation if gesture was intentionally horizontal (> 35px, 1.2x vertical)
          if (Math.abs(diffX) > Math.abs(diffY) * 1.2 && Math.abs(diffX) > 35 && touchElapsed < 800) {{
            if (diffX < 0) {{
              self.next();
            }} else {{
              self.prev();
            }}
          }}
        }}
        // Small reading cushion before resuming autoplay
        setTimeout(function() {{
          if (self.isInViewport && !document.hidden) {{
            self.resume();
          }}
        }}, 600);
      }}, {{ passive: true }});
    }}

    // IntersectionObserver: 0% battery/CPU drain when farmer scrolls down the feed
    if ('IntersectionObserver' in window) {{
      this.observer = new IntersectionObserver(function(entries) {{
        entries.forEach(function(entry) {{
          self.isInViewport = entry.isIntersecting;
          if (entry.isIntersecting) {{
            if (!document.hidden && (!window.speechSynthesis || !window.speechSynthesis.speaking)) {{
              self.resume();
            }}
          }} else {{
            self.pause();
          }}
        }});
      }}, {{ threshold: 0.15 }});

      var card = document.getElementById('recent-posts-tab-card') || viewport;
      if (card) this.observer.observe(card);
    }}

    // Page Visibility API: Stop animation completely when phone is locked or app in background
    document.addEventListener('visibilitychange', function() {{
      if (document.hidden) {{
        self.pause();
      }} else if (self.isInViewport) {{
        self.resume();
      }}
    }});

    this.startCycle(this.slideDuration);
  }},

  startCycle: function(duration) {{
    clearTimeout(this.slideTimer);
    this.remainingTime = duration;
    this.startTime = Date.now();

    if (this.progressBar) {{
      // GPU-accelerated linear progress bar transition with 0 polling intervals
      this.progressBar.style.transition = 'none';
      this.progressBar.style.transform = 'scaleX(0)';
      void this.progressBar.offsetWidth;
      if (!this.isPaused && this.isInViewport && (!window.speechSynthesis || !window.speechSynthesis.speaking)) {{
        this.progressBar.style.transition = 'transform ' + duration + 'ms linear';
        this.progressBar.style.transform = 'scaleX(1)';
      }}
    }}

    var self = this;
    this.slideTimer = setTimeout(function() {{
      if (!self.isPaused && self.isInViewport && (!window.speechSynthesis || !window.speechSynthesis.speaking)) {{
        self.next();
      }} else {{
        self.startCycle(self.slideDuration);
      }}
    }}, duration);
  }},

  goTo: function(index) {{
    if (!this.track) return;
    this.currentIndex = index;
    this.track.style.transition = 'transform 0.42s cubic-bezier(0.25, 1, 0.5, 1)';
    this.track.style.transform = 'translate3d(-' + (this.currentIndex * 100) + '%, 0, 0)';
    this.updatePills(this.currentIndex % this.totalSlides);
    this.startCycle(this.slideDuration);
  }},

  next: function() {{
    if (!this.track) return;
    this.currentIndex++;
    this.track.style.transition = 'transform 0.42s cubic-bezier(0.25, 1, 0.5, 1)';
    this.track.style.transform = 'translate3d(-' + (this.currentIndex * 100) + '%, 0, 0)';
    this.updatePills(this.currentIndex % this.totalSlides);
    this.startCycle(this.slideDuration);
  }},

  prev: function() {{
    if (!this.track) return;
    if (this.currentIndex === 0) {{
      // Instant jump to clone at index 3, then slide to index 2
      this.track.style.transition = 'none';
      this.currentIndex = this.totalSlides;
      this.track.style.transform = 'translate3d(-' + (this.currentIndex * 100) + '%, 0, 0)';
      void this.track.offsetHeight;
      this.currentIndex = this.totalSlides - 1;
      this.track.style.transition = 'transform 0.42s cubic-bezier(0.25, 1, 0.5, 1)';
      this.track.style.transform = 'translate3d(-' + (this.currentIndex * 100) + '%, 0, 0)';
    }} else {{
      this.currentIndex--;
      this.track.style.transition = 'transform 0.42s cubic-bezier(0.25, 1, 0.5, 1)';
      this.track.style.transform = 'translate3d(-' + (this.currentIndex * 100) + '%, 0, 0)';
    }}
    this.updatePills(this.currentIndex % this.totalSlides);
    this.startCycle(this.slideDuration);
  }},

  updatePills: function(activeIdx) {{
    this.pills.forEach(function(pill, idx) {{
      var isActive = (idx === activeIdx);
      pill.classList.toggle('active', isActive);
      pill.setAttribute('aria-selected', isActive ? 'true' : 'false');
    }});
  }},

  pause: function() {{
    if (this.isPaused) return;
    this.isPaused = true;
    clearTimeout(this.slideTimer);

    if (this.progressBar) {{
      var elapsed = Date.now() - this.startTime;
      this.remainingTime = Math.max(200, this.remainingTime - elapsed);
      var currentScale = Math.min(1, Math.max(0, (this.slideDuration - this.remainingTime) / this.slideDuration));
      this.progressBar.style.transition = 'none';
      this.progressBar.style.transform = 'scaleX(' + currentScale + ')';
    }}
  }},

  resume: function() {{
    if (!this.isPaused) return;
    if (window.speechSynthesis && window.speechSynthesis.speaking && activeSpeechId) return;
    this.isPaused = false;
    this.startTime = Date.now();

    var self = this;
    var rem = Math.max(200, this.remainingTime);

    if (this.progressBar) {{
      void this.progressBar.offsetWidth;
      this.progressBar.style.transition = 'transform ' + rem + 'ms linear';
      this.progressBar.style.transform = 'scaleX(1)';
    }}

    clearTimeout(this.slideTimer);
    this.slideTimer = setTimeout(function() {{
      if (!self.isPaused && self.isInViewport && (!window.speechSynthesis || !window.speechSynthesis.speaking)) {{
        self.next();
      }} else {{
        self.startCycle(self.slideDuration);
      }}
    }}, rem);
  }}
}};

function goToRecentSlide(idx) {{
  if (recentSlider) recentSlider.goTo(idx);
}}
function nextRecentSlide() {{
  if (recentSlider) recentSlider.next();
}}
function prevRecentSlide() {{
  if (recentSlider) recentSlider.prev();
}}
function pauseRecentSlider() {{
  if (recentSlider) recentSlider.pause();
}}
function resumeRecentSlider() {{
  if (recentSlider) recentSlider.resume();
}}

// Deep link check ?story=... and background PostgreSQL social sync
document.addEventListener('DOMContentLoaded', () => {{
  initSpeechEngine();
  recentSlider.init();
  const params = new URLSearchParams(window.location.search);
  const deepId = params.get('story');
  if (deepId) openStoryReader(deepId);

  // Sync live likes & comments from PostgreSQL in single batch call
  const ids = (window.KRASHI_ALL_NEWS || []).slice(0, 50).map(s => s.id);
  if (ids.length) {{
    fetch(getApiBase() + '/api/news/social/batch?ids=' + encodeURIComponent(ids.join(',')))
      .then(r => r.json())
      .then(batch => {{
        if (!batch) return;
        Object.keys(batch).forEach(nid => {{
          const stats = batch[nid];
          if (!stats || typeof stats !== 'object') return;
          if (nid === 'news-lead' || (window.KRASHI_ALL_NEWS[0] && window.KRASHI_ALL_NEWS[0].id === nid)) {{
            const ll = document.getElementById('lead-like-count');
            const lc = document.getElementById('lead-comment-count');
            if (ll && stats.likes !== undefined) ll.textContent = stats.likes;
            if (lc && stats.comments !== undefined) lc.textContent = stats.comments;
          }}
          const card = document.querySelector(`.news-card[data-id="${{nid}}"]`);
          if (card) {{
            const lk = card.querySelector('.like-count');
            const cm = card.querySelector('.comment-count');
            if (lk && stats.likes !== undefined) lk.textContent = stats.likes;
            if (cm && stats.comments !== undefined) cm.textContent = stats.comments;
          }}
        }});
      }}).catch(() => {{}});
  }}
}});
</script>
"""

    return _news_doc(
        # 61 chars, no brand suffix — Google truncates past ~68 and the
        # brand is not what anyone searches for (memory: serp-length-budgets).
        title="कृषि समाचार: आज की ताज़ा किसान खबरें, मंडी भाव व सरकारी योजना",
        desc="किसानों के लिए आज की ताज़ा कृषि खबरें — मंडी भाव, सरकारी योजना, मौसम चेतावनी और फसल सलाह, सरल हिंदी में रोज़ाना अपडेट।",
        body=body_html,
        ld=ld_json,
    )
