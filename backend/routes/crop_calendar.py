# ============================================================
# backend/routes/crop_calendar.py
# KrashiMitra — Crop Calendar (मेरी फसल) Router
#
# Public (no login — guests keep crops in localStorage and use
# /timeline directly):
#   GET  /crop-calendar/crops      → supported crops for the picker
#   GET  /crop-calendar/timeline   → computed calendar for crop+date
#
# Authenticated (crops saved server-side, also feeds KrashiBook):
#   GET    /crop-calendar/my       → farmer's crops with timelines
#   POST   /crop-calendar/my       → add a crop
#   DELETE /crop-calendar/my/{id}  → remove a crop
# ============================================================

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from backend.database.db import UserCrop, get_db
from backend.utils.auth_utils import get_current_user
from backend.services.crop_calendar_service import CROP_STAGES, build_timeline, list_crops

router = APIRouter(prefix="/crop-calendar", tags=["crop-calendar"])

MAX_CROPS_PER_USER = 6


class CropAddRequest(BaseModel):
    crop_key:    str
    sowing_date: str                     # "YYYY-MM-DD"
    area:        Optional[str] = None
    area_unit:   Optional[str] = "acres"


def _parse_sowing_date(raw: str) -> date:
    try:
        d = date.fromisoformat(str(raw).strip())
    except ValueError:
        raise HTTPException(400, "तारीख का प्रारूप गलत है — YYYY-MM-DD में भेजें।")
    today = date.today()
    # Allow a bit of future (planned sowing) and up to ~14 months back
    if (d - today).days > 60:
        raise HTTPException(400, "बुवाई की तारीख 2 महीने से ज़्यादा आगे की नहीं हो सकती।")
    if (today - d).days > 430:
        raise HTTPException(400, "बुवाई की तारीख बहुत पुरानी है — यह फसल कट चुकी होगी।")
    return d


# ── GET /crop-calendar/crops — picker metadata (public) ──────

@router.get("/crops")
def get_crops():
    return {"success": True, "message": "", "data": {"crops": list_crops()}}


# ── GET /crop-calendar/timeline — computed calendar (public) ─

@router.get("/timeline")
def get_timeline(
    crop:        str = Query(..., description="crop key, e.g. wheat"),
    sowing_date: str = Query(..., description="YYYY-MM-DD"),
):
    d = _parse_sowing_date(sowing_date)
    timeline = build_timeline(crop.strip().lower(), d)
    if timeline is None:
        raise HTTPException(404, "यह फसल अभी कैलेंडर में उपलब्ध नहीं है।")
    return {"success": True, "message": "", "data": timeline}


# ── GET /crop-calendar/my — farmer's saved crops ─────────────

@router.get("/my")
def my_crops(
    current_user: dict    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    rows = (
        db.query(UserCrop)
        .filter(UserCrop.user_id == current_user["user_id"], UserCrop.status == "active")
        .order_by(UserCrop.created_at.asc())
        .all()
    )
    crops = []
    for r in rows:
        timeline = build_timeline(r.crop_key, r.sowing_date)
        if timeline is None:
            continue  # crop removed from crop_stages.json — skip silently
        crops.append({
            "id":        r.id,
            "area":      r.area,
            "area_unit": r.area_unit,
            **timeline,
        })
    return {"success": True, "message": "", "data": {"crops": crops}}


# ── GET /crop-calendar/nudges — "due now / this week" tasks ──
# Flattens every active crop's week_tasks (already computed by
# build_timeline as now/soon) + a near-harvest mandi nudge into one
# sorted list for KrashiBook (and, later, web-push/WhatsApp).
# Parse-on-request: no scheduler, always live off today's date.

@router.get("/nudges")
def crop_nudges(
    current_user: dict    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    rows = (
        db.query(UserCrop)
        .filter(UserCrop.user_id == current_user["user_id"], UserCrop.status == "active")
        .order_by(UserCrop.created_at.asc())
        .all()
    )
    nudges = []
    for r in rows:
        tl = build_timeline(r.crop_key, r.sowing_date)
        if tl is None:
            continue  # crop removed from crop_stages.json — skip silently
        for t in tl["week_tasks"]:            # already state now/soon, active crops only
            nudges.append({
                "crop_key":  tl["crop_key"],
                "crop_hi":   tl["name_hi"],
                "emoji":     tl["emoji"],
                "kind":      "task",
                "urgency":   t["state"],       # "now" | "soon"
                "type":      t["type"],
                "title_hi":  t["title_hi"],
                "detail_hi": t["detail_hi"],
                "day":       t["day"],
                "date":      t["date"],
                "stage_hi":  t.get("stage_hi"),
            })
        if tl["near_harvest"]:                # sell-planning nudge as harvest approaches
            nudges.append({
                "crop_key":  tl["crop_key"],
                "crop_hi":   tl["name_hi"],
                "emoji":     tl["emoji"],
                "kind":      "harvest",
                "urgency":   "soon",
                "type":      "mandi",
                "title_hi":  "कटाई नज़दीक — मंडी भाव देखें",
                "detail_hi": f"{tl['name_hi']} की कटाई लगभग {tl['days_to_harvest']} दिन में। "
                             f"अभी से मंडी भाव देखकर बेचने की योजना बनाएं।",
                "day":       None,
                "date":      tl["harvest_eta"],
                "stage_hi":  None,
            })

    _rank = {"now": 0, "soon": 1}
    nudges.sort(key=lambda n: (_rank.get(n["urgency"], 2), n.get("date") or ""))
    now_count = sum(1 for n in nudges if n["urgency"] == "now")
    return {
        "success": True,
        "message": "",
        "data": {"nudges": nudges, "count": len(nudges), "now_count": now_count},
    }


# ── POST /crop-calendar/my — add a crop ──────────────────────

@router.post("/my")
def add_crop(
    body:         CropAddRequest,
    current_user: dict    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    user_id = current_user["user_id"]
    crop_key = body.crop_key.strip().lower()
    if crop_key not in CROP_STAGES:
        raise HTTPException(404, "यह फसल अभी कैलेंडर में उपलब्ध नहीं है।")

    sowing = _parse_sowing_date(body.sowing_date)

    active = (
        db.query(UserCrop)
        .filter(UserCrop.user_id == user_id, UserCrop.status == "active")
        .all()
    )
    if len(active) >= MAX_CROPS_PER_USER:
        raise HTTPException(400, f"अधिकतम {MAX_CROPS_PER_USER} फसलें ही जोड़ सकते हैं — पहले कोई पुरानी फसल हटाएं।")

    # Same crop + same sowing date already saved → return it, don't duplicate
    for r in active:
        if r.crop_key == crop_key and r.sowing_date == sowing:
            return {
                "success": True,
                "message": "यह फसल पहले से जुड़ी है।",
                "data":    {"id": r.id, **build_timeline(crop_key, sowing)},
            }

    row = UserCrop(
        user_id     = user_id,
        crop_key    = crop_key,
        sowing_date = sowing,
        area        = (body.area or "").strip() or None,
        area_unit   = body.area_unit or "acres",
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return {
        "success": True,
        "message": "फसल कैलेंडर में जुड़ गई। 🌱",
        "data":    {"id": row.id, **build_timeline(crop_key, sowing)},
    }


# ── DELETE /crop-calendar/my/{crop_id} — remove ──────────────

@router.delete("/my/{crop_id}")
def delete_crop(
    crop_id:      int,
    current_user: dict    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    row = (
        db.query(UserCrop)
        .filter(UserCrop.id == crop_id, UserCrop.user_id == current_user["user_id"])
        .first()
    )
    if not row:
        raise HTTPException(404, "फसल नहीं मिली।")
    row.status = "done"
    row.updated_at = datetime.utcnow()
    db.commit()
    return {"success": True, "message": "फसल हटा दी गई।", "data": {}}
