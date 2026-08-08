"""The sugar-mill register: parsing traps, and never overstating what it covers.

Two bugs this pins, both found against the live mahasugar.in markup:

1. The page carries commented-out <tr> rows. Parsed naively, Solapur came out
   with 68 mills instead of 50 — eighteen of them invisible on the real page,
   published as if they were current.

2. The register is CO-OPERATIVE ONLY (every table is headed "सहकारी साखर
   कारखान्याचे नाव व पत्ता"). Maharashtra has roughly as many purely private
   mills. A district page that presents this as "the mills near you" is wrong
   by omission, and the farmer it misleads is the one whose mill is missing.
"""

import re

import pytest

from backend.services import ganna_mill_service as svc

STATE = "maharashtra"


@pytest.fixture(scope="module")
def register():
    data = svc.load()
    if not data:
        pytest.skip("no mill register cached — run svc.refresh() to seed it")
    return data


# ── parsing ─────────────────────────────────────────────────────────────────

def test_commented_out_rows_are_not_parsed():
    """A row inside an HTML comment is not on the page and must not be in the
    directory. This is the Solapur bug, reduced to a fixture."""
    page = """
    <h3>सोलापूर जिल्हा :-</h3>
    <table>
      <tr><td>1</td><td>खरी सहकारी साखर कारखाना लि., सोलापूर</td><td></td><td>5,000</td></tr>
      <!-- <tr><td>2</td><td>भुताटकी सहकारी साखर कारखाना लि., सोलापूर</td><td></td><td>9,999</td></tr> -->
      <tr><td>3</td><td>दुसरी सहकारी साखर कारखाना लि., सोलापूर</td><td></td><td>2,500</td></tr>
    </table>"""
    got, _ = svc.parse(page)
    names = [m["name"] for m in got]
    assert len(got) == 2, f"expected 2 visible rows, got {len(got)}: {names}"
    assert not any("भुताटकी" in n for n in names), "a commented-out mill was published"


def test_unknown_district_heading_is_rejected_not_guessed():
    page = """<h3>अटलांटिस जिल्हा :-</h3>
    <table><tr><td>1</td><td>कुठलीतरी सहकारी साखर कारखाना लि.</td><td></td><td>5,000</td></tr></table>"""
    got, rejects = svc.parse(page)
    assert got == []
    assert any("unknown district" in r for r in rejects)


def test_capacity_is_a_number_or_zero_never_garbage(register):
    for m in register["mills"]:
        assert isinstance(m["tcd"], int) and m["tcd"] >= 0, m
        assert m["tcd"] < 100_000, f"implausible capacity: {m}"


def test_every_mill_has_a_name_and_a_known_district(register):
    slugs = set(svc._DISTRICTS.values())
    for m in register["mills"]:
        assert len(m["name"]) >= 8, f"implausible name: {m}"
        assert m["district_slug"] in slugs, f"unmapped district: {m}"


def test_mill_slugs_are_unique(register):
    slugs = [m["slug"] for m in register["mills"]]
    assert len(slugs) == len(set(slugs)), "duplicate mill slugs would collide as URLs"


def test_by_district_is_sorted_biggest_first(register):
    for d, ms in svc.by_district(STATE).items():
        caps = [m["tcd"] for m in ms]
        assert caps == sorted(caps, reverse=True), f"{d} is not ordered by capacity"


# ── honesty about coverage ──────────────────────────────────────────────────

def test_register_declares_its_cooperative_scope(register):
    assert register.get("scope") == "cooperative"


def test_district_pages_say_the_list_is_cooperatives_only(client, register):
    """Every page built on this register has to carry the caveat."""
    for d_slug, ms in list(svc.by_district(STATE).items())[:6]:
        html = client.get(f"/ganna/{STATE}/{d_slug}").text
        assert "सहकारी" in html, f"/ganna/{STATE}/{d_slug} does not say co-operative"
        assert "निजी" in html, (
            f"/ganna/{STATE}/{d_slug} never mentions that private mills are excluded")


def test_state_page_does_not_claim_the_register_is_every_mill(client, register):
    html = client.get(f"/ganna/{STATE}").text
    body = html.split('<div class="wrap">', 1)[1]
    assert "जिलेवार चीनी मिलें" in body
    assert "निजी" in body, "state page presents the co-op register as the whole picture"


# ── routing ─────────────────────────────────────────────────────────────────

def test_district_without_a_register_redirects(client):
    r = client.get("/ganna/uttar-pradesh/meerut", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].endswith("/ganna/uttar-pradesh")


def test_unknown_district_redirects_to_the_state(client):
    r = client.get(f"/ganna/{STATE}/atlantis", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].endswith(f"/ganna/{STATE}")


def test_single_mill_districts_are_noindex(client, register):
    for d_slug, ms in svc.by_district(STATE).items():
        html = client.get(f"/ganna/{STATE}/{d_slug}").text
        m = re.search(r'name="robots" content="([^"]*)"', html)
        noindex = bool(m and "noindex" in m.group(1))
        assert noindex == (len(ms) < 2), (
            f"{d_slug} has {len(ms)} mills but noindex={noindex}")


def test_sitemap_lists_district_pages_but_not_the_noindex_ones(client, register):
    locs = re.findall(r"<loc>(.*?)</loc>", client.get("/ganna/sitemap.xml").text)
    listed = {l.rsplit("/", 1)[-1] for l in locs if f"/ganna/{STATE}/" in l}
    for d_slug, ms in svc.by_district(STATE).items():
        assert (d_slug in listed) == (len(ms) >= 2), f"{d_slug} sitemap membership is wrong"


def test_district_page_shows_every_mill_it_counts(client, register):
    for d_slug, ms in list(svc.by_district(STATE).items())[:5]:
        html = client.get(f"/ganna/{STATE}/{d_slug}").text
        shown = len(re.findall(r'class="gn-bar-name"', html))
        assert shown == len(ms), f"{d_slug}: counted {len(ms)} but rendered {shown}"


def test_district_pages_fit_the_serp_window(client, register):
    for d_slug in list(svc.by_district(STATE))[:8]:
        html = client.get(f"/ganna/{STATE}/{d_slug}").text
        t = re.search(r"<title>(.*?)</title>", html, re.S).group(1)
        d = re.search(r'name="description" content="([^"]*)"', html).group(1)
        assert len(t) <= 68, f"{d_slug} title {len(t)}: {t}"
        assert len(d) <= 162, f"{d_slug} desc {len(d)}: {d}"


# ── refresh safety ──────────────────────────────────────────────────────────

def test_refresh_refuses_to_overwrite_cache_with_a_collapsed_parse(monkeypatch):
    """If the source markup moves, half a directory is worse than yesterday's
    whole one — the fetch must raise rather than write."""
    class _Resp:
        text = "<h3>कोल्हापूर जिल्हा :-</h3><table></table>"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(svc.requests, "get", lambda *a, **k: _Resp())
    with pytest.raises(ValueError, match="refusing to overwrite"):
        svc.refresh(force=True)
