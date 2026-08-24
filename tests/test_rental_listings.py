"""The /rental listing system: the term, the expiry, and the two hire terms.

This mirrors test_dukan_plan_validity.py because /rental sells the same thing
on the same call, and the two claims made to a machine owner on the phone are
the same two:

* **"आप जितने महीने का लेंगे, उतने का ही चलेगा."** The term is per owner,
  agreed on the call, and every renewal extends by exactly that.
* **"पैसा नहीं आया तो लिस्टिंग हट जाएगी."** Not "greys out", not "drops down
  the list" — the rows stop being rendered anywhere a farmer can reach.

The second is the one that fails silently, so the expiry is asserted through
the reads the public pages actually run on, never through `is_live` alone.

There is a THIRD claim here that कृषि दुकान has no equivalent of, and it is
asserted just as hard: a /rental page must keep working when nobody is listed.
Unlike a dukan product page, whose whole content is the shop rows, an
equipment page still answers "what should this cost, what should I check" and
still routes the farmer to a government CHC. A lapse must empty the owner list
WITHOUT emptying the page — and must take the Offer schema with it, because an
editorial estimate marked up as an offer is a false claim.
"""

from datetime import datetime, timedelta

import pytest

from backend.database.db import RentalListing, RentalProvider
from backend.services import rental


EQUIP = "tractor"          # a slug the JSON registry is asserted to carry


@pytest.fixture()
def owner(db_session):
    """One live owner with one priced machine."""
    stamp = datetime.utcnow().strftime("%H%M%S%f")
    slug = f"test-rental-{stamp}"

    row = RentalProvider(slug=slug, name="Test Tractor Service", district="Bareilly",
                         state="Uttar Pradesh", phone="9870951001", kind="owner",
                         plan="season", plan_months=3, active=True)
    db_session.add(row)
    db_session.add(RentalListing(provider_slug=slug, equipment_slug=EQUIP,
                                 rate=650, rate_unit_hi="प्रति घंटा",
                                 with_operator=True, fuel_included=False,
                                 active=True, available=True))
    db_session.commit()
    yield row

    # Several tests set attributes on `row` without committing, to describe a
    # clock state. Dropping those first stops the teardown flushing an UPDATE
    # for a row it is about to delete.
    db_session.rollback()
    db_session.query(RentalListing).filter(RentalListing.provider_slug == slug).delete()
    db_session.query(RentalProvider).filter(RentalProvider.slug == slug).delete()
    db_session.commit()


def _visible(db, provider_slug) -> bool:
    """Is this owner reachable by a farmer, through either read path?"""
    on_equipment = any(o["provider_slug"] == provider_slug
                       for o in rental.offers_for_equipment(db, EQUIP))
    on_hub = rental.listed_equipment(db).get(EQUIP, {}).get("providers", 0) > 0
    # With one owner in the fixture the two must agree. Disagreeing means one
    # read path forgot the gate — exactly the bug this file exists to catch.
    assert on_equipment == on_hub, "the equipment page and the hub disagree"
    return on_equipment


# ── the term ────────────────────────────────────────────────

def test_the_registry_has_the_slug_these_tests_hang_off():
    """A guard on the fixture itself: if `tractor` is ever renamed in the JSON,
    every assertion below would pass vacuously against an empty offer list."""
    assert rental.by_slug(EQUIP), f"{EQUIP} is no longer in rental_equipment.json"


def test_payment_extends_by_the_owners_own_term_not_a_constant(db_session, owner):
    """"आप जितने महीने का लेंगे" — 6 months means 6, not the 3-month default."""
    owner.plan_months = 6
    db_session.commit()
    rental.record_payment(db_session, owner.slug, 500)
    assert 175 <= rental.days_left(owner) <= 185


def test_a_per_payment_override_does_not_change_the_standing_term(db_session, owner):
    """A free month to close a haggle is one payment, not a new contract."""
    rental.record_payment(db_session, owner.slug, 200, months=1)
    assert 25 <= rental.days_left(owner) <= 35
    assert rental.plan_months_of(owner) == 3, "the agreed term was overwritten"


def test_renewing_early_adds_a_season_instead_of_discarding_days(db_session, owner):
    rental.record_payment(db_session, owner.slug, 500)
    first = owner.paid_until
    rental.record_payment(db_session, owner.slug, 500)
    # Extended from the existing expiry, not from today.
    assert owner.paid_until > first + timedelta(days=80)


def test_a_lapsed_owner_restarts_from_today_not_from_the_gap(db_session, owner):
    owner.paid_until = datetime.utcnow() - timedelta(days=40)
    db_session.commit()
    rental.record_payment(db_session, owner.slug, 500)
    # Backdating into the dark period would sell days already lost.
    assert rental.days_left(owner) >= 85


def test_clean_months_clamps_rather_than_rejecting(db_session):
    """A 0 would list an owner who is dark the moment he pays."""
    assert rental.clean_months(0) == rental.MIN_PLAN_MONTHS
    assert rental.clean_months(99) == rental.MAX_PLAN_MONTHS
    assert rental.clean_months("") == rental.SEASON_MONTHS
    assert rental.clean_months("6") == 6


# ── the expiry, through the public read paths ───────────────

def test_an_owner_who_never_paid_stays_visible(db_session, owner):
    """The onboarding grace: an empty directory is worth less than an unbilled
    listing, and there is nothing to show an owner on a phone otherwise."""
    assert owner.paid_until is None
    assert rental.days_left(owner) is None, "a clock is running that should not be"
    assert _visible(db_session, owner.slug)


def test_an_expired_owner_disappears_from_every_read(db_session, owner):
    """"पैसा नहीं आया तो लिस्टिंग हट जाएगी" — asserted through the reads the
    pages actually run, not through is_live()."""
    rental.record_payment(db_session, owner.slug, 500)
    assert _visible(db_session, owner.slug)

    owner.paid_until = datetime.utcnow() - timedelta(seconds=1)
    db_session.commit()
    assert not _visible(db_session, owner.slug)
    assert rental.is_lapsed(owner)


def test_deactivating_hides_the_owner_immediately(db_session, owner):
    owner.active = False
    db_session.commit()
    assert not _visible(db_session, owner.slug)


def test_days_left_rounds_down_so_it_never_promises_time_that_is_not_there(db_session, owner):
    owner.paid_until = datetime.utcnow() + timedelta(hours=11)
    db_session.commit()
    # Rounding up would print "1 दिन बाकी" on a listing that dies before the
    # owner picks up the phone.
    assert rental.days_left(owner) == 0
    assert rental.expiring_soon(owner)


def test_a_lapsed_owner_is_not_also_reported_as_expiring(db_session, owner):
    """Two warnings about one owner read as two problems. After the expiry
    there is nothing left to save, only to win back."""
    owner.paid_until = datetime.utcnow() - timedelta(days=3)
    db_session.commit()
    assert rental.is_lapsed(owner)
    assert not rental.expiring_soon(owner)


# ── the page survives having no supply ──────────────────────

def test_the_equipment_page_still_serves_when_every_owner_lapses(db_session, owner, client):
    """The claim /krashi_dukan cannot make. An equipment page's editorial half
    — the rate range, the checklist, the CHC route — is the reason the page
    exists, so losing all supply must cost the owner rows and nothing else."""
    rental.record_payment(db_session, owner.slug, 500)
    live = client.get(f"/rental/{EQUIP}")
    assert live.status_code == 200
    assert 'class="rent-owner"' in live.text
    assert "AggregateOffer" in live.text

    owner.paid_until = datetime.utcnow() - timedelta(seconds=1)
    db_session.commit()

    dark = client.get(f"/rental/{EQUIP}")
    assert dark.status_code == 200, "the page died with its listings"
    assert 'class="rent-owner"' not in dark.text
    # An estimate marked up as an offer is a false claim in structured data.
    assert "AggregateOffer" not in dark.text
    # The editorial half must be untouched.
    assert "क्या जाँचें" in dark.text
    assert "कस्टम हायरिंग सेंटर" in dark.text
    assert "noindex" not in dark.text, "the page must stay indexable without supply"


def test_the_owner_page_is_noindex_in_every_state(db_session, owner, client):
    """Every (machine × owner) pair is a near-duplicate URL. On a site where
    72% of impressions already sit at positions 4-10, these must never enter
    the index — but `follow` keeps the links out of them alive."""
    r = client.get(f"/rental/{EQUIP}/{owner.slug}")
    assert r.status_code == 200
    assert "noindex,follow" in r.text


def test_a_lapsed_owners_page_404s_rather_than_showing_a_stale_rate(db_session, owner, client):
    owner.paid_until = datetime.utcnow() - timedelta(seconds=1)
    db_session.commit()
    assert client.get(f"/rental/{EQUIP}/{owner.slug}").status_code == 404


# ── the two terms every hire argument is about ──────────────

def test_a_rate_without_a_unit_is_rejected(db_session):
    """"₹1800" is a different deal per hour than per acre. A unitless rate is
    unusable to the farmer and incomparable against every other row."""
    assert rental.validate_listing({"equipment_slug": EQUIP, "rate": 1800})
    assert not rental.validate_listing(
        {"equipment_slug": EQUIP, "rate": 1800, "rate_unit_hi": "प्रति एकड़"})


def test_a_listing_cannot_point_at_a_machine_that_is_not_in_the_registry(db_session):
    """The slug is the join to the JSON catalogue — a typo would create a row
    the panel can see and no page can ever render."""
    assert rental.validate_listing(
        {"equipment_slug": "flying-tractor", "rate": 500, "rate_unit_hi": "प्रति घंटा"})


def test_the_fuel_and_operator_terms_reach_the_farmer(db_session, owner, client):
    """The tractor page's own checklist opens with "किराये में डीज़ल शामिल है या
    नहीं — यही सबसे बड़ा झगड़ा है". Storing it as a flag is only worth doing if
    the flag is actually rendered."""
    page = client.get(f"/rental/{EQUIP}").text
    assert "डीज़ल अलग" in page          # fuel_included=False on the fixture
    assert "चालक सहित" in page          # with_operator=True

    row = db_session.query(RentalListing).filter(
        RentalListing.provider_slug == owner.slug).first()
    row.fuel_included = True
    db_session.commit()
    assert "डीज़ल शामिल" in client.get(f"/rental/{EQUIP}").text


def test_one_owner_cannot_quote_the_same_machine_twice(db_session, owner):
    """Two rows from the same yard at different rates reads as a bug to the one
    person the page exists for."""
    again = rental.listing_create(db_session, owner.slug, {
        "equipment_slug": EQUIP, "rate": 900, "rate_unit_hi": "प्रति घंटा"})
    assert again is None, "the duplicate was accepted"


def test_deleting_an_owner_takes_their_listings_with_them(db_session, owner):
    """The join is by slug, not a foreign key — orphaned rows would be
    invisible, uneditable, and still counted."""
    slug = owner.slug
    assert rental.provider_delete(db_session, slug)
    assert db_session.query(RentalListing).filter(
        RentalListing.provider_slug == slug).count() == 0


# ── the ordering rule that cannot bend ──────────────────────

def test_paying_does_not_move_an_owner_up_the_list(db_session, owner):
    """The one rule inherited unchanged from krashi_dukan. A directory whose
    order can be bought stops being worth reading, and the ordering is the only
    thing we actually have to sell."""
    stamp = datetime.utcnow().strftime("%H%M%S%f")
    cheap_slug = f"test-rental-cheap-{stamp}"
    db_session.add(RentalProvider(slug=cheap_slug, name="Cheaper Yard",
                                  district="Bareilly", phone="9870951002",
                                  plan="season", plan_months=3, active=True))
    db_session.add(RentalListing(provider_slug=cheap_slug, equipment_slug=EQUIP,
                                 rate=400, rate_unit_hi="प्रति घंटा", active=True))
    db_session.commit()
    try:
        # The fixture owner pays; the cheaper one never does.
        rental.record_payment(db_session, owner.slug, 5000, months=12)
        order = [o["provider_slug"] for o in rental.offers_for_equipment(db_session, EQUIP)]
        assert order[0] == cheap_slug, "the paying owner was floated to the top"
    finally:
        db_session.rollback()
        db_session.query(RentalListing).filter(
            RentalListing.provider_slug == cheap_slug).delete()
        db_session.query(RentalProvider).filter(
            RentalProvider.slug == cheap_slug).delete()
        db_session.commit()


def test_an_unavailable_machine_sinks_below_the_bookable_ones(db_session, owner):
    """A rate you cannot book is not an offer."""
    stamp = datetime.utcnow().strftime("%H%M%S%f")
    busy_slug = f"test-rental-busy-{stamp}"
    db_session.add(RentalProvider(slug=busy_slug, name="Busy Yard", district="Bareilly",
                                  phone="9870951003", plan="season", plan_months=3,
                                  active=True))
    # Cheaper than the fixture's 650, but not free right now.
    db_session.add(RentalListing(provider_slug=busy_slug, equipment_slug=EQUIP,
                                 rate=300, rate_unit_hi="प्रति घंटा",
                                 active=True, available=False))
    db_session.commit()
    try:
        order = [o["provider_slug"] for o in rental.offers_for_equipment(db_session, EQUIP)]
        assert order[-1] == busy_slug
    finally:
        db_session.rollback()
        db_session.query(RentalListing).filter(
            RentalListing.provider_slug == busy_slug).delete()
        db_session.query(RentalProvider).filter(
            RentalProvider.slug == busy_slug).delete()
        db_session.commit()


def test_the_disclaimer_matches_the_claim_the_page_is_making(db_session, owner, client):
    """A page showing a named owner's firm rate must not call it an estimate.

    Doing so is false, and it teaches the farmer to discount a number that is
    actually firm — which costs the owner the booking and costs us the owner.
    What must survive on every page in both wordings: we do not own the
    machine.
    """
    from backend.routes.rental import DISCLAIMER, DISCLAIMER_LISTED

    # "we are only the connector" is the half that is always true.
    assert "कृषि मित्र मशीन किराये पर नहीं देता" in DISCLAIMER
    assert "कृषि मित्र मशीन किराये पर नहीं देता" in DISCLAIMER_LISTED
    # Only the estimate wording may call the rates estimates.
    assert "अनुमानित" in DISCLAIMER
    assert "अनुमानित" not in DISCLAIMER_LISTED

    listed = client.get(f"/rental/{EQUIP}").text
    assert "मालिक के अपने बताए हुए हैं" in listed, "a listed page called a firm rate an estimate"

    # With no owner left, the estimate wording is the honest one again.
    owner.active = False
    db_session.commit()
    bare = client.get(f"/rental/{EQUIP}").text
    assert "यहाँ दिए किराये अनुमानित हैं" in bare

    # An owner's own page always shows a quoted rate, so it never says estimate.
    owner.active = True
    db_session.commit()
    own = client.get(f"/rental/{EQUIP}/{owner.slug}").text
    assert "मालिक के अपने बताए हुए हैं" in own
