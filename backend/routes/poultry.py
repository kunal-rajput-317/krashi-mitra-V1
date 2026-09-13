# ============================================================
# routes/poultry.py
# पशुपालन — /pashupalan, and the daily अंडे का रेट under it
#
# TWO TIERS, ~36 URLS. THAT IS THE WHOLE POINT.
#   /pashupalan                       the पशुपालन section hub
#   /pashupalan/anda-rate             today's egg rate in every NECC zone
#   /pashupalan/anda-rate/{zone}      one zone: today, trend, last year
#
# THE URL SAYS WHAT THE PAGE ANSWERS. This section shipped at /farm/poultry/
# anda-rate/{zone} — four segments in which "poultry" and "anda-rate" said the
# same thing twice, under an English section word on a site whose sections are
# /bhav, /naksha, /khoj, /sawal. Renamed 2026-09-12. The old tree still answers,
# as 301s, at the bottom of this file: /farm/poultry was earning ~1,800
# impressions a month at position 8 when it moved, and that equity has to
# travel with the page rather than evaporate.
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
# THE TABLE HANDS OFF; IT DOES NOT ANSWER FOR ALL 34 CITIES. /pashupalan/
# anda-rate prints its OWN answer in full — today's average, the dearest zone,
# the cheapest — and then lists the 34 zones with a delta and "रेट देखें →"
# and no absolute rate. That is /bhav's shape, not a new one: a tier page
# there answers its own question and hands off to the tier below as .dcards
# carrying a name and "भाव देखें →". The table used to print every absolute,
# and the result is in the numbers — 1,793 impressions to the table in the 28
# days to 2026-09-09 and ZERO to all 34 zone pages, because a farmer who could
# read his city's rate off row 21 had no reason to open the page with that
# city's trend, last-year comparison and rank on it. Changed 2026-09-13.
#
# WHY THIS SECTION EXISTS AT ALL. The egg rate changes every single day and a
# poultry farmer checks it every single morning — which is the one thing the
# crop side never had. /bhav answers a question a farmer asks twice a season;
# this answers one he asks daily, and that is the difference between ~200 new
# visitors a day and visitors who come back.
#
# THE LAYOUT IS THE SITE'S, NOT A SECOND ONE. Shell, tokens, header, footer,
# FAQ and breadcrumb JSON-LD are imported from bhav.py exactly the way
# product.py, krashi_dukan.py and rental.py import them — and so are the layout
# COMPONENTS: _tier_head for a hub top, .shop-section-title for a section
# heading, .ctile-search-row for a search box, .crop-card/.crop-grid for a
# photo card. This module first shipped with its own .egg-sec/.shelf pair that
# existed nowhere else on the site, so a farmer arriving from /bhav met
# headings and cards he had never seen. _EXTRA_CSS now adds only the rate list
# itself, which nothing else on the site has.
#
# THE BLUE BAR IS THIS SECTION'S, TOO. bhav.py's _header builds it from the
# mandi index, so borrowing the shell and leaving it alone put गेहूं/धान/प्याज
# on top of an egg rate. _section_nav() passes the zones a poultry farmer would
# actually tap — built from what has a rate today, so it cannot link to an
# empty page.
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
    _MIC_SVG_HTML, _axis_band, _crumb_ld, _doc, _faq, _fit, _lead_gen_html,
    _ld, _sparkline, _tier_head, _trend_colour,
)
from backend.services import poultry, poultry_necc

router = APIRouter()

SITE = "https://krashimitra.in"
SECTION = f"{SITE}/pashupalan"          # the पशुपालन hub
BASE = f"{SECTION}/anda-rate"           # the egg-rate table + its zone pages

# The section's own face in a SERP and on WhatsApp. Every page here fell back
# to the generic site banner while /bhav's leaves shipped a real crop photo.
# Both files are already self-hosted and credited on /articles/credits, so this
# costs nothing but the line (see tests/test_no_hotlinked_images.py).
OG_POULTRY = f"{SITE}/images/articles/murgi-palan-guide.webp"
OG_FARM = f"{SITE}/images/articles/dairy-farming-doodh-utpadan.webp"

_HI_MONTHS = ("जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई",
              "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर")

# The blue bar's zone links, in editorial order — the cities a poultry farmer
# actually types, not the dearest six, which would reshuffle the navigation
# every morning. Filtered against what has a rate before it renders.
_NAV_ZONES = ("delhi", "mumbai", "kolkata", "hyderabad", "chennai", "lucknow")

# The three poultry guides already on the site. Listed here rather than
# discovered from disk because the order is editorial — a farmer looking up a
# rate is most likely to want the disease page next, not the setup guide.
_GUIDES = [
    ("murgi-ranikhet-rog", "रानीखेत रोग", "टीका और बचाव",
     "मुर्गियों की सबसे बड़ी जानलेवा बीमारी, और लासोटा/R2B टीके का पूरा शेड्यूल।"),
    ("murgi-palan-guide", "मुर्गी पालन", "पूरी गाइड",
     "ब्रॉयलर, लेयर और देसी — नस्ल चुनाव, ब्रूडिंग, फीड और FCR का हिसाब।"),
    ("murgi-palan-backyard", "बैकयार्ड मुर्गी पालन", "कम लागत में शुरुआत",
     "10-50 पक्षियों से घर के पिछवाड़े शुरू करने का तरीका और असली खर्च।"),
]

# The rest of the पशुपालन shelf — real pages that already exist, each with the
# hero image the article itself ships, so the hub reads like the rest of the
# site instead of a list of emoji. /pashupalan is the hub these guides never
# had, not a placeholder for pages nobody has written.
_FARM_SHELF = [
    ("अंडे का रेट", "रोज़ का NECC भाव", BASE, "murgi-palan-guide", "रोज़ अपडेट",
     "हर दिन का NECC अंडा रेट — 34 शहरों का — और मुर्गी पालन की गाइड।"),
    ("डेयरी — दूध उत्पादन", "नस्ल से दुहाई तक",
     f"{SITE}/articles/dairy-farming-doodh-utpadan",
     "dairy-farming-doodh-utpadan", "गाइड",
     "नस्ल, हरा चारा, ब्यांत का प्रबंधन और दूध बढ़ाने का पूरा गणित।"),
    ("बकरी पालन", "कम पूँजी का पालन", f"{SITE}/articles/bakri-palan-guide",
     "bakri-palan-guide", "गाइड",
     "कम ज़मीन और कम पूँजी में शुरू होने वाला पालन — नस्ल से बिक्री तक।"),
    ("मत्स्य पालन", "तालाब से बाज़ार तक", f"{SITE}/articles/machhli-palan-guide",
     "machhli-palan-guide", "गाइड",
     "तालाब की तैयारी, बीज संचय और फीड — मछली पालन की बुनियाद।"),
    ("मधुमक्खी पालन", "शहद का मौसमी चक्र", f"{SITE}/articles/madhumakhi-palan-guide",
     "madhumakhi-palan-guide", "गाइड",
     "बक्सा, कॉलोनी और शहद निकालने का पूरा मौसमी चक्र।"),
    ("पशु रोग — लंपी स्किन", "पहचान और टीका", f"{SITE}/articles/pashu-lumpy-skin-rog",
     "pashu-lumpy-skin-rog", "रोग",
     "लंपी स्किन रोग की पहचान, फैलाव रोकना और टीकाकरण।"),
    ("हरा चारा — नेपियर, बरसीम", "दूध की असली लागत",
     f"{SITE}/articles/hara-chara-napier-berseem", "hara-chara-napier-berseem",
     "चारा", "साल भर हरा चारा कैसे मिले — नेपियर, बरसीम और ज्वार का चक्र।"),
]

# Only the rate list is local now. Everything else on these pages is a
# component the rest of the site already uses (see the module header).
_EXTRA_CSS = """
.desc{font-size:14px;color:var(--text-mid);margin:14px 0;line-height:1.7}
/* Section headings are .shop-section-title — serif, amber rule — like every
   other hub on the site. This only teaches that component the quiet sub-label
   the headings here carry ("NECC का घोषित दाम" beside "NECC सुझाया रेट"). */
.shop-section-title{margin-top:26px;flex-wrap:wrap}
.shop-section-title em{font-style:normal;font-weight:600;font-size:11.5px;
color:var(--text-soft);font-family:var(--font-body)}
.crop-card .note{padding:0 14px 13px;margin:0}

.egg-list{margin-top:12px;border:1px solid var(--border);border-radius:var(--radius-md);
overflow:hidden;background:var(--white);box-shadow:var(--shadow-sm)}
.egg-row{display:flex;align-items:center;gap:10px;padding:11px 14px;text-decoration:none;
color:inherit;border-top:1px solid var(--border)}
.egg-row:first-child{border-top:none}
/* eggFilter() hides with el.hidden, and the UA's [hidden]{display:none} is a
   (0,1,0) rule that LOSES to the display:flex above and to .shop-section-title
   in the shell — so without these three the search box hid nothing but the
   list it had emptied, and a query for one city left the other section's 24
   rows on screen looking like results. */
.egg-row[hidden],.egg-list[hidden],.shop-section-title[hidden]{display:none}
.egg-row:hover{background:var(--green-pale)}
.egg-z{flex:1;min-width:0}
.egg-n{display:block;font-size:14px;font-weight:700;color:var(--text-dark);line-height:1.25}
.egg-s{display:block;font-size:11px;color:var(--text-soft);font-weight:600;margin-top:1px}
.egg-p{text-align:right;flex-shrink:0}
/* The row's right-hand side carries a hook and a way in, never the rate — see
   _rows_html. .egg-d has to restate its own size because the shell's global
   .up/.dn set 11.5px, and a delta standing in for the number reads as a
   footnote at that size. */
.egg-d{display:block;font-size:13.5px;font-weight:700;color:var(--text-soft);line-height:1.2;white-space:nowrap}
.egg-d.up{color:#1b7a3d;font-size:13.5px}
.egg-d.dn{color:#c0392b;font-size:13.5px}
.egg-go{display:block;font-size:11px;font-weight:700;color:var(--green-mid);margin-top:2px;white-space:nowrap}
/* The "no city matched" line the search box reveals. Hidden until it has
   something to say, so the page never ships an empty state it does not need. */
.egg-none{display:none;padding:16px 14px;font-size:13px;color:var(--text-soft);
line-height:1.65;background:var(--white);border:1px solid var(--border);
border-radius:var(--radius-md);margin-top:12px}

.egg-stat{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px}
.egg-stat div,.egg-stat a{flex:1;min-width:132px;background:var(--white);border:1px solid var(--border);
border-radius:var(--radius-sm);padding:10px 13px;box-shadow:var(--shadow-sm)}
/* The dearest and the cheapest are the two stats that NAME a zone, so they are
   the door to that zone rather than a dead label. */
.egg-stat a{display:block;text-decoration:none;color:inherit}
.egg-stat a:hover{background:var(--green-pale);border-color:var(--green-mid)}
.egg-stat a span::after{content:" →";color:var(--green-mid);font-weight:700}
.egg-stat b{display:block;font-size:17px;font-weight:700;color:var(--green-dark);line-height:1.2}
.egg-stat span{font-size:11px;color:var(--text-soft);font-weight:600}

/* The hub's live-rate card. .next-up — the strip this replaced — is
   white-on-transparent and only legible inside the dark .answer panel; the hub
   now opens with _tier_head on the cream ground, the way /bhav's hub does. */
.egg-live{display:flex;align-items:center;gap:16px;flex-wrap:wrap;margin:18px 0 8px;
padding:16px 18px;background:var(--white);border:1px solid var(--border);
border-left:4px solid var(--amber);border-radius:var(--radius-md);box-shadow:var(--shadow-sm)}
.egg-live-n{font-size:32px;font-weight:700;color:var(--green-dark);line-height:1;letter-spacing:-1px}
.egg-live-n small{font-size:13px;font-weight:600;color:var(--text-soft);letter-spacing:0;margin-left:4px}
.egg-live-t{flex:1;min-width:180px}
.egg-live-t b{display:block;font-size:13.5px;font-weight:700;color:var(--text-dark);line-height:1.4}
.egg-live-t span{font-size:11.5px;color:var(--text-soft);font-weight:600}
.egg-live-go{background:var(--green-mid);color:#fff;font-size:13px;font-weight:700;
text-decoration:none;padding:10px 16px;border-radius:var(--radius-sm);white-space:nowrap}
.egg-live-go:hover{background:var(--green-dark)}

.necc-note{margin-top:26px;padding:13px 15px;border:1px solid var(--border);
border-left:3px solid var(--amber);border-radius:var(--radius-sm);background:var(--cream)}
.necc-note h3{font-size:12.5px;font-weight:700;color:var(--text-dark);margin-bottom:5px}
.necc-note p{font-size:11.5px;color:var(--text-mid);line-height:1.65;margin-bottom:7px}
.necc-note p:last-child{margin-bottom:0}
.necc-note .en{font-size:10.5px;color:var(--text-soft);line-height:1.6}
@media(max-width:640px){.egg-row{padding:10px 12px}.egg-n{font-size:13.5px}
.egg-live{gap:12px;padding:14px}.egg-live-n{font-size:27px}
.egg-live-go{width:100%;text-align:center}}
"""

# Filters both rate lists at once and tells the farmer when nothing matched.
# Same interaction /bhav's hub ships (bhavFilterTiles), namespaced so the two
# could never collide if a page ever carried both.
_SEARCH_JS = """<script>
function eggFilter(){
  var i=document.getElementById('egg-search');
  var q=(i&&i.value||'').trim().toLowerCase();
  var shown=0;
  document.querySelectorAll('.egg-list .egg-row').forEach(function(r){
    var hit=(!q||(r.dataset.name||'').indexOf(q)>=0);
    r.hidden=!hit;
    if(hit){shown++;}
  });
  /* A section whose rows all filtered out takes its heading with it —
     otherwise the page shows "NECC सुझाया रेट" over nothing. */
  document.querySelectorAll('.egg-list').forEach(function(l){
    var any=!!l.querySelector('.egg-row:not([hidden])');
    l.hidden=!any;
    var h=l.previousElementSibling;
    if(h&&h.classList.contains('shop-section-title')){h.hidden=!any;}
  });
  var none=document.getElementById('egg-none');
  if(none){none.style.display=shown?'none':'block';}
}
function eggVoice(){
  var SR=window.SpeechRecognition||window.webkitSpeechRecognition;
  if(!SR){return;}
  var mic=document.getElementById('egg-mic');
  var r=new SR();r.lang='hi-IN';r.interimResults=false;r.maxAlternatives=1;
  if(mic){mic.classList.add('listening');}
  r.onresult=function(e){
    var i=document.getElementById('egg-search');
    if(i){i.value=e.results[0][0].transcript;eggFilter();}
  };
  r.onend=function(){if(mic){mic.classList.remove('listening');}};
  r.onerror=function(){if(mic){mic.classList.remove('listening');}};
  try{r.start();}catch(_){}
}
</script>"""


# ── small shared bits ───────────────────────────────────────

def _hi_date(d: date) -> str:
    return f"{d.day} {_HI_MONTHS[d.month - 1]} {d.year}"


def _hook_html(r: dict, compare_to: dict | None) -> str:
    """The curiosity hook on a zone row, standing where the rate used to.

    /bhav settled this shape over two over-corrections on 2026-07-16: a bare
    "ज़्यादा" creates no curiosity, and collapsing the row to a name-only link
    reads as thin content. So the row keeps its full layout and shows a
    CONCRETE comparison — the delta — while the absolute stays on the page it
    belongs to.

    Two kinds of delta, because the two lists ask different questions. On the
    table it is "कल से", the only comparison a list of 34 unrelated cities can
    honestly make. In the peers block at the foot of a zone page it is against
    THAT zone, which is what a heading reading "तुलना" promises — the block
    used to print each peer's own day-over-day change underneath it, which
    compared nothing to anything.
    """
    if compare_to is not None:
        diff = r["paise"] - compare_to["paise"]
        if not diff:
            return '<span class="egg-d">बराबर</span>'
        cls, arrow, word = (("up", "▲", "ज़्यादा") if diff > 0
                            else ("dn", "▼", "कम"))
        return (f'<span class="egg-d {cls}">{arrow} ₹{abs(diff) / 100:.2f} '
                f'{word}</span>')
    # None and 0 are different facts and the section's rule is that a day we
    # do not have never gets invented: None means there is no day before this
    # one to compare against, 0 means the rate genuinely held.
    if r["change"] is None:
        return ""
    if not r["change"]:
        return '<span class="egg-d">कल जितना ही</span>'
    cls, arrow = ("up", "▲") if r["change"] > 0 else ("dn", "▼")
    return (f'<span class="egg-d {cls}">{arrow} ₹{abs(r["change"]) / 100:.2f} '
            f'कल से</span>')


def _section_nav(rows: list[dict]) -> str:
    """This section's blue bar, replacing the mandi crop links the shell would
    otherwise put on top of an egg rate (see the module header).

    Built from zones that HAVE a rate, so — like _quicknav, which it mirrors —
    it can never link to a page that would render empty.
    """
    have = {r["slug"]: r["hi"] for r in rows}
    items = "".join(
        f'<a class="cnav-item" href="{BASE}/{s}">{escape(have[s])} अंडा रेट</a>'
        for s in _NAV_ZONES if s in have)
    return (f'<div class="commodity-navbar"><div class="cnav-inner">'
            f'<a class="cnav-item" href="{SECTION}">पशुपालन</a>'
            f'<a class="cnav-item" href="{BASE}">आज का अंडा रेट</a>{items}'
            f'<a class="cnav-item" href="{SITE}/articles/murgi-palan-guide">'
            f'मुर्गी पालन</a></div></div>')


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


def _sec_title(label: str, sub: str = "") -> str:
    """The site's section heading — serif, amber rule — the same component
    /bhav's hub puts over its crop grid. This section used to declare its own
    12.5px grey `.egg-sec`, which appeared nowhere else on the site."""
    em = f"<em>{escape(sub)}</em>" if sub else ""
    return f'<div class="shop-section-title"><span>{escape(label)}</span>{em}</div>'


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


def _rows_html(rows: list[dict], compare_to: dict | None = None) -> str:
    """The zone list — this section's tier-below grid, and the only way into a
    zone page other than the blue bar.

    IT DOES NOT PRINT THE RATE, and that is the point of it. This is /bhav's
    settled pattern rather than a new idea: a tier page there answers its own
    question in full (the crop's average, the dearest mandi, the cheapest) and
    then hands off to the tier below as `.dcard`s carrying a name, "भाव देखें
    →" and no number at all.

    This table used to print all 34 absolutes, which made it the last page of
    the section. In the 28 days to 2026-09-09 it earned 1,793 impressions and
    every one of the 34 zone pages earned ZERO — and a farmer who could read
    लखनऊ's rate off row 21 had no reason to open the page carrying लखनऊ's
    30-day trend, its last-year comparison and its rank. The hub's own answer
    (today's average, the dearest zone, the cheapest) stays complete above
    this list: that is page content, the same line /bhav draws around a
    district average.
    """
    out = []
    for r in rows:
        spark = _sparkline([str(p) for p in r["spark"]]) if len(r["spark"]) > 1 else ""
        where = " · ".join(x for x in (r["state_hi"],
                                       "खपत केंद्र" if r["centre"] == "CC" else "") if x)
        # What the search box matches on: Hindi name, slug and state, so
        # "lucknow", "लखनऊ" and "उत्तर प्रदेश" all find the same row.
        hay = f'{r["hi"]} {r["slug"].replace("-", " ")} {r["state_hi"]}'.lower()
        out.append(
            f'<a class="egg-row" href="{BASE}/{r["slug"]}" data-name="{escape(hay, quote=True)}">'
            f'<span class="egg-z"><span class="egg-n">{escape(r["hi"])}</span>'
            f'<span class="egg-s">{escape(where)}</span></span>'
            f'{spark}'
            f'<span class="egg-p">{_hook_html(r, compare_to)}'
            f'<span class="egg-go">रेट देखें →</span></span></a>')
    return f'<div class="egg-list">{"".join(out)}</div>'


def _search_box() -> str:
    """The city filter over the 34 rows. The section shipped without one, so a
    farmer whose city sat 28 rows down had to scroll for it — on a page whose
    whole job is answering one question fast. Same component /bhav's hub uses
    to filter its crop tiles, down to the voice button."""
    return (
        '<div class="mandi-toolbar"><div class="ctile-search-row">'
        '<span class="cs-icon">🔍</span>'
        '<input id="egg-search" type="text" autocomplete="off" '
        'placeholder="अपना शहर खोजें... (लखनऊ, दिल्ली, Hyderabad)" oninput="eggFilter()">'
        '<button class="mn-mic-btn" id="egg-mic" type="button" '
        'onmousedown="event.preventDefault()" onclick="eggVoice()" '
        f'title="बोलकर खोजें">{_MIC_SVG_HTML}</button>'
        '</div></div>')


def _card(href: str, img: str, title: str, kicker: str, tag: str, sub: str,
          heading: bool = True) -> str:
    """One photo card in the site's .crop-card shape — the component /bhav's
    state hub uses for its crop cards.

    `heading` renders the name as an <h2> the way that grid does. The guide
    strip at the foot of a rate page passes False, so those pages keep one <h1>
    and a flat run of section <h2>s instead of ten.
    """
    name_tag = "h2" if heading else "span"
    return (
        f'<a class="crop-card" href="{href}">'
        f'<div class="crop-card-photo">'
        f'<img src="{SITE}/images/articles/{img}-card.webp" alt="{escape(title)}" '
        f'loading="lazy" decoding="async" width="240" height="120">'
        f'<{name_tag} class="crop-card-name">{escape(title)}'
        f'<span class="crop-card-en">{escape(kicker)}</span></{name_tag}></div>'
        f'<div class="crop-card-body"><span class="lbl">{escape(tag)}</span>'
        f'<span class="rate">देखें →</span></div>'
        f'<p class="note">{escape(sub)}</p></a>')


def _guides_html() -> str:
    cards = "".join(
        _card(f"{SITE}/articles/{slug}", slug, title, kicker, "गाइड", sub,
              heading=False)
        for slug, title, kicker, sub in _GUIDES)
    return (_sec_title("मुर्गी पालन की गाइड", "रेट देखने के बाद का अगला सवाल")
            + f'<div class="crop-grid">{cards}</div>')


def _feed_links_html() -> str:
    """Feed is roughly two-thirds of what a poultry farm spends, and both feed
    grains already have live /bhav pages. So this is the honest next question
    after "what is the egg rate" — and it is the link that ties this section to
    the engine that already ranks."""
    return (
        _sec_title("दाने का खर्च",
                   "अंडे के रेट से ज़्यादा यही तय करता है कि कमाई बचेगी या नहीं")
        + '<div class="dlinks" style="margin-top:12px">'
          f'<a href="{SITE}/bhav/maize">🌽 मक्का का आज का भाव</a>'
          f'<a href="{SITE}/bhav/soyabean">🫘 सोयाबीन का आज का भाव</a>'
          f'<a href="{SITE}/product/#cat-pashu_aahaar">🛒 पशु व पोल्ट्री आहार</a>'
          f'<a href="{SITE}/articles/hara-chara-napier-berseem">🌱 हरा चारा</a>'
          '</div>')


def _peers(db: Session, me: dict) -> list[dict]:
    """Other zones worth showing at the foot of one zone's page — its own state
    first, then the big consumption centres.

    This used to be `latest(db)[:6]`, i.e. the six dearest zones — the SAME six
    on all 34 pages, and none of them near the reader. State-first gives each
    page a tail of its own and puts the comparison a farmer would actually make
    (the next mandi over) above the one he would not (Kolkata, from Ajmer).
    """
    rows = [r for r in poultry.latest(db) if r["slug"] != me["slug"]]
    same = [r for r in rows if r["state_hi"] and r["state_hi"] == me["state_hi"]]
    seen = {r["slug"] for r in same}
    big = [r for r in rows if r["slug"] in _NAV_ZONES and r["slug"] not in seen]
    seen |= {r["slug"] for r in big}
    rest = [r for r in rows if r["slug"] not in seen]
    return (same + big + rest)[:6]


# ── /pashupalan/sitemap.xml ─────────────────────────────────

@router.get("/pashupalan/sitemap.xml")
def poultry_sitemap(db: Session = Depends(get_db)):
    """The two hubs and every zone that has a rate — nothing speculative.

    Built from what is actually in the snapshot, not from the registry, so the
    sitemap can never advertise a zone page that would render empty. Same rule
    /bhav's sitemap follows.
    """
    day = poultry.updated(db)
    lastmod = f"<lastmod>{day.isoformat()}</lastmod>" if day else ""
    urls = [f"  <url><loc>{SECTION}</loc>{lastmod}<changefreq>weekly</changefreq></url>",
            f"  <url><loc>{BASE}</loc>{lastmod}<changefreq>daily</changefreq>"
            f"<priority>0.9</priority></url>"]
    for r in poultry.latest(db):
        urls.append(
            f'  <url><loc>{BASE}/{r["slug"]}</loc>'
            f'<lastmod>{r["date"].isoformat()}</lastmod>'
            f"<changefreq>daily</changefreq><priority>0.8</priority></url>")
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
           + "\n".join(urls) + "\n</urlset>")
    return Response(content=xml, media_type="application/xml",
                    headers={"Cache-Control": "public, max-age=3600"})


# ── /pashupalan — the section hub ───────────────────────────

@router.get("/pashupalan", response_class=HTMLResponse)
@router.get("/pashupalan/", response_class=HTMLResponse)
def farm_hub(db: Session = Depends(get_db)):
    """The section landing for पशुपालन.

    It exists because /pashupalan/anda-rate cannot hang off a 404, and it earns
    its own place by being the only page that gathers the livestock guides that
    were scattered across /articles. When a second vertical gets a daily
    number, this is where it goes — the shelf is a list, not a redirect.

    Laid out like /bhav's hub — centred heading, then the live number, then a
    photo-card grid — rather than with the dark price panel, which belongs on a
    page whose whole subject IS one price.
    """
    day = poultry.updated(db)
    rows = poultry.latest(db, section="necc")
    all_rows = poultry.latest(db)
    # The average is over the NECC-suggested zones only (mixing in prevailing
    # prices would average two different claims), but the LINK counts every
    # zone the table actually shows — promising 24 and landing on 34 is a
    # small lie the farmer notices immediately.
    total = len(all_rows)
    # `live` PRINTS A NECC NUMBER, WHICH MAKES THIS A PAGE UNDER THE LICENCE.
    # The section hub was written as a shelf of guides and the clarification
    # test was scoped to PAGES[1:] accordingly — then this block was added and
    # the hub started publishing "आज का औसत NECC अंडा रेट — ₹579 प्रति 100"
    # with nothing beside it. NECC permits republication only if its
    # clarification travels with the numbers, so the block below is emitted
    # exactly when this one is, and the test now covers all three pages.
    live = ""
    if rows and day:
        avg = round(sum(r["paise"] for r in rows) / len(rows))
        live = (
            '<div class="egg-live">'
            f'<span class="egg-live-n">₹{poultry.rupees(avg)}<small>प्रति अंडा</small></span>'
            '<span class="egg-live-t">'
            f'<b>आज का औसत NECC अंडा रेट — ₹{poultry.per_hundred(avg)} प्रति 100</b>'
            f'<span>{escape(_hi_date(day))} · {total} शहर / ज़ोन</span></span>'
            f'<a class="egg-live-go" href="{BASE}">सभी {total} शहरों का रेट देखें →</a>'
            '</div>')

    cards = "".join(
        _card(href, img, title, kicker, tag, sub)
        for title, kicker, href, img, tag, sub in _FARM_SHELF)

    body = f"""{_tier_head("पशुपालन — दूध, अंडा, बकरी, मछली और मधुमक्खी",
                           "खेती के साथ चलने वाली कमाई, और उसके रोज़ बदलते दाम")}
{live}
<p class="desc">पशुपालन की कमाई खेती से एक बात में अलग है — यह रोज़ आती है। अंडा रोज़
बिकता है, दूध रोज़ बिकता है, और दाना रोज़ खरीदना पड़ता है। इसीलिए यहाँ भाव भी रोज़ का
है, सीज़न का नहीं।</p>

{_sec_title("पशुपालन के विषय", f"{len(_FARM_SHELF)} हिस्से")}
<div class="crop-grid">{cards}</div>

<p class="desc">अभी इस हिस्से में रोज़ का भाव सिर्फ़ पोल्ट्री (अंडे) का है, क्योंकि
अंडे का ही रोज़ का राष्ट्रीय रेट प्रकाशित होता है। दूध, बकरी और मछली के दाम इलाके
और सौदे पर तय होते हैं — उनके लिए यहाँ गाइड हैं, झूठा "आज का रेट" नहीं।</p>
{_lead_gen_html()}
{_clarification() if live else ""}
"""
    crumbs = _crumb_ld([("होम", f"{SITE}/"), ("पशुपालन", SECTION)])
    return _doc(
        title=_fit("पशुपालन — अंडा रेट, डेयरी, बकरी, मछली व मधुमक्खी पालन",
                   "पशुपालन — अंडा रेट, डेयरी, बकरी व मछली पालन",
                   "पशुपालन — अंडा रेट, डेयरी और बकरी पालन"),
        desc=_fit("रोज़ का अंडा रेट और पशुपालन की पूरी जानकारी — डेयरी, बकरी पालन, "
                  "मत्स्य पालन, मधुमक्खी पालन और पशु रोग की हिंदी गाइड।", limit=162),
        canon=SECTION,
        crumbs=f'<a href="{SITE}/">होम</a> › <span>पशुपालन</span>',
        body=body, ld=_ld(crumbs), og_img=OG_FARM,
        active="poultry", extra_css=_EXTRA_CSS,
        quicknav=_section_nav(all_rows),
        updated=day.isoformat() if day else "",
        footer_note="अंडे के दाम NECC से रोज़ अपडेट होते हैं। "
                    "बेचने से पहले अपने व्यापारी से रेट की पुष्टि करें।")


# ── /pashupalan/anda-rate — today's rate, everywhere ────────

@router.get("/pashupalan/anda-rate", response_class=HTMLResponse)
@router.get("/pashupalan/anda-rate/", response_class=HTMLResponse)
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
                    canon=BASE, crumbs="", body=body, og_img=OG_POULTRY,
                    active="poultry", extra_css=_EXTRA_CSS, robots="noindex, follow")

    rows = necc or prevailing
    all_rows = necc + prevailing
    avg = round(sum(r["paise"] for r in rows) / len(rows))
    high, low = rows[0], rows[-1]
    changed = [r for r in rows if r["change"]]
    avg_change = (round(sum(r["change"] for r in changed) / len(changed))
                  if changed else 0)

    stats = (
        '<div class="egg-stat">'
        f'<div><b>₹{poultry.rupees(avg)}</b><span>औसत रेट प्रति अंडा</span></div>'
        f'<a href="{BASE}/{high["slug"]}"><b>₹{poultry.rupees(high["paise"])}</b>'
        f'<span>सबसे ऊँचा — {escape(high["hi"])}</span></a>'
        f'<a href="{BASE}/{low["slug"]}"><b>₹{poultry.rupees(low["paise"])}</b>'
        f'<span>सबसे कम — {escape(low["hi"])}</span></a>'
        f'<div><b>{len(all_rows)}</b><span>शहर / ज़ोन</span></div>'
        '</div>')

    sections = ""
    if necc:
        sections += (_sec_title("NECC सुझाया रेट", "NECC का घोषित दाम")
                     + _rows_html(necc))
    if prevailing:
        sections += (_sec_title("बाज़ार में चल रहा रेट",
                                "Prevailing — जहाँ सौदा असल में हो रहा है")
                     + _rows_html(prevailing))
    sections += ('<div class="egg-none" id="egg-none">इस नाम का कोई शहर इस सूची में '
                 'नहीं है। NECC सिर्फ़ इन्हीं ज़ोन का रेट घोषित करता है — अपने सबसे '
                 'नज़दीकी शहर का रेट देखें।</div>')

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
<p class="answer-sub">NECC egg rate today · {len(all_rows)} शहर</p>
<div class="answer-price"><span class="answer-rupee">₹{poultry.rupees(avg)}
<small>प्रति अंडा</small></span>
{f'<span class="answer-delta {"up" if avg_change > 0 else "dn"}">'
 f'{"▲" if avg_change > 0 else "▼"} ₹{abs(avg_change) / 100:.2f} कल से</span>'
 if avg_change else ''}</div>
<p class="answer-lead">यह {len(rows)} NECC ज़ोन का औसत है — ₹{poultry.per_hundred(avg)}
प्रति 100 अंडे। नीचे अपना शहर चुनें — वहाँ आज का पूरा रेट, पिछले 30 दिन का रुझान और
पिछले साल से तुलना मिलेगी।</p>
</section>

{stats}
{_search_box()}
{sections}

<h2>अकसर पूछे जाने वाले सवाल</h2>
{faq_html}

{_feed_links_html()}
{_guides_html()}
{_lead_gen_html()}
{_clarification()}
{_SEARCH_JS}
"""
    crumbs_ld = _crumb_ld([("होम", f"{SITE}/"), ("पशुपालन", SECTION),
                           ("अंडे का रेट", BASE)])
    return _doc(
        # NO DATE IN THE TITLE. It read "आज का अंडा रेट 13 सितंबर 2026" — the
        # word "today" beside a date that is, by construction, never today:
        # `day` is the date of the last NECC sheet, so on a good morning the
        # SERP shows yesterday and on a Sunday it shows Friday. On a query
        # whose entire point is freshness, that contradiction is the first
        # thing a farmer reads. In the 28 days to 2026-09-09 "अंडा रेट" put
        # 308 impressions in front of this title at position 7.8 and earned
        # ZERO clicks; the whole section took 546 impressions and one click.
        # The freshness claim belongs in dateModified and the visible "अपडेट"
        # line, which carry the real date and are tested to never say today.
        #
        # THE ROMANISED FORM EARNS ITS PLACE. ande ka rate / anda ka rate /
        # aaj ka anda rate / andaret are ~50 impressions sitting at positions
        # 10-25 while the Devanagari queries sit at 6-8 — the same script
        # mismatch the /sarkari_yojana read found, and the same fix. "anda
        # rate today" covers the romanised and English readings in three
        # words, which is what the dropped date paid for.
        title=_fit(f"आज का अंडा रेट — anda rate today | {len(all_rows)} शहरों का NECC भाव",
                   "आज का अंडा रेट — anda rate today | NECC egg rate",
                   "आज का अंडा रेट — anda rate today"),
        # The number stays where it already was — the description is the one
        # place a price query gets its answer before the click, and this page
        # carries NECC's clarification exactly as the licence requires. What
        # changed is the tail: "NECC egg rate today" said the same thing the
        # title said, so one of the two repetitions buys the romanised form
        # instead.
        desc=_fit(f"आज का अंडा रेट (anda rate today): औसत ₹{poultry.rupees(avg)} प्रति अंडा "
                  f"(₹{poultry.per_hundred(avg)} प्रति 100)। "
                  f"{len(all_rows)} शहरों का NECC रेट — "
                  f"{high['hi']} सबसे ऊँचा, {low['hi']} सबसे कम।",
                  f"आज का अंडा रेट (anda rate today): औसत ₹{poultry.rupees(avg)} प्रति अंडा "
                  f"(₹{poultry.per_hundred(avg)} प्रति 100)। "
                  f"{len(all_rows)} शहरों का NECC रेट।",
                  f"आज का अंडा रेट (anda rate today): औसत ₹{poultry.rupees(avg)} प्रति अंडा। "
                  f"{len(all_rows)} शहरों का NECC egg rate।",
                  limit=162),
        canon=BASE,
        crumbs=f'<a href="{SITE}/">होम</a> › <a href="{SECTION}">पशुपालन</a> '
               '› <span>अंडे का रेट</span>',
        body=body, ld=_ld(crumbs_ld, faq_ld), og_img=OG_POULTRY,
        active="poultry", extra_css=_EXTRA_CSS,
        quicknav=_section_nav(all_rows), updated=day.isoformat(),
        footer_note="अंडे के दाम NECC से रोज़ अपडेट होते हैं। "
                    "बेचने से पहले अपने व्यापारी से रेट की पुष्टि करें।")


# ── /pashupalan/anda-rate/{zone} — one zone ─────────────────

@router.get("/pashupalan/anda-rate/{zone_slug}", response_class=HTMLResponse)
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
    section_rows = poultry.latest(db, section=z["section"])
    all_rows = poultry.latest(db)
    rank = next((i + 1 for i, r in enumerate(section_rows) if r["slug"] == zone_slug), 0)
    peers = _peers(db, z)

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
        facts.append(f'<div><b>{rank} / {len(section_rows)}</b>'
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
        near = f"{z['state_hi']} और आसपास" if z["state_hi"] else "दूसरे शहरों"
        peers_html = (_sec_title(f"{near} का आज का रेट",
                                 f"{hi} के ₹{poultry.rupees(paise)} से तुलना")
                      + _rows_html(peers, compare_to=z)
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

<h2>अकसर पूछे जाने वाले सवाल</h2>
{faq_html}

{peers_html}
{_feed_links_html()}
{_guides_html()}
{_lead_gen_html()}
{_clarification()}
"""
    crumbs_ld = _crumb_ld([("होम", f"{SITE}/"), ("पशुपालन", SECTION),
                           ("अंडे का रेट", BASE),
                           (hi, f"{BASE}/{zone_slug}")])
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
        canon=f"{BASE}/{zone_slug}",
        crumbs=f'<a href="{SITE}/">होम</a> › <a href="{SECTION}">पशुपालन</a> '
               f'› <a href="{BASE}">अंडे का रेट</a> › <span>{escape(hi)}</span>',
        body=body, ld=_ld(crumbs_ld, faq_ld), og_img=OG_POULTRY,
        active="poultry", extra_css=_EXTRA_CSS,
        quicknav=_section_nav(all_rows), updated=day.isoformat(),
        footer_note="अंडे के दाम NECC से रोज़ अपडेट होते हैं। "
                    "बेचने से पहले अपने व्यापारी से रेट की पुष्टि करें।")


# ════════════════════════════════════════════════════════════
# THE OLD ADDRESSES
#
# This section lived at /farm/* until 2026-09-12. /farm/poultry was earning
# ~1,800 impressions a month at position 8 when it moved, so every old URL 301s
# to its new one rather than 404ing or falling through to the site catch-all —
# the equity has to travel with the page.
#
# Netlify's _redirects carries the same rules at the edge, so a farmer on an
# old link is never made to wait for a Render cold start just to be told where
# the page went. These routes exist anyway: the edge rules cannot be tested
# from here, a request that reaches Render directly still has to be answered,
# and a section that ever moves again should find the pattern written down.
#
# /pashupalan/poultry is not an old URL — it is the one a farmer guesses from
# the drawer label. It lands on the table for the same reason /farm/poultry/
# anda-rate used to: two URLs for one answer is how an index gets diluted.
# ════════════════════════════════════════════════════════════

_MOVED = {
    "/farm": SECTION,
    "/farm/": SECTION,
    "/farm/poultry": BASE,
    "/farm/poultry/": BASE,
    "/farm/poultry/anda-rate": BASE,
    "/pashupalan/poultry": BASE,
}


def _moved_route(to: str):
    """One handler per old path.

    `to` is captured by the factory's own scope, NOT as a default argument on
    the handler. FastAPI reads a handler's signature to build its parameters,
    so `def handler(to: str = to)` — the obvious way to avoid the late-binding
    loop-variable trap — turns `to` into a QUERY PARAMETER, and
    `/farm?to=https://evil.example.com` becomes a 301 to evil.example.com off
    our own domain. A factory closure has no late-binding problem to solve in
    the first place: each call gets its own cell.
    """
    def handler() -> RedirectResponse:
        return RedirectResponse(to, status_code=301)
    return handler


for _old, _new in _MOVED.items():
    router.add_api_route(_old, _moved_route(_new), methods=["GET"],
                         include_in_schema=False)


@router.get("/farm/poultry/anda-rate/{zone_slug}", include_in_schema=False)
def zone_moved(zone_slug: str):
    return RedirectResponse(f"{BASE}/{zone_slug}", status_code=301)


@router.get("/farm/poultry/sitemap.xml", include_in_schema=False)
def sitemap_moved():
    return RedirectResponse(f"{SECTION}/sitemap.xml", status_code=301)
