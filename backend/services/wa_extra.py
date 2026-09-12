# ============================================================
# services/wa_extra.py
# और क्या डालें — one extra line in the daily post, beyond the भाव.
# ------------------------------------------------------------
# The post says what five crops sold for. That is the reason a farmer follows
# the channel, and it is also the reason he stops reading it in week three: the
# prices are the same five facts in the same shape every morning. services/
# wa_style already varies the SHAPE. This varies the CONTENT — one line, under
# the prices, carrying something the numbers alone could not say.
#
# THE LINE IS THE ONLY PART OF THE POST WHOSE WORDS DID NOT COME FROM wa_post.
# That is a real hole in an otherwise closed system, so it is fenced on four
# sides and every one of the four is enforced here rather than left to whoever
# is pasting at 8am:
#
#   1. IT IS OPT-IN, PER STATE, PER MORNING. Nothing here runs on its own and
#      nothing is stored. The owner presses a button, reads what comes back,
#      and clicks one — or none, which is the default and costs nothing.
#   2. IT MAY NOT CARRY A NUMBER WE DID NOT GIVE IT. Every suggestion is
#      checked against the facts it was built from, using the same numeric
#      comparison the news generator's review_flags() uses. A figure that
#      appears in the sentence and not in the facts is a fabrication, and it is
#      flagged by name so the owner sees exactly which one.
#   3. IT MAY NOT CARRY A LINK. The post has exactly one link, to the state's
#      /bhav hub, and a test in tests/test_wa_style.py asserts that. A second
#      link would split the click and quietly break the only measurement we
#      have of whether the channel works at all.
#   4. IT MAY NOT CARRY A CONTACT DETAIL. Same rule the news generator keeps,
#      for the same reason: a phone number in a broadcast is a support channel
#      nobody staffed.
#
# THE FIRST SUGGESTION IS NEVER FROM A MODEL.
# facts() builds a deterministic MSP line out of services/msp.py, and that one
# is offered first, every time, with no API call. It is the best line on the
# list on most mornings — "these two crops are selling below the government
# floor" is the single most actionable thing we know that the price list does
# not say — and it means the button does something useful when there is no key
# configured, no quota left, or no network. The model's suggestions come after
# it, if they come at all.
#
# Runnable manually:  python -m backend.services.wa_extra "Madhya Pradesh"
# ============================================================

import logging
import re

from backend.services import msp, state_lang, wa_style

log = logging.getLogger(__name__)

# One line, in a message read on a phone in a field. Anything longer is a
# paragraph, and a paragraph under a price list does not get read.
#
# Taken from wa_style rather than set here: that module does the truncating, so
# a second number in this one would mean the panel could show a suggestion as
# acceptable and the composer could then cut it — the owner picking a line and
# getting a different one is worse than the line being too long.
_MAX_LEN = wa_style.EXTRA_MAX
_MAX_SUGGESTIONS = 3

# Guard 3 and guard 4. Deliberately broad: krashimitra.in is as unwelcome here
# as anyone else's domain, because the post already links to it once and the
# rule being kept is "one link", not "one of our links".
_LINK_RE = re.compile(r"https?://|www\.|\b[a-z0-9-]+\.(in|com|org|net|gov)\b", re.I)
_CONTACT_RE = re.compile(r"\b(?:\+?91[\s-]?)?[6-9]\d{9}\b|\b[\w.]+@[\w.]+\.\w+")

# Guard 2's exemption list. A rupee figure is a claim; a date is not, and
# neither is "5 फसल". Kept in step with news_auto_service._numbers(), which is
# imported rather than re-implemented — see _invented().
_YEAR_RE = re.compile(r"(19|20)\d{2}")


def _s(lang: str, key: str, default: str) -> str:
    """One wording, in the post's language, Hindi underneath — the same
    per-string fallback contract services/wa_style and the /bhav pages keep."""
    blk = state_lang.pack("wa", lang)
    v = (blk or {}).get(key) if isinstance(blk, dict) else None
    return v if isinstance(v, str) and v.strip() else default


# ── the facts a line may be built from ───────────────────────

def facts(post: dict) -> list:
    """Everything true we know about this state today that the price list does
    not already say. Each is {kind, text, numbers}.

    This is both the menu the owner picks from AND the ground truth the model's
    suggestions are checked against — one list, so a fact good enough to offer
    is a fact good enough to verify against, and there is no third thing the
    model could have been told."""
    out = []
    lang = post.get("lang") or state_lang.HINDI
    crops = post.get("crops") or []

    # ── MSP: the floor the government already promised, which a mandi price
    # on its own never mentions. msp_for() returns None unless the figure is
    # verified AND its marketing season is still live, so an expired MSP
    # cannot leak in here — that guard lives in services/msp.py and this
    # module does not get to second-guess it.
    below, above = [], []
    for c in crops:
        rec = msp.msp_for(c.get("commodity") or "")
        if not rec:
            continue
        cmp_ = msp.compare(c.get("avg"), rec["msp"])
        if not cmp_:
            continue
        (below if cmp_["side"] == "below" else above).append((c, rec, cmp_))

    if below:
        names = ", ".join(f"{c['name']} (MSP ₹{r['msp']:,})" for c, r, _ in below[:3])
        text = _s(lang, "extra.msp_below",
                  "⚖️ MSP से नीचे — {names}। सरकारी खरीद केंद्र पर इससे कम नहीं मिलना चाहिए।"
                  ).format(names=names)
        out.append({"kind": "msp", "text": text[:_MAX_LEN],
                    "numbers": _numbers(text), "source": "msp.json"})
    elif above:
        text = _s(lang, "extra.msp_above",
                  "⚖️ आज इन फसलों का मंडी भाव MSP से ऊपर है — {names}।"
                  ).format(names=", ".join(c["name"] for c, _, _ in above[:4]))
        out.append({"kind": "msp", "text": text[:_MAX_LEN],
                    "numbers": _numbers(text), "source": "msp.json"})

    # ── One headline, from our own published news. Title only, never the body
    # and never a link: it is a "there is more on the site today" nudge, and
    # the post already carries the one link that gets there.
    try:
        from backend.services.news_auto_service import get_published_posts
        latest = (get_published_posts() or [])[:1]
    except Exception:                                    # noqa: BLE001
        latest = []
    for p in latest:
        title = re.sub(r"\s+", " ", str(p.get("title") or "")).strip()
        if 10 < len(title) <= 110:
            text = _s(lang, "extra.news", "📰 आज की खबर — {title}").format(title=title)
            out.append({"kind": "news", "text": text[:_MAX_LEN],
                        "numbers": _numbers(text), "source": "krashi_news"})

    return out


# ── the four guards ──────────────────────────────────────────

def _numbers(text: str) -> set:
    """Comparable numeric tokens, exactly as the news generator counts them.

    Imported rather than copied, deliberately. "Which figures count as a claim"
    has to have ONE answer across this codebase — two implementations would
    drift, and the drift would show up as a fabricated price going out under a
    check that thought it had looked. The lazy import keeps a heavy module off
    the path of callers that only want facts()."""
    try:
        from backend.services.news_auto_service import _numbers as shared
        return shared(text)
    except Exception:                                    # noqa: BLE001
        # Same rule, spelled out, for the case where that module cannot load:
        # two or more digits, and a bare year is not a claim.
        out = set()
        for m in re.findall(r"[\d,]+(?:\.\d+)?", text or ""):
            d = m.replace(",", "").rstrip(".")
            if len(d.replace(".", "")) >= 2 and not _YEAR_RE.fullmatch(d):
                out.add(d)
        return out


# ── पक्कापन — how much of an AI line is actually ours ────────
#
# check() above is a gate: pass or fail, and a failing line cannot be clicked.
# This is the meter beside it, and it answers the question the gate cannot:
# a line can clear every hard rule and still be subtly wrong.
#
# THE OBSERVED FAILURE, which is why this exists. Given the fact
#     "MSP से नीचे — सोयाबीन (MSP ₹5,328), गेहूं (MSP ₹2,585)"
# the model returned
#     "सोयाबीन (₹5,328) और गेहूं (₹2,585) MSP से नीचे न बेचें"
# Every figure is one of ours, so check() passes it. But the word MSP has moved
# off the figures, and ₹5,328 now reads as what सोयाबीन is selling for. Nothing
# was invented; a label was dropped, and the sentence changed meaning.
#
# WHAT THIS IS NOT: the model's own confidence. A language model's self-rating
# is not evidence — it is more text from the same source, and it is highest
# exactly when the model is fluently wrong. Every component below is computed
# from the line and the facts, and could be recomputed by hand from the card.
#
# 100 points across the three ways a grounded-looking sentence goes wrong.
_W_GROUND, _W_FIGURE, _W_TONE = 45, 35, 20

# Words that change what a number MEANS. A figure that had one of these beside
# it in the fact and has lost it in the rewording is the failure above.
_QUALIFIERS = ("msp", "एमएसपी", "भाव", "रेट", "दाम", "कीमत", "औसत", "क्विंटल")

# How far before a figure to look for its label.
_QUAL_WINDOW = 34

# Hindi function words. They carry no claim, so they are not evidence of
# grounding either way and are left out of the count entirely — otherwise a
# sentence could score well on "में", "से" and "है".
_STOP = {
    "से", "में", "पर", "का", "की", "के", "को", "है", "हैं", "हो", "और", "या",
    "यह", "ये", "वह", "वे", "कि", "तो", "ही", "भी", "नहीं", "न", "एक", "जो",
    "इस", "उस", "अपने", "अपना", "अपनी", "लिए", "साथ", "कर", "करें", "गया",
    "गई", "हुआ", "हुई", "रहा", "रही", "था", "थी", "ना", "व", "ने", "कुछ",
    "सब", "अगर", "जब", "तब", "आप", "हम", "इसे", "उसे", "इससे", "उससे",
    "ऐसे", "वैसे", "दे", "ले", "दिया", "लिया", "कोई", "क्या",
}

# A word, in any script this project posts in.
#
# NOT plain \w. Python's \w is "alphanumeric", and an Indic vowel sign is a
# combining mark, not an alphanumeric — so \w+ chops किसान into क, स, न and
# every "word" it compares is a shard. The grounding score built on that was
# measuring nothing. U+0900–U+0D7F spans Devanagari through Malayalam, which
# covers Hindi, Marathi, Tamil, Kannada, Telugu, Gujarati, Bengali and
# Gurmukhi — every script services/state_lang can put a post in — and the two
# joiners keep conjuncts whole.
_WORD_RE = re.compile(r"[\wऀ-ൿ‌‍]+", re.UNICODE)


def _decomma(t: str) -> str:
    """"₹5,328" → "₹5328", so a figure can be located whichever way it was
    typed. _numbers() already compares them stripped; this lets the label
    check find them in the running text as well."""
    return re.sub(r"(?<=\d),(?=\d)", "", t or "")


def _content(text: str) -> list:
    return [w for w in _WORD_RE.findall((text or "").lower())
            if w not in _STOP and not w.isdigit() and len(w) > 1]


def _grounded(word: str, bag: set) -> bool:
    """Is this word ours? Exact, or a four-letter prefix match.

    The prefix is for inflection, not for generosity: Hindi conjugates, so a
    fact saying "बेचना" and a line saying "बेचें" is the same word doing its
    job. Four letters is short enough to survive a suffix and long enough that
    two unrelated words rarely collide."""
    if word in bag:
        return True
    return len(word) >= 5 and any(
        len(b) >= 5 and b[:4] == word[:4] for b in bag)


def _quals_at(text: str, digits: str) -> set:
    """Which labels sit just before `digits` in `text`, anywhere it appears."""
    flat = _decomma(text).lower()
    found = set()
    for m in re.finditer(re.escape(digits), flat):
        window = flat[max(0, m.start() - _QUAL_WINDOW):m.start()]
        found |= {q for q in _QUALIFIERS if q in window}
    return found


def surety(text: str, facts: list) -> dict:
    """{score, band, hi, reasons} — how much of this line came from our facts.

    Deliberately NOT a truth score. It cannot tell you the sentence is right;
    it tells you how much of it we can account for, which is the part a person
    about to press send can actually act on. A high score on a line that still
    reads oddly means the oddness is in the arrangement, not in the material —
    and that is worth knowing too."""
    fact_text = " ".join(f.get("text", "") for f in (facts or []))
    reasons = []

    # 1. कितना हमारा — content-word overlap. The largest share, because an
    #    ungrounded sentence is one the model wrote out of its own beliefs
    #    about mandi rates, and those are not a source.
    words = _content(text)
    bag = set(_content(fact_text))
    if not words:
        return {"score": 0, "band": "thin", "hi": _BANDS["thin"],
                "reasons": ["इसमें कुछ है ही नहीं"]}
    hits = [w for w in words if _grounded(w, bag)]
    share = len(hits) / len(words)
    # Full marks at 0.8, nothing at 0.35: a real rewording still brings its own
    # verbs and connectives, and demanding 100% would be demanding the fact
    # back verbatim.
    ground = _W_GROUND * max(0.0, min(1.0, (share - 0.35) / 0.45))
    if share < 0.55:
        stray = [w for w in words if w not in hits][:3]
        reasons.append("इस लाइन का बड़ा हिस्सा हमारी बातों में नहीं है"
                       + (f" — जैसे: {', '.join(stray)}" if stray else ""))

    # 2. आंकड़े का लेबल — every figure kept the word that says what it is.
    nums = _numbers(text)
    if not nums:
        figure = _W_FIGURE            # nothing to mislabel
    else:
        kept = 0
        for n in nums:
            want = _quals_at(fact_text, n)
            got = _quals_at(text, n)
            if not want or (want & got):
                kept += 1
            else:
                reasons.append(
                    f"₹{n} पर से '{'/'.join(sorted(want))}' हट गया है — "
                    f"अब यह भाव जैसा पढ़ा जाएगा")
        figure = _W_FIGURE * (kept / len(nums))

    # 3. लहजा — the wordings a broadcast must not carry. Same lists the news
    #    generator screens on; imported rather than restated, for the reason
    #    given at _numbers().
    tone, bad = _W_TONE, []
    try:
        from backend.services.news_auto_service import (
            _ALLEGATION_WORDS, _DOSAGE_RE, _GUARANTEE_WORDS, _POLITICAL_WORDS)
        if any(w in text for w in _GUARANTEE_WORDS):
            bad.append("लाभ की गारंटी जैसी बात")
        if any(w in text for w in _ALLEGATION_WORDS):
            bad.append("किसी पर आरोप")
        if any(w in text for w in _POLITICAL_WORDS):
            bad.append("राजनीतिक दल का ज़िक्र")
        if _DOSAGE_RE.search(text):
            bad.append("दवा या रसायन की मात्रा")
    except Exception:                                    # noqa: BLE001
        pass
    if bad:
        tone = 0
        reasons.append("इसमें " + ", ".join(bad) + " है")

    score = int(round(ground + figure + tone))
    # A promise of profit or a party's name is not a proportional fault that a
    # well-grounded sentence can outweigh — it is a line that must not go out,
    # and a well-written one is worse than a clumsy one. So it caps the meter
    # into the bottom band rather than costing it twenty points. check() blocks
    # it as well; this is what the owner SEES when it does.
    if bad:
        score = min(score, 45)
    key = ("sure" if score >= 85 else "ok" if score >= 70
           else "read" if score >= 50 else "thin")
    return {"score": score, "band": key, "hi": _BANDS[key], "reasons": reasons}


# What the number means, in one phrase, to the person deciding whether to send.
# Parallel to wa_post.band() and deliberately worded differently: that one is
# about whether a price is right, this one about whose words these are.
_BANDS = {
    "sure": "हमारी ही बात",
    "ok":   "ठीक है",
    "read": "पढ़कर भेजिए",
    "thin": "अपनी बात जोड़ी है",
}


def check(text: str, known: set) -> list:
    """Why this line must not go out as written. Empty list = clean."""
    flags = []
    t = (text or "").strip()
    if not t:
        return ["खाली है"]
    if len(t) > _MAX_LEN:
        flags.append(f"बहुत लंबी है — {len(t)} अक्षर, {_MAX_LEN} तक ही चलेगी")
    if _LINK_RE.search(t):
        flags.append("इसमें लिंक है — पोस्ट में सिर्फ़ एक लिंक जाता है, /bhav का")
    if _CONTACT_RE.search(t):
        flags.append("इसमें फ़ोन नंबर या ईमेल है")
    invented = _numbers(t) - set(known or ())
    if invented:
        flags.append("इसमें ऐसे आंकड़े हैं जो हमारे पास नहीं हैं: "
                     + ", ".join(sorted(invented)[:4]))

    # The wordings the news generator refuses to auto-publish, refused here for
    # the same reasons — a broadcast to a state's farmers is a worse place for
    # a profit guarantee than an article is, not a better one. Imported rather
    # than restated; see the note at _numbers().
    try:
        from backend.services.news_auto_service import (
            _ALLEGATION_WORDS, _DOSAGE_RE, _GUARANTEE_WORDS, _POLITICAL_WORDS)
        if any(w in t for w in _GUARANTEE_WORDS):
            flags.append("इसमें लाभ की गारंटी जैसा दावा है")
        if any(w in t for w in _ALLEGATION_WORDS):
            flags.append("इसमें किसी पर आरोप है")
        if any(w in t for w in _POLITICAL_WORDS):
            flags.append("इसमें राजनीतिक दल का ज़िक्र है")
        if _DOSAGE_RE.search(t):
            flags.append("इसमें दवा या रसायन की मात्रा बताई गई है")
    except Exception:                                    # noqa: BLE001
        pass
    return flags


# ── asking the model ─────────────────────────────────────────

_LANG_NAME = {"hi": "Hindi (Devanagari)", "mr": "Marathi (Devanagari)",
              "ta": "Tamil script", "kn": "Kannada script",
              "te": "Telugu script", "gu": "Gujarati script",
              "bn": "Bengali script", "pa": "Gurmukhi script"}


def _prompt(post: dict, fs: list) -> str:
    """What the model is allowed to work from — and nothing else.

    It is given the facts and told to REPHRASE them. It is not given the
    internet, a search tool, or permission to add anything of its own, because
    a broadcast to a state's farmers is the wrong place to find out what a
    language model believes about mandi rates."""
    lang = post.get("lang") or state_lang.HINDI
    script = _LANG_NAME.get(lang, "Hindi (Devanagari)")
    facts_txt = "\n".join(f"- {f['text']}" for f in fs) or "- (none)"
    return f"""You are helping write ONE extra line for a WhatsApp broadcast to farmers in {post.get('state', '')}, India. The message already lists today's mandi prices. Your line goes underneath them.

The ONLY facts you may use:
{facts_txt}

Hard rules:
- Write in {script}.
- Rephrase or combine the facts above. Do NOT add any fact, figure, crop, place or claim that is not in that list.
- Never invent or adjust a number. If a number is not in the facts above, it must not appear.
- No links, no URLs, no website names, no phone numbers, no email.
- No advice on pesticide or fertiliser doses. No guarantee of profit. No political mention.
- One line, at most {_MAX_LEN} characters, plain text. An emoji at the start is fine.

Give exactly {_MAX_SUGGESTIONS} different options, one per line, nothing else — no numbering, no quotes, no explanation."""


async def suggest(post: dict) -> dict:
    """{facts, suggestions, error} — the menu for one state's extra line.

    `facts` always comes back and always comes first: those lines are built
    from our own data by the code above and need no model, no key and no
    network. `suggestions` is the model's rewording of them, each carrying its
    own flags — and an empty list there is a normal morning, not a failure.

    Never raises. A panel button that can 500 is a panel button that gets
    pressed once and never again."""
    fs = facts(post)
    known = set().union(*[f["numbers"] for f in fs]) if fs else set()
    # The पक्की lines carry the meter too, and score 100 by construction — they
    # ARE the facts. That is the point: a scale whose top is only ever
    # theoretical teaches nobody what a good number looks like, and the owner
    # can see what 100 reads like sitting directly above what 72 reads like.
    out = {"facts": [{**f, "surety": surety(f["text"], fs)} for f in fs],
           "suggestions": [], "error": ""}

    if not fs:
        out["error"] = ("आज इस राज्य के लिए भाव के अलावा कोई पक्की बात नहीं है — "
                        "MSP का मौसम नहीं चल रहा और कोई खबर छपी नहीं है।")
        return out

    try:
        from backend.services.chatbot_service import call_gemini
        raw = await call_gemini(_prompt(post, fs), max_tokens=400)
    except Exception as e:                               # noqa: BLE001
        log.info("[wa_extra] model unavailable: %s", e)
        out["error"] = f"AI से सुझाव नहीं आ पाए — ऊपर वाली पक्की लाइनें अब भी चलेंगी। ({e})"
        return out

    seen = set()
    for raw_line in (raw or "").splitlines():
        line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", raw_line).strip().strip('"“”')
        if not line or line in seen:
            continue
        seen.add(line)
        flags = check(line, known)
        out["suggestions"].append({"text": line, "flags": flags, "ok": not flags,
                                   "surety": surety(line, fs)})
        if len(out["suggestions"]) >= _MAX_SUGGESTIONS:
            break

    # Ordered by the meter, best first. The owner reads top-down and stops at
    # the first line he likes, so the order is a recommendation whether or not
    # it was meant as one — better that it be the honest one.
    out["suggestions"].sort(key=lambda s: (-s["surety"]["score"], bool(s["flags"])))
    return out


if __name__ == "__main__":  # pragma: no cover
    import asyncio
    import sys

    from backend.services import wa_post

    st = " ".join(a for a in sys.argv[1:] if not a.startswith("--")) or "Uttar Pradesh"
    p = wa_post.post_for(st)
    if not p:
        print("no post for that state")
        raise SystemExit(1)
    r = asyncio.run(suggest(p))
    print(f"-- {p['hi_state']} · {p['lang']}")
    for f in r["facts"]:
        print(f"  [{f['kind']}] {f['text']}")
    if r["error"]:
        print("  ! " + r["error"])
    for s in r["suggestions"]:
        print(f"  {'OK ' if s['ok'] else '!! '}{s['text']}")
        for fl in s["flags"]:
            print("       - " + fl)
