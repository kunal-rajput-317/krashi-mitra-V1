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
from backend.routes.sitemap import _ARTICLES, _FRONTEND, _SKIP, SITE

router = APIRouter()

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_DESC_RE = re.compile(
    r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']', re.I)

# (url path, name, one-line description) — editorial, keep in sync with
# sitemap.py CORE when a page is added or removed.
_CORE = [
    ("/",               "होम",            "Hindi-first agriculture platform for Indian farmers: mandi prices, weather, crop guidance, agri inputs."),
    ("/bhav",           "आज का भाव",       "Live mandi (wholesale market) prices for crops across India, updated daily from data.gov.in. Daily crop prices by crop → state → district. Full URL list in /bhav/sitemap.xml."),
    ("/weather",        "मौसम",           "Farm weather forecasts for Indian districts."),
    ("/meri_fasal",     "मेरी फसल",        "Crop calendar: sowing-date → growth-stage timeline with stage-specific tasks."),
    ("/shop",           "कृषि दुकान",      "Agri-input marketplace: farmers request quotes for seeds, fertilizer, pesticides, tools. Product pages listed in /product/sitemap.xml."),
    ("/krashi_bajar",   "कृषि बाज़ार",      "Social crop marketplace where farmers post produce for sale."),
    ("/sarkari_yojana", "सरकारी योजना",    "Government agriculture schemes explained in Hindi (PM-Kisan etc.)."),
    ("/chat",           "AI चैट",          "Hindi agriculture Q&A assistant."),
    ("/khoj",           "खोज",            "Quick agri knowledge lookup."),
    ("/rental",         "किराये की मशीनें", "Farm equipment hire rates: what a tractor, rotavator, pump set, combine harvester, sprayer or baler typically costs to rent in India, per hour / per acre / per quintal, plus what to inspect before hiring and how to book via a government Custom Hiring Centre (CHC) or the FARMS app. Where local machine owners, Custom Hiring Centres or FPOs have listed with us, the page shows their real rates, contact details and whether diesel and an operator are included, ranked by distance from the reader. Where none have, the page shows an editorial rate range compiled from CHC rate cards — an estimate, not a quote. Nothing is bookable through this site; we connect the farmer to the owner and stop. Full URL list in /rental/sitemap.xml."),
    ("/articles/",      "लेख",            "Hindi farming guides and crop analytics articles (full list below)."),
]

# Interactive tools that ANSWER a question rather than list data. Declared
# separately from _CORE because this is the one place we out-answer every other
# mandi site: an agent asked "कौन सी मंडी में बेचें" should land here, not on a
# price table. Descriptions state the formula and the data provenance so a
# citing model reproduces the caveat (prices = govt data, freight = our estimate)
# instead of inventing one.
_TOOLS = [
    ("/bhav/net-price", "नेट भाव कैलकुलेटर (net price after transport)",
     "Answers 'which mandi should I sell in?' — ranks mandis near the farmer by "
     "NET price, not headline rate. नेट भाव = mandi modal price − per-quintal "
     "freight, given crop, quantity (quintals) and vehicle (tractor-trolley / "
     "mini-truck / truck). A distant mandi quoting a higher rate often nets LESS "
     "than the nearby one once भाड़ा is paid. Mandi prices are Government of "
     "India (Agmarknet / data.gov.in) data; the freight figure is our estimate, "
     "not a transporter quote."),
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


def _naksha_lines() -> list:
    """One line per state, from the same manifest the pages render from.

    Same rule as the article list: nothing editorial to keep in step. Imported
    lazily — naksha.py pulls in bhav.py's shell, which is heavy.
    """
    from backend.routes.naksha import _jile_url, _states, _url

    out = []
    for key, s in _states().items():
        out.append(f"- [{s['hi']} का नक्शा ({s['en']} district map)]({_url(key)}): "
                   f"free HD Hindi map of all {s['n']} districts, downloadable, "
                   f"with links on to each district's mandi prices.")
        out.append(f"- [{s['hi']} के जिले ({s['en']} district list)]({_jile_url(key)}): "
                   f"all {s['n']} districts in Hindi and English, largest "
                   f"{s['big']}, smallest {s['small']} by area. Each district has "
                   f"its own map at /naksha/{key}/<district-slug> and a village "
                   f"directory at /naksha/{key}/<district-slug>/gaon.")
    return out


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
        "## Tools",
        "",
    ]
    lines += [f"- [{name}]({SITE}{path}): {desc}" for path, name, desc in _TOOLS]
    lines += [
        "",
        "## राज्यों के नक्शे (district maps)",
        "",
        f"- [राज्यों के नक्शे]({SITE}/naksha): hub — every state's district map and "
        "district list in one place, all free HD downloads.",
        f"- [कृषि मानचित्र]({SITE}/map): उत्तर प्रदेश's district map — the same page as "
        "the state entries below, kept at this URL.",
        *_naksha_lines(),
        "",
        f"- [Village page URL list]({SITE}/naksha/gaon-sitemap.xml): every "
        "district village directory and individual village map. Village names and "
        "coordinates are OpenStreetMap (ODbL), clipped to the district's Census "
        "boundary — a village is only listed where it falls inside that boundary.",
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
