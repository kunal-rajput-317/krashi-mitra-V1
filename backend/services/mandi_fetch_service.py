# ============================================================
# backend/services/mandi_fetch_service.py
# KrashiMitra — Mandi Price Auto-Fetcher
# ------------------------------------------------------------
# Pulls the full nationwide Agmarknet dataset from data.gov.in,
# rebuilds the "latest snapshot" table (mandi_prices) and appends
# to an append-only history table (mandi_price_history).
# History is never auto-purged, enabling previous-price trends.
#
# Designed to be called by the APScheduler job (daily) and also
# runnable manually:  python -m backend.services.mandi_fetch_service
# ============================================================

import os
import time
import hashlib
import logging
from datetime import datetime, date, timedelta

import requests
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.database.db import (
    SessionLocal, init_db, MandiPrice, MandiPriceHistory,
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
# fetch so it doesn't grow unbounded (~14 MB/day). 0 = keep forever.
HISTORY_DAYS = int(os.getenv("MANDI_HISTORY_DAYS", "90"))

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
    "Uttrakhand", "West Bengal", "Andaman and Nicobar Islands", "Chandigarh",
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

def _get_page(params: dict, label: str) -> list | None:
    """
    GET one page with retry+backoff on transient (5xx / network) errors.
    Returns the list of records, or None if the page ultimately failed
    (so the caller can distinguish "empty" from "error").
    """
    for attempt in range(MAX_RETRIES):
        try:
            res = requests.get(ENDPOINT, params=params, headers=HEADERS, timeout=TIMEOUT)
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

        # Recent price series per group (includes the day we just inserted)
        spark_map = _spark_map(db, group_keys)

        # 2) Refresh the latest snapshot PER STATE with day-over-day deltas +
        #    sparkline series. States whose fetch hard-failed midway keep their
        #    existing snapshot rows — a wholesale delete-and-rebuild used to
        #    wipe good data whenever data.gov flaked mid-run (e.g. a run that
        #    got only 20 of 30 states replaced the whole nationwide snapshot).
        complete_rows = [x for x in rows if x["state"] not in failed_states]
        states_to_replace = {x["state"] for x in complete_rows}
        if states_to_replace:
            db.query(MandiPrice).filter(
                MandiPrice.state.in_(states_to_replace)
            ).delete(synchronize_session=False)
        snapshot = []
        for x in complete_rows:
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

        # Age out rows never refreshed recently (state kept on failure but
        # then absent from the feed for a week+) so they don't linger forever.
        db.query(MandiPrice).filter(
            MandiPrice.fetched_at < now - timedelta(days=SNAPSHOT_KEEP_DAYS)
        ).delete(synchronize_session=False)
        db.commit()

        logger.info(
            f"✅ Mandi fetch done | fetched={len(rows)} "
            f"snapshot_inserted={len(snapshot)} history_added={history_added} "
            f"failed_states={len(failed_states)}"
        )
        status = "partial" if failed_states else "success"
        detail = f"{len(rows)} rows, {len(snapshot)} snapshot, +{history_added} history"
        if failed_states:
            detail += f" — {len(failed_states)} state(s) incomplete"
        record_sync("mandi", status, len(rows), detail, started_at)
        return {"fetched": len(rows), "snapshot": len(snapshot),
                "history_added": history_added, "failed_states": sorted(failed_states)}

    except Exception as e:
        db.rollback()
        logger.error(f"❌ fetch_and_store failed: {e}")
        record_sync("mandi", "failed", 0, f"fetch_and_store crashed: {e}", started_at)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(fetch_and_store())
