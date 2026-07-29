# ============================================================
# services/checklist.py
# The owner's 31-Aug-2026 deadline checklist (admin panel).
#
# The plan lives in data/deadline_checklist.json; the progress lives in the
# admin_tasks table. This module is the join between them — see AdminTask in
# database/db.py for why the two are kept apart.
#
# Config is read live and cached by mtime, so adding or rewording a task is a
# file edit with no deploy and no migration, in line with the project's
# "everything automatic" rule.
# ============================================================
import json
from datetime import date, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from backend.database.db import AdminTask

_PATH = Path(__file__).resolve().parents[1] / "data" / "deadline_checklist.json"

_cache: dict | None = None
_mtime: float = -1.0

# Custom tasks the owner adds from the panel land here — their own section,
# appended after the curated ones so the plan always reads before the additions.
_MINE = {"key": "mine", "icon": "📌", "title": "मेरे काम — added by me",
         "sub": "Tasks you added yourself. They count towards the ring like any other."}


def _spec() -> dict:
    global _cache, _mtime
    try:
        m = _PATH.stat().st_mtime
    except OSError:
        return {"sections": []}
    if _cache is None or m != _mtime:
        try:
            _cache = json.loads(_PATH.read_text(encoding="utf-8"))
        except Exception:
            _cache = {"sections": []}
        _mtime = m
    return _cache


def _days_left(deadline: str) -> int | None:
    """Whole days from today to the deadline; negative once it has passed."""
    try:
        y, mo, d = (int(x) for x in deadline.split("-"))
        return (date(y, mo, d) - date.today()).days
    except Exception:
        return None


def board(db: Session) -> dict:
    """The whole panel in one payload: sections, tasks, tick state, progress."""
    spec = _spec()
    rows = {r.slug: r for r in db.query(AdminTask).all()}

    sections, done_n, total_n = [], 0, 0

    for sec in spec.get("sections", []):
        tasks = []
        for t in sec.get("tasks", []):
            slug = t.get("id", "")
            if not slug:
                continue
            row = rows.get(slug)
            is_done = bool(row and row.done)
            total_n += 1
            done_n += int(is_done)
            tasks.append({
                "id": slug,
                "title": t.get("title", ""),
                "note": t.get("note", ""),
                "owner": t.get("owner", "you"),
                "critical": bool(t.get("critical")),
                "custom": False,
                "done": is_done,
                "done_at": row.done_at.isoformat() if (row and row.done_at) else None,
            })
        if tasks:
            sections.append({
                "key": sec.get("key", ""), "icon": sec.get("icon", "•"),
                "title": sec.get("title", ""), "sub": sec.get("sub", ""),
                "tasks": tasks,
            })

    # ── the owner's own tasks ──
    mine = []
    for r in db.query(AdminTask).filter(AdminTask.custom == True).order_by(  # noqa: E712
            AdminTask.sort, AdminTask.id).all():
        total_n += 1
        done_n += int(bool(r.done))
        mine.append({
            "id": r.slug, "title": r.title or "", "note": r.note or "",
            "owner": "you", "critical": False, "custom": True,
            "done": bool(r.done),
            "done_at": r.done_at.isoformat() if r.done_at else None,
        })
    if mine:
        sections.append({**_MINE, "tasks": mine})

    return {
        "deadline": spec.get("deadline", ""),
        "deadline_label": spec.get("deadline_label", spec.get("deadline", "")),
        "days_left": _days_left(spec.get("deadline", "")),
        "ref": spec.get("ref", ""),
        "sections": sections,
        "progress": {
            "done": done_n,
            "total": total_n,
            "pct": round(done_n * 100 / total_n) if total_n else 0,
        },
    }


def _known_slugs() -> set:
    return {t.get("id") for s in _spec().get("sections", []) for t in s.get("tasks", [])}


def set_done(db: Session, slug: str, done: bool) -> bool:
    """Tick or untick. Creates the row on first touch for a seeded task."""
    row = db.query(AdminTask).filter(AdminTask.slug == slug).first()
    if row is None:
        if slug not in _known_slugs():
            return False                      # unknown task — never invent a row
        row = AdminTask(slug=slug, custom=False)
        db.add(row)
    row.done = bool(done)
    row.done_at = datetime.utcnow() if done else None
    db.commit()
    return True


def add_custom(db: Session, title: str, note: str = "") -> dict | None:
    """Add one of the owner's own tasks. Slug is generated, never user-supplied."""
    title = (title or "").strip()
    if not title:
        return None
    n = db.query(AdminTask).filter(AdminTask.custom == True).count()  # noqa: E712
    # Count can repeat after a delete, so walk until the slug is free.
    i = n + 1
    while db.query(AdminTask).filter(AdminTask.slug == f"mine-{i}").first():
        i += 1
    row = AdminTask(slug=f"mine-{i}", custom=True, title=title[:300],
                    note=(note or "").strip()[:500], section="mine", sort=i)
    db.add(row)
    db.commit()
    return {"id": row.slug, "title": row.title, "note": row.note,
            "owner": "you", "critical": False, "custom": True,
            "done": False, "done_at": None}


def delete_custom(db: Session, slug: str) -> bool:
    """Only the owner's own tasks can be deleted — a seeded task is the plan."""
    row = db.query(AdminTask).filter(AdminTask.slug == slug,
                                     AdminTask.custom == True).first()  # noqa: E712
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True
