"""/rental must never state a hire rate it cannot stand behind.

Every rupee figure in this section is EDITORIAL — a range compiled from CHC
rate cards, not a quote from anyone who will honour it. That distinction is
invisible to a smoke test that only checks for HTTP 200, and it is exactly the
distinction a farmer loses when he turns up at a tractor owner saying "कृषि
मित्र पर ₹500 लिखा है". So the claims are pinned here:

* **No Offer markup while nobody is offering.** An Offer/AggregateOffer needs a
  seller and a price someone will honour; we have neither. Marking estimates up
  as offers would put a false claim into structured data — the same rule
  krashi_dukan.py follows by emitting AggregateOffer only for real shop rows.
* **The estimate always reads as an estimate.** The disclaimer and the rate
  basis ride on every page that prints a number.
* **The headline rate is the FIRST listed, not the cheapest.** Order in the JSON
  is editorial and means "this is how this machine is normally hired". Sorting
  by price would quietly re-frame a combine (quoted per acre) behind a per-hour
  figure, on the page a farmer opened to compare per-acre rates.
* **The unit always travels with the number.** "₹1600–₹2600" is meaningless —
  and misleading — until you know it is per acre and not per hour.

The registry is a hand-edited JSON file, so its shape is asserted too: a
half-finished row must fail here rather than render a card with no price.
"""

import json
import re

import pytest

from backend.services import rental

# These run against the real app via conftest's `client` fixture, not a bare
# router: /rental borrows /bhav's page shell, whose header builds the quick-nav
# from the mandi index, so the pages touch the DB even though the equipment data
# itself is a flat file. Mounting the router alone renders a 500 that no
# assertion here would catch — and it would miss a missing include_router.

ALL = rental.equipment()
SLUGS = [e["slug"] for e in ALL]


def _lds(html: str) -> list[dict]:
    return [json.loads(m) for m in
            re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]


def _head(html: str, tag: str) -> str:
    if tag == "title":
        return re.search(r"<title>(.*?)</title>", html, re.S).group(1)
    return re.search(rf'<meta name="{tag}" content="(.*?)">', html, re.S).group(1)


# ── the registry itself ─────────────────────────────────────

def test_registry_is_populated():
    """A blank registry would render an empty hub, which the route noindexes —
    so a botched JSON edit must fail loudly here, not quietly de-index /rental."""
    assert len(ALL) >= 20
    assert len(rental.categories()) >= 4


@pytest.mark.parametrize("item", ALL, ids=SLUGS)
def test_every_equipment_row_is_complete(item):
    """A card with no price is the one thing this page cannot show."""
    for field in ("slug", "cat", "emoji", "name_hi", "name_en", "spec_hi",
                  "summary_hi", "check_hi", "tips_hi"):
        assert item.get(field), f"{item.get('slug')} missing {field}"

    rates = rental.rates(item)
    assert rates, f"{item['slug']} has no usable rate line"
    for r in rates:
        assert r["min"] <= r["max"], f"{item['slug']} inverted range {r}"
        assert r["min"] > 0, f"{item['slug']} non-positive rate {r}"
        # A basis, not necessarily a "प्रति X" one — "पूरा दिन (8 घंटे)" is a
        # real way a tractor is hired. What matters is that a basis EXISTS,
        # because a bare number on this page would read as a fixed price.
        assert r["unit_hi"].strip(), f"{item['slug']} has a rate with no basis"


def test_slugs_are_unique_and_url_safe():
    assert len(set(SLUGS)) == len(SLUGS)
    for s in SLUGS:
        assert re.fullmatch(r"[a-z0-9-]+", s), s


def test_every_equipment_sits_in_a_declared_category():
    """category_of() falls back rather than raising, so a typo'd `cat` would
    otherwise surface only as a breadcrumb reading the machine's own name."""
    declared = {c["key"] for c in rental.categories()}
    for e in ALL:
        assert e["cat"] in declared, f"{e['slug']} has undeclared cat {e['cat']}"


def test_updated_is_a_real_reviewed_date_not_today():
    """`updated` becomes dateModified and Last-Modified on all 25 pages. It must
    be the date the ranges were reviewed — stamping today's on every render is
    the false-freshness signal that had Google serving a three-week-old /bhav
    snippet as if it were the morning's."""
    from datetime import date
    day = rental.updated()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", day), day
    # Today's date is legal exactly once — on the day the rates are reviewed.
    # What is never legal is a date that has not happened yet.
    assert day <= date.today().isoformat(), "reviewed date is in the future"


# ── the headline rate contract ──────────────────────────────

@pytest.mark.parametrize("item", ALL, ids=SLUGS)
def test_headline_rate_is_the_first_listed_not_the_cheapest(item):
    """The ordering in the JSON is editorial: it says how the machine is
    normally hired. A future "show the best price" tweak would silently re-frame
    the deal on every page that quotes two ways."""
    assert rental.headline_rate(item) == rental.rates(item)[0]


@pytest.mark.parametrize("item", ALL, ids=SLUGS)
def test_span_covers_every_rate_line(item):
    lo, hi = rental.span(item)
    rates = rental.rates(item)
    assert lo == min(r["min"] for r in rates)
    assert hi == max(r["max"] for r in rates)


def test_rate_text_collapses_an_equal_range():
    assert rental.rate_text({"min": 500, "max": 900, "unit_hi": "x"}) == "₹500–₹900"
    assert rental.rate_text({"min": 500, "max": 500, "unit_hi": "x"}) == "₹500"
    assert rental.rate_text(None) == "—"


def test_the_registry_carries_no_supply_of_its_own():
    """Supply lives in Postgres (RentalProvider/RentalListing), never in the
    JSON. A `providers` key creeping back into the registry would be a second
    place to look for "who hires this out" — and the JSON one, being editorial,
    could name a phone number nobody ever rang. One source, and it is the one
    an admin has to type into after a call."""
    for item in rental.equipment():
        assert "providers" not in item, item["slug"]


# ── what the pages claim ────────────────────────────────────

@pytest.mark.parametrize("slug", SLUGS)
def test_equipment_page_renders(client, slug):
    r = client.get(f"/rental/{slug}")
    assert r.status_code == 200
    assert "किराया" in r.text


def test_hub_renders_and_links_every_machine(client):
    """The hub is the only internal path into the leaves. A machine missing from
    it is a page nothing links to, which on this site means a page Google never
    indexes — the exact JS-only-links gap that cost /bhav its indexation."""
    html = client.get("/rental").text
    assert html.count('class="prod-card"') >= len(ALL)
    for slug in SLUGS:
        assert f'href="https://krashimitra.in/rental/{slug}"' in html


def test_sitemap_lists_the_hub_and_every_machine(client):
    xml = client.get("/rental/sitemap.xml").text
    assert "<loc>https://krashimitra.in/rental</loc>" in xml
    for slug in SLUGS:
        assert f"<loc>https://krashimitra.in/rental/{slug}</loc>" in xml
    # The tree stays deliberately flat — no district/state expansion. 72% of
    # this site's impressions already sit at positions 4-10 behind thin URLs.
    assert xml.count("<loc>") == len(ALL) + 1


@pytest.mark.parametrize("path", ["/rental"] + [f"/rental/{s}" for s in SLUGS])
def test_no_offer_markup_while_nothing_is_actually_on_offer(client, path):
    """THE honesty invariant. An Offer needs a seller and a price someone will
    honour; these are estimates and no owner has signed up."""
    html = client.get(path).text
    for ld in _lds(html):
        blob = json.dumps(ld, ensure_ascii=False)
        assert '"Offer"' not in blob, f"{path} claims an Offer"
        assert '"AggregateOffer"' not in blob, f"{path} claims an AggregateOffer"
        assert '"priceCurrency"' not in blob, f"{path} claims a price in schema"


@pytest.mark.parametrize("path", ["/rental"] + [f"/rental/{s}" for s in SLUGS])
def test_every_page_that_prints_a_rupee_says_the_rate_is_an_estimate(client, path):
    html = client.get(path).text
    assert "₹" in html, f"{path} shows no rate at all"
    assert "अनुमानित" in html, f"{path} prints a rate with no estimate caveat"
    # ...and never claims we rent the machine out ourselves.
    assert "कृषि मित्र मशीन किराये पर नहीं देता" in html


@pytest.mark.parametrize("item", ALL, ids=SLUGS)
def test_the_unit_always_travels_with_the_number(client, item):
    """"₹1600–₹2600" is misleading until you know it is per acre, not per hour."""
    html = client.get(f"/rental/{item['slug']}").text
    for r in rental.rates(item):
        assert rental.rate_text(r) in html
        assert r["unit_hi"] in html, f"{item['slug']} prints a rate without its unit"


@pytest.mark.parametrize("path", ["/rental"] + [f"/rental/{s}" for s in SLUGS])
def test_serp_budgets_and_schema(client, path):
    """Titles ≤68 / descriptions ≤162 — the same budget the article builder
    fails a build over, rather than shipping truncated SERP copy."""
    html = client.get(path).text
    assert len(_head(html, "title")) <= 68
    assert len(_head(html, "description")) <= 162

    lds = _lds(html)
    faq = next((l for l in lds if l.get("@type") == "FAQPage"), None)
    assert faq, f"{path} has no FAQ schema"
    # Visible markup and JSON-LD come from ONE list in _faq() and must never
    # drift — a past bug on other pages declared 3 and showed 8.
    assert len(faq["mainEntity"]) == html.count('<div class="faq">')
    assert any(l.get("@type") == "BreadcrumbList" for l in lds)


@pytest.mark.parametrize("path", ["/rental"] + [f"/rental/{s}" for s in SLUGS])
def test_pages_are_indexable_and_carry_their_own_canonical(client, path):
    html = client.get(path).text
    assert "noindex" not in html, f"{path} is noindexed"
    assert f'<link rel="canonical" href="https://krashimitra.in{path}">' in html


def test_no_img_tag_in_the_body(client):
    """A missing static file returns 200 with the SPA's HTML on this site, not a
    404, so a wrong <img> src fails silently and invisibly. This section renders
    emoji tiles instead — asserted, because "add a photo" is the obvious future
    edit that would reintroduce the failure mode."""
    html = client.get("/rental/tractor").text
    body = html.split('<div class="wrap">')[1].split("<footer")[0]
    assert "<img" not in body


def test_a_dropped_machine_sends_the_farmer_back_to_the_directory(client):
    """Google holds URLs long after a row leaves the registry."""
    r = client.get("/rental/no-such-machine")
    assert r.status_code == 404
    assert "noindex" in r.text
    assert 'href="https://krashimitra.in/rental"' in r.text


def test_the_footer_note_is_not_the_agmarknet_line(client):
    """_footer()'s default claims prices come from the daily Agmarknet feed and
    tells the farmer to confirm in his mandi. Nothing here comes from that feed,
    and no mandi quotes tractor hire."""
    html = client.get("/rental/tractor").text
    assert "Agmarknet" not in html


# ── the service must never take the section down ────────────

def test_service_survives_a_broken_file(monkeypatch, tmp_path):
    """A hand-edited JSON is a hand-breakable JSON. /rental going briefly stale
    is survivable; /rental raising a 500 into Googlebot is not."""
    import backend.services.rental as mod

    bad = tmp_path / "broken.json"
    bad.write_text("{ this is not json", encoding="utf-8")
    monkeypatch.setattr(mod, "_PATH", bad)
    monkeypatch.setattr(mod, "_cache", None)
    monkeypatch.setattr(mod, "_mtime", -1.0)

    assert mod.equipment() == []
    assert mod.categories() == []
    assert mod.by_slug("tractor") is None
    assert mod.updated() == ""


def test_service_survives_a_missing_file(monkeypatch, tmp_path):
    import backend.services.rental as mod

    monkeypatch.setattr(mod, "_PATH", tmp_path / "gone.json")
    monkeypatch.setattr(mod, "_cache", None)
    monkeypatch.setattr(mod, "_mtime", -1.0)

    assert mod.equipment() == []
    assert mod.by_slug("tractor") is None


def test_lookup_tolerates_a_hand_typed_slug():
    assert rental.by_slug("  Tractor ")["slug"] == "tractor"
    assert rental.by_slug("pump_set")["slug"] == "pump-set"
    assert rental.by_slug("") is None


def test_siblings_never_dead_end_and_never_self_link():
    for e in ALL:
        sibs = rental.siblings(e)
        assert sibs, f"{e['slug']} has no onward links"
        assert e["slug"] not in [s["slug"] for s in sibs]


# ── the way in, from the other sections ─────────────────────
#
# /rental is a section nothing linked to when it shipped. These pin the
# cross-links that fix that, including the failure they were written after:
# krashi_dukan rendered the .km-cross markup while the rules for it lived only
# in rental.py's own sheet, so the strip arrived unstyled. Markup and CSS must
# always travel together — a caller cannot reach _doc's _CSS closure.

CROSS_MARKUP = 'class="km-cross"'
CROSS_RULE = ".km-cross{"


def test_dukan_hub_offers_the_rental_section(client):
    html = client.get("/krashi_dukan").text
    assert CROSS_MARKUP in html, "कृषि दुकान does not mention /rental"
    assert 'href="https://krashimitra.in/rental"' in html
    assert CROSS_RULE in html, "the strip shipped without its CSS"


def test_rental_hub_offers_the_dukan_section(client):
    """Both ways, or the link equity only ever flows one direction."""
    html = client.get("/rental").text
    assert 'href="https://krashimitra.in/krashi_dukan"' in html
    assert CROSS_RULE in html


def test_dukan_product_page_offers_the_rental_section(client, db_session):
    """The hub is not enough: a farmer who lands on a product page from Google
    never sees the hub at all."""
    from datetime import datetime

    from backend.database.db import DukanCatalog, DukanItem, DukanShop

    stamp = datetime.utcnow().strftime("%H%M%S%f")
    slug, product = f"x-dukan-{stamp}", f"x-urea-{stamp}"
    db_session.add(DukanCatalog(slug=product, cat="fertilizer",
                                name_hi="यूरिया", active=True))
    db_session.add(DukanShop(slug=slug, name="Test Krishi Kendra",
                             district="Bareilly", plan="season", plan_months=3,
                             active=True))
    db_session.add(DukanItem(shop_slug=slug, product_slug=product,
                             price=280, active=True, in_stock=True))
    db_session.commit()
    try:
        r = client.get(f"/krashi_dukan/{product}")
        assert r.status_code == 200
        assert CROSS_MARKUP in r.text, "product page does not mention /rental"
        assert 'href="https://krashimitra.in/rental"' in r.text
        assert CROSS_RULE in r.text, "the strip shipped without its CSS"
    finally:
        db_session.query(DukanItem).filter(DukanItem.shop_slug == slug).delete()
        db_session.query(DukanCatalog).filter(DukanCatalog.slug == product).delete()
        db_session.query(DukanShop).filter(DukanShop.slug == slug).delete()
        db_session.commit()


def test_rental_leaf_pages_do_not_link_to_themselves(client):
    """The strip is a way IN. On a /rental page it would point at the section
    the farmer is already standing in."""
    html = client.get("/rental/tractor").text
    assert CROSS_MARKUP not in html
