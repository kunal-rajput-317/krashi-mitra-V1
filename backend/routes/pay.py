# ============================================================
# routes/pay.py
# /pay and everything under it — the one place anybody pays कृषि मित्र.
#
#   /pay                    the hub: every way to pay, calm and short. No QR.
#   /pay/{source}/{key}     one payer's page: name, amount, QR, UPI ID.
#   /pay?d=<slug>           old dealer links already sent on WhatsApp → 301.
#   /donate                 removed 2026-09-26 → 410 Gone.
#
# The URL shapes and the source table live in services/pay_links.py.
#
# The rail is a upi:// deep link and a QR of the same link (services/upi.py).
# There is no gateway, no card form, and no field on these pages that accepts
# anything sensitive: the payer taps through to his own UPI app and the money
# moves bank-to-bank. Nothing here touches money, so nothing here can leak it.
#
# WHAT THESE PAGES MUST NEVER CLAIM. A upi:// hand-off reports nothing back, so
# no page can know whether payment happened and none may say it did. Each one
# renders a request to pay. Settlement is seen in the owner's bank app and
# typed into the admin panel by hand — a page that printed "पेमेंट हो गया" off
# a tapped link would be inventing a receipt.
#
# ONE PAYER OR NO QR. The hub names nobody, so it shows no QR and no UPI ID.
# Money that arrives with no payer attached cannot be matched to a row: nobody
# can be marked paid for it and the payer has to be chased for a screenshot to
# learn who they were. That is why the old generic /pay became a dead end
# (2026-08-04) and why /donate went (2026-09-26). An unknown key renders the
# same dead end, never a generic fee.
#
# noindex, always. The hub is reached from the footer and has nothing to rank
# for; a payer's page is a private billing link reached from WhatsApp.
# ============================================================
from datetime import datetime
from html import escape
from urllib.parse import quote

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

from backend.database.db import Buyer, SessionLocal, Sponsor
from backend.routes.bhav import _doc
from backend.services import pay_links, upi

router = APIRouter()

PHONE_TEL = "tel:+919870951001"
PHONE_TXT = "+91 98709 51001"
WA = "https://wa.me/919870951001"

_PAY_CSS = """
.pay-wrap{max-width:520px;margin:0 auto;padding:8px 0 44px}
.pay-card{background:var(--white);border:1px solid var(--border);
border-radius:var(--radius-sm);padding:26px 22px;text-align:center;
box-shadow:var(--shadow-sm)}
.pay-for{font-size:12.5px;color:var(--text-soft);margin:0 0 4px;letter-spacing:.02em}
.pay-for + .pay-amt{margin-top:12px}
.pay-name{font-size:20px;font-weight:700;color:var(--text-dark);margin:0 0 2px;line-height:1.4}
.pay-place{font-size:13px;color:var(--text-soft);margin:0 0 18px}
.pay-amt{font-size:40px;font-weight:800;color:var(--green-dark);margin:0;line-height:1.1}
.pay-amt-sub{font-size:12.5px;color:var(--text-soft);margin:4px 0 20px}
.pay-qr{display:inline-block;padding:14px;background:#fff;border:1px solid var(--border);
border-radius:var(--radius-sm);line-height:0;margin-bottom:6px}
.pay-qr svg{width:190px;height:190px;display:block}
.pay-scan{font-size:12px;color:var(--text-soft);margin:0 0 18px}
.pay-btn{display:block;width:100%;padding:15px 18px;background:var(--green-dark);color:#fff;
border:0;border-radius:var(--radius-sm);font-size:16px;font-weight:700;text-decoration:none;
cursor:pointer;box-shadow:var(--shadow-sm);font-family:inherit}
.pay-btn:hover{background:var(--green-mid)}
.pay-or{font-size:12px;color:var(--text-soft);margin:16px 0 8px}
.pay-vpa{display:flex;gap:8px;align-items:center;justify-content:center;flex-wrap:wrap;
padding:11px 14px;background:var(--green-pale);border-radius:var(--radius-sm);
font-family:var(--font-mono,monospace);font-size:14px;color:var(--text-dark);
word-break:break-all}
.pay-copy{padding:6px 12px;background:var(--white);border:1px solid var(--border);
border-radius:6px;font-size:12px;cursor:pointer;font-family:inherit;color:var(--text-mid);
flex-shrink:0}
.pay-copy:hover{border-color:var(--green-mid);color:var(--green-dark)}
.pay-ref{margin:14px 0 0;font-size:12.5px;color:var(--text-soft)}
.pay-ref b{font-family:var(--font-mono,monospace);color:var(--text-dark);letter-spacing:.02em;
word-break:break-all}
.pay-after{margin-top:20px;padding:14px 16px;background:var(--cream,#faf8f2);
border:1px solid var(--border);border-radius:var(--radius-sm);font-size:13px;
color:var(--text-mid);line-height:1.8;text-align:left}
.pay-after b{color:var(--text-dark)}
.pay-after a,.pay-help a,.pay-off a{color:var(--green-dark);font-weight:600}
.pay-help{margin:20px 4px 0;font-size:12.5px;color:var(--text-soft);line-height:1.8;text-align:center}
.pay-off{padding:18px;background:var(--cream,#faf8f2);border:1px solid var(--border);
border-radius:var(--radius-sm);font-size:14px;color:var(--text-mid);line-height:1.8;text-align:left}

/* ── The hub ── calm: one column, lots of air, no colour but the prices ── */
.pay-hero{padding:14px 4px 6px}
.pay-hero h1{font-size:24px;font-weight:800;color:var(--text-dark);margin:0 0 8px;line-height:1.35}
.pay-hero p{font-size:14.5px;color:var(--text-soft);line-height:1.7;margin:0}
.pay-list{list-style:none;margin:18px 0 0;padding:0;border-top:1px solid var(--border)}
.pay-list li{border-bottom:1px solid var(--border)}
.pay-row{display:grid;grid-template-columns:1fr auto;gap:3px 14px;align-items:center;
padding:17px 4px;text-decoration:none;color:inherit}
.pay-row:hover .pay-row-t{color:var(--green-dark)}
.pay-row-t{font-size:15.5px;font-weight:700;color:var(--text-dark);line-height:1.45}
.pay-row-s{grid-column:1;font-size:13px;color:var(--text-soft);line-height:1.6}
.pay-row-p{grid-column:1;font-size:13px;font-weight:700;color:var(--green-dark);line-height:1.6}
.pay-row-go{grid-column:2;grid-row:1 / span 3;font-size:20px;color:var(--text-light,#9aa5a0)}
.pay-got{margin:26px 0 0;padding:16px 18px;background:var(--green-pale);
border-radius:var(--radius-sm);font-size:13.5px;color:var(--text-mid);line-height:1.75}
.pay-got b{color:var(--text-dark)}

@media(max-width:480px){.pay-card{padding:22px 16px}.pay-amt{font-size:34px}
.pay-qr svg{width:170px;height:170px}.pay-hero h1{font-size:22px}}
"""

_COPY_JS = """<script>
function kmCopyVpa(btn){
  var t = document.getElementById('pay-vpa-text');
  if(!t) return;
  var done = function(){ var o = btn.textContent; btn.textContent = '✓ कॉपी हो गया';
    setTimeout(function(){ btn.textContent = o; }, 1800); };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(t.textContent).then(done).catch(function(){});
  } else {
    /* Older Android WebViews have no clipboard API — select the text so the
       payer can long-press copy rather than retype a VPA by hand. */
    var r = document.createRange(); r.selectNodeContents(t);
    var s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
  }
}
</script>"""

# Said on every payable page, in the same words. The last line matters on a
# page that asks a farmer for money: nothing here is a government fee.
_HELP = (
    f'<p class="pay-help">कोई दिक्कत हो तो कॉल करें — <a href="{PHONE_TEL}">{PHONE_TXT}</a><br>'
    'पैसा UPI से सीधे कृषि मित्र के बैंक खाते में जाता है। हम कभी कार्ड नंबर, OTP या UPI PIN '
    'नहीं माँगते।<br>कृषि मित्र एक निजी वेबसाइट है, सरकारी नहीं। '
    '<a href="/terms">शुल्क और रिफ़ंड के नियम</a></p>')


def _page(title: str, body: str, canon: str, status: int = 200) -> HTMLResponse:
    resp = _doc(title[:68], "कृषि मित्र को भुगतान — UPI से, सीधे बैंक खाते में।",
                canon, "", f'<div class="pay-wrap">{body}</div>', active="",
                extra_css=_PAY_CSS, robots="noindex, nofollow", journey=False)
    resp.status_code = status
    return resp


def _dead_end(message: str, canon: str) -> HTMLResponse:
    return _page("पेमेंट — कृषि मित्र",
                 f'<div class="pay-card"><div class="pay-off">{message}</div></div>{_HELP}',
                 canon)


def _incomplete(canon: str) -> HTMLResponse:
    return _dead_end(
        '<b>यह पेमेंट लिंक अधूरा है।</b><br>'
        'कृपया वही लिंक खोलें जो कृषि मित्र टीम ने आपको WhatsApp पर भेजा था, '
        f'या हमें कॉल करें — <a href="{PHONE_TEL}">{PHONE_TXT}</a><br>'
        '<a href="/pay">पेमेंट के सभी तरीके देखें →</a>', canon)


def _unconfigured(canon: str) -> HTMLResponse:
    # Never a fabricated VPA to keep the page pretty — a wrong destination
    # silently sends a payer's money to a stranger.
    return _dead_end(
        '<b>पेमेंट अभी चालू नहीं है।</b><br>'
        f'कृपया कृषि मित्र टीम से संपर्क करें — <a href="{PHONE_TEL}">{PHONE_TXT}</a>',
        canon)


def _date(dt) -> str:
    return dt.strftime("%d-%m-%Y") if dt else ""


# ── The hub ──────────────────────────────────────────────────

def _hub_rows() -> list[tuple[str, str, str, str]]:
    """(href, title, one line, price) — prices from the same functions the
    pages that sell them use, never typed here, so the hub cannot quote a
    figure the next page contradicts."""
    from backend.services import placements, seller_verify
    tick = " · ".join(f"₹{p['price']} / {p['months']} महीने" if p["months"] > 1
                      else f"₹{p['price']} / महीना" for p in seller_verify.plans())
    wa_dukan = WA + "?text=" + quote("कृषि मित्र पर अपनी दुकान लिस्ट करनी है")
    wa_rent = WA + "?text=" + quote("कृषि मित्र पर अपनी मशीन किराये के लिए लिस्ट करनी है")
    return [
        ("/bluetick", "नीला टिक — कृषि मित्र प्रीमियम",
         "आपके नाम और फ़ोटो पर नीला टिक। यह सदस्यता है, पहचान की जाँच नहीं।", tick),
        ("/dukanlisting", "मंडी भाव पेज पर लिस्टिंग",
         "खाद-बीज डीलर और व्यापारी — अपने ज़िले के भाव पेज पर दिखें।",
         f"₹{placements.PRICE_DISTRICT} प्रति ज़िला + ₹{placements.PRICE_CROP} प्रति फ़सल · "
         f"{placements.SEASON_MONTHS} महीने"),
        (wa_dukan, "कृषि दुकान लिस्टिंग",
         "अपनी दुकान और सामान कृषि दुकान पर दिखाएँ।", "शुल्क बात करके तय"),
        (wa_rent, "किराये की मशीन लिस्टिंग",
         "ट्रैक्टर, थ्रेशर जैसी मशीनें किराये पर दें।", "शुल्क बात करके तय"),
        ("/sponsor", "विज्ञापन · प्रायोजक",
         "कंपनियों के लिए — साफ़ लिखा “प्रायोजक” वाला स्थान।", "रेट कार्ड देखें"),
    ]


def _hub() -> HTMLResponse:
    rows = "".join(
        f'<li><a class="pay-row" href="{escape(href, quote=True)}">'
        f'<span class="pay-row-t">{escape(t)}</span>'
        f'<span class="pay-row-s">{escape(s)}</span>'
        f'<span class="pay-row-p">{escape(p)}</span>'
        f'<span class="pay-row-go" aria-hidden="true">›</span></a></li>'
        for href, t, s, p in _hub_rows())
    body = f"""<div class="pay-hero">
<h1>पेमेंट</h1>
<p>मंडी भाव, मौसम और खेती की सलाह मुफ़्त हैं। शुल्क सिर्फ़ इन चीज़ों का है —</p>
</div>
<ul class="pay-list">{rows}</ul>
<div class="pay-got">
<b>पेमेंट लिंक मिला है?</b> वही लिंक खोलें जो हमने WhatsApp पर भेजा था — उसमें आपका
नाम, राशि और QR होता है। लिंक खो गया हो तो <a href="{WA}">WhatsApp</a> करें, दोबारा भेज देंगे।
</div>
{_HELP}"""
    return _page("पेमेंट — कृषि मित्र", body, f"{pay_links.SITE}/pay")


@router.get("/pay", response_class=HTMLResponse)
def pay_hub(d: str = "", amount: str = ""):
    # Dealer links sent before 2026-09-26 were /pay?d=<slug>&amount=<n>. They
    # are in people's WhatsApp chats, so they keep working — as a redirect to
    # the one URL shape everything now uses.
    if d.strip():
        target = f"/pay/listing/{quote(d.strip()[:80], safe='')}"
        amt = upi.clean_amount(amount, default=0) if amount else 0
        return RedirectResponse(f"{target}?amount={amt}" if amt else target, status_code=301)
    return _hub()


@router.get("/donate", response_class=HTMLResponse)
def donate_gone():
    """Removed 2026-09-26: a gift from nobody in particular is money no row can
    be matched to. 410, not 404, so Google drops the URL instead of retrying."""
    body = ('<div class="pay-card"><div class="pay-off"><b>यह पेज हटा दिया गया है।</b><br>'
            'कृषि मित्र अब दान नहीं लेता। '
            '<a href="/pay">पेमेंट के सभी तरीके देखें →</a></div></div>')
    return _page("पेज हटा दिया गया — कृषि मित्र", body, f"{pay_links.SITE}/donate", status=410)


# ── One payer ────────────────────────────────────────────────

def _lookup(source: str, key: str, amount: str) -> dict | None:
    """Everything the page needs about one payer, as plain values (the session
    closes before rendering). None = nobody by that key.

    Fails soft: Neon asleep must not turn a payment page into an error page —
    it reads as an incomplete link and the payer is pointed at the phone."""
    if source == "link":
        req = pay_links.read_link(key)
        if not req:
            return None
        issued = ""
        try:
            issued = _date(datetime.strptime(req["issued"], "%Y-%m-%d"))
        except ValueError:
            pass
        return {"name": req["payer"], "place": "", "amount": req["amount"],
                "for": req["purpose"], "period": "",
                "status": f"यह लिंक {issued} को बना।" if issued else "",
                "ref": req["ref"], "note": f"KrashiMitra {req['purpose']}"}

    db = None
    try:
        db = SessionLocal()
        return _LOOKUPS[source](db, key, amount)
    except Exception:
        return None
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass


def _amount(raw: str, fallback) -> int:
    """An explicit ?amount= wins — it is how a renewal or a negotiated rate is
    sent, and the admin panel puts the figure it quoted onto the link itself.
    Clamped either way, so a hand-edited URL cannot conjure a ₹0 QR."""
    fallback = upi.clean_amount(fallback) if fallback else upi.DEFAULT_AMOUNT
    return upi.clean_amount(raw, default=fallback) if raw else fallback


def _running(until) -> str:
    if until and until > datetime.utcnow():
        return f"अभी {_date(until)} तक चालू है — यह पेमेंट उसके आगे की अवधि के लिए है।"
    return ""


def _listing(db, key, amount):
    from backend.services import dealers, placements
    row = db.query(Buyer).filter(Buyer.slug == key.strip()[:80]).first()
    if not row or not (row.name or "").strip():
        return None
    # A /dukanlisting account owes its own district count (dealers.quote), not
    # the flat KM_LISTING_FEE that has nothing to do with it.
    own = dealers.account_price(db, row.owner_user_id) if row.owner_user_id else None
    return {"name": row.name.strip(), "place": (row.district or "").strip(),
            "amount": _amount(amount, own), "for": pay_links.SOURCES["listing"][0],
            "period": (f"{placements.SEASON_MONTHS} महीने के लिए" if row.owner_user_id else ""),
            "status": _running(row.paid_until), "ref": pay_links.ref("listing", row.slug)}


def _dukan(db, key, amount):
    from backend.services import krashi_dukan
    row = krashi_dukan.shop_get(db, key)
    if not row or not (row.name or "").strip():
        return None
    return {"name": row.name.strip(), "place": (row.district or "").strip(),
            "amount": _amount(amount, None), "for": pay_links.SOURCES["dukan"][0],
            "period": "", "status": _running(getattr(row, "paid_until", None)),
            "ref": pay_links.ref("dukan", row.slug)}


def _rent(db, key, amount):
    from backend.services import rental
    row = rental.provider_get(db, key)
    if not row or not (row.name or "").strip():
        return None
    return {"name": row.name.strip(), "place": (row.district or "").strip(),
            "amount": _amount(amount, None), "for": pay_links.SOURCES["rent"][0],
            "period": "", "status": _running(getattr(row, "paid_until", None)),
            "ref": pay_links.ref("rent", row.slug)}


def _sponsor(db, key, amount):
    row = db.query(Sponsor).filter(Sponsor.slug == key.strip()[:80]).first()
    if not row or not (row.name or "").strip():
        return None
    # No agreed figure and none on the link → nothing to charge. A sponsor is
    # never shown the dealer listing fee as a default.
    amt = upi.clean_amount(amount or row.amount or 0, default=0)
    if not amt:
        return None
    return {"name": row.name.strip(), "place": "", "amount": amt,
            "for": pay_links.SOURCES["sponsor"][0], "period": "",
            "status": "", "ref": pay_links.ref("sponsor", row.slug)}


def _tick(db, key, amount):
    """The member's name is NOT shown — the ref is enough to pay against, and
    a private person's name has no business on a URL anyone can open."""
    from backend.services import seller_verify
    row = seller_verify.by_ref(db, key)
    if not row:
        return None
    chosen = seller_verify.plan(row.plan)
    out = {"name": "", "place": "", "amount": row.fee_amount or chosen["price"],
           "for": pay_links.SOURCES["tick"][0], "period": chosen["term_hi"],
           "status": "", "ref": pay_links.ref("tick", row.ref),
           "note": f"KrashiMitra premium {row.ref}", "tick_ref": row.ref}
    if seller_verify.is_active(row):
        out["closed"] = (f"आपका नीला टिक {_date(row.valid_until)} तक चालू है। "
                         "आगे बढ़ाने के लिए <a href=\"/verify\">नीला टिक पेज</a> खोलें।")
    elif row.status != seller_verify.APPLIED:
        out["closed"] = ("यह आवेदन अब खुला नहीं है। नया शुरू करने के लिए "
                         "<a href=\"/verify\">नीला टिक पेज</a> खोलें।")
    return out


_LOOKUPS = {"listing": _listing, "dukan": _dukan, "rent": _rent,
            "sponsor": _sponsor, "tick": _tick}


@router.get("/pay/{source}/{key}", response_class=HTMLResponse)
def pay_page(source: str, key: str, amount: str = ""):
    canon = f"{pay_links.SITE}/pay/{source}"
    if source not in pay_links.SOURCES:
        return _incomplete(canon)
    if not upi.configured():
        return _unconfigured(canon)
    info = _lookup(source, key, amount)
    if not info:
        return _incomplete(canon)
    if info.get("closed"):
        return _dead_end(info["closed"], canon)

    amt = info["amount"]
    if "note" in info:
        link = upi.link(amt, note=info["note"], ref=info["ref"])
        pack = {"amount": upi.clean_amount(amt), "link": link, "vpa": upi.vpa(),
                "qr_svg": upi.qr_svg(link)}
    else:
        pack = upi.collect(info["name"], info["place"], amount=amt, ref=info["ref"])

    name = (f'<h2 class="pay-name">{escape(info["name"])}</h2>' if info["name"] else "")
    place = (f'<p class="pay-place">{escape(info["place"])}</p>'
             if info["name"] or info["place"] else "")
    sub = " · ".join(x for x in (info["period"], "कोई अतिरिक्त चार्ज नहीं") if x)
    status = (f'<p class="pay-amt-sub">{escape(info["status"])}</p>' if info["status"] else "")
    qr = (f'<div class="pay-qr">{pack["qr_svg"]}</div>'
          '<p class="pay-scan">किसी भी UPI ऐप से QR स्कैन करें</p>' if pack["qr_svg"] else "")
    shown_ref = info.get("tick_ref") or info["ref"]

    if source == "tick":
        after = ('<b>पेमेंट के बाद:</b> <a href="/bluetick">नीला टिक पेज</a> पर '
                 '“मैंने पैसे भेज दिए” दबाएँ। पैसा पहुँचते ही टिक चालू हो जाएगा।<br>'
                 'नीला टिक प्रीमियम सदस्यता का निशान है — यह पहचान की जाँच या फसल, भाव '
                 'या सौदे की गारंटी नहीं है।')
    else:
        after = ('<b>पेमेंट के बाद:</b> स्क्रीनशॉट या UPI रेफरेंस नंबर WhatsApp पर भेज दीजिए — '
                 f'<a href="{WA}">{PHONE_TXT}</a>।')

    body = f"""<div class="pay-card">
<p class="pay-for">{escape(info["for"])}</p>
{name}{place}
<p class="pay-amt">₹{pack["amount"]}</p>
<p class="pay-amt-sub">{escape(sub)}</p>
{status}
{qr}
<a class="pay-btn" href="{escape(pack["link"], quote=True)}">UPI ऐप में पे करें</a>
<p class="pay-or">या यह UPI ID कॉपी करके किसी भी ऐप में भेजें</p>
<div class="pay-vpa">
  <span id="pay-vpa-text">{escape(pack["vpa"])}</span>
  <button class="pay-copy" type="button" onclick="kmCopyVpa(this)">कॉपी</button>
</div>
<p class="pay-ref">आपका नंबर: <b>{escape(shown_ref)}</b></p>
<div class="pay-after">{after}</div>
</div>
{_HELP}
{_COPY_JS}"""
    who = info["name"] or info["for"]
    return _page(f"₹{pack['amount']} पेमेंट — {who}", body, canon)
