# ============================================================
# backend/services/placements.py
# Which /bhav page a paying dealer is shown on, and in which of its 3 slots.
#
# THE SPLIT THIS MODULE EXISTS FOR. services/buyers.py answers "may this shop
# be shown at all" — active, verified, subscription current. That is
# eligibility. This module answers "and where", which is the thing money is
# actually exchanged for.
#
# FIVE PRODUCTS, ONE TABLE. A placement row is a *pattern*, not always a single
# page: "*" in a column means "every value of this column". That is the whole
# mechanism behind the wide plans — one row covers 1,800 pages, so selling UP
# wheat state-wide is one INSERT, not 73 of them.
#
#     tier            crop  state  district   covers
#     district_crop    C      S       D       one page
#     district_all     *      S       D       every crop page in one district
#     state_page       C      S       ""      the state landing page only
#     state_all        C      S       *       state page + all its districts
#     national         C      *       *       every page for that crop
#
# COLLISIONS ARE RESOLVED BY SPECIFICITY, AND NOTHING IS EVER DELETED. Once
# patterns overlap, two dealers can legitimately claim one page. The rule is
# the CSS/DNS one — the narrower pattern wins — and it is resolved at render
# time, so no sale ever destroys another sale:
#
#     /bhav/wheat/uttar-pradesh/bareilly is claimed, in this order, by
#       (wheat, uttar-pradesh, bareilly)   the ₹199 local buyer
#       (*,     uttar-pradesh, bareilly)   the ₹499 whole-district buyer
#       (wheat, uttar-pradesh, *)          the ₹6,999 state-wide buyer
#       (wheat, *,             *)          the ₹12,999 national buyer
#
# Geographic specificity outranks crop specificity — (*, S, D) beats (C, S, *)
# — because farmers search by place, and because it is what protects the
# small-ticket base: a local dealer's whole reason to pay is being top in his
# own district, and one national sale must not be able to take that from him.
#
# AND THE BROAD PLANS ARE NOT STARVED. If specificity alone decided, three
# local buyers in Bareilly would push the national buyer off the very pages he
# paid most for. So local tiers may occupy at most LOCAL_CAP of the SLOTS —
# the remainder is reserved for whoever holds the broadest claim. That reserve
# is what makes "हर पेज पर कम से कम एक जगह" a promise we actually keep. An
# unsold reserve is not wasted: if no broad buyer exists, locals fill it.
#
# READS ARE HOT, WRITES ARE RARE. A /bhav render must not query this table —
# there are ~15,000 of those pages and one owner setting slots by hand. The
# whole table is a few dozen rows, so it is cached whole and dropped on write,
# the same shape services/buyers.py already uses for the same reason.
# ============================================================
import logging
import threading
import time
from datetime import datetime

from backend.database.db import DealerPlacement, SessionLocal
from backend.services import buyers as buyers_read

logger = logging.getLogger(__name__)

# The wildcard. Stored as an ordinary slug value, which is why none of this
# needed a migration: "*" can never collide with a real crop or district
# because norm() only ever produces [a-z0-9- ] from real names.
WILD = "*"

# Three, because that is what the panel renders. Not a config knob: the number
# is baked into the page design and into what a dealer is told he is buying.
SLOTS = 3

# How many of those three the *local* tiers may take. The gap is the reserve
# the wide plans are sold against — see the module header. Two is the smallest
# number that still lets a district have real competition on it.
LOCAL_CAP = 2

# ── Money ───────────────────────────────────────────────────────────────────
# A SEASON IS THE UNIT, NOT A MONTH. Three months matches how the buyer already
# thinks: a mustard dealer trades Oct–Feb and would rather buy two seasons than
# twelve months, and the renewal conversation becomes "अगला सीज़न चालू रखें?"
# rather than "did it pay for itself?" — a question this site's traffic cannot
# yet win twelve times a year. services/dealers.py::record_payment(months=3)
# is what actually moves the date; SEASON_MONTHS is the one place that 3 lives.
SEASON_MONTHS = 3

# METERED, AND WITHOUT A CEILING. Price is per district plus per crop page:
#
#     ₹199 × districts  +  ₹50 × crops        (per season)
#
# There is deliberately NO cap and NO "all crops" bundle. A flat ceiling was
# proposed and rejected for a reason worth keeping written down: crop counts
# per district run 4 → 61 in UP alone (15x), so any cap charges a dealer with
# twelve pages the same as one with sixty-one. Metered all the way up means two
# dealers with different page counts can never pay the same amount.
#
# The corollary is that nobody buys sixty-one crops — and that is fine, because
# they are not meant to. The dealer picks the crops he trades, sees each page's
# real impression count while picking (services/page_stats.py), and the pages
# worth nothing simply do not get bought. That is what keeps a flat ₹50 fair
# without a formula: only the pages worth ₹50 are chosen.
#
# Crops are charged ONCE per account, districts per district. A dealer's crop
# mix does not change between his districts, so billing him per district×crop
# pair would be a penalty for expanding.
PRICE_DISTRICT = 199        # each district he wants to be listed in
PRICE_CROP = 50             # each crop page, counted once across the account

# The list prices, shown struck through beside the offer.
#
# THIS IS A PROMISE, NOT A DECORATION. A crossed-out number that was never
# charged and never will be is a false reference price — the thing India's
# CCPA dark-pattern rules are about, and the same kind of claim /dukanlisting
# explicitly promises farmers we do not make about ranking. So these are the
# real list prices: when the introductory period ends, THIS is what a new
# dealer pays, and every surface says "शुरुआती ऑफर" rather than implying a
# discount that has already been taken away from someone.
LIST_DISTRICT = 599
LIST_CROP = 150

# Buy four seasons at once, pay for three. Kept here rather than in the copy so
# the admin collect modal and the page quote the same number.
YEAR_SEASONS_CHARGED = 3
YEAR_SEASONS_GIVEN = 4

# ── The custom tier ─────────────────────────────────────────────────────────
# One page, anywhere, sold by hand. The floor is a floor and not a price: what
# is actually quoted comes from that page's own measured traffic, because
# "₹4,999 for any page" is only defensible on the pages that earn it. Of 12,908
# crop×district pages, 22 got three or more clicks in the last 28 days and
# 12,689 got none — selling the floor price on one of those is how a buyer is
# lost permanently.
CUSTOM_FLOOR = 4999
# Below this many impressions in the last 28 days, a page is not offered as a
# custom placement at all. capacity() and the admin panel both refuse it.
CUSTOM_MIN_IMPRESSIONS = 300

# Which placement PATTERNS exist, and whether each competes for the local slots
# or the reserve. This is about collision resolution, not about the rate card —
# the metered plan buys ordinary (crop, state, district) rows, one per crop, and
# the wildcard shapes stay available for the hand-sold custom tier.
TIERS = {
    "district_crop": {"label": "जिला — एक फसल",   "local": True},
    "district_all":  {"label": "मेरा पूरा जिला",   "local": True},
    "state_page":    {"label": "राज्य का पेज",     "local": True},
    "state_all":     {"label": "पूरा राज्य",       "local": False},
    "national":      {"label": "राष्ट्रीय",         "local": False},
}

_TTL = 120.0                # seconds; the floor under a missed invalidate()
_cache: list | None = None
_at = -1.0
_lock = threading.Lock()

# Sorts before every real timestamp, for rows written before created_at existed.
_EPOCH = datetime.min


def norm(s: str) -> str:
    """Slug spelling is the join key between this table and a URL, and a URL is
    always lowercase here."""
    return " ".join((s or "").strip().lower().split())


def page_key(crop: str, state: str, district: str = "") -> tuple:
    return (norm(crop), norm(state), norm(district))


def page_url(crop: str, state: str, district: str = "") -> str:
    """The URL a placement points at. A pattern has no single URL, so the
    wildcard is rendered as-is — /bhav/wheat/uttar-pradesh/* reads as what it
    is in the admin list, and is never linked."""
    crop, state, district = page_key(crop, state, district)
    return f"/bhav/{crop}/{state}/{district}" if district else f"/bhav/{crop}/{state}"


def tier_of(crop: str, state: str, district: str = "") -> str:
    """Which of the five products this (crop, state, district) triple is.

    Order matters: a wild state means national regardless of what the district
    column says, which is why normalise_pattern() forces the two to agree.
    """
    c, s, d = page_key(crop, state, district)
    if s == WILD:
        return "national"
    if d == WILD:
        return "state_all"
    if d == "":
        return "state_page"
    if c == WILD:
        return "district_all"
    return "district_crop"


def tier_label(tier: str) -> str:
    return TIERS.get(tier, {}).get("label", tier)


def is_local(tier: str) -> bool:
    return TIERS.get(tier, {}).get("local", True)


# The two ways a listing is bought. Not the same axis as TIERS above: TIERS is
# about which pages a placement row covers, this is about how it was sold.
PLANS = {
    "metered": {"label": "जिला + फसल (खुद चुनें)", "self_serve": True},
    "custom":  {"label": "कस्टम — एक खास पेज",     "self_serve": False},
}
DEFAULT_PLAN = "metered"


def plan_label(plan: str) -> str:
    return PLANS.get(plan, {}).get("label", plan or "")


def normalise_pattern(crop: str, state: str, district: str = "") -> tuple:
    """Force the one impossible shape into the one it must have meant.

    A wild state with a named district — (wheat, *, bareilly) — would claim
    "Bareilly in every state", which is not a product and not what any admin
    means by it. It becomes national.
    """
    c, s, d = page_key(crop, state, district)
    if s == WILD:
        d = WILD
    return (c, s, d)


def quote(n_districts: int, n_crops: int) -> int:
    """THE rate card, in one line. Everything that shows a price calls this.

    ₹199 per district + ₹50 per crop page, per season. No cap — see the module
    header for why a ceiling was rejected.
    """
    d = max(1, int(n_districts or 1))
    c = max(0, int(n_crops or 0))
    return PRICE_DISTRICT * d + PRICE_CROP * c


def list_quote(n_districts: int, n_crops: int) -> int:
    """The struck-through twin, on the same shape, so the discount shown is the
    discount actually given on every line of the basket rather than on the
    first item only."""
    d = max(1, int(n_districts or 1))
    c = max(0, int(n_crops or 0))
    return LIST_DISTRICT * d + LIST_CROP * c


def year_quote(n_districts: int, n_crops: int) -> int:
    """Four seasons for the price of three."""
    return quote(n_districts, n_crops) * YEAR_SEASONS_CHARGED


def breakdown(n_districts: int, n_crops: int) -> dict:
    """The itemised version, for the form's live readout and the receipt.

    Itemised on purpose: a dealer who can see "2 जिले × ₹199 + 5 फसल × ₹50" can
    check the arithmetic himself, and a price he can check is a price he argues
    with less on the call.
    """
    d = max(1, int(n_districts or 1))
    c = max(0, int(n_crops or 0))
    return {
        "districts":       d,
        "crops":           c,
        "district_rate":   PRICE_DISTRICT,
        "crop_rate":       PRICE_CROP,
        "districts_total": PRICE_DISTRICT * d,
        "crops_total":     PRICE_CROP * c,
        "total":           quote(d, c),
        "list_total":      list_quote(d, c),
        "season_months":   SEASON_MONTHS,
        "year_total":      year_quote(d, c),
        "year_seasons":    YEAR_SEASONS_GIVEN,
    }


def slot_price(crop: str, state: str = "", district: str = "") -> int | None:
    """What ONE placement row is worth, for the `price` snapshot column.

    An ordinary crop page is ₹50 — the metered rate the dealer actually paid
    for it. The wildcard patterns are hand-sold and have no formula price, so
    this returns None rather than inventing one: a fabricated number in a
    column labelled "what was agreed" is worse than an empty one, because the
    receipt reads from it.
    """
    if tier_of(crop, state, district) == "district_crop":
        return PRICE_CROP
    return None


def custom_quote(crop: str, state: str, district: str = "") -> dict:
    """What the hand-sold single-page tier costs here, and whether it is even
    offered.

    The floor is not the price. A page nobody sees is not worth ₹4,999 and
    saying so in the quote is cheaper than saying it after the money arrives —
    so this refuses outright below CUSTOM_MIN_IMPRESSIONS rather than returning
    a number the page cannot honour.
    """
    from backend.services import page_stats
    stats = page_stats.for_page(crop, state, district)
    impressions = stats["impressions"] if stats else None
    out = {
        "url":         page_url(crop, state, district),
        "floor":       CUSTOM_FLOOR,
        "min_impressions": CUSTOM_MIN_IMPRESSIONS,
        "impressions": impressions,
        "clicks":      stats["clicks"] if stats else None,
        "window_days": page_stats.WINDOW_DAYS,
    }
    if impressions is None:
        out.update(offered=False,
                   reason="इस पेज का डेटा अभी नहीं है — पहले आंकड़े देखने होंगे")
        return out
    if impressions < CUSTOM_MIN_IMPRESSIONS:
        out.update(offered=False,
                   reason=(f"पिछले {page_stats.WINDOW_DAYS} दिन में यह पेज सिर्फ "
                           f"{impressions} बार दिखा — इतने का ₹{CUSTOM_FLOOR} "
                           f"लेना सही नहीं होगा"))
        return out
    # Above the gate, the floor scales with what the page actually delivers.
    # Integer multiples of the floor rather than a per-impression rate: this is
    # negotiated by hand, and a number like ₹9,998 invites a discussion the
    # owner should be having about the page, not about the arithmetic.
    steps = max(1, impressions // CUSTOM_MIN_IMPRESSIONS)
    out.update(offered=True, price=CUSTOM_FLOOR * steps, reason="")
    return out


def invalidate() -> None:
    global _cache, _at
    with _lock:
        _cache, _at = None, -1.0


def _row_dict(r) -> dict:
    tier = tier_of(r.crop_slug, r.state_slug, r.district_slug or "")
    return {
        "id":       r.id,
        "slug":     r.buyer_slug,
        "crop":     r.crop_slug,
        "state":    r.state_slug,
        "district": r.district_slug or "",
        "rank":     r.rank,
        "price":    r.price,
        "tier":     tier,
        "tier_label": tier_label(tier),
        "created":  r.created_at or _EPOCH,
        "url":      page_url(r.crop_slug, r.state_slug, r.district_slug or ""),
    }


def _all() -> list:
    """Every placement, cached. Never raises: a /bhav page that cannot read this
    table renders without a dealer panel, which is how it looked yesterday."""
    global _cache, _at
    now = time.time()
    if _cache is not None and (now - _at) < _TTL:
        return _cache
    rows: list = []
    try:
        db = SessionLocal()
        try:
            rows = [_row_dict(r) for r in db.query(DealerPlacement).all()]
        finally:
            db.close()
    except Exception as e:
        logger.warning("placement read failed, rendering no panel: %s", e)
        return _cache or []
    with _lock:
        _cache, _at = rows, now
    return rows


def match_chain(crop: str, state: str, district: str = "") -> list[tuple]:
    """Every pattern that can claim this page, narrowest first.

    This is the whole collision rule in one function — read it top to bottom
    and you know who beats whom. Returns [(key, is_local)].
    """
    c, s, d = page_key(crop, state, district)
    if not d:
        # The state landing page. There is no "all crops in this state" product,
        # so only the crop's own tiers reach it.
        return [((c, s, ""),    True),
                ((c, s, WILD),  False),
                ((c, WILD, WILD), False)]
    return [((c, s, d),       True),    # this crop, this district
            ((WILD, s, d),    True),    # every crop, this district
            ((c, s, WILD),    False),   # this crop, whole state
            ((c, WILD, WILD), False)]   # this crop, everywhere


def _sorted(rows: list) -> list:
    """Rank first, then seniority, within ONE pattern.

    uq_placement_slot already makes rank unique per pattern, so the seniority
    tie-break normally never fires — it is here so that if that constraint is
    ever absent (a mid-migration table, a restore, SQLite in a test) the order
    is still stable rather than whatever the query happened to return. A slot
    order that reshuffled every time the 120s cache dropped would look exactly
    like being cheated to the dealer watching it.

    Note this sorts inside a pattern, never across them: ordering BETWEEN
    tiers is match_chain()'s job, and rank must never be allowed to override
    specificity.
    """
    return sorted(rows, key=lambda p: (p["rank"], p["created"], p["id"]))


def for_page(crop: str, state: str, district: str = "") -> list:
    """The dealers to render on one page, best first.

    Each slug is resolved through buyers.by_id(), which is where eligibility
    lives — so a lapsed or hidden dealer silently drops out of his slot and the
    page shows one fewer card rather than a dead listing.
    """
    grouped: dict[tuple, list] = {}
    for p in _all():
        grouped.setdefault((p["crop"], p["state"], p["district"]), []).append(p)

    local, broad = [], []
    for key, local_tier in match_chain(crop, state, district):
        (local if local_tier else broad).extend(_sorted(grouped.get(key, [])))

    out: list = []
    seen: set = set()

    def take(candidates: list, limit: int) -> None:
        for p in candidates:
            if limit <= 0:
                return
            if p["slug"] in seen:
                continue                  # already placed by a narrower pattern
            dealer = buyers_read.by_id(p["slug"])
            if not dealer:
                continue                  # unpaid / unverified / hidden
            seen.add(p["slug"])
            out.append(dealer)
            limit -= 1

    take(local, LOCAL_CAP)                # locals, capped so the reserve survives
    take(broad, SLOTS - len(out))         # the reserve
    take(local, SLOTS - len(out))         # reserve unsold? a local may have it
    return out


def for_dealer(slug: str) -> list:
    """Every slot one dealer holds, for the admin panel. Ordered widest product
    first, so what he pays most for reads at the top."""
    slug = (slug or "").strip()
    order = ["national", "state_all", "state_page", "district_all", "district_crop"]
    mine = [p for p in _all() if p["slug"] == slug]
    return sorted(mine, key=lambda p: (order.index(p["tier"]), p["crop"],
                                       p["state"], p["district"], p["rank"]))


def slots_on(crop: str, state: str, district: str = "") -> list:
    """[{rank, slug|None}] for the patterns held at exactly this key — what the
    admin box shows so "who is already at rank 1" is answerable before
    overwriting them. This is about one *pattern*, not about what the page
    finally renders; use for_page() for that."""
    key = page_key(crop, state, district)
    held = {p["rank"]: p for p in _all()
            if (p["crop"], p["state"], p["district"]) == key}
    out = []
    for rank in range(1, SLOTS + 1):
        p = held.get(rank)
        out.append({"rank": rank, "slug": p["slug"] if p else None,
                    "placement_id": p["id"] if p else None})
    return out


def capacity(crop: str, state: str = "", district: str = "") -> dict:
    """Is there anything left to sell on this pattern, and is it guaranteed?

    Nothing stopped an admin selling a fourth dealer into three slots before —
    the sale simply evicted someone. Now that a wide plan can be sold once and
    render on 1,800 pages, over-selling is not visible at all without this, so
    it is answered before the money is taken rather than after.

    `guaranteed` is the honest half: LOCAL_CAP < SLOTS means the top-ranked
    broad holder always renders, but the second and third only appear on pages
    where the local slots went unsold. Sell those as remnant or not at all.
    """
    key = normalise_pattern(crop, state, district)
    tier = tier_of(*key)
    held = _sorted([p for p in _all()
                    if (p["crop"], p["state"], p["district"]) == key])
    cap = LOCAL_CAP if is_local(tier) else SLOTS
    guaranteed = cap if is_local(tier) else SLOTS - LOCAL_CAP
    return {
        "tier":        tier,
        "tier_label":  tier_label(tier),
        "url":         page_url(*key),
        "sold":        len(held),
        "cap":         cap,
        "left":        max(0, cap - len(held)),
        "guaranteed":  guaranteed,
        "guaranteed_left": max(0, guaranteed - len(held)),
        "price":       slot_price(*key),
        "holders":     [{"rank": p["rank"], "slug": p["slug"]} for p in held],
        # What this page actually delivered, so nothing is ever sold on it
        # without the number being on screen first. None means "no data",
        # which is different from zero and is said differently.
        "traffic":     _traffic(*key),
    }


def _traffic(crop: str, state: str, district: str = "") -> dict | None:
    """Impressions/clicks for a real page. A wildcard pattern spans thousands
    of pages and has no single figure, so it reports None rather than a sum
    that would read as one page's performance."""
    if WILD in (norm(crop), norm(state), norm(district)):
        return None
    from backend.services import page_stats
    return page_stats.for_page(crop, state, district)


def set_placement(db, buyer_slug: str, crop: str, state: str,
                  district: str = "", rank: int = 1, price: int | None = None):
    """Put one dealer on one pattern. Returns the row, or None if `rank` is out
    of range or the key is unusable.

    Two collisions are resolved here rather than left to the database, because
    both are ordinary admin actions and neither should be an error:

      * somebody else holds this rank on this pattern → they lose it (the panel
        shows who, before you click)
      * this dealer already holds another rank on this pattern → it moves,
        rather than him appearing twice

    Note both are scoped to the *pattern*, not the page. A dealer holding both
    (wheat, up, bareilly) and (wheat, up, *) is legitimate and common — he
    bought two products — and for_page() dedupes him so he still renders once.
    """
    try:
        rank = int(rank)
    except (TypeError, ValueError):
        return None
    if rank not in range(1, SLOTS + 1):
        return None

    crop, state, district = normalise_pattern(crop, state, district)
    if not crop or not state:
        return None
    if crop == WILD and (state == WILD or district in ("", WILD)):
        return None                       # "every crop everywhere" is not sold

    q = db.query(DealerPlacement).filter(
        DealerPlacement.crop_slug == crop,
        DealerPlacement.state_slug == state,
        DealerPlacement.district_slug == district)
    for other in q.all():
        if other.rank == rank or other.buyer_slug == buyer_slug:
            db.delete(other)
    db.flush()

    row = DealerPlacement(
        buyer_slug=buyer_slug, crop_slug=crop, state_slug=state,
        district_slug=district, rank=rank,
        price=price if price is not None else slot_price(crop, state, district),
        created_at=datetime.utcnow(), updated_at=datetime.utcnow())
    db.add(row)
    db.commit()
    db.refresh(row)
    invalidate()
    return row


def clear_placement(db, placement_id: int) -> bool:
    row = db.query(DealerPlacement).filter(DealerPlacement.id == placement_id).first()
    if not row:
        return False
    db.delete(row)
    db.commit()
    invalidate()
    return True


def clear_for_dealer(db, buyer_slug: str) -> int:
    """Called when a listing is deleted. Placements outlive a lapse on purpose,
    but not the row they point at — that would leave a slot held by a dealer
    who no longer exists, and it would look empty rather than wrong."""
    rows = db.query(DealerPlacement).filter(
        DealerPlacement.buyer_slug == buyer_slug).all()
    for r in rows:
        db.delete(r)
    if rows:
        db.commit()
        invalidate()
    return len(rows)


def counts() -> dict:
    """Admin summary: how many slots are sold, and how many dealers are paying
    for nothing because nobody put them on a page."""
    all_rows = _all()
    placed = {p["slug"] for p in all_rows}
    per_tier = {t: 0 for t in TIERS}
    for p in all_rows:
        per_tier[p["tier"]] = per_tier.get(p["tier"], 0) + 1
    return {
        "slots":     len(all_rows),
        "dealers":   len(placed),
        # kept for the existing admin panel, which reads these two by name
        "state":     per_tier["state_page"] + per_tier["state_all"],
        "district":  per_tier["district_crop"] + per_tier["district_all"],
        "per_tier":  per_tier,
        # what the wide plans commit us to, in rupees per season
        "season_value": sum(p["price"] or 0 for p in all_rows),
    }
