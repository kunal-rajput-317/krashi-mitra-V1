"""The snapshot must not rewrite rows whose prices have not moved.

Neon's free plan enforces `neon.max_cluster_size` (512 MB) against BRANCH
storage — live data plus retained change history — not against
`pg_database_size`. So row *churn* is what trips it, and when it trips, the
compute goes read-only: every page still serves, nothing can be saved, and
Neon's own dashboard says "All OK". That outage hit on 29 Jul, 5 Aug and
7 Aug 2026.

On 21 Sep 2026 `pg_stat_user_tables` showed where the churn came from:

    mandi_prices   live=28,512   ins=556,334   del=542,819

— roughly 20x the table's own size, because the merge deleted and re-inserted
every identity the feed re-reported, six times a day, whether or not a single
paisa had moved. `mandi_last_seen` (the same 28.5k identities) had only 90k
updates, because its upsert already carried an is-distinct-from guard.

These tests pin the guard the snapshot now has. They are about row *identity*
surviving: an untouched mandi must keep its primary key across a fetch, since
a new id is proof it was deleted and written again.
"""

from datetime import datetime, timedelta

import pytest

from backend.database.db import MandiPrice, SessionLocal
from backend.services import mandi_fetch_service as mfs


def _rec(market: str, modal: str, day: str = "21/09/2026") -> dict:
    return {
        "state": "Uttar Pradesh", "district": "Meerut", "market": market,
        "commodity": "Wheat", "variety": "Dara", "grade": "FAQ",
        "min_price": "2400", "max_price": "2600", "modal_price": modal,
        "arrival_date": day,
    }


FEED = [_rec(f"Mandi {i}", "2500") for i in range(12)]


def _merge(records, now=None):
    """Run one merge, the way fetch_and_store() does.

    _prev_modal_map and _spark_map are Postgres-only SQL (DISTINCT ON, ANY),
    so they are supplied as plain dicts here — they are inputs to the merge,
    not part of what is under test.
    """
    rows, _keys, _dts = mfs._history_rows(records)
    db = SessionLocal()
    try:
        out = mfs._merge_snapshot(db, rows, prev_map={}, spark_map={},
                                  now=now or datetime.utcnow())
        db.commit()
        return out
    finally:
        db.close()


def _snapshot() -> dict:
    """{market: (id, modal_price, fetched_at)} for the rows under test."""
    db = SessionLocal()
    try:
        return {r.market: (r.id, r.modal_price, r.fetched_at)
                for r in db.query(MandiPrice).filter(
                    MandiPrice.district == "Meerut").all()}
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _clean(db_engine):
    db = SessionLocal()
    try:
        db.query(MandiPrice).filter(MandiPrice.district == "Meerut").delete(
            synchronize_session=False)
        db.commit()
    finally:
        db.close()


class TestUnchangedRowsAreLeftAlone:
    def test_identical_feed_does_not_rewrite_a_single_row(self):
        """The regression itself. Same prices in, same primary keys out."""
        _merge(FEED)
        before = _snapshot()
        assert len(before) == len(FEED), "first merge did not build the snapshot"

        out = _merge(FEED)
        after = _snapshot()

        assert {m: v[0] for m, v in after.items()} == {m: v[0] for m, v in before.items()}, (
            "a re-fetch with identical prices deleted and re-inserted the "
            "snapshot rows — this is the churn that fills Neon's branch "
            "storage and flips the compute read-only")
        assert out["rewritten"] == 0, f"expected no rewrites, got {out}"
        assert out["unchanged"] == len(FEED), out

    def test_a_moved_price_is_still_rewritten(self):
        """The guard must not freeze the snapshot — real movement still lands."""
        _merge(FEED)
        before = _snapshot()

        moved = [_rec("Mandi 0", "2750")] + [r for r in FEED if r["market"] != "Mandi 0"]
        out = _merge(moved)
        after = _snapshot()

        assert after["Mandi 0"][1] == "2750", "a changed price did not reach the snapshot"
        assert after["Mandi 0"][0] != before["Mandi 0"][0], "the changed row was not rewritten"
        assert after["Mandi 5"][0] == before["Mandi 5"][0], (
            "an unrelated mandi was rewritten because its neighbour moved")
        assert out["rewritten"] == 1, out

    def test_no_duplicate_rows_survive_the_guard(self):
        """Skipping the delete must never leave two rows for one identity —
        that was the 21 Aug 2026 bug that made /bhav average a mandi twice."""
        for _ in range(3):
            _merge(FEED)

        db = SessionLocal()
        try:
            markets = [r.market for r in db.query(MandiPrice).filter(
                MandiPrice.district == "Meerut").all()]
        finally:
            db.close()
        assert len(markets) == len(set(markets)), f"duplicate snapshot rows: {markets}"

    def test_a_pre_existing_duplicate_is_collapsed(self):
        """Rows written before the 21 Aug fix must still be cleaned up, not
        protected by the new "leave it alone" path."""
        _merge(FEED)
        db = SessionLocal()
        try:
            twin = db.query(MandiPrice).filter(MandiPrice.market == "Mandi 0").first()
            db.add(MandiPrice(
                state=twin.state, district=twin.district, market=twin.market,
                commodity=twin.commodity, variety=twin.variety, grade=twin.grade,
                min_price=twin.min_price, max_price=twin.max_price,
                modal_price=twin.modal_price, arrival_date=twin.arrival_date,
                fetched_at=twin.fetched_at))
            db.commit()
        finally:
            db.close()

        _merge(FEED)

        db = SessionLocal()
        try:
            n = db.query(MandiPrice).filter(MandiPrice.market == "Mandi 0").count()
        finally:
            db.close()
        assert n == 1, f"duplicate identity survived the merge ({n} rows)"


class TestAgeOutStillWorks:
    def test_an_untouched_row_is_kept_fresh_enough_to_survive(self):
        """An unchanged row is not rewritten, so its fetched_at must still be
        bumped — otherwise SNAPSHOT_KEEP_DAYS would delete a mandi that is
        reporting faithfully at a steady price."""
        _merge(FEED)

        db = SessionLocal()
        try:
            stale = datetime.utcnow() - timedelta(hours=mfs.FRESH_BUMP_HOURS + 2)
            db.query(MandiPrice).filter(MandiPrice.district == "Meerut").update(
                {MandiPrice.fetched_at: stale}, synchronize_session=False)
            db.commit()
        finally:
            db.close()

        out = _merge(FEED)
        assert out["touched"] == len(FEED), f"stale rows were not bumped: {out}"

        cutoff = datetime.utcnow() - timedelta(days=mfs.SNAPSHOT_KEEP_DAYS)
        for market, (_id, _modal, fetched_at) in _snapshot().items():
            assert fetched_at > cutoff, f"{market} would age out despite reporting"

    def test_a_fresh_row_is_not_bumped_on_every_fetch(self):
        """The whole point: six fetches a day must not mean six writes a row."""
        _merge(FEED)
        out = _merge(FEED)
        assert out["touched"] == 0, (
            f"an already-fresh row was rewritten anyway: {out}")
