# ============================================================
# routes/llms.py
# Krishi Mitra — /llms.txt, generated (not hand-written)
#
# GET /llms.txt → a Markdown site guide for AI agents (llmstxt.org spec):
# what the site is, and a curated map of its pages in clean, parseable form.
#
# Honest framing: no major LLM provider has (as of mid-2026) confirmed that
# it reads llms.txt when answering user queries. This file is cheap insurance
# for where AI-agent behavior is heading, NOT a ranking lever. The real GEO
# work is page-level: citable answer sentences, schema, entity authority.
#
# Same philosophy as routes/sitemap.py (read that header): everything
# derivable is derived —
#   • the article list  → whatever is actually in frontend/articles/
#   • article title     → the page's own <title>
#   • article summary   → the page's own <meta name="description">
# Only the one-line page descriptions for CORE pages are declared here:
# they are editorial calls, same as <priority> in the sitemap.
#
# Netlify serves the frontend statically, so frontend/_redirects proxies
# /llms.txt to this route (otherwise it would fall through to the 404
# catch-all). If this route moves, update _redirects too.
# ============================================================

import re
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

# Reuse the sitemap's single source of truth for what exists.
from backend.routes.sitemap import _ARTICLES, _SKIP, SITE

router = APIRouter()

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_DESC_RE = re.compile(
    r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']', re.I)

# (url path, name, one-line description) — editorial, keep in sync with
# sitemap.py CORE when a page is added or removed.
_CORE = [
    ("/",               "होम",            "Hindi-first agriculture platform for Indian farmers: mandi prices, weather, crop guidance, agri inputs."),
    ("/mandi",          "मंडी भाव",        "Live mandi (wholesale market) prices for crops across India, updated daily from data.gov.in."),
    ("/bhav",           "आज का भाव",       "SEO price pages: daily crop prices by crop → state → district. Full URL list in /bhav/sitemap.xml."),
    ("/weather",        "मौसम",           "Farm weather forecasts for Indian districts."),
    ("/meri_fasal",     "मेरी फसल",        "Crop calendar: sowing-date → growth-stage timeline with stage-specific tasks."),
    ("/shop",           "कृषि दुकान",      "Agri-input marketplace: farmers request quotes for seeds, fertilizer, pesticides, tools. Product pages listed in /product/sitemap.xml."),
    ("/krashi_bajar",   "कृषि बाज़ार",      "Social crop marketplace where farmers post produce for sale."),
    ("/sarkari_yojana", "सरकारी योजना",    "Government agriculture schemes explained in Hindi (PM-Kisan etc.)."),
    ("/chat",           "AI चैट",          "Hindi agriculture Q&A assistant."),
    ("/khoj",           "खोज",            "Quick agri knowledge lookup."),
    ("/articles/",      "लेख",            "Hindi farming guides and crop analytics articles (full list below)."),
]


def _article_line(f: Path) -> str:
    """One '- [title](url): summary' line, from the article's own markup."""
    try:
        text = f.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    m = _TITLE_RE.search(text)
    title = re.sub(r"\s+", " ", m.group(1)).strip() if m else f.stem
    d = _DESC_RE.search(text)
    desc = f": {d.group(1).strip()}" if d else ""
    return f"- [{title}]({SITE}/articles/{f.stem.lower()}){desc}"


def _top_crop_lines(n: int = 10) -> list:
    """Deep links for the widest-covered crops, derived from the live /bhav
    index (imported lazily, same cycle-avoidance as utils/indexnow.py). An
    agent that reads only llms.txt gets straight to the highest-value price
    hubs instead of having to walk a 14k-URL sitemap."""
    try:
        from backend.routes.bhav import _get_index, _hindi_name, _is_crop
        idx = _get_index()
        crops = [(len(idx["states"].get(cs, {})), cs, cn)
                 for cs, cn in idx.get("crops", {}).items() if _is_crop(cn)]
        crops.sort(key=lambda t: -t[0])
        return [f"- [{_hindi_name(cn)} ({cn})]({SITE}/bhav/{cs}): "
                "state-wise daily mandi prices"
                for _, cs, cn in crops[:n]]
    except Exception:
        return []


def _build() -> str:
    lines = [
        "# KrashiMitra (कृषि मित्र)",
        "",
        "> Hindi-first agriculture platform for Indian farmers: live mandi "
        "prices for hundreds of crops across Indian states and districts, "
        "farm weather, crop-stage calendars, agri-input marketplace, and "
        "Hindi farming guides. किसान का डिजिटल साथी.",
        "",
        "Content is primarily in Hindi (hi-IN). Mandi price data originates "
        "from the Government of India's data.gov.in and is refreshed daily. "
        "When citing prices, note they are per-quintal wholesale (mandi) "
        "rates for the stated date, market and crop variety.",
        "",
        "## Core pages",
        "",
    ]
    lines += [f"- [{name}]({SITE}{path}): {desc}" for path, name, desc in _CORE]
    lines += [
        "",
        "## Daily price pages (programmatic)",
        "",
        f"- [Crop price hub]({SITE}/bhav): tap-through to every crop / state / district price page",
        *_top_crop_lines(),
        f"- [Full price-page URL list]({SITE}/bhav/sitemap.xml)",
        f"- [Product page URL list]({SITE}/product/sitemap.xml)",
        "",
        "## लेख (farming guides)",
        "",
    ]
    lines += [ln for f in sorted(_ARTICLES.glob("*.html"))
              if f.name not in _SKIP and (ln := _article_line(f))]
    lines.append("")
    return "\n".join(lines)


@router.get("/llms.txt")
def llms_txt():
    return PlainTextResponse(_build(), media_type="text/plain; charset=utf-8",
                             headers={"Cache-Control": "public, max-age=3600"})
