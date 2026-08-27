# ============================================================
# routes/rental.py
# किराये की मशीनें — /rental, the farm-equipment hire section
#
# THREE PAGES, ONE IDEA.
#   /rental                     every machine a farmer can hire, by category
#   /rental/{equipment}         that machine's rate, and who near him has one
#   /rental/{equipment}/{owner} one owner's rate + how to reach him
#
# THE LAYOUT IS /bhav's AND /product's, NOT A COPY OF EITHER. The page shell
# (CSS tokens, header, footer, FAQ/breadcrumb JSON-LD) comes from bhav.py and
# the card/hero/grid CSS is imported straight out of product.py's _EXTRA_CSS —
# exactly the way product.py imports the shell and krashi_dukan.py imports
# both. Four SEO surfaces, one stylesheet: a change to the product card lands
# on all of them and they can never drift apart.
#
# TWO LAYERS, AND THE PAGE SAYS WHICH ONE IT IS SHOWING.
#   The CATALOGUE — what a machine is, what it should cost, what to check — is
#   editorial, from data/rental_equipment.json, read live by mtime.
#   The SUPPLY — named owners, CHCs and FPOs with a rate they will honour — is
#   Postgres (RentalProvider / RentalListing), typed in through /admin/rental.
# When owners exist the page LEADS with their real rates and the estimate
# becomes background; when none do, the estimate is all there is and the page
# routes the farmer to the government CHC instead. The two are never blended
# into one number, because "what this should cost" and "what this man charges"
# are different claims.
#
# WE ARE NOT THE OWNER, AND THERE IS NO BOOKING HERE. No cart, no deposit, no
# commission taken from the farmer, no guarantee — we connect and stop. Said in
# Hindi on every page rather than buried in Terms.
#
# Offer JSON-LD IS EMITTED ONLY WHEN REAL OWNERS ARE LISTED. An Offer needs a
# seller and a price someone will honour; an editorial range has neither, so
# marking one up as an offer would be a false claim in structured data. Same
# rule krashi_dukan.py follows, and there is a test that fails the build if an
# estimate ever acquires one.
#
# RANKED BY DISTANCE, NEVER BY WHO PAID. Inherited unchanged from krashi_dukan:
# a directory whose order can be bought stops being worth reading.
# ============================================================

import re
from html import escape
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from backend.database.db import get_db

from backend.routes.bhav import (
    _ANALYTICS, _CSS as _BASE_CSS, _FONTS, _ICON, _crumb_ld, _doc, _faq,
    _fit, _footer, _header, _ld,
)
from backend.routes.product import _EXTRA_CSS as _PRODUCT_CSS
from backend.services import free_month, rental

router = APIRouter()

SITE = "https://krashimitra.in"
BASE = f"{SITE}/rental"

# The disclaimer, in one place, on every page of this section — because "we
# are not the owner" is worth nothing to a farmer who never read it.
#
# TWO WORDINGS, BECAUSE THE PAGE MAKES TWO DIFFERENT CLAIMS. Where the numbers
# are our editorial estimate, saying so is the whole point. Where a named owner
# has quoted a rate he will honour, calling it an estimate would be false — and
# worse, it would teach the farmer to discount a number that is actually firm.
# What stays true in both: we do not own the machine and we take no booking.
_NOT_OURS = "कृषि मित्र मशीन किराये पर नहीं देता — हम सिर्फ़ जोड़ने का काम करते हैं। "

DISCLAIMER = (_NOT_OURS +
              "यहाँ दिए किराये अनुमानित हैं — असली रेट मशीन मालिक, इलाके, सीज़न और "
              "डीज़ल के दाम पर निर्भर करता है। सौदा तय करने से पहले मशीन देख लें और "
              "रेट में क्या-क्या शामिल है यह लिखवा लें।")

DISCLAIMER_LISTED = (_NOT_OURS +
                     "नीचे दिए रेट मालिक के अपने बताए हुए हैं, हमारे नहीं — और बदल सकते हैं। "
                     "न हम बुकिंग करते हैं, न किसी मशीन या सौदे की गारंटी लेते हैं। "
                     "जाने से पहले फ़ोन करके रेट और मशीन की उपलब्धता पक्की कर लें।")

# The one honest answer to "अभी किराये पर कहाँ से लूँ" while we have no
# providers listed: the government's own custom-hiring network. Both are real,
# free and national — a farmer sent here is not sent to a dead end.
_CHC_URL = "https://agrimachinery.nic.in/"
_FARMS_URL = "https://play.google.com/store/apps/details?id=com.cdac.farms"

# ── the way IN, for pages that are not this one ──────────────
#
# A farmer standing on /krashi_dukan is buying inputs; the machine he needs for
# the same job is one section away and he has no way of knowing it exists. This
# is that pointer — and it lives HERE, beside the section it advertises, so
# every entry point into /rental reads the same and a change lands on all of
# them at once. Callers append CROSS_CSS to their own extra_css; they cannot
# reach this module's _CSS closure (see _doc's note on extra_css).
CROSS_CSS = """
.km-cross{margin:22px 0 0;padding:15px 16px 14px;border-radius:14px;background:var(--white);
border:1px solid var(--border);border-left:4px solid var(--green-light);box-shadow:var(--shadow-sm)}
.km-cross-head{display:flex;align-items:center;gap:14px;text-decoration:none;color:inherit}
.km-cross-ic{flex:0 0 auto;width:40px;height:40px;border-radius:50%;background:var(--green-pale);
display:flex;align-items:center;justify-content:center;font-size:20px}
.km-cross-t{flex:1 1 auto;min-width:0}
.km-cross-t b{display:block;font-size:14.5px;font-weight:800;color:var(--text-dark);line-height:1.3}
.km-cross-t span{display:block;font-size:12px;color:var(--text-mid);line-height:1.45;margin-top:2px}
.km-cross-go{flex:0 0 auto;font-size:13px;font-weight:800;color:var(--green-dark);white-space:nowrap}
.km-cross-head:hover .km-cross-go{text-decoration:underline}

/* the machines themselves — the whole point of the expanded card */
.km-cross-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-top:13px}
@media(min-width:560px){.km-cross-grid{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(min-width:900px){.km-cross-grid{grid-template-columns:repeat(6,minmax(0,1fr))}}
.km-chip{display:flex;flex-direction:column;gap:3px;padding:9px 10px;border-radius:10px;
background:var(--cream);border:1px solid var(--border);text-decoration:none;color:inherit;
transition:background .15s,border-color .15s}
.km-chip:hover{background:var(--green-pale);border-color:var(--green-light)}
.km-chip-e{font-size:17px;line-height:1}
.km-chip b{font-size:12.5px;font-weight:700;color:var(--text-dark);line-height:1.28}
.km-chip i{font-style:normal;font-size:11.5px;font-weight:700;color:var(--green-dark);line-height:1.25}
.km-chip i span{display:block;font-weight:400;font-size:10px;color:var(--text-soft);margin-top:1px}
.km-cross-all{display:inline-block;margin-top:12px;font-size:12.5px;font-weight:700;
color:var(--green-dark);text-decoration:none}
.km-cross-all:hover{text-decoration:underline}
@media(max-width:560px){.km-cross{padding:13px 13px 12px}
.km-cross-head{gap:10px}.km-cross-t b{font-size:13.5px}.km-cross-go{font-size:12.5px}}
"""


def _cross_picks(limit: int = 6) -> list[dict]:
    """One machine from each category, in file order.

    Breadth is the message. Six chips running जुताई → ढुलाई say "there is a
    whole section behind this card" in a way the six most popular machines
    never could — those would all be tillage, and the card would read as a
    tractor advert. Tops up from the flat registry if the file ever ships
    fewer categories than `limit`.
    """
    picks = [items[0] for _, items in rental.by_category() if items][:limit]
    if len(picks) < limit:
        seen = {e["slug"] for e in picks}
        picks += [e for e in rental.equipment()
                  if e["slug"] not in seen][:limit - len(picks)]
    return picks


def _cross_chip(item: dict) -> str:
    """One machine, its emoji, and the rate a farmer would actually be quoted.

    The unit keeps its parenthetical off — "प्रति घंटा (चालक सहित)" is right on
    the machine's own page, but in a 160px chip it wraps to three lines and
    buries the number that makes the card worth reading.
    """
    r    = rental.headline_rate(item)
    unit = (r or {}).get("unit_hi", "").split("(")[0].strip()
    return (f'<a class="km-chip" href="{BASE}/{escape(item["slug"])}">'
            f'<span class="km-chip-e">{escape(item.get("emoji", ""))}</span>'
            f'<b>{escape(item["name_hi"])}</b>'
            f'<i>{escape(rental.rate_text(r))}'
            + (f'<span>{escape(unit)}</span>' if unit else "")
            + "</i></a>")


def cross_link(sub: str = "") -> str:
    """A card pointing at /rental, for another section to render.

    THE CARD NAMES REAL MACHINES ON PURPOSE. A one-line teaser asks the farmer
    to take it on faith that a hire section exists; six machines with six real
    rates prove it before he taps, and each chip is a direct link into the tree
    rather than a second hop through the hub. That also gives /rental the
    static internal links its pages need to get crawled at all — the same gap
    that kept /bhav out of the index until July.

    `sub` lets the host page say why it is showing this — a product page can
    name the job the farmer is already there for. Default copy works anywhere.
    """
    n     = len(rental.equipment())
    chips = "".join(_cross_chip(e) for e in _cross_picks())
    return cross_card(
        BASE, "🚜", "मशीन खरीदनी नहीं, किराये पर चाहिए?",
        sub or "खेत के हर काम की मशीन — जुताई से कटाई तक, हर एक का सही किराया।",
        extra=f'<div class="km-cross-grid">{chips}</div>'
              f'<a class="km-cross-all" href="{BASE}">'
              f'पूरी सूची — {n} मशीनों का किराया देखें →</a>')


def cross_card(href: str, icon: str, head: str, sub: str, extra: str = "") -> str:
    """The shell EVERY cross-section card is built from — both directions.

    It exists because the alternative already broke once: the card pointing at
    कृषि दुकान was hand-written at its call site, and when this card grew a
    `.km-cross-head` row (so the container could hold chips underneath), the
    stylesheet and the copy moved together while the hand-written twin did not.
    It kept the container's border and lost `display:flex` and
    `text-decoration:none`, so it rendered as a tall empty box with a blue
    underlined heading — styled enough to look deliberate, wrong enough to look
    broken.

    So: one renderer beside the one stylesheet. A caller supplies what differs
    and nothing else, and `extra` carries whatever sits under the head row.
    """
    return f"""<div class="km-cross">
<a class="km-cross-head" href="{href}">
<div class="km-cross-ic">{icon}</div>
<div class="km-cross-t">
<b>{escape(head)}</b>
<span>{escape(sub)}</span>
</div>
<span class="km-cross-go">देखें →</span>
</a>
{extra}
</div>"""


def dukan_link(sub: str = "") -> str:
    """A card pointing at कृषि दुकान, for /rental to render.

    It lives here rather than in krashi_dukan.py only because that module
    already imports this one — the reverse import would be a cycle. The CSS it
    needs is this module's CROSS_CSS, which /rental already carries.
    """
    return cross_card(
        f"{SITE}/krashi_dukan", "🏪", "बीज, खाद या दवा चाहिए?",
        sub or "कृषि दुकान पर अपने ज़िले की दुकानों के आज के भाव देखें और सीधे दुकान से खरीदें।")


# ── the supply side, rendered ───────────────────────────────

_OWNER_CSS = """
/* ── owner rows under a machine ── */
.rent-owners{display:flex;flex-direction:column;gap:10px;margin-top:14px}
.rent-owner{display:flex;gap:14px;align-items:stretch;background:var(--white);
border:1px solid var(--border);border-radius:var(--radius-md);padding:13px 15px;
box-shadow:var(--shadow-sm);text-decoration:none;color:inherit;
transition:transform .15s,box-shadow .15s,border-color .15s}
.rent-owner:hover{transform:translateY(-2px);box-shadow:var(--shadow-md);border-color:var(--green-light)}
.rent-owner-main{flex:1;min-width:0}
.rent-owner-name{font-size:14.5px;font-weight:700;color:var(--text-dark);line-height:1.3}
.rent-owner-where{display:block;font-size:11.5px;color:var(--text-soft);margin-top:2px}
.rent-owner-meta{display:flex;flex-wrap:wrap;gap:6px;margin-top:7px}
.rent-tag{font-size:10.5px;font-weight:700;padding:2px 8px;border-radius:10px;
background:var(--cream);color:var(--text-mid);white-space:nowrap}
.rent-tag.tick{background:#e7f6ed;color:#1b7a45}
.rent-tag.km{background:#eaf1fb;color:#22508f}
.rent-tag.out{background:#fdeceb;color:#b23b2e}
.rent-tag.fuel{background:#fff4e0;color:#8a5a00}
.rent-owner-rate{text-align:right;flex-shrink:0;display:flex;flex-direction:column;
justify-content:center;gap:2px}
.rent-owner-rate b{font-size:19px;font-weight:700;color:var(--green-dark);line-height:1.1}
.rent-owner-rate .unit{font-size:10.5px;color:var(--text-soft)}
.rent-owner-note{font-size:11.5px;color:var(--text-mid);margin-top:6px;font-style:italic}

.rent-geo-hint{font-size:12px;color:var(--text-soft);margin:12px 0 0;
display:flex;align-items:center;gap:7px;flex-wrap:wrap}
.rent-geo-btn{background:var(--green-pale);color:var(--green-dark);border:none;
font-family:inherit;font-size:12px;font-weight:700;padding:5px 12px;border-radius:14px;cursor:pointer}
.rent-geo-btn:hover{background:var(--green-light);color:#fff}

/* ── one owner's own card on the offer page ── */
.rent-card{background:var(--white);border:1px solid var(--border);
border-radius:var(--radius-md);padding:16px 18px;box-shadow:var(--shadow-sm);margin-top:14px}
.rent-card h3{margin:0 0 10px;font-size:15px;color:var(--text-dark)}
.rent-kv{display:flex;flex-direction:column;gap:9px}
.rent-kv div{display:flex;gap:12px;font-size:13px;line-height:1.5}
.rent-kv span{flex-shrink:0;width:100px;color:var(--text-soft);font-size:12px}
.rent-kv b{font-weight:600;color:var(--text-dark);min-width:0;word-break:break-word}

@media(max-width:560px){
.rent-owner{padding:11px 12px;gap:10px}
.rent-owner-rate b{font-size:17px}
.rent-kv span{width:84px}
}
"""

# The client-side nearest sort. Kept inline and dependency-free: a farmer who
# has not shared his location must still see a complete, ordered list, and this
# must work before any other script loads. Same shape as krashi_dukan's — the
# server renders a default order, the client swaps to nearest once km_geo is
# known, because the server has no farmer to measure from.
_EXTRA_CSS = _PRODUCT_CSS + CROSS_CSS + _OWNER_CSS + free_month.CSS + """
/* ── photo tiles ──
   product.py's card art is a product cut-out on white, so it is sized to sit
   INSIDE the band with padding (object-fit:contain). These are photographs of
   machines in fields — they must fill the band edge to edge, or the card shows
   a small picture floating in a cream box. Only tiles that actually carry a
   photo are touched: an emoji tile still needs its padding, and /product's own
   cards are not affected because this sheet is this section's alone. */
.prod-card-photo.has-photo{padding:0}
.prod-card-photo.has-photo img{display:block;width:100%;height:100%;
max-width:none;max-height:none;object-fit:cover}
.answer-prod-photo-lg.has-photo{padding:0;background:var(--cream)}
.answer-prod-photo-lg.has-photo img{width:100%;height:100%;object-fit:cover}
@media(max-width:560px){
.prod-card-photo.has-photo{padding:0}
.prod-card-photo.has-photo img{object-fit:cover}
/* The hero keeps `cover` on a phone as well. product.py switches to `contain`
   there because a portrait bag or bottle gets its label cropped off; a machine
   photographed in a field is landscape and still reads as that machine when
   cropped square, whereas `contain` shrinks it to a stamp inside a 104px box. */
.answer-prod-photo-lg.has-photo img{object-fit:cover}
}

/* ── rate table on an equipment page ── */
.rent-rates{display:flex;flex-direction:column;gap:9px;margin-top:14px}
.rent-rate{display:flex;align-items:center;gap:14px;background:var(--white);
border:1px solid var(--border);border-radius:var(--radius-md);padding:13px 16px;
box-shadow:var(--shadow-sm)}
.rent-rate-unit{flex:1;min-width:0;font-size:13.5px;font-weight:600;color:var(--text-mid);line-height:1.4}
.rent-rate-val{flex-shrink:0;font-size:18px;font-weight:700;color:var(--green-dark);
letter-spacing:-.3px;white-space:nowrap}
.rent-basis{font-size:11.5px;color:var(--text-soft);margin-top:10px;line-height:1.6}

/* ── "क्या जाँचें" / "काम की बात" lists ── */
.rent-list{list-style:none;display:flex;flex-direction:column;gap:8px;margin-top:12px}
.rent-list li{position:relative;background:var(--white);border:1px solid var(--border);
border-radius:var(--radius-sm);padding:11px 14px 11px 40px;font-size:13px;
color:var(--text-mid);line-height:1.6;box-shadow:var(--shadow-sm)}
.rent-list li::before{content:"✓";position:absolute;left:14px;top:11px;
color:var(--green-light);font-weight:800;font-size:13px}
.rent-list.tips li::before{content:"💡";font-size:12px;left:13px}

/* ── how to actually hire it today ── */
.rent-book{background:var(--white);border:1px solid var(--border);
border-radius:var(--radius-md);padding:16px 18px;box-shadow:var(--shadow-sm);margin-top:14px}
.rent-book h3{margin:0 0 6px;font-size:15px;color:var(--text-dark)}
.rent-book p{font-size:13px;color:var(--text-mid);line-height:1.65}
.rent-book .cta-row{margin:14px 0 0}

/* ── the "we only tell you the rate" strip ── */
.rent-note{background:#fff8e6;border:1px solid #f0dca8;border-radius:var(--radius-md);
padding:12px 15px;font-size:12.5px;color:#6b5312;line-height:1.6;margin:20px 0 0}
.rent-note b{color:#4a3908}

/* the card's stat line — spec + how it's charged, under the rate */
.rent-card-spec{font-size:10.5px;color:var(--text-soft);margin-top:3px;line-height:1.4}

@media(max-width:560px){
.rent-rate{padding:11px 13px;gap:10px}
.rent-rate-val{font-size:16px}
.rent-rate-unit{font-size:12.5px}
/* A rate RANGE is twice the characters .answer-rupee was sized for on /bhav,
   and these are four-digit ranges ("₹1600–₹2600") — at the inherited 38px it
   wraps to two lines inside the ~200px info column left beside the tile on a
   390px phone. Same fix, same reasoning, as krashi_dukan.py's .rng. */
.answer-rupee.rng{font-size:24px;line-height:1.2}
.answer-rupee.rng small{font-size:12px}
}
"""

# One sheet for the hand-built 404 below, same trick product.py uses.
_CSS = _BASE_CSS + _EXTRA_CSS


# ── small helpers ───────────────────────────────────────────

# Photographs live in frontend/images/rental/, fetched and licence-checked by
# tools/fetch_rental_images.py, and credited on /articles/credits.
_IMG_DIR = Path(__file__).resolve().parents[2] / "frontend" / "images" / "rental"
_IMG_URL = "/images/rental"
_img_cache: dict = {"mtime": -1.0, "slugs": frozenset()}


def _photo_slugs() -> frozenset:
    """Which machines actually have a committed photo, read off the DIRECTORY.

    Scanned rather than assumed from a list, because a missing static file on
    this site answers 200 with the SPA's HTML instead of 404 — so a wrong src
    does not fail loudly, it renders an empty grey box that nobody ever hears
    about. If the file is not on disk, the emoji tile is used and the page is
    still complete.

    Re-scanned when the directory's mtime changes, so dropping a new photo in
    needs no restart ("everything automatic"). A missing directory is a normal
    state, not an error — every tile simply stays an emoji.
    """
    try:
        m = _IMG_DIR.stat().st_mtime
    except OSError:
        return frozenset()
    if m != _img_cache["mtime"]:
        try:
            _img_cache["slugs"] = frozenset(
                f.stem for f in _IMG_DIR.glob("*.webp"))
            _img_cache["mtime"] = m
        except OSError:
            return _img_cache["slugs"]
    return _img_cache["slugs"]


def _tile(item: dict, cls: str, size: int, eager: bool = False) -> str:
    """A photograph of the machine, or an emoji where we have none.

    The alt text names the machine in Hindi AND English and says it is for
    hire, because these tiles are the only images this section has and image
    search is a real entry point for "ट्रैक्टर किराया".

    `width`/`height` are the file's true size, so the box reserves its space
    before the image lands and nothing shifts under a farmer's thumb on a slow
    connection.

    `eager` is for the ONE image above the fold — an equipment page's hero.
    That image is the page's LCP element, and `loading="lazy"` on an LCP image
    defers the very fetch the metric is timing. Everything else stays lazy:
    the hub grid is 24 photos and a farmer on mobile data must not pay for the
    ones he never scrolls to.
    """
    slug = item.get("slug") or ""
    if slug in _photo_slugs():
        name_en = item.get("name_en") or ""
        alt = f"{item['name_hi']} किराये पर" + (f" — {name_en} on rent" if name_en else "")
        loading = "eager" if eager else "lazy"
        priority = ' fetchpriority="high"' if eager else ""
        return (f'<div class="{cls} has-photo">'
                f'<img src="{_IMG_URL}/{escape(slug)}.webp" alt="{escape(alt)}" '
                f'loading="{loading}"{priority} decoding="async" '
                f'width="400" height="300"></div>')
    return (f'<div class="{cls}" style="display:flex;align-items:center;'
            f'justify-content:center;font-size:{size}px">{escape(item.get("emoji") or "🚜")}</div>')


def _headline(item: dict) -> tuple[str, str]:
    """(rate range, how it is charged) — the pair every surface shows together.

    Never one without the other: "₹1600–₹2600" means nothing until the farmer
    knows whether that is per acre or per hour, and those differ by machine.
    """
    r = rental.headline_rate(item)
    return rental.rate_text(r), (r or {}).get("unit_hi", "")


def _unit_short(unit_hi: str) -> str:
    """A rate's unit trimmed to its core — "प्रति एकड़ (एक चक्कर)" → "प्रति एकड़".

    Only for the <title>, where the qualifier costs characters against a 68-char
    budget and says nothing a searcher typed. The full unit is what the rate
    table, the hero and the FAQ show, because there the qualifier IS the answer.
    """
    u = re.sub(r"\s*\([^)]*\)", "", unit_hi or "")   # "(चालक सहित)", "(एक चक्कर)"
    u = re.sub(r"^.*?—\s*", "", u)                    # "जुताई — प्रति एकड़"
    return re.sub(r"\s+", " ", u).strip()


def _units_phrase(item: dict) -> str:
    """How this machine is actually charged, for its title — "प्रति एकड़ व प्रति घंटा".

    Derived from the machine's own rate lines rather than hardcoded, because
    they genuinely differ: a seed drill is only ever quoted per acre, a thresher
    per quintal, a trolley per trip. Writing one fixed phrase across all 24
    pages would both claim rates that do not exist and hand Google two dozen
    near-identical titles.
    """
    seen, out = set(), []
    for r in rental.rates(item):
        u = _unit_short(r["unit_hi"])
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return " व ".join(out[:2])


def _card(item: dict, listed: dict | None = None) -> str:
    """The /product hub card, told what this section knows: a rate range and
    the unit it is charged in, instead of one shelf price.

    `listed` is the live-supply rollup for this machine, when there is any. It
    REPLACES the editorial range with the real one owners are quoting — a page
    with three actual rates should lead with those, not with an estimate.
    """
    if listed and listed.get("providers"):
        lo, hi = listed["min_rate"], listed["max_rate"]
        rate = f"₹{lo}" if lo == hi else f"₹{lo}–₹{hi}"
        n = listed["providers"]
        unit = f"{n} मालिक के पास उपलब्ध"
    else:
        rate, unit = _headline(item)
    return f"""<a class="prod-card" href="{BASE}/{item['slug']}">
{_tile(item, "prod-card-photo", 40)}
<div class="prod-card-body">
<div class="prod-card-name">{escape(item['name_hi'])}</div>
<span class="prod-card-en">{escape(item.get('name_en') or '')}</span>
<div class="prod-card-price"><b>{rate}</b></div>
<div class="prod-card-unit">{escape(unit)}</div>
<div class="rent-card-spec">{escape(item.get('spec_hi') or '')}</div>
</div>
</a>"""


def _own_machine(equipment_hi: str = "") -> str:
    """Supply-side acquisition — the only ask on the page.

    The card itself is services/free_month.py's, shared with कृषि दुकान, so the
    offer a tractor owner reads and the offer a shopkeeper reads are the same
    promise for the same number of months — and the same one the admin panel
    actually grants. This wrapper exists only to name the machine the reader is
    already looking at, so the WhatsApp message that arrives says which page it
    came from.

    It stays a WhatsApp link rather than a form on purpose: the people who own
    a tractor worth hiring out are reached in a chat, not through a sign-up
    flow they will abandon halfway.
    """
    return free_month.card("rental", equipment_hi or "")


_CTA_ARTICLE = "📰 इससे जुड़ा पूरा लेख पढ़ें"
_CTA_LABELS = {"/bhav/net-price": "🧮 भाड़ा जोड़कर नेट भाव निकालिए"}


def _how_to_book(item: dict | None = None, has_owners: bool = False) -> str:
    """"अभी किराये पर कहाँ से लूँ" — answered honestly, in whatever state.

    When owners ARE listed this still renders, below them, because the CHC
    route is usually cheaper than a private owner and a directory that hid the
    cheaper option to protect its own listings would not be worth reading. The
    heading changes so it does not read as "nobody has this".
    """
    what = item["name_hi"] if item else "मशीन"
    head = (f"{escape(what)} किराये पर और कहाँ से मिलेगी"
            if has_owners else f"{escape(what)} किराये पर कहाँ से लें")
    lead = ("इनके अलावा दो और रास्ते हैं, और अक्सर सस्ते पड़ते हैं:"
            if has_owners else "")
    lead_html = f'<p class="desc">{lead}</p>' if lead else ""

    return f"""<h2>{head}</h2>
{lead_html}
<div class="rent-book">
<h3>1. गाँव का कस्टम हायरिंग सेंटर (CHC)</h3>
<p>सरकार ने हर ब्लॉक में यंत्रों के किराया केंद्र बनाए हैं, जहाँ मशीनें बाज़ार से
सस्ते किराये पर मिलती हैं। सरकारी <b>FARMS</b> ऐप पर अपने आसपास का CHC ढूँढकर
सीधे बुकिंग की जा सकती है।</p>
<div class="cta-row">
<a class="btn btn-app" target="_blank" rel="noopener nofollow" href="{_CHC_URL}">CHC पोर्टल खोलें</a>
<a class="btn btn-kh" target="_blank" rel="noopener nofollow" href="{_FARMS_URL}">FARMS ऐप</a>
</div>
</div>
<div class="rent-book">
<h3>2. गाँव का मशीन मालिक या किसान समूह</h3>
<p>ज़्यादातर सौदे आज भी गाँव में ही होते हैं — पड़ोसी किसान, सहकारी समिति या FPO के पास।
रेट पूछने से पहले ऊपर दी रेंज देख लीजिए, ताकि आपको पता हो कि सही दाम क्या है।
सीज़न के पीक हफ़्ते से 8–10 दिन पहले बात कर लेना सबसे सस्ता पड़ता है।</p>
</div>
<div class="rent-book">
<h3>3. ज़िला कृषि कार्यालय</h3>
<p>कौन-सी मशीन आपके ब्लॉक में कहाँ उपलब्ध है और उस पर कितनी सब्सिडी चल रही है —
इसकी सही जानकारी यहीं मिलती है। यंत्र खरीदने पर मिलने वाली सब्सिडी का हिसाब भी
एक बार ज़रूर देख लीजिए।</p>
</div>"""


_NEAR_JS = """
<script>
(function(){
  var geo; try { geo = JSON.parse(localStorage.getItem("km_geo")||"null"); } catch(e){ geo = null; }
  var list = document.getElementById("rent-owners");
  if (!list) return;
  function km(a,b,c,d){
    var R=6371,p=Math.PI/180,x=(c-a)*p,y=(d-b)*p;
    var h=Math.sin(x/2)*Math.sin(x/2)+Math.cos(a*p)*Math.cos(c*p)*Math.sin(y/2)*Math.sin(y/2);
    return 2*R*Math.asin(Math.sqrt(h));
  }
  function sort(lat,lon){
    var rows=[].slice.call(list.children), any=false;
    rows.forEach(function(r){
      var la=parseFloat(r.getAttribute("data-lat")), lo=parseFloat(r.getAttribute("data-lon"));
      if(isNaN(la)||isNaN(lo)){ r._km=Infinity; return; }
      r._km=km(lat,lon,la,lo); any=true;
      var tag=r.querySelector("[data-km-tag]");
      if(tag){ tag.textContent=(r._km<1?"1 किमी से कम":Math.round(r._km)+" किमी दूर"); tag.hidden=false; }
    });
    if(!any) return;
    rows.sort(function(a,b){ return (a._km-b._km) || 0; });
    rows.forEach(function(r){ list.appendChild(r); });
    var hint=document.getElementById("rent-geo-hint");
    if(hint) hint.innerHTML="\\u2705 आपके सबसे नज़दीक का मालिक सबसे ऊपर है।";
  }
  if(geo && geo.lat && geo.lon){ sort(geo.lat, geo.lon); return; }
  var btn=document.getElementById("rent-geo-btn");
  if(!btn||!navigator.geolocation) return;
  btn.addEventListener("click", function(){
    btn.textContent="ढूँढ रहे हैं…";
    navigator.geolocation.getCurrentPosition(function(pos){
      var lat=pos.coords.latitude, lon=pos.coords.longitude;
      try{ localStorage.setItem("km_geo", JSON.stringify(
        {status:"ok",lat:lat,lon:lon,location:"",ts:Date.now()})); }catch(e){}
      sort(lat,lon);
    }, function(){ btn.textContent="जगह नहीं मिली"; }, {timeout:8000, maximumAge:600000});
  });
})();
</script>"""


def _offer_range(offers: list) -> str:
    """Real owners' rates as one string, with the unit when they agree on it.

    When two owners quote in different units ("प्रति घंटा" vs "प्रति एकड़")
    the unit is dropped rather than guessed — a range labelled with the wrong
    basis is worse than an unlabelled one.
    """
    if not offers:
        return "—"
    lo = min(o["rate"] for o in offers)
    hi = max(o["rate"] for o in offers)
    money = f"₹{lo}" if lo == hi else f"₹{lo}–₹{hi}"
    units = {o["rate_unit_hi"] for o in offers if o["rate_unit_hi"]}
    return f"{money} {units.pop()}" if len(units) == 1 else money


def _owner_row(equipment_slug: str, offer: dict) -> str:
    """One owner's row on a machine page.

    data-lat/data-lon ride on the element so the client can re-sort by real
    distance the moment km_geo is known. The two flags a hire argument is
    actually about — डीज़ल and चालक — are tags rather than prose, so two
    quotes on the same page are comparable at a glance.
    """
    tags = []
    if offer["verified"]:
        tags.append('<span class="rent-tag tick">✓ जाँचा हुआ</span>')
    if offer["kind_label"]:
        tags.append(f'<span class="rent-tag">{escape(offer["kind_label"])}</span>')
    tags.append('<span class="rent-tag fuel">'
                + ("डीज़ल शामिल" if offer["fuel_included"] else "डीज़ल अलग")
                + '</span>')
    tags.append('<span class="rent-tag">'
                + ("चालक सहित" if offer["with_operator"] else "बिना चालक")
                + '</span>')
    if not offer["available"]:
        tags.append('<span class="rent-tag out">अभी खाली नहीं</span>')
    tags.append('<span class="rent-tag km" data-km-tag hidden></span>')

    where = " · ".join(x for x in (offer["district"], offer["state"]) if x)
    note_html = (f'<div class="rent-owner-note">{escape(offer["note"])}</div>'
                 if offer["note"] else "")
    min_html = (f'<span class="unit">कम से कम ₹{offer["min_charge"]}</span>'
                if offer["min_charge"] else "")
    coords = ""
    if offer["lat"] is not None and offer["lon"] is not None:
        coords = f' data-lat="{offer["lat"]}" data-lon="{offer["lon"]}"'

    return f"""<a class="rent-owner" href="{BASE}/{equipment_slug}/{offer['provider_slug']}"{coords}>
<div class="rent-owner-main">
<div class="rent-owner-name">{escape(offer['provider_name'])}</div>
<span class="rent-owner-where">📍 {escape(where)}</span>
<div class="rent-owner-meta">{''.join(tags)}</div>
{note_html}
</div>
<div class="rent-owner-rate"><b>₹{offer['rate']}</b>
<span class="unit">{escape(offer['rate_unit_hi'])}</span>{min_html}</div>
</a>"""


def _owners_block(item: dict, offers: list) -> str:
    """The owner list, or nothing at all when none is listed.

    Renders NOTHING rather than an empty-state box when there are no owners:
    _how_to_book already answers "कहाँ से लें" with the government CHC route,
    and a second panel saying "nobody here" would only make the page look
    broken on the 24 machines that have no supply yet.
    """
    if not offers:
        return ""
    rows = "".join(_owner_row(item["slug"], o) for o in offers)
    geo_hint = ('<p class="rent-geo-hint" id="rent-geo-hint">'
                'दूरी के हिसाब से लगाने के लिए अपनी जगह बताएं '
                '<button class="rent-geo-btn" id="rent-geo-btn" type="button">'
                '📍 मेरे पास वाले</button></p>')
    return (f'<h2>{escape(item["name_hi"])} किराये पर देने वाले ({len(offers)})</h2>'
            f'{geo_hint}'
            f'<div class="rent-owners" id="rent-owners">{rows}</div>')


# The Agmarknet line _footer() defaults to is FALSE here — nothing on these
# pages comes from the mandi feed, and sending a farmer to "confirm in your
# mandi" for a tractor rate would be nonsense. Same reason /ganna overrides it.
_FOOT = ("किराये की दरें अनुमानित हैं — मशीन मालिक, इलाके और सीज़न से बदलती हैं।\n"
         "सौदा तय करने से पहले रेट और शर्तें ज़रूर पुष्टि कर लें।")


def _not_found(message: str, sub: str) -> HTMLResponse:
    """An equipment can be dropped from the registry while Google still holds
    the URL — send that farmer into the directory instead of a dead end."""
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="hi">
<head>
{_ANALYTICS}
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(message)} | कृषि मित्र</title>
<meta name="robots" content="noindex">
{_ICON}
{_FONTS}
<style>{_CSS}</style>
</head>
<body>
{_header("")}
<div class="wrap">
<div class="hero nophoto">
<div class="hero-body">
<h1>{escape(message)}</h1>
<p class="hero-sub">{escape(sub)}</p>
</div>
</div>
<div class="cta-row">
<a class="btn btn-app" href="{BASE}">किराये की मशीनें देखें</a>
</div>
</div>
{_footer(_FOOT)}
</body>
</html>""", status_code=404)


# ── /rental/sitemap.xml ─────────────────────────────────────
# Declared before /rental/{slug}: FastAPI matches in registration order, so
# "sitemap.xml" would otherwise be read as an equipment slug.

@router.get("/rental/sitemap.xml")
def rental_sitemap():
    """The hub and every equipment page — 25 URLs, all of them content-rich.

    The per-owner pages are deliberately absent, and noindex on top of that:
    24 machines × every owner is a set of URLs differing by a name and a
    number, which is the near-duplicate pattern that already has 72% of this
    site's impressions stuck at positions 4-10. The farmer reaches them by
    tapping; Google does not need them. Same call krashi_dukan makes about its
    per-shop offer pages.

    Not expanded by district or state either, for the same reason.
    """
    day = rental.updated()
    lastmod = f"<lastmod>{day}</lastmod>" if day else ""
    urls = [f"  <url><loc>{BASE}</loc>{lastmod}<changefreq>monthly</changefreq></url>"]
    urls += [f"  <url><loc>{BASE}/{e['slug']}</loc>{lastmod}"
             f"<changefreq>monthly</changefreq></url>" for e in rental.equipment()]
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
           + "\n".join(urls) + "\n</urlset>")
    return Response(content=xml, media_type="application/xml",
                    headers={"Cache-Control": "public, max-age=3600"})


# ── /rental — the hub ───────────────────────────────────────

@router.get("/rental", response_class=HTMLResponse)
@router.get("/rental/", response_class=HTMLResponse)
def rental_hub(db: Session = Depends(get_db)):
    groups = rental.by_category()
    total = len(rental.equipment())
    # {slug: {"providers": n, ...}} for machines a live owner actually hires
    # out. Unlike /krashi_dukan this does NOT filter the grid — see
    # rental.listed_equipment on why a machine with no owner still earns a page.
    listed = rental.listed_equipment(db)
    owners = sum(b["providers"] for b in listed.values())

    jump_chips, sections = [], []
    for cat, rows in groups:
        jump_chips.append(f'<a class="hub-filter-btn" href="#cat-{escape(cat["key"], quote=True)}">'
                          f'{escape(cat["label_hi"])}</a>')
        cards = "".join(_card(e, listed.get(e["slug"])) for e in rows)
        intro = (f'<p class="desc">{escape(cat.get("intro_hi") or "")}</p>'
                 if cat.get("intro_hi") else "")
        sections.append(
            f'<h2 id="cat-{escape(cat["key"], quote=True)}">{escape(cat["label_hi"])} ({len(rows)})</h2>'
            f'{intro}<div class="prod-grid">{cards}</div>')

    if not groups:
        # An empty registry must say so plainly rather than render a hub with no
        # cards, and must not be indexed while it has nothing in it.
        sections.append('<h2>अभी सूची तैयार हो रही है</h2>'
                        '<p class="desc">किराये की मशीनों की जानकारी जल्द ही यहाँ मिलेगी।</p>')

    faqs = [
        ("खेती की मशीन किराये पर लेना सस्ता पड़ता है या खरीदना?",
         "जिस मशीन का साल में 25–30 दिन से कम इस्तेमाल हो, उसे किराये पर लेना ही सस्ता है — "
         "ट्रैक्टर, कंबाइन हार्वेस्टर, लेज़र लेवलर और बेलर इसी श्रेणी में आते हैं। "
         "जो मशीन लगभग रोज़ चलती है, जैसे चारा काटने की मशीन, उसे खरीदना बेहतर है क्योंकि "
         "4–6 महीने का किराया अक्सर नई मशीन के दाम के बराबर बैठ जाता है।"),
        ("किराया प्रति घंटा लेना चाहिए या प्रति एकड़?",
         "जुताई, बुवाई और कटाई जैसे कामों में प्रति एकड़ सौदा किसान के हक़ में रहता है, "
         "क्योंकि तब मशीन धीरे चलाने या बार-बार रुकने का घाटा आपका नहीं होता। "
         "पंप और JCB जैसे कामों में, जहाँ काम की मात्रा पहले से तय नहीं होती, घंटे का हिसाब ही चलता है — "
         "वहाँ पहले अनुमान लिखवा लीजिए।"),
        ("क्या कृषि मित्र से मशीन बुक हो सकती है?",
         "नहीं। कृषि मित्र सिर्फ़ बताता है कि किस मशीन का किराया आमतौर पर कितना होता है और "
         "उसे लेने से पहले क्या जाँचना चाहिए। बुकिंग सीधे मशीन मालिक, गाँव के कस्टम हायरिंग सेंटर (CHC) "
         "या सरकारी FARMS ऐप से होती है।"),
        ("सरकारी कस्टम हायरिंग सेंटर (CHC) क्या है?",
         "CHC यंत्रों का किराया केंद्र है, जहाँ से किसान घंटे या एकड़ के हिसाब से मशीन किराए पर लेते हैं। "
         "इसे किसान, स्वयं सहायता समूह, FPO, सहकारी समिति या ग्राम पंचायत चला सकते हैं और "
         "परियोजना लागत पर सरकारी सहायता मिलती है। यहाँ किराया आमतौर पर बाज़ार से कम रहता है। "
         "सरकार का FARMS ऐप आसपास के CHC से सीधी बुकिंग की सुविधा देता है।"),
        ("यहाँ दिए किराये तय रेट हैं क्या?",
         "नहीं, ये अनुमानित रेंज हैं। असली किराया इलाके, सीज़न, डीज़ल के दाम और मशीन की हालत से "
         "बदलता है — पीक हफ़्ते में यह 30–40% तक चढ़ जाता है। इस रेंज का मक़सद यह है कि "
         "रेट पूछते समय आपको पता हो कि माँगा जा रहा दाम सही है या ज़्यादा।"),
    ]
    faq_html, faq_ld = _faq(faqs)

    title = _fit("किराये की कृषि मशीनें — ट्रैक्टर, पंप, हार्वेस्टर का रेट",
                 "किराये की कृषि मशीनें — रेट व बुकिंग",
                 "किराये की कृषि मशीनें — रेट")
    desc = (f"ट्रैक्टर, रोटावेटर, पंप सेट, हार्वेस्टर समेत {total} खेती की मशीनों का किराया — "
            f"प्रति घंटा व प्रति एकड़ रेट, क्या जाँचें और CHC से बुकिंग कैसे करें।")[:162]

    body = f"""<div class="hero nophoto">
<div class="hero-body">
<h1>किराये की कृषि मशीनें</h1>
<p class="hero-sub">🚜 {total} मशीनें{f" · {owners} मालिक जुड़े" if owners else ""} · प्रति घंटा व प्रति एकड़ किराया · सौदा करने से पहले सही रेट जानिए</p>
</div>
</div>
<p class="desc">खेती की जो मशीन आप साल में कुछ ही दिन चलाते हैं, उसे खरीदने के बजाय किराये पर
लेना लगभग हमेशा सस्ता पड़ता है। नीचे हर मशीन का आम किराया, उसे लेते समय क्या जाँचना है और
उसे कहाँ से बुक करना है — तीनों दिए हैं।</p>
<div class="hub-filter-row">
{"".join(jump_chips)}
</div>
{"".join(sections)}
{_own_machine()}
{dukan_link()}
{_how_to_book()}
<div class="rent-note"><b>ध्यान दें:</b> {escape(DISCLAIMER)}</div>
<h2>अक्सर पूछे जाने वाले सवाल</h2>
{faq_html}"""

    return _doc(title, desc, BASE,
                f'<a href="{SITE}/">कृषि मित्र</a> › किराये की मशीनें', body,
                _ld(_crumb_ld([("कृषि मित्र", f"{SITE}/"),
                               ("किराये की मशीनें", BASE)]), faq_ld),
                active="", extra_css=_EXTRA_CSS,
                robots="" if groups else "noindex,follow",
                updated=rental.updated(), footer_note=_FOOT)


# ── /rental/{equipment} — one machine ───────────────────────

@router.get("/rental/{equipment_slug}", response_class=HTMLResponse)
def rental_equipment(equipment_slug: str, db: Session = Depends(get_db)):
    item = rental.by_slug(equipment_slug)
    if not item:
        return _not_found("यह मशीन अभी सूची में नहीं है",
                          "हो सकता है लिंक पुराना हो। नीचे से पूरी सूची देखें।")

    offers = rental.offers_for_equipment(db, item["slug"])
    cat = rental.category_of(item)
    canon = f"{BASE}/{item['slug']}"
    name = item["name_hi"]
    rate, unit = _headline(item)
    lo, hi = rental.span(item)

    rate_rows = "".join(
        f'<div class="rent-rate"><div class="rent-rate-unit">{escape(r["unit_hi"])}</div>'
        f'<div class="rent-rate-val">{rental.rate_text(r)}</div></div>'
        for r in rental.rates(item))
    basis = rental.rate_basis()
    basis_html = f'<p class="rent-basis">{escape(basis)}</p>' if basis else ""

    check_html = ""
    if item.get("check_hi"):
        items = "".join(f"<li>{escape(c)}</li>" for c in item["check_hi"])
        check_html = (f'<h2>{escape(name)} किराये पर लेते समय क्या जाँचें</h2>'
                      f'<ul class="rent-list">{items}</ul>')

    tips_html = ""
    if item.get("tips_hi"):
        items = "".join(f"<li>{escape(t)}</li>" for t in item["tips_hi"])
        tips_html = (f'<h2>काम की बात</h2>'
                     f'<ul class="rent-list tips">{items}</ul>')

    # A machine's `article` is usually a guide, but the haulage rows point at
    # the net-भाव calculator instead, and a button promising a लेख that opens a
    # calculator is a small lie the farmer catches on the tap. Keyed by target
    # so the registry stays free of a label column nobody would keep in sync;
    # test_netprice_hauliers.py fails if a non-article target has no label.
    article = item.get("article") or ""
    article_html = ""
    if article:
        article_html = (f'<div class="cta-row">'
                        f'<a class="btn btn-kh" href="{SITE}{escape(article)}">'
                        f'{escape(_CTA_LABELS.get(article, _CTA_ARTICLE))}</a></div>')

    others = rental.siblings(item)
    others_html = ""
    if others:
        cards = "".join(_card(e) for e in others)
        others_html = (f'<h2>दूसरी मशीनों का किराया</h2>'
                       f'<div class="prod-grid">{cards}</div>')

    faqs = [
        # A page with real quotes on it must answer with those, not with the
        # estimate above them — otherwise the FAQ and the owner list disagree
        # about the price on the same screen.
        (f"{name} का किराया कितना है?",
         (f"कृषि मित्र पर जुड़े {len(offers)} मालिकों के पास {name} का किराया "
          f"{_offer_range(offers)} है। हर मालिक का अपना रेट है — ऊपर की सूची में "
          f"अपने नज़दीक का दाम देखें।"
          if offers else
          f"{name} का किराया आमतौर पर {rate} {unit} रहता है। "
          + (f"अलग-अलग हिसाब से यह ₹{lo} से ₹{hi} के बीच पड़ता है। " if lo != hi else "")
          + "यह अनुमानित रेंज है — इलाके, सीज़न, डीज़ल के दाम और मशीन की हालत से रेट बदलता है।")),
        (f"{name} किराये पर लेने से पहले क्या देखना चाहिए?",
         ((item.get("check_hi") or [""])[0] + "। " if item.get("check_hi") else "")
         + "इसके अलावा मशीन की हालत खुद देख लें और रेट में क्या-क्या शामिल है — "
           "डीज़ल, चालक, ढुलाई — यह पहले ही साफ़ कर लें।"),
        (f"{name} किराये में डीज़ल और चालक शामिल हैं क्या?",
         f"आमतौर पर {item.get('operator_hi') or 'चालक की व्यवस्था मालिक की'} होती है और "
         f"{item.get('fuel_hi') or 'ईंधन किसान का'} लगता है। यह हर मालिक के साथ बदलता है, "
         f"इसलिए सौदा तय करते समय यही सबसे पहले पूछिए — किराये को लेकर सबसे ज़्यादा झगड़े इसी बात पर होते हैं।"),
        (f"{name} कब किराये पर मिलनी सबसे मुश्किल होती है?",
         f"{item.get('season_hi') or 'सीज़न के पीक हफ़्ते'} में माँग सबसे ज़्यादा रहती है और तभी रेट भी चढ़ता है। "
         f"उस दौर से 8–10 दिन पहले बुकिंग कर लेने पर मशीन भी मिलती है और किराया भी कम लगता है।"),
    ]
    faq_html, faq_ld = _faq(faqs)

    units = _units_phrase(item)
    title = _fit(f"{name} किराया — {units} का रेट" if units else f"{name} किराया — रेट",
                 f"{name} किराया — {_unit_short(unit)} का रेट" if unit else f"{name} किराया",
                 f"{name} किराया — रेट व बुकिंग",
                 f"{name} किराया")
    desc = (f"{name} का किराया {rate} {unit}। रेट में डीज़ल-चालक शामिल है या नहीं, "
            f"लेने से पहले क्या जाँचें और CHC से बुकिंग कैसे करें — पूरी जानकारी।")[:162]

    # "rng" only when the rate actually is a range — a single number keeps the
    # full-size hero figure /bhav and /product use.
    unit_small = f"<small>{escape(unit)}</small>" if unit else ""
    price_line = (f'<div class="answer-rupee{" rng" if "–" in rate else ""}">'
                  f'{rate} {unit_small}</div>')

    body = f"""<section class="answer">
<div class="answer-prod-split">
{_tile(item, "answer-prod-photo-lg", 72, eager=True)}
<div class="answer-prod-info">
<h1>{escape(item.get('emoji') or '🚜')} {escape(name)} किराया</h1>
<p class="answer-sub">{escape(cat.get('label_hi') or '')}{f" · {escape(item['name_en'])}" if item.get('name_en') else ""}</p>
<div class="answer-price">{price_line}</div>
<div class="answer-range">
<div><span>मशीन</span><b>{escape(item.get('spec_hi') or '—')}</b></div>
<div><span>चालक</span><b>{escape(item.get('operator_hi') or '—')}</b></div>
<div><span>ईंधन</span><b>{escape(item.get('fuel_hi') or '—')}</b></div>
</div>
</div>
</div>
</section>
<p class="lead-out">{escape(item.get('summary_hi') or '')}</p>
<h2>{escape(name)} का किराया — किस हिसाब से कितना</h2>
<div class="rent-rates">{rate_rows}</div>
{basis_html}
<div class="rent-note"><b>ध्यान दें:</b> {escape(DISCLAIMER_LISTED if offers else DISCLAIMER)}</div>
{check_html}
{tips_html}
{article_html}
{_owners_block(item, offers)}
{_how_to_book(item, has_owners=bool(offers))}
{_own_machine(name)}
<h2>अक्सर पूछे जाने वाले सवाल</h2>
{faq_html}
{others_html}
{_NEAR_JS if offers else ""}"""

    crumbs = (f'<a href="{SITE}/">कृषि मित्र</a> › <a href="{BASE}">किराये की मशीनें</a> › '
              f'{escape(cat.get("label_hi") or "")} › {escape(name)}')
    blocks = [_crumb_ld([("कृषि मित्र", f"{SITE}/"),
                         ("किराये की मशीनें", BASE), (name, canon)]), faq_ld]
    if offers:
        # NOW an offer is a real thing: named owners who will honour a rate.
        # AggregateOffer, not Offer, because the seller is never us — the same
        # rule krashi_dukan follows. While `offers` is empty this block is
        # absent entirely, because the editorial ranges above it are estimates
        # and marking an estimate as an offer is a false claim in schema.
        blocks.append({
            "@context": "https://schema.org", "@type": "Service",
            "serviceType": f"{item.get('name_en') or name} rental",
            "name": f"{name} किराये पर",
            "description": (item.get("summary_hi") or name)[:300],
            "areaServed": sorted({o["district"] for o in offers if o["district"]}),
            "offers": {
                "@type": "AggregateOffer", "priceCurrency": "INR",
                "lowPrice": str(min(o["rate"] for o in offers)),
                "highPrice": str(max(o["rate"] for o in offers)),
                "offerCount": str(len(offers)), "url": canon,
            },
        })
    return _doc(title, desc, canon, crumbs, body, _ld(*blocks),
                active="", extra_css=_EXTRA_CSS,
                updated=rental.updated(), footer_note=_FOOT)


# ── /rental/{equipment}/{owner} — one owner's rate ──────────

@router.get("/rental/{equipment_slug}/{provider_slug}", response_class=HTMLResponse)
def rental_offer(equipment_slug: str, provider_slug: str,
                 db: Session = Depends(get_db)):
    """NOINDEX, FOLLOW — on purpose, in every state.

    This page is the farmer's destination after he taps an owner: rate, terms,
    phone, directions. It is not a search landing page. Every
    (machine × owner) pair would otherwise be a URL differing from its siblings
    by a name and a number, which is the near-duplicate pattern that already
    has 72% of this site's impressions stuck at positions 4-10. `follow` keeps
    the links out of here alive.
    """
    item = rental.by_slug(equipment_slug)
    provider = rental.provider_get(db, provider_slug)
    if not item or not provider or not rental.is_live(provider):
        return _not_found("यह मालिक अभी उपलब्ध नहीं है",
                          "हो सकता है लिस्टिंग हटा दी गई हो या लिंक पुराना हो।")

    offer = next((o for o in rental.offers_for_equipment(db, item["slug"])
                  if o["provider_slug"] == provider.slug), None)
    if not offer:
        return _not_found("यह मशीन इस मालिक के पास नहीं है",
                          "दूसरे मालिकों के रेट देखें।")

    name = item["name_hi"]
    canon = f"{BASE}/{item['slug']}/{provider.slug}"
    where = " · ".join(x for x in (offer["district"], offer["state"]) if x)

    ctas = []
    if offer["phone"]:
        ctas.append(f'<a class="btn btn-app" href="tel:{escape(offer["phone"])}">'
                    f'📞 मालिक को फ़ोन करें</a>')
    if offer["whatsapp"]:
        wa = quote(f"नमस्ते, कृषि मित्र पर आपकी लिस्टिंग देखी — "
                   f"{name} ₹{offer['rate']} {offer['rate_unit_hi']} में मिलेगी क्या?")
        ctas.append(f'<a class="btn btn-wa" target="_blank" rel="noopener" '
                    f'href="https://wa.me/{escape(offer["whatsapp"])}?text={wa}">'
                    f'💬 व्हाट्सऐप करें</a>')
    if offer["address"]:
        maps_q = quote(f"{provider.name} {offer['address']} {where}")
        ctas.append(f'<a class="btn btn-wa" style="background:var(--green-dark)" '
                    f'target="_blank" rel="noopener nofollow" '
                    f'href="https://www.google.com/maps/search/?api=1&query={maps_q}">'
                    f'🗺️ रास्ता देखें</a>')
    ctas.append(f'<a class="btn btn-app" style="background:var(--green-mid)" '
                f'href="{BASE}/{item["slug"]}">↔ दूसरे मालिकों से रेट मिलाएं</a>')

    kv = [("मालिक", escape(provider.name))]
    if offer["kind_label"]:
        kv.append(("किस तरह", escape(offer["kind_label"])))
    if where:
        kv.append(("जगह", escape(where)))
    if offer["address"]:
        kv.append(("पता", escape(offer["address"])))
    if offer["phone"]:
        kv.append(("फ़ोन", escape(offer["phone"])))
    # The two terms every hire argument is actually about, stated as facts
    # rather than left for the farmer to discover at the field gate.
    kv.append(("डीज़ल", "किराये में शामिल" if offer["fuel_included"] else "किसान का अपना"))
    kv.append(("चालक", "साथ आएगा" if offer["with_operator"] else "नहीं — खुद चलाना है"))
    if offer["min_charge"]:
        kv.append(("कम से कम", f"₹{offer['min_charge']}"))
    if offer["since"]:
        kv.append(("कब से", escape(offer["since"])))
    kv_html = "".join(f"<div><span>{k}</span><b>{v}</b></div>" for k, v in kv)

    note_html = f'<p class="desc">{escape(offer["note"])}</p>' if offer["note"] else ""
    avail = "हाँ" if offer["available"] else "अभी नहीं"

    title = _fit(f"{name} किराया — {provider.name}, {offer['district']} में ₹{offer['rate']}",
                 f"{name} किराया — {provider.name} ₹{offer['rate']}",
                 f"{name} किराया — ₹{offer['rate']}")
    desc = (f"{provider.name} ({where}) के पास {name} ₹{offer['rate']} "
            f"{offer['rate_unit_hi']}। डीज़ल-चालक की शर्तें, फ़ोन नंबर और रास्ता देखें।")[:162]

    body = f"""<section class="answer">
<div class="answer-prod-split">
{_tile(item, "answer-prod-photo-lg", 72, eager=True)}
<div class="answer-prod-info">
<h1>{escape(item.get('emoji') or '🚜')} {escape(name)} किराया</h1>
<p class="answer-sub">🚜 {escape(provider.name)}{f" · {escape(where)}" if where else ""}</p>
<div class="answer-price">
<div class="answer-rupee">₹{offer['rate']} <small>{escape(offer['rate_unit_hi'])}</small></div>
</div>
<div class="answer-range">
<div><span>डीज़ल</span><b>{"शामिल" if offer["fuel_included"] else "अलग"}</b></div>
<div><span>चालक</span><b>{"सहित" if offer["with_operator"] else "नहीं"}</b></div>
<div><span>अभी खाली</span><b>{avail}</b></div>
</div>
</div>
</div>
</section>
{note_html}
<div class="cta-row">{"".join(ctas)}</div>
<div class="rent-card">
<h3>मालिक की जानकारी</h3>
<div class="rent-kv">{kv_html}</div>
</div>
<div class="rent-note"><b>ध्यान दें:</b> {escape(DISCLAIMER_LISTED)}</div>
{_how_to_book(item, has_owners=True)}"""

    crumbs = (f'<a href="{SITE}/">कृषि मित्र</a> › <a href="{BASE}">किराये की मशीनें</a> › '
              f'<a href="{BASE}/{item["slug"]}">{escape(name)}</a> › {escape(provider.name)}')
    return _doc(title, desc, canon, crumbs, body,
                _ld(_crumb_ld([("कृषि मित्र", f"{SITE}/"),
                               ("किराये की मशीनें", BASE),
                               (name, f"{BASE}/{item['slug']}"),
                               (provider.name, canon)])),
                active="", extra_css=_EXTRA_CSS,
                robots="noindex,follow",
                updated=rental.updated(), footer_note=_FOOT)
