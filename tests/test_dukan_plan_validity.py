"""The कृषि दुकान plan term, and what happens when it runs out.

Two claims are made to a shopkeeper on the phone, and this file is the only
thing that keeps either one honest:

* **"आप जितने महीने का लेंगे, उतने का ही चलेगा."** The term is per shop, agreed
  on the call, and every renewal extends by exactly that — not by whatever
  constant the code happened to ship with.
* **"पैसा नहीं आया तो दुकान हट जाएगी."** Not "greys out", not "drops down the
  list" — the items stop being rendered anywhere a farmer can reach.

The second is the one that fails silently. `is_live` is checked in three
separate read paths, and a fourth path added later that forgets it would keep
serving an unpaid shop's prices forever while every admin count still says
LAPSED. So the expiry is asserted through the reads the public pages actually
run on, never through `is_live` alone.
"""

from datetime import datetime, timedelta

import pytest

from backend.database.db import DukanCatalog, DukanItem, DukanShop
from backend.services import krashi_dukan as dukan


@pytest.fixture()
def shop(db_session):
    """One live shop with one priced item, and the catalogue row behind it."""
    stamp = datetime.utcnow().strftime("%H%M%S%f")
    slug, product = f"test-dukan-{stamp}", f"test-urea-{stamp}"

    db_session.add(DukanCatalog(slug=product, cat="fertilizer",
                                name_hi="यूरिया", active=True))
    row = DukanShop(slug=slug, name="Test Krishi Kendra", district="Bareilly",
                    license_no="UP/TEST/1", plan="season", plan_months=3,
                    active=True)
    db_session.add(row)
    db_session.add(DukanItem(shop_slug=slug, product_slug=product,
                             price=280, active=True, in_stock=True))
    db_session.commit()
    yield row, product

    # Several tests set attributes on `row` without committing, to describe a
    # clock state. Dropping those first stops the teardown flushing an UPDATE
    # for a row it is about to delete.
    db_session.rollback()
    db_session.query(DukanItem).filter(DukanItem.shop_slug == slug).delete()
    db_session.query(DukanCatalog).filter(DukanCatalog.slug == product).delete()
    db_session.query(DukanShop).filter(DukanShop.slug == slug).delete()
    db_session.commit()


def _visible(db, shop_slug, product_slug) -> bool:
    """Is this shop's price reachable by a farmer, through either read path?"""
    on_product = any(o["shop_slug"] == shop_slug
                     for o in dukan.offers_for_product(db, product_slug))
    on_hub = any(p["slug"] == product_slug for p in dukan.stocked_products(db))
    # The hub lists a product only while some live shop carries it, so with one
    # shop in the fixture the two must agree. Disagreeing means one read path
    # learned about expiry and the other did not.
    assert on_product == on_hub, "the two read paths disagree about expiry"
    return on_product


class TestTheTermIsPerShop:
    def test_a_renewal_extends_by_the_shops_own_term_not_the_default(self, db_session, shop):
        row, _ = shop
        row.plan_months = 6
        db_session.commit()

        dukan.record_payment(db_session, row.slug, 1200)

        left = (row.paid_until - datetime.utcnow()).days
        assert 175 <= left <= 181, f"{left} days — a 6-month shop got the default term"

    def test_an_explicit_months_overrides_this_payment_only(self, db_session, shop):
        row, _ = shop
        row.plan_months = 6
        db_session.commit()

        dukan.record_payment(db_session, row.slug, 200, months=1)

        assert (row.paid_until - datetime.utcnow()).days < 32
        # The one-off must not quietly rewrite what was agreed.
        assert dukan.plan_months_of(row) == 6

    def test_a_row_from_before_the_column_existed_reads_as_the_season(self, shop):
        row, _ = shop
        row.plan_months = None
        assert dukan.plan_months_of(row) == dukan.SEASON_MONTHS

    @pytest.mark.parametrize("given,expected", [
        ("6", 6), (6.0, 6), (0, dukan.MIN_PLAN_MONTHS), (99, dukan.MAX_PLAN_MONTHS),
        ("", 3), (None, 3), ("साल भर", 3),
    ])
    def test_clean_months_clamps_rather_than_explodes(self, given, expected):
        # This runs on the write path, after validation. A 0 here would list a
        # shop that is dark the instant it pays.
        assert dukan.clean_months(given, default=3) == expected

    @pytest.mark.parametrize("months", ["0", "13", "abcd"])
    def test_a_bad_term_is_refused_at_the_form(self, months):
        problem = dukan.validate_shop({
            "name": "X", "district": "Bareilly", "license_no": "L",
            "plan": "season", "plan_months": months})
        assert problem, f"{months!r} was accepted as a plan term"


class TestPayingEarlyDoesNotThrowDaysAway:
    def test_a_renewal_stacks_on_top_of_what_is_left(self, db_session, shop):
        row, _ = shop
        dukan.record_payment(db_session, row.slug, 600, months=3)
        first = row.paid_until

        dukan.record_payment(db_session, row.slug, 600, months=3)

        assert (row.paid_until - first).days >= 89, \
            "renewing early reset the clock instead of extending it"

    def test_a_lapsed_shop_starts_today_not_backdated(self, db_session, shop):
        row, _ = shop
        row.paid_at = datetime.utcnow() - timedelta(days=200)
        row.paid_until = datetime.utcnow() - timedelta(days=110)
        db_session.commit()

        dukan.record_payment(db_session, row.slug, 600, months=3)

        # Extending from the old expiry would hand back a season already spent
        # dark — the shop would pay today and lapse again inside a fortnight.
        assert row.paid_until > datetime.utcnow() + timedelta(days=85)


class TestExpiryTakesTheItemsOffTheSite:
    def test_a_paid_shop_is_visible(self, db_session, shop):
        row, product = shop
        dukan.record_payment(db_session, row.slug, 600)
        assert _visible(db_session, row.slug, product)

    def test_the_day_after_expiry_the_price_is_gone(self, db_session, shop):
        row, product = shop
        dukan.record_payment(db_session, row.slug, 600)
        assert _visible(db_session, row.slug, product)

        row.paid_until = datetime.utcnow() - timedelta(days=1)
        db_session.commit()

        assert not _visible(db_session, row.slug, product), \
            "a lapsed shop is still quoting a price to farmers"
        assert dukan.is_lapsed(row)
        assert not dukan.is_live(row)

    def test_renewing_brings_the_items_straight_back(self, db_session, shop):
        row, product = shop
        row.paid_at = datetime.utcnow() - timedelta(days=100)
        row.paid_until = datetime.utcnow() - timedelta(days=10)
        db_session.commit()
        assert not _visible(db_session, row.slug, product)

        dukan.record_payment(db_session, row.slug, 600)

        # Nothing was deleted on the way out, so nothing has to be re-entered.
        assert _visible(db_session, row.slug, product)

    def test_a_shop_that_never_paid_keeps_the_onboarding_grace(self, db_session, shop):
        row, product = shop
        assert row.paid_until is None
        # Deliberate asymmetry, not an oversight: during onboarding an empty
        # directory is worth less than an unbilled listing, and there has to be
        # something to show a shopkeeper on a phone.
        assert _visible(db_session, row.slug, product)
        assert not dukan.is_lapsed(row)


class TestWhatTheAdminPanelReads:
    def test_days_left_is_none_when_no_clock_is_running(self, shop):
        row, _ = shop
        # None is "never paid", which the panel must not draw as "0 दिन बाकी".
        assert dukan.days_left(row) is None

    def test_a_last_day_reads_as_zero_not_as_a_day_that_is_not_there(self, shop):
        row, _ = shop
        row.paid_until = datetime.utcnow() + timedelta(hours=11)
        # The panel says "आज आखिरी दिन" for this. Rounding up would promise a
        # whole day on a listing that dies before the shopkeeper picks up.
        assert dukan.days_left(row) == 0

    def test_days_left_goes_negative_once_it_has_lapsed(self, shop):
        row, _ = shop
        row.paid_until = datetime.utcnow() - timedelta(days=2, hours=23)
        assert dukan.days_left(row) == -3

    def test_a_listing_that_died_an_hour_ago_never_reads_as_zero(self, shop):
        row, _ = shop
        row.paid_until = datetime.utcnow() - timedelta(hours=1)
        # 0 is reserved for "today is the last day" — a shop already off the
        # site must not share that number with one farmers can still see.
        assert dukan.days_left(row) == -1

    @pytest.mark.parametrize("hours,expected", [
        (30 * 24, False),   # plenty of time
        (5 * 24, True),     # the call worth making today
        (11, True),         # last day, still live
        (-1, False),        # already gone — that is LAPSED, not "soon"
        (-30 * 24, False),
    ])
    def test_expiring_soon_is_the_still_live_warning_only(self, shop, hours, expected):
        row, _ = shop
        row.paid_until = datetime.utcnow() + timedelta(hours=hours)
        assert dukan.expiring_soon(row) is expected

    def test_an_inactive_shop_is_not_chased_for_renewal(self, shop):
        row, _ = shop
        row.paid_until = datetime.utcnow() + timedelta(days=3)
        row.active = False
        # Nothing to save: it is not on the site whatever the date says.
        assert dukan.expiring_soon(row) is False

    def test_counts_carries_the_expiring_bucket(self, db_session, shop):
        row, _ = shop
        row.paid_until = datetime.utcnow() + timedelta(days=2)
        db_session.commit()
        assert dukan.counts(db_session)["expiring"] >= 1


class TestTheAdminAPICarriesTheTerm:
    """The panel draws entirely from these two responses. A field the panel
    reads and the API stopped sending renders as `undefined` in a Hindi
    sentence about money, so the contract is asserted rather than assumed."""

    AUTH = ("testadmin", "test-admin-pass")

    @pytest.fixture()
    def created(self, client):
        r = client.post("/admin/dukan/shops", auth=self.AUTH, json={
            "name": "API Krishi Kendra", "district": "Hardoi",
            "license_no": "UP/API/9", "plan": "season", "plan_months": 6,
            "active": True})
        assert r.status_code == 200, r.text
        slug = r.json()["shop"]["slug"]
        yield slug
        client.delete(f"/admin/dukan/shops/{slug}", auth=self.AUTH)

    def test_the_shop_carries_its_term_and_its_clock(self, client, created):
        r = client.get("/admin/dukan/shops", auth=self.AUTH)
        assert r.status_code == 200
        body = r.json()
        row = next(s for s in body["shops"] if s["slug"] == created)

        assert row["plan_months"] == 6
        # Never paid: no clock, and the panel draws that differently from 0.
        assert row["days_left"] is None
        assert row["expiring"] is False
        assert row["live"] is True

        # The rate card and the warning window come from the service, so the
        # panel never keeps a second opinion about what we sell.
        assert body["plan_months"] == list(dukan.PLAN_MONTHS)
        assert body["default_months"] == dukan.SEASON_MONTHS
        assert body["expiring_soon_days"] == dukan.EXPIRING_SOON_DAYS
        assert "expiring" in body["counts"]

    def test_the_term_can_be_changed_without_resending_the_whole_shop(
            self, client, created):
        # The drawer's dropdown sends exactly this one key. Validation must not
        # reject it for the name and licence it did not bother to repeat.
        r = client.patch(f"/admin/dukan/shops/{created}", auth=self.AUTH,
                         json={"plan_months": 12})
        assert r.status_code == 200, r.text
        assert r.json()["shop"]["plan_months"] == 12

    def test_a_nonsense_term_is_refused_with_a_message_not_a_500(
            self, client, created):
        r = client.patch(f"/admin/dukan/shops/{created}", auth=self.AUTH,
                         json={"plan_months": 99})
        assert r.status_code == 400
        assert "अवधि" in r.json()["detail"]

    def test_a_payment_with_no_months_uses_the_shops_own_term(self, client, created):
        r = client.post(f"/admin/dukan/shops/{created}/payment", auth=self.AUTH,
                        json={"amount": 1200, "ref": "TESTREF"})
        assert r.status_code == 200, r.text
        row = r.json()["shop"]

        # 6 months was agreed at creation; a blank months field is a plain
        # renewal, not a request for the global default.
        assert 175 <= row["days_left"] <= 181
        assert row["live"] is True
        assert row["expiring"] is False

    def test_a_payment_may_override_the_term_for_that_payment_only(
            self, client, created):
        r = client.post(f"/admin/dukan/shops/{created}/payment", auth=self.AUTH,
                        json={"amount": 200, "months": 1})
        assert r.status_code == 200, r.text
        row = r.json()["shop"]
        assert row["days_left"] <= 31
        assert row["plan_months"] == 6, "a one-off payment rewrote the agreed term"
