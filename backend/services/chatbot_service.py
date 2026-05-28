# ============================================================
# services/chatbot_service.py
# KrashiMitra — Chatbot Service
# Flow: Cache → RAG → Gemini (multi-key, async) → Ollama fallback
# ============================================================

import json
import os
import httpx   # ← async HTTP (replaces synchronous `requests`)

# ── Bad answer phrases — never cache these ────────────────────
BAD_ANSWER_PHRASES = [
    "क्षमा करें, अभी AI सेवा",
    "AI सेवा उपलब्ध नहीं",
    "i cannot", "i don't know", "i am not able",
    "as an ai", "i'm sorry",
]

def is_good_answer(answer: str) -> bool:
    """Reject empty, too short, or error answers before caching."""
    if not answer or len(answer.strip()) < 20:
        return False
    lower = answer.lower()
    return not any(phrase.lower() in lower for phrase in BAD_ANSWER_PHRASES)


# ── Load all crop JSON files once at import ──────────────────
def _load_all_crops() -> dict:
    crops = {}
    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    crops_dir = os.path.join(project_root, "crops")
    if not os.path.exists(crops_dir):
        print(f"[crops] Warning: crops/ folder not found at {crops_dir}")
        return crops
    for filename in os.listdir(crops_dir):
        if filename.endswith(".json"):
            name = filename.replace(".json", "")
            with open(os.path.join(crops_dir, filename), "r", encoding="utf-8") as f:
                crops[name] = json.load(f)
    print(f"[crops] Loaded {len(crops)} crop files: {list(crops.keys())}")
    return crops

all_crops = _load_all_crops()


def get_crop_keys() -> list:
    return list(all_crops.keys())


def build_context(crop_key: str, question: str = "") -> str:
    """
    Build context from crop JSON.
    If question provided, return only relevant topics (max 10).
    Avoids sending entire JSON to Gemini.
    """
    data = all_crops.get(crop_key, {})
    if not data:
        return ""

    # If question given, score topics by keyword overlap
    if question:
        q_words = set(question.lower().split())
        scored = []
        for topic, content in data.items():
            topic_words = set(topic.lower().replace("_", " ").split())
            answer_words = set(content.get("answer", "").lower().split()[:20])
            overlap = len(q_words & (topic_words | answer_words))
            scored.append((overlap, topic, content))
        # Sort by relevance, take top 10
        scored.sort(reverse=True)
        items = scored[:10]
    else:
        items = [(0, t, c) for t, c in list(data.items())[:10]]

    lines = [f"- {topic}: {content['answer']}" for _, topic, content in items]
    return "\n".join(lines)


def build_prompt(question: str, district: str, language: str,
                 context: str, history_text: str) -> str:
    """Build final prompt — strict retrieval-first instructions."""
    lang_instruction = (
        "तुम्हें केवल सरल हिंदी में जवाब देना है। English बिल्कुल मत लिखो।"
        if (language or "").lower() in ("hindi", "hi")
        else ("Answer only in simple Kannada." if (language or "").lower() in ("kannada", "kn") else "Answer in simple English only.")
    )
    context_block = context.strip() if context.strip() else "No specific crop data available."

    return f"""You are KrashiMitra — agriculture assistant for UP farmers.
Farmer location: {district}

RULES (follow strictly):
1. {lang_instruction}
2. Max 5 lines. Direct and practical only.
3. Answer ONLY from the KNOWLEDGE BASE below.
4. If not found in knowledge base: say "इस विषय पर जानकारी नहीं है। कृपया नजदीकी कृषि केंद्र से पूछें।"
5. Give specific quantities, timing, product names where available.
6. Never hallucinate or guess.

KNOWLEDGE BASE:
{context_block}

HISTORY:
{history_text if history_text else "None"}

QUESTION: {question}

ANSWER:"""


# ── Gemini with multi-key rotation (ASYNC) ───────────────────
async def call_gemini(prompt: str) -> str:
    """
    Try all configured Gemini keys in order — fully async via httpx.
    Supports GEMINI_API_KEY, GEMINI_API_KEY2, GEMINI_API_KEY3.
    """
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    TIMEOUT = float(os.getenv("GEMINI_TIMEOUT", "15"))   # 15s per key — 3 keys × 15s = 45s max

    # Collect all configured keys (dedup)
    keys = []
    seen = set()
    for key_name in [
        "GEMINI_API_KEY",
        "GEMINI_API_KEY2",
        "GEMINI_API_KEY_2",
        "GEMINI_API_KEY3",
        "GEMINI_API_KEY_3",
    ]:
        k = os.getenv(key_name, "").strip()
        if k and k not in seen:
            keys.append((key_name, k))
            seen.add(k)

    if not keys:
        raise ValueError("No Gemini API key set in environment")

    last_error = None
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for key_name, api_key in keys:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{GEMINI_MODEL}:generateContent?key={api_key}"
            )
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature":     0.3,
                    "maxOutputTokens": 500,
                    "topP":            0.8,
                },
            }
            try:
                resp = await client.post(url, json=payload)
                if resp.status_code == 429:
                    print(f"[Gemini] {key_name} quota exceeded, trying next key...")
                    last_error = f"{key_name}: 429 quota"
                    continue
                resp.raise_for_status()
                data = resp.json()
                answer = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                print(f"[Gemini] ✅ Success with {key_name}")
                return answer
            except httpx.TimeoutException:
                print(f"[Gemini] {key_name} timed out after {TIMEOUT}s")
                last_error = f"{key_name}: timeout"
                continue
            except Exception as e:
                print(f"[Gemini] {key_name} failed: {e}")
                last_error = str(e)
                continue

    raise Exception(f"All Gemini keys failed. Last error: {last_error}")


# ── Ollama local fallback (ASYNC) ─────────────────────────────
async def call_ollama(prompt: str) -> str:
    """Call local Ollama — async. Only used when OLLAMA_ENABLED=true."""
    hindi_prefix = "You must respond ONLY in Hindi. हिंदी में उत्तर दें।\n\n"
    model    = os.getenv("OLLAMA_MODEL", "gemma4:e4b")
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{base_url}/api/generate",
            json={"model": model, "prompt": hindi_prefix + prompt, "stream": False},
        )
        resp.raise_for_status()
        return resp.json()["response"]


# ── Smart call: Gemini → Ollama (ASYNC) ───────────────────────
async def call_ai(prompt: str) -> tuple[str, str]:
    """
    Returns: (answer, source)
    source = "gemini" | "ollama" | "error"
    """
    # ── Try Gemini ────────────────────────────────────────────
    try:
        answer = await call_gemini(prompt)
        if is_good_answer(answer):
            return answer, "gemini"
        print("[AI] Gemini returned bad/short answer, trying Ollama")
    except Exception as e:
        print(f"[AI] Gemini failed: {e}")

    # ── Try Ollama fallback (if enabled) ──────────────────────
    if os.getenv("OLLAMA_ENABLED", "false").lower() != "true":
        print("[AI] Ollama fallback disabled (OLLAMA_ENABLED != true)")
        return (
            "क्षमा करें, अभी AI सेवा उपलब्ध नहीं है। कृपया थोड़ी देर बाद पुनः प्रयास करें।",
            "error"
        )

    try:
        answer = await call_ollama(prompt)
        if is_good_answer(answer):
            return answer, "ollama"
        print("[AI] Ollama returned bad answer")
    except Exception as e:
        print(f"[AI] Ollama failed: {e}")

    return (
        "क्षमा करें, अभी AI सेवा उपलब्ध नहीं है। कृपया थोड़ी देर बाद पुनः प्रयास करें।",
        "error"
    )
