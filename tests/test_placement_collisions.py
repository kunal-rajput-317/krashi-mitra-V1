"""Who wins a slot when two paid plans claim the same page.

Before wildcards there was no such thing as a collision: one sale was one page,
and set_placement() resolved a double-booking by evicting the loser. Once a
single row can cover 1,800 pages that stops working — a national sale would
silently evict every local dealer it overlapped, and neither of them would ever
see it happen.

So resolution moved to render time, and these tests pin the two rules that make
it safe to sell overlapping plans at once:

  * SPECIFICITY WINS. The narrower pattern renders first, so the ₹199 dealer
    keeps the top of his own district page against a ₹12,999 national buyer.
    Without this the small tier is worthless the moment one wide plan sells.

  * BUT THE WIDE PLANS ARE NOT STARVED. Locals may take at most LOCAL_CAP of
    the SLOTS; the rest is reserved for the broadest claimant. That reserve is
    the "हर पेज पर कम से कम एक जगह" promise, and it is the only reason the
    wide tiers are sellable at all.

Every case here is a real invoice, not a hypothetical: each one is two plans
that a farmer would see on one page and that we have taken money for twice.
"""

import pytest

from backend.services import buyers, dealers, placements

W = placements.WILD


@pytest.fixture()
def clean(db_session, monkeypatch):
    from backend.database.db import (BazarPost, Buyer, DealerPlacement,
                                     DealerProduct, User)
    from backend.utils import security

    security._hits.clear()
    for model in (DealerProduct, DealerPlacement, Buyer, BazarPost):
        db_session.query(model).delete()
    db_session.query(User).filter(User.email.like("dealer-test%")).delete()
    db_session.commit()
    buyers.invalidate()
    placements.invalidate()
    monkeypatch.setattr(buyers, "_cache", None)
    monkeypatch.setattr(buyers, "_mtime", -1.0)
    monkeypatch.setattr(buyers, "_place_idx", {})
    yield db_session
    for model in (DealerProduct, DealerPlacement, Buyer, BazarPost):
        db_session.query(model).delete()
    db_session.query(User).filter(User.email.like("dealer-test%")).delete()
    db_session.commit()
    buyers.invalidate()
    placements.invalidate()


def _live(db, name, district="Hardoi", state="UP", owner_user_id=None):
    """A dealer who is live, verified and paid — i.e. eligible everywhere. The
    only thing left deciding where he shows up is this module."""
    row = dealers.create(db, {
        "name": name, "district": district, "state": state,
        "phone": "9876543210", "commodities": ["wheat"],
        "owner_user_id": owner_user_id}, source="signup")
    dealers.approve(db, row.slug)
    dealers.record_payment(db, row.slug, placements.quote(1, 1))
    return row.slug


def _names(crop="wheat", state="up", district="hardoi"):
    buyers.invalidate()
    placements.invalidate()
    return [b["name"] for b in placements.for_page(crop, state, district)]


# ── the ladder, narrowest to widest ─────────────────────────────────────────

class TestSpecificityWins:

    def test_exact_beats_every_wider_plan(self, clean):
        """The ₹199 local buyer outranks all three plans above him on his own
        district page. This is what his money buys, and the sales copy says so
        in as many words — if it ever stops being true the small tier is a lie."""
        local = _live(clean, "Local Traders")
        whole = _live(clean, "District Wide", owner_user_id=2)
        state = _live(clean, "State Wide", owner_user_id=3)
        nation = _live(clean, "National Brand", owner_user_id=4)

        placements.set_placement(clean, nation, "wheat", W, W, 1)
        placements.set_placement(clean, state, "wheat", "up", W, 1)
        placements.set_placement(clean, whole, W, "up", "hardoi", 1)
        placements.set_placement(clean, local, "wheat", "up", "hardoi", 1)

        # local + district-wide take the two local slots; the reserve goes to
        # the narrower of the two broad claims (state, not national).
        assert _names() == ["Local Traders", "District Wide", "State Wide"]

    def test_geography_outranks_crop(self, clean):
        """(*, up, hardoi) beats (wheat, up, *) — both have exactly one
        wildcard, so specificity alone cannot separate them and the tie is
        broken toward place. Farmers search by district, and this is the rule
        that keeps one wide sale from demoting every local dealer it covers."""
        crop_wide = _live(clean, "Wheat Across UP")
        place_wide = _live(clean, "All Crops In Hardoi", owner_user_id=2)
        placements.set_placement(clean, crop_wide, "wheat", "up", W, 1)
        placements.set_placement(clean, place_wide, W, "up", "hardoi", 1)
        assert _names() == ["All Crops In Hardoi", "Wheat Across UP"]

    def test_state_page_is_not_reached_by_the_district_plans(self, clean):
        """/bhav/wheat/uttar-pradesh is its own product. A dealer who bought
        one district must not surface on the state landing page — that is a
        more expensive page and he did not buy it."""
        local = _live(clean, "Local Traders")
        placements.set_placement(clean, local, "wheat", "up", "hardoi", 1)
        assert _names(district="") == []

    def test_state_all_covers_the_state_page_too(self, clean):
        """...but पूरा राज्य is sold as "state page + every district in it",
        so it must reach both or we are billing for a page we never render."""
        wide = _live(clean, "State Wide")
        placements.set_placement(clean, wide, "wheat", "up", W, 1)
        assert _names(district="") == ["State Wide"]
        assert _names(district="hardoi") == ["State Wide"]

    def test_national_does_not_leak_into_another_crop(self, clean):
        """(wheat, *, *) is one crop everywhere, not everything everywhere.
        A brand that bought wheat appearing on the potato page is inventory we
        gave away free, and a farmer being shown an irrelevant dealer."""
        nation = _live(clean, "Wheat Brand")
        placements.set_placement(clean, nation, "wheat", W, W, 1)
        assert _names(crop="wheat", state="mp", district="ujjain") == ["Wheat Brand"]
        assert _names(crop="potato", state="up", district="hardoi") == []


# ── the reserve ─────────────────────────────────────────────────────────────

class TestBroadPlansAreNotStarved:

    def test_locals_cannot_take_the_last_slot(self, clean):
        """Three local dealers, one national buyer, three slots. Pure
        specificity would give all three to the locals and leave the national
        buyer — who paid the most — on none of the pages he cares about."""
        for i in range(3):
            slug = _live(clean, f"Local {i}", owner_user_id=10 + i)
            placements.set_placement(clean, slug, "wheat", "up", "hardoi", i + 1)
        nation = _live(clean, "National Brand", owner_user_id=99)
        placements.set_placement(clean, nation, "wheat", W, W, 1)

        got = _names()
        assert got == ["Local 0", "Local 1", "National Brand"]
        assert "Local 2" not in got, "the reserve was eaten by a local"

    def test_an_unsold_reserve_is_not_wasted(self, clean):
        """The cap only exists to protect a broad buyer who exists. With none
        sold, holding a slot empty would serve nobody — least of all the farmer
        looking at a two-card panel with room for three."""
        for i in range(3):
            slug = _live(clean, f"Local {i}", owner_user_id=10 + i)
            placements.set_placement(clean, slug, "wheat", "up", "hardoi", i + 1)
        assert _names() == ["Local 0", "Local 1", "Local 2"]

    def test_the_promise_holds_on_a_fully_sold_district(self, clean):
        """The literal sales claim for the wide tiers: at least one slot on
        every page they cover, no matter how well sold that page already is."""
        for i in range(3):
            slug = _live(clean, f"Local {i}", owner_user_id=10 + i)
            placements.set_placement(clean, slug, "wheat", "up", "hardoi", i + 1)
        nation = _live(clean, "National Brand", owner_user_id=99)
        placements.set_placement(clean, nation, "wheat", W, W, 1)
        assert "National Brand" in _names()


# ── one dealer, several plans ───────────────────────────────────────────────

class TestNoDoubleRendering:

    def test_a_dealer_holding_two_plans_renders_once(self, clean):
        """Buying both his district and the whole state is a legitimate, and
        expected, pair of purchases. Rendering him twice on one page would look
        like a bug to the farmer and like padding to him."""
        slug = _live(clean, "Sharma Traders")
        placements.set_placement(clean, slug, "wheat", "up", "hardoi", 1)
        placements.set_placement(clean, slug, "wheat", "up", W, 1)
        assert _names() == ["Sharma Traders"]
        assert len(placements.for_dealer(slug)) == 2, "both sales still on the books"

    def test_the_duplicate_does_not_consume_the_reserve(self, clean):
        """He is placed by the narrower pattern, so his own wide plan must not
        also burn the reserved slot — that would be him outbidding himself and
        a third dealer losing a slot to nobody."""
        both = _live(clean, "Sharma Traders")
        other = _live(clean, "Verma Aadhat", owner_user_id=2)
        placements.set_placement(clean, both, "wheat", "up", "hardoi", 1)
        placements.set_placement(clean, both, "wheat", "up", W, 1)
        placements.set_placement(clean, other, "wheat", "up", W, 2)
        assert _names() == ["Sharma Traders", "Verma Aadhat"]


# ── lapses ──────────────────────────────────────────────────────────────────

class TestLapseStillEmptiesSlots:

    def test_a_lapsed_wide_buyer_frees_the_reserve(self, clean):
        """Eligibility is still re-checked at render for wildcards too — the
        property that lets a subscription end without anything remembering to
        clean up 1,800 pages."""
        for i in range(3):
            slug = _live(clean, f"Local {i}", owner_user_id=10 + i)
            placements.set_placement(clean, slug, "wheat", "up", "hardoi", i + 1)
        nation = _live(clean, "National Brand", owner_user_id=99)
        placements.set_placement(clean, nation, "wheat", W, W, 1)
        assert _names() == ["Local 0", "Local 1", "National Brand"]

        row = clean.query(dealers.Buyer).filter_by(slug=nation).one()
        row.active = False
        clean.commit()

        # The third local takes the freed slot rather than it going dark.
        assert _names() == ["Local 0", "Local 1", "Local 2"]
        assert placements.for_dealer(nation), "the slot itself was deleted"


# ── selling it ──────────────────────────────────────────────────────────────

class TestCapacity:

    def test_a_local_page_sells_two_not_three(self, clean):
        """The number the admin must see BEFORE quoting. Selling a third local
        slot is taking money for something the reserve will not render."""
        cap = placements.capacity("wheat", "up", "hardoi")
        assert (cap["cap"], cap["left"], cap["tier"]) == (2, 2, "district_crop")
        slug = _live(clean, "Local")
        placements.set_placement(clean, slug, "wheat", "up", "hardoi", 1)
        placements.invalidate()
        assert placements.capacity("wheat", "up", "hardoi")["left"] == 1

    def test_only_one_broad_slot_is_guaranteed(self, clean):
        """Three wide buyers can be sold, but only the first renders where the
        local slots are full. The other two are remnant, and capacity() has to
        say so rather than reporting three equal slots."""
        cap = placements.capacity("wheat", "up", W)
        assert cap["tier"] == "state_all"
        assert cap["cap"] == placements.SLOTS
        assert cap["guaranteed"] == placements.SLOTS - placements.LOCAL_CAP == 1

    def test_national_normalises_a_half_wild_pattern(self, clean):
        """(wheat, *, hardoi) would mean "Hardoi in every state", which is not
        a product and not what anyone typing it meant."""
        assert placements.normalise_pattern("wheat", W, "hardoi") == ("wheat", W, W)
        assert placements.tier_of("wheat", W, "hardoi") == "national"

    def test_everything_everywhere_is_not_for_sale(self, clean):
        """(*, *, *) would be the whole site for one price, which is not on the
        rate card. Rejected at the write rather than quietly created."""
        slug = _live(clean, "Greedy")
        assert placements.set_placement(clean, slug, W, W, W, 1) is None
        assert placements.set_placement(clean, slug, W, "up", W, 1) is None


# ── the rate card ───────────────────────────────────────────────────────────

class TestMeteredPricing:
    """₹199 per district + ₹50 per crop page, per season, with no ceiling.

    THE MISSING CAP IS THE FEATURE. A flat "all crops" price was proposed and
    rejected: crop counts per district run 4 → 61 in UP alone, so any ceiling
    charges a dealer with twelve pages the same as one with sixty-one. These
    tests pin that no two different baskets can ever come to the same number,
    which is the property a cap would break.
    """

    def test_the_worked_examples_on_the_page(self):
        """The exact figures printed on /dukanlisting. If these drift, the page
        is quoting a price the backend will not charge."""
        assert placements.quote(1, 0) == 199
        assert placements.quote(1, 1) == 249
        assert placements.quote(1, 5) == 449
        assert placements.quote(2, 5) == 648

    def test_price_never_flattens(self):
        """The whole objection to a cap: every extra page must cost something,
        all the way up. Sixty-one crops is a real district (Kanpur)."""
        prices = [placements.quote(1, n) for n in range(0, 62)]
        assert prices == sorted(prices)
        assert len(set(prices)) == len(prices), "two different baskets priced the same"

    def test_crops_are_charged_once_across_districts(self):
        """A dealer's crop mix does not change between his districts, so
        billing per district×crop pair would be a penalty for expanding."""
        one = placements.quote(1, 5)
        three = placements.quote(3, 5)
        assert three - one == 2 * placements.PRICE_DISTRICT
        assert three != placements.quote(1, 15)

    def test_list_price_is_above_the_offer_on_every_line(self):
        """The struck-through number is a promise about what a new dealer pays
        once the intro ends, not decoration — a list price at or below the
        offer is a false reference price under the CCPA dark-pattern rules."""
        assert placements.LIST_DISTRICT > placements.PRICE_DISTRICT
        assert placements.LIST_CROP > placements.PRICE_CROP
        for d, c in ((1, 0), (1, 5), (3, 12), (2, 61)):
            assert placements.list_quote(d, c) > placements.quote(d, c)

    def test_a_year_is_four_seasons_for_three(self):
        assert placements.year_quote(1, 5) == placements.quote(1, 5) * 3
        assert placements.YEAR_SEASONS_GIVEN == 4

    def test_breakdown_adds_up(self):
        """The form shows the itemised sum, so the items have to equal the
        total a dealer is asked for."""
        b = placements.breakdown(2, 5)
        assert b["districts_total"] + b["crops_total"] == b["total"]
        assert b["total"] == placements.quote(2, 5)

    def test_the_signup_quote_matches_the_rate_card(self):
        assert dealers.quote(2, 5) == placements.quote(2, 5)
        assert dealers.quote_year(2, 5) == placements.year_quote(2, 5)


class TestCropListIsMoney:
    """plan_crops is half the bill, so it is validated like money rather than
    like a description."""

    def test_junk_is_dropped_not_stored(self):
        got = dealers.normalise_plan_crops(
            ["Wheat", " potato ", "wheat", "bad crop!", "<script>", ""])
        assert got == ["wheat", "potato"]

    def test_duplicates_cannot_inflate_the_bill(self):
        """Two spellings of one crop must not be charged twice — the count
        feeds straight into quote()."""
        got = dealers.normalise_plan_crops(["wheat", "WHEAT", "wheat "])
        assert got == ["wheat"]

    def test_crops_of_dedupes_across_an_accounts_rows(self, clean):
        """Every row of an account carries the same list; if a hand-corrected
        row disagrees, the account must not be billed for the union twice."""
        for dist in ("Hardoi", "Sitapur"):
            dealers.create(clean, {
                "name": "Sharma", "district": dist, "state": "UP",
                "phone": "9876543210", "owner_user_id": 4,
                "plan_crops": ["wheat", "potato"]}, source="signup")
        rows = dealers.for_owner(clean, 4)
        assert dealers.crops_of(rows) == ["wheat", "potato"]
        assert dealers.account_price(clean, 4) == placements.quote(2, 2)


class TestCustomTierIsGatedOnTraffic:
    """₹4,999 is a floor, not a price. Of ~12,900 crop×district pages, most got
    no clicks at all last month — quoting the floor on one of those buys a
    season of revenue and loses the buyer permanently."""

    def test_a_dead_page_is_refused_outright(self, monkeypatch):
        from backend.services import page_stats
        monkeypatch.setattr(page_stats, "for_page",
                            lambda *a, **k: {"impressions": 0, "clicks": 0})
        q = placements.custom_quote("masur-dal", "uttar-pradesh", "bareilly")
        assert q["offered"] is False
        assert "price" not in q
        assert q["reason"]

    def test_below_the_gate_is_refused(self, monkeypatch):
        from backend.services import page_stats
        monkeypatch.setattr(page_stats, "for_page",
                            lambda *a, **k: {"impressions": placements.CUSTOM_MIN_IMPRESSIONS - 1,
                                             "clicks": 1})
        assert placements.custom_quote("wheat", "up", "x")["offered"] is False

    def test_above_the_gate_scales_with_the_page(self, monkeypatch):
        from backend.services import page_stats
        monkeypatch.setattr(page_stats, "for_page",
                            lambda *a, **k: {"impressions": 700, "clicks": 9})
        q = placements.custom_quote("garlic", "madhya-pradesh", "sehore")
        assert q["offered"] is True
        assert q["price"] == placements.CUSTOM_FLOOR * 2

    def test_no_snapshot_means_no_quote_not_a_guess(self, monkeypatch):
        """With no data we must not fall back to the floor: that is a price
        invented for a page we have never measured."""
        from backend.services import page_stats
        monkeypatch.setattr(page_stats, "for_page", lambda *a, **k: None)
        q = placements.custom_quote("wheat", "up", "x")
        assert q["offered"] is False and "price" not in q
