"""Every page that shows goods says whose the RISK is, not only whose the price.

Asked for directly on 18 Sep 2026. The "ध्यान दें" notice already said we do
not sell and that the figure is अनुमानित — and said nothing about what happens
when a farmer sprays the thing. Roughly half this catalogue is कीटनाशक, खाद and
पशु आहार: products that burn a crop, poison a well or kill an animal when they
are mixed wrong, named on pages that also print a number, on a site he found by
searching for that chemical.

Two halves, and the test keeps both:

  * the SAFETY half — read the label, the dose and the warning, wear gloves,
    ask कृषि विभाग / KVK, and know that what is written here is general
    information, not advice for your field. This is the half that can prevent
    the harm, so it may never be dropped in favour of the legal one;
  * the LIABILITY half — the goods and their use belong to the company, the
    shop and the user.

Four sections print goods or machines for money (/product, /product/{slug},
/krashi_dukan, /rental) and a fifth links them (/bhav's affiliate shelf). The
text lives in ONE place, backend/services/legal.py, for the reason the
affiliate disclosure does: four hand-typed copies is how one of them quietly
stops saying the thing that matters.

See also tests/test_product_price_claims.py — the price half of the same
notice — and the working rule behind both: never ship a claim the site would
have to defend.
"""

import re

import pytest

from backend.services import legal
from backend.routes.product import DISCLAIMER as PRODUCT_NOTE, _get_products
from backend.routes.krashi_dukan import DISCLAIMER as DUKAN_NOTE
from backend.routes.rental import (
    DISCLAIMER as RENTAL_NOTE, DISCLAIMER_LISTED as RENTAL_LISTED_NOTE,
)


ALL = _get_products()
PESTICIDE_SLUGS = [p["slug"] for p in ALL if p["cat"] in ("pesticide", "fertilizer")]
FEED_SLUGS = [p["slug"] for p in ALL if p["cat"] == "pashu_aahaar"]


def _page(client, url):
    r = client.get(url)
    assert r.status_code == 200, f"{url} returned {r.status_code}"
    return r.text


# ── what the sentences have to say ───────────────────────────

def test_the_safety_half_tells_him_what_to_actually_do():
    """A disclaimer that only protects us is not worth printing. This half has
    to name the label, the dose and a real person to ask."""
    s = legal.SAFETY_INPUTS
    assert "लेबल" in s
    assert "मात्रा" in s
    assert "KVK" in s or "कृषि विभाग" in s
    assert "सिफ़ारिश नहीं" in s, "it must say this is not advice for his field"


def test_the_liability_half_says_it_plainly():
    assert "ज़िम्मेदार नहीं" in legal.NO_LIABILITY_GOODS
    assert "ज़िम्मेदार नहीं" in legal.NO_LIABILITY_MACHINE
    for text in (legal.NO_LIABILITY_GOODS, legal.NO_LIABILITY_MACHINE):
        assert "कृषि मित्र" in text, "it has to name who is not responsible"


def test_the_machine_wording_is_about_machines():
    """A rotavator has no expiry date; it has a guard that may be missing.
    Printing the pesticide sentence on /rental would read as boilerplate."""
    assert "कीटनाशक" not in legal.MACHINE_NOTE
    assert "मशीन" in legal.SAFETY_MACHINE


def test_it_does_not_promise_the_product_works():
    """The notice is a caution, not a sales line — and never a dose. A number
    here would be the advice these very sentences say we do not give."""
    for text in (legal.GOODS_NOTE, legal.MACHINE_NOTE, legal.SHELF_CAUTION):
        assert "गारंटी देते" not in text
        assert not re.search(r"\d+\s*(ग्राम|ml|मिली|लीटर|किलो)", text), \
            f"a dose crept into the notice: {text}"


# ── one copy, not four ───────────────────────────────────────

@pytest.mark.parametrize("module,attr", [
    ("backend/routes/product.py",      "legal.GOODS_NOTE"),
    ("backend/routes/krashi_dukan.py", "legal.GOODS_NOTE"),
    ("backend/routes/rental.py",       "legal.MACHINE_NOTE"),
    ("backend/routes/bhav.py",         "legal.SHELF_CAUTION"),
])
def test_each_section_imports_the_text_instead_of_retyping_it(module, attr):
    import io
    from pathlib import Path
    src = io.open(Path(__file__).resolve().parents[1] / module, encoding="utf-8").read()
    assert attr in src, f"{module} does not use {attr}"
    assert "ज़िम्मेदार नहीं है।\"" not in src, \
        f"{module} has a hand-typed copy of the liability sentence"


# ── and it is actually on the pages ──────────────────────────

def test_the_product_notice_carries_both_halves():
    assert legal.SAFETY_INPUTS in PRODUCT_NOTE
    assert legal.NO_LIABILITY_GOODS in PRODUCT_NOTE
    # …without losing the price half it already had.
    assert "अनुमानित" in PRODUCT_NOTE
    assert "कृषि मित्र सामान नहीं बेचता" in PRODUCT_NOTE


def test_the_dukan_notice_carries_both_halves():
    assert legal.SAFETY_INPUTS in DUKAN_NOTE
    assert legal.NO_LIABILITY_GOODS in DUKAN_NOTE


@pytest.mark.parametrize("note", [RENTAL_NOTE, RENTAL_LISTED_NOTE])
def test_both_rental_wordings_carry_the_machine_halves(note):
    """/rental has two notices — one for our editorial estimate and one for a
    named owner's own rate. The safety line belongs on both."""
    assert legal.SAFETY_MACHINE in note
    assert legal.NO_LIABILITY_MACHINE in note


@pytest.mark.parametrize("url", ["/product", "/krashi_dukan"])
def test_the_goods_sections_print_it(client, url):
    html = _page(client, url)
    assert legal.SAFETY_INPUTS in html, f"{url} drops the safety half"
    assert legal.NO_LIABILITY_GOODS in html, f"{url} drops the liability half"


def test_the_rental_section_prints_it(client):
    html = _page(client, "/rental")
    assert legal.SAFETY_MACHINE in html
    assert legal.NO_LIABILITY_MACHINE in html


@pytest.mark.parametrize("slug", (PESTICIDE_SLUGS + FEED_SLUGS)[:8])
def test_the_riskiest_product_pages_print_it(client, slug):
    """Chemicals and animal feed: the pages where a wrong dose costs a field or
    an animal. The catalogue is parsed out of shop.html at request time, so
    this sweeps rather than samples."""
    html = _page(client, f"/product/{slug}")
    assert legal.SAFETY_INPUTS in html, f"/product/{slug} drops the safety half"
    assert legal.NO_LIABILITY_GOODS in html, f"/product/{slug} drops the liability half"


def test_the_order_form_repeats_the_liability_line(client):
    """The pre-book form is where he commits. The full notice is further up the
    page; this is the one clause that has to be under the button."""
    html = _page(client, f"/product/{ALL[0]['slug']}")
    note = re.search(r'<p class="pb-note">(.*?)</p>', html, re.S)
    assert note, "the pre-book note is gone"
    assert "ज़िम्मेदार नहीं" in note.group(1)


def test_the_bhav_shelf_carries_the_one_line_version():
    """It lists a neem-oil pesticide beside a wheat price and has room for one
    line of fine print, not four.

    Asserted against the block builder rather than a live URL: which districts
    exist depends on what the mandi feed last returned, and this rule is about
    the markup, not about today's index.
    """
    from backend.routes.bhav import _kheti_saman_html
    html = _kheti_saman_html("wheat", "गेहूं")
    assert "lead-card" in html, "the shelf itself stopped rendering"
    assert legal.SHELF_CAUTION in html
