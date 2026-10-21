# -*- coding: utf-8 -*-
# ============================================================
# KrashiMitra — the /sarkari_yojana hub, generated from the scheme articles.
#
# WHY THIS EXISTS
# ---------------
# The hub's twelve cards were hand-written in June 2026 and never touched
# again. By October they promised eligibility ("पात्रता: सभी किसान परिवार"),
# printed a PM-KISAN installment window that had long passed, pushed bank
# loans and a post-office savings product behind "अभी आवेदन करें" buttons,
# called a 2017 loan waiver "✓ चालू है", and carried a fake "KCC लोन —
# पात्रता जांचें" ad. Every one of those breaks LEGAL_RULES §1 or §3. Meanwhile
# the 26 scheme guides that actually earn search traffic (UP dhan kharid, MP
# e-uparjan, MahaDBT ...) were mostly not linked from it at all.
#
# So the hub no longer has authored cards. It lists every scheme article in
# tools/articles/ (is_scheme_article), filed under the state its ARTICLE dict
# names, and links to the guide. The guide carries the facts, the official
# link and the private-website notice; the hub carries no amount, eligibility,
# date or "apply" button of its own. A new scheme article appears here the
# moment the builder runs — article_builder.build_one() calls sync().
#
# WHAT IT WRITES — the regions between <!-- yojana-hub:NAME --> markers in
# frontend/sarkari_yojana.html. Everything outside them (shell, CSS, ads,
# private-website notice) stays hand-maintained.
#
#   python tools/yojana_hub.py           # rewrite the regions
#   python tools/yojana_hub.py --check   # exit 1 if the page is out of date
#
# tests/test_yojana_hub.py fails CI when the page on disk is not what this
# would write, so a hand edit inside a region cannot survive.
# ============================================================

from __future__ import annotations

import argparse
import html
import importlib.util
import json
import re
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
CONTENT_DIR = TOOLS / "articles"
ARTICLES = ROOT / "frontend" / "articles"
HUB = ROOT / "frontend" / "sarkari_yojana.html"
SITE = "https://krashimitra.in"

sys.path.insert(0, str(TOOLS))
from article_scheme_notice import is_scheme_article  # noqa: E402

# Every scheme article must name one of these as ARTICLE["state"]. The order is
# the order of the filter buttons; a state with no article gets no button.
STATES = {
    "central": "केंद्र सरकार",
    "up": "उत्तर प्रदेश",
    "mp": "मध्य प्रदेश",
    "mh": "महाराष्ट्र",
    "rj": "राजस्थान",
    "br": "बिहार",
    "cg": "छत्तीसगढ़",
    "hr": "हरियाणा",
    "pb": "पंजाब",
    "gj": "गुजरात",
    "ka": "कर्नाटक",
    "tn": "तमिलनाडु",
    "ap": "आंध्र प्रदेश",
    "ts": "तेलंगाना",
    "wb": "पश्चिम बंगाल",
    "od": "ओडिशा",
    "jh": "झारखंड",
    "uk": "उत्तराखंड",
}

# Scheme pages that predate the builder and have no content module.
# (slug, file in frontend/articles, state, emoji, card background)
LEGACY = [
    ("pm-kisan-samman-nidhi", "PM-kisan-samman-nidhi.html", "central", "🌾", "#e8f5e9"),
]

# Visible FAQ and its FAQPage JSON-LD come from this one list, so they cannot
# drift. Answers never state an amount, a date or who is eligible (§3) — they
# send the farmer to the official source. The UP answer is generated, see faqs().
FAQS = [
    ("क्या KrashiMitra पर सरकारी योजना का आवेदन होता है?",
     "नहीं। KrashiMitra एक <strong>निजी वेबसाइट</strong> है — हम न आवेदन लेते हैं, "
     "न कोई फ़ीस। यहाँ हर योजना की आसान हिंदी गाइड है; आवेदन सिर्फ़ योजना के "
     "<strong>आधिकारिक पोर्टल</strong>, CSC केंद्र या अपने कृषि विभाग के दफ़्तर में करें।"),
    ("PM KISAN paisa kab aayega? (PM किसान की किस्त कब आएगी?)",
     "किस्त की तारीख केंद्र सरकार घोषित करती है — कोई वेबसाइट उसे पहले से पक्का नहीं "
     "बता सकती। अपनी किस्त का स्टेटस <strong>pmkisan.gov.in</strong> पर देखें। किस्त रुकी "
     "हो तो सबसे आम वजहें होती हैं: e-KYC बाकी होना, बैंक खाते का आधार से न जुड़ा होना, "
     "या ज़मीन का रिकॉर्ड सत्यापित न होना। पूरी प्रक्रिया "
     '<a href="/articles/pm-kisan-samman-nidhi">PM किसान गाइड</a> में है।'),
    ("धान-गेहूं MSP पर बेचने का पंजीकरण कहाँ होता है?",
     "हर राज्य का अपना पोर्टल है — जैसे UP में खाद्य एवं रसद विभाग का पोर्टल, MP में "
     "ई-उपार्जन, हरियाणा में मेरी फसल मेरा ब्यौरा और पंजाब में अनाज खरीद पोर्टल। "
     "पंजीकरण की तारीखें हर सीज़न में अलग घोषित होती हैं, और <strong>पंजीकरण के बिना "
     "सरकारी केंद्र पर उपज नहीं तुलती</strong>। अपने राज्य की गाइड ऊपर राज्य वाले बटन से खोलें।"),
    ("योजना में कितना पैसा मिलेगा, और मैं पात्र हूँ या नहीं?",
     "यह सिर्फ़ योजना का विभाग तय करता है। हमारी गाइड बताती है कि आधिकारिक नियम क्या "
     "कहते हैं, पर पात्रता, राशि और तारीखें बदलती रहती हैं — आवेदन से पहले आधिकारिक "
     "वेबसाइट या कृषि विभाग से पुष्टि करें। KrashiMitra किसी राशि या पात्रता की "
     "गारंटी नहीं देता।"),
    ("कोई फ़ोन पर योजना के नाम पर OTP या पैसे माँगे तो क्या करें?",
     "न OTP बताएँ, न पैसे भेजें। सरकारी योजनाएं फ़ोन पर OTP, UPI PIN या बैंक की जानकारी "
     "नहीं माँगतीं। ऐसी कॉल या मैसेज की शिकायत राष्ट्रीय साइबर क्राइम हेल्पलाइन "
     "<strong>1930</strong> या <strong>cybercrime.gov.in</strong> पर करें।"),
]

_REGION = "<!-- yojana-hub:{0} -->\n{1}<!-- /yojana-hub:{0} -->"
_REGION_RE = r"<!-- yojana-hub:{0} -->\n.*?<!-- /yojana-hub:{0} -->"


def _esc(s: str) -> str:
    return html.escape(s, quote=True)


def _plain(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s))).strip()


def _load(path: Path) -> dict:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.ARTICLE


def _meta(doc: str, name: str) -> str:
    m = re.search(rf'<meta name="{name}" content="([^"]*)"', doc)
    return html.unescape(m.group(1)) if m else ""


def entries() -> list[dict]:
    """Every scheme guide, grouped by state in STATES order, newest first within.

    Raises ValueError naming each scheme article with no valid state — a guide
    that cannot be filed is a build failure, not a silent omission.
    """
    out, missing = [], []
    for f in sorted(CONTENT_DIR.glob("*.py")):
        if f.name.startswith("_"):
            continue
        a = _load(f)
        if not is_scheme_article(a):
            continue
        if a.get("state") not in STATES:
            missing.append(f.name)
            continue
        c = a["card"]
        out.append({
            "slug": a["slug"], "name": a["h1"], "desc": a["description"],
            "state": a["state"], "emoji": c["emoji"], "bg": c["bg"],
            "search": f'{c["keywords"]} {a["slug"].replace("-", " ")}',
            "date": a.get("date_modified", a["date"]), "lang": a.get("lang", "hi"),
        })
    if missing:
        raise ValueError(
            'scheme article(s) without ARTICLE["state"] (one of '
            f'{", ".join(STATES)}): {", ".join(missing)}')
    for slug, fname, state, emoji, bg in LEGACY:
        doc = (ARTICLES / fname).read_text(encoding="utf-8")
        title = _plain(re.search(r"<title>(.*?)</title>", doc, re.S).group(1))
        modified = re.search(r'"dateModified":\s*"(\d{4}-\d\d-\d\d)', doc)
        out.append({
            "slug": slug, "name": title.split("—")[0].strip(),
            "desc": _meta(doc, "description"), "state": state, "emoji": emoji,
            "bg": bg, "search": f'{title} {slug.replace("-", " ")}'.lower(),
            "date": modified.group(1) if modified else "", "lang": "hi",
        })
    order = list(STATES)
    out.sort(key=lambda e: e["date"], reverse=True)
    out.sort(key=lambda e: order.index(e["state"]))
    return out


def _states(es: list[dict]) -> list[tuple[str, str, int]]:
    return [(k, v, n) for k, v in STATES.items()
            if (n := sum(e["state"] == k for e in es))]


def faqs(es: list[dict]) -> list[tuple[str, str]]:
    up = [e for e in es if e["state"] in ("up", "central")]
    links = ", ".join(f'<a href="/articles/{e["slug"]}">{_esc(e["name"])}</a>' for e in up)
    return FAQS + [(
        "Sarkari kisan yojana UP 2026 — UP के किसान के लिए कौन-सी गाइड हैं?",
        f"UP के किसान के काम की गाइड: {links}। तारीखें और नियम हर साल बदलते हैं, "
        "इसलिए आवेदन से पहले आधिकारिक पोर्टल पर पुष्टि करें।")]


# ── the regions ─────────────────────────────────────────────────────────────

def _navbar(es):
    rows = ['    <button class="cnav-item" onclick="quickJumpFilter(\'all\')">📋 सभी योजनाएं</button>\n']
    rows += [f'    <button class="cnav-item" onclick="quickJumpFilter(\'{k}\')">📍 {v}</button>\n'
             for k, v, _ in _states(es)]
    return "".join(rows)


def _badges(es):
    k = sum(1 for s, *_ in _states(es) if s != "central")
    return (f'      <span class="hero-badge">📋 {len(es)} योजना गाइड</span>\n'
            f'      <span class="hero-badge">🗺️ केंद्र + {k} राज्य</span>\n'
            '      <span class="hero-badge">🔗 हर गाइड में आधिकारिक पोर्टल</span>\n'
            '      <span class="hero-badge">🆓 मुफ्त जानकारी</span>\n')


def _intro(es):
    states = _states(es)
    central = sum(n for k, _, n in states if k == "central")
    names = ", ".join(v for k, v, _ in states if k != "central")
    return (
        '    <section style="background:var(--white);border:1.5px solid var(--border-card);'
        'border-radius:var(--radius);padding:20px 22px;margin-bottom:24px;">\n'
        '      <h2 style="font-size:16px;font-weight:700;color:var(--green-dark);'
        'margin-bottom:10px;">सरकारी किसान योजना 2026 — केंद्र और राज्यों की गाइड</h2>\n'
        '      <p style="font-size:13px;color:var(--text-mid);line-height:1.75;">\n'
        f'        यहाँ केंद्र सरकार की {central} और {names} की {len(es) - central} योजनाओं व '
        'सरकारी खरीद (MSP) पंजीकरण की आसान हिंदी गाइड हैं। हर गाइड बताती है कि आवेदन '
        'कहाँ होता है, कौन-से कागज़ लगते हैं और आधिकारिक पोर्टल कौन-सा है। अपने राज्य '
        'का बटन दबाएँ।\n'
        '      </p>\n'
        '    </section>\n')


def _chips(es):
    rows = [f'      <button class="chip active" id="chip-all" '
            f'onclick="setFilter(\'all\',this)">सभी ({len(es)})</button>\n']
    rows += [f'      <button class="chip" id="chip-{k}" '
             f'onclick="setFilter(\'{k}\',this)">{v} ({n})</button>\n'
             for k, v, n in _states(es)]
    return "".join(rows)


def _count(es):
    return (f'      <div class="result-count" id="resultCount">{len(es)} योजनाएं मिलीं</div>\n'
            '      <div class="result-hint">पूरी गाइड पढ़ें — आवेदन आधिकारिक पोर्टल पर</div>\n')


def _cards(es):
    out = []
    for e in es:
        lang = f' lang="{e["lang"]}"' if e["lang"] != "hi" else ""
        out.append(
            f'      <article class="scheme-card"{lang} data-tags="{e["state"]} all" '
            f'data-search="{_esc(e["search"].lower())}">\n'
            '        <div class="card-top">\n'
            f'          <div class="card-icon-wrap" style="background:{e["bg"]}">{e["emoji"]}</div>\n'
            '          <div class="card-meta">\n'
            f'            <h3 class="card-name">{_esc(e["name"])}</h3>\n'
            f'            <p class="card-desc">{_esc(e["desc"])}</p>\n'
            f'            <span class="card-tag">📍 {STATES[e["state"]]}</span>\n'
            '          </div>\n'
            '        </div>\n'
            '        <div class="card-footer">\n'
            f'          <a class="btn-apply" href="/articles/{e["slug"]}">📖 पूरी गाइड पढ़ें</a>\n'
            f'          <button class="btn-wa" data-name="{_esc(e["name"])}" '
            'onclick="whatsappHelp(this.dataset.name)">🟢 मदद</button>\n'
            '        </div>\n'
            '      </article>\n')
    return "\n".join(out)


def _faq(es):
    items = "".join(
        '        <details style="background:var(--white);border:1.5px solid var(--border-card);'
        'border-radius:var(--radius-sm);padding:14px 18px;cursor:pointer;">\n'
        '          <summary style="font-size:14px;font-weight:700;color:var(--green-dark);'
        'list-style:none;display:flex;align-items:center;gap:8px;">\n'
        '            <span style="color:var(--amber);font-size:16px;">❓</span>\n'
        f'            {q}\n'
        '          </summary>\n'
        '          <p style="margin-top:10px;font-size:13px;color:var(--text-mid);line-height:1.75;">\n'
        f'            {a}\n'
        '          </p>\n'
        '        </details>\n\n'
        for q, a in faqs(es))
    return (
        '    <section style="margin-top:20px;" id="faq-section">\n'
        '      <h2 style="font-size:18px;font-weight:700;color:var(--green-dark);'
        'margin-bottom:16px;">अक्सर पूछे जाने वाले सवाल — सरकारी किसान योजना 2026</h2>\n\n'
        '      <div style="display:flex;flex-direction:column;gap:10px;">\n\n'
        f'{items}'
        '      </div>\n'
        '    </section>\n')


def _ld(obj, indent: int | None = 2) -> str:
    body = json.dumps(obj, ensure_ascii=False, indent=indent)
    return f'<script type="application/ld+json">\n{body}\n</script>\n'


def _faq_ld(es):
    return _ld({
        "@context": "https://schema.org", "@type": "FAQPage",
        "mainEntity": [{"@type": "Question", "name": _plain(q),
                        "acceptedAnswer": {"@type": "Answer", "text": _plain(a)}}
                       for q, a in faqs(es)],
    })


def _list_ld(es):
    return _ld({
        "@context": "https://schema.org", "@type": "ItemList",
        "name": "सरकारी किसान योजना 2026 — केंद्र और राज्यों की गाइड",
        "url": f"{SITE}/sarkari_yojana",
        "numberOfItems": len(es),
        "itemListElement": [{"@type": "ListItem", "position": i,
                             "name": _plain(e["name"]),
                             "url": f'{SITE}/articles/{e["slug"]}'}
                            for i, e in enumerate(es, 1)],
    }, indent=None)  # one line: 30 items pretty-printed are 180 lines of page weight


REGIONS = {
    "navbar": _navbar, "badges": _badges, "intro": _intro, "chips": _chips,
    "count": _count, "cards": _cards, "faq": _faq, "faq-ld": _faq_ld,
    "list-ld": _list_ld,
}


def render(doc: str, es: list[dict] | None = None) -> str:
    es = entries() if es is None else es
    for name, fn in REGIONS.items():
        pat = re.compile(_REGION_RE.format(re.escape(name)), re.S)
        if not pat.search(doc):
            raise ValueError(f"{HUB.name}: region marker '{name}' is missing")
        new = _REGION.format(name, fn(es))
        doc = pat.sub(lambda _m: new, doc, count=1)
    # The WebPage JSON-LD's dateModified follows the newest guide listed.
    newest = max((e["date"] for e in es if e["date"]), default="")
    if newest:
        doc = re.sub(r'("@type": "WebPage",.*?"dateModified": ")[^"]*(")',
                     lambda m: m.group(1) + newest + m.group(2), doc, count=1, flags=re.S)
    return doc


def sync(write: bool = True) -> bool:
    """Rewrite the hub's regions; return True if the page changed (or would)."""
    doc = HUB.read_text(encoding="utf-8")
    new = render(doc)
    if new != doc and write:
        HUB.write_text(new, encoding="utf-8")
    return new != doc


def main() -> int:
    p = argparse.ArgumentParser(description="Regenerate the /sarkari_yojana hub.")
    p.add_argument("--check", action="store_true", help="exit 1 if out of date")
    args = p.parse_args()
    changed = sync(write=not args.check)
    n = len(entries())
    if args.check:
        print(f"{HUB.name}: {'OUT OF DATE' if changed else 'up to date'} ({n} guides)")
        return 1 if changed else 0
    print(f"{HUB.name}: {'rewritten' if changed else 'unchanged'} ({n} guides)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
