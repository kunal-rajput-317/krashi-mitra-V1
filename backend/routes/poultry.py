# ============================================================
# routes/poultry.py
# अंडे का रेट — /farm/poultry, the second daily-price engine
#
# TWO TIERS, ~35 URLS. THAT IS THE WHOLE POINT.
#   /farm                             the पशुपालन section hub
#   /farm/poultry                     today's egg rate in every NECC zone
#   /farm/poultry/anda-rate/{zone}    one zone: today, trend, last year
#
# DELIBERATELY NOT A TREE. /bhav multiplies crop x state x district into ~14k
# URLs, and the 2026-08-23 read of that index found 72% of impressions stuck
# at positions 4-10 with half the URLs earning five impressions or fewer. So
# this section is capped at what the source actually distinguishes: NECC
# publishes ~34 zones, so there are ~34 leaf pages and there will never be a
# district or state expansion of them. A zone page earns its place because a
# farmer types "लखनऊ अंडा रेट"; a district page underneath it would earn
# nothing and dilute the zone above it.
#
# WHY THIS SECTION EXISTS AT ALL. The egg rate changes every single day and a
# poultry farmer checks it every single morning — which is the one thing the
# crop side never had. /bhav answers a question a farmer asks twice a season;
# this answers one he asks daily, and that is the difference between ~200 new
# visitors a day and visitors who come back.
#
# THE LAYOUT IS /bhav's, NOT A COPY OF IT. Shell, tokens, header, footer, FAQ
# and breadcrumb JSON-LD are imported from bhav.py exactly the way product.py,
# krashi_dukan.py and rental.py import them. _EXTRA_CSS here adds only the
# rate list, which nothing else on the site has.
#
# NECC'S CLARIFICATION TRAVELS WITH THE NUMBERS. The source permits
# republication on the condition that its clarification is reproduced
# alongside. _clarification() renders it on every page that prints a rate, and
# tests/test_poultry.py fails the build if any of them stops doing so. It is
# the licence, not a disclaimer we chose to add.
#
# WE NEVER INVENT A DAY. A zone that did not report simply has no point on the
# chart and no row change — no carry-forward, no interpolation. Same rule
# /bhav follows, and the reason its stale-district rescue shows a real old
# date rather than a fresh-looking wrong one.
# ============================================================

from datetime import date
from html import escape

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from backend.database.db import get_db
from backend.routes.bhav import (
    _axis_band, _crumb_ld, _doc, _faq, _fit, _lead_gen_html, _ld, _sparkline,
    _trend_colour,
)
from backend.services import poultry, poultry_necc

router = APIRouter()

SITE = "https://krashimitra.in"
BASE = f"{SITE}/farm/poultry"

_HI_MONTHS = ("जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई",
              "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर")

# The three poultry guides already on the site. Listed here rather than
# discovered from disk because the order is editorial — a farmer looking up a
# rate is most likely to want the disease page next, not the setup guide.
_GUIDES = [
    ("murgi-ranikhet-rog", "रानीखेत रोग — पहचान, टीका और बचाव",
     "मुर्गियों की सबसे बड़ी जानलेवा बीमारी, और लासोटा/R2B टीके का पूरा शेड्यूल।"),
    ("murgi-palan-guide", "मुर्गी पालन — पूरी गाइड",
     "ब्रॉयलर, लेयर और देसी — नस्ल चुनाव, ब्रूडिंग, फीड और FCR का हिसाब।"),
    ("murgi-palan-backyard", "बैकयार्ड मुर्गी पालन — कम लागत में शुरुआत",
     "10-50 पक्षियों से घर के पिछवाड़े शुरू करने का तरीका और असली खर्च।"),
]

# The rest of the पशुपालन shelf — real pages that already exist. /farm is the
# hub they have never had, not a placeholder for pages nobody has written.
_FARM_SHELF = [
    ("poultry", f"{SITE}/farm/poultry", "🐓", "पोल्ट्री — अंडे का रेट",
     "हर दिन का NECC अंडा रेट, 34 शहरों का, और मुर्गी पालन की गाइड।"),
    ("dairy", f"{SITE}/articles/dairy-farming-doodh-utpadan", "🐄",
     "डेयरी — दूध उत्पादन", "नस्ल, हरा चारा, ब्यांत का प्रबंधन और दूध बढ़ाने का गणित।"),
    ("lumpy", f"{SITE}/articles/pashu-lumpy-skin-rog", "🩺",
     "पशु रोग — लंपी स्किन", "पहचान, फैलाव रोकना और टीकाकरण।"),
    ("bakri", f"{SITE}/articles/bakri-palan-guide", "🐐", "बकरी पालन",
     "कम ज़मीन और कम पूँजी में शुरू होने वाला पालन — नस्ल से बिक्री तक।"),
    ("machhli", f"{SITE}/articles/machhli-palan-guide", "🐟", "मत्स्य पालन",
     "तालाब तैयारी, बीज संचय और फीड — मछली पालन की बुनियाद।"),
    ("madhumakhi", f"{SITE}/articles/madhumakhi-palan-guide", "🐝", "मधुमक्खी पालन",
     "बक्सा, कॉलोनी और शहद निकालने का मौसमी चक्र।"),
]

_EXTRA_CSS = """
.desc{font-size:14px;color:var(--text-mid);margin:14px 0;line-height:1.7}
.egg-list{margin-top:12px;border:1px solid var(--border);border-radius:var(--radius-md);
overflow:hidden;background:var(--white);box-shadow:var(--shadow-sm)}
.egg-row{display:flex;align-items:center;gap:10px;padding:11px 14px;text-decoration:none;
color:inherit;border-top:1px solid var(--border)}
.egg-row:first-child{border-top:none}
.egg-row:hover{background:var(--green-pale)}
.egg-z{flex:1;min-width:0}
.egg-n{display:block;font-size:14px;font-weight:700;color:var(--text-dark);line-height:1.25}
.egg-s{display:block;font-size:11px;color:var(--text-soft);font-weight:600;margin-top:1px}
.egg-p{text-align:right;flex-shrink:0}
.egg-r{display:block;font-size:16px;font-weight:700;color:var(--green-dark);line-height:1.2;white-space:nowrap}
.egg-r small{font-size:10.5px;font-weight:600;color:var(--text-soft);margin-left:2px}
.egg-h{display:block;font-size:10.5px;color:var(--text-soft);font-weight:600;margin-top:1px;white-space:nowrap}
.egg-sec{font-size:12.5px;font-weight:700;color:var(--text-mid);margin:22px 0 0;
display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}
.egg-sec em{font-style:normal;font-weight:600;font-size:11px;color:var(--text-soft)}
.egg-stat{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px}
.egg-stat div{flex:1;min-width:132px;background:var(--white);border:1px solid var(--border);
border-radius:var(--radius-sm);padding:10px 13px;box-shadow:var(--shadow-sm)}
.egg-stat b{display:block;font-size:17px;font-weight:700;color:var(--green-dark);line-height:1.2}
.egg-stat span{font-size:11px;color:var(--text-soft);font-weight:600}
.necc-note{margin-top:22px;padding:13px 15px;border:1px solid var(--border);
border-left:3px solid var(--amber);border-radius:var(--radius-sm);background:var(--cream)}
.necc-note h3{font-size:12.5px;font-weight:700;color:var(--text-dark);margin-bottom:5px}
.necc-note p{font-size:11.5px;color:var(--text-mid);line-height:1.65;margin-bottom:7px}
.necc-note p:last-child{margin-bottom:0}
.necc-note .en{font-size:10.5px;color:var(--text-soft);line-height:1.6}
.shelf{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:12px;margin-top:14px}
.shelf a{display:flex;gap:11px;background:var(--white);border:1px solid var(--border);
border-radius:var(--radius-md);padding:13px 15px;text-decoration:none;color:inherit;
box-shadow:var(--shadow-sm);transition:transform .15s,border-color .15s}
.shelf a:hover{transform:translateY(-2px);border-color:var(--green-light)}
.shelf .ic{font-size:21px;line-height:1}
.shelf b{display:block;font-size:13.5px;font-weight:700;color:var(--text-dark);line-height:1.3}
.shelf small{display:block;font-size:11.5px;color:var(--text-soft);line-height:1.55;margin-top:3px}
@media(max-width:640px){.egg-row{padding:10px 12px}.egg-n{font-size:13.5px}}
"""


# ── small shared bits ───────────────────────────────────────

def _hi_date(d: date) -> str:
    return f"{d.day} {_HI_MONTHS[d.month - 1]} {d.year}"


def _delta_html(change) -> str:
    if not change:
        return ""
    cls, sign = ("up", "▲") if change > 0 else ("dn", "▼")
    return (f'<span class="{cls}">{sign} ₹{abs(change) / 100:.2f}</span>')


def _clarification() -> str:
    """NECC's condition for republishing its numbers. Hindi first because that
    is who reads the page; the English is the text the permission is actually
    on, so it is reproduced verbatim and never summarised away."""
    return (
        '<section class="necc-note">'
        '<h3>🥚 यह रेट कहाँ से आता है</h3>'
        f'<p>{escape(poultry_necc.CLARIFICATION_HI)}</p>'
        f'<p class="en">{escape(poultry_necc.CLARIFICATION)}</p>'
        f'<p class="en">Source: National Egg Co-ordination Committee (NECC) — '
        f'<a href="{poultry_necc.NECC_URL}" rel="nofollow noopener" target="_blank">'
        'e2necc.com</a></p></section>')


def _trend_chart(series: list[dict]) -> str:
    """Daily trend for one zone, in ₹ per 100 eggs (whole rupees, so the axis
    never carries decimals).

    A local chart rather than bhav.py's _chart: that one hardcodes "आज" on its
    right-hand axis, which is true for a mandi page rendered the day of a fetch
    and false here whenever NECC has not published yet. It reuses the same two
    scale primitives, so the two charts stay visually identical while this one
    labels the days it is actually showing.
    """
    if len(series) < 3:
        return ""
    vals = [p["paise"] for p in series]
    w, h = 600, 150
    pad_l, pad_r, pad_t, pad_b = 46, 12, 16, 24
    lo, hi = _axis_band(min(vals), max(vals))
    span = hi - lo
    n = len(vals)

    def x(i): return pad_l + i * (w - pad_l - pad_r) / (n - 1)
    def y(v): return pad_t + (1 - (v - lo) / span) * (h - pad_t - pad_b)

    pts = [(x(i), y(v)) for i, v in enumerate(vals)]
    line = " ".join(f"{px:.1f},{py:.1f}" for px, py in pts)
    area = (f"M{pts[0][0]:.1f},{h - pad_b:.1f} "
            + " ".join(f"L{px:.1f},{py:.1f}" for px, py in pts)
            + f" L{pts[-1][0]:.1f},{h - pad_b:.1f} Z")
    col = _trend_colour([float(v) for v in vals])
    dots = "".join(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3" fill="{col}"/>'
                   for px, py in pts)
    grid = "".join(
        f'<line x1="{pad_l}" y1="{pad_t + f * (h - pad_t - pad_b):.1f}" '
        f'x2="{w - pad_r}" y2="{pad_t + f * (h - pad_t - pad_b):.1f}" '
        f'stroke="#e5e9e6" stroke-width="1"/>'
        f'<text x="{pad_l - 6}" y="{pad_t + f * (h - pad_t - pad_b) + 3.5:.1f}" '
        f'font-size="10" fill="#7c8983" text-anchor="end">₹{round(v):,}</text>'
        for f, v in ((0, hi), (0.5, (hi + lo) / 2), (1, lo)))
    first, last = series[0]["date"], series[-1]["date"]
    return f"""<svg class="chart" viewBox="0 0 {w} {h}" role="img"
 aria-label="{escape(_hi_date(first))} से {escape(_hi_date(last))} तक अंडे के रेट का रुझान">
<defs><linearGradient id="eg" x1="0" y1="0" x2="0" y2="1">
<stop offset="0" stop-color="{col}" stop-opacity=".18"/>
<stop offset="1" stop-color="{col}" stop-opacity="0"/></linearGradient></defs>
{grid}
<path d="{area}" fill="url(#eg)"/>
<polyline points="{line}" fill="none" stroke="{col}" stroke-width="2.5"
 stroke-linecap="round" stroke-linejoin="round"/>
{dots}
<circle cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="5.5" fill="{col}"
 stroke="#fff" stroke-width="2.5"/>
<text x="{pad_l}" y="{h - 7}" font-size="11" fill="#7c8983">{escape(_hi_date(first))}</text>
<text x="{w - pad_r}" y="{h - 7}" font-size="11" fill="#7c8983"
 text-anchor="end">{escape(_hi_date(last))}</text>
</svg>"""


def _rows_html(rows: list[dict]) -> str:
    out = []
    for r in rows:
        spark = _sparkline([str(p) for p in r["spark"]]) if len(r["spark"]) > 1 else ""
        where = " · ".join(x for x in (r["state_hi"],
                                       "खपत केंद्र" if r["centre"] == "CC" else "") if x)
        out.append(
            f'<a class="egg-row" href="{BASE}/anda-rate/{r["slug"]}">'
            f'<span class="egg-z"><span class="egg-n">{escape(r["hi"])}</span>'
            f'<span class="egg-s">{escape(where)}</span></span>'
            f'{spark}'
            f'<span class="egg-p"><span class="egg-r">₹{poultry.rupees(r["paise"])}'
            f'<small>/अंडा</small></span>'
            f'<span class="egg-h">₹{poultry.per_hundred(r["paise"])} प्रति 100 '
            f'{_delta_html(r["change"])}</span></span></a>')
    return f'<div class="egg-list">{"".join(out)}</div>'


def _guides_html() -> str:
    cards = "".join(
        f'<a href="{SITE}/articles/{slug}"><span class="ic">📗</span>'
        f'<span><b>{escape(title)}</b><small>{escape(sub)}</small></span></a>'
        for slug, title, sub in _GUIDES)
    return ('<h2 class="egg-sec">मुर्गी पालन की गाइड</h2>'
            f'<div class="shelf">{cards}</div>')


def _feed_links_html() -> str:
    """Feed is roughly two-thirds of what a poultry farm spends, and both feed
    grains already have live /bhav pages. So this is the honest next question
    after "what is the egg rate" — and it is the link that ties the new section
    to the engine that already ranks."""
    return (
        '<h2 class="egg-sec">दाने का खर्च <em>अंडे के रेट से ज़्यादा यही तय करता है कि '
        'कमाई बचेगी या नहीं</em></h2>'
        '<div class="shelf">'
        f'<a href="{SITE}/bhav/maize"><span class="ic">🌽</span><span>'
        '<b>मक्का का आज का भाव</b><small>पोल्ट्री फीड का सबसे बड़ा हिस्सा — '
        'हर मंडी का रेट।</small></span></a>'
        f'<a href="{SITE}/bhav/soyabean"><span class="ic">🫘</span><span>'
        '<b>सोयाबीन का आज का भाव</b><small>फीड का प्रोटीन हिस्सा — खली का दाम '
        'यहीं से चलता है।</small></span></a>'
        f'<a href="{SITE}/product/#cat-pashu_aahaar"><span class="ic">🛒</span><span>'
        '<b>पशु व पोल्ट्री आहार</b><small>लेयर फीड, ब्रॉयलर फीड और मिनरल '
        'मिक्सचर।</small></span></a>'
        '</div>')


# ── /farm/poultry/sitemap.xml ───────────────────────────────

@router.get("/farm/poultry/sitemap.xml")
def poultry_sitemap(db: Session = Depends(get_db)):
    """The two hubs and every zone that has a rate — nothing speculative.

    Built from what is actually in the snapshot, not from the registry, so the
    sitemap can never advertise a zone page that would render empty. Same rule
    /bhav's sitemap follows.
    """
    day = poultry.updated(db)
    lastmod = f"<lastmod>{day.isoformat()}</lastmod>" if day else ""
    urls = [f"  <url><loc>{SITE}/farm</loc>{lastmod}<changefreq>weekly</changefreq></url>",
            f"  <url><loc>{BASE}</loc>{lastmod}<changefreq>daily</changefreq>"
            f"<priority>0.9</priority></url>"]
    for r in poultry.latest(db):
        urls.append(
            f'  <url><loc>{BASE}/anda-rate/{r["slug"]}</loc>'
            f'<lastmod>{r["date"].isoformat()}</lastmod>'
            f"<changefreq>daily</changefreq><priority>0.8</priority></url>")
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
           + "\n".join(urls) + "\n</urlset>")
    return Response(content=xml, media_type="application/xml",
                    headers={"Cache-Control": "public, max-age=3600"})


# ── /farm — the पशुपालन hub ─────────────────────────────────

@router.get("/farm", response_class=HTMLResponse)
@router.get("/farm/", response_class=HTMLResponse)
def farm_hub(db: Session = Depends(get_db)):
    """The section landing for पशुपालन.

    It exists because /farm/poultry cannot hang off a 404, and it earns its
    own place by being the only page that gathers the livestock guides that
    were scattered across /articles. When a second vertical gets a daily
    number, this is where it goes — the shelf is a list, not a redirect.
    """
    day = poultry.updated(db)
    rows = poultry.latest(db, section="necc")
    # The average is over the NECC-suggested zones only (mixing in prevailing
    # prices would average two different claims), but the LINK counts every
    # zone the table actually shows — promising 24 and landing on 34 is a
    # small lie the farmer notices immediately.
    total = len(poultry.latest(db))
    live = ""
    if rows and day:
        avg = round(sum(r["paise"] for r in rows) / len(rows))
        live = (f'<div class="next-up">आज ({escape(_hi_date(day))}) का औसत NECC अंडा रेट — '
                f'<b>₹{poultry.rupees(avg)} प्रति अंडा</b> '
                f'(₹{poultry.per_hundred(avg)} प्रति 100)। '
                f'<a href="{BASE}" style="color:#fff;text-decoration:underline">'
                f'सभी {total} शहरों का रेट देखें →</a></div>')

    cards = "".join(
        f'<a href="{href}"><span class="ic">{ic}</span><span><b>{escape(title)}</b>'
        f'<small>{escape(sub)}</small></span></a>'
        for _, href, ic, title, sub in _FARM_SHELF)

    body = f"""<section class="answer">
<h1>पशुपालन — दूध, अंडा, बकरी, मछली और मधुमक्खी</h1>
<p class="answer-sub">खेती के साथ चलने वाली कमाई, और उसके रोज़ बदलते दाम</p>
<p class="answer-lead">पशुपालन की कमाई खेती से एक बात में अलग है — यह रोज़ आती है।
अंडा रोज़ बिकता है, दूध रोज़ बिकता है, और दाना रोज़ खरीदना पड़ता है। इसीलिए यहाँ भाव
भी रोज़ का है, सीज़न का नहीं।</p>
{live}
</section>

<h2 class="egg-sec">पशुपालन के विषय</h2>
<div class="shelf">{cards}</div>

<p class="desc">अभी इस हिस्से में रोज़ का भाव सिर्फ़ पोल्ट्री (अंडे) का है, क्योंकि
अंडे का ही रोज़ का राष्ट्रीय रेट प्रकाशित होता है। दूध, बकरी और मछली के दाम इलाके
और सौदे पर तय होते हैं — उनके लिए यहाँ गाइड हैं, झूठा "आज का रेट" नहीं।</p>
"""
    crumbs = _crumb_ld([("होम", f"{SITE}/"), ("पशुपालन", f"{SITE}/farm")])
    return _doc(
        title=_fit("पशुपालन — अंडा रेट, डेयरी, बकरी, मछली व मधुमक्खी पालन",
                   "पशुपालन — अंडा रेट, डेयरी, बकरी व मछली पालन",
                   "पशुपालन — अंडा रेट, डेयरी और बकरी पालन"),
        desc=_fit("रोज़ का अंडा रेट और पशुपालन की पूरी जानकारी — डेयरी, बकरी पालन, "
                  "मत्स्य पालन, मधुमक्खी पालन और पशु रोग की हिंदी गाइड।", limit=162),
        canon=f"{SITE}/farm",
        crumbs=f'<a href="{SITE}/">होम</a> › <span>पशुपालन</span>',
        body=body, ld=_ld(crumbs),
        active="", extra_css=_EXTRA_CSS,
        updated=day.isoformat() if day else "",
        footer_note="अंडे के दाम NECC से रोज़ अपडेट होते हैं। "
                    "बेचने से पहले अपने व्यापारी से रेट की पुष्टि करें।")


# ── /farm/poultry — today's rate, everywhere ────────────────

@router.get("/farm/poultry/anda-rate", response_class=HTMLResponse)
def anda_rate_index():
    """The national table IS the hub, so this guessable URL is a 301 rather
    than a second page saying the same thing — two URLs for one answer is how
    the /bhav index got diluted."""
    return RedirectResponse(BASE, status_code=301)


@router.get("/farm/poultry", response_class=HTMLResponse)
@router.get("/farm/poultry/", response_class=HTMLResponse)
def poultry_hub(db: Session = Depends(get_db)):
    necc = poultry.latest(db, section="necc")
    prevailing = poultry.latest(db, section="prevailing")
    day = poultry.updated(db)

    if not necc and not prevailing:
        # Before the first fetch lands (or if NECC has been unreachable since
        # the very first boot) the page says so instead of rendering an empty
        # table that looks like a rate of zero.
        body = ('<section class="answer"><h1>आज का अंडा रेट</h1>'
                '<p class="answer-lead">आज का रेट अभी उपलब्ध नहीं है। NECC की '
                'दैनिक शीट आने पर यह पेज अपने आप भर जाएगा।</p></section>'
                + _clarification())
        return _doc(title="आज का अंडा रेट — NECC egg rate today",
                    desc="भारत के सभी प्रमुख शहरों का आज का अंडा रेट (NECC egg rate).",
                    canon=BASE, crumbs="", body=body,
                    active="", extra_css=_EXTRA_CSS, robots="noindex, follow")

    rows = necc or prevailing
    avg = round(sum(r["paise"] for r in rows) / len(rows))
    high, low = rows[0], rows[-1]
    changed = [r for r in rows if r["change"]]
    avg_change = (round(sum(r["change"] for r in changed) / len(changed))
                  if changed else 0)

    stats = (
        '<div class="egg-stat">'
        f'<div><b>₹{poultry.rupees(avg)}</b><span>औसत रेट प्रति अंडा</span></div>'
        f'<div><b>₹{poultry.rupees(high["paise"])}</b>'
        f'<span>सबसे ऊँचा — {escape(high["hi"])}</span></div>'
        f'<div><b>₹{poultry.rupees(low["paise"])}</b>'
        f'<span>सबसे कम — {escape(low["hi"])}</span></div>'
        f'<div><b>{len(necc) + len(prevailing)}</b><span>शहर / ज़ोन</span></div>'
        '</div>')

    sections = ""
    if necc:
        sections += ('<h2 class="egg-sec">NECC सुझाया रेट '
                     '<em>NECC का घोषित दाम</em></h2>' + _rows_html(necc))
    if prevailing:
        sections += ('<h2 class="egg-sec">बाज़ार में चल रहा रेट '
                     '<em>Prevailing — जहाँ सौदा असल में हो रहा है</em></h2>'
                     + _rows_html(prevailing))

    faq_html, faq_ld = _faq([
        ("आज अंडे का रेट क्या है?",
         f"{_hi_date(day)} को NECC ज़ोन का औसत रेट ₹{poultry.rupees(avg)} प्रति अंडा "
         f"(₹{poultry.per_hundred(avg)} प्रति 100 अंडे) है। सबसे ऊँचा "
         f"{high['hi']} में ₹{poultry.rupees(high['paise'])} और सबसे कम "
         f"{low['hi']} में ₹{poultry.rupees(low['paise'])} प्रति अंडा है।"),
        ("एक पेटी यानी 100 अंडों का दाम कितना है?",
         f"NECC रेट प्रति 100 अंडे के हिसाब से ही बोला जाता है। आज यह औसतन "
         f"₹{poultry.per_hundred(avg)} है। 30 अंडे की एक ट्रे का दाम इसका लगभग "
         "तीन-दहाई होगा, उसमें ट्रे और ढुलाई अलग जुड़ती है।"),
        ("NECC रेट और दुकान के रेट में फ़र्क क्यों होता है?",
         "NECC का रेट थोक व्यापार के लिए सुझाया गया दाम है, फ़ार्म या मंडी स्तर का। "
         "दुकान तक पहुँचते-पहुँचते उसमें ढुलाई, टूट-फूट और दुकानदार का मुनाफ़ा जुड़ता "
         "है, इसलिए खुदरा दाम हमेशा इससे ऊपर रहता है।"),
        ("क्या यही दाम मुर्गी पालक को मिलता है?",
         "ज़रूरी नहीं। यह ज़ोन का घोषित दाम है; फ़ार्म गेट पर मिलने वाला दाम अंडे के "
         "आकार, ढुलाई और व्यापारी से हुए सौदे पर निर्भर करता है। बेचने से पहले अपने "
         "व्यापारी से रेट की पुष्टि ज़रूर करें।"),
        ("अंडे का रेट रोज़ बदलता क्यों है?",
         "अंडा रखा नहीं जा सकता — जो आज बना है वह आज ही बिकना है। इसलिए दाम रोज़ की "
         "आवक, मौसम, त्योहार और दाने की लागत के साथ रोज़ बदलता है। सर्दी में माँग "
         "बढ़ने से दाम चढ़ते हैं और गर्मी में गिरते हैं।"),
    ])

    body = f"""<section class="answer">
<h1>आज का अंडा रेट — {escape(_hi_date(day))}</h1>
<p class="answer-sub">NECC egg rate today · {len(necc) + len(prevailing)} शहर</p>
<div class="answer-price"><span class="answer-rupee">₹{poultry.rupees(avg)}
<small>प्रति अंडा</small></span>
{f'<span class="answer-delta {"up" if avg_change > 0 else "dn"}">'
 f'{"▲" if avg_change > 0 else "▼"} ₹{abs(avg_change) / 100:.2f} कल से</span>'
 if avg_change else ''}</div>
<p class="answer-lead">यह {len(rows)} NECC ज़ोन का औसत है — ₹{poultry.per_hundred(avg)}
प्रति 100 अंडे। नीचे हर शहर का अपना रेट है; अपने शहर पर टैप करें तो पिछले महीने का
रुझान भी दिखेगा।</p>
</section>

{stats}
{sections}

<h2 class="egg-sec">अकसर पूछे जाने वाले सवाल</h2>
{faq_html}

{_feed_links_html()}
{_guides_html()}
{_lead_gen_html()}
{_clarification()}
"""
    crumbs_ld = _crumb_ld([("होम", f"{SITE}/"), ("पशुपालन", f"{SITE}/farm"),
                           ("अंडे का रेट", BASE)])
    return _doc(
        title=_fit(f"आज का अंडा रेट {_hi_date(day)} — NECC egg rate today",
                   "आज का अंडा रेट — सभी शहर | NECC egg rate today",
                   "आज का अंडा रेट — NECC egg rate today"),
        desc=_fit(f"आज का अंडा रेट: औसत ₹{poultry.rupees(avg)} प्रति अंडा "
                  f"(₹{poultry.per_hundred(avg)} प्रति 100)। "
                  f"{len(necc) + len(prevailing)} शहरों का NECC egg rate today — "
                  f"{high['hi']} सबसे ऊँचा, {low['hi']} सबसे कम।",
                  f"आज का अंडा रेट: औसत ₹{poultry.rupees(avg)} प्रति अंडा। "
                  f"{len(necc) + len(prevailing)} शहरों का NECC egg rate today।",
                  limit=162),
        canon=BASE,
        crumbs=f'<a href="{SITE}/">होम</a> › <a href="{SITE}/farm">पशुपालन</a> '
               '› <span>अंडे का रेट</span>',
        body=body, ld=_ld(crumbs_ld, faq_ld),
        active="", extra_css=_EXTRA_CSS, updated=day.isoformat(),
        footer_note="अंडे के दाम NECC से रोज़ अपडेट होते हैं। "
                    "बेचने से पहले अपने व्यापारी से रेट की पुष्टि करें।")


# ── /farm/poultry/anda-rate/{zone} — one zone ───────────────

@router.get("/farm/poultry/anda-rate/{zone_slug}", response_class=HTMLResponse)
def zone_page(zone_slug: str, db: Session = Depends(get_db)):
    z = poultry.zone(db, zone_slug)
    if not z:
        # A zone we have never stored is not a page — send the farmer to the
        # table that definitely has his city rather than to a 404.
        return RedirectResponse(BASE, status_code=302)

    day = z["date"]
    hi, paise = z["hi"], z["paise"]
    en = zone_slug.replace("-", " ").title()
    series = poultry.series(db, zone_slug, days=30)
    ly = poultry.last_year(db, zone_slug, day)
    all_rows = poultry.latest(db, section=z["section"])
    rank = next((i + 1 for i, r in enumerate(all_rows) if r["slug"] == zone_slug), 0)
    peers = [r for r in poultry.latest(db) if r["slug"] != zone_slug][:6]

    month_vals = [p["paise"] for p in series]
    facts = ['<div class="egg-stat">'
             f'<div><b>₹{poultry.rupees(paise)}</b><span>आज प्रति अंडा</span></div>'
             f'<div><b>₹{poultry.per_hundred(paise)}</b><span>प्रति 100 अंडे</span></div>']
    if month_vals:
        facts.append(f'<div><b>₹{poultry.rupees(max(month_vals))}</b>'
                     '<span>महीने का सबसे ऊँचा</span></div>')
        facts.append(f'<div><b>₹{poultry.rupees(min(month_vals))}</b>'
                     '<span>महीने का सबसे कम</span></div>')
    if rank:
        # Ranked inside its OWN section. A suggested price and a prevailing one
        # are different claims (see the module header), so ordering them in one
        # list would invent a comparison the source does not make.
        rank_lbl = ("NECC ज़ोन में महँगाई का क्रम" if z["section"] == "necc"
                    else "इन शहरों में महँगाई का क्रम")
        facts.append(f'<div><b>{rank} / {len(all_rows)}</b>'
                     f'<span>{rank_lbl}</span></div>')
    facts.append("</div>")

    ly_html = ""
    if ly:
        diff = paise - ly["paise"]
        word = "ज़्यादा" if diff > 0 else "कम"
        ly_html = (
            '<div class="card-w"><div class="card-w-h"><h2>पिछले साल इसी समय</h2>'
            f'<em>{escape(_hi_date(ly["date"]))} के आसपास</em></div>'
            f'<p class="desc">पिछले साल इन्हीं दिनों {escape(hi)} में अंडा लगभग '
            f'₹{poultry.rupees(ly["paise"])} प्रति अंडा था। आज का रेट उससे '
            f'₹{abs(diff) / 100:.2f} {word} है।</p></div>')

    chart_html = ""
    if series:
        chart_html = (
            '<div class="card-w"><div class="card-w-h">'
            '<h2>पिछले 30 दिन का रुझान</h2><em>₹ प्रति 100 अंडे</em></div>'
            + (_trend_chart(series) or
               '<p class="desc">रुझान दिखाने के लिए अभी पर्याप्त दिन नहीं हैं।</p>')
            + '</div>')

    peers_html = ""
    if peers:
        peers_html = ('<h2 class="egg-sec">दूसरे शहरों का आज का रेट</h2>'
                      + _rows_html(peers)
                      + f'<p class="note"><a href="{BASE}">सभी शहरों का अंडा रेट '
                        'देखें →</a></p>')

    section_hi = ("NECC का सुझाया दाम" if z["section"] == "necc"
                  else "बाज़ार में चल रहा दाम (Prevailing)")

    faq_html, faq_ld = _faq([
        (f"आज {hi} में अंडे का रेट क्या है?",
         f"{_hi_date(day)} को {hi} में अंडे का रेट ₹{poultry.rupees(paise)} प्रति "
         f"अंडा है, यानी ₹{poultry.per_hundred(paise)} प्रति 100 अंडे। यह "
         f"{section_hi} है।"),
        (f"{hi} में 100 अंडे का दाम कितना है?",
         f"₹{poultry.per_hundred(paise)}। अंडे का रेट थोक में 100 अंडों के हिसाब से "
         f"ही बोला जाता है, इसलिए ₹{poultry.per_hundred(paise)} और "
         f"₹{poultry.rupees(paise)} प्रति अंडा एक ही दाम हैं।"),
        (f"क्या {hi} का यही रेट पूरे {z['state_hi'] or 'राज्य'} में लागू होता है?",
         f"नहीं। NECC {hi} ज़ोन के लिए दाम घोषित करता है और आसपास के इलाके उसी के "
         "आसपास चलते हैं, पर हर मंडी और हर सौदे का दाम अलग हो सकता है। बेचने से "
         "पहले अपने व्यापारी से पुष्टि करें।"),
        (f"{hi} में अंडे का रेट कब बढ़ता है?",
         "सर्दियों में माँग बढ़ने से दाम आम तौर पर चढ़ते हैं और गर्मियों में गिरते हैं। "
         "इसके अलावा मक्का और सोयाबीन खली महँगी होने पर दाने की लागत बढ़ती है, जो "
         "कुछ हफ़्तों में अंडे के दाम पर दिखती है।"),
    ])

    body = f"""<section class="answer">
<h1>{escape(hi)} में आज का अंडा रेट</h1>
<p class="answer-sub">{escape(en)} egg rate today · {escape(_hi_date(day))}
{f" · {escape(z['state_hi'])}" if z["state_hi"] else ""}</p>
<div class="answer-price"><span class="answer-rupee">₹{poultry.rupees(paise)}
<small>प्रति अंडा</small></span>
{f'<span class="answer-delta {"up" if z["change"] > 0 else "dn"}">'
 f'{"▲" if z["change"] > 0 else "▼"} ₹{abs(z["change"]) / 100:.2f} पिछले दिन से</span>'
 if z["change"] else ''}</div>
<p class="answer-lead">₹{poultry.per_hundred(paise)} प्रति 100 अंडे — यह {section_hi}
है, {escape(_hi_date(day))} का।
{f'इस महीने का औसत ₹{poultry.rupees(z["month_avg"])} प्रति अंडा रहा है।'
 if z["month_avg"] else ''}</p>
</section>

{"".join(facts)}
{chart_html}
{ly_html}

<h2 class="egg-sec">अकसर पूछे जाने वाले सवाल</h2>
{faq_html}

{peers_html}
{_feed_links_html()}
{_guides_html()}
{_lead_gen_html()}
{_clarification()}
"""
    crumbs_ld = _crumb_ld([("होम", f"{SITE}/"), ("पशुपालन", f"{SITE}/farm"),
                           ("अंडे का रेट", BASE),
                           (hi, f"{BASE}/anda-rate/{zone_slug}")])
    return _doc(
        title=_fit(f"{hi} अंडा रेट आज ₹{poultry.rupees(paise)} — {en} egg rate today",
                   f"{hi} में आज का अंडा रेट — {en} egg rate today",
                   f"{hi} अंडा रेट आज — {en} egg rate",
                   f"{hi} अंडा रेट — egg rate"),
        desc=_fit(f"{hi} में आज अंडे का रेट ₹{poultry.rupees(paise)} प्रति अंडा "
                  f"(₹{poultry.per_hundred(paise)} प्रति 100)। {en} egg rate today, "
                  f"पिछले 30 दिन का रुझान और पिछले साल से तुलना।",
                  f"{hi} में आज अंडे का रेट ₹{poultry.rupees(paise)} प्रति अंडा। "
                  f"{en} egg rate today और 30 दिन का रुझान।",
                  limit=162),
        canon=f"{BASE}/anda-rate/{zone_slug}",
        crumbs=f'<a href="{SITE}/">होम</a> › <a href="{SITE}/farm">पशुपालन</a> '
               f'› <a href="{BASE}">अंडे का रेट</a> › <span>{escape(hi)}</span>',
        body=body, ld=_ld(crumbs_ld, faq_ld),
        active="", extra_css=_EXTRA_CSS, updated=day.isoformat(),
        footer_note="अंडे के दाम NECC से रोज़ अपडेट होते हैं। "
                    "बेचने से पहले अपने व्यापारी से रेट की पुष्टि करें।")
