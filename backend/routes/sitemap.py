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
# A नक्शा page's ImageObject — the full district map, which is the asset that
# has to reach Google Images, not the social card in og:image.
_MAP_IMAGE_RE = re.compile(r'"contentUrl"\s*:\s*"([^"]+district-map\.png)"')

# hreflang code → the value Google expects
_HREFLANG = {"hi": "hi", "en": "en-IN", "kn": "kn"}

# (file, url path, priority, changefreq, languages, images)
#
# languages: () none · ("hi",) Hindi-only, no ?lang= query · more than one →
# the page has a real language switcher, so each variant gets its own ?lang= URL.
CORE = [
    ("index.html",          "/",                1.0, "daily",  ("hi",),
     ("/assets/hero-section-photo.webp",)),
    ("meri_fasal.html",     "/meri_fasal",      0.9, "weekly", ("hi",), ()),
    ("shop.html",           "/shop",            0.9, "daily",  ("hi", "en", "kn"),
     ("/images/shop-hero.webp",)),
    ("krashi_bajar.html",   "/krashi_bajar",    0.9, "daily",  ("hi", "en", "kn"), ()),
    ("chat.html",           "/chat",            0.9, "daily",  ("hi", "en", "kn"), ()),
    ("weather.html",        "/weather",         0.8, "daily",  ("hi", "en", "kn"), ()),
    ("sarkari_yojana.html", "/sarkari_yojana",  0.8, "weekly", ("hi", "en", "kn"), ()),
    ("khoj.html",           "/khoj",            0.7, "weekly", ("hi", "en", "kn"), ()),
    # /map and the rest of the नक्शा cluster are not listed here: they are
    # server-rendered from backend/data/naksha_states.json and emitted by
    # _naksha_entries() below, so the manifest stays the single list.
    # Supply-side acquisition for the खरीदार directory. Hindi-only: the audience
    # is Indian traders and डीलर, and there is no ?lang= switcher on the page.
    ("dukanlisting/index.html", "/dukanlisting", 0.7, "monthly", ("hi",), ()),
    ("help.html",           "/help",            0.6, "weekly", ("hi",), ()),
    ("about.html",          "/about",           0.4, "yearly", (), ()),
    ("privacy-policy.html", "/privacy-policy",  0.3, "yearly", (), ()),
    ("terms.html",          "/terms",           0.3, "yearly", (), ()),
    # login.html is deliberately absent — the page is noindex.
    ("articles/index.html", "/articles/",       0.9, "daily",  ("hi", "en", "kn"), ()),
    # International Hub & Dedicated Country Portals
    ("international/index.html", "/international", 0.9, "weekly", (), ()),
    ("international/us.html",    "/us",            0.8, "weekly", (), ()),
    ("international/uk.html",    "/uk",            0.8, "weekly", (), ()),
    ("international/np.html",    "/np",            0.8, "weekly", (), ()),
    ("international/bd.html",    "/bd",            0.8, "weekly", (), ()),
    ("international/id.html",    "/id",            0.8, "weekly", (), ()),
    ("international/ng.html",    "/ng",            0.8, "weekly", (), ()),
    ("international/lk.html",    "/lk",            0.8, "weekly", (), ()),
]

# Hubs only. The full lists live in /bhav/sitemap.xml, /product/sitemap.xml,
# /sawal/sitemap.xml and /ganna/sitemap.xml.
# /ganna is "yearly" on purpose: cane price is announced once a season, so
# claiming anything faster is the same false-freshness signal /bhav's own
# sitemap comment warns about.
# /rental is "monthly" for the same honesty reason /ganna is "yearly": the
# rate ranges are reviewed editorially, not fed from anywhere, so claiming a
# faster cadence would be the false-freshness signal /bhav's sitemap warns of.
# /farm/poultry is "daily" and that is the honest cadence, not an optimistic
# one: NECC publishes a new egg rate every morning and the fetch stores it, so
# the page genuinely changes daily. Its ~34 zone URLs are NOT listed here —
# they live in /farm/poultry/sitemap.xml with their own real lastmod.
# /donate is not a hub, but it is server-rendered (routes/donate.py) so it has
# no file in CORE to take a date from. "yearly" is the honest cadence: the
# page changes only when the copy does.
HUBS = [("/bhav", 0.9, "daily"), ("/product/", 0.8, "weekly"),
        ("/sawal", 0.7, "monthly"), ("/ganna", 0.8, "yearly"),
        ("/rental", 0.7, "monthly"), ("/donate", 0.3, "yearly"),
        ("/farm", 0.7, "weekly"), ("/farm/poultry", 0.9, "daily")]

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
    # Absolutised here, not at every call site. The sitemap protocol requires a
    # fully-qualified <loc>, and callers that passed a site-relative path (the
    # whole नक्शा cluster did — _url()/_jile_url() return hrefs, which is what
    # they are for) were emitting entries Google discards silently.
    loc = _abs(loc)
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


def _naksha_entries() -> list:
    """The नक्शा hub, every state's map page, its district list, and every
    district's own map page.

    District pages (~780) go in unconditionally — they are server-rendered from
    the same manifest, so every one of them exists the moment the state does.
    गांव pages do NOT: those are listed in /naksha/gaon-sitemap.xml, and only
    for districts whose village data has actually been fetched (see
    _gaon_entries) — a sitemap entry for a page we serve as noindex is a
    contradiction, and the same rule already governs 1–2 district UTs below.

    Imported lazily: naksha.py imports bhav.py for the shared page shell, and
    bhav.py is heavy (DB index) — this module must stay importable on its own.
    """
    from backend.routes.naksha import (
        _d_url, _jile_url, _states, _updated, _url, slugify)

    states = _states()
    when = _updated()
    out = [_entry(f"{SITE}/naksha", when, "weekly", 0.8, ("hi", "en"))]
    for key, s in states.items():
        img = f"{SITE}/images/{s['prefix']}-district-map.png"
        # _url() already knows UP lives at /map.
        out.append(_entry(_url(key), when, "weekly", 0.7, ("hi", "en"), (img,)))
        # A 1–2 district UT's list page is noindex (see naksha.py) — a sitemap
        # entry for a page we ask Google not to index is a contradiction.
        if s["n"] >= 3:
            out.append(_entry(_jile_url(key), when, "weekly", 0.6, ("hi", "en")))
        for d in s["districts"]:
            out.append(_entry(_d_url(key, slugify(d["en"])), when, "monthly", 0.6))
    return out


def _gaon_entries() -> list:
    """Village directory + village pages, for districts that have real data.

    Kept out of sitemap.xml and given their own file: this list grows with
    traffic (each district is fetched on first view), it is by far the biggest
    tier, and mixing a slow-growing 40k-URL set into the 14k-URL main sitemap
    makes the main one's lastmod churn for no reason.
    """
    from backend.routes.naksha import _gaon_url, _states, _updated, _v_url
    from backend.services import village_service

    states = _states()
    when = _updated()
    out = []
    for key, dslug in village_service.cached_districts():
        if key not in states:
            continue
        villages = village_service.load(key, dslug) or []
        if not villages:
            continue
        out.append(_entry(_gaon_url(key, dslug), when, "monthly", 0.5))
        for v in villages:
            out.append(_entry(_v_url(key, dslug, v["slug"]), when, "monthly", 0.4))
    return out


def _build() -> str:
    urls = []

    for fname, path_, priority, changefreq, langs, images in CORE:
        f = _FRONTEND / fname
        urls.append(_entry(f"{SITE}{path_}", _page_date(f), changefreq, priority,
                           langs, images))

    # The नक्शा cluster. These are server-rendered (routes/naksha.py) from
    # backend/data/naksha_states.json, so there are no files to glob — the
    # manifest is the list, and a state added to it appears here on its own.
    # /map is in CORE above: it is UP's page under its original URL.
    urls.extend(_naksha_entries())

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


def build_gaon_sitemap() -> str:
    """Serialized village sitemap. The *route* lives in naksha.py, which is
    included before this module — /naksha/{state} would otherwise match
    /naksha/gaon-sitemap.xml and serve it the "state not found" page. The
    builder stays here with its siblings so all sitemap shapes are one file."""
    body = "\n".join(_gaon_entries())
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{body}\n</urlset>")
