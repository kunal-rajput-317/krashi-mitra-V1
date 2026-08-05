"""The dealer pipeline: paid signup → admin queue → live on the state page.

/dukanlisting replaced the free anonymous /dukan/signup entirely: a dealer now
logs in, picks several districts, and pays a monthly subscription (₹199 for the
first district, +₹50 each after). Four properties carry the weight here.

**The trust rule is structural.** data/buyers.json states it in prose — a blue
tick is a claim we make to a farmer about a stranger's phone number, so it costs
one real phone call. Prose does not enforce anything. `from_signup()` has no
code path to `active` or `verified`, and these tests fail if one is ever added.
Paying does not open that door either: for a self-serve account `record_payment`
buys the subscription window and nothing else.

**The money and the listing are separate gates.** A dealer who has paid but not
been called is not live; a dealer who was called but has lapsed is not live
either. Both directions are asserted, because each fails silently the other way.

**One payment covers the account, not one row.** A dealer with three districts
has three `buyers` rows and one subscription — a renewal that only extended the
row the admin happened to click would quietly unlist the other two.

**Durability is the reason the table exists at all.** Render's free plan has no
persistent disk, so a dealer written back into data/buyers.json would survive
until the next restart and then silently revert. The admin panel therefore must
never write to the seed file — asserted directly, because that regression looks
like success right up until the dyno sleeps.
"""

import json
from datetime import datetime, timedelta

import pytest

from backend.services import buyers, dealers

ADMIN = ("testadmin", "test-admin-pass")     # set in conftest before backend import


def _dealer_panel(body: str) -> str:
    """Just the "सत्यापित दुकानें" panel (bhav.py::_dealer_teaser_html).

    A tier-3 page carries two blocks built from the same product-card design:
    this panel, which renders the dealer's REAL catalogue, and the दुकान promo
    under the MSP card, whose sample card is hard-coded. Asserting against the
    whole page cannot tell them apart, so a "the dealer's product must not show
    X" test would pass or fail on the promo's dummy data instead.
    """
    start = body.find('class="bp-wrap"')
    if start < 0:
        return ""
    end = body.find("</section>", start)
    return body[start:end if end > 0 else len(body)]


@pytest.fixture()
def clean(db_session, monkeypatch):
    """Empty buyers table, caches dropped on both sides, rate limiter reset.

    The limiter is process-global and keyed by IP; every test here shares
    TestClient's, so without the reset the fourth signup in the file 429s and
    the failure looks like a validation bug.
    """
    from backend.database.db import BazarPost, Buyer, DealerProduct, User
    from backend.utils import security

    security._hits.clear()
    # DealerProduct first: it outlives its buyer row, so leaving it behind
    # leaks a catalogue into the next test and trips the per-dealer cap.
    db_session.query(DealerProduct).delete()
    db_session.query(Buyer).delete()
    db_session.query(BazarPost).delete()
    db_session.query(User).filter(User.email.like("dealer-test%")).delete()
    db_session.commit()
    buyers.invalidate()
    monkeypatch.setattr(buyers, "_cache", None)
    monkeypatch.setattr(buyers, "_mtime", -1.0)
    monkeypatch.setattr(buyers, "_place_idx", {})
    yield db_session
    db_session.query(DealerProduct).delete()
    db_session.query(Buyer).delete()
    db_session.query(BazarPost).delete()
    db_session.query(User).filter(User.email.like("dealer-test%")).delete()
    db_session.commit()
    buyers.invalidate()


@pytest.fixture()
def dealer_user(clean):
    """A verified account for the dealer to sign up with, plus its bearer token.

    Verified on purpose: resolve_token_user() rejects a token for an unverified
    account, so an unverified user here would fail every request for the wrong
    reason and hide whatever the test was actually checking.
    """
    from backend.database.db import User
    from backend.utils.auth_utils import create_access_token

    user = User(name="Sharma Ji", email="dealer-test@example.com",
                hashed_password="x", is_verified=True,
                created_at=datetime.utcnow())
    clean.add(user)
    clean.commit()
    clean.refresh(user)
    token = create_access_token(user.id, user.email)
    return user, {"Authorization": f"Bearer {token}"}


def _listings(client, headers, **over):
    body = {"name": "Sharma Traders", "kind": "trader", "phone": "9876543210",
            "commodities": ["wheat"],
            "districts": [{"state": "Uttar Pradesh", "district": "Hardoi",
                           "market": "Hardoi Mandi"}]}
    body.update(over)
    return client.post("/dukanlisting/listings", json=body, headers=headers)


class TestLoginIsRequired:
    """The whole model rests on a real account: a bazar post needs a users.id
    to author as, and a subscription needs somebody to renew it."""

    @pytest.mark.parametrize("method, path", [
        ("post", "/dukanlisting/listings"),
        ("get", "/dukanlisting/mine"),
        ("delete", "/dukanlisting/listings/any-slug"),
    ])
    def test_endpoints_reject_anonymous_callers(self, clean, client, method, path):
        response = getattr(client, method)(path, **({"json": {}} if method == "post" else {}))
        assert response.status_code in (401, 403), (
            f"{method.upper()} {path} answered an anonymous caller")

    @pytest.mark.parametrize("path", ["/dukan/signup", "/dukanlisting/signup"])
    def test_the_old_free_signup_endpoint_is_gone(self, clean, client, path):
        """It let anyone create a row with no account and no subscription.

        Both spellings: /dukan/signup is the one that actually shipped, and the
        whole /dukan prefix moved to /dukanlisting afterwards. A rename must not
        quietly resurrect a free signup under the new name.

        405 rather than 404: a catch-all GET route further down the stack still
        matches the path, so the method is what gets rejected. Either way it is
        unroutable — and the row count is the assertion that actually matters.
        """
        response = client.post(path, json={
            "name": "Ghost Traders", "district": "Hardoi", "phone": "9876543210"})
        assert response.status_code in (404, 405)
        assert clean.query(dealers.Buyer).count() == 0


class TestPaidSignupCannotListItself:
    """The trust rule, enforced in the schema rather than remembered."""

    def test_signup_is_accepted(self, dealer_user, client):
        _user, headers = dealer_user
        response = _listings(client, headers)
        assert response.status_code == 200, response.text
        assert response.json()["success"] is True

    def test_signup_lands_inactive_and_unverified(self, clean, dealer_user, client):
        _user, headers = dealer_user
        _listings(client, headers)
        row = clean.query(dealers.Buyer).filter(
            dealers.Buyer.name == "Sharma Traders").one()
        assert row.active is False, "a self-signup went live without a phone call"
        assert row.verified is False, "a self-signup awarded itself the blue tick"
        assert row.source == "signup"
        assert row.status == "new"

    def test_signup_cannot_set_the_flags_directly(self, clean, dealer_user, client):
        """The payload is attacker-controlled; the flags must be ignored."""
        _user, headers = dealer_user
        _listings(client, headers, active=True, verified=True, featured=True,
                  status="listed", bhav_rank=1)
        row = clean.query(dealers.Buyer).filter(
            dealers.Buyer.name == "Sharma Traders").one()
        assert (row.active, row.verified, row.featured) == (False, False, False)
        assert row.status == "new"
        assert row.bhav_rank is None, "a self-signup ranked itself onto the bhav panel"

    def test_signup_cannot_claim_another_users_account(self, clean, dealer_user, client):
        """owner_user_id comes from the token, never from the body."""
        user, headers = dealer_user
        _listings(client, headers, owner_user_id=user.id + 999)
        row = clean.query(dealers.Buyer).filter(
            dealers.Buyer.name == "Sharma Traders").one()
        assert row.owner_user_id == user.id

    def test_pending_signup_is_invisible_to_farmers(self, dealer_user, client):
        """The read side must not surface it — no district, no sitemap, nothing."""
        _user, headers = dealer_user
        _listings(client, headers)
        buyers.invalidate()
        assert buyers.for_place("wheat", "Uttar Pradesh", "Hardoi") == []
        assert buyers.live_places() == set()


class TestMultiDistrict:
    """One account, several districts, one subscription."""

    THREE = [{"state": "Uttar Pradesh", "district": "Hardoi"},
             {"state": "Uttar Pradesh", "district": "Sitapur"},
             {"state": "Uttar Pradesh", "district": "Unnao"}]

    def test_one_row_per_district_all_sharing_the_owner(self, clean, dealer_user, client):
        user, headers = dealer_user
        response = _listings(client, headers, districts=self.THREE)
        assert response.status_code == 200, response.text
        rows = dealers.for_owner(clean, user.id)
        assert sorted(r.district for r in rows) == ["Hardoi", "Sitapur", "Unnao"]
        assert {r.owner_user_id for r in rows} == {user.id}

    def test_resubmitting_adds_only_the_new_district(self, clean, dealer_user, client):
        """Additive, not replace-all: re-submitting must not duplicate a row or
        wipe the call/payment history already on it."""
        user, headers = dealer_user
        _listings(client, headers)
        _listings(client, headers, districts=[
            {"state": "Uttar Pradesh", "district": "Hardoi"},     # already there
            {"state": "Uttar Pradesh", "district": "Sitapur"},    # new
        ])
        rows = dealers.for_owner(clean, user.id)
        assert sorted(r.district for r in rows) == ["Hardoi", "Sitapur"]

    def test_district_is_required(self, dealer_user, client):
        _user, headers = dealer_user
        assert _listings(client, headers, districts=[]).status_code == 400

    def test_mine_reports_districts_and_price(self, dealer_user, client):
        _user, headers = dealer_user
        _listings(client, headers, districts=self.THREE)
        data = client.get("/dukanlisting/mine", headers=headers).json()["data"]
        assert data["district_count"] == 3
        assert data["price"] == 299          # 199 + 2 x 50
        assert {l["district"] for l in data["listings"]} == {"Hardoi", "Sitapur", "Unnao"}

    def test_dealer_can_drop_one_of_his_own_districts(self, clean, dealer_user, client):
        user, headers = dealer_user
        _listings(client, headers, districts=self.THREE)
        slug = dealers.for_owner(clean, user.id)[0].slug
        assert client.delete(f"/dukanlisting/listings/{slug}", headers=headers).status_code == 200
        assert len(dealers.for_owner(clean, user.id)) == 2

    def test_dealer_cannot_drop_someone_elses_listing(self, clean, dealer_user, client):
        """Ownership is checked in the route: dealers.delete() is also the
        admin's tool and must not grow an auth check of its own."""
        _user, headers = dealer_user
        other = dealers.create(clean, {"name": "Verma Aadhat", "district": "Kanpur Nagar",
                                       "state": "Uttar Pradesh", "phone": "9998887770"})
        assert client.delete(f"/dukanlisting/listings/{other.slug}",
                             headers=headers).status_code == 404
        assert clean.query(dealers.Buyer).filter_by(slug=other.slug).first() is not None


class TestPricing:
    """₹199 for the first district, +₹50 for each additional one. One formula,
    quoted by both the signup form and the admin collect modal."""

    @pytest.mark.parametrize("n, expected", [
        (1, 199), (2, 249), (3, 299), (5, 399), (10, 649),
        (0, 199),   # never below the floor — a 0-district account cannot exist
    ])
    def test_quote(self, n, expected):
        assert dealers.quote(n) == expected

    def test_account_price_follows_the_district_count(self, clean, dealer_user, client):
        user, headers = dealer_user
        _listings(client, headers, districts=[
            {"state": "Uttar Pradesh", "district": "Hardoi"},
            {"state": "Uttar Pradesh", "district": "Sitapur"},
        ])
        assert dealers.account_price(clean, user.id) == 249


class TestPaymentAndVerificationAreSeparateGates:
    """Paying buys the subscription window. Being listed costs a phone call.
    Neither substitutes for the other."""

    def _signed_up(self, clean, dealer_user, client, districts=None):
        user, headers = dealer_user
        _listings(client, headers, **({"districts": districts} if districts else {}))
        return user, headers, dealers.for_owner(clean, user.id)

    def test_paying_does_not_list_a_self_serve_dealer(self, clean, dealer_user, client):
        """The regression this exists to prevent: record_payment() used to set
        active=True unconditionally, which would put an unverified stranger's
        phone number in front of farmers the moment he paid."""
        _user, _headers, rows = self._signed_up(clean, dealer_user, client)
        dealers.record_payment(clean, rows[0].slug, 199)
        row = clean.query(dealers.Buyer).filter_by(slug=rows[0].slug).one()
        assert row.paid_until is not None, "the subscription window was not opened"
        assert row.active is False, "paying listed a dealer nobody has called"
        assert row.verified is False, "paying awarded the blue tick"

    def test_paying_still_lists_a_legacy_admin_row(self, clean):
        """Unchanged behaviour for admin-typed rows: the owner is adding it
        *because* he just spoke to the dealer."""
        row = dealers.create(clean, {"name": "Verma Aadhat", "district": "Hardoi",
                                     "state": "Uttar Pradesh", "phone": "9998887770"})
        dealers.record_payment(clean, row.slug, 500)
        after = clean.query(dealers.Buyer).filter_by(slug=row.slug).one()
        assert after.active is True and after.status == "listed"

    def test_one_payment_renews_every_district_on_the_account(self, clean, dealer_user, client):
        _user, _headers, rows = self._signed_up(clean, dealer_user, client, districts=[
            {"state": "Uttar Pradesh", "district": "Hardoi"},
            {"state": "Uttar Pradesh", "district": "Sitapur"},
        ])
        dealers.record_payment(clean, rows[0].slug, 249)
        paid = [r.paid_until for r in dealers.for_owner(clean, rows[0].owner_user_id)]
        assert all(p is not None for p in paid), (
            "a renewal only extended the row the admin clicked — the rest lapsed")
        assert len(set(paid)) == 1, "the account's districts expire on different days"

    def test_verified_but_unpaid_is_not_visible(self, clean, dealer_user, client):
        """The subscription is what the dealer is buying; without it there is
        nothing to show, however trusted he is."""
        _user, _headers, rows = self._signed_up(clean, dealer_user, client)
        dealers.approve(clean, rows[0].slug)
        buyers.invalidate()
        assert buyers.for_place("wheat", "Uttar Pradesh", "Hardoi") == []

    def test_verified_and_paid_is_visible(self, clean, dealer_user, client):
        _user, _headers, rows = self._signed_up(clean, dealer_user, client)
        dealers.approve(clean, rows[0].slug)
        dealers.record_payment(clean, rows[0].slug, 199)
        buyers.invalidate()
        assert [b["name"] for b in buyers.for_place("wheat", "Uttar Pradesh", "Hardoi")] \
            == ["Sharma Traders"]

    def test_a_lapsed_subscription_disappears_without_being_deleted(self, clean, dealer_user, client):
        """Lapsing must be reversible by paying, so the row stays — it just
        stops rendering. active/verified are deliberately left alone."""
        _user, _headers, rows = self._signed_up(clean, dealer_user, client)
        dealers.approve(clean, rows[0].slug)
        dealers.record_payment(clean, rows[0].slug, 199)
        row = clean.query(dealers.Buyer).filter_by(slug=rows[0].slug).one()
        row.paid_until = datetime.utcnow() - timedelta(days=1)
        clean.commit()
        buyers.invalidate()
        assert buyers.for_place("wheat", "Uttar Pradesh", "Hardoi") == []
        assert clean.query(dealers.Buyer).filter_by(slug=rows[0].slug).one().active is True

    def test_legacy_rows_never_need_a_subscription(self, clean):
        """The seed file and admin-added rows predate the paid model and keep
        working exactly as before — this is the check that the payment gate did
        not quietly unlist every dealer already on the site."""
        row = dealers.create(clean, {"name": "Verma Aadhat", "district": "Hardoi",
                                     "state": "Uttar Pradesh", "phone": "9998887770",
                                     "commodities": ["wheat"]})
        assert row.paid_until is None
        buyers.invalidate()
        assert [b["name"] for b in buyers.for_place("wheat", "Uttar Pradesh", "Hardoi")] \
            == ["Verma Aadhat"]


class TestBhavPanelRanking:
    """Which <=3 dealers appear on a crop+state Tier-3 page is the owner's call,
    made in the admin panel — never automatic."""

    def _live_dealer(self, clean, name, district, state="Uttar Pradesh",
                     owner_user_id=1, commodities=("wheat",)):
        row = dealers.create(clean, {
            "name": name, "district": district, "state": state,
            "phone": "9876543210", "commodities": list(commodities),
            "owner_user_id": owner_user_id}, source="signup")
        dealers.approve(clean, row.slug)
        dealers.record_payment(clean, row.slug, 199)
        return clean.query(dealers.Buyer).filter_by(slug=row.slug).one()

    def test_unranked_dealers_do_not_appear(self, clean):
        """Paying buys eligibility for the panel, not a slot on it."""
        self._live_dealer(clean, "Sharma Traders", "Hardoi")
        buyers.invalidate()
        assert buyers.for_bhav_panel("Uttar Pradesh", "wheat") == []

    def test_ranked_dealer_appears(self, clean):
        row = self._live_dealer(clean, "Sharma Traders", "Hardoi")
        dealers.set_bhav_rank(clean, row.slug, 1)
        buyers.invalidate()
        assert [b["name"] for b in buyers.for_bhav_panel("Uttar Pradesh", "wheat")] \
            == ["Sharma Traders"]

    def test_panel_is_ordered_by_rank_and_capped_at_three(self, clean):
        for i, (name, dist) in enumerate([
            ("Third Firm", "Unnao"), ("First Firm", "Hardoi"),
            ("Second Firm", "Sitapur"), ("Fourth Firm", "Kanpur Nagar"),
        ]):
            row = self._live_dealer(clean, name, dist, owner_user_id=i + 1)
            # Fourth Firm deliberately gets no rank — there are only three slots.
            rank = {"First Firm": 1, "Second Firm": 2, "Third Firm": 3}.get(name)
            if rank:
                dealers.set_bhav_rank(clean, row.slug, rank)
        buyers.invalidate()
        assert [b["name"] for b in buyers.for_bhav_panel("Uttar Pradesh", "wheat")] \
            == ["First Firm", "Second Firm", "Third Firm"]

    def test_one_holder_per_rank_per_state(self, clean):
        """Giving rank 1 to a second dealer takes it off the first, rather than
        rendering two dealers in the same slot."""
        a = self._live_dealer(clean, "Sharma Traders", "Hardoi", owner_user_id=1)
        b = self._live_dealer(clean, "Verma Aadhat", "Sitapur", owner_user_id=2)
        dealers.set_bhav_rank(clean, a.slug, 1)
        dealers.set_bhav_rank(clean, b.slug, 1)
        assert clean.query(dealers.Buyer).filter_by(slug=a.slug).one().bhav_rank is None
        assert clean.query(dealers.Buyer).filter_by(slug=b.slug).one().bhav_rank == 1

    def test_the_same_rank_is_free_in_another_state(self, clean):
        """Ranks are scoped per state — a Bihar slot 1 must not evict a UP one."""
        up = self._live_dealer(clean, "Sharma Traders", "Hardoi", owner_user_id=1)
        br = self._live_dealer(clean, "Kumar Traders", "Patna", state="Bihar",
                               owner_user_id=2)
        dealers.set_bhav_rank(clean, up.slug, 1)
        dealers.set_bhav_rank(clean, br.slug, 1)
        assert clean.query(dealers.Buyer).filter_by(slug=up.slug).one().bhav_rank == 1
        assert clean.query(dealers.Buyer).filter_by(slug=br.slug).one().bhav_rank == 1

    def test_panel_respects_the_crop_filter(self, clean):
        row = self._live_dealer(clean, "Aloo Wale", "Hardoi", commodities=("potato",))
        dealers.set_bhav_rank(clean, row.slug, 1)
        buyers.invalidate()
        assert buyers.for_bhav_panel("Uttar Pradesh", "wheat") == []
        assert len(buyers.for_bhav_panel("Uttar Pradesh", "potato")) == 1

    def test_empty_commodities_matches_every_crop(self, clean):
        """The आढ़तिया case: buys everything, so it must not filter to nothing."""
        row = self._live_dealer(clean, "Sab Kuch Traders", "Hardoi", commodities=())
        dealers.set_bhav_rank(clean, row.slug, 1)
        buyers.invalidate()
        assert len(buyers.for_bhav_panel("Uttar Pradesh", "wheat")) == 1

    def test_rank_survives_only_while_paid(self, clean):
        row = self._live_dealer(clean, "Sharma Traders", "Hardoi")
        dealers.set_bhav_rank(clean, row.slug, 1)
        row.paid_until = datetime.utcnow() - timedelta(days=1)
        clean.commit()
        buyers.invalidate()
        assert buyers.for_bhav_panel("Uttar Pradesh", "wheat") == [], (
            "a lapsed dealer kept his paid slot on the state page")

    def test_rank_is_admin_only_over_http(self, clean):
        row = self._live_dealer(clean, "Sharma Traders", "Hardoi")
        assert client_patch_rank_unauthed(row.slug) in (401, 403)


def client_patch_rank_unauthed(slug):
    """Kept out of the test body so the fixture list stays readable."""
    from fastapi.testclient import TestClient

    from backend.main import app
    return TestClient(app, raise_server_exceptions=False).patch(
        f"/admin/buyers/{slug}/rank", json={"rank": 1}).status_code


class TestPrivateNoteNeverReachesAFarmer:
    """`note` is the admin's call log — log_call() appends "[04 Aug] wants a
    discount" to it after every call — and it used to be the very field the
    public kharidar card rendered. Internal remarks about a dealer's haggling
    were therefore published to farmers under his own name.

    `description` now carries the dealer's own public words and `note` is not
    in the public dict at all, so no render path can reach it.
    """

    def _live(self, clean, **over):
        data = {"name": "Sharma Traders", "district": "Hardoi",
                "state": "Uttar Pradesh", "phone": "9876543210",
                "commodities": ["wheat"]}
        data.update(over)
        return dealers.create(clean, data)

    def test_note_is_absent_from_the_public_dict(self, clean):
        self._live(clean, note="बहुत मोल-भाव करता है, 300 से ऊपर नहीं देगा")
        buyers.invalidate()
        row = buyers.for_place("wheat", "Uttar Pradesh", "Hardoi")[0]
        assert "note" not in row, "the private call log is in the public payload"

    def test_call_log_never_renders_on_the_kharidar_page(self, clean, client, monkeypatch):
        from backend.routes import bhav

        row = self._live(clean)
        dealers.log_call(clean, row.slug, "pitched", "मोल-भाव कर रहा है")
        monkeypatch.setattr(bhav, "_index", {
            "crops": {"wheat": "Wheat"},
            "states": {"wheat": {"up": "Uttar Pradesh"}},
            "dists": {"wheat": {"up": {"hardoi": "Hardoi"}}},
            "dates": {"wheat": {"up": {"hardoi": "2026-07-30"}}}})
        monkeypatch.setattr(bhav, "_index_ts", float("inf"))
        monkeypatch.setattr(bhav, "_kharidar_places", lambda: set())
        monkeypatch.setattr(bhav, "_bazar_slice", lambda *a, **k: [])
        monkeypatch.setattr(bhav, "_sell_intent", lambda *a, **k: 0)
        buyers.invalidate()

        body = client.get("/bhav/wheat/up/hardoi/kharidar").text
        assert "मोल-भाव" not in body, "a private call note was published to farmers"

    def test_description_is_what_renders(self, clean, client, monkeypatch):
        from backend.routes import bhav

        self._live(clean, description="गेहूं थोक में खरीदते हैं, नकद भुगतान")
        monkeypatch.setattr(bhav, "_index", {
            "crops": {"wheat": "Wheat"},
            "states": {"wheat": {"up": "Uttar Pradesh"}},
            "dists": {"wheat": {"up": {"hardoi": "Hardoi"}}},
            "dates": {"wheat": {"up": {"hardoi": "2026-07-30"}}}})
        monkeypatch.setattr(bhav, "_index_ts", float("inf"))
        monkeypatch.setattr(bhav, "_kharidar_places", lambda: set())
        monkeypatch.setattr(bhav, "_bazar_slice", lambda *a, **k: [])
        monkeypatch.setattr(bhav, "_sell_intent", lambda *a, **k: 0)
        buyers.invalidate()

        assert "नकद भुगतान" in client.get("/bhav/wheat/up/hardoi/kharidar").text

    def test_signup_can_set_its_description_but_not_its_note(self, clean, dealer_user, client):
        """A dealer writes his own blurb; he cannot write into the call log."""
        _user, headers = dealer_user
        _listings(client, headers, description="मैं गेहूं खरीदता हूं",
                  note="मुझे मुफ्त लिस्टिंग दो")
        row = clean.query(dealers.Buyer).filter(
            dealers.Buyer.name == "Sharma Traders").one()
        assert row.description == "मैं गेहूं खरीदता हूं"
        assert row.note is None, "a dealer wrote into the private call log"


class TestCredentialsAreAdminOnly:
    """GSTIN / licence / email / address make `verified` checkable instead of a
    feeling. None of them may ever reach a farmer-facing page."""

    CREDS = {"gstin": "09ABCDE1234F1Z5", "license_no": "FERT/2019/4471",
             "email": "sharma@example.com", "address": "Mandi Road, Hardoi"}

    def test_admin_can_set_and_read_them(self, clean, client):
        row = dealers.create(clean, {
            "name": "Sharma Traders", "district": "Hardoi", "state": "Uttar Pradesh",
            "phone": "9876543210", **self.CREDS})
        listed = [b for b in dealers.listing(clean) if b["slug"] == row.slug][0]
        for key, value in self.CREDS.items():
            assert listed[key] == value

    def test_they_are_absent_from_the_public_dict(self, clean):
        dealers.create(clean, {
            "name": "Sharma Traders", "district": "Hardoi", "state": "Uttar Pradesh",
            "phone": "9876543210", "commodities": ["wheat"], **self.CREDS})
        buyers.invalidate()
        public = buyers.for_place("wheat", "Uttar Pradesh", "Hardoi")[0]
        for key in self.CREDS:
            assert key not in public, f"{key} leaked into the farmer-facing payload"

    def test_a_signup_cannot_set_its_own_credentials(self, clean, dealer_user, client):
        """They are our record of what WE checked, not his claim about himself."""
        _user, headers = dealer_user
        _listings(client, headers, **self.CREDS)
        row = clean.query(dealers.Buyer).filter(
            dealers.Buyer.name == "Sharma Traders").one()
        assert row.gstin is None and row.license_no is None
        assert row.email is None and row.address is None

    def test_editing_over_http_persists_them(self, clean, client):
        row = dealers.create(clean, {"name": "Sharma Traders", "district": "Hardoi",
                                     "state": "Uttar Pradesh", "phone": "9876543210"})
        r = client.patch(f"/admin/buyers/{row.slug}", auth=ADMIN, json=self.CREDS)
        assert r.status_code == 200, r.text
        after = clean.query(dealers.Buyer).filter_by(slug=row.slug).one()
        clean.refresh(after)
        assert after.gstin == self.CREDS["gstin"]
        assert after.license_no == self.CREDS["license_no"]

    def test_editing_keeps_the_slug(self, clean, client):
        """The panel's edit path must not orphan LeadClick history."""
        row = dealers.create(clean, {"name": "Old Firm", "district": "Hardoi",
                                     "state": "Uttar Pradesh", "phone": "9876543210"})
        before = row.slug
        client.patch(f"/admin/buyers/{before}", auth=ADMIN,
                     json={"name": "New Firm", "gstin": "09ABCDE1234F1Z5"})
        # The route wrote through its own session; this one still holds the
        # pre-edit instance.
        clean.expire_all()
        assert clean.query(dealers.Buyer).filter_by(slug=before).one().name == "New Firm"


class TestSubscriptionLapseIsNeverSilent:
    """A subscription simply ending used to be invisible.

    services/buyers.py::_usable drops a /dukanlisting dealer from every
    farmer-facing surface the moment `paid_until` passes, and nothing told him
    — his listing went dark and the first he knew was the calls stopping. Worse
    for us: a lapse nobody chases is revenue lost in silence.

    Both halves are asserted here — the dealer's own KrashiBook warning, and the
    renewal list the owner works from. Derived live on every request (no
    scheduler, no "reminder sent" flag), because a cron that quietly stops is
    exactly the failure this is meant to prevent.
    """

    def _account(self, clean, client, dealer_user, days=None, verified=True):
        """A dealer whose subscription ends `days` from now (negative = past)."""
        user, headers = dealer_user
        _listings(client, headers)
        row = dealers.for_owner(clean, user.id)[0]
        if verified:
            dealers.approve(clean, row.slug)
        if days is not None:
            dealers.record_payment(clean, row.slug, 199)
            live = clean.query(dealers.Buyer).filter_by(slug=row.slug).one()
            live.paid_until = datetime.utcnow() + timedelta(days=days)
            clean.commit()
        return headers, row

    def test_anonymous_callers_are_rejected(self, clean, client):
        assert client.get("/dukanlisting/subscription").status_code in (401, 403)

    def test_a_farmer_with_no_listing_gets_nothing(self, clean, dealer_user, client):
        """This endpoint is polled by KrashiBook on pages farmers use too."""
        _user, headers = dealer_user
        d = client.get("/dukanlisting/subscription", headers=headers).json()["data"]
        assert d["state"] == "none"
        assert d["alerts"] == []

    @pytest.mark.parametrize("days, state", [
        (30, "active"),      # comfortably paid
        (7, "expiring"),     # inside the warning window
        (1, "expiring"),
        (-1, "lapsed"),      # already dark
    ])
    def test_state_is_derived_from_paid_until(self, clean, dealer_user, client,
                                               days, state):
        headers, _row = self._account(clean, client, dealer_user, days=days)
        d = client.get("/dukanlisting/subscription", headers=headers).json()["data"]
        assert d["state"] == state

    def test_a_healthy_subscription_raises_no_alert(self, clean, dealer_user, client):
        """A badge that lights up for good news teaches him to ignore the badge."""
        headers, _row = self._account(clean, client, dealer_user, days=30)
        d = client.get("/dukanlisting/subscription", headers=headers).json()["data"]
        assert d["alerts"] == []
        assert d["now_count"] == 0

    def test_expiring_warns_before_it_goes_dark(self, clean, dealer_user, client):
        headers, _row = self._account(clean, client, dealer_user, days=3)
        d = client.get("/dukanlisting/subscription", headers=headers).json()["data"]
        assert len(d["alerts"]) == 1
        assert "खत्म" in d["alerts"][0]["title_hi"]
        # The price he has to pay is in the message — a reminder he cannot act
        # on is just an interruption.
        assert str(d["price"]) in d["alerts"][0]["detail_hi"]

    def test_lapsed_says_the_listing_is_already_off(self, clean, dealer_user, client):
        headers, _row = self._account(clean, client, dealer_user, days=-2)
        d = client.get("/dukanlisting/subscription", headers=headers).json()["data"]
        assert d["alerts"][0]["urgency"] == "now"
        assert d["now_count"] == 1
        assert "बंद" in d["alerts"][0]["title_hi"]

    def test_verified_but_never_paid_is_chased_too(self, clean, dealer_user, client):
        """Called, approved, and then the close was never made."""
        headers, _row = self._account(clean, client, dealer_user, days=None)
        d = client.get("/dukanlisting/subscription", headers=headers).json()["data"]
        assert d["state"] == "unpaid"
        assert len(d["alerts"]) == 1
        assert "भुगतान" in d["alerts"][0]["title_hi"]

    def test_an_unverified_signup_is_not_nagged_for_money(self, clean, dealer_user,
                                                           client):
        """He has not been called yet — asking him to pay would jump the queue
        the whole trust model rests on."""
        headers, _row = self._account(clean, client, dealer_user, days=None,
                                      verified=False)
        d = client.get("/dukanlisting/subscription", headers=headers).json()["data"]
        assert d["alerts"] == []

    def test_price_reflects_every_district_on_the_account(self, clean, dealer_user,
                                                           client):
        user, headers = dealer_user
        _listings(client, headers, districts=[
            {"state": "Uttar Pradesh", "district": "Hardoi"},
            {"state": "Uttar Pradesh", "district": "Sitapur"},
            {"state": "Uttar Pradesh", "district": "Unnao"},
        ])
        row = dealers.for_owner(clean, user.id)[0]
        dealers.approve(clean, row.slug)
        d = client.get("/dukanlisting/subscription", headers=headers).json()["data"]
        assert d["district_count"] == 3
        assert d["price"] == 299

    # ── the owner's half: the renewal call list ──

    def test_admin_counts_expiring_and_lapsed(self, clean, dealer_user, client):
        headers, _row = self._account(clean, client, dealer_user, days=3)
        counts = client.get("/admin/buyers", auth=ADMIN).json()["counts"]
        assert counts["expiring"] == 1
        assert counts["lapsed"] == 0

        # Push it past the end date; it should move buckets, not vanish.
        row = dealers.for_owner(clean, dealer_user[0].id)[0]
        live = clean.query(dealers.Buyer).filter_by(slug=row.slug).one()
        live.paid_until = datetime.utcnow() - timedelta(days=1)
        clean.commit()
        counts = client.get("/admin/buyers", auth=ADMIN).json()["counts"]
        assert counts["expiring"] == 0
        assert counts["lapsed"] == 1

    def test_renewal_list_counts_accounts_not_rows(self, clean, dealer_user, client):
        """Three districts on one subscription is ONE phone call."""
        user, headers = dealer_user
        _listings(client, headers, districts=[
            {"state": "Uttar Pradesh", "district": "Hardoi"},
            {"state": "Uttar Pradesh", "district": "Sitapur"},
            {"state": "Uttar Pradesh", "district": "Unnao"},
        ])
        row = dealers.for_owner(clean, user.id)[0]
        dealers.approve(clean, row.slug)
        dealers.record_payment(clean, row.slug, 299)   # renews all three
        for r in dealers.for_owner(clean, user.id):
            r.paid_until = datetime.utcnow() + timedelta(days=3)
        clean.commit()
        assert client.get("/admin/buyers", auth=ADMIN).json()["counts"]["expiring"] == 1

    def test_the_warning_window_is_one_shared_constant(self):
        """The dealer's warning and the owner's call list must agree about who
        is about to go dark."""
        from backend.routes import dukanlisting as dukan_route
        assert dukan_route._EXPIRY_WARN_DAYS == dealers.EXPIRY_WARN_DAYS



class TestDealerCatalogue:
    """/dukanlisting is named after this: what a paying dealer sells, and at
    what price, rendered as a card a farmer recognises from the shop.

    The card shape is deliberately the same as routes/product.py::_hub_card —
    name_hi, name_en, price, struck MRP, "% off", pack size — so a dealer's
    item and a KrashiMitra item read as the same kind of thing.
    """

    def _png(self, size=(600, 400)):
        import io

        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", size, (34, 90, 60)).save(buf, format="PNG")
        return buf.getvalue()

    # Deliberately not 1: the `dealer_user` fixture's account is usually id 1,
    # and an owner id that collides with it would make "someone else's product"
    # actually his — the ownership test would then pass for the wrong reason.
    OTHER_OWNER = 4242

    @pytest.fixture()
    def listed(self, clean):
        """A live, paying, ranked dealer — products only ever render for one."""
        row = dealers.create(clean, {
            "name": "Sharma Traders", "district": "Hardoi", "state": "Uttar Pradesh",
            "phone": "9876543210", "commodities": ["wheat"],
            "owner_user_id": self.OTHER_OWNER},
            source="signup")
        dealers.approve(clean, row.slug)
        dealers.record_payment(clean, row.slug, 199)
        dealers.set_bhav_rank(clean, row.slug, 1)
        buyers.invalidate()
        return row

    def _add(self, client, slug, **over):
        body = {"name_hi": "गेहूं बीज HD-2967", "name_en": "Wheat Seeds HD-2967",
                "price": 280, "mrp": 350, "unit_hi": "5 kg बैग", "badge": "बीज"}
        body.update(over)
        return client.post(f"/admin/buyers/{slug}/products", auth=ADMIN, json=body)

    # ── the numbers on the card ──

    @pytest.mark.parametrize("price, mrp, expected", [
        (280, 350, 20),      # the screenshot
        (100, 200, 50),
        (280, None, 0),      # no MRP -> no discount pill at all
        (280, 280, 0),       # equal -> not a saving
    ])
    def test_discount_matches_the_shops_formula(self, price, mrp, expected):
        from backend.services import dealer_products
        assert dealer_products.off_pct(price, mrp) == expected

    def test_mrp_below_price_is_rejected(self, clean, listed, client):
        """It would render a negative "% off" — a typo reaching a farmer as a
        lie about a saving."""
        assert self._add(client, listed.slug, price=350, mrp=280).status_code == 400

    def test_price_is_required(self, clean, listed, client):
        assert self._add(client, listed.slug, price=0).status_code == 400
        assert self._add(client, listed.slug, name_hi="").status_code == 400

    # ── rendering ──

    def _bhav(self, monkeypatch):
        from backend.routes import bhav
        monkeypatch.setattr(bhav, "_index", {
            "crops": {"wheat": "Wheat"},
            "states": {"wheat": {"up": "Uttar Pradesh"}},
            "dists": {"wheat": {"up": {"hardoi": "Hardoi"}}},
            "dates": {"wheat": {"up": {"hardoi": "2026-08-05"}}}})
        monkeypatch.setattr(bhav, "_index_ts", float("inf"))
        monkeypatch.setattr(bhav, "_kharidar_places", lambda: set())
        monkeypatch.setattr(bhav, "_bazar_slice", lambda *a, **k: [])
        monkeypatch.setattr(bhav, "_sell_intent", lambda *a, **k: 0)

    @pytest.mark.parametrize("url", ["/bhav/wheat/up",
                                     "/bhav/wheat/up/hardoi/kharidar"])
    def test_card_shows_price_mrp_discount_and_pack(self, clean, listed, client,
                                                     monkeypatch, url):
        self._add(client, listed.slug)
        self._bhav(monkeypatch)
        buyers.invalidate()

        body = client.get(url).text
        assert "गेहूं बीज HD-2967" in body
        assert "Wheat Seeds HD-2967" in body
        assert "₹280" in body
        assert "₹350" in body, "MRP is not struck through"
        assert "20% off" in body
        assert "5 kg बैग" in body

    def test_no_mrp_means_no_discount_pill(self, clean, listed, client, monkeypatch):
        self._add(client, listed.slug, name_hi="यूरिया", mrp=None)
        self._bhav(monkeypatch)
        buyers.invalidate()
        # Scoped to the dealer panel, not the whole page: the दुकान promo now
        # renders under the MSP card on every tier, and its hard-coded sample
        # card carries a "20% off" pill of its own.
        assert "% off" not in _dealer_panel(client.get("/bhav/wheat/up").text)

    def test_products_never_render_for_an_unpaid_dealer(self, clean, listed, client,
                                                         monkeypatch):
        """The catalogue is what he is paying for.

        A deliberately odd product name: the dealer PROMO that renders in his
        place carries a sample card, and its demo product is the same
        "गेहूं बीज HD-2967" from the design reference — so the default name
        would be found on the page whether or not his real one rendered.
        """
        unique = "ZZ-टेस्ट-प्रोडक्ट-9931"
        self._add(client, listed.slug, name_hi=unique)
        row = clean.query(dealers.Buyer).filter_by(slug=listed.slug).one()
        row.paid_until = datetime.utcnow() - timedelta(days=1)
        clean.commit()
        buyers.invalidate()
        self._bhav(monkeypatch)
        assert unique not in client.get("/bhav/wheat/up").text

    def test_a_dealer_with_no_products_renders_as_before(self, clean, listed,
                                                          client, monkeypatch):
        self._bhav(monkeypatch)
        body = client.get("/bhav/wheat/up").text
        assert "Sharma Traders" in body
        assert 'class="dp-card"' not in body

    # ── the photo ──

    def test_image_uploads_and_serves_as_webp(self, clean, listed, client):
        pid = self._add(client, listed.slug).json()["product"]["id"]
        up = client.post(f"/admin/products/{pid}/image", auth=ADMIN,
                         files={"file": ("x.png", self._png(), "image/png")})
        assert up.status_code == 200, up.text

        got = client.get(f"/dukanlisting/product-image/{pid}.webp")
        assert got.status_code == 200
        assert got.headers["content-type"] == "image/webp"
        assert got.content[:4] == b"RIFF"
        assert "max-age" in got.headers.get("cache-control", "")

    def test_image_keeps_its_aspect_ratio(self, clean, listed, client):
        """`contain`, not a centre-crop: a product shot is a bag or a bottle and
        cropping it square cuts the label off."""
        import io

        from PIL import Image
        pid = self._add(client, listed.slug).json()["product"]["id"]
        client.post(f"/admin/products/{pid}/image", auth=ADMIN,
                    files={"file": ("x.png", self._png((600, 400)), "image/png")})
        w, h = Image.open(io.BytesIO(
            client.get(f"/dukanlisting/product-image/{pid}.webp").content)).size
        assert w > h, "a landscape pack shot came back square — it was cropped"
        assert max(w, h) <= 480

    def test_image_is_never_inlined_into_the_page(self, clean, listed, client,
                                                  monkeypatch):
        """~15KB of base64 per product, on the site's highest-traffic pages."""
        pid = self._add(client, listed.slug).json()["product"]["id"]
        client.post(f"/admin/products/{pid}/image", auth=ADMIN,
                    files={"file": ("x.png", self._png(), "image/png")})
        self._bhav(monkeypatch)
        buyers.invalidate()

        body = client.get("/bhav/wheat/up").text
        assert f"/dukanlisting/product-image/{pid}.webp" in body
        assert "data:image/webp" not in body

    def test_public_payload_has_no_blob(self, clean, listed, client):
        pid = self._add(client, listed.slug).json()["product"]["id"]
        client.post(f"/admin/products/{pid}/image", auth=ADMIN,
                    files={"file": ("x.png", self._png(), "image/png")})
        buyers.invalidate()
        product = buyers.for_place("wheat", "Uttar Pradesh", "Hardoi")[0]["products"][0]
        assert product["has_image"] is True
        assert "image_data" not in product

    def test_missing_image_is_404(self, clean, listed, client):
        pid = self._add(client, listed.slug).json()["product"]["id"]
        assert client.get(f"/dukanlisting/product-image/{pid}.webp").status_code == 404
        assert client.get("/dukanlisting/product-image/999999.webp").status_code == 404

    def test_garbage_upload_is_rejected(self, clean, listed, client):
        pid = self._add(client, listed.slug).json()["product"]["id"]
        r = client.post(f"/admin/products/{pid}/image", auth=ADMIN,
                        files={"file": ("x.png", b"not an image", "image/png")})
        assert r.status_code == 400

    def test_removing_the_image_clears_both_columns(self, clean, listed, client):
        pid = self._add(client, listed.slug).json()["product"]["id"]
        client.post(f"/admin/products/{pid}/image", auth=ADMIN,
                    files={"file": ("x.png", self._png(), "image/png")})
        assert client.delete(f"/admin/products/{pid}/image",
                             auth=ADMIN).status_code == 200
        assert client.get(f"/dukanlisting/product-image/{pid}.webp").status_code == 404

    # ── ownership + limits ──

    def test_catalogue_follows_the_account_across_districts(self, clean, listed, client):
        """A dealer paying for three districts types his catalogue once."""
        from backend.services import dealer_products

        second = dealers.create(clean, {
            "name": "Sharma Traders", "district": "Sitapur", "state": "Uttar Pradesh",
            "phone": "9876543210", "owner_user_id": self.OTHER_OWNER}, source="signup")
        self._add(client, listed.slug)
        assert len(dealer_products.for_buyer(clean, second.slug, second.owner_user_id)) == 1

    def test_admin_endpoints_require_auth(self, clean, listed, client):
        assert client.get(f"/admin/buyers/{listed.slug}/products").status_code == 401
        assert client.post(f"/admin/buyers/{listed.slug}/products",
                           json={}).status_code == 401
        assert client.post("/admin/products/1/image").status_code == 401

    def test_dealer_manages_only_his_own(self, clean, listed, dealer_user, client):
        """dealer_products.delete() is also the admin's tool, so ownership is
        checked in the route rather than in the service."""
        _user, headers = dealer_user
        pid = self._add(client, listed.slug).json()["product"]["id"]
        assert client.delete(f"/dukanlisting/products/{pid}",
                             headers=headers).status_code == 404

    def test_a_dealer_can_add_and_drop_his_own(self, clean, dealer_user, client):
        user, headers = dealer_user
        _listings(client, headers)
        r = client.post("/dukanlisting/products", headers=headers, json={
            "name_hi": "यूरिया", "price": 266, "unit_hi": "45 kg बैग"})
        assert r.status_code == 200, r.text
        pid = r.json()["data"]["id"]
        assert client.get("/dukanlisting/products", headers=headers).json()["data"]["products"]
        assert client.delete(f"/dukanlisting/products/{pid}", headers=headers).status_code == 200

    def test_product_endpoints_reject_anonymous(self, clean, client):
        assert client.get("/dukanlisting/products").status_code in (401, 403)
        assert client.post("/dukanlisting/products", json={}).status_code in (401, 403)

    def test_catalogue_is_capped(self, clean, listed, client):
        from backend.services import dealer_products
        for i in range(dealer_products.MAX_PER_DEALER):
            assert self._add(client, listed.slug,
                             name_hi=f"item {i}").status_code == 200
        assert self._add(client, listed.slug, name_hi="one too many").status_code == 400



class TestTier3PanelRendering:
    """What a farmer actually sees on /bhav/{crop}/{state}.

    The panel withholds the phone number on purpose: a farmer who wants to ring
    the dealer has to click through to the /kharidar page, which is still on
    krashimitra.in. Asserting the *absence* of the number is the point — if it
    ever leaks in here the feature still looks like it works.
    """

    @pytest.fixture()
    def rendered(self, clean, monkeypatch):
        from backend.routes import bhav

        monkeypatch.setattr(bhav, "_index", {
            "crops":  {"wheat": "Wheat"},
            "states": {"wheat": {"up": "Uttar Pradesh"}},
            "dists":  {"wheat": {"up": {"hardoi": "Hardoi", "sitapur": "Sitapur"}}},
            "dates":  {"wheat": {"up": {"hardoi": "2026-07-30",
                                        "sitapur": "2026-07-30"}}},
        })
        monkeypatch.setattr(bhav, "_index_ts", float("inf"))
        monkeypatch.setattr(bhav, "_kharidar_places", lambda: set())

        def _live(name, district, phone, rank=None, commodities=("wheat",)):
            row = dealers.create(clean, {
                "name": name, "district": district, "state": "Uttar Pradesh",
                "phone": phone, "commodities": list(commodities),
                "owner_user_id": abs(hash(name)) % 10000}, source="signup")
            dealers.approve(clean, row.slug)
            dealers.record_payment(clean, row.slug, 199)
            if rank:
                dealers.set_bhav_rank(clean, row.slug, rank)
            buyers.invalidate()
            return row

        return _live

    def test_panel_is_absent_until_a_dealer_is_ranked(self, rendered, client):
        rendered("Sharma Traders", "Hardoi", "9876543210")     # paid, but no rank
        body = client.get("/bhav/wheat/up").text
        assert "सत्यापित दुकानें" not in body
        assert "Sharma Traders" not in body

    def test_ranked_dealer_shows_name_but_never_the_number(self, rendered, client):
        rendered("Sharma Traders", "Hardoi", "9876543210", rank=1)
        body = client.get("/bhav/wheat/up").text

        assert "Sharma Traders" in body, "the paid dealer never rendered"
        assert "सत्यापित दुकानें" in body
        assert "9876543210" not in body, (
            "the phone number leaked onto the state page — a farmer can now ring "
            "the dealer without ever passing through krashimitra.in")
        assert "tel:9876543210" not in body
        assert "wa.me/919876543210" not in body

    def test_panel_links_through_to_the_kharidar_page(self, rendered, client):
        """Where the number legitimately lives, still on our own site."""
        rendered("Sharma Traders", "Hardoi", "9876543210", rank=1)
        body = client.get("/bhav/wheat/up").text
        assert "/bhav/wheat/up/hardoi/kharidar" in body

    def test_panel_pitches_the_signup_to_other_dealers(self, rendered, client):
        rendered("Sharma Traders", "Hardoi", "9876543210", rank=1)
        assert "/dukanlisting" in client.get("/bhav/wheat/up").text

    def test_tier4_district_page_carries_no_panel(self, rendered, client):
        """The panel is a Tier-3 (crop+state) surface only."""
        rendered("Sharma Traders", "Hardoi", "9876543210", rank=1)
        body = client.get("/bhav/wheat/up/hardoi").text
        assert "सत्यापित दुकानें" not in body

    def test_lapsed_dealer_vanishes_from_the_panel(self, clean, rendered, client):
        row = rendered("Sharma Traders", "Hardoi", "9876543210", rank=1)
        live = clean.query(dealers.Buyer).filter_by(slug=row.slug).one()
        live.paid_until = datetime.utcnow() - timedelta(days=1)
        clean.commit()
        buyers.invalidate()
        assert "Sharma Traders" not in client.get("/bhav/wheat/up").text


class TestBazarPostSync:
    """A paying, verified dealer also shows up in the krashi_bajar feed — created
    and retired automatically, never by an admin remembering to."""

    def _account(self, clean, dealer_user, client):
        user, headers = dealer_user
        _listings(client, headers)
        return user, dealers.for_owner(clean, user.id)[0]

    def _post(self, clean, user_id):
        from backend.database.db import BazarPost
        return (clean.query(BazarPost)
                .filter(BazarPost.user_id == user_id, BazarPost.source == "dukan")
                .first())

    def test_no_post_before_the_dealer_is_live(self, clean, dealer_user, client):
        user, _row = self._account(clean, dealer_user, client)
        assert self._post(clean, user.id) is None

    def test_post_appears_once_verified_and_paid(self, clean, dealer_user, client):
        user, row = self._account(clean, dealer_user, client)
        dealers.approve(clean, row.slug)
        dealers.record_payment(clean, row.slug, 199)
        post = self._post(clean, user.id)
        assert post is not None and post.status == "active"
        assert post.post_type == "buy"
        assert "Sharma Traders" in post.text

    def test_post_closes_when_the_subscription_lapses(self, clean, dealer_user, client):
        user, row = self._account(clean, dealer_user, client)
        dealers.approve(clean, row.slug)
        dealers.record_payment(clean, row.slug, 199)
        live = clean.query(dealers.Buyer).filter_by(slug=row.slug).one()
        live.paid_until = datetime.utcnow() - timedelta(days=1)
        clean.commit()
        dealers.update(clean, row.slug, {})     # any eligibility-touching write
        assert self._post(clean, user.id).status == "closed"

    def test_only_one_post_per_account(self, clean, dealer_user, client):
        """Renewing must refresh the existing post, not stack up a new one every
        month until the feed is nothing but one dealer."""
        from backend.database.db import BazarPost

        user, row = self._account(clean, dealer_user, client)
        dealers.approve(clean, row.slug)
        dealers.record_payment(clean, row.slug, 199)
        dealers.record_payment(clean, row.slug, 199)
        dealers.update(clean, row.slug, {"note": "changed"})
        assert clean.query(BazarPost).filter(
            BazarPost.user_id == user.id, BazarPost.source == "dukan").count() == 1

    def test_legacy_rows_never_get_a_bazar_post(self, clean):
        """There is no users.id behind an admin-typed row to author one as."""
        from backend.database.db import BazarPost

        row = dealers.create(clean, {"name": "Verma Aadhat", "district": "Hardoi",
                                     "state": "Uttar Pradesh", "phone": "9998887770"})
        dealers.record_payment(clean, row.slug, 500)
        assert clean.query(BazarPost).filter(BazarPost.source == "dukan").count() == 0

    # ── whose name is on the card ──
    #
    # The post is authored under the dealer's personal login, because that is
    # the only users.id there is. Signed with his profile name it read as a
    # private person advertising a business — and it is the shop name he pays
    # to put in front of farmers, not his own.

    def _live(self, clean, dealer_user, client):
        user, row = self._account(clean, dealer_user, client)
        dealers.approve(clean, row.slug)
        dealers.record_payment(clean, row.slug, 199)
        return user

    def test_feed_signs_the_post_with_the_shop_name(self, clean, dealer_user, client):
        user = self._live(clean, dealer_user, client)
        posts = client.get("/bazar/feed").json()["data"]["posts"]
        mine = [p for p in posts if p["author"]["user_id"] == user.id]
        assert mine, "the dealer's post is missing from the feed entirely"
        assert mine[0]["author"]["name"] == "Sharma Traders"

    def test_the_card_still_points_at_the_real_account(self, clean, dealer_user, client):
        """Only the displayed name changes. Follow must still follow the person,
        and tapping through must still open a real profile — a shopfront name
        over a dead user_id would be a listing nobody can reach."""
        user = self._live(clean, dealer_user, client)
        posts = client.get("/bazar/feed").json()["data"]["posts"]
        mine = [p for p in posts if p["author"]["user_id"] == user.id][0]
        assert mine["author"]["user_id"] == user.id

    def test_the_profile_keeps_the_real_name(self, clean, dealer_user, client):
        """The profile card's whole job is saying who the account actually is.

        Checked on the name fields, not on the whole payload: the post TEXT
        legitimately contains the firm's name — _sync_bazar_post writes it
        there — and that is the dealer advertising, not the card mislabelling
        the account.
        """
        user = self._live(clean, dealer_user, client)
        body = client.get(f"/bazar/users/{user.id}").json()["data"]
        assert body["name"] != "Sharma Traders", "shopfront name on the profile"
        for post in body["recent_posts"]:
            assert post["author"]["name"] != "Sharma Traders"

    def test_a_farmers_own_post_is_never_renamed(self, clean, dealer_user, client):
        """The rename keys off source == "dukan", not off "this user happens to
        own a shop" — a dealer who also sells his own crop posts as himself."""
        from backend.database.db import BazarPost

        user = self._live(clean, dealer_user, client)
        clean.add(BazarPost(user_id=user.id, post_type="sell", status="active",
                            text="मेरा अपना गेहूं बिकाऊ है"))
        clean.commit()
        posts = client.get("/bazar/feed").json()["data"]["posts"]
        own = [p for p in posts if p["post_type"] == "sell"]
        assert own, "the farmer-side post was not created"
        assert own[0]["author"]["name"] != "Sharma Traders"


class TestApprovalPutsItLive:
    """The other direction: after the call and the payment, it has to appear."""

    def _paid_slug(self, clean, dealer_user, client):
        user, headers = dealer_user
        _listings(client, headers)
        slug = dealers.for_owner(clean, user.id)[0].slug
        dealers.record_payment(clean, slug, 199)
        return slug

    def test_approve_makes_it_visible(self, clean, dealer_user, client):
        slug = self._paid_slug(clean, dealer_user, client)
        dealers.approve(clean, slug)
        buyers.invalidate()
        rows = buyers.for_place("wheat", "Uttar Pradesh", "Hardoi")
        assert [b["name"] for b in rows] == ["Sharma Traders"]
        assert rows[0]["verified"] is True

    def test_approved_dealer_opens_the_district_gate(self, clean, dealer_user, client):
        """Same gate the sitemap and the noindex flag both read."""
        from backend.routes import bhav

        slug = self._paid_slug(clean, dealer_user, client)
        buyers.invalidate()
        assert bhav._has_kharidar("wheat", "Uttar Pradesh", "Hardoi") is False
        dealers.approve(clean, slug)
        buyers.invalidate()
        assert bhav._has_kharidar("wheat", "Uttar Pradesh", "Hardoi") is True

    def test_edit_takes_effect_without_waiting_out_the_cache(self, clean, dealer_user, client):
        """The panel exists to be used while standing in front of the dealer."""
        slug = self._paid_slug(clean, dealer_user, client)
        dealers.approve(clean, slug)
        dealers.update(clean, slug, {"name": "Sharma Brothers"})
        assert buyers.for_place("wheat", "Uttar Pradesh", "Hardoi")[0]["name"] \
            == "Sharma Brothers"

    def test_delete_removes_it_from_the_directory(self, clean, dealer_user, client):
        slug = self._paid_slug(clean, dealer_user, client)
        dealers.approve(clean, slug)
        assert dealers.delete(clean, slug) is True
        assert buyers.for_place("wheat", "Uttar Pradesh", "Hardoi") == []


class TestAdminSurface:
    def test_listing_requires_auth(self, clean, client):
        assert client.get("/admin/buyers").status_code == 401

    def test_write_requires_auth(self, clean, client):
        response = client.post("/admin/buyers", json={"name": "X", "district": "Y",
                                                      "phone": "9876543210"})
        assert response.status_code == 401

    def test_admin_sees_the_pending_queue_farmers_cannot(self, dealer_user, client):
        _user, headers = dealer_user
        _listings(client, headers)
        body = client.get("/admin/buyers", auth=ADMIN).json()
        assert [b["name"] for b in body["buyers"]] == ["Sharma Traders"]
        assert body["counts"]["pending"] == 1
        assert body["counts"]["live"] == 0

    def test_admin_listing_carries_the_account_id(self, dealer_user, client):
        """The panel groups a dealer's districts by it."""
        user, headers = dealer_user
        _listings(client, headers)
        body = client.get("/admin/buyers", auth=ADMIN).json()
        assert body["buyers"][0]["owner_user_id"] == user.id

    def test_admin_created_dealer_is_live_immediately(self, clean, client):
        """The owner adds it *because* he just spoke to the dealer."""
        response = client.post("/admin/buyers", auth=ADMIN, json={
            "name": "Verma Aadhat", "district": "Hardoi", "state": "Uttar Pradesh",
            "phone": "9998887770", "commodities": ["wheat"]})
        assert response.status_code == 200, response.text
        assert [b["name"] for b in buyers.for_place("wheat", "Uttar Pradesh", "Hardoi")] \
            == ["Verma Aadhat"]

    def test_approve_over_http(self, dealer_user, client):
        _user, headers = dealer_user
        _listings(client, headers)
        slug = client.get("/admin/buyers", auth=ADMIN).json()["buyers"][0]["slug"]
        response = client.patch(f"/admin/buyers/{slug}", auth=ADMIN,
                                json={"active": True, "verified": True})
        assert response.status_code == 200, response.text
        assert response.json()["counts"]["live"] == 1

    def test_set_rank_over_http(self, clean, dealer_user, client):
        user, headers = dealer_user
        _listings(client, headers)
        slug = dealers.for_owner(clean, user.id)[0].slug
        response = client.patch(f"/admin/buyers/{slug}/rank", auth=ADMIN,
                                json={"rank": 2})
        assert response.status_code == 200, response.text
        assert response.json()["bhav_rank"] == 2

    @pytest.mark.parametrize("bad", [4, -1, "x"])
    def test_rank_rejects_values_outside_the_three_slots(self, clean, dealer_user,
                                                          client, bad):
        """There are exactly three slots. Junk must 404, not 500 — the panel
        sends this straight from a <select> and a typo is not a server fault."""
        user, headers = dealer_user
        _listings(client, headers)
        slug = dealers.for_owner(clean, user.id)[0].slug
        response = client.patch(f"/admin/buyers/{slug}/rank", auth=ADMIN,
                                json={"rank": bad})
        assert response.status_code == 404, response.text

    @pytest.mark.parametrize("empty", [0, "", None])
    def test_falsy_rank_clears_the_slot(self, clean, dealer_user, client, empty):
        """The panel's "—" option, whichever way the browser serialises it."""
        user, headers = dealer_user
        _listings(client, headers)
        slug = dealers.for_owner(clean, user.id)[0].slug
        client.patch(f"/admin/buyers/{slug}/rank", auth=ADMIN, json={"rank": 2})
        response = client.patch(f"/admin/buyers/{slug}/rank", auth=ADMIN,
                                json={"rank": empty})
        assert response.status_code == 200, response.text
        assert response.json()["bhav_rank"] is None

    def test_unknown_slug_is_404(self, clean, client):
        assert client.patch("/admin/buyers/nope", auth=ADMIN,
                            json={"active": True}).status_code == 404
        assert client.delete("/admin/buyers/nope", auth=ADMIN).status_code == 404


class TestSeedFileIsNeverWritten:
    """Why the table exists. A write here reverts on the next dyno restart."""

    def test_admin_create_does_not_touch_buyers_json(self, clean, client, repo_root):
        path = repo_root / "backend" / "data" / "buyers.json"
        before = path.read_bytes()
        client.post("/admin/buyers", auth=ADMIN, json={
            "name": "Disk Test", "district": "Hardoi", "phone": "9876500000"})
        assert path.read_bytes() == before, (
            "admin wrote to the JSON seed — on Render's free plan (no persistent "
            "disk) that dealer is lost on the next restart")

    def test_seed_file_still_parses_and_keeps_its_documentation(self, repo_root):
        """The seed is committed and hand-read; the note is load-bearing."""
        data = json.loads((repo_root / "backend" / "data" / "buyers.json")
                          .read_text(encoding="utf-8"))
        assert "_note" in data
        assert isinstance(data.get("buyers"), list)


class TestSeedAndTableMerge:
    def test_db_row_overrides_a_seed_row_with_the_same_slug(self, clean, tmp_path,
                                                            monkeypatch):
        """So a committed listing can be corrected from the panel, no deploy."""
        seed = tmp_path / "buyers.json"
        seed.write_text(json.dumps({"buyers": [{
            "id": "seeded-one", "active": True, "name": "Old Name",
            "state": "Uttar Pradesh", "district": "Hardoi",
            "commodities": [], "phone": "9000000000"}]}), encoding="utf-8")
        monkeypatch.setattr(buyers, "_PATH", seed)
        monkeypatch.setattr(buyers, "_cache", None)
        monkeypatch.setattr(buyers, "_mtime", -1.0)

        assert buyers.for_place("wheat", "Uttar Pradesh", "Hardoi")[0]["name"] == "Old Name"

        row = dealers.create(clean, {"name": "Corrected Name", "district": "Hardoi",
                                     "state": "Uttar Pradesh", "phone": "9000000000"})
        row.slug = "seeded-one"
        clean.commit()
        buyers.invalidate()
        monkeypatch.setattr(buyers, "_cache", None)   # force the merge to rerun

        names = [b["name"] for b in buyers.for_place("wheat", "Uttar Pradesh", "Hardoi")]
        assert names == ["Corrected Name"], f"seed override failed: {names}"

    def test_directory_survives_a_dead_database(self, clean, tmp_path, monkeypatch):
        """A kharidar page must render off the seed while Neon is asleep."""
        seed = tmp_path / "buyers.json"
        seed.write_text(json.dumps({"buyers": [{
            "id": "seeded-one", "active": True, "name": "Seed Trader",
            "state": "Uttar Pradesh", "district": "Hardoi",
            "commodities": [], "phone": "9000000000"}]}), encoding="utf-8")
        monkeypatch.setattr(buyers, "_PATH", seed)
        monkeypatch.setattr(buyers, "_cache", None)
        monkeypatch.setattr(buyers, "_mtime", -1.0)

        def _dead(*a, **k):
            raise RuntimeError("could not connect to server")

        monkeypatch.setattr("backend.database.db.SessionLocal", _dead)
        buyers.invalidate()

        assert [b["name"] for b in buyers.for_place("wheat", "Uttar Pradesh", "Hardoi")] \
            == ["Seed Trader"]


class TestSlugs:
    """The slug is permanent: LeadClick quotes it, so a rename must not orphan
    the click history. That makes it worth being readable at creation time."""

    def test_hindi_names_do_not_all_collapse_to_one_slug(self, clean):
        """The regression this exists to prevent — an ASCII-only slugify drops
        every Devanagari character, so every Hindi firm becomes dealer-<dist>-N."""
        a = dealers.create(clean, {"name": "शर्मा ट्रेडर्स", "district": "Hardoi",
                                   "phone": "9876543210"})
        b = dealers.create(clean, {"name": "गुप्ता आढ़तिया", "district": "Hardoi",
                                   "phone": "9876543211"})
        assert a.slug != b.slug
        assert not a.slug.startswith("dealer-"), a.slug
        assert "shrma" in a.slug and "hardoi" in a.slug, a.slug

    def test_collisions_still_get_a_counter(self, clean):
        first = dealers.create(clean, {"name": "Sharma Traders", "district": "Hardoi",
                                       "phone": "9876543210"})
        second = dealers.create(clean, {"name": "Sharma Traders", "district": "Hardoi",
                                        "phone": "9876543211"})
        assert first.slug == "sharma-traders-hardoi"
        assert second.slug == "sharma-traders-hardoi-2"

    def test_slug_is_url_safe(self, clean):
        row = dealers.create(clean, {"name": "मेसर्स राज कुमार & Sons (Pvt.)",
                                     "district": "Sri Ganganagar", "phone": "9876543210"})
        assert all(ch.isalnum() or ch == "-" for ch in row.slug)
        assert "--" not in row.slug
        assert not row.slug.startswith("-") and not row.slug.endswith("-")

    def test_rename_keeps_the_slug(self, clean):
        """Otherwise the dealer's lead_clicks history detaches on a typo fix."""
        row = dealers.create(clean, {"name": "Old Firm", "district": "Hardoi",
                                     "phone": "9876543210"})
        before = row.slug
        dealers.update(clean, before, {"name": "New Firm"})
        assert clean.query(dealers.Buyer).filter_by(slug=before).one().name == "New Firm"


class TestPhoneNormalisation:
    @pytest.mark.parametrize("raw, expected", [
        ("9876543210", "9876543210"),
        ("+91 98765 43210", "9876543210"),
        ("098765-43210", "9876543210"),
        ("91 9876543210", "9876543210"),
        ("12345", ""),              # too short
        ("1234567890", ""),         # Indian mobiles do not start with 1
        ("", ""),
    ])
    def test_clean_phone(self, raw, expected):
        assert dealers.clean_phone(raw) == expected

    def test_signup_without_a_reachable_number_is_rejected(self, dealer_user, client):
        """The whole value of a queued row is being able to ring it back."""
        _user, headers = dealer_user
        response = _listings(client, headers, phone="12345", whatsapp="")
        assert response.status_code == 400

    def test_signup_without_a_name_is_rejected(self, dealer_user, client):
        _user, headers = dealer_user
        assert _listings(client, headers, name="").status_code == 400
