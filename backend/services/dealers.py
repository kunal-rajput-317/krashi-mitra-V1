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
from datetime import datetime, timedelta

from backend.database.db import Buyer
from backend.services import buyers as buyers_read
from backend.utils.hindi_translit import slug_chars

# The four listing types the directory renders (services/buyers.py::_KIND_HI).
# Anything else is stored as "trader", which is how kind_label() reads unknown
# values anyway — so the page and the table agree instead of drifting.
KINDS = ("trader", "dealer", "fpo", "processor")

STATUSES = ("new", "called", "listed", "rejected")

# What happened on the phone. `status` cannot carry this: a listing that was
# never rung and one that was rung and refused both sit at "not live", and
# deadline_checklist.json §8.4 says telling those two apart is the difference
# between "the market said no" and "the calls never happened" — the only
# reading of a failed 31-Aug test that is worth anything.
CALL_RESULTS = ("no_answer", "callback", "interested", "not_interested", "pitched")

# How many days before expiry a subscription counts as "expiring" — for the
# dealer's own KrashiBook warning (routes/dukanlisting.py) and the owner's renewal
# call list (counts() below) alike. One constant so the two can never
# disagree about which dealers are about to go dark.
EXPIRY_WARN_DAYS = 7

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
# Character-for-character, no inserted vowels — see utils/hindi_translit.py's
# module docstring for why this stays deliberately different from the
# human-facing readable() used for the UPI payment note. Not a transliteration
# standard and not trying to be: the output is a URL component, never shown to
# a farmer, so "sharma-tredars" is a complete success.
_translit = slug_chars


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

    `owner_user_id` sits outside that gate on purpose — it is not a trust flag,
    it is bookkeeping of *which account* a row belongs to. The only caller that
    ever passes it is routes/dukanlisting.py, which stamps it from the authenticated
    token itself; there is no request field a client could forge it through.

    `bhav_rank` is deliberately NOT settable here at all, trusted or not — it
    has cross-row side effects (clearing whoever else held that rank in the
    same state) that only services/placements.py knows how to do safely.
    """
    if "name" in data:
        row.name = (data.get("name") or "").strip()[:120]
    if "kind" in data:
        kind = (data.get("kind") or "trader").strip().lower()
        row.kind = kind if kind in KINDS else "trader"
    # `description` is the dealer's own public blurb and IS settable from the
    # signup form; `note` is the private call log and is not (see below).
    for field, limit in (("state", 80), ("district", 80), ("market", 120),
                         ("since", 40), ("description", 400)):
        if field in data:
            setattr(row, field, (data.get(field) or "").strip()[:limit] or None)
    for field in ("phone", "whatsapp"):
        if field in data:
            setattr(row, field, clean_phone(data.get(field)) or None)
    if "commodities" in data:
        row.commodities = _commodities(data.get("commodities")) or None
    if "owner_user_id" in data:
        row.owner_user_id = data.get("owner_user_id")
    if trusted:
        for flag in ("active", "verified", "featured"):
            if flag in data:
                setattr(row, flag, bool(data.get(flag)))
        if "status" in data:
            status = (data.get("status") or "new").strip().lower()
            row.status = status if status in STATUSES else "new"
        # Admin-only, all of them.
        #
        # `note` is the private call log — log_call() appends to it and the
        # public card must never render it, so a dealer cannot write into it
        # from the signup form either; his own words go to `description`.
        #
        # The credentials are what make `verified` checkable rather than a
        # feeling, so they can only ever be typed by whoever made the call.
        for field, limit in (("note", 400), ("gstin", 20), ("license_no", 60),
                             ("email", 120), ("address", 200)):
            if field in data:
                setattr(row, field, (data.get(field) or "").strip()[:limit] or None)


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
    # Covers approve() (active/verified flip here, not in record_payment) and
    # any other admin edit that could change a self-serve account's eligibility
    # — e.g. rejecting one already-paid district. No-op for owner_user_id=None.
    _sync_bazar_post(db, row.owner_user_id)
    return row


def approve(db, slug: str) -> Buyer | None:
    """The one call that turns a signup into a listing. Named for what it means
    so the phone call it implies is visible in the code, not just in a flag."""
    return update(db, slug, {"active": True, "verified": True, "status": "listed"})


def log_call(db, slug: str, result: str, note: str = "") -> Buyer | None:
    """Record that the phone actually rang.

    Appends to `note` rather than replacing it: the second call is the one that
    closes, and losing what he said on the first defeats the point of logging.

    Only `pitched` moves `status` to "called" — the rest leave it alone, because
    a no-answer is not progress and marking it as such is how a funnel starts
    lying to the person reading it.
    """
    row = db.query(Buyer).filter(Buyer.slug == slug).first()
    if not row:
        return None
    result = (result or "").strip().lower()
    if result not in CALL_RESULTS:
        return None
    now = datetime.utcnow()
    row.called_at = now
    row.call_result = result
    row.call_count = (row.call_count or 0) + 1
    note = (note or "").strip()[:200]
    if note:
        stamp = now.strftime("%d %b")
        row.note = f"{row.note}\n[{stamp}] {note}"[:400] if row.note else f"[{stamp}] {note}"[:400]
    if result in ("interested", "pitched") and row.status == "new":
        row.status = "called"
    elif result == "not_interested":
        row.status = "rejected"
    row.updated_at = now
    db.commit()
    db.refresh(row)
    buyers_read.invalidate()
    return row


def record_payment(db, slug: str, amount: int, ref: str = "",
                   months: int = 1) -> Buyer | None:
    """Money actually arrived. Typed in by hand, and that is the design.

    A upi:// link hands off to the dealer's own app and reports nothing back
    (services/upi.py), so `paid_at` means one thing only: a human saw the credit
    in the bank app. Nothing automated may ever set it — an auto-ticked "paid"
    on an unconfirmed payment is a fabricated receipt.

    For a legacy/admin row (no owner_user_id) paying also lists him, same as
    always: he is not paying to stay invisible, and the admin is the one who
    just clicked collect after deciding to trust him.

    For a /dukanlisting self-serve account (owner_user_id set), paying does
    NOT flip active/verified — the phone-verification call stays a hard gate
    for those (see approve()); the payment only buys the subscription window.
    It renews every row that shares the same owner_user_id at once, since one
    payment covers the whole account's districts, not just the row the admin
    happened to click collect on.
    """
    row = db.query(Buyer).filter(Buyer.slug == slug).first()
    if not row:
        return None
    now = datetime.utcnow()
    targets = for_owner(db, row.owner_user_id) if row.owner_user_id else [row]
    # Renewals extend from whichever is later: paying early should add a month,
    # not throw away the days already bought, and a lapsed dealer's new month
    # starts today rather than backdated into a gap he was not listed for.
    base = row.paid_until if (row.paid_until and row.paid_until > now) else now
    paid_until = base + timedelta(days=30 * max(1, int(months)))
    for r in targets:
        r.paid_at = now
        r.paid_amount = int(amount)
        r.payment_ref = (ref or "").strip()[:80] or None
        r.paid_until = paid_until
        if not r.owner_user_id:
            r.status = "listed"
            r.active = True
        r.updated_at = now
    db.commit()
    db.refresh(row)
    buyers_read.invalidate()
    _sync_bazar_post(db, row.owner_user_id)
    return row


def quote(n_districts: int) -> int:
    """₹199/month for the first interested district, +₹50/month for each
    additional one — the one place this formula lives, so the signup form's
    live price readout and the admin collect modal's prefilled amount can
    never quietly disagree."""
    return 199 + 50 * (max(1, int(n_districts)) - 1)


def for_owner(db, owner_user_id: int) -> list[Buyer]:
    """Every row one /dukanlisting account owns. Powers the admin panel's
    per-account grouping and the dealer's own "my listings" view — and is how
    record_payment() finds every district a single payment has to renew."""
    if not owner_user_id:
        return []
    return (db.query(Buyer).filter(Buyer.owner_user_id == owner_user_id)
              .order_by(Buyer.created_at.asc()).all())


def account_price(db, owner_user_id: int) -> int:
    """quote() for however many districts this account currently has —
    what the admin's collect modal should prefill instead of the flat
    KM_LISTING_FEE default once a row has an owner_user_id."""
    return quote(len(for_owner(db, owner_user_id)))


# set_bhav_rank() was here. It could only say "rank N somewhere in this state",
# which is neither of the two things now sold — a district page (₹199) and a
# state page (₹999) are separate inventory with their own three slots each.
# services/placements.py replaced it; the Buyer.bhav_rank column is left in
# place, unread, so a value written before the change is still recoverable if
# anyone needs to see what the old panel had set.


def _norm_state(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _sync_bazar_post(db, owner_user_id) -> None:
    """Keep one krashi_bajar feed post in sync with a /dukanlisting account's
    eligibility (active + verified + a currently paid subscription) — created,
    refreshed, or closed automatically as a side effect of approve()/
    record_payment()/update(), the same way every other consequence on this
    table already is (see the module docstring on invalidate()-on-write).

    Never touches admin-created/legacy rows (owner_user_id is None) — there is
    no users.id to author a post as, since nobody logged in to create them.
    """
    if not owner_user_id:
        return
    from backend.database.db import BazarPost

    now = datetime.utcnow()
    rows = for_owner(db, owner_user_id)
    live = [r for r in rows if r.active and r.verified
            and r.paid_until and r.paid_until > now]

    post = (db.query(BazarPost)
              .filter(BazarPost.user_id == owner_user_id, BazarPost.source == "dukan")
              .first())

    if not live:
        if post and post.status != "closed":
            post.status = "closed"
            db.commit()
        return

    lead = live[0]
    # commodities stores /bhav crop *slugs* (e.g. "paddy-common"), not Hindi
    # names — there is no slug->Hindi reverse index this service layer can
    # reach without importing routes/bhav.py (a real import cycle, not just a
    # lazy one: bhav.py already imports from this module's neighbours). Good
    # enough for an auto-generated caption; the hyphen swap just keeps it readable.
    crops = sorted({c.replace("-", " ") for r in live
                    for c in (r.commodities or "").split(",") if c.strip()})
    districts = sorted({r.district for r in live if r.district})
    crop_txt = ", ".join(crops) if crops else "सभी फसलें"
    dist_txt = ", ".join(districts[:3])
    if len(districts) > 3:
        dist_txt += f" और {len(districts) - 3} अन्य जिले"
    label, emoji = buyers_read.kind_label(lead.kind)
    text = (f"{emoji} {lead.name} — {label}\n"
            f"हम खरीदते हैं: {crop_txt}\n"
            f"जिले: {dist_txt}")

    if post:
        post.text = text
        post.state = lead.state
        post.district = lead.district
        post.status = "active"
    else:
        post = BazarPost(
            user_id=owner_user_id, post_type="buy", text=text,
            state=lead.state, district=lead.district, source="dukan",
            status="active",
        )
        db.add(post)
    db.commit()


def funnel(db) -> dict:
    """The 31-Aug test as five numbers, in the order they must happen.

    Targets come straight from deadline_checklist.json: 20 listed, 10 called,
    3 free listings live, 1 paid. Shown next to the counts so the panel reads
    as "7 of 20" rather than a bare number with no sense of enough.
    """
    rows = db.query(Buyer).all()
    now = datetime.utcnow()
    paying = [r for r in rows if r.paid_at]
    return {
        "added":      len(rows),
        "called":     sum(1 for r in rows if r.called_at),
        "interested": sum(1 for r in rows if r.call_result in ("interested", "pitched")),
        "refused":    sum(1 for r in rows if r.call_result == "not_interested"),
        "no_answer":  sum(1 for r in rows if r.call_result == "no_answer" and (r.call_count or 0) <= 2),
        # A live listing nobody has paid for is the free listing the plan trades
        # for a reference — worth counting separately from a paid one.
        "free_live":  sum(1 for r in rows if r.active and not r.paid_at),
        "paid":       len(paying),
        "paid_live":  sum(1 for r in paying if r.paid_until and r.paid_until > now),
        "revenue":    sum(r.paid_amount or 0 for r in paying),
        "targets":    {"added": 20, "called": 10, "free_live": 3, "paid": 1},
    }


def delete(db, slug: str) -> bool:
    row = db.query(Buyer).filter(Buyer.slug == slug).first()
    if not row:
        return False
    owner_user_id = row.owner_user_id
    db.delete(row)
    db.commit()
    buyers_read.invalidate()
    # Re-check after the delete: if that was the dealer's last remaining
    # district, _sync_bazar_post's own for_owner() lookup now comes back
    # empty and it closes the bazar post; if other districts remain, it just
    # refreshes the caption's crop/district summary.
    _sync_bazar_post(db, owner_user_id)
    return True


def listing(db, *, source: str = "") -> list[dict]:
    """Every row for the admin panel — including inactive ones, which is the
    point: the pending queue is exactly what the read side hides."""
    q = db.query(Buyer)
    if source:
        q = q.filter(Buyer.source == source)
    rows = q.order_by(Buyer.created_at.desc()).all()
    now = datetime.utcnow()
    # Where each dealer is actually shown. On the row rather than behind a
    # click because "paid but on no page" is the failure this panel exists to
    # surface, and it is invisible from every other field here.
    from backend.services import placements as placements_read
    out = []
    for r in rows:
        d = buyers_read.as_dict(r)
        d["placements"] = placements_read.for_dealer(r.slug)
        d.update({
            "slug": r.slug, "source": r.source, "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else "",
            "called_at":   r.called_at.isoformat() if r.called_at else "",
            "call_result": r.call_result or "",
            "call_count":  r.call_count or 0,
            "paid_at":     r.paid_at.isoformat() if r.paid_at else "",
            "paid_amount": r.paid_amount or 0,
            "payment_ref": r.payment_ref or "",
            "paid_until":  r.paid_until.isoformat() if r.paid_until else "",
            # Derived here so the panel never has to re-implement the date
            # comparison and drift from the funnel counts next to it.
            "paying":      bool(r.paid_until and r.paid_until > now),
            # /dukanlisting account grouping — None for admin-created/legacy
            # rows, which the panel keeps showing exactly as it does today.
            "owner_user_id": r.owner_user_id,
            "bhav_rank":     r.bhav_rank,
            # Admin-only, every one. services/buyers.py::as_dict() carries none
            # of these, so the panel is the only surface that can render them —
            # `note` especially, which is the private call log.
            "note":       r.note or "",
            "gstin":      r.gstin or "",
            "license_no": r.license_no or "",
            "email":      r.email or "",
            "address":    r.address or "",
        })
        out.append(d)
    return out


def counts(db) -> dict:
    """Queue sizes for the panel's badge — "3 dealers waiting on a call"."""
    rows = db.query(Buyer).all()
    now = datetime.utcnow()
    soon = now + timedelta(days=EXPIRY_WARN_DAYS)
    # A renewal nobody remembers to ask for is revenue lost in silence, and the
    # dealer's own KrashiBook warning (routes/dukanlisting.py::my_subscription) only
    # helps if the owner is making the call from this side too. Counted per
    # ACCOUNT, not per row: three districts on one subscription is one call.
    def _accounts(pred):
        return len({r.owner_user_id or r.slug for r in rows if pred(r)})
    return {
        "total":   len(rows),
        "live":    sum(1 for r in rows if r.active),
        "pending": sum(1 for r in rows if r.source == "signup" and not r.active
                       and r.status not in ("rejected",)),
        "expiring": _accounts(lambda r: r.paid_until and now < r.paid_until <= soon),
        "lapsed":   _accounts(lambda r: r.paid_until and r.paid_until <= now),
    }
