# ============================================================
# routes/bhav.py
# Krishi Mitra — SEO price pages ("aaj ka mandi bhav")
#
# Server-rendered, indexable pages at /bhav/{commodity}/{district}
# targeting the daily "गेहूं का भाव मेरठ / gehu ka rate meerut"
# searches. Reached via the Netlify proxy rule /bhav/* → backend
# (same 200-rewrite pattern as /share/*), so the public URL stays
# https://krashimitra.in/bhav/wheat/meerut while FastAPI renders it.
#
# Pages exist ONLY for (commodity, district) combos present in the
# mandi_prices snapshot — anything else 404s, so we never publish
# thin/empty doorway pages.
#
# Also serves /bhav/sitemap.xml (all live combos, daily lastmod)
# and a /bhav/ hub page as a single crawlable entry point.
# ============================================================

import re
import time
from datetime import date
from html import escape
from urllib.parse import quote

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, Response

from backend.database.db import SessionLocal, MandiPrice
from backend.services.mandi_service import get_mandi_prices
from backend.routes.share import _crop_image, _HI_CROP_EN

router = APIRouter()

SITE = "https://krashimitra.in"

# English commodity keyword → Hindi display name (reverse of share.py's
# _HI_CROP_EN, plus data.gov spellings that differ from the chip names).
_EN_HI = {en: hi for hi, en in _HI_CROP_EN.items()}
_EN_HI.update({
    "soyabean": "सोयाबीन", "bengal gram": "चना", "gram": "चना",
    "green gram": "मूंग", "black gram": "उड़द", "red gram": "अरहर",
    "tur": "अरहर", "arhar dal": "अरहर", "masur": "मसूर", "lentil": "मसूर",
    "rice": "चावल", "dhan": "धान", "maize": "मक्का", "corn": "मक्का",
    "mustard": "सरसों", "rapeseed": "सरसों", "garlic": "लहसुन",
    "chilly": "मिर्च", "chilli": "मिर्च", "dry chillies": "सूखी मिर्च",
    "turmeric": "हल्दी", "ginger": "अदरक", "banana": "केला",
    "tomato": "टमाटर", "brinjal": "बैंगन", "cauliflower": "फूलगोभी",
    "cabbage": "पत्तागोभी", "bajra": "बाजरा", "pearl millet": "बाजरा",
    "jowar": "ज्वार", "sorghum": "ज्वार", "barley": "जौ", "jau": "जौ",
    "sugarcane": "गन्ना", "cotton": "कपास", "groundnut": "मूंगफली",
    "peas": "मटर", "green peas": "हरी मटर", "apple": "सेब",
    "mango": "आम", "lemon": "नींबू", "coriander": "धनिया",
})

_HI_MONTHS = ["जनवरी", "फरवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई",
              "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"]


def _hindi_name(commodity: str) -> str:
    """Best-effort Hindi display name; falls back to the English name."""
    cl = (commodity or "").lower()
    if cl in _EN_HI:
        return _EN_HI[cl]
    for en, hi in _EN_HI.items():           # substring match: "Wheat(Desi)" → गेहूं
        if en in cl:
            return hi
    return commodity


def _slugify(text: str) -> str:
    """'Sri Ganganagar' → 'sri-ganganagar'; 'Bengal Gram(Gram)' → 'bengal-gram-gram'."""
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower())
    return s.strip("-")


def _hindi_date(d: date) -> str:
    return f"{d.day} {_HI_MONTHS[d.month - 1]} {d.year}"


def _num(v) -> float | None:
    try:
        n = float(str(v).replace(",", ""))
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


# ── Slug map: (commodity_slug, district_slug) → names ────────
# Built from SELECT DISTINCT on the snapshot table; refreshed every
# 6h (data changes once a day). Also powers the sitemap + hub page.
_slug_map: dict[tuple[str, str], tuple[str, str]] = {}
_slug_map_ts: float = 0.0
_SLUG_TTL = 6 * 3600


def _get_slug_map() -> dict:
    global _slug_map, _slug_map_ts
    if _slug_map and (time.time() - _slug_map_ts) < _SLUG_TTL:
        return _slug_map
    db = SessionLocal()
    try:
        rows = (db.query(MandiPrice.commodity, MandiPrice.district)
                  .filter(MandiPrice.commodity.isnot(None),
                          MandiPrice.district.isnot(None))
                  .distinct().all())
    finally:
        db.close()
    m = {}
    for commodity, district in rows:
        cs, ds = _slugify(commodity), _slugify(district)
        if cs and ds:
            m[(cs, ds)] = (commodity, district)
    if m:                       # keep the stale map if the DB comes back empty
        _slug_map, _slug_map_ts = m, time.time()
    return _slug_map


def _related_links(c_slug: str, d_slug: str, commodity: str, district: str) -> str:
    """Same crop in other districts + other crops in this district."""
    m = _get_slug_map()
    hi = _hindi_name(commodity)

    same_crop = [(ds, dn) for (cs, ds), (_, dn) in m.items()
                 if cs == c_slug and ds != d_slug][:8]
    same_dist = [(cs, cn) for (cs, ds), (cn, _) in m.items()
                 if ds == d_slug and cs != c_slug][:8]

    out = []
    if same_crop:
        links = " ".join(
            f'<a href="/bhav/{c_slug}/{ds}">{escape(hi)} भाव {escape(dn)}</a>'
            for ds, dn in same_crop)
        out.append(f'<h2>अन्य मंडियों में {escape(hi)} का भाव</h2><p class="links">{links}</p>')
    if same_dist:
        links = " ".join(
            f'<a href="/bhav/{cs}/{d_slug}">{escape(_hindi_name(cn))} भाव {escape(district)}</a>'
            for cs, cn in same_dist)
        out.append(f'<h2>{escape(district)} मंडी में अन्य फसलों के भाव</h2><p class="links">{links}</p>')
    return "\n".join(out)


_CSS = """
:root{--g:#1b7a3d;--bg:#f6faf6;--line:#e0e8e0;--txt:#213021}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;background:var(--bg);color:var(--txt);line-height:1.55}
.wrap{max-width:860px;margin:0 auto;padding:16px}
header.top{background:var(--g);color:#fff;padding:10px 16px}
header.top a{color:#fff;text-decoration:none;font-weight:700}
h1{font-size:1.35rem;margin:14px 0 2px}
.date{color:#5a6b5a;font-size:.92rem;margin-bottom:12px}
.sum{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0}
.sum .card{background:#fff;border:1px solid var(--line);border-radius:10px;padding:10px 14px;flex:1;min-width:110px;text-align:center}
.sum .card b{display:block;font-size:1.15rem;color:var(--g)}
.sum .card span{font-size:.8rem;color:#5a6b5a}
.tblwrap{overflow-x:auto;background:#fff;border:1px solid var(--line);border-radius:10px}
table{width:100%;border-collapse:collapse;font-size:.92rem;min-width:520px}
th,td{padding:8px 10px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}
th{background:#eef5ee;font-size:.82rem}
td.modal{font-weight:700;color:var(--g)}
.up{color:#1b7a3d;font-size:.82rem}.dn{color:#c0392b;font-size:.82rem}
svg.spark{vertical-align:middle}
.share{display:inline-block;background:#25d366;color:#fff;font-weight:700;padding:10px 18px;border-radius:24px;text-decoration:none;margin:16px 0}
h2{font-size:1.05rem;margin:20px 0 8px}
.links a{display:inline-block;background:#fff;border:1px solid var(--line);border-radius:16px;padding:4px 12px;margin:3px 4px 3px 0;text-decoration:none;color:var(--g);font-size:.88rem}
.faq{background:#fff;border:1px solid var(--line);border-radius:10px;padding:4px 14px;margin:8px 0}
.faq h3{font-size:.95rem;margin:10px 0 4px}
.faq p{font-size:.9rem;color:#445444;margin-bottom:10px}
footer{margin:24px 0 12px;font-size:.85rem;color:#5a6b5a}
footer a{color:var(--g)}
.note{font-size:.8rem;color:#7a8a7a;margin-top:10px}
"""


def _sparkline(points: list[str]) -> str:
    """Inline SVG sparkline from the row's 7-day modal history."""
    vals = [v for v in (_num(p) for p in points) if v is not None]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    w, h = 64, 18
    step = w / (len(vals) - 1)
    pts = " ".join(f"{i * step:.1f},{h - 2 - (v - lo) / span * (h - 4):.1f}"
                   for i, v in enumerate(vals))
    color = "#1b7a3d" if vals[-1] >= vals[0] else "#c0392b"
    return (f'<svg class="spark" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'<polyline fill="none" stroke="{color}" stroke-width="1.5" points="{pts}"/></svg>')


@router.get("/bhav/sitemap.xml")
def bhav_sitemap():
    m = _get_slug_map()
    today = date.today().isoformat()
    urls = "\n".join(
        f"  <url><loc>{SITE}/bhav/{cs}/{ds}</loc>"
        f"<lastmod>{today}</lastmod><changefreq>daily</changefreq></url>"
        for (cs, ds) in sorted(m))
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
           f'{urls}\n</urlset>')
    return Response(content=xml, media_type="application/xml",
                    headers={"Cache-Control": "public, max-age=3600"})


@router.get("/bhav/", response_class=HTMLResponse)
@router.get("/bhav", response_class=HTMLResponse)
def bhav_hub():
    """Crawlable hub: every commodity with its district links."""
    m = _get_slug_map()
    by_crop: dict[str, list] = {}
    for (cs, ds), (cn, dn) in sorted(m.items()):
        by_crop.setdefault(cs, []).append((cn, ds, dn))

    sections = []
    for cs, rows in sorted(by_crop.items()):
        cn = rows[0][0]
        hi = _hindi_name(cn)
        links = " ".join(f'<a href="/bhav/{cs}/{ds}">{escape(dn)}</a>'
                         for _, ds, dn in rows)
        sections.append(f"<h2>{escape(hi)} ({escape(cn)})</h2>"
                        f'<p class="links">{links}</p>')

    today_hi = _hindi_date(date.today())
    body = "\n".join(sections) or "<p>डेटा लोड हो रहा है — कृपया थोड़ी देर बाद देखें।</p>"
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="hi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>आज का मंडी भाव — सभी फसलें व मंडियां | कृषि मित्र</title>
<meta name="description" content="{today_hi}: गेहूं, धान, प्याज, आलू समेत सभी फसलों का ताजा मंडी भाव — जिला चुनें और आज का रेट देखें। रोज़ अपडेट।">
<link rel="canonical" href="{SITE}/bhav/">
<style>{_CSS}</style>
</head>
<body>
<header class="top"><a href="{SITE}/">🌾 कृषि मित्र</a></header>
<div class="wrap">
<h1>आज का मंडी भाव — फसल और मंडी चुनें</h1>
<p class="date">📅 {today_hi} · रोज़ सुबह अपडेट (स्रोत: data.gov.in)</p>
{body}
<footer><a href="{SITE}/mandi.html">📊 मंडी भाव ऐप में देखें</a> · <a href="{SITE}/">कृषि मित्र होम</a></footer>
</div>
</body>
</html>""", headers={"Cache-Control": "public, max-age=3600"})


@router.get("/bhav/{c_slug}/{d_slug}", response_class=HTMLResponse)
def bhav_page(c_slug: str, d_slug: str):
    names = _get_slug_map().get((c_slug.lower(), d_slug.lower()))
    if not names:
        return HTMLResponse(
            '<!DOCTYPE html><html lang="hi"><head><meta charset="utf-8">'
            '<title>पेज नहीं मिला | कृषि मित्र</title>'
            '<meta name="robots" content="noindex"></head>'
            f'<body><p>यह भाव पेज उपलब्ध नहीं है। <a href="{SITE}/bhav/">सभी मंडी भाव देखें →</a></p>'
            "</body></html>", status_code=404)

    commodity, district = names
    data   = get_mandi_prices(commodity, district, "")
    prices = (data or {}).get("prices") or []
    if not prices:                       # snapshot aged out since map was built
        return HTMLResponse("<p>No data</p>", status_code=404)

    hi        = _hindi_name(commodity)
    state     = prices[0].get("state", "")
    today_hi  = _hindi_date(date.today())
    data_date = prices[0].get("date", "-")
    canon     = f"{SITE}/bhav/{c_slug}/{d_slug}"

    modals = [v for v in (_num(p["modal_price"]) for p in prices) if v]
    mins   = [v for v in (_num(p["min_price"])   for p in prices) if v]
    maxs   = [v for v in (_num(p["max_price"])   for p in prices) if v]
    avg_modal = round(sum(modals) / len(modals)) if modals else None
    lo        = round(min(mins))  if mins else None
    hie       = round(max(maxs))  if maxs else None

    # ── market rows ──
    rows_html = []
    for p in prices:
        arrow = ""
        try:
            pct = float(p.get("change_pct"))
            if pct:
                cls  = "up" if pct > 0 else "dn"
                sym  = "▲" if pct > 0 else "▼"
                sign = "+" if pct > 0 else ""
                arrow = f' <span class="{cls}">{sym}{sign}{pct:g}%</span>'
        except (TypeError, ValueError):
            pass
        rows_html.append(
            "<tr>"
            f"<td>{escape(p.get('market', '-'))}</td>"
            f"<td>{escape(p.get('variety', '-'))}</td>"
            f"<td>₹{escape(p.get('min_price', '-'))}</td>"
            f"<td class=\"modal\">₹{escape(p.get('modal_price', '-'))}{arrow}</td>"
            f"<td>₹{escape(p.get('max_price', '-'))}</td>"
            f"<td>{_sparkline(p.get('spark') or [])}</td>"
            "</tr>")
    table = "\n".join(rows_html)

    # ── summary cards ──
    cards = []
    if avg_modal:
        cards.append(f'<div class="card"><b>₹{avg_modal:,}</b><span>औसत भाव/क्विंटल</span></div>')
    if lo:
        cards.append(f'<div class="card"><b>₹{lo:,}</b><span>न्यूनतम</span></div>')
    if hie:
        cards.append(f'<div class="card"><b>₹{hie:,}</b><span>अधिकतम</span></div>')
    cards.append(f'<div class="card"><b>{len(prices)}</b><span>मंडियां</span></div>')
    summary = f'<div class="sum">{"".join(cards)}</div>'

    # ── FAQ: visible markup AND JSON-LD generated from this ONE list ──
    price_txt = (f"औसतन ₹{avg_modal:,} प्रति क्विंटल (₹{lo:,} से ₹{hie:,} तक)"
                 if avg_modal and lo and hie else "ऊपर तालिका में मंडीवार भाव देखें")
    faqs = [
        (f"आज {district} में {hi} का भाव क्या है?",
         f"{today_hi} को {district} की मंडियों में {hi} का भाव {price_txt} है। "
         f"यह भाव {len(prices)} मंडियों की सरकारी रिपोर्ट पर आधारित है।"),
        (f"{hi} का न्यूनतम और अधिकतम रेट कितना है?",
         (f"आज {district} में {hi} का न्यूनतम भाव ₹{lo:,} और अधिकतम भाव ₹{hie:,} प्रति क्विंटल दर्ज हुआ है।"
          if lo and hie else "मंडीवार न्यूनतम/अधिकतम भाव ऊपर तालिका में दिए गए हैं।")),
        ("यह भाव कब और कहां से अपडेट होता है?",
         "भाव रोज़ सुबह भारत सरकार के data.gov.in (Agmarknet) से अपडेट होते हैं। "
         "जिन मंडियों की रिपोर्ट आज नहीं आई, उनका पिछला भाव दिखता है।"),
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
            {"@type": "ListItem", "position": 2, "name": "मंडी भाव", "item": f"{SITE}/bhav/"},
            {"@type": "ListItem", "position": 3, "name": f"{hi} — {district}", "item": canon}]}

    import json as _json
    ld = (f'<script type="application/ld+json">{_json.dumps(faq_ld, ensure_ascii=False)}</script>\n'
          f'<script type="application/ld+json">{_json.dumps(crumbs_ld, ensure_ascii=False)}</script>')

    title = f"{hi} का भाव आज {district} मंडी में — {commodity} Price Today | कृषि मित्र"
    desc  = (f"{today_hi}: {district} ({state}) में {hi} का ताजा मंडी भाव — "
             + (f"औसत ₹{avg_modal:,}/क्विंटल। " if avg_modal else "")
             + f"{len(prices)} मंडियों के रेट, कल से तुलना और 7-दिन का रुझान। रोज़ अपडेट।")
    og_img = _crop_image(commodity, 960)

    wa_text = quote(f"आज {district} में {hi} का भाव"
                    + (f" — औसत ₹{avg_modal:,}/क्विंटल" if avg_modal else "")
                    + f" ({today_hi})\n{canon}")

    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="hi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title>
<meta name="description" content="{escape(desc)}">
<link rel="canonical" href="{canon}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="कृषि मित्र (KrashiMitra)">
<meta property="og:title" content="{escape(title)}">
<meta property="og:description" content="{escape(desc)}">
<meta property="og:image" content="{escape(og_img)}">
<meta property="og:url" content="{canon}">
<meta property="og:locale" content="hi_IN">
<meta name="twitter:card" content="summary_large_image">
{ld}
<style>{_CSS}</style>
</head>
<body>
<header class="top"><a href="{SITE}/">🌾 कृषि मित्र</a></header>
<div class="wrap">
<h1>आज का {escape(hi)} भाव — {escape(district)} मंडी{f" ({escape(state)})" if state and state != "-" else ""}</h1>
<p class="date">📅 {today_hi} · मंडी रिपोर्ट: {escape(data_date)} · स्रोत: data.gov.in (Agmarknet)</p>
{summary}
<div class="tblwrap">
<table>
<thead><tr><th>मंडी</th><th>किस्म</th><th>न्यूनतम</th><th>मॉडल भाव</th><th>अधिकतम</th><th>7-दिन</th></tr></thead>
<tbody>
{table}
</tbody>
</table>
</div>
<p class="note">सभी भाव ₹ प्रति क्विंटल। ▲▼ = कल के मुकाबले बदलाव।</p>
<a class="share" href="https://wa.me/?text={wa_text}">📲 WhatsApp पर भाव भेजें</a>
<h2>अक्सर पूछे जाने वाले सवाल</h2>
{faq_html}
{_related_links(c_slug.lower(), d_slug.lower(), commodity, district)}
<footer>
<a href="{SITE}/mandi.html?commodity={quote(commodity)}&district={quote(district)}">📊 ऐप में ट्रेंड चार्ट देखें</a>
 · <a href="{SITE}/bhav/">सभी मंडी भाव</a>
 · <a href="{SITE}/chat.html">🤖 खेती का सवाल पूछें</a>
</footer>
</div>
</body>
</html>""", headers={"Cache-Control": "public, max-age=3600"})
