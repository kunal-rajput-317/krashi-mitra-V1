"""The /product catalogue can be edited from the panel without losing shop.html.

Until now the catalogue was a `const PRODUCTS = [...]` literal inside
frontend/shop.html: adding a product meant hand-editing a 94-entry JS array and
shipping a deploy. Every product is also an affiliate placement, so a catalogue
that could only grow at a laptop was revenue that could only grow at a laptop.

The panel writes an OVERLAY (services/shop_catalog.py) merged over that array
rather than replacing it. That one decision is what the tests below exist to
protect, because it is what makes the feature safe:

* **The committed catalogue is never damaged.** No panel action rewrites
  shop.html. Delete an override and the original shows through again; empty the
  table and /product is byte-for-byte what it was.
* **A sleeping or read-only database costs nothing.** The merge is additive, so
  when the overlay cannot be read the catalogue is exactly the baseline — the
  site does not degrade, it just stops showing edits.
* **An edit reaches every surface.** Not only /product/<slug>, but the hub, the
  /bhav affiliate shelf and anything else reading the catalogue — they all go
  through one accessor, and a regression here would split them.

tests/test_product_price_claims.py sweeps the same pages for the claims they
may not make; this file is about where the data comes from.
"""

import io

import pytest

from backend.services import shop_catalog

AUTH = ("testadmin", "test-admin-pass")

SAMPLE = {
    "name_en": "Test Sprayer Nozzle Set",
    "name_hi": "टेस्ट स्प्रेयर नोज़ल सेट",
    "cat": "sprayers",
    "emoji": "🔵",
    "unit_hi": "1 सेट",
    "desc_hi": "जाँच के लिए जोड़ा गया उत्पाद।",
    "price": 250,
    "affil_amazon": "https://www.amazon.in/s?k=sprayer+nozzle&tag=krashimitra-21",
}
SAMPLE_SLUG = "test-sprayer-nozzle-set"


@pytest.fixture()
def clean(db_session):
    """Remove anything a previous test left, before and after.

    The overlay is global state behind a process-wide cache, so a stray row
    would leak into the sweeps in test_product_price_claims.py — which render
    all 94 pages and would then be rendering 95.
    """
    from backend.database.db import ShopProduct

    def _purge():
        db_session.query(ShopProduct).filter(
            ShopProduct.slug.in_([SAMPLE_SLUG, "wheat-seeds-hd-2967"])).delete(
            synchronize_session=False)
        db_session.commit()
        shop_catalog.invalidate()

    _purge()
    yield db_session
    _purge()


def _create(client, **over):
    payload = dict(SAMPLE)
    payload.update(over)
    return client.post("/admin/catalogue", json=payload, auth=AUTH)


# ── the baseline is untouchable ─────────────────────────────

def test_an_empty_overlay_is_the_committed_catalogue(clean):
    """The safety property everything else rests on: no rows, no change."""
    from backend.routes.product import _get_products
    shop_catalog.invalidate()
    assert len(_get_products()) == 94


def test_the_merge_survives_a_dead_database(monkeypatch):
    """Neon suspends, and the catalogue is on the hot path of every /bhav
    district page. A failed overlay read must degrade to the baseline, not to
    an exception on the site's highest-traffic surface."""
    monkeypatch.setattr(shop_catalog, "_fetch",
                        lambda: (_ for _ in ()).throw(RuntimeError("compute suspended")))
    shop_catalog.invalidate()
    assert shop_catalog.overlay_cached() == ([], set())
    baseline = [{"slug": "x", "name_en": "X"}]
    assert shop_catalog.merge(baseline) == baseline


def test_the_slug_rule_matches_the_page_that_serves_it():
    """Three places build this URL — here, product.py and shop.html. A drift
    means the panel writes a row the page cannot find."""
    from backend.routes.product import _slugify
    for name in ("NPK Fertilizer (10:26:26)", "SSP (Single Super Phosphate)",
                 "Mustard/Groundnut Oil Cake Feed", "Urea Fertilizer 46% N"):
        assert shop_catalog.slugify(name) == _slugify(name), name


# ── adding ──────────────────────────────────────────────────

def test_a_new_product_reaches_its_own_page(client, clean):
    r = _create(client)
    assert r.status_code == 200, r.text
    assert r.json()["slug"] == SAMPLE_SLUG

    page = client.get(f"/product/{SAMPLE_SLUG}")
    assert page.status_code == 200
    assert SAMPLE["name_hi"] in page.text


def test_a_new_product_reaches_the_hub_and_the_sitemap(client, clean):
    _create(client)
    hub = client.get("/product/")
    assert hub.status_code == 200 and SAMPLE_SLUG in hub.text
    sm = client.get("/product/sitemap.xml")
    assert f"/product/{SAMPLE_SLUG}" in sm.text


def test_a_new_product_can_carry_an_affiliate_link(client, clean):
    """The point of the panel: more products is more affiliate inventory. A
    product added here has to be linkable and disclosed exactly like a
    committed one."""
    _create(client)
    from backend.services import affiliate
    p = affiliate.by_slug(SAMPLE_SLUG)
    assert p is not None, "a panel-added product never reached the affiliate catalogue"
    assert affiliate.network_for(p) == "amazon"

    page = client.get(f"/product/{SAMPLE_SLUG}").text
    assert f"/go/p/amazon/{SAMPLE_SLUG}" in page, "its button skipped the tracked hop"
    assert affiliate.AFFILIATE_NOTE in page, "its page dropped the disclosure"


def test_a_duplicate_slug_is_refused_not_silently_merged(client, clean):
    assert _create(client).status_code == 200
    again = _create(client)
    assert again.status_code == 400
    assert "already" in again.json()["detail"].lower()


@pytest.mark.parametrize("payload,why", [
    ({"name_en": "", "name_hi": "क", "cat": "seeds"}, "no English name"),
    ({"name_en": "X", "name_hi": "", "cat": "seeds"}, "no Hindi name"),
    ({"name_en": "X", "name_hi": "क", "cat": "not-a-cat"}, "bad category"),
    ({"name_en": "X", "name_hi": "क", "cat": "seeds", "price": "abc"}, "price not a number"),
    ({"name_en": "X", "name_hi": "क", "cat": "seeds",
      "affil_amazon": "amzn.to/x"}, "link without a scheme"),
])
def test_bad_input_is_refused_with_a_sentence(client, clean, payload, why):
    r = client.post("/admin/catalogue", json=payload, auth=AUTH)
    assert r.status_code == 400, f"{why} was accepted"
    assert r.json()["detail"], "refused without telling the owner anything"


# ── editing a committed product ─────────────────────────────

def test_editing_a_committed_product_creates_an_override(client, clean):
    """The first edit of a shop.html product has no row to update. It must
    create one seeded from the page's current values, so a farmer never sees a
    half-empty product because one field was changed."""
    r = client.patch("/admin/catalogue/wheat-seeds-hd-2967",
                     json={"price": 999}, auth=AUTH)
    assert r.status_code == 200, r.text
    assert r.json().get("created_override") is True

    shop_catalog.invalidate()
    from backend.routes.product import _get_by_slug
    p = _get_by_slug()["wheat-seeds-hd-2967"]
    assert p["price"] == 999
    assert p["name_hi"] == "गेहूं बीज HD-2967", "the override lost the committed name"
    assert p["affil_amazon"], "the override lost the affiliate link"


def test_deleting_an_override_reverts_to_the_committed_product(client, clean):
    client.patch("/admin/catalogue/wheat-seeds-hd-2967", json={"price": 999}, auth=AUTH)
    r = client.delete("/admin/catalogue/wheat-seeds-hd-2967", auth=AUTH)
    assert r.status_code == 200 and r.json()["reverted"] is True

    shop_catalog.invalidate()
    from backend.routes.product import _get_by_slug
    assert _get_by_slug()["wheat-seeds-hd-2967"]["price"] == 280, \
        "the committed price did not come back"


def test_an_edit_never_changes_the_number_of_products(client, clean):
    from backend.routes.product import _get_products
    client.patch("/admin/catalogue/wheat-seeds-hd-2967", json={"price": 999}, auth=AUTH)
    shop_catalog.invalidate()
    assert len(_get_products()) == 94, "editing a product cloned it"


def test_hiding_a_committed_product_takes_it_down(client, clean):
    """A committed product cannot be deleted — shop.html still lists it — so
    active:false is the only way to take one down."""
    from backend.routes.product import _get_products
    client.patch("/admin/catalogue/wheat-seeds-hd-2967",
                 json={"active": False}, auth=AUTH)
    shop_catalog.invalidate()
    slugs = [p["slug"] for p in _get_products()]
    assert "wheat-seeds-hd-2967" not in slugs
    assert len(slugs) == 93
    assert client.get("/product/wheat-seeds-hd-2967").status_code == 404


def test_a_blank_field_does_not_erase_a_live_value(client, clean):
    """The panel posts only the boxes it holds. A field sent absent must keep
    the committed value — the difference between correcting one field and
    blanking a live page."""
    client.patch("/admin/catalogue/wheat-seeds-hd-2967", json={"price": 999}, auth=AUTH)
    shop_catalog.invalidate()
    from backend.routes.product import _get_by_slug
    assert _get_by_slug()["wheat-seeds-hd-2967"].get("desc_hi"), "the description was erased"


# ── the editor's own payload ────────────────────────────────

def test_the_list_shows_the_live_catalogue_and_what_is_edited(client, clean):
    _create(client)
    r = client.get("/admin/catalogue", auth=AUTH)
    assert r.status_code == 200
    d = r.json()
    assert len(d["catalogue"]) == 95
    row = next(x for x in d["catalogue"] if x["slug"] == SAMPLE_SLUG)
    assert row["state"] == "added"
    assert row["has_amazon"] is True
    assert d["edited"][SAMPLE_SLUG]["source"] == "added"
    assert "seeds" in d["cats"], "the category picker would be a second hardcoded list"


def test_the_list_carries_the_links_the_rows_edit_inline(client, clean):
    """The Shop Panel edits a price and an Amazon link in place, so both have to
    ride in the listing. Without the URL there, every row would need its own
    round trip just to show what is already on screen."""
    r = client.get("/admin/catalogue", auth=AUTH)
    row = next(x for x in r.json()["catalogue"] if x["slug"] == "wheat-seeds-hd-2967")
    assert row["affil_amazon"].startswith("http")
    assert row["price"] == 280


def test_a_not_available_placeholder_never_reaches_the_link_box(client, clean):
    """The catalogue spells "no link" as `not_available_<image>.webp`. If that
    reached the panel's URL box, the next inline save would write the
    placeholder back as though someone had typed it in as a real link."""
    r = client.get("/admin/catalogue", auth=AUTH)
    for row in r.json()["catalogue"]:
        for f in ("affil_amazon", "affil_flipkart"):
            assert not row[f].startswith("not_available_"), f"{row['slug']}.{f} leaked a placeholder"
        assert row["has_amazon"] == bool(row["affil_amazon"])


def test_an_inline_edit_saves_one_field_and_nothing_else(client, clean):
    """What the panel's price box actually sends: a single-key PATCH. It must
    not disturb the rest of the product."""
    r = client.patch("/admin/catalogue/wheat-seeds-hd-2967",
                     json={"price": 321}, auth=AUTH)
    assert r.status_code == 200
    shop_catalog.invalidate()
    from backend.routes.product import _get_by_slug
    p = _get_by_slug()["wheat-seeds-hd-2967"]
    assert p["price"] == 321
    assert p["unit_hi"] == "5 kg बैग" and p["emoji"] == "🌾"


def test_opening_a_committed_product_prefills_from_the_page(client, clean):
    """Opening an unedited product must return what the page currently shows,
    not a blank form — otherwise the first save silently retypes the product."""
    r = client.get("/admin/catalogue/wheat-seeds-hd-2967", auth=AUTH)
    assert r.status_code == 200
    p = r.json()["product"]
    assert p["source"] == "committed"
    assert p["name_hi"] == "गेहूं बीज HD-2967"
    assert p["price"] == 280


def test_the_panel_is_behind_admin_auth(client):
    for call in (lambda: client.get("/admin/catalogue"),
                 lambda: client.post("/admin/catalogue", json=SAMPLE),
                 lambda: client.patch("/admin/catalogue/x", json={"price": 1}),
                 lambda: client.delete("/admin/catalogue/x"),
                 lambda: client.post("/admin/catalogue/x/preview", json={"price": 1})):
        assert call().status_code == 401


# ── preview ─────────────────────────────────────────────────

def test_preview_shows_the_edit_without_saving_it(client, clean):
    """The whole point of Preview: see the real page with the new number on it,
    and have changed nothing if you walk away. Anything less and the button is
    a lie about what it costs to press."""
    r = client.post("/admin/catalogue/wheat-seeds-hd-2967/preview",
                    json={"price": 777}, auth=AUTH)
    assert r.status_code == 200
    assert "₹777" in r.text, "the preview did not apply the unsaved price"
    assert "गेहूं बीज HD-2967" in r.text, "the preview lost the rest of the product"

    shop_catalog.invalidate()
    from backend.routes.product import _get_by_slug
    assert _get_by_slug()["wheat-seeds-hd-2967"]["price"] == 280, \
        "previewing saved the change"
    assert "₹280" in client.get("/product/wheat-seeds-hd-2967").text


def test_preview_is_rendered_by_the_page_itself(client, clean):
    """Rendered through routes/product.py::render_product, so a preview cannot
    drift from the live page. The disclosure and disclaimer prove it is the
    real thing rather than a mock."""
    from backend.routes.product import AFFILIATE_NOTE, DISCLAIMER
    r = client.post("/admin/catalogue/wheat-seeds-hd-2967/preview",
                    json={"price": 777}, auth=AUTH)
    assert DISCLAIMER in r.text
    assert AFFILIATE_NOTE in r.text


def test_preview_works_for_a_product_that_does_not_exist_yet(client, clean):
    """"+ नया प्रोडक्ट" can be looked at before it is saved, so the payload is
    merged onto an empty skeleton rather than 404-ing."""
    r = client.post("/admin/catalogue/brand-new-thing/preview",
                    json={"name_hi": "नया सामान", "name_en": "Brand New Thing",
                          "cat": "tools", "price": 99, "emoji": "🔧"}, auth=AUTH)
    assert r.status_code == 200
    assert "नया सामान" in r.text and "₹99" in r.text
    assert client.get("/product/brand-new-thing").status_code == 404, "preview created it"


def test_preview_refuses_what_save_would_refuse(client, clean):
    """A link with no scheme fails the same way here as on save — finding that
    out at Preview is the cheaper half."""
    r = client.post("/admin/catalogue/wheat-seeds-hd-2967/preview",
                    json={"affil_amazon": "amzn.to/x"}, auth=AUTH)
    assert r.status_code == 400


# ── photos ──────────────────────────────────────────────────

def test_an_uploaded_photo_replaces_the_committed_one(client, clean):
    """The catalogue's oldest content bug: most products reuse a handful of
    stock pack shots, so the tarpaulin shows a drip kit. This is the path that
    fixes one — and it has to win over the committed image path."""
    from PIL import Image

    _create(client)
    buf = io.BytesIO()
    Image.new("RGB", (640, 480), (30, 120, 60)).save(buf, format="PNG")
    buf.seek(0)

    r = client.post(f"/admin/catalogue/{SAMPLE_SLUG}/image",
                    files={"file": ("pack.png", buf, "image/png")}, auth=AUTH)
    assert r.status_code == 200, r.text
    img_url = r.json()["img"]
    assert img_url.startswith("/product/img/")

    shop_catalog.invalidate()
    from backend.routes.product import _get_by_slug
    assert _get_by_slug()[SAMPLE_SLUG]["img"] == img_url

    served = client.get(img_url)
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/webp"


def test_a_missing_photo_is_a_404_not_a_500(client):
    assert client.get("/product/img/99999999.webp").status_code == 404
