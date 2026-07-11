# ============================================================
# services/crop_calendar_service.py
# KrashiMitra — Crop Calendar (मेरी फसल)
# Static agronomy timelines from crop_stages.json + pure
# date math. No FastAPI dependency here.
#
# day-0 semantics: sowing date for direct-seeded crops,
# transplanting date for paddy/onion/tomato (see day0_hi).
# "Today" is computed in IST — the server runs in UTC.
# ============================================================

import json
import os
from datetime import date, datetime, timedelta
from typing import Optional

_json_path = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "data",
    "crop_stages.json"
)
with open(_json_path, "r", encoding="utf-8") as f:
    _raw = json.load(f)

CROP_STAGES = {k: v for k, v in _raw.items() if not k.startswith("_")}

# Show the mandi nudge this many days before expected harvest
NEAR_HARVEST_DAYS = 21


def today_ist() -> date:
    return (datetime.utcnow() + timedelta(hours=5, minutes=30)).date()


def list_crops() -> list:
    """Crop picker metadata — everything except the stage details."""
    out = []
    for key, c in CROP_STAGES.items():
        out.append({
            "key":             key,
            "name_hi":         c["name_hi"],
            "name_en":         c["name_en"],
            "emoji":           c["emoji"],
            "season_hi":       c["season_hi"],
            "duration_days":   c["duration_days"],
            "day0_hi":         c["day0_hi"],
            "sowing_hint_hi":  c["sowing_hint_hi"],
        })
    return out


def _task_state(task_date: date, today: date) -> str:
    """done < (now: ±1 day) < soon (next 7 days) < later"""
    if task_date < today - timedelta(days=1):
        return "done"
    if abs((task_date - today).days) <= 1:
        return "now"
    if task_date <= today + timedelta(days=7):
        return "soon"
    return "later"


def build_timeline(crop_key: str, sowing_date: date) -> Optional[dict]:
    """Full computed calendar for one crop + sowing date.
    Returns None for an unknown crop."""
    crop = CROP_STAGES.get(crop_key)
    if not crop:
        return None

    today = today_ist()
    days = (today - sowing_date).days
    duration = crop["duration_days"]
    harvest_eta = sowing_date + timedelta(days=duration)

    if days < 0:
        status = "upcoming"       # sowing date is in the future
    elif days > duration + 30:
        status = "finished"       # well past harvest window
    else:
        status = "active"

    current_stage = None
    stages_out = []
    week_tasks = []

    for stage in crop["stages"]:
        if days > stage["end_day"]:
            stage_state = "past"
        elif days >= stage["start_day"]:
            stage_state = "current"
        else:
            stage_state = "future"

        tasks_out = []
        for t in stage["tasks"]:
            t_date = sowing_date + timedelta(days=t["day"])
            t_state = _task_state(t_date, today)
            task = {
                "day":       t["day"],
                "date":      t_date.isoformat(),
                "state":     t_state,
                "type":      t["type"],
                "title_hi":  t["title_hi"],
                "detail_hi": t["detail_hi"],
            }
            tasks_out.append(task)
            if t_state in ("now", "soon") and status == "active":
                week_tasks.append({**task, "stage_hi": stage["name_hi"]})

        stage_out = {
            "key":       stage["key"],
            "name_hi":   stage["name_hi"],
            "emoji":     stage["emoji"],
            "start_day": stage["start_day"],
            "end_day":   stage["end_day"],
            "about_hi":  stage["about_hi"],
            "state":     stage_state,
            "tasks":     tasks_out,
        }
        stages_out.append(stage_out)
        if stage_state == "current" and current_stage is None:
            current_stage = {
                "key":     stage["key"],
                "name_hi": stage["name_hi"],
                "emoji":   stage["emoji"],
            }

    # Past the last stage but within the +30-day grace window
    if current_stage is None and status == "active" and days > duration:
        last = crop["stages"][-1]
        current_stage = {"key": last["key"], "name_hi": last["name_hi"], "emoji": last["emoji"]}

    week_tasks.sort(key=lambda t: t["date"])

    return {
        "crop_key":        crop_key,
        "name_hi":         crop["name_hi"],
        "name_en":         crop["name_en"],
        "emoji":           crop["emoji"],
        "season_hi":       crop["season_hi"],
        "day0_hi":         crop["day0_hi"],
        "sowing_date":     sowing_date.isoformat(),
        "duration_days":   duration,
        "day_number":      days,          # negative while upcoming
        "status":          status,
        "progress_pct":    max(0, min(100, round(days * 100 / duration))) if days >= 0 else 0,
        "current_stage":   current_stage,
        "harvest_eta":     harvest_eta.isoformat(),
        "days_to_harvest": max(0, (harvest_eta - today).days),
        "near_harvest":    status == "active" and 0 <= (harvest_eta - today).days <= NEAR_HARVEST_DAYS,
        "week_tasks":      week_tasks,    # tasks due now / next 7 days
        "stages":          stages_out,
    }
