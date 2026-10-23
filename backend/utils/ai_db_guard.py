# ============================================================
# utils/ai_db_guard.py — an AI tool never connects to the live database
#
# LEGAL_RULES §4 / CLAUDE.md: whatever an AI coding tool reads is sent to its
# company, and the privacy policy does not allow farmers' data to go there.
# A rule in a markdown file is not enough: any script an AI runs that imports
# backend/database/db.py loads .env by itself and is connected to Neon.
#
# So every place that opens a database connection calls refuse_live_db_for_ai()
# first. When the process was started by an AI tool, only a database on this
# machine (SQLite, localhost) is allowed — the test suite still runs, the live
# one is refused before any connection is made. Owner, 24 Oct 2026: "make it
# impossible even if I give access."
#
# What it cannot stop: someone deliberately clearing these variables, or a
# password pasted into a chat. The complete fix is that the live password is
# not on the developer's PC at all — it lives in Render's settings.
#
# NEVER remove, weaken or bypass this, and never print the URL in the message.
# ============================================================
import os
from urllib.parse import urlsplit

# Set by the tool in every shell it starts. KM_AI_AGENT is ours, for any other
# AI tool: put `KM_AI_AGENT=1` in that tool's terminal environment.
AI_MARKERS = (
    "CLAUDECODE",
    "CLAUDE_CODE_ENTRYPOINT",
    "CLAUDE_CODE_SESSION_ID",
    "KM_AI_AGENT",
)

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class LiveDatabaseBlocked(RuntimeError):
    pass


def running_under_ai() -> bool:
    return any(os.getenv(k) for k in AI_MARKERS)


def is_local(url: str) -> bool:
    if url.startswith("sqlite"):
        return True
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return False
    return host in _LOCAL_HOSTS


def refuse_live_db_for_ai(url: str) -> None:
    """Raise before connecting if an AI tool is about to reach a non-local
    database. The message never contains the URL — it holds the password."""
    if url and running_under_ai() and not is_local(url):
        raise LiveDatabaseBlocked(
            "🔒 Live database blocked: this program was started by an AI tool. "
            "Farmers' data must never reach an AI service (LEGAL_RULES §4). "
            "Use the test database (pytest) — or run this yourself, in your own "
            "terminal, not through the AI.")
