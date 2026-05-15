from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pathlib import Path
import shutil, secrets, json
from datetime import datetime

router  = APIRouter(prefix="/admin")
security = HTTPBasic()

# ── Simple hardcoded auth (replace with DB auth when going live) ──────
ADMIN_USER = "admin"
ADMIN_PASS = "krashi2025"   # change before deployment

UPLOAD_DIR = Path(__file__).parent.parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

def require_admin(creds: HTTPBasicCredentials = Depends(security)):
    ok_user = secrets.compare_digest(creds.username.encode(), ADMIN_USER.encode())
    ok_pass = secrets.compare_digest(creds.password.encode(), ADMIN_PASS.encode())
    if not (ok_user and ok_pass):
        raise HTTPException(status_code=401, detail="Invalid credentials",
                            headers={"WWW-Authenticate": "Basic"})
    return creds.username


# ── Upload PDF ────────────────────────────────────────────────────────
@router.post("/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    _: str = Depends(require_admin)
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(400, "Only PDF files allowed")

    dest = UPLOAD_DIR / file.filename
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Trigger re-indexing of the new PDF
    indexed = 0
    try:
        from rag.indexer import get_collection, index_pdf
        collection = get_collection()
        indexed = index_pdf(collection, dest)
    except Exception as e:
        pass  # index later — file is saved

    return {
        "status":   "uploaded",
        "filename": file.filename,
        "chunks_indexed": indexed,
        "saved_at": datetime.now().isoformat(),
    }


# ── List uploaded files ───────────────────────────────────────────────
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


# ── Delete uploaded file ──────────────────────────────────────────────
@router.delete("/files/{filename}")
async def delete_file(filename: str, _: str = Depends(require_admin)):
    target = UPLOAD_DIR / filename
    if not target.exists():
        raise HTTPException(404, "File not found")
    target.unlink()
    return {"status": "deleted", "filename": filename}


# ── Cache stats ───────────────────────────────────────────────────────
@router.get("/cache/stats")
async def cache_stats(_: str = Depends(require_admin)):
    try:
        from cache.cache_engine import get_cache_stats
        stats = get_cache_stats()
        # Strip embeddings from top_questions before sending to UI
        for q in stats.get("top_questions", []):
            q.pop("embedding", None)
        return stats
    except Exception as e:
        return {"error": str(e)}


# ── Clear cache ───────────────────────────────────────────────────────
@router.delete("/cache/clear")
async def clear_cache(_: str = Depends(require_admin)):
    try:
        from cache.cache_engine import clear_cache
        count = clear_cache()
        return {"status": "cleared", "deleted_entries": count}
    except Exception as e:
        raise HTTPException(500, str(e))


# ── Re-index all knowledge ────────────────────────────────────────────
# ── Delete single cache entry ────────────────────────────────
@router.delete("/cache/delete")
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


# ── Edit single cache entry answer ───────────────────────────
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


# ── Add Q&A entry manually ────────────────────────────────────
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
        # save_to_cache returns False for both duplicates and quality fails.
        # Re-check: if a semantic hit exists it's a duplicate, else quality fail.
        hit = search_cache(question)
        if hit:
            return {"saved": False, "duplicate": True}
        return {"saved": False, "reason": "quality check failed"}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/reindex")
async def reindex(_: str = Depends(require_admin)):
    try:
        from rag.indexer import run_indexing
        total = run_indexing(force=True)
        return {"status": "reindexed", "total_chunks": total}
    except Exception as e:
        raise HTTPException(500, str(e))


# ── System status ─────────────────────────────────────────────────────
@router.get("/status")
async def system_status():
    import os
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "gemma4:e4b")

    # Check Ollama
    ollama_ok = False
    try:
        import httpx
        r = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=2)
        ollama_ok = r.status_code == 200
    except Exception:
        pass

    # ChromaDB chunk count
    chroma_count = 0
    try:
        from rag.indexer import get_collection
        chroma_count = get_collection().count()
    except Exception:
        pass

    # Cache entry count
    cache_count = 0
    try:
        from cache.cache_engine import get_cache_stats
        cache_count = get_cache_stats()["total_entries"]
    except Exception:
        pass

    return {
        "gemini_configured": bool(GEMINI_API_KEY),
        "ollama_running":    ollama_ok,
        "ollama_model":      OLLAMA_MODEL,
        "chroma_chunks":     chroma_count,
        "cache_entries":     cache_count,
        "upload_dir":        str(UPLOAD_DIR),
        "checked_at":        datetime.now().strftime("%d %b %Y %H:%M:%S"),
    }