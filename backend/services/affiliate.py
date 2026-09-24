# ============================================================
# services/affiliate.py
# Which catalogue product to put in front of a farmer, and the one URL every
# affiliate click leaves through.
#
# THE PROBLEM THIS SOLVES. The Amazon/Flipkart links have been on
# /product/<slug> since the catalogue pages shipped — 94 pages, every one
# carrying a tagged link. Two things were wrong, and neither was the link:
#
#   1. **Nobody measured them.** The hrefs went straight out to amzn.to, so a
#      click left no trace on our side. `lead_clicks` knew about the किसान-सेवा
#      card and the खरीदार WhatsApp hops and nothing at all about the one
#      program that can actually pay. "Which of the 94 earns?" had no answer.
#   2. **They sat on the quietest pages we own.** /product is a catalogue
#      nobody searches for by name; /bhav is where the traffic is. The program
#      was parked on the wrong pages.
#
# So this module does two jobs: build the tracked URL (routes/product.py owns
# the redirect that consumes it), and answer "given this page, which products
# belong on it".
#
# HOW THE MATCH IS MADE, AND WHY IT IS NOT A HAND-MAINTAINED TABLE. 354 crop
# slugs against 94 products: a crop→product map would be 354 rows for somebody
# to re-edit every time the catalogue changes, which is the manual seam this
# project refuses to ship. Instead, two sources, in order:
#
#   * **crop-specific** — token overlap between the crop slug and the product
#     slug (wheat → wheat-seeds-hd-2967). Only about a dozen crops have a
#     product of their own, so this is the garnish and never the meal. Capped
#     at CROP_MAX so one lucky match cannot fill the whole block.
#   * **sell-stage** — the rest comes from what the farmer is doing while he
#     reads a mandi page: he is about to SELL. That makes a grain moisture
#     meter (the reading a buyer docks the rate on), storage bags and a
#     tarpaulin the genuinely right shelf — not a random fertilizer. Which
#     shelf depends on services/crop_types.py, which already knows whether a
#     crop is perishable, storable or a staple.
#
# Selection is DETERMINISTIC for a given crop. These pages are cached HTML, so
# two farmers on the same page have to see the same block — and a shuffle would
# also make "which product earns" unreadable in lead_clicks.
# ============================================================
from backend.services import crop_types

# Amazon is the account that exists and has earned; Flipkart rides along where
# it already did. Order matters — a block links through the first network a
# product actually carries a live link for.
NETWORKS = ("amazon", "flipkart")
_FIELD = {"amazon": "affil_amazon", "flipkart": "affil_flipkart"}

CROP_MAX = 2      # at most this many crop-specific picks in one block
BLOCK_MAX = 4     # cards per block — four fills one phone-width shelf

# The material-connection disclosure. rel="sponsored" tells Google; this tells
# the farmer, which is the half the CCPA's endorsement guidelines actually ask
# for. It lives here rather than in one of the two route modules that print it
# so /product and /bhav can never drift into saying different things about the
# same commercial relationship — and so a page that carries an affiliate link
# without this string is a test failure, not a judgement call.
# The English sentence is Amazon's own required wording — the Associates
# Operating Agreement asks for it verbatim, and a Hindi paraphrase alone does not
# satisfy it (the account can be closed and unpaid commission withheld).
AFFILIATE_NOTE = ("Amazon और Flipkart के लिंक एफ़िलिएट लिंक हैं — "
                  "उनसे खरीदने पर कृषि मित्र को कमीशन मिल सकता है। "
                  "आपको कोई अतिरिक्त शुल्क नहीं लगता। "
                  "As an Amazon Associate, KrashiMitra earns from qualifying purchases.")


def _catalogue() -> list[dict]:
    """Every catalogue product that carries at least one live affiliate link.

    Imported inside the call rather than at module scope: routes/product.py
    imports routes/bhav.py for the page shell, and bhav imports this module —
    a top-level import here would close that circle at startup. By the time a
    request runs, both route modules are loaded and this is a dict lookup.
    """
    from backend.routes.product import _available, _get_products
    return [p for p in _get_products()
            if any(_available(p.get(f, "")) for f in _FIELD.values())]


def _by_slug() -> dict:
    return {p["slug"]: p for p in _catalogue()}


# ── the outbound hop ────────────────────────────────────────

def network_for(p: dict) -> str:
    """The network this product should be linked through — the first one it has
    a live link for. Returns "" when it has none, which is how a caller tells a
    linkable product from an unlinkable one."""
    from backend.routes.product import _available
    for net in NETWORKS:
        if _available(p.get(_FIELD[net], "")):
            return net
    return ""


def raw_url(p: dict, net: str) -> str:
    """The affiliate URL itself. Only the redirect handler should call this —
    everything that renders HTML uses go_url(), so every click is counted and
    so a network's URLs stay swappable in one place."""
    from backend.routes.product import _available
    url = p.get(_FIELD.get(net, ""), "")
    return url if _available(url) else ""


def go_url(slug: str, net: str) -> str:
    """The tracked hop. Mirrors /go/<offer_id> for the किसान-सेवा card, one
    level deeper so the two can never collide on a slug that happens to look
    like an offer id."""
    return f"/go/p/{net}/{slug}"


# ── matching ────────────────────────────────────────────────

# Words that appear in crop slugs and product slugs alike and mean nothing on
# their own. Without these, `mentha-oil` matches every oil in the catalogue and
# `black-gram-dal` matches on "dal"; the block then looks automated, which is
# the one thing it cannot afford to look like next to a price a farmer trusts.
_STOP = {
    "whole", "dal", "seed", "seeds", "oil", "green", "red", "black", "white",
    "common", "local", "other", "fine", "medium", "large", "small", "hybrid",
    "kit", "mix", "powder", "fresh", "dry", "dried", "leaves", "pod", "beans",
    "gram", "cake", "feed", "set", "pack", "combo", "organic", "bio", "the",
}

# Spelling gaps between what data.gov calls a crop and what the catalogue calls
# a product. Deliberately tiny: these are the only ones that cost a real match.
_ALIAS = {
    "soyabean": "soybean",
    "rice": "paddy",
    "dhan": "paddy",
    "basmati": "paddy",
    "corn": "maize",
    "makka": "maize",
    "sarson": "mustard",
    "gehun": "wheat",
    "aloo": "potato",
    "pyaz": "onion",
    "ganna": "sugarcane",
    "chillies": "chilli",
    "mirch": "chilli",
}


def _tokens(slug: str) -> set:
    """Meaningful words in a slug, aliases applied. Digits go too — 'HD-2967'
    and '17-8' are model numbers, and matching on them is coincidence."""
    out = set()
    for t in (slug or "").lower().replace("_", "-").split("-"):
        t = _ALIAS.get(t, t)
        if t and not t.isdigit() and t not in _STOP and len(t) > 2:
            out.add(t)
    return out


def _crop_picks(crop_slug: str, limit: int = CROP_MAX) -> list[dict]:
    """Products whose own name is about this crop, best match first.

    Scored by how many meaningful words the two slugs share, so `bitter-gourd`
    outranks `bottle-gourd` on brinjal-bitter-gourd-seeds rather than both
    landing arbitrarily. Ties break on slug, so the order is stable across
    requests and a cached page never disagrees with a fresh one.
    """
    want = _tokens(crop_slug)
    if not want:
        return []
    scored = []
    for p in _catalogue():
        # Animal feed is named after the crop it is pressed from — "खली
        # (सरसों/मूंगफली)" matches `mustard` and then outranks mustard seed on
        # a mustard price page. It is a real product, but it is never "this
        # crop's product" in the sense this block promises, so it is not
        # eligible for a crop-specific slot at all.
        if p.get("cat") == "pashu_aahaar":
            continue
        hits = len(want & _tokens(p["slug"]))
        if hits:
            # Seed is the strongest crop match there is — it IS the crop — so
            # it breaks a tie ahead of a tool that merely mentions it.
            scored.append((-hits, 0 if p.get("cat") == "seeds" else 1, p["slug"], p))
    scored.sort(key=lambda r: (r[0], r[1], r[2]))
    return [p for *_, p in scored[:limit]]


# What a farmer standing on a mandi page is about to do, by crop type. Every
# entry is gear for SELLING, not for growing — that is the whole reason this
# shelf belongs under a price rather than under an agronomy article.
#
#   staple      sold once a season, usually against MSP. The moisture reading
#               is what a buyer docks the rate on, so it leads.
#   storable    the real question is sell-now-or-hold, so it leads with what
#               holding actually costs: bags and a cover.
#   perishable  no holding option; what is left is protecting the load between
#               the field and the mandi.
_SELL_STAGE = {
    "staple": ("digital-grain-moisture-meter",
               "grain-fodder-storage-bags-hdpe-woven",
               "silpaulin-tarpaulin",
               "mini-grain-thresher"),
    # No moisture meter here: it reads grain, and "storable" is mostly potato,
    # onion and orchard fruit. What a storable crop actually loses money to
    # while it waits is damp, sun and rodents.
    "storable": ("grain-fodder-storage-bags-hdpe-woven",
                 "silpaulin-tarpaulin",
                 "shade-net-50-75-shade",
                 "rodent-bait-station-box"),
    "perishable": ("silpaulin-tarpaulin",
                   "shade-net-50-75-shade",
                   "grow-bags-hdpe-fabric-poly",
                   "anti-bird-net"),
}

# Last resort, if a slug named above is ever renamed out of the catalogue: the
# block degrades to something honest rather than to an empty section.
_FALLBACK = ("knapsack-sprayer-16l", "soil-testing-kit",
             "neem-oil-bio-pesticide", "urea-fertilizer-46-n")


def for_crop(crop_slug: str, limit: int = BLOCK_MAX) -> list[dict]:
    """The products to show beside this crop's price, in render order.

    Crop-specific first (a farmer recognises his own crop on a card), then the
    sell-stage shelf for that crop's type, then the fallback — de-duped and
    trimmed to `limit`. Never raises, and never returns a product without a
    live link, so a caller can render the result unconditionally.
    """
    picked, seen = [], set()

    def take(items):
        for p in items:
            if p and p["slug"] not in seen and len(picked) < limit:
                seen.add(p["slug"])
                picked.append(p)

    by_slug = _by_slug()
    take(_crop_picks(crop_slug))
    stage = _SELL_STAGE.get(crop_types.crop_type(crop_slug), _SELL_STAGE["staple"])
    take(by_slug.get(s) for s in stage)
    take(by_slug.get(s) for s in _FALLBACK)
    return picked


def by_slug(slug: str) -> dict | None:
    """One product, or None — used by the redirect to label the click."""
    return _by_slug().get(slug)
