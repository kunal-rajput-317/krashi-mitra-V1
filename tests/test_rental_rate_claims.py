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


def test_every_body_image_is_a_rental_photo_we_actually_ship(client):
    """This section used to ban <img> outright, because a missing static file
    answers 200 with the SPA's HTML here and a wrong src fails invisibly. It now
    ships real photographs, so the rule became narrower rather than weaker: any
    <img> in the body must come out of /images/rental, and
    test_a_page_never_points_at_an_image_that_is_not_there proves each one
    resolves to a real image. An <img> from anywhere else is the old bug back.
    """
    import re
    html = client.get("/rental/tractor").text
    body = html.split('<div class="wrap">')[1].split("<footer")[0]
    for src in re.findall(r'<img[^>]+src="([^"]+)"', body):
        assert src.startswith("/images/rental/"), f"unexpected image source {src}"


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


# ── the photographs, and what their licences oblige ─────────

def _rental_images():
    from backend.routes.rental import _IMG_DIR
    return sorted(f.stem for f in _IMG_DIR.glob("*.webp")) if _IMG_DIR.exists() else []


def test_every_photo_belongs_to_a_machine_that_exists():
    """A stray .webp would be served, credited and attached to nothing."""
    slugs = {e["slug"] for e in rental.equipment()}
    for name in _rental_images():
        assert name in slugs, f"{name}.webp matches no equipment slug"


def test_every_photo_is_credited(client):
    """CC BY and CC BY-SA licence these files to us ONLY while the author, the
    licence and the fact we modified the file are stated. /articles/credits is
    that statement, so a photo shipped without an entry there is a licence
    breach — and a silent one, because the image still renders perfectly.
    """
    import json
    from backend.routes.rental import _IMG_DIR

    images = _rental_images()
    if not images:
        pytest.skip("no rental photos committed")
    credits = json.loads((_IMG_DIR / "CREDITS.json").read_text(encoding="utf-8"))
    page = client.get("/articles/credits").text
    for name in images:
        assert name in credits, f"{name}.webp has no CREDITS.json entry"
        row = credits[name]
        assert row.get("author"), f"{name}: no author recorded"
        assert row.get("licence"), f"{name}: no licence recorded"
        assert f"images/rental/{name}.webp" in page, f"{name} is not on the credits page"


def test_no_photo_carries_a_noncommercial_licence():
    """This site runs AdSense, so every use of these images is commercial. An
    NC-licensed file is not licensed for it however well attributed."""
    import json
    from backend.routes.rental import _IMG_DIR
    if not _rental_images():
        pytest.skip("no rental photos committed")
    credits = json.loads((_IMG_DIR / "CREDITS.json").read_text(encoding="utf-8"))
    for name, row in credits.items():
        lic = (row.get("licence") or "").lower()
        assert "-nc" not in lic and "noncommercial" not in lic, f"{name}: {row['licence']}"


def test_photos_stay_small_enough_for_mobile_data():
    """98% of visits are phones, and this site has already blown a 5GB/month
    bandwidth cap once. The hub lazy-loads 24 of these, so a file creeping up
    to article-hero size costs real money and real load time.
    """
    from backend.routes.rental import _IMG_DIR
    for name in _rental_images():
        kb = (_IMG_DIR / f"{name}.webp").stat().st_size / 1024
        assert kb <= 40, f"{name}.webp is {kb:.0f} KB — re-encode it smaller"


@pytest.mark.parametrize("slug", SLUGS)
def test_a_page_never_points_at_an_image_that_is_not_there(client, slug):
    """The failure this guards is invisible: a missing static file on this site
    answers 200 with the SPA's HTML rather than 404, so a wrong src renders an
    empty grey box and nothing anywhere reports it. Assert on content-type, not
    on status.
    """
    import re
    html = client.get(f"/rental/{slug}").text
    for src in set(re.findall(r'src="(/images/rental/[^"]+)"', html)):
        r = client.get(src)
        assert r.status_code == 200, f"{src} → {r.status_code}"
        assert "image" in r.headers.get("content-type", ""), \
            f"{src} served {r.headers.get('content-type')} — the file is missing"


def test_the_hero_image_is_not_lazy_loaded(client):
    """The hero is the equipment page's LCP element. `loading="lazy"` on an LCP
    image defers the very fetch Core Web Vitals is timing."""
    html = client.get("/rental/tractor").text
    # Anchor on the MARKUP, not the class name — the same string appears in the
    # stylesheet far earlier in the document.
    hero = html[html.index('<div class="answer-prod-photo-lg has-photo">'):]
    hero = hero[:hero.index("</div>")]
    assert 'loading="eager"' in hero, "the hero image is lazy-loaded"
    assert 'fetchpriority="high"' in hero


def test_the_hub_grid_stays_lazy(client):
    """The hub is 24 photos. Eager-loading them would hand a farmer on mobile
    data the whole 450 KB before he has scrolled anywhere."""
    html = client.get("/rental").text
    assert 'loading="eager"' not in html
    assert html.count('loading="lazy"') >= 20


# ── the cross-section cards ─────────────────────────────────

@pytest.mark.parametrize("url", ["/rental", "/krashi_dukan"])
def test_every_cross_card_matches_the_stylesheet_it_depends_on(client, url):
    """A `.km-cross` that has no `.km-cross-head` inside it is the bug this
    test was written for, and it is invisible to every other check.

    CROSS_CSS moved the flex row out of `.km-cross` and into `.km-cross-head`
    so the container could hold machine chips underneath. One call site
    hand-wrote its own `<a class="km-cross">` instead of using the helper, so
    it kept the container's border and lost `display:flex` and
    `text-decoration:none` — a tall empty box with a blue underlined heading.
    Valid HTML, present CSS, right classes, wrong shape.
    """
    import re
    html = client.get(url).text
    body = html.split('<div class="wrap">')[1].split("<footer")[0]

    # The container is a <div>, never an <a> — an <a> gets the UA's inline +
    # underline defaults, which is exactly how the broken one rendered.
    assert '<a class="km-cross"' not in body, \
        "a cross card is still hand-written as an anchor"

    for m in re.finditer(r'<div class="km-cross">', body):
        chunk = body[m.start():m.start() + 1200]
        assert 'class="km-cross-head"' in chunk, \
            "a .km-cross card has no .km-cross-head — it will render unstyled"
        assert 'class="km-cross-ic"' in chunk
        assert 'class="km-cross-t"' in chunk


def test_both_cross_directions_come_from_one_renderer():
    """The card pointing at /rental and the card pointing at कृषि दुकान must be
    built by the same function, or the next stylesheet change breaks whichever
    one nobody remembered."""
    from backend.routes import rental as R
    for html in (R.cross_link(), R.dukan_link()):
        assert html.startswith('<div class="km-cross">')
        assert 'class="km-cross-head"' in html
        assert html.rstrip().endswith("</div>")


def test_the_dukan_card_points_at_dukan_and_the_rental_card_at_rental():
    """One renderer, two destinations — a swapped href would send a farmer
    looking for urea into a tractor directory."""
    from backend.routes import rental as R
    assert "/krashi_dukan" in R.dukan_link()
    assert "बीज, खाद या दवा" in R.dukan_link()
    assert "/rental" in R.cross_link()
    assert "किराये पर चाहिए" in R.cross_link()
