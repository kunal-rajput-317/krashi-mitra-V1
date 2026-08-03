# ============================================================
# services/upi.py
# The ₹500 collect rail: a UPI deep link, and a QR of that same link.
#
# WHY UPI AND NOTHING ELSE. A payment gateway wants a registered entity, KYC and
# a cut of every rupee; that decision is still open (deadline_checklist.json →
# entity-decision) and it blocks nothing here. Bank-account UPI is zero-MDR by
# RBI mandate, needs no onboarding on either side, and a trader already has an
# app on his phone. The whole rail is a URL — there is no integration to break,
# no webhook to miss, and no card data anywhere near this codebase.
#
# WHAT THIS DELIBERATELY IS NOT. There is no payment *confirmation* here, and
# there cannot be: a upi:// link hands off to the dealer's own app and tells us
# nothing on the way back. Settlement is observed in the owner's bank app and
# typed into the panel by hand (dealers.record_payment). So nothing in this file
# may ever render "paid" — it renders a request to pay. Treating a generated
# link as proof of payment would be inventing a receipt.
#
# CONFIG IS ENVIRONMENT, NEVER A LITERAL. A VPA committed to the repo is a
# real-money destination in a public git history, and a wrong one silently sends
# a dealer's ₹500 to a stranger. Unset config makes every surface here say "not
# configured" rather than fall back to a guess.
# ============================================================
import logging
import os
import re
from urllib.parse import quote

from backend.utils.hindi_translit import readable as _translit_readable

log = logging.getLogger("krishi.upi")

# A VPA is `handle@psp`. Deliberately strict: this string becomes the
# destination of real money, and a malformed one fails inside the dealer's app
# where we can neither see it nor explain it.
_VPA_RE = re.compile(r"^[a-zA-Z0-9._-]{2,64}@[a-zA-Z][a-zA-Z0-9.-]{1,32}$")

# UPI notes are shown on the payer's confirmation screen and echoed into bank
# statements. Several PSP apps mangle or reject anything outside this set, so
# the note is reduced to it rather than trusted — it is assembled from a dealer
# name that arrived over a public form.
_NOTE_SAFE = re.compile(r"[^A-Za-z0-9 .\-/]")
_NOTE_MAX = 48

# `tr` is the merchant-side reference echoed back in some PSP statements. Same
# reasoning as the note, tighter charset: it must survive being a URL param.
_REF_SAFE = re.compile(r"[^A-Za-z0-9-]")
_REF_MAX = 35

# The listing fee. Env-overridable because the first real negotiation may not
# land on ₹500, and re-deploying to change a price is the kind of seam the
# project's everything-must-be-automatic rule exists to prevent.
DEFAULT_AMOUNT = int(os.getenv("KM_LISTING_FEE", "500") or 500)

# Guard rails on a hand-typed amount, not a business rule: ₹1 catches an empty
# field, ₹1,00,000 catches a slipped decimal point before it reaches a QR that
# somebody actually scans.
MIN_AMOUNT = 1
MAX_AMOUNT = 100000


def vpa() -> str:
    return (os.getenv("KM_UPI_ID") or "").strip()


def payee_name() -> str:
    """The name a dealer sees in his UPI app before he confirms.

    Must match the name registered on the receiving account closely enough that
    a trader recognises it — a mismatch here reads as a scam and kills the
    payment at the last screen.
    """
    return (os.getenv("KM_UPI_NAME") or "KrashiMitra").strip()[:50]


def configured() -> bool:
    return bool(_VPA_RE.match(vpa()))


def clean_amount(raw, default: int | None = None) -> int:
    """A whole-rupee amount inside the guard rails, or the default.

    Whole rupees only: the fee is quoted in round numbers, and paise in a QR is
    a typo every time.
    """
    if default is None:
        default = DEFAULT_AMOUNT
    try:
        n = int(round(float(str(raw).strip())))
    except (TypeError, ValueError):
        return default
    return n if MIN_AMOUNT <= n <= MAX_AMOUNT else default


def _note(text: str) -> str:
    """Reduce to the charset UPI apps reliably render, then collapse runs.

    Callers should pass text through utils.hindi_translit.readable() first —
    this filter has no Devanagari handling of its own and, applied straight to
    a Hindi firm name (most of them), leaves one space per stripped character:
    a wall of blanks that eats the whole 48-char budget before the district is
    reached. See collect() below, which is the one place this note is built.
    """
    return re.sub(r"\s+", " ", _NOTE_SAFE.sub(" ", (text or "").strip())).strip()[:_NOTE_MAX].strip()


def _ref(text: str) -> str:
    return _REF_SAFE.sub("", (text or "").strip())[:_REF_MAX]


def link(amount=None, note: str = "", ref: str = "") -> str:
    """The `upi://pay?…` deep link. "" when no VPA is configured.

    Every value is percent-encoded with a `safe=""` quote, including `@` in the
    VPA. The note carries a dealer-supplied firm name, so an unencoded `&` would
    let that name append its own parameters — an `&am=` in a firm name would
    rewrite the amount on the confirmation screen the dealer is looking at.
    """
    if not configured():
        return ""
    parts = [
        f"pa={quote(vpa(), safe='')}",
        f"pn={quote(payee_name(), safe='')}",
        "cu=INR",
    ]
    amt = clean_amount(amount)
    parts.append(f"am={amt}")
    n = _note(note)
    if n:
        parts.append(f"tn={quote(n, safe='')}")
    r = _ref(ref)
    if r:
        parts.append(f"tr={quote(r, safe='')}")
    return "upi://pay?" + "&".join(parts)


def qr_svg(data: str, scale: int = 5) -> str:
    """The link as an inline SVG QR, or "" if it cannot be built.

    Inline SVG rather than a PNG endpoint: it needs no image route, no disk
    (Render has none), scales on a phone without going blurry, and cannot 404
    the way the site's missing static files silently do.

    Fails soft — the copyable link and the pay button are the real rail, and a
    QR that will not render must not take the page down with it. But soft must
    not mean silent: a missing `segno` (e.g. installed into a different Python
    than the one actually running the server — two coexist on the dev machine)
    used to fail into an empty string with no trace anywhere, which looks
    identical to "it rendered nothing" from the outside. Logged instead, once
    per distinct cause, so that failure mode is diagnosable from the server log
    rather than from guessing.
    """
    if not data:
        return ""
    try:
        import segno
        return segno.make(data, error="m").svg_inline(scale=scale, dark="#0f2419")
    except ImportError:
        log.warning(
            "QR not rendered: segno is not importable in this Python "
            "(sys.executable may differ from the one `pip install segno` ran "
            "against). The pay button and copyable link still work."
        )
        return ""
    except Exception as e:
        log.warning("QR not rendered (%s): %s", type(e).__name__, e)
        return ""


def collect(dealer_name: str = "", district: str = "", amount=None,
            ref: str = "") -> dict:
    """Everything a collect surface needs, in the shape both callers want.

    `note` is what lands on the dealer's confirmation screen and in the owner's
    bank statement — the firm and district are there so a row in a statement can
    be matched back to a listing weeks later without guesswork.
    """
    amt = clean_amount(amount)
    # Most firm names are written in Devanagari. _note() alone has no Hindi
    # handling and reduces one straight to a wall of blanks — see its
    # docstring — so the name is transliterated to readable Latin first
    # ("शर्मा ट्रेडर्स" -> "Sharma Tredars"), and only THAT goes through the
    # charset filter. The slug is the last resort, for the rare case a name is
    # entirely punctuation/whitespace and transliterates to nothing.
    name_part = _note(_translit_readable(dealer_name))
    label = _note(f"{name_part} {district}") if name_part else _ref(ref)
    # Report the note that actually ships in the link, not the one we asked
    # for: a caller rendering this would otherwise show text the dealer's UPI
    # app is never going to display.
    note = f"KrashiMitra listing {label}".strip() if label else "KrashiMitra listing"
    url = link(amt, note=note, ref=ref)
    return {
        "configured": configured(),
        "vpa": vpa(),
        "payee": payee_name(),
        "amount": amt,
        "note": note,
        "link": url,
        "qr_svg": qr_svg(url),
    }
