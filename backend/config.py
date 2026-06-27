# ============================================================
# backend/config.py
# KrashiMitra — Runtime Settings Store
# Admin-controllable settings that survive until server restart.
# Read from env on startup; updated via POST /admin/settings.
# ============================================================

import os

_settings: dict = {
    "gemini_model":           os.getenv("GEMINI_MODEL",        "gemini-1.5-flash"),
    "gemini_timeout":         float(os.getenv("GEMINI_TIMEOUT",  "15")),
    "cache_semantic_enabled": os.getenv("CACHE_SEMANTIC_ENABLED", "true").lower() == "true",
    "ollama_enabled":         os.getenv("OLLAMA_ENABLED",      "false").lower() == "true",
    "ollama_model":           os.getenv("OLLAMA_MODEL",        "gemma3:4b"),
    "pipeline_timeout":       float(os.getenv("PIPELINE_TIMEOUT", "50")),
}

ALLOWED_GEMINI_MODELS = [
    "gemini-1.5-flash",
    "gemini-2.0-flash",
    "gemini-2.5-flash",
    "gemini-1.5-pro",
    "gemini-2.0-flash-lite",
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
