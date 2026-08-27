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
# Two things every reader of this file should know:
#
# 1. THIN STATES GET A POST TOO. The >=3-mandi bar below is what makes a "state
#    average" an average, but four channels were silenced by it for a reason
#    that has nothing to do with bad data: their state only HAS one or two
#    reporting markets. Delhi is the clearest case — Azadpur is one of the
#    largest mandis in the country and it was posting nothing, because it is
#    one market. So when nothing clears the bar, the post is rebuilt at one
#    mandi and marked thin; the footer then names that mandi instead of
#    claiming a state average, and the confidence score below drops on its own.
#
# 2. THE SCORE DOES NOT CHANGE THE NUMBERS. mandi_prices keeps a market's last
#    known price until it reports again (~7 days), so roughly a third of the
#    rows behind any average are older than today. /bhav shows those same rows.
#    Filtering them here would make the channel and the page disagree, which is
#    the one thing this module exists to prevent — so the average is left alone
#    and the staleness is *reported* instead, as points off a 100-point score
#    the owner sees before pasting. One wrong number in a channel costs more
#    trust than a whole week of right ones buys.
#
# Cached for a few minutes: the admin page renders all 31 states at once, and
# the snapshot behind it only changes when the fetch cron runs.
#
# Runnable manually:  python -m backend.services.wa_post "Uttar Pradesh"
# ============================================================

import math
import re
import statistics
import time
from datetime import date, datetime

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

# The fallback bar, used only when a state clears nothing at _MIN_MANDIS. One
# mandi's price is still a real, checkable, useful number — it just is not an
# average, and a post built at this bar stops calling it one.
_THIN_MIN_MANDIS = 1

# A row counts as today's if its arrival_date is today or yesterday: Agmarknet
# publishes a day behind for much of the country, so demanding today would mark
# almost every state stale and the signal would stop meaning anything.
_FRESH_DAYS = 1

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

# Nor is Agmarknet's list only crops. The post is headed 🌾 and priced in
# ₹/क्विंटल, and a cow is not sold by the quintal. Mizoram's only two reporting
# rows are Cow and Pigs: at the thin bar it built a मंडी भाव post out of
# livestock at a per-quintal rate that means nothing — caught by the confidence
# score at 30/100, then fixed here, which is the better place. Exact names on
# purpose, so Cowpea(Lobia) stays the pulse it is.
_LIVESTOCK = {"cow", "calf", "ox", "he buffalo", "she buffalo", "goat", "sheep",
              "pigs", "cock", "hen", "egg", "fish"}


def _farm_gate(commodity: str) -> bool:
    c = (commodity or "").strip().lower()
    return not (_MILLED_RE.search(c) or c in _MILLED_NAMES or c in _LIVESTOCK)


_cache: dict = {}
_cache_ts: float = 0.0


def _num(v):
    try:
        n = float(str(v).replace(",", ""))
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


def _age_days(raw, today: date):
    """How old a row's arrival_date is, in days. None when it carries no usable
    date — which is itself worth knowing, so the caller counts those separately
    rather than assuming they are fresh."""
    if not raw:
        return None
    s = str(raw).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return max(0, (today - datetime.strptime(s, fmt).date()).days)
        except ValueError:
            continue
    return None


def _snapshot() -> dict:
    """{state: {commodity: {modals, prev_pairs, mandis, ages}}} for the whole country.

    One query for every state rather than one per state: the admin page asks
    for all 31 at once, and 31 round trips to Neon for what is a single index
    scan is the difference between a page that opens and a page that times out
    on the free tier.

    `ages` carries each row's arrival_date in days-old form. It never touches
    an average — it is the raw material for the freshness part of the
    confidence score, and nothing else reads it."""
    db = SessionLocal()
    try:
        rows = db.query(MandiPrice.state, MandiPrice.commodity, MandiPrice.market,
                        MandiPrice.modal_price, MandiPrice.prev_modal_price,
                        MandiPrice.arrival_date).all()
    finally:
        db.close()

    today = date.today()
    out: dict = {}
    for state, commodity, market, modal, prev, arrival in rows:
        m = _num(modal)
        if not (state and commodity and m):
            continue
        slot = out.setdefault(state, {}).setdefault(
            commodity, {"modals": [], "prev_pairs": [], "mandis": set(), "ages": []})
        slot["modals"].append(m)
        slot["mandis"].add(market or "")
        slot["ages"].append(_age_days(arrival, today))
        p = _num(prev)
        if p:
            slot["prev_pairs"].append((m, p))
    return out


# ── भरोसा स्कोर — how sure are we that this line is right? ────
# 100 points, split across the four ways a printed price goes wrong. Each
# weight answers "how badly would a follower be misled if this went bad?",
# which is why freshness is the largest share: a stale price is a confidently
# wrong number, while a thin one is merely a weak one — and a channel survives
# weak numbers. It does not survive wrong ones.
_W_FRESH, _W_BREADTH, _W_AGREE, _W_MOVE = 40, 25, 20, 15

# Above this spread the "average" is describing two different markets rather
# than one price — Madhya Pradesh onion runs ₹700 to ₹5,000 on the same day.
_CV_FLAG, _CV_ZERO = 0.35, 0.55

# A day-on-day move this big is almost never a move. It is a different variety
# arriving under the same commodity name, or a quintal/kg slip in one feed.
_MOVE_ODD, _MOVE_ABSURD = 15.0, 40.0


def _score_line(l: dict) -> tuple:
    """(score out of 100, [(kind, Hindi reason)]) for one crop line.

    The kind travels with the reason so that _flags() can roll five identical
    complaints up into one — a card that says "सिर्फ़ 1 मंडी से" five times is
    read as decoration, and the sixth thing it says gets skipped with it."""
    name = l["hi"]
    flags = []

    # 1. ताज़गी — today's price, or a market's last known price kept warm?
    if not l["dated"]:
        fresh = _W_FRESH * 0.5
        flags.append(("undated", f"{name} के भाव पर तारीख़ ही नहीं है"))
    else:
        fresh = _W_FRESH * l["fresh_share"]
        if l["age"] is not None and l["age"] >= 2:
            flags.append(("stale", f"{name} का भाव {l['age']} दिन पुराना है"))
        elif l["fresh_share"] < 0.5:
            flags.append(("half_stale", f"{name} के आधे से ज़्यादा भाव कल से भी पुराने हैं"))

    # 2. कितनी मंडियां — log, not linear: the 3rd mandi adds far more
    #    confidence than the 30th, and the curve should say so.
    n = l["mandis"]
    breadth = _W_BREADTH * min(1.0, math.log(1 + n) / math.log(11))
    if n < _MIN_MANDIS:
        flags.append(("thin", f"{name} सिर्फ़ {n} मंडी से — यह औसत नहीं, एक भाव है"))

    # 3. सहमति — do the mandis agree? One mandi has nothing to be checked
    #    against, which is not the same thing as agreement: partial credit.
    if n < 2:
        agree = _W_AGREE * 0.4
    else:
        agree = _W_AGREE * max(0.0, min(1.0, (_CV_ZERO - l["cv"]) / (_CV_ZERO - 0.10)))
        if l["cv"] > _CV_FLAG:
            flags.append(("spread",
                          f"{name} के भाव ₹{l['p_lo']:,} से ₹{l['p_hi']:,} तक अलग-अलग हैं"))

    # 4. कल से मिलान — the arrow is a claim of its own, and "कल जैसा" is the
    #    loudest one of all: it tells a farmer that nothing moved.
    if not l["paired_share"]:
        move = _W_MOVE * 0.2
        flags.append(("nopair", f"{name} का कल का भाव नहीं मिला — 'कल जैसा' जाँची हुई बात नहीं है"))
    else:
        swing = abs(l["pct"] or 0)
        sane = 1.0 if swing <= _MOVE_ODD else (0.4 if swing <= _MOVE_ABSURD else 0.0)
        move = _W_MOVE * (0.65 * l["paired_share"] + 0.35 * sane)
        if swing > _MOVE_ABSURD:
            flags.append(("absurd",
                          f"{name} एक दिन में {swing:g}% बदला — रिपोर्ट की गलती हो सकती है"))

    return int(round(fresh + breadth + agree + move)), flags


def _score_post(lines: list) -> int:
    """The post's score — mostly the average of its lines, pulled toward the
    worst one. A follower does not average five lines; he remembers the one
    that was wrong. So four good lines and one bad line is not a good post."""
    if not lines:
        return 0
    scores = [l["score"] for l in lines]
    return int(round(0.65 * (sum(scores) / len(scores)) + 0.35 * min(scores)))


def band(score: int) -> dict:
    """What the number means, in one word, to the person deciding whether to paste."""
    if score >= 85:
        return {"key": "good", "hi": "भरोसेमंद"}
    if score >= 70:
        return {"key": "ok", "hi": "ठीक है"}
    if score >= 50:
        return {"key": "check", "hi": "जाँच लें"}
    return {"key": "risky", "hi": "बिना जाँचे मत भेजें"}


# A complaint raised by this many of a post's five lines stops being about one
# crop and starts being about the state — Goa's card listed "सिर्फ़ 1 मंडी से"
# five times, which is one fact printed five ways.
_ROLLUP_AT = 3

# How a repeated complaint reads once. Given the lines that raised it.
_ROLLUP = {
    "thin": lambda ls: (f"इस राज्य में सिर्फ़ {max(l['mandis'] for l in ls)} मंडी रिपोर्ट कर रही है — "
                        f"ये {len(ls)} भाव औसत नहीं, एक-एक मंडी के भाव हैं"),
    "stale": lambda ls: (f"{len(ls)} फसलों के भाव पुराने हैं — "
                         f"{max(l['age'] or 0 for l in ls)} दिन तक पुराने"),
    "half_stale": lambda ls: f"{len(ls)} फसलों के आधे से ज़्यादा भाव कल से भी पुराने हैं",
    "nopair": lambda ls: (f"{len(ls)} फसलों का कल का भाव नहीं मिला — "
                          f"उनका 'कल जैसा' जाँची हुई बात नहीं है"),
    "undated": lambda ls: f"{len(ls)} फसलों के भाव पर तारीख़ ही नहीं है",
}


def _flags(lines: list) -> list:
    """The post's complaints, worst line first, deduped and rolled up.

    "spread" and "absurd" are never rolled up: each one names a specific price
    range to go and look at on /bhav, which is the whole use of the line."""
    by_kind = {}
    for l in lines:
        for kind, _ in l.get("flag_kinds", []):
            by_kind.setdefault(kind, []).append(l)

    out, seen, rolled = [], set(), set()
    for l in sorted(lines, key=lambda x: x["score"]):
        for kind, text in l.get("flag_kinds", []):
            group = by_kind.get(kind, [])
            if kind in _ROLLUP and len(group) >= _ROLLUP_AT:
                if kind in rolled:
                    continue
                rolled.add(kind)
                text = _ROLLUP[kind](group)
            if text not in seen:
                seen.add(text)
                out.append(text)
    return out


def _crop_lines(state_rows: dict, min_mandis: int = _MIN_MANDIS) -> list:
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
        if mandis < min_mandis:
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

        # Everything from here down exists only to be scored. None of it can
        # move a printed price — see note 2 in the file header.
        ages = [a for a in agg.get("ages", []) if a is not None]
        mean = sum(modals) / len(modals)
        line = {
            "commodity": commodity,
            "hi": bhav._hindi_name(commodity),
            "avg": avg, "pct": pct, "mandis": mandis,
            "rank": bhav._tile_rank(commodity),
            "dated": len(ages),
            "age": int(statistics.median(ages)) if ages else None,
            "fresh_share": (sum(1 for a in ages if a <= _FRESH_DAYS) / len(ages)) if ages else 0.0,
            "cv": (statistics.pstdev(modals) / mean) if (len(modals) > 1 and mean) else 0.0,
            "p_lo": round(min(modals)), "p_hi": round(max(modals)),
            "paired_share": len(agg["prev_pairs"]) / len(modals) if modals else 0.0,
        }
        line["score"], line["flag_kinds"] = _score_line(line)
        line["flags"] = [t for _, t in line["flag_kinds"]]
        picks.append(line)

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


def _text(hi_state: str, s_slug: str, lines: list, mandis: int, market: str = "") -> str:
    """The post itself. WhatsApp bolds *between asterisks*.

    A one-market state names its market and drops the word औसत: calling one
    trader's quote a state average is exactly the small dishonesty a follower
    catches once and never forgets."""
    from backend.routes import bhav

    body = "\n".join(f"{l['hi']} — ₹{l['avg']:,} {_move(l['pct'])}" for l in lines)
    if mandis == 1:
        source = f"मॉडल भाव ₹/क्विंटल · {market or 'एक मंडी'} की सरकारी रिपोर्ट"
    else:
        source = f"औसत मॉडल भाव ₹/क्विंटल · {mandis} मंडियों की सरकारी रिपोर्ट"
    return (f"🌾 *{hi_state} मंडी भाव — {bhav._hindi_date(date.today())}*\n\n"
            f"{body}\n\n"
            f"{source}\n"
            f"स्रोत: Agmarknet (data.gov.in)\n\n"
            f"अपने जिले का पूरा भाव 👇\n"
            f"{SITE}/bhav/rajya/{s_slug}{_LINK_Q}")


def posts(refresh: bool = False) -> list:
    """One entry per state that has a channel and something true to say.

    A state whose every market is thin is retried at one mandi rather than
    dropped (note 1 in the file header): Delhi's Azadpur is a bigger mandi than
    most states have, and silence there was a rule misfiring, not a data gap."""
    global _cache, _cache_ts
    from backend.routes import bhav

    if not refresh and _cache and (time.time() - _cache_ts) < _TTL:
        return _cache.get("posts", [])

    snap = _snapshot()
    out, seen = [], {}
    for state, state_rows in snap.items():
        markets = {m for agg in state_rows.values() for m in agg["mandis"] if m}
        # Kept for coverage(), which has to tell "no market reported" apart
        # from "markets reported, but nothing a farmer grows".
        seen[wa_channels._key(state)] = {"markets": len(markets),
                                         "commodities": len(state_rows)}
        chan = wa_channels.channel_for(state)
        if not chan:
            continue
        thin = False
        lines = _crop_lines(state_rows)
        if not lines:
            lines = _crop_lines(state_rows, min_mandis=_THIN_MIN_MANDIS)
            thin = bool(lines)
        if not lines:
            continue
        hi_state = bhav._hindi_state(state)
        s_slug = bhav._slugify(state)
        mandis = len(markets)
        score = _score_post(lines)
        out.append({
            "state":    state,
            "hi_state": hi_state,
            "slug":     s_slug,
            "channel":  chan["name"],
            "url":      chan["url"],
            "crops":    lines,
            "mandis":   mandis,
            "thin":     thin,
            "score":    score,
            "band":     band(score),
            "flags":    _flags(lines),
            "text":     _text(hi_state, s_slug, lines, mandis,
                              next(iter(markets)) if mandis == 1 else ""),
        })

    # Biggest first — that is the order they should be posted in on a morning
    # where there is not time for all 31.
    out.sort(key=lambda p: -p["mandis"])
    _cache, _cache_ts = {"posts": out, "seen": seen}, time.time()
    return out


# Why a channel has nothing today. Both are honest answers and they are not the
# same answer, so the page says which one it is.
_WHY = {
    "no_rows":  "आज इस राज्य की किसी मंडी ने कोई रिपोर्ट नहीं भेजी",
    "no_crops": "मंडी की रिपोर्ट तो आई, पर उसमें कोई फसल नहीं थी",
}


def coverage(refresh: bool = False) -> dict:
    """Posts, plus the channels that get nothing today.

    Every channel in wa_channels.json comes back in one list or the other, so
    the page is the whole morning rather than a filtered view of it. Dropping
    the quiet ones silently would leave the owner wondering why his list is
    short and whether the page is broken; naming them, with the reason, says
    the quiet part out loud: those channels have nothing honest to post."""
    from backend.routes import bhav

    rows = posts(refresh)
    seen = _cache.get("seen", {})
    have = {wa_channels._key(r["state"]) for r in rows}
    quiet = []
    for key, chan in wa_channels.live().items():
        if key in have:
            continue
        raw = (wa_channels._spec().get("channels", {}).get(key) or {}).get("state") or key
        why = "no_crops" if seen.get(key, {}).get("markets") else "no_rows"
        quiet.append({"state": raw, "hi_state": bhav._hindi_state(raw),
                      "channel": chan["name"], "url": chan["url"],
                      "slug": bhav._slugify(raw), "why": why, "why_hi": _WHY[why]})
    quiet.sort(key=lambda q: q["hi_state"])
    return {"posts": rows, "quiet": quiet, "channels": len(wa_channels.live())}

def post_for(state: str, refresh: bool = False):
    key = wa_channels._key(state)
    return next((p for p in posts(refresh) if wa_channels._key(p["state"]) == key), None)


if __name__ == "__main__":  # pragma: no cover
    import sys
    if len(sys.argv) > 1:
        p = post_for(" ".join(sys.argv[1:]))
        if not p:
            print("no post for that state (no channel, or no prices)")
        else:
            print(f"-- भरोसा {p['score']}/100 · {p['band']['hi']}"
                  + (" · thin" if p["thin"] else ""))
            for f in p["flags"]:
                print("   ! " + f)
            print()
            print(p["text"])
    else:
        cov = coverage()
        for p in cov["posts"]:
            print(f"-- {p['hi_state']} ({p['channel']}) · {p['mandis']} mandis "
                  f"· भरोसा {p['score']}/100 {p['band']['hi']}"
                  + (" · thin" if p["thin"] else ""))
            for f in p["flags"]:
                print("   ! " + f)
        print(f"\n{len(cov['posts'])}/{cov['channels']} channels have a post today")
        for q in cov["quiet"]:
            print(f"   x {q['hi_state']:18} {q['why_hi']}")
