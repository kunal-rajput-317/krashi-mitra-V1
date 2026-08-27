# ============================================================
# services/free_month.py
# "पहला महीना मुफ़्त" — the acquisition offer for कृषि दुकान and किराये की मशीनें
#
# WHY THIS IS ONE MODULE AND NOT TWO. The two directories keep their tables,
# their services and their admin panels deliberately separate (see the headers
# of krashi_dukan.py and rental.py) — a fertiliser shop must never surface on a
# tractor-hire page just because both are "listings". The OFFER is the one
# thing that must not diverge: the same promise, in the same words, for the
# same number of months, on both sections. A shopkeeper told "पहला महीना
# मुफ़्त" and a tractor owner told the same must get the same deal, and the
# term the admin panel grants must be the term the public page advertised.
# So the promise, its copy, its CTA and the rule that honours it live here and
# both sides call in. Nothing about either business leaks through: this module
# imports neither service and knows no model — it takes a row and reads four
# columns that both tables happen to share.
#
# WHAT THE OFFER ACTUALLY IS. One month of a full listing, granted by an admin,
# costing nothing and asking for nothing up front. At the end of it the listing
# goes dark exactly the way a lapsed paid one does — no sweep, no cron: the
# `paid_until` date is consulted by is_live on every render, so the month ends
# itself. That expiry IS the product. It turns a directory entry into a phone
# call with a reason ("आपकी दुकान का मुफ़्त महीना कल खत्म हो रहा है"), which is
# the only thing that has ever converted a free listing into money.
#
# A FREE MONTH IS NOT A PAYMENT AND MUST NEVER LOOK LIKE ONE. `paid_at` is set
# by exactly one thing in this codebase — a human who saw the credit in the
# bank app — because an auto-ticked "paid" is a fabricated receipt. So granting
# a free month moves `paid_until` and leaves `paid_at`, `paid_amount` and
# `payment_ref` alone. That asymmetry is also what identifies the state later:
#
#     paid_until NULL                 →  never started — the onboarding grace
#     paid_until set + paid_at NULL   →  on (or just off the end of) a free month
#     paid_until set + paid_at set    →  a paying listing
#
# No new column, and nothing else in either service writes `paid_until` — only
# record_payment does — so the derivation cannot drift.
#
# ONCE PER LISTING. The grant is refused to anyone whose clock has ever
# started, paid or free. "पहला महीना" said twice is not an offer, it is free
# hosting — and re-granting would also throw away the expiry that the renewal
# call depends on.
#
# THE FREE MONTH BUYS NOTHING EXTRA. Same card, same items, same position: a
# free listing and a paid one are indistinguishable to a farmer, because order
# is by distance and by nothing else, and that ordering is the only thing this
# site actually has to sell.
# ============================================================

import math
from datetime import datetime, timedelta
from html import escape
from urllib.parse import quote

# How long the offer runs, in months. Read by the public card, by the grant
# below and by both admin panels — change it here and the promise, the button
# and the expiry date move together, which is the whole point of this file.
FREE_MONTHS = 1

# Days in a "month" here, matching record_payment's own arithmetic so that a
# free month and a paid one are the same length of time.
_DAYS_PER_MONTH = 30

HELPLINE = "919870951001"        # the official number, never the owner's personal one
HELPLINE_HI = "+91 98709 51001"


# ── the rule ────────────────────────────────────────────────

def may_grant(row) -> bool:
    """Whether this listing can still take its free month.

    Only a row whose clock has never started. One that already had the free
    month gets a different answer to "और एक महीना?" and it is the paid one; one
    that has paid is past the offer entirely, and re-granting would overwrite a
    date that real money bought.
    """
    return bool(row) and row.paid_at is None and row.paid_until is None


def on_free_month(row) -> bool:
    """On a free month, or on the far side of one that has run out.

    True from the moment it is granted until the day the listing pays — a
    lapsed free month is still a free month, and the panel must say so rather
    than reporting a *renewal* on a listing that never paid anything.
    """
    return bool(row) and row.paid_at is None and row.paid_until is not None


def days_left(row) -> int | None:
    """Whole days of the free month left, negative once it has run out.

    Floored, for krashi_dukan.days_left's reason: the number must never promise
    time that is not there. None when no free month is running.
    """
    if not on_free_month(row):
        return None
    return math.floor((row.paid_until - datetime.utcnow()).total_seconds() / 86400)


def grant(db, row, months: int = FREE_MONTHS):
    """Start the free month. None when the row is not eligible.

    Lists the shop in the same motion, for record_payment's reason: an admin
    who has just decided to give someone a month has already made the trust
    decision, and making them tick `active` separately only creates a listing
    that was granted and never appeared.

    `paid_at` / `paid_amount` / `payment_ref` are deliberately untouched — see
    the module header. `status` says "trial" so the panel and the call sheet can
    tell a gifted month from a sold one at a glance.
    """
    if not may_grant(row):
        return None
    now = datetime.utcnow()
    row.paid_until = now + timedelta(days=_DAYS_PER_MONTH * max(1, int(months)))
    row.status     = "trial"
    row.active     = True
    row.updated_at = now
    db.commit()
    db.refresh(row)
    return row


# ── the promise, in three languages, once ───────────────────
#
# WHY THREE. The offer is the supply side's only entry point: a shopkeeper or
# a machine owner who cannot read this card cannot list. Hindi covers the
# north, but कृषि दुकान and /rental rank by distance and take listings from any
# district — and the two southern states the site is expanding into do not read
# Devanagari. A Coimbatore shop owner staring at "मुफ़्त में दुकान लिस्ट कराएँ"
# is a lost listing, not a reluctant one.
#
# WHY IT IS A TOGGLE AND NOT A ?lang= URL. Translated URL variants were
# measured and rejected: ?lang=kn earned 0 impressions in 28 days, and
# multiplying URLs is exactly the index bloat this site is mid-way through
# pruning. All three languages live at the SAME URL — nothing new for Google to
# index, nothing to canonicalise away. Hindi is what a crawler and a JS-off
# reader see, so the indexed text of the page does not change at all.
#
# THE PROMISE ITSELF DOES NOT DIVERGE. FREE_MONTHS, the terms and the ordering
# rule stay one source; only their wording changes. The month a Tamil owner is
# promised is the month the admin panel grants, in the same words.

LANGS = ("hi", "ta", "kn")

# What each language calls itself, for the switch. Never "Hindi/Tamil/Kannada"
# in English — the person who needs the switch is the one who cannot read the
# card, so the label has to be legible in its own script.
LANG_LABEL = {"hi": "हिंदी", "ta": "தமிழ்", "kn": "ಕನ್ನಡ"}

_MONTHS_WORD = {
    "hi": ("1 महीना", "{n} महीने"),
    "ta": ("1 மாதம்", "{n} மாதங்கள்"),
    "kn": ("1 ತಿಂಗಳು", "{n} ತಿಂಗಳುಗಳು"),
}


def months_in(lang: str = "hi", months: int = FREE_MONTHS) -> str:
    one, many = _MONTHS_WORD.get(lang) or _MONTHS_WORD["hi"]
    return one if months == 1 else many.format(n=months)


def months_hi(months: int = FREE_MONTHS) -> str:
    """The Hindi form, kept under its own name: both admin panels, both
    services and both public routes call it directly."""
    return months_in("hi", months)


# What the offer includes, in the shopkeeper's terms rather than ours. Three
# lines on purpose: this renders on a 390px phone under a grid of cards, and
# the person reading it is standing behind a counter, not reading a terms page.
#
# The third line is load-bearing: it is the promise that money cannot buy
# position, and it is asserted by the tests. It has to say the same thing in
# every language, or the offer would be making three different promises.
TERMS = {
    "hi": (
        "कोई एडवांस नहीं, कोई कागज़ी काम नहीं",
        "महीना पूरा होने पर आगे बढ़ाना है या नहीं — पूरी तरह आपकी मर्ज़ी",
        "मुफ़्त और पैसे वाली लिस्टिंग में कोई फ़र्क़ नहीं — क्रम हमेशा दूरी से लगता है",
    ),
    "ta": (
        "முன்பணம் இல்லை, காகித வேலை இல்லை",
        "மாதம் முடிந்ததும் தொடர்வதா இல்லையா — முழுக்க உங்கள் விருப்பம்",
        "இலவசப் பட்டியலுக்கும் கட்டணப் பட்டியலுக்கும் வித்தியாசமே இல்லை — வரிசை எப்போதும் தூரத்தால் மட்டுமே",
    ),
    "kn": (
        "ಮುಂಗಡ ಇಲ್ಲ, ಕಾಗದದ ಕೆಲಸ ಇಲ್ಲ",
        "ತಿಂಗಳು ಮುಗಿದ ಮೇಲೆ ಮುಂದುವರಿಸುವುದೋ ಬೇಡವೋ — ಸಂಪೂರ್ಣ ನಿಮ್ಮ ಇಷ್ಟ",
        "ಉಚಿತ ಮತ್ತು ಪಾವತಿಸಿದ ಪಟ್ಟಿಯ ನಡುವೆ ಯಾವ ವ್ಯತ್ಯಾಸವೂ ಇಲ್ಲ — ಕ್ರಮ ಯಾವಾಗಲೂ ದೂರದಿಂದಲೇ",
    ),
}

# Kept under its old name: imported elsewhere and asserted by name in tests.
TERMS_HI = TERMS["hi"]

# The chrome around the pitch — everything on the card that is not the pitch
# itself, kept per language so a card can never end up half-translated.
_CHROME = {
    "hi": {"tag": "🎁 पहला {m} बिल्कुल मुफ़्त", "tick": "✓ सत्यापित",
           "call_btn": "📞 फ़ोन करें", "cap": "↑ आपकी लिस्टिंग ऐसी दिखेगी",
           "cap_b": "पहला {m} ₹0",
           "reach": "व्हाट्सऐप पर मैसेज करें या कॉल करें —",
           "wa_tail": "पहला {m} मुफ़्त वाला ऑफ़र चाहिए।"},
    "ta": {"tag": "🎁 முதல் {m} முற்றிலும் இலவசம்", "tick": "✓ சரிபார்க்கப்பட்டது",
           "call_btn": "📞 அழையுங்கள்", "cap": "↑ உங்கள் பட்டியல் இப்படித் தெரியும்",
           "cap_b": "முதல் {m} ₹0",
           "reach": "WhatsApp-இல் செய்தி அனுப்புங்கள் அல்லது அழையுங்கள் —",
           "wa_tail": "முதல் {m} இலவசச் சலுகை வேண்டும்."},
    "kn": {"tag": "🎁 ಮೊದಲ {m} ಸಂಪೂರ್ಣ ಉಚಿತ", "tick": "✓ ಪರಿಶೀಲಿಸಲಾಗಿದೆ",
           "call_btn": "📞 ಫೋನ್ ಮಾಡಿ", "cap": "↑ ನಿಮ್ಮ ಪಟ್ಟಿ ಹೀಗೆ ಕಾಣುತ್ತದೆ",
           "cap_b": "ಮೊದಲ {m} ₹0",
           "reach": "WhatsApp ನಲ್ಲಿ ಸಂದೇಶ ಕಳುಹಿಸಿ ಅಥವಾ ಕರೆ ಮಾಡಿ —",
           "wa_tail": "ಮೊದಲ {m} ಉಚಿತ ಕೊಡುಗೆ ಬೇಕು."},
}

# The pitch, per section per language. `head`/`sub` are what the reader sees;
# `wa` is what they will end up sending us.
_PITCH = {
    "dukan": {
        "icon": "🏪", "prev_ic": "🏪", "prev_amt": "₹266",
        "hi": {
            "head": "अपनी दुकान का सामान यहाँ दिखाएँ",
            "sub":  ("आपके ज़िले के किसान रोज़ यहाँ भाव देखते हैं। अपनी दुकान का सामान और "
                     "अपना काउंटर रेट डालिए — किसान सीधे आपकी दुकान तक पहुँचेगा।"),
            "wa":   "नमस्ते, मेरी कृषि दुकान है और मैं उसे कृषि मित्र पर लिस्ट कराना चाहता हूँ।",
            "cta":  "मुफ़्त में दुकान लिस्ट कराएँ",
            "prev": {"who": "आपकी दुकान का नाम", "where": "आपका ज़िला · 3 km",
                     "what": "यूरिया 45 kg बैग", "unit": "आपका काउंटर रेट"},
        },
        "ta": {
            "head": "உங்கள் கடையின் பொருட்களை இங்கே காட்டுங்கள்",
            "sub":  ("உங்கள் மாவட்ட விவசாயிகள் தினமும் இங்கே விலை பார்க்கிறார்கள். உங்கள் "
                     "கடையின் பொருளையும் கவுண்டர் விலையையும் இடுங்கள் — விவசாயி நேராக "
                     "உங்கள் கடைக்கே வருவார்."),
            "wa":   ("வணக்கம், என்னிடம் வேளாண் இடுபொருள் கடை உள்ளது; அதை கிருஷி மித்ரா-வில் "
                     "பட்டியலிட விரும்புகிறேன்."),
            "cta":  "இலவசமாகக் கடையைப் பட்டியலிடுங்கள்",
            "prev": {"who": "உங்கள் கடையின் பெயர்", "where": "உங்கள் மாவட்டம் · 3 km",
                     "what": "யூரியா 45 kg மூட்டை", "unit": "உங்கள் கவுண்டர் விலை"},
        },
        "kn": {
            "head": "ನಿಮ್ಮ ಅಂಗಡಿಯ ಸಾಮಾನನ್ನು ಇಲ್ಲಿ ತೋರಿಸಿ",
            "sub":  ("ನಿಮ್ಮ ಜಿಲ್ಲೆಯ ರೈತರು ಪ್ರತಿದಿನ ಇಲ್ಲಿ ದರ ನೋಡುತ್ತಾರೆ. ನಿಮ್ಮ ಅಂಗಡಿಯ ಸಾಮಾನು "
                     "ಮತ್ತು ನಿಮ್ಮ ಕೌಂಟರ್ ದರವನ್ನು ಹಾಕಿ — ರೈತ ನೇರವಾಗಿ ನಿಮ್ಮ ಅಂಗಡಿಗೇ ಬರುತ್ತಾನೆ."),
            "wa":   ("ನಮಸ್ಕಾರ, ನನಗೆ ಕೃಷಿ ಪರಿಕರಗಳ ಅಂಗಡಿ ಇದೆ; ಅದನ್ನು ಕೃಷಿ ಮಿತ್ರದಲ್ಲಿ ಪಟ್ಟಿ "
                     "ಮಾಡಿಸಲು ಬಯಸುತ್ತೇನೆ."),
            "cta":  "ಉಚಿತವಾಗಿ ಅಂಗಡಿ ಪಟ್ಟಿ ಮಾಡಿಸಿ",
            "prev": {"who": "ನಿಮ್ಮ ಅಂಗಡಿಯ ಹೆಸರು", "where": "ನಿಮ್ಮ ಜಿಲ್ಲೆ · 3 km",
                     "what": "ಯೂರಿಯಾ 45 kg ಚೀಲ", "unit": "ನಿಮ್ಮ ಕೌಂಟರ್ ದರ"},
        },
    },
    "rental": {
        "icon": "⚙️", "prev_ic": "🚜", "prev_amt": "₹1,100",
        "hi": {
            "head": "अपनी मशीन किराये पर देकर कमाएँ",
            "sub":  ("ट्रैक्टर, रोटावेटर, पंप सेट, हार्वेस्टर — जो मशीन खाली खड़ी है उसका "
                     "किराया यहाँ डालिए। आपके इलाके का किसान सीधे आपको फ़ोन करेगा।"),
            "wa":   "नमस्ते, मेरे पास खेती की मशीन है और मैं उसे कृषि मित्र पर किराये के लिए लिस्ट कराना चाहता हूँ।",
            "cta":  "मुफ़्त में मशीन लिस्ट कराएँ",
            "prev": {"who": "आपका नाम", "where": "आपका गाँव · 6 km",
                     "what": "ट्रैक्टर + रोटावेटर", "unit": "प्रति एकड़"},
        },
        "ta": {
            "head": "உங்கள் இயந்திரத்தை வாடகைக்குக் கொடுத்து சம்பாதியுங்கள்",
            "sub":  ("டிராக்டர், ரோட்டவேட்டர், பம்ப் செட், அறுவடை இயந்திரம் — காலியாக நிற்கும் "
                     "இயந்திரத்தின் வாடகையை இங்கே இடுங்கள். உங்கள் பகுதி விவசாயி நேராக "
                     "உங்களுக்கே தொலைபேசுவார்."),
            "wa":   ("வணக்கம், என்னிடம் வேளாண் இயந்திரம் உள்ளது; அதை கிருஷி மித்ரா-வில் "
                     "வாடகைக்குப் பட்டியலிட விரும்புகிறேன்."),
            "cta":  "இலவசமாக இயந்திரத்தைப் பட்டியலிடுங்கள்",
            "prev": {"who": "உங்கள் பெயர்", "where": "உங்கள் ஊர் · 6 km",
                     "what": "டிராக்டர் + ரோட்டவேட்டர்", "unit": "ஏக்கருக்கு"},
        },
        "kn": {
            "head": "ನಿಮ್ಮ ಯಂತ್ರವನ್ನು ಬಾಡಿಗೆಗೆ ಕೊಟ್ಟು ಗಳಿಸಿ",
            "sub":  ("ಟ್ರ್ಯಾಕ್ಟರ್, ರೋಟವೇಟರ್, ಪಂಪ್ ಸೆಟ್, ಹಾರ್ವೆಸ್ಟರ್ — ಖಾಲಿ ನಿಂತಿರುವ ಯಂತ್ರದ "
                     "ಬಾಡಿಗೆಯನ್ನು ಇಲ್ಲಿ ಹಾಕಿ. ನಿಮ್ಮ ಪ್ರದೇಶದ ರೈತ ನೇರವಾಗಿ ನಿಮಗೇ ಫೋನ್ ಮಾಡುತ್ತಾನೆ."),
            "wa":   ("ನಮಸ್ಕಾರ, ನನ್ನ ಬಳಿ ಕೃಷಿ ಯಂತ್ರ ಇದೆ; ಅದನ್ನು ಕೃಷಿ ಮಿತ್ರದಲ್ಲಿ ಬಾಡಿಗೆಗೆ ಪಟ್ಟಿ "
                     "ಮಾಡಿಸಲು ಬಯಸುತ್ತೇನೆ."),
            "cta":  "ಉಚಿತವಾಗಿ ಯಂತ್ರ ಪಟ್ಟಿ ಮಾಡಿಸಿ",
            "prev": {"who": "ನಿಮ್ಮ ಹೆಸರು", "where": "ನಿಮ್ಮ ಊರು · 6 km",
                     "what": "ಟ್ರ್ಯಾಕ್ಟರ್ + ರೋಟವೇಟರ್", "unit": "ಎಕರೆಗೆ"},
        },
    },
}


def _pitch(kind: str, lang: str) -> dict:
    sec = _PITCH.get(kind) or _PITCH["dukan"]
    return sec.get(lang) or sec["hi"]


def wa_url(kind: str, what: str = "", lang: str = "hi") -> str:
    """The WhatsApp deep link, with the message already typed.

    The CTA is a chat, not a form: the people who own a shop or a tractor worth
    listing are reached on WhatsApp, and a sign-up flow is a thing they abandon
    halfway. `what` names the product or machine whose page this is, so the
    message that arrives tells us where it came from — and the language it
    arrives in tells us which language to answer in.
    """
    msg = _pitch(kind, lang)["wa"]
    if what:
        msg = f"{msg} ({what})"
    tail = (_CHROME.get(lang) or _CHROME["hi"])["wa_tail"].format(m=months_in(lang))
    return f"https://wa.me/{HELPLINE}?text={quote(f'{msg} {tail}')}"


CSS = """
/* ── "पहला महीना मुफ़्त" — the supply-side offer, shared by कृषि दुकान and /rental ── */
.km-offer{margin:22px 0 0;padding:16px 18px;border-radius:16px;
background:linear-gradient(135deg,#f4fbf6 0%,#fff8e6 100%);
border:1px solid #cfe8d8;box-shadow:var(--shadow-sm)}
.km-offer-tag{display:inline-flex;align-items:center;gap:6px;background:#1b7a45;color:#fff;
font-size:11px;font-weight:800;letter-spacing:.2px;padding:4px 11px;border-radius:12px}
.km-offer-head{display:flex;gap:13px;align-items:flex-start;margin-top:11px}
.km-offer-ic{flex:0 0 auto;width:42px;height:42px;border-radius:50%;background:#fff;
border:1px solid #cfe8d8;display:flex;align-items:center;justify-content:center;font-size:21px}
.km-offer-t{flex:1 1 auto;min-width:0}
.km-offer-t b{display:block;font-size:15.5px;font-weight:800;color:var(--green-dark);line-height:1.3}
.km-offer-t span{display:block;font-size:12.5px;color:var(--text-mid);line-height:1.55;margin-top:4px}
.km-offer-terms{list-style:none;margin:12px 0 0;padding:0;display:flex;flex-direction:column;gap:5px}
.km-offer-terms li{position:relative;padding-left:19px;font-size:11.5px;color:#3d6b52;line-height:1.5}
.km-offer-terms li::before{content:"✓";position:absolute;left:0;top:0;font-weight:800;color:var(--green-light)}
.km-offer-go{display:inline-flex;align-items:center;justify-content:center;gap:7px;margin-top:14px;
background:var(--green-mid);color:#fff;text-decoration:none;font-size:14px;font-weight:800;
padding:11px 20px;border-radius:12px}
.km-offer-go:hover{background:var(--green-dark)}
.km-offer-call{display:block;font-size:11.5px;color:var(--text-soft);margin-top:9px}
.km-offer-call a{color:var(--green-dark);font-weight:700;text-decoration:none}

/* ── the language switch ──
   The supply side is not Hindi-only. कृषि दुकान and /rental order by distance
   and take listings from any district, and the two southern states the site is
   growing into do not read Devanagari — a shop owner who cannot read the pitch
   is a lost listing, not a reluctant one.

   This is a TOGGLE, not a ?lang= URL: translated URLs were measured at 0
   impressions and would multiply an index the site is trying to prune. All
   three languages sit at the same URL, Hindi is the one served, and the choice
   is remembered on the phone that made it. */
.km-offer-langs{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 2px;justify-content:flex-end}
.km-offer-lang{background:#fff;border:1px solid #cfe8d8;color:#3d6b52;font-family:inherit;
font-size:11.5px;font-weight:700;line-height:1;padding:6px 11px;border-radius:9px;cursor:pointer}
.km-offer-lang[aria-pressed="true"]{background:var(--green-mid);border-color:var(--green-mid);color:#fff}
.km-offer [data-km-l]{display:none}
.km-offer [data-km-l="hi"]{display:block}
.km-offer .km-offer-l-tag[data-km-l="hi"]{display:inline-flex}

/* ── the listing preview ──
   The card's copy column has a natural reading width, so on a wide screen the
   right half of the card was simply empty. What fills it is the one question a
   shopkeeper actually has — "मुझे मिलेगा क्या?" — answered by showing him his
   own listing rather than describing it. Same device as _dukan_pitch's demo
   card on /bhav, and for the same reason: a mock-up is believed, a sentence is
   not.

   THE FIELDS SAY "आपका", NOT A MADE-UP NAME. A preview with an invented
   shopkeeper in it reads as someone else's listing; "आपकी दुकान का नाम" reads
   as the empty slot he is being offered, which is the whole pitch. It also
   keeps us from printing a person who does not exist.

   Unlike the ₹0 block this replaced, it earns its place on a phone too — so it
   floats beside the copy at 390px instead of being hidden, and only becomes a
   column of its own once there is room. */
.km-offer-body{display:flow-root}
.km-offer-main{min-width:0}
/* the CTA clears the float so a full-width button on a phone can never
   run under the mock-up beside it */
.km-offer-go{clear:both}
.km-offer-prev{float:right;width:132px;margin:0 0 10px 13px}
.km-offer-card{background:#fff;border:1px solid #cfe8d8;border-radius:12px;
padding:11px 12px;box-shadow:var(--shadow-sm)}
.km-offer-prev-top{display:flex;align-items:center;justify-content:space-between;gap:6px}
.km-offer-prev-ic{width:26px;height:26px;border-radius:50%;background:#eef8f1;
display:flex;align-items:center;justify-content:center;font-size:14px}
.km-offer-prev-tick{font-size:9px;font-weight:800;color:#1b7a45;background:#e7f6ed;
padding:2px 6px;border-radius:8px;white-space:nowrap}
.km-offer-prev-who{font-size:12px;font-weight:800;color:var(--text-dark);
line-height:1.3;margin-top:8px}
.km-offer-prev-where{display:block;font-size:9.5px;color:var(--text-soft);margin-top:2px}
.km-offer-prev-what{font-size:10.5px;color:var(--text-mid);line-height:1.4;margin-top:7px;
padding-top:7px;border-top:1px dashed #dfeee5}
.km-offer-prev-amt{font-size:17px;font-weight:800;color:var(--green-dark);
line-height:1.1;margin-top:5px}
.km-offer-prev-unit{font-size:9.5px;color:var(--text-soft);display:block;margin-top:1px}
.km-offer-prev-btn{display:block;text-align:center;background:var(--green-pale);
color:var(--green-dark);font-size:10px;font-weight:800;padding:5px 0;
border-radius:7px;margin-top:9px}
.km-offer-prev-cap{font-size:9.5px;color:#6d8a78;line-height:1.4;margin:6px 0 0;text-align:center}
.km-offer-prev-cap b{display:block;color:var(--green-dark);font-size:10.5px;margin-top:2px}
@media(min-width:721px){
.km-offer-body{display:flow-root}
.km-offer [data-km-l="hi"].km-offer-body{display:flex;gap:22px;align-items:flex-start}
.km-offer-main{flex:1 1 auto}
.km-offer-prev{float:none;flex:0 0 176px;width:176px;margin:0;order:2}
.km-offer-card{padding:13px 14px}
.km-offer-prev-who{font-size:13px}
.km-offer-prev-amt{font-size:19px}
.km-offer-prev-cap{font-size:10.5px}
}

@media(max-width:560px){
.km-offer{padding:14px 14px}
.km-offer-head{gap:10px}
.km-offer-ic{width:38px;height:38px;font-size:19px}
.km-offer-t b{font-size:14.5px}
.km-offer-go{display:flex;width:100%;padding:12px 16px}
.km-offer-langs{justify-content:flex-start}
}
"""

# One script per page, not per card: a product page renders the offer once but
# the hub renders it under a grid of cards, and two copies of the same listener
# would double-fire. Guarded on window for that reason.
#
# The desktop two-column layout is a flex rule that only matches the visible
# body, so switching language has to reapply it — hence the explicit
# display value rather than a class toggle.
JS = """
<script>
(function(){
if(window.__kmOfferLang)return;window.__kmOfferLang=1;
var KEY='km_offer_lang',WIDE=window.matchMedia('(min-width:721px)');
function show(n,on){
  if(!on){n.style.display='none';return;}
  n.style.display=n.classList.contains('km-offer-l-tag')?'inline-flex':
    (n.classList.contains('km-offer-body')&&WIDE.matches?'flex':'block');
}
function apply(l){
  document.querySelectorAll('.km-offer').forEach(function(o){
    o.querySelectorAll('[data-km-l]').forEach(function(n){
      show(n,n.getAttribute('data-km-l')===l);
    });
    o.querySelectorAll('.km-offer-lang').forEach(function(b){
      b.setAttribute('aria-pressed',String(b.getAttribute('data-km-set')===l));
    });
  });
}
function current(){
  var v=null;try{v=localStorage.getItem(KEY);}catch(e){}
  return (v==='ta'||v==='kn')?v:'hi';
}
document.addEventListener('click',function(e){
  var b=e.target&&e.target.closest?e.target.closest('.km-offer-lang'):null;
  if(!b)return;
  var l=b.getAttribute('data-km-set');
  try{localStorage.setItem(KEY,l);}catch(e){}
  apply(l);
});
if(WIDE.addEventListener)WIDE.addEventListener('change',function(){apply(current());});
if(current()!=='hi')apply(current());
})();
</script>
"""


def _preview(kind: str, lang: str) -> str:
    """The listing the reader is being offered, drawn as it will actually look.

    NO STRUCK-THROUGH "REGULAR PRICE" ANYWHERE IN THIS CARD. There is no
    published listing price to strike through, and inventing one to make ₹0
    look like a saving would be a fabricated anchor on a page whose whole pitch
    is that we do not play those games. The offer is stated as what it is, in
    the caption under the mock-up.

    The ✓ tick is drawn because a listing genuinely carries one — it is set by
    hand after we have spoken to the owner, the same promise buyers.json makes.
    """
    sec = _PITCH.get(kind) or _PITCH["dukan"]
    pv  = _pitch(kind, lang).get("prev") or {}
    ch  = _CHROME.get(lang) or _CHROME["hi"]
    return f"""<div class="km-offer-prev">
<div class="km-offer-card">
<div class="km-offer-prev-top">
<div class="km-offer-prev-ic">{sec.get('prev_ic', '🏪')}</div>
<span class="km-offer-prev-tick">{escape(ch['tick'])}</span>
</div>
<div class="km-offer-prev-who">{escape(pv.get('who', ''))}
<span class="km-offer-prev-where">{escape(pv.get('where', ''))}</span></div>
<div class="km-offer-prev-what">{escape(pv.get('what', ''))}</div>
<div class="km-offer-prev-amt">{escape(sec.get('prev_amt', ''))}
<span class="km-offer-prev-unit">{escape(pv.get('unit', ''))}</span></div>
<span class="km-offer-prev-btn">{escape(ch['call_btn'])}</span>
</div>
<p class="km-offer-prev-cap">{escape(ch['cap'])}
<b>{escape(ch['cap_b'].format(m=months_in(lang)))}</b></p>
</div>"""


def _body(kind: str, what: str, lang: str) -> str:
    """One language's half of the card — preview, pitch, terms and CTA."""
    sec   = _PITCH.get(kind) or _PITCH["dukan"]
    p     = _pitch(kind, lang)
    ch    = _CHROME.get(lang) or _CHROME["hi"]
    terms = "".join(f"<li>{escape(t)}</li>" for t in (TERMS.get(lang) or TERMS["hi"]))
    return f"""<div class="km-offer-body" data-km-l="{lang}" lang="{lang}">
{_preview(kind, lang)}
<div class="km-offer-main">
<div class="km-offer-head">
<div class="km-offer-ic">{sec['icon']}</div>
<div class="km-offer-t">
<b>{escape(p['head'])}</b>
<span>{escape(p['sub'])}</span>
</div>
</div>
<ul class="km-offer-terms">{terms}</ul>
<a class="km-offer-go" target="_blank" rel="noopener" href="{wa_url(kind, what, lang)}">{escape(p['cta'])} →</a>
<span class="km-offer-call">{escape(ch['reach'])}
<a href="tel:+{HELPLINE}">{HELPLINE_HI}</a></span>
</div>
</div>"""


def card(kind: str, what: str = "") -> str:
    """The offer, rendered in all three languages with one of them showing.

    `kind` is "dukan" or "rental"; `what` is the product or machine whose page
    this is, so the WhatsApp message names it.

    Hindi is what a crawler and a JS-off reader get — the other two are hidden
    in CSS and revealed by the switch. That ordering is deliberate: the indexed
    text of the page does not change, so a card that now speaks three languages
    still adds no duplicate-content surface to an index being pruned.

    The calling page must carry `CSS` in its own extra_css — a route module
    cannot reach another one's stylesheet (see bhav._doc on extra_css).
    """
    tags = "".join(
        f'<span class="km-offer-tag km-offer-l-tag" data-km-l="{l}" lang="{l}">'
        f'{escape(_CHROME[l]["tag"].format(m=months_in(l)))}</span>'
        for l in LANGS)
    switch = "".join(
        f'<button type="button" class="km-offer-lang" data-km-set="{l}" lang="{l}" '
        f'aria-pressed="{"true" if l == "hi" else "false"}">{escape(LANG_LABEL[l])}</button>'
        for l in LANGS)
    bodies = "".join(_body(kind, what, l) for l in LANGS)
    return f"""<div class="km-offer">
<div class="km-offer-langs" role="group" aria-label="भाषा · மொழி · ಭಾಷೆ">{switch}</div>
{tags}
{bodies}
</div>{JS}"""
