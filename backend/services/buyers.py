# ============================================================
# services/buyers.py
# The verified खरीदार / डीलर directory behind /bhav/.../kharidar.
#
# Every /bhav page ends a farmer's journey at a number. The next question —
# "अब बेचूं किसे?" — is the one with money in it: it is transactional intent
# sitting on top of traffic we already have, and it is what a local trader or
# input dealer will actually pay to appear in (listing fee, per-lead, or the
# featured slot). This module is only the supply side of that: load a
# hand-seeded list, index it by place, hand it back.
#
# TWO SOURCES, ONE INDEX. data/buyers.json is the committed seed, read live and
# cached by mtime. The `buyers` table is everything added since — from the admin
# panel or the public अपनी दुकान form — and it exists because Render's free plan
# has no persistent disk, so a dealer written back into the JSON at runtime
# would vanish on the next restart (see database/db.py::Buyer). A DB row whose
# slug matches a JSON id overrides it, so a seeded listing can be fixed from the
# panel without a deploy.
#
# The DB read is TTL-cached and fails soft: a kharidar page must render, and the
# sitemap must stay honest, even while Neon is asleep or read-only. Falling back
# to the JSON seed shows fewer dealers; falling over shows a farmer a 500.
#
# A listing must EARN its way onto the page: active, named, placed, and
# reachable. Anything less is filtered here rather than in the template, so no
# caller can accidentally render a dead phone number to a farmer — and a public
# signup, which arrives active=False, is invisible until someone calls it.
# ============================================================
import json
import logging
import re
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_PATH = Path(__file__).resolve().parents[1] / "data" / "buyers.json"

_cache: dict | None = None
_mtime: float = -1.0
_place_idx: dict[tuple[str, str], list] = {}   # (state, district) → [buyer]

# Short enough that a dealer added in a mandi appears while you are still
# standing there; long enough that a crawl of 1,300 /bhav pages is not 1,300
# queries. Admin writes call invalidate() anyway, so this is only the ceiling
# on how stale a *missed* invalidation can get.
_DB_TTL = 60.0
_db_rows_cache: list | None = None
_db_at: float = -1.0
# Identity of the row list the current _place_idx was built from. _db_rows()
# hands back the same object until it actually refetches, so an `is not` check
# rebuilds the index exactly when the data changed — no clock, no version
# counter to keep in sync. Boxed in a list so _load() can assign without a
# `global` for it.
_last_db_rows: list = [None]

_KIND_HI = {
    "trader":    ("व्यापारी", "🧾"),
    "dealer":    ("खाद-बीज डीलर", "🏪"),
    "fpo":       ("किसान उत्पादक संगठन (FPO)", "🤝"),
    "processor": ("प्रोसेसर / मिल", "🏭"),
}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _usable(b: dict) -> bool:
    """A listing a farmer can actually act on. The phone check is the point:
    an unreachable number is worse than an empty page."""
    return bool(b.get("active")
                and (b.get("name") or "").strip()
                and (b.get("district") or "").strip()
                and ((b.get("phone") or "").strip() or (b.get("whatsapp") or "").strip()))


def as_dict(row) -> dict:
    """A `Buyer` row in the JSON row's shape, so nothing downstream has to know
    which source a listing came from."""
    return {
        "id":          row.slug,
        "active":      bool(row.active),
        "verified":    bool(row.verified),
        "featured":    bool(row.featured),
        "name":        row.name or "",
        "kind":        row.kind or "trader",
        "state":       row.state or "",
        "district":    row.district or "",
        "market":      row.market or "",
        "commodities": [c for c in (row.commodities or "").split(",") if c.strip()],
        "phone":       row.phone or "",
        "whatsapp":    row.whatsapp or "",
        "note":        row.note or "",
        "since":       row.since or "",
    }


def _db_rows() -> list:
    """Live listings from the `buyers` table, TTL-cached.

    Swallows every error on purpose. This runs inside page renders and the
    sitemap; if Neon is asleep, cold-starting, or read-only, the correct
    outcome is the JSON seed and a warning line — not a 500 on the SEO surface.
    """
    global _db_rows_cache, _db_at
    now = time.time()
    if _db_rows_cache is not None and now - _db_at < _DB_TTL:
        return _db_rows_cache
    rows = []
    try:
        from backend.database.db import Buyer, SessionLocal
        db = SessionLocal()
        try:
            rows = [as_dict(r) for r in db.query(Buyer).filter(Buyer.active.is_(True)).all()]
        finally:
            db.close()
    except Exception as e:
        logger.warning("buyer table read failed, using JSON seed only: %s", e)
        rows = _db_rows_cache or []
    _db_rows_cache, _db_at = rows, now
    return rows


def invalidate() -> None:
    """Drop the DB cache so an admin edit shows on the next page load.

    The panel's whole reason to exist is adding a dealer while sitting in front
    of him; waiting out a TTL to confirm it worked would defeat that."""
    global _db_rows_cache, _db_at
    _db_rows_cache, _db_at = None, -1.0


def _load() -> dict:
    global _cache, _mtime, _place_idx
    try:
        m = _PATH.stat().st_mtime
    except OSError:
        m = -1.0                       # no seed file is fine; the table may still have rows
    db_rows = _db_rows()
    if _cache is None or m != _mtime or db_rows is not _last_db_rows[0]:
        if _cache is None or m != _mtime:
            try:
                _cache = json.loads(_PATH.read_text(encoding="utf-8"))
            except Exception:
                _cache = {"buyers": []}
            _mtime = m
        # DB last so a row overrides the seed entry it shares a slug with —
        # that is what makes a committed listing correctable from the panel.
        merged: dict[str, dict] = {}
        for b in list(_cache.get("buyers") or []) + db_rows:
            key = b.get("id") or f"anon-{len(merged)}"
            merged[key] = b
        idx: dict[tuple[str, str], list] = {}
        for b in merged.values():
            if _usable(b):
                idx.setdefault((_norm(b.get("state")), _norm(b.get("district"))), []).append(b)
        _place_idx = idx
        _last_db_rows[0] = db_rows
    return _cache


def kind_label(kind: str) -> tuple[str, str]:
    """(Hindi label, emoji) for a listing type; unknown kinds read as व्यापारी."""
    return _KIND_HI.get((kind or "").lower(), _KIND_HI["trader"])


def phone_of(b: dict) -> str:
    return (b.get("phone") or b.get("whatsapp") or "").strip()


def wa_of(b: dict) -> str:
    return (b.get("whatsapp") or b.get("phone") or "").strip()


def for_place(c_slug: str, state: str, district: str) -> list:
    """Live listings for one district that buy this crop, featured first.

    An empty `commodities` means "buys everything" — the common case for an
    आढ़तिया — so it matches every crop rather than none.
    """
    _load()
    rows = _place_idx.get((_norm(state), _norm(district)), [])
    cs = _norm(c_slug)
    out = [b for b in rows
           if not b.get("commodities") or cs in {_norm(x) for x in b["commodities"]}]
    # Featured is the paid slot, so it sorts first; verified next (it is the
    # thing we ask a farmer to trust); then stable by name.
    out.sort(key=lambda b: (not b.get("featured"), not b.get("verified"),
                            _norm(b.get("name"))))
    return out


def has_any(c_slug: str, state: str, district: str) -> bool:
    """Cheap gate for callers that must not link to an empty directory page."""
    return bool(for_place(c_slug, state, district))


def by_id(buyer_id: str) -> dict | None:
    _load()
    for rows in _place_idx.values():
        for b in rows:
            if b.get("id") == buyer_id:
                return b
    return None


def live_places() -> set[tuple[str, str]]:
    """{(normalised state, normalised district)} that have at least one live
    listing — lets the sitemap add only directory pages with real content."""
    _load()
    return set(_place_idx.keys())
