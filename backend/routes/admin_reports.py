# ============================================================
# routes/admin_reports.py
# /admin/bazar-reports — the queue behind कृषि बाज़ार's "रिपोर्ट करें".
#
# IT Rules 2021: acknowledge a complaint within 24 hours, resolve within 15
# days. One row per reported post, open ones first, oldest first — the oldest
# open report is the one closest to breaking that clock. "हटाएँ" removes the
# post through bazar.purge_post (the same path the owner's own delete uses);
# "खारिज" closes the reports and leaves the post up.
# ============================================================
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database.db import BazarPost, BazarReport, User
from backend.routes.admin import admin_db, require_admin
from backend.routes.bazar import REPORT_REASONS, purge_post

router = APIRouter(prefix="/admin/bazar-reports", tags=["admin-reports"])


@router.get("")
def list_reports(db: Session = Depends(admin_db), _: str = Depends(require_admin)):
    rows = db.query(BazarReport).order_by(BazarReport.created_at).all()
    by_post: dict[int, dict] = {}
    for r in rows:
        g = by_post.setdefault(r.post_id, {"post_id": r.post_id, "reports": [],
                                           "open": 0, "first_at": r.created_at})
        g["reports"].append({"reason": REPORT_REASONS.get(r.reason, r.reason),
                             "note": r.note or "", "status": r.status,
                             "at": r.created_at.isoformat()})
        if r.status == "open":
            g["open"] += 1
    posts = {p.id: p for p in db.query(BazarPost).filter(BazarPost.id.in_(list(by_post))).all()} \
        if by_post else {}
    authors = {u.id: u.name for u in db.query(User).filter(
        User.id.in_([p.users_id for p in posts.values()])).all()} if posts else {}
    out = []
    for pid, g in by_post.items():
        p = posts.get(pid)
        age_h = (datetime.utcnow() - g["first_at"]).total_seconds() / 3600
        out.append({
            "post_id": pid, "open": g["open"], "count": len(g["reports"]),
            "age_hours": round(age_h, 1), "reports": g["reports"],
            "exists": p is not None,
            "crop": p.crop if p else "", "text": (p.text or "")[:300] if p else "",
            "media_url": p.media_url if p else "", "location": p.location if p else "",
            "author": authors.get(p.users_id, "") if p else "",
        })
    out.sort(key=lambda g: (g["open"] == 0, -g["age_hours"]))
    return {"success": True, "open": sum(1 for g in out if g["open"]), "posts": out}


@router.post("/{post_id}/resolve")
def resolve(post_id: int, payload: dict, db: Session = Depends(admin_db),
            _: str = Depends(require_admin)):
    action = str((payload or {}).get("action") or "")
    if action not in ("remove", "dismiss"):
        raise HTTPException(400, "action must be remove or dismiss")
    reports = db.query(BazarReport).filter(BazarReport.post_id == post_id,
                                           BazarReport.status == "open").all()
    if not reports:
        raise HTTPException(404, "इस पोस्ट पर कोई खुली शिकायत नहीं")
    if action == "remove":
        post = db.query(BazarPost).filter(BazarPost.id == post_id).first()
        if post:
            purge_post(db, post)
    now = datetime.utcnow()
    for r in reports:
        r.status = "removed" if action == "remove" else "dismissed"
        r.handled_at = now
    db.commit()
    return {"success": True}
