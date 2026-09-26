# -*- coding: utf-8 -*-
# ============================================================
# KrashiMitra — the "we are a private website" notice every scheme
# (सरकारी योजना) article must show.
#
# WHY THIS EXISTS
# ---------------
# LEGAL_RULES.md §1 and §3: scheme pages must say we are a private website,
# never promise eligibility or an amount, and never take applications or fees.
# The /sarkari_yojana hub said so; the ~20 scheme ARTICLES did not — found on
# 26 Sep 2026, when the नक्शा district pages were about to start linking them.
# A farmer who lands on "महाडीबीटी शेतकरी योजना" from Google cannot tell a
# private explainer from the portal itself unless the page tells him, and a
# page that looks official is exactly what the "pretending to be the
# government" rule forbids.
#
# HOW IT IS WIRED — the same three seams as tools/article_advisory.py
# -------------------------------------------------------------------
#   * article_builder.render() injects scheme_notice_html() for every article
#     whose section is a scheme section (is_scheme_section) — no per-article
#     opt-in, because the author who has to remember it forgets it once.
#   * validate() fails the build for a scheme page without the mark.
#   * sweep() inserts it into the module-less legacy pages, idempotently; the
#     builder's --all runs it.
# tests/test_scheme_private_notice.py then holds every page on disk to it,
# whichever path produced the page.
#
# ARTICLE["scheme"] = True forces it on for a scheme page filed under another
# section. There is deliberately no way to force it off.
# ============================================================

from __future__ import annotations

import re

# The marker validate() and the test look for. Changing it silently disarms
# both, so it lives here next to the markup that carries it.
SCHEME_MARK = "data-km-private-notice"

# Section names that make a page a scheme page, as authors have spelled them.
_SCHEME_SECTION_RE = re.compile(
    r"^\s*(सरकारी\s+योजना(?:एं|एँ|ओं)?|ಸರ್ಕಾರಿ\s+ಯೋಜನೆ(?:ಗಳು)?|"
    r"அரசு\s+திட்ட(?:ம்|ங்கள்)|government\s+schemes?)\s*$", re.I)


def is_scheme_section(section: str) -> bool:
    return bool(_SCHEME_SECTION_RE.match(section or ""))


def is_scheme_article(a: dict) -> bool:
    return bool(a.get("scheme")) or is_scheme_section(a.get("section", ""))


# ── the block ──────────────────────────────────────────────────────────────
# Four claims, each one a rule in LEGAL_RULES: private, not government → we
# take no application or fee → we promise no eligibility or amount → the
# official site / office is the authority.
_COPY = {
    "hi": ("KrashiMitra एक <strong>निजी वेबसाइट</strong> है — सरकारी वेबसाइट नहीं, और "
           "किसी सरकारी विभाग से जुड़ी नहीं।",
           "हम किसी योजना का <strong>आवेदन या फ़ीस नहीं लेते</strong>, और पात्रता या "
           "मिलने वाली राशि की कोई गारंटी नहीं देते।",
           "नियम, तारीख़ें और राशि बदलती रहती हैं — आवेदन से पहले योजना की "
           "<strong>आधिकारिक वेबसाइट</strong>, अपने कृषि विभाग या CSC केंद्र से पुष्टि करें।"),
    "kn": ("KrashiMitra ಒಂದು <strong>ಖಾಸಗಿ ವೆಬ್‌ಸೈಟ್</strong> — ಸರ್ಕಾರಿ ವೆಬ್‌ಸೈಟ್ ಅಲ್ಲ, "
           "ಯಾವುದೇ ಸರ್ಕಾರಿ ಇಲಾಖೆಗೆ ಸೇರಿಲ್ಲ.",
           "ನಾವು ಯಾವುದೇ ಯೋಜನೆಯ <strong>ಅರ್ಜಿ ಅಥವಾ ಶುಲ್ಕ ತೆಗೆದುಕೊಳ್ಳುವುದಿಲ್ಲ</strong>, "
           "ಅರ್ಹತೆ ಅಥವಾ ಸಿಗುವ ಮೊತ್ತದ ಯಾವುದೇ ಭರವಸೆ ನೀಡುವುದಿಲ್ಲ.",
           "ನಿಯಮ, ದಿನಾಂಕ ಮತ್ತು ಮೊತ್ತ ಬದಲಾಗುತ್ತಿರುತ್ತದೆ — ಅರ್ಜಿ ಸಲ್ಲಿಸುವ ಮೊದಲು ಯೋಜನೆಯ "
           "<strong>ಅಧಿಕೃತ ವೆಬ್‌ಸೈಟ್</strong>, ನಿಮ್ಮ ಕೃಷಿ ಇಲಾಖೆ ಅಥವಾ ರೈತ ಸಂಪರ್ಕ ಕೇಂದ್ರದಿಂದ ಖಚಿತಪಡಿಸಿಕೊಳ್ಳಿ."),
    "ta": ("KrashiMitra ஒரு <strong>தனியார் இணையதளம்</strong> — அரசு இணையதளம் அல்ல, "
           "எந்த அரசுத் துறையுடனும் தொடர்புடையது அல்ல.",
           "எந்தத் திட்டத்திற்கும் நாங்கள் <strong>விண்ணப்பமோ கட்டணமோ பெறுவதில்லை</strong>; "
           "தகுதி அல்லது தொகைக்கு எந்த உத்தரவாதமும் அளிப்பதில்லை.",
           "விதிகள், தேதிகள், தொகை மாறக்கூடும் — விண்ணப்பிக்கும் முன் திட்டத்தின் "
           "<strong>அதிகாரப்பூர்வ இணையதளம்</strong> அல்லது உங்கள் வேளாண் துறையிடம் உறுதிப்படுத்துங்கள்."),
    "en": ("KrashiMitra is a <strong>private website</strong> — not a government "
           "website, and not part of any government department.",
           "We <strong>take no applications or fees</strong> for any scheme, and we "
           "promise no eligibility or amount.",
           "Rules, dates and amounts change — before applying, confirm on the "
           "scheme's <strong>official website</strong> or with your agriculture office."),
}

_CSS = (
    "<style>"
    ".km-private{border:1px solid #9cc3e6;background:#f2f8fd;"
    "border-left:5px solid #2f6fa8;border-radius:10px;padding:14px 16px;"
    "margin:18px 0 22px;font-size:.95rem;line-height:1.7;color:#1d3548}"
    ".km-private p{margin:0 0 6px}"
    ".km-private p:last-child{margin:0}"
    "@media(max-width:480px){.km-private{padding:12px 13px;font-size:.92rem}}"
    "</style>"
)


def scheme_notice_html(lang: str = "hi") -> str:
    """The visible block. Self-contained CSS, like the advisory, so a shell
    redesign cannot strip its styling."""
    c = _COPY.get(lang, _COPY["hi"])
    paras = "\n".join(f"    <p>{'ℹ️ ' if i == 0 else ''}{x}</p>" for i, x in enumerate(c))
    return (
        "\n  <!-- Private-website notice — tools/article_scheme_notice.py -->\n  "
        + _CSS + "\n"
        f'  <div class="km-private" {SCHEME_MARK}="1" role="note">\n'
        + paras + "\n  </div>\n"
    )


# ── built pages on disk ────────────────────────────────────────────────────

_SECTION_IN_PAGE = re.compile(r'"articleSection"\s*:\s*"([^"]+)"')


def page_is_scheme(doc: str) -> bool:
    """A built page is a scheme page when its Article schema says so."""
    m = _SECTION_IN_PAGE.search(doc or "")
    return bool(m and is_scheme_section(m.group(1)))


def page_lang(doc: str) -> str:
    m = re.search(r'<html[^>]*\blang="([^"]+)"', doc)
    return (m.group(1) if m else "hi").split("-")[0]


def _anchor(doc: str) -> int | None:
    """Top of the article: just before the first body section, else before the
    FAQ, else before the closing CTA."""
    for probe in ("<!-- INTRODUCTION -->", '<section class="article-section"'):
        i = doc.find(probe)
        if i != -1:
            return i
    f = doc.find('<div class="faq-item"')
    if f != -1:
        s = doc.rfind("<section", 0, f)
        if s != -1:
            return s
    c = doc.find('<div class="cta-block"')
    return c if c != -1 else None


def ensure_in_html(doc: str) -> tuple[str, bool]:
    """Insert the notice into a scheme page that lacks it. (document, changed)."""
    if SCHEME_MARK in doc or not page_is_scheme(doc):
        return doc, False
    at = _anchor(doc)
    if at is None:
        raise ValueError("no anchor found for the private-website notice")
    block = scheme_notice_html(page_lang(doc))
    return doc[:at] + block.lstrip("\n") + "\n  " + doc[at:], True


def sweep(articles_dir, write: bool = True) -> list[str]:
    """Add the notice to every scheme page on disk that lacks it. Idempotent."""
    import pathlib
    changed = []
    for p in sorted(pathlib.Path(articles_dir).glob("*.html")):
        if p.stem == "index":
            continue
        doc = p.read_text(encoding="utf-8", errors="replace")
        new, did = ensure_in_html(doc)
        if did:
            changed.append(p.stem)
            if write:
                p.write_text(new, encoding="utf-8")
    return changed


if __name__ == "__main__":
    import argparse
    import pathlib

    ap = argparse.ArgumentParser(description="Add the private-website notice to scheme pages.")
    ap.add_argument("--check", action="store_true", help="report only, write nothing")
    ap.add_argument("--dir", type=pathlib.Path,
                    default=pathlib.Path(__file__).resolve().parents[1] / "frontend" / "articles")
    ns = ap.parse_args()
    hit = sweep(ns.dir, write=not ns.check)
    print(("missing on" if ns.check else "added to"), len(hit), "page(s)")
    for s in hit:
        print(" ", s)
