"""Every scheme (सरकारी योजना) page says KrashiMitra is a PRIVATE website.

LEGAL_RULES.md §1 ("Scheme pages must say we are a private website") and §3
(never promise eligibility or an amount, never take applications or fees).
Found missing on all ~20 scheme articles on 26 Sep 2026. The builder now
injects tools/article_scheme_notice.py's block; this test holds every built
page on disk to it, whichever path — builder or legacy sweep — produced it.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from article_scheme_notice import (SCHEME_MARK, is_scheme_section,  # noqa: E402
                                   page_is_scheme, scheme_notice_html)

ARTICLES = ROOT / "frontend" / "articles"
SCHEME_PAGES = sorted(p for p in ARTICLES.glob("*.html")
                      if p.stem != "index"
                      and page_is_scheme(p.read_text(encoding="utf-8", errors="replace")))


def test_there_are_scheme_pages_to_check():
    """A detector that silently matches nothing would make the test below
    pass vacuously."""
    assert len(SCHEME_PAGES) >= 20


@pytest.mark.parametrize("page", SCHEME_PAGES, ids=lambda p: p.stem)
def test_scheme_page_carries_the_private_notice(page):
    assert SCHEME_MARK in page.read_text(encoding="utf-8", errors="replace"), \
        f"{page.name} is a scheme page without the private-website notice"


@pytest.mark.parametrize("section", ["सरकारी योजना", "सरकारी योजनाएं", "ಸರ್ಕಾರಿ ಯೋಜನೆ"])
def test_every_spelling_of_the_section_counts(section):
    assert is_scheme_section(section)


def test_the_hindi_notice_says_the_three_things():
    html = scheme_notice_html("hi")
    assert "निजी वेबसाइट" in html
    assert "आवेदन या फ़ीस नहीं लेते" in html
    assert "गारंटी नहीं" in html
