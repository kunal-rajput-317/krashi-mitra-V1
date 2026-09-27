"""/bhav meta descriptions: no freshness claim beside an old price, and the
description test's group B never quotes a figure.

From 25 to 28 Sep 2026 data.gov.in was down, and every /bhav snippet went on
saying "ताजा भाव … रोज़ सुबह अपडेट" next to a date three days old. The date
was honest; "ताजा" and "रोज़ सुबह अपडेट" were not (bhav._is_current).

The description test (utils/desc_test.py) splits district pages in two by a
fixed hash of the URL. Group B's description leaves out "औसत ₹X/क्विंटल" and
must stay otherwise the same, or the test measures two things at once.
"""

import re
from datetime import date, datetime, timedelta

import pytest

from backend.routes import bhav
from backend.utils import desc_test

STATE = "Uttar Pradesh"


def _iso(days_ago: int) -> str:
    return (date.today() - timedelta(days=days_ago)).isoformat()


def _meta_desc(html: str) -> str:
    return re.search(r'<meta name="description" content="([^"]*)"', html).group(1)


class TestIsCurrent:
    def test_today_and_yesterday_are_current(self):
        assert bhav._is_current(_iso(0)) and bhav._is_current(_iso(1))

    def test_two_days_and_older_are_not(self):
        assert not bhav._is_current(_iso(2))
        assert not bhav._is_current(_iso(9))

    def test_no_date_is_never_current(self):
        for missing in ("", None, "not-a-date"):
            assert not bhav._is_current(missing)


class TestVariant:
    def test_is_stable(self):
        assert desc_test.variant("wheat", "uttar-pradesh", "agra") == \
               desc_test.variant("wheat", "uttar-pradesh", "agra")

    def test_splits_roughly_in_half(self):
        groups = [desc_test.variant("wheat", "uttar-pradesh", f"d{i}") for i in range(2000)]
        share_b = groups.count("B") / len(groups)
        assert 0.45 < share_b < 0.55


def _district_named(group: str, prefix: str) -> str:
    """A made-up district whose /bhav/wheat/uttar-pradesh/<slug> URL falls in
    `group`, so both halves of the test can be rendered on purpose."""
    for i in range(200):
        name = f"{prefix}pur{i}"
        if desc_test.variant("wheat", "uttar-pradesh", name.lower()) == group:
            return name
    raise AssertionError("no district name found for the group")


@pytest.fixture()
def render(db_session, client):
    """Seed one district's snapshot + last-seen row with a price `days_ago`
    old, render its tier-4 page, return the HTML."""
    from backend.database.db import MandiLastSeen, MandiPrice
    made = []

    def go(district: str, days_ago: int) -> str:
        day = date.today() - timedelta(days=days_ago)
        ddmm = day.strftime("%d/%m/%Y")
        price = MandiPrice(
            state=STATE, district=district, market=f"{district} APMC",
            commodity="Wheat", variety="Dara", grade="FAQ",
            min_price="2500", max_price="2600", modal_price="2550",
            arrival_date=ddmm, fetched_at=datetime.utcnow())
        seen = MandiLastSeen(
            group_key=f"honest-{district}", commodity="Wheat", state=STATE,
            district=district, market=f"{district} APMC",
            min_price="2500", max_price="2600", modal_price="2550",
            arrival_date=ddmm, arrival_dt=day)
        db_session.add_all([price, seen])
        db_session.commit()
        made.extend([price, seen])
        bhav._index, bhav._index_ts = {}, 0.0
        return client.get(f"/bhav/wheat/uttar-pradesh/{district.lower()}").text

    yield go
    for row in made:
        db_session.delete(row)
    db_session.commit()
    bhav._index, bhav._index_ts = {}, 0.0


class TestDistrictDescription:
    def test_current_price_may_say_taza(self, render):
        desc = _meta_desc(render(_district_named("A", "Tazanagar"), 0))
        assert "ताजा भाव" in desc

    def test_old_price_makes_no_freshness_claim(self, render):
        desc = _meta_desc(render(_district_named("A", "Purananagar"), 3))
        assert "ताजा" not in desc
        assert "रोज़" not in desc
        assert bhav._hindi_date(date.today() - timedelta(days=3)) in desc, \
            "the description still leads with the price's own date"

    def test_group_a_quotes_the_average(self, render):
        desc = _meta_desc(render(_district_named("A", "Ankganj"), 0))
        assert "औसत ₹2,550/क्विंटल" in desc

    def test_group_b_quotes_no_figure(self, render):
        desc = _meta_desc(render(_district_named("B", "Binankganj"), 0))
        assert "₹" not in desc
        assert "ताजा भाव" in desc, "group B changes the figure and nothing else"


class TestShareCard:
    """The WhatsApp price card is drawn on the phone from the page's share
    config. It must carry the numbers the page prints, and the age note
    when the price is old, so the picture never says more than the page."""

    @staticmethod
    def _cfg(html: str) -> dict:
        import json
        raw = re.search(r"var CFG=(\{.*?\});\n", html).group(1)
        return json.loads(raw)

    def test_card_carries_the_page_numbers(self, render):
        html = render(_district_named("A", "Cardpur"), 0)
        card = self._cfg(html)["card"]
        assert card["avg"] == "₹2,550" and "₹2,550" in html
        assert card["lo"] == "₹2,500" and card["hi"] == "₹2,600"
        assert card["age"] == ""
        assert "kmPriceCard" in html

    def test_old_price_card_says_how_old(self, render):
        card = self._cfg(render(_district_named("A", "Oldcardpur"), 4))["card"]
        assert card["age"] == "4 दिन पुराना भाव"
