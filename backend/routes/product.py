# ============================================================
# routes/product.py
# Krishi Mitra — SEO shop-product pages ("beej/khad/pesticide kharidein")
#
# Server-rendered, indexable pages at /product/{slug} for the shop
# catalog — same pattern as routes/bhav.py's mandi price pages, and now
# the same look: the page shell (CSS tokens, sticky header, footer, FAQ/
# breadcrumb JSON-LD) is imported straight from bhav.py rather than
# duplicated, so the two SEO surfaces stay visually identical for free.
# Reached via the Netlify proxy rule /product/* → backend (same
# 200-rewrite as /bhav, /share), so the public URL stays
# https://krashimitra.in/product/<slug> while FastAPI renders it.
#
# Single source of truth: the `const PRODUCTS = [ ... ]` array inside
# frontend/shop.html — we parse it straight from that file (no snapshot,
# no build step, no manual re-run). Edit PRODUCTS in shop.html and these
# pages follow automatically: the parse is cached and re-run whenever
# shop.html's mtime changes, so a live edit shows up without a restart.
#
# Also serves /product/sitemap.xml and a /product/ hub page.
#
# THE PRICE HERE IS INDICATIVE, AND THE PAGE HAS TO SAY SO. PRODUCTS carries a
# rupee figure per item, and this page used to present it as OUR sale price:
# Offer JSON-LD with availability InStock and seller KrashiMitra, a "% छूट"
# computed against an MRP nobody verified, a ⭐ rating nobody gave, and a
# promise of free delivery over ₹500 with Cash on Delivery.
#
# None of that is what the business does. An order placed from the shop becomes
# an ENQUIRY that a dealer later quotes against — `orders` carries quote_total,
# dealer_name, quote_note and quoted_at for exactly that reason — and of the 28
# orders placed to date, 8 came back "Not Available". So "InStock", "seller:
# KrashiMitra" and a firm ₹850 were claims the business never made, on the
# site's best-converting family. Under the Consumer Protection Act 2019 a
# stated price, a discount against an unverified MRP, an invented rating and a
# delivery promise are each a representation we would have to stand behind.
#
# The truthful version is the one krashi_dukan.py and rental.py already
# settled on: WE CONNECT, WE DO NOT SELL. The number stays — a farmer searching
# "कपिला पशु आहार की कीमत" wants a number, and reporting a typical market price
# is what /bhav does all day — but it is labelled as indicative, it carries no
# Offer markup, and the disclaimer rides on the page rather than sitting in
# Terms. tests/test_product_price_claims.py fails the build if any of that
# comes back.
#
# Offer JSON-LD RETURNS ONLY WITH A REAL SELLER. Same rule as rental.py: an
# Offer needs a seller and a price someone will honour. When dukan_items carries
# a shop's own price for a product, that shop is the seller and an AggregateOffer
# is honest — krashi_dukan.py already does this. An indicative catalogue figure
# is neither, so it gets no offers block.
# ============================================================

import re
from html import escape
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, Response

from backend.routes.bhav import (
    _CSS as _BASE_CSS, _FONTS, _ICON, _ANALYTICS, _header, _footer, _doc, _faq,
    _crumb_ld, _fit, _ld,
)

router = APIRouter()

SITE = "https://krashimitra.in"
_SHOP_HTML = Path(__file__).resolve().parents[2] / "frontend" / "shop.html"

# The disclaimer, in one place, on every page that prints a rupee figure —
# because "we are only the connector" is worth nothing to a farmer who never
# read it. Same stance and the same strip krashi_dukan.py and rental.py use;
# this module owns the text because both of those already import from here,
# and the reverse import would be circular.
DISCLAIMER = ("कृषि मित्र सामान नहीं बेचता — हम सिर्फ़ जोड़ने का काम करते हैं। "
              "यहाँ दी कीमत अनुमानित बाज़ार भाव है, किसी दुकान का पक्का रेट नहीं — "
              "असली दाम दुकान, कंपनी, पैक और इलाके से बदलता है। "
              "ऑर्डर करने पर दुकानदार अपना रेट बताता है। खरीदने से पहले "
              "पैक, वज़न और एक्सपायरी ज़रूर जाँच लें।")

# The material-connection disclosure for the Amazon/Flipkart buttons. rel=
# "sponsored" tells Google; this tells the farmer, which is the half the CCPA's
# endorsement guidelines actually ask for.
AFFILIATE_NOTE = ("Amazon और Flipkart के लिंक एफ़िलिएट लिंक हैं — "
                  "उनसे खरीदने पर कृषि मित्र को कमीशन मिल सकता है। "
                  "आपको कोई अतिरिक्त शुल्क नहीं लगता।")

CAT_LABELS = {
    "seeds": "🌱 बीज", "fertilizer": "🧪 खाद", "pesticide": "🌿 कीटनाशक",
    "tools": "🔧 उपकरण", "pashu_aahaar": "🐄 पशु आहार", "sprayers": "🔵 स्प्रेयर",
    "irrigation": "💧 सिंचाई", "soil": "🧪 मिट्टी / ग्रोथ",
    "protection": "🛡️ फसल सुरक्षा", "structures": "🏗️ नेट व संरचनाएं",
    "machinery": "⚙️ मशीनरी", "misc": "📦 अन्य",
}

def _bare_name(name: str) -> str:
    """'SSP (सिंगल सुपर फॉस्फेट)' → 'SSP'. The bracket holds the expansion of
    the name in front of it, so dropping it never loses the searched term —
    and for the long ones it is the only way the title fits at all."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", name).strip() or name


# PRODUCTS entries are flat object literals — scalar string/number values
# only (verified: no braces, apostrophes or newlines inside any value), so
# a per-field regex over each `{...}` block parses them reliably.
_STR_FIELDS = ("cat", "emoji", "badge", "badgeClass", "img",
               "name_hi", "name_en", "name_kn",
               "desc_hi", "desc_en", "desc_kn",
               "unit_hi", "unit_en", "unit_kn",
               "rating", "affil_amazon", "affil_flipkart")
_NUM_FIELDS = ("id", "price", "mrp")


def _slugify(name_en: str) -> str:
    """Must stay identical to getProductSlug() in shop.html so the
    client's share links resolve to the page we render here."""
    s = re.sub(r"[()%]", "", name_en.lower())
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def _parse_shop_html(text: str) -> list[dict]:
    start = text.index("const PRODUCTS = [")
    end = text.index("\n  ];", start)
    # Strip only full-line `// ── section ──` comments — anchored to line
    # start so it never touches the `//` inside an https:// value.
    block = re.sub(r"(?m)^[ \t]*//.*$", "", text[start:end])

    products, seen = [], set()
    for obj in re.findall(r"\{([^{}]+)\}", block):
        p = {}
        for f in _STR_FIELDS:
            m = re.search(rf"\b{f}:\s*'([^']*)'", obj)
            if m:
                p[f] = m.group(1)
        for f in _NUM_FIELDS:
            m = re.search(rf"\b{f}:\s*(\d+)", obj)
            if m:
                p[f] = int(m.group(1))
        if "id" not in p or not p.get("name_en"):
            continue
        slug = _slugify(p["name_en"])
        if slug in seen:               # first wins (name_en values are unique)
            continue
        seen.add(slug)
        p["slug"] = slug
        products.append(p)
    return products


# Parsed catalog, refreshed when shop.html changes (mtime check per access) —
# same "cache with cheap invalidation" idea as bhav.py's slug map.
_cache: dict = {"mtime": 0.0, "products": [], "by_slug": {}}


def _get_products() -> list[dict]:
    try:
        mtime = _SHOP_HTML.stat().st_mtime
    except OSError:
        return _cache["products"]
    if mtime != _cache["mtime"]:
        try:
            parsed = _parse_shop_html(_SHOP_HTML.read_text(encoding="utf-8"))
        except Exception:
            return _cache["products"]         # keep last good on a bad edit
        if parsed:                            # never clobber good cache with empty
            _cache.update(mtime=mtime, products=parsed,
                          by_slug={p["slug"]: p for p in parsed})
    return _cache["products"]


def _get_by_slug() -> dict:
    _get_products()
    return _cache["by_slug"]


def _available(url: str) -> bool:
    return bool(url) and not url.startswith("not_available_")


# There is deliberately no _off_pct() here any more. A "% off" needs an MRP
# somebody stands behind, and PRODUCTS' mrp is an editorial figure — so the
# discount computed from it was a claim about a saving no farmer could hold us
# to. services/dealer_products.py::off_pct() keeps the pill for the one case
# where it is honest: a real dealer quoting his own price against the MRP on
# the sack he is selling.


# badge/badgeClass are already parsed off PRODUCTS but the old page never
# surfaced them — mirrors the 🔥/🌿/🆕 prefix shop.html itself uses on cards.
_BADGE = {"organic": ("🌿", "ऑर्गेनिक"), "new-badge": ("🆕", "नया")}


def _badge_pill(p: dict, cls: str = "prod-badge") -> str:
    bc = p.get("badgeClass") or ""
    if bc in _BADGE:
        e, label = _BADGE[bc]
    elif p.get("badge") == "bestseller":
        e, label = "🔥", "बेस्टसेलर"
    else:
        return ""
    return f'<span class="{cls}">{e} {label}</span>'


def _product_chip(p: dict) -> str:
    return (f'<a class="chip" href="/product/{p["slug"]}">'
            f'<img src="{escape(p["img"])}" alt="" loading="lazy">{escape(p["name_hi"])}</a>')


# Extra rules layered on top of bhav.py's shared tokens/header/footer/hero/answer/
# chip/FAQ styles, so this file only carries what's genuinely product-specific:
# the catalog grid, the affiliate CTA colours and the product photo frame.
#
# Passed separately as `extra_css` to _doc() rather than folded into a local
# `_CSS` — _doc() is defined in bhav.py and its `<style>{_CSS}</style>` closes
# over bhav.py's OWN module-level _CSS, not this file's, so a same-named local
# override here would silently never render.
_EXTRA_CSS = """
.desc{font-size:14px;color:var(--text-mid);margin:16px 0}

/* ── "we connect, we do not sell" ── the same amber strip /krashi_dukan and
   /rental carry, so the three sections make one claim in one voice ── */
.prod-disclaimer{background:#fff8e6;border:1px solid #f0dca8;border-radius:var(--radius-md);
padding:12px 15px;font-size:12.5px;color:#6b5312;line-height:1.6;margin:16px 0 0}
.prod-disclaimer b{color:#4a3908}
.prod-affil-note{font-size:11.5px;color:var(--text-soft);line-height:1.6;margin:10px 0 0}
/* The price is a market estimate, and the label sits ON the number rather than
   in a footnote under it. */
.prod-est{font-size:11px;font-weight:700;color:var(--text-soft);background:var(--cream);
border-radius:10px;padding:3px 10px;white-space:nowrap;align-self:center}

.prod-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:14px;margin-top:14px}
.prod-card{background:var(--white);border:1px solid var(--border);border-radius:var(--radius-md);
overflow:hidden;box-shadow:var(--shadow-sm);text-decoration:none;color:inherit;display:block;
transition:transform .15s,box-shadow .15s,border-color .15s}
.prod-card:hover{transform:translateY(-2px);box-shadow:var(--shadow-md);border-color:var(--green-light)}
.prod-card-photo{position:relative;height:118px;background:var(--cream);
display:flex;align-items:center;justify-content:center;padding:10px}
.prod-card-photo img{max-height:100px;max-width:88%;object-fit:contain}
.prod-card-body{padding:11px 13px 13px}
.prod-card-name{font-size:13.5px;font-weight:700;color:var(--text-dark);line-height:1.3}
.prod-card-en{display:block;font-size:10.5px;font-weight:600;color:var(--text-soft);margin-top:1px}
.prod-card-price{display:flex;align-items:baseline;gap:6px;flex-wrap:wrap;margin-top:8px}
.prod-card-price b{font-size:16px;font-weight:700;color:var(--green-dark)}
.prod-card-price .est{font-size:10.5px;font-weight:600;color:var(--text-soft)}
.prod-card-unit{font-size:11px;color:var(--text-soft);margin-top:2px}

.prod-badge-card{position:absolute;top:8px;left:8px;background:var(--amber);color:#fff;
font-size:10px;font-weight:700;padding:3px 8px;border-radius:10px;box-shadow:0 1px 4px rgba(0,0,0,.15)}
.prod-badge{display:inline-flex;align-items:center;gap:4px;background:rgba(255,255,255,.16);
border:1px solid rgba(255,255,255,.28);color:#fff;font-size:11px;font-weight:700;
padding:4px 10px;border-radius:20px;margin-bottom:7px}

.chip.cat{padding:7px 16px}

/* Photo panel stretches to match the info column's height (flex default
align-items:stretch) so the image fills the whole left side of the card
instead of floating as a small icon above text that runs on below it. */
.answer-prod-split{display:flex;gap:26px}
.answer-prod-photo-lg{width:280px;flex-shrink:0;border-radius:16px;background:#fff;
overflow:hidden;box-shadow:0 4px 14px rgba(0,0,0,.18)}
.answer-prod-photo-lg img{display:block;width:100%;height:100%;object-fit:cover}
.answer-prod-info{flex:1;min-width:0}
/* Mobile: details must stay to the right of the photo, not stack below it —
so instead of switching to a column, the photo panel just shrinks to a small
square. `cover` would crop hard into that shape for portrait product photos
(bag/bottle labels get cut off), so it also switches to contain + padding:
the whole photo stays visible, letterboxed rather than cropped. */
@media(max-width:560px){
.answer-prod-photo-lg{width:104px;height:104px;padding:8px}
.answer-prod-photo-lg img{object-fit:contain}
.answer-prod-split{gap:14px}
/* product-grid cards: list rows — image left (small, fixed), details right —
instead of stacked cards, matching the app's own product-list layout. */
.prod-grid{grid-template-columns:1fr}
.prod-card{display:flex;align-items:stretch}
.prod-card-photo{width:96px;height:auto;flex-shrink:0;padding:8px}
.prod-card-photo img{max-height:100%;max-width:100%}
.prod-card-body{flex:1;min-width:0}
}

.btn-amazon{background:#ff9900;color:#111}
.btn-amazon:hover{background:#e68a00}
.btn-flipkart{background:#2874f0;color:#fff}
.btn-flipkart:hover{background:#1f5fc9}

/* product photo — click to zoom into a full-screen lightbox */
.answer-prod-photo-lg{position:relative}
.answer-prod-photo-lg img{cursor:zoom-in}
.photo-zoom-hint{position:absolute;right:10px;bottom:10px;width:30px;height:30px;border-radius:50%;
background:rgba(26,60,46,.75);color:#fff;display:flex;align-items:center;justify-content:center;
font-size:14px;pointer-events:none}
.km-lightbox{display:none;position:fixed;inset:0;background:rgba(10,15,12,.92);z-index:5000;
align-items:center;justify-content:center;padding:24px;cursor:zoom-out}
.km-lightbox.open{display:flex}
.km-lightbox img{max-width:92vw;max-height:92vh;object-fit:contain;border-radius:8px;box-shadow:0 8px 40px rgba(0,0,0,.5)}
.km-lightbox-close{position:absolute;top:18px;right:18px;width:38px;height:38px;border-radius:50%;
background:rgba(255,255,255,.15);border:none;color:#fff;font-size:18px;cursor:pointer}
"""

# Only _not_found() below needs the combined sheet — it builds its own <head>
# by hand instead of going through bhav.py's _doc().
_CSS = _BASE_CSS + _EXTRA_CSS


def _hub_card(p: dict) -> str:
    """One catalogue tile — on the /product/ hub and in the related strip.

    The struck-through MRP and the "% off" pill are gone for the same reason
    they are gone from the product page itself: the MRP is unverified, so the
    discount computed against it is a claim we cannot stand behind, and a card
    is exactly where a farmer reads one without reading anything else. The
    price stays and is labelled ~ for approximate, which is what it is."""
    return f"""<a class="prod-card" href="/product/{p['slug']}">
<div class="prod-card-photo">{_badge_pill(p, "prod-badge-card")}
<img src="{escape(p['img'])}" alt="{escape(p['name_hi'])}" loading="lazy" width="120" height="100"></div>
<div class="prod-card-body">
<div class="prod-card-name">{escape(p['name_hi'])}</div>
<span class="prod-card-en">{escape(p['name_en'])}</span>
<div class="prod-card-price"><b>~₹{p['price']}</b><span class="est">अनुमानित</span></div>
<div class="prod-card-unit">{escape(p['unit_hi'])}</div>
</div>
</a>"""


@router.get("/product/sitemap.xml")
def product_sitemap():
    urls = "\n".join(
        f"  <url><loc>{SITE}/product/{p['slug']}</loc>"
        f"<changefreq>weekly</changefreq></url>"
        for p in _get_products())
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
           f'{urls}\n</urlset>')
    return Response(content=xml, media_type="application/xml",
                     headers={"Cache-Control": "public, max-age=3600"})


@router.get("/product/", response_class=HTMLResponse)
@router.get("/product", response_class=HTMLResponse)
def product_hub():
    """Crawlable hub: every product grouped by category, in the /bhav look."""
    products = _get_products()
    by_cat: dict[str, list] = {}
    for p in products:
        by_cat.setdefault(p["cat"], []).append(p)

    jump_chips, sections = [], []
    for cat, label in CAT_LABELS.items():
        rows = by_cat.get(cat) or []
        if not rows:
            continue
        jump_chips.append(f'<a class="hub-filter-btn" href="#cat-{cat}">{escape(label)}</a>')
        cards = "".join(_hub_card(p) for p in rows)
        sections.append(
            f'<h2 id="cat-{cat}">{escape(label)} ({len(rows)})</h2>'
            f'<div class="prod-grid">{cards}</div>')

    # The hub advertised Cash on Delivery and free delivery over ₹500 in its
    # title, its description and its hero — three places Google reads, for a
    # service this site does not run. Replaced with what the catalogue is: the
    # going rate on farm inputs, and a dealer who quotes the real one.
    title = "बीज, खाद, कीटनाशक व उपकरण के भाव — कृषि मित्र दुकान"
    desc = (f"कृषि मित्र दुकान के {len(products)} उत्पाद — बीज, खाद, कीटनाशक, उपकरण, पशु आहार व "
            f"सिंचाई सामान का अनुमानित बाज़ार भाव। रेट पूछें, दुकानदार अपना दाम बताएगा।")

    body = f"""<div class="hero nophoto">
<div class="hero-body">
<h1>कृषि मित्र दुकान — सभी उत्पाद</h1>
<p class="hero-sub">🛒 {len(products)} उत्पाद · अनुमानित बाज़ार भाव · रेट दुकानदार का</p>
</div>
</div>
<div class="cta-row">
<a class="btn btn-app" href="{SITE}/shop.html">🛒 पूरी दुकान ऐप में खोलें</a>
</div>
<div class="hub-filter-row">
<form class="hub-search" action="{SITE}/find" method="get" role="search">
<input type="text" name="q" placeholder="उत्पाद खोजें... (DAP, नीम तेल, स्प्रेयर)" autocomplete="off" aria-label="उत्पाद खोजें">
<button type="submit" aria-label="खोजें">🔍</button>
</form>
{"".join(jump_chips)}
</div>
{"".join(sections)}
<div class="prod-disclaimer"><b>ध्यान दें:</b> {escape(DISCLAIMER)}</div>"""

    return _doc(title, desc, f"{SITE}/product/",
                f'<a href="{SITE}/">कृषि मित्र</a> › उत्पाद', body,
                active="shop", extra_css=_EXTRA_CSS)


def _not_found() -> HTMLResponse:
    """A product can be retired from PRODUCTS while Google still holds the
    URL — send that farmer into the catalog instead of a dead end."""
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="hi">
<head>
{_ANALYTICS}
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>यह उत्पाद उपलब्ध नहीं है | कृषि मित्र</title>
<meta name="robots" content="noindex">
{_ICON}
{_FONTS}
<style>{_CSS}</style>
</head>
<body>
{_header("shop")}
<div class="wrap">
<div class="hero nophoto">
<div class="hero-body">
<h1>यह उत्पाद अभी उपलब्ध नहीं है</h1>
<p class="hero-sub">हो सकता है यह उत्पाद हटा दिया गया हो या लिंक पुराना हो।</p>
</div>
</div>
<div class="cta-row">
<a class="btn btn-app" href="{SITE}/product/">सभी उत्पाद देखें</a>
<a class="btn btn-wa" style="background:var(--green-dark)" href="{SITE}/shop.html">🛒 दुकान ऐप खोलें</a>
</div>
</div>
{_footer()}
</body>
</html>""", status_code=404)


@router.get("/product/{slug}", response_class=HTMLResponse)
def product_page(slug: str):
    p = _get_by_slug().get(slug.lower())
    if not p:
        return _not_found()

    cat_label = CAT_LABELS.get(p["cat"], p["cat"])
    canon = f"{SITE}/product/{p['slug']}"

    # Measured against production 2026-09-12: 89 of the 94 product titles ran
    # over Google's 68-char window (median 83) and 40 of 94 descriptions over
    # 162. The cause was a fixed f-string that printed the same product twice —
    # "SSP (सिंगल सुपर फॉस्फेट) (SSP (Single Super Phosphate)) खरीदें ₹460 |
    # कृषि मित्र दुकान", 86 chars — because name_hi and name_en are parallel
    # names, each already carrying its own expansion in brackets. /product is
    # the site's best-converting family (13.7k impressions at 1.30%), so a
    # title Google cuts at "खरीदें" is the most expensive truncation we ship.
    #
    # The ladder drops, in order: the pack size, the brand, the English
    # expansion, then the Hindi one. The bare acronym survives to the last
    # variant because "SSP"/"DAP"/"MOP" is what gets typed.
    hi_name, en_name = p["name_hi"], p["name_en"]
    hi_bare, en_bare = _bare_name(hi_name), _bare_name(en_name)
    rs = f"₹{p['price']}"
    # "SSP (सिंगल सुपर फॉस्फेट)" already opens with its own acronym, so the
    # short English form would print it a second time ("… (SSP) ₹460"). Where
    # the bare English name is already in the Hindi one, the bracket is dropped
    # and the space goes to the pack size instead.
    en_tag = "" if en_bare.lower() in hi_name.lower() else f" ({en_bare})"
    en_lead = hi_bare if en_bare.lower() in hi_bare.lower() else f"{hi_bare} ({en_bare})"
    title = _fit(
        f"{hi_name} ({en_name}) {rs} — {p['unit_hi']}",
        f"{hi_name} ({en_name}) की कीमत {rs}",
        f"{hi_name} {rs} — {en_name} Price Online",
        f"{hi_name}{en_tag} {rs} — {p['unit_hi']}",
        f"{hi_name} {rs} — {en_bare} Price {p['unit_hi']}",
        f"{hi_name} {rs} — {en_bare} Price Online",
        f"{en_lead} {rs} — {p['unit_hi']} की कीमत",
        f"{hi_bare} {rs} — {en_bare} Price Online",
        f"{hi_name} की कीमत {rs} — {p['unit_hi']}",
        f"{hi_bare} की कीमत {rs} — {p['unit_hi']}",
        f"{hi_bare} {rs} — {en_bare}",
        f"{hi_bare} की कीमत {rs}")
    # The description sold what we do not sell: "अभी ऑर्डर करें" plus free
    # delivery over ₹500 and Cash on Delivery, on every variant. What is true is
    # that the figure is a typical market price and that a dealer quotes the
    # real one — so that is what the snippet now says. It still leads with the
    # name, the pack and the number, which is what the query asked for.
    desc = _fit(
        f"{hi_name} ({p['unit_hi']}) का अनुमानित भाव {rs} — {p['desc_hi']} "
        f"असली रेट दुकान और इलाके से बदलता है।",
        f"{hi_name} ({p['unit_hi']}) का अनुमानित भाव {rs} — {p['desc_hi']} "
        f"रेट दुकान से बदलता है।",
        f"{hi_name} ({p['unit_hi']}) — अनुमानित {rs}। {p['desc_hi']} "
        f"असली रेट दुकान पर पक्का करें।",
        f"{hi_name} ({p['unit_hi']}) का अनुमानित भाव {rs} — {p['desc_hi']}",
        f"{hi_name} ({p['unit_hi']}) — अनुमानित {rs}। {p['desc_hi']}",
        f"{hi_name} ({en_bare}) {p['unit_hi']} की अनुमानित कीमत {rs} — "
        f"असली रेट दुकान, कंपनी और इलाके से बदलता है।",
        f"{hi_name} — {p['unit_hi']} का अनुमानित भाव {rs}। रेट दुकान से बदलता है।",
        f"{hi_name} — {p['unit_hi']} की अनुमानित कीमत {rs}।",
        limit=162)

    # ── CTAs ──
    # "ऐप में खरीदें" promised a purchase; the button opens an enquiry that a
    # dealer quotes against, so it now says what it does.
    ctas = [f'<a class="btn btn-app" href="{SITE}/shop.html?product={p["id"]}">🛒 रेट पूछें</a>']
    if _available(p.get("affil_amazon", "")):
        ctas.append(f'<a class="btn btn-amazon" target="_blank" rel="noopener sponsored" '
                    f'href="{escape(p["affil_amazon"])}">Amazon पर देखें</a>')
    if _available(p.get("affil_flipkart", "")):
        ctas.append(f'<a class="btn btn-flipkart" target="_blank" rel="noopener sponsored" '
                    f'href="{escape(p["affil_flipkart"])}">Flipkart पर देखें</a>')
    wa_text = quote(f"{p['name_hi']} — अनुमानित ₹{p['price']} ({p['unit_hi']})\n{canon}")
    ctas.append(f'<a class="btn btn-wa" target="_blank" href="https://wa.me/?text={wa_text}">📲 शेयर करें</a>')
    # The disclosure rides beside the buttons it is about, and only on pages
    # that actually carry one — a page with no affiliate link has nothing to
    # disclose, and printing it there would be noise that trains the reader to
    # skip the notice on the pages where it means something.
    affil_note = (f'<p class="prod-affil-note">{escape(AFFILIATE_NOTE)}</p>'
                  if _available(p.get("affil_amazon", ""))
                  or _available(p.get("affil_flipkart", "")) else "")

    # ── related products: same category, same rich card as the /product/ hub ──
    related = [r for r in _get_products() if r["cat"] == p["cat"] and r["slug"] != p["slug"]][:8]
    related_html = ""
    if related:
        cards = "".join(_hub_card(r) for r in related)
        related_html = f'<h2>{escape(cat_label)} में अन्य उत्पाद</h2><div class="prod-grid">{cards}</div>'

    # ── FAQ + JSON-LD from the one shared helper, same as /bhav ──
    #
    # The first answer used to state the price as a fact and claim a "% छूट"
    # against an MRP nobody verified; the second promised free delivery and
    # Cash on Delivery, which is the opposite of what the section says it does.
    # Both are now the true answer, which is also the more useful one: here is
    # the going rate, here is why yours will differ, here is who sets it.
    faqs = [
        (f"{p['name_hi']} ({p['name_en']}) की कीमत क्या है?",
         f"{p['name_hi']} ({p['unit_hi']}) का अनुमानित बाज़ार भाव ₹{p['price']} के आसपास है। "
         f"यह पक्का रेट नहीं है — दुकान, कंपनी, पैक साइज़ और इलाके के हिसाब से दाम बदलता है। "
         f"अपने नज़दीकी दुकानदार से आज का रेट पूछ लें।"),
        ("क्या कृषि मित्र यह सामान बेचता है?",
         "नहीं। कृषि मित्र सामान न बेचता है, न डिलीवरी करता है, न किसी सामान की गारंटी "
         "लेता है। हम सिर्फ़ किसान और दुकानदार को जोड़ते हैं — रेट पूछने पर दुकानदार "
         "अपना भाव बताता है, और सौदा आपका उसी से होता है।"),
    ]
    faq_html, faq_ld = _faq(faqs)

    # Product WITHOUT offers. An Offer needs a seller and a price someone will
    # honour; an indicative catalogue figure has neither, so marking one up as
    # an offer puts a false claim into structured data — the same rule
    # rental.py and krashi_dukan.py follow. `brand` went with it: declaring
    # "Kapila Cattle Feed" to be a KrashiMitra brand is someone else's
    # trademark on our name. A product whose brand we cannot state truthfully
    # simply does not carry the key.
    product_ld = {
        "@context": "https://schema.org", "@type": "Product",
        "name": f"{p['name_en']} — {p['name_hi']}",
        "description": p["desc_en"],
        "image": p["img"],
    }
    ld = _ld(product_ld, faq_ld, _crumb_ld([
        ("कृषि मित्र", f"{SITE}/"), ("उत्पाद", f"{SITE}/product/"), (p["name_hi"], canon)]))

    # The stat row used to print MRP and a ⭐ rating beside the price. The MRP
    # is unverified — which made the "% छूट" badge above it a discount claim
    # against a number we made up — and the rating was never collected from
    # anybody. Both are gone. What replaces them is true and more useful: the
    # pack the price refers to, and where the price comes from.
    body = f"""<section class="answer">
<div class="answer-prod-split">
<div class="answer-prod-photo-lg">
<img src="{escape(p['img'])}" alt="{escape(p['name_hi'])}" loading="lazy" width="280" height="280"
onclick="document.getElementById('km-lightbox-img').src=this.src;document.getElementById('km-lightbox').classList.add('open')">
<span class="photo-zoom-hint">🔍</span></div>
<div class="answer-prod-info">
{_badge_pill(p)}
<h1>{p['emoji']} {escape(p['name_hi'])}</h1>
<p class="answer-sub">{escape(cat_label)} · {escape(p['name_en'])}</p>
<div class="answer-price">
<div class="answer-rupee">₹{p['price']}<small>/{escape(p['unit_hi'])}</small></div>
<div class="prod-est">अनुमानित भाव</div>
</div>
<div class="answer-range">
<div><span>पैक</span><b>{escape(p['unit_hi'])}</b></div>
<div><span>श्रेणी</span><b>{escape(cat_label)}</b></div>
<div><span>रेट किसका</span><b>दुकानदार का</b></div>
</div>
</div>
</div>
</section>

<p class="desc">{escape(p['desc_hi'])}</p>

<div class="cta-row">{"".join(ctas)}</div>
{affil_note}
<div class="prod-disclaimer"><b>ध्यान दें:</b> {escape(DISCLAIMER)}</div>

<h2>अक्सर पूछे जाने वाले सवाल</h2>
{faq_html}
{related_html}
<div class="km-lightbox" id="km-lightbox" onclick="this.classList.remove('open')">
<img id="km-lightbox-img" src="" alt="{escape(p['name_hi'])}">
<button class="km-lightbox-close" onclick="event.stopPropagation();document.getElementById('km-lightbox').classList.remove('open')" aria-label="बंद करें">✕</button>
</div>"""

    crumbs = (f'<a href="{SITE}/">कृषि मित्र</a> › <a href="{SITE}/product/">उत्पाद</a> › '
              f'{escape(cat_label)} › {escape(p["name_hi"])}')
    return _doc(title, desc, canon, crumbs, body, ld, p["img"],
                active="shop", extra_css=_EXTRA_CSS)
