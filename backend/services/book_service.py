# ============================================================
# backend/services/book_service.py
# कृषि मित्र Book — the operating manual behind the admin panel
# ------------------------------------------------------------
# The goal, the standing rules, the mistakes that already cost us, the
# commands, and the free-tier arithmetic. All of it lived in three places
# before this: scattered across docs/, in the head of whoever last touched
# the file, and in commit messages nobody re-reads. A rule you have to
# remember is a rule you will break on the day you are busy.
#
# Content lives in backend/data/krashimitra_book.json and is read live, cached
# by mtime — the same arrangement as checklist.py, and for the same reason:
# editing a rule must be a file edit, not a deploy. There is deliberately no
# database table here. The Book holds no state; nothing is ticked, nothing is
# per-user, so there is nothing to migrate and nothing to lose.
#
# The one thing this module computes rather than reads is `live`: the days
# left to the deadline, taken from deadline_checklist.json so the Book and the
# Checklist page can never disagree about the date. A manual "days left" in
# the JSON would be wrong the morning after it was written.
#
# Runnable manually:  python -m backend.services.book_service
# ============================================================

import json
from datetime import date, datetime
from pathlib import Path

_DATA = Path(__file__).resolve().parents[1] / "data"
_PATH = _DATA / "krashimitra_book.json"
_CHECKLIST = _DATA / "deadline_checklist.json"

_cache: dict | None = None
_mtime: float = -1.0


def _spec() -> dict:
    global _cache, _mtime
    try:
        m = _PATH.stat().st_mtime
    except OSError:
        return {"sections": [], "error": f"{_PATH.name} not found"}
    if _cache is None or m != _mtime:
        try:
            _cache = json.loads(_PATH.read_text(encoding="utf-8"))
            _mtime = m
        except (OSError, ValueError) as e:
            # Keep serving the last good copy. A typo in the JSON should cost
            # you the edit, not the whole page.
            if _cache is None:
                return {"sections": [], "error": f"{_PATH.name} is not valid JSON: {e}"}
    return _cache or {"sections": []}


def _deadline() -> dict:
    """Days left, from the Checklist's own JSON — one date, two pages."""
    try:
        spec = json.loads(_CHECKLIST.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    raw = spec.get("deadline")
    try:
        d = datetime.strptime(str(raw), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return {}
    left = (d - date.today()).days
    return {
        "deadline": raw,
        "deadline_label": spec.get("deadline_label") or raw,
        "days_left": left,
        "passed": left < 0,
        "ref": spec.get("ref", ""),
    }


def get_book() -> dict:
    """The whole Book: sections as authored, plus the numbers that must not
    be hand-written. Entry ids are stable so a deep link into one rule keeps
    working after the text around it is reworded."""
    spec = _spec()
    sections = []
    for s in spec.get("sections", []):
        entries = [e for e in s.get("entries", []) if e.get("title")]
        if not entries:
            continue
        sections.append({
            "key": s.get("key", ""),
            "icon": s.get("icon", "•"),
            "title": s.get("title", ""),
            "sub": s.get("sub", ""),
            "count": len(entries),
            "entries": entries,
        })
    return {
        "title": spec.get("title", "कृषि मित्र Book"),
        "sub": spec.get("sub", ""),
        "ref": spec.get("ref", "backend/data/krashimitra_book.json"),
        "error": spec.get("error", ""),
        "live": _deadline(),
        "total": sum(s["count"] for s in sections),
        "sections": sections,
    }


if __name__ == "__main__":
    print(json.dumps(get_book(), indent=2, ensure_ascii=False))
