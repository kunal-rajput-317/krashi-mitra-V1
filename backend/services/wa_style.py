# ============================================================
# services/wa_style.py
# अंदाज़ — the WRITING layer for the daily WhatsApp channel post.
# ------------------------------------------------------------
# services/wa_post.py works out what is TRUE for a state today. This module
# works out how to SAY it. The split is the whole point of the file, and it is
# a hard rule rather than a tidiness preference:
#
#     wa_post decides the numbers. wa_style may only arrange words around
#     them. Nothing here computes, rounds, filters or drops a price.
#
# Everything printed arrives pre-formatted in the line dicts wa_post built, so
# there is no path by which choosing a different format or a different tone can
# change a rupee figure. A test asserts exactly that: all 30 format×tone
# combinations for a state print the identical set of prices.
#
# WHY THIS EXISTS
# ---------------
# The post had one shape and one voice, and it went out 365 days a year. A
# follower in Maharashtra saw the same six lines in the same order opening on
# the same word every single morning; by week three the message is not read,
# it is recognised and swiped past. That is how a channel dies — not by being
# wrong, by being predictable. A mute costs a follower permanently, and there
# is no notification that tells you it happened.
#
# So a post now varies along three axes, and none of them is random:
#
#   1. FORMAT — six ways to lay out the same day's prices. A list, an up/down
#      split, a lead on the biggest mover, the spread across mandis (which
#      names the market paying most — information the list shape simply cannot
#      carry), the week's range, and the question-and-answer shape a farmer
#      actually types into Google.
#   2. TONE — five voices. A tone may reword the heading, the source line and
#      the call to action. It may never add a claim, a number or advice.
#   3. LANGUAGE — krashimitra_kerala was broadcasting in Hindi, and so were
#      nine other state channels whose followers do not read it. Maharashtra's
#      was subtler and the same kind of mistake: the post said मंडी भाव and
#      गेहूं while the page it linked to said बाजार भाव and गहू. Wrong script
#      or wrong dialect, a follower who cannot read the message did not get
#      the price. See services/wa_lang, which resolves both.
#
# ROTATION, NOT RANDOMNESS
# ------------------------
# _slot() walks each state through a full cycle before anything repeats: the
# step is chosen coprime to the cycle length, so over six days a state sees all
# six formats and over five days all five tones — never the same one twice in
# the window, and never two states in lockstep on the same morning. It is a
# pure function of (state, date), which buys three things random.choice() could
# not: the panel can show the next seven days before they happen, a reload
# never reshuffles a post the owner was halfway through checking, and the tests
# can assert the no-repeat property instead of hoping for it.
#
# A format today's data cannot honestly support is skipped, not faked — हफ़्ता
# needs a week of history, दायरा needs more than one market. The rotation walks
# on to the next one. सूची fits every day and is the floor.
#
# Runnable manually:  python -m backend.services.wa_style
# ============================================================

import hashlib
import math
from datetime import date, timedelta

from backend.services import wa_lang

# Day 0 of every rotation. Fixed forever: moving it re-deals which state gets
# which format on which morning, which is churn with no upside.
_EPOCH = date(2026, 1, 1)

# A move smaller than this is rounding, not news. Both the चढ़े/गिरे grouping
# and the "biggest mover" headline refuse to call it a move.
_REAL_MOVE = 0.5

# The hard ceiling on compose()'s optional `extra` line. Public because
# services/wa_extra checks against the same number when it builds and screens
# candidates — a suggestion the panel shows as acceptable must be a suggestion
# that survives composition intact, or the owner picks a line and gets a
# different one.
EXTRA_MAX = 160


# ── the rotation ─────────────────────────────────────────────

def _h(key: str) -> int:
    """A stable integer for a state name.

    hashlib, deliberately, not the builtin hash(): PYTHONHASHSEED is randomised
    per process, so builtin hash would hand Bihar a different format every time
    Render restarts the worker — and the panel's "next 7 days" would be a lie
    the moment it was read."""
    return int(hashlib.md5(key.encode("utf-8")).hexdigest()[:8], 16)


def _slot(key: str, day: date, n: int) -> int:
    """Which of `n` choices this key gets on this day.

    Advances by a step coprime to n, so the sequence is a full cycle: all n
    choices appear before any repeats. A plain +1 would give that too, but then
    every state would move in step and the whole country would read the same
    shape on the same morning — the offset from _h() is what staggers them, and
    the per-key step is what keeps two states that happen to start together
    from staying together."""
    if n <= 1:
        return 0
    h = _h(key)
    step = 1 + (h % (n - 1))
    for _ in range(n):                     # bounded; step=1 always terminates it
        if math.gcd(step, n) == 1:
            break
        step = 1 + (step % (n - 1))
    return (h + step * (day - _EPOCH).days) % n


# ── tones — voice only, never a claim ────────────────────────
# Each tone supplies the frame: the heading, an optional opening line, how the
# source is worded, and the call to action. The crop lines between them are
# built by the format and are byte-identical across all five tones.
#
# `src_avg`/`src_one` are two wordings of one slot — which one a post uses is a
# data question (does this state have more than one reporting market?) answered
# in compose(); how each reads is a language question, answered here. Same
# division state_lang.fill() draws for /bhav.

TONES = [
    {
        "id": "seedha", "hi": "सीधा", "note": "जो है वही — कोई सजावट नहीं।",
        "title": "🌾 *{state} {bhav} — {date}*",
        "open": "",
        "src_avg": "औसत मॉडल भाव ₹/क्विंटल · {n} मंडियों की सरकारी रिपोर्ट",
        "src_one": "मॉडल भाव ₹/क्विंटल · {market} की सरकारी रिपोर्ट",
        "credit": "स्रोत: Agmarknet (data.gov.in)",
        "cta": "अपने जिले का पूरा भाव 👇",
    },
    {
        "id": "bazaari", "hi": "मंडी की भाषा", "note": "जैसे मंडी में बात होती है।",
        "title": "🌾 *{state} — आज की मंडी, {date}*",
        "open": "आज का हाल —",
        "src_avg": "भाव ₹/क्विंटल · {n} मंडियों का औसत, सरकारी रिपोर्ट से",
        "src_one": "भाव ₹/क्विंटल · {market} मंडी की सरकारी रिपोर्ट",
        "credit": "स्रोत: Agmarknet (data.gov.in)",
        "cta": "अपनी मंडी का भाव यहाँ 👇",
    },
    {
        "id": "saathi", "hi": "अपनापन", "note": "घर जैसी बात — पर बात वही।",
        "title": "🙏 *{state} {bhav} — {date}*",
        "open": "राम-राम! आज के भाव देख लीजिए —",
        "src_avg": "ये {n} मंडियों की सरकारी रिपोर्ट का औसत है, ₹/क्विंटल",
        "src_one": "ये {market} की सरकारी रिपोर्ट है, ₹/क्विंटल",
        "credit": "स्रोत: Agmarknet (data.gov.in)",
        "cta": "अपने जिले का पूरा भाव इस लिंक पर 👇",
    },
    {
        "id": "report", "hi": "रिपोर्ट जैसा", "note": "सरकारी रिपोर्ट का लहजा।",
        "title": "📋 *{state} — {date} की मंडी रिपोर्ट*",
        "open": "सरकारी रिपोर्ट के अनुसार आज के मॉडल भाव —",
        "src_avg": "{n} मंडियों का औसत · ₹/क्विंटल",
        "src_one": "{market} · ₹/क्विंटल",
        "credit": "स्रोत: Agmarknet (data.gov.in), भारत सरकार",
        "cta": "जिलेवार पूरी रिपोर्ट 👇",
    },
    {
        "id": "sankshipt", "hi": "छोटा और साफ़", "note": "सिर्फ़ भाव — कम से कम शब्द।",
        "title": "🌾 *{state} · {date}*",
        "open": "",
        "src_avg": "₹/क्विंटल · {n} मंडियां · Agmarknet (data.gov.in)",
        "src_one": "₹/क्विंटल · {market} · Agmarknet (data.gov.in)",
        "credit": "",
        "cta": "पूरा भाव 👇",
    },
]

# Words the FORMATS need. Not part of a tone: "चढ़े" is the name of a group, not
# a way of speaking, and it has to read the same whichever voice is on.
LABELS = {
    "up": "📈 चढ़े", "down": "📉 गिरे", "flat": "➖ टिके",
    "top_market": "सबसे ऊँचा {market} ₹{hi}",
    "week": "हफ़्ते में ₹{lo}–₹{hi}",
    "ask": "❓ आज {state} में {crop} का भाव क्या है?",
    "ans": "👉 ₹{price} प्रति क्विंटल",
    "also": "बाकी फसलें —",
    "big_up": "*{crop} ₹{price}* — कल से {pct}% ऊपर",
    "big_down": "*{crop} ₹{price}* — कल से {pct}% नीचे",
    "rest": "बाकी भाव —",
    "same": "— कल जैसा",
}


def _pack(lang: str) -> dict:
    """The tone/label strings for a language, Hindi underneath.

    Per-string fallback, the same contract state_lang.word() gives the /bhav
    pages: an untranslated line renders in Hindi, which a Marathi reader still
    reads, rather than blanking or raising. Keys are flat and namespaced
    (`seedha.title`, `label.up`) so a translator can add one wording at a time
    and watch it appear."""
    blk = wa_lang.pack("wa", lang)
    return blk if isinstance(blk, dict) else {}


def _s(pack: dict, key: str, default: str) -> str:
    v = pack.get(key)
    return v if isinstance(v, str) and v.strip() else default


def move_text(pct, lang: str = wa_lang.HINDI) -> str:
    """"▲ 2.8%", or the words for "no change".

    The one piece of wording wa_post has to bake into a line rather than leave
    to a format, because every format prints it and all of them print it
    identically. The arrow already says which way, so a "-" after a ▼ would be
    the same word twice."""
    if pct is None or pct == 0:
        return _s(_pack(lang), "label.same", LABELS["same"])
    return f"{'▲' if pct > 0 else '▼'} {abs(pct):g}%"


# ── formats — six ways to lay out one day's prices ───────────
# Each is a `fits` test and a `body` builder. `fits` is what keeps the module
# honest: हफ़्ता cannot be written for a state with no price history and दायरा
# cannot be written for a state with one market, so on those mornings those
# formats are not offered rather than written around a gap.

def moved(lines: list) -> list:
    """The lines that really moved since yesterday. Public because wa_post's
    नयापन count has to mean exactly what चढ़े–गिरे means by "moved" — two
    thresholds would be two answers to one question on the same card."""
    return [l for l in lines if l.get("pct") is not None and abs(l["pct"]) >= _REAL_MOVE]


def _by_move(pool: list) -> list:
    return sorted(pool, key=lambda l: (-abs(l.get("pct") or 0), l.get("rank", 999)))


def _line(l: dict, move: bool = True) -> str:
    """One crop's line — the shape every format shares.

    The rupee figure and the arrow arrive from wa_post already decided; this
    only chooses whether the move is printed beside them."""
    return f"{l['name']} — ₹{l['avg']:,}" + (f" {l['move']}" if move else "")


def _f_suchi(lines, ctx, pack):
    return "\n".join(_line(l) for l in lines)


def _f_chadha(lines, ctx, pack):
    """चढ़े / गिरे / टिके — the same crops as the list, read in the order a
    farmer cares about: what moved. An empty group is dropped, never printed
    empty."""
    up = [l for l in lines if (l.get("pct") or 0) >= _REAL_MOVE]
    dn = [l for l in lines if (l.get("pct") or 0) <= -_REAL_MOVE]
    moved = {id(l) for l in up} | {id(l) for l in dn}
    flat = [l for l in lines if id(l) not in moved]
    out = []
    for key, group in (("up", up), ("down", dn), ("flat", flat)):
        if not group:
            continue
        head = _s(pack, f"label.{key}", LABELS[key])
        out.append(f"*{head}*\n" + "\n".join(_line(l, move=key != "flat") for l in group))
    return "\n\n".join(out)


def _f_bada(lines, ctx, pack):
    """One headline, then the rest. The headline is the day's biggest real
    move — the one line a follower would have wanted if he read only one, and
    the line the plain list buries at position four."""
    head, rest = lines[0], lines[1:]
    pct = abs(head.get("pct") or 0)
    key = "big_up" if (head.get("pct") or 0) > 0 else "big_down"
    top = _s(pack, f"label.{key}", LABELS[key]).format(
        crop=head["name"], price=f"{head['avg']:,}", pct=f"{pct:g}")
    body = "\n".join(_line(l) for l in rest)
    return f"{top}\n\n{_s(pack, 'label.rest', LABELS['rest'])}\n{body}" if body else top


def _f_daayra(lines, ctx, pack):
    """Where in the state the highest price is being paid, crop by crop.

    The only format that answers "so where do I take it?" — an average never
    can. A line carries the tail only when its top market is named and actually
    above the average; the rest print plain rather than say the same number
    twice in one line."""
    out = []
    for l in lines:
        row = _line(l, move=False)
        if l.get("top_market") and l.get("p_hi") and l["p_hi"] > l["avg"]:
            tail = _s(pack, "label.top_market", LABELS["top_market"]).format(
                market=l["top_market"], hi=f"{l['p_hi']:,}")
            row += f" · {tail}"
        out.append(row)
    return "\n".join(out)


def _f_hafta(lines, ctx, pack):
    """Today's price against the week it sits in. Genuinely new information:
    ₹2,645 means one thing after a week at ₹2,600 and the opposite after a week
    at ₹2,900, and no single-day post has ever said which."""
    out = []
    for l in lines:
        row = _line(l, move=False)
        if l.get("w_lo") and l.get("w_hi") and l["w_hi"] > l["w_lo"]:
            tail = _s(pack, "label.week", LABELS["week"]).format(
                lo=f"{l['w_lo']:,}", hi=f"{l['w_hi']:,}")
            row += f" · {tail}"
        out.append(row)
    return "\n".join(out)


def _f_sawal(lines, ctx, pack):
    """The shape of the question a farmer types into Google, answered.

    Not decoration: it is the phrasing the /bhav page this post links to is
    titled with, so the post and the page read as one answer instead of two."""
    top, rest = lines[0], lines[1:]
    q = _s(pack, "label.ask", LABELS["ask"]).format(state=ctx["state"], crop=top["name"])
    a = _s(pack, "label.ans", LABELS["ans"]).format(price=f"{top['avg']:,}")
    body = "\n".join(_line(l) for l in rest)
    return f"{q}\n{a}\n\n{_s(pack, 'label.also', LABELS['also'])}\n{body}" if body else f"{q}\n{a}"


FORMATS = [
    {"id": "suchi", "hi": "सूची", "note": "सीधी लिस्ट — जो अब तक जाता रहा है।",
     "pick": "rank", "min": 1, "fits": lambda p: True, "body": _f_suchi},

    {"id": "chadha", "hi": "चढ़े–गिरे", "note": "ऊपर, नीचे और टिके — अलग-अलग।",
     "pick": "rank", "min": 3,
     "fits": lambda p: bool(moved(p)), "body": _f_chadha},

    {"id": "bada", "hi": "सबसे बड़ी हलचल", "note": "दिन की सबसे बड़ी हलचल सबसे ऊपर।",
     "pick": "move", "min": 2,
     "fits": lambda p: bool(moved(p)), "body": _f_bada},

    {"id": "daayra", "hi": "कहाँ सबसे ऊँचा", "note": "किस मंडी में सबसे ज़्यादा मिल रहा है।",
     "pick": "rank", "min": 2,
     "fits": lambda p: sum(1 for l in p if l.get("top_market")
                           and (l.get("p_hi") or 0) > l["avg"]) >= 2,
     "body": _f_daayra},

    {"id": "hafta", "hi": "हफ़्ते का हाल", "note": "आज का भाव, हफ़्ते के दायरे में।",
     "pick": "rank", "min": 2,
     "fits": lambda p: sum(1 for l in p if l.get("w_lo") and l.get("w_hi")
                           and l["w_hi"] > l["w_lo"]) >= 2,
     "body": _f_hafta},

    {"id": "sawal", "hi": "सवाल–जवाब", "note": "जो सवाल किसान Google में लिखता है।",
     "pick": "rank", "min": 2, "fits": lambda p: True, "body": _f_sawal},
]

_FMT = {f["id"]: f for f in FORMATS}
_TONE = {t["id"]: t for t in TONES}


def catalog() -> dict:
    """What the panel puts in its two dropdowns. Metadata only — no builders."""
    return {
        "formats": [{k: f[k] for k in ("id", "hi", "note")} for f in FORMATS],
        "tones":   [{k: t[k] for k in ("id", "hi", "note")} for t in TONES],
    }


def fits(fmt_id: str, pool: list) -> bool:
    """Can this format be written honestly from today's pool? The panel greys
    out the ones that cannot rather than hiding them — "why is दायरा missing?"
    is a question worth answering on the card."""
    f = _FMT.get(fmt_id)
    return bool(f) and len(pool) >= f["min"] and f["fits"](pool)


# ── choosing ─────────────────────────────────────────────────

def pick_lines(fmt_id: str, pool: list, n: int) -> list:
    """The crops this format will name, most important first.

    Two orders, because the formats want different things: most want the
    curated staple order (गेहूं first, whatever the day did), while सबसे बड़ी
    हलचल is *about* the movement and would be pointless led by a crop that did
    not move. Both draw on the same pool, so no format reaches a crop the
    others could not."""
    f = _FMT.get(fmt_id) or FORMATS[0]
    ordered = _by_move(pool) if f["pick"] == "move" else pool
    return ordered[:max(1, n)]


def tone_at(state_key: str, day: date) -> dict:
    """Tone rotates on its own key, so voice and shape do not travel together —
    otherwise the pair would repeat every six days instead of every thirty."""
    return TONES[_slot(state_key + "|tone", day, len(TONES))]


def plan(state_key: str, day: date, pool: list) -> tuple:
    """(format, tone) for this state on this day.

    Walks the rotation from today's slot and takes the first format the data
    can honestly support, so a one-market state is never offered दायरा and a
    state with no history is never offered हफ़्ता. सूची fits everything, so this
    always returns."""
    n = len(FORMATS)
    base = _slot(state_key, day, n)
    for i in range(n):
        f = FORMATS[(base + i) % n]
        if len(pool) >= f["min"] and f["fits"](pool):
            return f, tone_at(state_key, day)
    return FORMATS[0], tone_at(state_key, day)


def schedule(state_key: str, day: date, days: int = 7) -> list:
    """The next `days` mornings for one channel, before they happen.

    The rotation is a pure function of (state, date), so this is not a forecast
    — it is the same arithmetic the post itself will run. It is on the panel
    for one reason: "is this actually varying?" is the question the owner will
    ask, and the honest answer is a list he can read. It shows the rotation's
    intent, not its outcome: a format the day's data cannot support will be
    stepped over when the morning arrives."""
    out = []
    for i in range(days):
        d = day + timedelta(days=i)
        f = FORMATS[_slot(state_key, d, len(FORMATS))]
        t = tone_at(state_key, d)
        out.append({"date": d.isoformat(), "format": f["id"], "format_hi": f["hi"],
                    "tone": t["id"], "tone_hi": t["hi"]})
    return out


# ── composing ────────────────────────────────────────────────

def compose(ctx: dict, lines: list, fmt_id: str, tone_id: str,
            extra: str = "") -> str:
    """The post. WhatsApp bolds *between asterisks*.

    `ctx` carries the already-decided facts — state name, date string, mandi
    count, link — and `lines` the already-computed prices. Nothing here does
    arithmetic; the day it needs to, that number belongs in wa_post instead.

    `extra` is the one string in this function that did not come from wa_post:
    an optional line the owner chose on the panel, from services/wa_extra. It
    is placed BETWEEN the prices and the source line, so it can never be read
    as part of a crop row or as part of the attribution.

    Two levels of guard, and they are split on purpose. Here, where every
    format×tone test runs, the guard is structural and unconditional: one
    line, length-capped. It cannot break the shape of a post whatever it
    contains. The guards about MEANING — no second link, no contact detail, no
    figure we did not supply — live in wa_extra.check() and are enforced once,
    at wa_post.recompose(), which is the only door the panel can come through.
    Putting them here too would be a second answer to the same question."""
    f = _FMT.get(fmt_id) or FORMATS[0]
    t = _TONE.get(tone_id) or TONES[0]
    pack = _pack(ctx.get("lang") or wa_lang.HINDI)
    tid = t["id"]

    title = _s(pack, f"{tid}.title", t["title"]).format(
        state=ctx["state"], bhav=ctx["bhav"], date=ctx["date"])
    open_ = _s(pack, f"{tid}.open", t["open"])
    body = f["body"](lines, ctx, pack)

    # One market is not an average, and a post built on one must not use the
    # word. The same small honesty the /bhav page keeps one level down.
    if ctx.get("mandis", 0) == 1 and ctx.get("market"):
        src = _s(pack, f"{tid}.src_one", t["src_one"]).format(market=ctx["market"])
    else:
        src = _s(pack, f"{tid}.src_avg", t["src_avg"]).format(n=ctx.get("mandis", 0))
    credit = _s(pack, f"{tid}.credit", t["credit"])
    cta = _s(pack, f"{tid}.cta", t["cta"])

    parts = [title]
    if open_:
        parts.append(open_)
    parts.append(body)
    if extra:
        parts.append(" ".join(str(extra).split())[:EXTRA_MAX])
    parts.append("\n".join(x for x in (src, credit) if x))
    parts.append(f"{cta}\n{ctx['url']}")
    return "\n\n".join(p for p in parts if p)


if __name__ == "__main__":  # pragma: no cover
    today = date.today()
    print(f"rotation from {_EPOCH} · {len(FORMATS)} formats × {len(TONES)} tones "
          f"= {len(FORMATS) * len(TONES)} combinations, "
          f"repeating every {len(FORMATS) * len(TONES)} days\n")
    for st in ("uttar_pradesh", "maharashtra", "bihar", "punjab", "delhi"):
        row = "  ".join(f"{s['format']:6}/{s['tone']:9}" for s in schedule(st, today, 5))
        print(f"{st:16} {row}")
