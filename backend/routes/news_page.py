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
from fastapi.responses import HTMLResponse

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
@media(max-width:768px){.top-utility-inner{padding:0 14px}}
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
  border: 1.5px solid #111827;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  padding: 12px 18px;
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
  font-size: 24px;
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
  flex-wrap: wrap;
}
.bulletin-select {
  background: #f8faf8;
  border: 1px solid #cbd5e1;
  border-radius: 16px;
  padding: 6px 10px;
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
    flex-direction: column;
    align-items: stretch;
    gap: 12px;
    padding: 12px 14px;
  }
  .bulletin-controls {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    width: 100%;
  }
  .bulletin-select {
    flex: 1 1 130px;
    max-width: none;
  }
  .btn-bulletin-play {
    width: 100%;
    justify-content: center;
  }
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
<div class="topbar-spacer" id="topbar-spacer" style="height:135px;"></div>
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


def _news_doc(title: str, desc: str, body: str, ld: str = "") -> HTMLResponse:
    canon = f"{SITE}/krashi_news"
    og = f"{SITE}/images/og-banner.webp"
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="hi">
<head>
{_ANALYTICS}
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
{f'<script type="application/ld+json">{ld}</script>' if ld else ''}
<style>{_BASE_RESET_CSS}{NEWS_EXTRA_CSS}</style>
</head>
<body>
{_news_header()}
<nav class="crumbs" style="max-width:1240px;margin:0 auto;padding:16px 24px 0;box-sizing:border-box;"><a href="{SITE}/">कृषि मित्र</a> › <span class="current">कृषि समाचार</span></nav>
{body}
{_news_footer()}
<script src="/api-config.js"></script>
<script src="/drawer-menu.js" defer></script>
<script src="/bottomnav.js" defer></script>
<script src="/header-scroll.js" defer></script>
</body>
</html>""", headers=_CACHE_HEADERS)


def _generate_article_card_html(item: dict, live_likes: int, live_comments: int) -> str:
    """Renders a single news card with 3-tier mobile layout."""
    item_id = escape(item.get("id") or "")
    title = escape(item.get("title") or "")
    excerpt = escape(item.get("excerpt") or "")
    category = escape(item.get("category") or "all")
    cat_label = escape(item.get("catLabel") or "समाचार")
    time_str = escape(item.get("time") or "आज ताज़ा")
    read_time = escape(item.get("readTime") or "3 मिनट")
    img_url = item.get("image") or "/images/og-banner.jpg"
    if not img_url.startswith("http") and not img_url.startswith("/"):
        img_url = "/" + img_url
    img_url = escape(img_url)

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
    <a href="#" class="card-read-link" onclick="{click_action}">विस्तार से पढ़ें →</a>
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
    lead_img = lead_story.get("image") or "/images/og-banner.jpg"
    if not lead_img.startswith("http") and not lead_img.startswith("/"):
        lead_img = "/" + lead_img

    lead_title_esc = escape(lead_story.get("title") or "")
    lead_excerpt_esc = escape(lead_story.get("excerpt") or "")
    lead_click = f"openStoryReader('{escape(lead_id)}'); return false;"

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
      <button class="btn-bulletin-play" id="btn-daily-bulletin" onclick="toggleDailyBulletin(this)">
        <span id="adb-play-icon">▶️</span>
        <span id="adb-play-text">पूरा बुलेटिन सुनें</span>
      </button>
    </div>
  </div>

  <!-- Editorial Spotlight -->
  <div class="spotlight-grid">
    <article class="lead-story" id="lead-story-card">
      <div class="lead-media" onclick="{lead_click}" style="cursor:pointer;">
        <img src="{escape(lead_img)}" alt="{lead_title_esc}" class="lead-img" fetchpriority="high">
      </div>
      <div class="lead-body">
        <div>
          <div><span class="lead-tag">🔥 मुख्य समाचार</span></div>
          <h2 class="lead-title" onclick="{lead_click}" style="cursor:pointer;">{lead_title_esc}</h2>
          <p class="lead-excerpt">{lead_excerpt_esc}</p>
        </div>
        <div class="lead-footer">
          <button class="action-btn" onclick="playNewsAudio(this, '{escape(lead_id)}')" style="background:#e0f2fe;color:#0369a1;padding:6px 12px;border-radius:20px;">
            <span>▶️ खबर सुनें</span>
          </button>
          <div style="display:flex;align-items:center;gap:14px;">
            <button class="action-btn" onclick="toggleLike('{escape(lead_id)}', this)" title="पसंद करें">
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/></svg>
              <span class="like-count" id="lead-like-count">{lead_likes}</span>
            </button>
            <button class="action-btn" onclick="openCommentDrawer('{escape(lead_id)}')" title="किसान चर्चा">
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
              <span class="comment-count" id="lead-comment-count">{lead_comments}</span>
            </button>
            <button class="action-btn" onclick="openShareMenu('{escape(lead_id)}', '{lead_title_esc}')" title="शेयर">
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>
            </button>
            <a href="#" class="card-read-link" onclick="{lead_click}">विस्तार से पढ़ें →</a>
          </div>
        </div>
      </div>
    </article>

    <aside class="trending-box">
      <div class="trending-box-title">
        <span>⚡ शीर्ष सुर्खियां (Trending)</span>
      </div>
      <div class="trending-list">
        {trending_items_html}
      </div>
    </aside>
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
      <img id="reader-img" src="" alt="" style="width:100%;max-height:280px;object-fit:cover;border-radius:8px;margin-bottom:14px;">
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
window.KRASHI_ALL_NEWS = {json.dumps(all_stories, ensure_ascii=False)};
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
    return;
  }}

  window.speechSynthesis.cancel();
  activeSpeechId = id;
  updateAudioButtonsUi();

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
  }};
  utter.onerror = function () {{
    activeSpeechId = null;
    updateAudioButtonsUi();
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

// Deep link check ?story=... and background PostgreSQL social sync
document.addEventListener('DOMContentLoaded', () => {{
  initSpeechEngine();
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
        title="कृषि समाचार — ताज़ा खबरें, मंडी विश्लेषण व सरकारी योजनाएं | KrashiMitra",
        desc="भारत के किसानों के लिए ताज़ा कृषि समाचार, मंडी भाव, मौसम चेतावनी, सरकारी योजनाएं और विशेषज्ञ सलाह। हिंदी में रोज़ाना ताज़ा अपडेट।",
        body=body_html,
        ld=ld_json,
    )
