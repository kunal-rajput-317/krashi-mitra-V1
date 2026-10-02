"""/bhav pages read prices from services/mandi_memory instead of Postgres.

The memory copy exists only for speed (27 Sep 2026: an uncached district page
took 3-6 s, almost all of it database round trips). It must never change what
a page says. So every helper that now reads memory is run twice here on the
same rows, once through the database and once through the loaded copy, and
the two answers must be identical.

Tests run on SQLite, where the copy is off by default (see
mandi_memory.enabled). This file switches it on explicitly and loads it
synchronously.
"""

from datetime import date, datetime

import pytest

from backend.routes import bhav
from backend.services import mandi_memory

STATE, DISTRICT = "Uttar Pradesh", "Memorytestpur"
OTHER_DISTRICT = "Memoryganj"

# (market, commodity, variety, [(day-of-August, modal), ...]) — newest last.
FEED = [
    ("Alpha APMC", "Wheat",  "Dara",  [(3, 2600), (4, 2610), (6, 2630)]),
    ("Beta APMC",  "Wheat",  "Other", [(2, 2550), (5, 2580)]),
    ("Alpha APMC", "Onion",  "Red",   [(4, 1400), (6, 1450)]),
    (None,         "Wheat",  "Local", [(6, 2500)]),      # no market name
    ("Gamma APMC", "Mustard", "Black", [(1, 5900), (6, 6010)]),
]


@pytest.fixture()
def rows(db_session):
    from backend.database.db import MandiPrice, MandiPriceHistory

    def _wipe():
        for model in (MandiPrice, MandiPriceHistory):
            (db_session.query(model)
               .filter(model.district.in_([DISTRICT, OTHER_DISTRICT])).delete(
                   synchronize_session=False))
        db_session.commit()

    _wipe()
    for n, (market, crop, variety, points) in enumerate(FEED):
        for day, modal in points:
            db_session.add(MandiPriceHistory(
                state=STATE, district=DISTRICT, market=market, commodity=crop,
                variety=variety, grade="FAQ",
                min_price=str(modal - 50), max_price=str(modal + 50),
                modal_price=str(modal),
                arrival_date=f"0{day}/08/2026", arrival_dt=date(2026, 8, day),
                group_key=f"{n}", row_key=f"{n}|{day}",
            ))
        day, modal = points[-1]
        db_session.add(MandiPrice(
            state=STATE, district=DISTRICT, market=market, commodity=crop,
            variety=variety, grade="FAQ",
            min_price=str(modal - 50), max_price=str(modal + 50),
            modal_price=str(modal), prev_modal_price=None, change_pct=None,
            spark=",".join(str(m) for _, m in points),
            arrival_date=f"0{day}/08/2026", fetched_at=datetime.utcnow(),
        ))
    # Same crop, other district, different case in the state name: the
    # page queries are case-insensitive and must stay so.
    db_session.add(MandiPrice(
        state=STATE.upper(), district=OTHER_DISTRICT, market="Delta APMC",
        commodity="Wheat", variety="Dara", grade="FAQ",
        min_price="2400", max_price="2500", modal_price="2450",
        arrival_date="06/08/2026", fetched_at=datetime.utcnow(),
    ))
    db_session.commit()
    yield
    _wipe()


@pytest.fixture()
def both(rows, monkeypatch):
    """Call `fn()` with the memory copy off, then on; return both answers."""
    def run(fn):
        mandi_memory._snap = None
        monkeypatch.setattr(mandi_memory, "enabled", lambda: False)
        bhav._board_cache.clear()
        bhav._place_rates.clear()
        from_db = fn()

        monkeypatch.setattr(mandi_memory, "enabled", lambda: True)
        assert mandi_memory.load(), "memory copy failed to load"
        bhav._board_cache.clear()
        bhav._place_rates.clear()
        from_mem = fn()
        return from_db, from_mem

    yield run
    mandi_memory._snap = None


def _key(rows):
    return sorted(rows, key=lambda r: repr(sorted(r.items())))


@pytest.mark.parametrize("args", [
    ("Wheat", STATE, DISTRICT),
    ("wheat", STATE.lower(), DISTRICT.upper()),
    ("Wheat", STATE, ""),
    ("Wheat", "", ""),
    ("Onion", STATE, DISTRICT),
    ("Nosuchcrop", STATE, DISTRICT),
])
def test_rows_for_matches_the_database(both, args):
    c, s, d = args
    from_db, from_mem = both(lambda: bhav._rows_for(c, state=s, district=d))
    assert _key(from_mem) == _key(from_db)


def test_rows_for_sees_rows_at_all(both):
    """Guards the parity test above against passing on two empty lists."""
    _, from_mem = both(lambda: bhav._rows_for("Wheat", state=STATE, district=DISTRICT))
    assert len(from_mem) == 3


def test_district_trend_matches_the_database(both):
    def series():
        prices = bhav._rows_for("Wheat", state=STATE, district=DISTRICT)
        return bhav._district_series(prices, "2026-08-06", bhav._stats(prices)["avg"])
    from_db, from_mem = both(series)
    assert from_db, "fixture must be long enough to draw a trend"
    assert from_mem == from_db


def test_district_board_matches_the_database(both):
    from_db, from_mem = both(lambda: bhav._district_board(STATE, DISTRICT))
    assert from_db
    assert from_mem == from_db


def test_mandi_list_matches_the_database(both):
    def mandis():
        return sorted(bhav._mem_place_rows(STATE, DISTRICT, ("market", "commodity", "modal_price"))
                      or [], key=repr)
    _, from_mem = both(mandis)
    from backend.database.db import SessionLocal, MandiPrice
    db = SessionLocal()
    try:
        from_db = sorted(((r.market, r.commodity, r.modal_price) for r in
                          db.query(MandiPrice).filter(MandiPrice.state.ilike(STATE),
                                                      MandiPrice.district.ilike(DISTRICT))),
                         key=repr)
    finally:
        db.close()
    assert from_mem == from_db, "a missing market must come back as None, not '-'"


def test_nothing_loaded_means_ask_the_database(monkeypatch):
    mandi_memory._snap = None
    monkeypatch.setattr(mandi_memory, "enabled", lambda: False)
    assert mandi_memory.rows_for("Wheat", STATE, DISTRICT) is None
    assert mandi_memory.history(["Wheat"], STATE, DISTRICT,
                                date(2026, 8, 1), date(2026, 8, 6)) is None


def test_off_on_sqlite_by_default():
    """The test database is SQLite; the copy must stay off unless a test
    turns it on, or every other test would read a stale copy."""
    assert mandi_memory.enabled() is False


# ── incremental reload after a fetch ─────────────────────────
# Neon's free plan meters egress (5 GB/month), so after a fetch the copy
# reads only what that fetch wrote and replays the fetch's own rules
# (replace by _group_key, age out after SNAPSHOT_KEEP_DAYS, trim history).
# Whatever it builds must equal a full reload of the same tables.

def _state(snap_rows, hist_names=("Wheat", "Onion", "Mustard")):
    return (
        _key(mandi_memory.rows_for("", STATE, DISTRICT)),
        _key(mandi_memory.rows_for("Wheat", "", "")),
        sorted(map(repr, mandi_memory.history(hist_names, STATE, DISTRICT,
                                              date(2026, 7, 1), date(2026, 9, 30)))),
    )


def test_merge_after_a_fetch_equals_a_full_reload(rows, db_session, monkeypatch):
    from datetime import timedelta
    from backend.database.db import MandiPrice, MandiPriceHistory
    from backend.services import mandi_fetch_service as mfs

    # Keep this fixture's August history inside the retention window.
    monkeypatch.setattr(mfs, "HISTORY_DAYS", 0)
    monkeypatch.setattr(mandi_memory, "enabled", lambda: True)
    assert mandi_memory.load()

    # A fetch, written the way mandi_fetch_service writes it.
    now = datetime.utcnow() + timedelta(minutes=5)
    old = (db_session.query(MandiPrice)
             .filter(MandiPrice.district == DISTRICT, MandiPrice.market == "Beta APMC").one())
    db_session.delete(old)                                   # identity re-appeared
    db_session.add(MandiPrice(state=STATE, district=DISTRICT, market="Beta APMC",
                              commodity="Wheat", variety="Other", grade="FAQ",
                              min_price="2590", max_price="2690", modal_price="2640",
                              spark="2550,2580,2640", arrival_date="07/08/2026",
                              fetched_at=now))
    db_session.add(MandiPrice(state=STATE, district=DISTRICT, market="New APMC",
                              commodity="Onion", variety="Red", grade="FAQ",
                              min_price="1300", max_price="1500", modal_price="1420",
                              arrival_date="07/08/2026", fetched_at=now))
    db_session.add(MandiPriceHistory(state=STATE, district=DISTRICT, market="Beta APMC",
                                     commodity="Wheat", variety="Other", grade="FAQ",
                                     modal_price="2640", arrival_date="07/08/2026",
                                     arrival_dt=date(2026, 8, 7), group_key="b",
                                     row_key="b|7"))
    db_session.commit()

    mandi_memory.load_changes()
    merged = _state(rows)
    assert mandi_memory.status()["last_load"] == "changes"

    mandi_memory.load()
    assert _state(rows) == merged, "merging a fetch must equal reading everything again"
    assert any(r["market"] == "New APMC" for r in mandi_memory.rows_for("", STATE, DISTRICT))
    assert [r["modal_price"] for r in mandi_memory.rows_for("Wheat", STATE, DISTRICT)
            if r["market"] == "Beta APMC"] == ["2640"], "the replaced row is gone"


def test_merge_ages_out_what_the_fetch_ages_out(rows, db_session, monkeypatch):
    from datetime import timedelta
    from backend.database.db import MandiPrice
    from backend.services import mandi_fetch_service as mfs

    monkeypatch.setattr(mfs, "HISTORY_DAYS", 0)
    monkeypatch.setattr(mandi_memory, "enabled", lambda: True)
    stale = MandiPrice(state=STATE, district=DISTRICT, market="Quiet APMC",
                       commodity="Wheat", variety="Old", grade="FAQ", modal_price="2400",
                       arrival_date="01/08/2026",
                       fetched_at=datetime.utcnow() - timedelta(days=mfs.SNAPSHOT_KEEP_DAYS + 1))
    db_session.add(stale)
    db_session.commit()
    assert mandi_memory.load()
    assert any(r["market"] == "Quiet APMC" for r in mandi_memory.rows_for("", STATE, DISTRICT))

    db_session.add(MandiPrice(state=STATE, district=OTHER_DISTRICT, market="Fresh APMC",
                              commodity="Wheat", variety="Dara", grade="FAQ",
                              modal_price="2500", arrival_date="07/08/2026",
                              fetched_at=datetime.utcnow() + timedelta(minutes=5)))
    db_session.delete(stale)                  # the fetch's own age-out
    db_session.commit()
    mandi_memory.load_changes()
    assert not any(r["market"] == "Quiet APMC" for r in mandi_memory.rows_for("", STATE, DISTRICT))


# ── the stale-district rescue (mandi_last_seen) ──────────────
# A district whose crop is no longer in the snapshot shows the last prices we
# ever saw for it. About half the /bhav URLs are such districts, so this read
# comes from the memory copy too, and must say exactly what the database says.

QUIET = "Memorystalepur"


@pytest.fixture()
def quiet(db_session):
    from backend.database.db import MandiLastSeen

    def _wipe():
        (db_session.query(MandiLastSeen).filter(MandiLastSeen.district == QUIET)
           .delete(synchronize_session=False))
        db_session.commit()

    _wipe()
    for n, (market, crop, day, modal) in enumerate([
            ("Old APMC",   "Wheat", 20, 2400),     # the newest day: shown
            ("Other APMC", "Wheat", 20, 2380),
            ("Older APMC", "Wheat", 12, 2300),     # an older day: not shown
            ("Old APMC",   "Onion", 20, 1300),     # another crop: not shown
            (None,         "Wheat", None, 2350)]): # no date, no market
        db_session.add(MandiLastSeen(
            group_key=f"quiet-{n}", state=STATE, district=QUIET, market=market,
            commodity=crop, variety="Local", grade="FAQ",
            min_price=str(modal - 50), max_price=str(modal + 50), modal_price=str(modal),
            arrival_date=f"{day}/07/2026" if day else None,
            arrival_dt=date(2026, 7, day) if day else None,
            updated_at=datetime.utcnow()))
    db_session.commit()
    yield
    _wipe()


def _rescue():
    idx = {"raws": {"wheat": {"Wheat"}}, "crops": {"wheat": "Wheat"},
           "states": {"wheat": {"uttar-pradesh": STATE.lower()}},
           "dists": {"wheat": {"uttar-pradesh": {"memorystalepur": QUIET.upper()}}}}
    return bhav._rows_for_district(idx, "wheat", "uttar-pradesh", "memorystalepur")


def test_stale_district_rescue_matches_the_database(both, quiet):
    from_db, from_mem = both(_rescue)
    assert sorted(r["market"] for r in from_db) == ["Old APMC", "Other APMC"]
    assert _key(from_mem) == _key(from_db)


def test_stale_district_rescue_reads_no_database(both, quiet, monkeypatch):
    both(lambda: None)                       # leaves the copy loaded
    monkeypatch.setattr(mandi_memory, "enabled", lambda: True)
    def boom():
        raise AssertionError("the rescue opened a database session")
    monkeypatch.setattr(bhav, "SessionLocal", boom)
    assert len(_rescue()) == 2


def test_last_seen_merge_equals_a_full_reload(rows, quiet, db_session, monkeypatch):
    from datetime import timedelta
    from backend.database.db import MandiLastSeen

    monkeypatch.setattr(mandi_memory, "enabled", lambda: True)
    assert mandi_memory.load()
    later = datetime.utcnow() + timedelta(minutes=5)
    # The fetch's upsert: a newer day for one line-item, plus a new one.
    row = db_session.query(MandiLastSeen).filter_by(group_key="quiet-0").one()
    row.modal_price, row.arrival_dt, row.arrival_date, row.updated_at = (
        "2450", date(2026, 7, 22), "22/07/2026", later)
    db_session.add(MandiLastSeen(
        group_key="quiet-new", state=STATE, district=QUIET, market="New APMC",
        commodity="Wheat", variety="Local", grade="FAQ", modal_price="2460",
        arrival_date="22/07/2026", arrival_dt=date(2026, 7, 22), updated_at=later))
    db_session.commit()

    mandi_memory.load_changes()
    merged = _key(r for *_, r in mandi_memory.last_seen(["Wheat"], STATE, QUIET))
    assert sorted(r["market"] for r in _rescue()) == ["New APMC", "Old APMC"]
    mandi_memory.load()
    assert _key(r for *_, r in mandi_memory.last_seen(["Wheat"], STATE, QUIET)) == merged
