# -*- coding: utf-8 -*-
# ============================================================
# KrashiMitra — real dates on the /articles/ cards.
#
# WHY THIS EXISTS
# ---------------
# Every one of the 175 cards in frontend/articles/index.html shipped with the
# literal string "नया" where a date belongs, and "👁 नया" where a view count
# belongs. Neither was ever a number: the eye icon promised a statistic the
# site has never measured, and "नया" stayed on a card whose article was
# published in June.
#
# The real date was there the whole time — every article carries datePublished
# and dateModified in its own JSON-LD, which is what Google reads and can
# already show in the SERP. So putting it on the card exposes nothing new; it
# only stops our own cards being less informative than the search result.
#
# WHAT IT WRITES
# --------------
# `<time class="article-date" datetime="YYYY-MM-DD">सितंबर 2026</time>` — the
# baked label is the offline fallback; articles/index.html recomputes
# "आज / कल / N दिन पहले" at view time, because a baked "आज" is wrong by the
# next morning ([[feedback_everything-must-be-automatic]]).
#
# The view slot is emptied rather than filled. There is no view counter in this
# codebase, and inventing one is the sort of number that is very hard to
# un-publish. JS turns it into a "नया" badge for articles that genuinely are.
#
# HOW IT IS WIRED
# ---------------
# article_builder.sync_index_card() already emits the right markup for the 139
# articles that have a content module. The other 36 cards are hand-written and
# no rebuild reaches them, so `--all` runs this sweep afterwards — the same
# shape as the advisory sweep, for the same reason.
#
#   python tools/article_cards.py --check     # report, write nothing
# ============================================================

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

ARTICLES = ROOT / "frontend" / "articles"
INDEX = ARTICLES / "index.html"

HI_MONTHS = ("जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून",
             "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर")

_PUBLISHED = re.compile(r'"datePublished"\s*:\s*"([^"]+)"')
_MODIFIED = re.compile(r'"dateModified"\s*:\s*"([^"]+)"')

# One card, from its opening <a> to its </a>.
_CARD = re.compile(r'<a class="article-card" href="([^"#?]+)".*?</a>', re.S)
# The date token, anchored on the meta-dot so the match cannot stop early at
# the read-time span. Three forms have shipped on these cards:
#   "नया"                                  — the builder's placeholder
#   <span data-i18n="a1_date">2 दिन पहले</span>
#        — the hand-written legacy cards, and the worst of the three: a frozen
#          relative date. 32 cards claimed "2 दिन पहले" about articles
#          published in July. That is a false figure, not just a vague one.
#   <time class="article-date" …>          — what this tool writes
# The data-i18n key is dropped with the span: a date is computed at view time
# from `datetime`, so there is nothing for the phrase table to translate.
_DATE_SLOT = re.compile(
    r'(<div class="article-meta">.*?<span class="meta-dot"[^>]*></span>\s*)'
    r'(?:नया'
    r'|<span data-i18n="[^"]*_date"[^>]*>.*?</span>'
    r'|<time class="article-date"[^>]*>.*?</time>'
    r'|<span[^>]*>[^<]*</span>)'          # bare span: "इस सप्ताह" on a July page
    r'(\s*</div>)', re.S)
_VIEW_SLOT = re.compile(r'<div class="article-views">.*?</div>', re.S)


def article_date(slug: str) -> str | None:
    """The date the card should show: dateModified when the article has one,
    else datePublished. Two legacy pages carry a 2025 datePublished with a 2026
    dateModified — preferring modified keeps a live page from advertising
    itself as a year old."""
    p = ARTICLES / f"{slug}.html"
    if not p.is_file():
        # Hrefs use the lowercase slug convention but two legacy files are not
        # lowercase on disk (motha-ghaas-UP.html). Windows hides that; Linux
        # would silently skip the card, which is exactly the page that had the
        # worst frozen date. Match case-insensitively rather than rely on the
        # filesystem being forgiving.
        p = next((f for f in ARTICLES.glob("*.html")
                  if f.stem.lower() == slug.lower()), None)
        if p is None:
            return None
    doc = p.read_text(encoding="utf-8", errors="replace")
    m = _MODIFIED.search(doc) or _PUBLISHED.search(doc)
    return m.group(1)[:10] if m else None


def label(iso: str) -> str:
    try:
        y, mth, _ = (int(x) for x in iso.split("-"))
        return f"{HI_MONTHS[mth - 1]} {y}"
    except Exception:
        return ""


def time_html(iso: str) -> str:
    return f'<time class="article-date" datetime="{iso}">{label(iso)}</time>'


def sweep(index_path: Path = INDEX, write: bool = True) -> list[str]:
    """Give every card in index.html a real date. Idempotent."""
    doc = index_path.read_text(encoding="utf-8")
    changed: list[str] = []

    def fix(m: re.Match) -> str:
        card, href = m.group(0), m.group(1)
        slug = href.rstrip("/").split("/")[-1].removesuffix(".html")
        iso = article_date(slug)
        if not iso:
            return card
        new = _DATE_SLOT.sub(lambda d: d.group(1) + time_html(iso) + d.group(2),
                             card, count=1)
        new = _VIEW_SLOT.sub('<div class="article-views"></div>', new, count=1)
        if new != card:
            changed.append(slug)
        return new

    out = _CARD.sub(fix, doc)
    if write and changed:
        index_path.write_text(out, encoding="utf-8")
    return changed


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Put real dates on article cards.")
    ap.add_argument("--check", action="store_true",
                    help="report what is stale, write nothing")
    ns = ap.parse_args()
    hit = sweep(write=not ns.check)
    print(f"{'stale' if ns.check else 'updated'}: {len(hit)} card(s)")
    for s in hit[:20]:
        print(f"  {s}")
    if len(hit) > 20:
        print(f"  … and {len(hit) - 20} more")
    raise SystemExit(1 if (ns.check and hit) else 0)
