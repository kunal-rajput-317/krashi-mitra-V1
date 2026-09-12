# -*- coding: utf-8 -*-
"""Every article that tells a farmer to put something on his crop must carry
the spray/dose advisory.

The articles were generated, not written by an agronomist. 97 of the 175 pages
name a pesticide or print a dose, and they rank in front of a very large number
of searches. Under the Insecticides Act, 1968 the approved label on the
container is the legal instruction — so what protects both the reader and the
site is not "our numbers are right" but "the label is the authority, confirm
with your KVK", said on the page itself.

Two code paths produce these pages and this file holds both to the same rule:
the builder injects the block at render time for the 139 pages that have a
content module, and article_advisory.sweep() patches the 36 legacy pages that
do not. A page that slips through either path fails here.
"""

import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

import article_advisory as adv          # noqa: E402
import article_builder as ab            # noqa: E402

PAGES = [p for p in sorted(ab.ARTICLES.glob("*.html")) if p.stem != "index"]


def _own_text(doc: str) -> str:
    """The page's own prose: without the related-articles strip (other pages'
    titles) and without the advisory itself (which would otherwise be able to
    satisfy the rule it is being tested against)."""
    own = re.split(r'<div class="relevant-articles">', doc)[0]
    own = re.sub(r'<div class="km-advisory".*?</div>', " ", own, flags=re.S)
    return ab._visible(own)


def test_pages_exist():
    assert len(PAGES) > 100, f"only found {len(PAGES)} article pages"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.stem)
def test_chemistry_page_carries_the_advisory(page):
    doc = page.read_text(encoding="utf-8", errors="replace")
    text = _own_text(doc)
    if not adv.needs_advisory(text):
        return
    chems = adv.find_chemicals(text)[:3]
    doses = adv.find_doses(text)[:3]
    assert adv.ADVISORY_MARK in doc, (
        f"{page.stem} names {chems or doses} but carries no spray/dose "
        f"advisory — run: python tools/article_builder.py --all")


def test_the_advisory_says_the_things_that_matter():
    """The block is not decoration. If any of these four claims is edited out,
    what is left is an apology, not a protection."""
    hi = adv.advisory_html("hi")
    assert "कृषि विज्ञान केंद्र" in hi, "dropped the KVK referral"
    assert "लेबल ही अंतिम प्रमाण है" in hi, "dropped 'the label is the authority'"
    assert "प्रतीक्षा अवधि" in hi, "dropped the waiting period"
    assert "CIB&amp;RC" in hi, "dropped the registration warning"
    assert "ज़िम्मेदारी नहीं लेता" in hi, "dropped the liability line"


@pytest.mark.parametrize("lang", ["hi", "kn", "ta", "en"])
def test_every_locale_has_real_copy(lang):
    """A missing locale silently falls back to Hindi, which on a Tamil page is
    both useless to the reader and worthless as a disclaimer."""
    h = adv.advisory_html(lang)
    assert adv.ADVISORY_MARK in h
    assert h.count("<div") == h.count("</div>") == 1
    assert h.count("<ul>") == h.count("</ul>") == 1
    assert h.count("<li>") == 4, "the four claims must all be present"
    if lang != "hi":
        assert h != adv.advisory_html("hi"), f"{lang} is falling back to Hindi"


def test_detector_catches_what_it_missed_before():
    """The first version read only body + quick facts + FAQs and missed a
    '200 लीटर / एकड़' sitting in `badges`, which then failed the build it was
    meant to satisfy. render() now flattens every authored field."""
    assert adv.needs_advisory("200 लीटर / एकड़")
    assert adv.needs_advisory("2 ग्राम प्रति लीटर पानी")
    assert adv.needs_advisory("मैंकोजेब 75% WP")
    assert adv.needs_advisory("spray Imidacloprid 17.8% SL")
    assert adv.needs_advisory("20 ಕೆಜಿ ಪ್ರತಿ ಎಕರೆ")
    assert not adv.needs_advisory("खेत की जुताई करें और समय पर सिंचाई दें")
    assert not adv.needs_advisory("मंडी में गेहूं का भाव 2400 रुपये प्रति क्विंटल")


def test_builder_injects_for_a_chemical_article():
    """The injection is automatic — there is no per-article opt-in, because an
    author who has to remember a disclaimer will forget it exactly once."""
    a = ab._load_content(ab.CONTENT_DIR / "chana_unnat_kheti.py")
    assert "advisory" not in a, "this fixture must rely on detection, not a flag"
    assert adv.ADVISORY_MARK in ab.render(a)


def test_builder_leaves_a_clean_article_alone():
    a = ab._load_content(ab.CONTENT_DIR / "kisan_credit_card.py")
    assert adv.ADVISORY_MARK not in ab.render(a), (
        "advisory shown on a page with no chemistry — the detector is too loose")


def test_validate_rejects_a_page_that_lost_its_advisory(tmp_path):
    """The gate itself. If this stops failing, every other test here is
    decorative: the builder could ship a dosage page with no advisory and
    nothing would notice."""
    src = ab.ARTICLES / "chana-unnat-kheti.html"
    doc = src.read_text(encoding="utf-8")
    assert adv.ADVISORY_MARK in doc, "fixture no longer carries an advisory"

    stripped = re.sub(r'<div class="km-advisory".*?</div>', "", doc, flags=re.S)
    victim = tmp_path / "chana-unnat-kheti.html"
    victim.write_text(stripped, encoding="utf-8")

    problems = ab.validate(victim)
    assert any("advisory" in p for p in problems), (
        f"validate() accepted a dosage page with no advisory: {problems}")


def test_sweep_is_idempotent():
    """It runs on every --all, so a second pass must not stack a second block."""
    assert adv.sweep(ab.ARTICLES, write=False) == [], (
        "pages still missing the advisory — run: "
        "python tools/article_builder.py --all")


def test_advisory_cannot_be_switched_off():
    """ARTICLE['advisory'] = True forces the block on for something the
    detector cannot see. There is deliberately no way to force it off, and
    adding one would remove the only thing this module does."""
    a = ab._load_content(ab.CONTENT_DIR / "kisan_credit_card.py")
    a["advisory"] = True
    assert adv.ADVISORY_MARK in ab.render(a)

    a["advisory"] = False
    b = ab._load_content(ab.CONTENT_DIR / "chana_unnat_kheti.py")
    b["advisory"] = False
    assert adv.ADVISORY_MARK in ab.render(b), (
        "a falsy 'advisory' key suppressed the block on a page full of "
        "pesticide doses")
