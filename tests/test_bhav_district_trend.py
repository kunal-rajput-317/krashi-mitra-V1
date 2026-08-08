"""The /bhav district page must quote ONE number, not three.

Reproduces /bhav/wheat/uttar-pradesh/bijnor exactly as it served on 6 Aug 2026,
where the price panel and the chart under it disagreed in front of the farmer:

    headline          ₹2,615   (average of 4 rows across 3 mandis)
    ▲ +0.9% कल से              (unweighted mean of the per-row change_pct)
    4-दिन औसत ₹2,651           (Bijnaur APMC's "Other" variety, alone)
    chart, last point ₹2,650   (the same single variety)

Three different row sets, three different bases, three different answers to
"what is wheat worth in Bijnor today". The chart was `max(sparks, key=len)` —
whichever single mandi+variety had reported most often — drawn under a heading
naming the whole district, with an axis that counted data points and called
them days.

The fixture below keeps every property that made the live page wrong:
  • the longest-spark row (Bijnaur/Other, 2650) is NOT the district average;
  • two rows tie on report count, so the old code's tie-break was list order;
  • the mandis report on different days, and one (Nagina) reported once, days
    ago — so index-aligning the sparks would compare Monday to Thursday.
"""

from datetime import date, datetime

import pytest

from backend.routes import bhav

STATE, DISTRICT = "Uttar Pradesh", "Trendtestpur"
END_ISO = "2026-08-06"

# (market, variety, [(day-of-August, modal), ...]) — newest last.
FEED = [
    ("Bijnaur APMC", "Other",  [(3, 2675), (4, 2690), (5, 2590), (6, 2650)]),
    ("Haldaur APMC", "Medium", [(4, 2610), (5, 2600), (6, 2620)]),
    ("Bijnaur APMC", "Dara",   [(3, 2599), (4, 2585), (5, 2593), (6, 2585)]),
    ("Nagina APMC",  "Other",  [(2, 2605)]),
]
HEADLINE = round((2650 + 2620 + 2585 + 2605) / 4)   # 2615, as the live page read


@pytest.fixture()
def district(db_session):
    """The snapshot the page renders, plus the history the trend is built from.

    Both tables, because that is the real shape: mandi_prices holds one merged
    row per line-item (a mandi that went quiet keeps its last rate) and
    mandi_price_history holds the dated rows behind it.
    """
    from backend.database.db import MandiPrice, MandiPriceHistory

    def _wipe():
        for model in (MandiPrice, MandiPriceHistory):
            db_session.query(model).filter(model.district == DISTRICT).delete()
        db_session.commit()

    _wipe()
    for market, variety, points in FEED:
        for day, modal in points:
            db_session.add(MandiPriceHistory(
                state=STATE, district=DISTRICT, market=market, commodity="Wheat",
                variety=variety, grade="FAQ",
                min_price=str(modal), max_price=str(modal), modal_price=str(modal),
                arrival_date=f"0{day}/08/2026", arrival_dt=date(2026, 8, day),
                group_key=f"{market}|{variety}", row_key=f"{market}|{variety}|{day}",
            ))
        last_day, last_modal = points[-1]
        db_session.add(MandiPrice(
            state=STATE, district=DISTRICT, market=market, commodity="Wheat",
            variety=variety, grade="FAQ",
            min_price=str(last_modal), max_price=str(last_modal),
            modal_price=str(last_modal),
            spark=",".join(str(m) for _, m in points),
            arrival_date=f"0{last_day}/08/2026", fetched_at=datetime.utcnow(),
        ))
    db_session.commit()
    yield
    _wipe()


@pytest.fixture()
def prices(district):
    rows = bhav._rows_for("Wheat", state=STATE, district=DISTRICT)
    assert len(rows) == len(FEED), "fixture did not load"
    return rows


def test_headline_is_still_the_district_average(prices):
    """Pins the number the rest of the page has to agree with."""
    assert bhav._stats(prices)["avg"] == HEADLINE


def test_chart_ends_on_the_headline_price(prices):
    """The one guarantee the whole fix exists for: the last point of the trend
    line IS the big number above it. It used to be ₹2,650 under a ₹2,615."""
    series = bhav._district_series(prices, END_ISO, HEADLINE)

    assert series, "a district with four reporting days must draw a chart"
    assert series[-1] == HEADLINE


def test_trend_is_the_district_not_its_chattiest_mandi(prices):
    """The old series was one mandi+variety's spark. Assert we did not simply
    reproduce it under a new name."""
    sparks = [[v for v in (bhav._num(x) for x in (p.get("spark") or [])) if v]
              for p in prices]
    old = max(sparks, key=len)
    series = bhav._district_series(prices, END_ISO, HEADLINE)

    assert old[-1] == 2650, "fixture no longer reproduces the reported bug"
    assert series != old
    assert series[-1] != old[-1]


def test_one_point_per_calendar_day(prices):
    """Points are days, not reports.

    The window opens on the district's earliest reported day (2 Aug, Nagina)
    and closes on the page's own data date (6 Aug) — five consecutive days,
    even though no single mandi filed on all five.
    """
    series = bhav._district_series(prices, END_ISO, HEADLINE)

    assert len(series) == (date(2026, 8, 6) - date(2026, 8, 2)).days + 1 == 5


def test_every_point_averages_the_same_mandis(prices):
    """A mandi that skips a day carries its last rate forward, and one that had
    not started reporting yet carries its first rate backward.

    Without both fills the line moves when the *set of mandis* changes rather
    than when a price does — on this fixture, 2 Aug would be Nagina's ₹2,605
    alone and the chart would open with a ₹17 "drop" nobody traded.
    """
    series = bhav._district_series(prices, END_ISO, HEADLINE)

    assert series == [2622, 2622, 2622, 2597, 2615]
    assert min(series) > 2500, "a point built from a shrunken mandi set"


def test_day_move_is_yesterday_to_today(prices):
    """The headline delta comes off the same series, so "कल से" is measured
    from the previous calendar day — not from an average of per-mandi
    percentages whose base dates differ by up to a week (the old +0.9%)."""
    series = bhav._district_series(prices, END_ISO, HEADLINE)
    move = round((series[-1] - series[-2]) / series[-2] * 100, 1)

    assert move == 0.7
    assert move != 0.9, "still the mean-of-percentages number"


def test_single_reporting_day_draws_nothing(db_session, district):
    """One day of history is not a trend. Better no chart than a straight line
    presented as one — the per-mandi sparklines still carry the movement."""
    from backend.database.db import MandiPriceHistory

    db_session.query(MandiPriceHistory).filter(
        MandiPriceHistory.district == DISTRICT,
        MandiPriceHistory.arrival_dt < date(2026, 8, 6)).delete()
    db_session.commit()

    rows = bhav._rows_for("Wheat", state=STATE, district=DISTRICT)
    assert bhav._district_series(rows, END_ISO, HEADLINE) == []


def test_no_reported_date_draws_nothing(prices):
    """Without a date to end on there is no window, and dead-reckoning one from
    the clock would date the line by the visit instead of by the data."""
    assert bhav._district_series(prices, "", HEADLINE) == []


def test_axis_counts_days_not_points():
    """N daily points span N-1 days. The label used to print N."""
    svg = bhav._chart([2600, 2610, 2590, 2620, 2615])

    assert "4 दिन पहले" in svg
    assert "5 दिन पहले" not in svg


# ── the whole panel, rendered ────────────────────────────────

@pytest.fixture()
def page(district, db_session, client):
    """The real tier-4 HTML. The index is rebuilt off mandi_last_seen, which is
    also what dates the page (_fresh_iso) — so the chart's window closes on the
    same day the sitemap's <lastmod> claims."""
    from backend.database.db import MandiLastSeen

    seen = MandiLastSeen(
        group_key="trend-test-wheat", commodity="Wheat", state=STATE,
        district=DISTRICT, market="Bijnaur APMC",
        min_price="2585", max_price="2650", modal_price="2650",
        arrival_date="06/08/2026", arrival_dt=date(2026, 8, 6))
    db_session.add(seen)
    db_session.commit()
    bhav._index, bhav._index_ts = {}, 0.0
    try:
        yield client.get(f"/bhav/wheat/uttar-pradesh/{DISTRICT.lower()}").text
    finally:
        db_session.delete(seen)
        db_session.commit()
        bhav._index, bhav._index_ts = {}, 0.0


def test_rendered_panel_quotes_one_number(page):
    """End to end: the headline, the sell-signal and the chart heading are the
    three places the page used to contradict itself."""
    assert "₹2,615</div>" in page or "₹2,615<small>" in page
    assert "▲ +0.7% कल से" in page
    assert "5-दिन औसत ₹2,616" in page          # the district's own 5 daily points
    assert "गेहूं का 5-दिन रुझान" in page
    assert "4 दिन पहले" in page


def test_rendered_chart_line_ends_on_the_headline(page):
    """Read the ₹ gridline labels back out of the SVG: the panel's ₹2,615 has to
    be inside the range the line is drawn against, and the old ₹2,651 four-day
    average must be gone."""
    import re

    chart = page[page.index("गेहूं का 5-दिन रुझान"):]
    chart = chart[:chart.index("</svg>")]
    labels = [int(v.replace(",", ""))
              for v in re.findall(r'text-anchor="end">₹([\d,]+)</text>', chart)]

    assert labels, "chart lost its rupee gridlines"
    assert min(labels) <= 2615 <= max(labels)
    assert "₹2,651" not in page, "the single-variety average is back"
    assert "+0.9%" not in page, "the mean-of-percentages delta is back"
