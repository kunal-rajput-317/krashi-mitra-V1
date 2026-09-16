"""Every affiliate link on the site is counted, disclosed, and makes no claim.

The Amazon program shipped on /product and then sat there: 94 pages, every one
carrying a tagged link, every click going straight out to amzn.to. Nothing on
our side saw a single one of them, so "which product earns?" had no answer at
all — and the program was parked on the quietest pages the site owns while
/bhav carried the traffic.

Moving it onto /bhav is what this file guards, because that move is exactly
where an affiliate placement turns into a liability:

* **Counted.** A link that skips /go/p/ is a click nobody will ever see. The
  whole point of the redirect is that `lead_clicks` can answer the question a
  partner (or an Amazon dashboard) asks first.
* **Disclosed.** rel="sponsored" tells Google; AFFILIATE_NOTE tells the farmer,
  which is the half the CCPA's endorsement guidelines ask for. The rule is
  page-level and absolute: a page carrying an affiliate link carries the note.
* **No claim.** /product's price is an editorial estimate, and it is labelled
  one (tests/test_product_price_claims.py pins that). On /bhav the shelf prints
  no rupee figure at all — the farmer sees Amazon's real price one tap later,
  so ours could only ever be the number he catches us being wrong about.

`tests/test_product_price_claims.py` covers the same rules on /product itself;
this file is about the new surface and the redirect they now share.
"""

import re

import pytest

from backend.services import affiliate, crop_types

# One crop per type, so the sell-stage shelf is exercised in all three shapes,
# plus a crop with no product of its own (the fallback path) and one whose slug
# only matches through an alias.
CROPS = [
    ("wheat", "madhya-pradesh", "katni"),          # staple, crop-specific hit
    ("onion", "maharashtra", "nashik"),            # storable
    ("tomato", "karnataka", "kolar"),              # perishable
    ("cotton", "gujarat", "rajkot"),               # staple, no product of its own
]

BLOCK_RE = re.compile(r'<section class="lead-gen"><h2>🛒.*?</section>', re.S)


def _district_page(client, crop, state, dist):
    r = client.get(f"/bhav/{crop}/{state}/{dist}")
    if r.status_code != 200:
        pytest.skip(f"/bhav/{crop}/{state}/{dist} has no rows in this snapshot")
    return r.text


def _block(html):
    m = BLOCK_RE.search(html)
    assert m, "the affiliate shelf did not render on a district page"
    return m.group(0)


# ── selection ───────────────────────────────────────────────

def _known_crops() -> list:
    """Crop slugs to sweep, read off disk rather than out of the live index.

    /bhav's index is built from the mandi tables, which the test database does
    not carry; data/crop_types.json names 200 of the same slugs across all
    three types and needs nothing but the filesystem. It is the registry these
    shelves are keyed on anyway, so a crop listed there is exactly a crop this
    has to work for.
    """
    import json
    with open("backend/data/crop_types.json", encoding="utf-8") as fh:
        crops = list(json.load(fh).get("crops", {}))
    assert len(crops) > 150, "the crop-type registry shrank — this sweep went vacuous"
    return crops


def test_every_crop_fills_a_block():
    """Hundreds of crop slugs share 94 products. A crop that matches nothing
    still has to get a full shelf off the sell-stage fallback, or the section
    renders half-empty on pages nobody thought to check."""
    thin = {cs: len(affiliate.for_crop(cs)) for cs in _known_crops()
            if len(affiliate.for_crop(cs)) < affiliate.BLOCK_MAX}
    assert not thin, f"crops with an under-filled shelf: {dict(list(thin.items())[:5])}"


def test_every_pick_has_a_live_link():
    """A card with no destination is a dead card. _catalogue() filters on this,
    so a regression here means the filter stopped being applied."""
    for cs in _known_crops():
        for p in affiliate.for_crop(cs):
            assert affiliate.network_for(p), f"{cs}: {p['slug']} has no live affiliate link"


def test_selection_is_deterministic():
    """These pages are cached HTML. Two farmers on the same page must see the
    same shelf — and a shuffle would also make "which product earns" unreadable
    in lead_clicks, which is the number this whole change exists to produce."""
    for cs in ("wheat", "onion", "tomato", "cotton"):
        runs = {tuple(p["slug"] for p in affiliate.for_crop(cs)) for _ in range(5)}
        assert len(runs) == 1, f"{cs} returned a different shelf across calls: {runs}"


def test_animal_feed_never_takes_a_crop_specific_slot():
    """"खली (सरसों/मूंगफली)" is named after the crop it is pressed from, so it
    matches `mustard` and used to outrank mustard seed on a mustard price page.
    It is a real product but never *this crop's* product."""
    slugs = [p["slug"] for p in affiliate.for_crop("mustard")]
    assert "mustard-seeds-pusa-bold" in slugs
    assert slugs.index("mustard-seeds-pusa-bold") == 0, \
        f"mustard seed is not the first pick on a mustard page: {slugs}"


def test_a_grain_moisture_meter_stays_off_the_fruit_pages():
    """It reads grain. "storable" is mostly potato, onion and orchard fruit —
    and a farmer who sees a grain tool on an apple page stops believing the
    rest of the shelf."""
    for cs in ("apple", "orange", "grapes"):
        if crop_types.crop_type(cs) != "storable":
            continue
        slugs = [p["slug"] for p in affiliate.for_crop(cs)]
        assert "digital-grain-moisture-meter" not in slugs, f"{cs} shows a grain tool"


# ── the rendered shelf ──────────────────────────────────────

# The markup is asserted against the renderer itself rather than only through a
# district page: /bhav's index is built from the mandi tables, so on a database
# without them every page-level check would skip — silently, and exactly on the
# assertions that matter most here. The renderer needs nothing but shop.html.

def _shelf(crop: str) -> str:
    from backend.routes.bhav import _kheti_saman_html
    html = _kheti_saman_html(crop, "गेहूं")
    assert html, f"the shelf rendered empty for {crop}"
    return html


@pytest.mark.parametrize("crop", [c[0] for c in CROPS])
def test_the_shelf_renders_a_full_row(crop):
    assert _shelf(crop).count('data-affil="') == affiliate.BLOCK_MAX


@pytest.mark.parametrize("crop", [c[0] for c in CROPS])
def test_every_card_goes_through_the_tracked_hop(crop):
    """A raw network URL in the markup is a click nobody counts. This is the
    single assertion that keeps the program measurable."""
    blk = _shelf(crop)
    hrefs = re.findall(r'<a class="lead-card" href="([^"]+)" data-affil=', blk)
    assert len(hrefs) == affiliate.BLOCK_MAX
    for h in hrefs:
        assert h.startswith("/go/p/"), f"card links straight out: {h}"
    for leak in ("amzn.to", "amazon.in", "flipkart.com"):
        assert leak not in blk, f"a raw {leak} URL reached the page markup"


@pytest.mark.parametrize("crop", [c[0] for c in CROPS])
def test_every_card_is_marked_sponsored(crop):
    blk = _shelf(crop)
    assert blk.count('rel="nofollow sponsored"') == blk.count('data-affil="')


@pytest.mark.parametrize("crop", [c[0] for c in CROPS])
def test_the_shelf_shows_no_product_photo(crop):
    """PRODUCTS reuses a handful of real pack shots as placeholders: 19 of the
    24 items this shelf can surface carry a picture of something else — the
    tarpaulin shows a drip kit, the storage bags show another company's branded
    cattle-feed sack. Wrong on 94 quiet /product pages is a bug; wrong on every
    district page is a farmer learning not to trust the block above it. The
    hand-picked `emoji` in each row IS accurate, so that is what renders.

    Delete this test the day the catalogue has its own photography — not before.
    """
    blk = _shelf(crop)
    assert "<img" not in blk, "the shelf is rendering catalogue photos again"
    assert 'class="lead-ic"' in blk, "the shelf lost its emoji"


@pytest.mark.parametrize("crop", [c[0] for c in CROPS])
def test_the_disclosure_rides_with_the_links(crop):
    """Absolute: affiliate links present ⇒ the note is present, in the same
    words /product uses, out of the one constant both import."""
    blk = _shelf(crop)
    assert "/go/p/" in blk
    assert affiliate.AFFILIATE_NOTE in blk, "the shelf drops the disclosure"


@pytest.mark.parametrize("crop", [c[0] for c in CROPS])
def test_the_shelf_makes_no_price_or_stock_claim(crop):
    """The catalogue figure is editorial. Beside an outbound link it is a
    number the farmer checks against Amazon three seconds later, so the shelf
    simply does not print one — nor an MRP, a discount, or a stock promise."""
    blk = _shelf(crop)
    assert "₹" not in blk, "the shelf prints a rupee figure"
    for phrase in ("% off", "% छूट", "MRP", "InStock", "मुफ्त डिलीवरी",
                   "में खरीदें", "ऑर्डर करें", "⭐"):
        assert phrase not in blk, f"the shelf claims {phrase!r}"


# ── the shelf in its page ───────────────────────────────────
# These need mandi rows, so they skip on a bare test database. They are the
# integration half: that the renderer is actually wired into the page, low.

@pytest.mark.parametrize("crop,state,dist", CROPS)
def test_the_shelf_reaches_the_district_page(client, crop, state, dist):
    blk = _block(_district_page(client, crop, state, dist))
    assert blk.count('data-affil="') == affiliate.BLOCK_MAX
    assert affiliate.AFFILIATE_NOTE in blk


def test_the_shelf_sits_below_the_price(client):
    """Placed low for the same reason the किसान-सेवा card is: it must never
    compete with the answer the farmer came for, or cost the page its LCP."""
    html = _district_page(client, *CROPS[0])
    assert html.index("मंडीवार भाव") < html.index('<h2>🛒'), \
        "the affiliate shelf climbed above the mandi table"


# ── the redirect ────────────────────────────────────────────

def test_the_hop_302s_to_the_network(client):
    r = client.get("/go/p/amazon/wheat-seeds-hd-2967", follow_redirects=False)
    assert r.status_code == 302
    assert "amzn.to" in r.headers["location"] or "amazon." in r.headers["location"]


def test_an_unknown_slug_lands_somewhere_sane(client):
    """A stale link in a cached page is exactly when this matters: a farmer who
    tapped a product should land on something, never on an error."""
    r = client.get("/go/p/amazon/no-such-product", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/product"


def test_an_unknown_network_falls_back_to_the_product(client):
    r = client.get("/go/p/bogus/wheat-seeds-hd-2967", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/product/wheat-seeds-hd-2967"


def test_the_offer_redirect_still_works(client):
    """/go/p/<net>/<slug> was added one level under /go/<offer_id>. If the two
    ever collide, the किसान-सेवा card silently stops redirecting."""
    r = client.get("/go/kcc-loan", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].startswith("http")


def test_the_click_is_recorded_with_its_district(client, monkeypatch):
    """The referer is the only thing that knows where the farmer was standing —
    the catalogue is national. Without it, /bhav placement is unmeasurable and
    we cannot tell a wheat-page click from a catalogue-page one."""
    seen = []
    monkeypatch.setattr("backend.services.lead_clicks.record",
                        lambda *a, **k: seen.append((a, k)))
    client.get("/go/p/amazon/digital-grain-moisture-meter", follow_redirects=False,
               headers={"user-agent": "Mozilla/5.0 (Linux; Android 13) Chrome/120 Mobile",
                        "referer": "https://krashimitra.in/bhav/wheat/madhya-pradesh/katni"})
    assert seen, "the affiliate hop recorded nothing"
    args, kw = seen[0]
    assert args == ("product", "amazon:digital-grain-moisture-meter")
    assert kw["district"] == "katni"
    assert kw["category"] == "misc"


def test_our_own_test_client_never_lands_in_the_count():
    """The dev setup points uvicorn at the LIVE Neon database, so a test that
    walks a /go/ route writes a real row into the table whose count gets quoted
    to a counterparty. It has happened. A run of this file must cost the number
    nothing."""
    from backend.services import lead_clicks
    assert lead_clicks.is_bot("testclient"), \
        "TestClient traffic would be counted as a farmer's click"


def test_crawlers_are_kept_off_the_hop():
    """Both robots groups must carry it — a bot matching the named AI group
    ignores the * group entirely."""
    robots = open("frontend/robots.txt", encoding="utf-8").read()
    assert robots.count("Disallow: /go/") == 2, \
        "the /go/ disallow is missing from one of the two robots groups"
