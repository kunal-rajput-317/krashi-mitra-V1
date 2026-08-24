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


# ── the promise, in Hindi, once ─────────────────────────────

def months_hi(months: int = FREE_MONTHS) -> str:
    return "1 महीना" if months == 1 else f"{months} महीने"


# What the offer includes, in the shopkeeper's terms rather than ours. Three
# lines on purpose: this renders on a 390px phone under a grid of cards, and
# the person reading it is standing behind a counter, not reading a terms page.
TERMS_HI = (
    "कोई एडवांस नहीं, कोई कागज़ी काम नहीं",
    "महीना पूरा होने पर आगे बढ़ाना है या नहीं — पूरी तरह आपकी मर्ज़ी",
    "मुफ़्त और पैसे वाली लिस्टिंग में कोई फ़र्क़ नहीं — क्रम हमेशा दूरी से लगता है",
)

# The pitch, per section. `head`/`sub` are what the reader sees; `wa` is what
# they will end up sending us.
_PITCH = {
    "dukan": {
        "icon": "🏪",
        "head": "अपनी दुकान का सामान यहाँ दिखाएँ",
        "sub":  ("आपके ज़िले के किसान रोज़ यहाँ भाव देखते हैं। अपनी दुकान का सामान और "
                 "अपना काउंटर रेट डालिए — किसान सीधे आपकी दुकान तक पहुँचेगा।"),
        "wa":   "नमस्ते, मेरी कृषि दुकान है और मैं उसे कृषि मित्र पर लिस्ट कराना चाहता हूँ।",
        "cta":  "मुफ़्त में दुकान लिस्ट कराएँ",
    },
    "rental": {
        "icon": "⚙️",
        "head": "अपनी मशीन किराये पर देकर कमाएँ",
        "sub":  ("ट्रैक्टर, रोटावेटर, पंप सेट, हार्वेस्टर — जो मशीन खाली खड़ी है उसका "
                 "किराया यहाँ डालिए। आपके इलाके का किसान सीधे आपको फ़ोन करेगा।"),
        "wa":   "नमस्ते, मेरे पास खेती की मशीन है और मैं उसे कृषि मित्र पर किराये के लिए लिस्ट कराना चाहता हूँ।",
        "cta":  "मुफ़्त में मशीन लिस्ट कराएँ",
    },
}


def wa_url(kind: str, what: str = "") -> str:
    """The WhatsApp deep link, with the message already typed.

    The CTA is a chat, not a form: the people who own a shop or a tractor worth
    listing are reached on WhatsApp, and a sign-up flow is a thing they abandon
    halfway. `what` names the product or machine whose page this is, so the
    message that arrives tells us where it came from.
    """
    pitch = _PITCH.get(kind) or _PITCH["dukan"]
    msg = pitch["wa"]
    if what:
        msg = f"{msg} ({what})"
    return f"https://wa.me/{HELPLINE}?text={quote(f'{msg} पहला {months_hi()} मुफ़्त वाला ऑफ़र चाहिए।')}"


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
@media(max-width:560px){
.km-offer{padding:14px 14px}
.km-offer-head{gap:10px}
.km-offer-ic{width:38px;height:38px;font-size:19px}
.km-offer-t b{font-size:14.5px}
.km-offer-go{display:flex;width:100%;padding:12px 16px}
}
"""


def card(kind: str, what: str = "") -> str:
    """The offer, rendered. `kind` is "dukan" or "rental"; `what` is the product
    or machine whose page this is, so the WhatsApp message names it.

    The calling page must carry `CSS` in its own extra_css — a route module
    cannot reach another one's stylesheet (see bhav._doc on extra_css).
    """
    pitch = _PITCH.get(kind) or _PITCH["dukan"]
    terms = "".join(f"<li>{escape(t)}</li>" for t in TERMS_HI)
    return f"""<div class="km-offer">
<span class="km-offer-tag">🎁 पहला {escape(months_hi())} बिल्कुल मुफ़्त</span>
<div class="km-offer-head">
<div class="km-offer-ic">{pitch['icon']}</div>
<div class="km-offer-t">
<b>{escape(pitch['head'])}</b>
<span>{escape(pitch['sub'])}</span>
</div>
</div>
<ul class="km-offer-terms">{terms}</ul>
<a class="km-offer-go" target="_blank" rel="noopener" href="{wa_url(kind, what)}">{escape(pitch['cta'])} →</a>
<span class="km-offer-call">व्हाट्सऐप पर मैसेज करें या कॉल करें —
<a href="tel:+{HELPLINE}">{HELPLINE_HI}</a></span>
</div>"""
