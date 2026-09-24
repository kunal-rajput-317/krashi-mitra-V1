# ============================================================
# routes/admin_ledger.py
# /admin/ledger — हिसाब. Every payment, from every feature, in one list.
#
# Read services/ledger.py first; this file is only its HTTP face. Payments
# made through a feature (dealer, दुकान, rental, नीला टिक, sponsor) land here
# on their own when the admin records them there. This panel adds what no
# feature sees — AdSense, a bank transfer, a donation — and exports the whole
# financial year as a CSV for the CA.
# ============================================================
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from backend.routes.admin import admin_db, require_admin
from backend.database.db import Payment
from backend.services import ledger

router = APIRouter(prefix="/admin/ledger", tags=["admin-ledger"])

# What the manual form may file under. The feature sources are left out on
# purpose: a dealer payment keyed in here would not renew his listing, and the
# feature's own "record payment" button would then add it a second time.
MANUAL_SOURCES = ("adsense", "sponsor", "donation", "leads", "other")


@router.get("")
def list_payments(fy: str = "", source: str = "",
                  db: Session = Depends(admin_db), _: str = Depends(require_admin)):
    fy = fy or ledger.current_fy()
    return {
        "success": True,
        "summary": ledger.summary(db, fy),
        "fys": ledger.fys(db),
        "sources": ledger.SOURCES,
        "manual_sources": list(MANUAL_SOURCES),
        "payments": [ledger.out(p) for p in ledger.rows(db, fy, source or None)],
    }


@router.post("")
def add_payment(payload: dict, db: Session = Depends(admin_db),
                _: str = Depends(require_admin)):
    p = payload or {}
    source = str(p.get("source") or "")
    if source not in MANUAL_SOURCES:
        raise HTTPException(400, "यह स्रोत यहाँ से दर्ज नहीं होता — उसके अपने पन्ने पर 'भुगतान दर्ज' दबाइए")
    try:
        amount = int(p.get("amount") or 0)
    except (TypeError, ValueError):
        amount = 0
    if amount <= 0:
        raise HTTPException(400, "राशि ₹1 या उससे ज़्यादा होनी चाहिए")
    when = None
    if p.get("date"):
        try:
            # The date the money landed, as the bank shows it (IST) — noon, so
            # the IST→UTC shift can never move it into the previous day.
            d = datetime.strptime(str(p["date"])[:10], "%Y-%m-%d")
            when = d + timedelta(hours=12) - timedelta(hours=5, minutes=30)
        except ValueError:
            raise HTTPException(400, "तारीख़ YYYY-MM-DD में दीजिए")
        if when > datetime.utcnow() + timedelta(days=1):
            raise HTTPException(400, "आगे की तारीख़ का भुगतान दर्ज नहीं हो सकता")
    row = ledger.record(db, source, amount, payer=p.get("payer") or "",
                        contact=p.get("contact") or "", ref=p.get("ref") or "",
                        method=p.get("method") or "bank", note=p.get("note") or "",
                        received_at=when, origin="manual")
    db.commit()
    db.refresh(row)
    return {"success": True, "payment": ledger.out(row)}


@router.post("/{pid}/void")
def void_payment(pid: int, payload: dict | None = None,
                 db: Session = Depends(admin_db), _: str = Depends(require_admin)):
    reason = str((payload or {}).get("reason") or "").strip()
    if not reason:
        raise HTTPException(400, "रद्द करने का कारण लिखिए")
    row = ledger.void(db, pid, reason)
    if not row:
        raise HTTPException(404, "no such payment")
    return {"success": True, "payment": ledger.out(row)}


@router.get("/export.csv")
def export_csv(fy: str = "", db: Session = Depends(admin_db),
               _: str = Depends(require_admin)):
    fy = fy or ledger.current_fy()
    return Response(
        ledger.to_csv(db, fy), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="krashimitra-payments-FY{fy}.csv"',
                 "Cache-Control": "no-store"})


@router.get("/{pid}/receipt", response_class=HTMLResponse)
def receipt(pid: int, db: Session = Depends(admin_db), _: str = Depends(require_admin)):
    """A printable receipt for one payment — the admin opens it, saves it as a
    PDF or screenshots it, and sends it to the payer."""
    row = db.query(Payment).filter(Payment.id == pid).first()
    if not row:
        raise HTTPException(404, "no such payment")
    return HTMLResponse(ledger.receipt_html(row), headers={"Cache-Control": "no-store"})
