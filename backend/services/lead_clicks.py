# ============================================================
# services/lead_clicks.py
# Durable record of every outbound click we could charge for.
#
# Two surfaces feed it: the किसान-सेवा offers on /bhav (/go/<id>) and the
# खरीदार WhatsApp hops (/kharidar/go/<id>). Both already fired a GA4 event and
# a logger.info line; neither survives — Render rotates logs, and GA4 is a
# report someone has to remember to open. The number a dealer gets quoted
# before he pays ₹500 has to come from our own database.
#
# Two rules shape this module:
#
#   1. **A click must never wait on us.** record() is called from a background
#      task, after the 302 has already gone out. A suspended Neon compute can
#      take seconds to wake; a farmer must not sit through that to reach a
#      WhatsApp number.
#   2. **A click must never fail because of us.** Every write is wrapped. A
#      read-only compute (Neon plan limit — see is_read_only_error) loses the
#      row and logs one line; it does not cost the site an outbound lead.
#
# Reporting is in IST, not UTC: "leads this month" is read by someone in India,
# and a UTC boundary would file the last 5½ hours of every month under the next.
# ============================================================
import logging
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.database.db import LeadClick, SessionLocal, is_read_only_error

log = logging.getLogger("krishi.leads")

IST = timedelta(hours=5, minutes=30)

# Crawlers follow /go/ links like any other href. They are not leads, and an
# inflated count is worse than no count — it is the one number we quote to
# someone who is deciding whether to pay. Substring match on a lowered UA:
# cheap, and it catches the traffic that actually reaches these routes.
_BOT_TOKENS = (
    "bot", "crawl", "spider", "slurp", "bingpreview", "facebookexternalhit",
    "whatsapp", "telegram", "preview", "fetcher", "monitor", "headless",
    "python-requests", "curl", "wget", "httpx", "axios", "scrapy", "lighthouse",
)

_MAX = 300   # referer/label column headroom — a URL can be arbitrarily long


def is_bot(user_agent: str | None) -> bool:
    """True for traffic that should not count as a lead.

    An empty UA counts as a bot too: every real browser sends one, and the
    scripted clients that skip it are never farmers.
    """
    ua = (user_agent or "").strip().lower()
    if not ua:
        return True
    return any(t in ua for t in _BOT_TOKENS)


def _clip(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s[:_MAX] or None


def _district(v) -> str | None:
    """One spelling per district, whatever the source.

    A buyer row carries "Hardoi"; a /bhav URL carries the slug "hardoi", and
    "sant-kabir-nagar" for the multi-word ones. Left alone they group as
    different districts in the report, which is exactly the column we would be
    quoting to a dealer. De-slug and title-case both sides on the way in.
    """
    s = _clip(v)
    return " ".join(w.capitalize() for w in s.replace("-", " ").split()) if s else None


def record(kind: str, target_id: str, *, label=None, category=None,
           district=None, referer=None, user_agent=None) -> None:
    """Persist one click. Safe to call from a background task — never raises.

    Opens its own session rather than taking one: the redirect handlers have no
    `db` dependency, and borrowing the request's session would keep a pooled
    connection checked out past the response.
    """
    if is_bot(user_agent):
        return
    # A click we cannot attribute is noise in the only number we quote.
    target_id = (target_id or "").strip()
    if not target_id:
        return
    db = None
    try:
        db = SessionLocal()
        db.add(LeadClick(
            kind      = kind,
            target_id = target_id[:_MAX],
            label     = _clip(label),
            category  = _clip(category),
            district  = _district(district),
            referer   = _clip(referer),
        ))
        db.commit()
    except Exception as e:
        if db is not None:
            try:
                db.rollback()
            except Exception:
                pass
        # Named, not swallowed silently: a read-only compute means the panel's
        # numbers are quietly drifting from reality, and that is worth grepping.
        if is_read_only_error(e):
            log.warning("lead_click NOT saved (database is read-only): %s/%s", kind, target_id)
        else:
            log.warning("lead_click NOT saved (%s/%s): %s", kind, target_id, e)
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass


# ── Reporting ────────────────────────────────────────────────

_MONTHS_HI = ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून",
              "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"]


def _ist_now() -> datetime:
    return datetime.utcnow() + IST


def _month_start_utc(year: int, month: int) -> datetime:
    """Midnight IST on the 1st, expressed in UTC — created_at is stored in UTC."""
    return datetime(year, month, 1) - IST


def _prev_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def _count(db: Session, since: datetime, until: datetime | None = None) -> dict:
    """Totals in a window, split by surface. One query, grouped."""
    q = db.query(LeadClick.kind, func.count(LeadClick.id)).filter(LeadClick.created_at >= since)
    if until is not None:
        q = q.filter(LeadClick.created_at < until)
    by = dict(q.group_by(LeadClick.kind).all())
    return {"offer": by.get("offer", 0),
            "buyer": by.get("buyer", 0),
            "total": sum(by.values())}


def report(db: Session, recent: int = 12) -> dict:
    """Everything the admin panel's leads card shows, in one payload.

    Deliberately small: this month, last month for a direction, and the two
    breakdowns that turn a total into a sentence you can say on a phone call —
    which listing, and which district.
    """
    now = _ist_now()
    this_start = _month_start_utc(now.year, now.month)
    py, pm     = _prev_month(now.year, now.month)
    prev_start = _month_start_utc(py, pm)
    day_start  = datetime(now.year, now.month, now.day) - IST

    this_month = _count(db, this_start)
    last_month = _count(db, prev_start, this_start)
    today      = _count(db, day_start)

    delta = this_month["total"] - last_month["total"]

    # Top listings this month — the "your listing got 14 enquiries" line.
    # Grouped on the id alone, never the label: the label is a snapshot, so
    # rewording an offer mid-month would otherwise split one listing into two
    # rows and halve the number we are trying to quote. max() just picks a
    # spelling to display.
    top = [
        {"kind": k, "target_id": t, "label": lb or t, "count": n}
        for k, t, lb, n in (
            db.query(LeadClick.kind, LeadClick.target_id, func.max(LeadClick.label),
                     func.count(LeadClick.id).label("n"))
              .filter(LeadClick.created_at >= this_start)
              .group_by(LeadClick.kind, LeadClick.target_id)
              .order_by(func.count(LeadClick.id).desc())
              .limit(8).all()
        )
    ]

    # Districts this month — a listing is priced per district, so this is the
    # column that says where a seed district is already worth selling.
    districts = [
        {"district": d, "count": n}
        for d, n in (
            db.query(LeadClick.district, func.count(LeadClick.id))
              .filter(LeadClick.created_at >= this_start, LeadClick.district.isnot(None))
              .group_by(LeadClick.district)
              .order_by(func.count(LeadClick.id).desc())
              .limit(8).all()
        )
    ]

    latest = [
        {"kind": r.kind, "target_id": r.target_id, "label": r.label or r.target_id,
         "district": r.district, "at": (r.created_at + IST).strftime("%d %b, %I:%M %p")
                                       if r.created_at else None}
        for r in (db.query(LeadClick)
                    .order_by(LeadClick.created_at.desc())
                    .limit(max(0, recent)).all())
    ]

    first = db.query(func.min(LeadClick.created_at)).scalar()

    return {
        "this_month": this_month,
        "last_month": last_month,
        "today":      today,
        "delta":      delta,
        "month_label":      f"{_MONTHS_HI[now.month - 1]} {now.year}",
        "last_month_label": f"{_MONTHS_HI[pm - 1]} {py}",
        "top":        top,
        "districts":  districts,
        "recent":     latest,
        "all_time":   db.query(func.count(LeadClick.id)).scalar() or 0,
        "since":      (first + IST).strftime("%d %b %Y") if first else None,
    }
