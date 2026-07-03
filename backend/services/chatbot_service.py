# ============================================================
# services/chatbot_service.py
# KrashiMitra — Chatbot Service
# Flow: Cache → RAG → Gemini (multi-key, async) → Ollama fallback
# ============================================================

import json
import os
import httpx

from backend.config import get_setting

# ── Bad answer phrases — never cache these ────────────────────
BAD_ANSWER_PHRASES = [
    "क्षमा करें, अभी AI सेवा",
    "AI सेवा उपलब्ध नहीं",
    "i cannot", "i don't know", "i am not able",
    "as an ai", "i'm sorry",
]

def is_good_answer(answer: str) -> bool:
    """Reject empty, too short, or error-message answers before caching."""
    if not answer or len(answer.strip()) < 20:
        return False
    lower = answer.lower()
    return not any(phrase.lower() in lower for phrase in BAD_ANSWER_PHRASES)


# ── Website feature suggestions ──────────────────────────────
# After answering a farmer's question, surface the most relevant KrashiMitra
# tool so the assistant actively guides users to site features. Deterministic
# (intent keywords → feature) so it's reliable, testable and token-free.
# First matching rule wins, so order = priority.
FEATURE_RULES = [
    {
        "id": "mandi",
        "url": "mandi.html",
        "keywords": [
            "भाव", "कीमत", "रेट", "मंडी", "दाम", "मूल्य", "क्विंटल",
            "बेच", "बेचना", "बेचूं", "बेचूँ", "बेचनी",
            "price", "rate", "mandi", "sell", "bhav", "daam", "quintal", "bhaav",
        ],
        "label": {
            "hindi": "📊 आज का मंडी भाव देखें",
            "kannada": "📊 ಇಂದಿನ ಮಂಡಿ ಬೆಲೆ ನೋಡಿ",
            "english": "📊 See today's mandi prices",
        },
    },
    {
        "id": "shop",
        "url": "shop.html",
        "keywords": [
            "बीज", "खाद", "उर्वरक", "यूरिया", "डीएपी", "कीटनाशक", "दवा", "दवाई",
            "स्प्रे", "छिड़काव", "उपकरण", "खरीद", "खरीदना", "खरपतवार",
            "रोग", "बीमारी", "इलाज", "कीट", "फफूंद",
            "seed", "fertilizer", "urea", "dap", "npk", "pesticide", "spray",
            "tool", "buy", "khareed", "khaad", "disease", "pest", "fungus",
        ],
        "label": {
            "hindi": "🛒 बीज/खाद/दवा खरीदें (दुकान)",
            "kannada": "🛒 ಬೀಜ/ಗೊಬ್ಬರ ಖರೀದಿಸಿ (ಅಂಗಡಿ)",
            "english": "🛒 Buy seeds / fertilizer (Shop)",
        },
    },
    {
        "id": "yojana",
        "url": "sarkari_yojana.html",
        # NOTE: use "फसल बीमा" / "बीमा योजना" (not bare "बीमा") — "बीमा" is a
        # substring of "बीमारी" (disease) and would wrongly match crop-disease
        # questions to the schemes page.
        "keywords": [
            "योजना", "सब्सिडी", "अनुदान", "ऋण", "लोन", "फसल बीमा", "बीमा योजना",
            "सरकारी", "scheme", "subsidy", "loan", "insurance", "pm kisan",
            "किसान सम्मान", "kcc", "credit card", "yojana", "yojna",
        ],
        "label": {
            "hindi": "🏛️ सरकारी योजनाएं देखें",
            "kannada": "🏛️ ಸರ್ಕಾರಿ ಯೋಜನೆಗಳು ನೋಡಿ",
            "english": "🏛️ See govt schemes",
        },
    },
    {
        "id": "articles",
        "url": "articles/index.html",
        "keywords": [
            "कैसे", "तरीका", "विधि", "गाइड", "कब",
            "उगाना", "बुवाई", "सिंचाई", "पैदावार", "उत्पादन",
            "how", "guide", "method", "when", "grow",
            "irrigation", "yield", "kaise",
        ],
        "label": {
            "hindi": "📰 विस्तृत खेती गाइड पढ़ें",
            "kannada": "📰 ವಿವರವಾದ ಕೃಷಿ ಮಾರ್ಗದರ್ಶಿ ಓದಿ",
            "english": "📰 Read detailed farming guides",
        },
    },
]


# Features that aren't keyword-matched here but are surfaced by the router
# (e.g. the weather redirect intercepts weather questions before this runs).
_EXTRA_FEATURES = {
    "weather": {
        "url": "weather.html",
        "label": {
            "hindi": "🌤️ मौसम देखें",
            "kannada": "🌤️ ಹವಾಮಾನ ನೋಡಿ",
            "english": "🌤️ Check weather",
        },
    },
}


def _lang_key(language: str) -> str:
    lang = (language or "hindi").lower()
    if lang in ("kannada", "kn"):
        return "kannada"
    if lang in ("english", "en"):
        return "english"
    return "hindi"


def feature_suggestion(feature_id: str, language: str = "hindi") -> dict | None:
    """Build a {id, url, label} chip for a known feature id (any language)."""
    meta = _EXTRA_FEATURES.get(feature_id)
    if not meta:
        meta = next(({"url": r["url"], "label": r["label"]}
                     for r in FEATURE_RULES if r["id"] == feature_id), None)
    if not meta:
        return None
    lk = _lang_key(language)
    return {
        "id": feature_id,
        "url": meta["url"],
        "label": meta["label"].get(lk, meta["label"]["hindi"]),
    }


# Greetings / small talk — used to suppress a weak "articles" suggestion that
# only matched on generic words like "कैसे" (as in "आप कैसे हैं" = how are you).
_GREETINGS = [
    "नमस्ते", "नमस्कार", "प्रणाम", "राम राम", "हैलो", "हेलो", "हाय",
    "कैसे हैं", "कैसे हो", "धन्यवाद", "शुक्रिया",
    "hello", "hii", "hey", "thanks", "thank you", "how are you", "good morning",
]


def suggest_feature(question: str, language: str = "hindi") -> dict | None:
    """
    Map a farmer's question to the most relevant KrashiMitra feature.
    Returns {id, url, label} for a clickable chip, or None when nothing
    is clearly relevant (we don't force a suggestion on every message).
    """
    if not question:
        return None
    q = question.lower()
    lk = _lang_key(language)
    for rule in FEATURE_RULES:
        if any(kw.lower() in q for kw in rule["keywords"]):
            # Don't push a generic "read guides" chip on a plain greeting.
            if rule["id"] == "articles" and any(g in q for g in _GREETINGS):
                return None
            return {
                "id": rule["id"],
                "url": rule["url"],
                "label": rule["label"].get(lk, rule["label"]["hindi"]),
            }
    return None


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
    Scores topics by keyword overlap with the question — returns top 10.
    """
    data = all_crops.get(crop_key, {})
    if not data:
        return ""

    if question:
        q_words = set(question.lower().split())
        scored = []
        for topic, content in data.items():
            topic_words = set(topic.lower().replace("_", " ").split())
            answer_words = set(content.get("answer", "").lower().split()[:20])
            overlap = len(q_words & (topic_words | answer_words))
            scored.append((overlap, topic, content))
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
        else (
            "Answer only in simple Kannada."
            if (language or "").lower() in ("kannada", "kn")
            else "Answer in simple English only."
        )
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
    Reads model/timeout from runtime config (admin-controllable).
    Disables thinking tokens to protect quota.
    """
    model   = get_setting("gemini_model",   "gemini-1.5-flash")
    timeout = get_setting("gemini_timeout", 15.0)

    # Collect all configured keys (dedup, preserve order)
    keys = []
    seen = set()
    for key_name in [
        "GEMINI_API_KEY",
        "GEMINI_API_KEY2", "GEMINI_API_KEY_2",
        "GEMINI_API_KEY3", "GEMINI_API_KEY_3",
    ]:
        k = os.getenv(key_name, "").strip()
        if k and k not in seen:
            keys.append((key_name, k))
            seen.add(k)

    if not keys:
        raise ValueError("No Gemini API key configured in environment")

    # generationConfig — disable thinking for models that support it, to save quota
    gen_config: dict = {
        "temperature":     0.3,
        "maxOutputTokens": 500,
        "topP":            0.8,
    }
    if "2.5" in model or "3.5" in model:
        gen_config["thinkingConfig"] = {"thinkingBudget": 0}

    last_error = None
    async with httpx.AsyncClient(timeout=timeout) as client:
        for key_name, api_key in keys:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model}:generateContent?key={api_key}"
            )
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": gen_config,
            }
            try:
                resp = await client.post(url, json=payload)
                if resp.status_code == 429:
                    print(f"[Gemini] {key_name} quota exceeded, trying next key...")
                    last_error = f"{key_name}: 429 quota exceeded"
                    continue
                resp.raise_for_status()
                data = resp.json()
                answer = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                print(f"[Gemini] ✅ Success with {key_name} ({model})")
                return answer
            except httpx.TimeoutException:
                print(f"[Gemini] {key_name} timed out after {timeout}s")
                last_error = f"{key_name}: timeout"
                continue
            except Exception as e:
                print(f"[Gemini] {key_name} failed: {e}")
                last_error = str(e)
                continue

    raise Exception(f"All Gemini keys failed. Last error: {last_error}")


# ── Ollama local fallback (ASYNC) ─────────────────────────────
async def call_ollama(prompt: str) -> str:
    """Call local Ollama — only when ollama_enabled=true in settings."""
    model    = get_setting("ollama_model",   "gemma3:4b")
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    hindi_prefix = "You must respond ONLY in Hindi. हिंदी में उत्तर दें।\n\n"
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

    If Gemini returns a substantive answer (even if borderline quality),
    we use it rather than discarding it. Only true error/refusal messages
    are discarded and fall through to Ollama.
    """
    # ── Try Gemini ────────────────────────────────────────────
    try:
        answer = await call_gemini(prompt)
        if is_good_answer(answer):
            return answer, "gemini"
        # Gemini gave a valid but very short or borderline answer.
        # Only fall through if it looks like a refusal — not just short.
        is_refusal = any(p.lower() in answer.lower() for p in BAD_ANSWER_PHRASES)
        if not is_refusal and len(answer.strip()) >= 10:
            print(f"[AI] Gemini short answer (len={len(answer)}), using anyway")
            return answer, "gemini"
        print("[AI] Gemini returned a refusal/error message, trying Ollama")
    except Exception as e:
        print(f"[AI] Gemini failed: {e}")

    # ── Try Ollama fallback ───────────────────────────────────
    if not get_setting("ollama_enabled", False):
        print("[AI] Ollama fallback disabled (ollama_enabled=false in settings)")
        return (
            "क्षमा करें, अभी AI सेवा उपलब्ध नहीं है। कृपया थोड़ी देर बाद पुनः प्रयास करें।",
            "error",
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
        "error",
    )
