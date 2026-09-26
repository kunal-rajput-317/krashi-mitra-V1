"""Every waiting panel on the site shows the shape of what is coming.

98% of this site is read on a phone, much of it on a slow connection, and the
answer to "something is loading" was a 26px spinner, a spinning ↻, two grey
bars — or, on most panels, nothing at all. Each page now waits in the shape of
its OWN content: listing cards on /krashi_bajar, forecast card on /weather,
crop tiles on the homepage, result cards on /khoj, story cards on /krashi_news,
crop cards on /meri_fasal, and per-shape panels on /bhav's ~14k server pages.

What is pinned here is what would undo it:

  * ONE shimmer. Four private copies existed (index's skelShine, weather's
    wx-shimmer, bhav's skel-sh, krashibook's ↻) and none of them answered
    prefers-reduced-motion. km-skeleton.css is now the only definition;
  * it has to REACH every page — the static ones link it, and drawer-menu.js
    (the one script every page loads, including bhav.py's server pages and the
    articles) bootstraps it for the rest;
  * a skeleton must carry the page's own shape, not a generic grey box — that
    is the whole difference between this and the spinner it replaced;
  * a returning phone holds cache-first copies of these pages, so shipping
    them without bumping CACHE_NAME ships nothing to anyone who has been here
    before.
"""

import io
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
SKELETON_CSS = FRONTEND / "km-skeleton.css"


def read(rel):
    return io.open(ROOT / rel, encoding="utf-8").read()


@pytest.fixture(scope="module")
def css():
    return io.open(SKELETON_CSS, encoding="utf-8").read()


# ── The primitive ────────────────────────────────────────────

def test_the_primitive_exists(css):
    assert ".km-sk {" in css
    assert "@keyframes km-sk-sweep" in css
    assert ".km-sk::after" in css, "the sweep rides on ::after, not on the block"


def test_the_sweep_stops_for_reduced_motion(css):
    """A highlight travelling across the screen is exactly the motion a
    vestibular trigger asks the browser to stop. The block still has to read as
    loading, so it fades instead of freezing."""
    assert "@media (prefers-reduced-motion: reduce)" in css
    block = css.split("@media (prefers-reduced-motion: reduce)", 1)[1]
    assert "km-sk-fade" in block
    assert "animation: km-sk-fade" in block


def test_a_dark_panel_gets_an_inverted_tint(css):
    """The pale block disappears on /weather's dark card and on the homepage
    snapshot; `on-dark` is what those panels use."""
    assert ".km-sk.on-dark" in css


def test_screen_readers_get_one_label_not_a_wall_of_blocks(css):
    assert ".km-sk-label" in css
    rule = css.split(".km-sk-label", 1)[1].split("}", 1)[0]
    assert "clip:" in rule and "width: 1px" in rule


# ── It reaches every page ────────────────────────────────────

def test_the_shell_bootstraps_the_stylesheet():
    """drawer-menu.js is the one script every page already loads — the static
    pages, the articles and bhav.py's server pages alike. Without this, a page
    nobody remembered to edit renders its skeleton as invisible empty divs."""
    js = read("frontend/drawer-menu.js")
    assert "bootSkeletonCss" in js
    assert "km-skeleton.css" in js
    assert 'link[href*="km-skeleton.css"]' in js, "no double-include guard"


def test_the_server_shell_links_it():
    """bhav.py's _FONTS is what product.py, rental.py, naksha.py and poultry.py
    all put in their <head>. A lazy panel paints on first paint, before the
    deferred drawer-menu.js could inject anything."""
    py = read("backend/routes/bhav.py")
    assert '_FONTS += f\'<link rel="stylesheet" href="{_asset("km-skeleton.css")}">\'' in py


@pytest.mark.parametrize("page", [
    "index.html", "weather.html", "khoj.html", "krashi_news.html",
    "meri_fasal.html", "krashi_bajar.html", "profile.html",
])
def test_pages_that_paint_before_their_scripts_link_it(page):
    """These pages carry skeleton markup in the HTML itself, so the stylesheet
    cannot wait on a deferred script."""
    assert 'href="km-skeleton.css"' in read("frontend/" + page), page


# ── One shimmer, not five ────────────────────────────────────

@pytest.mark.parametrize("page,gone", [
    ("frontend/index.html",        "skelShine"),
    ("frontend/index.html",        "skel-box"),
    ("frontend/weather.html",      "wx-shimmer"),
    ("frontend/khoj.html",         "search-spinner"),
    ("frontend/krashi_news.html",  "scroll-spinner"),
    ("frontend/krashibook.js",     "km-book-spinner"),
    ("frontend/krashi_bajar.html", "bz-grow"),
])
def test_the_private_copies_are_gone(page, gone):
    assert gone not in read(page), f"{page} still ships its own {gone}"


def test_the_one_shimmer_that_stayed_still_answers_reduced_motion():
    """profile.html paints its shimmer ONTO the hero's real elements rather
    than standing blocks in for them, so it is not .km-sk — but it must still
    stop moving when asked."""
    html = read("frontend/profile.html")
    assert "@media (prefers-reduced-motion: reduce)" in html
    block = html.split("@media (prefers-reduced-motion: reduce)", 1)[1].split("}", 1)[0]
    assert "animation: none" in block


# ── Each page waits in its own shape ─────────────────────────

def test_homepage_waits_as_mandi_tiles():
    html = read("frontend/index.html")
    assert 'class="mandi-skel"' in html
    assert html.count('class="km-sk"') >= 12, "the six crop tiles lost their blocks"
    assert "weatherSkeleton()" in html, "the snapshot's values wait behind nothing"


def test_weather_waits_as_the_forecast_card():
    html = read("frontend/weather.html")
    for shape in (".wx-sk-card", ".wx-sk-hero", ".wx-sk-stats"):
        assert shape in html, shape
    assert "WX_SKELETON" in html, "every later lookup should reuse the same markup"


def test_khoj_waits_as_a_result_card():
    html = read("frontend/khoj.html")
    loading = html.split('id="search-loading-view"', 1)[1].split("</div>\n    </div>", 1)[0]
    assert "search-result-card" in loading
    assert "src-header" in loading and "src-body" in loading


def test_news_waits_as_a_story_card():
    html = read("frontend/krashi_news.html")
    assert "sk-card" in html
    assert "card-media-side" in html.split('id="news-grid"', 1)[1][:2000], \
        "the 155px picture is half of what a story card looks like"


def test_meri_fasal_waits_as_crop_cards_and_tiles():
    html = read("frontend/meri_fasal.html")
    grid = html.split('id="crop-grid"', 1)[1][:1200]
    assert "crop-tile" in grid and "ct-imgwrap" in grid
    crops = html.split('id="crops-container"', 1)[1][:1200]
    assert "fasal-card" in crops


def test_bazar_waits_as_listing_cards():
    html = read("frontend/krashi_bajar.html")
    assert ".bz-sk-hero" in html and ".bz-sk-acts" in html
    assert "bzSkeleton(fresh ? 3 : 2)" in html, \
        "a fresh feed and the next page are different waits"


def test_krashibook_waits_as_its_own_cards():
    js = read("frontend/krashibook.js")
    assert "function skeletonCards(" in js
    assert "km-book-card-head" in js.split("function skeletonCards(", 1)[1][:900]


# ── The server pages ─────────────────────────────────────────

def test_a_lazy_panel_names_its_shape():
    py = read("backend/routes/bhav.py")
    assert "def _lazy_skel(" in py
    for shape in ('"tiles"', '"rows"', '"card"'):
        assert shape in py, shape


@pytest.mark.parametrize("panel,shape", [
    ("bhav-crop-tail",   "tiles"),   # a grid of crop tiles
    ("bhav-lazy-t2",     "card"),    # the सबसे ऊंचा / सबसे कम pair
    ("bhav-lazy-t3",     "rows"),
    ("bhav-lazy-t4",     "rows"),    # the nearby-mandi comparison
    # The seasonality panel no longer has a skeleton of its own: it is the
    # "साल भर का" view inside the trend card, whose switch only appears once
    # that view has data (see bhav._trend_card) — nothing waits on screen.
])
def test_every_bhav_panel_picked_one(panel, shape):
    py = read("backend/routes/bhav.py")
    assert re.search(r"_lazy_div\(\s*'%s'\s*,\s*'%s'\s*\)" % (panel, shape), py), \
        f"{panel} still waits behind the generic shape"


def test_the_shaped_skeletons_have_css_to_hang_on():
    py = read("backend/routes/bhav.py")
    lazy_css = py.split("_LAZY_CSS = ", 1)[1].split('"""', 2)[1]
    for cls in (".lz-tiles", ".lz-tile", ".lz-rows", ".lz-row"):
        assert cls in lazy_css, cls


# ── The returning phone ──────────────────────────────────────

def test_the_service_worker_shipped_this():
    """These pages are cached cache-first. Without a bump, every phone that has
    been here before keeps the old spinner — and worse, keeps a page whose
    skeleton markup has no stylesheet."""
    sw = read("frontend/sw.js")
    m = re.search(r"const CACHE_NAME = 'krashimitra-v(\d+)'", sw)
    assert m, "no CACHE_NAME"
    assert int(m.group(1)) >= 19, "CACHE_NAME was not bumped for the skeletons"
    assert "'./km-skeleton.css'" in sw, "the stylesheet is not precached"
