"""/shop/mandi must serve the snapshot newest-arrival-date first.

mandi_prices is a MERGED snapshot, not one day's feed: a market that has not
reported for days keeps its last known row (MandiPrice's docstring), and one
crop legitimately holds several rows per district — one per market, and one per
variety. Meerut APMC files wheat three times, as Other / Medium / Dara.

So "the price of wheat in Meerut" is a choice among rows of different dates,
and the service used to return them in arbitrary physical order under an
unordered LIMIT. Both consumers got it wrong on 6 Aug 2026:

  • krashibook.js reads prices[0] — an arbitrary market on an arbitrary day.
  • index.html's homepage panel kept the row with the LONGEST sparkline, which
    ranks reporting streak, not recency: गेहूं showed ₹2,605 from 1 Aug when
    5 Aug was ₹2,600, and आलू showed ₹450 from 2 Aug when Mawana's 5 Aug price
    was ₹672.73 — under a freshness pill reading "कल".

The ordering is the service's half of that fix, and it is what makes prices[0]
meaningful for any caller.
"""

from datetime import datetime, timedelta

import pytest

from backend.services import mandi_service

DISTRICT = "Orderingtestpur"


@pytest.fixture()
def snapshot(db_session):
    """Three wheat varieties at one market, on three different days.

    Written so that recency and sparkline length DISAGREE — the stale row
    carries the longest series, exactly as the live Meerut data did. A fixture
    where the newest row also had the longest sparkline would pass either way.
    """
    from backend.database.db import MandiPrice

    def _wipe():
        db_session.query(MandiPrice).filter(MandiPrice.district == DISTRICT).delete()
        db_session.commit()

    _wipe()
    now = datetime.utcnow()
    rows = [
        # (variety, arrival_date, modal, spark, days since last seen reporting)
        ("Other",  "01/08/2026", "2605", "2600,2600,2600,2600,2605", 5),
        ("Dara",   "04/08/2026", "2650", "2600,2600,2600,2650",      2),
        ("Medium", "05/08/2026", "2600", "2600",                     1),
    ]
    for variety, adate, modal, spark, age in rows:
        db_session.add(MandiPrice(
            state="Uttar Pradesh", district=DISTRICT, market="Ordering APMC",
            commodity="Wheat", variety=variety, grade="FAQ",
            min_price=modal, max_price=modal, modal_price=modal,
            spark=spark, arrival_date=adate,
            fetched_at=now - timedelta(days=age),
        ))
    db_session.commit()
    yield
    _wipe()


def test_newest_arrival_date_is_first(snapshot):
    prices = mandi_service.get_mandi_prices("Wheat", DISTRICT, "")["prices"]

    assert len(prices) == 3, "all three varieties should still be served"
    assert [p["date"] for p in prices] == ["05/08/2026", "04/08/2026", "01/08/2026"]
    assert prices[0]["modal_price"] == "2600", (
        "prices[0] must be the most recent price — krashibook.js quotes it directly"
    )


def test_ordering_is_by_date_not_string_or_streak(snapshot):
    """Two wrong sorts this must not be: lexical on DD/MM/YYYY, and sparkline
    length. Lexical would put 01/08 first; sparkline length would too."""
    prices = mandi_service.get_mandi_prices("Wheat", DISTRICT, "")["prices"]

    assert prices[0]["date"] != "01/08/2026", "sorted as a string, or by streak"
    assert len(prices[-1]["spark"]) > len(prices[0]["spark"]), (
        "fixture no longer pins the disagreement between recency and streak"
    )


def test_undated_rows_sink(db_session, snapshot):
    """A row with no parseable arrival_date must not lead the list — it would
    be quoted as today's price with nothing to say it isn't."""
    from backend.database.db import MandiPrice

    db_session.add(MandiPrice(
        state="Uttar Pradesh", district=DISTRICT, market="Ordering APMC",
        commodity="Wheat", variety="Undated", grade="FAQ",
        min_price="9999", max_price="9999", modal_price="9999",
        arrival_date=None, fetched_at=datetime.utcnow(),
    ))
    db_session.commit()

    prices = mandi_service.get_mandi_prices("Wheat", DISTRICT, "")["prices"]
    assert prices[0]["modal_price"] != "9999"
    assert prices[-1]["modal_price"] == "9999"
