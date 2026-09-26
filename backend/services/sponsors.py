# ============================================================
# backend/services/sponsors.py
# The site-wide sponsor — who is paying this month, and what may be shown.
#
# WHAT THIS IS NOT. services/placements.py sells one dealer one slot on one
# /bhav crop page and resolves overlaps by geographic specificity; a sponsor
# here buys the whole site for one category. Two different products, two
# different prices, deliberately two different modules — merged, a ₹199
# district listing and a ₹25,000 category partnership would compete for the
# same render and the cheap one would sometimes win.
#
# READS ARE HOT, WRITES ARE RARE, AND A SALE MUST NOT NEED A DEPLOY. There are
# ~15,000 server-rendered pages and at most a handful of sponsor rows, so the
# file is cached whole and re-read by mtime — the same shape services/buyers.py
# uses for the same reason. Editing backend/data/sponsors.json is enough to put
# a brand live; nothing to re-run, nothing to restart.
#
# EXPIRY IS ENFORCED HERE, NOT REMEMBERED. `until` is a date and the row stops
# rendering the day after it. Sponsorship is the one product on this site where
# over-delivering is the failure mode that costs money: a brand whose month ran
# out and whose logo is still up has no reason to send the next payment, and
# finds out we do not track what we sold. The clock is the product — the same
# argument as services/free_month.py.
#
# CATEGORY EXCLUSIVITY IS THE THING BEING SOLD. It is why a brand pays site
# rates for a site this size, and it is worth more to them than the impressions
# are. Two active sponsors sharing a category silently voids it for both, so
# `active()` drops the later one rather than render both, and
# tests/test_sponsors.py fails the build if the file ever contains the clash.
# ============================================================
import hashlib
import hmac
import json
import logging
import os
import time
from datetime import date
from html import escape
from pathlib import Path

logger = logging.getLogger("krishi.sponsors")

_PATH = Path(__file__).resolve().parents[1] / "data" / "sponsors.json"

_cache: dict | None = None
_mtime: float = -1.0

# The DB half. Same split as services/buyers.py, for the same reason: the JSON
# is the committed seed, the table is what an admin changes at runtime, and
# Render's free plan has no persistent disk — a sponsor written to the file
# would silently revert on the next deploy, taking a paying brand's logo with
# it. Cached briefly because /bhav renders this on ~14k pages.
_db_rows_cache: list | None = None
_db_at: float = -1.0
_DB_TTL = 60.0
_last_db_rows: list = [None]


def _db_rows() -> list[dict]:
    """Sponsor rows from Postgres, or the last good list.

    Swallows every error on purpose: this runs inside page renders, and if Neon
    is asleep, cold-starting or read-only the right outcome is the JSON seed
    and a warning line — never a 500 on the SEO surface.
    """
    global _db_rows_cache, _db_at
    now = time.time()
    if _db_rows_cache is not None and now - _db_at < _DB_TTL:
        return _db_rows_cache
    rows: list[dict] = []
    try:
        from backend.database.db import Sponsor, SessionLocal
        db = SessionLocal()
        try:
            rows = [row_to_dict(r) for r in
                    db.query(Sponsor).filter(Sponsor.active.is_(True)).all()]
        finally:
            db.close()
    except Exception as e:
        logger.warning("sponsor table read failed, using JSON seed only: %s", e)
        rows = _db_rows_cache or []
    _db_rows_cache, _db_at = rows, now
    return rows


def row_to_dict(r) -> dict:
    """A Sponsor row in the shape the render path already understands, so the
    seed and the table stay interchangeable."""
    def _list(v):
        if not v:
            return []
        try:
            out = json.loads(v)
            return out if isinstance(out, list) else []
        except Exception:
            # Tolerates a comma-separated string typed into the panel.
            return [x.strip() for x in str(v).split(",") if x.strip()]
    return {
        "id": r.slug, "active": bool(r.active), "name": r.name or "",
        "category": r.category or "", "line": r.line or "", "url": r.url or "",
        "logo": r.logo or "", "since": r.since or "", "until": r.until or "",
        "sections": _list(r.sections), "states": _list(r.states),
        "crops": _list(r.crops),
    }


def invalidate() -> None:
    """Drop the DB cache so an admin edit shows on the next page load — the
    panel's whole point is putting a brand live while you are on the call."""
    global _db_rows_cache, _db_at
    _db_rows_cache, _db_at = None, -1.0

# Every field a row needs before it may be shown to a farmer. `until` is in
# here because a row without one can never expire, and an unexpiring sponsor
# slot is how a brand ends up advertised for free for a year.
_REQUIRED = ("id", "name", "category", "url", "until")


def _load() -> dict:
    global _cache, _mtime
    try:
        m = _PATH.stat().st_mtime
    except OSError:
        m = -1.0            # no seed file is fine; the table may still have rows
    db_rows = _db_rows()
    if _cache is None or m != _mtime or db_rows is not _last_db_rows[0]:
        if _cache is None or m != _mtime:
            try:
                seed = json.loads(_PATH.read_text(encoding="utf-8"))
            except Exception as e:
                # A syntax error in the seed must not take the site down; it
                # means the table alone decides, which is a working site.
                logger.warning("sponsors.json unreadable, using the table only: %s", e)
                seed = {"sponsors": []}
            _cache = seed
            _mtime = m
        # DB LAST so a row overrides the seed entry sharing its slug — that is
        # what makes a committed sponsor correctable from the panel without a
        # deploy. Order is otherwise preserved, and active() keeps the FIRST
        # row of a category, so a seed entry still wins its category unless it
        # was deliberately overridden by slug.
        merged: dict[str, dict] = {}
        for row in list((_cache or {}).get("sponsors") or []) + db_rows:
            key = str(row.get("id") or f"anon-{len(merged)}")
            merged[key] = row
        _cache = {**(_cache or {}), "sponsors": list(merged.values())}
        _last_db_rows[0] = db_rows
    return _cache


def _live(row: dict, today: date) -> bool:
    if not isinstance(row, dict) or not row.get("active"):
        return False
    if any(not str(row.get(k) or "").strip() for k in _REQUIRED):
        return False
    try:
        return date.fromisoformat(str(row["until"]).strip()) >= today
    except ValueError:
        # An unparseable date is treated as expired, never as forever.
        logger.warning("sponsor %s has an unreadable 'until' — not rendering",
                       row.get("id"))
        return False


def _norm(s: str) -> str:
    return str(s or "").strip().lower().replace("-", "_").replace(" ", "_")


def all_active(today: date | None = None) -> list[dict]:
    """Every live sponsor currently valid in the registry, without category de-duplication.
    Used for click tracking redirects and multi-dimensional state/crop lookups.
    """
    today = today or date.today()
    return [r for r in (_load().get("sponsors") or []) if _live(r, today)]


def active(today: date | None = None) -> list[dict]:
    """Every sponsor that may be rendered right now, one per category.

    Order is the file's own, and the FIRST row of a category wins — so fixing
    an accidental clash is moving a line, not editing a state flag.
    """
    today = today or date.today()
    seen: set[str] = set()
    out: list[dict] = []
    for row in (_load().get("sponsors") or []):
        if not _live(row, today):
            continue
        cat = str(row.get("category") or "").strip().lower()
        if cat in seen:
            logger.warning("two live sponsors in category %r — keeping the first", cat)
            continue
        seen.add(cat)
        out.append(row)
    return out


def _match_sponsor(row: dict, path: str, state: str, crop: str) -> tuple[bool, int]:
    """Checks whether a sponsor matches the requested path, state, and crop.
    Returns (matches: bool, specificity_score: int).
    """
    # 1. Section matching
    secs = row.get("sections") or []
    if secs:
        if not any(path == s or path.startswith(s.rstrip("/") + "/") for s in secs):
            return False, 0

    score = 1 if secs else 0

    # 2. State matching
    row_states = [_norm(s) for s in (row.get("states") or []) if str(s).strip()]
    if row_states:
        if not state:
            return False, 0
        norm_state = _norm(state)
        matched_state = any(norm_state == rs or norm_state in rs or rs in norm_state for rs in row_states)
        if not matched_state:
            return False, 0
        score += 2

    # 3. Crop matching
    row_crops = [_norm(c) for c in (row.get("crops") or []) if str(c).strip()]
    if row_crops:
        if not crop:
            return False, 0
        norm_crop = _norm(crop)
        matched_crop = any(norm_crop == rc or norm_crop in rc or rc in norm_crop for rc in row_crops)
        if not matched_crop:
            return False, 0
        score += 2

    return True, score


def for_path(path: str, state: str | date = "", crop: str = "", today: date | None = None) -> list[dict]:
    """The sponsors allowed on one page. An empty `sections`, `states`, or `crops`
    means universal for that dimension.

    If category collides, the more specific match (State + Crop targeting) wins
    over generic site-wide sponsors.
    """
    if isinstance(state, date):
        today = state
        state = ""
    today = today or date.today()

    candidates: list[tuple[int, int, dict]] = []
    for idx, row in enumerate(_load().get("sponsors") or []):
        if not _live(row, today):
            continue
        matches, score = _match_sponsor(row, path, str(state or ""), str(crop or ""))
        if matches:
            candidates.append((score, idx, row))

    # Sort candidates by:
    # 1. Specificity score descending (highest specificity wins)
    # 2. Original registry position ascending (first row wins on tie)
    candidates.sort(key=lambda x: (-x[0], x[1]))

    seen_categories: set[str] = set()
    out: list[dict] = []
    for score, idx, row in candidates:
        cat = str(row.get("category") or "").strip().lower()
        if cat in seen_categories:
            continue
        seen_categories.add(cat)
        out.append(row)

    return out


def have_any(today: date | None = None) -> bool:
    return bool(active(today))


def card_html(path: str = "/", state: str | date = "", crop: str = "", today: date | None = None) -> str:
    """The rendered sponsor strip, or "" when nobody is paying.

    Returning "" rather than a placeholder is load-bearing: an empty slot that
    still prints its 'प्रायोजक' label is a blank box on ~15,000 pages, and the
    same defect frontend/ads.js already collapses for AdSense.

    The label sits ABOVE the card and is never hidden behind a tooltip or
    buried in Terms. A farmer has to be able to tell in one glance that this
    box was paid for and the price table above it was not — that distinction
    is the entire reason the site is worth sponsoring.
    """
    if isinstance(state, date):
        today = state
        state = ""
    rows = for_path(path, state=str(state or ""), crop=str(crop or ""), today=today)
    if not rows:
        return ""
    cards = []
    for r in rows:
        name = escape(str(r.get("name") or ""))
        line = escape(str(r.get("line") or ""))
        # /go/s/<id> mirrors the /go/<id> lead-click rail: the destination can
        # be swapped in one place, and we can tell a sponsor how many farmers
        # actually tapped through without asking them to trust our word for it.
        href = escape(f"/go/s/{r.get('id')}", quote=True)
        logo = str(r.get("logo") or "").strip()
        img = (f'<img class="km-sp-logo" src="{escape(logo, quote=True)}" alt="{name}" '
               f'width="56" height="56" loading="lazy" decoding="async">') if logo else ""
        cards.append(
            f'<a class="km-sp-card" href="{href}" rel="nofollow sponsored" '
            f'target="_blank">{img}<span class="km-sp-text">'
            f'<b class="km-sp-name">{name}</b>'
            + (f'<span class="km-sp-line">{line}</span>' if line else "")
            + '</span><span class="km-sp-go">→</span></a>')
    return ('<aside class="km-sp" aria-label="प्रायोजक">'
            '<p class="km-sp-label">प्रायोजक · Sponsored</p>'
            + "".join(cards) + '</aside>')


# ── The rate card ───────────────────────────────────────────────────────────
# Lives here, beside the registry, so the public page, a future admin collect
# modal and a renewal email cannot quote different prices for one thing.
#
# Kharif Harvest & Rabi Sowing Season packages (60-day campaign terms).
# Pricing reflects high-intent rural purchase traffic, category exclusivity,
# permanent SEO guide equity, and WhatsApp channel integration.
MIN_MONTHS = 2
# ── The private media kit ───────────────────────────────────────────────────
# WHY THE NUMBERS ARE NOT ON THE PUBLIC PAGE. The owner's instruction, 2026-09-18:
# the Search Console figures must not be readable by anyone who opens the URL.
# A public page carrying 1.5M impressions, a per-section breakdown and a URL
# count is a competitive disclosure — it tells every other agri site exactly
# which surfaces work and how big they are — and it is worth far more to a
# competitor than it is to the one brand we are actually pitching.
#
# So /sponsor sells without the figures, and the figures live behind an
# unguessable per-prospect link that we hand out deliberately.
#
# FAIL CLOSED. With KM_SPONSOR_KIT_SECRET unset there is no valid token at all
# and the kit route 404s for everyone, including us. That is the correct
# default for a surface whose only job is to not leak: the numbers stay
# private until someone deliberately turns the mechanism on, rather than
# leaking because a deploy forgot an env var.
#
# ONE LINK PER PROSPECT, and the slug is inside the signature — so a link we
# sent to one brand cannot be edited into another's, an unexpected visit is
# attributable to whoever we gave that slug to, and rotating the secret
# revokes every outstanding link at once.
_SECRET_ENV = "KM_SPONSOR_KIT_SECRET"
_SIG_LEN = 16          # 64 bits of truncated HMAC — unguessable, still short
                       # enough to paste into an email without wrapping.


def _secret() -> str:
    return (os.getenv(_SECRET_ENV) or "").strip()


def kit_enabled() -> bool:
    return bool(_secret())


def kit_token(slug: str) -> str:
    """The token for one prospect. `slug` is our own label for them — a company
    name, lowercased — and it travels in the clear so an incoming request tells
    us who we gave it to."""
    slug = _norm(slug).replace(" ", "-")
    if not slug or not kit_enabled():
        return ""
    sig = hmac.new(_secret().encode(), slug.encode(), hashlib.sha256).hexdigest()
    return f"{slug}.{sig[:_SIG_LEN]}"


def kit_verify(token: str) -> str | None:
    """The prospect slug if this token is one we issued, else None.

    compare_digest, not ==, because a plain comparison leaks how much of a
    guessed signature was right through its timing, which is the whole attack
    against a truncated MAC.
    """
    if not kit_enabled() or not token or "." not in token:
        return None
    slug, _, sig = token.rpartition(".")
    expect = kit_token(slug)
    if not expect:
        return None
    return slug if hmac.compare_digest(expect, f"{slug}.{sig}") else None


MIN_DAYS = 60

RATE_CARD = [
    {
        "id": "title",
        "name": "Harvest Season Presenting Partner",
        "price": 190000,
        "price_extra": "– ₹3,75,000",
        "badge": "Title Sponsor · 1 Brand Only",
        "unit": "60-day harvest window · priced by scope",
        "highlight": True,
        "gets": [
            "Banner on every page, clearly labelled 'प्रायोजक · Sponsored' and never on the mandi prices.",
            "100% category exclusivity across the entire site — zero competitor ads. Articles, prices and advice never change.",
            "A 'प्रायोजक · Sponsored' line under the daily WhatsApp price posts in all 31 agricultural states.",
        ],
    },
    {
        "id": "category",
        "name": "Category Exclusive Partner",
        "price": 95000,
        "price_extra": "– ₹1,90,000",
        "badge": "Category Lock · 4 Brands Max",
        "unit": "60-day campaign · priced by category",
        "highlight": False,
        "gets": [
            "100% category exclusivity (Tractors, Seeds, Crop Protection, or Solar Pumps) — zero competitor ads.",
            "Prominent labelled sponsor card on top of price data tables for relevant crops.",
            "A 'प्रायोजक · Sponsored' line under the WhatsApp channel posts in your top 5 priority states.",
            "One Hindi guide in your category, labelled Sponsored; the advice itself stays independent.",
        ],
    },
    {
        "id": "state",
        "name": "State Champion Regional Partner",
        "price": 30000,
        "price_extra": "– ₹75,000",
        "badge": "Geo-Targeted · Per State",
        "unit": "60-day campaign · per state",
        "highlight": False,
        "gets": [
            "Direct 'Find Authorized Dealer' button routing farmers directly to your local distribution network.",
            "A 'प्रायोजक · Sponsored' line under the daily WhatsApp price post in your state's channel.",
        ],
    },
    {
        "id": "guide",
        "name": "Sponsored Hindi Guide",
        "price": 20000,
        "price_extra": "– ₹40,000",
        "badge": "Labelled · Stays Published",
        "unit": "per guide · written and hosted by us",
        "highlight": False,
        "gets": [
            "A Hindi guide on a topic in your category, written by our team and labelled Sponsored.",
            "Your brand named with a tracked link; the advice itself stays independent.",
            "Stays published on the site after the campaign ends.",
        ],
    },
    {
        "id": "custom",
        "name": "Custom Sponsorship",
        "price": 125000,
        "price_extra": "+",
        "badge": "Built Around Your Brand",
        "unit": "Price and services agreed with you directly",
        "highlight": False,
        "gets": [
            "A package shaped around your brand, season and target states.",
            "Price and services are confirmed on WhatsApp, a call or email.",
            "WhatsApp / Call: +91 98709 51001",
            "Email: krashimitra038@gmail.com",
        ],
    },
]

# ── when to raise the prices ───────────────────────────────────────────────
#
# The rate card is priced per visitor: ~₹2–5 of search traffic per rupee, set
# on the audience the site had on PRICED_FOR["date"]. Traffic was doubling
# every couple of weeks when it was set, so a card that is right today is
# underpriced within a month — and nobody opens a file to check. So the daily
# GSC job compares recent search clicks against the baseline below and, the
# first time traffic crosses each step in REVIEW_STEPS, emails the owner the
# suggested new prices. The admin Sponsors panel shows the same banner.
#
# WHEN YOU CHANGE A PRICE, UPDATE PRICED_FOR TOO — the date, the card, and the
# KM_SPONSOR_BASE_CLICKS env var (search clicks/day on that date). The clicks
# figure lives in the ENVIRONMENT, not here: this repo is public and the
# site's Search Console numbers are exactly what /sponsor keeps private.
# Unset, the review stays silent rather than guessing. tests/test_sponsor.py
# fails if RATE_CARD and PRICED_FOR["card"] disagree.
PRICED_FOR = {
    "date": "2026-09-26",
    "clicks_per_day": int(os.getenv("KM_SPONSOR_BASE_CLICKS") or 0),
    "card": {"title": 190000, "category": 95000, "state": 30000,
             "guide": 20000, "custom": 125000},
}
REVIEW_STEPS = (1.5, 2, 3, 4, 5, 7, 10)
_REVIEW_STATE = Path(__file__).resolve().parents[2] / "cache" / "price_review.json"


def _round_price(v: float) -> int:
    step = 5000 if v >= 50000 else 1000
    return int(round(v / step) * step)


def price_review(stats: dict | None = None) -> dict | None:
    """None while the card still fits the traffic; otherwise how far traffic
    has grown and what each tier would cost at the same per-visitor rate."""
    if stats is None:
        try:
            from backend.services import mediakit
            stats = mediakit.stats()
        except Exception:
            stats = None
    series = (stats or {}).get("series") or []
    last = [int(r.get("c") or 0) for r in series[-7:]]
    if len(last) < 7:
        return None
    avg = sum(last) / 7
    base = PRICED_FOR["clicks_per_day"]
    if base <= 0:
        return None                     # KM_SPONSOR_BASE_CLICKS not set
    ratio = avg / base
    steps = [s for s in REVIEW_STEPS if ratio >= s]
    if not steps:
        return None
    return {
        "avg_clicks": int(round(avg)),
        "base_clicks": base,
        "priced_on": PRICED_FOR["date"],
        "ratio": round(ratio, 1),
        "step": steps[-1],
        "suggest": [{"id": t["id"], "name": t["name"], "now": t["price"],
                     "new": _round_price(t["price"] * ratio)} for t in RATE_CARD],
    }


def price_review_check() -> dict | None:
    """Daily, from gsc_scheduler. Mails once per step per baseline — a new
    PRICED_FOR date (i.e. the prices were updated) starts the steps over."""
    r = price_review()
    if not r:
        return None
    try:
        seen = json.loads(_REVIEW_STATE.read_text(encoding="utf-8"))
    except Exception:
        seen = {}
    if seen.get("priced_on") == r["priced_on"] and seen.get("step", 0) >= r["step"]:
        return r
    lines = [
        f"Search traffic is now {r['ratio']}× what the sponsor prices were set for.",
        f"Last 7 days: ~{r['avg_clicks']:,} visits/day from Google "
        f"(prices set on {r['priced_on']} for ~{r['base_clicks']:,}/day).",
        "",
        "Suggested starting prices at the same per-visitor rate:",
    ]
    lines += [f"• {s['name']}: ₹{s['now']:,} → ₹{s['new']:,}" for s in r["suggest"]]
    lines += ["",
              "Existing sponsors keep their price until renewal; raise it then.",
              "To apply: update RATE_CARD and PRICED_FOR in backend/services/sponsors.py."]
    try:
        from backend.services.infra_service import _mail
        _mail(f"KrashiMitra: traffic {r['ratio']}× — time to raise sponsor prices",
              "\n".join(lines))
    except Exception as e:
        logger.warning("price review mail failed: %s", e)
        return r
    try:
        _REVIEW_STATE.parent.mkdir(parents=True, exist_ok=True)
        _REVIEW_STATE.write_text(json.dumps({"priced_on": r["priced_on"], "step": r["step"]}),
                                 encoding="utf-8")
    except Exception:
        pass
    return r


# What money cannot buy here, printed on /sponsor as prominently as the prices.
# This is a selling point and not a disclaimer: the reason a farmer trusts a
# price on this site is that no one can pay to change it, and a sponsor is
# buying that trust rather than borrowing against it.
NEVER_FOR_SALE = [
    "Mandi prices. They come from Agmarknet and no one can pay to change, "
    "delay or hide one.",
    "Ranking and search results. Not on /bhav, not on /khoj, not in the "
    "shop directory — ordering is by distance and relevance, never by who paid.",
    "Advice in an article. If a guide recommends a dose or a variety, that is "
    "what we believe, and a sponsor cannot edit it.",
    "A dofollow link. Every sponsor link is rel=\"nofollow sponsored\", which "
    "is what Google requires and what protects both of us.",
    "An unlabelled placement. Every sponsor unit says प्रायोजक · Sponsored, "
    "above the card, in the markup.",
]


CSS = """
.km-sp{margin:26px 0;padding:0}
.km-sp-label{font-size:11.5px;letter-spacing:.08em;text-transform:uppercase;
color:var(--text-soft,#8a8a7e);margin:0 0 7px;font-weight:700}
.km-sp-card{display:flex;align-items:center;gap:13px;padding:14px 15px;
background:var(--white,#fff);border:1px solid var(--border,#e4e2d8);
border-radius:var(--radius-sm,10px);text-decoration:none;color:inherit}
.km-sp-logo{flex:0 0 auto;width:56px;height:56px;object-fit:contain;border-radius:8px}
.km-sp-text{flex:1 1 auto;min-width:0}
.km-sp-name{display:block;font-size:15.5px;font-weight:700;
color:var(--green-dark,#2c5c2e);line-height:1.35}
.km-sp-line{display:block;font-size:13.5px;color:var(--text-mid,#5a5a50);
line-height:1.6;margin-top:2px}
.km-sp-go{flex:0 0 auto;font-size:18px;color:var(--text-soft,#8a8a7e)}
"""
