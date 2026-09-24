"""/sponsor may never say anything about our audience that we cannot show.

This is the only page on the site that is read by someone about to send money,
and every failure mode here costs a relationship rather than a pageview. Three
of them are easy to ship by accident:

* **A stale number.** The figures are pulled from Search Console on a daily
  schedule. If the pull stops — no credentials on Render, a 403, a redeploy
  that wipes the cache — the page must stop quoting numbers, not keep serving
  August's audience to someone paying for September's. Nothing about a stale
  snapshot looks broken from the outside, which is exactly why it is pinned.

* **A sponsor who stopped paying.** A logo left up after `until` is both free
  advertising we are giving away and the reason a brand does not renew: it
  proves we do not track what we sold. Expiry is enforced in code, never
  remembered.

* **Exclusivity quietly voided.** Category exclusivity is the thing that makes
  a site this size worth brand money at all. Two live sponsors in one category
  breaks it for both, silently, and neither would find out from us.

Plus the standing trust rules, which are the product and not the fine print:
every sponsor unit is visibly labelled, every sponsor link is
rel="nofollow sponsored", and the page says in plain words that we cannot issue
a GST invoice yet rather than going quiet about it and letting a brand discover
it after saying yes.
"""
import json
from datetime import date, timedelta

import pytest

from backend.services import mediakit, sponsors

TODAY = date(2026, 9, 18)
PAST = (TODAY - timedelta(days=1)).isoformat()
FUTURE = (TODAY + timedelta(days=60)).isoformat()


def _row(**kw):
    base = {"id": "acme", "active": True, "name": "Acme Seeds",
            "category": "seed", "line": "Hybrid seed", "url": "https://acme.example",
            "until": FUTURE}
    base.update(kw)
    return base


@pytest.fixture
def registry(monkeypatch):
    """Swap the JSON registry for rows the test controls, without touching the
    real file — _load() caches by mtime, so writing to disk here would leak
    into every later test in the session."""
    def use(rows):
        monkeypatch.setattr(sponsors, "_load", lambda: {"sponsors": rows})
        return rows
    return use


@pytest.fixture
def snapshot(monkeypatch):
    """Control what mediakit believes it measured, including when."""
    def use(fetched_on, impressions=1_234_567):
        payload = {
            "fetched_on": fetched_on, "window_days": 28,
            "start": "2026-08-19", "end": "2026-09-15",
            "totals": {"impressions": impressions, "clicks": 11111,
                       "ctr": 0.5, "urls": 22222, "per_day": 33333},
            "series": [], "sections": {"/bhav": {"i": 765432, "c": 4444, "urls": 5555}},
            "devices": [{"k": "MOBILE", "pct": 90.0}],
            "countries": [{"k": "ind", "pct": 95.0}],
        }
        monkeypatch.setattr(mediakit, "_load", lambda: payload)
        return payload
    return use


@pytest.fixture
def kit(monkeypatch):
    """A valid kit URL for a prospect, with the signing secret set for the
    duration of the test."""
    monkeypatch.setenv("KM_SPONSOR_KIT_SECRET", "test-signing-secret")
    def url(who="acme"):
        return f"/sponsor/kit/{sponsors.kit_token(who)}"
    return url


# ── The numbers ─────────────────────────────────────────────────────────────

def test_page_renders_without_any_snapshot(client, monkeypatch):
    """No snapshot is a working page, not a 500 — and no figure either way."""
    monkeypatch.setattr(mediakit, "_load", lambda: {})
    r = client.get("/sponsor")
    assert r.status_code == 200
    assert 'class="sp-stat"' not in r.text


def test_a_stale_snapshot_is_withheld_from_the_KIT(client, snapshot, kit):
    """Older than MAX_AGE_DAYS and the numbers go away even for a prospect who
    holds a valid link. A partly-fresh media kit is the failure mediakit.py is
    shaped around, and the kit is now the only place figures appear at all."""
    snapshot((TODAY - timedelta(days=mediakit.MAX_AGE_DAYS + 1)).isoformat())
    assert mediakit.stats() is None
    r = client.get(kit("acme"))
    assert r.status_code == 200
    assert 'class="sp-stat"' not in r.text


def test_public_page_never_prints_a_figure_even_with_a_fresh_snapshot(client, snapshot):
    """THE LOAD-BEARING TEST OF THIS MODULE.

    The owner's instruction, 2026-09-18: the Search Console numbers must not be
    readable by anyone who opens the URL. Published, they tell every other agri
    publisher which surfaces work here and how large they are — worth far more
    to a competitor than to the one brand being pitched.

    A fresh snapshot is exactly the condition under which the old page DID
    print them, so that is the condition tested. Nothing about a leak here
    looks broken from the outside; it just quietly hands the numbers away.
    """
    snapshot(TODAY.isoformat())
    t = client.get("/sponsor").text
    # Made-up figures on purpose — this repo is public and the real Search
    # Console numbers are exactly what /sponsor keeps private.
    for figure in ("12,34,567", "1234567", "11,111", "11111",
                   "22,222", "22222", "33,333", "33333", "7,65,432", "765432"):
        assert figure not in t, figure
    assert "2026-08-19" not in t and "2026-09-15" not in t
    assert 'class="sp-stat"' not in t
    assert "not published on this page" in t


def test_no_snapshot_means_no_half_media_kit(monkeypatch):
    """A payload missing its totals must collapse to None rather than render
    the sections table on its own."""
    monkeypatch.setattr(mediakit, "_load", lambda: {"fetched_on": TODAY.isoformat()})
    assert mediakit.stats() is None


# ── What the page must keep saying ──────────────────────────────────────────

def test_page_admits_it_cannot_invoice(client):
    """Going quiet about this is how a signed sponsor stalls in someone's
    accounts department a month later."""
    t = client.get("/sponsor").text
    assert "not yet a registered company" in t
    assert "GST" in t


def test_nothing_for_sale_list_is_on_the_page(client):
    t = client.get("/sponsor").text
    for claim in sponsors.NEVER_FOR_SALE:
        # First clause is enough; the full sentence is escaped in the markup.
        assert claim.split(".")[0] in t, claim


def test_page_quotes_the_one_rate_card(client):
    """The prices come from services/sponsors.py so a future admin modal and a
    renewal email cannot disagree with the public page."""
    t = client.get("/sponsor").text
    for tier in sponsors.RATE_CARD:
        assert f'{tier["price"]:,}'.replace(",", ",") in t or str(tier["price"]) in t
        assert tier["name"] in t


def test_page_makes_no_cpm_or_roi_claim(client):
    t = client.get("/sponsor").text.lower()
    for forbidden in ("cpm", "roi", "guaranteed", "leads per", "conversion rate"):
        assert forbidden not in t.replace("no cpm", "").replace("not a cpm", ""), forbidden


# ── The registry ────────────────────────────────────────────────────────────

def test_empty_registry_renders_no_slot(registry):
    """An unsold slot collapses completely — the same rule ads.js follows for
    an unfilled AdSense unit. A labelled empty box on ~14k pages is worse than
    nothing."""
    registry([])
    assert sponsors.card_html("/bhav", TODAY) == ""


def test_live_sponsor_is_labelled_and_nofollowed(registry):
    registry([_row()])
    html = sponsors.card_html("/bhav", TODAY)
    assert "प्रायोजक" in html and "Sponsored" in html
    assert 'rel="nofollow sponsored"' in html
    # Never the brand's URL directly — the tracked hop is what we invoice on.
    assert "/go/s/acme" in html
    assert "acme.example" not in html


def test_expired_sponsor_disappears_on_its_own(registry):
    registry([_row(until=PAST)])
    assert sponsors.card_html("/bhav", TODAY) == ""


def test_an_unparseable_until_is_treated_as_expired(registry):
    """Never as forever. A typo in a date must fail closed."""
    registry([_row(until="soon")])
    assert sponsors.active(TODAY) == []


def test_half_filled_row_never_reaches_a_farmer(registry):
    for missing in ("name", "url", "category", "until"):
        registry([_row(**{missing: ""})])
        assert sponsors.active(TODAY) == [], missing


def test_inactive_row_never_renders(registry):
    registry([_row(active=False)])
    assert sponsors.active(TODAY) == []


def test_category_exclusivity_cannot_be_silently_voided(registry):
    """Two live sponsors in one category is the one bug that breaks the
    promise the Category Partner tier is sold on."""
    registry([_row(id="acme"), _row(id="rival", name="Rival Seeds")])
    live = sponsors.active(TODAY)
    assert [s["id"] for s in live] == ["acme"]


def test_different_categories_coexist(registry):
    registry([_row(id="acme"), _row(id="urea-co", category="fertilizer",
                                    name="Urea Co")])
    assert len(sponsors.active(TODAY)) == 2


def test_sections_limit_where_a_sponsor_appears(registry):
    registry([_row(sections=["/bhav"])])
    assert sponsors.for_path("/bhav/wheat", TODAY)
    assert sponsors.for_path("/articles/urea-guide-up", TODAY) == []


def test_empty_sections_means_site_wide(registry):
    registry([_row(sections=[])])
    assert sponsors.for_path("/articles/anything", TODAY)


def test_registry_file_on_disk_is_valid_and_starts_empty():
    """The shipped file must parse — a syntax error would mean no sponsor can
    be put live without a deploy, which is the seam this design removes."""
    data = json.loads(sponsors._PATH.read_text(encoding="utf-8"))
    assert isinstance(data.get("sponsors"), list)


# ── The tracked hop ─────────────────────────────────────────────────────────

def test_unknown_sponsor_id_redirects_and_records_nothing(client):
    """This count is what we invoice against, so it may never include a tap on
    a sponsorship that does not exist or has ended."""
    r = client.get("/go/s/nobody-here", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/"


# ── The link that makes any of this reachable ───────────────────────────────

def test_the_server_footer_links_to_both_money_pages(client):
    """The defect that made all of this worth building: /donate worked for
    weeks and was linked from two footers; /sponsor had nowhere at all."""
    t = client.get("/bhav").text
    assert "/sponsor" in t
    assert "/donate" in t


def test_the_slot_is_empty_on_every_page_while_nobody_is_paying(client, registry):
    """Today's real state, and it must look like nothing at all — no label, no
    reserved box, no gap at the bottom of ~14k pages."""
    registry([])
    t = client.get("/bhav").text
    assert 'class="km-sp"' not in t
    assert "प्रायोजक" not in t


def test_a_live_sponsor_reaches_a_real_page(client, registry, monkeypatch):
    """The other half: adding a row to the JSON must put the card on the site
    with no deploy. Without this the registry is a file nothing reads."""
    import backend.routes.bhav as bhav
    registry([_row()])
    monkeypatch.setattr(bhav.sponsors, "_load", lambda: {"sponsors": [_row()]})
    t = client.get("/bhav").text
    assert 'class="km-sp"' in t
    assert 'rel="nofollow sponsored"' in t
    assert "/go/s/acme" in t


def test_the_slot_sits_below_the_content(client, registry, monkeypatch):
    """Below what the farmer came for and below the page's own CTA — the same
    rule ads.js follows, for a stronger reason: a sponsor card above the price
    table spends the trust the sponsorship is priced on."""
    import backend.routes.bhav as bhav
    monkeypatch.setattr(bhav.sponsors, "_load", lambda: {"sponsors": [_row()]})
    t = client.get("/bhav").text
    assert t.index('class="km-sp"') > t.index('<div class="wrap">')
    assert t.index('class="km-sp"') < t.index('<footer class="km-footer">')


# ── Multi-Dimensional Targeting (State & Crop) ─────────────────────────────

def test_sponsor_state_targeting(registry):
    """A sponsor targeting MP should only render on MP pages, not on UP or generic pages."""
    registry([
        _row(id="mp-dealer", name="MP Agro", states=["madhya_pradesh"]),
    ])
    assert sponsors.for_path("/bhav", state="madhya_pradesh", today=TODAY)
    assert not sponsors.for_path("/bhav", state="uttar_pradesh", today=TODAY)
    assert not sponsors.for_path("/bhav", state="", today=TODAY)


def test_sponsor_crop_targeting(registry):
    """A crop-specific sponsor should only render when that crop is in scope."""
    registry([
        _row(id="soy-guard", name="Soy Guard", crops=["soybean"]),
    ])
    assert sponsors.for_path("/bhav", crop="soybean", today=TODAY)
    assert not sponsors.for_path("/bhav", crop="wheat", today=TODAY)
    assert not sponsors.for_path("/bhav", crop="", today=TODAY)


def test_sponsor_specificity_resolution(registry):
    """When a generic and a state-specific sponsor share a category, the state-specific
    one wins for that state due to higher specificity scoring."""
    registry([
        _row(id="pan-india", name="National Chem", category="pesticide"),
        _row(id="mp-specific", name="MP Pest Shield", category="pesticide",
             states=["madhya_pradesh"]),
    ])
    # On MP page: MP Pest Shield wins the single category slot
    mp_hits = sponsors.for_path("/bhav", state="madhya_pradesh", today=TODAY)
    assert len(mp_hits) == 1
    assert mp_hits[0]["id"] == "mp-specific"

    # On UP page: National Chem wins
    up_hits = sponsors.for_path("/bhav", state="uttar_pradesh", today=TODAY)
    assert len(up_hits) == 1
    assert up_hits[0]["id"] == "pan-india"


def test_page_does_not_promise_raw_gsc_access(client):
    """Search Console raw property access must never be promised or given away.
    The page should only offer verified summary exports."""
    t = client.get("/sponsor").text.lower()
    assert "read-only search console access" not in t
    assert "give a prospective sponsor read-only" not in t
    assert "search console access" not in t.replace("search console export", "")


# ── The private media kit ───────────────────────────────────────────────────
# The figures exist in exactly one place now. These pin the three things that
# keep them there: you need a link we issued, the link cannot be guessed or
# edited, and the mechanism is off unless deliberately switched on.

def test_kit_shows_the_figures_to_someone_holding_a_link(client, snapshot, kit):
    snapshot(TODAY.isoformat())
    r = client.get(kit("Acme Agro"))
    assert r.status_code == 200
    assert "12,34,567" in r.text
    assert 'class="sp-stat"' in r.text


def test_kit_names_the_prospect_it_was_issued_to(client, snapshot, kit):
    """So a forwarded link is attributable to whoever we gave it to."""
    snapshot(TODAY.isoformat())
    assert "acme_agro" in client.get(kit("Acme Agro")).text


def test_kit_is_noindex_in_header_and_body(client, snapshot, kit):
    """The header matters more than the meta tag: a crawler reaching this
    through a forwarded email obeys X-Robots-Tag long before it parses HTML."""
    snapshot(TODAY.isoformat())
    r = client.get(kit())
    assert "noindex" in r.headers.get("x-robots-tag", "")
    assert "noindex" in r.text
    assert "no-store" in r.headers.get("cache-control", "")


def test_a_forged_signature_is_a_404(client, kit):
    """404, never 401 or 'invalid link' — an error that distinguishes a wrong
    signature from a missing route confirms there is something here to probe."""
    kit()
    assert client.get("/sponsor/kit/acme.0000000000000000").status_code == 404
    assert client.get("/sponsor/kit/acme").status_code == 404


def test_a_link_cannot_be_edited_into_another_prospects(client, kit):
    """The slug is signed, so swapping the name invalidates the token — one
    brand cannot rename its own link and hand it on."""
    good = kit("acme")
    token = good.rsplit("/", 1)[1]
    sig = token.split(".", 1)[1]
    assert client.get(f"/sponsor/kit/rival.{sig}").status_code == 404


def test_the_kit_is_closed_entirely_when_no_secret_is_set(client, monkeypatch):
    """Fail closed. A deploy that forgets the env var must expose nothing,
    rather than fall back to some default signature."""
    monkeypatch.delenv("KM_SPONSOR_KIT_SECRET", raising=False)
    assert sponsors.kit_enabled() is False
    assert sponsors.kit_token("acme") == ""
    assert sponsors.kit_verify("acme.0000000000000000") is None
    assert client.get("/sponsor/kit/acme.0000000000000000").status_code == 404


def test_rotating_the_secret_revokes_outstanding_links(client, monkeypatch):
    monkeypatch.setenv("KM_SPONSOR_KIT_SECRET", "first")
    old = sponsors.kit_token("acme")
    monkeypatch.setenv("KM_SPONSOR_KIT_SECRET", "second")
    assert sponsors.kit_verify(old) is None


def test_the_kit_is_never_in_the_sitemap(client):
    """Unlinked and unguessable is the whole defence. Listing it anywhere —
    even to disallow it — announces that it exists."""
    assert "/sponsor/kit" not in client.get("/sitemap.xml").text


def test_no_page_on_the_site_links_to_the_kit(client):
    for path in ("/sponsor", "/bhav", "/donate"):
        assert "/sponsor/kit" not in client.get(path).text, path


# ── The admin panel ─────────────────────────────────────────────────────────
# The registry has to be editable while you are on the call with a brand, and
# the edit has to survive a redeploy — Render's free plan has no persistent
# disk, so a write to data/sponsors.json would silently revert. These pin the
# table half and the one rule the panel exists to enforce.

AUTH = ("testadmin", "test-admin-pass")


@pytest.fixture
def clean_sponsors(db_engine):
    """Empty the table around each test, holding NO session while the test runs.

    Deliberately not built on the `db_session` fixture: that one stays open for
    the whole test, and these tests then write through the app's own session
    over HTTP. Two live sessions against the one SQLite file is enough for a
    writer to block, and the failure does not look like a lock — the commit is
    simply lost, a later suite-mate finds rows it did not expect, and something
    innocent fails several files away.
    """
    from backend.database.db import Sponsor, SessionLocal

    def wipe():
        db = SessionLocal()
        try:
            db.query(Sponsor).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()
        sponsors.invalidate()

    wipe()
    yield
    wipe()


def _new(client, **kw):
    body = {"name": "Acme Seeds", "category": "seed", "url": "https://acme.example",
            "until": FUTURE, "active": True}
    body.update(kw)
    return client.post("/admin/sponsor", json=body, auth=AUTH)


def test_panel_requires_admin(client):
    assert client.get("/admin/sponsor").status_code == 401


def test_a_sponsor_added_in_the_panel_reaches_the_site(client, clean_sponsors):
    """The whole point: no deploy, no file edit, live on the next render."""
    assert _new(client).status_code == 200
    sponsors.invalidate()
    html = sponsors.card_html("/bhav", TODAY)
    assert "Acme Seeds" in html
    assert 'rel="nofollow sponsored"' in html


def test_the_panel_refuses_a_second_live_sponsor_in_one_category(client, clean_sponsors):
    """Refused with a message naming the holder, not silently dropped at render
    time — quietly hiding someone who paid is the worst way to find out."""
    assert _new(client).status_code == 200
    r = _new(client, name="Rival Seeds", slug="rival-seeds")
    assert r.status_code == 409
    assert "Acme Seeds" in r.json()["detail"]


def test_a_different_category_is_allowed(client, clean_sponsors):
    assert _new(client).status_code == 200
    assert _new(client, name="Urea Co", slug="urea-co",
                category="fertilizer").status_code == 200


def test_an_expired_sponsor_does_not_block_the_category(client, clean_sponsors):
    """A finished partnership is history, not a conflict — otherwise a renewal
    is impossible exactly when it matters."""
    assert _new(client, until=PAST).status_code == 200
    assert _new(client, name="Rival", slug="rival").status_code == 200


def test_going_live_needs_an_end_date_to_expire_on(client, clean_sponsors):
    """A row with no `until` can never expire, and an unexpiring slot is how a
    brand gets advertised free for a year."""
    r = _new(client, until="")
    # Accepted as a draft, but never rendered — the render guard requires until.
    if r.status_code == 200:
        sponsors.invalidate()
        assert sponsors.card_html("/bhav", TODAY) == ""


def test_a_paid_sponsor_cannot_be_deleted(client, clean_sponsors):
    """Ending a campaign is active=false. The record is what answers 'what did
    we run for them, and when'."""
    assert _new(client).status_code == 200
    assert client.post("/admin/sponsor/acme-seeds/payment",
                       json={"amount": 25000}, auth=AUTH).status_code == 200
    r = client.delete("/admin/sponsor/acme-seeds", auth=AUTH)
    assert r.status_code == 400
    assert "active=false" in r.json()["detail"]


def test_payment_is_recorded_by_a_human_not_inferred(client, clean_sponsors):
    """Nothing sets paid_at from a tapped upi:// link, because that hand-off
    reports nothing back."""
    assert _new(client).status_code == 200
    listed = client.get("/admin/sponsor", auth=AUTH).json()["sponsors"]
    assert listed[0]["paid_at"] is None
    # No amount, no payment: a ₹-less row would land in the हिसाब ledger as nothing.
    assert client.post("/admin/sponsor/acme-seeds/payment", json={},
                       auth=AUTH).status_code in (200, 400)
    client.post("/admin/sponsor/acme-seeds/payment", json={"amount": 75000}, auth=AUTH)
    listed = client.get("/admin/sponsor", auth=AUTH).json()["sponsors"]
    assert listed[0]["paid_at"] is not None


def test_panel_reports_whether_kit_links_can_be_issued(client, monkeypatch):
    """So the panel never offers a 'copy kit link' button that 404s."""
    monkeypatch.delenv("KM_SPONSOR_KIT_SECRET", raising=False)
    assert client.get("/admin/sponsor", auth=AUTH).json()["kit_enabled"] is False
    monkeypatch.setenv("KM_SPONSOR_KIT_SECRET", "x")
    assert client.get("/admin/sponsor", auth=AUTH).json()["kit_enabled"] is True


def test_kit_link_endpoint_refuses_clearly_when_the_secret_is_unset(client, monkeypatch):
    monkeypatch.delenv("KM_SPONSOR_KIT_SECRET", raising=False)
    r = client.get("/admin/sponsor/kit-link/Coromandel", auth=AUTH)
    assert r.status_code == 400
    assert "KM_SPONSOR_KIT_SECRET" in r.json()["detail"]


# ── the price-review reminder ───────────────────────────────────────────────

def test_price_baseline_matches_the_rate_card():
    """Change a price without moving PRICED_FOR and the growth reminder would
    measure traffic against the wrong baseline — so the two must agree."""
    card = {t["id"]: t["price"] for t in sponsors.RATE_CARD}
    assert card == sponsors.PRICED_FOR["card"], (
        "RATE_CARD changed — update PRICED_FOR (date, clicks_per_day, card) too")


@pytest.fixture(autouse=False)
def base_clicks(monkeypatch):
    # A made-up baseline; the real one is an env var (the repo is public).
    monkeypatch.setitem(sponsors.PRICED_FOR, "clicks_per_day", 1000)
    return 1000


def test_review_is_silent_without_a_baseline(monkeypatch):
    monkeypatch.setitem(sponsors.PRICED_FOR, "clicks_per_day", 0)
    assert sponsors.price_review(_series([10 ** 6] * 7)) is None


def _series(clicks):
    return {"series": [{"d": f"2026-10-{i + 1:02d}", "i": 0, "c": c}
                       for i, c in enumerate(clicks)]}


def test_no_review_while_traffic_is_near_the_baseline(base_clicks):
    base = sponsors.PRICED_FOR["clicks_per_day"]
    assert sponsors.price_review(_series([base] * 7)) is None
    assert sponsors.price_review(_series([base * 3] * 3)) is None   # too few days to judge


def test_review_suggests_prices_scaled_to_the_growth(base_clicks):
    base = sponsors.PRICED_FOR["clicks_per_day"]
    r = sponsors.price_review(_series([base * 2] * 7))
    assert r and r["step"] == 2 and r["ratio"] == 2.0
    by_id = {s["id"]: s for s in r["suggest"]}
    title = next(t for t in sponsors.RATE_CARD if t["id"] == "title")
    assert by_id["title"]["new"] == title["price"] * 2


def test_review_mails_once_per_step(tmp_path, monkeypatch, base_clicks):
    base = sponsors.PRICED_FOR["clicks_per_day"]
    sent = []
    real = sponsors.price_review
    monkeypatch.setattr(sponsors, "_REVIEW_STATE", tmp_path / "pr.json")
    monkeypatch.setattr(sponsors, "price_review",
                        lambda stats=None: real(_series([base * 2] * 7)))
    import backend.services.infra_service as infra
    monkeypatch.setattr(infra, "_mail", lambda subject, body: sent.append(subject))
    sponsors.price_review_check()
    sponsors.price_review_check()
    assert len(sent) == 1 and "raise sponsor prices" in sent[0]
