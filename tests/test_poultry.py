"""/farm/poultry must never print an egg rate it cannot stand behind.

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
than a bare router — /farm borrows /bhav's shell, whose header builds the
quick-nav from the mandi index, so mounting the router alone would render a 500
that no assertion here would catch, and would miss a missing include_router.
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

PAGES = ["/farm", "/farm/poultry", "/farm/poultry/anda-rate/lucknow"]


@pytest.mark.parametrize("path", PAGES)
def test_page_renders(client, stored, path):
    r = client.get(path)
    assert r.status_code == 200, path
    assert "text/html" in r.headers["content-type"]


@pytest.mark.parametrize("path", PAGES[1:])
def test_every_page_that_prints_a_rate_carries_neccs_clarification(client, stored, path):
    """THE LICENCE TEST. NECC allows republication on the condition that this
    text goes with the numbers. Dropping it is not a cosmetic regression."""
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
        body = client.get("/farm/poultry/anda-rate/lucknow").text
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
    body = client.get("/farm/poultry/anda-rate/lucknow").text
    assert "प्रति अंडा" in body and "प्रति 100" in body


def test_zone_page_states_which_kind_of_price_it_is(client, stored):
    """Suggested and prevailing are different claims and the page has to say
    which one the number is."""
    assert "बाज़ार में चल रहा दाम" in client.get(
        "/farm/poultry/anda-rate/lucknow").text          # a prevailing zone
    assert "NECC का सुझाया दाम" in client.get(
        "/farm/poultry/anda-rate/ludhiana").text          # a suggested zone


def test_unknown_zone_goes_to_the_table_not_a_404(client, stored):
    r = client.get("/farm/poultry/anda-rate/nowhere", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].endswith("/farm/poultry")


def test_the_guessable_index_url_is_a_301_not_a_second_page(client, stored):
    """Two URLs for one answer is how an index gets diluted."""
    r = client.get("/farm/poultry/anda-rate", follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"].endswith("/farm/poultry")


# ── the plumbing that has been forgotten before ─────────────

def test_sitemap_lists_only_zones_that_have_a_rate(client, stored):
    xml = client.get("/farm/poultry/sitemap.xml").text
    locs = re.findall(r"<loc>(.*?)</loc>", xml)
    assert "https://krashimitra.in/farm/poultry" in locs
    zone_locs = [u for u in locs if "/anda-rate/" in u]
    assert len(zone_locs) == 34
    for u in zone_locs:
        assert u.rsplit("/", 1)[1] in poultry.zones()
    # A sitemap must not advertise a URL that renders empty.
    assert "/anda-rate/kurnool" not in xml


def test_redirects_proxies_the_whole_farm_tree(repo_root):
    """/ganna shipped once answering 200 on Render and 404 on krashimitra.in
    because this line was missing. It is asserted, not remembered."""
    rules = (repo_root / "frontend" / "_redirects").read_text(encoding="utf-8")
    assert re.search(r"^/farm\s+https://\S+/farm\s+200", rules, re.M)
    assert re.search(r"^/farm/\*\s+https://\S+/farm/:splat\s+200", rules, re.M)


def test_robots_declares_the_section_sitemap(repo_root):
    robots = (repo_root / "frontend" / "robots.txt").read_text(encoding="utf-8")
    assert "Sitemap: https://krashimitra.in/farm/poultry/sitemap.xml" in robots


def test_root_sitemap_lists_the_hubs(client, stored):
    xml = client.get("/sitemap.xml").text
    assert "<loc>https://krashimitra.in/farm</loc>" in xml
    assert "<loc>https://krashimitra.in/farm/poultry</loc>" in xml


def test_drawer_link_exists_on_both_sides(repo_root):
    """The drawer is built by drawer-menu.js at runtime and by bhav.py's
    _DRAWER_ITEMS on the server. A link added to one and not the other appears
    on half the site."""
    js = (repo_root / "frontend" / "drawer-menu.js").read_text(encoding="utf-8")
    py = (repo_root / "backend" / "routes" / "bhav.py").read_text(encoding="utf-8")
    assert "'/farm/poultry'" in js
    assert "🥚" in js and "🥚" in py
    assert "/farm/poultry" in py
