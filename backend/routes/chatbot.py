# ============================================================
# routes/chatbot.py
# KrashiMitra — Chatbot Router
# Full pipeline: Cache → RAG → Gemini (multi-key) → Ollama
# ============================================================

import asyncio
import os
import sys

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

from backend.database.db import ChatHistory, get_db
from backend.services.chatbot_service import (
    build_context,
    build_prompt,
    call_ollama,   # now async
    call_ai,       # now async
    get_crop_keys,
    is_good_answer,
)

# ── Resolve project root once at module level (not inside handler) ──
_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# ── Pre-import cache + RAG at startup (not per-request) ──────
try:
    from cache.cache_engine import search_cache, save_to_cache
    _CACHE_AVAILABLE = True
    print("[Cache] ✅ Cache engine loaded")
except Exception as e:
    _CACHE_AVAILABLE = False
    print(f"[Cache] ❌ Cache unavailable: {e}")

try:
    from rag.retriever import retrieve_with_context
    _RAG_AVAILABLE = True
    print("[RAG] ✅ RAG retriever loaded")
except Exception as e:
    _RAG_AVAILABLE = False
    print(f"[RAG] ❌ RAG unavailable: {e}")

router = APIRouter()


class Question(BaseModel):
    q:        str
    crop:     str = "wheat_up"
    language: str = "hindi"
    district: str = "Uttar Pradesh"
    user_id:  Optional[int] = None


# ── Weather redirect keywords ─────────────────────────────────
WEATHER_KEYWORDS = [
    "weather", "mausam", "मौसम", "temperature", "rain",
    "बारिश", "तापमान", "ठंड", "गर्मी", "forecast", "बाढ़"
]

def is_weather_question(q: str) -> bool:
    return any(w in q.lower() for w in WEATHER_KEYWORDS)


# ── Total timeout — must finish BEFORE Render gateway kills us ─
PIPELINE_TIMEOUT = float(os.getenv("PIPELINE_TIMEOUT", "50"))  # seconds


@router.post("/ask")
async def ask(body: Question, db: Session = Depends(get_db)):   # ← async
    """
    Full pipeline: Cache → RAG → Gemini (async) → Ollama → error.
    Wrapped in asyncio.wait_for so we ALWAYS respond before Render's
    60-second gateway timeout (returns 200 + error message, not 502).
    """
    try:
        return await asyncio.wait_for(
            _ask_pipeline(body, db),
            timeout=PIPELINE_TIMEOUT,
        )
    except asyncio.TimeoutError:
        print(f"[ASK] ⏰ Pipeline timed out after {PIPELINE_TIMEOUT}s for: {body.q[:50]}")
        return {
            "question": body.q,
            "answer":   "⏰ सर्वर अभी व्यस्त है। कृपया 30 सेकंड बाद दोबारा पूछें।",
            "source":   "timeout",
            "cached":   False,
            "rag_chunks": 0,
        }
    except Exception as e:
        print(f"[ASK] ❌ Unexpected error: {e}")
        return {
            "question": body.q,
            "answer":   "क्षमा करें, कुछ गड़बड़ हो गई। कृपया दोबारा कोशिश करें।",
            "source":   "error",
            "cached":   False,
            "rag_chunks": 0,
        }


async def _ask_pipeline(body: Question, db: Session) -> dict:
    """Inner pipeline — can be timed out by the caller."""

    # ── Weather redirect ──────────────────────────────────────
    if is_weather_question(body.q):
        return {
            "question": body.q,
            "answer":   "🌤️ मौसम की जानकारी के लिए कृपया 'Weather' tab पर जाएं — वहाँ आपके जिले का live मौसम और कृषि सलाह मिलेगी।",
            "source":   "redirect",
            "cached":   False,
            "rag_chunks": 0,
        }

    # ── Step 1: Cache check ───────────────────────────────────
    if _CACHE_AVAILABLE:
        try:
            cached = search_cache(body.q)
            if cached:
                print(f"[Cache] HIT score={cached['score']} q={body.q[:50]}")
                _save_to_db(db, body, body.q, cached["answer"])
                return {
                    "question": body.q,
                    "answer":   cached["answer"],
                    "source":   "cache",
                    "cached":   True,
                    "rag_chunks": 0,
                    "api_usage_saved": True,
                }
        except Exception as e:
            print(f"[Cache] Search failed: {e}")

    # ── Step 2: Crop JSON context ─────────────────────────────
    crop_context = build_context(body.crop, question=body.q)

    # ── Step 3: RAG retrieval (run in thread — ChromaDB is sync) ──
    rag_context = ""
    rag_chunks  = 0
    if _RAG_AVAILABLE:
        try:
            # ChromaDB + sentence-transformers are synchronous.
            # Run in a thread so we don't block the async event loop.
            chunks, rag_context = await asyncio.to_thread(
                retrieve_with_context, body.q, body.crop
            )
            rag_chunks = len(chunks)
            print(f"[RAG] {rag_chunks} chunks retrieved for: {body.q[:50]}")
        except Exception as e:
            print(f"[RAG] Retrieval failed: {e}")

    # ── Combine contexts — RAG first (more specific), crop JSON second ──
    if rag_context and crop_context:
        full_context = f"{rag_context}\n\n--- Crop Knowledge ---\n{crop_context}"
    elif rag_context:
        full_context = rag_context
    else:
        full_context = crop_context

    # ── Step 4: Conversation history ──────────────────────────
    history_text = ""
    if body.user_id:
        try:
            history_rows = db.query(ChatHistory).filter(
                ChatHistory.user_id == body.user_id
            ).order_by(ChatHistory.created_at.desc()).limit(6).all()
            history_rows.reverse()
            history_text = "\n".join([
                f"{row.role.upper()}: {row.message}" for row in history_rows
            ])
        except Exception as e:
            print(f"[History] Failed: {e}")

    # ── Step 5: Build prompt + call AI (awaited) ──────────────
    prompt = build_prompt(body.q, body.district, body.language, full_context, history_text)
    answer, source = await call_ai(prompt)   # ← await async call

    # ── Step 6: Save to DB ────────────────────────────────────
    _save_to_db(db, body, body.q, answer)

    # ── Step 7: Save to cache if AI gave good answer ──────────
    if source in ("gemini", "ollama") and _CACHE_AVAILABLE and is_good_answer(answer):
        try:
            saved = save_to_cache(body.q, answer, source=source)
            if saved:
                print(f"[Cache] Saved from {source}: {body.q[:50]}")
        except Exception as e:
            print(f"[Cache] Save failed: {e}")

    return {
        "question":        body.q,
        "answer":          answer,
        "source":          source,
        "cached":          False,
        "api_usage_saved": False,
        "rag_chunks":      rag_chunks,
        "rag_context":     rag_context[:300] if rag_context else "",
    }


def _save_to_db(db: Session, body: Question, question: str, answer: str):
    """Save user message + assistant reply to DB."""
    try:
        db.add(ChatHistory(
            user_id=body.user_id, crop=body.crop, district=body.district,
            role="user", message=question, language=body.language
        ))
        db.add(ChatHistory(
            user_id=body.user_id, crop=body.crop, district=body.district,
            role="assistant", message=answer, language=body.language
        ))
        db.commit()
    except Exception as e:
        print(f"[DB] Save failed: {e}")
        db.rollback()


@router.get("/chat/history/{user_id}")
def get_chat_history(user_id: int, db: Session = Depends(get_db)):
    rows = db.query(ChatHistory).filter(
        ChatHistory.user_id == user_id
    ).order_by(ChatHistory.created_at.asc()).all()
    return {"user_id": user_id, "messages": [
        {"role": row.role, "message": row.message,
         "crop": row.crop, "time": row.created_at}
        for row in rows
    ]}


@router.post("/reset")
def reset():
    return {"message": "Session reset. History saved in database."}


@router.get("/crops")
def get_crops():
    return {"crops": get_crop_keys()}
