"""The romanised crop name in the /bhav <title> (bhav._ROMAN_NAME).

"chini ka bhav" and its spellings took 3,600 impressions at position 6.8 for
7 clicks in the 14 days to 3 Oct 2026, while romanised searches for other
crops clicked at 0.5-1.5% from the same positions. The sugar title carried
"चीनी" and "Sugar" but never "chini", the word the searcher typed.

What must hold:
  • every sugar title tier (crop, state, district) says "Chini Ka Bhav";
  • the title still fits the 68-character SERP budget;
  • a crop not in _ROMAN_NAME gets exactly the title it had before.
"""

import re
from datetime import date, datetime

import pytest

from backend.routes import bhav


def _title(html: str) -> str:
    return re.search(r"<title>([^<]*)</title>", html).group(1)


@pytest.fixture()
def seed(db_session):
    from backend.database.db import MandiPrice
    made = []
    for commodity in ("Sugar", "Wheat"):
        row = MandiPrice(
            state="Rajasthan", district="Jaipur", market="Jaipur (Grain)",
            commodity=commodity, variety="Other", grade="FAQ",
            min_price="5400", max_price="5600", modal_price="5500",
            arrival_date=date.today().strftime("%d/%m/%Y"),
            fetched_at=datetime.utcnow())
        db_session.add(row)
        made.append(row)
    db_session.commit()
    bhav._index, bhav._index_ts = {}, 0.0
    bhav._board_cache.clear()
    yield
    for row in made:
        db_session.delete(row)
    db_session.commit()
    bhav._index, bhav._index_ts = {}, 0.0
    bhav._board_cache.clear()


class TestHelper:
    def test_sugar(self):
        assert bhav._roman_bhav("Sugar") == "Chini Ka Bhav, "

    @pytest.mark.parametrize("commodity", ["Sugarcane", "Wheat", "Mustard", ""])
    def test_others_get_nothing(self, commodity):
        assert bhav._roman_bhav(commodity) == ""


class TestPages:
    @pytest.mark.parametrize("url", [
        "/bhav/sugar",
        "/bhav/sugar/rajasthan",
        "/bhav/sugar/rajasthan/jaipur",
    ])
    def test_sugar_titles_say_chini(self, seed, client, url):
        title = _title(client.get(url).text)
        assert "Chini Ka Bhav" in title
        assert "चीनी" in title and "Sugar" in title
        assert len(title) <= 68

    def test_other_crops_unchanged(self, seed, client):
        title = _title(client.get("/bhav/wheat/rajasthan/jaipur").text)
        assert "Ka Bhav" not in title
