"""The /bhav/{crop} "साल भर में भाव" card: a national seasonal SHAPE, never a ₹.

Districts trade different grades at different price levels, so a ₹ average
across whichever districts happen to have history would move with the sample,
not the season. Each district is measured against its own yearly average and
the national figure is the median of those ratios. These tests pin that, and
the card's copy rules: % only, a record and never advice.
"""

import re

from backend.routes import bhav
from backend.services import mandi_season_service as season


def _district(key: str, level: float, shape: dict, months=range(1, 13)):
    """One district's monthly rows: its own price level × a seasonal shape."""
    return [(key, m, level * shape.get(m, 1.0)) for m in months]


ONION_LIKE = {5: 0.7, 11: 1.3}   # glut in May, scarcity in November


def test_price_level_does_not_move_the_pattern():
    # Same season, wildly different price levels: the ratio method must give
    # the same answer as if every district sold at one price.
    rows = []
    for i, level in enumerate([800, 1500, 2500, 4000, 6000]):
        rows += _district(f"d{i}", level, ONION_LIKE)
    p = season._crop_pattern(rows)
    assert p["districts"] == 5
    assert p["best"][0] == 11 and p["worst"][0] == 5
    # 12 months, mean ratio 1.0 → Nov ≈ 130/100 of the mean.
    assert p["index"][11] > 120 and p["index"][5] < 80


def test_too_few_districts_prints_nothing():
    rows = []
    for i in range(season.CROP_MIN_DISTRICTS - 1):
        rows += _district(f"d{i}", 2000, ONION_LIKE)
    assert season._crop_pattern(rows) is None


def test_district_covering_part_of_the_year_is_left_out():
    rows = []
    for i in range(5):
        rows += _district(f"full{i}", 2000, ONION_LIKE)
    # A district with only 4 months cannot say what its yearly average is.
    rows += _district("partial", 9000, {}, months=range(1, 5))
    assert season._crop_pattern(rows)["districts"] == 5


def test_card_is_percent_not_rupees_and_never_advice(monkeypatch):
    rows = []
    for i in range(6):
        rows += _district(f"d{i}", 1000 + 300 * i, ONION_LIKE)
    pattern = season._crop_pattern(rows)
    monkeypatch.setattr(season, "get_crop_pattern", lambda c: pattern)

    html = bhav._crop_season_html("Onion", "प्याज")
    assert "प्याज का भाव साल भर में" in html
    assert "नवंबर" in html and "मई" in html
    assert not re.search(r"₹\s*\d", html)       # no rupee figure anywhere
    assert "अनुमान या बेचने-खरीदने की सलाह नहीं" in html
    assert "6 जिलों" in html


def test_flat_crop_says_so(monkeypatch):
    flat = {"index": {m: 100 for m in range(1, 13)} | {1: 101},
            "best": (1, 101), "worst": (2, 100), "districts": 40}
    monkeypatch.setattr(season, "get_crop_pattern", lambda c: flat)
    html = bhav._crop_season_html("Wheat", "गेहूं")
    assert "लगभग एक जैसा" in html
    assert "सबसे ऊंचा" not in html


def test_no_pattern_or_db_error_renders_nothing(monkeypatch):
    monkeypatch.setattr(season, "get_crop_pattern", lambda c: None)
    assert bhav._crop_season_html("Onion", "प्याज") == ""

    def boom(c):
        raise RuntimeError("neon asleep")
    monkeypatch.setattr(season, "get_crop_pattern", boom)
    assert bhav._crop_season_html("Onion", "प्याज") == ""


def test_district_chart_still_labels_rupees():
    svg = bhav._season_chart({m: 2000 + m * 10 for m in range(1, 13)}, 9, 12, 1)
    assert "₹2,120" in svg


def test_api_outage_never_marks_a_slice_empty(monkeypatch):
    """A failed archive page (data.gov.in down) must stop the drain and leave
    the slice queued. Recorded as "empty" it would never be built again."""
    import pytest
    monkeypatch.setattr(season, "_get_page", lambda *a, **k: None)
    with pytest.raises(season.DataGovDown):
        season._fetch_slice_rows("Uttar Pradesh", "Mathura", "Wheat")

    built = []
    monkeypatch.setattr(season, "build_slice",
                        lambda *a: (_ for _ in ()).throw(season.DataGovDown("down")))

    class _Db:
        def execute(self, *a, **k):
            class R:
                def fetchall(self_inner):
                    return [("UP", "Mathura", "Wheat"), ("UP", "Agra", "Wheat")]
            built.append(1)
            return R()
        def close(self):
            pass
    monkeypatch.setattr(season, "SessionLocal", lambda: _Db())
    monkeypatch.setattr(season.time, "sleep", lambda s: None)
    assert season.drain_queue() == {"built": 0, "pending": 2}
