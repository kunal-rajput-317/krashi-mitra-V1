"""The price ON the crop-less place hubs — /bhav/rajya/{state}[/{district}].

The bug this pins: the WhatsApp channel post prints five prices under "अपनी
मंडी का भाव यहाँ 👇" and deep-links to /bhav/rajya/<state>, and that page
carried no price at all. Every crop card said "भाव देखें →", so a follower who
tapped the link landed on a picker of 105 crops, two taps away from the number
he had just been shown. The link resolved fine; it simply did not answer.

So the hubs now print today's average per crop, computed the same way
services/wa_post computes the one in the post — the plain mean of every row's
modal price for that crop in that place. The post and the page are one
calculation over one snapshot, which is the invariant wa_post's file header
exists to protect, and the test below is what holds the two together.
"""

from datetime import date

import pytest

STATE = "Chhattisgarh"          # a state no other test file seeds prices for
SS = "chhattisgarh"

# Wheat: three markets across two districts, so the state average (2600) and
# the Raipur average (2550) are different numbers — a district hub printing
# its state's figure would otherwise pass unnoticed.
PRICES = [
    ("Wheat",  "Raipur", "Raipur Mandi", "2600"),
    ("Wheat",  "Raipur", "Bhatapara",    "2500"),
    ("Wheat",  "Durg",   "Durg Mandi",   "2700"),
    ("Potato", "Raipur", "Raipur Mandi", "724"),
]
# In the index but NOT in today's snapshot: a market that has gone quiet keeps
# its URL forever (see MandiLastSeen), and that page must still work.
QUIET = [("Onion", "Durg")]

REPORTED = date(2026, 8, 4)
WHEAT_STATE_AVG, WHEAT_RAIPUR_AVG = 2600, 2550


@pytest.fixture(scope="module", autouse=True)
def seeded(request):
    from datetime import datetime

    from backend.database.db import MandiLastSeen, MandiPrice, SessionLocal
    from backend.routes import bhav

    db = SessionLocal()
    made = []
    for commodity, district, market, modal in PRICES:
        made.append(MandiPrice(
            state=STATE, district=district, market=market, commodity=commodity,
            variety="FAQ", grade="FAQ", min_price=modal, max_price=modal,
            modal_price=modal, arrival_date="04/08/2026",
            fetched_at=datetime.utcnow()))
    # One last_seen row per crop×district, however many markets priced it.
    for commodity, district in dict.fromkeys([(c, d) for c, d, _m, _p in PRICES]
                                             + QUIET):
        made.append(MandiLastSeen(
            group_key=f"rates-{commodity}-{STATE}-{district}".lower(),
            commodity=commodity, state=STATE, district=district, market=district,
            min_price="1", max_price="1", modal_price="1",
            arrival_date="04/08/2026", arrival_dt=REPORTED))
    for r in made:
        db.add(r)
    db.commit()

    bhav._index, bhav._index_ts = {}, 0.0     # rebuild the page index off these
    bhav._place_rates = {}                     # and never serve a warm rate cache
    bhav._get_index()

    def _cleanup():
        for r in made:
            db.delete(r)
        db.commit()
        db.close()
        bhav._index, bhav._index_ts = {}, 0.0
        bhav._place_rates = {}

    request.addfinalizer(_cleanup)


class TestTheNumberIsOnThePage:
    def test_state_hub_prints_todays_average(self, client):
        html = client.get(f"/bhav/rajya/{SS}").text
        assert f"₹{WHEAT_STATE_AVG:,}" in html
        assert "₹724" in html

    def test_district_hub_prints_its_own_average(self, client):
        """Not the state's — Raipur's two markets, not all three."""
        html = client.get(f"/bhav/rajya/{SS}/raipur").text
        # The headline figure of the wheat row. (₹2,600 can still appear in
        # the row's min–max range — it is the Raipur Mandi's own rate — so
        # the check is on the big number, not on the digits anywhere.)
        assert f"₹{WHEAT_RAIPUR_AVG:,}<small>" in html
        assert f"₹{WHEAT_STATE_AVG:,}<small>" not in html

    def test_the_unit_is_stated(self, client):
        """A bare ₹2,600 next to "12 जिले" is a number without a unit."""
        assert "औसत भाव ₹/क्विंटल" in client.get(f"/bhav/rajya/{SS}").text


class TestThePostAndThePageAgree:
    def test_the_hub_prints_the_channel_posts_own_figure(self, client):
        """The invariant: one calculation, two places it is printed.

        Built through wa_post's real snapshot → pool path rather than by
        re-deriving the mean here, so a change to either side's arithmetic
        fails this rather than passing on both sides' new answer."""
        from backend.services import wa_post

        pool = wa_post._crop_lines(wa_post._snapshot()[STATE], min_mandis=1)
        wheat = next(l for l in pool if l["commodity"] == "Wheat")

        assert wheat["avg"] == WHEAT_STATE_AVG
        assert f"₹{wheat['avg']:,}" in client.get(f"/bhav/rajya/{SS}").text

    def test_the_post_links_where_the_figure_is(self):
        """The deep link in the post is the hub this file is about."""
        from backend.services import wa_post

        ctx = wa_post._ctx(STATE, "hi", 3, "")
        assert ctx["url"].startswith(f"https://krashimitra.in/bhav/rajya/{SS}?")


class TestNothingBreaksWithoutAPrice:
    def test_a_quiet_crop_still_renders_and_links(self, client):
        """A crop in the index but absent from today's snapshot keeps its card
        and its link — the never-404 rule. It shows the label, not a ₹0."""
        html = client.get(f"/bhav/rajya/{SS}/durg").text
        assert f'href="/bhav/onion/{SS}/durg"' in html
        assert "इनका आज का भाव नहीं आया" in html

    @pytest.mark.parametrize("bad", ["₹0", "₹-", "₹None", "₹1,1"])
    def test_no_placeholder_ever_reaches_a_card(self, client, bad):
        for url in (f"/bhav/rajya/{SS}", f"/bhav/rajya/{SS}/durg"):
            assert bad not in client.get(url).text


class TestTheDateBelongsToTheNumbers:
    """A page that states a price must date that price, not its own render —
    see bhav._as_of_hi. Both hubs printed today on every number until they
    started carrying numbers at all."""

    def test_the_chip_shows_the_reported_date(self, client):
        html = client.get(f"/bhav/rajya/{SS}").text
        assert "📅 4 अगस्त 2026" in html
        assert f"📅 {_hindi_today()}" not in html

    def test_dateModified_matches_the_sitemap(self, client):
        """Same rollup the sitemap publishes for this URL — bhav._fresh_iso."""
        html = client.get(f"/bhav/rajya/{SS}").text
        assert '"dateModified": "2026-08-04"' in html

        smap = client.get("/bhav/sitemap.xml").text
        loc = f"<loc>https://krashimitra.in/bhav/rajya/{SS}</loc>"
        assert f"{loc}<lastmod>2026-08-04</lastmod>" in smap

    def test_last_modified_header_is_sent(self, client):
        r = client.get(f"/bhav/rajya/{SS}/raipur")
        assert "04 Aug 2026" in r.headers["Last-Modified"]

    def test_the_snippet_does_not_contradict_the_page(self, client):
        """The one string Google actually displays. A description opening with
        today's date over a dateModified of 4 अगस्त is the self-contradiction
        the tier-3/4 handlers were already fixed for."""
        html = client.get(f"/bhav/rajya/{SS}").text
        desc = html.split('name="description" content="')[1].split('"')[0]
        assert desc.startswith("4 अगस्त 2026")
        assert _hindi_today() not in html

    def test_old_prices_say_how_old(self, client):
        """_age_badge — the amber pill tiers 2-3 already carry."""
        assert "दिन पुराना भाव" in client.get(f"/bhav/rajya/{SS}").text


def _hindi_today() -> str:
    from backend.routes import bhav

    return bhav._hindi_date(date.today())
