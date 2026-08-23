# ============================================================
# services/wa_channels.py
# राज्यवार WhatsApp चैनल — one broadcast channel per state.
# ------------------------------------------------------------
# The /bhav answer panel used to end with "message us and we'll send you this
# mandi's bhav daily". That request lands in one inbox and has to be answered
# by hand, per farmer, every day — a list that cannot grow past the person
# working it. A WhatsApp channel inverts it: the farmer joins in one tap, we
# post once, and everyone in that state gets the number. Nobody replies to a
# channel, which is exactly the point — it is a broadcast, not a conversation.
#
# State-wise rather than national because a Raisen farmer will not read
# Punjab's rates, and one national channel would have to post 36 states' prices
# to serve anybody — the fastest way to be muted.
#
# The invite links live in data/wa_channels.json and are read live, cached by
# mtime: creating a channel is manual work inside WhatsApp, so pasting its link
# must be a file edit and nothing more — no deploy step, no migration, no code
# change. A state whose `url` is still blank simply keeps the old
# message-us card (see routes/bhav._wa_daily); a link we do not have must never
# render as a link that 404s.
#
# Runnable manually:  python -m backend.services.wa_channels
# ============================================================

import json
import re
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "data" / "wa_channels.json"

_cache: dict | None = None
_mtime: float = -1.0

# Agmarknet's own spellings, normalised onto one key each. Same list as
# bhav._state_svg_slug's overrides and for the same reason: the feed sends
# "Keralam" and "Chattisgarh", and a farmer in either spelling gets the same
# channel. Keyed post-slugify, so both "NCT of Delhi" and "nct_of_delhi" land.
_ALIASES = {
    "keralam":     "kerala",
    "uttrakhand":  "uttarakhand",
    "chattisgarh": "chhattisgarh",
    "nct_of_delhi": "delhi",
    "pondicherry": "puducherry",
    "andaman_and_nicobar_islands": "andaman_and_nicobar",
}


def _key(state: str) -> str:
    """'Uttar Pradesh' / 'uttar-pradesh' / 'Keralam' → 'uttar_pradesh' / 'kerala'."""
    s = re.sub(r"[^a-z0-9]+", "_", (state or "").lower()).strip("_")
    return _ALIASES.get(s, s)


def _spec() -> dict:
    global _cache, _mtime
    try:
        m = _PATH.stat().st_mtime
    except OSError:
        return {"channels": {}}
    if _cache is None or m != _mtime:
        try:
            _cache = json.loads(_PATH.read_text(encoding="utf-8"))
            _mtime = m
        except (OSError, ValueError):
            # Keep serving the last good copy — a typo in the JSON should cost
            # you the edit, not every /bhav page in the country.
            if _cache is None:
                return {"channels": {}}
    return _cache or {"channels": {}}


def channel_for(state: str) -> dict | None:
    """{"name", "url"} for a state's channel, or None if there isn't one yet.

    None is the honest answer for the 30-odd states whose channel has not been
    created — the caller falls back to the older card rather than inviting a
    farmer into an empty room."""
    row = _spec().get("channels", {}).get(_key(state))
    if not isinstance(row, dict):
        return None
    url = str(row.get("url") or "").strip()
    if not url.startswith("https://"):
        return None
    return {"name": str(row.get("name") or "").strip() or handle(state), "url": url}


def handle(state: str) -> str:
    """The channel's own name — krashimitra_uttar_pradesh. Only a default: what
    a channel is actually called is whatever the JSON says it is called."""
    k = _key(state)
    return f"krashimitra_{k}" if k else "krashimitra"


def live() -> dict[str, dict]:
    """Every state that has a working link — for a quick 'what's live' count."""
    return {k: c for k in _spec().get("channels", {}) if (c := channel_for(k))}


if __name__ == "__main__":  # pragma: no cover
    all_ = _spec().get("channels", {})
    on = live()
    print(f"{_PATH}: {len(on)}/{len(all_)} states have a channel link")
    for k, c in sorted(on.items()):
        print(f"  {k:28} {c['name']:34} {c['url']}")
    missing = [k for k in sorted(all_) if k not in on]
    if missing:
        print("\nno link yet: " + ", ".join(missing))
