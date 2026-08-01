"""The contract between the mandi upserts and the indexes that back them.

On 30 Jul 2026 every mandi fetch failed for two days with

    InvalidColumnReference: there is no unique or exclusion constraint
    matching the ON CONFLICT specification

An index-storage cleanup had dropped the full unique index on
mandi_price_history.row_key, judging it a duplicate of
mandi_history_row_key_uidx. It is not a duplicate: that index is PARTIAL
(WHERE row_key IS NOT NULL), and Postgres only infers a partial index as the
ON CONFLICT arbiter when the INSERT repeats the predicate. The upsert did not,
so it matched no index and raised — taking the whole fetch down rather than
degrading.

The failure needed two independent mistakes, so both are pinned here. These
run on SQLite (CI has no Postgres) by checking the *compiled* SQL, which is
where the bug actually lived — the statement was malformed before it was ever
sent.
"""

from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from backend.database import db as dbmod
from backend.services import mandi_fetch_service as mfs

ARBITER = ("mandi_price_history", "row_key")


def _arbiter():
    for table, column, index, predicate in dbmod._CONFLICT_ARBITERS:
        if (table, column) == ARBITER:
            return index, predicate
    pytest.fail(f"no ON CONFLICT arbiter declared for {ARBITER[0]}.{ARBITER[1]}")


class _RecordingSession:
    """Captures statements instead of executing them — the assertions are
    about the SQL that gets built, not about a live database."""

    def __init__(self):
        self.statements = []

    def execute(self, stmt, *a, **kw):
        self.statements.append(stmt)
        return SimpleNamespace(rowcount=0)

    def commit(self):
        pass


SAMPLE = {
    "state": "Rajasthan", "district": "Sri Ganganagar", "market": "Gharsana",
    "commodity": "Wheat", "variety": "Dara", "grade": "FAQ",
    "min_price": "2400", "max_price": "2600", "modal_price": "2500",
    "arrival_date": "30/07/2026",
}


def _history_insert_sql():
    rows, _keys, _dts = mfs._history_rows([SAMPLE])
    session = _RecordingSession()
    mfs._append_history(session, rows, datetime(2026, 7, 30, 12, 0))
    assert session.statements, "_append_history issued no statement"
    return str(session.statements[0].compile(dialect=postgresql.dialect()))


class TestHistoryUpsertMatchesItsArbiter:
    def test_upsert_repeats_the_partial_index_predicate(self):
        """The bug itself: ON CONFLICT (row_key) with no WHERE cannot infer a
        partial index, and Postgres raises rather than falling back."""
        index, predicate = _arbiter()
        sql = " ".join(_history_insert_sql().split()).lower()

        conflict = sql.split("on conflict", 1)
        assert len(conflict) == 2, f"{index}-backed upsert lost its ON CONFLICT"
        clause = conflict[1]

        assert predicate.lower() in clause, (
            f"ON CONFLICT must repeat the predicate of {index} "
            f"({predicate}) or Postgres cannot infer it as the arbiter. "
            f"Got: ON CONFLICT{clause[:120]}"
        )

    def test_conflict_target_is_the_arbiter_column(self):
        sql = " ".join(_history_insert_sql().split()).lower()
        target = sql.split("on conflict", 1)[1]
        assert ARBITER[1] in target.split("do ", 1)[0]


class TestArbiterIndexesAreProtected:
    def test_no_arbiter_is_listed_as_a_dead_index(self):
        """_DEAD_INDEXES is a hand-maintained list; an arbiter landing on it is
        the drop that caused the outage."""
        dead = set(dbmod._DEAD_INDEXES)
        for _t, _c, index, _p in dbmod._CONFLICT_ARBITERS:
            assert index not in dead, (
                f"{index} backs an ON CONFLICT upsert — dropping it makes every "
                f"write to that table fail. Remove it from _DEAD_INDEXES."
            )

    def test_drop_is_refused_when_it_would_leave_no_arbiter(self):
        """The exact drop that caused the outage, replayed against the guard."""
        table, column, index, _p = dbmod._CONFLICT_ARBITERS[0]
        sole = {table: {column: {index}}}

        assert dbmod._sole_arbiter_for(
            index, lambda t, c: sole[t][c]) == f"{table}({column})"

    def test_drop_is_allowed_while_another_unique_index_survives(self):
        """Two unique indexes on the column: dropping one is the storage
        cleanup working as intended, and must not be blocked."""
        table, column, index, _p = dbmod._CONFLICT_ARBITERS[0]
        both = {table: {column: {index, "ix_mandi_price_history_row_key"}}}

        assert dbmod._sole_arbiter_for(
            index, lambda t, c: both[t][c]) is None

    def test_unrelated_index_is_never_blocked(self):
        """An arbiter that is already missing is not this drop's doing —
        blocking unrelated indexes on that basis would stall the cleanup."""
        table, column, _i, _p = dbmod._CONFLICT_ARBITERS[0]
        missing = {table: {column: set()}}

        assert dbmod._sole_arbiter_for(
            "ix_mandi_prices_id", lambda t, c: missing[t][c]) is None

    def test_every_arbiter_declares_a_predicate_or_none(self):
        """A declared predicate must be a real SQL fragment: the writers paste
        it into their ON CONFLICT clause verbatim."""
        for table, column, index, predicate in dbmod._CONFLICT_ARBITERS:
            assert table and column and index
            assert predicate is None or column in predicate, (
                f"{index}: predicate {predicate!r} does not mention {column}, "
                f"so the writer's ON CONFLICT ... WHERE cannot match it."
            )


class TestRowKeyIsStableAcrossWriters:
    """The live fetch and the archive backfill both write history. If they
    derived row_key differently, the backfill would duplicate every row it was
    meant to dedup against."""

    def test_row_key_is_deterministic(self):
        first, _k, _d = mfs._history_rows([SAMPLE])
        again, _k, _d = mfs._history_rows([SAMPLE])
        assert first[0]["row_key"] == again[0]["row_key"]

    def test_row_key_separates_days_and_markets(self):
        base, _k, _d = mfs._history_rows([SAMPLE])
        other_day, _k, _d = mfs._history_rows([{**SAMPLE, "arrival_date": "31/07/2026"}])
        other_mkt, _k, _d = mfs._history_rows([{**SAMPLE, "market": "Suratgarh"}])

        assert base[0]["row_key"] != other_day[0]["row_key"]
        assert base[0]["row_key"] != other_mkt[0]["row_key"]
        # Same mandi × crop across days shares a group_key — that is what the
        # trend chart and the day-over-day delta group on.
        assert base[0]["group_key"] == other_day[0]["group_key"]

    def test_row_key_is_never_null(self):
        """The arbiter index is partial on `row_key IS NOT NULL`; a NULL row_key
        would silently fall outside it and bypass dedup entirely."""
        sparse, _k, _d = mfs._history_rows([{"commodity": "Wheat"}])
        assert sparse[0]["row_key"]
