# ============================================================
# backend/services/mandi_fetch_service.py
# KrashiMitra — Mandi Price Auto-Fetcher
# ------------------------------------------------------------
# Pulls the full nationwide Agmarknet dataset from data.gov.in,
# rebuilds the "latest snapshot" table (mandi_prices), appends to a
# short-window history table (mandi_price_history, trimmed to
# MANDI_HISTORY_DAYS) and upserts mandi_last_seen — the permanent
# one-row-per-(mandi × crop) record that lets the trim stay short
# without any /bhav URL losing its data.
#
# Two data.gov resources are used:
#   RESOURCE_ID          — the live "today only" feed, wiped and refilled daily
#   ARCHIVE_RESOURCE_ID  — the same feed archived back to 2001, never wiped,
#                          trailing by ~a day. Only consulted when the live
#                          feed is too sparse to serve (see MIN_ROWS).
#
# Designed to be called by the APScheduler job (daily) and also
# runnable manually:  python -m backend.services.mandi_fetch_service
#   ... --archive-probe [YYYY-MM-DD]   fetch-only check of the archive path
# ============================================================

import os
import time
import hashlib
import logging
from datetime import datetime, date, timedelta, timezone

import requests
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.database.db import (
    SessionLocal, init_db, MandiPrice, MandiPriceHistory, MandiLastSeen,
)

load_dotenv()

logger = logging.getLogger("krishi.mandi_fetch")

# .strip() guards against the #1 cause of "403 Key not authorised": a key
# pasted into the host env with surrounding quotes or a trailing newline/space.
API_KEY = os.getenv("DATA_GOV_API_KEY", "").strip().strip('"').strip("'").strip()

# Variety-wise Daily Market Prices Data of Commodity (Agmarknet)
RESOURCE_ID = "9ef84268-d588-465a-a308-a864a43d0070"
ENDPOINT    = f"https://api.data.gov.in/resource/{RESOURCE_ID}"

PAGE_LIMIT = 5000      # rows per request
MAX_PAGES  = 20        # safety cap on pages per state

# History retention: trim mandi_price_history to the last N days after each
# fetch. Measured 2026-07-29 at ~9 MB/day (11 days = 101 MB), so 30d would be
# ~275 MB of a 512 MB cap — and the cap counts change history too, which is why
# it was already tripping. 0 = keep forever (do not use on the Free plan).
# 15 days is what the detail-sheet trend chart and the day-over-day delta
# need. Nothing else reads this table: "which pages exist" and "last known
# price for a quiet district" moved to mandi_last_seen, and the multi-year
# view is mandi_price_monthly. Kept low because history is ~9MB/day and the
# Free-plan branch cap (512MB) turns the whole database read-only when hit.
HISTORY_DAYS = int(os.getenv("MANDI_HISTORY_DAYS", "15"))

# Sparse-feed floor: data.gov wipes this resource overnight and refills it
# through the day (seen 2026-07-09/10: 2 rows at 06:30 IST, ~5.7k by 09:40,
# ~10k by 11:40, ~17.9k by evening). A normal day lands thousands of rows, so
# a tiny result means "fetched too early", NOT "markets were quiet". Runs
# below this floor must never replace the snapshot — they'd clobber it down
# to a handful of rows AND mark it fresh, silencing the staleness watchdog
# for a whole day (exactly the 2-row bug of 2026-07-09/10).
MIN_ROWS = int(os.getenv("MANDI_MIN_ROWS", "500"))

# data.gov.in is Elasticsearch-backed: offset + limit must be <= 10000, so
# plain nationwide offset-paging can never reach rows beyond 10k (~56% of the
# ~17.7k daily total). We instead partition by state — every state's result set
# is well under 10k — using the EXACT-match "state.keyword" filter. NOTE:
# "filters[state]" does analyzed/token matching (e.g. every "* Pradesh" state
# collides), so the ".keyword" sub-field is required for correct partitioning.
STATE_FILTER_FIELD = "filters[state.keyword]"

# Canonical state/UT spellings as data.gov.in stores them (note the non-standard
# ones: "Keralam", "Chattisgarh", "Pondicherry"). States absent on a given day
# simply return zero rows and are skipped — extra spellings are harmless.
STATES = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chattisgarh",
    "Chhattisgarh", "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand",
    "Karnataka", "Kerala", "Keralam", "Madhya Pradesh", "Maharashtra", "Manipur",
    "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim",
    "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand",
    "Uttrakhand", "West Bengal",
    # Both resources store this UT as "Andaman and Nicobar" — the "… Islands"
    # spelling matches 0 rows, so this UT was silently absent from every fetch
    # until 2026-07-29. Keeping both costs one empty request.
    "Andaman and Nicobar", "Andaman and Nicobar Islands", "Chandigarh",
    "Dadra and Nagar Haveli", "NCT of Delhi", "Delhi", "Jammu and Kashmir",
    "Ladakh", "Lakshadweep", "Puducherry", "Pondicherry", "Daman and Diu",
]
TIMEOUT    = 120       # seconds per request

# data.gov.in's API gateway throws intermittent 5xx errors under load;
# retry each page a few times before giving up on the whole run.
TRANSIENT_STATUS = {500, 502, 503, 504}
RATE_LIMIT_STATUS = 429          # data.gov throttles rapid bursts of requests
MAX_RETRIES       = 5            # attempts per page
STATE_DELAY       = 0.4          # polite pause (s) between per-state requests

# IMPORTANT: data.gov.in's WAF returns HTTP 502 for the default
# "python-requests/x.y" User-Agent. A browser-like UA is required or
# every request fails. (curl / browsers work; python-requests does not.)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

# ── Archive fallback ─────────────────────────────────────────
# "Variety-wise Daily Market Prices Data of Commodity" (DMI) is the SAME
# Agmarknet feed as RESOURCE_ID above — but it is never wiped: ~80M rows going
# back to 2001, trailing the live resource by about a day. We use it purely as
# a fallback: when the live feed is still filling (see MIN_ROWS), a pre-dawn or
# post-outage visitor would otherwise get an empty or days-old snapshot. The
# archive gives us yesterday's COMPLETE prices instead.
#
# Verified against the live API on 2026-07-29:
#   • Field names are Capitalised here ("State"/"Arrival_Date") where the live
#     resource uses lowercase ("state"/"arrival_date") — _archive_to_feed()
#     translates, so nothing downstream changes.
#   • filters[State] and filters[Arrival_Date] are EXACT matches: "Uttar
#     Pradesh" returned only Uttar Pradesh (no "* Pradesh" token bleed), and
#     all 18,877 rows of a day carried exactly the requested date. NOTE the
#     ".keyword" sub-field the live resource needs does NOT exist here — using
#     it returns 0 rows.
#   • One day nationwide ≈ 18.9k rows; the largest single state ≈ 1.7k. So one
#     request per state fits in a single page and we never rely on deep offset
#     paging, which returns overlapping rows on this resource.
ARCHIVE_RESOURCE_ID = "35985678-0d79-46b4-9ed6-6f13308a1d24"
ARCHIVE_ENDPOINT    = f"https://api.data.gov.in/resource/{ARCHIVE_RESOURCE_ID}"
ARCHIVE_STATE_FIELD = "filters[State]"
ARCHIVE_DATE_FIELD  = "filters[Arrival_Date]"

# The archive trails the live feed by ~a day, and a given day can be thin
# (holidays, mandi closures), so walk back until we find a complete-looking day.
ARCHIVE_LOOKBACK_DAYS = int(os.getenv("MANDI_ARCHIVE_LOOKBACK_DAYS", "3"))

# Kill switch — set MANDI_ARCHIVE_FALLBACK=0 to go back to live-feed-only.
ARCHIVE_FALLBACK = os.getenv("MANDI_ARCHIVE_FALLBACK", "1").strip().lower() \
    not in ("0", "false", "no", "off")

# Mandi days are IST days; the process may run in UTC.
IST_TZ = timezone(timedelta(hours=5, minutes=30))


# ── Helpers ──────────────────────────────────────────────────

def _parse_dt(raw: str):
    """Parse Agmarknet arrival_date into a date object. Tolerant of formats."""
    if not raw:
        return None
    raw = str(raw).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _norm(v) -> str:
    return ("" if v is None else str(v)).strip()


def _group_key(r: dict) -> str:
    raw = "|".join([
        _norm(r.get("state")).lower(),
        _norm(r.get("district")).lower(),
        _norm(r.get("market")).lower(),
        _norm(r.get("commodity")).lower(),
        _norm(r.get("variety")).lower(),
        _norm(r.get("grade")).lower(),
    ])
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


# ── Fetch ────────────────────────────────────────────────────

def _get_page(params: dict, label: str, endpoint: str = ENDPOINT) -> list | None:
    """
    GET one page with retry+backoff on transient (5xx / network) errors.
    Returns the list of records, or None if the page ultimately failed
    (so the caller can distinguish "empty" from "error").
    `endpoint` lets the same retry/backoff path serve the archive resource.
    """
    for attempt in range(MAX_RETRIES):
        try:
            res = requests.get(endpoint, params=params, headers=HEADERS, timeout=TIMEOUT)
        except requests.RequestException as e:
            wait = 2 ** attempt
            logger.warning(f"{label} attempt {attempt + 1}/{MAX_RETRIES} "
                           f"request error: {e} — retrying in {wait}s")
            time.sleep(wait)
            continue

        if res.status_code == RATE_LIMIT_STATUS:
            # Rate limited — back off harder, honoring Retry-After when present.
            wait = int(res.headers.get("Retry-After") or 0) or (3 * (attempt + 1))
            logger.warning(f"{label} attempt {attempt + 1}/{MAX_RETRIES} "
                           f"HTTP 429 (rate limited) — retrying in {wait}s")
            time.sleep(wait)
            continue

        if res.status_code in TRANSIENT_STATUS:
            wait = 2 ** attempt
            logger.warning(f"{label} attempt {attempt + 1}/{MAX_RETRIES} "
                           f"HTTP {res.status_code} — retrying in {wait}s")
            time.sleep(wait)
            continue

        if res.status_code == 403:
            # data.gov returns 403 {"error":"Key not authorised"} for a bad /
            # expired / malformed key — not transient, so don't waste retries.
            logger.error(
                f"{label}: HTTP 403 from data.gov ({res.text.strip()[:160]}). "
                f"DATA_GOV_API_KEY is missing/expired or has stray quotes or "
                f"whitespace — set it to the exact key (no quotes) and redeploy."
            )
            return None

        if res.status_code != 200 or not res.text.strip():
            logger.error(f"{label}: bad response HTTP {res.status_code}")
            return None

        return res.json().get("records", [])

    logger.error(f"{label}: exhausted {MAX_RETRIES} retries — giving up on this page.")
    return None


def _fetch_state(state: str) -> tuple[list, bool]:
    """
    Page through all rows for one state via the exact-match keyword filter.
    Returns (records, complete) — complete=False when a page hard-failed
    after retries, i.e. the state's data may be partial.
    """
    records, offset = [], 0
    for page in range(MAX_PAGES):
        params = {
            "api-key": API_KEY,
            "format":  "json",
            "limit":   PAGE_LIMIT,
            "offset":  offset,
            STATE_FILTER_FIELD: state,
        }
        recs = _get_page(params, f"[{state}] offset={offset}")
        if recs is None:      # hard error for this page — stop this state
            return records, False
        if not recs:          # no (more) rows for this state
            break

        records.extend(recs)
        if len(recs) < PAGE_LIMIT:
            break
        offset += PAGE_LIMIT
        time.sleep(STATE_DELAY)

    return records, True


def _fetch_all_records() -> tuple[list, set]:
    """
    Fetch the full nationwide dataset by partitioning per state (data.gov caps
    plain offset-paging at 10k rows). Deduplicates across states by row identity.
    Returns (records, failed_states) — failed_states are the state names whose
    fetch hard-failed midway, so their records may be incomplete. (The keyword
    filter is exact-match, so the filter string equals the stored state name.)
    """
    if not API_KEY:
        logger.error("DATA_GOV_API_KEY not set — cannot fetch mandi prices.")
        return [], set()

    all_records, seen = [], set()
    failed_states = set()
    states_hit = 0
    for state in STATES:
        recs, complete = _fetch_state(state)
        time.sleep(STATE_DELAY)   # pace requests to avoid data.gov 429 throttling
        if not complete:
            failed_states.add(state)
        if not recs:
            continue
        added = 0
        for r in recs:
            rk = _group_key(r) + "|" + _norm(r.get("arrival_date"))
            if rk in seen:
                continue
            seen.add(rk)
            all_records.append(r)
            added += 1
        if added:
            states_hit += 1
            logger.info(f"📥 {state}: +{added} (total {len(all_records)})")

    if failed_states:
        logger.warning(f"⚠️ Incomplete fetch for {len(failed_states)} state(s): "
                       f"{sorted(failed_states)} — their snapshot rows will be kept as-is.")
    logger.info(f"🌾 Fetched {len(all_records)} rows across {states_hit} states.")
    return all_records, failed_states


# ── Archive fallback fetch ───────────────────────────────────

def _archive_to_feed(r: dict) -> dict:
    """Translate one archive row into the live feed's lowercase field shape,
    so _group_key / normalisation / storage all work unchanged."""
    return {
        "state":        r.get("State"),
        "district":     r.get("District"),
        "market":       r.get("Market"),
        "commodity":    r.get("Commodity"),
        "variety":      r.get("Variety"),
        "grade":        r.get("Grade"),
        "arrival_date": r.get("Arrival_Date"),
        "min_price":    r.get("Min_Price"),
        "max_price":    r.get("Max_Price"),
        "modal_price":  r.get("Modal_Price"),
    }


def _fetch_archive_day(day: date) -> list:
    """
    Every archive row for one calendar day, partitioned per state (one request
    each — a state's day is ~1-2k rows, well inside a single page). Returns
    live-feed-shaped dicts, deduplicated by market identity + date.
    """
    stamp = day.strftime("%d/%m/%Y")
    records, seen = [], set()
    for state in STATES:
        offset = 0
        for _page in range(MAX_PAGES):
            params = {
                "api-key": API_KEY,
                "format":  "json",
                "limit":   PAGE_LIMIT,
                "offset":  offset,
                ARCHIVE_STATE_FIELD: state,
                ARCHIVE_DATE_FIELD:  stamp,
            }
            recs = _get_page(params, f"[archive {stamp} {state}] offset={offset}",
                             endpoint=ARCHIVE_ENDPOINT)
            if not recs:      # hard error or no (more) rows — move to next state
                break
            for raw in recs:
                r  = _archive_to_feed(raw)
                rk = _group_key(r) + "|" + _norm(r.get("arrival_date"))
                if rk in seen:
                    continue
                seen.add(rk)
                records.append(r)
            if len(recs) < PAGE_LIMIT:
                break
            offset += PAGE_LIMIT
        time.sleep(STATE_DELAY)   # pace requests to avoid data.gov 429 throttling
    return records


def merge_archive_rows(live: list, archive: list) -> tuple[list, int]:
    """
    Combine a sparse live fetch with archived rows, returning (rows, n_added).

    Live rows ALWAYS win per market identity: the archive only fills markets
    that have not reported yet today. Without this rule a market that appears
    in both would land in the snapshot twice — the same /bhav page showing one
    market at two different prices.
    """
    live_keys = {_group_key(r) for r in live}
    rows, added = list(live), 0
    for r in archive:
        if _group_key(r) in live_keys:
            continue
        rows.append(r)
        added += 1
    return rows, added


def fetch_archive_fallback() -> tuple[list, date | None]:
    """
    Best-effort: the most recent archived day that looks complete, as
    (records, day) — or ([], None) if the archive can't help. Never raises;
    a fallback failure must leave the live fetch exactly as it was.
    """
    if not ARCHIVE_FALLBACK:
        logger.info("🗄️ Archive fallback disabled (MANDI_ARCHIVE_FALLBACK=0).")
        return [], None
    if not API_KEY:
        return [], None

    today_ist = datetime.now(IST_TZ).date()
    try:
        for back in range(1, ARCHIVE_LOOKBACK_DAYS + 1):
            day  = today_ist - timedelta(days=back)
            recs = _fetch_archive_day(day)
            logger.info(f"🗄️ Archive {day:%d/%m/%Y}: {len(recs)} rows")
            if len(recs) >= MIN_ROWS:
                return recs, day
    except Exception as e:
        logger.error(f"🗄️ Archive fallback failed (non-fatal): {e}")
        return [], None

    logger.warning(f"🗄️ Archive fallback found no day with ≥{MIN_ROWS} rows in "
                   f"the last {ARCHIVE_LOOKBACK_DAYS} days — leaving snapshot as-is.")
    return [], None


# ── Store ────────────────────────────────────────────────────

def _prev_modal_map(db, group_keys: set, before_dt) -> dict:
    """
    For each group_key, return the most recent modal_price strictly BEFORE
    `before_dt` from history → used to compute the day-over-day delta.
    """
    if not group_keys:
        return {}

    keys = list(group_keys)
    result = {}
    # ANY(:keys) handles large key lists; DISTINCT ON gives latest per group.
    sql = text("""
        SELECT DISTINCT ON (group_key) group_key, modal_price
        FROM mandi_price_history
        WHERE group_key = ANY(:keys)
          AND arrival_dt IS NOT NULL
          AND (:before_dt IS NULL OR arrival_dt < :before_dt)
        ORDER BY group_key, arrival_dt DESC
    """)
    for row in db.execute(sql, {"keys": keys, "before_dt": before_dt}):
        result[row[0]] = row[1]
    return result


SPARK_POINTS = 8   # how many recent days to keep for the inline card sparkline


def _spark_map(db, group_keys: set) -> dict:
    """For each group_key, return the last SPARK_POINTS modal prices (chronological)."""
    if not group_keys:
        return {}

    keys = list(group_keys)
    sql = text("""
        SELECT group_key, modal_price, arrival_dt FROM (
            SELECT group_key, modal_price, arrival_dt,
                   ROW_NUMBER() OVER (PARTITION BY group_key ORDER BY arrival_dt DESC) AS rn
            FROM mandi_price_history
            WHERE group_key = ANY(:keys) AND arrival_dt IS NOT NULL
        ) t
        WHERE rn <= :n
        ORDER BY group_key, arrival_dt ASC
    """)
    out = {}
    for gk, modal, _dt in db.execute(sql, {"keys": keys, "n": SPARK_POINTS}):
        out.setdefault(gk, []).append(_norm(modal))
    return {gk: ",".join(vals) for gk, vals in out.items()}


def _change_pct(modal: str, prev: str):
    try:
        m, p = float(modal), float(prev)
        if p > 0:
            return round((m - p) / p * 100, 1)
    except (TypeError, ValueError):
        pass
    return None


# Snapshot rows not refreshed for this many days are dropped — covers states
# kept on fetch failure that then never reappear in the feed.
SNAPSHOT_KEEP_DAYS = 7


def check_api_key() -> bool:
    """One-row probe logged on startup so every deploy shows immediately whether
    DATA_GOV_API_KEY is authorised — turns a silent 403 into an obvious log line."""
    if not API_KEY:
        logger.error("🔑 DATA_GOV_API_KEY is not set — mandi fetch will be skipped.")
        return False
    try:
        res = requests.get(
            ENDPOINT,
            params={"api-key": API_KEY, "format": "json", "limit": 1},
            headers=HEADERS, timeout=30,
        )
    except requests.RequestException as e:
        logger.error(f"🔑 DATA_GOV_API_KEY check — request error: {e}")
        return False
    if res.status_code == 200:
        logger.info(f"🔑 DATA_GOV_API_KEY OK (ends …{API_KEY[-6:]}) — data.gov authorised.")
        return True
    logger.error(
        f"🔑 DATA_GOV_API_KEY REJECTED — HTTP {res.status_code}: "
        f"{res.text.strip()[:140]} (key len={len(API_KEY)}, ends …{API_KEY[-6:] or '∅'})"
    )
    return False


def fetch_and_store() -> dict:
    """Main entry point. Returns a small summary dict for logging/tests."""
    from backend.services.sync_log_service import record_sync

    started_at = datetime.utcnow()
    init_db()
    records, failed_states = _fetch_all_records()

    # SPARSE-FEED FALLBACK — data.gov wipes the live resource overnight and
    # refills it as mandis report, so an early run sees only a handful of rows
    # and (by the MIN_ROWS guard below) would leave the snapshot untouched:
    # empty on a cold start, days old after an outage. Top up from the archive
    # resource, which already holds yesterday complete.
    #
    # Live rows always win per market identity — the archive only fills markets
    # that have not reported yet today, so a market is never shown yesterday's
    # price when today's is already known, and the snapshot can never end up
    # with two rows for the same market.
    archive_day, archive_added, live_count = None, 0, len(records)
    if len(records) < MIN_ROWS:
        logger.warning(f"⚠️ Live feed sparse ({live_count} rows < MANDI_MIN_ROWS="
                       f"{MIN_ROWS}) — falling back to the archive resource.")
        arch, archive_day = fetch_archive_fallback()
        if arch:
            records, archive_added = merge_archive_rows(records, arch)
            logger.info(f"🗄️ Archive fallback: +{archive_added} rows from "
                        f"{archive_day:%d/%m/%Y} on top of {live_count} live "
                        f"rows → {len(records)} total.")

    db = SessionLocal()
    try:
        if not records:
            existing = db.query(MandiPrice).count()
            logger.warning(f"No records fetched. Keeping existing snapshot ({existing} rows).")
            record_sync(
                "mandi", "failed", 0,
                f"no records fetched — kept existing snapshot ({existing} rows)",
                started_at,
            )
            return {"fetched": 0, "snapshot": existing, "history_added": 0}

        # Normalise + enrich every record
        rows, group_keys, dts = [], set(), []
        for r in records:
            adate = _norm(r.get("arrival_date"))
            adt   = _parse_dt(adate)
            gk    = _group_key(r)
            rk    = hashlib.md5(f"{gk}|{adate}".encode("utf-8")).hexdigest()
            if adt:
                dts.append(adt)
            group_keys.add(gk)
            rows.append({
                "state":        _norm(r.get("state")),
                "district":     _norm(r.get("district")),
                "market":       _norm(r.get("market")),
                "commodity":    _norm(r.get("commodity")),
                "variety":      _norm(r.get("variety")),
                "grade":        _norm(r.get("grade")),
                "min_price":    _norm(r.get("min_price")),
                "max_price":    _norm(r.get("max_price")),
                "modal_price":  _norm(r.get("modal_price")),
                "arrival_date": adate,
                "arrival_dt":   adt,
                "group_key":    gk,
                "row_key":      rk,
            })

        # min(), not max(): on an archive-topped-up run the batch spans two
        # dates, and min() keeps the "previous price" strictly older than the
        # archive rows. With max() a yesterday row would find *itself* in
        # history and report a 0% change.
        before_dt = min(dts) if dts else None
        prev_map  = _prev_modal_map(db, group_keys, before_dt)

        # 1) Append to history (idempotent — skip rows already stored for that date)
        now = datetime.utcnow()
        history_added = 0
        CHUNK = 1000
        for i in range(0, len(rows), CHUNK):
            chunk = [{**x, "fetched_at": now} for x in rows[i:i + CHUNK]]
            stmt = pg_insert(MandiPriceHistory.__table__).values(chunk)
            stmt = stmt.on_conflict_do_nothing(index_elements=["row_key"])
            res = db.execute(stmt)
            history_added += (res.rowcount or 0)
        db.commit()

        # 1a) Last-seen — one permanent row per (mandi × crop), updated only when
        # the incoming row is at least as new. This is what makes the trim below
        # safe: the page index and the stale-district rescue read from here, so
        # a district that stops reporting keeps its URL and its last known price
        # no matter how short retention gets. See MandiLastSeen in database/db.
        last_seen_n = 0
        _ls = MandiLastSeen.__table__.c
        for i in range(0, len(rows), CHUNK):
            chunk = [{k: v for k, v in x.items() if k != "row_key"}
                     for x in rows[i:i + CHUNK] if x.get("group_key")]
            if not chunk:
                continue
            stmt = pg_insert(MandiLastSeen.__table__).values(
                [{**x, "updated_at": now} for x in chunk])
            stmt = stmt.on_conflict_do_update(
                index_elements=["group_key"],
                set_={
                    "state":        stmt.excluded.state,
                    "district":     stmt.excluded.district,
                    "market":       stmt.excluded.market,
                    "commodity":    stmt.excluded.commodity,
                    "variety":      stmt.excluded.variety,
                    "grade":        stmt.excluded.grade,
                    "min_price":    stmt.excluded.min_price,
                    "max_price":    stmt.excluded.max_price,
                    "modal_price":  stmt.excluded.modal_price,
                    "arrival_date": stmt.excluded.arrival_date,
                    "arrival_dt":   stmt.excluded.arrival_dt,
                    "updated_at":   stmt.excluded.updated_at,
                },
                # Two jobs for this predicate:
                #  • never let a late-arriving OLD row overwrite a newer price;
                #  • never rewrite a row that has not changed. The fetch runs
                #    6×/day and mostly re-reads the same rows, so a plain
                #    `>=` would rewrite all ~31k rows six times a day. Each
                #    rewrite is a new row version the storage cap counts, which
                #    is the whole problem we are here to fix. Same-day updates
                #    still land — but only when a price actually moved.
                where=(_ls.arrival_dt.is_(None)) |
                      (stmt.excluded.arrival_dt > _ls.arrival_dt) |
                      ((stmt.excluded.arrival_dt == _ls.arrival_dt) &
                       (stmt.excluded.modal_price.is_distinct_from(_ls.modal_price) |
                        stmt.excluded.min_price.is_distinct_from(_ls.min_price) |
                        stmt.excluded.max_price.is_distinct_from(_ls.max_price))),
            )
            res = db.execute(stmt)
            last_seen_n += (res.rowcount or 0)
        db.commit()
        if last_seen_n:
            logger.info(f"📌 last-seen rows touched: {last_seen_n}")

        # 1b) Retention — drop history older than HISTORY_DAYS (keeps table flat).
        if HISTORY_DAYS > 0:
            cutoff = date.today() - timedelta(days=HISTORY_DAYS)
            trim = db.execute(
                text("DELETE FROM mandi_price_history "
                     "WHERE arrival_dt IS NOT NULL AND arrival_dt < :cutoff"),
                {"cutoff": cutoff},
            )
            db.commit()
            if trim.rowcount:
                logger.info(f"🧹 Trimmed {trim.rowcount} history rows older than "
                            f"{cutoff} ({HISTORY_DAYS}d retention).")

        # SPARSE-FEED GUARD — keep whatever rows came in as history (they're
        # real and dedupe against the later full fetch), but never let a
        # near-empty run touch the snapshot or bump fetched_at: keeping
        # fetched_at old leaves the staleness watchdog armed, so the fetch
        # simply retries once the feed has actually filled up.
        if len(rows) < MIN_ROWS:
            existing = db.query(MandiPrice).count()
            logger.warning(
                f"⚠️ Feed sparse: only {len(rows)} rows (< MANDI_MIN_ROWS={MIN_ROWS}), "
                f"archive fallback added {archive_added} — keeping existing snapshot "
                f"({existing} rows), history +{history_added}."
            )
            record_sync(
                "mandi", "partial", len(rows),
                f"feed sparse ({len(rows)} rows < {MIN_ROWS}, archive added "
                f"{archive_added}) — kept snapshot ({existing} rows), "
                f"+{history_added} history; will refetch when feed fills",
                started_at,
            )
            return {"fetched": len(rows), "snapshot": existing,
                    "history_added": history_added, "sparse": True,
                    "archive_added": archive_added}

        # Recent price series per group (includes the day we just inserted)
        spark_map = _spark_map(db, group_keys)

        # 2) MERGE into the latest snapshot (upsert per market/commodity
        #    identity), with day-over-day deltas + sparkline series. The feed
        #    refills through the day, so an early fetch only carries what
        #    mandis have reported so far — the old delete-whole-state rebuild
        #    gutted the page every morning (e.g. UP down to 9 rows at 09:38
        #    on 2026-07-10). Instead: replace only rows whose identity
        #    re-appeared in this fetch; every other market keeps its last
        #    known price until it reports again (aged out after
        #    SNAPSHOT_KEEP_DAYS). No wholesale delete also means rows from
        #    states whose fetch hard-failed midway are safe to merge — a
        #    fetch can now only improve the snapshot, never shrink it.
        fetched_keys   = {x["group_key"] for x in rows}
        touched_states = {x["state"] for x in rows}
        stale_ids = []
        existing_q = db.query(
            MandiPrice.id, MandiPrice.state, MandiPrice.district,
            MandiPrice.market, MandiPrice.commodity, MandiPrice.variety,
            MandiPrice.grade,
        ).filter(MandiPrice.state.in_(touched_states))
        for rid, st, di, mk, co, va, gr in existing_q:
            gk = _group_key({"state": st, "district": di, "market": mk,
                             "commodity": co, "variety": va, "grade": gr})
            if gk in fetched_keys:
                stale_ids.append(rid)
        CHUNK_IDS = 5000
        for i in range(0, len(stale_ids), CHUNK_IDS):
            db.query(MandiPrice).filter(
                MandiPrice.id.in_(stale_ids[i:i + CHUNK_IDS])
            ).delete(synchronize_session=False)
        snapshot = []
        for x in rows:
            prev = prev_map.get(x["group_key"])
            snapshot.append({
                "state":            x["state"],
                "commodity":        x["commodity"],
                "district":         x["district"],
                "market":           x["market"],
                "variety":          x["variety"],
                "grade":            x["grade"],
                "min_price":        x["min_price"],
                "max_price":        x["max_price"],
                "modal_price":      x["modal_price"],
                "prev_modal_price": prev,
                "change_pct":       _change_pct(x["modal_price"], prev),
                "spark":            spark_map.get(x["group_key"]),
                "arrival_date":     x["arrival_date"],
                "fetched_at":       now,
            })
        db.bulk_insert_mappings(MandiPrice, snapshot)

        # Age out rows never refreshed recently (market stopped reporting for
        # a week+) so last-known prices don't linger forever.
        db.query(MandiPrice).filter(
            MandiPrice.fetched_at < now - timedelta(days=SNAPSHOT_KEEP_DAYS)
        ).delete(synchronize_session=False)
        db.commit()

        logger.info(
            f"✅ Mandi fetch done | fetched={len(rows)} "
            f"(live={live_count} archive={archive_added}) "
            f"merged={len(snapshot)} (updated {len(stale_ids)}) "
            f"history_added={history_added} failed_states={len(failed_states)}"
        )
        # An archive-topped-up run is reported as "partial": the snapshot is
        # complete and correct, but it is carrying yesterday's prices for the
        # markets that had not reported yet, and that should be visible in the
        # admin sync log rather than looking like a clean live fetch.
        status = "partial" if (failed_states or archive_added) else "success"
        detail = (f"{len(rows)} rows merged into snapshot "
                  f"({len(stale_ids)} updated), +{history_added} history")
        if archive_added:
            detail += (f" — live feed sparse ({live_count} rows), "
                       f"+{archive_added} from archive "
                       f"{archive_day:%d/%m/%Y}")
        if failed_states:
            detail += f" — {len(failed_states)} state(s) incomplete"
        record_sync("mandi", status, len(rows), detail, started_at)
        return {"fetched": len(rows), "snapshot": len(snapshot),
                "replaced": len(stale_ids), "history_added": history_added,
                "failed_states": sorted(failed_states),
                "live": live_count, "archive_added": archive_added,
                "archive_day": archive_day.isoformat() if archive_day else None}

    except Exception as e:
        db.rollback()
        logger.error(f"❌ fetch_and_store failed: {e}")
        record_sync("mandi", "failed", 0, f"fetch_and_store crashed: {e}", started_at)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    # `--archive-probe [YYYY-MM-DD]` exercises the archive path ONLY: it fetches
    # and reports, and never touches the database. Use it to confirm the
    # fallback still works after a data.gov schema change, without waiting for
    # a real sparse morning.
    if "--archive-probe" in sys.argv:
        args = [a for a in sys.argv[1:] if not a.startswith("-")]
        if args:                                  # explicit day
            day  = date.fromisoformat(args[0])
            recs = _fetch_archive_day(day)
        else:                                     # whatever the fallback would pick
            recs, day = fetch_archive_fallback()
        states = sorted({_norm(r.get("state")) for r in recs})
        logger.info(f"\narchive day : {day}")
        logger.info(f"rows        : {len(recs)}")
        logger.info(f"states      : {len(states)}")
        logger.info(f"usable      : {len(recs) >= MIN_ROWS} (MIN_ROWS={MIN_ROWS})")
        if recs:
            logger.info(f"sample      : {recs[0]}")
        sys.exit(0)

    logger.info(fetch_and_store())
