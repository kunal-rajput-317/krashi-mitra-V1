# ============================================================
# routes/sitemap.py
# Krishi Mitra — the root sitemap, generated (not hand-written)
#
# GET /sitemap.xml  → core pages + the articles index + every article
#
# This replaces the hand-maintained frontend/sitemap.xml. That file had to be
# edited by hand for every new article and every content change, so it drifted:
# its <lastmod> dates were weeks behind the pages they described, and four
# article slugs were spelled in the wrong case. The URL list and the dates are
# both derivable, so they are derived here instead:
#
#   • the article list  → whatever is actually in frontend/articles/
#   • every <lastmod>   → the page's OWN JSON-LD "dateModified", the same single
#                         source of truth the article cards already read
#                         (routes/articles.py), falling back to the file's mtime
#                         for the few pages that carry no JSON-LD date
#   • article <image>   → the article's own og:image
#
# What is NOT derivable stays declared in CORE below: <priority>, <changefreq>
# and which languages a page is actually translated into are editorial calls,
# not facts about the file. They are the only thing anyone should need to touch.
#
# The two programmatic surfaces keep their own generated sitemaps — /bhav and
# /product each list thousands of URLs from the DB / the shop catalog, and
# robots.txt points crawlers at all three. Only their hubs are listed here; do
# not re-add individual /bhav or /product URLs (the last hand-written list went
# stale the moment a mandi stopped reporting).
# ============================================================

import re
from datetime import date, datetime
from html import escape
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import Response

router = APIRouter()

SITE = "https://krashimitra.in"
_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
_ARTICLES = _FRONTEND / "articles"

# Articles that are not articles.
_SKIP = {"index.html", "article_template.html"}

_MODIFIED_RE = re.compile(r'"dateModified"\s*:\s*"(\d{4}-\d{2}-\d{2})')
_PUBLISHED_RE = re.compile(r'"datePublished"\s*:\s*"(\d{4}-\d{2}-\d{2})')
_OG_IMAGE_RE = re.compile(
    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', re.I)

# hreflang code → the value Google expects
_HREFLANG = {"hi": "hi", "en": "en-IN", "kn": "kn"}

# (file, url path, priority, changefreq, languages, images)
#
# languages: () none · ("hi",) Hindi-only, no ?lang= query · more than one →
# the page has a real language switcher, so each variant gets its own ?lang= URL.
CORE = [
    ("index.html",          "/",                1.0, "daily",  ("hi",),
     ("/assets/hero-section-photo.webp",)),
    ("mandi.html",          "/mandi",           1.0, "daily",  ("hi", "en", "kn"), ()),
    ("meri_fasal.html",     "/meri_fasal",      0.9, "weekly", ("hi",), ()),
    ("shop.html",           "/shop",            0.9, "daily",  ("hi", "en", "kn"),
     ("/images/shop-hero.webp",)),
    ("krashi_bajar.html",   "/krashi_bajar",    0.9, "daily",  ("hi", "en", "kn"), ()),
    ("chat.html",           "/chat",            0.9, "daily",  ("hi", "en", "kn"), ()),
    ("weather.html",        "/weather",         0.8, "daily",  ("hi", "en", "kn"), ()),
    ("sarkari_yojana.html", "/sarkari_yojana",  0.8, "weekly", ("hi", "en", "kn"), ()),
    ("khoj.html",           "/khoj",            0.7, "weekly", ("hi", "en", "kn"), ()),
    ("map.html",            "/map",             0.7, "weekly", ("hi", "en"),
     ("/images/up-ka-naksha-district-map.png",)),
    ("rajasthan-ka-naksha.html", "/rajasthan-ka-naksha", 0.7, "weekly", ("hi", "en"),
     ("/images/rajasthan-ka-naksha-district-map.png",)),
    ("help.html",           "/help",            0.6, "weekly", ("hi",), ()),
    ("about.html",          "/about",           0.4, "yearly", (), ()),
    ("privacy-policy.html", "/privacy-policy",  0.3, "yearly", (), ()),
    # login.html is deliberately absent — the page is noindex.
    ("articles/index.html", "/articles/",       0.9, "daily",  ("hi", "en", "kn"), ()),
]

# Hubs only. The full lists live in /bhav/sitemap.xml and /product/sitemap.xml.
HUBS = [("/bhav", 0.9, "daily"), ("/product/", 0.8, "weekly")]

_ARTICLE_PRIORITY = 0.8
_ARTICLE_CHANGEFREQ = "weekly"


def _page_date(path: Path) -> str:
    """The page's own JSON-LD dateModified — the same source the article cards
    read, so a page and its sitemap entry can never disagree. Pages without
    JSON-LD dates (index, privacy-policy, meri_fasal) fall back to the file's
    mtime, and an unreadable file falls back to today rather than dropping the
    URL: a missing <lastmod> costs nothing, a missing <loc> costs a page."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return date.today().isoformat()
    m = _MODIFIED_RE.search(text) or _PUBLISHED_RE.search(text)
    if m:
        return m.group(1)
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).date().isoformat()
    except OSError:
        return date.today().isoformat()


def _og_image(path: Path) -> str:
    try:
        m = _OG_IMAGE_RE.search(path.read_text(encoding="utf-8", errors="ignore"))
    except OSError:
        return ""
    return m.group(1) if m else ""


def _abs(url: str) -> str:
    return url if url.startswith("http") else f"{SITE}{url}"


def _entry(loc: str, lastmod: str, changefreq: str, priority: float,
           langs: tuple = (), images: tuple = ()) -> str:
    out = [f"  <url>", f"    <loc>{escape(loc)}</loc>"]
    if langs:
        for code in langs:
            href = f"{loc}?lang={code}" if len(langs) > 1 else loc
            out.append(f'    <xhtml:link rel="alternate" hreflang="{_HREFLANG[code]}" '
                       f'href="{escape(href)}"/>')
        out.append(f'    <xhtml:link rel="alternate" hreflang="x-default" '
                   f'href="{escape(loc)}"/>')
    if lastmod:
        out.append(f"    <lastmod>{lastmod}</lastmod>")
    out.append(f"    <changefreq>{changefreq}</changefreq>")
    out.append(f"    <priority>{priority}</priority>")
    for img in images:
        out.append(f"    <image:image><image:loc>{escape(_abs(img))}</image:loc>"
                   f"</image:image>")
    out.append("  </url>")
    return "\n".join(out)


def _build() -> str:
    urls = []

    for fname, path_, priority, changefreq, langs, images in CORE:
        f = _FRONTEND / fname
        urls.append(_entry(f"{SITE}{path_}", _page_date(f), changefreq, priority,
                           langs, images))

    # Every article actually on disk — not a list anyone has to remember to update.
    # The URL is the lowercased stem: files like DAP-guide-up.html are served at
    # /articles/dap-guide-up (Netlify 301s the mixed-case form), and the old
    # hand-written sitemap had four of these spelled the wrong way.
    for f in sorted(_ARTICLES.glob("*.html")):
        if f.name in _SKIP:
            continue
        slug = f.stem.lower()
        img = _og_image(f)
        urls.append(_entry(f"{SITE}/articles/{slug}", _page_date(f),
                           _ARTICLE_CHANGEFREQ, _ARTICLE_PRIORITY, ("hi",),
                           (img,) if img else ()))

    for path_, priority, changefreq in HUBS:
        urls.append(_entry(f"{SITE}{path_}", "", changefreq, priority))

    body = "\n".join(urls)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"\n'
            '        xmlns:xhtml="http://www.w3.org/1999/xhtml"\n'
            '        xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">\n'
            f"{body}\n</urlset>")


@router.get("/sitemap.xml")
def sitemap():
    return Response(_build(), media_type="application/xml",
                    headers={"Cache-Control": "public, max-age=3600"})
