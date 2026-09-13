"""/pashupalan must never print an egg rate it cannot stand behind.

This section republishes someone else's numbers under someone else's terms, so
three things are pinned here that a 200-OK smoke test would sail straight past:

* **NECC's clarification is the licence, not a disclaimer.** The source permits
  republication only if the clarification travels with the prices. Every page
  that prints a rate reproduces it verbatim, and these tests fail the build the
  day one stops.
* **A gap stays a gap.** NECC skips days and revises published ones. The store
  is therefore an upsert, never an append-with-duplicates, and a day nobody
  reported never acquires a carried-forward number.
* **The rate is a suggestion, not our offer.** No Offer/price structured data —
  the same rule /rental follows for its editorial rate ranges, for the same
  reason: an Offer needs a seller who will honour it, and we are not one.

Plus the two mechanical things this repo has actually been bitten by: the
`_redirects` proxy line (missing on /ganna once, nearly missing on /rental) and
the lowercase-slug convention.

The page tests run against the real app via conftest's `client` fixture rather
than a bare router — /pashupalan borrows /bhav's shell, whose header builds the
quick-nav from the mandi index, so mounting the router alone would render a 500
that no assertion here would catch, and would miss a missing include_router.

The section moved from /farm/* to /pashupalan/* on 2026-09-12, while
/farm/poultry was earning ~1,800 impressions a month at position 8. THE OLD
URLs ARE PINNED HERE TOO: a rename that quietly starts 404ing is the one way
this change can cost more than it gains.
"""

import re
from datetime import date, timedelta
from pathlib import Path

import pytest

from backend.services import poultry, poultry_necc

FIXTURE = Path(__file__).parent / "fixtures" / "necc_eggprice_sample.html"
SHEET_MONTH, SHEET_YEAR = 8, 2026


@pytest.fixture(scope="module")
def sheet():
    return poultry_necc.parse_sheet(
        FIXTURE.read_text(encoding="utf-8", errors="replace"),
        SHEET_MONTH, SHEET_YEAR)


@pytest.fixture(scope="module")
def stored(db_engine, sheet):
    """Load the sample month once for the whole module, then clear it.

    Cleaned up explicitly rather than by session rollback: store_sheet commits
    (it is what the scheduler calls), so a rollback would not undo it and the
    rows would leak into every test that runs after this file.
    """
    from backend.database.db import (PoultryRate, PoultryRateHistory,
                                     SessionLocal)
    db = SessionLocal()
    try:
        poultry.store_sheet(db, sheet)
        yield db
    finally:
        db.query(PoultryRateHistory).delete()
        db.query(PoultryRate).delete()
        db.commit()
        db.close()


# ── the parser ──────────────────────────────────────────────

def test_parses_every_zone_in_both_sections(sheet):
    assert len(sheet["rows"]) == 34
    sections = {r["section"] for r in sheet["rows"]}
    assert sections == {"necc", "prevailing"}
    # The marker row splits the sheet; if it were missed, everything would
    # land in one section and the pages would claim NECC declared a rate it
    # did not.
    assert sum(1 for r in sheet["rows"] if r["section"] == "prevailing") == 10


def test_every_price_is_a_plausible_egg_price(sheet):
    for row in sheet["rows"]:
        for day, paise in row["days"].items():
            assert 1 <= day <= 31
            assert poultry_necc.PAISE_MIN <= paise <= poultry_necc.PAISE_MAX, row["zone"]


def test_unreported_days_are_absent_not_zero(sheet):
    """The sample is a month-to-date sheet: days after the 28th had not
    happened, so they must not exist at all rather than exist as 0."""
    for row in sheet["rows"]:
        assert 0 not in row["days"].values()
        assert max(row["days"]) <= 28


def test_table_is_found_by_header_not_position():
    """A source that adds one more table must not silently shift us onto it."""
    html = FIXTURE.read_text(encoding="utf-8", errors="replace")
    decoy = "<table><tr><td>an advert NECC added</td></tr></table>"
    parsed = poultry_necc.parse_sheet(decoy + html, SHEET_MONTH, SHEET_YEAR)
    assert len(parsed["rows"]) == 34


def test_a_reshaped_source_raises_rather_than_returning_nothing():
    """Silence is the dangerous failure — an empty parse would quietly wipe
    the pages. It has to be loud enough for the scheduler to log and keep the
    stored rates instead."""
    with pytest.raises(ValueError):
        poultry_necc.parse_sheet("<html><table><tr><td>x</td></tr></table></html>", 8, 2026)


def test_out_of_range_values_are_dropped_not_stored():
    html = ('<table><tr><th>Name Of Zone / Day</th><th>1</th><th>2</th></tr>'
            '<tr><td>Testpur</td><td>550</td><td>99999</td></tr></table>')
    row = poultry_necc.parse_sheet(html, 8, 2026)["rows"][0]
    assert row["days"] == {1: 550}


# ── the registry ────────────────────────────────────────────

def test_slugs_are_unique_and_lowercase():
    """The lowercase-slug convention: mixed case once put five article pages
    on two URLs each with conflicting canonicals."""
    zones = poultry.zones()
    assert len(zones) == 34
    for slug in zones:
        assert slug == slug.lower()
        assert re.fullmatch(r"[a-z0-9-]+", slug), slug


def test_registry_keys_match_neccs_own_spelling(sheet):
    """NECC's labels carry typos ('Luknow', 'Muzaffurpur') and a double space.
    The registry keys on those strings deliberately; correcting one here would
    silently drop that zone into the unknown path."""
    for row in sheet["rows"]:
        assert poultry.zone_meta(row["zone"])["known"], row["zone"]


def test_an_unregistered_zone_still_gets_a_page():
    """A zone NECC adds must not vanish because nobody has typed a Hindi name."""
    meta = poultry.zone_meta("Kurnool (CC)")
    assert meta["known"] is False
    assert meta["slug"] == "kurnool"
    assert meta["hi"] == "Kurnool"
    assert meta["centre"] == "CC"


# ── the store ───────────────────────────────────────────────

def test_store_writes_history_and_snapshot(stored, sheet):
    from backend.database.db import PoultryRate, PoultryRateHistory

    assert stored.query(PoultryRate).count() == 34
    expected = sum(len(r["days"]) for r in sheet["rows"])
    assert stored.query(PoultryRateHistory).count() == expected


def test_storing_the_same_sheet_twice_changes_nothing(stored, sheet):
    """NECC restates the whole month every day, so the daily job re-stores days
    it already has. That must be an upsert, not 28 duplicate rows per zone."""
    from backend.database.db import PoultryRateHistory

    before = stored.query(PoultryRateHistory).count()
    summary = poultry.store_sheet(stored, sheet)
    assert stored.query(PoultryRateHistory).count() == before
    assert summary["written"] == 0 and summary["revised"] == 0


def test_a_revised_day_is_corrected_in_place(stored, sheet):
    """NECC republishes a day with a different number; we must follow it
    rather than keep the first value we happened to see."""
    from backend.database.db import PoultryRateHistory

    revised = {**sheet, "rows": [{**sheet["rows"][0],
                                  "days": {**sheet["rows"][0]["days"], 1: 599}}]}
    before = stored.query(PoultryRateHistory).count()
    summary = poultry.store_sheet(stored, revised)
    assert summary["revised"] == 1
    assert stored.query(PoultryRateHistory).count() == before

    slug = poultry.zone_meta(sheet["rows"][0]["zone"])["slug"]
    row = (stored.query(PoultryRateHistory)
                 .filter_by(row_key=f"{slug}|{SHEET_YEAR}-{SHEET_MONTH:02d}-01").one())
    assert row.paise == 599
    # Put it back so later tests see the real sheet.
    poultry.store_sheet(stored, sheet)


def test_an_old_sheet_cannot_drag_the_headline_backwards(stored, sheet):
    """The backfill replays older months. Storing June must not overwrite
    today's rate with June's."""
    from backend.database.db import PoultryRate

    zone = sheet["rows"][0]["zone"]
    slug = poultry.zone_meta(zone)["slug"]
    today = stored.query(PoultryRate).filter_by(zone_slug=slug).one()
    kept_paise, kept_date = today.paise, today.rate_date

    poultry.store_sheet(stored, {"month": 6, "year": SHEET_YEAR,
                                 "rows": [{"zone": zone, "section": "necc",
                                           "days": {1: 480}, "avg": 480}]})
    stored.expire_all()
    after = stored.query(PoultryRate).filter_by(zone_slug=slug).one()
    assert (after.paise, after.rate_date) == (kept_paise, kept_date)


def test_history_trim_respects_the_declared_ceiling(stored):
    from backend.database.db import PoultryRateHistory

    old = date.today() - timedelta(days=poultry.POULTRY_HISTORY_DAYS + 10)
    stored.add(PoultryRateHistory(zone_slug="lucknow", section="prevailing",
                                  paise=500, rate_date=old,
                                  row_key=f"lucknow|{old.isoformat()}"))
    stored.commit()
    assert poultry.trim_history(stored) >= 1
    assert (stored.query(PoultryRateHistory)
                  .filter(PoultryRateHistory.rate_date == old).count() == 0)


# ── the pages ───────────────────────────────────────────────

PAGES = ["/pashupalan", "/pashupalan/anda-rate", "/pashupalan/anda-rate/lucknow"]


@pytest.mark.parametrize("path", PAGES)
def test_page_renders(client, stored, path):
    r = client.get(path)
    assert r.status_code == 200, path
    assert "text/html" in r.headers["content-type"]


@pytest.mark.parametrize("path", PAGES)
def test_every_page_that_prints_a_rate_carries_neccs_clarification(client, stored, path):
    """THE LICENCE TEST. NECC allows republication on the condition that this
    text goes with the numbers. Dropping it is not a cosmetic regression.

    Scoped to PAGES[1:] until 2026-09-14, on the reasoning that /pashupalan was
    a shelf of guides rather than a rate page. It had stopped being one: the
    hub grew a headline block printing "आज का औसत NECC अंडा रेट — ₹579 प्रति
    100" and shipped it with no clarification anywhere on the page. The rule is
    about the number, not about which tier prints it, so the parametrisation
    now follows the rule instead of the original page list."""
    body = client.get(path).text
    assert poultry_necc.CLARIFICATION in body, path
    assert poultry_necc.CLARIFICATION_HI in body, path
    assert "e2necc.com" in body, path


@pytest.mark.parametrize("path", PAGES[1:])
def test_no_offer_markup_for_a_suggested_price(client, stored, path):
    """An Offer needs a seller who will honour the price. NECC's number is a
    suggestion and we are not selling eggs, so marking it up as an offer would
    be a false claim in structured data — same rule /rental follows."""
    body = client.get(path).text
    assert '"@type": "Offer"' not in body
    assert '"@type": "AggregateOffer"' not in body


@pytest.mark.parametrize("path", PAGES[1:])
def test_freshness_signal_is_the_rate_date_never_today(client, stored, path):
    """A page whose FAQ states "आज ₹5.50" only stays honest while Google's copy
    is recent, and without a real dateModified Google has nothing to judge that
    by — the bug that put a 13 Jul snippet on a 2 Aug /bhav page."""
    r = client.get(path)
    stored_day = poultry.updated(stored)
    assert "Last-Modified" in r.headers
    # Not "today's date is absent" — the sample's newest day may BE today, and
    # then that assertion proves nothing. The real claim is that every date the
    # page declares is the date the rate was reported, whatever today is.
    declared = set(re.findall(r'"dateModified":\s*"(\d{4}-\d{2}-\d{2})"', r.text))
    assert declared == {stored_day.isoformat()}, path


def test_a_stale_snapshot_dates_itself_honestly(client, stored):
    """The signal has to follow the DATA, not the clock. Pushed a week back,
    the page must say so rather than quietly presenting week-old numbers as
    today's — the failure that put a 13 Jul snippet on a 2 Aug /bhav page."""
    from backend.database.db import PoultryRate

    row = stored.query(PoultryRate).filter_by(zone_slug="lucknow").one()
    real_date, real_paise = row.rate_date, row.paise
    row.rate_date = real_date - timedelta(days=7)
    stored.commit()
    try:
        body = client.get("/pashupalan/anda-rate/lucknow").text
        assert f'"dateModified": "{(real_date - timedelta(days=7)).isoformat()}"' in body
        assert date.today().isoformat() not in body.split("</head>")[0]
    finally:
        row.rate_date, row.paise = real_date, real_paise
        stored.commit()


@pytest.mark.parametrize("path", PAGES)
def test_serp_budgets(client, stored, path):
    """Titles over 68 chars and descriptions over 162 get truncated in the
    SERP — the budget the article builder already enforces."""
    body = client.get(path).text
    title = re.search(r"<title>(.*?)</title>", body, re.S).group(1)
    desc = re.search(r'<meta name="description" content="(.*?)"', body, re.S).group(1)
    assert len(title) <= 68, f"{path}: {len(title)} — {title}"
    assert len(desc) <= 162, f"{path}: {len(desc)}"


def test_both_units_appear_together(client, stored):
    """"₹5.50" and "₹550" are the same price. Printing one without the other is
    how a farmer reads a per-100 rate as a per-egg rate."""
    body = client.get("/pashupalan/anda-rate/lucknow").text
    assert "प्रति अंडा" in body and "प्रति 100" in body


def test_zone_page_states_which_kind_of_price_it_is(client, stored):
    """Suggested and prevailing are different claims and the page has to say
    which one the number is."""
    assert "बाज़ार में चल रहा दाम" in client.get(
        "/pashupalan/anda-rate/lucknow").text          # a prevailing zone
    assert "NECC का सुझाया दाम" in client.get(
        "/pashupalan/anda-rate/ludhiana").text          # a suggested zone


def test_unknown_zone_goes_to_the_table_not_a_404(client, stored):
    r = client.get("/pashupalan/anda-rate/nowhere", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].endswith("/pashupalan/anda-rate")


def test_the_guessable_index_url_is_a_301_not_a_second_page(client, stored):
    """Two URLs for one answer is how an index gets diluted."""
    r = client.get("/pashupalan/poultry", follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"].endswith("/pashupalan/anda-rate")


# ── the plumbing that has been forgotten before ─────────────

def test_sitemap_lists_only_zones_that_have_a_rate(client, stored):
    xml = client.get("/pashupalan/sitemap.xml").text
    locs = re.findall(r"<loc>(.*?)</loc>", xml)
    assert "https://krashimitra.in/pashupalan/anda-rate" in locs
    zone_locs = [u for u in locs if "/anda-rate/" in u]
    assert len(zone_locs) == 34
    for u in zone_locs:
        assert u.rsplit("/", 1)[1] in poultry.zones()
    # A sitemap must not advertise a URL that renders empty.
    assert "/anda-rate/kurnool" not in xml


def test_redirects_proxies_the_whole_section(repo_root):
    """/ganna shipped once answering 200 on Render and 404 on krashimitra.in
    because this line was missing. It is asserted, not remembered."""
    rules = (repo_root / "frontend" / "_redirects").read_text(encoding="utf-8")
    assert re.search(r"^/pashupalan\s+https://\S+/pashupalan\s+200", rules, re.M)
    assert re.search(r"^/pashupalan/\*\s+https://\S+/pashupalan/:splat\s+200",
                     rules, re.M)


def test_robots_declares_the_section_sitemap(repo_root):
    robots = (repo_root / "frontend" / "robots.txt").read_text(encoding="utf-8")
    assert "Sitemap: https://krashimitra.in/pashupalan/sitemap.xml" in robots


def test_root_sitemap_lists_the_hubs(client, stored):
    xml = client.get("/sitemap.xml").text
    assert "<loc>https://krashimitra.in/pashupalan</loc>" in xml
    assert "<loc>https://krashimitra.in/pashupalan/anda-rate</loc>" in xml
    # A sitemap lists canonicals only. The old tree 301s, and advertising a
    # redirect asks Google to pick between two URLs for one answer.
    assert "/farm" not in xml


def test_drawer_link_exists_on_both_sides(repo_root):
    """The drawer is built by drawer-menu.js at runtime and by bhav.py's
    _DRAWER_ITEMS on the server. A link added to one and not the other appears
    on half the site."""
    js = (repo_root / "frontend" / "drawer-menu.js").read_text(encoding="utf-8")
    py = (repo_root / "backend" / "routes" / "bhav.py").read_text(encoding="utf-8")
    assert "'/pashupalan/anda-rate'" in js
    assert "🥚" in js and "🥚" in py
    assert "/pashupalan/anda-rate" in py


# ── the rename: every old address still answers ─────────────
#
# The section was /farm/* until 2026-09-12. /farm/poultry was the only URL in
# it earning anything — ~1,800 impressions a month at position 8 — so a 404
# here would cost more than the rename gains. Both halves are pinned: the
# backend routes (for a request that reaches Render directly) and the Netlify
# edge rules (for everyone else).

OLD_TO_NEW = [
    ("/farm", "/pashupalan"),
    ("/farm/poultry", "/pashupalan/anda-rate"),
    ("/farm/poultry/anda-rate", "/pashupalan/anda-rate"),
    ("/farm/poultry/anda-rate/lucknow", "/pashupalan/anda-rate/lucknow"),
    ("/farm/poultry/sitemap.xml", "/pashupalan/sitemap.xml"),
]


@pytest.mark.parametrize("old,new", OLD_TO_NEW)
def test_every_old_url_is_a_301_to_its_new_one(client, stored, old, new):
    r = client.get(old, follow_redirects=False)
    assert r.status_code == 301, old
    assert r.headers["location"].endswith(new), f"{old} -> {r.headers['location']}"


def _edge_resolve(rules: str, path: str) -> tuple[str, str] | None:
    """Where Netlify would actually send `path`, and with what status.

    Applies the FIRST matching rule, which is what Netlify does, and expands
    :splat — so this answers "where does the farmer land", not merely "is
    there a line for it". Returns None if the path falls through to the site
    catch-all.
    """
    for line in rules.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        src, dest, status = parts[0], parts[1], (parts[2] if len(parts) > 2 else "200")
        if src.endswith("/*"):
            stem = src[:-2]
            if path == stem or path.startswith(stem + "/"):
                # A splat matches its own parent with an EMPTY splat — which is
                # how /farm/poultry/anda-rate once landed on a trailing slash.
                splat = path[len(stem) + 1:] if path != stem else ""
                return dest.replace(":splat", splat), status
        elif src == path:
            return dest, status
    return None


@pytest.mark.parametrize("old,new", OLD_TO_NEW)
def test_the_old_urls_301_at_the_edge_too(repo_root, old, new):
    """A 301 served by Render costs a cold start; one served by Netlify does
    not. /ganna taught this repo that a missing _redirects line is invisible
    locally and fatal in production, so the edge half is asserted rather than
    remembered.

    The assertion is on the EXACT landing URL, not on "a rule exists". Netlify
    applies the first match and a splat matches its own parent with an empty
    :splat, so with /anda-rate/* listed above /anda-rate the old index URL
    301'd to /pashupalan/anda-rate/ — a second URL for one answer that only a
    canonical tag was cleaning up after. A 301 has to land ON the canonical.
    """
    rules = (repo_root / "frontend" / "_redirects").read_text(encoding="utf-8")
    got = _edge_resolve(rules, old)
    assert got, f"{old} falls through to the site catch-all"
    dest, status = got
    assert status.startswith("301"), f"{old} -> {dest} ({status})"
    assert dest == new, f"{old} -> {dest}, expected exactly {new}"


@pytest.mark.parametrize("old,_new", OLD_TO_NEW)
def test_a_redirect_cannot_be_pointed_somewhere_else(client, stored, old, _new):
    """These 301s are built by a factory, and the obvious way to bind the
    target — `def handler(to: str = to)` — makes FastAPI read `to` as a QUERY
    PARAMETER. /farm?to=https://evil.example.com then 301s off our own domain,
    from a URL Google still has indexed. Caught 2026-09-12 before it shipped."""
    r = client.get(f"{old}?to=https://evil.example.com/x&url=https://evil.example.com",
                   follow_redirects=False)
    assert r.status_code in (301, 302), old
    assert "evil.example.com" not in r.headers["location"], (
        f"{old} is an open redirect: {r.headers['location']}")
    assert r.headers["location"].startswith("https://krashimitra.in/"), old


def test_the_farm_splat_rule_stays_last(repo_root):
    """Netlify takes the FIRST matching rule. /farm/* would swallow every more
    specific /farm/poultry line above it and drop a farmer looking for his
    city's rate onto the section hub instead."""
    rules = (repo_root / "frontend" / "_redirects").read_text(encoding="utf-8")
    lines = [ln for ln in rules.splitlines() if ln.startswith("/farm")]
    assert lines, "the old tree has no redirect rules at all"
    assert lines[-1].startswith("/farm/*"), lines


# ── the shell: this section is not a stranger inside it ─────

@pytest.mark.parametrize("path", PAGES)
def test_the_drawer_says_you_are_here(client, stored, path):
    """Every page here shipped with active="", so the 🥚 drawer entry never
    lit up — on the one section whose pages a farmer returns to daily.
    drawer-menu.js cannot rescue it: it only marks links it ADDS, and bhav.py's
    server drawer already ships this one."""
    body = client.get(path).text
    assert 'sidebar-drawer-link active' in body, path
    assert re.search(r'class="sidebar-drawer-link active"[^>]*>\s*'
                     r'<span class="sidebar-drawer-link-icon">🥚', body), path


@pytest.mark.parametrize("path", PAGES)
def test_the_blue_bar_belongs_to_this_section(client, stored, path):
    """bhav.py's _header builds the blue bar from the mandi index, so a section
    that borrows the shell and leaves it alone advertises गेहूं/धान/प्याज on
    top of an egg rate. These pages pass their own."""
    body = client.get(path).text
    bar = body.split('<div class="commodity-navbar">')[1].split("</div>")[0]
    assert "की कीमत" not in bar, f"{path}: still showing the mandi crop bar"
    assert "/pashupalan/anda-rate" in bar, path


@pytest.mark.parametrize("path", PAGES)
def test_pages_carry_a_real_image_not_the_generic_banner(client, stored, path):
    """/bhav's leaves ship a crop photo; every page here fell back to the site
    banner, so a share of "लखनऊ अंडा रेट" looked like a share of the homepage."""
    body = client.get(path).text
    og = re.search(r'property="og:image" content="(.*?)"', body).group(1)
    assert og.endswith(".webp") and "og-banner" not in og, f"{path}: {og}"


def test_the_rate_table_can_be_searched(client, stored):
    """34 rows with no filter meant a farmer whose city sat 28 down had to
    scroll for it, on a page whose whole job is answering fast. Same component
    /bhav's hub filters its crop tiles with."""
    body = client.get("/pashupalan/anda-rate").text
    assert 'id="egg-search"' in body
    assert 'class="ctile-search-row"' in body          # the site's own search box
    # …and every row has to be findable by Hindi name, English slug or state.
    assert re.search(r'class="egg-row"[^>]*data-name="[^"]*lucknow[^"]*"', body)
    assert re.search(r'class="egg-row"[^>]*data-name="[^"]*लखनऊ[^"]*"', body)
    # eggFilter() hides with el.hidden, and the UA's [hidden]{display:none} is
    # a (0,1,0) rule that loses to .egg-row{display:flex}. Without this line
    # the filter hid nothing it was asked to: searching one city left the
    # other section's 24 rows on screen, looking like results for the query.
    assert ".egg-row[hidden]" in body and ".shop-section-title[hidden]" in body


@pytest.mark.parametrize("path", PAGES)
def test_headings_use_the_sites_own_component(client, stored, path):
    """This module shipped a 12.5px grey `.egg-sec` heading that existed
    nowhere else on the site, so a farmer arriving from /bhav met a page that
    did not look like the one he left."""
    body = client.get(path).text
    assert "egg-sec" not in body, f"{path}: the local heading style is back"
    assert "shop-section-title" in body, path


def test_the_homepage_links_into_the_section(repo_root):
    """The section was reachable only from the hamburger drawer — the one page
    on the site that answers a question DAILY was invisible from the front
    door, which is the opposite of what a return-visit surface needs."""
    home = (repo_root / "frontend" / "index.html").read_text(encoding="utf-8")
    assert "/pashupalan" in home


def test_the_bottom_bar_does_not_break_on_a_nested_path(repo_root):
    """bottomnav.js decided relative-vs-absolute links from a hand-kept list of
    backend trees. Every section added after it was written inherited a broken
    bar: on /farm/poultry/anda-rate/lucknow, दुकान pointed at a sibling
    shop.html and कृषि न्यूज़ at another — two of four tabs 404ing on every
    page in this section. The fallback below cannot go stale, so it must stay:
    a relative link is only ever correct when the page's directory IS the root.
    """
    js = (repo_root / "frontend" / "bottomnav.js").read_text(encoding="utf-8")
    assert "path.replace(/[^/]*$/, '') !== '/'" in js, (
        "the relative/absolute rule is back to being a hand-kept allow-list")


def test_the_feed_grain_hubs_link_back():
    """/pashupalan links out to मक्का and सोयाबीन because feed is two-thirds of
    what a poultry farm spends. Nothing linked back, so the only routes into
    this section were the sitemap and the hamburger drawer — which is how 34
    zone pages spent their first fortnight earning zero impressions.

    Tier 2 only: the same link on the ~2,000 maize district pages would be
    spam, and the crop hub is the page in that tree that ranks.
    """
    from backend.routes.bhav import _poultry_cta

    for crop in ("maize", "soyabean"):
        assert "/pashupalan/anda-rate" in _poultry_cta(crop), crop
    # …and nowhere else, so every other crop hub renders byte-identically to
    # before. (Asserted on the helper, not a rendered page: /bhav/{crop} needs
    # the mandi index, which this suite's throwaway SQLite DB has no rows for.)
    assert _poultry_cta("wheat") == ""


# ── the table hands off, it does not answer for 34 cities ───

def test_the_table_does_not_print_a_rate_it_should_be_handing_off(client, stored):
    """/pashupalan/anda-rate is a tier page: it answers its own question and
    then sends the farmer down, exactly the way /bhav's tier pages do.

    It used to print all 34 absolutes, which made it the last page anyone
    needed. In the 28 days to 2026-09-09 the table earned 1,793 impressions
    and all 34 zone pages earned ZERO — a farmer who could read लखनऊ's rate
    off row 21 had no reason to open the page carrying लखनऊ's 30-day trend,
    last-year comparison and rank. Each row now carries the delta as the hook
    and a way in, and nothing else. (/bhav's own `.dcard` goes further and
    shows no number at all; the delta is here because the 2026-07-16 round on
    /bhav settled that a bare word creates no curiosity.)
    """
    body = client.get("/pashupalan/anda-rate").text
    rows = re.findall(r'<a class="egg-row".*?</a>', body, re.S)
    assert len(rows) >= 20, len(rows)

    z = poultry.zone(stored, "lucknow")
    mine = [r for r in rows if f'/anda-rate/{z["slug"]}"' in r]
    assert len(mine) == 1
    row = mine[0]
    # Neither unit of the absolute may appear inside the row…
    assert f"₹{poultry.rupees(z['paise'])}" not in row
    assert f"₹{poultry.per_hundred(z['paise'])}" not in row
    assert "प्रति 100" not in row and "/अंडा" not in row
    # …and the name is still there, so the layout is teased, not collapsed.
    assert z["hi"] in row

    # Every row, not just this one, offers the way in.
    for r in rows:
        assert "रेट देखें →" in r


def test_the_tables_own_answer_stays_complete(client, stored):
    """Hiding the per-city rate must not leave the page with no number on it —
    a farmer who searched "आज का अंडा रेट" came here for one, and this is the
    section's only URL that has ever earned an impression.

    The page's OWN answer — today's average, the dearest zone, the cheapest —
    is page content and stays, the same line /bhav draws around a district
    average (see feedback: hide the value, not the layout).
    """
    body = client.get("/pashupalan/anda-rate").text
    rows = (poultry.latest(stored, section="necc")
            or poultry.latest(stored, section="prevailing"))
    avg = round(sum(r["paise"] for r in rows) / len(rows))
    assert f"₹{poultry.rupees(avg)}" in body
    assert f"₹{poultry.per_hundred(avg)}" in body

    # And the two stats that NAME a zone are doors into it, not dead labels.
    for edge in (rows[0], rows[-1]):
        assert re.search(
            rf'<a href="[^"]*/anda-rate/{re.escape(edge["slug"])}">'
            rf'<b>₹{re.escape(poultry.rupees(edge["paise"]))}</b>', body), edge["slug"]


def test_the_peer_block_compares_against_the_zone_whose_page_it_is(client, stored):
    """The block is headed "तुलना". It used to print each peer's own
    day-over-day change under that heading, which compared nothing to
    anything. The delta is now peer-minus-this-zone — /bhav's `_cmp_card`
    shape, where the sub-label names the number being compared against.
    """
    me = poultry.zone(stored, "lucknow")
    body = client.get("/pashupalan/anda-rate/lucknow").text
    assert f"₹{poultry.rupees(me['paise'])} से तुलना" in body

    rows = re.findall(r'<a class="egg-row" href="[^"]*/anda-rate/([a-z0-9-]+)".*?</a>',
                      body, re.S)
    assert rows, "the zone page lost its peer block"
    assert "lucknow" not in rows, "a zone must not be its own peer"
    for slug in rows:
        row = re.search(rf'<a class="egg-row" href="[^"]*/anda-rate/{slug}".*?</a>',
                        body, re.S).group(0)
        diff = poultry.zone(stored, slug)["paise"] - me["paise"]
        if diff:
            assert f"₹{abs(diff) / 100:.2f} {'ज़्यादा' if diff > 0 else 'कम'}" in row, slug
        else:
            assert "बराबर" in row, slug
