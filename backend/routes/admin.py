import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import shutil, secrets, json
from pydantic import BaseModel
from sqlalchemy.orm import Session

router   = APIRouter(prefix="/admin")
security = HTTPBasic()

SITE = "https://krashimitra.in"

ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "krashi2025")

UPLOAD_DIR = Path(__file__).parent.parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


# Brute-force lockout. The panel holds every farmer's phone number and every
# payment, so a password guesser must not get unlimited tries. Only FAILED
# attempts count: the panel fires dozens of authenticated requests per page,
# and those must never lock the owner out.
_ADMIN_FAIL_LIMIT = 10
_ADMIN_FAIL_WINDOW = 15 * 60          # seconds
_admin_fails: dict = {}


def _admin_locked(ip: str, now: float) -> bool:
    fails = [t for t in _admin_fails.get(ip, []) if now - t < _ADMIN_FAIL_WINDOW]
    if fails:
        _admin_fails[ip] = fails
    else:
        _admin_fails.pop(ip, None)
    return len(fails) >= _ADMIN_FAIL_LIMIT


def require_admin(request: Request, creds: HTTPBasicCredentials = Depends(security)):
    import time
    from backend.utils.security import client_ip
    ip, now = client_ip(request), time.time()
    if _admin_locked(ip, now):
        raise HTTPException(429, "बहुत ज़्यादा गलत पासवर्ड — 15 मिनट बाद कोशिश करें।",
                            headers={"Retry-After": str(_ADMIN_FAIL_WINDOW)})
    ok_user = secrets.compare_digest(creds.username.encode(), ADMIN_USER.encode())
    ok_pass = secrets.compare_digest(creds.password.encode(), ADMIN_PASS.encode())
    if not (ok_user and ok_pass):
        if len(_admin_fails) > 5000:          # bound the dict against spoofed IPs
            _admin_fails.clear()
        _admin_fails.setdefault(ip, []).append(now)
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

    # One discovery helper for every caller — see services/chatbot_service.
    # Adding a key is an env var, never a code change here.
    from backend.services.chatbot_service import gemini_keys as _gemini_keys
    gemini_keys = _gemini_keys()

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
        "gemini_configured":    bool(gemini_keys),
        "gemini_keys_count":    len(gemini_keys),
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
        "news_ai_enabled":      settings.get("news_ai_enabled"),
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


# ── Free-tier runway: Netlify / Render / Neon ─────────────────

@router.get("/infra")
def infra(refresh: int = Query(0, ge=0, le=1), _: str = Depends(require_admin)):
    """How much is left on each of the three free plans.

    Every outage this site has had was a quota outage, not a bug — Netlify's
    usage cap took the whole front end down in August, and Neon's storage cap
    flips the compute read-only while its own dashboard still says "All OK".
    None of that shows up in /health, which is forbidden from calling a
    third-party API at all, so the billing numbers live here instead.

    Deliberately `def`, not `async def`: the probe makes up to a dozen
    outbound HTTP calls, and running that on the event loop would stall every
    other request for the duration. FastAPI puts a sync route on the
    threadpool, where blocking is free.

    `refresh=1` bypasses the 5-minute memo. Use it sparingly — these are
    rate-limited billing APIs, not a metrics endpoint.
    """
    from backend.services import infra_service
    return {"success": True, **infra_service.run(use_cache=not refresh)}


@router.get("/bandwidth")
def bandwidth(days: int = Query(7, ge=1, le=62), _: str = Depends(require_admin)):
    """Where Render's outbound bandwidth goes: bytes this origin sent, by site
    section and by requester (googlebot, gptbot, human…). Everything counted
    here is something Cloudflare did not serve from cache — i.e. exactly what
    Render meters against the 5 GB/month cap. See services/bandwidth_meter.py."""
    from backend.services import bandwidth_meter
    return {"success": True, **bandwidth_meter.report(days)}


# ── Index gate (which /bhav pages Google is allowed to keep) ───

@router.get("/index-gate")
def index_gate_view(_: str = Depends(require_admin)):
    """Blast radius of the thin-page gate, BEFORE it is switched on.

    The site renders ~14,000 /bhav URLs. 5,624 have ever earned an impression;
    half of those earn five or fewer and 38 clicks between the lot, while the
    top tenth carries 64%. That tail is why the strong pages sit at the bottom
    of page one instead of the top. The gate withdraws the tail's claim on the
    index — noindex, follow; the pages stay live and usable, nothing is
    deleted or redirected.

    `enabled` in data/index_gate.json starts false, and this endpoint is the
    reason: the verdict is computed for every URL and counted here whether or
    not it is being applied, so the split can be read and the threshold tuned
    before Google sees anything. Flip `enabled` when the numbers look right.

    Read `buckets` before changing `max_age_days` — it is the age histogram the
    threshold is cutting, so it shows what a different cut would cost.
    """
    from backend.routes import bhav
    from backend.services import index_gate as _gate

    idx = bhav._get_index()
    return {"success": True, **_gate.split(idx.get("dates", {}))}


# ── Crop types (which crop gets which /bhav layout) ───────────

@router.get("/crop-types")
def crop_types_view(
    type:   str = "",
    source: str = "",
    q:      str = "",
    _: str = Depends(require_admin),
):
    """Every crop /bhav serves, and the layout its sale cadence earns it.

    This is the answer to "which crop type stays on which layout". The type is
    NOT in the URL and deliberately so — 5,624 /bhav URLs already rank, and a
    path segment would cost that many redirects to encode something no farmer
    types. It lives in data/crop_types.json, is stamped on each page as
    data-crop-type/data-layout, and is listed here.

    `source` is the honest part: "explicit" means someone classified the crop
    by hand, "rule" means a keyword guessed it (and `matched` shows which
    keyword), "default" means nothing claimed it and the page renders exactly
    as it does today. Sort by impressions and read the rule rows first — a bad
    keyword is the only way this registry can quietly mis-type a crop.

    Filters are all optional and combine: ?type=perishable&source=rule.
    """
    from backend.routes import bhav
    from backend.services import crop_types as _ct

    idx = bhav._get_index()
    slugs = sorted((idx.get("crops") or {}).keys())
    rows = _ct.classify(slugs)
    for r in rows:
        r["hi_crop"] = bhav._hindi_name((idx.get("crops") or {}).get(r["slug"], r["slug"]))
        r["url"] = f"{SITE}/bhav/{r['slug']}"

    if type:
        rows = [r for r in rows if r["type"] == type]
    if source:
        rows = [r for r in rows if r["source"] == source]
    if q:
        needle = q.strip().lower()
        rows = [r for r in rows if needle in r["slug"] or needle in r["hi_crop"]]

    counts: dict = {}
    for r in rows:
        counts[r["type"]] = counts.get(r["type"], 0) + 1
    by_source: dict = {}
    for r in rows:
        by_source[r["source"]] = by_source.get(r["source"], 0) + 1

    return {
        "success": True,
        "types": _ct.all_types(),
        "counts": counts,
        "by_source": by_source,
        "total": len(rows),
        "crops": rows,
    }


# ── कृषि मित्र Book ────────────────────────────────────────────

@router.get("/book")
async def book(_: str = Depends(require_admin)):
    """The operating manual: goal, standing rules, past mistakes, commands,
    free-tier arithmetic, file map.

    Content is backend/data/krashimitra_book.json, read live by mtime — add a
    rule by editing the file and it is on the panel at the next load, with no
    deploy and no migration. The only computed field is the deadline
    countdown, which is sourced from deadline_checklist.json so the Book and
    the Checklist page cannot drift apart on the date.
    """
    from backend.services.book_service import get_book
    return {"success": True, **get_book()}


# ── WhatsApp चैनल — आज की पोस्ट ────────────────────────────────

@router.get("/wa-posts")
async def wa_posts(refresh: int = Query(0, ge=0, le=1), _: str = Depends(require_admin)):
    """Today's ready-to-paste bhav post for every state that has a channel.

    WhatsApp has no API for posting to a channel, so this cannot send — it
    writes. The morning job is 31 posts, and the difference between a routine
    that survives and one that dies in week two is whether each post is a paste
    or a piece of composition. Ordered biggest-state-first so a morning that
    runs out of time runs out on Sikkim, not Uttar Pradesh.

    Returns every channel, in one of two lists: `posts` (with a भरोसा score out
    of 100 and the reasons it is not higher — read before pasting, since one
    wrong number costs more trust than a week of right ones buys) and `quiet`
    (channels with nothing honest to say today, and why). Channels come from
    data/wa_channels.json; a state with no link there is in neither list.

    Each post also carries the day's chosen `format` and `tone`, the `can` list
    of formats today's rows could honestly support, a `pool` of swappable
    crops, a नयापन count, and the next seven days of the rotation. `catalog`
    names every format and tone once, at the top, rather than repeating the
    labels inside 31 posts.
    """
    from backend.services import wa_image, wa_post, wa_style
    cov = wa_post.coverage(refresh=bool(refresh))
    return {"success": True, "count": len(cov["posts"]),
            "catalog": wa_style.catalog(),
            # The picture's prompt modes, sent once at the top for the same
            # reason the format/tone labels are: repeating three fixed
            # descriptions inside 31 posts is payload with no information in it.
            "image": wa_image.catalog(), **cov}


@router.get("/wa-post")
async def wa_post_one(state: str = Query(..., min_length=2, max_length=60),
                      format: str = Query("", max_length=24),
                      tone: str = Query("", max_length=24),
                      n: int = Query(0, ge=0, le=8),
                      drop: str = Query("", max_length=600),
                      extra: str = Query("", max_length=400),
                      _: str = Depends(require_admin)):
    """One state's post, rewritten under the panel's overrides.

    The rotation picks a shape and a voice for every channel every morning, and
    that is the right default — but the person about to paste is the one who
    can see that today's biggest mover is a crop nobody in the state grows for
    sale, or that four of the five lines are three days old. So each control
    here overrides one of the rotation's decisions and nothing else:
    `format`/`tone` the shape and voice, `n` how many crops, `drop` a
    comma-separated list of commodities to leave out, `extra` one line of
    non-price content chosen from /admin/wa-extra.

    Omitted arguments fall back to what the rotation chose, so sending none of
    them is how the panel gets a post back to अपने आप.

    The भरोसा score comes back recomputed on the lines that survived — dropping
    a stale crop has to visibly move it, or the control is decoration. What
    cannot change through any combination of these is a price: services/wa_style
    only arranges words around figures services/wa_post has already decided.

    `extra` is the single exception to that — words from outside wa_post — and
    it is the one argument that can be REFUSED. recompose() screens it against
    the day's own facts and drops it if it carries a second link, a contact
    detail, or a figure we did not supply; `extra_flags` on the response says
    which, so the panel reports it rather than quietly posting a shorter post.
    """
    from backend.services import wa_post as svc
    dropped = {c.strip() for c in drop.split(",") if c.strip()}
    row = svc.recompose(state, fmt=format.strip(), tone=tone.strip(),
                        n=n, drop=dropped, extra=extra.strip())
    if not row:
        raise HTTPException(status_code=404, detail="इस राज्य की आज कोई पोस्ट नहीं है")
    return {"success": True, "post": row}


@router.post("/wa-image")
async def wa_image_make(state: str = Query(..., min_length=2, max_length=60),
                        mode: str = Query("scene", max_length=16),
                        prompt: str = Query("", max_length=600),
                        dry: int = Query(0, ge=0, le=1),
                        _: str = Depends(require_admin)):
    """The picture for one state's card — and the prompt that made it.

    Three modes, all defined in services/wa_image: `scene` builds the prompt
    from today's post (state, month, opening crop), `random` takes one of the
    curated scenes on the same (state, date) rotation the post itself uses, and
    `custom` uses what the owner typed. Whichever it is, the model is asked for
    a BACKDROP and never for text — the prices are drawn over it by the panel's
    canvas from the same line dicts the caption used, so the figure in the
    picture and the figure in the message are one variable.

    `dry=1` returns the prompt without generating, which is what the panel
    calls when the mode dropdown moves. Every image is billed, so showing the
    owner what will be asked for costs nothing and re-rolling a bad prompt
    after paying for it costs money.

    Generating is optional. With no picture the panel still draws a complete
    card — the prices on a brand-coloured ground — so a failure here is never
    the reason a channel goes without one.
    """
    from backend.services import wa_image, wa_post as svc

    post = svc.post_for(state)
    if not post:
        raise HTTPException(status_code=404, detail="इस राज्य की आज कोई पोस्ट नहीं है")

    built = wa_image.build_prompt(post, mode=mode.strip(), custom=prompt.strip())
    out = {"success": True, "state": post["state"], "mode": built["mode"],
           "prompt": built["prompt"], "warnings": built["warnings"],
           "image": "", "error": ""}
    if dry:
        return out

    try:
        made = await wa_image.generate(built["full"])
        out.update(image=made["image"], cached=made["cached"], model=made["model"])
    except Exception as e:                               # noqa: BLE001
        # Not a 500. The card renders without a picture, and a button that
        # errors out is a button that gets pressed once and never again.
        out["error"] = str(e)
    return out


@router.post("/wa-extra")
async def wa_extra_suggest(state: str = Query(..., min_length=2, max_length=60),
                           _: str = Depends(require_admin)):
    """और क्या डालें — candidate lines for this state's post beyond the भाव.

    Two tiers, and the order matters. `facts` are built by services/wa_extra
    from our own data — today's prices against their MSP floor, our own latest
    headline — and need no model, no key and no network; they are offered
    first and are usually the better line. `suggestions` are the model's
    rewordings of exactly those facts, each carrying its own `flags`.

    Nothing here changes a post. The owner reads, picks one or none, and the
    chosen line goes back through /admin/wa-post as `extra`, where it is
    screened again before it can reach the text. Never 500s: an empty
    suggestion list with a readable `error` is a normal morning.
    """
    from backend.services import wa_extra, wa_post as svc

    post = svc.post_for(state)
    if not post:
        raise HTTPException(status_code=404, detail="इस राज्य की आज कोई पोस्ट नहीं है")
    return {"success": True, "state": post["state"], **await wa_extra.suggest(post)}

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
    from backend.config import (update_setting, get_all_settings, ALLOWED_GEMINI_MODELS,
                                ALLOWED_GEMINI_IMAGE_MODELS, ALLOWED_CLAUDE_MODELS)

    if "gemini_model" in payload:
        model = payload["gemini_model"]
        if model not in ALLOWED_GEMINI_MODELS:
            raise HTTPException(400, f"Unknown model. Allowed: {ALLOWED_GEMINI_MODELS}")

    # Billed per image, not per token — an unrecognised name here is an
    # unbounded bill, so it is checked the same way the text model is.
    if "gemini_image_model" in payload:
        model = payload["gemini_image_model"]
        if model not in ALLOWED_GEMINI_IMAGE_MODELS:
            raise HTTPException(400, f"Unknown image model. Allowed: {ALLOWED_GEMINI_IMAGE_MODELS}")

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

    # The profile joins on User.user_id, not MandiAlert.user_id: mandi_alerts
    # keys on users.id like every other child table, while user_profiles keys
    # on the account number. The already-joined User row is the bridge.
    q = db.query(MandiAlert, User, UserProfile) \
          .outerjoin(User,        User.id        == MandiAlert.user_id) \
          .outerjoin(UserProfile, UserProfile.user_id == User.user_id)
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


# ── 🔔 Alert system control ───────────────────────────────────
# The subscriber table above answers "who signed up". These answer "is any of
# it working", which is the question that went unasked for 57 days while
# push_enabled() was missing and every run died silently.

@router.get("/alerts/health")
async def alerts_health(
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    """Delivery health for the 🔔 system, in one call.

    `ever_notified` is the number that matters. Alerts and devices both climbed
    into the seventies while it sat at zero, and nothing on the panel said so —
    the subscriber list looked healthy because every row in it was real."""
    from sqlalchemy import text as _sql
    from backend.services.app_settings import get_all
    from backend.services.push_service import (
        MIN_MOVE_PCT, MIN_MOVE_RS, push_enabled)

    def _one(sql):
        try:
            return db.execute(_sql(sql)).scalar()
        except Exception:
            return None

    active   = int(_one("SELECT count(*) FROM mandi_alerts WHERE active") or 0)
    total    = int(_one("SELECT count(*) FROM mandi_alerts") or 0)
    devices  = int(_one("SELECT count(*) FROM push_subscriptions WHERE active") or 0)
    dead     = int(_one("SELECT count(*) FROM push_subscriptions WHERE NOT active") or 0)
    ever     = int(_one("SELECT count(*) FROM mandi_alerts "
                        "WHERE last_notified_on IS NOT NULL") or 0)
    today_n  = int(_one("SELECT count(*) FROM mandi_alerts "
                        "WHERE last_notified_on = CURRENT_DATE") or 0)
    last     = _one("SELECT max(last_notified_on) FROM mandi_alerts")
    # Alerts whose owner has no reachable device — subscribed, undeliverable.
    orphan   = int(_one("""
        SELECT count(*) FROM mandi_alerts a
         WHERE a.active
           AND NOT EXISTS (
                 SELECT 1 FROM push_subscriptions s
                  WHERE s.active
                    AND (CASE WHEN a.user_id IS NULL
                              THEN s.id = a.subscription_id
                              ELSE s.user_id = a.user_id END))""") or 0)

    cfg = get_all()
    return {
        "success": True,
        "vapid_configured": push_enabled(),
        "settings": cfg,
        "defaults": {"min_move_rs": MIN_MOVE_RS, "min_move_pct": MIN_MOVE_PCT},
        "stats": {
            "alerts_active":    active,
            "alerts_total":     total,
            "devices_active":   devices,
            "devices_dead":     dead,
            "ever_notified":    ever,
            "notified_today":   today_n,
            "never_notified":   active - ever if active > ever else 0,
            "undeliverable":    orphan,
            "last_delivery":    last.isoformat() if hasattr(last, "isoformat") else (last or None),
        },
    }


class AlertSettingsIn(BaseModel):
    sending_enabled: Optional[bool]  = None
    bell_visible:    Optional[bool]  = None
    min_move_rs:     Optional[float] = None
    min_move_pct:    Optional[float] = None


@router.post("/alerts/settings")
async def alerts_settings(
    body: AlertSettingsIn,
    who:  str = Depends(require_admin),
):
    """Change how the bell behaves, without a deploy.

    Only the fields actually sent are written, so the panel can toggle one
    switch without having to echo back the rest of the form and risk clobbering
    a value somebody else just changed."""
    from backend.services.app_settings import set_many

    mapping = {
        "alerts.sending_enabled": body.sending_enabled,
        "alerts.bell_visible":    body.bell_visible,
        "alerts.min_move_rs":     body.min_move_rs,
        "alerts.min_move_pct":    body.min_move_pct,
    }
    values = {k: v for k, v in mapping.items() if v is not None}
    if not values:
        raise HTTPException(400, "कुछ बदलने को नहीं मिला।")
    return {"success": True, "settings": set_many(values, who=str(who))}


@router.post("/alerts/run")
async def alerts_run(_: str = Depends(require_admin)):
    """Run the alert pass now, instead of waiting for the next fetch sweep.

    This DELIVERS to real phones. It is the same function the scheduler calls,
    including the once-a-day and minimum-move dedupes, so pressing it twice in
    a row sends nothing the second time."""
    from backend.services.push_service import run_mandi_alerts
    return {"success": True, "result": run_mandi_alerts()}


@router.post("/alerts/test")
async def alerts_test(
    user_id: Optional[int] = Query(None, description="Send to this account's devices; omit for the newest device"),
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    """Send one obviously-labelled test notification.

    Marked as a test in the body itself. A test push that looked like a real
    bhav alert would be indistinguishable from the thing it is testing, and a
    farmer acting on a made-up price is the one outcome this system must never
    produce — so it carries no number at all."""
    from backend.database.db import PushSubscription
    from backend.services.push_service import push_enabled, send_push

    if not push_enabled():
        raise HTTPException(503, "VAPID कुंजी कॉन्फ़िगर नहीं — कुछ नहीं भेजा जा सकता।")

    q = db.query(PushSubscription).filter(PushSubscription.active.is_(True))
    if user_id is not None:
        q = q.filter(PushSubscription.user_id == user_id)
    devices = q.order_by(PushSubscription.id.desc()).limit(5).all()
    if not devices:
        raise HTTPException(404, "कोई चालू डिवाइस नहीं मिला।")

    payload = {
        "title": "KrashiMitra — टेस्ट सूचना",
        "body":  "यह जाँच के लिए भेजी गई है। कोई भाव नहीं बदला।",
        "url":   "https://krashimitra.in/bhav",
        "tag":   "bhav-test",
    }
    ok = sum(1 for d in devices if send_push(db, d, payload))
    db.commit()
    return {"success": ok > 0, "sent": ok, "tried": len(devices),
            "message": f"{ok}/{len(devices)} डिवाइस पर टेस्ट भेजा गया।"}


# ── 🔔 Custom broadcast ───────────────────────────────────────

class BroadcastIn(BaseModel):
    title:     str
    body:      str
    url:       Optional[str] = None
    audience:  str = "alerts"            # 'alerts' (has a 🔔) or 'all' (any device)
    commodity: Optional[str] = None
    state:     Optional[str] = None
    district:  Optional[str] = None
    dry:       bool = True               # preview by default — see the docstring
    # The recipient count the operator was shown when they pressed preview. A
    # send whose real audience differs is refused rather than delivered.
    expect_recipients: Optional[int] = None


# Notification text is truncated by the OS, not by us, and a cut-off sentence
# reads as a broken app. These are the practical limits across Android Chrome.
TITLE_MAX = 60
BODY_MAX  = 180


def _broadcast_devices(db, b: BroadcastIn):
    """The distinct devices a broadcast would reach.

    Deduplicated by endpoint: a farmer with three 🔔s that all match the filter
    is one person and must receive one notification, not three."""
    from backend.database.db import MandiAlert, PushSubscription

    q = db.query(PushSubscription).filter(PushSubscription.active.is_(True))

    if b.audience == "all":
        return q.all()

    # 'alerts' — only farmers who actually asked for bhav notifications, and
    # optionally only those watching a particular crop or place. An alert
    # reaches its account's devices when it has one, else the device that
    # created it (the same rule push_service._devices_for uses).
    a = db.query(MandiAlert).filter(MandiAlert.active.is_(True))
    if b.commodity:
        a = a.filter(MandiAlert.commodity == b.commodity.strip())
    if b.state:
        a = a.filter(MandiAlert.state == b.state.strip())
    if b.district:
        a = a.filter(MandiAlert.district == b.district.strip())
    alerts = a.all()
    if not alerts:
        return []

    uids = {x.user_id for x in alerts if x.user_id is not None}
    sids = {x.subscription_id for x in alerts if x.user_id is None}

    from sqlalchemy import or_
    conds = []
    if uids:
        conds.append(PushSubscription.user_id.in_(uids))
    if sids:
        conds.append(PushSubscription.id.in_(sids))
    if not conds:
        return []
    return q.filter(or_(*conds)).all()


def _price_claim_warning(text: str) -> Optional[str]:
    """Flag a hand-typed rupee figure. Advisory, never a block.

    Every other number this site publishes comes from the feed and carries its
    own date. A broadcast is the one place a price can be typed from memory and
    land on 70 lock screens with our name on it, where it is indistinguishable
    from a real bhav alert. The operator may well have a good reason — so this
    warns and lets them proceed, rather than deciding for them."""
    if re.search(r"[₹]\s*\d|\b\d{3,}\s*(रु|रुपये|/क्विं)", text or ""):
        return ("इसमें एक भाव लिखा है जो हमारे डेटा से नहीं आया — "
                "भेजने से पहले जाँच लें कि यह सही और आज का है।")
    return None


@router.post("/alerts/broadcast")
async def alerts_broadcast(
    body: BroadcastIn,
    who:  str     = Depends(require_admin),
    db:   Session = Depends(admin_db),
):
    """Send a hand-written notification to subscribers.

    Two-step by design: `dry: true` (the default) resolves the audience and
    returns the count and a sample WITHOUT sending, and the real call must echo
    that count back as `expect_recipients`. A broadcast cannot be unsent, and
    the gap between "I think this goes to Raisen" and "this goes to everyone"
    is one unticked checkbox — so the count the operator saw has to match the
    count the server is about to deliver to, or nothing goes out.

    Deliberately NOT routed through run_mandi_alerts(): this must ignore quiet
    hours, the once-a-day dedupe and the minimum-move rule, all of which exist
    to stop *automated* price pushes being noisy. A person deciding to send a
    specific message has already made that judgement."""
    from backend.database.db import PushBroadcast
    from backend.services.push_service import push_enabled, send_push

    title = (body.title or "").strip()
    text  = (body.body or "").strip()
    if not title or not text:
        raise HTTPException(400, "शीर्षक और संदेश दोनों चाहिए।")
    if len(title) > TITLE_MAX:
        raise HTTPException(400, f"शीर्षक {TITLE_MAX} अक्षर से छोटा रखें।")
    if len(text) > BODY_MAX:
        raise HTTPException(400, f"संदेश {BODY_MAX} अक्षर से छोटा रखें।")
    if body.audience not in ("alerts", "all"):
        raise HTTPException(400, "audience 'alerts' या 'all' होना चाहिए।")

    devices = _broadcast_devices(db, body)
    warning = _price_claim_warning(title + " " + text)

    if body.dry:
        # Who, concretely — a count alone does not tell an operator whether the
        # filter did what they meant.
        sample = [{"user_id": d.user_id,
                   "endpoint": (d.endpoint or "")[:48] + "…"} for d in devices[:5]]
        return {"success": True, "dry": True, "recipients": len(devices),
                "sample": sample, "warning": warning,
                "message": (f"{len(devices)} डिवाइस पर जाएगा।" if devices
                            else "इस फ़िल्टर पर कोई डिवाइस नहीं मिला।")}

    if not push_enabled():
        raise HTTPException(503, "VAPID कुंजी कॉन्फ़िगर नहीं — कुछ नहीं भेजा जा सकता।")
    if not devices:
        raise HTTPException(404, "इस फ़िल्टर पर कोई डिवाइस नहीं मिला।")
    if body.expect_recipients is None:
        raise HTTPException(400, "पहले प्रीव्यू करें — expect_recipients चाहिए।")
    if body.expect_recipients != len(devices):
        raise HTTPException(409,
            f"पहले {body.expect_recipients} डिवाइस दिखे थे, अब {len(devices)} हैं — "
            "फिर से प्रीव्यू करके भेजें।")

    payload = {"title": title, "body": text,
               "url": (body.url or "").strip() or "https://krashimitra.in/bhav",
               # Its own tag, so a broadcast never replaces a price alert
               # sitting in the tray (they share one tag per crop otherwise).
               "tag": "km-broadcast"}
    ok = sum(1 for d in devices if send_push(db, d, payload))

    db.add(PushBroadcast(title=title, body=text, url=payload["url"],
                         audience=body.audience, commodity=body.commodity,
                         state=body.state, district=body.district,
                         devices=len(devices), sent=ok, sent_by=str(who)[:120]))
    db.commit()
    return {"success": ok > 0, "sent": ok, "tried": len(devices),
            "warning": warning,
            "message": f"{ok}/{len(devices)} डिवाइस पर भेजा गया।"}


@router.get("/alerts/broadcasts")
async def alerts_broadcast_history(
    limit: int = Query(25, ge=1, le=100),
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    """What we have already told farmers. Answers "did I send this yesterday?"
    before the operator sends it again."""
    from backend.database.db import PushBroadcast
    rows = (db.query(PushBroadcast)
              .order_by(PushBroadcast.created_at.desc())
              .limit(limit).all())
    return {"success": True, "total": len(rows), "broadcasts": [{
        "id": r.id, "title": r.title, "body": r.body, "url": r.url,
        "audience": r.audience,
        "target": ", ".join(x for x in [r.commodity, r.district, r.state] if x) or "everyone",
        "devices": r.devices, "sent": r.sent, "sent_by": r.sent_by,
        "created_at": r.created_at.isoformat() if r.created_at else "",
    } for r in rows]}


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
        # Keyed by account number (user_profiles.user_id), so the lookup below
        # goes through user.user_id — NOT user.id.
        profiles = {p.user_id: p for p in db.query(UserProfile).all() if p.user_id is not None}
        users = db.query(User).all()

        needle = _norm(q)
        needle_id = None
        if needle and needle.isdigit():
            needle_id = int(needle)

        farmers = []
        for user in users:
            profile = profiles.get(user.user_id)
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
# The dealer types what he sells on /dukanlisting; the photos are put on here.
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


# ── Placement: which /bhav page a dealer is shown on ──────────
# The thing that is actually sold. Eligibility (paid, verified, live) is a
# different question and lives on the Buyer row; a dealer can satisfy every one
# of those and still be shown nowhere, which is precisely the mistake these
# endpoints exist to make visible and fixable.


def _page_label(idx: dict, crop: str, state: str, district: str = "") -> dict:
    """One searchable /bhav page, named the way a person would say it."""
    from backend.routes import bhav
    from backend.services import page_stats, placements

    return {
        "url":        placements.page_url(crop, state, district),
        "crop":       crop,
        "state":      state,
        "district":   district,
        "kind":       "district" if district else "state",
        "crop_hi":    bhav._hindi_name(idx.get("crops", {}).get(crop, crop)),
        "state_hi":   idx.get("states", {}).get(crop, {}).get(state, state),
        "district_hi": (idx.get("dists", {}).get(crop, {})
                           .get(state, {}).get(district, district)),
        "price":      placements.slot_price(crop, state, district),
        "tier":       placements.tier_of(crop, state, district),
        "tier_label": placements.tier_label(placements.tier_of(crop, state, district)),
        # What the page actually did, on the row the owner is about to sell.
        # None = no data yet, 0 = Google showed it to nobody — the panel says
        # different things for each, because only one of them is a reason not
        # to take the money.
        "traffic":    page_stats.for_page(crop, state, district),
    }


@router.get("/bhav/pages")
async def search_bhav_pages(
    q:     str = "",
    slug:  str = "",
    limit: int = 25,
    _: str = Depends(require_admin),
):
    """Search the real /bhav pages a dealer could be placed on.

    Only pages that EXIST are returned, and that is the point of doing this
    server-side against the live index rather than letting the panel build a
    URL from a crop name. A dealer whose only crop is sugarcane in UP has no
    page anywhere — data.gov reports no UP cane mandi rows, because cane goes
    to mills at SAP — and the honest answer is an empty result list, not a slot
    quietly sold on a URL that 404s.

    `slug` biases the results toward that dealer's own state and district,
    which is what is wanted 95% of the time.
    """
    from backend.routes import bhav
    from backend.services import buyers, placements

    idx = bhav._get_index()
    # Tokenised, and it accepts a pasted URL. Typing "/bhav/wheat" is the
    # obvious thing to do in a box that lists URLs, and a single-substring
    # match answered that with "कोई पेज नहीं मिला" — indistinguishable from
    # "this crop has no page", which is the one answer this box must get right.
    # Splitting on / and whitespace turns both "/bhav/wheat/uttar-pradesh" and
    # "wheat bijnor" into tokens; every token has to match, so more words
    # narrow rather than widen.
    tokens = [t for t in re.split(r"[\s/,]+", placements.norm(q)) if t and t != "bhav"]
    home_state = home_district = ""
    dealer_crops: set = set()
    if slug:
        d = buyers.by_id(slug) or {}
        if not d:
            from backend.services import dealers as _dealers
            row = _dealers.get(slug) if hasattr(_dealers, "get") else None
            d = {"state": getattr(row, "state", ""), "district": getattr(row, "district", ""),
                 "commodities": []} if row else {}
        home_state = placements.norm(d.get("state", "")).replace(" ", "-")
        home_district = placements.norm(d.get("district", "")).replace(" ", "-")
        dealer_crops = {placements.norm(c) for c in (d.get("commodities") or [])}

    def matches(*parts) -> bool:
        if not tokens:
            return True
        hay = " ".join(placements.norm(str(p)) for p in parts if p)
        return all(t in hay for t in tokens)

    out, seen = [], set()
    for crop, states in idx.get("states", {}).items():
        crop_hi = bhav._hindi_name(idx.get("crops", {}).get(crop, crop))
        for state, state_name in states.items():
            # the state page (₹999)
            if matches(crop, crop_hi, state, state_name):
                key = (crop, state, "")
                if key not in seen:
                    seen.add(key)
                    out.append(_page_label(idx, crop, state))
            dists = idx.get("dists", {}).get(crop, {}).get(state, {})
            for district, district_name in dists.items():
                if not matches(crop, crop_hi, district, district_name, state, state_name):
                    continue
                key = (crop, state, district)
                if key not in seen:
                    seen.add(key)
                    out.append(_page_label(idx, crop, state, district))

    def sort_key(p):
        return (
            0 if p["district"] and p["district"] == home_district else 1,
            0 if p["state"] == home_state else 1,
            0 if placements.norm(p["crop"]) in dealer_crops else 1,
            0 if p["kind"] == "district" else 1,
            p["url"],
        )

    out.sort(key=sort_key)
    limit = max(1, min(int(limit or 25), 100))
    for p in out[:limit]:
        p["slots"] = placements.slots_on(p["crop"], p["state"], p["district"])
        p["crop_is_his"] = placements.norm(p["crop"]) in dealer_crops if slug else True
    return {"success": True, "pages": out[:limit], "total": len(out)}


@router.get("/buyers/{slug}/placements")
async def list_buyer_placements(
    slug: str,
    _: str = Depends(require_admin),
):
    from backend.services import placements
    return {"success": True, "placements": placements.for_dealer(slug)}


@router.post("/buyers/{slug}/placements")
async def add_buyer_placement(
    slug:    str,
    payload: dict,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    """{"crop": "...", "state": "...", "district": "", "rank": 1, "price": 999}

    Any of crop/state/district may be "*" — that is how the wide plans are
    sold. See services/placements.py::TIERS for the five shapes.

    A crop the dealer does not deal in is allowed on purpose — the owner knows
    his dealers better than a comma-separated list does — and the panel warns
    before sending it. What is NOT allowed is selling a pattern that covers no
    real page: on an exact page that would be a slot on a 404, and on a
    wildcard it would be worse — an invoice for 1,800 pages, none of which
    exist. _pattern_covers() is the one check for both.
    """
    from backend.services import placements

    crop, state, district = placements.normalise_pattern(
        payload.get("crop"), payload.get("state"), payload.get("district") or "")

    covered = _pattern_covers(crop, state, district)
    if not covered:
        raise HTTPException(400, f"{placements.page_url(crop, state, district)} "
                                 f"covers no page that exists")

    row = _dealer_write(placements.set_placement, db, slug, crop, state,
                        district, payload.get("rank"), payload.get("price"))
    if not row:
        raise HTTPException(400, "rank must be 1, 2 or 3, and the pattern must "
                                 "be one of the five sold tiers")
    return {"success": True, "pages_covered": covered,
            "placements": placements.for_dealer(slug)}


def _pattern_covers(crop: str, state: str, district: str) -> int:
    """How many real /bhav pages this placement pattern would appear on.

    Also the honesty check before money changes hands: quoting ₹6,999 for
    "wheat across UP" is only defensible if we can say it is 74 real pages, and
    a pattern that resolves to zero is a sale that must not happen.
    """
    from backend.routes import bhav
    from backend.services import placements

    idx = bhav._get_index()
    W = placements.WILD
    crops = ([c for c in idx.get("crops", {}) if bhav._is_crop(idx["crops"][c])]
             if crop == W else [crop])

    n = 0
    for c in crops:
        states = idx.get("states", {}).get(c, {})
        for s in (states if state == W else [state]):
            if s not in states:
                continue
            dists = idx.get("dists", {}).get(c, {}).get(s, {})
            if district == W:
                n += len(dists) + 1        # every district page, plus the state page
            elif district == "":
                n += 1                     # the state landing page only
            elif district in dists:
                n += 1
    return n


@router.get("/placements/capacity")
async def placement_capacity(
    crop:     str = "",
    state:    str = "",
    district: str = "",
    _: str = Depends(require_admin),
):
    """Is there anything left to sell here, and is it guaranteed to render?

    Called before quoting. Over-selling used to be self-correcting because a
    sale simply evicted the previous holder on one visible page; a wide plan
    renders on 1,800 pages, so the fourth buyer's disappointment is invisible
    without asking first.
    """
    from backend.services import placements
    cap = placements.capacity(crop, state, district)
    cap["pages_covered"] = _pattern_covers(
        *placements.normalise_pattern(crop, state, district))
    return {"success": True, **cap}


@router.get("/placements/rates")
async def placement_rates(_: str = Depends(require_admin)):
    """The rate card, straight from services/placements.py, so the panel can
    never quote a number the backend does not charge."""
    from backend.services import page_stats, placements
    return {"success": True,
            "season_months": placements.SEASON_MONTHS,
            "slots": placements.SLOTS,
            "local_cap": placements.LOCAL_CAP,
            "year_seasons_charged": placements.YEAR_SEASONS_CHARGED,
            "year_seasons_given": placements.YEAR_SEASONS_GIVEN,
            "district_rate": placements.PRICE_DISTRICT,
            "crop_rate": placements.PRICE_CROP,
            "list_district_rate": placements.LIST_DISTRICT,
            "list_crop_rate": placements.LIST_CROP,
            "custom_floor": placements.CUSTOM_FLOOR,
            "custom_min_impressions": placements.CUSTOM_MIN_IMPRESSIONS,
            "stats_age_days": page_stats.snapshot_age_days(),
            "stats_stale": page_stats.is_stale(),
            "patterns": [{"key": k, "label": v["label"], "local": v["local"]}
                         for k, v in placements.TIERS.items()]}


@router.get("/placements/custom-quote")
async def custom_page_quote(
    crop:     str = "",
    state:    str = "",
    district: str = "",
    _: str = Depends(require_admin),
):
    """What the hand-sold single-page tier is worth on THIS page, and whether
    it should be offered at all.

    Refuses below the impression gate rather than returning the floor: of
    ~12,900 crop×district pages, most got no clicks at all last month, and
    quoting ₹4,999 on one of those buys a season of revenue and loses the
    buyer permanently."""
    from backend.services import placements
    return {"success": True, **placements.custom_quote(crop, state, district)}


@router.delete("/placements/{placement_id}")
async def remove_placement(
    placement_id: int,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    from backend.services import placements
    if not _dealer_write(placements.clear_placement, db, placement_id):
        raise HTTPException(404, "Unknown placement")
    return {"success": True}


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
    # A /dukanlisting account's real fee is dealers.quote() over however many
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
    from backend.services import pay_links
    pack = upi.collect(row.name or "", row.district or "",
                       amount=amount or None, ref=pay_links.ref("listing", slug))
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
    """Absolute URL of the dealer's /pay/listing/{slug} page — it gets pasted into WhatsApp, so a
    site-relative path would arrive as unclickable text.

    `amount` is carried explicitly rather than left for /pay to re-derive: the
    figure in the WhatsApp message and the figure on the page the dealer opens
    have to be the same number, and only the caller knows whether this is the
    standard fee, a renewal, or a rate that was negotiated on the phone. /pay
    re-clamps it, so a hand-edited URL still cannot produce a ₹0 QR."""
    from backend.services import pay_links
    return pay_links.url("listing", slug, amount)


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
    from backend.routes.admin_ledger import entry_or_400
    e = entry_or_400(db, payload, limit=upi.MAX_AMOUNT)
    try:
        months = max(1, min(12, int(payload.get("months") or 1)))
    except (TypeError, ValueError):
        months = 1
    row = _dealer_write(dealers.record_payment, db, slug, e.amount, e.ref, months,
                        received_at=e.received_at, method=e.method,
                        payer=e.payer, note=e.note, tds=e.tds)
    if not row:
        raise HTTPException(404, "Unknown dealer")
    return {"success": True, "counts": dealers.counts(db), "funnel": dealers.funnel(db)}


# ── Blue-tick membership queue ───────────────────────────────
# The tick is a paid membership (changed 2026-09-18) — it claims nothing about
# the seller, so there is no phone call to make and no review to pass. What is
# left for a human is the one thing UPI cannot do: confirm that the money
# actually landed. `payment` is therefore the button that grants the badge,
# `approve` is the owner's complimentary grant, and `reject` is the kill switch
# for impersonation. See backend/services/seller_verify.py.
#
# The queue sorts itself by who is waiting on whom: a farmer who has pressed
# "मैंने पैसे भेज दिए" and has no badge yet is at the top, every time.

# A membership is a renewal business, so a term running out IS work — the
# owner has to ask before it lapses, not after. Seven days is the window a
# WhatsApp reminder can still land in.
EXPIRING_DAYS = 7


def _wa_phone(raw) -> str:
    """A number wa.me will accept, or "".

    India only, because every seller on this site is in India: ten digits get
    91 in front, a number that already carries it is left alone, and anything
    else returns empty so the panel shows no WhatsApp button rather than a link
    that opens a chat with nobody.
    """
    d = "".join(ch for ch in str(raw or "") if ch.isdigit())
    if len(d) == 10:
        return "91" + d
    if len(d) == 12 and d.startswith("91"):
        return d
    if len(d) == 11 and d.startswith("0"):
        return "91" + d[1:]
    return ""


@router.get("/verifications")
def list_verifications(
    status: str = Query("", max_length=20),
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    """The queue, and the money behind it.

    `status` takes the five real statuses plus two synthetic views that match
    how this screen is actually used:

      todo      — anybody waiting on a human: a claimed payment to confirm, an
                  unpaid signup to chase, a term about to run out.
      expiring  — live memberships with a week or less left.

    The money block is deliberately computed over EVERY row, not the filtered
    page: "₹ इस महीने" must not change because somebody clicked a filter.
    """
    from datetime import datetime, timedelta

    from sqlalchemy import and_, func, or_

    from backend.database.db import SellerVerification, User, UserProfile
    from backend.services import seller_verify, upi

    seller_verify.expire_due(db)

    now = datetime.utcnow()
    soon = now + timedelta(days=EXPIRING_DAYS)

    q = db.query(SellerVerification)
    if status == "todo":
        # Claimed-but-unconfirmed, unpaid signups, and terms about to lapse.
        q = q.filter(or_(
            SellerVerification.status == seller_verify.APPLIED,
            and_(SellerVerification.status.in_(tuple(seller_verify.ACTIVE_STATUSES)),
                   SellerVerification.valid_until.isnot(None),
                   SellerVerification.valid_until <= soon),
        ))
    elif status == "expiring":
        q = q.filter(SellerVerification.status.in_(tuple(seller_verify.ACTIVE_STATUSES)),
                     SellerVerification.valid_until.isnot(None),
                     SellerVerification.valid_until <= soon)
    elif status and status in seller_verify.STATUSES:
        q = q.filter(SellerVerification.status == status)
    rows = seller_verify.pending_first(
        q.order_by(SellerVerification.updated_at.desc()).limit(300).all())

    users = {}
    if rows:
        ids = {r.user_id for r in rows}
        users = {u.id: u for u in db.query(User).filter(User.id.in_(ids)).all()}

    items = []
    for r in rows:
        u = users.get(r.user_id)
        chosen = seller_verify.plan(r.plan)
        # Three states, and the panel needs all three separately: nothing yet,
        # he says he sent it, and a human has seen it in the bank.
        if r.paid_at:
            pay_status = "received"
        elif seller_verify.payment_claimed(r):
            pay_status = "claimed"
        else:
            pay_status = "pending"
        items.append({
            "ref":        r.ref,
            "user_id":    r.user_id,
            "email":      u.email if u else None,
            "verified_now": bool(u.seller_verified) if u else False,
            "status":     r.status,
            "active":     seller_verify.is_active(r),
            "plan":       chosen["code"],
            "plan_hi":    chosen["term_hi"],
            "plan_price": chosen["price"],
            "pay_status": pay_status,
            # Digits only, country code included — wa.me refuses anything else.
            "wa_phone":   _wa_phone(r.phone),
            "expiring":   bool(seller_verify.is_active(r) and r.valid_until
                               and r.valid_until <= soon),
            "payment_claimed_at": (r.payment_claimed_at.isoformat()
                                   if r.payment_claimed_at else None),
            "full_name":  r.full_name,
            "phone":      r.phone,
            "village":    r.village,
            "district":   r.district,
            "state":      r.state,
            "id_kind":    r.id_kind,
            "id_kind_hi": seller_verify.ID_KIND_HI.get(r.id_kind or "", ""),
            "note":       r.note,
            "fee_amount": r.fee_amount,
            "paid_at":    r.paid_at.isoformat() if r.paid_at else None,
            "paid_ref":   r.paid_ref,
            "refunded_at": r.refunded_at.isoformat() if r.refunded_at else None,
            "refund_due": seller_verify.refund_due(r),
            "reject_reason": r.reject_reason,
            "reviewed_by": r.reviewed_by,
            "valid_until": r.valid_until.isoformat() if r.valid_until else None,
            "days_left":  seller_verify.days_left(r),
            "applied_at": r.created_at.isoformat() if r.created_at else None,
            "pay_url":    f"https://krashimitra.in/verify",
        })

    counts = {}
    for s in seller_verify.STATUSES:
        counts[s] = db.query(SellerVerification).filter(
            SellerVerification.status == s).count()
    # What the panel's own summary strip counts: money waiting to be confirmed.
    awaiting = sum(1 for i in items if i["pay_status"] == "claimed")

    # ── The money, over the whole table ──
    # This screen sells a membership and never said what the membership earned.
    # Without it the owner cannot tell a good week from a bad one, which is the
    # only question a paid product has to answer.
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    def _sum(*filters):
        return int(db.query(func.coalesce(func.sum(SellerVerification.fee_amount), 0))
                     .filter(*filters).scalar() or 0)

    money = {
        "collected_month": _sum(SellerVerification.paid_at.isnot(None),
                                SellerVerification.paid_at >= month_start),
        "collected_total": _sum(SellerVerification.paid_at.isnot(None)),
        # Signed up and never paid — the number the owner can actually go and
        # collect today, which is the whole point of showing it.
        "pending":         _sum(SellerVerification.status == seller_verify.APPLIED),
        "active":          db.query(SellerVerification).filter(
                               SellerVerification.status.in_(
                                   tuple(seller_verify.ACTIVE_STATUSES))).count(),
        "expiring":        db.query(SellerVerification).filter(
                               SellerVerification.status.in_(
                                   tuple(seller_verify.ACTIVE_STATUSES)),
                               SellerVerification.valid_until.isnot(None),
                               SellerVerification.valid_until <= soon).count(),
        "awaiting":        awaiting,
        "refunds_due":     sum(1 for i in items if i["refund_due"]),
    }

    return {"success": True, "data": {
        "items": items, "counts": counts,
        "awaiting_confirm": awaiting,
        "money": money,
        "expiring_days": EXPIRING_DAYS,
        # Sent once, not per row: the panel builds each WhatsApp message on the
        # client, and a collect pack per row would be one HTTP call per farmer.
        "upi": {"configured": upi.configured(), "vpa": upi.vpa(),
                "payee": upi.payee_name()},
        "plans": seller_verify.plans(),
        "fee": seller_verify.fee(),
        "months": seller_verify.months()}}


@router.get("/verifications/{ref}/collect")
def verification_collect(
    ref: str,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    """QR + link + a ready-to-send WhatsApp message for one application."""
    from backend.routes.verify import _pay_pack
    from backend.services import seller_verify
    from backend.utils.hindi_translit import readable

    row = seller_verify.by_ref(db, ref)
    if not row:
        raise HTTPException(404, "Unknown application")
    pack = _pay_pack(row)
    name = (row.full_name or "").strip()
    chosen = seller_verify.plan(row.plan)
    # Says what he is buying and what it is not, in the same words /verify uses.
    # It may never offer a check, a verification or a guarantee — the badge is a
    # membership, and a WhatsApp message is as public a claim as a web page.
    pack["whatsapp"] = (
        f"नमस्ते {name}, कृषि मित्र से।\n\n"
        f"कृषि मित्र प्रीमियम (नीला टिक) का शुल्क ₹{pack['amount']} है "
        f"— {chosen['term_hi']}।\n"
        f"QR वाला पेमेंट पेज: {pack['pay_url']}\n"
        f"UPI: {pack['vpa']}\n"
        f"आपका नंबर: {row.ref}\n\n"
        f"पैसा पहुँचते ही हम आपका नीला टिक चालू कर देंगे।\n"
        f"नीला टिक प्रीमियम सदस्यता का निशान है — यह पहचान की जाँच या फसल, भाव "
        f"या सौदे की गारंटी नहीं है।\n"
        f"https://krashimitra.in/verify"
    )
    return {"success": True, "data": pack}


@router.post("/verifications/{ref}/payment")
def record_verification_payment(
    ref:     str,
    payload: dict,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    """Money arrived — and this is what turns the tick on.

    Hand-entered from the bank app, because a upi:// hand-off has no callback.
    Under the old phone-check tick this endpoint was forbidden from granting
    the badge; the badge is now a paid membership, so payment is the whole of
    it and there is nothing left to review. Press this when you have seen the
    credit, not when the farmer says you will.
    """
    from backend.services import seller_verify, upi
    from backend.routes.admin_ledger import entry_or_400

    if not seller_verify.by_ref(db, ref):
        raise HTTPException(404, "Unknown application")
    e = entry_or_400(db, payload, limit=upi.MAX_AMOUNT)
    row = seller_verify.record_payment(db, ref, e.amount, e.ref,
                                       received_at=e.received_at, method=e.method,
                                       payer=e.payer, note=e.note, tds=e.tds)
    if not row:
        raise HTTPException(404, "Unknown application")
    return {"success": True, "data": {
        "status": row.status,
        "paid": True,
        "active": seller_verify.is_active(row),
        "valid_until": row.valid_until.isoformat() if row.valid_until else None,
        "days_left": seller_verify.days_left(row),
    }}


@router.post("/verifications/{ref}/approve")
def approve_verification(
    ref:     str,
    payload: dict = None,
    _:  str      = Depends(require_admin),
    db: Session  = Depends(admin_db),
):
    """Give the badge away — a complimentary membership, no payment.

    The ordinary paid grant is /payment above. This is for the ones you choose
    to hand out: the first sellers on a new district page, someone you already
    know, a goodwill month. It adds a term on top of whatever is left, so it is
    safe to press on a live membership.
    """
    from backend.services import seller_verify

    by = ((payload or {}).get("by") or "admin")
    row = seller_verify.approve(db, ref, by=by)
    if not row:
        raise HTTPException(404, "Unknown application")
    return {"success": True, "data": {
        "status": row.status,
        "valid_until": row.valid_until.isoformat() if row.valid_until else None,
        "days_left": seller_verify.days_left(row),
    }}


@router.post("/verifications/{ref}/reject")
def reject_verification(
    ref:     str,
    payload: dict = None,
    _:  str      = Depends(require_admin),
    db: Session  = Depends(admin_db),
):
    """Take the badge away. The kill switch, and it marks the refund due.

    A membership that claims nothing about its holder still cannot be sold to
    someone posing as someone else, so this is the answer to impersonation, to
    a member pushing a scam behind the tick, and to a chargeback. A term cut
    short was not delivered, so the money goes back — send it, then hit
    /refund to record that you did.
    """
    from backend.services import seller_verify

    payload = payload or {}
    reason = (payload.get("reason") or "").strip()
    if not seller_verify.by_ref(db, ref):
        raise HTTPException(404, "Unknown application")
    # He reads this — in the email, KrashiBook, /verify and his profile.
    if not reason:
        raise HTTPException(400, "कारण लिखें — सदस्य को यही दिखेगा")
    row = seller_verify.revoke(db, ref, reason=reason, by=payload.get("by") or "admin")
    emailed = seller_verify.notify(db, row)
    return {"success": True, "data": {"status": row.status,
                                      "refund_due": seller_verify.refund_due(row),
                                      "emailed": emailed}}


@router.post("/verifications/{ref}/decline")
def decline_verification(
    ref:     str,
    payload: dict = None,
    _:  str      = Depends(require_admin),
    db: Session  = Depends(admin_db),
):
    """Refuse an application that never got a tick, and tell him.

    Not /reject: that removes a live tick and owes a refund. This is for an
    `applied` row — a claimed payment that never reached the bank, a duplicate,
    details that are plainly not his. The reason is required because he reads
    it, on /verify, on his profile and in the email. The email is best-effort:
    `emailed` says whether it went, so the panel can offer WhatsApp when not.
    """
    from backend.services import seller_verify

    payload = payload or {}
    reason = (payload.get("reason") or "").strip()
    if not seller_verify.by_ref(db, ref):
        raise HTTPException(404, "Unknown application")
    if not reason:
        raise HTTPException(400, "कारण लिखें — सदस्य को यही दिखेगा")
    try:
        row = seller_verify.decline(db, ref, reason, by=payload.get("by") or "admin")
    except seller_verify.NotDeclinable as e:
        raise HTTPException(
            409, f"सिर्फ़ 'भुगतान बाकी' वाला आवेदन रद्द हो सकता है (अभी: {e}). "
                 "चालू टिक के लिए '✕ टिक हटाएँ' दबाएँ।")
    emailed = seller_verify.notify(db, row)
    return {"success": True, "data": {"status": row.status, "emailed": emailed}}


@router.post("/verifications/{ref}/refund")
def record_verification_refund(
    ref: str,
    payload: dict = None,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    """The refund actually went out. Hand-entered, same rule as paid_at.

    The admin types the amount sent back, and it must be the whole fee (that is
    the refund /verify promises); a different number is a typo or a different
    refund, and either way it does not go in the ledger as this one.
    """
    from backend.services import seller_verify
    from backend.routes.admin_ledger import entry_or_400

    row = seller_verify.by_ref(db, ref)
    if not row:
        raise HTTPException(404, "Unknown application")
    if not row.refunded_at:
        e = entry_or_400(db, payload)
        if e.tds:
            raise HTTPException(400, "रिफंड में TDS नहीं होता — वह खाना खाली छोड़िए")
        if row.paid_at and row.fee_amount and e.amount != int(row.fee_amount):
            raise HTTPException(
                400, f"रिफंड पूरी फ़ीस ₹{row.fee_amount} का होता है; आपने ₹{e.amount} लिखा")
        row = seller_verify.record_refund(db, ref, sent_at=e.received_at, method=e.method,
                                          refund_ref=e.ref, payer=e.payer, note=e.note)
    return {"success": True, "data": {"refunded_at": row.refunded_at.isoformat()}}
