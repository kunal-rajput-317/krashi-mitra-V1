"""Auto ads must never be able to silence frontend/ads.js again.

ads.js owns ad placement for the whole site, but it deliberately stands down on
the handful of pages that were laid out by hand (index, weather,
sarkari_yojana, the /articles index). It used to detect those pages by asking
"does this document already contain an <ins class=adsbygoogle>?".

That test was wrong in a way that only shows up in a real browser. init() runs
at window load plus a settle loop, and by then AdSense Auto ads — an account
setting, invisible in the repo — has usually injected units of its own. ads.js
read Google's injected markup as the page's own deliberate layout and placed
nothing.

Measured on the live site 2026-09-05 at 390px after a full scroll:
/krashi_news is a 25,320px document, comfortably the MAX budget of 3, and
carried zero ads.js units. The /bhav hub placed 2 where it should place 3. That
is the missing coverage behind a site-wide 1.06 ads per pageview. It is a race,
so it looked random rather than broken.

The fix is an attribute Google cannot forge: a unit WE authored says so with
data-km-ad="page". These tests keep the two halves of that contract in step —
if someone adds a hand-placed unit without the attribute, ads.js will stack its
own units on top of it; if someone removes the attribute from an existing one,
the page silently loses its deliberate layout.
"""

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
FRONTEND = REPO / "frontend"
ADS_JS = FRONTEND / "ads.js"

PUB = "ca-pub-2792326360609634"

# Every <ins class="adsbygoogle"> written into a source file, with its attrs.
INS_RE = re.compile(r"<ins\b[^>]*\bclass=\"[^\"]*\badsbygoogle\b[^\"]*\"[^>]*>", re.S)


def html_files():
    return sorted(p for p in FRONTEND.rglob("*.html") if p.is_file())


def authored_units():
    """(path, tag) for every hand-written ad unit in the repo."""
    for path in html_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in INS_RE.finditer(text):
            yield path, m.group(0)


def test_authored_units_are_found_by_attribute_not_by_tag():
    """Auto ads must never be mistakable for a page's own deliberate layout.

    ads.js used to bail out entirely on finding any <ins class="adsbygoogle">,
    which is exactly what Auto ads injects at runtime — so /krashi_news, a
    25,320px page, placed zero units. It no longer stands down at all: authored
    units are counted against the page budget and the remainder is filled
    around them. Either way the detection must key on an attribute we write and
    Google cannot forge.
    """
    src = ADS_JS.read_text(encoding="utf-8")
    assert 'ins.adsbygoogle[data-km-ad="page"]' in src, (
        "ads.js no longer identifies hand-placed units by data-km-ad. Whatever "
        "replaced it will mistake Auto ads' injected markup for the page's own."
    )
    # A bare selector anywhere in placement logic reintroduces the bug.
    bare = re.findall(r"querySelector(?:All)?\('ins\.adsbygoogle'\)", src)
    assert not bare, (
        f"ads.js queries a bare ins.adsbygoogle ({len(bare)}x). Auto ads "
        "injects exactly that tag, so this cannot distinguish our markup from "
        'Google\'s - always qualify with [data-km-ad="page"].'
    )


def test_authored_units_count_against_the_budget():
    """A hand-laid-out page earns to its length, not to whatever it shipped with."""
    src = ADS_JS.read_text(encoding="utf-8")
    assert "authored.length" in src, (
        "hand-placed units are no longer counted against the page budget — "
        "index.html (9,370px) would go back to earning from just the 2 units "
        "someone added by hand years ago."
    )


def test_every_authored_unit_declares_itself():
    """A hand-placed unit ads.js cannot see is a unit it will double up on."""
    missing = [f"{p.relative_to(REPO)}: {tag[:70]}..."
               for p, tag in authored_units() if 'data-km-ad="page"' not in tag]
    assert not missing, (
        "These hand-written ad units lack data-km-ad=\"page\", so ads.js will "
        "not recognise the page as hand-laid-out and will add its own units on "
        "top of them:\n  " + "\n  ".join(missing)
    )


def test_no_placeholder_publisher_id():
    """A unit with a placeholder client can never fill.

    frontend/sarkari_yojana.html shipped three units on
    data-ad-client="ca-pub-XXXXXXXXXXXXXXXX" — every one of them dead, on a
    page carrying real traffic.
    """
    bad = []
    for path in html_files() + [ADS_JS]:
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"ca-pub-[A-Za-z0-9]+", text):
            if m.group(0) != PUB:
                bad.append(f"{path.relative_to(REPO)}: {m.group(0)}")
    assert not bad, (
        "Ad markup referencing a publisher ID that is not ours — these slots "
        "cannot fill:\n  " + "\n  ".join(sorted(set(bad)))
    )


def test_units_keep_clear_of_tap_targets():
    """The rule that was missing when AdSense limited the account.

    ads.js had rules for the distance between two units, the fold, and the
    page's own CTA — none of which knew where a thumb was going. Measured at
    390px on 5 Sept, a /krashi_news unit sat 36px below the sub-filter pills:
    one missed tap from a click nobody meant. A 3.2% CTR (3-6x normal display)
    is what that looks like in the reports, and invalid-traffic limiting is
    what it looks like in the Policy centre.
    """
    src = ADS_JS.read_text(encoding="utf-8")
    assert "clearOfTaps" in src, (
        "ads.js no longer measures distance from tap targets. That check is "
        "the reason the account was limited on 4 Sept 2026 — do not remove it."
    )
    assert re.search(r"var CLEAR\s*=\s*\d+", src), "the CLEAR constant is gone"
    assert re.search(r"var CLEAR_MIN\s*=\s*\d+", src), (
        "CLEAR_MIN is gone. Without the relaxed floor, a card grid where every "
        "card has its own button (/krashi_news) places zero units and the page "
        "earns nothing."
    )
    # The clearance filter must actually gate placement, not just exist.
    assert "clearOfTaps(g.y)" in src, "clearance is computed but never applied"
