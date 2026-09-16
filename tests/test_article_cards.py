# -*- coding: utf-8 -*-
"""Article cards must show a real date, and must not show a fabricated figure.

Every card in frontend/articles/index.html once carried "नया" where a date
belongs and "👁 नया" where a view count belongs. 32 of the hand-written cards
were worse: a frozen "2 दिन पहले" on articles published in July, and one
"इस सप्ताह" on a page last touched in May.

The date is real — it comes from the article's own JSON-LD dateModified, which
is what Google already reads. The view count is not real and never was: there
is no view counter anywhere in this codebase, so the slot holds a नया badge
driven by that same date instead of a number nobody measured.
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

import article_cards as ac          # noqa: E402

INDEX = ac.INDEX
DOC = INDEX.read_text(encoding="utf-8")
CARDS = [(m.group(1), m.group(0)) for m in ac._CARD.finditer(DOC)]


def _slug(href: str) -> str:
    return href.rstrip("/").split("/")[-1].removesuffix(".html")


def test_there_are_cards():
    assert len(CARDS) > 100, f"only found {len(CARDS)} cards"


def test_every_card_has_a_real_date():
    missing = [_slug(h) for h, c in CARDS if 'class="article-date"' not in c]
    assert not missing, (
        f"{len(missing)} cards have no <time> date: {missing[:8]} — run: "
        "python tools/article_cards.py")


def test_card_dates_match_the_article_they_link_to():
    """The card may not contradict the page Google indexed."""
    wrong = []
    for href, card in CARDS:
        slug = _slug(href)
        t = re.search(r'<time class="article-date" datetime="([^"]+)"', card)
        real = ac.article_date(slug)
        if t and real and t.group(1) != real:
            wrong.append(f"{slug}: card {t.group(1)} vs article {real}")
    assert not wrong, wrong[:8]


def test_no_frozen_relative_dates():
    """A baked "2 दिन पहले" is wrong the day after it is written. Relative
    labels are computed at view time from the datetime attribute; only an
    absolute month-year may be baked, as the offline fallback."""
    for href, card in CARDS:
        meta = re.search(r'<div class="article-meta">.*?</div>', card, re.S)
        if not meta:
            continue
        body = meta.group(0)
        for frozen in ("दिन पहले", "इस सप्ताह", "आज", "कल"):
            assert frozen not in body, (
                f"{_slug(href)} bakes a relative date ({frozen}) into its card")


def test_no_fabricated_view_count():
    """There is no view counter in this codebase. If one is ever built, this
    test should be rewritten to assert the number comes from it — not deleted
    so an invented figure can ship."""
    for href, card in CARDS:
        assert "👁" not in card, (
            f"{_slug(href)} shows an eye icon, implying a view count nothing "
            f"measures")
    for href, card in CARDS:
        slot = re.search(r'<div class="article-views">(.*?)</div>', card, re.S)
        if slot:
            assert not slot.group(1).strip(), (
                f"{_slug(href)} bakes something into the view slot: "
                f"{slot.group(1)[:40]!r} — the नया badge is added at view time")


def test_sweep_is_idempotent():
    assert ac.sweep(write=False) == [], (
        "cards are stale — run: python tools/article_cards.py")


def test_modified_wins_over_published():
    """Two legacy pages carry a 2025 datePublished with a 2026 dateModified.
    Preferring published there would advertise a live page as a year old."""
    d = ac.article_date("ganna-rog")
    assert d and d.startswith("2026"), f"ganna-rog resolved to {d}"


def test_slug_lookup_is_case_insensitive():
    """motha-ghaas-UP.html is not lowercase on disk. Windows hides that; Linux
    would skip the card silently."""
    assert ac.article_date("motha-ghaas-up") is not None


# ── canonical slug resolution ────────────────────────────────────────

def test_every_article_file_is_reachable_at_its_canonical_slug():
    """The canonical URL is the lowercased stem; five files carry capitals.

    Windows hides this (case-insensitive filesystem), Render's Linux disk does
    not — /articles/dap-guide-up, /articles/mop-guide,
    /articles/pm-kisan-samman-nidhi, /articles/motha-ghaas-up and
    /articles/soyabean-mp-guide all 404'd in production while the _redirects
    301 from the .html form pointed straight at them.
    """
    from pathlib import Path

    from backend.routes.articles import _article_file

    articles = Path(__file__).resolve().parents[1] / "frontend" / "articles"
    missing = []
    for path in articles.glob("*.html"):
        if path.name == "index.html":
            continue
        slug = path.stem.lower()
        if _article_file(slug) is None:
            missing.append(slug)
    assert not missing, f"canonical slugs with no file behind them: {missing}"


def test_lookup_prefers_an_exact_filename_match():
    """A miss triggers a directory scan; a hit must never pay for one, and an
    exact name must never be beaten by a differently-cased sibling."""
    from backend.routes.articles import _ARTICLES_DIR, _article_file

    assert _article_file("dap-guide-up") == _ARTICLES_DIR / "DAP-guide-up.html"
    assert _article_file("no-such-article-anywhere") is None
