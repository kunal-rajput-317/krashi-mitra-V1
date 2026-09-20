# ============================================================
# backend/config.py
# KrashiMitra — Runtime Settings Store
# Admin-controllable settings that survive until server restart.
# Read from env on startup; updated via POST /admin/settings.
# ============================================================

import os

_settings: dict = {
    "gemini_model":           os.getenv("GEMINI_MODEL",        "gemini-2.5-flash"),
    "gemini_timeout":         float(os.getenv("GEMINI_TIMEOUT",  "15")),
    # Image generation for the WhatsApp channel card (services/wa_image).
    # Separate model and a much longer timeout: drawing a picture takes tens of
    # seconds where a text answer takes two, and sharing gemini_timeout would
    # have meant every image "timed out" at 15s having already been billed.
    "gemini_image_model":     os.getenv("GEMINI_IMAGE_MODEL",   "gemini-2.5-flash-image"),
    "gemini_image_timeout":   float(os.getenv("GEMINI_IMAGE_TIMEOUT", "60")),
    "cache_semantic_enabled": os.getenv("CACHE_SEMANTIC_ENABLED", "true").lower() == "true",
    "ollama_enabled":         os.getenv("OLLAMA_ENABLED",      "false").lower() == "true",
    "ollama_model":           os.getenv("OLLAMA_MODEL",        "gemma3:4b"),
    "pipeline_timeout":       float(os.getenv("PIPELINE_TIMEOUT", "50")),
    # RAM-saving killswitches for low-memory hosts — set to "false" in env
    # to run cache-only (no ChromaDB index in memory, no Gemini/Ollama calls).
    "rag_enabled":            os.getenv("RAG_ENABLED",          "true").lower() == "true",
    "ai_enabled":             os.getenv("AI_RESPONSE_ENABLED",   "true").lower() == "true",
    # कृषि न्यूज़ auto-pilot — the AI half of it, as one switch.
    #
    # OFF means the news pipeline makes NO model call anywhere: no Gemini for
    # the headline and bullets, none for the image prompt, no Imagen, no
    # Pollinations. Staging still runs, the post is still built — from the
    # source text as written and a cover from our OWN photo library, which is
    # the same path the pipeline already takes whenever Gemini errors. So the
    # switch turns off spend, never the section.
    #
    # It gates the SCHEDULER too, not just the admin button. The auto-pilot
    # stages stories on its own every few days; a switch that only disarmed
    # the panel would leave the quota being spent by the half nobody is
    # watching, which is the half that matters when the reason for switching
    # off is a bill.
    "news_ai_enabled":        os.getenv("NEWS_AI_ENABLED",     "true").lower() == "true",
    # Claude (Anthropic) — OFF by default. Admin toggles it on only while
    # seeding the semantic cache with premium answers, then off again
    # (paid API — not meant for regular user traffic).
    "claude_enabled":         os.getenv("CLAUDE_ENABLED",      "false").lower() == "true",
    "claude_model":           os.getenv("CLAUDE_MODEL",        "claude-opus-4-8"),
    "claude_timeout":         float(os.getenv("CLAUDE_TIMEOUT",  "30")),
}

ALLOWED_GEMINI_MODELS = [
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-2.5-flash",
]

# Image models are billed PER IMAGE, not per token, so this list is short and
# deliberate: an unrecognised name here is an unbounded bill on a project whose
# whole infrastructure runs on free tiers.
ALLOWED_GEMINI_IMAGE_MODELS = [
    "gemini-2.5-flash-image",
    "gemini-3-pro-image",
]

ALLOWED_CLAUDE_MODELS = [
    "claude-opus-4-8",     # best quality — default for cache seeding
    "claude-sonnet-5",     # cheaper, near-Opus on most answers
    "claude-haiku-4-5",    # cheapest / fastest
]


def get_setting(key: str, default=None):
    return _settings.get(key, default)


def update_setting(key: str, value) -> bool:
    if key not in _settings:
        return False
    existing = _settings[key]
    if isinstance(existing, bool):
        _settings[key] = bool(value)
    elif isinstance(existing, float):
        _settings[key] = float(value)
    elif isinstance(existing, int):
        _settings[key] = int(value)
    else:
        _settings[key] = str(value)
    return True


def get_all_settings() -> dict:
    return dict(_settings)
