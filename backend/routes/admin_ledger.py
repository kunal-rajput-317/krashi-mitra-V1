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
MANUAL_SOURCES = ("adsense", "affiliate", "sponsor", "donation", "leads", "other")


def entry_or_400(db, payload: dict | None, *, limit: int = ledger.MAX_ENTRY) -> ledger.Entry:
    """ledger.clean_entry() for a route: a refusal is a 400 carrying the reason.

    Every admin route that records money calls this BEFORE it touches anything,
    and tests/test_payment_ledger.py fails the build for one that does not.
    """
    try:
        return ledger.clean_entry(db, payload or {}, limit=limit)
    except ValueError as e:
        raise HTTPException(400, str(e))


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
    e = entry_or_400(db, p)
    row = ledger.record(db, source, e.amount, payer=e.payer,
                        contact=p.get("contact") or "", ref=e.ref,
                        method=e.method, note=e.note, tds=e.tds,
                        received_at=e.received_at, origin="manual")
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
