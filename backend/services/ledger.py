# ============================================================
# services/ledger.py
# हिसाब — one append-only record of every rupee in and out.
#
# WHY IT EXISTS. Money arrives through five features (dealer listing fee,
# कृषि दुकान, rental, नीला टिक, sponsors), and each kept only its LATEST
# payment on its own row: paid_at / paid_amount / payment_ref. A renewal
# overwrote the payment before it, so the first ₹500 a dealer ever paid was
# gone the day he paid the second. Income tax and GST are filed from the full
# list — who paid, how much, when, and the UPI reference — so the full list
# has to exist somewhere. This is it.
#
# THE RULES:
#   • Append-only. record() adds a row; nothing edits or deletes one. A wrong
#     entry is VOIDED with a reason, and still shows in the export as voided,
#     because "the ledger quietly lost a row" is exactly the question a tax
#     officer asks about.
#   • A refund is a NEGATIVE row, never an edit of the payment it reverses.
#   • Only money a human saw land is recorded — the same rule every
#     record_payment() already follows (see services/upi.py). Nothing here is
#     ever called from a upi:// hand-off or a farmer's "I have paid" claim.
#   • record() does not commit. It is called inside each feature's own
#     record_payment(), before that function's commit, so the feature row and
#     its ledger row land together or not at all.
#
# Also answers the one number the owner has to watch: income this financial
# year against the ₹20 lakh GST registration threshold. Every source counts
# toward that limit, AdSense included — so AdSense and any bank transfer that
# did not go through a feature are keyed in by hand (source "adsense"/"other").
# ============================================================
from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta

from backend.database.db import (Buyer, DukanShop, Payment, RentalProvider,
                                 SellerVerification, Sponsor)

# key → label shown in the admin panel and the CSV.
SOURCES = {
    "dealer":   "खरीदार / Dealer listing",
    "dukan":    "कृषि दुकान",
    "rental":   "किराये की मशीन",
    "verify":   "नीला टिक / प्रीमियम",
    "sponsor":  "प्रायोजक / Sponsor",
    "adsense":  "Google AdSense",
    "donation": "सहयोग / Donation",
    "leads":    "Leads",
    "other":    "अन्य / Other",
}
METHODS = ("upi", "bank", "other")

# GST registration becomes mandatory once aggregate turnover in a financial
# year crosses this (services, most states). The panel warns well before it.
GST_LIMIT = 20_00_000
GST_WARN_AT = 15_00_000

_IST = timedelta(hours=5, minutes=30)


def _clip(v, n: int) -> str | None:
    v = (str(v).strip() if v is not None else "")[:n]
    return v or None


def record(db, source: str, amount: int, *, payer: str = "", contact: str = "",
           ref: str = "", method: str = "upi", note: str = "",
           source_key: str = "", received_at: datetime | None = None,
           origin: str = "live") -> Payment:
    """Add one row. Does NOT commit — the caller's commit carries it."""
    if source not in SOURCES:
        raise ValueError(f"unknown source {source!r}")
    amt = int(amount)
    if amt == 0:
        raise ValueError("amount must not be zero")
    row = Payment(
        received_at=received_at or datetime.utcnow(),
        amount=amt,
        source=source,
        source_key=_clip(source_key, 120),
        payer=_clip(payer, 160),
        contact=_clip(contact, 120),
        ref=_clip(ref, 80),
        method=method if method in METHODS else "other",
        note=_clip(note, 1000),
        origin=origin,
    )
    db.add(row)
    return row


def void(db, pid: int, reason: str) -> Payment | None:
    row = db.query(Payment).filter(Payment.id == int(pid)).first()
    if not row or row.voided_at:
        return row
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("a void needs a reason")
    row.voided_at = datetime.utcnow()
    row.void_reason = reason[:300]
    db.commit()
    db.refresh(row)
    return row


# ── financial year (India: 1 April – 31 March) ─────────────────────────────

def fy_of(dt: datetime) -> str:
    """'2026-27' for any moment from 1 Apr 2026 to 31 Mar 2027, in IST."""
    d = dt + _IST
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def fy_bounds(fy: str) -> tuple[datetime, datetime]:
    """UTC [start, end) of a financial year like '2026-27'."""
    start = int(fy.split("-")[0])
    return (datetime(start, 4, 1) - _IST, datetime(start + 1, 4, 1) - _IST)


def current_fy() -> str:
    return fy_of(datetime.utcnow())


# ── reading ───────────────────────────────────────────────────────────────

def out(p: Payment) -> dict:
    ist = p.received_at + _IST
    return {
        "id": p.id, "date": ist.strftime("%Y-%m-%d"), "time": ist.strftime("%H:%M"),
        "amount": p.amount, "source": p.source,
        "source_label": SOURCES.get(p.source, p.source),
        "source_key": p.source_key or "", "payer": p.payer or "",
        "contact": p.contact or "", "ref": p.ref or "", "method": p.method or "",
        "note": p.note or "", "origin": p.origin,
        "voided": bool(p.voided_at),
        "void_reason": p.void_reason or "",
        "fy": fy_of(p.received_at),
    }


def rows(db, fy: str | None = None, source: str | None = None,
         include_void: bool = True) -> list[Payment]:
    q = db.query(Payment)
    if fy:
        a, b = fy_bounds(fy)
        q = q.filter(Payment.received_at >= a, Payment.received_at < b)
    if source:
        q = q.filter(Payment.source == source)
    if not include_void:
        q = q.filter(Payment.voided_at.is_(None))
    return q.order_by(Payment.received_at.desc(), Payment.id.desc()).all()


def summary(db, fy: str | None = None) -> dict:
    fy = fy or current_fy()
    live = rows(db, fy, include_void=False)
    total = sum(p.amount for p in live)
    by_source: dict[str, int] = {}
    by_month: dict[str, int] = {}
    for p in live:
        by_source[p.source] = by_source.get(p.source, 0) + p.amount
        m = (p.received_at + _IST).strftime("%Y-%m")
        by_month[m] = by_month.get(m, 0) + p.amount
    this_month = (datetime.utcnow() + _IST).strftime("%Y-%m")
    return {
        "fy": fy,
        "total": total,
        "count": len(live),
        "refunds": -sum(p.amount for p in live if p.amount < 0),
        "this_month": by_month.get(this_month, 0),
        "by_source": [{"source": k, "label": SOURCES.get(k, k), "amount": v}
                      for k, v in sorted(by_source.items(), key=lambda kv: -kv[1])],
        "by_month": [{"month": k, "amount": v} for k, v in sorted(by_month.items())],
        "gst_limit": GST_LIMIT,
        "gst_warn": total >= GST_WARN_AT,
        "gst_over": total >= GST_LIMIT,
    }


def fys(db) -> list[str]:
    """Every financial year with at least one row, newest first, always
    including the current one."""
    seen = {current_fy()}
    for (ts,) in db.query(Payment.received_at).all():
        seen.add(fy_of(ts))
    return sorted(seen, reverse=True)


def to_csv(db, fy: str | None = None) -> str:
    """The file handed to the CA. Voided rows stay in, marked, so the list
    reconciles with what was keyed in; the Amount column is what counts."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Date (IST)", "Time", "Amount (INR)", "Counts", "Source",
                "Payer", "Contact", "Reference (UPI/UTR)", "Method",
                "For", "Note", "Voided reason", "Entry"])
    for p in reversed(rows(db, fy)):
        o = out(p)
        w.writerow([o["date"], o["time"], o["amount"],
                    "no" if o["voided"] else "yes", o["source_label"],
                    o["payer"], o["contact"], o["ref"], o["method"],
                    o["source_key"], o["note"], o["void_reason"], o["origin"]])
    # A UTF-8 BOM so Excel opens the Hindi labels as Hindi rather than mojibake.
    return "﻿" + buf.getvalue()


# ── one-time copy of what the feature tables already know ─────────────────

def backfill(db) -> int:
    """Copy each feature row's recorded payment into the ledger, once.

    Only the LATEST payment per row can be recovered — the earlier ones were
    overwritten before this ledger existed, which is the whole reason for it.
    Idempotent: a row whose (source, source_key, received_at) is already in
    the ledger is skipped, so this is safe to run at every startup.
    """
    have = {(s, k, t) for s, k, t in
            db.query(Payment.source, Payment.source_key, Payment.received_at).all()}
    added = 0

    def add(source, key, when, amount, **kw):
        nonlocal added
        if not when or not amount or (source, key, when) in have:
            return
        record(db, source, amount, source_key=key, received_at=when,
               origin="backfill", **kw)
        have.add((source, key, when))
        added += 1

    # One /dukanlisting payment renews every row of the same owner at once and
    # stamps the same paid_at on each — count it once, not once per district.
    seen_owner = set()
    for b in db.query(Buyer).filter(Buyer.paid_at.isnot(None)).all():
        if b.owner_user_id:
            if (b.owner_user_id, b.paid_at) in seen_owner:
                continue
            seen_owner.add((b.owner_user_id, b.paid_at))
        add("dealer", b.slug, b.paid_at, b.paid_amount,
            payer=b.name, contact=b.phone or "", ref=b.payment_ref or "")
    for s in db.query(DukanShop).filter(DukanShop.paid_at.isnot(None)).all():
        add("dukan", s.slug, s.paid_at, s.paid_amount,
            payer=s.name, contact=s.phone or "", ref=s.payment_ref or "")
    for r in db.query(RentalProvider).filter(RentalProvider.paid_at.isnot(None)).all():
        add("rental", r.slug, r.paid_at, r.paid_amount,
            payer=r.name, contact=r.phone or "", ref=r.payment_ref or "")
    for v in db.query(SellerVerification).filter(SellerVerification.paid_at.isnot(None)).all():
        add("verify", v.ref, v.paid_at, v.fee_amount,
            payer=v.full_name or "", contact=v.phone or "", ref=v.paid_ref or "")
        if v.refunded_at and v.fee_amount:
            add("verify", v.ref, v.refunded_at, -int(v.fee_amount),
                payer=v.full_name or "", contact=v.phone or "",
                note="refund")
    for s in db.query(Sponsor).filter(Sponsor.paid_at.isnot(None)).all():
        add("sponsor", s.slug, s.paid_at, s.amount,
            payer=s.name, contact=s.contact or "", method="bank")
    if added:
        db.commit()
    return added


# ── receipts ──────────────────────────────────────────────────────────────
#
# A receipt is what the payer keeps as proof he paid — and what a brand's
# accounts team files against a TDS entry. It is a PAYMENT RECEIPT, never a
# tax invoice: a GST invoice needs a GSTIN, SAC code and a tax break-up, and
# printing "Tax Invoice" without them is a false document. Until KM_GSTIN is
# set the receipt says in plain words that it is not a GST invoice.

_ONES = ("", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
         "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
         "Seventeen", "Eighteen", "Nineteen")
_TENS = ("", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety")


def _words_99(n: int) -> str:
    return _ONES[n] if n < 20 else (_TENS[n // 10] + (" " + _ONES[n % 10] if n % 10 else ""))


def rupees_in_words(n: int) -> str:
    """Indian grouping: 1,50,000 → 'One Lakh Fifty Thousand'."""
    n = abs(int(n))
    if n == 0:
        return "Zero"
    parts = []
    for size, name in ((10**7, "Crore"), (10**5, "Lakh"), (1000, "Thousand"), (100, "Hundred")):
        if n >= size:
            q, n = divmod(n, size)
            parts.append(f"{rupees_in_words(q) if q > 99 else _words_99(q)} {name}")
    if n:
        parts.append(_words_99(n))
    return " ".join(parts)


def _inr(n: int) -> str:
    """1,50,000 — Indian digit grouping."""
    s = str(abs(int(n)))
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join(groups) + "," + tail


def receipt_no(p: Payment) -> str:
    return f"KM-{fy_of(p.received_at)}-{p.id:05d}"


_RECEIPT_CSS = """
body{font-family:system-ui,-apple-system,"Noto Sans Devanagari",sans-serif;background:#f4f5f2;margin:0;padding:24px 16px;color:#1a2e23}
.r{max-width:560px;margin:0 auto;background:#fff;border:1px solid #dfe5e1;border-radius:12px;padding:26px 24px}
h1{font-size:19px;margin:0 0 4px}
.iss{font-size:13px;color:#56655d;margin:0 0 18px;line-height:1.6}
.amt{font-size:30px;font-weight:800;margin:6px 0 2px;color:#1b5e3b}
.amt.neg{color:#b42318}
.w{font-size:13px;color:#56655d;margin:0 0 18px}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:9px 6px;border-top:1px solid #edf0ee;vertical-align:top}
th{width:44%;font-weight:600;color:#56655d}
.tax{font-size:12px;color:#56655d;margin-top:18px;line-height:1.6}
.void{background:#fdecea;color:#b42318;font-weight:800;padding:8px 12px;border-radius:8px;margin-bottom:14px}
.p{margin-top:18px;text-align:center}
.p button{padding:10px 20px;border-radius:8px;border:0;background:#1b5e3b;color:#fff;font-size:14px;cursor:pointer}
@media print{body{background:#fff;padding:0}.p{display:none}.r{border:0}}
"""


def receipt_html(p: Payment) -> str:
    import os
    from html import escape as e
    from backend.services import upi
    o = out(p)
    issuer = (os.getenv("KM_RECEIPT_NAME") or upi.payee_name()).strip()
    gstin = (os.getenv("KM_GSTIN") or "").strip()
    refund = p.amount < 0
    title = "Refund Receipt / वापसी रसीद" if refund else "Payment Receipt / भुगतान रसीद"
    methods = {"upi": "UPI", "bank": "Bank transfer", "other": "Other"}
    rows = [
        ("Receipt no. / रसीद नं.", receipt_no(p)),
        ("Date / तारीख़", o["date"]),
        ("Refunded to / किसे" if refund else "Received from / किससे", o["payer"] or "—"),
        ("For / किसके लिए",
         o["source_label"] + (f" ({o['source_key']})" if o["source_key"] else "")),
        ("Method / तरीका", methods.get(o["method"], o["method"])),
        ("Reference (UPI/UTR)", o["ref"] or "—"),
    ]
    if o["note"]:
        rows.append(("Note / नोट", o["note"]))
    body = "".join(f"<tr><th>{e(k)}</th><td>{e(v)}</td></tr>" for k, v in rows)
    tax = (f"GSTIN: {e(gstin)}" if gstin else
           "This is a payment receipt, not a GST tax invoice. / "
           "यह भुगतान रसीद है, GST टैक्स इनवॉइस नहीं।")
    void = ""
    if o["voided"]:
        void = ('<div class="void">VOID — रद्द'
                + (f": {e(o['void_reason'])}" if o["void_reason"] else "") + "</div>")
    sign = "−" if refund else ""
    return (
        '<!doctype html><html lang="hi"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="robots" content="noindex,nofollow">'
        f"<title>{e(receipt_no(p))}</title><style>{_RECEIPT_CSS}</style></head>"
        f'<body><div class="r">{void}<h1>{e(title)}</h1>'
        f'<p class="iss"><b>{e(issuer)}</b> · KrashiMitra (krashimitra.in)<br>'
        "+91 9870951001 · krashimitra038@gmail.com</p>"
        f'<div class="amt{" neg" if refund else ""}">{sign}₹{_inr(p.amount)}</div>'
        f'<p class="w">Rupees {e(rupees_in_words(p.amount))} Only</p>'
        f"<table>{body}</table>"
        f'<p class="tax">{tax}<br>Computer-generated receipt; no signature required.</p>'
        '<div class="p"><button onclick="window.print()">Print / Save PDF</button></div>'
        "</div></body></html>"
    )
