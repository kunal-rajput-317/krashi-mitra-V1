"""/product must never state a price, a saving or a service it cannot stand behind.

Every rupee figure on these pages comes from the `PRODUCTS` array in shop.html.
It is an EDITORIAL figure — what a sack of Kapila roughly goes for — not a price
any shop has agreed to sell at. The page used to present it as the opposite:

* `Offer` JSON-LD with `availability: InStock` and `seller: KrashiMitra`
* `brand: KrashiMitra` on products that are somebody else's registered mark
* a "% छूट" badge computed against an `mrp` nobody verified
* a `⭐ 4.7` rating nobody ever collected
* "₹500+ पर मुफ्त डिलीवरी और Cash on Delivery उपलब्ध", in the title, the
  description, the hero and an FAQ answer

What the business actually does is take an enquiry and let a dealer quote
against it — `orders` carries quote_total, dealer_name and quoted_at — and 8 of
the first 28 orders came back "Not Available". So each of those was a claim we
would have had to defend, on the site's best-converting family, and two other
sections (krashi_dukan, rental) were already saying the opposite in Hindi on
every page.

None of that is visible to a smoke test that checks for HTTP 200. It is pinned
here instead:

* **No Offer markup without a real seller.** Same rule rental.py follows. When
  a shop lists its own price through dukan_items, krashi_dukan.py emits an
  AggregateOffer for it and that is honest; an indicative catalogue figure gets
  nothing.
* **No brand we cannot name truthfully.** Declaring "Kapila Cattle Feed" a
  KrashiMitra brand puts another company's trademark on our name.
* **No discount, no rating.** Both were computed or invented from numbers with
  no source.
* **No delivery or payment promise anywhere Google reads.**
* **The estimate always reads as an estimate**, and the connector disclaimer
  rides on every page that prints a number.

The catalogue is parsed out of shop.html at request time, so a careless edit
there lands on 94 live pages with no deploy step in between. That is why the
assertions below sweep the whole family rather than sampling one slug.
"""

import json
import re

import pytest

from backend.routes.product import (
    AFFILIATE_NOTE, DISCLAIMER, _available, _get_products,
)

ALL = _get_products()
SLUGS = [p["slug"] for p in ALL]

# A feed page is where this went wrong first and where it costs most: the
# livestock feed cluster is the best-converting thing on the site (2.30% CTR
# against a 0.81% site average), so it gets named rather than left to the sweep.
FEED_SLUGS = [p["slug"] for p in ALL if p["cat"] == "pashu_aahaar"]


def _lds(html: str) -> list[dict]:
    return [json.loads(m) for m in
            re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]


def _walk(node):
    """Every (key, value) pair in a JSON-LD block, nested ones included.

    The assertions below are about KEYS, not about text: "Bio-pesticide —
    organic pest control bestseller" contains the string "seller", and a
    substring check over json.dumps() fails on a page that is perfectly
    honest. Structured data has structure; this reads it."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield k, v
            yield from _walk(v)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


def _head(html: str, tag: str) -> str:
    if tag == "title":
        return re.search(r"<title>(.*?)</title>", html, re.S).group(1)
    return re.search(rf'<meta name="{tag}" content="(.*?)">', html, re.S).group(1)


def _page(client, slug: str) -> str:
    r = client.get(f"/product/{slug}")
    assert r.status_code == 200, f"/product/{slug} returned {r.status_code}"
    return r.text


# ── the catalogue itself ────────────────────────────────────

def test_the_catalogue_parses():
    """These pages are parsed out of shop.html at request time. A botched edit
    to PRODUCTS would empty the family, and every sweep below would then pass
    vacuously against nothing."""
    assert len(ALL) >= 80, f"only {len(ALL)} products parsed out of shop.html"
    assert FEED_SLUGS, "no pashu_aahaar products — the feed cluster vanished"


# ── structured data ─────────────────────────────────────────

@pytest.mark.parametrize("slug", SLUGS)
def test_no_offer_markup_for_an_editorial_price(client, slug):
    """An Offer needs a seller and a price someone will honour. PRODUCTS has
    neither, so marking one up as an offer is a false claim in structured data
    — and unlike the visible page, structured data is read by machines that
    will repeat it."""
    for block in _lds(_page(client, slug)):
        for key, value in _walk(block):
            assert key != "offers", f"{slug} emits an offers block"
            assert not (key == "@type" and "Offer" in str(value)), \
                f"{slug} emits {value} markup"


@pytest.mark.parametrize("slug", SLUGS)
def test_we_never_declare_ourselves_the_seller(client, slug):
    html = _page(client, slug)
    for block in _lds(html):
        for key, _ in _walk(block):
            assert key != "seller", f"{slug} names a seller in structured data"
    assert "InStock" not in html, f"{slug} claims stock it does not hold"


@pytest.mark.parametrize("slug", SLUGS)
def test_we_never_claim_someone_elses_product_as_our_brand(client, slug):
    """`brand: KrashiMitra` on "Kapila Cattle Feed" is another company's
    trademark on our name. A product whose brand we cannot state truthfully
    carries no brand key at all."""
    for block in _lds(_page(client, slug)):
        for key, _ in _walk(block):
            assert key != "brand", f"{slug} declares a brand"


@pytest.mark.parametrize("slug", SLUGS)
def test_the_json_ld_still_parses(client, slug):
    """The blocks are hand-built dicts; a stray comma ships invalid JSON-LD to
    every page at once."""
    assert _lds(_page(client, slug)), f"{slug} emits no structured data at all"


# ── the visible claims ──────────────────────────────────────

# Each of these shipped on all 94 pages. Listed one by one, with the reason,
# because a future "let's put the discount pill back, it converts" is exactly
# the edit this file exists to stop.
BANNED = [
    ("% छूट",             "a discount against an MRP nobody verified"),
    ("% off",             "the same discount, in the card's English"),
    ("⭐",                 "a star rating nobody ever gave"),
    ("मुफ्त डिलीवरी",       "a delivery service this site does not run"),
    ("Cash on Delivery",  "a payment method we do not collect"),
    ("में खरीदें",          "an offer to sell"),
    ("ऑर्डर करें",          "an instruction to buy from us"),
]


@pytest.mark.parametrize("slug", SLUGS)
@pytest.mark.parametrize("phrase,why", BANNED)
def test_no_banned_claim_on_a_product_page(client, slug, phrase, why):
    assert phrase not in _page(client, slug), f"{slug} still claims {phrase!r} — {why}"


@pytest.mark.parametrize("phrase,why", BANNED)
def test_no_banned_claim_on_the_hub(client, phrase, why):
    """The hub repeated the delivery promise in its title, its description and
    its hero — three places Google reads before a farmer reads anything."""
    r = client.get("/product/")
    assert r.status_code == 200
    assert phrase not in r.text, f"the /product/ hub still claims {phrase!r} — {why}"


@pytest.mark.parametrize("slug", SLUGS)
def test_the_price_reads_as_an_estimate(client, slug):
    """The number stays — it is what the farmer searched for — but the page has
    to say what kind of number it is, beside the number and not in a footer."""
    assert "अनुमानित" in _page(client, slug), f"{slug} prints a bare price"


@pytest.mark.parametrize("slug", SLUGS)
def test_the_connector_disclaimer_rides_on_every_page(client, slug):
    """"we only connect" is worth nothing to a farmer who never read it, so it
    is on the page rather than in Terms — the same strip /krashi_dukan and
    /rental carry, in the same words."""
    assert DISCLAIMER in _page(client, slug), f"{slug} drops the disclaimer"


@pytest.mark.parametrize("slug", SLUGS)
def test_an_affiliate_button_always_carries_its_disclosure(client, slug):
    """rel="sponsored" tells Google about the material connection. This tells
    the farmer, which is the half the CCPA's endorsement guidelines ask for —
    and it must appear exactly on the pages that actually earn a commission."""
    p = next(x for x in ALL if x["slug"] == slug)
    html = _page(client, slug)
    has_affil = (_available(p.get("affil_amazon", ""))
                 or _available(p.get("affil_flipkart", "")))
    assert (AFFILIATE_NOTE in html) == has_affil, (
        f"{slug}: affiliate link present={has_affil} but disclosure "
        f"present={AFFILIATE_NOTE in html}")
    if has_affil:
        for m in re.findall(r'<a class="btn btn-(?:amazon|flipkart)"[^>]*>', html):
            assert "sponsored" in m, f"{slug} has an affiliate button without rel=sponsored"


# ── the money question, asked directly ──────────────────────

@pytest.mark.parametrize("slug", FEED_SLUGS)
def test_a_feed_page_answers_who_sets_the_price(client, slug):
    """The livestock feed pages are the ones that rank and convert, and "कपिला
    पशु आहार की कीमत" is the query behind them. The honest answer names the
    number AND says whose it is — a farmer who turns up at a shop quoting our
    figure has to have been told it was an estimate."""
    html = _page(client, slug)
    assert "दुकानदार" in html, f"{slug} never says the shopkeeper sets the price"
    assert "कृषि मित्र सामान नहीं बेचता" in html, \
        f"{slug} never says plainly that we do not sell"
