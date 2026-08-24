"""पहला महीना मुफ़्त — the acquisition offer, and the four ways it can become a lie.

The offer is a sentence a shopkeeper reads on a public page and a button an
admin presses days later. Nothing in the type system connects the two, so this
file is what keeps them the same deal:

* **"पहला 1 महीना मुफ़्त."** The months the card advertises are the months the
  grant actually gives, on BOTH sections. A card saying one and a button giving
  another is a promise broken to the one person who agreed to be listed.
* **"महीना खत्म, लिस्टिंग हट जाएगी."** Not "greys out", not "drops down" — the
  rows stop being rendered anywhere a farmer can reach. That expiry is the whole
  commercial point of the offer, so it is asserted through the reads the public
  pages actually run on, never through `is_live` alone.
* **A free month is not a payment.** `paid_at` is set by exactly one thing in
  this codebase: a human who saw the credit in the bank app. If a grant ever
  touches it, the panel starts reporting giveaways as sales and the one number
  that decides whether this business works becomes fiction.
* **Once per listing.** Re-granting would both make "पहला महीना" meaningless and
  throw away the expiry that the conversion call depends on.

Both directories are asserted the same way and in the same file on purpose: the
offer is the one thing about कृषि दुकान and किराये की मशीनें that must NOT be
allowed to diverge, and a test per section is how it would drift.
"""

from datetime import datetime, timedelta

import pytest

from backend.database.db import (
    DukanCatalog, DukanItem, DukanShop, RentalListing, RentalProvider,
)
from backend.services import free_month, krashi_dukan as dukan, rental


EQUIP = "tractor"          # a slug the JSON registry is asserted to carry


@pytest.fixture()
def shop(db_session):
    """A brand-new shop: typed in, never called, never paid, no clock running."""
    stamp = datetime.utcnow().strftime("%H%M%S%f")
    slug, product = f"test-free-dukan-{stamp}", f"test-free-urea-{stamp}"

    db_session.add(DukanCatalog(slug=product, cat="fertilizer",
                                name_hi="यूरिया", active=True))
    row = DukanShop(slug=slug, name="Test Krishi Kendra", district="Bareilly",
                    license_no="UP/TEST/1", plan="season", plan_months=3,
                    active=False, status="new")
    db_session.add(row)
    db_session.add(DukanItem(shop_slug=slug, product_slug=product,
                             price=280, active=True, in_stock=True))
    db_session.commit()
    yield row, product

    # Tests set attributes on `row` without committing, to describe a clock
    # state. Dropping those first stops the teardown flushing an UPDATE for a
    # row it is about to delete.
    db_session.rollback()
    db_session.query(DukanItem).filter(DukanItem.shop_slug == slug).delete()
    db_session.query(DukanCatalog).filter(DukanCatalog.slug == product).delete()
    db_session.query(DukanShop).filter(DukanShop.slug == slug).delete()
    db_session.commit()


@pytest.fixture()
def provider(db_session):
    """A brand-new machine owner, in the same never-started state."""
    stamp = datetime.utcnow().strftime("%H%M%S%f")
    slug = f"test-free-rental-{stamp}"

    row = RentalProvider(slug=slug, name="Test Tractor Service", district="Bareilly",
                         state="Uttar Pradesh", phone="9870951001", kind="owner",
                         plan="season", plan_months=3, active=False, status="new")
    db_session.add(row)
    db_session.add(RentalListing(provider_slug=slug, equipment_slug=EQUIP,
                                 rate=650, rate_unit_hi="प्रति घंटा",
                                 active=True, available=True))
    db_session.commit()
    yield row

    db_session.rollback()
    db_session.query(RentalListing).filter(RentalListing.provider_slug == slug).delete()
    db_session.query(RentalProvider).filter(RentalProvider.slug == slug).delete()
    db_session.commit()


def _dukan_visible(db, shop_slug, product_slug) -> bool:
    """Is this shop's price reachable by a farmer, through either read path?"""
    on_product = any(o["shop_slug"] == shop_slug
                     for o in dukan.offers_for_product(db, product_slug))
    on_hub = any(p["slug"] == product_slug for p in dukan.stocked_products(db))
    assert on_product == on_hub, (
        "the two dukan read paths disagree about one shop — one of them has "
        "stopped consulting is_live")
    return on_product


def _rental_visible(db, provider_slug) -> bool:
    on_equipment = any(o["provider_slug"] == provider_slug
                       for o in rental.offers_for_equipment(db, EQUIP))
    on_hub = EQUIP in rental.listed_equipment(db)
    assert on_equipment == on_hub, (
        "the two rental read paths disagree about one owner — one of them has "
        "stopped consulting is_live")
    return on_equipment


# ── the promise itself ──────────────────────────────────────

def test_both_sections_advertise_the_same_offer():
    """One promise, not two.

    The whole reason free_month.py exists is that a shopkeeper and a tractor
    owner must be told the same thing. If either card ever grows its own month
    count, the two halves of the business start selling different deals under
    one brand.
    """
    dukan_card  = free_month.card("dukan")
    rental_card = free_month.card("rental")
    term = free_month.months_hi()

    for card in (dukan_card, rental_card):
        assert f"पहला {term} बिल्कुल मुफ़्त" in card
        assert "मुफ़्त" in card
        # The CTA is a chat, not a form — and it must be OUR number.
        assert f"wa.me/{free_month.HELPLINE}" in card

    # The two pitches must still differ, or one section is advertising the other.
    assert "दुकान" in dukan_card
    assert "मशीन" in rental_card


def test_the_card_never_promises_something_the_ranking_cannot_honour():
    """A paid listing and a free one are the same listing.

    The one thing this directory has to sell is that its order cannot be
    bought. If the offer ever implied that paying moves a shop up, the offer
    would have destroyed the product it is trying to fill.
    """
    card = free_month.card("dukan")
    assert "क्रम हमेशा दूरी से लगता है" in card
    for word in ("ऊपर दिखेंगे", "पहले नंबर", "सबसे ऊपर"):
        assert word not in card, f"the offer implied paid placement: {word}"


def test_the_public_pages_carry_the_offer_and_its_stylesheet(client, shop):
    """An unstyled card is a broken card.

    The route modules build their own stylesheet by concatenation, so an offer
    rendered on a page that forgot free_month.CSS comes out as naked list items
    at the bottom of the page. Both halves are asserted together because they
    fail apart.

    All four public surfaces, not just the two hubs: a shopkeeper searching for
    his own product lands on the deep page far more often than on the hub, and
    that is exactly the reader the offer is written for.
    """
    _, product = shop
    for url in ("/krashi_dukan", f"/krashi_dukan/{product}", "/rental", f"/rental/{EQUIP}"):
        html = client.get(url).text
        assert 'class="km-offer"' in html, f"{url} does not show the offer"
        assert ".km-offer{" in html, f"{url} shows the offer without its CSS"
        assert f"पहला {free_month.months_hi()} बिल्कुल मुफ़्त" in html


# ── the grant ───────────────────────────────────────────────

def test_a_free_month_lists_the_shop_and_starts_a_clock(db_session, shop):
    """Granting is what puts a shop in front of a farmer.

    Making the admin tick `active` separately would only produce shops that
    were granted a month and never appeared — the same reasoning record_payment
    already follows.
    """
    row, product = shop
    assert not _dukan_visible(db_session, row.slug, product), "fixture starts hidden"
    assert dukan.days_left(row) is None, "a new shop has no clock"

    assert dukan.start_free_month(db_session, row.slug) is not None
    db_session.refresh(row)

    assert row.active is True
    assert row.status == "trial"
    assert _dukan_visible(db_session, row.slug, product)
    # 30 days per month, matching record_payment's own arithmetic. Floored, so
    # the day it is granted reads as 29 — never a day more than there is.
    assert dukan.days_left(row) in (29, 30)


def test_a_free_month_lists_the_owner_and_starts_a_clock(db_session, provider):
    """Same guarantee on the /rental side, asserted through its own read paths."""
    assert not _rental_visible(db_session, provider.slug), "fixture starts hidden"
    assert rental.days_left(provider) is None

    assert rental.start_free_month(db_session, provider.slug) is not None
    db_session.refresh(provider)

    assert provider.active is True
    assert provider.status == "trial"
    assert _rental_visible(db_session, provider.slug)
    assert rental.days_left(provider) in (29, 30)


def test_a_free_month_is_never_recorded_as_money(db_session, shop, provider):
    """The one number this business is judged on must stay true.

    `paid_at` means "a human saw the credit in the bank app" and nothing else.
    A grant that set it would turn every giveaway into a sale in the panel
    header — a fabricated receipt, arrived at by accident.
    """
    row, _ = shop
    before = dukan.counts(db_session)

    dukan.start_free_month(db_session, row.slug)
    db_session.refresh(row)
    after = dukan.counts(db_session)

    assert row.paid_at is None
    assert row.paid_amount is None
    assert row.payment_ref is None
    assert after["paying"] == before["paying"], "a free month was counted as revenue"
    assert after["free"] == before["free"] + 1
    assert dukan.on_free_month(row) is True

    rental.start_free_month(db_session, provider.slug)
    db_session.refresh(provider)
    assert provider.paid_at is None
    assert rental.on_free_month(provider) is True


def test_the_month_ends_itself(db_session, shop, provider):
    """The expiry IS the product.

    Without it the offer is open-ended free hosting and there is never a reason
    to ring back. Asserted through the reads the public pages run on, because
    that is where a forgotten is_live check would leak an expired listing.
    """
    row, product = shop
    dukan.start_free_month(db_session, row.slug)
    rental.start_free_month(db_session, provider.slug)
    db_session.refresh(row)
    db_session.refresh(provider)
    assert _dukan_visible(db_session, row.slug, product)
    assert _rental_visible(db_session, provider.slug)

    # Yesterday's expiry. No sweep runs — the next render is simply without it.
    row.paid_until = datetime.utcnow() - timedelta(days=1)
    provider.paid_until = datetime.utcnow() - timedelta(days=1)
    db_session.commit()

    assert not _dukan_visible(db_session, row.slug, product), \
        "an expired free month kept serving a shop's prices"
    assert not _rental_visible(db_session, provider.slug), \
        "an expired free month kept serving an owner's rates"

    # And the panel must call it the right kind of call: this is the FIRST ask
    # for money, not a renewal, because nothing was ever paid.
    assert dukan.is_lapsed(row) is True
    assert dukan.on_free_month(row) is True
    assert rental.on_free_month(provider) is True


def test_the_offer_is_once_per_listing(db_session, shop, provider):
    """"पहला महीना" said twice is not an offer, it is free hosting.

    A second grant would also move the expiry, throwing away the only date that
    makes the conversion call happen.
    """
    row, _ = shop
    assert dukan.may_free_month(row) is True
    dukan.start_free_month(db_session, row.slug)
    db_session.refresh(row)
    first_until = row.paid_until

    assert dukan.may_free_month(row) is False
    assert dukan.start_free_month(db_session, row.slug) is None
    db_session.refresh(row)
    assert row.paid_until == first_until, "a second grant moved the expiry"

    assert rental.may_free_month(provider) is True
    rental.start_free_month(db_session, provider.slug)
    db_session.refresh(provider)
    assert rental.may_free_month(provider) is False
    assert rental.start_free_month(db_session, provider.slug) is None


def test_a_paying_listing_can_never_be_pushed_back_onto_the_offer(db_session, shop):
    """A date real money bought must not be overwritable by a free one.

    A shop that paid for six months and was then handed a "free month" would
    lose five of them — silently, on a click meant to be generous.
    """
    row, _ = shop
    dukan.record_payment(db_session, row.slug, 500, "TEST-REF", months=6)
    db_session.refresh(row)
    paid_until = row.paid_until

    assert dukan.may_free_month(row) is False
    assert dukan.on_free_month(row) is False, "a paid shop read as being on the offer"
    assert dukan.start_free_month(db_session, row.slug) is None
    db_session.refresh(row)
    assert row.paid_until == paid_until


def test_paying_after_the_free_month_extends_it_rather_than_restarting(db_session, shop):
    """The conversion, end to end — the whole reason the offer exists.

    A shopkeeper who pays two days before the free month runs out must get his
    season ON TOP of the days he has left, not from today. Throwing those days
    away is a small theft that the person on the phone will notice.
    """
    row, product = shop
    dukan.start_free_month(db_session, row.slug)
    db_session.refresh(row)
    free_until = row.paid_until

    dukan.record_payment(db_session, row.slug, 500, "TEST-REF")   # its own 3-month term
    db_session.refresh(row)

    assert row.paid_at is not None, "the conversion did not record a payment"
    assert dukan.on_free_month(row) is False, "still reading as a free listing after paying"
    assert row.paid_until > free_until + timedelta(days=85), \
        "the season was backdated over the days the free month still had"
    assert _dukan_visible(db_session, row.slug, product)
    assert dukan.counts(db_session)["free"] == 0


# ── the admin API the panel actually calls ──────────────────

class TestTheAdminAPI:
    """The panel draws entirely from these responses.

    A field the panel reads and the API stopped sending renders as `undefined`
    in a Hindi sentence about money; a refusal that arrives as a 500 renders as
    a stack trace where a sentence should be. Both are asserted rather than
    assumed, on both sections, because the offer is the one thing about them
    that must stay identical.
    """

    AUTH = ("testadmin", "test-admin-pass")

    @pytest.fixture()
    def shop_slug(self, client):
        r = client.post("/admin/dukan/shops", auth=self.AUTH, json={
            "name": "Free Month Kendra", "district": "Hardoi",
            "license_no": "UP/FREE/1", "plan": "season", "plan_months": 3})
        assert r.status_code == 200, r.text
        slug = r.json()["shop"]["slug"]
        yield slug
        client.delete(f"/admin/dukan/shops/{slug}", auth=self.AUTH)

    @pytest.fixture()
    def provider_slug(self, client):
        r = client.post("/admin/rental/providers", auth=self.AUTH, json={
            "name": "Free Month Tractors", "district": "Hardoi",
            "phone": "9870951001", "kind": "owner",
            "plan": "season", "plan_months": 3})
        assert r.status_code == 200, r.text
        slug = r.json()["provider"]["slug"]
        yield slug
        client.delete(f"/admin/rental/providers/{slug}", auth=self.AUTH)

    def test_the_panel_is_told_the_offer_and_who_may_still_take_it(
            self, client, shop_slug, provider_slug):
        """The term comes off the service, so the button and the public card
        can never advertise different months."""
        for url, key, slug in (("/admin/dukan/shops", "shops", shop_slug),
                               ("/admin/rental/providers", "providers", provider_slug)):
            body = client.get(url, auth=self.AUTH).json()
            assert body["free_months"] == free_month.FREE_MONTHS
            assert "free" in body["counts"]
            row = next(r for r in body[key] if r["slug"] == slug)
            assert row["may_free_month"] is True
            assert row["free_month"] is False

    def test_granting_it_lists_the_row_without_recording_a_payment(
            self, client, shop_slug, provider_slug):
        for base, key, slug in (("/admin/dukan/shops", "shop", shop_slug),
                                ("/admin/rental/providers", "provider", provider_slug)):
            r = client.post(f"{base}/{slug}/free-month", auth=self.AUTH)
            assert r.status_code == 200, r.text
            row = r.json()[key]

            assert row["live"] is True
            assert row["free_month"] is True
            assert row["may_free_month"] is False, "the button must disappear once taken"
            assert row["paid_at"] is None, "a free month was recorded as a payment"
            assert row["days_left"] in (29, 30)
            assert r.json()["counts"]["paying"] == 0
            assert r.json()["counts"]["free"] >= 1

    def test_a_second_grant_is_a_sentence_not_a_stack_trace(
            self, client, shop_slug, provider_slug):
        """The admin sees this while on the phone. It has to read like Hindi."""
        for base, slug in (("/admin/dukan/shops", shop_slug),
                           ("/admin/rental/providers", provider_slug)):
            assert client.post(f"{base}/{slug}/free-month", auth=self.AUTH).status_code == 200
            r = client.post(f"{base}/{slug}/free-month", auth=self.AUTH)
            assert r.status_code == 400, r.text
            assert "मुफ़्त महीना" in r.json()["detail"]

    def test_an_unknown_slug_is_a_404_not_a_grant(self, client):
        for base in ("/admin/dukan/shops", "/admin/rental/providers"):
            r = client.post(f"{base}/no-such-listing-at-all/free-month", auth=self.AUTH)
            assert r.status_code == 404, r.text

    def test_the_offer_is_admin_only(self, client, shop_slug, provider_slug):
        """No public route may hand out a month — the grant is a business
        decision made on a call, and an open endpoint is a free directory."""
        for base, slug in (("/admin/dukan/shops", shop_slug),
                           ("/admin/rental/providers", provider_slug)):
            r = client.post(f"{base}/{slug}/free-month")
            assert r.status_code in (401, 403), r.text
