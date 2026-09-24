# ============================================================
# routes/admin_sponsor.py
# Admin API for site sponsors — /admin/sponsor/*
#
# A SEPARATE ROUTER FROM admin_dukan.py AND admin_rental.py, and the reason is
# the same one that keeps those two apart: they sell different things. A dukan
# row is a shop selling over a counter, a rental row is a machine let by the
# hour, and a sponsor is one brand buying category exclusivity across the whole
# site for a quarter. The auth and the read-only guard are shared because they
# are infrastructure; nothing else is.
#
# THE PAYMENT MECHANICS ARE DELIBERATELY IDENTICAL to /admin/dukan's and
# /admin/rental's — the same services/upi.py collect link, the same
# hand-entered confirmation, the same rule that a upi:// hand-off reports
# nothing back so only a human who saw the credit may set paid_at. Same rail,
# separate books.
#
# CATEGORY EXCLUSIVITY IS CHECKED HERE, NOT ONLY AT RENDER TIME.
# services/sponsors.py::active() already drops the second live sponsor in a
# category, which keeps the promise on the page. But silently dropping someone
# who paid is the worst possible way to discover a double-sale, so the panel
# refuses the write instead and says who already holds it. The render-time
# guard stays as the backstop; this is the one that saves the conversation.
#
# WHY WRITES GO TO THE TABLE AND NEVER TO data/sponsors.json: Render's free
# plan has no persistent disk, so a sponsor written to the file would revert on
# the next deploy and take a paying brand's logo with it. The JSON stays the
# committed seed; a row whose slug matches a seed id overrides it.
# ============================================================
import json
import re
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database.db import Sponsor
from backend.routes.admin import admin_db, require_admin
from backend.services import sponsors, upi

router = APIRouter(prefix="/admin/sponsor", tags=["admin-sponsor"])

_SLUG_OK = re.compile(r"^[a-z0-9][a-z0-9-]{1,48}$")


def _slugify(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").strip().lower()).strip("-")
    return s[:49]


def _as_json_list(v) -> str | None:
    """Accepts a list or a comma-separated string from the panel; stores JSON.
    Empty means 'everywhere', which is what the site-wide tier actually sells,
    so it is stored as NULL rather than '[]' to keep that reading obvious."""
    if v is None or v == "" or v == []:
        return None
    if isinstance(v, str):
        v = [x.strip() for x in v.split(",") if x.strip()]
    v = [str(x).strip() for x in v if str(x).strip()]
    return json.dumps(v, ensure_ascii=False) if v else None


def _out(r: Sponsor) -> dict:
    """The admin view — the public shape plus the money columns a farmer must
    never see. Kept in one place so a template cannot leak `contact` or
    `amount` onto a page by reaching for the wrong dict."""
    pub = sponsors.row_to_dict(r)
    today = date.today()
    live = False
    try:
        live = bool(r.active and r.until and date.fromisoformat(r.until) >= today)
    except (ValueError, TypeError):
        live = False
    days_left = None
    try:
        days_left = (date.fromisoformat(r.until) - today).days if r.until else None
    except (ValueError, TypeError):
        days_left = None
    return {
        **pub,
        "row_id":    r.id,
        "live":      live,
        "days_left": days_left,
        "amount":    r.amount,
        "tier":      r.tier or "",
        "contact":   r.contact or "",
        "notes":     r.notes or "",
        "paid_at":   r.paid_at.isoformat() if r.paid_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _clash(db: Session, category: str, until: str, exclude_id: int | None) -> Sponsor | None:
    """Another ACTIVE, UNEXPIRED sponsor in the same category.

    Only live rows count: an expired partnership in the same category is
    history, not a conflict, and refusing a renewal because last quarter's row
    exists would make the panel unusable exactly when it matters.
    """
    cat = (category or "").strip().lower()
    if not cat:
        return None
    today = date.today().isoformat()
    q = db.query(Sponsor).filter(Sponsor.active.is_(True))
    if exclude_id:
        q = q.filter(Sponsor.id != exclude_id)
    for r in q.all():
        if (r.category or "").strip().lower() != cat:
            continue
        if r.until and r.until >= today:
            return r
    return None


@router.get("")
def list_sponsors(db: Session = Depends(admin_db), _: str = Depends(require_admin)):
    """Every sponsor, live first, then by expiry. Also reports whether the
    private media-kit link can be issued at all, because a panel that offers a
    'copy kit link' button which silently 404s is worse than one that says the
    secret is unset."""
    rows = db.query(Sponsor).order_by(Sponsor.active.desc(), Sponsor.until.desc()).all()
    out = [_out(r) for r in rows]
    return {
        "sponsors": out,
        "live":     sum(1 for r in out if r["live"]),
        "seed_only": [s.get("id") for s in (sponsors._load().get("sponsors") or [])
                      if s.get("id") and s["id"] not in {r["id"] for r in out}],
        "rate_card": sponsors.RATE_CARD,
        "min_days":  sponsors.MIN_DAYS,
        "kit_enabled": sponsors.kit_enabled(),
        # Non-null once search traffic has outgrown the rate card — the panel
        # shows the suggested prices. Same check the daily email runs.
        "price_review": sponsors.price_review(),
        "categories": sorted({(r.category or "").lower() for r in rows if r.category}),
    }


@router.post("")
def create_sponsor(payload: dict, db: Session = Depends(admin_db),
                   _: str = Depends(require_admin)):
    slug = _slugify(payload.get("slug") or payload.get("name") or "")
    if not _SLUG_OK.match(slug):
        raise HTTPException(400, "slug must be 2-49 chars, a-z 0-9 and hyphens")
    if db.query(Sponsor).filter(Sponsor.slug == slug).first():
        raise HTTPException(409, f"'{slug}' already exists — edit it instead")
    for field in ("name", "category", "url"):
        if not str(payload.get(field) or "").strip():
            raise HTTPException(400, f"{field} is required")

    # Refused, not silently dropped — see the module header.
    if payload.get("active"):
        other = _clash(db, payload["category"], payload.get("until") or "", None)
        if other:
            raise HTTPException(
                409, f"{other.name} already holds '{other.category}' until "
                     f"{other.until or 'no end date'}. Category exclusivity is what "
                     f"this tier sells — end that one first, or use a different category.")

    r = Sponsor(
        slug     = slug,
        active   = bool(payload.get("active")),
        name     = str(payload["name"]).strip(),
        category = str(payload["category"]).strip().lower(),
        line     = (payload.get("line") or "").strip() or None,
        url      = str(payload["url"]).strip(),
        logo     = (payload.get("logo") or "").strip() or None,
        sections = _as_json_list(payload.get("sections")),
        states   = _as_json_list(payload.get("states")),
        crops    = _as_json_list(payload.get("crops")),
        since    = (payload.get("since") or date.today().isoformat()),
        until    = (payload.get("until") or "").strip() or None,
        amount   = payload.get("amount") or None,
        tier     = (payload.get("tier") or "").strip() or None,
        contact  = (payload.get("contact") or "").strip() or None,
        notes    = (payload.get("notes") or "").strip() or None,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    sponsors.invalidate()
    return {"success": True, "sponsor": _out(r)}


@router.patch("/{slug}")
def update_sponsor(slug: str, payload: dict, db: Session = Depends(admin_db),
                   _: str = Depends(require_admin)):
    r = db.query(Sponsor).filter(Sponsor.slug == slug).first()
    if not r:
        raise HTTPException(404, "no such sponsor")

    going_live = payload.get("active", r.active)
    cat = (payload.get("category") or r.category or "")
    if going_live:
        other = _clash(db, cat, payload.get("until") or r.until or "", r.id)
        if other:
            raise HTTPException(
                409, f"{other.name} already holds '{other.category}' until "
                     f"{other.until or 'no end date'}.")

    for f in ("name", "category", "line", "url", "logo", "since", "until",
              "tier", "contact", "notes"):
        if f in payload:
            v = payload[f]
            v = str(v).strip() if v is not None else None
            if f == "category" and v:
                v = v.lower()
            setattr(r, f, v or None)
    for f in ("sections", "states", "crops"):
        if f in payload:
            setattr(r, f, _as_json_list(payload[f]))
    if "active" in payload:
        r.active = bool(payload["active"])
    if "amount" in payload:
        r.amount = payload["amount"] or None
    db.commit()
    db.refresh(r)
    sponsors.invalidate()
    return {"success": True, "sponsor": _out(r)}


@router.delete("/{slug}")
def delete_sponsor(slug: str, db: Session = Depends(admin_db),
                   _: str = Depends(require_admin)):
    """Hard delete, and only for a row that never went live.

    A sponsor who paid is history we have to be able to answer questions about
    — what ran, for how long, at what price — so ending one is `active=false`,
    not a delete. Refusing here rather than warning keeps that from being a
    late-night mistake.
    """
    r = db.query(Sponsor).filter(Sponsor.slug == slug).first()
    if not r:
        raise HTTPException(404, "no such sponsor")
    if r.paid_at:
        raise HTTPException(
            400, "this sponsor has a recorded payment — set active=false to end "
                 "the campaign instead of deleting the record.")
    db.delete(r)
    db.commit()
    sponsors.invalidate()
    return {"success": True}


@router.get("/{slug}/collect")
def collect(slug: str, amount: int | None = None,
            db: Session = Depends(admin_db), _: str = Depends(require_admin)):
    """The UPI request to put in front of a brand. Identical rail to
    /admin/dukan and /admin/rental — deliberately, see the module header."""
    r = db.query(Sponsor).filter(Sponsor.slug == slug).first()
    if not r:
        raise HTTPException(404, "no such sponsor")
    if not upi.configured():
        raise HTTPException(400, "KM_UPI_ID is not set — no collect link can be made")
    amt = amount or r.amount or 0
    link = upi.link(amt or None, note=f"KrashiMitra sponsorship — {r.name}",
                    ref=f"sponsor-{r.slug}")
    return {
        "success": True, "amount": amt, "link": link,
        "qr": upi.qr_svg(link), "vpa": upi.vpa(),
        # A upi:// hand-off tells us nothing, so the panel must not imply it did.
        "note": "पैसा आने के बाद ही 'payment record' दबाएं — UPI हमें कुछ नहीं बताता।",
    }


@router.post("/{slug}/payment")
def record_payment(slug: str, payload: dict | None = None,
                   db: Session = Depends(admin_db), _: str = Depends(require_admin)):
    """Set by a human who saw the credit. Never inferred from a tapped link."""
    r = db.query(Sponsor).filter(Sponsor.slug == slug).first()
    if not r:
        raise HTTPException(404, "no such sponsor")
    payload = payload or {}
    if payload.get("amount"):
        r.amount = payload["amount"]
    if not r.amount:
        raise HTTPException(400, "राशि (₹) लिखिए — बिना राशि के भुगतान दर्ज नहीं होगा")
    r.paid_at = datetime.utcnow()
    if payload.get("until"):
        r.until = str(payload["until"]).strip()
    from backend.services import ledger
    ledger.record(db, "sponsor", int(r.amount), payer=r.name, contact=r.contact or "",
                  ref=str(payload.get("ref") or ""), method="bank",
                  source_key=r.slug, received_at=r.paid_at)
    db.commit()
    db.refresh(r)
    sponsors.invalidate()
    return {"success": True, "sponsor": _out(r)}


@router.get("/kit-link/{prospect}")
def kit_link(prospect: str, _: str = Depends(require_admin)):
    """The private media-kit link for one prospect — the ONLY place this site's
    Search Console figures appear. /sponsor itself publishes none of them."""
    if not sponsors.kit_enabled():
        raise HTTPException(
            400, "KM_SPONSOR_KIT_SECRET is not set, so no kit link can be issued "
                 "and /sponsor/kit/* 404s for everyone. Set it in the Render "
                 "dashboard (and .env locally) to any long random string.")
    token = sponsors.kit_token(prospect)
    if not token:
        raise HTTPException(400, "give the prospect a name with letters or digits in it")
    from backend.routes.bhav import SITE
    return {"success": True, "prospect": prospect,
            "url": f"{SITE}/sponsor/kit/{token}"}
