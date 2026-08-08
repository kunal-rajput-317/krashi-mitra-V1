"""/ganna must never state a cane price it cannot source.

The bug this pins: the state page had one "no SAP here" branch serving two
different situations. Karnataka genuinely has no State Advised Price — the
centre's FRP is the whole story. Bihar *does* declare a SAP; we simply could
not source this season's figure. Both rendered the same copy, so Bihar's
<title>, meta description and FAQ answer all told a cane farmer his state has
no SAP. That is a false claim about money, on the page he came to for the
number, and it is invisible in a smoke test that only checks for HTTP 200.

The three cases must stay distinguishable:
  verified SAP        → show the rate
  SAP, unsourced      → say the rate is not confirmed, never that none exists
  FRP-only state      → say there is no SAP
"""

import json
import re

from backend.routes.ganna import _eff_frp, _frp, _load, _season_for

# These run against the real app via conftest's `client` fixture, not a bare
# router: /ganna borrows /bhav's page shell, whose header builds the quick-nav
# from the mandi index, so the pages touch the DB even though the cane data
# itself is a flat file. Mounting the router alone renders a 500 that no
# assertion here would catch — and it would miss a missing include_router.


def _states():
    return _load()["states"]


def _slugs(kind=None, indexed=None, has_rates=None):
    out = []
    for s in _states():
        if kind is not None and s.get("kind") != kind:
            continue
        if indexed is not None and bool(s.get("indexed")) != indexed:
            continue
        if has_rates is not None and bool(s.get("rates")) != has_rates:
            continue
        out.append(s["slug"])
    return out


def _page(client, slug):
    r = client.get(f"/ganna/{slug}")
    assert r.status_code == 200
    return r.text


def _title(html):
    return re.search(r"<title>(.*?)</title>", html, re.S).group(1)


def _desc(html):
    return re.search(r'name="description" content="([^"]*)"', html).group(1)


# ── the actual bug ──────────────────────────────────────────────────────────

# "there is no SAP in this state", in the phrasings the page can produce.
_DENIES_SAP = re.compile(r"अलग\s+(राज्य दर\s*\(SAP\)|SAP|राज्य दर)\s+नहीं")


def test_sap_state_without_a_sourced_rate_never_denies_having_a_sap(client):
    """Bihar and Tamil Nadu declare a SAP. We just don't have the number."""
    slugs = _slugs(kind="sap", has_rates=False)
    assert slugs, "fixture drift: no unsourced SAP state left to test"
    for slug in slugs:
        html = _page(client, slug)
        for where, text in (("title", _title(html)),
                            ("description", _desc(html)),
                            ("body", html)):
            assert not _DENIES_SAP.search(text), (
                f"/ganna/{slug} {where} claims the state has no SAP; it has one "
                f"we could not source")


def test_hub_does_not_file_unsourced_sap_states_under_no_sap(client):
    """The state pages were fixed for this and the hub still had it.

    The hub grouped states two ways — "has a SAP figure" and everything else —
    so बिहार and तमिलनाडु were listed under a heading reading "जहां SAP नहीं".
    Same false claim, different page. Whatever section an unsourced SAP state
    appears in must not be the one that denies SAPs exist there.
    """
    html = client.get("/ganna").text
    body = html.split('<div class="wrap">', 1)[1]
    deny_at = [m.start() for m in re.finditer(r"जहां SAP नहीं", body)]
    assert deny_at, "fixture drift: the FRP-only heading is gone"
    # Everything from that heading to the next <h2> is the "no SAP" section.
    start = deny_at[0]
    end = body.find("<h2", start + 1)
    section = body[start:end if end != -1 else len(body)]
    for slug in _slugs(kind="sap", has_rates=False):
        st = next(s for s in _states() if s["slug"] == slug)
        assert st["hi"] not in section, (
            f"hub lists {st['hi']} under 'जहां SAP नहीं'; that state declares a "
            f"SAP we simply could not source")


def test_hub_lists_every_state_somewhere(client):
    """Three groups now, so it is newly possible to drop one on the floor."""
    body = client.get("/ganna").text.split('<div class="wrap">', 1)[1]
    for st in _states():
        assert f'/ganna/{st["slug"]}' in body, f"{st['slug']} is unreachable from the hub"


def test_frp_only_state_does_say_there_is_no_sap(client):
    """The other side of the same split — Karnataka's page should be plain."""
    for slug in _slugs(kind="frp"):
        html = _page(client, slug)
        assert _DENIES_SAP.search(html), (
            f"/ganna/{slug} is FRP-only and should say so outright")


def test_unsourced_state_shows_no_invented_sap_figure(client):
    """No rupee figure on the page may be presented as that state's SAP."""
    for slug in _slugs(kind="sap", has_rates=False):
        html = _page(client, slug)
        body = html.split('<div class="wrap">', 1)[1]
        assert not re.search(r"SAP[^।<]{0,20}₹\s*[\d,]+", body), (
            f"/ganna/{slug} pairs 'SAP' with a rupee figure it cannot source")


def test_recovery_derived_rate_is_not_labelled_frp(client):
    """₹402 is what a mill at Maharashtra's recovery owes. The FRP is ₹365.

    Titling the derived number "FRP ₹402" is a small false claim that costs
    trust in every other figure on the page."""
    frp = _frp(_load().get("next_season") or _season_for(__import__("datetime").date.today()))
    for st in _states():
        if not st.get("recovery"):
            continue
        eff = _eff_frp(st["recovery"], frp)
        assert eff != frp["rate"], "fixture drift: recovery no longer moves the rate"
        title = _title(_page(client, st["slug"]))
        assert not re.search(rf"FRP\s*₹{eff}\b", title), (
            f"/ganna/{st['slug']} title calls the recovery-adjusted ₹{eff} the FRP")
        assert str(frp["rate"]) in title, (
            f"/ganna/{st['slug']} title drops the actual FRP ₹{frp['rate']}")


# ── indexation discipline ───────────────────────────────────────────────────

def test_states_without_a_verified_number_are_noindex(client):
    for slug in _slugs(indexed=False):
        assert "noindex" in _page(client, slug), f"/ganna/{slug} should be noindex"
    for slug in _slugs(indexed=True):
        html = _page(client, slug)
        m = re.search(r'name="robots" content="([^"]*)"', html)
        assert not (m and "noindex" in m.group(1)), f"/ganna/{slug} should be indexable"


def test_sitemap_carries_only_indexable_pages(client):
    xml = client.get("/ganna/sitemap.xml").text
    locs = re.findall(r"<loc>(.*?)</loc>", xml)
    listed = {u.rsplit("/", 1)[-1] for u in locs}
    for slug in _slugs(indexed=False):
        assert slug not in listed, f"{slug} is noindex but sits in the sitemap"
    for slug in _slugs(indexed=True):
        assert slug in listed, f"{slug} is indexable but missing from the sitemap"


# ── SERP budgets (the project-wide rule: title <=68, description <=162) ─────

def test_every_page_fits_the_serp_window(client):
    urls = ["/ganna"] + [f"/ganna/{s['slug']}" for s in _states()]
    for u in urls:
        html = client.get(u).text
        t, d = _title(html), _desc(html)
        assert len(t) <= 68, f"{u} title is {len(t)} chars: {t}"
        assert len(d) <= 162, f"{u} description is {len(d)} chars: {d}"


# ── schema parity (FAQ schema is generated from the visible markup) ─────────

def test_faq_schema_matches_visible_faqs(client):
    for u in ["/ganna"] + [f"/ganna/{s['slug']}" for s in _states()]:
        html = client.get(u).text
        # Accordions, not stacked cards — collapsed in the UI but still in the
        # HTML, which is what the schema has to agree with.
        visible = len(re.findall(r'<details class="gn-faq"', html))
        blocks = [json.loads(b) for b in re.findall(
            r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]
        faq = next((b for b in blocks if b.get("@type") == "FAQPage"), None)
        assert faq, f"{u} has no FAQPage schema"
        assert len(faq["mainEntity"]) == visible, (
            f"{u}: {len(faq['mainEntity'])} in schema vs {visible} shown")


# ── season arithmetic ───────────────────────────────────────────────────────

def test_season_rolls_over_on_1_october():
    from datetime import date
    assert _season_for(date(2026, 9, 30)) == "2025-26"
    assert _season_for(date(2026, 10, 1)) == "2026-27"
    assert _season_for(date(2027, 1, 15)) == "2026-27"


def test_frp_floor_applies_below_the_cut_off():
    frp = _frp("2026-27")
    assert _eff_frp(9.2, frp) == round(frp["floor_rate"])
    assert _eff_frp(frp["recovery"], frp) == frp["rate"]
    assert _eff_frp(11.29, frp) > frp["rate"]


def test_footer_does_not_promise_daily_agmarknet_updates(client):
    """The shared footer's standing line is true for /bhav and false here.

    "भाव … data.gov.in (Agmarknet) से रोज़ अपडेट होते हैं। बेचने से पहले अपनी मंडी
    में भाव ज़रूर पुष्टि करें।" claims a daily feed for a number that changes once
    a season, and sends a cane farmer to a mandi that never trades his crop.
    """
    for u in ["/ganna"] + [f"/ganna/{s['slug']}" for s in _states()]:
        foot = re.search(r'<div class="km-footer-note">(.*?)</div>',
                         client.get(u).text, re.S)
        assert foot, f"{u} lost its footer note"
        text = foot.group(1)
        assert "Agmarknet" not in text, f"{u} footer promises Agmarknet updates"
        assert "रोज़ अपडेट" not in text, f"{u} footer promises daily updates"


def test_bhav_footer_note_is_unchanged(client):
    """The override must not have altered the default for everyone else."""
    from backend.routes.bhav import _FOOTER_NOTE

    foot = re.search(r'<div class="km-footer-note">(.*?)</div>',
                     client.get("/bhav").text, re.S)
    assert foot and "Agmarknet" in foot.group(1)
    assert "Agmarknet" in _FOOTER_NOTE


def test_unknown_state_redirects_to_the_hub(client):
    r = client.get("/ganna/atlantis", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].endswith("/ganna")
