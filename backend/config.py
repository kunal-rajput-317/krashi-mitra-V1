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
    "cache_semantic_enabled": os.getenv("CACHE_SEMANTIC_ENABLED", "true").lower() == "true",
    "ollama_enabled":         os.getenv("OLLAMA_ENABLED",      "false").lower() == "true",
    "ollama_model":           os.getenv("OLLAMA_MODEL",        "gemma3:4b"),
    "pipeline_timeout":       float(os.getenv("PIPELINE_TIMEOUT", "50")),
    # RAM-saving killswitches for low-memory hosts — set to "false" in env
    # to run cache-only (no ChromaDB index in memory, no Gemini/Ollama calls).
    "rag_enabled":            os.getenv("RAG_ENABLED",          "true").lower() == "true",
    "ai_enabled":             os.getenv("AI_RESPONSE_ENABLED",   "true").lower() == "true",
    # Claude (Anthropic) — OFF by default. Admin toggles it on only while
    # seeding the semantic cache with premium answers, then off again
    # (paid API — not meant for regular user traffic).
    "claude_enabled":         os.getenv("CLAUDE_ENABLED",      "false").lower() == "true",
    "claude_model":           os.getenv("CLAUDE_MODEL",        "claude-opus-4-8"),
    "claude_timeout":         float(os.getenv("CLAUDE_TIMEOUT",  "30")),
}

ALLOWED_GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-3.5-flash",
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
