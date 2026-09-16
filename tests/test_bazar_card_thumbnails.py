"""Every listing card shows a picture of the crop.

The 390px feed was five grey text boxes: 381px of filters above the first
listing, 147-231px per card for ~100 characters, and not one image, because
almost nobody uploads a photo and the ones that existed had 404'd. Cards now
fall back to the site's own licence-checked crop photos.

What is pinned here is what would put the feed back where it was:

  * the fallback must never be the OG banner — a card showing the KrashiMitra
    logo where the crop belongs looks broken, not branded;
  * a stock photo is OURS, not a picture of this farmer's crop, so the card
    must keep marking it as such;
  * the crop field is free text and the live feed is romanized Hindi ("Green
    matar", "Mera kela teyyari hai"), which no Devanagari table matches;
  * nothing important may sit in the bottom-right corner of a card, where the
    fixed "+ पोस्ट करें" button was found covering the offer button.
"""

import io
import re
from pathlib import Path

import pytest

from backend.routes.bazar import _crop_photo
from backend.routes.share import _FALLBACK_IMAGE


PAGE = Path(__file__).resolve().parents[1] / "frontend" / "krashi_bajar.html"


@pytest.fixture(scope="module")
def html():
    return io.open(PAGE, encoding="utf-8").read()


# ── The crop → photo fallback ────────────────────────────────

@pytest.mark.parametrize("crop", ["केला", "सरसों", "गेहूं", "आलू", "प्याज", "अदरक"])
def test_devanagari_crops_resolve(crop):
    url = _crop_photo(crop)
    assert url.startswith("https://krashimitra.in/images/crops/"), crop


@pytest.mark.parametrize("typed,devanagari", [
    # Every one of these is a real crop string from the production feed.
    ("Green matar", "मटर"),
    ("Mera kela teyyari hai", "केला"),
    ("Ginger", "अदरक"),
    # …and the shapes farmers type around them.
    ("gehu 50 qtl", "गेहूं"),
    ("Aloo", "आलू"),
    ("SARSON", "सरसों"),
])
def test_romanized_hindi_resolves(typed, devanagari):
    """_HI_CROP_EN is Devanagari-only, so the whole live feed missed it.

    Asserted against the Devanagari spelling rather than a filename: the photos
    carry their Commons names (आलू is `patates.webp`), and what matters is that
    both spellings of one crop land on one photo.
    """
    url = _crop_photo(typed)
    assert url, f"{typed!r} resolved to no photo"
    assert url == _crop_photo(devanagari), f"{typed!r} → {url}"


def test_an_unmatched_crop_returns_nothing_not_the_og_banner():
    """_crop_image() answers the site banner for anything it cannot place.

    That is right for a link preview and wrong on a card: it would put the
    KrashiMitra logo in the slot that is supposed to show a crop. The page
    draws an emoji tile when this is empty.
    """
    for crop in ["Ready for Sell", "", None, "zzqq", "  "]:
        out = _crop_photo(crop)
        assert out == "", f"{crop!r} → {out}"
        assert out != _FALLBACK_IMAGE


def test_the_photos_are_self_hosted():
    """Hotlinking is a standing rule here — see tests/test_no_hotlinked_images.py.

    These come back as krashimitra.in URLs rather than backend ones on purpose:
    Netlify serves them, so a feed full of thumbnails costs nothing against
    Render's metered egress.
    """
    url = _crop_photo("केला")
    assert url.startswith("https://krashimitra.in/")
    assert "wikimedia" not in url and "unsplash" not in url


def test_feed_serves_the_crop_photo(client):
    posts = client.get("/bazar/feed").json()["data"]["posts"]
    # The field must be present even on an empty feed's schema — check via a
    # post if there is one, and never 500 either way.
    for p in posts:
        assert "crop_image" in p, "the card cannot fall back to a photo it is not sent"


# ── The card markup ──────────────────────────────────────────

def test_the_farmers_own_photo_always_wins(html):
    """Priority: his upload → a relevant crop photo → an emoji tile.

    The tiers are stacked in the DOM rather than chosen between, so a dead src
    reveals the next one instead of leaving a hole. That only works if his
    upload is painted ON TOP — the fallback markup comes first and the <img>
    after it, and the z-index has to agree.
    """
    card = html[html.index("function postCardHtml"):]
    card = card[:card.index("\n}\n")]
    # In both real-media branches the fallback layer is emitted before the
    # farmer's own <img>/<video>, so his sits on top of it.
    branches = re.findall(r'heroHtml = `<div class="bz-hero is-real".*?`;', card, re.S)
    assert len(branches) == 2, f"expected an image and a video branch, found {len(branches)}"
    for branch in branches:
        media = re.search(r"<img |<video ", branch)
        assert media, branch[:120]
        assert branch.index("${fallback}") < media.start()

    under = re.search(r"\.bz-thumb-under\s*\{([^}]*)\}", html).group(1)
    real = re.search(r"\.bz-hero > img, \.bz-hero > video\s*\{([^}]*)\}", html).group(1)
    assert "z-index: 1" in under
    assert "z-index: 2" in real, "his own photo must paint above the fallback"


def test_a_stock_photo_is_never_passed_off_as_the_farmers_own(html):
    """It is our photo of the crop, not his photo of the goods.

    The first version said so by washing the photo out, which made the whole
    feed look drab. It now says so in words, so the label is what carries the
    claim and it may not quietly disappear.
    """
    assert ".bz-stock-tag" in html
    # Rendered when — and only when — the photo came from our crop table.
    assert "p.crop_image\n    ? `<span class=\"bz-stock-tag\">" in html
    # And the label is real text in every language the page ships, not a glyph.
    assert html.count("stock_photo:") == 3
    for word in ["प्रतीकात्मक चित्र", "Representative photo", "ಪ್ರಾತಿನಿಧಿಕ ಚಿತ್ರ"]:
        assert word in html


def test_a_dead_upload_falls_back_and_gets_labelled(html):
    """Every photo posted before R2 is gone, so this runs on real rows.

    Dropping the farmer's <img> reveals our crop photo underneath — at which
    point the card is no longer showing his crop and must say so.
    """
    fn = html[html.index("function bzThumbFallback"):]
    fn = fn[:fn.index("\n}\n")]
    assert "closest('.bz-hero')" in fn
    assert "is-real" in fn and "box.onclick = null" in fn, "a stock photo must stop opening full-size"
    assert "bz-stock-tag" in fn and "stock_photo" in fn


def test_the_fab_yields_to_the_offer_button(html):
    """The FAB must never be tappable on top of "₹ ऑफर भेजें".

    A hit test caught it there once, which is why the offer button spent a day
    on the left of the action row. The user asked for it back on the right
    (2026-09-16), so the resolution moved to the other side: the FAB now checks
    what it is covering once a scroll settles and hides itself rather than
    intercepting the one tap the whole page exists to produce.
    """
    # The requested order: icon buttons first, offer button last.
    assert "bz-act-spacer" in html
    assert html.index('<span class="bz-act-spacer">') < html.index("${offerBtn}")

    # And the guard that makes that safe.
    assert ".bz-fab.bz-fab-hide" in html
    fn = html[html.index("function fabAutoHide"):]
    fn = fn[:fn.index("\n  })();")]
    assert "coversOffer" in fn and ".bz-offer-btn" in fn, (
        "the FAB no longer checks whether it is covering the offer button"
    )
    assert "elementsFromPoint" in fn, "the check must hit-test, not guess from layout"
    assert "setTimeout" in fn, (
        "the check must run on scroll-settle; every frame would flicker the button"
    )


def test_no_stray_blues_on_a_green_and_amber_page(html):
    """#1a56db appeared once in the whole file, on the page heading, and the
    Follow link borrowed the verified badge's Twitter blue. Both read as
    unstyled defaults beside the site's palette."""
    # Matched as a declared value, not as a string: the comment explaining why
    # it went away names the colour too.
    assert not re.search(r":\s*#1a56db", html)
    follow = re.search(r"\.bz-follow-link\s*\{([^}]*)\}", html)
    assert follow, ".bz-follow-link rule not found"
    assert not re.search(r"color:\s*var\(--tick-blue\)", follow.group(1))
    # --tick-blue still exists — it is the verified badge, a real convention.
    assert "--tick-blue" in html


def test_an_unchanged_old_price_does_not_strike_itself_through(html):
    """A live listing rendered "₹2,100" beside a struck-through "₹2,100"."""
    assert "p.old_price !== p.price" in html


def test_the_owner_menu_is_a_menu_not_a_browser_prompt(html):
    """The ⋯ on your own listing used to call prompt("1 = बिक गया\n2 = पोस्ट
    हटाएं") — a browser dialog asking a farmer to type a digit.

    It is a real menu now, and edit moved into it from the action row so your
    own card has the same shape as everyone else's.
    """
    fn = html[html.index("function togglePostMenu"):]
    fn = fn[:fn.index("\n}\n")]

    assert "prompt(" not in fn, "the ⋯ menu is back to a browser prompt"
    for act in ("openEditPost", "markPostSold", "deletePost"):
        assert act in fn, f"{act} missing from the ⋯ menu"
    assert "danger: true" in fn, "delete must be marked as the destructive item"
    # Mark-sold is pointless on something already sold.
    assert "p.status === 'sold' ? [] :" in fn
    # It must be dismissible without choosing anything.
    assert "document.addEventListener('click', closePostMenu" in fn
    assert "Escape" in fn

    # And the standalone edit pill is gone from the action row.
    assert "bz-act-btn edit" not in html


def test_deleting_a_listing_can_be_taken_back_if_the_server_refuses(html):
    """The row is removed from the feed before the request is sent; if the
    request fails it has to go back where it was, not at the end."""
    fn = html[html.index("async function deletePost("):]
    fn = fn[:fn.index("\n}\n")]
    assert "feedPosts.splice(idx, 0, removed)" in fn, (
        "a refused delete must restore the listing at its original index"
    )
    assert "confirm(" in fn, "deleting a listing is irreversible; it must ask first"
