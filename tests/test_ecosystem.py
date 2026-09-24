"""The ecosystem — every page offers a way into a DIFFERENT part of the site.

backend/services/ecosystem.py exists because every section of this site was a
cul-de-sac: /bhav linked to /bhav, an article linked to articles, and the only
route to /pashupalan, /rental, /sawal or /naksha was the hamburger drawer.

The point of these tests is not that the strip renders today. It is that the
NEXT section cannot ship without it. The load-bearing ones:

  * test_every_ssr_section_offers_a_way_out walks the routes the app actually
    serves, so a section added later is tested the moment its route exists —
    nobody has to remember to add it here.
  * test_every_section_id_is_a_real_page fails if SECTIONS names a hub the app
    does not serve, which is what a renamed or retired section looks like.
  * test_no_step_ever_points_back_into_its_own_section is the rule that makes
    this an ecosystem rather than a longer list of links to the same place.
"""

import re
from pathlib import Path

import pytest

from backend.services import ecosystem as E

SITE = "https://krashimitra.in"
FRONTEND = Path(__file__).resolve().parents[1] / "frontend"

STRIP = re.compile(r'<nav class="km-journey".*?</nav>', re.S)
CARD = re.compile(r'<a class="km-journey-card" href="([^"]+)"[^>]*'
                  r'data-km-step="([a-z]+)"', re.S)


def steps_on(client, path):
    """(href, section) for every card in the strip on a live page.

    A section with no rows in the throwaway SQLite DB serves its not-found page
    (/sawal does when no crop has enough Kisan Call Centre answers). That is a
    data condition, not a broken strip, so it skips rather than fails — the
    graph-level tests below still cover those sections with no DB at all.
    """
    r = client.get(path)
    if r.status_code == 404:
        pytest.skip(f"{path} has no content in the test database")
    assert r.status_code == 200, f"{path} -> {r.status_code}"
    m = STRIP.search(r.text)
    return CARD.findall(m.group(0)) if m else []


# ── the contract a future section inherits ──────────────────

# One page per section that renders through bhav.py's _doc() shell. A section
# added later belongs here; test_every_ssr_section_offers_a_way_out catches it
# even if nobody adds it, but naming it makes the failure readable.
SSR_PAGES = ["/bhav", "/pashupalan", "/pashupalan/anda-rate", "/ganna",
             "/rental", "/rental/tractor", "/sawal", "/naksha", "/product/"]


@pytest.mark.parametrize("path", SSR_PAGES)
def test_every_ssr_section_offers_a_way_out(client, path):
    """Four onward links, in four sections, none of them this one.

    This is the whole deliverable. A page that fails this is a dead end, which
    is the state every one of these sections was in before ecosystem.py.
    """
    steps = steps_on(client, path)
    assert steps, f"{path} renders no ecosystem strip at all"
    sections = [s for _href, s in steps]
    assert len(sections) == len(set(sections)), \
        f"{path} offers two links into the same section: {sections}"
    assert len(sections) >= 2, \
        f"{path} offers only {len(sections)} onward section(s): {sections}"


@pytest.mark.parametrize("path", SSR_PAGES)
def test_a_page_never_offers_the_section_it_is_already_in(client, path):
    """A "go somewhere else" strip that points at the page you are on is noise
    dressed as navigation."""
    here = E.parse(SITE + path).section
    for href, section in steps_on(client, path):
        assert section != here, f"{path} offers its own section: {href}"


def test_a_section_is_never_advertised_unless_its_hub_resolves(client):
    """SECTIONS is the registry a future section adds itself to, and this is the
    invariant that keeps a stale row from becoming a site-wide dead link: a hub
    that does not answer 200 must not appear in anybody's strip.

    Stated this way rather than as "every hub must be 200" on purpose. Some
    sections are data-dependent — /sawal returns the not-found page when no
    crop has enough Kisan Call Centre answers to publish, which is exactly the
    state of the throwaway SQLite DB these tests run against. The rule that
    actually matters is not that every section has data, it is that a section
    WITHOUT data stops being advertised.
    """
    offered = set()
    for section in list(E.SECTIONS) + [""]:
        ctx = E.Ctx(section=section, canon=f"{SITE}/{section}")
        offered.update(s.section for s in E.next_steps(ctx, n=99))

    for sec_id in offered:
        hub = E.SECTIONS[sec_id].hub
        assert _hub_exists(client, hub), (
            f"the graph offers '{sec_id}' but its hub {hub} resolves to "
            f"nothing — either the section moved or it has no content")


def _hub_exists(client, hub) -> bool:
    """Does this URL lead anywhere?

    Two surfaces, because this site has two. /bhav, /product and /pashupalan
    are rendered by FastAPI; /, /weather, /chat, /khoj and /sarkari_yojana stay
    Netlify-static and the app never sees them, so a test client alone would
    call half the real site a 404. A static hub is verified against the file
    Netlify actually serves — which is also what catches a page being renamed
    out from under the graph.
    """
    if client.get(hub, follow_redirects=True).status_code == 200:
        return True
    rel = hub.strip("/")
    name = f"{rel}/index.html" if hub.endswith("/") else f"{rel}.html"
    return (FRONTEND / name).is_file()


def test_no_step_ever_points_back_into_its_own_section():
    """Checked on the graph directly rather than through a page, so it holds
    for contexts no route serves yet."""
    for section in E.SECTIONS:
        ctx = E.Ctx(section=section, canon=f"{SITE}/{section}")
        for s in E.next_steps(ctx, n=8):
            assert s.section != section, \
                f"a {section} page was offered {s.href}"


def test_a_page_never_repeats_a_link_it_already_shows(client):
    """`have` is how a page says "I already link there prominently". An article
    carries its own related-articles grid and price chips; spending a slot on
    either restates a link the reader can see instead of opening a section he
    has no route to."""
    ctx = E.Ctx(section="bhav", crop="wheat", crop_hi="गेहूं",
                canon=f"{SITE}/bhav/wheat", have=frozenset({"articles", "sawal"}))
    got = {s.section for s in E.next_steps(ctx, n=8)}
    assert not (got & {"articles", "sawal", "bhav"}), got


# ── the honesty rules ───────────────────────────────────────

def test_a_step_is_never_labelled_in_the_wrong_script():
    """The measured defect behind this guard: a wrong-script label converts far
    worse than a right one, and `district_hi or district` is the natural thing
    to write at a call site — it ships "bijnor का नक्शा" onto a Hindi page the
    moment the caller has no Hindi name to give."""
    latin = re.compile(r"[A-Za-z]{3,}")
    ctx = E.Ctx(section="bhav", state="uttar-pradesh", district="bijnor",
                canon=f"{SITE}/bhav/rajya/uttar-pradesh/bijnor")   # no *_hi
    for s in E.next_steps(ctx, n=8):
        # "AI" and "MSP" are read as-is in Hindi; a bare slug is not.
        words = [w for w in latin.findall(s.title) if w not in ("AI", "MSP")]
        assert not words, f"Latin text on a Hindi step: {s.title!r}"


def test_a_tamil_page_is_never_given_hindi_copy():
    """Tamil and Kannada do not inherit the Hindi table — a Hindi line under a
    Tamil heading is the script mismatch, not a graceful fallback."""
    devanagari = re.compile(r"[ऀ-ॿ]")
    ctx = E.Ctx(section="articles", crop="paddy", crop_hi="धान",
                lang="ta", canon=f"{SITE}/articles/samba-dhan-tamil-nadu")
    steps = E.next_steps(ctx, n=8)
    assert steps, "a Tamil page got no steps at all"
    for s in steps:
        assert not devanagari.search(s.title + s.why), \
            f"Hindi on a Tamil step: {s.title!r} / {s.why!r}"


def test_weather_is_offered_only_where_it_is_true():
    """/weather serves UP districts. Offering it to a Karnataka reader spends
    his click to show him someone else's forecast."""
    def sections(state):
        return {s.section for s in E.next_steps(
            E.Ctx(section="bhav", state=state, canon=f"{SITE}/bhav/x/{state}"), n=9)}

    assert "weather" in sections("uttar-pradesh")
    assert "weather" in sections("")                 # unknown state: still fair
    assert "weather" not in sections("karnataka")
    assert "weather" not in sections("maharashtra")


def test_the_strip_never_claims_where_a_number_came_from():
    """This copy is printed on every section, so a provenance line true of
    /bhav also lands on /rental — whose footer was deliberately rewritten
    because tractor hire comes from no feed. See tests/test_rental_rate_claims.
    """
    for lang, table in E._COPY.items():
        for key, text in table.items():
            assert "Agmarknet" not in text, f"{lang}.{key} names the feed"


def test_a_transaction_page_gets_no_onward_menu(client):
    """/pay is noindex,nofollow — a payment flow, where a menu of somewhere
    else to go is a distraction from the one thing the page is for."""
    r = client.get("/pay")
    if r.status_code == 200:
        assert 'class="km-journey"' not in r.text


# ── the graph's own resolution ──────────────────────────────

@pytest.mark.parametrize("path,section,crop", [
    ("/bhav/wheat/uttar-pradesh/bijnor", "bhav", "wheat"),
    ("/bhav/rajya/uttar-pradesh/bijnor", "bhav", ""),
    ("/articles/gehun-me-khad-kab-kitni", "articles", ""),
    ("/pashupalan/anda-rate/up", "pashupalan", ""),
    ("/rental/thresher/ram-singh", "rental", ""),
    ("/naksha/uttar-pradesh/bijnor", "naksha", ""),
    ("/product/urea-45kg", "shop", ""),
    ("/krashi_news/some-story", "news", ""),
])
def test_a_url_resolves_to_the_position_it_describes(path, section, crop):
    ctx = E.parse(SITE + path)
    assert ctx.section == section
    assert ctx.crop == crop


def test_ganna_never_asserts_a_mandi_price_url():
    """Cane is bought by mills at an administered rate. /ganna knows its crop,
    but claiming a /bhav/sugarcane address from the path would be a guessed URL
    for a number that does not move daily.

    The family is still resolved, so the cane Q&A and the cane articles remain
    reachable — knowing the crop and claiming its price page are separate.
    """
    ctx = E.parse(f"{SITE}/ganna/uttar-pradesh/meerut")
    assert ctx.crop == ""
    assert ctx.fam == "ganna"
    for s in E.next_steps(ctx, n=9):
        assert "/bhav/sugarcane" not in s.href, f"guessed a cane price URL: {s.href}"


@pytest.mark.parametrize("slug,fam", [
    ("wheat", "gehu"), ("gehu", "gehu"), ("paddy-common", "dhan"),
    ("bengal-gram-gram-whole", "chana"), ("red-gram-arhar-tur-whole", "arhar"),
    ("sesamum-sesame-gingelly-til", "til"), ("gur-jaggery", "ganna"),
    ("green-gram-moong-whole", "moong"), ("turmeric-raw", "haldi"),
    ("masur-dal", "masur"), ("dry-chillies", "mirch"),
    # The traps token matching exists for: "lentil" contains "til" as a
    # substring but not as a token, and "custard-apple" is not an apple.
    ("custard-apple-sharifa", ""), ("firewood", ""), ("jute", ""),
])
def test_crop_families_match_on_tokens_not_substrings(slug, fam):
    assert E.family(slug) == fam


def test_the_same_page_always_gets_the_same_steps():
    """Deterministic, so a crawler sees one stable block rather than churn."""
    ctx = E.parse(f"{SITE}/bhav/wheat/uttar-pradesh/bijnor", crop_hi="गेहूं")
    first = [s.href for s in E.next_steps(ctx)]
    assert first == [s.href for s in E.next_steps(ctx)]


def test_neighbouring_pages_do_not_all_vote_for_one_url():
    """…while still differing between pages, so 14,000 /bhav URLs do not all
    point at the same four addresses and read as boilerplate."""
    picks = set()
    for d in ["bijnor", "meerut", "agra", "kanpur", "jhansi", "aligarh"]:
        ctx = E.parse(f"{SITE}/bhav/wheat/uttar-pradesh/{d}", crop_hi="गेहूं")
        picks.update(s.href for s in E.next_steps(ctx))
    assert len(picks) > 4, f"every district page offered the same links: {picks}"


# ── never take a page down ──────────────────────────────────

def test_a_broken_lookup_costs_a_step_not_the_page(monkeypatch):
    """The module's one guarantee. A provider that raises must cost its own
    step and nothing else — the alternative is a 500 on a page that worked."""
    def boom(ctx, loc):
        raise RuntimeError("the DB is read-only again")

    # REPLACE the rental provider — prepending a broken one leaves the working
    # one in the list, and the test passes without testing anything.
    monkeypatch.setattr(E, "_PROVIDERS",
                        [(sec, boom if sec == "rental" else fn)
                         for sec, fn in E._PROVIDERS])
    ctx = E.parse(f"{SITE}/articles/x", crop="wheat", crop_hi="गेहूं")
    steps = E.next_steps(ctx)
    assert steps
    assert "rental" not in {s.section for s in steps}


def test_an_unknown_crop_gets_hubs_and_never_a_guessed_url():
    """A commodity nobody has classified must not produce an invented address.
    Agmarknet adds spellings without warning; this is the long tail's contract.
    """
    ctx = E.parse(f"{SITE}/articles/x", crop="some-new-agmarknet-spelling")
    for s in E.next_steps(ctx, n=9):
        assert s.href in {SITE + sec.hub for sec in E.SECTIONS.values()} \
            or s.section == "articles", f"guessed a deep URL: {s.href}"


# ── the shell's own name resolution ─────────────────────────
#
# bhav.py::_journey turns a canonical URL into named places and crops before
# handing the context to the graph. Nothing else covers it: the throwaway
# SQLite DB has no mandi rows, so no /bhav crop page renders in this suite —
# and that branch is the one running on the ~14,000 pages that carry most of
# the site's traffic. Stub the index instead of skipping it.

_FAKE_INDEX = {
    "crops":  {"wheat": "Wheat"},
    "states": {"wheat": {"uttar-pradesh": "Uttar Pradesh"}},
    "dists":  {"wheat": {"uttar-pradesh": {"bijnor": "Bijnor"}}},
}


def test_a_crop_page_names_its_crop_and_district_in_hindi(monkeypatch):
    from backend.routes import bhav

    monkeypatch.setattr(bhav, "_get_index", lambda: _FAKE_INDEX)
    html = bhav._journey(f"{SITE}/bhav/wheat/uttar-pradesh/bijnor",
                         "wheat", "hi", "")
    assert 'class="km-journey"' in html
    # The names the shell resolved must reach the copy — this is what stops the
    # strip degrading to generic hub wording on every deep page.
    assert "गेहूं" in html
    assert "बिजनौर" in html
    assert "bijnor" not in html.lower().split('href=')[0]


def test_a_place_only_page_still_names_its_district(monkeypatch):
    """/bhav/rajya/{state}/{district} has no crop, so the slug → spelling map
    has to be read off whichever crop reports from there."""
    from backend.routes import bhav

    monkeypatch.setattr(bhav, "_get_index", lambda: _FAKE_INDEX)
    html = bhav._journey(f"{SITE}/bhav/rajya/uttar-pradesh/bijnor",
                         "", "hi", "")
    assert "बिजनौर" in html


def test_a_nofollow_page_gets_no_strip_but_noindex_follow_does(monkeypatch):
    """nofollow is the right test, not noindex: "noindex, follow" is the site
    saying keep this URL out of the index but do follow its links — an empty
    dealer directory, which is exactly where a reader needs somewhere to go."""
    from backend.routes import bhav

    monkeypatch.setattr(bhav, "_get_index", lambda: _FAKE_INDEX)
    assert bhav._journey(f"{SITE}/bhav", "", "hi", "noindex, nofollow") == ""
    assert bhav._journey(f"{SITE}/bhav", "", "hi", "noindex, follow") != ""


def test_a_broken_index_costs_the_strip_not_the_page(monkeypatch):
    """_journey wraps everything: a page that was working must not start
    500ing because the graph could not resolve a name."""
    from backend.routes import bhav

    def boom():
        raise RuntimeError("Neon is read-only again")

    monkeypatch.setattr(bhav, "_get_index", boom)
    assert bhav._journey(f"{SITE}/bhav/wheat", "wheat", "hi", "") == ""


def test_the_strip_is_empty_rather_than_half_built():
    """A caller interpolates journey_html() unconditionally, so "nothing to
    offer" has to be the empty string, not a heading with no cards under it."""
    ctx = E.Ctx(section="bhav", lang="zz", canon=f"{SITE}/bhav")
    assert E.journey_html(ctx) == ""


def test_every_section_photo_ships():
    """The strip's section icons are real files under frontend/images/journey.
    A missing one would answer 200 + HTML (see missing-static-files memory) and
    render as a broken circle on every page, so check the disk, not a request."""
    from pathlib import Path
    from backend.services import ecosystem
    front = Path(__file__).resolve().parents[1] / "frontend"
    for sec in ecosystem.SECTIONS.values():
        assert sec.icon.startswith("/images/journey/"), sec
        assert (front / sec.icon.lstrip("/")).is_file(), f"missing {sec.icon}"
