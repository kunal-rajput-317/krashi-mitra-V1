# ============================================================
# routes/krashi_dukan.py
# कृषि दुकान — /krashi_dukan, the local shop directory
#
# THREE PAGES, ONE IDEA.
#   /krashi_dukan                     every product some live shop stocks
#   /krashi_dukan/{product}           that product, and the shops that have it
#   /krashi_dukan/{product}/{shop}    one shop's counter price + how to reach it
#
# THE LAYOUT IS /product/'s, NOT A COPY OF IT. The page shell comes from
# bhav.py (_doc/_header/_footer/_faq) and the card, hero and grid CSS is
# imported straight out of product.py's _EXTRA_CSS, exactly the way product.py
# itself imports the shell rather than duplicating it. Three SEO surfaces, one
# stylesheet: a change to the product card lands on all of them for free, and
# they can never drift apart.
#
# NOTHING HERE TOUCHES /shop OR /product. That catalogue still runs off the
# PRODUCTS array in frontend/shop.html and is not read, written or imported
# for data anywhere below — only its stylesheet is. This is also not
# /dukanlisting, which sells advertising slots on /bhav price pages.
#
# WE ARE THE CONNECTION, NOT THE SELLER. No cart, no order, no delivery, no
# guarantee — every page says so in Hindi rather than burying it in Terms.
# ============================================================

import base64
from datetime import datetime
from html import escape
from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from backend.database.db import DukanCatalog, get_db
from backend.routes.bhav import (
    _ANALYTICS, _CSS as _BASE_CSS, _FONTS, _ICON, _crumb_ld, _doc, _faq,
    _fit, _footer, _header, _ld,
)
from backend.routes.product import CAT_LABELS, _EXTRA_CSS as _PRODUCT_CSS
from backend.services import krashi_dukan as dukan

router = APIRouter()

SITE = "https://krashimitra.in"
BASE = f"{SITE}/krashi_dukan"

# The disclaimer, in one place. It is on every page of this section because
# "we are only the connector" is worth nothing to a farmer who never read it.
DISCLAIMER = ("कृषि मित्र सिर्फ़ जोड़ने का काम करता है — सामान दुकानदार का है, "
              "कीमत दुकानदार की है। हम न सामान बेचते हैं, न डिलीवरी करते हैं, "
              "न किसी सामान की गारंटी लेते हैं। दुकान पर जाकर सामान ज़रूर जाँच लें।")

_EXTRA_CSS = _PRODUCT_CSS + """
/* ── shop rows under a product ── */
.dukan-shops{display:flex;flex-direction:column;gap:10px;margin-top:14px}
.dukan-shop{display:flex;gap:14px;align-items:stretch;background:var(--white);
border:1px solid var(--border);border-radius:var(--radius-md);padding:13px 15px;
box-shadow:var(--shadow-sm);text-decoration:none;color:inherit;
transition:transform .15s,box-shadow .15s,border-color .15s}
.dukan-shop:hover{transform:translateY(-2px);box-shadow:var(--shadow-md);border-color:var(--green-light)}
.dukan-shop-main{flex:1;min-width:0}
.dukan-shop-name{font-size:14.5px;font-weight:700;color:var(--text-dark);line-height:1.3}
.dukan-shop-where{display:block;font-size:11.5px;color:var(--text-soft);margin-top:2px}
.dukan-shop-meta{display:flex;flex-wrap:wrap;gap:6px;margin-top:7px}
.dukan-tag{font-size:10.5px;font-weight:700;padding:2px 8px;border-radius:10px;
background:var(--cream);color:var(--text-mid);white-space:nowrap}
.dukan-tag.tick{background:#e7f6ed;color:#1b7a45}
.dukan-tag.km{background:#eaf1fb;color:#22508f}
.dukan-tag.out{background:#fdeceb;color:#b23b2e}
.dukan-shop-price{text-align:right;flex-shrink:0;display:flex;flex-direction:column;
justify-content:center;gap:2px}
.dukan-shop-price b{font-size:19px;font-weight:700;color:var(--green-dark);line-height:1.1}
.dukan-shop-price .mrp{font-size:11px;color:var(--text-soft);text-decoration:line-through}
.dukan-shop-price .off{font-size:10.5px;font-weight:700;color:#c0392b}
.dukan-shop-price .unit{font-size:10.5px;color:var(--text-soft)}
.dukan-note{font-size:11.5px;color:var(--text-mid);margin-top:6px;font-style:italic}

.dukan-geo-hint{font-size:12px;color:var(--text-soft);margin:12px 0 0;
display:flex;align-items:center;gap:7px;flex-wrap:wrap}
.dukan-geo-btn{background:var(--green-pale);color:var(--green-dark);border:none;
font-family:inherit;font-size:12px;font-weight:700;padding:5px 12px;border-radius:14px;cursor:pointer}
.dukan-geo-btn:hover{background:var(--green-light);color:#fff}

/* ── the "we are only the connector" strip ── */
.dukan-disclaimer{background:#fff8e6;border:1px solid #f0dca8;border-radius:var(--radius-md);
padding:12px 15px;font-size:12.5px;color:#6b5312;line-height:1.6;margin:20px 0 0}
.dukan-disclaimer b{color:#4a3908}

/* ── one shop's own card on the offer page ── */
.dukan-card{background:var(--white);border:1px solid var(--border);
border-radius:var(--radius-md);padding:16px 18px;box-shadow:var(--shadow-sm);margin-top:14px}
.dukan-card h3{margin:0 0 10px;font-size:15px;color:var(--text-dark)}
.dukan-kv{display:flex;flex-direction:column;gap:9px}
.dukan-kv div{display:flex;gap:12px;font-size:13px;line-height:1.5}
.dukan-kv span{flex-shrink:0;width:92px;color:var(--text-soft);font-size:12px}
.dukan-kv b{font-weight:600;color:var(--text-dark);min-width:0;word-break:break-word}

@media(max-width:560px){
.dukan-shop{padding:11px 12px;gap:10px}
.dukan-shop-price b{font-size:17px}
.dukan-kv span{width:76px}
/* A price RANGE is twice the characters of the single price .answer-rupee was
   sized for on /bhav and /product. At its inherited 38px, "₹266–₹275" wraps to
   two lines inside the 200px info column left over beside the photo on a 390px
   phone. Only the range is shrunk, and only here — on desktop the column is
   wide enough that the full-size number still fits, and that is the number the
   page is for. */
.answer-rupee.rng{font-size:25px;line-height:1.2}
.answer-rupee.rng small{font-size:12px}
}
"""

# One sheet for the hand-built 404 below, same trick product.py uses.
_CSS = _BASE_CSS + _EXTRA_CSS


# ── small helpers ───────────────────────────────────────────

def _img_src(product: dict) -> str:
    """Prefer an admin upload, fall back to a committed file, then to nothing.

    Returning "" rather than a placeholder path matters: a missing static file
    on this site returns 200 with the SPA's HTML, not a 404, so a wrong <img>
    src fails silently and invisibly. No src at all is at least honest.
    """
    if product.get("has_image"):
        return f"{BASE}/img/{product['image_id']}.webp"
    return product.get("image_url") or ""


def _photo_block(product: dict, cls: str) -> str:
    src = _img_src(product)
    if not src:
        # An emoji tile is a real fallback, not a broken-image icon.
        return (f'<div class="{cls}" style="display:flex;align-items:center;'
                f'justify-content:center;font-size:44px">{escape(product.get("emoji") or "🛒")}</div>')
    return (f'<div class="{cls}"><img src="{escape(src)}" '
            f'alt="{escape(product["name_hi"])}" loading="lazy" width="240" height="240"></div>')


def _price_range(product: dict) -> str:
    lo, hi = product.get("min_price"), product.get("max_price")
    if lo is None:
        return "—"
    return f"₹{lo}" if lo == hi else f"₹{lo}–₹{hi}"


def _hub_card(product: dict) -> str:
    """The /product/ hub card, told what this section actually knows: a price
    range across shops instead of one price, and how many shops have it."""
    shops = product["shops"]
    return f"""<a class="prod-card" href="{BASE}/{product['slug']}">
{_photo_block(product, "prod-card-photo")}
<div class="prod-card-body">
<div class="prod-card-name">{escape(product['name_hi'])}</div>
<span class="prod-card-en">{escape(product['name_en'] or '')}</span>
<div class="prod-card-price"><b>{_price_range(product)}</b></div>
<div class="prod-card-unit">{shops} दुकान{'ों' if shops > 1 else ''} में उपलब्ध</div>
</div>
</a>"""


def _shop_row(product_slug: str, offer: dict) -> str:
    """One shop's row on a product page.

    data-lat/data-lon ride on the element so the client can re-sort by real
    distance the moment km_geo is known — the same server-renders-a-default,
    client-swaps-to-nearest shape the /bhav nearest-mandi panel uses. The
    server has no farmer to measure from, so it must not pretend to.
    """
    tags = []
    if offer["verified"]:
        tags.append('<span class="dukan-tag tick">✓ जाँची हुई दुकान</span>')
    if offer["since"]:
        tags.append(f'<span class="dukan-tag">{escape(offer["since"])}</span>')
    if not offer["in_stock"]:
        tags.append('<span class="dukan-tag out">अभी स्टॉक नहीं</span>')
    tags.append('<span class="dukan-tag km" data-km-tag hidden></span>')

    mrp_html = f'<span class="mrp">₹{offer["mrp"]}</span>' if offer["off"] else ""
    off_html = f'<span class="off">{offer["off"]}% कम</span>' if offer["off"] else ""
    unit = offer["unit_hi"]
    unit_html = f'<span class="unit">{escape(unit)}</span>' if unit else ""
    where = " · ".join(x for x in (offer["district"], offer["state"]) if x)
    note_html = f'<div class="dukan-note">{escape(offer["note"])}</div>' if offer["note"] else ""
    coords = ""
    if offer["lat"] is not None and offer["lon"] is not None:
        coords = f' data-lat="{offer["lat"]}" data-lon="{offer["lon"]}"'

    return f"""<a class="dukan-shop" href="{BASE}/{product_slug}/{offer['shop_slug']}"{coords}>
<div class="dukan-shop-main">
<div class="dukan-shop-name">{escape(offer['shop_name'])}</div>
<span class="dukan-shop-where">📍 {escape(where)}</span>
<div class="dukan-shop-meta">{''.join(tags)}</div>
{note_html}
</div>
<div class="dukan-shop-price"><b>₹{offer['price']}</b>{mrp_html}{off_html}{unit_html}</div>
</a>"""


# The client-side nearest sort. Kept inline and dependency-free: this is the
# one thing on the page that must work before any other script loads, and a
# farmer who has not shared location must still see a complete, ordered list.
_NEAR_JS = """
<script>
(function(){
  var geo; try { geo = JSON.parse(localStorage.getItem("km_geo")||"null"); } catch(e){ geo = null; }
  var list = document.getElementById("dukan-shops");
  if (!list) return;
  function km(a,b,c,d){
    var R=6371,p=Math.PI/180,x=(c-a)*p,y=(d-b)*p;
    var h=Math.sin(x/2)*Math.sin(x/2)+Math.cos(a*p)*Math.cos(c*p)*Math.sin(y/2)*Math.sin(y/2);
    return 2*R*Math.asin(Math.sqrt(h));
  }
  function sort(lat,lon){
    var rows=[].slice.call(list.children), any=false;
    rows.forEach(function(r){
      var la=parseFloat(r.getAttribute("data-lat")), lo=parseFloat(r.getAttribute("data-lon"));
      if(isNaN(la)||isNaN(lo)){ r._km=Infinity; return; }
      r._km=km(lat,lon,la,lo); any=true;
      var tag=r.querySelector("[data-km-tag]");
      if(tag){ tag.textContent=(r._km<1?"1 किमी से कम":Math.round(r._km)+" किमी दूर"); tag.hidden=false; }
    });
    if(!any) return;
    rows.sort(function(a,b){ return (a._km-b._km) || 0; });
    rows.forEach(function(r){ list.appendChild(r); });
    var hint=document.getElementById("dukan-geo-hint");
    if(hint) hint.innerHTML="\\u2705 आपके सबसे नज़दीक की दुकान सबसे ऊपर है।";
  }
  if(geo && geo.lat && geo.lon){ sort(geo.lat, geo.lon); return; }
  var btn=document.getElementById("dukan-geo-btn");
  if(!btn||!navigator.geolocation) return;
  btn.addEventListener("click", function(){
    btn.textContent="ढूँढ रहे हैं…";
    navigator.geolocation.getCurrentPosition(function(pos){
      var lat=pos.coords.latitude, lon=pos.coords.longitude;
      try{ localStorage.setItem("km_geo", JSON.stringify(
        {status:"ok",lat:lat,lon:lon,location:"",ts:Date.now()})); }catch(e){}
      sort(lat,lon);
    }, function(){ btn.textContent="जगह नहीं मिली"; }, {timeout:8000, maximumAge:600000});
  });
})();
</script>"""


def _not_found(message: str, sub: str) -> HTMLResponse:
    """A shop can close and a product can be dropped while Google still holds
    the URL — send that farmer into the directory instead of a dead end."""
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="hi">
<head>
{_ANALYTICS}
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(message)} | कृषि मित्र</title>
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
<h1>{escape(message)}</h1>
<p class="hero-sub">{escape(sub)}</p>
</div>
</div>
<div class="cta-row">
<a class="btn btn-app" href="{BASE}">कृषि दुकान खोलें</a>
</div>
</div>
{_footer()}
</body>
</html>""", status_code=404)


# ── /krashi_dukan/img/{id}.webp ─────────────────────────────
# Declared before the {product}/{shop} routes: FastAPI matches in registration
# order, so "img" would otherwise be read as a product slug.

@router.get("/krashi_dukan/img/{catalog_id}.webp")
def catalog_image(catalog_id: int, db: Session = Depends(get_db)):
    """An admin-uploaded catalogue photo, out of Postgres.

    Stored in the DB rather than on disk for the reason profile.py's avatars
    already learned: Render's free tier wipes uploads/ on every restart, so a
    photo on disk is a photo that disappears at the next deploy.
    """
    row = db.query(DukanCatalog).filter(DukanCatalog.id == catalog_id).first()
    if not row or not row.image_data:
        return Response(status_code=404)
    try:
        blob = base64.b64decode(row.image_data)
    except (ValueError, TypeError):
        return Response(status_code=404)
    return Response(content=blob, media_type=row.image_mime or "image/webp",
                    headers={"Cache-Control": "public, max-age=86400"})


# ── /krashi_dukan/sitemap.xml ───────────────────────────────

@router.get("/krashi_dukan/sitemap.xml")
def dukan_sitemap(db: Session = Depends(get_db)):
    """Only the hub and the product pages.

    The per-shop offer pages are deliberately absent, and noindex on top of
    that: twenty shops across thirty products is six hundred near-identical
    URLs, which is index bloat on a site that spent a year earning its
    indexation. The farmer reaches them by tapping; Google does not need them.
    """
    products = dukan.stocked_products(db)
    urls = [f"  <url><loc>{BASE}</loc><changefreq>daily</changefreq></url>"]
    urls += [f"  <url><loc>{BASE}/{p['slug']}</loc><changefreq>daily</changefreq></url>"
             for p in products]
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
           + "\n".join(urls) + "\n</urlset>")
    return Response(content=xml, media_type="application/xml",
                    headers={"Cache-Control": "public, max-age=3600"})


# ── /krashi_dukan — the hub ─────────────────────────────────

@router.get("/krashi_dukan", response_class=HTMLResponse)
@router.get("/krashi_dukan/", response_class=HTMLResponse)
def dukan_hub(db: Session = Depends(get_db)):
    products = dukan.stocked_products(db)
    shops = len({s.slug for s in dukan.shop_all(db, only_live=True)})

    by_cat: dict = {}
    for p in products:
        by_cat.setdefault(p["cat"], []).append(p)

    jump_chips, sections = [], []
    for cat, label in CAT_LABELS.items():
        rows = by_cat.get(cat) or []
        if not rows:
            continue
        jump_chips.append(f'<a class="hub-filter-btn" href="#cat-{cat}">{escape(label)}</a>')
        cards = "".join(_hub_card(p) for p in rows)
        sections.append(f'<h2 id="cat-{cat}">{escape(label)} ({len(rows)})</h2>'
                        f'<div class="prod-grid">{cards}</div>')

    if not products:
        # An empty directory must say so plainly rather than render a hub with
        # no cards, and must not be indexed while it has nothing in it.
        sections.append(
            '<h2>अभी कोई दुकान नहीं जुड़ी है</h2>'
            '<p class="desc">हम अभी आपके ज़िले की दुकानें जोड़ रहे हैं। '
            'दुकान चलाते हैं और अपना सामान यहाँ दिखाना चाहते हैं? नीचे दिए नंबर पर संपर्क करें।</p>')

    title = _fit(f"कृषि दुकान — नज़दीकी दुकानों में बीज, खाद व दवा के भाव",
                 "कृषि दुकान — नज़दीकी दुकानों के भाव",
                 "कृषि दुकान — नज़दीकी दुकानों के रेट")
    desc = (f"आपके ज़िले की {shops} दुकानों में बीज, खाद, कीटनाशक व उपकरण के आज के भाव। "
            f"दाम देखें, नज़दीकी दुकान चुनें और सीधे दुकान पर जाकर खरीदें।"
            if shops else
            "आपके ज़िले की दुकानों में बीज, खाद, कीटनाशक व उपकरण के भाव — "
            "दाम देखें और सीधे नज़दीकी दुकान से खरीदें।")

    body = f"""<div class="hero nophoto">
<div class="hero-body">
<h1>कृषि दुकान — नज़दीकी दुकानों के भाव</h1>
<p class="hero-sub">🏪 {shops} दुकानें · {len(products)} उत्पाद · दाम की तुलना करें, सीधे दुकान से खरीदें</p>
</div>
</div>
<div class="hub-filter-row">
{"".join(jump_chips)}
</div>
{"".join(sections)}
<div class="dukan-disclaimer"><b>ध्यान दें:</b> {escape(DISCLAIMER)}</div>"""

    return _doc(title, desc, BASE,
                f'<a href="{SITE}/">कृषि मित्र</a> › कृषि दुकान', body,
                _ld(_crumb_ld([("कृषि मित्र", f"{SITE}/"), ("कृषि दुकान", BASE)])),
                active="shop", extra_css=_EXTRA_CSS,
                robots="" if products else "noindex,follow",
                footer_note="दुकानों के भाव दुकानदार के बताए अनुसार — खरीदने से पहले दुकान पर पुष्टि कर लें।")


# ── /krashi_dukan/{product} — the product page ──────────────

@router.get("/krashi_dukan/{product_slug}", response_class=HTMLResponse)
def dukan_product(product_slug: str, db: Session = Depends(get_db)):
    row = dukan.catalog_get(db, product_slug)
    if not row or not row.active:
        return _not_found("यह उत्पाद अभी उपलब्ध नहीं है",
                          "हो सकता है यह हटा दिया गया हो या लिंक पुराना हो।")

    offers = dukan.offers_for_product(db, row.slug)
    product = {
        "slug": row.slug, "name_hi": row.name_hi, "name_en": row.name_en or "",
        "emoji": row.emoji or "🛒", "unit_hi": row.unit_hi or "",
        "desc_hi": row.desc_hi or "", "image_url": row.image_url or "",
        "has_image": bool(row.image_mime), "image_id": row.id,
        "min_price": min((o["price"] for o in offers), default=None),
        "max_price": max((o["price"] for o in offers), default=None),
        "shops": len(offers),
    }
    cat_label = CAT_LABELS.get(row.cat, row.cat)
    canon = f"{BASE}/{row.slug}"

    if offers:
        shop_rows = "".join(_shop_row(row.slug, o) for o in offers)
        geo_hint = ('<p class="dukan-geo-hint" id="dukan-geo-hint">'
                    'दूरी के हिसाब से लगाने के लिए अपनी जगह बताएं '
                    '<button class="dukan-geo-btn" id="dukan-geo-btn" type="button">'
                    '📍 मेरे पास की दुकानें</button></p>')
        shops_html = (f'<h2>यह सामान किन दुकानों में है ({len(offers)})</h2>'
                      f'{geo_hint}'
                      f'<div class="dukan-shops" id="dukan-shops">{shop_rows}</div>')
    else:
        shops_html = ('<h2>अभी किसी दुकान ने यह सामान नहीं जोड़ा</h2>'
                      '<p class="desc">हम आपके इलाके की दुकानें जोड़ रहे हैं। '
                      'थोड़े दिन बाद फिर देखें।</p>')

    faqs = [
        (f"{row.name_hi} का भाव कितना है?",
         (f"कृषि मित्र पर जुड़ी दुकानों में {row.name_hi} का भाव "
          f"{_price_range(product)} के बीच है। हर दुकान का अपना भाव है — ऊपर की सूची में "
          f"अपनी नज़दीकी दुकान का दाम देखें।")
         if offers else
         f"{row.name_hi} के लिए अभी किसी जुड़ी दुकान ने भाव नहीं दिया है।"),
        ("क्या कृषि मित्र से सामान ऑर्डर कर सकते हैं?",
         "नहीं। कृषि मित्र सिर्फ़ बताता है कि कौन-सी दुकान में सामान किस दाम पर है। "
         "खरीद सीधे दुकान से होती है — कृषि मित्र न सामान बेचता है, न डिलीवरी करता है, "
         "न किसी सामान की गारंटी लेता है।"),
        ("दुकान का भाव कब का है?",
         "भाव दुकानदार के बताए अनुसार होता है और बदल सकता है। दुकान पर जाने से पहले "
         "फ़ोन करके भाव और स्टॉक की पुष्टि कर लेना सबसे अच्छा है।"),
    ]
    faq_html, faq_ld = _faq(faqs)

    blocks = [_crumb_ld([("कृषि मित्र", f"{SITE}/"), ("कृषि दुकान", BASE),
                         (row.name_hi, canon)]), faq_ld]
    if offers:
        # AggregateOffer, not Offer: the price is a range across independent
        # shops and the seller is never us. Naming ourselves as seller here
        # would be a false claim in structured data.
        blocks.append({
            "@context": "https://schema.org", "@type": "Product",
            "name": f"{row.name_en or row.name_hi} — {row.name_hi}",
            "description": row.desc_hi or row.name_hi,
            **({"image": _img_src(product)} if _img_src(product) else {}),
            "offers": {
                "@type": "AggregateOffer", "priceCurrency": "INR",
                "lowPrice": str(product["min_price"]),
                "highPrice": str(product["max_price"]),
                "offerCount": str(len(offers)), "url": canon,
            },
        })
    ld = _ld(*blocks)

    title = _fit(f"{row.name_hi} का भाव — नज़दीकी दुकान में कीमत",
                 f"{row.name_hi} — नज़दीकी दुकान का भाव",
                 f"{row.name_hi} का भाव")
    desc = (f"{row.name_hi} का भाव {len(offers)} दुकानों में {_price_range(product)}। "
            f"अपने ज़िले की नज़दीकी दुकान का दाम देखें, फ़ोन नंबर लें और सीधे दुकान से खरीदें।"
            if offers else
            f"{row.name_hi} किन दुकानों में मिलेगा — कृषि मित्र पर अपने ज़िले की "
            f"दुकानों के भाव देखें और सीधे दुकान से खरीदें।")[:162]

    # "rng" only when the shops actually disagree — a single price keeps the
    # full-size number the /bhav and /product heroes use.
    rng = _price_range(product)
    unit_small = f'<small>/{escape(row.unit_hi)}</small>' if row.unit_hi else ""
    price_line = (f'<div class="answer-rupee{" rng" if "–" in rng else ""}">'
                  f'{rng}{unit_small}</div>')
    desc_html = f'<p class="desc">{escape(row.desc_hi)}</p>' if row.desc_hi else ""

    body = f"""<section class="answer">
<div class="answer-prod-split">
{_photo_block(product, "answer-prod-photo-lg")}
<div class="answer-prod-info">
<h1>{escape(product['emoji'])} {escape(row.name_hi)}</h1>
<p class="answer-sub">{escape(cat_label)}{f" · {escape(row.name_en)}" if row.name_en else ""}</p>
<div class="answer-price">{price_line}</div>
<div class="answer-range">
<div><span>दुकानें</span><b>{len(offers)}</b></div>
<div><span>सबसे कम</span><b>{f"₹{product['min_price']}" if offers else "—"}</b></div>
<div><span>इकाई</span><b>{escape(row.unit_hi or "—")}</b></div>
</div>
</div>
</div>
</section>
{desc_html}
{shops_html}
<div class="dukan-disclaimer"><b>ध्यान दें:</b> {escape(DISCLAIMER)}</div>
<h2>अक्सर पूछे जाने वाले सवाल</h2>
{faq_html}
{_NEAR_JS}"""

    crumbs = (f'<a href="{SITE}/">कृषि मित्र</a> › <a href="{BASE}">कृषि दुकान</a> › '
              f'{escape(cat_label)} › {escape(row.name_hi)}')
    return _doc(title, desc, canon, crumbs, body, ld, _img_src(product),
                active="shop", extra_css=_EXTRA_CSS,
                robots="" if offers else "noindex,follow",
                footer_note="भाव दुकानदार के बताए अनुसार — खरीदने से पहले दुकान पर पुष्टि कर लें।")


# ── /krashi_dukan/{product}/{shop} — one shop's price ───────

@router.get("/krashi_dukan/{product_slug}/{shop_slug}", response_class=HTMLResponse)
def dukan_offer(product_slug: str, shop_slug: str, db: Session = Depends(get_db)):
    """NOINDEX, FOLLOW — on purpose, in every state.

    This page is the farmer's destination after he taps a shop: address, phone,
    directions. It is not a search landing page. Every (product × shop) pair
    would otherwise be a URL that differs from its siblings by a shop name and
    a number, which is exactly the near-duplicate pattern that costs a site its
    crawl budget. `follow` keeps the links out of here alive.
    """
    row = dukan.catalog_get(db, product_slug)
    shop = dukan.shop_get(db, shop_slug)
    if not row or not row.active or not shop or not dukan.is_live(shop):
        return _not_found("यह दुकान अभी उपलब्ध नहीं है",
                          "हो सकता है दुकान ने यह सामान हटा दिया हो।")

    offer = next((o for o in dukan.offers_for_product(db, row.slug)
                  if o["shop_slug"] == shop.slug), None)
    if not offer:
        return _not_found("यह सामान इस दुकान में नहीं है",
                          "दूसरी दुकानों में यह सामान देखें।")

    canon = f"{BASE}/{row.slug}/{shop.slug}"
    product = {"name_hi": row.name_hi, "emoji": row.emoji or "🛒",
               "image_url": row.image_url or "", "has_image": bool(row.image_mime),
               "image_id": row.id}
    unit = offer["unit_hi"] or row.unit_hi or ""
    where = " · ".join(x for x in (offer["district"], offer["state"]) if x)

    # Everything else the shop sells, so one tap is not a dead end.
    others = [i for i in dukan.items_for_shop(db, shop.slug)
              if i.product_slug != row.slug]
    others_html = ""
    if others:
        catalog = {c.slug: c for c in dukan.catalog_all(db)}
        cards = []
        for item in others[:12]:
            cat_row = catalog.get(item.product_slug)
            if not cat_row:
                continue
            cards.append(_hub_card({
                "slug": cat_row.slug, "name_hi": cat_row.name_hi,
                "name_en": cat_row.name_en or "", "emoji": cat_row.emoji or "🛒",
                "image_url": cat_row.image_url or "",
                "has_image": bool(cat_row.image_mime), "image_id": cat_row.id,
                "min_price": item.price, "max_price": item.price, "shops": 1,
            }))
        if cards:
            others_html = (f'<h2>इस दुकान का बाकी सामान</h2>'
                           f'<div class="prod-grid">{"".join(cards)}</div>')

    ctas = []
    if offer["phone"]:
        ctas.append(f'<a class="btn btn-app" href="tel:{escape(offer["phone"])}">'
                    f'📞 दुकान को फ़ोन करें</a>')
    if offer["whatsapp"]:
        wa_text = quote(f"नमस्ते, कृषि मित्र पर आपकी दुकान देखी — "
                        f"{row.name_hi} ₹{offer['price']} का भाव है क्या?")
        ctas.append(f'<a class="btn btn-wa" target="_blank" rel="noopener" '
                    f'href="https://wa.me/{escape(offer["whatsapp"])}?text={wa_text}">'
                    f'💬 व्हाट्सऐप करें</a>')
    if offer["address"]:
        maps_q = quote(f"{shop.name} {offer['address']} {where}")
        ctas.append(f'<a class="btn btn-wa" style="background:var(--green-dark)" '
                    f'target="_blank" rel="noopener nofollow" '
                    f'href="https://www.google.com/maps/search/?api=1&query={maps_q}">'
                    f'🗺️ रास्ता देखें</a>')
    ctas.append(f'<a class="btn btn-app" style="background:var(--green-mid)" '
                f'href="{BASE}/{row.slug}">↔ दूसरी दुकानों से दाम मिलाएं</a>')

    kv = [("दुकान", escape(shop.name))]
    if where:
        kv.append(("जगह", escape(where)))
    if offer["address"]:
        kv.append(("पता", escape(offer["address"])))
    if offer["phone"]:
        kv.append(("फ़ोन", escape(offer["phone"])))
    if offer["license_no"]:
        kv.append(("लाइसेंस", escape(offer["license_no"])))
    if offer["since"]:
        kv.append(("कब से", escape(offer["since"])))
    kv_html = "".join(f"<div><span>{k}</span><b>{v}</b></div>" for k, v in kv)

    mrp_html = (f'<div class="answer-delta up">{offer["off"]}% कम</div>'
                if offer["off"] else "")
    stock = "हाँ" if offer["in_stock"] else "अभी नहीं"
    note_html = f'<p class="desc">{escape(offer["note"])}</p>' if offer["note"] else ""

    title = _fit(f"{row.name_hi} — {shop.name}, {offer['district']} में ₹{offer['price']}",
                 f"{row.name_hi} — {shop.name} में ₹{offer['price']}",
                 f"{row.name_hi} — ₹{offer['price']}")
    desc = (f"{shop.name} ({where}) में {row.name_hi} ₹{offer['price']}"
            f"{f' — {unit}' if unit else ''}। दुकान का पता, फ़ोन नंबर और रास्ता देखें।")[:162]

    body = f"""<section class="answer">
<div class="answer-prod-split">
{_photo_block(product, "answer-prod-photo-lg")}
<div class="answer-prod-info">
<h1>{escape(product['emoji'])} {escape(row.name_hi)}</h1>
<p class="answer-sub">🏪 {escape(shop.name)}{f" · {escape(where)}" if where else ""}</p>
<div class="answer-price">
<div class="answer-rupee">₹{offer['price']}{f"<small>/{escape(unit)}</small>" if unit else ""}</div>
{mrp_html}
</div>
<div class="answer-range">
<div><span>MRP</span><b>{f"₹{offer['mrp']}" if offer['mrp'] else "—"}</b></div>
<div><span>स्टॉक</span><b>{stock}</b></div>
<div><span>दुकान</span><b>{"जाँची हुई" if offer["verified"] else "नई"}</b></div>
</div>
</div>
</div>
</section>
{note_html}
<div class="cta-row">{"".join(ctas)}</div>
<div class="dukan-card">
<h3>दुकान की जानकारी</h3>
<div class="dukan-kv">{kv_html}</div>
</div>
<div class="dukan-disclaimer"><b>ध्यान दें:</b> {escape(DISCLAIMER)}</div>
{others_html}"""

    crumbs = (f'<a href="{SITE}/">कृषि मित्र</a> › <a href="{BASE}">कृषि दुकान</a> › '
              f'<a href="{BASE}/{row.slug}">{escape(row.name_hi)}</a> › {escape(shop.name)}')
    return _doc(title, desc, canon, crumbs, body,
                _ld(_crumb_ld([("कृषि मित्र", f"{SITE}/"), ("कृषि दुकान", BASE),
                               (row.name_hi, f"{BASE}/{row.slug}"), (shop.name, canon)])),
                _img_src(product), active="shop", extra_css=_EXTRA_CSS,
                robots="noindex,follow",
                footer_note="भाव दुकानदार के बताए अनुसार — खरीदने से पहले दुकान पर पुष्टि कर लें।")
