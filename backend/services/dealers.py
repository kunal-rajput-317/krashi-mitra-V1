# ============================================================
# services/dealers.py
# Writes to the `buyers` table — the admin panel's CRUD and the public
# अपनी दुकान signup, which are two doors into the same rows.
#
# services/buyers.py is the READ side and stays read-only: it merges this table
# with the data/buyers.json seed and hands listings to the kharidar page. This
# module is the only thing that writes. Keeping them apart means a render path
# can never accidentally open a write transaction against a Neon compute that
# has gone read-only.
#
# THE TRUST RULE, enforced here rather than remembered:
#   from_signup() cannot set active or verified. A dealer asking to be listed
#   is a request, not a listing — `verified` is a claim WE make to a farmer
#   about a stranger's phone number, and it costs one real phone call. The
#   public endpoint has no code path to that flag; only approve() does.
#
# Every write invalidates the read cache, so a dealer added while standing in
# front of him is live on the next page load rather than up to a minute later.
# ============================================================
import re
from datetime import datetime

from backend.database.db import Buyer
from backend.services import buyers as buyers_read

# The four listing types the directory renders (services/buyers.py::_KIND_HI).
# Anything else is stored as "trader", which is how kind_label() reads unknown
# values anyway — so the page and the table agree instead of drifting.
KINDS = ("trader", "dealer", "fpo", "processor")

STATUSES = ("new", "called", "listed", "rejected")

_PHONE_RE = re.compile(r"\D+")


def clean_phone(raw: str) -> str:
    """Ten bare digits, or "".

    Same normalisation as routes/appeal.py: farmers and dealers type +91, 0,
    spaces and dashes interchangeably, and a number stored three different ways
    cannot be deduplicated or dialled from a `tel:` link.
    """
    digits = _PHONE_RE.sub("", raw or "")
    if len(digits) > 10 and digits.startswith(("91", "091")):
        digits = digits[-10:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits if len(digits) == 10 and digits[0] in "6789" else ""


# Devanagari → Latin, enough to build a readable slug. Most dealers type the
# firm name in Hindi, and a plain ASCII slugify drops every character — so all
# of them would collapse to "dealer-<district>" and be told apart only by the
# counter unique_slug appends. The slug is permanent (LeadClick quotes it, and
# renaming a firm must not orphan its click history), so it is worth getting
# readable at creation time rather than never.
#
# Not a transliteration standard and not trying to be: the output is a URL
# component, never shown to a farmer, so "sharma-tredars" is a complete success.
_DEVA = {
    "अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo", "ऋ": "ri",
    "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au", "अं": "an",
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n",
    "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "n",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "व": "v", "ळ": "l",
    "श": "sh", "ष": "sh", "स": "s", "ह": "h",
    "क़": "q", "ख़": "kh", "ग़": "gh", "ज़": "z", "ड़": "r", "ढ़": "rh", "फ़": "f",
    # Vowel signs (मात्रा).
    "ा": "a", "ि": "i", "ी": "i", "ु": "u", "ू": "u", "ृ": "ri",
    "े": "e", "ै": "ai", "ो": "o", "ौ": "au",
    # Silent/among-consonant marks: drop rather than guess.
    "्": "", "ं": "n", "ः": "", "ँ": "n", "़": "",
    "०": "0", "१": "1", "२": "2", "३": "3", "४": "4",
    "५": "5", "६": "6", "७": "7", "८": "8", "९": "9",
}


def _translit(text: str) -> str:
    return "".join(_DEVA.get(ch, ch) for ch in (text or ""))


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", _translit(text).lower()).strip("-")
    return s or "dealer"


def unique_slug(db, name: str, district: str) -> str:
    """A stable public id. Quoted by /kharidar/go/<slug> and LeadClick, so it is
    generated once and never derived again — renaming a firm must not orphan
    its click history."""
    base = f"{_slugify(name)}-{_slugify(district)}".strip("-")[:60] or "dealer"
    slug, n = base, 2
    while db.query(Buyer).filter(Buyer.slug == slug).first():
        slug, n = f"{base}-{n}", n + 1
    return slug


def _commodities(value) -> str:
    """Accepts a list or a comma string; stores a comma string of crop slugs.

    Empty means "buys everything" — the आढ़तिया case — which the read side
    treats as matching every crop rather than none.
    """
    if isinstance(value, str):
        value = value.split(",")
    return ",".join(_slugify(c) for c in (value or []) if str(c).strip())


def _apply(row: Buyer, data: dict, *, trusted: bool) -> None:
    """Copy the editable fields onto a row.

    `trusted` is the whole security boundary of this module: False for anything
    that arrived over the public form, and it gates exactly the three flags a
    dealer must not be able to set about himself.
    """
    if "name" in data:
        row.name = (data.get("name") or "").strip()[:120]
    if "kind" in data:
        kind = (data.get("kind") or "trader").strip().lower()
        row.kind = kind if kind in KINDS else "trader"
    for field, limit in (("state", 80), ("district", 80), ("market", 120),
                         ("note", 400), ("since", 40)):
        if field in data:
            setattr(row, field, (data.get(field) or "").strip()[:limit] or None)
    for field in ("phone", "whatsapp"):
        if field in data:
            setattr(row, field, clean_phone(data.get(field)) or None)
    if "commodities" in data:
        row.commodities = _commodities(data.get("commodities")) or None
    if trusted:
        for flag in ("active", "verified", "featured"):
            if flag in data:
                setattr(row, flag, bool(data.get(flag)))
        if "status" in data:
            status = (data.get("status") or "new").strip().lower()
            row.status = status if status in STATUSES else "new"


def validate(data: dict) -> str:
    """The minimum a listing needs to be worth storing. Returns "" when fine.

    Deliberately looser than services/buyers.py::_usable(): a signup with a bad
    phone number is still worth keeping so the owner can chase it, it just
    never renders. This only rejects what is unusable to *us*.
    """
    if len((data.get("name") or "").strip()) < 2:
        return "फर्म का नाम डालें"
    if not (data.get("district") or "").strip():
        return "जिला डालें"
    if not (clean_phone(data.get("phone")) or clean_phone(data.get("whatsapp"))):
        return "सही 10 अंकों का मोबाइल नंबर डालें"
    return ""


def create(db, data: dict, *, source: str = "admin") -> Buyer:
    """Add a listing. `source="admin"` is the owner typing it in; the public
    form goes through from_signup() instead, which cannot set the flags."""
    trusted = source == "admin"
    row = Buyer(
        slug=unique_slug(db, data.get("name", ""), data.get("district", "")),
        source=source,
        # An admin-created listing is live unless told otherwise — the owner is
        # adding it *because* he just spoke to the dealer. A signup is not.
        active=trusted and bool(data.get("active", True)),
        status="listed" if trusted else "new",
    )
    _apply(row, data, trusted=trusted)
    db.add(row)
    db.commit()
    db.refresh(row)
    buyers_read.invalidate()
    return row


def from_signup(db, data: dict) -> Buyer:
    """A dealer asking to be listed. Never live, never verified — see the
    module docstring. The row lands in the admin queue as status="new"."""
    return create(db, data, source="signup")


def update(db, slug: str, data: dict) -> Buyer | None:
    row = db.query(Buyer).filter(Buyer.slug == slug).first()
    if not row:
        return None
    _apply(row, data, trusted=True)
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    buyers_read.invalidate()
    return row


def approve(db, slug: str) -> Buyer | None:
    """The one call that turns a signup into a listing. Named for what it means
    so the phone call it implies is visible in the code, not just in a flag."""
    return update(db, slug, {"active": True, "verified": True, "status": "listed"})


def delete(db, slug: str) -> bool:
    row = db.query(Buyer).filter(Buyer.slug == slug).first()
    if not row:
        return False
    db.delete(row)
    db.commit()
    buyers_read.invalidate()
    return True


def listing(db, *, source: str = "") -> list[dict]:
    """Every row for the admin panel — including inactive ones, which is the
    point: the pending queue is exactly what the read side hides."""
    q = db.query(Buyer)
    if source:
        q = q.filter(Buyer.source == source)
    rows = q.order_by(Buyer.created_at.desc()).all()
    out = []
    for r in rows:
        d = buyers_read.as_dict(r)
        d.update({"slug": r.slug, "source": r.source, "status": r.status,
                  "created_at": r.created_at.isoformat() if r.created_at else ""})
        out.append(d)
    return out


def counts(db) -> dict:
    """Queue sizes for the panel's badge — "3 dealers waiting on a call"."""
    rows = db.query(Buyer).all()
    return {
        "total":   len(rows),
        "live":    sum(1 for r in rows if r.active),
        "pending": sum(1 for r in rows if r.source == "signup" and not r.active
                       and r.status not in ("rejected",)),
    }
