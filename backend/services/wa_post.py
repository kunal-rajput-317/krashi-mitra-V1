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
# WHAT NEVER CHANGES, whatever shape the post takes:
#   • the numbers are IN the post, not behind the link. A post that withholds
#     the price to force a click is the kind farmers mute.
#   • one deep link, to /bhav/rajya/<state> — the crop-less state hub, which is
#     the page that asks "which district?" instead of assuming a crop.
#   • utm_source=wa so GA4 can separate channel traffic from SEO traffic. That
#     is the only way to answer "is the channel working": in-app WhatsApp
#     clicks arrive with no referrer and would otherwise count as direct.
#
# WHAT DOES CHANGE is the layout and the voice, and that is deliberate. The
# post used to have exactly one shape, sent 365 mornings a year; a message a
# follower can recognise without reading is a message he stops reading. The
# rotation lives in services/wa_style, which may only arrange words around the
# figures this module computes — see that file's header for the split. Nothing
# there can move a price, and a test holds it to that.
#
# THIS FILE OWNS THE FACTS. Three of them are newer than the original post and
# exist because one day's average, alone, is not enough to act on:
#   • `top_market` — which market in the state is paying the most today, named
#     only when the mandis broadly agree (otherwise the "highest" price is a
#     different variety under the same name, and naming it sends a farmer
#     200km for a premium his sack does not qualify for).
#   • `w_lo`/`w_hi` — the state average across its last week of reports, so
#     ₹2,645 can be read against the week it sits in.
#   • novelty() — how many of today's crops actually moved. A post where
#     nothing moved is yesterday's post, and the panel says so rather than
#     letting a rearranged copy go out looking new.
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
from backend.services import state_lang, wa_channels, wa_style

SITE = "https://krashimitra.in"
_TTL = 300.0                      # seconds; the fetch cron runs ~6×/day
_LINK_Q = "?utm_source=wa&utm_medium=channel&utm_campaign=daily_bhav"

# How many crops a post carries. Five fits a phone screen without scrolling and
# is about as much as anyone reads standing in a field; more just buries the
# top line. A crop needs a few mandis behind it before its "state average" is
# an average at all rather than one trader's quote.
_CROPS_PER_POST = 5
_MIN_MANDIS = 3

# How many crops the POOL holds. The formats in services/wa_style pick their
# own lines out of it — सबसे बड़ी हलचल wants the day's biggest mover, which is
# often the ninth staple rather than the first — and the panel's "फसल चुनें"
# chips let the owner swap a crop he does not trust for one he does. Both need
# more than the five that get printed. Twelve is where the curated tile order
# stops being staples and starts being whatever else the state reported.
_POOL = 12

# Crops per post, as the panel may change it. Three fits a glance, five is the
# default that fits a phone screen, eight is as much as anyone reads standing
# in a field.
_MIN_CROPS, _MAX_CROPS = 3, 8

# हफ़्ते का हाल — how far back `spark` is read, and the floor below which a
# "week" is not a week. See _week().
_WEEK_DAYS = 7
_WEEK_MIN_POINTS = 3
_WEEK_MIN_MANDIS = 2

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


def _market_name(state: str, market: str, lang: str) -> str:
    """A market's name in the post's language, or the feed's spelling unchanged.

    Agmarknet sends markets in English ("Lasalgaon"), and most of them are
    named after the district they sit in — so the district table already knows
    the great majority of them, and the ones it does not fall through unchanged
    exactly as the one-market source line has always printed them. Never
    raises, never invents: an unknown market prints as the feed spells it,
    which is at worst what a follower saw yesterday."""
    from backend.routes import bhav
    if not market:
        return ""
    return state_lang.district(bhav._hindi_district(state, market), lang)


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


def _week(sparks: list) -> tuple:
    """(low, high) of the STATE AVERAGE over its recent reports, or (None, None).

    `spark` is one mandi's last ~8 modal prices, chronological, with no dates
    on them — so the only alignment available is position-from-the-end, which
    is "each mandi's k-th most recent report". For mandis reporting daily that
    is a date; for the rest it is close enough, and the aggregate is an average
    across mandis either way.

    The number this produces is therefore the same *kind* of number as the
    headline: the state's average, computed the same way, on an earlier report.
    Min and max across those is what हफ़्ते का हाल prints, and the wording
    ("हफ़्ते में ₹lo–₹hi") claims exactly that and nothing more.

    Two guards, because a range built on one mandi or two points is not a
    week: at least _WEEK_MIN_MANDIS mandis have to carry a spark, and at least
    _WEEK_MIN_POINTS positions have to be usable. Below either, the caller
    gets (None, None) and हफ़्ता is simply not offered for that crop."""
    series = []
    for s in sparks:
        vals = [v for v in (_num(x) for x in str(s or "").split(",")) if v]
        if len(vals) >= _WEEK_MIN_POINTS:
            series.append(vals[-_WEEK_DAYS:])
    if len(series) < _WEEK_MIN_MANDIS:
        return None, None
    avgs = []
    for k in range(1, _WEEK_DAYS + 1):                 # k-th from the end
        at_k = [s[-k] for s in series if len(s) >= k]
        if len(at_k) >= _WEEK_MIN_MANDIS:
            avgs.append(sum(at_k) / len(at_k))
    if len(avgs) < _WEEK_MIN_POINTS:
        return None, None
    return round(min(avgs)), round(max(avgs))


def _snapshot() -> dict:
    """{state: {commodity: {modals, prev_pairs, mandis, ages, sparks, top}}}
    for the whole country.

    One query for every state rather than one per state: the admin page asks
    for all 31 at once, and 31 round trips to Neon for what is a single index
    scan is the difference between a page that opens and a page that times out
    on the free tier.

    `ages` carries each row's arrival_date in days-old form. It never touches
    an average — it is the raw material for the freshness part of the
    confidence score, and nothing else reads it.

    `sparks` and `top` are the two facts the older single-day post had no way
    to carry, and both are read straight off the row we were already fetching:
    where in the state today's highest price is being paid, and what the last
    week looked like. A price with neither is a number; with them it is
    something a farmer can act on."""
    db = SessionLocal()
    try:
        rows = db.query(MandiPrice.state, MandiPrice.commodity, MandiPrice.market,
                        MandiPrice.modal_price, MandiPrice.prev_modal_price,
                        MandiPrice.arrival_date, MandiPrice.spark).all()
    finally:
        db.close()

    today = date.today()
    out: dict = {}
    for state, commodity, market, modal, prev, arrival, spark in rows:
        m = _num(modal)
        if not (state and commodity and m):
            continue
        slot = out.setdefault(state, {}).setdefault(
            commodity, {"modals": [], "prev_pairs": [], "mandis": set(),
                        "ages": [], "sparks": [], "top": None})
        slot["modals"].append(m)
        slot["mandis"].add(market or "")
        slot["ages"].append(_age_days(arrival, today))
        if spark:
            slot["sparks"].append(spark)
        if market and (slot["top"] is None or m > slot["top"][0]):
            slot["top"] = (m, market)
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
    name = l.get("name") or l["hi"]
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


def _crop_lines(state_rows: dict, min_mandis: int = _MIN_MANDIS,
                limit: int = _POOL, lang: str = "hi", state: str = "") -> list:
    """The crops this state's post could name, most-important first.

    Ordered by _tile_rank — the same curated staple order the mandi grid and
    the /bhav hub use — so a state's post opens on गेहूं/धान rather than on
    whatever sorts first alphabetically. Ties break on how many mandis
    reported, because that is how confident the number is.

    This returns a POOL, not the post: the formats in services/wa_style pick
    their own lines out of it and the panel can swap one for another. What each
    line carries is decided here and only here — a format may rearrange these
    strings but never recompute them, which is what makes "the same numbers in
    every format" a property of the code rather than a promise.

    `lang` localises the crop and market names onto whatever the /bhav page
    this post links to is written in. A Maharashtra post that says गेहूं while
    the page it points at says गहू is two answers to one question."""
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
        hi = bhav._hindi_name(commodity)
        top = agg.get("top")
        w_lo, w_hi = _week(agg.get("sparks") or [])
        line = {
            "commodity": commodity,
            "hi": hi,
            "name": state_lang.crop(hi, lang),
            "avg": avg, "pct": pct, "mandis": mandis,
            "rank": bhav._tile_rank(commodity),
            "dated": len(ages),
            "age": int(statistics.median(ages)) if ages else None,
            "fresh_share": (sum(1 for a in ages if a <= _FRESH_DAYS) / len(ages)) if ages else 0.0,
            "cv": (statistics.pstdev(modals) / mean) if (len(modals) > 1 and mean) else 0.0,
            "p_lo": round(min(modals)), "p_hi": round(max(modals)),
            "paired_share": len(agg["prev_pairs"]) / len(modals) if modals else 0.0,
            # Where the day's highest price is being paid — but only when the
            # state's mandis broadly agree. On a crop whose prices already run
            # ₹700 to ₹5,000 the "highest" market is a different variety under
            # the same name, and naming it would send a farmer 200km for a
            # premium his sack does not qualify for.
            "top_market": _market_name(state, top[1], lang) if (
                top and len(modals) > 1
                and (statistics.pstdev(modals) / mean if mean else 1.0) <= _CV_FLAG) else "",
            "w_lo": w_lo, "w_hi": w_hi,
        }
        line["move"] = _move(pct, lang)
        line["score"], line["flag_kinds"] = _score_line(line)
        line["flags"] = [t for _, t in line["flag_kinds"]]
        picks.append(line)

    picks.sort(key=lambda p: (p["rank"], -p["mandis"]))
    # One line per display name: Agmarknet ships several commodities that
    # render to the same word (three pumpkins are all कद्दू), and a post listing
    # कद्दू three times at three prices reads like a mistake.
    seen, out = set(), []
    for p in picks:
        if p["name"] in seen:
            continue
        seen.add(p["name"])
        out.append(p)
        if len(out) >= limit:
            break
    return out


def _move(pct, lang: str = state_lang.HINDI) -> str:
    """How a day-on-day change reads. The direction is data and is decided
    here; the words for "no change" are language and live in wa_style, which is
    where every other wording in the post already lives."""
    return wa_style.move_text(pct, lang)


def _ctx(state: str, lang: str, mandis: int, market: str) -> dict:
    """The facts a post is written around, all of them already decided.

    services/wa_style receives this and may only arrange words around it — so
    everything that involves a lookup, a date, a slug or a count is settled
    here, where it can be tested, rather than inside a wording."""
    from backend.routes import bhav

    today = date.today()
    hi_state = bhav._hindi_state(state)
    slug = bhav._slugify(state)
    return {
        "state":  hi_state,
        "slug":   slug,
        "lang":   lang,
        # Maharashtra's /bhav pages are headed बाजार भाव, not मंडी भाव. A post
        # that links to a page and disagrees with its first two words is two
        # answers to one question, and the follower has no way to tell which
        # of them is the site.
        "bhav":   state_lang.word("bhav", lang, "मंडी भाव"),
        "date":   state_lang.date_str(today.day, today.month, today.year, lang,
                                      bhav._hindi_date(today)),
        "mandis": mandis,
        "market": market,
        "url":    f"{SITE}/bhav/rajya/{slug}{_LINK_Q}",
    }


# नयापन — is there anything new in today's post at all?
#
# The भरोसा score answers "are these numbers right". This answers the other
# question, the one that decides whether the post is worth sending: "has
# anything changed since the last one?" A state where no crop moved produces
# the same five figures a follower already read yesterday, and a channel that
# says the same thing twice teaches people to stop opening it. The formats
# rotate regardless, which changes how it reads — but rearranging yesterday's
# numbers is not news, and the panel should not pretend otherwise.
#
# Deliberately NOT a score out of 100. It is a count, because a count is
# checkable and a composite would be a made-up number sitting next to real ones.
_NOVEL = {
    "fresh": "आज के भाव बदले हैं",
    "some":  "थोड़ा-बहुत बदला है",
    "same":  "कल जैसी ही पोस्ट",
}


def novelty(lines: list) -> dict:
    """{moved, total, key, hi} — how many of this post's crops actually moved.

    "Moved" means the paired day-on-day comparison found a real change, so a
    crop with no yesterday to compare against counts as not moved. That is the
    conservative reading and the right one: an unverifiable move is exactly
    what a follower should not be told about twice."""
    total = len(lines)
    n = len(wa_style.moved(lines))
    key = "same" if not n else ("fresh" if n >= max(2, total // 2) else "some")
    return {"moved": n, "total": total, "key": key, "hi": _NOVEL[key]}


def _slim(l: dict) -> dict:
    """One pool line as the panel needs it — for the फसल चुनें chips.

    The full line carries the scoring internals (cv, paired_share, flag_kinds);
    those are 31 states × 12 crops of payload that no chip renders."""
    return {k: l[k] for k in ("commodity", "hi", "name", "avg", "move", "score")}


def _build(state: str, state_rows: dict, chan: dict, today: date):
    """(row, pool, ctx) for one state, or None when there is nothing honest to say.

    The pool and ctx come back with the row because recompose() needs the same
    two objects this used, down to the identical line dicts. Rebuilding them on
    the way past would be a second source of truth for the same post, and the
    day the two drifted, the panel's preview would stop being the thing that
    gets pasted.

    A state whose every market is thin is retried at one mandi rather than
    dropped (note 1 in the file header): Delhi's Azadpur is a bigger mandi than
    most states have, and silence there was a rule misfiring, not a data gap."""
    markets = {m for agg in state_rows.values() for m in agg["mandis"] if m}
    lang = state_lang.lang_for(state)

    thin = False
    pool = _crop_lines(state_rows, lang=lang, state=state)
    if not pool:
        pool = _crop_lines(state_rows, min_mandis=_THIN_MIN_MANDIS, lang=lang, state=state)
        thin = bool(pool)
    if not pool:
        return None

    key = wa_channels._key(state)
    mandis = len(markets)
    ctx = _ctx(state, lang, mandis, next(iter(markets)) if mandis == 1 else "")

    fmt, tone = wa_style.plan(key, today, pool)
    lines = wa_style.pick_lines(fmt["id"], pool, _CROPS_PER_POST)
    score = _score_post(lines)
    row = {
        "state":    state,
        "key":      key,
        "hi_state": ctx["state"],
        "slug":     ctx["slug"],
        "lang":     lang,
        "channel":  chan["name"],
        "url":      chan["url"],
        "crops":    lines,
        "pool":     [_slim(l) for l in pool],
        "mandis":   mandis,
        "thin":     thin,
        "score":    score,
        "band":     band(score),
        "flags":    _flags(lines),
        "novelty":  novelty(lines),
        "format":   fmt["id"],
        "tone":     tone["id"],
        # Which of the six could be written honestly from today's rows. The
        # panel greys out the rest rather than hiding them: "why is दायरा
        # missing today?" is a question worth answering on the card.
        "can":      [f["id"] for f in wa_style.FORMATS if wa_style.fits(f["id"], pool)],
        "schedule": wa_style.schedule(key, today),
        "text":     wa_style.compose(ctx, lines, fmt["id"], tone["id"]),
    }
    return row, pool, ctx


def posts(refresh: bool = False) -> list:
    """One entry per state that has a channel and something true to say."""
    global _cache, _cache_ts

    if not refresh and _cache and (time.time() - _cache_ts) < _TTL:
        return _cache.get("posts", [])

    today = date.today()
    snap = _snapshot()
    out, seen, pools, ctxs = [], {}, {}, {}
    for state, state_rows in snap.items():
        markets = {m for agg in state_rows.values() for m in agg["mandis"] if m}
        # Kept for coverage(), which has to tell "no market reported" apart
        # from "markets reported, but nothing a farmer grows".
        seen[wa_channels._key(state)] = {"markets": len(markets),
                                         "commodities": len(state_rows)}
        chan = wa_channels.channel_for(state)
        if not chan:
            continue
        built = _build(state, state_rows, chan, today)
        if not built:
            continue
        row, pool, ctx = built
        # The full pool and ctx are kept out of the response and in the cache:
        # recompose() needs every field of every line, and shipping 31 states ×
        # 12 crops × 20 keys to a browser that renders six of them is the kind
        # of payload that makes a free-tier page feel broken.
        pools[row["key"]], ctxs[row["key"]] = pool, ctx
        out.append(row)

    # Biggest first — that is the order they should be posted in on a morning
    # where there is not time for all 31.
    out.sort(key=lambda p: -p["mandis"])
    _cache = {"posts": out, "seen": seen, "pools": pools, "ctxs": ctxs}
    _cache_ts = time.time()
    return out


def recompose(state: str, fmt: str = "", tone: str = "",
              n: int = 0, drop: set | None = None, refresh: bool = False) -> dict | None:
    """One state's post rewritten under the panel's overrides. None if no post.

    Every argument is optional and every one of them falls back to what the
    rotation chose, so this is also how the panel gets a post back to
    "अपने आप" — send nothing and you get today's plan.

    The भरोसा score is recomputed on the lines that SURVIVE the overrides, not
    on the ones the rotation picked. That is the whole point of letting the
    owner drop a crop: dropping the one line whose price is three days old must
    visibly raise the score, or the control is decoration."""
    key = wa_channels._key(state)
    posts(refresh)
    pool = (_cache.get("pools") or {}).get(key)
    ctx = (_cache.get("ctxs") or {}).get(key)
    base = next((p for p in _cache.get("posts", []) if p["key"] == key), None)
    if not (pool and ctx and base):
        return None

    drop = drop or set()
    kept = [l for l in pool if l["commodity"] not in drop] or pool

    # The format has to fit what is LEFT, not what the morning started with.
    # Dropping crops can take the last real mover out of a state, and सबसे बड़ी
    # हलचल built on a pool that no longer moves prints "कल से 0% ऊपर" — a
    # headline announcing that nothing happened. So an override that no longer
    # fits, and a rotation pick invalidated by the drops, both fall back
    # through plan(), which is the same walk _build() does.
    if not wa_style.fits(fmt, kept):
        fmt = base["format"] if wa_style.fits(base["format"], kept) \
            else wa_style.plan(key, date.today(), kept)[0]["id"]
    tone = tone if any(t["id"] == tone for t in wa_style.TONES) else base["tone"]
    n = min(_MAX_CROPS, max(_MIN_CROPS, n or _CROPS_PER_POST))

    lines = wa_style.pick_lines(fmt, kept, n)
    score = _score_post(lines)
    return {**base,
            "crops": lines, "format": fmt, "tone": tone, "n": n,
            "dropped": sorted(drop),
            "can": [f["id"] for f in wa_style.FORMATS if wa_style.fits(f["id"], kept)],
            "score": score, "band": band(score), "flags": _flags(lines),
            "novelty": novelty(lines),
            "text": wa_style.compose(ctx, lines, fmt, tone)}


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
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    every = "--all" in sys.argv          # every format for one state, side by side
    if args:
        p = post_for(" ".join(args))
        if not p:
            print("no post for that state (no channel, or no prices)")
        else:
            print(f"-- भरोसा {p['score']}/100 · {p['band']['hi']}"
                  f" · नयापन {p['novelty']['moved']}/{p['novelty']['total']}"
                  f" · {p['format']}/{p['tone']} · {p['lang']}"
                  + (" · thin" if p["thin"] else ""))
            for f in p["flags"]:
                print("   ! " + f)
            for v in (wa_style.FORMATS if every else []):
                if v["id"] not in p["can"]:
                    print(f"\n===== {v['id']}: आज नहीं बन सकता =====")
                    continue
                r = recompose(p["state"], fmt=v["id"], tone=p["tone"])
                print(f"\n===== {v['id']} / {p['tone']} =====\n{r['text']}")
            if not every:
                print()
                print(p["text"])
    else:
        cov = coverage()
        for p in cov["posts"]:
            print(f"-- {p['hi_state']} ({p['channel']}) · {p['mandis']} mandis "
                  f"· भरोसा {p['score']}/100 {p['band']['hi']} "
                  f"· {p['format']}/{p['tone']} · नयापन {p['novelty']['hi']}"
                  + (" · thin" if p["thin"] else ""))
            for f in p["flags"]:
                print("   ! " + f)
        print(f"\n{len(cov['posts'])}/{cov['channels']} channels have a post today")
        for q in cov["quiet"]:
            print(f"   x {q['hi_state']:18} {q['why_hi']}")
