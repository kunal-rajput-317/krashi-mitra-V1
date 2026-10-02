# ============================================================
# backend/services/mandi_memory.py
# KrashiMitra — the mandi snapshot and its recent history, held in memory
# ------------------------------------------------------------
# Why this exists. On 27 Sep 2026 an uncached /bhav district page took 3-6 s
# to answer. Profiling showed ~60 ms of Python and the rest database: two or
# three queries per page, each a fresh Neon connection (NullPool, see db.py)
# plus the rollback on close. Googlebot answers slow pages by crawling less —
# ~2,900 /bhav pages a day out of ~15,000 — so Google ranked "आज का भाव"
# searches on a copy of our page that was about 5 days old.
#
# The data behind those pages changes only when the mandi fetch runs (a few
# times a day), so reading it from Postgres on every page view buys nothing.
# This module keeps both tables in memory and answers the /bhav page helpers
# from there.
#
# 30 Sep 2026: mandi_last_seen joined them. About half the /bhav URLs are
# districts that no longer report (their crop is not in today's snapshot),
# and each of those pages still opened a Neon connection for the "last price
# we ever saw" rescue: 2.4-3 s at the edge against ~1 s for a fresh page.
# The table is ~31k rows, one per mandi line-item, never deleted and only
# upserted by the fetch (stamping updated_at), so after a fetch only the rows
# with a newer updated_at are read.
#
# Network transfer is metered too. Neon's free plan allows 5 GB of egress a
# month and suspends the compute past it. A full copy of both tables is
# ~21 MB of data (27 Sep 2026: 29,898 snapshot rows, 201,260 history rows),
# so reloading everything after each of ~6 fetches a day would cost several
# GB a month on its own. Instead:
#   * a FULL load happens at boot and then at most once a day, and sends the
#     history grouped per mandi line-item (one row of arrays per item instead
#     of one row per day), which is 3-4x fewer bytes on the wire;
#   * after a fetch only what that fetch wrote is read (snapshot rows with a
#     newer fetched_at, history rows with a higher id), and the fetch's own
#     rules are replayed here: a snapshot row is replaced by identity
#     (mandi_fetch_service._group_key), snapshot rows age out after
#     SNAPSHOT_KEEP_DAYS, history is trimmed to HISTORY_DAYS.
# The daily full load corrects anything written some other way
# (tools/neon/neon_load.py).
#
# Memory, measured: the loaded copy holds ~20 MB. Snapshot rows are interned
# tuples (a dict is built only for the rows a page renders); history is
# parallel arrays per district.
#
# Rules that keep it safe:
#   * Only on Postgres. Tests use SQLite and write rows between requests; a
#     copy loaded earlier would be stale there. Every getter returns None when
#     nothing is loaded, and every caller then falls back to its own query,
#     so behaviour is exactly the old one until a load has finished.
#   * Loads run in a background thread; a request never waits for one.
#   * A failed load keeps the previous copy. The live copy is never mutated:
#     every load builds a new one and swaps it in.
# ============================================================

import logging
import os
import sys
import threading
import time
from array import array
from datetime import date, datetime, timedelta

logger = logging.getLogger("krishi.mandi_memory")

FULL_RELOAD_SEC = 24 * 3600
STREAM_BATCH = 5000
_EPOCH = date(2000, 1, 1)
_EPOCH_ORD = _EPOCH.toordinal()

# Same keys, same order, as mandi_service._row_to_dict, so a row served
# from memory is indistinguishable from one read by _rows_for().
_KEYS = ("market", "district", "state", "commodity", "variety", "grade",
         "min_price", "max_price", "modal_price", "prev_modal_price",
         "change_pct", "spark", "date")


class _Snapshot:
    __slots__ = ("rows", "gks", "fetched", "by_c", "by_s", "by_sd", "hist",
                 "max_fetched", "max_hist_id", "loaded_at", "full_at",
                 "last_kind", "last_rows", "seen", "seen_by_sd", "max_seen")

    def __init__(self):
        self.rows: list[tuple] = []
        self.gks: list[str] = []                 # _group_key per row
        self.fetched = array("d")                # fetched_at, epoch seconds
        self.by_c: dict[str, list[int]] = {}     # lower(commodity) → row idx
        self.by_s: dict[str, list[int]] = {}     # lower(state)
        self.by_sd: dict[tuple, list[int]] = {}  # (lower(state), lower(district))
        # (state, district) exactly as stored → (items, item_idx, day, modal)
        self.hist: dict[tuple, tuple] = {}
        self.max_fetched: datetime | None = None
        self.max_hist_id = 0
        # mandi_last_seen: group_key → (state, district, arrival_dt, row
        # tuple), and (lower(state), lower(district)) → those entries.
        self.seen: dict[str, tuple] = {}
        self.seen_by_sd: dict[tuple, list[tuple]] = {}
        self.max_seen: datetime | None = None    # newest updated_at read
        self.loaded_at = 0.0
        self.full_at = 0.0
        self.last_kind = ""
        self.last_rows = 0


_snap: _Snapshot | None = None
_loading = threading.Lock()


def enabled() -> bool:
    if os.getenv("KM_MANDI_MEMORY", "").strip().lower() in ("0", "false", "no"):
        return False
    from backend.database.db import DATABASE_URL
    return DATABASE_URL.startswith("postgresql")


# ── building blocks ──────────────────────────────────────────

def _row_tuple(r, it=sys.intern) -> tuple:
    """mandi_service._row_to_dict(r), as a tuple, strings interned — market,
    state and price strings repeat thousands of times across the snapshot."""
    s = lambda v: it(str(v))
    return (
        it(r.market or "-"), it(r.district or "-"), it(r.state or "-"),
        it(r.commodity or "-"), it(r.variety or "-"), it(r.grade or "-"),
        s(r.min_price or "-"), s(r.max_price or "-"), s(r.modal_price or "-"),
        (s(r.prev_modal_price) if r.prev_modal_price else None),
        r.change_pct,
        (tuple(it(p) for p in r.spark.split(",") if p) if r.spark else ()),
        it(r.arrival_date or "-"),
    )


def _seen_entry(r, it=sys.intern) -> tuple:
    """A mandi_last_seen row as (state, district, arrival_dt, row tuple). The
    tuple is bhav._hist_to_dict(r) in _KEYS order: no delta, no spark."""
    s = lambda v: it(str(v))
    return (r.state, r.district, r.arrival_dt, (
        it(r.market or "-"), it(r.district or "-"), it(r.state or "-"),
        it(r.commodity or "-"), it(r.variety or "-"), it(r.grade or "-"),
        s(r.min_price or "-"), s(r.max_price or "-"), s(r.modal_price or "-"),
        None, None, (), it(r.arrival_date or "-"),
    ))


def _read_seen(db, new: "_Snapshot", since: datetime | None) -> None:
    """Read mandi_last_seen rows into new.seen (all of them, or only those
    updated after `since`) and advance new.max_seen."""
    from backend.database.db import MandiLastSeen
    q = db.query(MandiLastSeen)
    if since is not None:
        q = q.filter(MandiLastSeen.updated_at > since)
    for r in q.order_by(MandiLastSeen.id).yield_per(STREAM_BATCH):
        new.seen[r.group_key] = _seen_entry(r)
        u = r.updated_at
        if u and (new.max_seen is None or u > new.max_seen):
            new.max_seen = u


def _index_seen(new: "_Snapshot") -> None:
    for e in new.seen.values():
        key = ((e[0] or "").lower(), (e[1] or "").lower())
        new.seen_by_sd.setdefault(key, []).append(e)


def _gk(r) -> str:
    from backend.services.mandi_fetch_service import _group_key
    return _group_key({"state": r.state, "district": r.district, "market": r.market,
                       "commodity": r.commodity, "variety": r.variety, "grade": r.grade})


def _as_dict(t: tuple) -> dict:
    d = dict(zip(_KEYS, t))
    d["spark"] = list(d["spark"])
    return d


def _num(v) -> float | None:
    try:
        n = float(str(v).replace(",", ""))
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


def _index(new: _Snapshot) -> None:
    for i, t in enumerate(new.rows):
        c, s, d = t[3].lower(), t[2].lower(), t[1].lower()
        new.by_c.setdefault(c, []).append(i)
        new.by_s.setdefault(s, []).append(i)
        new.by_sd.setdefault((s, d), []).append(i)


def _hist_cutoff_ord() -> int:
    """History older than this is deleted by the fetch (mandi_fetch_service,
    'Retention'), so it must not linger here either."""
    from backend.services.mandi_fetch_service import HISTORY_DAYS
    if HISTORY_DAYS <= 0:
        return 0
    return (date.today() - timedelta(days=HISTORY_DAYS)).toordinal()


def _add_hist(groups: dict, st, dist, com, mkt, var, grd, day_ord: int, m: float,
              it=sys.intern) -> None:
    key = (st, dist)
    g = groups.get(key)
    if g is None:
        g = groups[key] = ([], {}, array("I"), array("i"), array("d"))
    items, pos, ix, days, modals = g
    ident = tuple(it(x) if x else x for x in (com, mkt, var, grd))
    k = pos.get(ident)
    if k is None:
        k = pos[ident] = len(items)
        items.append(ident)
    ix.append(k)
    days.append(day_ord)
    modals.append(m)


def _freeze(groups: dict) -> dict:
    return {k: (g[0], g[2], g[3], g[4]) for k, g in groups.items()}


# ── full load ────────────────────────────────────────────────

def _load_history_full(db) -> tuple[dict, int]:
    from sqlalchemy import text
    from backend.database.db import MandiPriceHistory
    groups: dict[tuple, tuple] = {}
    max_id = 0
    if db.get_bind().dialect.name == "postgresql":
        # One row per line-item with its days and modals as arrays: the same
        # data as one row per day, at a fraction of the bytes on the wire.
        res = db.execute(text(
            "SELECT state, district, commodity, market, variety, grade, "
            "       array_agg(arrival_dt - DATE '2000-01-01' ORDER BY arrival_dt), "
            "       array_agg(modal_price ORDER BY arrival_dt), max(id) "
            "FROM mandi_price_history WHERE arrival_dt IS NOT NULL "
            "GROUP BY state, district, commodity, market, variety, grade"
        ).execution_options(yield_per=STREAM_BATCH))
        for st, dist, com, mkt, var, grd, offs, modals, mid in res:
            max_id = max(max_id, mid or 0)
            for off, modal in zip(offs, modals):
                m = _num(modal)
                if m:
                    _add_hist(groups, st, dist, com, mkt, var, grd, _EPOCH_ORD + off, m)
    else:
        cols = (MandiPriceHistory.state, MandiPriceHistory.district,
                MandiPriceHistory.commodity, MandiPriceHistory.market,
                MandiPriceHistory.variety, MandiPriceHistory.grade,
                MandiPriceHistory.arrival_dt, MandiPriceHistory.modal_price,
                MandiPriceHistory.id)
        for st, dist, com, mkt, var, grd, dt, modal, rid in (
                db.query(*cols).yield_per(STREAM_BATCH)):
            max_id = max(max_id, rid or 0)
            m = _num(modal)
            if dt and m:                    # _district_series skips these rows too
                _add_hist(groups, st, dist, com, mkt, var, grd, dt.toordinal(), m)
    return groups, max_id


def load() -> bool:
    """Read both tables in full and swap the new copy in. True on success."""
    global _snap
    from backend.database.db import SessionLocal, MandiPrice

    t0 = time.time()
    new = _Snapshot()
    db = SessionLocal()
    try:
        for r in (db.query(MandiPrice).order_by(MandiPrice.id)
                    .yield_per(STREAM_BATCH)):
            new.rows.append(_row_tuple(r))
            new.gks.append(_gk(r))
            f = r.fetched_at
            new.fetched.append(f.timestamp() if f else 0.0)
            if f and (new.max_fetched is None or f > new.max_fetched):
                new.max_fetched = f
        groups, new.max_hist_id = _load_history_full(db)
        new.hist = _freeze(groups)
        _read_seen(db, new, None)
    except Exception:
        logger.exception("mandi memory full load failed; keeping the previous copy")
        return False
    finally:
        db.close()

    if not new.rows:
        logger.warning("mandi memory load found an empty snapshot; not swapping it in")
        return False
    _index(new)
    _index_seen(new)
    new.loaded_at = new.full_at = time.time()
    new.last_kind, new.last_rows = "full", len(new.rows)
    _snap = new
    logger.info("mandi memory full load: %d rows, %d history districts in %.1fs",
                len(new.rows), len(new.hist), time.time() - t0)
    return True


# ── incremental load (after a fetch) ─────────────────────────

def load_changes() -> bool:
    """Read only what the last fetch wrote and merge it into a new copy.
    Falls back to a full load when there is nothing to merge into."""
    global _snap
    old = _snap
    if old is None or old.max_fetched is None:
        return load()
    from backend.database.db import SessionLocal, MandiPrice, MandiPriceHistory
    from backend.services.mandi_fetch_service import SNAPSHOT_KEEP_DAYS

    t0 = time.time()
    db = SessionLocal()
    try:
        fresh = (db.query(MandiPrice)
                   .filter(MandiPrice.fetched_at > old.max_fetched)
                   .order_by(MandiPrice.id).all())
        cols = (MandiPriceHistory.state, MandiPriceHistory.district,
                MandiPriceHistory.commodity, MandiPriceHistory.market,
                MandiPriceHistory.variety, MandiPriceHistory.grade,
                MandiPriceHistory.arrival_dt, MandiPriceHistory.modal_price,
                MandiPriceHistory.id)
        added_hist = (db.query(*cols)
                        .filter(MandiPriceHistory.id > old.max_hist_id).all())
        # Last-seen is upsert-only: start from the old entries (shared, never
        # mutated) and overwrite the ones this fetch touched.
        new = _Snapshot()
        new.seen, new.max_seen = dict(old.seen), old.max_seen
        _read_seen(db, new, old.max_seen)
    except Exception:
        logger.exception("mandi memory incremental load failed; keeping the previous copy")
        return False
    finally:
        db.close()

    new.max_fetched, new.max_hist_id = old.max_fetched, old.max_hist_id

    # Snapshot: the fetch deletes every row whose identity re-appeared and
    # inserts the new one, then ages out rows not refreshed for
    # SNAPSHOT_KEEP_DAYS. Same here, in the same order.
    replaced = {}
    for r in fresh:
        replaced[_gk(r)] = r
        if r.fetched_at and r.fetched_at > new.max_fetched:
            new.max_fetched = r.fetched_at
    cutoff = (new.max_fetched - timedelta(days=SNAPSHOT_KEEP_DAYS)).timestamp()
    for t, gk, f in zip(old.rows, old.gks, old.fetched):
        if gk in replaced or f < cutoff:
            continue
        new.rows.append(t); new.gks.append(gk); new.fetched.append(f)
    for r in fresh:
        f = r.fetched_at.timestamp() if r.fetched_at else 0.0
        if f < cutoff:
            continue
        new.rows.append(_row_tuple(r)); new.gks.append(_gk(r)); new.fetched.append(f)
    _index(new)
    _index_seen(new)

    # History: insert-only (ON CONFLICT DO NOTHING) plus the retention trim.
    # Untouched districts share the old arrays; a touched or trimmed one is
    # rebuilt, never appended to in place while a request may be reading it.
    cut = _hist_cutoff_ord()
    touched: dict[tuple, list] = {}
    for st, dist, com, mkt, var, grd, dt, modal, rid in added_hist:
        new.max_hist_id = max(new.max_hist_id, rid or 0)
        m = _num(modal)
        if dt and m and dt.toordinal() >= cut:
            touched.setdefault((st, dist), []).append((com, mkt, var, grd, dt.toordinal(), m))
    hist = {}
    for key, (items, ix, days, modals) in old.hist.items():
        if key not in touched and (not days or min(days) >= cut):
            hist[key] = (items, ix, days, modals)
            continue
        g: dict = {}
        for k, dy, m in zip(ix, days, modals):
            if dy >= cut:
                _add_hist(g, key[0], key[1], *items[k], dy, m)
        for com, mkt, var, grd, dy, m in touched.pop(key, []):
            _add_hist(g, key[0], key[1], com, mkt, var, grd, dy, m)
        if g:
            hist.update(_freeze(g))
    for key, adds in touched.items():            # districts new to history
        g = {}
        for com, mkt, var, grd, dy, m in adds:
            _add_hist(g, key[0], key[1], com, mkt, var, grd, dy, m)
        hist.update(_freeze(g))
    new.hist = hist

    if not new.rows:
        logger.warning("mandi memory merge produced an empty snapshot; not swapping it in")
        return False
    new.loaded_at, new.full_at = time.time(), old.full_at
    new.last_kind, new.last_rows = "changes", len(fresh) + len(added_hist)
    _snap = new
    logger.info("mandi memory merged %d snapshot + %d history rows in %.1fs",
                len(fresh), len(added_hist), time.time() - t0)
    return True


# ── scheduling ───────────────────────────────────────────────

def _in_background(fn):
    if not _loading.acquire(blocking=False):
        return                      # a load is already running
    def run():
        try:
            fn()
        finally:
            _loading.release()
    threading.Thread(target=run, name="mandi-memory-load", daemon=True).start()


def reload_now() -> bool:
    """For the mandi scheduler, right after a fetch stored rows: merge just
    what it wrote. Runs in the caller's thread; skipped if a load is already
    running."""
    if not enabled():
        return False
    if not _loading.acquire(blocking=False):
        return False
    try:
        return load_changes()
    finally:
        _loading.release()


def _current() -> _Snapshot | None:
    """The loaded copy, or None. Kicks off a full load when there is none or
    the last full one is a day old; the request carries on with whatever
    exists right now."""
    if not enabled():
        return None
    s = _snap
    if s is None or time.time() - s.full_at > FULL_RELOAD_SEC:
        _in_background(load)
    return s


# ── reads ────────────────────────────────────────────────────

def rows_for(commodity: str = "", state: str = "", district: str = "") -> list[dict] | None:
    """What bhav._rows_for's query returns: case-insensitive equality on
    each field that is given. None = not loaded, use the database."""
    s = _current()
    if s is None:
        return None
    c, st, d = commodity.lower(), state.lower(), district.lower()
    if st and d:
        idx = s.by_sd.get((st, d), [])
    elif c:
        idx = s.by_c.get(c, [])
    elif st:
        idx = s.by_s.get(st, [])
    else:
        idx = range(len(s.rows))
    out = []
    for i in idx:
        t = s.rows[i]
        if c and t[3].lower() != c:
            continue
        if st and t[2].lower() != st:
            continue
        if d and t[1].lower() != d:
            continue
        out.append(_as_dict(t))
    return out


def rows_by_commodities(names) -> list[dict] | None:
    """Every row whose commodity is exactly one of `names` (the IN query in
    bhav._rows_for_district). None = not loaded."""
    s = _current()
    if s is None:
        return None
    names = set(names)
    out = []
    for n in {x.lower() for x in names}:
        out.extend(_as_dict(s.rows[i]) for i in s.by_c.get(n, [])
                   if s.rows[i][3] in names)
    return out


def last_seen(names, state: str, district: str, limit: int = 500) -> list[tuple] | None:
    """The mandi_last_seen query in bhav._rows_for_district: commodity exactly
    one of `names`, state and district equal ignoring case, newest arrival
    first (NULL dates first, as Postgres sorts DESC), at most `limit`. Each
    item is (state, district, arrival_dt, row dict). None = not loaded."""
    s = _current()
    if s is None:
        return None
    names = set(names)
    hits = [e for e in s.seen_by_sd.get((state.lower(), district.lower()), [])
            if e[3][3] in names]
    hits.sort(key=lambda e: (e[2] is not None, -(e[2].toordinal() if e[2] else 0)))
    return [(e[0], e[1], e[2], _as_dict(e[3])) for e in hits[:limit]]


def history(names, state: str, district: str, start: date, end: date) -> list[tuple] | None:
    """(commodity, market, variety, grade, arrival_dt, modal) for one
    district between start and end inclusive — the rows _district_series
    reads. State and district match exactly, as in its query. Rows without
    a date or a positive modal are not kept (the series skips them anyway).
    None = not loaded."""
    s = _current()
    if s is None:
        return None
    g = s.hist.get((state, district))
    if g is None:
        return []
    items, ix, days, modals = g
    names = set(names)
    lo, hi = start.toordinal(), end.toordinal()
    out = []
    for k, dy, m in zip(ix, days, modals):
        if lo <= dy <= hi:
            com, mkt, var, grd = items[k]
            if com in names:
                out.append((com, mkt, var, grd, date.fromordinal(dy), m))
    return out


def status() -> dict:
    s = _snap
    if s is None:
        return {"loaded": False, "enabled": enabled()}
    return {"loaded": True, "rows": len(s.rows), "history_districts": len(s.hist),
            "last_seen_rows": len(s.seen),
            "age_sec": round(time.time() - s.loaded_at),
            "last_load": s.last_kind, "last_load_rows": s.last_rows}
