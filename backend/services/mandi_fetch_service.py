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
import hashlib
import logging
from datetime import datetime, date

import requests
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.database.db import (
    SessionLocal, init_db, MandiPrice, MandiPriceHistory,
)

load_dotenv()

logger = logging.getLogger("krishi.mandi_fetch")

API_KEY = os.getenv("DATA_GOV_API_KEY", "")

# Variety-wise Daily Market Prices Data of Commodity (Agmarknet)
RESOURCE_ID = "9ef84268-d588-465a-a308-a864a43d0070"
ENDPOINT    = f"https://api.data.gov.in/resource/{RESOURCE_ID}"

PAGE_LIMIT = 1000      # rows per request
MAX_PAGES  = 60        # safety cap → up to 60k rows / run
TIMEOUT    = 120       # seconds per request


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

def _fetch_all_records() -> list:
    """Page through the data.gov resource and return all records (nationwide)."""
    if not API_KEY:
        logger.error("DATA_GOV_API_KEY not set — cannot fetch mandi prices.")
        return []

    all_records, offset = [], 0
    for page in range(MAX_PAGES):
        params = {
            "api-key": API_KEY,
            "format":  "json",
            "limit":   PAGE_LIMIT,
            "offset":  offset,
        }
        try:
            res = requests.get(ENDPOINT, params=params, timeout=TIMEOUT)
        except Exception as e:
            logger.error(f"Request failed at offset={offset}: {e}")
            break

        if res.status_code != 200 or not res.text.strip():
            logger.error(f"Bad response at offset={offset}: HTTP {res.status_code}")
            break

        recs = res.json().get("records", [])
        if not recs:
            break

        all_records.extend(recs)
        logger.info(f"📥 page {page + 1}: +{len(recs)} (total {len(all_records)})")

        if len(recs) < PAGE_LIMIT:
            break
        offset += PAGE_LIMIT

    return all_records


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


def fetch_and_store() -> dict:
    """Main entry point. Returns a small summary dict for logging/tests."""
    init_db()
    records = _fetch_all_records()

    db = SessionLocal()
    try:
        if not records:
            existing = db.query(MandiPrice).count()
            logger.warning(f"No records fetched. Keeping existing snapshot ({existing} rows).")
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

        # Recent price series per group (includes the day we just inserted)
        spark_map = _spark_map(db, group_keys)

        # 2) Rebuild latest snapshot with day-over-day deltas + sparkline series
        db.query(MandiPrice).delete()
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
        db.commit()

        logger.info(
            f"✅ Mandi fetch done | fetched={len(rows)} "
            f"snapshot={len(snapshot)} history_added={history_added}"
        )
        return {"fetched": len(rows), "snapshot": len(snapshot), "history_added": history_added}

    except Exception as e:
        db.rollback()
        logger.error(f"❌ fetch_and_store failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(fetch_and_store())
