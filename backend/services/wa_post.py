# ============================================================
# services/wa_post.py
# आज की पोस्ट — the daily bhav message for each state's WhatsApp channel.
# ------------------------------------------------------------
# WhatsApp has no API for posting to a channel, so the send stays manual: the
# owner opens the channel and pastes. What does NOT have to be manual is the
# writing — 31 states × one post a day is the workload that kills this in week
# two, and a post assembled by hand at 8am is also the post that gets skipped
# on a busy morning.
#
# This builds each state's post from the same mandi_prices snapshot the /bhav
# pages read, so the number in the channel and the number on the page can never
# disagree. Nothing here writes, schedules or sends anything — it returns text.
#
# Shape of the post (deliberate, and worth keeping stable — a follower learns
# to recognise it):
#   • the numbers are IN the post, not behind the link. A post that withholds
#     the price to force a click is the kind farmers mute.
#   • one deep link, to /bhav/rajya/<state> — the crop-less state hub, which is
#     the page that asks "which district?" instead of assuming a crop.
#   • utm_source=wa so GA4 can separate channel traffic from SEO traffic. That
#     is the only way to answer "is the channel working": in-app WhatsApp
#     clicks arrive with no referrer and would otherwise count as direct.
#
# Cached for a few minutes: the admin page renders all 31 states at once, and
# the snapshot behind it only changes when the fetch cron runs.
#
# Runnable manually:  python -m backend.services.wa_post "Uttar Pradesh"
# ============================================================

import re
import time
from datetime import date

from backend.database.db import SessionLocal, MandiPrice
from backend.services import wa_channels

SITE = "https://krashimitra.in"
_TTL = 300.0                      # seconds; the fetch cron runs ~6×/day
_LINK_Q = "?utm_source=wa&utm_medium=channel&utm_campaign=daily_bhav"

# How many crops a post carries. Five fits a phone screen without scrolling and
# is about as much as anyone reads standing in a field; more just buries the
# top line. A crop needs a few mandis behind it before its "state average" is
# an average at all rather than one trader's quote.
_CROPS_PER_POST = 5
_MIN_MANDIS = 3

# What a farmer brings to the mandi — not what a mill sends back out.
# Agmarknet lists Rice, Wheat Atta, Maida, the split dals and refined oils
# alongside the crops, and by tile order they outrank the grain they are made
# from: Uttar Pradesh's first draft post read गेहूं, चावल, धान, टुकड़ा चावल, प्याज —
# two of five lines were mill output, and the farmer reading it sells neither.
# Whole-word matching, so "Cinamon(Dalchini)" is not a dal and "Paddy(Dhan)"
# is not rice. Oils are named one by one on purpose: Mentha Oil IS the thing a
# Barabanki farmer sells, distilled on his own field.
_MILLED_RE = re.compile(r"\b(rice|atta|maida|suji|besan|dal|sugar|bran)\b", re.I)
_MILLED_NAMES = {"mustard oil", "coconut oil", "sunflower oil", "groundnut oil",
                 "sesame oil", "castor oil", "rice bran oil"}


def _farm_gate(commodity: str) -> bool:
    c = (commodity or "").strip().lower()
    return not (_MILLED_RE.search(c) or c in _MILLED_NAMES)


_cache: dict = {}
_cache_ts: float = 0.0


def _num(v):
    try:
        n = float(str(v).replace(",", ""))
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


def _snapshot() -> dict:
    """{state: {commodity: {modals, prev_pairs, mandis}}} for the whole country.

    One query for every state rather than one per state: the admin page asks
    for all 31 at once, and 31 round trips to Neon for what is a single index
    scan is the difference between a page that opens and a page that times out
    on the free tier."""
    db = SessionLocal()
    try:
        rows = db.query(MandiPrice.state, MandiPrice.commodity, MandiPrice.market,
                        MandiPrice.modal_price, MandiPrice.prev_modal_price).all()
    finally:
        db.close()

    out: dict = {}
    for state, commodity, market, modal, prev in rows:
        m = _num(modal)
        if not (state and commodity and m):
            continue
        slot = out.setdefault(state, {}).setdefault(
            commodity, {"modals": [], "prev_pairs": [], "mandis": set()})
        slot["modals"].append(m)
        slot["mandis"].add(market or "")
        p = _num(prev)
        if p:
            slot["prev_pairs"].append((m, p))
    return out


def _crop_lines(state_rows: dict) -> list:
    """The crops this state's post will name, most-important first.

    Ordered by _tile_rank — the same curated staple order the mandi grid and
    the /bhav hub use — so a state's post opens on गेहूं/धान rather than on
    whatever sorts first alphabetically. Ties break on how many mandis
    reported, because that is how confident the number is."""
    from backend.routes import bhav          # lazy: bhav is a heavy module

    picks = []
    for commodity, agg in state_rows.items():
        if not (bhav._is_crop(commodity) and _farm_gate(commodity)):
            continue
        mandis = len([m for m in agg["mandis"] if m]) or len(agg["modals"])
        if mandis < _MIN_MANDIS:
            continue
        modals = agg["modals"]
        avg = round(sum(modals) / len(modals))

        # Day-on-day move, paired: only rows carrying BOTH today's modal and
        # their own previous one. Comparing today's full average against a
        # previous average built from a different (smaller) set of mandis
        # invents moves that never happened.
        pct = None
        if agg["prev_pairs"]:
            now = sum(a for a, _ in agg["prev_pairs"])
            was = sum(b for _, b in agg["prev_pairs"])
            if was:
                pct = round((now - was) / was * 100, 1)

        picks.append({"commodity": commodity,
                      "hi": bhav._hindi_name(commodity),
                      "avg": avg, "pct": pct, "mandis": mandis,
                      "rank": bhav._tile_rank(commodity)})

    picks.sort(key=lambda p: (p["rank"], -p["mandis"]))
    # One line per Hindi name: Agmarknet ships several commodities that render
    # to the same word (three pumpkins are all कद्दू), and a post listing कद्दू
    # three times at three prices reads like a mistake.
    seen, out = set(), []
    for p in picks:
        if p["hi"] in seen:
            continue
        seen.add(p["hi"])
        out.append(p)
        if len(out) >= _CROPS_PER_POST:
            break
    return out


def _move(pct) -> str:
    """The arrow already says which way — a '-' after a ▼ is the same word twice."""
    if pct is None or pct == 0:
        return "— कल जैसा"
    return f"{'▲' if pct > 0 else '▼'} {abs(pct):g}%"


def _text(hi_state: str, s_slug: str, lines: list, mandis: int) -> str:
    """The post itself. WhatsApp bolds *between asterisks*."""
    from backend.routes import bhav

    body = "\n".join(f"{l['hi']} — ₹{l['avg']:,} {_move(l['pct'])}" for l in lines)
    return (f"🌾 *{hi_state} मंडी भाव — {bhav._hindi_date(date.today())}*\n\n"
            f"{body}\n\n"
            f"औसत मॉडल भाव ₹/क्विंटल · {mandis} मंडियों की सरकारी रिपोर्ट\n"
            f"स्रोत: Agmarknet (data.gov.in)\n\n"
            f"अपने जिले का पूरा भाव 👇\n"
            f"{SITE}/bhav/rajya/{s_slug}{_LINK_Q}")


def posts(refresh: bool = False) -> list:
    """One entry per state that has a channel, ready to paste.

    States with no channel are skipped rather than listed empty: the point of
    this page is the morning routine, and a row you cannot act on is noise in
    it."""
    global _cache, _cache_ts
    from backend.routes import bhav

    if not refresh and _cache and (time.time() - _cache_ts) < _TTL:
        return _cache.get("posts", [])

    snap = _snapshot()
    out = []
    for state, state_rows in snap.items():
        chan = wa_channels.channel_for(state)
        if not chan:
            continue
        lines = _crop_lines(state_rows)
        if not lines:
            continue
        hi_state = bhav._hindi_state(state)
        s_slug = bhav._slugify(state)
        mandis = len({m for agg in state_rows.values() for m in agg["mandis"] if m})
        out.append({
            "state":    state,
            "hi_state": hi_state,
            "slug":     s_slug,
            "channel":  chan["name"],
            "url":      chan["url"],
            "crops":    lines,
            "mandis":   mandis,
            "text":     _text(hi_state, s_slug, lines, mandis),
        })

    # Biggest first — that is the order they should be posted in on a morning
    # where there is not time for all 31.
    out.sort(key=lambda p: -p["mandis"])
    _cache, _cache_ts = {"posts": out}, time.time()
    return out


def coverage(refresh: bool = False) -> dict:
    """Posts, plus the channels that get nothing today.

    Eight of the 31 channels had no crop with enough mandis reporting on the
    first run of this — mostly the north-east, where a handful of markets
    report irregularly. Dropping them silently would leave the owner wondering
    why his list is short and whether the page is broken; naming them says the
    quiet part out loud: those channels have nothing honest to post today."""
    from backend.routes import bhav

    rows = posts(refresh)
    have = {wa_channels._key(r["state"]) for r in rows}
    quiet = []
    for key, chan in wa_channels.live().items():
        if key in have:
            continue
        raw = (wa_channels._spec().get("channels", {}).get(key) or {}).get("state") or key
        quiet.append({"state": raw, "hi_state": bhav._hindi_state(raw), "channel": chan["name"]})
    quiet.sort(key=lambda q: q["hi_state"])
    return {"posts": rows, "quiet": quiet}

def post_for(state: str, refresh: bool = False):
    key = wa_channels._key(state)
    return next((p for p in posts(refresh) if wa_channels._key(p["state"]) == key), None)


if __name__ == "__main__":  # pragma: no cover
    import sys
    if len(sys.argv) > 1:
        p = post_for(" ".join(sys.argv[1:]))
        print(p["text"] if p else "no post for that state (no channel, or no prices)")
    else:
        for p in posts():
            print(f"-- {p['hi_state']} ({p['channel']}) · {p['mandis']} mandis")
            print(p["text"], "\n")
