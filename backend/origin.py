# ============================================================
# backend/origin.py
# KrashiMitra — the backend's own public URL, from one place
# ------------------------------------------------------------
# Render reassigns the .onrender.com subdomain when a service is recreated,
# and it has done so twice. The URL was copy-pasted into 23 files, so each
# rename meant hunting all of them while the site was down — and the site does
# not look down, because Netlify keeps serving the static homepage while every
# proxied route 404s.
#
# So Python never hardcodes it. This module is the only reader:
#
#   BACKEND_ORIGIN env var   — wins, for a one-off override on Render
#   config/backend-origin.txt — the committed source of truth
#
# Cached by mtime, like every other live-config file in this project
# (checklist.py, credits.py, book_service.py), so editing the file takes
# effect on the next call with no restart.
# ============================================================

import os
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "config" / "backend-origin.txt"

# Only used if the file is missing or unreadable — a wrong-but-plausible URL
# would be worse than an obvious one, so this is the current host and nothing
# clever. Anything reading it should still work; the health page will say so.
_FALLBACK = "https://krashi-mitra-v1-muup.onrender.com"

_cache: tuple[float, str] | None = None


def backend_origin() -> str:
    """The backend's public https origin, no trailing slash."""
    env = os.getenv("BACKEND_ORIGIN", "").strip().rstrip("/")
    if env:
        return env

    global _cache
    try:
        mtime = _PATH.stat().st_mtime
    except OSError:
        return _FALLBACK
    if _cache and _cache[0] == mtime:
        return _cache[1]

    value = _FALLBACK
    try:
        for line in _PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("http"):
                value = line.rstrip("/")
                break
    except OSError:
        return _FALLBACK

    _cache = (mtime, value)
    return value


if __name__ == "__main__":
    print(backend_origin())
