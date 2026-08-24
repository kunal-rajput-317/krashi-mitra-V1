# ============================================================
# services/rental.py
# किराये की मशीनें — the equipment registry behind /rental
#
# ONE JSON FILE, READ LIVE. data/rental_equipment.json holds the categories,
# the equipment and the rate ranges; it is re-read whenever its mtime changes,
# so a rate correction is an edit to the JSON and nothing else — no deploy, no
# regen step, no restart ("everything automatic"). Same shape as
# services/crop_types.py, which this deliberately copies rather than invents.
#
# TWO LAYERS, TWO STORES, ON PURPOSE.
#   The CATALOGUE (what a machine is, what it should cost, what to check) is
#   this JSON file. Those rows are editorial prose, written not typed, and
#   keeping them in git means a rate review is a diff someone can read.
#   The SUPPLY (who will actually hire one out, and for how much) is Postgres —
#   RentalProvider / RentalListing, at the bottom of this module. Those rows
#   are typed in by an admin after a phone call and change per owner.
# Putting the catalogue in the DB would buy nothing and cost a query per
# render; putting the owners in JSON would mean a deploy per phone call.
#
# THE RATES ARE ESTIMATES AND MUST NEVER READ AS QUOTES. A farmer who turns up
# at a tractor owner quoting "कृषि मित्र पर ₹500 लिखा है" and gets refused has
# been mislead by us, so the range is always rendered as a range, always
# carries `rate_basis_hi`, and `updated` is the date the ranges were last
# reviewed — never today's, never render time (see bhav.py::_doc on why a
# false freshness signal costs more than no signal).
#
# THE REGISTRY HALF STAYS PURE — no FastAPI import, and a missing, corrupt or
# half-edited file yields an EMPTY registry rather than an exception: /rental
# going briefly contentless is survivable, /rental raising a 500 into Googlebot
# is not. The supply half below takes a `db` session per call and touches
# Postgres only when a page actually asks for owners.
#
# WHEN NO OWNER IS LISTED the equipment page still answers its question — what
# should this cost, what should I check — and routes the farmer to a government
# CHC. That is the difference from /krashi_dukan, which hides a product no shop
# stocks because such a page is empty; a /rental page never is.
# ============================================================
import json
import re
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "data" / "rental_equipment.json"

_cache: dict | None = None
_mtime: float = -1.0


def _load() -> dict:
    """The parsed file, re-read only when it changes on disk.

    A bad edit keeps the last good copy rather than blanking the section —
    the same "never clobber good cache with empty" rule product.py applies to
    its shop.html parse, and for the same reason: the file is hand-edited.
    """
    global _cache, _mtime
    try:
        m = _PATH.stat().st_mtime
    except OSError:
        return _cache or {}
    if _cache is None or m != _mtime:
        try:
            parsed = json.loads(_PATH.read_text(encoding="utf-8"))
        except Exception:
            return _cache or {}
        if isinstance(parsed, dict) and parsed.get("equipment"):
            _cache, _mtime = parsed, m
        elif _cache is None:
            _cache, _mtime = {}, m
    return _cache or {}


def _norm(slug: str) -> str:
    """URL segment → lookup key. Tolerates spaces, underscores and stray case
    so a hand-typed or hand-linked URL still resolves to the right page."""
    s = (slug or "").strip().lower()
    s = re.sub(r"[\s_]+", "-", s)
    return re.sub(r"-{2,}", "-", s).strip("-")


# ── the registry ────────────────────────────────────────────

def categories() -> list[dict]:
    """Categories in file order — the file IS the running order, so re-ordering
    the hub is a JSON edit. Only those with at least one live equipment row are
    returned, so an emptied category can never render as a heading with nothing
    under it."""
    data = _load()
    live = {e["cat"] for e in equipment()}
    return [c for c in data.get("categories", [])
            if c.get("key") in live]


def equipment() -> list[dict]:
    """Every equipment row, file order. Rows missing a slug or a rate are
    dropped rather than rendered half-built — a card with no price is the one
    thing this page cannot show."""
    return [e for e in _load().get("equipment", [])
            if e.get("slug") and e.get("name_hi") and e.get("rates")]


def by_slug(slug: str) -> dict | None:
    key = _norm(slug)
    return next((e for e in equipment() if _norm(e["slug"]) == key), None)


def by_category() -> list[tuple[dict, list[dict]]]:
    """(category, its equipment) in file order — what the hub renders."""
    rows = equipment()
    return [(c, [e for e in rows if e["cat"] == c["key"]]) for c in categories()]


def category_of(item: dict) -> dict:
    """The category row an equipment belongs to, or a usable stand-in.

    Never returns None: the breadcrumb and the page title both read `label_hi`,
    and a crop of KeyErrors on a mistyped `cat` is a worse failure than a
    breadcrumb that says the equipment's own name.
    """
    key = item.get("cat")
    for c in _load().get("categories", []):
        if c.get("key") == key:
            return c
    return {"key": key or "", "label_hi": item.get("name_hi", ""), "intro_hi": ""}


def siblings(item: dict, limit: int = 6) -> list[dict]:
    """Other equipment in the same category — the "related" strip.

    Falls back to filling from the whole registry when the category is thin, so
    a one-item category still gets a row of onward links instead of a dead end.
    Every /rental page is a leaf; these links are the only internal path
    between them.
    """
    rows = [e for e in equipment() if e["slug"] != item["slug"]]
    same = [e for e in rows if e["cat"] == item["cat"]]
    rest = [e for e in rows if e["cat"] != item["cat"]]
    return (same + rest)[:limit]


# ── rates ───────────────────────────────────────────────────

def rates(item: dict) -> list[dict]:
    """This equipment's rate lines, worst-formed ones dropped."""
    return [r for r in item.get("rates", [])
            if isinstance(r.get("min"), int) and isinstance(r.get("max"), int)
            and r.get("unit_hi")]


def headline_rate(item: dict) -> dict | None:
    """The rate the card and the hero show — the FIRST listed, not the cheapest.

    Order in the JSON is editorial and means "this is how this machine is
    normally hired": a combine is quoted per acre and a pump per hour, and
    showing whichever number happens to be smallest would quietly re-frame the
    deal. Sorting here would have made the tractor's ₹500/घंटा outrank its
    ₹900/एकड़ ploughing rate on a page a farmer opens to compare ploughing.
    """
    rs = rates(item)
    return rs[0] if rs else None


def rate_text(rate: dict | None) -> str:
    """A rate range as one string. Equal ends collapse to a single number so we
    never print "₹500–₹500"."""
    if not rate:
        return "—"
    lo, hi = rate["min"], rate["max"]
    return f"₹{lo}" if lo == hi else f"₹{lo}–₹{hi}"


def span(item: dict) -> tuple[int | None, int | None]:
    """(lowest, highest) across every rate line — the hub's at-a-glance range
    and the Offer JSON-LD's low/high price."""
    rs = rates(item)
    if not rs:
        return None, None
    return min(r["min"] for r in rs), max(r["max"] for r in rs)


# ── file-level metadata ─────────────────────────────────────

def updated() -> str:
    """The date the ranges were last reviewed, "YYYY-MM-DD", or "" if the file
    does not say. Passed to _doc(updated=...) — so it must be a real reviewed
    date and never today's, or every /rental page starts claiming a freshness
    it does not have."""
    val = str(_load().get("updated") or "")
    return val if re.fullmatch(r"\d{4}-\d{2}-\d{2}", val) else ""


def rate_basis() -> str:
    """The one-line "where these numbers came from" note, shown on every page
    that prints a rupee figure."""
    return str(_load().get("rate_basis_hi") or "")


# ============================================================
# THE LISTING SIDE — real machine owners, out of Postgres
#
# Everything above is the editorial catalogue: what a machine is, what it
# should cost, what to check. Everything below is SUPPLY — the owners, CHCs and
# FPOs who will actually hire one out, and what they charge.
#
# THE SHAPE IS krashi_dukan's, DELIBERATELY. Same plan/term/payment columns,
# same hand-entered `paid_at`, same `is_live` gate consulted on every render
# rather than a sweep that expires rows on a schedule. That module's rules
# survived real shopkeepers; re-deriving them here would only re-learn them.
#
# THE ONE RULE THAT CANNOT BEND, inherited unchanged: owners are ranked by
# distance from the farmer and by nothing else. Not by plan, not by what they
# paid, not by how recently. A directory whose order can be bought stops being
# worth reading, and the ordering is the only thing we actually have to sell.
#
# THE ONE DIFFERENCE FROM krashi_dukan: there is no catalogue table. A machine
# is a row in rental_equipment.json, so `equipment_slug` is validated against
# the registry on write instead of against a DukanCatalog row. See
# RentalListing's docstring for why the catalogue stays editorial.
# ============================================================

import math
from datetime import datetime, timedelta

from backend.database.db import RentalListing, RentalProvider
from backend.services import district_geo, free_month

# Chosen to match krashi_dukan's rather than re-decided: a shopkeeper and a
# tractor owner are sold the same thing on the same call, and two panels
# quoting different season lengths would be a pricing bug nobody could see.
SEASON_MONTHS = 3
PLAN_MONTHS = (1, 3, 6, 12)
MIN_PLAN_MONTHS, MAX_PLAN_MONTHS = 1, 12
EXPIRING_SOON_DAYS = 14
PLANS = ("season", "commission")
CALL_RESULTS = ("interested", "callback", "no-answer", "not-interested", "wrong-number")

# What kind of supplier a row is. Shown to the farmer because it changes what
# he should expect on arrival: a government CHC has published rates and a
# counter, a neighbour with a tractor has neither.
KINDS = ("owner", "chc", "fpo", "dealer")
KIND_LABELS = {
    "owner":  "मशीन मालिक",
    "chc":    "कस्टम हायरिंग सेंटर",
    "fpo":    "FPO / किसान समूह",
    "dealer": "डीलर",
}

# A farmer will travel further for a harvester than for a bag of urea — the
# machine comes to him, and combine crews routinely work two districts. Wider
# than krashi_dukan's 150km for that reason, and still bounded so a "nearby
# owner" 400km away is never offered.
MAX_DISTANCE_KM = 200.0


# ── slugs ───────────────────────────────────────────────────

def slugify(text: str) -> str:
    """ASCII slug, lowercase. Devanagari has no useful transliteration here, so
    a purely Hindi name falls back to the caller's alternative."""
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (text or "").strip().lower())
    return re.sub(r"-{2,}", "-", s).strip("-")


def unique_slug(db, name: str, district: str = "") -> str:
    """`name-district`, then `-2`, `-3` … until free. The district rides in the
    slug because two "Kisan Tractor Service"s in different districts are the
    common case, not the edge case."""
    base = slugify(name) or "provider"
    if district:
        d = slugify(district)
        if d and d not in base:
            base = f"{base}-{d}"
    slug, n = base, 2
    while db.query(RentalProvider).filter(RentalProvider.slug == slug).first():
        slug, n = f"{base}-{n}", n + 1
    return slug


# ── providers ───────────────────────────────────────────────

def validate_provider(data: dict) -> str:
    """"" when the row is fit to save, else the message to show the admin."""
    if not (data.get("name") or "").strip():
        return "मालिक या केंद्र का नाम ज़रूरी है"
    if not (data.get("district") or "").strip():
        return "ज़िला ज़रूरी है — दूरी इसी से निकलती है"
    if not (data.get("phone") or "").strip() and not (data.get("whatsapp") or "").strip():
        # A listing with no way to reach it is not a listing. krashi_dukan can
        # fall back on an address because a shop has a counter to walk into; a
        # tractor owner has a phone and nothing else.
        return "फ़ोन या व्हाट्सऐप में से एक ज़रूरी है — वरना किसान संपर्क नहीं कर सकता"
    kind = (data.get("kind") or "owner").strip()
    if kind not in KINDS:
        return f"'{kind}' मान्य नहीं है"
    plan = (data.get("plan") or "season").strip()
    if plan not in PLANS:
        return f"प्लान '{plan}' मान्य नहीं है"
    if plan == "commission":
        try:
            pct = float(data.get("commission_pct") or 0)
        except (TypeError, ValueError):
            return "कमीशन प्रतिशत एक संख्या होनी चाहिए"
        if not (0 < pct <= 30):
            return "कमीशन 0 से 30% के बीच होना चाहिए"
    if str(data.get("plan_months") or "").strip():
        try:
            months = int(float(str(data["plan_months"]).strip()))
        except (TypeError, ValueError):
            return "प्लान की अवधि महीनों में लिखें"
        if not (MIN_PLAN_MONTHS <= months <= MAX_PLAN_MONTHS):
            return (f"प्लान की अवधि {MIN_PLAN_MONTHS} से {MAX_PLAN_MONTHS} "
                    "महीने के बीच होनी चाहिए")
    return ""


def clean_months(value, default: int = SEASON_MONTHS) -> int:
    """A month count that is always sane. Clamped rather than rejected: this
    runs on the write path, where a silently-wrong expiry is worse than a blunt
    one — a 0 would list an owner who is dark the moment he pays."""
    try:
        months = int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default
    return max(MIN_PLAN_MONTHS, min(MAX_PLAN_MONTHS, months))


def plan_months_of(row) -> int:
    """The owner's agreed term. Rows written before the column existed read
    NULL and were on the 3-month season, so that is what they get."""
    return clean_months(getattr(row, "plan_months", None), SEASON_MONTHS)


def _apply_provider(row: RentalProvider, data: dict) -> None:
    for field in ("name", "state", "district", "address", "phone", "whatsapp",
                  "since", "note", "call_result"):
        if field in data:
            setattr(row, field, (data.get(field) or "").strip() or None)
    if "kind" in data:
        kind = (data.get("kind") or "owner").strip()
        row.kind = kind if kind in KINDS else "owner"
    if "plan" in data:
        plan = (data.get("plan") or "season").strip()
        row.plan = plan if plan in PLANS else "season"
    if "commission_pct" in data:
        try:
            row.commission_pct = float(data["commission_pct"]) or None
        except (TypeError, ValueError):
            row.commission_pct = None
    # A season-plan owner has no percentage — a stale one would print a
    # commission rate on a receipt for a flat fee.
    if row.plan == "season":
        row.commission_pct = None
    if "plan_months" in data:
        row.plan_months = clean_months(data["plan_months"], plan_months_of(row))
    for flag in ("verified", "active"):
        if flag in data:
            setattr(row, flag, bool(data[flag]))
    if "status" in data:
        row.status = (data.get("status") or "new").strip() or "new"
    if "owner_user_id" in data:
        try:
            row.owner_user_id = int(data["owner_user_id"]) or None
        except (TypeError, ValueError):
            row.owner_user_id = None
    for coord in ("lat", "lon"):
        if coord in data and str(data.get(coord) or "").strip():
            try:
                setattr(row, coord, float(data[coord]))
            except (TypeError, ValueError):
                pass


def geocode(row: RentalProvider) -> bool:
    """Fill lat/lon from the district centroid when nobody typed better ones.
    Coarse, but the question the page asks is "which of these is nearer", and
    for that a centroid is exactly as good as a rooftop pin. Returns whether
    anything changed, so the caller knows to commit."""
    if row.lat is not None and row.lon is not None:
        return False
    coord = district_geo.coord_for(row.state or "", row.district or "")
    if not coord:
        return False
    row.lat, row.lon = coord
    return True


def provider_get(db, slug: str):
    return db.query(RentalProvider).filter(
        RentalProvider.slug == (slug or "").lower()).first()


def provider_all(db, only_live: bool = False) -> list:
    q = db.query(RentalProvider)
    if only_live:
        q = q.filter(RentalProvider.active.is_(True))
    rows = q.order_by(RentalProvider.district, RentalProvider.name).all()
    return [r for r in rows if is_live(r)] if only_live else rows


def provider_create(db, data: dict) -> RentalProvider:
    row = RentalProvider(
        slug = (data.get("slug") or "").strip().lower() or unique_slug(
            db, data.get("name") or "", data.get("district") or ""),
        name = (data.get("name") or "").strip(),
        plan = (data.get("plan") or "season").strip(),
    )
    _apply_provider(row, data)
    geocode(row)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def provider_update(db, slug: str, data: dict):
    row = provider_get(db, slug)
    if not row:
        return None
    _apply_provider(row, data)
    geocode(row)
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return row


def provider_delete(db, slug: str) -> bool:
    """Delete the owner AND every rate they listed. Hand-rolled because the
    join is by slug, not a foreign key — leaving listings behind would strand
    rows that are invisible, uneditable, and still counted."""
    row = provider_get(db, slug)
    if not row:
        return False
    db.query(RentalListing).filter(RentalListing.provider_slug == row.slug).delete()
    db.delete(row)
    db.commit()
    return True


def log_call(db, slug: str, result: str, note: str = ""):
    """Record that the owner was rung. `called_at` is what the call sheet reads
    to stop the same number being dialled twice in a morning."""
    row = provider_get(db, slug)
    if not row:
        return None
    row.called_at   = datetime.utcnow()
    row.call_count  = (row.call_count or 0) + 1
    row.call_result = (result or "").strip()[:40] or None
    if note:
        row.note = note.strip()[:400]
    if row.status == "new":
        row.status = "called"
    db.commit()
    db.refresh(row)
    return row


def record_payment(db, slug: str, amount: int, ref: str = "",
                   months: int | None = None):
    """Money actually arrived — typed in by hand, and that is the design.

    A upi:// link hands off to the owner's own app and reports nothing back, so
    `paid_at` means one thing only: a human saw the credit in the bank app.
    Nothing automated may ever set it, because an auto-ticked "paid" is a
    fabricated receipt. Paying also lists the owner — the admin who just
    watched the money land has already made the trust decision, and making them
    tick `active` separately only creates an owner who paid and never appeared.

    `months` overrides the term for this one payment; left out, the owner's own
    agreed term applies, which is what a plain renewal wants.
    """
    row = provider_get(db, slug)
    if not row:
        return None
    now  = datetime.utcnow()
    span = plan_months_of(row) if months is None else clean_months(months)
    # Paying early adds a season rather than discarding days already bought; a
    # lapsed owner's new season starts today rather than backdated into the gap.
    base = row.paid_until if (row.paid_until and row.paid_until > now) else now
    row.paid_at     = now
    row.paid_amount = int(amount)
    row.payment_ref = (ref or "").strip()[:80] or None
    row.paid_until  = base + timedelta(days=30 * span)
    row.status      = "listed"
    row.active      = True
    row.updated_at  = now
    db.commit()
    db.refresh(row)
    return row


# ── the free first month ────────────────────────────────────
#
# The offer itself — how long it runs, who may take it, what the page promises
# — lives in services/free_month.py, shared with कृषि दुकान so a tractor owner
# and a shopkeeper are told the same thing. These three are the doorway, so
# routes/admin_rental.py keeps talking to this module about owners and never
# has to know how the offer is stored.

def may_free_month(row) -> bool:
    """Whether this owner can still be given the free month — never paid, never
    granted one. See free_month.may_grant on why it is once per owner."""
    return free_month.may_grant(row)


def on_free_month(row) -> bool:
    """On a free month, or on the far side of one that ran out. Distinguishes a
    gifted listing from a paid one everywhere the panel talks about validity."""
    return free_month.on_free_month(row)


def start_free_month(db, slug: str, months: int | None = None):
    """Grant the free month. None when the owner is unknown OR not eligible —
    the caller separates the two by checking `may_free_month` first, because
    "यह मालिक नहीं मिला" and "इन्हें मुफ़्त महीना पहले ही मिल चुका है" are
    different sentences for the person on the phone.

    Nothing here touches `paid_at`: a free month is not a payment, and the
    `paying` count below must keep meaning "money actually arrived".
    """
    row = provider_get(db, slug)
    if not row:
        return None
    return free_month.grant(db, row, months or free_month.FREE_MONTHS)


def is_live(row) -> bool:
    """Whether this owner may be rendered to a farmer.

    Deliberately asymmetric, exactly as krashi_dukan.is_live: one with NO clock
    running at all stays visible, because during onboarding an empty directory
    is worth less than an unbilled listing and there is nothing to show an
    owner on a phone. One whose clock has run out goes dark — whether that was
    a paid season or the free first month, because both were agreed as having
    an end, and a free month that never ends is not an offer.
    """
    if not row or not row.active:
        return False
    if row.paid_until and row.paid_until < datetime.utcnow():
        return False
    return True


def is_lapsed(row) -> bool:
    """Had a term, ran out — a paid season or the free first month. Either way
    it is what the admin panel flags for a call, and `on_free_month` says which
    call it is: a renewal, or the first ask for money."""
    return bool(row and row.paid_until and row.paid_until < datetime.utcnow())


def days_left(row) -> int | None:
    """Whole days until the listing goes dark, negative once it has.

    None means no clock is running — neither paid nor on the free month, live
    under the onboarding grace. That is a different state from "0 days left"
    and the panel must not render it as one. Rounded DOWN so the number never
    promises time that is not there.
    """
    if not row or not row.paid_until:
        return None
    return math.floor((row.paid_until - datetime.utcnow()).total_seconds() / 86400)


def expiring_soon(row, within_days: int = EXPIRING_SOON_DAYS) -> bool:
    """Still live, but not for long — the renewal call worth making today.
    Gated on `is_live` so a lapsed owner raises one warning, not two."""
    left = days_left(row)
    return bool(row and is_live(row) and left is not None and 0 <= left <= within_days)


# ── listings ────────────────────────────────────────────────

def validate_listing(data: dict) -> str:
    """The equipment slug is checked against the JSON registry, not a table —
    that is the one structural difference from krashi_dukan.validate_item."""
    slug = (data.get("equipment_slug") or "").strip()
    if not slug:
        return "मशीन चुनें"
    if not by_slug(slug):
        return "यह मशीन सूची में नहीं है"
    try:
        rate = int(round(float(str(data.get("rate")).strip())))
    except (TypeError, ValueError):
        return "किराया एक संख्या होनी चाहिए"
    if rate <= 0:
        return "किराया ₹0 से ज़्यादा होना चाहिए"
    if not (data.get("rate_unit_hi") or "").strip():
        # The unit is not optional the way an MRP is. "₹1800" is a different
        # deal per hour than per acre, and a rate with no unit is unusable to
        # the farmer and incomparable against every other row on the page.
        return "किराया किस हिसाब से है यह ज़रूरी है (प्रति घंटा / प्रति एकड़)"
    if str(data.get("min_charge") or "").strip():
        try:
            if int(round(float(str(data["min_charge"]).strip()))) < 0:
                return "न्यूनतम चार्ज ऋणात्मक नहीं हो सकता"
        except (TypeError, ValueError):
            return "न्यूनतम चार्ज एक संख्या होनी चाहिए"
    return ""


def _int_or_none(value):
    try:
        n = int(round(float(str(value).strip())))
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


def listings_for_provider(db, provider_slug: str, only_active: bool = True) -> list:
    q = db.query(RentalListing).filter(RentalListing.provider_slug == provider_slug)
    if only_active:
        q = q.filter(RentalListing.active.is_(True))
    return q.order_by(RentalListing.sort_order, RentalListing.id).all()


def listing_get(db, listing_id: int):
    return db.query(RentalListing).filter(RentalListing.id == int(listing_id)).first()


def listing_create(db, provider_slug: str, data: dict):
    """None when this owner already prices this machine — the caller turns that
    into "यह मशीन पहले से जुड़ी है", not a 500 on the unique constraint."""
    equipment_slug = (data.get("equipment_slug") or "").strip().lower()
    existing = db.query(RentalListing).filter(
        RentalListing.provider_slug == provider_slug,
        RentalListing.equipment_slug == equipment_slug).first()
    if existing:
        return None
    row = RentalListing(
        provider_slug  = provider_slug,
        equipment_slug = equipment_slug,
        rate           = int(round(float(str(data.get("rate")).strip()))),
        rate_unit_hi   = (data.get("rate_unit_hi") or "").strip(),
        min_charge     = _int_or_none(data.get("min_charge")),
        with_operator  = bool(data.get("with_operator", True)),
        fuel_included  = bool(data.get("fuel_included", False)),
        available      = bool(data.get("available", True)),
        active         = bool(data.get("active", True)),
        note           = (data.get("note") or "").strip()[:200] or None,
        sort_order     = int(data.get("sort_order") or 0),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def listing_update(db, listing_id: int, data: dict):
    row = listing_get(db, listing_id)
    if not row:
        return None
    if "rate" in data:
        row.rate = int(round(float(str(data["rate"]).strip())))
    if "min_charge" in data:
        row.min_charge = _int_or_none(data.get("min_charge"))
    if "rate_unit_hi" in data:
        unit = (data.get("rate_unit_hi") or "").strip()
        # Never blanked — see validate_listing on why a unitless rate is unusable.
        if unit:
            row.rate_unit_hi = unit
    if "note" in data:
        row.note = (data.get("note") or "").strip()[:200] or None
    for flag in ("with_operator", "fuel_included", "available", "active"):
        if flag in data:
            setattr(row, flag, bool(data[flag]))
    if "sort_order" in data:
        row.sort_order = int(data.get("sort_order") or 0)
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return row


def listing_delete(db, listing_id: int) -> bool:
    row = listing_get(db, listing_id)
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True


# ── the reads the public pages run on ───────────────────────

def offers_for_equipment(db, equipment_slug: str) -> list:
    """Every live owner who hires out this machine, as flat dicts.

    Returned WITHOUT a distance sort on purpose — the server has no farmer to
    measure from. The route emits lat/lon onto each row and the page re-sorts
    client-side once km_geo is known, the same shape /krashi_dukan and the
    /bhav nearest-mandi panel already use.
    """
    rows = db.query(RentalListing).filter(
        RentalListing.equipment_slug == (equipment_slug or "").lower(),
        RentalListing.active.is_(True)).all()
    if not rows:
        return []
    providers_by_slug = {p.slug: p for p in db.query(RentalProvider).filter(
        RentalProvider.slug.in_([r.provider_slug for r in rows])).all()}
    out = []
    for row in rows:
        p = providers_by_slug.get(row.provider_slug)
        if not p or not is_live(p):
            continue
        out.append({
            "provider_slug": p.slug,
            "provider_name": p.name,
            "kind":       p.kind or "owner",
            "kind_label": KIND_LABELS.get(p.kind or "owner", ""),
            "district":   p.district or "",
            "state":      p.state or "",
            "address":    p.address or "",
            "phone":      p.phone or "",
            "whatsapp":   p.whatsapp or "",
            "since":      p.since or "",
            "verified":   bool(p.verified),
            "lat":        p.lat,
            "lon":        p.lon,
            "listing_id":    row.id,
            "rate":          row.rate,
            "rate_unit_hi":  row.rate_unit_hi or "",
            "min_charge":    row.min_charge,
            "with_operator": bool(row.with_operator),
            "fuel_included": bool(row.fuel_included),
            "available":     bool(row.available),
            "note":          row.note or "",
            "updated_at":    row.updated_at,
        })
    # Cheapest first is the honest default for a farmer with no location set,
    # and it is a fact about the offers rather than a fact about who paid.
    # Unavailable machines sink, because a rate you cannot book is not an offer.
    out.sort(key=lambda o: (not o["available"], o["rate"]))
    return out


def sort_by_distance(offers: list, lat: float, lon: float) -> list:
    """Server-side distance sort for callers that already know where the farmer
    is (a logged-in profile with geo_* set). Offers with no coordinates sink
    rather than being dropped — an un-geocoded owner is still a real owner."""
    def key(o):
        if o.get("lat") is None or o.get("lon") is None:
            return (1, 0.0, o["rate"])
        km = district_geo.haversine_km(lat, lon, o["lat"], o["lon"])
        o["distance_km"] = round(km, 1)
        return (0, km, o["rate"])
    ranked = sorted(offers, key=key)
    return [o for o in ranked
            if o.get("distance_km") is None or o["distance_km"] <= MAX_DISTANCE_KM]


def listed_equipment(db) -> dict:
    """{equipment_slug: {"providers": n, "min_rate": r, "max_rate": r}} for
    every machine at least one live owner actually hires out.

    The hub uses this to badge a card with "3 मालिक" — it does NOT hide the
    other machines the way krashi_dukan hides unstocked products. The reason is
    the difference between the two sections: an unstocked dukan product is an
    empty page, whereas a /rental page without owners still answers the
    question it was built for ("what should this cost?") and still routes the
    farmer to a government CHC.
    """
    rows = db.query(RentalListing).filter(RentalListing.active.is_(True)).all()
    if not rows:
        return {}
    live = {p.slug for p in db.query(RentalProvider).filter(
        RentalProvider.active.is_(True)).all() if is_live(p)}
    agg: dict = {}
    for row in rows:
        if row.provider_slug not in live:
            continue
        b = agg.setdefault(row.equipment_slug,
                           {"providers": 0, "min_rate": None, "max_rate": None})
        b["providers"] += 1
        lo, hi = b["min_rate"], b["max_rate"]
        b["min_rate"] = row.rate if lo is None else min(lo, row.rate)
        b["max_rate"] = row.rate if hi is None else max(hi, row.rate)
    return agg


def counts(db) -> dict:
    """The admin panel's header numbers."""
    rows = db.query(RentalProvider).all()
    return {
        "providers": len(rows),
        "live":      sum(1 for r in rows if is_live(r)),
        "lapsed":    sum(1 for r in rows if is_lapsed(r)),
        "expiring":  sum(1 for r in rows if expiring_soon(r)),
        "uncalled":  sum(1 for r in rows if not r.called_at),
        # Counted apart from `paying` on purpose: a free month is not revenue,
        # and a header that folded the two together would report a month of
        # giveaways as a month of sales.
        "free":      sum(1 for r in rows if on_free_month(r)),
        "paying":    sum(1 for r in rows if r.paid_at),
        "listings":  db.query(RentalListing).count(),
        "equipment": len(equipment()),
    }
