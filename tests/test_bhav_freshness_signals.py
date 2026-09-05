"""A /bhav page must be dated by its DATA, never by the clock.

Agmarknet reports roughly 18k of the ~34k mandi×crop pairs the snapshot holds,
so the snapshot deliberately carries a quiet mandi's last known price forward —
a farmer wants a number, not a blank page. Tier 4 was taught to say so on
2 Aug 2026 (_as_of_hi). Tiers 2 and 3 were not, and went on stamping
`_hindi_date(date.today())` on prices of any age. Measured against production on
4 Sep 2026:

    926 of 1,859 crop×state combos had a price from that day
    140 of them were more than a week old
    /bhav/cardamom/keralam  →  "📅 4 सितंबर 2026 · ताजा भाव"
                               over prices last reported on 17 अगस्त

The honest date was already in memory on that request — `_fresh_iso_state` was
computed two lines down and handed only to the robots gate.

The second half of the same lie is inside a single district: its rows routinely
span several days (Nashik onion, same date: 49 rows across 4 dates) and every
mandi card rendered identically, so a rate carried over from last week looked
exactly like one reported this morning. And the header's "… तक" date came from
`prices[0]` — whatever row Postgres happened to return first.

These tests pin all three: the tier-2/3 date, the age pill, and the per-card
stamp. Only the three that render a whole page need the schema, and even they
read no price row — every date on a tier-3 page comes from the slug index.
"""

from datetime import date, timedelta

from backend.routes import bhav


def _iso(days_ago: int) -> str:
    return (date.today() - timedelta(days=days_ago)).isoformat()


def _ddmmyyyy(days_ago: int) -> str:
    return (date.today() - timedelta(days=days_ago)).strftime("%d/%m/%Y")


# ── the age note ─────────────────────────────────────────────

class TestAgeNote:
    def test_today_and_yesterday_say_nothing(self):
        """Yesterday is the NORMAL case — the 08:00 IST fetch rebuilds the
        snapshot from the archive's copy of yesterday. A badge on half the site
        every morning is a badge farmers learn to ignore."""
        assert bhav._age_note(_iso(0)) == ""
        assert bhav._age_note(_iso(1)) == ""

    def test_two_days_and_older_say_how_old(self):
        assert bhav._age_note(_iso(2)) == "2 दिन पुराना भाव"
        assert bhav._age_note(_iso(18)) == "18 दिन पुराना भाव"

    def test_no_date_at_all_says_nothing(self):
        """A page with no reported date has nothing to disclose — inventing
        "0 दिन पुराना" would be a claim we cannot support."""
        for missing in ("", None, "not-a-date"):
            assert bhav._age_note(missing) == ""
            assert bhav._age_badge(missing) == ""

    def test_badge_wraps_the_note_only_when_there_is_one(self):
        assert bhav._age_badge(_iso(0)) == ""
        assert "18 दिन पुराना भाव" in bhav._age_badge(_iso(18))
        assert 'class="stale-pill"' in bhav._age_badge(_iso(18))


# ── the freshness rollups ────────────────────────────────────

IDX = {
    "crops":  {"wheat": "Wheat"},
    "states": {"wheat": {"uttar-pradesh": "Uttar Pradesh", "kerala": "Kerala"}},
    "dists":  {"wheat": {"uttar-pradesh": {"meerut": "Meerut", "agra": "Agra"},
                         "kerala": {"idukki": "Idukki"}}},
    "dates":  {"wheat": {"uttar-pradesh": {"meerut": _iso(0), "agra": _iso(9)},
                         "kerala": {"idukki": _iso(18)}}},
}


class TestFreshnessRollups:
    def test_state_is_as_fresh_as_its_newest_district(self):
        assert bhav._fresh_iso_state(IDX, "wheat", "uttar-pradesh") == _iso(0)
        assert bhav._fresh_iso_state(IDX, "wheat", "kerala") == _iso(18)

    def test_crop_is_as_fresh_as_its_newest_state(self):
        assert bhav._fresh_iso_crop(IDX, "wheat") == _iso(0)

    def test_rollups_match_what_the_sitemap_publishes(self):
        """<lastmod> and the printed date must come from the same numbers, or
        the page contradicts its own sitemap entry."""
        for ss in IDX["states"]["wheat"]:
            sitemap_lastmod = max(IDX["dates"]["wheat"][ss].values())
            assert bhav._fresh_iso_state(IDX, "wheat", ss) == sitemap_lastmod

    def test_unknown_crop_or_state_yields_no_date(self):
        assert bhav._fresh_iso_crop(IDX, "nope") == ""
        assert bhav._fresh_iso_state(IDX, "wheat", "nope") == ""


# ── the tier-2 / tier-3 pages ────────────────────────────────

class TestTierPagesAreDatedByData:
    """_state_page renders the real thing, so it needs the schema present
    (the dealer teaser and placement panels query it) — hence db_engine. It
    never reads a price row: every date on this page comes from the index."""

    def test_state_page_prints_the_data_date_not_today(self, db_engine):
        html = bhav._state_page(IDX, "wheat", "Wheat", "kerala").body.decode()
        stale_hi = bhav._hindi_date(date.today() - timedelta(days=18))
        today_hi = bhav._hindi_date(date.today())
        assert stale_hi in html, "the page must print the date its prices are from"
        assert f"📅 {today_hi}" not in html, (
            "18-day-old Kerala prices must not be presented under today's date")

    def test_state_page_shows_the_age_pill_when_stale(self, db_engine):
        html = bhav._state_page(IDX, "wheat", "Wheat", "kerala").body.decode()
        assert "18 दिन पुराना भाव" in html

    def test_state_page_stays_quiet_when_current(self, db_engine):
        html = bhav._state_page(IDX, "wheat", "Wheat", "uttar-pradesh").body.decode()
        # The CSS rule for .stale-pill ships on every page — only the
        # rendered span means the badge actually fired.
        assert '<span class="stale-pill">' not in html
        assert bhav._hindi_date(date.today()) in html

    def test_neither_tier_reintroduces_today_hi(self):
        """The mismatch came back once already. `today_hi` is deliberately not
        defined in any of the three tier renderers — keep it that way."""
        import inspect
        for fn in (bhav.bhav_crop, bhav._state_page, bhav.bhav_page):
            src = inspect.getsource(fn)
            assert "_hindi_date(date.today())" not in src, (
                f"{fn.__name__} dates itself from the clock again")


# ── inside one district: rows from different days ────────────

class TestMixedDateRows:
    ROWS = [
        {"date": _ddmmyyyy(7), "market": "Old APMC"},
        {"date": _ddmmyyyy(0), "market": "Fresh APMC"},
        {"date": _ddmmyyyy(3), "market": "Middling APMC"},
        {"date": "-",          "market": "Undated APMC"},
    ]

    def test_header_date_is_the_newest_row_not_the_first(self):
        """prices[0] is whatever Postgres returned first. Here it is a week old
        while the district has a price from today."""
        assert self.ROWS[0]["date"] != _ddmmyyyy(0)
        assert bhav._newest_row_date(self.ROWS) == _ddmmyyyy(0)

    def test_all_undated_rows_degrade_to_the_placeholder(self):
        assert bhav._newest_row_date([{"date": "-"}, {"date": ""}]) == "-"
        assert bhav._newest_row_date([]) == "-"

    def test_row_dates_sort_chronologically_not_lexically(self):
        """'02/09/2026' > '31/08/2026' as dates but not as strings — the whole
        reason these are compared as ISO."""
        assert bhav._row_date_iso("02/09/2026") > bhav._row_date_iso("31/08/2026")
        assert "02/09/2026" < "31/08/2026"      # the trap, spelled out
        assert bhav._row_date_iso("-") == ""
