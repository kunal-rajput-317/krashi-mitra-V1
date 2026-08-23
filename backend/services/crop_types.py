# ============================================================
# services/crop_types.py
# Crop-type lookup — "how often is this crop's sale re-decided?"
#
# A wheat grower sells once a marketing season against MSP; a tomato grower
# re-decides every morning against that day's आवक. Those are different pages,
# not the same page with different numbers, and until now /bhav rendered both
# identically. This module is the single place that says which crop is which,
# so the layout switch, the admin view and any future WhatsApp cadence all read
# one answer instead of each growing their own list.
#
# WHY A REGISTRY AND NOT A URL SEGMENT: the type is a property of the crop, not
# of the address. 5,624 /bhav URLs already rank; encoding the type in the path
# would cost that many redirects to express something no farmer types and no
# crawler needs. The slug stays the key.
#
# Rates live in data/crop_types.json, read live and cached by mtime — a new
# Agmarknet commodity must be classifiable by editing JSON, never by a deploy
# ("everything automatic").
#
# THE ONE GUARANTEE: crop_type() never raises and never returns an unknown
# type. A missing file, a corrupt file, a typo'd type name or a commodity
# nobody has classified all resolve to the default — which is "staple", today's
# layout. An unclassified crop must render exactly as it does now; being wrong
# about the cadence is a worse failure than being silent about it.
#
# Pure functions, no FastAPI/DB import — same contract as services/msp.py.
# ============================================================
import json
import re
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "data" / "crop_types.json"

_FALLBACK = "staple"

_cache: dict | None = None
_mtime: float = -1.0


def _norm(slug: str) -> str:
    """URL slug → lookup key. Slugs arrive lowercase-hyphenated from the path,
    but /bhav also resolves crop names from the feed, so accept spaces and
    stray case rather than silently missing a match."""
    s = (slug or "").strip().lower()
    s = re.sub(r"[\s_]+", "-", s)
    return re.sub(r"-{2,}", "-", s).strip("-")


def _load() -> dict:
    global _cache, _mtime
    try:
        m = _PATH.stat().st_mtime
    except OSError:
        return {}
    if _cache is None or m != _mtime:
        try:
            _cache = json.loads(_PATH.read_text(encoding="utf-8"))
        except Exception:
            _cache = {}
        _mtime = m
    return _cache or {}


def _default() -> str:
    """The configured default, but only if it is a type that actually exists —
    a typo in the JSON must not poison every lookup on the site."""
    d = _load()
    want = d.get("default") or _FALLBACK
    return want if want in (d.get("types") or {}) else _FALLBACK


def _resolve(slug: str) -> tuple[str, str, str]:
    """(type, source, evidence) — the single resolution path, so the answer and
    the account of how it was reached can never disagree.

    `source` is one of "explicit" | "rule" | "default". It is tracked here
    rather than re-derived by comparing against the default, because a keyword
    rule that resolves TO the default type is still a rule match: inferring the
    source after the fact reports those as unclassified and hides the rule.

    Resolution order, first hit wins:
      1. crops{} exact slug        — the curated answer
      2. rules[] keyword match     — the long tail, in listed order
      3. default                   — today's layout
    """
    d = _load()
    types = d.get("types") or {}
    if not types:
        return _FALLBACK, "default", "no registry loaded"
    key = _norm(slug)
    if not key:
        return _default(), "default", "empty slug"

    explicit = (d.get("crops") or {}).get(key)
    if explicit in types:
        return explicit, "explicit", key

    for rule in (d.get("rules") or []):
        t = rule.get("type")
        if t not in types:
            continue
        for frag in (rule.get("match") or []):
            if frag and frag in key:
                return t, "rule", frag
    return _default(), "default", ""


def crop_type(slug: str) -> str:
    """Type key for a /bhav crop slug. Always one of the keys in types{}."""
    return _resolve(slug)[0]


def type_meta(t: str) -> dict:
    """Display + layout metadata for a type key. Returns the default type's
    metadata for anything unrecognised, so callers can render unconditionally."""
    d = _load()
    types = d.get("types") or {}
    meta = types.get(t) or types.get(_default()) or {}
    return {
        "key": t if t in types else _default(),
        "hi": meta.get("hi", ""),
        "layout": meta.get("layout", "season"),
        "cadence_days": meta.get("cadence_days", 90),
        "why": meta.get("why", ""),
    }


def layout_for(slug: str) -> str:
    """The layout key a crop's /bhav page should render with. One call for the
    common case, so route code never has to chain crop_type + type_meta."""
    return type_meta(crop_type(slug))["layout"]


def is_explicit(slug: str) -> bool:
    """True when the crop is curated in crops{} rather than caught by a keyword
    rule or the default. Admin shows this — a rule match is a guess worth
    eyeballing, an explicit entry is a decision someone made."""
    return _resolve(slug)[1] == "explicit"


def all_types() -> dict:
    """Every declared type, key → metadata. For the admin panel and tests."""
    return {k: type_meta(k) for k in (_load().get("types") or {})}


def classify(slugs) -> list[dict]:
    """Classify many slugs at once — what the admin view renders. Each row
    carries how the answer was reached, and on a rule match which keyword did
    it, so a rule quietly mis-typing a crop is visible rather than buried."""
    out = []
    for s in slugs:
        t, source, evidence = _resolve(s)
        meta = type_meta(t)
        out.append({
            "slug": s,
            "type": t,
            "hi": meta["hi"],
            "layout": meta["layout"],
            "source": source,
            "matched": evidence if source == "rule" else "",
        })
    return out
