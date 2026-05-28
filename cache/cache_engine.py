"""
KrashiMitra Cache Engine
========================
In-memory embedding index for fast similarity search.
Persists to JSON on disk. Loads into RAM on first use.

Flow:
  search_cache(q) → embed q → cosine similarity → return if score >= threshold
  save_to_cache(q, a) → embed q → check duplicate → append → persist
"""

import json
import os
import re
from difflib import SequenceMatcher
import numpy as np
from datetime import datetime
from pathlib import Path

CACHE_FILE           = Path(__file__).parent / "cache_store.json"
SIMILARITY_THRESHOLD = 0.92
FUZZY_THRESHOLD      = 0.94
MAX_CACHE_SIZE       = 1000
CACHE_SEMANTIC_ENABLED = os.getenv("CACHE_SEMANTIC_ENABLED", "false").lower() == "true"

# ── In-memory index (loaded once, updated on write) ──────────
_index: list[dict] | None = None   # list of {question, answer, embedding, ...}

def _normalize_question(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"[?!.।,;:()\[\]{}\"']", " ", text)
    return " ".join(text.split())

def _is_same_question(a: str, b: str) -> bool:
    a_norm = _normalize_question(a)
    b_norm = _normalize_question(b)
    if not a_norm or not b_norm:
        return False
    if a_norm == b_norm:
        return True
    return SequenceMatcher(None, a_norm, b_norm).ratio() >= FUZZY_THRESHOLD

def _get_index() -> list[dict]:
    """Load cache into memory once. Subsequent calls return cached list."""
    global _index
    if _index is None:
        _index = _load_from_disk()
    return _index

def _load_from_disk() -> list[dict]:
    if not CACHE_FILE.exists():
        return []
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def _persist():
    """Write in-memory index to disk."""
    global _index
    if _index is None:
        return
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(_index, f, ensure_ascii=False, indent=2)

# Keep _load and _save as aliases for admin.py compatibility
def _load() -> list[dict]:
    return _get_index()

def _save(entries: list[dict]):
    global _index
    _index = entries
    _persist()


# ── Embedding model (lazy, singleton) ────────────────────────
_model = None

def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("intfloat/multilingual-e5-small")
        print("[Cache] Embedding model loaded")
    return _model

def _embed(text: str) -> list[float]:
    model = _get_model()
    vec = model.encode(f"query: {text}", normalize_embeddings=True)
    return vec.tolist()

def _cosine(a: list[float], b: list[float]) -> float:
    return float(np.dot(np.array(a), np.array(b)))


# ── Public API ────────────────────────────────────────────────
def search_cache(question: str) -> dict | None:
    """
    Search in-memory index for a semantically similar question.
    Returns cached entry or None.
    """
    index = _get_index()
    if not index:
        return None

    for entry in index:
        if _is_same_question(entry.get("question", ""), question):
            entry["hits"] = entry.get("hits", 0) + 1
            _persist()
            return {
                "answer":     entry["answer"],
                "score":      1.0,
                "source":     entry.get("source", "cache"),
                "original_q": entry["question"],
            }

    if not CACHE_SEMANTIC_ENABLED:
        return None

    q_vec = _embed(question)
    best_score = 0.0
    best_idx   = -1

    for i, entry in enumerate(index):
        emb = entry.get("embedding")
        if not emb:
            continue
        score = _cosine(q_vec, emb)
        if score > best_score:
            best_score = score
            best_idx   = i

    if best_score >= SIMILARITY_THRESHOLD and best_idx >= 0:
        index[best_idx]["hits"] = index[best_idx].get("hits", 0) + 1
        _persist()
        return {
            "answer":     index[best_idx]["answer"],
            "score":      round(best_score, 4),
            "source":     index[best_idx].get("source", "cache"),
            "original_q": index[best_idx]["question"],
        }

    return None


def save_to_cache(question: str, answer: str, source: str = "ai") -> bool:
    """
    Save Q&A to cache.
    Skips: duplicates, bad answers, error messages.
    """
    # Basic quality check
    if not answer or len(answer.strip()) < 20:
        return False

    index = _get_index()
    for entry in index:
        if _is_same_question(entry.get("question", ""), question):
            return False

    q_vec = _embed(question) if CACHE_SEMANTIC_ENABLED else None

    # Check for near-duplicate
    if CACHE_SEMANTIC_ENABLED and q_vec is not None:
        for entry in index:
            emb = entry.get("embedding")
            if emb and _cosine(q_vec, emb) >= SIMILARITY_THRESHOLD:
                return False  # already cached

    index.append({
        "question":  question,
        "answer":    answer,
        "source":    source,
        "embedding": q_vec,
        "hits":      0,
        "saved_at":  datetime.now().isoformat(),
    })

    # Prune if over limit — keep highest-hit entries
    if len(index) > MAX_CACHE_SIZE:
        index.sort(key=lambda x: x.get("hits", 0), reverse=True)
        del index[MAX_CACHE_SIZE:]

    _persist()
    return True


def get_cache_stats() -> dict:
    """Stats for admin panel — strips embeddings from top questions."""
    index = _get_index()
    total_hits = sum(e.get("hits", 0) for e in index)
    top = sorted(index, key=lambda x: x.get("hits", 0), reverse=True)[:10]
    # Strip embeddings before sending to UI
    top_clean = [{k: v for k, v in e.items() if k != "embedding"} for e in top]
    return {
        "total_entries":  len(index),
        "total_hits":     total_hits,
        "cache_file_kb":  round(CACHE_FILE.stat().st_size / 1024, 1) if CACHE_FILE.exists() else 0,
        "semantic_enabled": CACHE_SEMANTIC_ENABLED,
        "top_questions":  top_clean,
    }


def clear_cache() -> int:
    global _index
    count = len(_get_index())
    _index = []
    _persist()
    return count


def reload_cache():
    """Force reload from disk (useful after manual edits)."""
    global _index
    _index = None
    return _get_index()
