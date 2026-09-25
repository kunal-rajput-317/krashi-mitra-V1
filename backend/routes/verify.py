# ============================================================
# routes/verify.py
# /verify — the blue-tick funnel a farmer walks through himself.
# ============================================================
# WHAT THE TICK MEANS HERE (changed 2026-09-18). It is a paid membership, the
# same thing X's blue check is. It is NOT verification, NOT an identity check
# and NOT a guarantee of the crop, the price or the deal — and this page is
# where that distinction is either honoured or quietly broken, because it is
# the page selling the thing.
#
# SO THIS PAGE MAY NOT SAY "सत्यापित". Not in a headline, not in a benefit
# list, not in the phrase "सत्यापित विक्रेता बनें" it used to be titled. Every
# benefit printed below is something the site actually does when the flag goes
# on — a tick beside his name, a blue ring on his photo, the tick in the
# WhatsApp preview — and nothing about how buyers will behave, what price he
# will get, or who he is. A test sweeps the rendered page for the banned words.
#
# Nor may it say "पेमेंट हो गया": a upi:// hand-off reports nothing back
# (services/upi.py), so only a human who saw the bank credit can say that. What
# the farmer CAN say is that he sent it — that is the "मैंने पैसे भेज दिए"
# button, which records his claim, moves his row to the top of the admin queue
# and grants nothing.
#
# Six states on one page, driven by his own row:
#
#   none      → what the tick is, the two plans, the signup form
#   applied   → the UPI QR + "मैंने पैसे भेज दिए"
#   claimed   → "हमें आपका भुगतान जाँचना है" (his claim, unconfirmed)
#   paid      → the tick is on, when it ends, how to renew
#   approved  → same, given by the owner
#   rejected  → the badge was removed, and the refund
#   declined  → the application was refused before any tick → apply again
#   expired   → the term ran out → the plans again
#
# noindex, always. It is a logged-in billing page; it has no business in a
# sitemap or a SERP, and a farmer reaching it from search instead of from his
# own profile would be reading someone else's funnel.
# ============================================================
import json
from html import escape
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database.db import User, UserProfile, acct, get_db
from backend.routes.bhav import _doc
from backend.services import pay_links, seller_verify, upi
from backend.utils.auth_utils import get_current_user

router = APIRouter()

CANON = "https://krashimitra.in/verify"

# What the membership actually gets him. Every line is a thing this codebase
# does the moment users.seller_verified flips — the tick in bazar.py's feed
# payload, the ocean-blue ring krashi_bajar.html draws on his avatar, the ✅
# share.py puts in the WhatsApp preview, and the badge on his own profile.
#
# What is NOT on this list, and may never be: more buyers, a faster sale, a
# better price, or anything about who he is. Those are either unprovable or a
# claim about a person, and this badge is sold on neither.
GETS_HI = [
    "आपके नाम के साथ नीला टिक — हर पोस्ट पर",
    "प्रोफ़ाइल फ़ोटो पर नीला घेरा, जो भीड़ में दिखता है",
    "कृषि मित्र के WhatsApp चैनल पर आपके नाम के साथ टिक",
    "आपकी प्रोफ़ाइल पर प्रीमियम सदस्य का निशान",
]

# The one paragraph that keeps this page honest. It says what the tick is and,
# more importantly, the three things it is not.
MEANS_HI = (
    "नीला टिक कृषि मित्र प्रीमियम का निशान है — इसका मतलब है कि यह सदस्य "
    "कृषि मित्र प्रीमियम लेता है। यह पहचान की जाँच नहीं है, और फसल, भाव या "
    "सौदे की कोई गारंटी नहीं है। खरीदार को हर सौदे में खुद जाँच-परख करनी चाहिए।"
)


# The terms, in plain words, on the page that sells the membership. A paid
# badge with vague terms is a consumer-law argument waiting to happen, so each
# line states what the code ACTUALLY does — change the code, change the line:
#   • term       — seller_verify.record_payment: 30 days × the plan's months,
#                  from the day the money is confirmed; renewing early extends
#   • no renewal — nothing here can pull money; UPI is push-only
#   • expiry     — seller_verify.expire_due / the 04:20 sweep clear the flag
#   • refunds    — revoke() owes the whole fee back (record_refund, ledger)
#   • removal    — revoke() is the owner's kill switch for these reasons
# There is NO expiry reminder built, so this page must not promise one.
TERMS_HI = [
    "<b>कितने दिन:</b> 1 महीने का प्लान 30 दिन, 3 महीने का प्लान 90 दिन चलता है — "
    "उस दिन से, जिस दिन आपका पैसा हमारे खाते में पहुँचकर दर्ज होता है।",
    "<b>अपने-आप पैसा नहीं कटेगा:</b> कोई auto-renewal नहीं है। अवधि पूरी होते ही टिक "
    "अपने-आप हट जाता है। आगे चाहिए तो खुद दोबारा भुगतान करें — समय से पहले बढ़ाने पर "
    "बचे हुए दिन जुड़ जाते हैं, कटते नहीं।",
    "<b>पैसा वापस (रिफ़ंड):</b> पैसा पहुँचा लेकिन टिक चालू नहीं हुआ, या हमने टिक अवधि "
    "के बीच में हटा दिया — दोनों में पूरा शुल्क 7 दिन के अंदर उसी UPI / खाते में वापस। "
    "टिक चालू होने के बाद अपनी मर्ज़ी से छोड़ने पर शुल्क वापस नहीं होता।",
    "<b>टिक कब हटाया जा सकता है:</b> किसी और के नाम या फ़ोटो से खाता चलाने, टिक दिखाकर "
    "धोखा देने या झूठी पोस्ट डालने, या भुगतान वापस ले लेने (chargeback) पर।",
    "<b>टिक क्या नहीं है:</b> पहचान की जाँच, या फसल, भाव या सौदे की गारंटी नहीं। "
    "हर सौदा खरीदार और विक्रेता के बीच है — कृषि मित्र उसमें शामिल नहीं होता।",
    "<b>सवाल या शिकायत:</b> +91 9870951001 (WhatsApp / कॉल) या krashimitra038@gmail.com",
]


# ── API ──────────────────────────────────────────────────────

class ApplyRequest(BaseModel):
    full_name: Optional[str] = None
    phone:     Optional[str] = None
    village:   Optional[str] = None
    district:  Optional[str] = None
    state:     Optional[str] = None
    id_kind:   Optional[str] = None
    note:      Optional[str] = None
    # "m1" or "m3". Not validated here on purpose — seller_verify.plan() reads
    # anything it does not recognise as the monthly plan, so a junk code buys
    # the cheapest term rather than 400ing a farmer out of the funnel.
    plan:      Optional[str] = None


class PaidClaimRequest(BaseModel):
    # The UTR / reference off his UPI app, if he can find it. Optional, because
    # asking a farmer to copy a 12-digit transaction id off a confirmation
    # screen is exactly the step that ends a funnel.
    paid_ref:  Optional[str] = None


def _profile(user_id: int, db: Session) -> UserProfile:
    profile = db.query(UserProfile).filter(UserProfile.user_id == acct(user_id)).first()
    if not profile:
        raise HTTPException(403, "PROFILE_REQUIRED")
    return profile


@router.get("/verify/me")
def my_verification(
    current_user: dict    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """His own application. Also the page's only source of truth for state."""
    user_id = current_user["user_id"]
    # Cheap and idempotent: a badge whose window ran out should read as expired
    # the moment he looks, not whenever a timer next fires.
    seller_verify.expire_due(db)
    row = seller_verify.get(db, user_id)
    user = db.query(User).filter(User.id == user_id).first()
    data = seller_verify.to_dict(row)
    data["verified_now"] = bool(user and user.seller_verified)
    return {"success": True, "message": "", "data": data}


@router.post("/verify/apply")
def apply_for_badge(
    body:         ApplyRequest,
    current_user: dict    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    user_id = current_user["user_id"]
    profile = _profile(user_id, db)

    data = body.model_dump()
    # Fall back to what is already on file rather than making him retype it.
    data["full_name"] = (data.get("full_name") or profile.name or "").strip()
    data["phone"]     = (data.get("phone") or profile.phone_number or "").strip()
    data["village"]   = (data.get("village") or profile.village or "").strip()
    data["district"]  = (data.get("district") or profile.district or "").strip()
    data["state"]     = (data.get("state") or profile.state or "").strip()

    if not data["full_name"]:
        raise HTTPException(400, "अपना पूरा नाम डालें।")
    # Not a check — the badge checks nothing. It is the only way to reach him
    # about a payment that did not arrive or a term about to run out, and a
    # membership nobody can contact is a refund waiting to happen.
    digits = "".join(ch for ch in data["phone"] if ch.isdigit())
    if len(digits) < 10:
        raise HTTPException(400, "सही मोबाइल नंबर डालें — इसी पर हम आपसे संपर्क करेंगे।")

    try:
        row = seller_verify.apply(db, user_id, data)
    except seller_verify.RefundPending:
        raise HTTPException(409, "आपका पिछला शुल्क वापस भेजा जा रहा है। रिफंड पहुँचने के "
                                 "बाद फिर से आवेदन करें — सवाल हो तो +91 9870951001।")
    return {
        "success": True,
        "message": "हो गया। अब शुल्क भेजें — पैसा पहुँचते ही टिक चालू हो जाएगा।",
        "data": seller_verify.to_dict(row),
    }


@router.post("/verify/paid")
def claim_paid(
    body:         PaidClaimRequest,
    current_user: dict    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """"मैंने पैसे भेज दिए." His claim, recorded. It grants nothing.

    Keyed on his own session, never on a ref out of the URL, so one member
    cannot mark another member's row as paid. It does not move the status and
    never touches the flag — if it did, the badge would be free to anyone who
    can tap a button. What it buys him is position: the admin queue sorts
    claimed rows to the top (seller_verify.pending_first), so the confirmation
    is minutes away instead of whenever the list next gets scrolled.
    """
    user_id = current_user["user_id"]
    row = seller_verify.claim_payment(db, user_id, (body.paid_ref or ""))
    if not row:
        raise HTTPException(404, "पहले नीला टिक के लिए आवेदन करें।")
    return {
        "success": True,
        "message": "आपका संदेश मिल गया। पैसा पहुँचा है या नहीं, हम जाँच कर रहे हैं।",
        "data": seller_verify.to_dict(row),
    }


@router.get("/verify/plans")
def public_plans():
    """The price table, for pages that are static files and cannot be templated.

    krashi_bajar.html is served off disk, so the only honest way for its in-feed
    offer card to print ₹199 / ₹499 is to ask. Hard-coding them in the HTML
    would mean a price change needed a deploy AND a cache bust, and the card
    would quietly disagree with the UPI link the moment either was missed.

    Public and unauthenticated: it is a price list, the same one any visitor
    sees on /verify, and it carries nothing about anybody.
    """
    return {"success": True, "message": "", "data": {"plans": seller_verify.plans()}}


@router.get("/verify/pay/{ref}")
def payment_pack(ref: str, db: Session = Depends(get_db)):
    """The UPI link + QR for one application.

    Public by ref on purpose, exactly like /pay?d=<slug>: the ref is the only
    thread tying a bank credit back to a row, and the farmer opens this from
    his own phone or from a WhatsApp message. It exposes no personal data.
    """
    row = seller_verify.by_ref(db, ref)
    if not row:
        raise HTTPException(404, "यह आवेदन नहीं मिला।")
    return {"success": True, "message": "", "data": _pay_pack(row)}


def _pay_pack(row) -> dict:
    amount = row.fee_amount or seller_verify.fee()
    # The note lands on his confirmation screen and in the owner's bank
    # statement; the ref is what makes a credit matchable weeks later.
    # "premium", not "verify": this note is on his UPI app's confirmation
    # screen, and the tick is a membership, not a check of anybody. The `tr`
    # carries the source too, the same format every /pay/{source} page uses.
    note = f"KrashiMitra premium {row.ref}"
    url = upi.link(amount, note=note, ref=pay_links.ref("tick", row.ref))
    return {
        "configured": upi.configured(),
        "vpa":        upi.vpa(),
        "payee":      upi.payee_name(),
        "amount":     amount,
        "ref":        row.ref,
        "note":       note,
        "link":       url,
        "qr_svg":     upi.qr_svg(url),
        # The same request as a page — for paying from someone else's phone.
        "pay_url":    pay_links.url("tick", row.ref),
    }




# ── The page ─────────────────────────────────────────────────

_CSS = """
.vf-wrap{max-width:560px;margin:0 auto;padding:8px 0 48px}
.vf-card{background:var(--white);border:1px solid var(--border);
border-radius:var(--radius-sm);padding:24px 20px;box-shadow:var(--shadow-sm);margin-bottom:14px}
.vf-tick{display:inline-flex;align-items:center;gap:7px;background:#e8f4fd;color:#0284c7;
border-radius:20px;padding:5px 13px;font-size:13px;font-weight:700;margin-bottom:12px}
.vf-tick svg{width:16px;height:16px;flex-shrink:0}
.vf-h{font-size:21px;font-weight:800;color:var(--text-dark);margin:0 0 8px;line-height:1.35}
.vf-p{font-size:14px;color:var(--text-soft);line-height:1.65;margin:0 0 14px}
.vf-checks{list-style:none;padding:0;margin:0 0 4px}
.vf-checks li{position:relative;padding-left:26px;font-size:13.5px;line-height:1.6;
color:var(--text-dark);margin-bottom:8px}
.vf-checks li:before{content:'✓';position:absolute;left:0;top:0;color:#0284c7;font-weight:800}
.vf-note{background:#fff8e1;border:1px solid #ffe08a;border-radius:10px;padding:11px 13px;
font-size:12.5px;color:#7a5c00;line-height:1.6;margin-bottom:16px}

/* ── The two plans ── */
.vf-plans{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:0 0 16px}
.vf-plan{position:relative;display:flex;flex-direction:column;align-items:flex-start;gap:2px;
background:var(--cream);border:2px solid var(--border);border-radius:14px;padding:14px 12px 13px;
cursor:pointer;font-family:inherit;text-align:left;transition:border-color .15s,background .15s}
.vf-plan:hover{border-color:#bae0fb}
.vf-plan.on{border-color:#0284c7;background:#f0f8ff}
/* Indented past the radio, which sits on this same line. Without it the dot
covered the digit — "1 महीने के लिए" read as "महीने के लिए" on both cards, so
the one number telling a farmer what he was buying was the one hidden. */
.vf-plan-term{font-size:11.5px;font-weight:800;color:var(--text-soft);letter-spacing:.02em;
padding-left:21px}
.vf-plan-price{font-size:26px;font-weight:800;color:var(--green-dark);line-height:1.15}
.vf-plan-price s{font-size:14px;font-weight:600;color:var(--text-light);margin-left:6px}
.vf-plan-pm{font-size:11.5px;font-weight:700;color:var(--text-soft)}
.vf-plan-save{position:absolute;top:-9px;right:8px;background:#0284c7;color:#fff;
font-size:10px;font-weight:800;padding:2px 7px;border-radius:9px;letter-spacing:.02em}
.vf-plan-tick{position:absolute;top:13px;left:10px;width:15px;height:15px;border-radius:50%;
border:2px solid var(--border);background:#fff}
.vf-plan.on .vf-plan-tick{border-color:#0284c7;background:#0284c7;
box-shadow:inset 0 0 0 2px #fff}
.vf-offer-line{font-size:11.5px;font-weight:700;color:#0284c7;margin:-8px 0 14px}

.vf-field{margin-bottom:12px}
.vf-field label{display:block;font-size:12.5px;font-weight:700;color:var(--text-dark);margin-bottom:5px}
.vf-field input,.vf-field select,.vf-field textarea{width:100%;box-sizing:border-box;
border:1.5px solid var(--border);border-radius:10px;padding:11px 13px;font-size:14px;
font-family:inherit;outline:none;background:var(--cream);color:var(--text-dark)}
.vf-field input:focus,.vf-field select:focus,.vf-field textarea:focus{border-color:var(--green-light);background:#fff}
.vf-btn{display:block;width:100%;padding:15px 18px;background:var(--green-dark);color:#fff;
border:0;border-radius:var(--radius-sm);font-size:16px;font-weight:700;text-decoration:none;
text-align:center;cursor:pointer;font-family:inherit;box-shadow:var(--shadow-sm)}
.vf-btn:hover{background:var(--green-mid)}
.vf-btn[disabled]{opacity:.55;cursor:default}
.vf-btn.ghost{background:#fff;color:#0284c7;border:1.5px solid #bae0fb;box-shadow:none;
margin-top:10px;font-size:14px;padding:12px 16px}
.vf-btn.ghost:hover{background:#f0f8ff}
.vf-qr{display:inline-block;padding:14px;background:#fff;border:1px solid var(--border);
border-radius:var(--radius-sm);line-height:0;margin-bottom:6px}
.vf-qr svg{width:186px;height:186px;display:block}
.vf-vpa{font-size:14px;font-weight:700;color:var(--text-dark);word-break:break-all;
background:var(--cream);border:1px dashed var(--border);border-radius:8px;padding:9px 11px;margin:8px 0 0}
.vf-ref{font-size:12.5px;color:var(--text-soft);margin-top:10px}
.vf-ref b{color:var(--text-dark);letter-spacing:.06em}
.vf-state{text-align:center}
.vf-err{color:#b91c1c;font-size:13px;font-weight:700;margin-top:10px}
.vf-muted{font-size:12px;color:var(--text-soft);line-height:1.6;margin-top:14px}
.vf-terms{margin:0;padding:0 0 0 18px}
.vf-terms li{font-size:13px;line-height:1.65;color:var(--text-dark);margin-bottom:9px}
.vf-terms li b{color:var(--text-dark)}
.vf-wait{background:#f0f8ff;border:1px solid #cfe6fb;border-radius:10px;padding:13px 14px;
font-size:13px;color:#1e4e79;line-height:1.6;font-weight:600}
"""

# The badge, drawn once. Same path as the one krashi_bajar.html puts beside a
# member's name, so the thing he is buying is the thing he is looking at.
_TICK_SVG = (
    '<svg viewBox="0 0 24 24" fill="#0284c7" aria-hidden="true"><path d="M22.25 12c0-1.43-.88-2.67-2.19-3.34.46-1.39.2-2.9-.81-3.91s-2.52-1.27-3.91-.81c-.66-1.31-1.91-2.19-3.34-2.19s-2.67.88-3.33 2.19c-1.4-.46-2.91-.2-3.92.81s-1.26 2.52-.8 3.91c-1.31.67-2.2 1.91-2.2 3.34s.89 2.67 2.2 3.34c-.46 1.39-.21 2.9.8 3.91s2.52 1.26 3.91.81c.67 1.31 1.91 2.19 3.34 2.19s2.68-.88 3.34-2.19c1.39.45 2.9.2 3.91-.81s1.27-2.52.81-3.91c1.31-.67 2.19-1.91 2.19-3.34zm-11.71 4.2L6.8 12.46l1.41-1.42 2.26 2.26 4.8-5.23 1.47 1.36-6.2 6.77z"/></svg>'
)


# The page body. A plain template, not an f-string: the script below is full of
# object literals, and escaping every brace made the old version unreadable for
# no gain. Substitutions are the __TOKEN__ pairs at the bottom of verify_page().
_BODY = """
<div class="vf-wrap">
  <div class="vf-card" id="vf-intro">
    <span class="vf-tick">__TICK__ नीला टिक</span>
    <h1 class="vf-h">कृषि बाज़ार में नीला टिक लगवाएँ</h1>
    <p class="vf-p">__MEANS__</p>
    <p class="vf-p" style="margin-bottom:8px;"><b>क्या मिलेगा:</b></p>
    <ul class="vf-checks">__GETS__</ul>
  </div>

  <div class="vf-card" id="vf-body">
    <p class="vf-p vf-state" id="vf-loading">एक पल…</p>
  </div>

  <div class="vf-card" id="vf-terms">
    <h2 class="vf-h" style="font-size:17px;">नियम — साफ़-साफ़</h2>
    <ul class="vf-terms">__TERMS__</ul>
  </div>
</div>

<script>
(function() {
  var PLANS = __PLANS__;
  var API = (window.KRASHIMITRA_API_BASE || '');
  var tok = null;
  try { tok = localStorage.getItem('krishi_token'); } catch (e) {}
  var box = document.getElementById('vf-body');
  var picked = PLANS.length ? PLANS[0].code : 'm1';

  var esc = function(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function(c) {
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
    });
  };

  function api(path, opts) {
    opts = opts || {};
    opts.headers = Object.assign({'Content-Type': 'application/json'}, opts.headers || {});
    if (tok) opts.headers['Authorization'] = 'Bearer ' + tok;
    return fetch(API + path, opts).then(function(r) {
      return r.json().then(function(j) { j._status = r.status; return j; });
    });
  }

  function loginWall() {
    box.innerHTML = '<p class="vf-p vf-state">नीला टिक लेने के लिए पहले लॉगिन करें।</p>' +
      '<a class="vf-btn" href="/login.html?next=/verify">लॉगिन करें</a>';
  }
  if (!tok) { loginWall(); return; }

  function planOf(code) {
    for (var i = 0; i < PLANS.length; i++) if (PLANS[i].code === code) return PLANS[i];
    return PLANS[0] || {price: 199, months: 1};
  }

  /* The picker. Drawn from the same table the server prices from, so the
     price on the card and the amount in the UPI link cannot drift. No struck
     price: the only saving shown is the real one against the monthly plan. */
  function planCards() {
    return '<div class="vf-plans">' + PLANS.map(function(p) {
      return '<button type="button" class="vf-plan' + (p.code === picked ? ' on' : '') + '"' +
        ' data-plan="' + esc(p.code) + '" onclick="window.__vfPick(&quot;' + esc(p.code) + '&quot;)">' +
        '<span class="vf-plan-tick"></span>' +
        (p.save_pct ? '<span class="vf-plan-save">' + p.save_pct + '% बचत</span>' : '') +
        '<span class="vf-plan-term">' + esc(p.term_hi) + '</span>' +
        '<span class="vf-plan-price">₹' + p.price + '</span>' +
        (p.months > 1 ? '<span class="vf-plan-pm">₹' + p.per_month + ' / महीना</span>'
                      : '<span class="vf-plan-pm">हर महीने</span>') +
        '</button>';
    }).join('') + '</div>' +
    PLANS.filter(function(p) { return p.save_vs; }).map(function(p) {
      return '<p class="vf-offer-line">' + esc(p.term_hi) + ' एक साथ ₹' + p.price +
        ' — अलग-अलग महीने लेने पर ₹' + p.save_vs + ' लगते।</p>';
    }).join('');
  }

  window.__vfPick = function(code) {
    picked = code;
    var cards = document.querySelectorAll('.vf-plan');
    for (var i = 0; i < cards.length; i++) {
      cards[i].classList.toggle('on', cards[i].getAttribute('data-plan') === code);
    }
    var btn = document.getElementById('vf-submit');
    if (btn && !btn.disabled) btn.textContent = '₹' + planOf(code).price + ' — आगे बढ़ें';
  };

  /* ── State: no membership, or a lapsed one ── */
  function signupForm(d) {
    box.innerHTML =
      planCards() +
      '<div class="vf-field"><label>पूरा नाम</label><input id="vf-name" value="' + esc(d.full_name || '') + '" placeholder="जैसे: राम सिंह"></div>' +
      '<div class="vf-field"><label>मोबाइल नंबर</label><input id="vf-phone" inputmode="numeric" value="' + esc(d.phone || '') + '" placeholder="10 अंक"></div>' +
      '<div class="vf-field"><label>गाँव</label><input id="vf-village" value="' + esc(d.village || '') + '"></div>' +
      '<div class="vf-field"><label>ज़िला</label><input id="vf-district" value="' + esc(d.district || '') + '"></div>' +
      '<div class="vf-field"><label>कुछ और बताना हो (ज़रूरी नहीं)</label><textarea id="vf-note" rows="2"></textarea></div>' +
      '<button class="vf-btn" id="vf-submit">₹' + planOf(picked).price + ' — आगे बढ़ें</button>' +
      '<p class="vf-muted">अगला कदम शुल्क भेजना है। पैसा पहुँचते ही नीला टिक चालू हो जाएगा। ' +
      'नाम और नंबर इसलिए चाहिए कि रिन्यू या किसी दिक्कत पर हम आपसे संपर्क कर सकें।</p>' +
      '<div class="vf-err" id="vf-err" style="display:none;"></div>';
    document.getElementById('vf-submit').onclick = function() {
      var btn = this; btn.disabled = true; btn.textContent = 'भेजा जा रहा है…';
      api('/verify/apply', { method: 'POST', body: JSON.stringify({
        plan:      picked,
        full_name: document.getElementById('vf-name').value,
        phone:     document.getElementById('vf-phone').value,
        village:   document.getElementById('vf-village').value,
        district:  document.getElementById('vf-district').value,
        note:      document.getElementById('vf-note').value
      }) }).then(function(j) {
        if (j.success) return render(j.data);
        var e = document.getElementById('vf-err');
        e.style.display = 'block';
        e.textContent = (j.detail === 'PROFILE_REQUIRED')
          ? 'पहले अपनी प्रोफ़ाइल पूरी करें।' : (j.detail || j.message || 'नहीं हो पाया।');
        btn.disabled = false; btn.textContent = '₹' + planOf(picked).price + ' — आगे बढ़ें';
      });
    };
  }

  /* ── State: signed up, money not seen yet ── */
  function payBox(d) {
    box.innerHTML = '<p class="vf-p vf-state">शुल्क की जानकारी ला रहे हैं…</p>';
    api('/verify/pay/' + encodeURIComponent(d.ref)).then(function(j) {
      var p = (j && j.data) || {};
      if (!p.configured) {
        box.innerHTML = '<p class="vf-p vf-state">पेमेंट अभी चालू नहीं है। कृपया कृषि मित्र टीम से संपर्क करें — +91 9870951001</p>';
        return;
      }
      box.innerHTML =
        '<div class="vf-state">' +
        '<p class="vf-p" style="margin-bottom:6px;"><b>अब ₹' + p.amount + ' भेजें</b> — ' +
          esc(d.term_hi || '') + '</p>' +
        (p.qr_svg ? '<div class="vf-qr">' + p.qr_svg + '</div>' : '') +
        '<p class="vf-p" style="font-size:12px;margin:4px 0 14px;">किसी भी UPI ऐप से स्कैन करें</p>' +
        '<a class="vf-btn" href="' + esc(p.link) + '">UPI ऐप खोलें</a>' +
        '<div class="vf-vpa">' + esc(p.vpa) + '</div>' +
        '<button class="vf-btn ghost" id="vf-paid">मैंने पैसे भेज दिए</button>' +
        '<p class="vf-ref">आपका नंबर: <b>' + esc(p.ref) + '</b></p>' +
        (p.pay_url ? '<p class="vf-muted" style="margin-bottom:6px;">किसी और के फ़ोन से पे करना है? ' +
          'उन्हें यह लिंक भेजें — उसमें यही QR है: <a href="' + esc(p.pay_url) + '">' +
          esc(p.pay_url.replace('https://', '')) + '</a></p>' : '') +
        '<p class="vf-muted">पैसा पहुँचते ही हम टिक चालू कर देंगे। UPI ऐप हमें अपने आप ' +
        'नहीं बताता कि पैसा आया है, इसलिए भेजने के बाद ऊपर वाला बटन दबा दें — ' +
        'आपका नंबर सबसे पहले जाँचा जाएगा।</p>' +
        '</div>';
      document.getElementById('vf-paid').onclick = function() {
        var btn = this; btn.disabled = true; btn.textContent = 'भेजा जा रहा है…';
        api('/verify/paid', { method: 'POST', body: JSON.stringify({}) })
          .then(function(j) {
            if (j && j.success) return render(j.data);
            btn.disabled = false; btn.textContent = 'मैंने पैसे भेज दिए';
          });
      };
    });
  }

  /* ── State: he says he paid, nobody has confirmed ── */
  function claimedBox(d) {
    box.innerHTML = '<div class="vf-state">' +
      '<p class="vf-h" style="font-size:18px;">हम आपका भुगतान जाँच रहे हैं</p>' +
      '<div class="vf-wait">आपने बताया कि आपने ₹' + (d.fee || '') + ' भेज दिए हैं। ' +
      'हम बैंक में देखकर टिक चालू कर देंगे। ज़्यादा देर लगे तो ' +
      '<b>+91 9870951001</b> पर बताइए।</div>' +
      '<p class="vf-ref">आपका नंबर: <b>' + esc(d.ref) + '</b></p></div>';
  }

  /* ── State: the tick is on ── */
  function activeBox(d) {
    box.innerHTML = '<div class="vf-state">' +
      '<span class="vf-tick">__TICK__ नीला टिक चालू है</span>' +
      '<p class="vf-p">आपके नाम के साथ नीला टिक दिख रहा है।' +
      (d.days_left != null ? (' यह <b>' + d.days_left + ' दिन</b> और चलेगा।') : '') + '</p>' +
      '<button class="vf-btn ghost" id="vf-extend">और समय के लिए बढ़ाएँ</button>' +
      '<p class="vf-muted">खत्म होने की तारीख़ यहीं दिखती है — समय रहते बढ़ा लें। अभी ' +
      'बढ़ाने पर बाकी दिन जुड़ जाते हैं, कटते नहीं।</p></div>';
    document.getElementById('vf-extend').onclick = function() { signupForm(d); };
  }

  function render(d) {
    if (!d || !d.status) return signupForm(d || {});
    if (d.active) return activeBox(d);
    if (d.status === 'applied') return d.payment_claimed ? claimedBox(d) : payBox(d);
    if (d.status === 'rejected') {
      box.innerHTML = '<div class="vf-state">' +
        '<p class="vf-h" style="font-size:18px;">आपका नीला टिक हटा दिया गया है</p>' +
        (d.reject_reason ? '<p class="vf-p">कारण: ' + esc(d.reject_reason) + '</p>' : '') +
        (d.paid ? ('<p class="vf-p">' + (d.refunded ? 'आपका शुल्क वापस भेज दिया गया है।'
          : 'आपका पूरा शुल्क 7 दिन के अंदर वापस भेजा जाएगा।') + '</p>') : '') +
        // Same procedure again — except while his fee is still on its way
        // back, when apply() refuses so the owed refund stays on the queue.
        (d.refund_pending
          ? '<p class="vf-muted">रिफंड पहुँचने के बाद आप फिर से आवेदन कर सकते हैं।</p>'
          : '<button class="vf-btn" id="vf-again">फिर से आवेदन करें</button>') +
        '<p class="vf-muted">कोई गलतफ़हमी लगे तो +91 9870951001 पर बात करें।</p></div>';
      var again = document.getElementById('vf-again');
      if (again) again.onclick = function() { signupForm(d); };
      return;
    }
    if (d.status === 'declined') {
      // Refused before any tick — so not "हटा दिया", and he may try again.
      box.innerHTML = '<div class="vf-state">' +
        '<p class="vf-h" style="font-size:18px;">आपका आवेदन स्वीकार नहीं हुआ</p>' +
        (d.reject_reason ? '<p class="vf-p">कारण: ' + esc(d.reject_reason) + '</p>' : '') +
        '<p class="vf-p">हमारे रिकॉर्ड में इस आवेदन का कोई भुगतान दर्ज नहीं है। शुल्क आपके ' +
        'खाते से कट गया हो तो UTR के साथ <b>+91 9870951001</b> पर बताइए — पैसा हमारे ' +
        'खाते में पहुँचा होगा तो पूरा वापस भेजा जाएगा।</p>' +
        '<button class="vf-btn" id="vf-again">फिर से आवेदन करें</button></div>';
      document.getElementById('vf-again').onclick = function() { signupForm(d); };
      return;
    }
    if (d.status === 'expired') {
      box.innerHTML = '<div class="vf-state">' +
        '<p class="vf-h" style="font-size:18px;">आपका नीला टिक खत्म हो गया</p>' +
        '<p class="vf-p">फिर से चालू करने के लिए कोई एक प्लान चुनें।</p>' +
        '<button class="vf-btn" id="vf-renew">फिर से चालू करें</button></div>';
      document.getElementById('vf-renew').onclick = function() { signupForm(d); };
      return;
    }
    signupForm(d);
  }

  api('/verify/me').then(function(j) {
    if (j && j.success) {
      var d = j.data || {};
      if (d.plan) picked = d.plan;
      render(d);
    } else loginWall();
  }).catch(loginWall);
})();
</script>"""


@router.get("/verify", response_class=HTMLResponse)
def verify_page():
    gets = "".join(f"<li>{escape(g)}</li>" for g in GETS_HI)
    body = (_BODY
            .replace("__PLANS__", json.dumps(seller_verify.plans(), ensure_ascii=False))
            .replace("__GETS__", gets)
            # TERMS_HI is our own fixed markup (<b> only), never user input.
            .replace("__TERMS__", "".join(f"<li>{t}</li>" for t in TERMS_HI))
            .replace("__MEANS__", escape(MEANS_HI))
            .replace("__TICK__", _TICK_SVG))

    return _doc(
        "नीला टिक — कृषि मित्र प्रीमियम",
        "कृषि बाज़ार में नीला टिक — कृषि मित्र प्रीमियम सदस्यता का निशान। "
        "पहचान या सौदे की गारंटी नहीं।",
        CANON, "", body, active="", extra_css=_CSS,
        robots="noindex, nofollow",
    )
