# ============================================================
# backend/services/app_settings.py
# KrashiMitra — operator-editable settings (app_settings table)
#
# One dotted key per setting, JSON value, defaults in code. Used by the admin
# panel to change behaviour without a deploy.
#
# The read path is deliberately unbreakable: any failure — missing table, DB
# asleep, unparseable JSON — returns the code default rather than raising. A
# settings lookup sits inside the mandi fetch sweep and the /bhav render path,
# and neither may ever fail because an operator preference could not be read.
# ============================================================

import json
import logging
from datetime import datetime

from backend.database.db import AppSetting, SessionLocal

log = logging.getLogger("krishi.settings")

# Every key the panel can write, with the value that ships. A key absent here
# is refused by set() — a typo in the admin UI must not create a dead setting
# that looks saved but is read by nothing.
DEFAULTS = {
    # Master switch for the 🔔 bhav alert system.
    #   sending  — run_mandi_alerts() delivers pushes
    #   bell     — the 🔔 button renders on /bhav pages
    # Split in two on purpose: turning off sending while leaving the bell up
    # would keep collecting subscribers who get nothing, so the panel warns.
    "alerts.sending_enabled": True,
    "alerts.bell_visible":    True,
    # What counts as a move worth interrupting someone for. Both floors must be
    # cleared (see push_service.MIN_MOVE_*).
    "alerts.min_move_rs":     10,
    "alerts.min_move_pct":    1.0,
}


def _coerce(key, value):
    """Keep a stored value the same type as its default.

    The admin panel posts JSON, but a hand-edited row (or an older value written
    before a default changed type) can hold a string where a number belongs.
    Returning the wrong type here would reach arithmetic in push_service, so a
    value that cannot be coerced falls back to the default."""
    default = DEFAULTS[key]
    try:
        if isinstance(default, bool):
            if isinstance(value, str):
                return value.strip().lower() in ("1", "true", "yes", "on")
            return bool(value)
        if isinstance(default, int):
            return int(float(value))
        if isinstance(default, float):
            return float(value)
    except (TypeError, ValueError):
        return default
    return value


def get_all() -> dict:
    """Every setting, defaults filled in. Never raises."""
    out = dict(DEFAULTS)
    db = None
    try:
        db = SessionLocal()
        for row in db.query(AppSetting).all():
            if row.key not in DEFAULTS:
                continue                      # retired key still in the table
            try:
                out[row.key] = _coerce(row.key, json.loads(row.value))
            except (ValueError, TypeError):
                pass                          # unparseable → keep the default
    except Exception as e:
        log.warning("settings read failed, using defaults: %s", e)
    finally:
        if db is not None:
            db.close()
    return out


_CACHE = {"at": 0.0, "values": None}
_TTL_SECONDS = 60


def get_cached(key: str):
    """A setting for a hot render path, memoised for a minute.

    /bhav serves roughly 15,000 URLs and its HTML is edge-cached, so a settings
    lookup per render would add a Neon round trip to a page that otherwise
    needs none — and the compute is already billed around the clock. A minute
    of staleness is the right trade for an operator toggle: the panel's own
    read is uncached, so the switch still reflects reality immediately in the
    place where someone is watching it."""
    import time
    now = time.monotonic()
    if _CACHE["values"] is None or now - _CACHE["at"] > _TTL_SECONDS:
        _CACHE["values"] = get_all()
        _CACHE["at"] = now
    return _CACHE["values"].get(key, DEFAULTS.get(key))


def get(key: str):
    """One setting. Unknown key raises — that is a programming error, not an
    operator one, and silently returning None would hide it."""
    if key not in DEFAULTS:
        raise KeyError(key)
    return get_all()[key]


def set_many(values: dict, who: str = "") -> dict:
    """Write settings. Returns the full resulting set. Unknown keys are ignored."""
    db = SessionLocal()
    try:
        for key, value in values.items():
            if key not in DEFAULTS:
                continue
            value = _coerce(key, value)
            row = db.query(AppSetting).filter(AppSetting.key == key).first()
            if row:
                row.value      = json.dumps(value)
                row.updated_at = datetime.utcnow()
                row.updated_by = (who or "")[:120] or None
            else:
                db.add(AppSetting(key=key, value=json.dumps(value),
                                  updated_by=(who or "")[:120] or None))
        db.commit()
        _CACHE["values"] = None      # this process picks the change up at once
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return get_all()
