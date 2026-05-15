from fastapi import APIRouter
from backend.models import AskRequest, AskResponse, ResetResponse

router = APIRouter()
_sessions: dict[str, list] = {}


@router.post("/ask", response_model=AskResponse)
async def ask_question(req: AskRequest):
    """
    Full pipeline:
      1. Cache check       → instant return if similar Q seen before
      2. RAG retrieval     → fetch relevant agriculture knowledge
      3. Gemini AI         → generate Hindi answer using RAG context
      4. Ollama fallback   → if Gemini quota/unavailable
      5. Save to cache     → so next similar question is free
    """
    crop_key = req.crop or "general"
    if crop_key not in _sessions:
        _sessions[crop_key] = []
    _sessions[crop_key].append({"role": "user", "text": req.q})

    save_to_cache = None  # defined below if cache loads ok

    # ── Step 1: Cache check ───────────────────────────────────────────
    try:
        from cache.cache_engine import search_cache, save_to_cache as _save
        save_to_cache = _save
        cached = search_cache(req.q)
        if cached:
            _sessions[crop_key].append({"role": "bot", "text": cached["answer"]})
            return AskResponse(
                answer=cached["answer"],
                source="cache",
                cached=True,
            )
    except Exception:
        pass

    # ── Step 2: RAG retrieval ─────────────────────────────────────────
    rag_context = ""
    try:
        from rag.retriever import retrieve_with_context
        _, rag_context = retrieve_with_context(req.q, req.crop)
    except Exception:
        pass

    # ── Step 3 & 4: Gemini → Ollama ──────────────────────────────────
    from backend.ai_engine import generate_answer
    answer, source = await generate_answer(
        question    = req.q,
        crop        = req.crop or "general",
        district    = req.district or "",
        rag_context = rag_context,
    )

    # ── Step 5: Save to cache ─────────────────────────────────────────
    if source in ("gemini", "ollama") and save_to_cache:
        try:
            save_to_cache(req.q, answer, source=source)
        except Exception:
            pass

    _sessions[crop_key].append({"role": "bot", "text": answer})
    return AskResponse(answer=answer, source=source, cached=False)


@router.post("/reset", response_model=ResetResponse)
async def reset_chat(crop: str = "general"):
    _sessions.pop(crop, None)
    return ResetResponse(status="ok", message="Chat reset ho gaya ✅")