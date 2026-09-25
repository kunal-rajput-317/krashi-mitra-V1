# ============================================================
# services/pay_links.py
# Every payment URL on the site, from one place.
#
#   /pay                         the hub — every way to pay, no QR
#   /pay/listing/{dealer-slug}   /dukanlisting dealer (Buyer)
#   /pay/dukan/{shop-slug}       कृषि दुकान shop (DukanShop)
#   /pay/rent/{owner-slug}       किराये की मशीन owner (RentalProvider)
#   /pay/tick/{ref}              नीला टिक — प्रीमियम membership (SellerVerification)
#   /pay/sponsor/{slug}          sponsor (Sponsor)
#   /pay/link/{token}            a one-off request the owner made in /admin
#
# Every payable page is attributed. A QR with nobody behind it brings in money
# that cannot be matched to a row — the reason the old bare /pay became a dead
# end (2026-08-04) and the reason /donate was removed (2026-09-26). So the hub
# lists the ways to pay and carries no QR and no VPA; only a URL that names its
# payer renders one.
#
# The rail itself is unchanged: services/upi.py builds the upi:// link and its
# QR, and nothing here can know a payment happened. Money is still seen in the
# bank app and recorded by hand into the payments ledger.
#
# /pay/link TOKENS ARE SIGNED. The owner types the amount and what it is for;
# that text then renders on krashimitra.in. Unsigned, anyone could edit the URL
# into "₹5000 — PM-Kisan registration fee" on our own domain — a fake scheme
# fee under our name (LEGAL_RULES §3). The HMAC key is derived from JWT_SECRET
# with its own label, so no new secret has to be set anywhere; when JWT_SECRET
# is unset (or still the public repo default) custom links are simply off.
# Rotating JWT_SECRET voids every custom link already sent — resend them.
# ============================================================
import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta
from urllib.parse import quote

from backend.services import upi

SITE = "https://krashimitra.in"

# code → (Hindi label, payments-ledger source). The code is the URL segment.
# Order is the order the admin panel lists them in.
SOURCES = {
    "listing": ("मंडी भाव पेज पर लिस्टिंग", "dealer"),
    "dukan":   ("कृषि दुकान लिस्टिंग",      "dukan"),
    "rent":    ("किराये की मशीन लिस्टिंग",  "rental"),
    "tick":    ("नीला टिक — कृषि मित्र प्रीमियम", "verify"),
    "sponsor": ("प्रायोजक · Sponsorship",    "sponsor"),
    "link":    ("भुगतान",                   "other"),
}

# Hand-typed text limits for a custom link. Short on purpose: the text lives in
# the URL, and Devanagari costs ~4 URL characters per letter once encoded.
PURPOSE_MAX = 80
NAME_MAX = 60

# A public constant the boot check already refuses in production; treated as
# "no secret" here too, so a local run never signs with a published key.
_PUBLIC_DEFAULT = "change_this_secret_in_production"
_SIG_BYTES = 16


def url(source: str, key: str, amount=None) -> str:
    """Absolute URL of one payable page — it is pasted into WhatsApp, where a
    site-relative path arrives as unclickable text.

    `amount` travels on the URL when the caller quoted one: the figure in the
    message and the figure on the page have to be the same number. The page
    re-clamps it, so a hand-edited URL still cannot produce a ₹0 QR."""
    out = f"{SITE}/pay/{source}/{quote(str(key or ''), safe='')}"
    return f"{out}?amount={int(amount)}" if amount else out


def ref(source: str, key: str) -> str:
    """The UPI `tr` reference — the thread tying a bank credit back to a row.

    Source first, so a statement line reads "tick-KM8F2A" or "dukan-ram-khad"
    without looking anything up. upi.link() trims it to the 35 characters UPI
    allows; a long slug loses its tail, never its source."""
    return f"{source}-{key}"


# ── Custom links (/pay/link/{token}) ─────────────────────────

def _key() -> bytes:
    secret = (os.getenv("JWT_SECRET") or "").strip()
    if not secret or secret == _PUBLIC_DEFAULT:
        return b""
    return hmac.new(secret.encode(), b"krashimitra-pay-link-v1", hashlib.sha256).digest()


def links_enabled() -> bool:
    return bool(_key())


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(body: str) -> str:
    return _b64(hmac.new(_key(), body.encode(), hashlib.sha256).digest()[:_SIG_BYTES])


def clean_text(text: str, limit: int) -> str:
    return " ".join(str(text or "").split())[:limit].strip()


def make_link(amount, purpose: str, payer: str = "") -> dict:
    """A signed one-off payment request. Raises ValueError with a Hindi reason
    the panel can show as-is."""
    if not links_enabled():
        raise ValueError("JWT_SECRET सेट नहीं है — पेमेंट लिंक नहीं बन सकता")
    amt = upi.clean_amount(amount, default=0)
    if not amt:
        raise ValueError(f"राशि ₹{upi.MIN_AMOUNT} से ₹{upi.MAX_AMOUNT} के बीच लिखिए")
    purpose = clean_text(purpose, PURPOSE_MAX)
    if not purpose:
        raise ValueError("किस चीज़ का पैसा है — यह लिखिए")
    # India's date, not UTC's — a link made before 5:30 AM would otherwise say
    # it was made yesterday.
    ist = datetime.utcnow() + timedelta(hours=5, minutes=30)
    payload = {"a": amt, "f": purpose, "d": ist.strftime("%Y-%m-%d")}
    payer = clean_text(payer, NAME_MAX)
    if payer:
        payload["t"] = payer
    body = _b64(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode())
    token = f"{body}.{_sign(body)}"
    return {"token": token, "url": url("link", token), "amount": amt,
            "purpose": purpose, "payer": payer, "issued": payload["d"],
            "ref": link_ref(token)}


def read_link(token: str) -> dict | None:
    """The request behind a token we issued, or None — for a forged, edited or
    truncated token alike. compare_digest, never ==."""
    if not links_enabled() or not token or token.count(".") != 1:
        return None
    body, sig = token.split(".")
    if not hmac.compare_digest(_sign(body), sig):
        return None
    try:
        data = json.loads(_unb64(body).decode())
        amt = upi.clean_amount(data.get("a"), default=0)
        purpose = clean_text(data.get("f"), PURPOSE_MAX)
    except Exception:
        return None
    if not amt or not purpose:
        return None
    return {"amount": amt, "purpose": purpose,
            "payer": clean_text(data.get("t"), NAME_MAX),
            "issued": str(data.get("d") or ""), "ref": link_ref(token)}


def link_ref(token: str) -> str:
    """Short and stable per link: the first characters of its signature, which
    no two links share in practice and which the owner can read off a bank
    statement to know which request was paid."""
    sig = token.rpartition(".")[2]
    return ref("link", "".join(ch for ch in sig if ch.isalnum())[:10])


# ── The admin side: one pack for every collect button ────────

def collect_pack(source: str, key: str, name: str = "", district: str = "",
                 amount=None, purpose: str = "") -> dict:
    """What every admin "पैसे मांगें" button returns: the UPI link and QR, the
    /pay URL to send, and a ready-to-send WhatsApp message built around it.

    The page URL is what goes in the message, not the raw upi:// link — WhatsApp
    does not make upi:// tappable, so a payer on a phone was left with a string
    he could do nothing with."""
    label = SOURCES.get(source, ("", ""))[0]
    purpose = clean_text(purpose, 200) or label
    pack = upi.collect(name, district, amount=amount, ref=ref(source, key))
    pack["dealer_name"] = name
    pack["purpose"] = purpose
    pack["pay_url"] = url(source, key, pack["amount"])
    pack["whatsapp_text"] = whatsapp_text(name, pack["amount"], purpose, pack["pay_url"])
    return pack


def whatsapp_text(name: str, amount: int, purpose: str, pay_url: str) -> str:
    """Plain Hindi, no marketing — this goes to someone who has already said yes
    on the phone and only needs the link. Never promises what happens after."""
    name = (name or "").strip()
    for_line = f" — {purpose}" if purpose else ""
    return (
        f"नमस्ते{' ' + name if name else ''} जी,\n"
        f"कृषि मित्र: ₹{amount}{for_line}।\n\n"
        f"इस लिंक पर QR है, किसी भी UPI ऐप से पे कर सकते हैं:\n{pay_url}\n\n"
        f"पेमेंट के बाद स्क्रीनशॉट या UPI रेफरेंस नंबर इसी नंबर पर भेज दीजिए।"
    )
