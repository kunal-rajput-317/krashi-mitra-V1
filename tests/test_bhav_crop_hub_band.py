"""/bhav/{crop} puts a price band in its meta description.

Crop hubs ran at ~0.2-0.4% CTR at positions 4-7 with no number in the
snippet; district pages carry their average because the Sep–Oct 2026 test
showed the price never costs the click. The band comes from the in-memory
snapshot only (tier 2 is a no-DB fast path), trims outliers, and is left out
rather than guessed when there are too few mandis.
"""
import re
from datetime import date, datetime

import pytest

from backend.routes import bhav
from backend.services import mandi_memory


def _row(i: int, modal, state="Uttar Pradesh", market=None) -> dict:
    return {"state": state, "district": f"D{i}", "market": market or f"M{i} APMC",
            "commodity": "Wheat", "modal_price": str(modal)}


class TestNationalBand:
    def test_none_when_snapshot_not_loaded(self, monkeypatch):
        monkeypatch.setattr(mandi_memory, "rows_for", lambda *a, **k: None)
        assert bhav._national_band("Wheat") is None

    def test_none_when_too_few_mandis(self, monkeypatch):
        rows = [_row(i, 2500 + i) for i in range(9)]
        monkeypatch.setattr(mandi_memory, "rows_for", lambda *a, **k: rows)
        assert bhav._national_band("Wheat") is None

    def test_wrong_unit_outlier_cannot_set_the_range(self, monkeypatch):
        rows = [_row(i, 2400 + 10 * i) for i in range(19)] + [_row(99, 250000)]
        monkeypatch.setattr(mandi_memory, "rows_for", lambda *a, **k: rows)
        lo, hi = bhav._national_band("Wheat")
        assert 2400 <= lo < hi <= 2600

    def test_one_vote_per_mandi(self, monkeypatch):
        # One mandi reporting 30 varieties must not outvote the other ten.
        rows = [_row(i, 2400 + 10 * i) for i in range(10)]
        rows += [_row(50, 9000, market="Big APMC") for _ in range(30)]
        monkeypatch.setattr(mandi_memory, "rows_for", lambda *a, **k: rows)
        lo, hi = bhav._national_band("Wheat")
        assert hi < 3000, "a single mandi set the band"


@pytest.fixture()
def crop_hub(db_session, client, monkeypatch):
    from backend.database.db import MandiPrice
    ddmm = date.today().strftime("%d/%m/%Y")
    row = MandiPrice(state="Uttar Pradesh", district="Bandpur", market="Bandpur APMC",
                     commodity="Wheat", variety="Dara", grade="FAQ",
                     min_price="2500", max_price="2600", modal_price="2550",
                     arrival_date=ddmm, fetched_at=datetime.utcnow())
    db_session.add(row)
    db_session.commit()
    bhav._index, bhav._index_ts = {}, 0.0
    yield lambda: client.get("/bhav/wheat").text
    db_session.delete(row)
    db_session.commit()
    bhav._index, bhav._index_ts = {}, 0.0


def _desc(html: str) -> str:
    return re.search(r'name="description" content="([^"]*)"', html).group(1)


def test_crop_hub_description_quotes_the_band(crop_hub, monkeypatch):
    rows = [_row(i, 2400 + 10 * i) for i in range(20)]
    monkeypatch.setattr(mandi_memory, "rows_for", lambda *a, **k: rows)
    d = _desc(crop_hub())
    assert re.search(r"ज़्यादातर मंडियों में ₹[\d,]+–₹[\d,]+/क्विंटल", d), d
    assert len(d) <= 162


def test_crop_hub_without_snapshot_keeps_the_old_description(crop_hub, monkeypatch):
    monkeypatch.setattr(mandi_memory, "rows_for", lambda *a, **k: None)
    d = _desc(crop_hub())
    assert "₹" not in d and "राज्यों की मंडियों के रेट" in d
