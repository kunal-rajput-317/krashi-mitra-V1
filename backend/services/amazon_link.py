# ============================================================
# services/amazon_link.py
# Paste an Amazon link → a pre-filled Shop Panel form.
#
# WHAT THIS READS: the link text the owner pasted, and nothing else. It never
# opens amazon.in. Fetching the product page to lift its title, photo or price
# is scraping (LEGAL_RULES §1, and Amazon's Conditions of Use ban "robots or
# similar data gathering and extraction tools"), and the photos are Amazon's
# copyright. The only lawful way to get those is Amazon's own product API,
# which opens after qualifying sales — an owner decision under §8, not this.
#
# What the link itself carries is enough to save most of the typing:
#   * the ASIN — so the link can be rewritten as a clean /dp/<ASIN> link with
#     our tag, and checked against the catalogue for a duplicate;
#   * the product name — amazon.in/Kisan-Kraft-Sprayer-16L/dp/B0… puts it in
#     the path, which becomes the English name and therefore the slug.
#
# No price is derived, ever. The panel's price is the local shop's अनुमानित
# rate, decoupled from Amazon by design (see db.py ShopProduct).
# ============================================================
import re
from urllib.parse import parse_qs, unquote, urlparse

from backend.services.shop_catalog import slugify

TAG = "krashimitra-21"

# Only the Indian store: the tag above is an amazon.in Associates tag, and a
# farmer here cannot buy from amazon.com.
_HOSTS = {"amazon.in", "www.amazon.in", "m.amazon.in"}
_SHORT_HOSTS = {"amzn.to", "amzn.in", "a.co"}

# Every URL shape amazon.in uses for one product page.
_ASIN_RE = re.compile(
    r"/(?:dp|gp/product|gp/aw/d|exec/obidos/asin|o/asin)/([A-Z0-9]{10})(?=[/?#]|$)",
    re.I)

# Path words that are Amazon's plumbing, not part of the product name.
_JUNK = {"dp", "gp", "product", "aw", "d", "ref", "s"}


def asin_of(url: str) -> str:
    """The ASIN inside an amazon.in product link, or "" — used both for the
    pasted link and for every link already in the catalogue."""
    m = _ASIN_RE.search(urlparse((url or "").strip()).path or "")
    return m.group(1).upper() if m else ""


def clean_url(asin: str) -> str:
    return f"https://www.amazon.in/dp/{asin}?tag={TAG}"


def _name_from_path(path: str) -> str:
    """'/Kisan-Kraft-KK-KPS-16-Sprayer/dp/B0…' → 'Kisan Kraft KK KPS 16 Sprayer'."""
    head = _ASIN_RE.split(path)[0]
    seg = next((s for s in reversed(head.split("/")) if s and s.lower() not in _JUNK), "")
    words = [w for w in re.split(r"[-_+\s]+", unquote(seg)) if w]
    # Amazon titles are keyword-stuffed; the first several words are the
    # product, the rest is "for Agriculture Garden Home Farm Use…". The owner
    # trims it in the form either way — this just keeps the slug sane.
    return " ".join(words[:10])


def parse(url: str) -> dict:
    """What the link says, plus the one problem to show the owner (or None)."""
    url = (url or "").strip()
    out = {"asin": "", "affil_amazon": "", "name_en": "", "slug": "",
           "problem": None, "note": None}
    if not url:
        out["problem"] = "Paste an Amazon link first."
        return out
    if not re.match(r"https?://", url, re.I):
        url = "https://" + url
    u = urlparse(url)
    host = (u.hostname or "").lower()

    if host in _SHORT_HOSTS:
        out["problem"] = ("This is a short link (amzn.to), which does not contain the "
                          "product. Open it in your browser and paste the full amazon.in "
                          "link from the address bar.")
        return out
    if host not in _HOSTS:
        out["problem"] = "Only amazon.in product links work here."
        return out

    asin = asin_of(url)
    if not asin:
        if u.path.rstrip("/") == "/s":
            out["problem"] = ("This is a search link, not a product. Open the product "
                              "you want and paste that page's link.")
        else:
            out["problem"] = "No product code (ASIN) in this link — paste the product page's link."
        return out

    out["asin"] = asin
    out["affil_amazon"] = clean_url(asin)
    out["name_en"] = _name_from_path(u.path)
    out["slug"] = slugify(out["name_en"])

    their_tag = (parse_qs(u.query).get("tag") or [""])[0]
    if their_tag and their_tag != TAG:
        out["note"] = f"The link carried someone else's tag ({their_tag}); it now carries yours."
    if not out["name_en"]:
        out["note"] = ("This link has no product name in it — type the English "
                       "name yourself. The link and ASIN are filled in.")
    return out


# Words every Amazon title carries, which would match any product at all.
_STOP = {"for", "and", "the", "with", "use", "set", "pack", "agriculture",
         "farm", "farming", "garden", "home", "plants", "plant", "kit", "india"}


def _words(s) -> set:
    return {w for w in re.findall(r"[a-z]+", (s or "").lower())
            if len(w) > 2 and w not in _STOP}


def guess_category(name_en: str, catalogue: list[dict]) -> dict:
    """Category and emoji of the catalogue product whose English name shares
    the most words with this one — no hand-kept keyword map to rot.
    Returns {} when nothing overlaps, so the form stays on "misc"."""
    words = _words(name_en)
    if not words:
        return {}
    # A vote by category, not the single nearest product: the catalogue files
    # one "Knapsack Sprayer 16L" under tools while six sprayers sit under
    # sprayers, and one odd neighbour should not decide.
    votes, best = {}, {}
    for p in catalogue:
        s = len(words & _words(p.get("name_en")))
        if not s:
            continue
        c = p.get("cat", "")
        votes[c] = votes.get(c, 0) + s
        if s > best.get(c, (0, None))[0]:
            best[c] = (s, p)
    if not votes:
        return {}
    best = best[max(votes, key=votes.get)][1]
    return {"cat": best.get("cat", ""), "emoji": best.get("emoji", ""),
            "like": best.get("slug", "")}

