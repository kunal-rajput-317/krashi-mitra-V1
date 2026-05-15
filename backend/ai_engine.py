"""
KrashiMitra AI Engine
=====================
Primary  : Gemini-2.5-flash
Fallback : Ollama local model (auto-switches on quota/network error)

Prompt is built as:
  System instruction (Hindi farming assistant rules)
  + RAG context (retrieved agriculture knowledge)
  + Farmer question
"""

import httpx
import json
import os

GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL    = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "gemma4:e4b")

# ── System prompt ─────────────────────────────────────────────────────
SYSTEM_PROMPT = """आप KrashiMitra हैं — भारतीय किसानों के लिए एक AI कृषि सहायक।

आपके नियम:
1. हमेशा सरल, व्यावहारिक हिंदी में उत्तर दें
2. उत्तर संक्षिप्त रखें — 3-5 वाक्य पर्याप्त हैं
3. तकनीकी शब्दों से बचें, आम बोलचाल की भाषा उपयोग करें
4. केवल वही सलाह दें जो आप निश्चित हों
5. अनिश्चित होने पर कहें "कृपया नजदीकी कृषि केंद्र से सलाह लें"
6. दवा/खाद की मात्रा हमेशा प्रति एकड़ बताएं
7. मौसम और फसल के अनुसार सलाह दें
8. किसान का समय और पैसा बचाने वाली सलाह दें

आप उत्तर प्रदेश और उत्तर भारत के किसानों की मदद करते हैं।"""


def _build_prompt(question: str, crop: str, district: str, rag_context: str) -> str:
    """Combine RAG context + farmer question into final prompt."""
    parts = []

    if rag_context:
        parts.append(rag_context)
        parts.append("---")

    crop_info = f"फसल: {crop}" if crop and crop != "general" else ""
    loc_info  = f"स्थान: {district}" if district else ""
    context_line = " | ".join(filter(None, [crop_info, loc_info]))
    if context_line:
        parts.append(context_line)

    parts.append(f"किसान का सवाल: {question}")
    return "\n".join(parts)


# ── Gemini ────────────────────────────────────────────────────────────
async def ask_gemini(prompt: str) -> str:
    """Call Gemini-2.5-flash API."""
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not set in .env")

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    )
    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature":     0.3,   # low = more factual, less creative
            "maxOutputTokens": 400,   # keep answers short
            "topP":            0.8,
        },
    }

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()


# ── Ollama ────────────────────────────────────────────────────────────
async def ask_ollama(prompt: str) -> str:
    """Call local Ollama model as fallback."""
    url = f"{OLLAMA_BASE_URL}/api/generate"

    full_prompt = f"{SYSTEM_PROMPT}\n\n{prompt}"

    payload = {
        "model":  OLLAMA_MODEL,
        "prompt": full_prompt,
        "stream": False,
        "options": {
            "temperature": 0.3,
            "num_predict": 300,
        },
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["response"].strip()


# ── Main entry point ──────────────────────────────────────────────────
async def generate_answer(
    question:    str,
    crop:        str = "general",
    district:    str = "",
    rag_context: str = "",
) -> tuple[str, str]:
    """
    Generate AI answer using Gemini with Ollama fallback.

    Returns: (answer_text, source_label)
    source_label: "gemini" | "ollama" | "error"
    """
    prompt = _build_prompt(question, crop, district, rag_context)

    # ── Try Gemini first ──────────────────────────────────────────────
    try:
        answer = await ask_gemini(prompt)
        return answer, "gemini"

    except ValueError as e:
        # API key not set — go straight to Ollama
        pass
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        if status == 429:
            # Quota exceeded — switch to Ollama
            pass
        elif status in (401, 403):
            # Bad key
            pass
        else:
            pass
    except Exception:
        pass

    # ── Try Ollama fallback ───────────────────────────────────────────
    try:
        answer = await ask_ollama(prompt)
        return answer, "ollama"
    except Exception:
        pass

    # ── Both failed — return safe Hindi message ───────────────────────
    return (
        "🙏 अभी AI सेवा उपलब्ध नहीं है। "
        "कृपया थोड़ी देर बाद पुनः प्रयास करें या "
        "नजदीकी कृषि केंद्र से सलाह लें।",
        "error",
    )