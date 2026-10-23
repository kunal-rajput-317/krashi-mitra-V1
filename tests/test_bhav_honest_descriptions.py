"""/bhav meta descriptions: no freshness claim beside an old price, and every
district description quotes the average.

From 25 to 28 Sep 2026 data.gov.in was down, and every /bhav snippet went on
saying "ताजा भाव … रोज़ सुबह अपडेट" next to a date three days old. The date
was honest; "ताजा" and "रोज़ सुबह अपडेट" were not (bhav._is_current).

From 28 Sep to 19 Oct 2026 half the district pages left "औसत ₹X/क्विंटल" out
of the description to see whether the price cost the click. It did not, so
the test ended and every district page quotes it again.
"""

import re
from datetime import date, datetime, timedelta

import pytest

from backend.routes import bhav

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
        desc = _meta_desc(render("Tazanagar", 0))
        assert "ताजा भाव" in desc

    def test_old_price_makes_no_freshness_claim(self, render):
        desc = _meta_desc(render("Purananagar", 3))
        assert "ताजा" not in desc
        assert "रोज़" not in desc
        assert bhav._hindi_date(date.today() - timedelta(days=3)) in desc, \
            "the description still leads with the price's own date"

    def test_every_district_quotes_the_average(self, render):
        for name in ("Ankganj", "Binankganj"):
            desc = _meta_desc(render(name, 0))
            assert "औसत ₹2,550/क्विंटल" in desc, name


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
        html = render("Cardpur", 0)
        card = self._cfg(html)["card"]
        assert card["avg"] == "₹2,550" and "₹2,550" in html
        assert card["lo"] == "₹2,500" and card["hi"] == "₹2,600"
        assert card["age"] == ""
        assert "kmPriceCard" in html

    def test_old_price_card_says_how_old(self, render):
        card = self._cfg(render("Oldcardpur", 4))["card"]
        assert card["age"] == "4 दिन पुराना भाव"
