# ============================================================
# services/mandi_service.py
# Krishi Mitra — Mandi Price Service
# ------------------------------------------------------------
# Reads the latest snapshot from PostgreSQL (mandi_prices),
# populated by the daily auto-fetcher (mandi_fetch_service.py).
# Falls back to the bundled JSON seed when the DB is still empty
# (e.g. before the first scheduled fetch completes).
# Also serves day-over-day deltas and full price history.
# ============================================================

import json
import os
import logging

from sqlalchemy import func

from backend.database.db import SessionLocal, MandiPrice, MandiPriceHistory

logger = logging.getLogger("krishi.mandi_service")

# ── JSON seed (lazy fallback only) ───────────────────────────
_json_path = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "data",
    "crop_mandi_price.json",
)
_json_cache = None


def _json_records() -> list:
    global _json_cache
    if _json_cache is None:
        try:
            with open(_json_path, "r", encoding="utf-8") as f:
                _json_cache = json.load(f).get("records", [])
        except Exception as e:
            logger.warning(f"Could not load JSON seed: {e}")
            _json_cache = []
    return _json_cache


def _row_to_dict(r: MandiPrice) -> dict:
    return {
        "market":           r.market or "-",
        "district":         r.district or "-",
        "state":            r.state or "-",
        "commodity":        r.commodity or "-",
        "variety":          r.variety or "-",
        "grade":            r.grade or "-",
        "min_price":        str(r.min_price or "-"),
        "max_price":        str(r.max_price or "-"),
        "modal_price":      str(r.modal_price or "-"),
        "prev_modal_price": (str(r.prev_modal_price) if r.prev_modal_price else None),
        "change_pct":       r.change_pct,
        "spark":            ([p for p in r.spark.split(",") if p] if r.spark else []),
        "date":             r.arrival_date or "-",
    }


def _json_to_dict(r: dict) -> dict:
    return {
        "market":           r.get("market", "-"),
        "district":         r.get("district", "-"),
        "state":            r.get("state", "-"),
        "commodity":        r.get("commodity", "-"),
        "variety":          r.get("variety", "-"),
        "grade":            r.get("grade", "-"),
        "min_price":        str(r.get("min_price", "-")),
        "max_price":        str(r.get("max_price", "-")),
        "modal_price":      str(r.get("modal_price", "-")),
        "prev_modal_price": None,
        "change_pct":       None,
        "spark":            [],
        "date":             r.get("arrival_date", "-"),
    }


# ── Public API ───────────────────────────────────────────────

def get_mandi_prices(commodity: str, district: str, state: str) -> dict:
    db = SessionLocal()
    try:
        q = db.query(MandiPrice)
        # func.lower(col) == value.lower(), NOT .ilike(value) — this is the query
        # mandi_prices_csd_lower_idx (db.py) exists to serve, and Postgres only
        # matches a lower()-expression index against a literal `lower(col) = ...`
        # clause, never against ILIKE (even with no wildcards). Written as .ilike(),
        # this ran a full table scan on mandi.html's live price lookups regardless
        # of the index. See the identical fix + writeup in routes/bhav.py _rows_for().
        if commodity:
            q = q.filter(func.lower(MandiPrice.commodity) == commodity.lower())
        if state:
            q = q.filter(func.lower(MandiPrice.state) == state.lower())
        if district:
            q = q.filter(func.lower(MandiPrice.district) == district.lower())

        limit = 50 if commodity else 150
        rows  = q.limit(limit).all()

        if rows:
            return {"commodity": commodity or "all",
                    "prices": [_row_to_dict(r) for r in rows]}

        # If the snapshot table has ANY data, an empty result is a true "no match"
        if db.query(MandiPrice.id).first():
            return {"commodity": commodity or "all", "prices": [], "message": "No data found"}
    finally:
        db.close()

    # ── DB empty → JSON seed fallback ──
    records  = _json_records()
    filtered = records
    if commodity:
        filtered = [r for r in filtered if r.get("commodity", "").lower() == commodity.lower()]
    if state:
        filtered = [r for r in filtered if r.get("state", "").lower() == state.lower()]
    if district:
        filtered = [r for r in filtered if r.get("district", "").lower() == district.lower()]
    if not filtered:
        return {"commodity": commodity or "all", "prices": [], "message": "No data found"}
    limit = 50 if commodity else 150
    return {"commodity": commodity or "all",
            "prices": [_json_to_dict(r) for r in filtered[:limit]]}


def get_states() -> dict:
    db = SessionLocal()
    try:
        rows = db.query(MandiPrice.state).distinct().all()
        states = sorted({s[0] for s in rows if s[0]})
        if states:
            return {"states": states}
    finally:
        db.close()
    records = _json_records()
    return {"states": sorted({r.get("state", "") for r in records if r.get("state")})}


def get_districts(state: str) -> dict:
    db = SessionLocal()
    try:
        rows = (db.query(MandiPrice.district)
                  .filter(MandiPrice.state.ilike(state))
                  .distinct().all())
        districts = sorted({d[0] for d in rows if d[0]})
        if districts:
            return {"districts": districts}
        if db.query(MandiPrice.id).first():
            return {"districts": []}
    finally:
        db.close()
    records  = _json_records()
    filtered = [r for r in records if r.get("state", "").lower() == state.lower()]
    return {"districts": sorted({r.get("district", "") for r in filtered if r.get("district")})}


def get_commodities(state: str) -> dict:
    db = SessionLocal()
    try:
        q = db.query(MandiPrice.commodity)
        if state:
            q = q.filter(MandiPrice.state.ilike(state))
        rows = q.distinct().all()
        commodities = sorted({c[0] for c in rows if c[0]})
        if commodities:
            return {"commodities": commodities}
        if db.query(MandiPrice.id).first():
            return {"commodities": []}
    finally:
        db.close()
    records  = _json_records()
    filtered = [r for r in records if r.get("state", "").lower() == state.lower()] if state else records
    return {"commodities": sorted({r.get("commodity", "") for r in filtered if r.get("commodity")})}


def get_price_history(commodity: str, market: str = "", district: str = "",
                      state: str = "", variety: str = "", days: int = 60) -> dict:
    """
    Day-over-day price trend for a specific commodity at a market.
    Returns chronological points for the detail-sheet chart.
    """
    db = SessionLocal()
    try:
        q = db.query(MandiPriceHistory)
        if commodity:
            q = q.filter(MandiPriceHistory.commodity.ilike(commodity))
        if market:
            q = q.filter(MandiPriceHistory.market.ilike(market))
        if district:
            q = q.filter(MandiPriceHistory.district.ilike(district))
        if state:
            q = q.filter(MandiPriceHistory.state.ilike(state))
        if variety:
            q = q.filter(MandiPriceHistory.variety.ilike(variety))

        rows = (q.filter(MandiPriceHistory.arrival_dt.isnot(None))
                 .order_by(MandiPriceHistory.arrival_dt.desc())
                 .limit(days)
                 .all())
        rows = list(reversed(rows))   # chronological ascending

        points = [{
            "date":        r.arrival_date or "-",
            "iso":         r.arrival_dt.isoformat() if r.arrival_dt else None,
            "modal_price": str(r.modal_price or ""),
            "min_price":   str(r.min_price or ""),
            "max_price":   str(r.max_price or ""),
        } for r in rows]

        return {"commodity": commodity, "market": market, "points": points}
    finally:
        db.close()
