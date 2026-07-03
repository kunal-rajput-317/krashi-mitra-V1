import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import shutil, secrets, json

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
