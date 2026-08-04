import os
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import shutil, secrets, json
from sqlalchemy.orm import Session

router   = APIRouter(prefix="/admin")
security = HTTPBasic()

SITE = "https://krashimitra.in"

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
    from backend.config import get_all_settings, ALLOWED_GEMINI_MODELS, ALLOWED_CLAUDE_MODELS

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
        # Claude cache-seeder (admin-only, paid API)
        "claude_configured":    bool(os.getenv("ANTHROPIC_API_KEY", "").strip()),
        "claude_enabled":       settings.get("claude_enabled"),
        "claude_model":         settings.get("claude_model"),
        "allowed_claude_models": ALLOWED_CLAUDE_MODELS,
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


@router.get("/db-write-health")
async def db_write_health(_: str = Depends(require_admin)):
    """Can the database still accept writes, and how full is it?

    Neon turns a compute read-only on its storage cap: every page keeps
    serving while nothing can be saved. That failure is invisible from the
    outside, so this card is where it becomes visible.
    """
    from backend.services.db_health_service import check
    return {"success": True, **check()}


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
    from backend.config import get_all_settings, ALLOWED_GEMINI_MODELS, ALLOWED_CLAUDE_MODELS
    return {
        "settings": get_all_settings(),
        "allowed_models": ALLOWED_GEMINI_MODELS,
        "allowed_claude_models": ALLOWED_CLAUDE_MODELS,
    }


@router.post("/settings")
async def update_settings(payload: dict, _: str = Depends(require_admin)):
    """
    Update one or more runtime settings.
    Changes take effect immediately (no restart needed).
    Changes are lost on server restart — set env vars for persistence.
    """
    from backend.config import update_setting, get_all_settings, ALLOWED_GEMINI_MODELS, ALLOWED_CLAUDE_MODELS

    if "gemini_model" in payload:
        model = payload["gemini_model"]
        if model not in ALLOWED_GEMINI_MODELS:
            raise HTTPException(400, f"Unknown model. Allowed: {ALLOWED_GEMINI_MODELS}")

    if "claude_model" in payload:
        model = payload["claude_model"]
        if model not in ALLOWED_CLAUDE_MODELS:
            raise HTTPException(400, f"Unknown Claude model. Allowed: {ALLOWED_CLAUDE_MODELS}")

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


@router.post("/cache/seed")
async def seed_cache_from_file(_: str = Depends(require_admin)):
    """
    Re-seed the semantic cache from cache/seed_qa.json (the curated premium Q&A).

    Render's disk is ephemeral, so seeded entries vanish on every redeploy/restart.
    This lets an admin re-run the seeding from the panel instead of the CLI script.
    Safe to run anytime — duplicates are skipped by save_to_cache().
    """
    seed_file = Path(__file__).parent.parent.parent / "cache" / "seed_qa.json"
    if not seed_file.exists():
        raise HTTPException(404, f"Seed file not found: {seed_file.name}")

    try:
        topics = json.loads(seed_file.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(500, f"Could not read seed file: {e}")

    # [{topic, questions[], answer}] -> [(question, answer), ...]
    pairs = [
        (q, t["answer"])
        for t in topics
        for q in t.get("questions", [])
    ]
    if not pairs:
        return {"status": "empty", "topics": len(topics),
                "saved": 0, "duplicates": 0, "failed": 0, "total_entries": 0}

    from fastapi.concurrency import run_in_threadpool
    from cache.cache_engine import save_to_cache, get_cache_stats

    def _seed_all():
        # Embedding each question is blocking CPU work; run off the event loop
        # so the server stays responsive while all ~90 pairs are processed.
        saved = dupes = failed = 0
        for question, answer in pairs:
            try:
                if save_to_cache(question, answer, source="claude"):
                    saved += 1
                else:
                    dupes += 1   # already present (or rejected — curated data is valid)
            except Exception:
                failed += 1
        return saved, dupes, failed

    saved, dupes, failed = await run_in_threadpool(_seed_all)

    return {
        "status":        "seeded",
        "topics":        len(topics),
        "phrasings":     len(pairs),
        "saved":         saved,
        "duplicates":    dupes,
        "failed":        failed,
        "total_entries": get_cache_stats().get("total_entries", 0),
    }


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


# ── 🔔 Mandi price alerts ─────────────────────────────────────

@router.get("/alerts")
async def list_admin_alerts(
    limit:  int  = Query(200, ge=1, le=500),
    active: bool = Query(True, description="False also lists switched-off alerts"),
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    """Who is watching which mandi.

    The farmer's name, email and phone are read live through user_id rather than
    copied onto mandi_alerts: an alert is a standing subscription, so the answer
    to "who is this?" should be whoever the account is *today*. A name frozen at
    subscribe time would drift the moment he corrects his profile, and there
    would be no rule for which copy wins. (orders denormalises the opposite way
    on purpose — an order is a historical record of who bought at that moment.)

    Alerts created before the login gate have no account at all; they are
    reported with user_id null rather than hidden, since they still receive
    pushes and are part of what is going out."""
    from backend.database.db import MandiAlert, PushSubscription, User, UserProfile

    q = db.query(MandiAlert, User, UserProfile) \
          .outerjoin(User,        User.id        == MandiAlert.user_id) \
          .outerjoin(UserProfile, UserProfile.user_id == MandiAlert.user_id)
    if active:
        q = q.filter(MandiAlert.active.is_(True))

    rows = q.order_by(MandiAlert.updated_at.desc().nullslast(),
                      MandiAlert.id.desc()).limit(limit).all()

    # How many devices each account can actually be reached on — an alert with
    # zero live endpoints is silently undeliverable, which is worth seeing.
    uids    = {a.user_id for a, _u, _p in rows if a.user_id}
    devices = {}
    if uids:
        for uid, in db.query(PushSubscription.user_id).filter(
                PushSubscription.user_id.in_(uids),
                PushSubscription.active.is_(True)):
            devices[uid] = devices.get(uid, 0) + 1

    def _name(user, profile):
        """Same precedence as alerts.display_name: the name the farmer filled in
        on his profile wins over the signup name, which for a Google login is
        whatever Google supplied."""
        if profile and (profile.name or "").strip():
            return profile.name.strip()
        if user and (user.name or "").strip():
            return user.name.strip()
        return None

    out = []
    for a, user, profile in rows:
        out.append({
            "id":               a.id,
            "commodity":        a.commodity,
            "state":            a.state,
            "district":         a.district,
            "active":           a.active,
            "last_notified_on": a.last_notified_on.isoformat() if a.last_notified_on else None,
            "last_price":       a.last_price,
            "created_at":       a.created_at.isoformat() if a.created_at else "",
            "user_id":          a.user_id,
            "user_name":        _name(user, profile),
            "user_email":       user.email if user else None,
            "phone":            (profile.phone_number or profile.whatsapp_number) if profile else None,
            "user_place":       ", ".join(x for x in [(profile.district if profile else None),
                                                      (profile.state if profile else None)] if x) or None,
            "devices":          devices.get(a.user_id, 0) if a.user_id else (1 if a.active else 0),
            "pre_gate":         a.user_id is None,
        })

    return {"success": True, "total": len(out),
            "with_account": sum(1 for r in out if not r["pre_gate"]),
            "alerts": out}


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
    # Single source of truth — this endpoint and PUT /order/status must never
    # disagree about which labels exist.
    from backend.routes.order import VALID_STATUSES, canonical_status

    next_status = canonical_status(payload.get("status") or "")
    if next_status not in VALID_STATUSES:
        raise HTTPException(400, f"Invalid status. Use: {', '.join(sorted(VALID_STATUSES))}")

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
            elif status_lower in {"unavailable", "cancelled", "out of stock",
                                  "out of order"} or "not" in status_lower or "reject" in status_lower:
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


# ── Farmer Locator ─────────────────────────────────────────────
#
# Powers the admin "Farmer Locator" map: where each registered farmer is,
# searchable by id / name / phone / place, plus demand clusters (which
# regions to focus service on and what those farmers grow).
#
# A farmer is plotted at, in priority order:
#   1. their device location  (user_profiles.geo_lat/geo_lon) → "device" (exact)
#   2. their district centroid (registered address)           → "approx"
#   3. their state centroid                                    → "approx"
#   4. a state guessed from their PIN code's first digit       → "approx"
# Centroids are coarse on purpose — enough to cluster demand, never shown
# as an exact pin (the UI colours "approx" markers differently).

# State / UT centroids (lat, lon) — covers every place a farmer might register.
_STATE_CENTROIDS = {
    "andhra pradesh":   (15.91, 79.74),
    "arunachal pradesh":(28.22, 94.73),
    "assam":            (26.20, 92.94),
    "bihar":            (25.68, 85.56),
    "chhattisgarh":     (21.28, 81.87),
    "goa":              (15.36, 74.06),
    "gujarat":          (22.66, 71.72),
    "haryana":          (29.06, 76.09),
    "himachal pradesh": (31.90, 77.17),
    "jharkhand":        (23.61, 85.28),
    "karnataka":        (15.32, 75.71),
    "kerala":           (10.50, 76.27),
    "madhya pradesh":   (23.47, 77.95),
    "maharashtra":      (19.75, 75.71),
    "manipur":          (24.66, 93.91),
    "meghalaya":        (25.47, 91.37),
    "mizoram":          (23.16, 92.94),
    "nagaland":         (26.16, 94.56),
    "odisha":           (20.95, 85.10),
    "punjab":           (31.15, 75.34),
    "rajasthan":        (26.57, 73.84),
    "sikkim":           (27.53, 88.51),
    "tamil nadu":       (11.13, 78.66),
    "telangana":        (17.90, 79.27),
    "tripura":          (23.75, 91.72),
    "uttar pradesh":    (26.85, 80.95),
    "uttarakhand":      (30.07, 79.15),
    "west bengal":      (23.50, 87.32),
    "delhi":            (28.65, 77.10),
    "jammu and kashmir":(33.78, 76.58),
    "ladakh":           (34.15, 77.58),
    "chandigarh":       (30.73, 76.78),
    "puducherry":       (11.94, 79.83),
}

# Major UP district centroids (the audience is overwhelmingly UP). Keys are
# lowercased; a few historical names are aliased to their live district.
_UP_DISTRICT_CENTROIDS = {
    "meerut":       (28.98, 77.71),
    "lucknow":      (26.85, 80.95),
    "varanasi":     (25.32, 82.97),
    "aligarh":      (27.88, 78.08),
    "bareilly":     (28.37, 79.43),
    "gorakhpur":    (26.76, 83.37),
    "kanpur":       (26.45, 80.33),
    "kanpur nagar": (26.45, 80.33),
    "agra":         (27.18, 78.01),
    "prayagraj":    (25.44, 81.85),
    "allahabad":    (25.44, 81.85),
    "ghaziabad":    (28.67, 77.45),
    "gautam buddh nagar": (28.57, 77.32),
    "noida":        (28.57, 77.32),
    "moradabad":    (28.84, 78.77),
    "saharanpur":   (29.97, 77.55),
    "muzaffarnagar":(29.47, 77.70),
    "mathura":      (27.49, 77.67),
    "firozabad":    (27.16, 78.40),
    "jhansi":       (25.45, 78.57),
    "ayodhya":      (26.79, 82.15),
    "faizabad":     (26.79, 82.15),
    "sultanpur":    (26.26, 82.07),
    "azamgarh":     (26.07, 83.18),
    "jaunpur":      (25.75, 82.68),
    "ballia":       (25.76, 84.15),
    "deoria":       (26.50, 83.78),
    "basti":        (26.79, 82.73),
    "sitapur":      (27.57, 80.68),
    "hardoi":       (27.40, 80.13),
    "unnao":        (26.55, 80.49),
    "rae bareli":   (26.23, 81.24),
    "barabanki":    (26.93, 81.19),
    "bijnor":       (29.37, 78.14),
    "bulandshahr":  (28.40, 77.85),
    "etawah":       (26.78, 79.02),
    "mainpuri":     (27.23, 79.03),
    "budaun":       (28.03, 79.12),
    "rampur":       (28.79, 79.02),
    "shahjahanpur": (27.88, 79.91),
    "pilibhit":     (28.63, 79.80),
    "lakhimpur kheri": (27.95, 80.78),
    "kheri":        (27.95, 80.78),
    "gonda":        (27.13, 81.96),
    "bahraich":     (27.57, 81.60),
    "mirzapur":     (25.15, 82.57),
    "banda":        (25.48, 80.33),
    "fatehpur":     (25.93, 80.81),
    "pratapgarh":   (25.90, 81.95),
    "ghazipur":     (25.58, 83.58),
    "mau":          (25.94, 83.56),
    "sonbhadra":    (24.69, 83.07),
    "chandauli":    (25.26, 83.27),
    "hapur":        (28.73, 77.78),
    "amroha":       (28.90, 78.47),
    "sambhal":      (28.58, 78.55),
    "farrukhabad":  (27.39, 79.58),
    "etah":         (27.63, 78.66),
    "hathras":      (27.60, 78.05),
    "kaushambi":    (25.53, 81.38),
    "amethi":       (26.16, 81.81),
}

# PIN-code first digit → a representative state (very coarse; last-resort only).
_PIN_REGION = {
    "1": "delhi",         "2": "uttar pradesh", "3": "rajasthan",
    "4": "maharashtra",   "5": "telangana",     "6": "tamil nadu",
    "7": "west bengal",   "8": "bihar",
}


def _norm(s):
    return (s or "").strip().lower()


def _resolve_coords(profile, user):
    """(lat, lon, accuracy) for a farmer, or (None, None, None) if unplottable."""
    # 1 · exact device location
    if profile is not None and profile.geo_lat is not None and profile.geo_lon is not None:
        return profile.geo_lat, profile.geo_lon, "device"

    district = _norm(getattr(profile, "district", None)) or _norm(getattr(user, "district", None))
    if district:
        if district in _UP_DISTRICT_CENTROIDS:
            lat, lon = _UP_DISTRICT_CENTROIDS[district]
            return lat, lon, "approx"
        # relaxed contains-match (e.g. "meerut city")
        for key, (lat, lon) in _UP_DISTRICT_CENTROIDS.items():
            if key in district or district in key:
                return lat, lon, "approx"

    state = _norm(getattr(profile, "state", None))
    if state:
        if state in _STATE_CENTROIDS:
            lat, lon = _STATE_CENTROIDS[state]
            return lat, lon, "approx"
        for key, (lat, lon) in _STATE_CENTROIDS.items():
            if key in state or state in key:
                return lat, lon, "approx"

    pincode = "".join(ch for ch in str(getattr(profile, "pin_code", "") or "") if ch.isdigit())
    if pincode:
        st = _PIN_REGION.get(pincode[0])
        if st and st in _STATE_CENTROIDS:
            lat, lon = _STATE_CENTROIDS[st]
            return lat, lon, "approx"

    return None, None, None


def _primary_crop(profile, user):
    for val in (
        getattr(profile, "primary_crop", None),
        getattr(user, "primary_crop", None),
        getattr(profile, "crops_grown", None),
    ):
        val = (val or "").strip()
        if val:
            return val.split(",")[0].strip()
    return None


def _readable_place(profile, user, geo_lat_used):
    """A short human label for the farmer's location."""
    if profile is not None and geo_lat_used and (profile.geo_location or "").strip():
        return profile.geo_location.strip()
    parts = [
        (getattr(profile, "village", None) or getattr(user, "village", None)),
        (getattr(profile, "district", None) or getattr(user, "district", None)),
        getattr(profile, "state", None),
    ]
    return ", ".join(p.strip() for p in parts if p and str(p).strip()) or None


@router.get("/farmers/locations")
async def farmer_locations(
    q: str | None = Query(None, description="filter by id / name / phone / place / crop"),
    limit: int = Query(1000, ge=1, le=5000),
    _: str = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    from backend.database.db import User, UserProfile

    try:
        profiles = {p.user_id: p for p in db.query(UserProfile).all() if p.user_id is not None}
        users = db.query(User).all()

        needle = _norm(q)
        needle_id = None
        if needle and needle.isdigit():
            needle_id = int(needle)

        farmers = []
        for user in users:
            profile = profiles.get(user.id)
            lat, lon, accuracy = _resolve_coords(profile, user)
            crop = _primary_crop(profile, user)
            place = _readable_place(profile, user, accuracy == "device")

            phone = None
            if profile is not None:
                phone = (profile.phone_number or profile.whatsapp_number or "").strip() or None

            district = (getattr(profile, "district", None) or user.district or None)
            state = getattr(profile, "state", None)
            village = (getattr(profile, "village", None) or user.village or None)
            pincode = getattr(profile, "pin_code", None)

            geo_updated = getattr(profile, "geo_updated_at", None)

            rec = {
                "user_id":  user.id,
                "name":     user.name or (getattr(profile, "name", None)) or f"किसान #{user.id}",
                "email":    user.email,
                "phone":    phone,
                "occupation": getattr(profile, "occupation", None),   # व्यवसाय — who the customer is
                "crop":     crop,
                "state":    state,
                "district": district,
                "village":  village,
                "pincode":  pincode,
                "lat":      lat,
                "lon":      lon,
                "accuracy": accuracy,       # "device" | "approx" | None
                "location": place,
                "verified": bool(getattr(user, "seller_verified", False)),
                "updated_at": geo_updated.isoformat() if geo_updated else None,
            }

            if needle:
                if needle_id is not None and user.id == needle_id:
                    pass  # exact id match always passes
                else:
                    hay = " ".join(str(v or "") for v in (
                        user.id, rec["name"], rec["email"], rec["phone"],
                        rec["district"], rec["village"], rec["state"],
                        rec["pincode"], rec["crop"], rec["location"],
                    )).lower()
                    if needle not in hay:
                        continue

            farmers.append(rec)

        farmers = farmers[:limit]
        located = [f for f in farmers if f["lat"] is not None]

        # ── demand clusters — group located farmers by district (else state) ──
        clusters = {}
        for f in located:
            key = (f["district"] or f["state"] or "अन्य").strip()
            c = clusters.setdefault(key, {
                "region": key, "count": 0, "lat": 0.0, "lon": 0.0,
                "crops": {}, "_n": 0,
            })
            c["count"] += 1
            c["lat"] += f["lat"]
            c["lon"] += f["lon"]
            c["_n"] += 1
            if f["crop"]:
                c["crops"][f["crop"]] = c["crops"].get(f["crop"], 0) + 1

        cluster_list = []
        for c in clusters.values():
            n = max(c["_n"], 1)
            top_crops = sorted(c["crops"].items(), key=lambda kv: kv[1], reverse=True)[:4]
            cluster_list.append({
                "region": c["region"],
                "count":  c["count"],
                "lat":    round(c["lat"] / n, 5),
                "lon":    round(c["lon"] / n, 5),
                "crops":  [{"name": name, "count": cnt} for name, cnt in top_crops],
            })
        cluster_list.sort(key=lambda x: x["count"], reverse=True)

        return {
            "success":       True,
            "total":         len(farmers),
            "located":       len(located),
            "device_pins":   sum(1 for f in located if f["accuracy"] == "device"),
            "approx_pins":   sum(1 for f in located if f["accuracy"] == "approx"),
            "farmers":       farmers,
            "clusters":      cluster_list[:20],
            "query":         q or "",
        }
    except Exception as e:
        raise HTTPException(500, str(e))


# ── Lead clicks ───────────────────────────────────────────────
# The one number that decides the 31-Aug test is "how many enquiries did this
# listing get". It sits on the checklist page on purpose: the panel is opened to
# tick tasks, so the count is in front of the owner without anyone remembering
# to run a GA4 report. Source: lead_clicks, written by the /go/<id> redirects.

@router.get("/leads")
async def lead_report(
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    from backend.services import lead_clicks
    try:
        return {"success": True, **lead_clicks.report(db)}
    except Exception as e:
        raise HTTPException(500, str(e))


# ── Deadline Checklist ────────────────────────────────────────
# The owner's run-up to the 31-Aug-2026 revenue test (docs/MARKET-AND-MONEY.md
# §8). The plan is a JSON file, the tick state is the admin_tasks table, and
# services/checklist.py is the join — see AdminTask for why they are separate.

def _checklist_write(fn, *args):
    """Run a checklist write, naming a read-only database instead of 500-ing.

    Neon flips the compute read-only on a plan limit: every page still serves,
    so the only symptom is a checkbox that silently refuses to tick. Worth its
    own message — it is otherwise indistinguishable from a bug in this file.
    """
    from backend.database.db import is_read_only_error
    try:
        return fn(*args)
    except Exception as e:
        if is_read_only_error(e):
            raise HTTPException(
                503,
                "Database is read-only (Neon plan limit) — the tick was not saved. "
                "See the 'Settle the Neon migration' task."
            )
        raise HTTPException(500, str(e))


@router.get("/tasks")
async def get_tasks(
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    from backend.services import checklist
    try:
        return {"success": True, **checklist.board(db)}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.patch("/tasks/{slug}")
async def toggle_task(
    slug:    str,
    payload: dict,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    from backend.services import checklist
    ok = _checklist_write(checklist.set_done, db, slug, bool(payload.get("done")))
    if not ok:
        raise HTTPException(404, "Unknown task")
    return {"success": True, "progress": checklist.board(db)["progress"]}


@router.post("/tasks")
async def create_task(
    payload: dict,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    from backend.services import checklist
    task = _checklist_write(checklist.add_custom, db,
                            payload.get("title", ""), payload.get("note", ""))
    if not task:
        raise HTTPException(400, "Task needs a title")
    return {"success": True, "task": task, "progress": checklist.board(db)["progress"]}


@router.delete("/tasks/{slug}")
async def delete_task(
    slug: str,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    from backend.services import checklist
    ok = _checklist_write(checklist.delete_custom, db, slug)
    if not ok:
        raise HTTPException(404, "Not one of your own tasks")
    return {"success": True, "progress": checklist.board(db)["progress"]}


# ── खरीदार / डीलर directory ───────────────────────────────────
# CRUD behind /bhav/.../kharidar. Two kinds of row arrive here: ones the owner
# types in (source="admin") and ones from the public अपनी दुकान form
# (source="signup", never live until approved). services/dealers.py owns the
# writes and the trust rule; this file is just the HTTP surface.
#
# Reads go through the same _checklist_write() wrapper as the checklist: the
# symptom of a read-only Neon compute is identical here — the form submits, the
# panel says nothing, and the dealer is not saved.

def _dealer_write(fn, *args, **kwargs):
    from backend.database.db import is_read_only_error
    try:
        return fn(*args, **kwargs)
    except HTTPException:
        raise
    except Exception as e:
        if is_read_only_error(e):
            raise HTTPException(
                503,
                "Database is read-only (Neon plan limit) — the dealer was NOT saved. "
                "Write the number down and re-enter it once the DB accepts writes. "
                "See the 'Settle the Neon migration' task."
            )
        raise HTTPException(500, str(e))


@router.get("/buyers")
async def list_buyers(
    source: str = "",
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    """Every listing, live or not. The seeded data/buyers.json rows are NOT
    included — they are committed to the repo and not editable from here; a
    DB row sharing their slug overrides them (see database/db.py::Buyer)."""
    from backend.services import dealers, upi
    try:
        return {"success": True, "buyers": dealers.listing(db, source=source),
                "counts": dealers.counts(db),
                "funnel": dealers.funnel(db),
                # So the panel can grey out the collect button and say why,
                # instead of generating a QR that points nowhere.
                "upi": {"configured": upi.configured(),
                        "vpa": upi.vpa(),
                        "amount": upi.DEFAULT_AMOUNT}}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/buyers")
async def create_buyer(
    payload: dict,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    from backend.services import dealers
    problem = dealers.validate(payload)
    if problem:
        raise HTTPException(400, problem)
    row = _dealer_write(dealers.create, db, payload)
    return {"success": True, "buyer": dealers.listing(db, source="")[0] if row else None,
            "counts": dealers.counts(db)}


@router.patch("/buyers/{slug}")
async def update_buyer(
    slug:    str,
    payload: dict,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    """Also the approve path: {"active": true, "verified": true}. Both flags are
    settable only from here — the public form has no route to them."""
    from backend.services import dealers
    row = _dealer_write(dealers.update, db, slug, payload)
    if not row:
        raise HTTPException(404, "Unknown dealer")
    return {"success": True, "counts": dealers.counts(db)}


@router.delete("/buyers/{slug}")
async def delete_buyer(
    slug: str,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    from backend.services import dealers
    if not _dealer_write(dealers.delete, db, slug):
        raise HTTPException(404, "Unknown dealer")
    return {"success": True, "counts": dealers.counts(db)}


# ── A dealer's catalogue ──────────────────────────────────────
# The dealer types what he sells on /dukan/product; the photos are put on here.
# A public image upload would be a moderation queue nobody has time to run, on
# a surface where a bad picture goes out under our own verified tick.

@router.get("/buyers/{slug}/products")
async def list_buyer_products(
    slug: str,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    from backend.database.db import Buyer
    from backend.services import dealer_products
    row = db.query(Buyer).filter(Buyer.slug == slug).first()
    if not row:
        raise HTTPException(404, "Unknown dealer")
    return {"success": True,
            "products": dealer_products.for_buyer(db, row.slug, row.owner_user_id,
                                                  only_active=False),
            "max": dealer_products.MAX_PER_DEALER}


@router.post("/buyers/{slug}/products")
async def create_buyer_product(
    slug:    str,
    payload: dict,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    from backend.database.db import Buyer
    from backend.services import dealer_products
    row = db.query(Buyer).filter(Buyer.slug == slug).first()
    if not row:
        raise HTTPException(404, "Unknown dealer")
    problem = dealer_products.validate(payload)
    if problem:
        raise HTTPException(400, problem)
    created = _dealer_write(dealer_products.create, db, row.slug,
                            row.owner_user_id, payload)
    if not created:
        raise HTTPException(400, f"Max {dealer_products.MAX_PER_DEALER} products per dealer")
    return {"success": True, "product": dealer_products.as_dict(created)}


@router.patch("/products/{product_id}")
async def update_product(
    product_id: int,
    payload:    dict,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    from backend.services import dealer_products
    # Only validate what a full edit would break; a partial patch (e.g. just
    # `active`) must not be rejected for having no name in the body.
    if "name_hi" in payload or "price" in payload:
        problem = dealer_products.validate({
            "name_hi": payload.get("name_hi", "xx"),
            "price": payload.get("price", 1),
            "mrp": payload.get("mrp"),
        })
        if problem:
            raise HTTPException(400, problem)
    row = _dealer_write(dealer_products.update, db, product_id, payload)
    if not row:
        raise HTTPException(404, "Unknown product")
    return {"success": True, "product": dealer_products.as_dict(row)}


@router.delete("/products/{product_id}")
async def delete_product(
    product_id: int,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    from backend.services import dealer_products
    if not _dealer_write(dealer_products.delete, db, product_id):
        raise HTTPException(404, "Unknown product")
    return {"success": True}


@router.post("/products/{product_id}/image")
async def upload_product_image(
    product_id: int,
    file: UploadFile = File(...),
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    """The product photo the dealer sent over WhatsApp.

    Re-encoded to a small WebP and stored in Postgres, not on disk — Render's
    free tier wipes uploads/ on every restart, the bug routes/profile.py
    already hit with avatars.
    """
    import base64 as _b64
    import io

    from PIL import Image, ImageOps

    from backend.services import dealer_products

    raw = b""
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        raw += chunk
        if len(raw) > 8 * 1024 * 1024:
            raise HTTPException(400, "Image too large — 8 MB max")
    if not raw:
        raise HTTPException(400, "Empty upload")

    try:
        img = Image.open(io.BytesIO(raw))
        img = ImageOps.exif_transpose(img)              # honour phone rotation
        img = img.convert("RGB")
        # `contain`, not a centre-crop: a product shot is a bag or a bottle and
        # cropping it square cuts the label off. The card's photo box uses
        # object-fit:contain to match, so the whole pack stays visible.
        img.thumbnail((480, 480), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="WEBP", quality=82, method=6)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, "Could not read that image — try another file")

    b64 = _b64.b64encode(buf.getvalue()).decode("ascii")
    row = _dealer_write(dealer_products.set_image, db, product_id, b64, "image/webp")
    if not row:
        raise HTTPException(404, "Unknown product")
    return {"success": True, "bytes": len(buf.getvalue())}


@router.delete("/products/{product_id}/image")
async def delete_product_image(
    product_id: int,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    from backend.services import dealer_products
    if not _dealer_write(dealer_products.set_image, db, product_id, None):
        raise HTTPException(404, "Unknown product")
    return {"success": True}


@router.patch("/buyers/{slug}/rank")
async def set_buyer_bhav_rank(
    slug:    str,
    payload: dict,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    """Which (if any) of the <=3 Tier-3 bhav-panel slots this row holds for its
    state. {"rank": 1|2|3|null}. Routed through dealers.set_bhav_rank() rather
    than the generic update() above — it has to clear whoever else in the same
    state held that rank first, which update()/_apply() deliberately cannot do."""
    from backend.services import dealers
    row = _dealer_write(dealers.set_bhav_rank, db, slug, payload.get("rank"))
    if not row:
        raise HTTPException(404, "Unknown dealer, or rank must be 1, 2, 3 or null")
    return {"success": True, "bhav_rank": row.bhav_rank}


# ── Outreach: the call log and the ₹500 ───────────────────────
# These three endpoints ARE the 31-Aug test, in the order it happens: ring him,
# show him a QR, write down that the money landed.

@router.post("/buyers/{slug}/call")
async def log_dealer_call(
    slug:    str,
    payload: dict,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    """Log one phone call. `result` must be one of dealers.CALL_RESULTS."""
    from backend.services import dealers
    result = (payload.get("result") or "").strip().lower()
    if result not in dealers.CALL_RESULTS:
        raise HTTPException(400, f"result must be one of: {', '.join(dealers.CALL_RESULTS)}")
    row = _dealer_write(dealers.log_call, db, slug, result,
                        (payload.get("note") or ""))
    if not row:
        raise HTTPException(404, "Unknown dealer")
    return {"success": True, "counts": dealers.counts(db), "funnel": dealers.funnel(db)}


# The default answer to "what is this ₹500 for" — shown in the panel and in
# the WhatsApp message, editable per-request via `purpose=`. Not persisted:
# every collect call regenerates it fresh, so there is no schema to migrate
# and no stale copy to fall out of date.
_DEFAULT_PURPOSE = "मंडी भाव पेज पर वेरिफाइड लिस्टिंग — 30 दिन के लिए"


@router.get("/buyers/{slug}/collect")
async def dealer_collect(
    slug:    str,
    amount:  str = "",
    purpose: str = "",
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    """The UPI QR + deep link + a ready-to-send WhatsApp message for one dealer.

    A request to pay, never a record of one — see services/upi.py. The payment
    is only real once someone sees it in the bank app and posts it back to
    /payment below.

    `amount` and `purpose` are both editable from the panel per request — the
    fee is not one fixed number (a featured slot or a first-time discount is a
    real negotiation), and "what is this for" is copy the owner should be able
    to word for a specific dealer, not a string baked into the code.
    """
    from backend.database.db import Buyer
    from backend.services import dealers, upi
    row = db.query(Buyer).filter(Buyer.slug == slug).first()
    if not row:
        raise HTTPException(404, "Unknown dealer")
    # A /dukan/product account's real fee is dealers.quote() over however many
    # districts it has, not the flat KM_LISTING_FEE default — only when the
    # panel didn't already send its own amount, so a manual override always wins.
    if not amount and row.owner_user_id:
        amount = str(dealers.account_price(db, row.owner_user_id))
    if not upi.configured():
        raise HTTPException(
            503,
            "UPI is not configured — set KM_UPI_ID (your UPI id, e.g. name@okhdfcbank) "
            "and KM_UPI_NAME in the environment, then restart. Nothing is hardcoded "
            "on purpose: a wrong VPA sends a dealer's money to a stranger."
        )
    pack = upi.collect(row.name or "", row.district or "",
                       amount=amount or None, ref=slug)
    pack["purpose"]  = (purpose or "").strip()[:200] or _DEFAULT_PURPOSE
    # The amount the owner just typed has to travel WITH the link. Without it
    # the dealer opened /pay and saw the flat KM_LISTING_FEE default instead —
    # a WhatsApp message quoting ₹249 above a page charging ₹500, which is the
    # kind of mismatch that loses the payment and the trust in one go.
    pack["pay_url"]  = _pay_page_url(slug, pack["amount"])
    pack["whatsapp"] = _collect_message(row, pack["amount"], pack["pay_url"], pack["purpose"])
    # So the panel can show a receipt button (or not) without a second round
    # trip — this is the same row's payment history, already on hand.
    pack["paid_at"]     = row.paid_at.isoformat() if row.paid_at else None
    pack["paid_amount"] = row.paid_amount or 0
    pack["paid_until"]  = row.paid_until.isoformat() if row.paid_until else None
    pack["payment_ref"] = row.payment_ref or ""
    return {"success": True, **pack}


def _pay_page_url(slug: str, amount=None) -> str:
    """Absolute URL of the public /pay page — it gets pasted into WhatsApp, so a
    site-relative path would arrive as unclickable text.

    `amount` is carried explicitly rather than left for /pay to re-derive: the
    figure in the WhatsApp message and the figure on the page the dealer opens
    have to be the same number, and only the caller knows whether this is the
    standard fee, a renewal, or a rate that was negotiated on the phone. /pay
    re-clamps it, so a hand-edited URL still cannot produce a ₹0 QR."""
    url = f"{SITE}/pay?d={quote(slug, safe='')}"
    return f"{url}&amount={int(amount)}" if amount else url


def _collect_message(row, amount: int, pay_url: str, purpose: str = "") -> str:
    """What the owner sends the dealer. Plain Hindi, no marketing — this goes to
    someone who has already said yes on the phone and just needs the link."""
    name = (row.name or "").strip()
    for_line = f" — {purpose}" if purpose else ""
    return (
        f"नमस्ते{' ' + name if name else ''} जी,\n"
        f"कृषि मित्र पर आपकी लिस्टिंग के लिए ₹{amount}{for_line}।\n\n"
        f"नीचे लिंक से किसी भी UPI ऐप से पे कर सकते हैं:\n{pay_url}\n\n"
        f"पेमेंट के बाद स्क्रीनशॉट भेज दीजिए, आपकी लिस्टिंग पर ✓ वेरिफाइड लग जाएगा।"
    )


@router.get("/buyers/{slug}/receipt")
async def dealer_receipt(
    slug: str,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    """The WhatsApp-ready receipt for a dealer who has actually paid.

    Built only from fields record_payment() itself wrote — paid_amount,
    payment_ref, paid_at, paid_until. That is the same guarantee as the rest of
    this file: a receipt can only describe a payment a human already confirmed,
    never one this endpoint invented.
    """
    from backend.database.db import Buyer
    row = db.query(Buyer).filter(Buyer.slug == slug).first()
    if not row:
        raise HTTPException(404, "Unknown dealer")
    if not row.paid_at:
        raise HTTPException(400, "This dealer has no recorded payment yet")
    return {
        "success":     True,
        "receipt":     _receipt_message(row),
        "paid_amount": row.paid_amount or 0,
        "paid_at":     row.paid_at.isoformat(),
        "paid_until":  row.paid_until.isoformat() if row.paid_until else None,
        "payment_ref": row.payment_ref or "",
    }


def _fmt_date(dt) -> str:
    return dt.strftime("%d %b %Y") if dt else "—"


def _receipt_message(row) -> str:
    """Plain-text receipt, not a GST invoice — no entity is registered yet
    (deadline_checklist.json → entity-decision), so this is proof for the
    dealer's own records, not a tax document."""
    name = (row.name or "").strip()
    ref_line = f"UPI रेफरेंस: {row.payment_ref}\n" if row.payment_ref else ""
    return (
        f"🧾 कृषि मित्र — भुगतान रसीद\n\n"
        f"दुकान: {name or '—'}\n"
        f"जिला: {row.district or '—'}\n\n"
        f"राशि: ₹{row.paid_amount or 0}\n"
        f"{ref_line}"
        f"भुगतान तारीख: {_fmt_date(row.paid_at)}\n\n"
        f"लिस्टिंग यहाँ तक लाइव रहेगी: {_fmt_date(row.paid_until)}\n\n"
        f"धन्यवाद — कृषि मित्र टीम"
    )


@router.post("/buyers/{slug}/payment")
async def record_dealer_payment(
    slug:    str,
    payload: dict,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    """Mark a dealer paid. Hand-entered from the bank app, by design.

    There is no callback that could do this — a upi:// link hands off to the
    dealer's own app and tells us nothing. So this endpoint is the only thing
    that sets `paid_at`, and it requires a human who saw the credit.
    """
    from backend.services import dealers, upi
    amount = upi.clean_amount(payload.get("amount"), default=0)
    if amount < upi.MIN_AMOUNT:
        raise HTTPException(400, f"Enter the amount actually received (₹{upi.MIN_AMOUNT}–₹{upi.MAX_AMOUNT})")
    try:
        months = max(1, min(12, int(payload.get("months") or 1)))
    except (TypeError, ValueError):
        months = 1
    row = _dealer_write(dealers.record_payment, db, slug, amount,
                        (payload.get("ref") or ""), months)
    if not row:
        raise HTTPException(404, "Unknown dealer")
    return {"success": True, "counts": dealers.counts(db), "funnel": dealers.funnel(db)}
