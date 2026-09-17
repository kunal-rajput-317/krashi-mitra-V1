"""A long listing can be read to the end.

The feed clamped a seller's own words to two lines and stopped there — no
ellipsis affordance, no way to open it. The part that got cut is usually the
part that sells the crop: "सीधे खेत से पिकअप", a phone number, "दलाल नहीं"।
Cards now grow an "और देखें" toggle, and so do long comments in the sheet.

What is pinned here is what would quietly break it again:

  * the toggle is added by measurement, not by a character count — a block that
    fits must not grow a stray "और देखें", which is what would make the feed
    look untidier rather than tidier;
  * the clamped text is `overflow:hidden`, so the button has to be its SIBLING;
    put it inside and it is the first thing the clamp swallows;
  * every language table needs the two labels — a missing key renders the
    literal string "undefined" on the card;
  * the toggle only exists after a render paints, so every render path that
    can paint a clamped block has to call the pass.
"""

import io
import re
from pathlib import Path

import pytest


PAGE = Path(__file__).resolve().parents[1] / "frontend" / "krashi_bajar.html"


@pytest.fixture(scope="module")
def html():
    return io.open(PAGE, encoding="utf-8").read()


# ── The markup ───────────────────────────────────────────────

def test_card_text_is_clampable_and_wrapped(html):
    """The seller's words are a clampable inside a wrapper.

    The wrapper carries the card's side padding so the toggle sits under the
    text, aligned with it, rather than flush to the card edge.
    """
    assert '<div class="bz-card-textwrap"><div class="bz-card-text bz-clampable"' in html
    assert ".bz-card-textwrap { padding: 0 12px 9px; }" in html


def test_comment_text_is_clampable(html):
    assert 'class="bz-comment-text bz-clampable"' in html
    assert ".bz-comment-text" in html


@pytest.mark.parametrize("selector", [".bz-card-text", ".bz-comment-text"])
def test_clamped_blocks_still_clamp(html, selector):
    """Both blocks keep their line clamp — the toggle is the way out of it,
    not a replacement for it."""
    block = re.search(re.escape(selector) + r" \{(.*?)\}", html, re.S)
    assert block, selector
    assert "-webkit-line-clamp" in block.group(1), selector
    assert "overflow: hidden" in block.group(1), selector


def test_is_open_lifts_the_clamp(html):
    assert ".bz-clampable.is-open {" in html
    rule = html.split(".bz-clampable.is-open {", 1)[1].split("}", 1)[0]
    assert "-webkit-line-clamp: unset" in rule
    assert "overflow: visible" in rule


def test_the_toggle_is_a_sibling_not_a_child(html):
    """insertAdjacentElement('afterend') — inside the clamped block the button
    would be clipped away by the very overflow it is there to undo."""
    assert "insertAdjacentElement('afterend', btn)" in html
    assert "appendChild(btn)" not in html


# ── The measuring pass ───────────────────────────────────────

def test_only_overflowing_blocks_get_a_toggle(html):
    """A two-line post must not grow a button. The check is a measurement on
    the live node, which is why it cannot live in the HTML string."""
    assert "el.scrollHeight - el.clientHeight < 4" in html


def test_every_render_path_applies_the_pass(html):
    """renderFeed() has two painting branches (posts, and the demo/empty
    fallback) and renderComments() one. Miss any and long text there is cut
    with no way to open it."""
    feed = html.split("function renderFeed()", 1)[1].split("function postCardHtml", 1)[0]
    assert feed.count("bzApplyClamps(feed)") == 2, "a renderFeed() branch paints without the pass"

    comments = html.split("function renderComments(", 1)[1].split("\n}", 1)[0]
    assert "bzApplyClamps(body)" in comments


def test_open_state_survives_a_re_render(html):
    """Loading the next page re-renders the whole feed. Without the remembered
    key, the post the reader had just opened shuts under them."""
    assert "const bzOpenClamps = new Set()" in html
    assert 'data-clamp-key="post-${p.id}"' in html
    assert 'data-clamp-key="comment-${c.id}"' in html
    assert "bzOpenClamps.has(key)" in html


def test_the_state_is_restored_after_the_measurement(html):
    """An already-open block overflows by nothing. Restore `is-open` before the
    measurement and the post loses the button that would close it again."""
    fn = html.split("function bzApplyClamps(root)", 1)[1].split("\n}", 1)[0]
    measure = fn.index("el.scrollHeight - el.clientHeight")
    restore = fn.index("if (wasOpen) el.classList.add('is-open')")
    assert measure < restore


def test_the_toggle_does_not_trigger_the_card(html):
    """The card body opens a lightbox; a tap on "और देखें" must not reach it."""
    fn = html.split("function bzApplyClamps(root)", 1)[1].split("\n}", 1)[0]
    assert "ev.stopPropagation()" in fn


def test_a_late_webfont_forces_a_re_measure(html):
    """Devanagari arrives from Google Fonts and the fallback face wraps to a
    different number of lines, so a first measurement can be wrong."""
    assert "document.fonts.ready.then(" in html


# ── The labels ───────────────────────────────────────────────

@pytest.mark.parametrize("lang", ["hi", "en", "kn"])
def test_every_language_has_both_labels(html, lang):
    """T() falls back to the hi TABLE, not to a hi KEY: a key missing from en
    or kn renders "undefined" where the toggle's label belongs."""
    start = html.index("\n  %s: {" % lang)
    end = html.index("\n  },", start)
    block = html[start:end]
    assert "read_more:" in block, lang
    assert "read_less:" in block, lang
    assert re.search(r"read_more:'[^']+'", block), lang
    assert re.search(r"read_less:'[^']+'", block), lang


def test_the_hindi_labels_are_the_ones_farmers_read(html):
    assert "read_more:'और देखें', read_less:'कम देखें'," in html
