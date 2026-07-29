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
# Pure functions, no FastAPI/DB import. Data lives in data/buyers.json, read
# live and cached by mtime — signing a dealer is a JSON edit, not a deploy.
#
# A listing must EARN its way onto the page: active, named, placed, and
# reachable. Anything less is filtered here rather than in the template, so no
# caller can accidentally render a dead phone number to a farmer.
# ============================================================
import json
import re
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "data" / "buyers.json"

_cache: dict | None = None
_mtime: float = -1.0
_place_idx: dict[tuple[str, str], list] = {}   # (state, district) → [buyer]

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


def _load() -> dict:
    global _cache, _mtime, _place_idx
    try:
        m = _PATH.stat().st_mtime
    except OSError:
        return {"buyers": []}
    if _cache is None or m != _mtime:
        try:
            _cache = json.loads(_PATH.read_text(encoding="utf-8"))
        except Exception:
            _cache = {"buyers": []}
        idx: dict[tuple[str, str], list] = {}
        for b in (_cache.get("buyers") or []):
            if _usable(b):
                idx.setdefault((_norm(b.get("state")), _norm(b.get("district"))), []).append(b)
        _place_idx = idx
        _mtime = m
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
