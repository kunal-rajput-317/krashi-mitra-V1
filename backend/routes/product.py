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

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from backend.routes.bhav import (
    _CSS as _BASE_CSS, _FONTS, _ICON, _ANALYTICS, _asset, _district_from_referer,
    _header, _footer, _doc, _faq, _crumb_ld, _fit, _ld,
)
from backend.services import affiliate, legal, lead_clicks, shop_catalog

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
              "पैक, वज़न और एक्सपायरी ज़रूर जाँच लें।"
              + " " + legal.GOODS_NOTE)

# The material-connection disclosure for the Amazon/Flipkart buttons. rel=
# "sponsored" tells Google; this tells the farmer, which is the half the CCPA's
# endorsement guidelines actually ask for.
#
# It lives in services/affiliate.py now that /bhav carries affiliate links too:
# two sections printing two slightly different disclosures is how one of them
# quietly stops saying the thing that matters. Re-exported under the old name
# because this module is where the rest of the codebase already looks for it.
AFFILIATE_NOTE = affiliate.AFFILIATE_NOTE

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
    """The catalogue: shop.html's committed baseline, patched by the panel.

    The baseline half is unchanged — parsed out of shop.html, re-read only when
    its mtime moves. The overlay half is services/shop_catalog.py, which owns
    its own short-lived cache because a database has no mtime and this function
    is now on the hot path of every /bhav district page (the affiliate shelf
    calls it per render). Both halves fail closed: a bad edit to shop.html
    keeps the last good parse, and a sleeping or read-only database merges
    nothing at all, which leaves exactly the baseline.
    """
    try:
        mtime = _SHOP_HTML.stat().st_mtime
    except OSError:
        return shop_catalog.merge(_cache["products"])
    if mtime != _cache["mtime"]:
        try:
            parsed = _parse_shop_html(_SHOP_HTML.read_text(encoding="utf-8"))
        except Exception:
            return shop_catalog.merge(_cache["products"])   # keep last good on a bad edit
        if parsed:                            # never clobber good cache with empty
            _cache.update(mtime=mtime, products=parsed,
                          by_slug={p["slug"]: p for p in parsed})
    return shop_catalog.merge(_cache["products"])


def _get_by_slug() -> dict:
    """Built off the MERGED list, not the baseline cache.

    _cache["by_slug"] holds only what shop.html committed, so reading it here
    would make a panel-added product resolve on the hub and 404 on its own
    page — the one failure that looks like the feature is broken."""
    return {p["slug"]: p for p in _get_products()}


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


def _photo(p: dict, w: int, h: int, cls: str = "") -> str:
    """The product's picture, or its emoji when there is not one yet.

    A product typed into the admin panel may have no photo for another minute —
    the owner adds it, then uploads the pack shot. Rendering `<img src="">`
    meanwhile gives every browser's broken-image glyph on a live page, which
    looks like the product is broken rather than new. The emoji is honest, it
    is already hand-picked per product, and it is what the affiliate shelf on
    /bhav uses for the same reason."""
    img = (p.get("img") or "").strip()
    if img:
        return (f'<img src="{escape(img)}" alt="{escape(p.get("name_hi", ""))}" '
                f'loading="lazy" width="{w}" height="{h}">')
    return f'<span class="prod-noimg{" " + cls if cls else ""}">{escape(p.get("emoji", "📦"))}</span>'


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
/* No photo yet — a product typed into the panel before its pack shot
   arrives. The emoji fills the same box an <img> would, so the grid does not
   reflow when the photo is uploaded a minute later. */
.prod-noimg{font-size:44px;line-height:1;display:flex;align-items:center;
justify-content:center;width:100%;height:100%}
.prod-noimg.lg{font-size:112px;aspect-ratio:1;background:var(--cream)}
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

/* The buy CTA is a <button>, not an <a> — it opens the pre-book sheet rather
   than going anywhere. The shared .btn rule was written for anchors, so the
   browser's own button chrome (border, grey background, 13px system font)
   would otherwise show through everything .btn sets. */
button.btn{border:0;cursor:pointer;line-height:1.35}

/* ── the प्री-बुक sheet ── shop.html's buy funnel, on the page that replaced
   it. Same four fields, the same /order/log row and the same 📒 it lands in;
   the only thing left behind is the Amazon/Flipkart chooser it used to open
   first, because those two buttons already sit beside this one here. ── */
.pb-ov{position:fixed;inset:0;z-index:100000;background:rgba(16,32,25,.55);
display:flex;align-items:flex-end;justify-content:center;
-webkit-backdrop-filter:blur(2px);backdrop-filter:blur(2px)}
.pb-ov[hidden]{display:none}
.pb-box{position:relative;width:100%;max-width:520px;max-height:92vh;overflow-y:auto;
background:var(--white);border-radius:20px 20px 0 0;padding:20px 18px 18px;
box-shadow:var(--shadow-md);animation:pb-up .22s ease}
@keyframes pb-up{from{transform:translateY(24px);opacity:.4}to{transform:none;opacity:1}}
@media(min-width:600px){.pb-ov{align-items:center;padding:20px}
.pb-box{border-radius:var(--radius-md)}}
.pb-box h2{margin:0 0 3px;font-size:18px;line-height:1.35;color:var(--green-dark);padding-right:36px}
.pb-sub{margin:0 0 4px;font-size:12.5px;color:var(--text-soft);line-height:1.5}
.pb-x{position:absolute;top:12px;right:12px;width:34px;height:34px;border:0;border-radius:50%;
background:var(--cream);color:var(--text-mid);font-size:21px;line-height:1;cursor:pointer}
.pb-x:hover{background:var(--border)}
.pb-item{display:flex;align-items:center;gap:10px;margin:12px 0 2px;padding:10px 12px;
background:var(--cream);border-radius:12px;font-size:13px;color:var(--text-mid);line-height:1.45}
.pb-item b{display:block;font-size:14px;color:var(--text-dark)}
.pb-item .pb-em{font-size:26px;line-height:1;flex:0 0 auto}
.pb-lbl{display:block;font-size:12.5px;font-weight:700;color:var(--text-mid);margin:12px 0 5px}
.pb-req{color:#d32f2f}
.pb-in{width:100%;padding:11px 13px;border:1.5px solid var(--border);border-radius:11px;
font-size:15px;font-family:inherit;color:var(--text-dark);background:var(--white)}
.pb-in:focus{outline:none;border-color:var(--green-mid)}
.pb-in.bad{border-color:#e53935}
.pb-qty{display:flex;align-items:center;gap:10px}
.pb-qty button{width:40px;height:40px;flex:0 0 auto;border:1.5px solid var(--border);border-radius:11px;
background:var(--cream);color:var(--green-dark);font-size:19px;font-weight:800;cursor:pointer}
.pb-qty .pb-in{width:78px;text-align:center}
.pb-total{margin-top:10px;padding:9px 13px;border-radius:11px;background:var(--green-pale);
font-size:14px;font-weight:800;color:var(--green-dark)}
.pb-go{width:100%;margin-top:14px;padding:13px;border:0;border-radius:12px;
background:var(--green-dark);color:#fff;font-size:16px;font-weight:800;font-family:inherit;cursor:pointer}
.pb-go:hover{background:var(--green-mid)}
.pb-go:disabled{opacity:.62;cursor:default}
.pb-note{margin:10px 0 0;font-size:11.5px;color:var(--text-soft);line-height:1.6}
/* the state after a saved row — the form is gone, the tracking code is not */
.pb-ok{text-align:center;padding:6px 0 2px}
.pb-ok .pb-tick{font-size:40px;line-height:1}
.pb-ok h3{margin:8px 0 4px;font-size:17px;color:var(--green-dark)}
.pb-ok p{margin:0 0 4px;font-size:13px;color:var(--text-mid);line-height:1.6}
.pb-code{display:inline-block;margin:8px 0 2px;padding:6px 14px;border-radius:10px;
background:var(--cream);font-family:monospace;font-size:15px;font-weight:700;color:var(--text-dark)}
.pb-wa{display:block;margin-top:14px;padding:13px;border-radius:12px;background:#25d366;color:#0b3d1e;
font-size:15px;font-weight:800;text-decoration:none}
/* Top, not bottom: the only messages this carries are the two failure
   branches, and both leave a WhatsApp button sitting at the bottom of the
   sheet — a toast down there lands squarely on the thing it is telling him
   to tap. */
.pb-toast{position:fixed;left:50%;top:14px;transform:translateX(-50%);z-index:100001;
max-width:92vw;padding:12px 16px;border-radius:12px;background:#14361f;color:#fff;
font-size:13.5px;font-weight:600;line-height:1.5;box-shadow:0 8px 26px rgba(0,0,0,.3)}
.pb-toast[hidden]{display:none}
"""

# Only _not_found() below needs the combined sheet — it builds its own <head>
# by hand instead of going through bhav.py's _doc().
_CSS = _BASE_CSS + _EXTRA_CSS


# ── the buy funnel ──────────────────────────────────────────
#
# WHAT THE BUTTON DOES, AND WHY IT IS BACK. The page used to end on a WhatsApp
# link titled "रेट पूछें": it drafted a message and left. Nothing was recorded,
# so nobody could answer it later, it never reached /admin, and the farmer had
# no way to see a reply anywhere but that one chat.
#
# The funnel shop.html ran is the one the business actually has: the farmer
# pre-books (name, phone, quantity, pincode), the row lands in `orders` through
# POST /order/log, the owner sources a dealer and quotes back with
# quote_total/dealer_name, and the farmer reads the quote in the 📒 book. When
# /shop was retired on 16 Sep 2026 that funnel lost its only front end — the
# API, the admin queue and the book all stayed. This puts it back on /product,
# which is the shop now.
#
# It is NOT a sale, and the wording may never imply one. We take an enquiry, a
# dealer names the price, and 8 of the first 28 came back "Not Available" — so
# the sheet says प्री-बुक, says no money moves in this step, and keeps the
# estimate labelled as an estimate. tests/test_product_price_claims.py fails
# the build on "ऑर्डर करें" and "में खरीदें" for exactly that reason.
#
# Plain string, not an f-string — the JS braces would need doubling otherwise.
_BUY_JS = """
var ov=document.getElementById('pb-ov');
if(!ov)return;
var P={id:parseInt(ov.dataset.pid,10)||null,name:ov.dataset.pname,
       unit:ov.dataset.punit,price:parseFloat(ov.dataset.pprice)||0,url:ov.dataset.purl};
var qty=1, sent=false;
function $(id){return document.getElementById(id);}
function money(n){return n.toLocaleString('en-IN');}
function paint(){$('pb-q').value=qty;
 $('pb-total').textContent='अनुमानित: ₹'+money(P.price*qty)+' ('+qty+' × '+P.unit+')';}

var GATE={title:'प्री-बुक के लिए लॉगिन करें',
 text:'दाम तैयार होते ही सूचना आपके खाते पर आएगी — फ़ोन बदलने या ब्राउज़र साफ़ करने पर भी आपकी प्री-बुक सुरक्षित रहेगी।',
 resume:'product-buy'};

function show(){ov.hidden=false;document.body.style.overflow='hidden';paint();
 setTimeout(function(){var n=$('pb-name');if(n)n.focus();},180);}
window.kmCloseBuy=function(){ov.hidden=true;document.body.style.overflow='';};

/* Gated before the sheet opens, not after it is filled in — nobody should type
   his name, number and pincode only to be sent to login. He comes back to this
   same URL with ?do=product-buy and the sheet re-opens itself. */
window.kmOpenBuy=function(){
 if(window.KMRequireLogin&&!window.KMRequireLogin(GATE))return;
 show();
};
window.kmBuyQty=function(d){qty=Math.max(1,qty+d);paint();};
window.kmBuySetQty=function(v){var q=parseInt(v,10);qty=(isNaN(q)||q<1)?1:q;paint();};

ov.addEventListener('click',function(e){if(e.target===ov)window.kmCloseBuy();});
document.addEventListener('keydown',function(e){
 if(e.key==='Escape'&&!ov.hidden)window.kmCloseBuy();});
if(window.KMTakeResume&&window.KMTakeResume()==='product-buy')setTimeout(show,300);

function toast(msg,ms){var t=$('pb-toast');t.textContent=msg;t.hidden=false;
 setTimeout(function(){t.hidden=true;},ms||5000);}
function bad(id){var el=$(id);el.classList.add('bad');el.focus();
 setTimeout(function(){el.classList.remove('bad');},1400);}

function waHref(code,nm,ph,pin,vil){
 /* A real newline, built at runtime: _BUY_JS is an ordinary Python string, so
    a "\\n" written here would be a line break in the emitted JS source and the
    literal would never close. */
 var NL=String.fromCharCode(10);
 var msg='🌾 *कृषि मित्र — प्री-बुक*'+NL+(code?('🆔 '+code+NL):'')+
  NL+'👤 '+nm+NL+'📱 '+ph+
  NL+NL+'📦 '+P.name+NL+'🔢 मात्रा: '+qty+' ('+P.unit+')'+
  NL+'🏷️ अनुमानित दर: ₹'+money(P.price)+
  NL+NL+'📍 पिनकोड: '+pin+(vil?(NL+'🏘️ '+vil):'')+
  NL+NL+P.url+
  NL+'💬 कृपया मेरे इलाके के दुकानदार से पूरा दाम पता करके भेजें।';
 return 'https://wa.me/919870951001?text='+encodeURIComponent(msg);
}

/* The saved row IS the outcome — the WhatsApp hand-off is a tap, not a popup.
   window.open() from inside a fetch callback is not a user gesture any more and
   mobile browsers block it, which on shop.html could leave a farmer staring at
   nothing after a pre-book that had in fact gone through. */
function done(code,nm,ph,pin,vil){
 sent=true;
 /* A tick and "दर्ज हो गई" only where a row was actually written. Without a
    tracking code nothing was saved, nothing will reach 📒 and nobody will
    call — so that branch says so and makes WhatsApp the way out, rather than
    dressing a failure up as a booking. */
 var head=code
  ?('<div class="pb-tick">✅</div><h3>प्री-बुक दर्ज हो गई</h3>'+
    '<p>हम पिनकोड '+pin+' पर दुकानदार से दाम पता करके आपको भेजेंगे। अभी कोई भुगतान नहीं।</p>'+
    '<div class="pb-code">'+code+'</div>'+
    '<p>यह नंबर संभालकर रखें — दाम तैयार होते ही 📒 किताब में इसी नंबर पर आएगा।</p>')
  :('<div class="pb-tick">⚠️</div><h3>प्री-बुक सेव नहीं हो पाई</h3>'+
    '<p>आपकी जानकारी हमारे पास दर्ज नहीं हुई। नीचे के बटन से WhatsApp पर भेज '+
    'दीजिए — वहीं से दाम पता करके भेज देंगे।</p>');
 $('pb-form').innerHTML='<div class="pb-ok">'+head+
  '<a class="pb-wa" target="_blank" rel="noopener" href="'+waHref(code,nm,ph,pin,vil)+'">'+
  (code?'📲 WhatsApp पर भी भेजें':'📲 WhatsApp पर भेजें')+'</a></div>';
}

window.kmSubmitBuy=function(){
 if(sent)return;
 var nm=$('pb-name').value.trim(), ph=$('pb-phone').value.trim(),
     pin=$('pb-pin').value.trim(), vil=$('pb-vill').value.trim();
 if(!nm){bad('pb-name');return;}
 if(ph.length<10){bad('pb-phone');return;}
 if(pin.length<6){bad('pb-pin');return;}
 var btn=$('pb-go'), label=btn.textContent;
 btn.disabled=true;btn.textContent='भेजा जा रहा है…';
 var base=window.KRASHIMITRA_API_BASE||location.origin;
 var h={'Content-Type':'application/json'}, tok=null;
 try{tok=localStorage.getItem('krishi_token');}catch(e){}
 if(tok)h['Authorization']='Bearer '+tok;
 fetch(base+'/order/log',{method:'POST',headers:h,body:JSON.stringify({
  product_name:P.name, product_id:P.id, quantity:qty,
  unit_price:P.price, total:P.price*qty, phone:ph,
  customer_name:nm, pincode:pin, source:'prebook'})})
 .then(function(r){return r.json().catch(function(){return {};})
   .then(function(d){return {status:r.status,d:d};});})
 .then(function(res){
  btn.disabled=false;btn.textContent=label;
  /* Token expired while the sheet was open — nothing was saved, so do not hand
     him a tick that says it was. */
  if(res.status===401){window.kmCloseBuy();
   if(window.KMShowLoginGate)window.KMShowLoginGate(GATE);
   else toast('कृपया दोबारा लॉगिन करें।');
   return;}
  if(res.d&&res.d.success){
   if(window.kmTrack)kmTrack('prebook_order',{product:P.name,quantity:qty,
     value:P.price*qty,source:'product'});
   done(res.d.tracking_code,nm,ph,pin,vil);
   return;}
  done(null,nm,ph,pin,vil);
  toast('⚠️ सेव नहीं हो पाया — WhatsApp से भेज दीजिए।');
 })
 .catch(function(){
  btn.disabled=false;btn.textContent=label;
  done(null,nm,ph,pin,vil);
  toast('⚠️ इंटरनेट नहीं मिला — WhatsApp से भेज दीजिए।');
 });
};
"""


def _buy_sheet(p: dict, canon: str) -> str:
    """The pre-book sheet, its toast, and the script that drives them.

    Every product-specific value rides on data-* attributes rather than being
    baked into the script: /product HTML is edge-cached for half an hour, so
    the markup has to be identical for every visitor and one script has to work
    on all 94 pages. Nothing user-specific is rendered here — the login gate,
    the name and the number are all the browser's side of the job."""
    unit_val = (p.get("unit_hi") or "").strip() or "यूनिट"
    emoji_val = p.get("emoji") or "📦"
    return f"""<div class="pb-ov" id="pb-ov" hidden
 data-pid="{p.get('id') or ''}" data-pname="{escape(p['name_hi'], quote=True)}"
 data-punit="{escape(unit_val, quote=True)}" data-pprice="{p['price']}"
 data-purl="{escape(canon, quote=True)}">
<div class="pb-box" role="dialog" aria-modal="true" aria-labelledby="pb-t">
<button class="pb-x" type="button" onclick="kmCloseBuy()" aria-label="बंद करें">&times;</button>
<h2 id="pb-t">प्री-बुक करें</h2>
<p class="pb-sub">दाम दुकानदार का होता है — हम आपके इलाके में पता करके आपको भेजते हैं।</p>
<div id="pb-form">
<div class="pb-item"><span class="pb-em" aria-hidden="true">{emoji_val}</span>
<span><b>{escape(p['name_hi'])}</b>₹{p['price']} / {escape(unit_val)} · अनुमानित</span></div>

<label class="pb-lbl" for="pb-name">👤 किसान का नाम <span class="pb-req">*</span></label>
<input class="pb-in" id="pb-name" type="text" placeholder="जैसे: रामलाल सिंह" autocomplete="name">

<label class="pb-lbl" for="pb-phone">📱 मोबाइल नंबर <span class="pb-req">*</span></label>
<input class="pb-in" id="pb-phone" type="tel" maxlength="10" inputmode="numeric"
 placeholder="जैसे: 9876543210" autocomplete="tel"
 oninput="this.value=this.value.replace(/\\D/g,'')">

<label class="pb-lbl" for="pb-q">📦 मात्रा <span class="pb-req">*</span></label>
<div class="pb-qty">
<button type="button" onclick="kmBuyQty(-1)" aria-label="कम करें">&minus;</button>
<input class="pb-in" id="pb-q" type="number" min="1" value="1" inputmode="numeric"
 oninput="kmBuySetQty(this.value)">
<button type="button" onclick="kmBuyQty(1)" aria-label="ज़्यादा करें">+</button>
</div>
<div class="pb-total" id="pb-total">अनुमानित: ₹{p['price']}</div>

<label class="pb-lbl" for="pb-pin">📍 पिनकोड — कहाँ चाहिए <span class="pb-req">*</span></label>
<input class="pb-in" id="pb-pin" type="tel" maxlength="6" inputmode="numeric"
 placeholder="जैसे: 273001" autocomplete="postal-code"
 oninput="this.value=this.value.replace(/\\D/g,'')">

<label class="pb-lbl" for="pb-vill">🏘️ गाँव / जिला</label>
<input class="pb-in" id="pb-vill" type="text" placeholder="जैसे: मेरठ, UP (वैकल्पिक)">

<button class="pb-go" id="pb-go" type="button" onclick="kmSubmitBuy()">प्री-बुक भेजें</button>
<p class="pb-note">अभी कोई भुगतान नहीं। कृषि मित्र सामान नहीं बेचता — पैक, वज़न और
एक्सपायरी दुकानदार की ज़िम्मेदारी है, सौदा आपका उसी से होता है।
सामान के इस्तेमाल से किसी भी नुकसान के लिए कृषि मित्र ज़िम्मेदार नहीं।</p>
</div>
</div>
</div>
<div class="pb-toast" id="pb-toast" hidden></div>
<script>(function(){{{_BUY_JS}}})();</script>"""



def _hub_card(p: dict) -> str:
    """One catalogue tile — on the /product/ hub and in the related strip.

    The struck-through MRP and the "% off" pill are gone for the same reason
    they are gone from the product page itself: the MRP is unverified, so the
    discount computed against it is a claim we cannot stand behind, and a card
    is exactly where a farmer reads one without reading anything else. The
    price stays and is labelled ~ for approximate, which is what it is."""
    return f"""<a class="prod-card" href="/product/{p['slug']}">
<div class="prod-card-photo">{_badge_pill(p, "prod-badge-card")}
{_photo(p, 120, 100)}</div>
<div class="prod-card-body">
<div class="prod-card-name">{escape(p['name_hi'])}</div>
<span class="prod-card-en">{escape(p['name_en'])}</span>
<div class="prod-card-price"><b>~₹{p['price']}</b><span class="est">अनुमानित</span></div>
<div class="prod-card-unit">{escape(p['unit_hi'])}</div>
</div>
</a>"""


# ════════════════════════════════════════════════════════════
# The tracked affiliate hop
#
# Every Amazon/Flipkart link on the site now leaves through here instead of
# pointing straight at amzn.to. One extra redirect buys the two things the
# program was missing: a click we can count, and a URL we can swap in one
# place if a network or a tag ever changes.
#
# Same two rules as /go/<offer_id>, for the same reasons: the write happens in
# a background task AFTER the 302 (a sleeping Neon compute must never sit
# between a farmer and the product he tapped), and it can never fail the
# redirect (services/lead_clicks.record swallows everything).
# ════════════════════════════════════════════════════════════
@router.get("/go/p/{net}/{slug}")
def affiliate_redirect(net: str, slug: str, request: Request,
                       background: BackgroundTasks):
    """Tracked hop to a product's affiliate URL.

    An unknown slug, an unknown network or a product with no link for that
    network falls back to the product page rather than erroring — a farmer who
    tapped a product should land on something about that product, and a stale
    link in a cached page is exactly when that matters.
    """
    p = affiliate.by_slug(slug)
    url = affiliate.raw_url(p, net) if p else ""
    if not url:
        return RedirectResponse(f"/product/{slug}" if p else "/product",
                                status_code=302)
    ref = request.headers.get("referer", "")
    background.add_task(
        lead_clicks.record, "product", f"{net}:{slug}",
        # The catalogue name, not the Hindi one: this is read in the admin
        # panel beside offer and dealer rows, where English sorts and greps.
        label      = p.get("name_en"),
        category   = p.get("cat"),
        # Set only when the click came off a /bhav page — which is the whole
        # question this placement exists to answer.
        district   = _district_from_referer(ref),
        referer    = ref,
        user_agent = request.headers.get("user-agent"),
    )
    return RedirectResponse(url, status_code=302)


# ── /product/img/{id}.webp ──────────────────────────────────
# A photo typed into the admin panel, out of Postgres. On disk it would not
# survive the next Render restart — the same lesson profile.py's avatars and
# krashi_dukan.py's catalogue photos already learned.
#
# Three path segments, so /product/{slug} (two) cannot swallow it.

@router.get("/product/img/{product_id}.webp")
def product_image(product_id: int):
    import base64

    from backend.database.db import SessionLocal, ShopProduct
    db = None
    try:
        db = SessionLocal()
        row = db.query(ShopProduct).filter(ShopProduct.id == product_id).first()
        if not row or not row.image_data:
            return Response(status_code=404)
        blob = base64.b64decode(row.image_data)
    except Exception:
        return Response(status_code=404)
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass
    return Response(content=blob, media_type=row.image_mime or "image/webp",
                    headers={"Cache-Control": "public, max-age=86400"})


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
</div>
</div>
{_footer()}
</body>
</html>""", status_code=404)


@router.get("/product/{slug}", response_class=HTMLResponse)
def product_page(slug: str):
    by_slug = _get_by_slug()
    norm = slug.lower().strip()
    p = by_slug.get(norm)
    if not p:
        # Also try slugified version in case raw product name or unslugified URL was passed
        p = by_slug.get(_slugify(norm))
    if not p:
        return _not_found()
    return render_product(p)


def render_product(p: dict) -> HTMLResponse:
    """The product page for one already-resolved product.

    Split out of product_page so the Shop Panel can preview an edit that has
    not been saved: it hands in the merged dict and gets back the real page,
    rendered by this exact code rather than by a second, drifting copy of it.
    Same reason admin_articles.py previews through the article builder itself.
    """
    cat_label = CAT_LABELS.get(p.get("cat", "misc"), p.get("cat", "misc"))
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

    unit_hi = (p.get("unit_hi") or "").strip()
    unit_tag = f" — {unit_hi}" if unit_hi else ""
    unit_price = f" {unit_hi}" if unit_hi else ""
    unit_bracket = f" ({unit_hi})" if unit_hi else ""
    unit_slash = f"<small>/{escape(unit_hi)}</small>" if unit_hi else ""
    unit_label = escape(unit_hi) if unit_hi else "मानक"

    # "SSP (सिंगल सुपर फॉस्फेट)" already opens with its own acronym, so the
    # short English form would print it a second time ("… (SSP) ₹460"). Where
    # the bare English name is already in the Hindi one, the bracket is dropped
    # and the space goes to the pack size instead.
    en_tag = "" if en_bare.lower() in hi_name.lower() else f" ({en_bare})"
    en_lead = hi_bare if en_bare.lower() in hi_bare.lower() else f"{hi_bare} ({en_bare})"
    title = _fit(
        f"{hi_name} ({en_name}) {rs}{unit_tag}",
        f"{hi_name} ({en_name}) की कीमत {rs}",
        f"{hi_name} {rs} — {en_name} Price Online",
        f"{hi_name}{en_tag} {rs}{unit_tag}",
        f"{hi_name} {rs} — {en_bare} Price{unit_price}",
        f"{hi_name} {rs} — {en_bare} Price Online",
        f"{en_lead} {rs}{unit_tag} की कीमत",
        f"{hi_bare} {rs} — {en_bare} Price Online",
        f"{hi_name} की कीमत {rs}{unit_tag}",
        f"{hi_bare} की कीमत {rs}{unit_tag}",
        f"{hi_bare} {rs} — {en_bare}",
        f"{hi_bare} की कीमत {rs}")

    # The description sold what we do not sell: "अभी ऑर्डर करें" plus free
    # delivery over ₹500 and Cash on Delivery, on every variant. What is true is
    # that the figure is a typical market price and that a dealer quotes the
    # real one — so that is what the snippet now says. It still leads with the
    # name, the pack and the number, which is what the query asked for.
    desc_hi = (p.get("desc_hi") or "").strip()
    desc_en = (p.get("desc_en") or "").strip()
    desc_text = desc_hi or desc_en or f"{cat_label} का उच्च गुणवत्ता वाला उत्पाद।"
    desc_clean = desc_text.rstrip("। .") + "।"

    desc = _fit(
        f"{hi_name}{unit_bracket} का अनुमानित भाव {rs} — {desc_clean} असली रेट दुकान और इलाके से बदलता है।",
        f"{hi_name}{unit_bracket} का अनुमानित भाव {rs} — {desc_clean} रेट दुकान से बदलता है।",
        f"{hi_name}{unit_bracket} — अनुमानित {rs}। {desc_clean} असली रेट दुकान पर पक्का करें।",
        f"{hi_name}{unit_bracket} का अनुमानित भाव {rs} — {desc_clean}",
        f"{hi_name}{unit_bracket} — अनुमानित {rs}। {desc_clean}",
        f"{hi_name} ({en_bare}){unit_price} की अनुमानित कीमत {rs} — असली रेट दुकान, कंपनी और इलाके से बदलता है।",
        f"{hi_name} —{unit_price} का अनुमानित भाव {rs}। रेट दुकान से बदलता है।",
        f"{hi_name} —{unit_price} की अनुमानित कीमत {rs}।",
        limit=162)

    # ── CTAs ──
    # "रेट पूछें" drafted a WhatsApp message and left: no row, nothing in
    # /admin, nothing in the 📒 book, and no way to answer the farmer later
    # unless somebody happened to read that chat. The first button is the
    # pre-book again — shop.html's funnel, on the page that replaced it (see
    # _BUY_JS above). It still promises nothing but a dealer's quote.
    ctas = ['<button class="btn btn-app" type="button" onclick="kmOpenBuy()">🛒 खरीदें</button>']
    # Through /go/p/<net>/<slug>, never straight at the network. These buttons
    # were the site's only affiliate placement for months and left no record of
    # a single click; the redirect is what turns them into a number.
    if _available(p.get("affil_amazon", "")):
        ctas.append(f'<a class="btn btn-amazon" target="_blank" rel="noopener nofollow sponsored" '
                    f'href="{affiliate.go_url(p["slug"], "amazon")}">Amazon पर देखें</a>')
    if _available(p.get("affil_flipkart", "")):
        ctas.append(f'<a class="btn btn-flipkart" target="_blank" rel="noopener nofollow sponsored" '
                    f'href="{affiliate.go_url(p["slug"], "flipkart")}">Flipkart पर देखें</a>')
    wa_text = quote(f"{p['name_hi']} — अनुमानित ₹{p['price']}{unit_bracket}\n{canon}")
    ctas.append(f'<a class="btn btn-wa" target="_blank" href="https://wa.me/?text={wa_text}">📲 शेयर करें</a>')
    # The disclosure rides beside the buttons it is about, and only on pages
    # that actually carry one — a page with no affiliate link has nothing to
    # disclose, and printing it there would be noise that trains the reader to
    # skip the notice on the pages where it means something.
    affil_note = (f'<p class="prod-affil-note">{escape(AFFILIATE_NOTE)}</p>'
                  if _available(p.get("affil_amazon", ""))
                  or _available(p.get("affil_flipkart", "")) else "")

    # ── related products: same category, same rich card as the /product/ hub ──
    related = [r for r in _get_products() if r.get("cat") == p.get("cat") and r["slug"] != p["slug"]][:8]
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
         f"{p['name_hi']}{unit_bracket} का अनुमानित बाज़ार भाव ₹{p['price']} के आसपास है। "
         f"यह पक्का रेट नहीं है — दुकान, कंपनी, पैक साइज़ और इलाके के हिसाब से दाम बदलता है। "
         f"अपने नज़दीकी दुकानदार से आज का रेट पूछ लें।"),
        ("क्या कृषि मित्र यह सामान बेचता है?",
         "नहीं। कृषि मित्र सामान न बेचता है, न डिलीवरी करता है, न किसी सामान की गारंटी "
         "लेता है। हम सिर्फ़ किसान और दुकानदार को जोड़ते हैं — रेट पूछने पर दुकानदार "
         "अपना भाव बताता है, और सौदा आपका उसी से होता है।"),
    ]
    faq_html, faq_ld = _faq(faqs)

    raw_img = (p.get("img") or "").strip()
    if raw_img.startswith("http://") or raw_img.startswith("https://"):
        og_img = raw_img
    elif raw_img.startswith("/"):
        og_img = f"{SITE}{raw_img}"
    elif raw_img:
        og_img = f"{SITE}/{raw_img}"
    else:
        og_img = f"{SITE}/images/og-banner.webp"

    # Product WITHOUT offers. An Offer needs a seller and a price someone will
    # honour; an indicative catalogue figure has neither, so marking one up as
    # an offer puts a false claim into structured data — the same rule
    # rental.py and krashi_dukan.py follow. `brand` went with it: declaring
    # "Kapila Cattle Feed" to be a KrashiMitra brand is someone else's
    # trademark on our name. A product whose brand we cannot state truthfully
    # simply does not carry the key.
    product_ld = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": f"{p['name_en']} — {p['name_hi']}",
        "description": desc_en or desc_hi or f"{p['name_en']} ({cat_label})",
        "category": cat_label,
        "sku": f"KM-PROD-{p.get('id', p['slug'])}",
        "url": canon,
    }
    if og_img:
        product_ld["image"] = og_img

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
{_photo(p, 280, 280, "lg")}
<span class="photo-zoom-hint">🔍</span></div>
<div class="answer-prod-info">
{_badge_pill(p)}
<h1>{p.get('emoji', '📦')} {escape(p['name_hi'])}</h1>
<p class="answer-sub">{escape(cat_label)} · {escape(p['name_en'])}</p>
<div class="answer-price">
<div class="answer-rupee">₹{p['price']}{unit_slash}</div>
<div class="prod-est">अनुमानित भाव</div>
</div>
<div class="answer-range">
<div><span>पैक</span><b>{unit_label}</b></div>
<div><span>श्रेणी</span><b>{escape(cat_label)}</b></div>
<div><span>रेट किसका</span><b>दुकानदार का</b></div>
</div>
</div>
</div>
</section>

<p class="desc">{escape(desc_hi or desc_en or "")}</p>

<div class="cta-row">{"".join(ctas)}</div>
{affil_note}
<div class="prod-disclaimer"><b>ध्यान दें:</b> {escape(DISCLAIMER)}</div>

<h2>अक्सर पूछे जाने वाले सवाल</h2>
{faq_html}
{related_html}
<div class="km-lightbox" id="km-lightbox" onclick="this.classList.remove('open')">
<img id="km-lightbox-img" src="" alt="{escape(p['name_hi'])}">
<button class="km-lightbox-close" onclick="event.stopPropagation();document.getElementById('km-lightbox').classList.remove('open')" aria-label="बंद करें">✕</button>
</div>
{_buy_sheet(p, canon)}"""

    crumbs = (f'<a href="{SITE}/">कृषि मित्र</a> › <a href="{SITE}/product/">उत्पाद</a> › '
              f'{escape(cat_label)} › {escape(p["name_hi"])}')
    # The 📒 book rides on this page and only this one in the section, because
    # this is where a pre-book is placed and the book is where its quote comes
    # back — a tracking code with nowhere on the site to read it is the same
    # dead end the WhatsApp-only button was. It mounts itself next to the
    # header avatar and no-ops on a page that already has one.
    return _doc(title, desc, canon, crumbs, body, ld, og_img,
                active="shop", extra_css=_EXTRA_CSS,
                head_extra=f'<script src="{_asset("krashibook.js")}" defer></script>')
