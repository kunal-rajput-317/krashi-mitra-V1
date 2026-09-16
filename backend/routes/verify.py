# ============================================================
# routes/verify.py
# /verify — the blue-tick funnel a farmer walks through himself.
# ============================================================
# Four states on one page, driven by his own application row:
#
#   none      → what the tick means, what is checked, the fee → apply form
#   applied   → "we have your application" + the UPI QR for the fee
#   paid      → "we will call you on <number>" — the review is pending
#   approved  → the tick, when it expires, and how to renew
#   rejected  → the reason, and the refund
#
# WHAT THIS PAGE MUST NEVER SAY. Not "पेमेंट हो गया" — a upi:// hand-off
# reports nothing back (services/upi.py), so only a human who saw the bank
# credit can say that. And not that paying earns the tick: the fee buys the
# check. Every word of copy here is written to keep the badge's public claim —
# "KrashiMitra द्वारा सत्यापित" — true. See services/seller_verify.py.
#
# noindex, always. It is a logged-in billing page; it has no business in a
# sitemap or a SERP, and a farmer reaching it from search instead of from his
# own profile would be reading someone else's funnel.
# ============================================================
from html import escape
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database.db import User, UserProfile, acct, get_db
from backend.routes.bhav import _doc
from backend.services import seller_verify, upi
from backend.utils.auth_utils import get_current_user

router = APIRouter()

CANON = "https://krashimitra.in/verify"

# What the tick is allowed to assert, in the words the page uses. Kept here as
# one string because it appears on this page AND has to stay in step with the
# note on krashi_bajar.html — if the check ever changes, both move together.
CHECKS_HI = [
    "आपका नाम और मोबाइल नंबर — फ़ोन पर बात करके",
    "आपका गाँव / ज़िला",
    "आपकी बताई गई पहचान (आधार / KCC / लाइसेंस) — सिर्फ़ देखी जाती है, रखी नहीं जाती",
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
    # The whole check is a phone call. Without a number there is nothing to do.
    digits = "".join(ch for ch in data["phone"] if ch.isdigit())
    if len(digits) < 10:
        raise HTTPException(400, "सही मोबाइल नंबर डालें — सत्यापन फ़ोन पर होता है।")

    row = seller_verify.apply(db, user_id, data)
    return {
        "success": True,
        "message": "आवेदन मिल गया। अब शुल्क भेजें — फिर हम आपको फ़ोन करेंगे।",
        "data": seller_verify.to_dict(row),
    }


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
    note = f"KrashiMitra verify {row.ref}"
    url = upi.link(amount, note=note, ref=row.ref)
    return {
        "configured": upi.configured(),
        "vpa":        upi.vpa(),
        "payee":      upi.payee_name(),
        "amount":     amount,
        "ref":        row.ref,
        "note":       note,
        "link":       url,
        "qr_svg":     upi.qr_svg(url),
    }


# ── The page ─────────────────────────────────────────────────

_CSS = """
.vf-wrap{max-width:560px;margin:0 auto;padding:8px 0 48px}
.vf-card{background:var(--white);border:1px solid var(--border);
border-radius:var(--radius-sm);padding:24px 20px;box-shadow:var(--shadow-sm);margin-bottom:14px}
.vf-tick{display:inline-flex;align-items:center;gap:7px;background:#e8f4fd;color:#1d9bf0;
border-radius:20px;padding:5px 13px;font-size:13px;font-weight:700;margin-bottom:12px}
.vf-h{font-size:21px;font-weight:800;color:var(--text-dark);margin:0 0 8px;line-height:1.35}
.vf-p{font-size:14px;color:var(--text-soft);line-height:1.65;margin:0 0 14px}
.vf-checks{list-style:none;padding:0;margin:0 0 16px}
.vf-checks li{position:relative;padding-left:26px;font-size:13.5px;line-height:1.6;
color:var(--text-dark);margin-bottom:8px}
.vf-checks li:before{content:'✓';position:absolute;left:0;top:0;color:var(--green-mid);font-weight:800}
.vf-note{background:#fff8e1;border:1px solid #ffe08a;border-radius:10px;padding:11px 13px;
font-size:12.5px;color:#7a5c00;line-height:1.6;margin-bottom:16px}
.vf-fee{font-size:34px;font-weight:800;color:var(--green-dark);line-height:1.1;margin:0}
.vf-fee-sub{font-size:12.5px;color:var(--text-soft);margin:2px 0 18px}
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
"""


@router.get("/verify", response_class=HTMLResponse)
def verify_page():
    checks = "".join(f"<li>{escape(c)}</li>" for c in CHECKS_HI)
    fee = seller_verify.fee()
    months = seller_verify.months()
    id_opts = "".join(
        f'<option value="{escape(k)}">{escape(seller_verify.ID_KIND_HI[k])}</option>'
        for k in seller_verify.ID_KINDS
    )

    body = f"""
<div class="vf-wrap">
  <div class="vf-card" id="vf-intro">
    <span class="vf-tick">✓ नीला टिक</span>
    <h1 class="vf-h">कृषि बाज़ार में सत्यापित विक्रेता बनें</h1>
    <p class="vf-p">नीले टिक का मतलब है कि कृषि मित्र ने आपसे बात करके आपकी पहचान जाँची है।
      खरीदार सत्यापित विक्रेता पर ज़्यादा भरोसा करते हैं।</p>
    <p class="vf-p" style="margin-bottom:8px;"><b>हम क्या जाँचते हैं:</b></p>
    <ul class="vf-checks">{checks}</ul>
    <div class="vf-note"><b>ध्यान दें —</b> शुल्क सत्यापन की जाँच का है, टिक का नहीं।
      फ़ोन पर जाँच पूरी होने के बाद ही टिक मिलता है। अगर जाँच में जानकारी गलत निकली
      तो टिक नहीं मिलेगा और <b>पूरा शुल्क वापस</b> कर दिया जाएगा।</div>
    <p class="vf-fee">₹{fee}</p>
    <p class="vf-fee-sub">{months} महीने के लिए · एक बार</p>
  </div>

  <div class="vf-card" id="vf-body">
    <p class="vf-p vf-state" id="vf-loading">एक पल…</p>
  </div>
</div>

<script>
(function() {{
  var FEE = {fee}, MONTHS = {months};
  var API = (window.KRASHIMITRA_API_BASE || '');
  var tok = null;
  try {{ tok = localStorage.getItem('krishi_token'); }} catch (e) {{}}
  var box = document.getElementById('vf-body');
  var esc = function(s) {{
    return String(s == null ? '' : s).replace(/[&<>"']/g, function(c) {{
      return {{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c];
    }});
  }};

  function api(path, opts) {{
    opts = opts || {{}};
    opts.headers = Object.assign({{'Content-Type': 'application/json'}}, opts.headers || {{}});
    if (tok) opts.headers['Authorization'] = 'Bearer ' + tok;
    return fetch(API + path, opts).then(function(r) {{
      return r.json().then(function(j) {{ j._status = r.status; return j; }});
    }});
  }}

  if (!tok) {{
    box.innerHTML = '<p class="vf-p vf-state">सत्यापन के लिए पहले लॉगिन करें।</p>' +
      '<a class="vf-btn" href="/login.html?next=/verify">लॉगिन करें</a>';
    return;
  }}

  function applyForm(d) {{
    box.innerHTML =
      '<div class="vf-field"><label>पूरा नाम</label><input id="vf-name" value="' + esc(d.full_name || '') + '" placeholder="जैसे: राम सिंह"></div>' +
      '<div class="vf-field"><label>मोबाइल नंबर</label><input id="vf-phone" inputmode="numeric" value="' + esc(d.phone || '') + '" placeholder="10 अंक"></div>' +
      '<div class="vf-field"><label>गाँव</label><input id="vf-village" value="' + esc(d.village || '') + '"></div>' +
      '<div class="vf-field"><label>ज़िला</label><input id="vf-district" value="' + esc(d.district || '') + '"></div>' +
      '<div class="vf-field"><label>कौन सी पहचान दिखा सकते हैं?</label><select id="vf-id">{id_opts}</select></div>' +
      '<div class="vf-field"><label>कुछ और बताना हो (ज़रूरी नहीं)</label><textarea id="vf-note" rows="2"></textarea></div>' +
      '<button class="vf-btn" id="vf-submit">आवेदन भेजें</button>' +
      '<p class="vf-muted">आवेदन भेजने के बाद अगला कदम शुल्क भेजना है। हम उसी नंबर पर फ़ोन करेंगे।</p>' +
      '<div class="vf-err" id="vf-err" style="display:none;"></div>';
    document.getElementById('vf-submit').onclick = function() {{
      var btn = this; btn.disabled = true; btn.textContent = 'भेजा जा रहा है…';
      api('/verify/apply', {{ method: 'POST', body: JSON.stringify({{
        full_name: document.getElementById('vf-name').value,
        phone:     document.getElementById('vf-phone').value,
        village:   document.getElementById('vf-village').value,
        district:  document.getElementById('vf-district').value,
        id_kind:   document.getElementById('vf-id').value,
        note:      document.getElementById('vf-note').value
      }}) }}).then(function(j) {{
        if (j.success) return render(j.data);
        var e = document.getElementById('vf-err');
        e.style.display = 'block';
        e.textContent = (j.detail === 'PROFILE_REQUIRED')
          ? 'पहले अपनी प्रोफ़ाइल पूरी करें।' : (j.detail || j.message || 'नहीं हो पाया।');
        btn.disabled = false; btn.textContent = 'आवेदन भेजें';
      }});
    }};
  }}

  function payBox(d) {{
    box.innerHTML = '<p class="vf-p vf-state">शुल्क की जानकारी ला रहे हैं…</p>';
    api('/verify/pay/' + encodeURIComponent(d.ref)).then(function(j) {{
      var p = (j && j.data) || {{}};
      if (!p.configured) {{
        box.innerHTML = '<p class="vf-p vf-state">पेमेंट अभी चालू नहीं है। कृपया कृषि मित्र टीम से संपर्क करें — +91 9870951001</p>';
        return;
      }}
      box.innerHTML =
        '<div class="vf-state">' +
        '<p class="vf-p" style="margin-bottom:6px;"><b>आवेदन मिल गया।</b> अब ₹' + p.amount + ' शुल्क भेजें।</p>' +
        (p.qr_svg ? '<div class="vf-qr">' + p.qr_svg + '</div>' : '') +
        '<p class="vf-p" style="font-size:12px;margin:4px 0 14px;">किसी भी UPI ऐप से स्कैन करें</p>' +
        '<a class="vf-btn" href="' + esc(p.link) + '">UPI ऐप खोलें</a>' +
        '<div class="vf-vpa">' + esc(p.vpa) + '</div>' +
        '<p class="vf-ref">आपका आवेदन नंबर: <b>' + esc(p.ref) + '</b></p>' +
        '<p class="vf-muted">पैसा पहुँचने के बाद हम आपके नंबर पर फ़ोन करेंगे और जाँच पूरी होते ही टिक चालू कर देंगे। ' +
        'शुल्क भेजने भर से टिक नहीं मिलता।</p>' +
        '</div>';
    }});
  }}

  function render(d) {{
    if (!d || !d.status) return applyForm(d || {{}});
    if (d.status === 'applied') return payBox(d);
    if (d.status === 'paid') {{
      box.innerHTML = '<div class="vf-state">' +
        '<p class="vf-h" style="font-size:18px;">शुल्क मिल गया — अब जाँच बाकी है</p>' +
        '<p class="vf-p">हम <b>' + esc(d.phone || 'आपके नंबर') + '</b> पर फ़ोन करेंगे। ' +
        'बात होने और पहचान जाँचने के बाद नीला टिक चालू कर दिया जाएगा।</p>' +
        '<p class="vf-ref">आवेदन नंबर: <b>' + esc(d.ref) + '</b></p></div>';
      return;
    }}
    if (d.status === 'approved') {{
      box.innerHTML = '<div class="vf-state">' +
        '<span class="vf-tick">✓ सत्यापित</span>' +
        '<p class="vf-p">आपका नीला टिक चालू है। ' +
        (d.days_left != null ? ('यह <b>' + d.days_left + ' दिन</b> और चलेगा।') : '') + '</p>' +
        '<p class="vf-muted">खत्म होने से पहले हम आपको याद दिला देंगे।</p></div>';
      return;
    }}
    if (d.status === 'rejected') {{
      box.innerHTML = '<div class="vf-state">' +
        '<p class="vf-h" style="font-size:18px;">इस बार टिक नहीं मिला</p>' +
        (d.reject_reason ? '<p class="vf-p">कारण: ' + esc(d.reject_reason) + '</p>' : '') +
        (d.paid ? ('<p class="vf-p">' + (d.refunded ? 'आपका शुल्क वापस भेज दिया गया है।'
          : 'आपका पूरा शुल्क वापस भेजा जा रहा है।') + '</p>') : '') +
        '<button class="vf-btn" id="vf-again">फिर से आवेदन करें</button></div>';
      document.getElementById('vf-again').onclick = function() {{ applyForm(d); }};
      return;
    }}
    if (d.status === 'expired') {{
      box.innerHTML = '<div class="vf-state">' +
        '<p class="vf-h" style="font-size:18px;">आपका टिक खत्म हो गया</p>' +
        '<p class="vf-p">फिर से चालू करने के लिए ₹' + FEE + ' भेजें — जाँच दोबारा होगी।</p>' +
        '<button class="vf-btn" id="vf-renew">फिर से चालू करें</button></div>';
      document.getElementById('vf-renew').onclick = function() {{ applyForm(d); }};
      return;
    }}
    applyForm(d);
  }}

  api('/verify/me').then(function(j) {{
    if (j && j.success) render(j.data);
    else box.innerHTML = '<p class="vf-p vf-state">सत्यापन के लिए पहले लॉगिन करें।</p>' +
      '<a class="vf-btn" href="/login.html?next=/verify">लॉगिन करें</a>';
  }});
}})();
</script>"""

    return _doc(
        "सत्यापित विक्रेता बनें — कृषि मित्र",
        "कृषि बाज़ार में नीला टिक — कृषि मित्र फ़ोन पर आपकी पहचान जाँचता है।",
        CANON, "", body, active="", extra_css=_CSS,
        robots="noindex, nofollow",
    )
