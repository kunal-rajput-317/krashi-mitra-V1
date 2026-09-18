"""The completion ring never sits on the farmer's own name.

The ring is absolutely positioned over the hero's top-right and nothing
reserved the column it occupies, so the eyebrow, the name and the प्रीमियम
tick that follows the name all ran underneath it. Measured in Edge before the
fix: 24px of overlap at 390px with a three-word Hindi name, 40px at 360px, and
20px at 320px with a name as short as "kunal rajput".

Two halves, and the tests below pin both, because either alone leaves it broken:

  * the ring is smaller on a phone — but shrinking it only buys ~14px, which a
    long name eats immediately;
  * the two rows that reach that high reserve the ring's column, at EVERY
    width — a long enough Latin name collided at 641px too, so a mobile-only
    rule would have left that standing.

The arithmetic is pinned rather than the literal values, so the ring can be
resized freely as long as the reserve moves with it.
"""

import io
import re
from pathlib import Path

import pytest


PAGE = Path(__file__).resolve().parents[1] / "frontend" / "profile.html"


@pytest.fixture(scope="module")
def html():
    return io.open(PAGE, encoding="utf-8").read()


@pytest.fixture(scope="module")
def css(html):
    """Only the <style> blocks — the page's JS is full of braces."""
    return "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", html, re.S))


def _rules(text):
    """(selector list, declarations) for every rule; at-rules are descended into."""
    out, i = [], 0
    while True:
        o = text.find("{", i)
        if o < 0:
            return out
        sel = text[i:o].replace("}", " ").strip()
        if sel.startswith("@"):          # @media / @keyframes — step inside
            i = o + 1
            continue
        c = text.find("}", o)
        if c < 0:
            return out
        out.append((sel, text[o + 1:c]))
        i = c + 1


def _rule(block, selector):
    """Declarations of the rule for exactly `selector` (no pseudo-class variants)."""
    pat = re.compile(r"(?:^|[\s,])" + re.escape(selector) + r"(?![\w:.-])")
    hits = [d for sel, d in _rules(block) if pat.search(sel)]
    assert hits, "no rule for " + selector
    return hits[-1]


def _px(decls, prop):
    m = re.search(r"(?:^|[;{\s])" + re.escape(prop) + r"\s*:\s*(-?[\d.]+)px", decls)
    return float(m.group(1)) if m else None


def _ring_media(css):
    """The ≤640px block that sizes the ring, brace-matched.

    There is more than one `@media (max-width: 640px)` in this page, so the
    block has to be picked by what is inside it, not by being the first.
    """
    for m in re.finditer(r"@media \(max-width: 640px\)\s*\{", css):
        i, depth = m.end(), 1
        while depth and i < len(css):
            depth += (css[i] == "{") - (css[i] == "}")
            i += 1
        body = css[m.end():i - 1]
        if ".profile-progress-circle-wrap" in body:
            return m.start(), i, body
    raise AssertionError("the phone rules for the ring are gone")


def _mobile_block(css):
    return _ring_media(css)[2]


def _desktop_block(css):
    """Everything the ring's phone block does not override."""
    a, b, _ = _ring_media(css)
    return css[:a] + css[b:]


def test_the_svg_can_actually_be_resized(html):
    """Without a viewBox, sizing the svg in CSS CROPS the circle, not scales it.

    The ring is drawn in 54 user units (r=22 at cx/cy=27); the width and height
    attributes are not a coordinate system on their own.
    """
    svg = re.search(r'<svg class="progress-ring"[^>]*>', html).group(0)
    assert 'viewBox="0 0 54 54"' in svg, "the ring would be clipped, not shrunk"


def test_the_ring_is_smaller_on_a_phone(css):
    desktop = _px(_rule(_desktop_block(css), ".profile-progress-circle-wrap"), "width")
    phone = _px(_rule(_mobile_block(css), ".profile-progress-circle-wrap"), "width")
    assert desktop and phone
    assert phone < desktop, "the phone ring is no smaller than the desktop one"


def test_the_ring_svg_shrinks_with_its_wrapper(css):
    """A 54px svg inside a 40px wrapper overflows it and collides anyway."""
    phone = _mobile_block(css)
    assert _px(_rule(phone, ".progress-ring"), "width") == \
           _px(_rule(phone, ".profile-progress-circle-wrap"), "width")


@pytest.mark.parametrize("scope", ["desktop", "phone"])
def test_the_name_row_clears_the_ring(css, scope):
    """reserve >= ring width + right offset - the hero's own right padding.

    That expresses the ring's left edge from the content's right edge: any
    less and a long enough name slides back under it.
    """
    block = _desktop_block(css) if scope == "desktop" else _mobile_block(css)
    wrap = _rule(block, ".profile-progress-circle-wrap")
    hero_pad = re.search(r"\.profile-hero \{[^}]*padding:\s*[\d.]+px\s+([\d.]+)px", css)
    needed = _px(wrap, "width") + _px(wrap, "right") - float(hero_pad.group(1))

    for selector in (".ig-hero-eyebrow", ".ig-hero-name-row"):
        reserve = _px(_rule(block, selector), "padding-right")
        assert reserve is not None, selector + " reserves nothing on " + scope
        assert reserve >= needed, (
            "%s reserves %spx on %s, needs >= %spx" % (selector, reserve, scope, needed))


def test_the_reserve_is_not_phone_only(css):
    """A rule that only fires under 640px leaves the 641px collision standing."""
    assert _px(_rule(_desktop_block(css), ".ig-hero-name-row"), "padding-right")
