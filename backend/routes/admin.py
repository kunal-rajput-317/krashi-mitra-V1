import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import shutil, secrets, json
from sqlalchemy.orm import Session

router   = APIRouter(prefix="/admin")
security = HTTPBasic()

ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "krashi2025")

UPLOAD_DIR = Path(__file__).parent.parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


def require_admin(creds: HTTPBasicCredentials = Depends(security)):
    ok_user = secrets.compare_digest(creds.username.encode(), ADMIN_USER.encode())
    ok_pass = secrets.compare_digest(creds.password.encode(), ADMIN_PASS.encode())
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return creds.username


def admin_db():
    from backend.database.db import get_db
    yield from get_db()


# ── System Status ─────────────────────────────────────────────

@router.get("/status")
async def system_status(_: str = Depends(require_admin)):
    from backend.config import get_all_settings, ALLOWED_GEMINI_MODELS

    gemini_keys = [
        os.getenv(name, "").strip()
        for name in (
            "GEMINI_API_KEY",
            "GEMINI_API_KEY2",  "GEMINI_API_KEY_2",
            "GEMINI_API_KEY3",  "GEMINI_API_KEY_3",
        )
    ]

    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    ollama_ok = False
    try:
        import httpx
        r = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=2)
        ollama_ok = r.status_code == 200
    except Exception:
        pass

    chroma_count = 0
    try:
        from rag.indexer import get_collection
        chroma_count = get_collection().count()
    except Exception:
        pass

    cache_count = 0
    try:
        from cache.cache_engine import get_cache_stats
        cache_count = get_cache_stats()["total_entries"]
    except Exception:
        pass

    settings = get_all_settings()

    return {
        "gemini_configured":    any(gemini_keys),
        "gemini_keys_count":    sum(1 for k in gemini_keys if k),
        "ollama_running":       ollama_ok,
        "ollama_model":         settings.get("ollama_model", "—"),
        "chroma_chunks":        chroma_count,
        "cache_entries":        cache_count,
        "upload_dir":           str(UPLOAD_DIR),
        "checked_at":           datetime.now().strftime("%d %b %Y %H:%M:%S"),
        # current runtime pipeline config
        "current_model":        settings.get("gemini_model"),
        "semantic_cache":       settings.get("cache_semantic_enabled"),
        "ollama_enabled":       settings.get("ollama_enabled"),
        "pipeline_timeout":     settings.get("pipeline_timeout"),
        "gemini_timeout":       settings.get("gemini_timeout"),
        "allowed_models":       ALLOWED_GEMINI_MODELS,
    }


# ── Data Sync Log ─────────────────────────────────────────────

@router.get("/sync-log")
async def sync_log(
    limit: int = Query(40, ge=1, le=200),
    source: str | None = Query(None, description="mandi | weather"),
    _: str = Depends(require_admin),
):
    """
    Audit trail of mandi/weather data fetches — when each ran, whether it
    succeeded, how many rows came in. Powers the admin 'Data Sync Log' panel.
    """
    from backend.services.sync_log_service import get_recent, get_summary
    return {
        "success": True,
        "summary": get_summary(),          # latest run per source
        "runs":    get_recent(limit, source),
    }


# ── Manual data-fetch trigger ─────────────────────────────────

# Each source's registered APScheduler job (module, job_id). Triggering runs
# through the job (next_run_time=now) instead of calling the fetch directly, so
# it reuses the job's max_instances=1 guard (no overlap with the scheduled run)
# and executes in the scheduler's background thread — the HTTP call returns at
# once and the result lands in the Data Sync Log a minute or two later.
_FETCH_JOBS = {
    "mandi":   ("backend.services.mandi_scheduler",   "mandi_price_refresh"),
    "weather": ("backend.services.weather_scheduler", "weather_cache_refresh"),
}


@router.post("/fetch/{source}")
async def trigger_fetch(source: str, _: str = Depends(require_admin)):
    """
    Manually kick off a mandi or weather data fetch from the admin panel.

    Note the data.gov mandi feed is wiped overnight and refills through the
    day (scheduled runs: 08/10/13/16/20h IST) — a manual fetch can only get
    what mandis have reported so far. That's always safe: results are MERGED
    into the snapshot per market, and near-empty results are discarded by
    the sparse-feed guard.
    """
    import importlib
    import pytz

    if source not in _FETCH_JOBS:
        raise HTTPException(400, "source must be 'mandi' or 'weather'")

    module_path, job_id = _FETCH_JOBS[source]
    scheduler = getattr(importlib.import_module(module_path), "scheduler", None)
    job = scheduler.get_job(job_id) if scheduler else None
    if job is None:
        raise HTTPException(503, f"{source} scheduler is not running — cannot trigger a fetch")

    now_ist = datetime.now(pytz.timezone("Asia/Kolkata"))
    job.modify(next_run_time=now_ist)
    return {
        "status":       "triggered",
        "source":       source,
        "message":      f"{source.title()} fetch started in the background — "
                        f"refresh the sync log in a minute to see the result.",
        "triggered_at": now_ist.strftime("%d %b %Y, %I:%M %p IST"),
    }


# ── Runtime Settings ──────────────────────────────────────────

@router.get("/settings")
async def get_settings(_: str = Depends(require_admin)):
    """Return all runtime-configurable settings."""
    from backend.config import get_all_settings, ALLOWED_GEMINI_MODELS
    return {
        "settings": get_all_settings(),
        "allowed_models": ALLOWED_GEMINI_MODELS,
    }


@router.post("/settings")
async def update_settings(payload: dict, _: str = Depends(require_admin)):
    """
    Update one or more runtime settings.
    Changes take effect immediately (no restart needed).
    Changes are lost on server restart — set env vars for persistence.
    """
    from backend.config import update_setting, get_all_settings, ALLOWED_GEMINI_MODELS

    if "gemini_model" in payload:
        model = payload["gemini_model"]
        if model not in ALLOWED_GEMINI_MODELS:
            raise HTTPException(400, f"Unknown model. Allowed: {ALLOWED_GEMINI_MODELS}")

    updated = {}
    skipped = []
    for key, value in payload.items():
        if update_setting(key, value):
            updated[key] = value
        else:
            skipped.append(key)

    # If semantic cache toggled on, reload cache model lazily (happens on next request)
    return {
        "updated": updated,
        "skipped": skipped,
        "settings": get_all_settings(),
    }


# ── PDF Upload ────────────────────────────────────────────────

@router.post("/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    _: str = Depends(require_admin),
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are allowed")

    dest = UPLOAD_DIR / file.filename
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    indexed = 0
    try:
        from rag.indexer import get_collection, index_pdf
        indexed = index_pdf(get_collection(), dest)
    except Exception:
        pass  # file is saved; admin can re-index manually

    return {
        "status":         "uploaded",
        "filename":       file.filename,
        "chunks_indexed": indexed,
        "saved_at":       datetime.now().isoformat(),
    }


@router.get("/files")
async def list_files(_: str = Depends(require_admin)):
    files = []
    for f in UPLOAD_DIR.glob("*.pdf"):
        stat = f.stat()
        files.append({
            "name":        f.name,
            "size_kb":     round(stat.st_size / 1024, 1),
            "uploaded_at": datetime.fromtimestamp(stat.st_mtime).strftime("%d %b %Y %H:%M"),
        })
    return {"files": files, "count": len(files)}


@router.delete("/files/{filename}")
async def delete_file(filename: str, _: str = Depends(require_admin)):
    target = UPLOAD_DIR / filename
    if not target.exists():
        raise HTTPException(404, "File not found")
    target.unlink()
    return {"status": "deleted", "filename": filename}


# ── Cache Management ──────────────────────────────────────────

@router.get("/cache/stats")
async def cache_stats(_: str = Depends(require_admin)):
    try:
        from cache.cache_engine import get_cache_stats
        stats = get_cache_stats()
        for q in stats.get("top_questions", []):
            q.pop("embedding", None)
        return stats
    except Exception as e:
        return {"error": str(e)}


@router.delete("/cache/clear")
async def clear_cache(_: str = Depends(require_admin)):
    try:
        from cache.cache_engine import clear_cache
        count = clear_cache()
        return {"status": "cleared", "deleted_entries": count}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/cache/delete")
async def delete_cache_entry(payload: dict, _: str = Depends(require_admin)):
    """Delete a specific cache entry by question text."""
    question = payload.get("question", "").strip()
    if not question:
        raise HTTPException(400, "question required")
    try:
        from cache.cache_engine import _load, _save
        entries = _load()
        original_len = len(entries)
        entries = [e for e in entries if e.get("question", "").strip() != question]
        if len(entries) == original_len:
            return {"deleted": False, "message": "Entry not found"}
        _save(entries)
        return {"deleted": True, "remaining": len(entries)}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.put("/cache/edit")
async def edit_cache_entry(payload: dict, _: str = Depends(require_admin)):
    """Update the answer of a specific cache entry."""
    question   = payload.get("question", "").strip()
    new_answer = payload.get("new_answer", "").strip()
    if not question or not new_answer:
        raise HTTPException(400, "question and new_answer required")
    try:
        from cache.cache_engine import _load, _save
        entries = _load()
        updated = False
        for entry in entries:
            if entry.get("question", "").strip() == question:
                entry["answer"] = new_answer
                updated = True
                break
        if not updated:
            return {"updated": False, "message": "Entry not found"}
        _save(entries)
        return {"updated": True}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/cache/add")
async def add_cache_entry(payload: dict, _: str = Depends(require_admin)):
    """Manually add a Q&A pair to the cache from the admin panel."""
    question = payload.get("question", "").strip()
    answer   = payload.get("answer",   "").strip()
    source   = payload.get("source",   "manual").strip() or "manual"

    if not question:
        raise HTTPException(400, "question required")
    if len(answer) < 20:
        raise HTTPException(400, "answer too short (min 20 chars)")

    try:
        from cache.cache_engine import save_to_cache, search_cache
        saved = save_to_cache(question, answer, source=source)
        if saved:
            return {"saved": True}
        hit = search_cache(question)
        if hit:
            return {"saved": False, "duplicate": True}
        return {"saved": False, "reason": "quality check failed"}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/cache/search")
async def search_cache_test(payload: dict, _: str = Depends(require_admin)):
    """
    Test whether a question would hit the cache.
    Returns the match result without saving anything.
    """
    question = payload.get("question", "").strip()
    if not question:
        raise HTTPException(400, "question required")
    try:
        from cache.cache_engine import search_cache
        result = search_cache(question)
        if result:
            result.pop("embedding", None)
        return {
            "hit":    result is not None,
            "result": result,
        }
    except Exception as e:
        raise HTTPException(500, str(e))


# ── RAG Re-index ──────────────────────────────────────────────

@router.post("/reindex")
async def reindex(_: str = Depends(require_admin)):
    try:
        from rag.indexer import run_indexing
        total = run_indexing(force=True)
        return {"status": "reindexed", "total_chunks": total}
    except Exception as e:
        raise HTTPException(500, str(e))


# ── Regional Heatmap stats ─────────────────────────────────────

# Admin order operations -----------------------------------------------------

def _order_to_dict(o):
    return {
        "id":            o.id,
        "tracking_code": o.tracking_code,
        "user_id":       o.user_id,
        "user_email":    o.user_email,
        "user_name":     o.user_name,
        "is_guest":      o.is_guest,
        "session_id":    o.session_id,
        "product_name":  o.product_name,
        "product_id":    o.product_id,
        "quantity":      o.quantity,
        "unit_price":    o.unit_price,
        "total":         o.total,
        "phone":         o.phone,
        "source":        o.source,
        "status":        o.status,
        "created_at":    o.created_at.isoformat() if o.created_at else "",
        "customer_name": o.customer_name,
        "pincode":       o.pincode,
        "quote_total":   o.quote_total,
        "delivery_info": o.delivery_info,
        "dealer_name":   o.dealer_name,
        "quote_note":    o.quote_note,
        "quoted_at":     o.quoted_at.isoformat() if o.quoted_at else None,
    }


@router.get("/orders")
async def list_admin_orders(
    limit: int = Query(100, ge=1, le=500),
    source: str | None = Query(None),
    status: str | None = Query(None),
    _: str = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    from backend.database.db import Order

    q = db.query(Order)
    if source:
        q = q.filter(Order.source == source)
    if status:
        q = q.filter(Order.status == status)

    rows = q.order_by(Order.created_at.desc()).limit(limit).all()
    return {
        "success": True,
        "total": len(rows),
        "orders": [_order_to_dict(o) for o in rows],
    }


@router.put("/orders/{tracking_code}/quote")
async def quote_admin_order(
    tracking_code: str,
    payload: dict,
    _: str = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    from backend.database.db import Order

    try:
        quote_total = float(payload.get("quote_total"))
    except (TypeError, ValueError):
        raise HTTPException(400, "quote_total must be a number")

    delivery_info = (payload.get("delivery_info") or "").strip()
    if not delivery_info:
        raise HTTPException(400, "delivery_info required")

    order = db.query(Order).filter(Order.tracking_code == tracking_code).first()
    if not order:
        raise HTTPException(404, f"Order {tracking_code} not found")

    order.quote_total = quote_total
    order.delivery_info = delivery_info
    order.dealer_name = (payload.get("dealer_name") or "").strip() or None
    order.quote_note = (payload.get("quote_note") or "").strip() or None
    order.status = "Quoted"
    order.quoted_at = datetime.utcnow()
    db.commit()
    db.refresh(order)

    return {
        "success": True,
        "tracking_code": order.tracking_code,
        "status": order.status,
        "quote_total": order.quote_total,
        "order": _order_to_dict(order),
    }


@router.put("/orders/{tracking_code}/status")
async def update_admin_order_status(
    tracking_code: str,
    payload: dict,
    _: str = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    from backend.database.db import Order

    valid_statuses = {
        "Pending", "Booked", "Quoted", "Purchased",
        "Dispatched", "Delivered", "Cancelled", "Unavailable",
    }
    next_status = (payload.get("status") or "").strip()
    if next_status not in valid_statuses:
        raise HTTPException(400, f"Invalid status. Use: {', '.join(sorted(valid_statuses))}")

    order = db.query(Order).filter(Order.tracking_code == tracking_code).first()
    if not order:
        raise HTTPException(404, f"Order {tracking_code} not found")

    old_status = order.status
    order.status = next_status
    db.commit()
    db.refresh(order)

    return {
        "success": True,
        "tracking_code": order.tracking_code,
        "old_status": old_status,
        "new_status": order.status,
        "order": _order_to_dict(order),
    }


@router.get("/heatmap")
async def get_admin_heatmap(
    _: str = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    from backend.database.db import Order

    try:
        orders = db.query(Order).all()

        tracked_states = [
            "Uttar Pradesh", "Maharashtra", "Rajasthan", "Gujarat",
            "Madhya Pradesh", "Punjab", "Haryana", "Karnataka", "Bihar",
            "West Bengal", "Tamil Nadu", "Odisha", "Andhra Pradesh",
            "Telangana", "Kerala", "Jammu and Kashmir", "Ladakh", "Assam",
            "Delhi", "Uttarakhand", "Jharkhand", "Chhattisgarh",
        ]
        state_demand = {
            state: {"state": state, "demand": 0, "delivered": 0, "not_available": 0}
            for state in tracked_states
        }

        grid = {
            "Meerut":    [0] * 12,
            "Lucknow":   [0] * 12,
            "Varanasi":  [0] * 12,
            "Aligarh":   [0] * 12,
            "Bareilly":  [0] * 12,
            "Gorakhpur": [0] * 12,
            "Kanpur":    [0] * 12,
            "Other":     [0] * 12,
        }

        def state_from_pincode(pincode: str | None) -> str:
            digits = "".join(ch for ch in str(pincode or "") if ch.isdigit())
            if not digits:
                return "Uttar Pradesh"
            first = digits[0]
            if first == "2":
                return "Uttar Pradesh"
            if first == "3":
                return "Rajasthan"
            if first == "4":
                return "Maharashtra"
            if first == "5":
                return "Karnataka"
            if first == "6":
                return "Tamil Nadu"
            if first == "7":
                return "West Bengal"
            if first == "8":
                return "Bihar"
            if first == "1":
                return "Delhi"
            return "Uttar Pradesh"

        def district_bucket(order) -> str:
            haystack = " ".join(str(v or "") for v in (
                order.customer_name, order.delivery_info, order.dealer_name,
                order.quote_note, order.user_name, order.user_email,
            )).lower()
            for name in grid.keys():
                if name != "Other" and name.lower() in haystack:
                    return name
            return "Other"

        for order in orders:
            qty = order.quantity or 1
            state_key = state_from_pincode(order.pincode)
            if state_key not in state_demand:
                state_demand[state_key] = {"state": state_key, "demand": 0, "delivered": 0, "not_available": 0}

            state_demand[state_key]["demand"] += qty
            status_lower = (order.status or "").lower()
            if status_lower == "delivered":
                state_demand[state_key]["delivered"] += qty
            elif status_lower in {"unavailable", "cancelled"} or "not" in status_lower or "reject" in status_lower:
                state_demand[state_key]["not_available"] += qty

            month_idx = 6
            if order.created_at:
                month_idx = max(0, min(11, order.created_at.month - 1))
            grid[district_bucket(order)][month_idx] += qty

        return {
            "success": True,
            "state_demand": list(state_demand.values()),
            "monthly_grid": grid,
            "orders_count": len(orders),
        }
    except Exception as e:
        raise HTTPException(500, str(e))
