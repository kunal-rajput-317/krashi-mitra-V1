# ============================================================
# routes/ganna.py
# कृषि मित्र — the गन्ना cluster, server-rendered like /bhav and /naksha
#
#   GET /ganna                    hub — केंद्र का FRP + हर गन्ना राज्य का रेट
#   GET /ganna/{state}            one state's cane price (SAP, or FRP + recovery)
#   GET /ganna/{state}/{district} that district's sugar mills, by capacity
#   GET /ganna/sitemap.xml        the cluster's own sitemap
#
# Why cane does not live in /bhav
# ------------------------------
# /bhav's unit is crop × mandi × date and its whole value is a number that moves
# daily. Cane has no such number: it is bought by mills at an administered price
# — the centre's FRP, or a higher State Advised Price — fixed once a year and
# unchanged for the whole season. Fanned out across /bhav's crop→state→district
# drill that produces thousands of near-identical pages with no date variance,
# which is exactly the thin content the freshness work of 2 Aug was fixing.
# The cane farmer also cannot shop around: he is bonded to one mill by सट्टा, so
# /bhav's nearest-mandi and net-price-after-transport panels are meaningless to
# him. Different unit, different question, different page.
#
# Why the data is a hand-verified file and not a fetch
# ---------------------------------------------------
# SAP is announced once a year in a cabinet press note. There is no feed to
# poll, and a scraper that runs 365 days to catch one change is a liability, not
# automation. backend/data/ganna_sap.json carries the numbers; every one of them
# is sourced, and a state we cannot source is served noindex rather than padded
# out with the national FRP repeated back (the rule naksha.py already uses for a
# district whose village cache has not landed — real data, or the page does not
# claim to be one).
#
# The district tier exists only where a state register does. There is no free
# national mill directory — data.gov.in has nothing mill-level, OSM has 12 named
# mills in the whole country, ISMA's 642-mill Atlas is paid — so the directory
# grows one state adapter at a time (services/ganna_mill_service.py) and a state
# without one simply has no district pages. Maharashtra is the first, and its
# register is CO-OPERATIVES ONLY: every page built on it says so, because a list
# headed "your district's mills" that quietly omits the private half is wrong by
# omission.
#
# The per-mill tier is still absent on purpose. Name, capacity and a
# registration date is not enough to carry 234 pages, and the thing that would
# make a mill page worth having — what it owes its farmers — is the fortnightly
# arrears report, which is a scanned PDF and needs OCR.
# ============================================================

import json
from datetime import date
from html import escape
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from backend.routes.bhav import SITE, _crumb_ld, _doc, _fit, _ld
from backend.services import ganna_mill_service as mills

router = APIRouter()

_DATA = Path(__file__).resolve().parents[1] / "data" / "ganna_sap.json"

_cache: dict = {"mtime": None, "data": None}

# The shell's default footer line — "prices update daily from Agmarknet,
# confirm at your mandi before selling" — is false twice over here: cane is not
# in the mandi feed and its price changes once a season, and a cane farmer sent
# to confirm at a mandi is being sent to a market that never trades his crop.
_FOOTER_NOTE = ("गन्ने का दाम मंडी में नहीं, सरकार के आदेश से तय होता है — केंद्र का FRP "
                "या राज्य का SAP, हर पेराई सीजन में एक बार। ताज़ा रेट और भुगतान की स्थिति "
                "अपनी चीनी मिल या जिला गन्ना अधिकारी से पुष्ट कर लें।")

# The shell's .header-wrapper is position:fixed and NOTHING in _CSS offsets the
# content under it. /bhav gets away with that because its 200px hero absorbs the
# overlap and its <h1> sits at the hero's bottom edge; this cluster opens with a
# shorter .answer block, so at 390px the h1 rendered 70px underneath the header —
# invisible on desktop, broken on the 98% of traffic that is phones.
#
# Fixed here rather than in the shared shell on purpose: ~14k /bhav pages and
# every /naksha and /product page render off that same _CSS, and re-laying-out
# all of them is not part of shipping cane prices. Heights are measured, not
# guessed — 137px below the shell's 721px breakpoint, 169px above it — plus the
# .wrap top padding each side already had (14px / 18px).
_EXTRA_CSS = """
.wrap{padding-top:151px}
@media(min-width:721px){.wrap{padding-top:187px}}
/* /bhav's card classes are all <article>, so nothing there resets anchors and
   our linked chips would render browser-default blue and underlined. */
a.chip{text-decoration:none}

/* ── at-a-glance strip ── */
.gn-stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:14px 0 18px}
.gn-stat{background:var(--white);border:1px solid var(--border);
  border-radius:var(--radius-sm);padding:12px 8px;text-align:center}
.gn-stat b{display:block;font-family:var(--font-serif);font-size:20px;font-weight:800;
  color:var(--green-dark);letter-spacing:-.5px;line-height:1.1}
.gn-stat span{display:block;font-size:10.5px;color:var(--text-soft);margin-top:5px;
  line-height:1.35;font-weight:600}

/* ── ranked rate bars ── */
.gn-panel{background:var(--white);border:1px solid var(--border);
  border-radius:var(--radius-md);padding:16px 14px;margin:14px 0}
.gn-panel-h{font-family:var(--font-serif);font-size:17px;font-weight:800;
  color:var(--text-dark);margin:0 0 3px}
.gn-panel-s{font-size:11.5px;color:var(--text-soft);margin:0 0 12px;line-height:1.5}
.gn-bars{display:flex;flex-direction:column}
.gn-bar{display:block;text-decoration:none;color:inherit;padding:11px 8px;
  margin:0 -8px;border-radius:9px;border-bottom:1px solid var(--border)}
.gn-bar:last-child{border-bottom:0}
.gn-bar.is-on{background:var(--green-pale)}
.gn-bar-top{display:flex;justify-content:space-between;align-items:baseline;gap:10px}
.gn-bar-name{font-size:14.5px;font-weight:700;color:var(--text-dark)}
.gn-bar-val{font-size:17px;font-weight:800;color:var(--green-dark);
  letter-spacing:-.4px;white-space:nowrap}
.gn-bar-track{position:relative;height:8px;border-radius:6px;
  background:var(--green-pale);margin:8px 0 6px;overflow:hidden}
.gn-bar.is-on .gn-bar-track{background:rgba(255,255,255,.75)}
.gn-bar-fill{position:absolute;top:0;left:0;bottom:0;border-radius:6px;
  background:linear-gradient(90deg,var(--green-mid),var(--green-dark))}
.gn-bar-sub{display:flex;justify-content:space-between;gap:10px;
  font-size:11px;color:var(--text-soft);font-weight:600}
.gn-bar-sub span:first-child{color:var(--green-mid);font-weight:700}

/* ── inline variety pills in the hero ── */
.gn-pills{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}
.gn-pill{display:inline-flex;align-items:baseline;gap:6px;padding:7px 12px;
  border-radius:20px;background:rgba(255,255,255,.14);
  border:1px solid rgba(255,255,255,.22);font-size:12px;font-weight:600;
  color:rgba(255,255,255,.9)}
.gn-pill b{font-size:14px;font-weight:800;color:#fff}

/* A bare <p> on the cream background reads as an orphan between two cards. */
.gn-note{font-size:12px;color:var(--text-mid);line-height:1.65;background:var(--white);
  border:1px solid var(--border);border-radius:var(--radius-sm);
  padding:12px 14px;margin:14px 0}

/* ── one-line notice, replacing a paragraph in a box ── */
.gn-flag{display:flex;gap:11px;align-items:flex-start;background:#fffaf0;
  border:1px solid #f0dcb4;border-left:4px solid var(--amber);
  border-radius:var(--radius-sm);padding:12px 14px;margin:14px 0}
.gn-flag-ic{font-size:18px;line-height:1.2;flex:0 0 auto}
.gn-flag-t{font-size:13.5px;font-weight:700;color:var(--text-dark);display:block}
.gn-flag-d{font-size:12px;color:var(--text-mid);line-height:1.55;margin-top:3px;
  display:block}

/* ── FAQ accordion ── */
.gn-faq{background:var(--white);border:1px solid var(--border);
  border-radius:var(--radius-sm);margin-bottom:8px;overflow:hidden}
.gn-faq summary{cursor:pointer;list-style:none;padding:13px 40px 13px 14px;
  font-size:13.5px;font-weight:700;color:var(--text-dark);position:relative}
.gn-faq summary::-webkit-details-marker{display:none}
.gn-faq summary::after{content:"+";position:absolute;right:14px;top:50%;
  transform:translateY(-50%);font-size:19px;font-weight:700;color:var(--green-mid)}
.gn-faq[open] summary::after{content:"–"}
.gn-faq[open] summary{border-bottom:1px solid var(--border)}
.gn-faq-a{padding:12px 14px;font-size:13px;color:var(--text-mid);line-height:1.7}

/* Two columns of bars/FAQ would be nicer than one very long column once there
   is room for it — mobile is the real layout, desktop is the variant. */
@media(min-width:721px){
  .gn-stats{max-width:640px}
  .gn-panel{max-width:720px}
  .gn-faq{max-width:720px}
}
"""


def _load() -> dict:
    """Re-read only when the file actually changes on disk, so an edit lands
    without a restart but a hit does not pay for JSON parsing."""
    try:
        mtime = _DATA.stat().st_mtime
    except OSError:
        return {"states": [], "frp": {}}
    if _cache["mtime"] != mtime:
        with _DATA.open(encoding="utf-8") as fh:
            _cache["data"] = json.load(fh)
        _cache["mtime"] = mtime
    return _cache["data"]


def _season_for(d: date) -> str:
    """'2025-26' for any day in the sugar season that opened 1 October.

    The sugar season is October–September, not the calendar year, and every
    number on these pages is quoted against one. Deriving it from the clock is
    what keeps the pages honest through the rollover with nobody editing a
    constant on 1 October — the standing rule that nothing here needs a manual
    re-run."""
    start = d.year if d.month >= 10 else d.year - 1
    return f"{start}-{str(start + 1)[2:]}"


def _states() -> list[dict]:
    return _load().get("states", [])


def _state(slug: str) -> dict | None:
    return next((s for s in _states() if s["slug"] == slug), None)


def _frp(season: str) -> dict:
    """The FRP block for a season, falling back to the newest one we hold."""
    table = _load().get("frp", {})
    if season in table:
        return table[season]
    return table[max(table)] if table else {}


def _eff_frp(recovery: float, frp: dict) -> int:
    """FRP actually payable at a mill whose recovery is above (or below) the
    10.25% base — ₹3.56 per 0.1 percentage point, which is the part farmers
    never see spelled out. Floored per the 2026-27 order: no deduction at all
    below 9.5% recovery."""
    if not frp:
        return 0
    if recovery < frp.get("floor_recovery", 9.5):
        return round(frp.get("floor_rate", frp["rate"]))
    steps = (recovery - frp["recovery"]) / 0.1
    return round(frp["rate"] + steps * frp["step"])


def _rs(n) -> str:
    """₹390 — no decimal tail on a whole rupee, which is how a rate is spoken."""
    return f"₹{n:,.0f}" if float(n) == int(float(n)) else f"₹{n:,.2f}"


def _headline(st: dict, frp: dict) -> str:
    """The one number that belongs in a state's hero: its highest declared SAP,
    else the FRP its own recovery earns, else the plain national FRP."""
    if st.get("kind") == "sap" and st.get("rates"):
        return _rs(max(r["rate"] for r in st["rates"]))
    if st.get("recovery"):
        return _rs(_eff_frp(st["recovery"], frp))
    return _rs(frp.get("rate", 0))


def _stats(items: list[tuple[str, str]]) -> str:
    """A three-tile "at a glance" strip. The numbers a farmer came for should be
    readable in one glance, not recovered from the middle of a paragraph."""
    return ('<div class="gn-stats">' + "".join(
        f'<div class="gn-stat"><b>{escape(v)}</b><span>{escape(k)}</span></div>'
        for v, k in items) + "</div>")


def _rate_bars(states: list[dict], frp: dict, current: str = "") -> str:
    """Ranked SAP states as bars, reused by the hub and every state page.

    The bar length is the gap OVER the national FRP, not the rate itself, and
    the heading says so. Drawing full rates would be either useless or
    dishonest: ₹365–₹416 from a zero baseline is five near-identical bars, and
    the usual fix — starting the axis at ₹350 — silently turns a 14% spread
    into a 10x one. The gap is the real story anyway (that is what the state
    adds on top), and it separates cleanly: +₹51 down to +₹35.
    """
    base = frp.get("rate", 0)
    gaps = [(st, max(r["rate"] for r in st["rates"]) - base) for st in states]
    widest = max((g for _, g in gaps), default=0) or 1
    rows = []
    for st, gap in gaps:
        top = max(st["rates"], key=lambda r: r["rate"])
        # Floor the width so the shortest bar is still a bar, not a sliver.
        pct = max(12, round(gap / widest * 100))
        varieties = " · ".join(f'{r["hi"].replace(" प्रजाति", "")} {_rs(r["rate"])}'
                               for r in st["rates"]) if len(st["rates"]) > 1 else ""
        rows.append(
            f'<a class="gn-bar{" is-on" if st["slug"] == current else ""}" '
            f'href="{SITE}/ganna/{st["slug"]}">'
            f'<div class="gn-bar-top"><span class="gn-bar-name">{escape(st["hi"])}</span>'
            f'<span class="gn-bar-val">{_rs(top["rate"])}</span></div>'
            f'<div class="gn-bar-track"><i class="gn-bar-fill" style="width:{pct}%"></i></div>'
            f'<div class="gn-bar-sub"><span>FRP से +{_rs(gap)}</span>'
            f'<span>{escape(varieties)}</span></div></a>')
    return f'<div class="gn-bars">{"".join(rows)}</div>'


def _faq_ui(faqs: list[tuple[str, str]]) -> tuple[str, dict]:
    """Accordion markup AND the JSON-LD from ONE list — same single-source rule
    as bhav's _faq, which exists so the two can never drift.

    Accordions rather than _faq's stacked cards: five open prose blocks were
    most of these pages' height and made them read like a manual. Collapsed,
    the answers are still in the HTML for Google and one tap away for a farmer.
    The first is open so the control is obviously a control."""
    html = "\n".join(
        f'<details class="gn-faq"{" open" if i == 0 else ""}>'
        f'<summary>{escape(q)}</summary><div class="gn-faq-a">{escape(a)}</div></details>'
        for i, (q, a) in enumerate(faqs))
    ld = {"@context": "https://schema.org", "@type": "FAQPage",
          "mainEntity": [{"@type": "Question", "name": q,
                          "acceptedAnswer": {"@type": "Answer", "text": a}}
                         for q, a in faqs]}
    return html, ld


def _mill_rows(ms: list[dict]) -> str:
    """The district's mills as capacity bars — biggest crusher first.

    Capacity IS comparable across mills in a way a cane rate is not (the rate
    is the same for all of them by law), so unlike the state bars these scale
    from zero honestly."""
    top = max((m["tcd"] for m in ms), default=0) or 1
    out = []
    for m in ms:
        pct = max(6, round(m["tcd"] / top * 100)) if m["tcd"] else 0
        cap = (f'{m["tcd"]:,} TCD' if m["tcd"] else "क्षमता दर्ज नहीं")
        out.append(
            f'<div class="gn-bar">'
            f'<div class="gn-bar-top"><span class="gn-bar-name">{escape(m["name"])}</span></div>'
            + (f'<div class="gn-bar-track"><i class="gn-bar-fill" style="width:{pct}%"></i></div>'
               if pct else '<div style="height:6px"></div>')
            + f'<div class="gn-bar-sub"><span>{escape(cap)}</span>'
              f'<span>{escape(m["registered"] and "नोंदणी " + m["registered"] or "")}</span>'
              f'</div></div>')
    return f'<div class="gn-bars">{"".join(out)}</div>'


def _district_links(state_slug: str) -> str:
    by_d = mills.by_district(state_slug)
    if not by_d:
        return ""
    order = sorted(by_d.items(), key=lambda kv: -len(kv[1]))
    return "".join(
        f'<a class="chip" href="{SITE}/ganna/{state_slug}/{d}">'
        f'{escape(ms[0]["district"])} <b>{len(ms)}</b></a>'
        for d, ms in order)


# ── sitemap ─────────────────────────────────────────────────────────────────
# Declared before /ganna/{state}: that wildcard matches any single segment,
# including this filename, and would answer the sitemap with a state page.
@router.get("/ganna/sitemap.xml")
def ganna_sitemap():
    frp = _frp(_season_for(date.today()))
    rows = [(f"{SITE}/ganna", frp.get("announced", ""))]
    for st in _states():
        # Only indexable states are submitted. A noindex page in the sitemap
        # just spends crawl budget on a URL we have already told Google to
        # ignore — the same call bhav.py makes for the unseeded buyer pages.
        if not st.get("indexed"):
            continue
        rows.append((f"{SITE}/ganna/{st['slug']}", st.get("announced", "")))
        # District pages, where a register has landed. lastmod is the day the
        # register was fetched, not today — the same rule /bhav's sitemap uses.
        src = mills.meta(st["slug"])
        for d_slug, ms in sorted(mills.by_district(st["slug"]).items()):
            if len(ms) < 2:          # single-mill districts render noindex
                continue
            rows.append((f"{SITE}/ganna/{st['slug']}/{d_slug}", src.get("fetched", "")))
    body = "\n".join(
        "  <url>\n    <loc>" + escape(u) + "</loc>"
        + (f"\n    <lastmod>{lm}</lastmod>" if lm else "")
        + "\n  </url>"
        for u, lm in rows)
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
           f"{body}\n</urlset>\n")
    return Response(xml, media_type="application/xml",
                    headers={"Cache-Control": "public, max-age=3600"})


# ── hub ─────────────────────────────────────────────────────────────────────
@router.get("/ganna", response_class=HTMLResponse)
@router.get("/ganna/", response_class=HTMLResponse)
def ganna_hub():
    data = _load()
    today = date.today()
    season = _season_for(today)
    nxt = data.get("next_season", "")
    frp_now, frp_next = _frp(season), data.get("frp", {}).get(nxt, {})
    # Between seasons the interesting number is the one already announced for
    # the season that has not opened yet — that is what a farmer is searching
    # in August. Fall back to the running season's FRP before it is declared.
    show = frp_next or frp_now
    show_season = nxt if frp_next else season

    # Three groups, not two. Lumping "declares a SAP, we have no figure" in
    # with "has no SAP at all" put बिहार and तमिलनाडु under a heading that said
    # their state has no SAP — the same false claim the state pages were fixed
    # for, still being made here. The awaited group gets its own heading.
    sap_states = [s for s in _states() if s.get("kind") == "sap" and s.get("rates")]
    sap_states.sort(key=lambda s: max(r["rate"] for r in s["rates"]), reverse=True)
    awaited_states = [s for s in _states()
                      if s.get("kind") == "sap" and not s.get("rates")]
    frp_states = [s for s in _states() if s.get("kind") != "sap"]

    def _chips(states):
        return "".join(
            f'<a class="chip" href="{SITE}/ganna/{st["slug"]}">{escape(st["hi"])}</a>'
            for st in states)

    frp_chips, awaited_chips = _chips(frp_states), _chips(awaited_states)
    awaited_block = (f"""
<h2 class="shop-section-title">जहां SAP का इंतज़ार है</h2>
<p class="note">ये राज्य SAP घोषित करते हैं, पर इस सीजन का पुष्ट रेट अभी नहीं आया।
तब तक केंद्र का FRP {_rs(show.get('rate', 0))} न्यूनतम दाम है।</p>
<div class="chips">{awaited_chips}</div>
""" if awaited_states else "")

    top_state = sap_states[0] if sap_states else None
    stats = _stats([
        (_rs(show.get("rate", 0)), "केंद्र का FRP"),
        (_rs(max(r["rate"] for r in top_state["rates"])) if top_state else "—",
         f"सबसे ऊंचा SAP · {top_state['hi']}" if top_state else "सबसे ऊंचा SAP"),
        (str(len(_states())), "गन्ना राज्य"),
    ])

    title = _fit(
        f"गन्ना का भाव {show_season} — FRP {_rs(show.get('rate', 0))} और राज्यवार SAP रेट",
        f"गन्ना मूल्य {show_season} — FRP {_rs(show.get('rate', 0))} व राज्यवार SAP",
        f"गन्ना का भाव {show_season} — FRP और राज्यवार रेट")
    desc = _fit(
        f"गन्ना का सरकारी रेट {show_season}: केंद्र का FRP {_rs(show.get('rate', 0))} प्रति "
        f"क्विंटल ({show.get('recovery', 10.25)}% रिकवरी पर)। उत्तर प्रदेश, पंजाब, हरियाणा, "
        f"उत्तराखंड समेत हर गन्ना राज्य का SAP रेट एक जगह — किस राज्य में कितना मिलेगा।",
        f"गन्ना का सरकारी रेट {show_season}: केंद्र का FRP {_rs(show.get('rate', 0))} प्रति "
        f"क्विंटल। यूपी, पंजाब, हरियाणा, उत्तराखंड समेत हर राज्य का SAP रेट एक जगह।",
        limit=162)

    faq_html, faq_ld = _faq_ui([
        ("FRP और SAP में क्या फर्क है?",
         "FRP (Fair and Remunerative Price) केंद्र सरकार तय करती है और यह पूरे देश में "
         "गन्ने का न्यूनतम दाम है — इससे कम पर कोई मिल गन्ना नहीं खरीद सकती। SAP (State "
         "Advised Price) राज्य सरकार अपने किसानों के लिए तय करती है और यह आमतौर पर FRP से "
         "ऊंचा होता है। जिस राज्य में SAP घोषित है, वहां मिल को SAP देना पड़ता है।"),
        (f"{show_season} के लिए गन्ने का FRP कितना है?",
         f"{_rs(show.get('rate', 0))} प्रति क्विंटल, {show.get('recovery', 10.25)}% बेसिक "
         f"रिकवरी पर। रिकवरी हर 0.1% बढ़ने पर {_rs(show.get('step', 3.56))} प्रति क्विंटल "
         f"और जुड़ता है, और घटने पर उतना ही कटता है — लेकिन "
         f"{show.get('floor_recovery', 9.5)}% से नीचे रिकवरी वाली मिल पर कोई कटौती नहीं "
         f"होती, वहां भी कम से कम {_rs(show.get('floor_rate', 0))} मिलता है।"),
        ("रिकवरी क्या होती है और इससे मेरा रेट क्यों बदलता है?",
         "रिकवरी का मतलब है — 100 किलो गन्ने से मिल कितनी चीनी निकाल पाई। 11% रिकवरी यानी "
         "100 किलो गन्ने से 11 किलो चीनी। FRP इसी से जुड़ा है, इसलिए ऊंची रिकवरी वाली मिल "
         "में वही गन्ना ज़्यादा दाम पाता है। रिकवरी मिल के हिसाब से अलग-अलग होती है।"),
        ("क्या मेरे राज्य का SAP घोषित हो चुका है?",
         f"राज्य आमतौर पर पेराई सीजन शुरू होने के आसपास — अक्टूबर से नवंबर के बीच — SAP "
         f"घोषित करते हैं। इस पेज पर हर राज्य का वही रेट दिया है जो सरकारी घोषणा में आया "
         f"है। जिस राज्य का नया रेट अभी घोषित नहीं हुआ, वहां केंद्र का FRP लागू रहता है।"),
        ("गन्ने का भाव मंडी में क्यों नहीं दिखता?",
         "क्योंकि गन्ना मंडी में नहीं बिकता। किसान का सट्टा जिस चीनी मिल से बंधा है, गन्ना "
         "उसी मिल को जाता है और दाम सरकार का तय किया हुआ (FRP या SAP) मिलता है। इसलिए "
         "गन्ने का रेट रोज़ नहीं बदलता, सीजन में एक बार तय होता है।"),
    ])

    crumbs = (f'<a href="{SITE}/">होम</a> › <span>गन्ना मूल्य</span>')
    ld = _ld(_crumb_ld([("होम", f"{SITE}/"), ("गन्ना मूल्य", f"{SITE}/ganna")]), faq_ld)

    body = f"""
<section class="answer">
<div class="answer-in">
<h1>गन्ना का भाव {escape(show_season)}</h1>
<div class="answer-sub">केंद्र का FRP · पूरे देश में न्यूनतम दाम</div>
<div class="answer-price">
<span class="answer-rupee">{_rs(show.get('rate', 0))}</span>
<span class="answer-delta">प्रति क्विंटल</span>
</div>
<div class="gn-pills">
<span class="gn-pill">बेसिक रिकवरी <b>{show.get('recovery', 10.25)}%</b></span>
<span class="gn-pill">हर 0.1% पर <b>+{_rs(show.get('step', 3.56))}</b></span>
<span class="gn-pill">न्यूनतम गारंटी <b>{_rs(show.get('floor_rate', 0))}</b></span>
</div>
</div>
</section>

{stats}

<div class="gn-panel">
<h2 class="gn-panel-h">किस राज्य में कितना ज़्यादा</h2>
<p class="gn-panel-s">पट्टी की लंबाई = राज्य का SAP केंद्र के FRP से कितना ऊपर है।
बड़ा अंक पूरा रेट है। राज्य पर टैप करके पूरी जानकारी देखिए।</p>
{_rate_bars(sap_states, show)}
</div>

{awaited_block}

<h2 class="shop-section-title">जहां SAP नहीं, सिर्फ FRP लागू है</h2>
<p class="note">अलग राज्य दर नहीं — असल रकम मिल की रिकवरी पर तय होती है।</p>
<div class="chips">{frp_chips}</div>

<div class="gn-flag">
<span class="gn-flag-ic">🏭</span>
<span><span class="gn-flag-t">गन्ना मंडी में नहीं बिकता</span>
<span class="gn-flag-d">आपका सट्टा जिस चीनी मिल से बंधा है, गन्ना उसी को जाता है और दाम
सरकार का तय किया हुआ मिलता है — इसीलिए यह रेट रोज़ नहीं, सीजन में एक बार बदलता है।</span></span>
</div>

<h2 class="shop-section-title">अक्सर पूछे जाने वाले सवाल</h2>
{faq_html}
"""
    return _doc(title, desc, f"{SITE}/ganna", crumbs, body, ld=ld,
                active="ganna", extra_css=_EXTRA_CSS, footer_note=_FOOTER_NOTE,
                updated=show.get("announced", ""))


# ── state ───────────────────────────────────────────────────────────────────
@router.get("/ganna/{slug}", response_class=HTMLResponse)
def ganna_state(slug: str):
    st = _state(slug)
    if not st:
        # A state we do not carry is not a 404 story worth telling — send the
        # farmer to the hub, where every state we do have is one tap away.
        return RedirectResponse(f"{SITE}/ganna", status_code=302)

    data = _load()
    today = date.today()
    season = _season_for(today)
    nxt = data.get("next_season", "")
    frp_next = data.get("frp", {}).get(nxt, {})
    show = frp_next or _frp(season)
    show_season = nxt if frp_next else season

    hi, en = st["hi"], st["en"]
    is_sap = st.get("kind") == "sap" and bool(st.get("rates"))
    big = _headline(st, show)
    st_season = st.get("season", season)

    # ---- the answer block -------------------------------------------------
    # `pills` ride inside the green hero next to the big number; `stats` is the
    # three-tile strip under it. Both replace what used to be a paragraph the
    # farmer had to read to find the same figures.
    pills, stats, detail = "", "", ""
    if is_sap:
        gap = max(r["rate"] for r in st["rates"]) - show.get("rate", 0)
        pills = '<div class="gn-pills">' + "".join(
            f'<span class="gn-pill">{escape(r["hi"].replace(" प्रजाति", ""))} '
            f'<b>{_rs(r["rate"])}</b></span>' for r in st["rates"]) + "</div>"
        hike = next((r["rate"] - r["prev"] for r in st["rates"] if r.get("prev")), 0)
        stats = _stats([
            (f"+{_rs(abs(gap))}", "केंद्र के FRP से ऊपर"),
            (f"+{_rs(hike)}" if hike else "—", "पिछले सीजन से बढ़ोतरी"),
            (_rs(show.get("rate", 0)), "केंद्र का FRP"),
        ])
        lead = (f'{hi} की मिल को यही दाम देना पड़ता है, FRP नहीं — '
                f'केंद्र के {_rs(show.get("rate", 0))} से {_rs(abs(gap))} '
                f'{"ज़्यादा" if gap > 0 else "कम"}।')
    else:
        eff = _eff_frp(st["recovery"], show) if st.get("recovery") else 0
        if st.get("recovery"):
            lead = (f'{hi} में अलग SAP नहीं — केंद्र का FRP लागू है। पर यहां की औसत रिकवरी '
                    f'{st["recovery"]}% है, इसलिए देय रकम {_rs(eff)} बैठती है।')
            pills = ('<div class="gn-pills">'
                     f'<span class="gn-pill">बेस FRP <b>{_rs(show.get("rate", 0))}</b></span>'
                     f'<span class="gn-pill">औसत रिकवरी <b>{st["recovery"]}%</b></span>'
                     "</div>")
            tiles = [(_rs(eff), "रिकवरी जोड़कर देय"),
                     (f'{st["recovery"]}%', "राज्य की औसत रिकवरी")]
            if st.get("factories"):
                tiles.append((str(st["factories"]), "चालू चीनी मिलें"))
            elif st.get("crushed_lmt"):
                tiles.append((f'{st["crushed_lmt"]}', "लाख टन पेराई"))
            else:
                tiles.append((_rs(show.get("rate", 0)), "केंद्र का FRP"))
            stats = _stats(tiles)
            if st.get("crushed_lmt") and st.get("factories"):
                detail = (f'<p class="gn-note">{st["recovery_season"]} सीजन में '
                          f'{st["factories"]} मिलों ने {st["crushed_lmt"]} लाख टन गन्ना पेरा।</p>')
        elif st.get("kind") == "sap":
            # The state HAS a SAP — we just could not source this season's
            # number. Saying "there is no SAP here" would be a false claim
            # about money, which is the one thing these pages cannot do.
            lead = (f'{hi} अपना SAP घोषित करता है, लेकिन इस सीजन का रेट हमें अभी किसी '
                    f'सरकारी घोषणा में पुष्ट नहीं मिला — इसलिए हम यहां कोई आंकड़ा नहीं दिखा '
                    f'रहे। तब तक केंद्र का FRP {_rs(show.get("rate", 0))} प्रति क्विंटल '
                    f'न्यूनतम दाम है। पुष्ट होते ही यह पेज अपडेट होगा।')
            detail = ""
        else:
            lead = (f'{hi} में अलग राज्य दर (SAP) नहीं है — यहां केंद्र का FRP ही लागू होता '
                    f'है, और आपकी मिल जो रकम देगी वह उसकी रिकवरी पर तय होगी।')
            detail = ""

    # ---- honesty about the season we are in -------------------------------
    # In August the declared SAP belongs to the season that is ending, while the
    # FRP for the season that has not opened is already out. Saying so is the
    # difference between a page that looks current and one that is.
    gap_note = ""
    if is_sap and st_season != show_season:
        gap_note = (
            f'<div class="gn-flag"><span class="gn-flag-ic">🗓️</span>'
            f'<span><span class="gn-flag-t">{escape(show_season)} का SAP अभी घोषित नहीं</span>'
            f'<span class="gn-flag-d">ऊपर का रेट {escape(st_season)} सीजन का है — अब तक की '
            f'आखिरी सरकारी घोषणा। {escape(hi)} आमतौर पर अक्टूबर–नवंबर में नया SAP घोषित करता '
            f'है; घोषणा होते ही यह पेज अपडेट होगा।</span></span></div>')

    note_html = (f'<p class="gn-note">{escape(st["note"])}</p>' if st.get("note") else "")

    others = "".join(
        f'<a class="chip" href="{SITE}/ganna/{o["slug"]}">{escape(o["hi"])}</a>'
        for o in _states() if o["slug"] != slug)

    # The hub's ranked component again, with this state lit up. "मेरा राज्य कहां
    # खड़ा है" is the question a single rate cannot answer, and it is the reason
    # a farmer taps through to a second state page at all.
    ranked = [s for s in _states() if s.get("kind") == "sap" and s.get("rates")]
    ranked.sort(key=lambda s: max(r["rate"] for r in s["rates"]), reverse=True)
    bars = _rate_bars(ranked, show, current=slug)

    # District links, where this state's register has landed. This is the only
    # crawl path into the district tier — a sitemap alone does not get a tree
    # indexed, which is exactly what stalled /bhav until static links were added.
    d_links = _district_links(slug)
    src = mills.meta(slug)
    n_mills = len(src.get("mills", []))
    district_block = (f"""
<h2 class="shop-section-title">जिलेवार चीनी मिलें</h2>
<p class="note">{escape(src.get("source", ""))} के सहकारी रजिस्टर में दर्ज
{n_mills} मिलें, {len(mills.by_district(slug))} जिलों में। निजी मिलें इस रजिस्टर में
नहीं आतीं। जिला चुनकर वहां की मिलें और उनकी पेराई क्षमता देखिए।</p>
<div class="chips">{d_links}</div>
""" if d_links else "")

    # ---- SERP copy --------------------------------------------------------
    if is_sap:
        title = _fit(
            f"{hi} गन्ना मूल्य {st_season} — SAP {big} प्रति क्विंटल",
            f"{hi} गन्ना मूल्य {st_season} — SAP {big}",
            f"{hi} गन्ना मूल्य {st_season}")
        desc = _fit(
            f"{hi} ({en}) में गन्ने का सरकारी रेट {st_season}: "
            + "，".join(f'{r["hi"]} {_rs(r["rate"])}' for r in st["rates"]).replace("，", ", ")
            + f" प्रति क्विंटल। केंद्र के FRP से तुलना, पिछले सीजन से बढ़ोतरी और घोषणा की तारीख।",
            f"{hi} में गन्ने का सरकारी रेट {st_season}: SAP {big} प्रति क्विंटल। "
            f"FRP से तुलना और पिछले सीजन से बढ़ोतरी।",
            limit=162)
    elif st.get("recovery"):
        # ₹402 is what a mill at this state's recovery owes — it is NOT "the
        # FRP", which is ₹365 flat. Titling the derived number as the FRP is
        # the kind of small false claim that costs trust in every other number
        # on the page, so both figures are named for what they are.
        base = _rs(show.get("rate", 0))
        title = _fit(
            f"{hi} गन्ना मूल्य {show_season} — FRP {base}, रिकवरी जोड़कर {big}",
            f"{hi} गन्ना मूल्य {show_season} — रिकवरी जोड़कर {big}",
            f"{hi} गन्ना मूल्य {show_season} — FRP {base}")
        desc = _fit(
            f"{hi} ({en}) में गन्ने का दाम {show_season}: अलग SAP नहीं, केंद्र का FRP {base} "
            f"प्रति क्विंटल लागू है। यहां की {st['recovery']}% औसत रिकवरी जोड़कर देय रकम {big} "
            f"बैठती है। रिकवरी से रेट कैसे बदलता है — पूरी जानकारी।",
            f"{hi} में गन्ने का दाम {show_season}: FRP {base}, {st['recovery']}% रिकवरी "
            f"जोड़कर {big} प्रति क्विंटल।",
            limit=162)
    elif st.get("kind") == "sap":
        # NOT "SAP और FRP ₹365" — that reads as though the SAP were ₹365.
        title = _fit(
            f"{hi} गन्ना मूल्य {show_season} — FRP {big}, SAP का इंतज़ार",
            f"{hi} गन्ना मूल्य {show_season} — FRP {big}",
            f"{hi} गन्ना मूल्य {show_season}")
        desc = _fit(
            f"{hi} ({en}) में गन्ने का दाम {show_season}: राज्य का SAP इस सीजन के लिए अभी "
            f"पुष्ट नहीं है, इसलिए केंद्र का FRP {big} प्रति क्विंटल न्यूनतम दाम है। SAP कैसे "
            f"तय होता है और भुगतान के नियम क्या हैं — पूरी जानकारी।",
            f"{hi} में गन्ने का दाम {show_season}: राज्य का SAP अभी पुष्ट नहीं, केंद्र का "
            f"FRP {big} प्रति क्विंटल लागू है।",
            limit=162)
    else:
        title = _fit(
            f"{hi} गन्ना मूल्य {show_season} — FRP {big} प्रति क्विंटल",
            f"{hi} गन्ना मूल्य {show_season} — FRP {big}",
            f"{hi} गन्ना मूल्य {show_season}")
        desc = _fit(
            f"{hi} ({en}) में गन्ने का दाम {show_season}: यहां अलग SAP नहीं, केंद्र का FRP "
            f"{big} प्रति क्विंटल लागू है। रिकवरी के हिसाब से असल में देय रकम कैसे तय होती "
            f"है और भुगतान के नियम क्या हैं — पूरी जानकारी।",
            f"{hi} में गन्ने का दाम {show_season}: अलग SAP नहीं, केंद्र का FRP {big} "
            f"प्रति क्विंटल लागू।",
            limit=162)

    # Same three-way split as the SERP copy: a state that HAS a SAP we could
    # not source must never be described as one that has none.
    if is_sap:
        rate_answer = (f"{st_season} सीजन के लिए " + ", ".join(
            f'{r["hi"]} का SAP {_rs(r["rate"])} प्रति क्विंटल' for r in st["rates"]) + "।")
    elif st.get("recovery"):
        rate_answer = (
            f"{hi} में अलग राज्य दर नहीं है। केंद्र का FRP {_rs(show.get('rate', 0))} प्रति "
            f"क्विंटल लागू होता है, और यहां की {st['recovery']}% औसत रिकवरी जोड़कर देय रकम "
            f"{_rs(_eff_frp(st['recovery'], show))} प्रति क्विंटल बैठती है।")
    elif st.get("kind") == "sap":
        rate_answer = (
            f"{hi} अपना SAP घोषित करता है, लेकिन इस सीजन का पुष्ट रेट हमारे पास अभी नहीं है, "
            f"इसलिए हम कोई आंकड़ा नहीं दिखा रहे। तब तक केंद्र का FRP "
            f"{_rs(show.get('rate', 0))} प्रति क्विंटल न्यूनतम दाम है।")
    else:
        rate_answer = (
            f"{hi} में अलग राज्य दर (SAP) नहीं है। केंद्र का FRP "
            f"{_rs(show.get('rate', 0))} प्रति क्विंटल लागू होता है, और असल रकम आपकी मिल की "
            f"रिकवरी पर तय होती है।")

    faq_html, faq_ld = _faq_ui([
        (f"{hi} में गन्ने का रेट कितना है?", rate_answer),
        ("यह रेट कब से लागू है?",
         (f"{st_season} पेराई सीजन के लिए।" if is_sap else
          f"{show_season} पेराई सीजन के लिए, जो {show.get('effective_from', '1 अक्टूबर')} "
          f"से शुरू होता है।")
         + " पेराई सीजन अक्टूबर से सितंबर तक चलता है, इसलिए रेट कैलेंडर साल से नहीं, सीजन से जुड़ा है।"),
        ("मिल तय रेट से कम दे तो क्या करें?",
         "FRP और SAP दोनों कानूनी न्यूनतम दाम हैं — इससे कम पर गन्ना खरीदना गन्ना नियंत्रण "
         "आदेश का उल्लंघन है। ऐसी शिकायत अपने जिला गन्ना अधिकारी या राज्य के गन्ना आयुक्त "
         "कार्यालय में दर्ज कराई जा सकती है।"),
        ("भुगतान कितने दिन में मिलना चाहिए?",
         "गन्ना नियंत्रण आदेश के तहत मिल को गन्ना तौल के 14 दिन के भीतर भुगतान करना होता "
         "है। देर होने पर बकाया रकम पर ब्याज देना बनता है।"),
    ])

    crumbs = (f'<a href="{SITE}/">होम</a> › <a href="{SITE}/ganna">गन्ना मूल्य</a> › '
              f'<span>{escape(hi)}</span>')
    ld = _ld(_crumb_ld([("होम", f"{SITE}/"), ("गन्ना मूल्य", f"{SITE}/ganna"),
                        (hi, f"{SITE}/ganna/{slug}")]), faq_ld)

    body = f"""
<section class="answer">
<div class="answer-in">
<h1>{escape(hi)} में गन्ने का भाव</h1>
<div class="answer-sub">{escape(en)} · {escape(st_season)} पेराई सीजन</div>
<div class="answer-price">
<span class="answer-rupee">{big}</span>
<span class="answer-delta">प्रति क्विंटल</span>
</div>
<p class="answer-lead">{escape(lead)}</p>
{pills}
</div>
</section>

{stats}
{gap_note}
{detail}
{note_html}

<div class="gn-panel">
<h2 class="gn-panel-h">देश में कहां खड़ा है</h2>
<p class="gn-panel-s">पट्टी की लंबाई = राज्य का SAP केंद्र के FRP से कितना ऊपर है।</p>
{bars}
</div>

{district_block}

<h2 class="shop-section-title">बाकी राज्य</h2>
<div class="chips">{others}</div>

<h2 class="shop-section-title">अक्सर पूछे जाने वाले सवाल</h2>
{faq_html}

<div class="gn-flag">
<span class="gn-flag-ic">🏭</span>
<span><span class="gn-flag-t">गन्ना मंडी में नहीं बिकता</span>
<span class="gn-flag-d">इसीलिए यह रेट <a href="{SITE}/bhav">मंडी भाव</a> में नहीं मिलेगा।
अपने ज़िले की बाकी फसलों का आज का रेट देखने के लिए भाव पेज खोलिए।</span></span>
</div>
"""
    # A state with no verified number of its own is served noindex: its only
    # content would be the national FRP repeated back, and 7 such pages is
    # exactly the thin-content bloat this cluster was built to avoid. It stays
    # reachable and useful for a farmer who lands on it — just not submitted.
    robots = "" if st.get("indexed") else "noindex,follow"
    return _doc(title, desc, f"{SITE}/ganna/{slug}", crumbs, body, ld=ld,
                active="ganna", extra_css=_EXTRA_CSS, footer_note=_FOOTER_NOTE, robots=robots,
                updated=st.get("announced", ""))


# ── district (tier 3) ───────────────────────────────────────────────────────
@router.get("/ganna/{state_slug}/{dist_slug}", response_class=HTMLResponse)
def ganna_district(state_slug: str, dist_slug: str):
    """One district's sugar mills.

    Only states whose register we actually hold get these pages. Everything
    else 302s to the state page rather than rendering an empty list — a page
    headed "your district's mills" with nothing under it is worse than not
    existing, and it is the shape Google punishes hardest.
    """
    st = _state(state_slug)
    by_d = mills.by_district(state_slug)
    ms = by_d.get(dist_slug or "")
    if not st or not ms:
        return RedirectResponse(f"{SITE}/ganna/{state_slug}" if st else f"{SITE}/ganna",
                                status_code=302)

    src = mills.meta(state_slug)
    data = _load()
    season = _season_for(date.today())
    nxt = data.get("next_season", "")
    show = data.get("frp", {}).get(nxt, {}) or _frp(season)
    show_season = nxt if data.get("frp", {}).get(nxt) else season

    d_hi = ms[0]["district"]
    hi = st["hi"]
    rate = _headline(st, show)
    total_tcd = sum(m["tcd"] for m in ms)
    biggest = max(ms, key=lambda m: m["tcd"])

    stats = _stats([
        (str(len(ms)), "सहकारी चीनी मिलें"),
        (f"{total_tcd:,}", "कुल पेराई क्षमता (TCD)"),
        (rate, f"गन्ना रेट · {show_season}"),
    ])

    # The register is co-operatives only. Saying so on every page that uses it
    # is the whole difference between a useful list and a misleading one.
    scope = (
        '<div class="gn-flag"><span class="gn-flag-ic">ℹ️</span>'
        '<span><span class="gn-flag-t">यह सूची सहकारी चीनी मिलों की है</span>'
        f'<span class="gn-flag-d">{escape(src.get("source", ""))} के सहकारी रजिस्टर से। '
        f'{escape(d_hi)} जिले की निजी (प्राइवेट) चीनी मिलें इस रजिस्टर में दर्ज नहीं होतीं, '
        f'इसलिए वे यहां नहीं दिखेंगी।</span></span></div>')

    title = _fit(
        f"{d_hi} की चीनी मिलें — {len(ms)} सहकारी मिल, गन्ना रेट {rate}",
        f"{d_hi} की चीनी मिलें — {len(ms)} सहकारी मिल की सूची",
        f"{d_hi} की चीनी मिलें — सूची और गन्ना रेट")
    desc = _fit(
        f"{d_hi} जिले ({hi}) की {len(ms)} सहकारी चीनी मिलों की सूची — हर मिल का नाम और "
        f"पेराई क्षमता, सबसे बड़ी {biggest['tcd']:,} TCD। गन्ने का रेट {show_season}: "
        f"{rate} प्रति क्विंटल।",
        f"{d_hi} जिले की {len(ms)} सहकारी चीनी मिलें — नाम, पेराई क्षमता और "
        f"गन्ने का रेट {rate} प्रति क्विंटल।",
        limit=162)

    faq_html, faq_ld = _faq_ui([
        (f"{d_hi} जिले में कितनी चीनी मिलें हैं?",
         f"{escape(src.get('source', 'राज्य साखर आयुक्तालय'))} के सहकारी रजिस्टर में "
         f"{d_hi} जिले की {len(ms)} सहकारी चीनी मिलें दर्ज हैं। निजी मिलें इस रजिस्टर में "
         f"नहीं आतीं, इसलिए जिले में कुल मिलें इससे ज़्यादा हो सकती हैं।"),
        ("पेराई क्षमता (TCD) का क्या मतलब है?",
         "TCD यानी Tonnes Crushed per Day — मिल एक दिन में कितने टन गन्ना पेर सकती है। "
         "बड़ी क्षमता वाली मिल सीजन में ज़्यादा गन्ना लेती है, इसलिए वहां पर्ची और तौल का "
         "इंतज़ार आमतौर पर कम रहता है।"),
        (f"{d_hi} में गन्ने का रेट क्या है?",
         f"{hi} में गन्ने का दाम {rate} प्रति क्विंटल है — यह पूरे राज्य में एक जैसा लागू "
         f"होता है, जिला या मिल के हिसाब से नहीं बदलता। पूरी जानकारी {hi} के पेज पर है।"),
        ("मिल भुगतान न करे तो कहां शिकायत करें?",
         "गन्ना नियंत्रण आदेश के तहत मिल को तौल के 14 दिन के भीतर भुगतान करना होता है। "
         "देर होने पर जिला गन्ना अधिकारी या राज्य के साखर आयुक्त कार्यालय में शिकायत "
         "दर्ज कराई जा सकती है।"),
    ])

    crumbs = (f'<a href="{SITE}/">होम</a> › <a href="{SITE}/ganna">गन्ना मूल्य</a> › '
              f'<a href="{SITE}/ganna/{state_slug}">{escape(hi)}</a> › '
              f'<span>{escape(d_hi)}</span>')
    ld = _ld(_crumb_ld([("होम", f"{SITE}/"), ("गन्ना मूल्य", f"{SITE}/ganna"),
                        (hi, f"{SITE}/ganna/{state_slug}"),
                        (d_hi, f"{SITE}/ganna/{state_slug}/{dist_slug}")]), faq_ld)

    others = "".join(
        f'<a class="chip" href="{SITE}/ganna/{state_slug}/{d}">{escape(o[0]["district"])}</a>'
        for d, o in sorted(by_d.items(), key=lambda kv: -len(kv[1]))[:12] if d != dist_slug)

    body = f"""
<section class="answer">
<div class="answer-in">
<h1>{escape(d_hi)} जिले की चीनी मिलें</h1>
<div class="answer-sub">{escape(hi)} · सहकारी रजिस्टर</div>
<div class="answer-price">
<span class="answer-rupee">{len(ms)}</span>
<span class="answer-delta">सहकारी मिलें</span>
</div>
<p class="answer-lead">गन्ने का दाम {escape(hi)} में हर मिल पर एक ही है — {rate} प्रति
क्विंटल। मिल चुनने से रेट नहीं बदलता, पर पेराई क्षमता से यह तय होता है कि सीजन में
कितनी जल्दी नंबर आता है।</p>
</div>
</section>

{stats}
{scope}

<div class="gn-panel">
<h2 class="gn-panel-h">मिलें — पेराई क्षमता के हिसाब से</h2>
<p class="gn-panel-s">पट्टी की लंबाई = मिल की रोज़ की पेराई क्षमता (TCD)।
सबसे बड़ी मिल सबसे ऊपर।</p>
{_mill_rows(ms)}
</div>

<h2 class="shop-section-title">{escape(hi)} के दूसरे जिले</h2>
<div class="chips">{others}</div>

<h2 class="shop-section-title">अक्सर पूछे जाने वाले सवाल</h2>
{faq_html}
"""
    # One named mill plus the state rate is a real page; a district with a
    # single entry is close enough to thin that it is not worth submitting.
    robots = "" if len(ms) >= 2 else "noindex,follow"
    return _doc(title, desc, f"{SITE}/ganna/{state_slug}/{dist_slug}", crumbs, body,
                ld=ld, active="ganna", extra_css=_EXTRA_CSS,
                footer_note=_FOOTER_NOTE, robots=robots,
                updated=src.get("fetched", ""))
