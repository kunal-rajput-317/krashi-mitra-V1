# ============================================================
# routes/product.py
# Krishi Mitra — SEO shop-product pages ("beej/khad/pesticide kharidein")
#
# Server-rendered, indexable pages at /product/{slug} for the shop
# catalog — same pattern as routes/bhav.py's mandi price pages.
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
# ============================================================

import re
from html import escape
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, Response

router = APIRouter()

SITE = "https://krashimitra.in"
_SHOP_HTML = Path(__file__).resolve().parents[2] / "frontend" / "shop.html"

CAT_LABELS = {
    "seeds": "🌱 बीज", "fertilizer": "🧪 खाद", "pesticide": "🌿 कीटनाशक",
    "tools": "🔧 उपकरण", "pashu_aahaar": "🐄 पशु आहार", "sprayers": "🔵 स्प्रेयर",
    "irrigation": "💧 सिंचाई", "soil": "🧪 मिट्टी / ग्रोथ",
    "protection": "🛡️ फसल सुरक्षा", "structures": "🏗️ नेट व संरचनाएं",
    "machinery": "⚙️ मशीनरी", "misc": "📦 अन्य",
}

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


_CSS = """
:root{--g:#1b7a3d;--bg:#f6faf6;--line:#e0e8e0;--txt:#213021}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;background:var(--bg);color:var(--txt);line-height:1.55}
.wrap{max-width:860px;margin:0 auto;padding:16px}
header.top{background:var(--g);color:#fff;padding:10px 16px}
header.top a{color:#fff;text-decoration:none;font-weight:700}
h1{font-size:1.3rem;margin:14px 0 4px}
.cat{color:#5a6b5a;font-size:.9rem;margin-bottom:12px}
.pcard{display:flex;gap:14px;background:#fff;border:1px solid var(--line);border-radius:12px;padding:14px;margin:10px 0}
.pcard img{width:110px;height:110px;object-fit:contain;border-radius:8px;background:#f0f5f0;flex-shrink:0}
.pmeta .price{font-size:1.3rem;font-weight:800;color:var(--g)}
.pmeta .mrp{text-decoration:line-through;color:#8a9a8a;font-size:.9rem;margin-left:8px}
.pmeta .off{color:#c0392b;font-size:.85rem;font-weight:700;margin-left:6px}
.pmeta .unit{color:#5a6b5a;font-size:.85rem}
.pmeta .rating{font-size:.85rem;margin-top:4px}
.desc{margin:14px 0;font-size:.98rem}
.cta{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}
.cta a{display:inline-block;font-weight:700;padding:10px 18px;border-radius:24px;text-decoration:none;font-size:.9rem}
.cta .app{background:var(--g);color:#fff}
.cta .amazon{background:#ff9900;color:#111}
.cta .flipkart{background:#2874f0;color:#fff}
.cta .wa{background:#25d366;color:#fff}
h2{font-size:1.05rem;margin:20px 0 8px}
.links a{display:inline-block;background:#fff;border:1px solid var(--line);border-radius:16px;padding:4px 12px;margin:3px 4px 3px 0;text-decoration:none;color:var(--g);font-size:.88rem}
.faq{background:#fff;border:1px solid var(--line);border-radius:10px;padding:4px 14px;margin:8px 0}
.faq h3{font-size:.95rem;margin:10px 0 4px}
.faq p{font-size:.9rem;color:#445444;margin-bottom:10px}
footer{margin:24px 0 12px;font-size:.85rem;color:#5a6b5a}
footer a{color:var(--g)}
"""


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
    """Crawlable hub: every product grouped by category."""
    products = _get_products()
    by_cat: dict[str, list] = {}
    for p in products:
        by_cat.setdefault(p["cat"], []).append(p)

    sections = []
    for cat, label in CAT_LABELS.items():
        rows = by_cat.get(cat) or []
        if not rows:
            continue
        links = " ".join(
            f'<a href="/product/{p["slug"]}">{escape(p["name_hi"])}</a>'
            for p in rows)
        sections.append(f"<h2>{escape(label)}</h2><p class=\"links\">{links}</p>")

    body = "\n".join(sections)
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="hi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>बीज, खाद, कीटनाशक व उपकरण — सभी उत्पाद | कृषि मित्र दुकान</title>
<meta name="description" content="कृषि मित्र दुकान के सभी उत्पाद — बीज, खाद, कीटनाशक, उपकरण, पशु आहार व सिंचाई सामान। कीमत देखें, ऑनलाइन ऑर्डर करें।">
<link rel="canonical" href="{SITE}/product/">
<style>{_CSS}</style>
</head>
<body>
<header class="top"><a href="{SITE}/">🌾 कृषि मित्र</a></header>
<div class="wrap">
<h1>कृषि मित्र दुकान — सभी उत्पाद</h1>
<p class="cat">{len(products)} उत्पाद उपलब्ध — बीज से लेकर मशीनरी तक</p>
{body}
<footer><a href="{SITE}/shop.html">🛒 पूरी दुकान ऐप में खोलें</a> · <a href="{SITE}/">कृषि मित्र होम</a></footer>
</div>
</body>
</html>""", headers={"Cache-Control": "public, max-age=3600"})


@router.get("/product/{slug}", response_class=HTMLResponse)
def product_page(slug: str):
    p = _get_by_slug().get(slug.lower())
    if not p:
        return HTMLResponse(
            '<!DOCTYPE html><html lang="hi"><head><meta charset="utf-8">'
            '<title>उत्पाद नहीं मिला | कृषि मित्र</title>'
            '<meta name="robots" content="noindex"></head>'
            f'<body><p>यह उत्पाद उपलब्ध नहीं है। <a href="{SITE}/product/">सभी उत्पाद देखें →</a></p>'
            "</body></html>", status_code=404)

    cat_label = CAT_LABELS.get(p["cat"], p["cat"])
    canon = f"{SITE}/product/{p['slug']}"
    off_pct = round((1 - p["price"] / p["mrp"]) * 100) if p.get("mrp") and p["mrp"] > p["price"] else 0

    title = f"{p['name_hi']} ({p['name_en']}) खरीदें ₹{p['price']} | कृषि मित्र दुकान"
    desc = (f"{p['name_hi']} ({p['unit_hi']}) अभी ₹{p['price']} में ऑर्डर करें — "
            f"{p['desc_hi']} Cash on Delivery व ₹500+ पर मुफ्त डिलीवरी उपलब्ध।")

    # ── CTAs ──
    ctas = [f'<a class="app" href="{SITE}/shop.html?product={p["id"]}">🛒 ऐप में खरीदें</a>']
    if _available(p.get("affil_amazon", "")):
        ctas.append(f'<a class="amazon" target="_blank" rel="noopener sponsored" '
                    f'href="{escape(p["affil_amazon"])}">Amazon पर देखें</a>')
    if _available(p.get("affil_flipkart", "")):
        ctas.append(f'<a class="flipkart" target="_blank" rel="noopener sponsored" '
                    f'href="{escape(p["affil_flipkart"])}">Flipkart पर देखें</a>')
    wa_text = quote(f"{p['name_hi']} — ₹{p['price']} ({p['unit_hi']})\n{canon}")
    ctas.append(f'<a class="wa" target="_blank" href="https://wa.me/?text={wa_text}">📲 शेयर करें</a>')

    # ── related products: same category ──
    related = [r for r in _get_products() if r["cat"] == p["cat"] and r["slug"] != p["slug"]][:8]
    related_html = ""
    if related:
        links = " ".join(f'<a href="/product/{r["slug"]}">{escape(r["name_hi"])}</a>' for r in related)
        related_html = f'<h2>{escape(cat_label)} में अन्य उत्पाद</h2><p class="links">{links}</p>'

    # ── FAQ: visible markup AND JSON-LD generated from this ONE list ──
    faqs = [
        (f"{p['name_hi']} ({p['name_en']}) की कीमत क्या है?",
         (f"{p['name_hi']} की कीमत ₹{p['price']} है ({p['unit_hi']}), MRP ₹{p['mrp']} पर {off_pct}% की छूट के साथ।"
          if off_pct else f"{p['name_hi']} की कीमत ₹{p['price']} है ({p['unit_hi']})।")),
        ("क्या डिलीवरी और Cash on Delivery उपलब्ध है?",
         "हाँ, कृषि मित्र दुकान से ₹500+ के ऑर्डर पर मुफ्त डिलीवरी और Cash on Delivery उपलब्ध है।"),
    ]
    faq_html = "\n".join(
        f'<div class="faq"><h3>{escape(q)}</h3><p>{escape(a)}</p></div>' for q, a in faqs)
    faq_ld = {
        "@context": "https://schema.org", "@type": "FAQPage",
        "mainEntity": [{"@type": "Question", "name": q,
                        "acceptedAnswer": {"@type": "Answer", "text": a}}
                       for q, a in faqs]}
    crumbs_ld = {
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "कृषि मित्र", "item": f"{SITE}/"},
            {"@type": "ListItem", "position": 2, "name": "उत्पाद", "item": f"{SITE}/product/"},
            {"@type": "ListItem", "position": 3, "name": p["name_hi"], "item": canon}]}
    product_ld = {
        "@context": "https://schema.org", "@type": "Product",
        "name": f"{p['name_en']} — {p['name_hi']}",
        "description": p["desc_en"],
        "image": p["img"],
        "brand": {"@type": "Brand", "name": "KrashiMitra"},
        "offers": {
            "@type": "Offer", "price": str(p["price"]), "priceCurrency": "INR",
            "availability": "https://schema.org/InStock",
            "url": f"{SITE}/shop.html?product={p['id']}",
            "seller": {"@type": "Organization", "name": "KrashiMitra"},
        },
    }

    import json as _json
    ld = "\n".join(
        f'<script type="application/ld+json">{_json.dumps(block, ensure_ascii=False)}</script>'
        for block in (product_ld, faq_ld, crumbs_ld))

    mrp_html = f'<span class="mrp">₹{p["mrp"]}</span><span class="off">{off_pct}% छूट</span>' if off_pct else ""

    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="hi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title>
<meta name="description" content="{escape(desc)}">
<link rel="canonical" href="{canon}">
<meta property="og:type" content="product">
<meta property="og:site_name" content="कृषि मित्र (KrashiMitra)">
<meta property="og:title" content="{escape(title)}">
<meta property="og:description" content="{escape(desc)}">
<meta property="og:image" content="{escape(p['img'])}">
<meta property="og:url" content="{canon}">
<meta property="og:locale" content="hi_IN">
<meta name="twitter:card" content="summary_large_image">
{ld}
<style>{_CSS}</style>
</head>
<body>
<header class="top"><a href="{SITE}/">🌾 कृषि मित्र</a></header>
<div class="wrap">
<h1>{p['emoji']} {escape(p['name_hi'])}</h1>
<p class="cat"><a href="{SITE}/product/">उत्पाद</a> › {escape(cat_label)} · {escape(p['name_en'])}</p>
<div class="pcard">
<img src="{escape(p['img'])}" alt="{escape(p['name_hi'])}" loading="lazy">
<div class="pmeta">
<div><span class="price">₹{p['price']}</span>{mrp_html}</div>
<div class="unit">{escape(p['unit_hi'])} · {escape(p['name_kn'])}</div>
<div class="rating">{escape(p['rating'])}</div>
</div>
</div>
<p class="desc">{escape(p['desc_hi'])}</p>
<div class="cta">{"".join(ctas)}</div>
<h2>अक्सर पूछे जाने वाले सवाल</h2>
{faq_html}
{related_html}
<footer>
<a href="{SITE}/shop.html?cat={quote(p['cat'])}">🛒 {escape(cat_label)} की पूरी सूची</a>
 · <a href="{SITE}/product/">सभी उत्पाद</a>
 · <a href="{SITE}/chat.html">🤖 खेती का सवाल पूछें</a>
</footer>
</div>
</body>
</html>""", headers={"Cache-Control": "public, max-age=3600"})
