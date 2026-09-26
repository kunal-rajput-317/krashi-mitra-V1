"""/bigha-calculator — the land-unit converter.

A wrong factor here is a wrong land deal, so the arithmetic is pinned against
figures anyone can check by hand, and the page is pinned to say that a state's
बीघा is अनुमानित and that we are a private website.
"""

import json
import re

import pytest

from backend.routes import zameen


def test_exact_units_are_exact():
    assert zameen.convert(1, "hectare", "acre") == pytest.approx(2.4710538, rel=1e-7)
    assert zameen.convert(1, "acre", "sqft") == pytest.approx(43560, rel=1e-9)
    assert zameen.convert(1, "acre", "guntha") == pytest.approx(40)
    assert zameen.convert(1, "acre", "kanal") == pytest.approx(8)
    assert zameen.convert(1, "kanal", "marla") == pytest.approx(20)
    assert zameen.convert(1, "acre", "decimal") == pytest.approx(100)


def test_up_pakka_bigha_matches_the_naksha_measure():
    """naksha.py's field-measure HUD uses 1 acre = 1.6 बीघा. The two tools on
    one site must not disagree about the same field."""
    assert zameen.convert(1, "acre", "bigha", "up") == pytest.approx(1.6)
    assert zameen.convert(1, "bigha", "biswa", "up") == pytest.approx(20)


def test_state_subunits():
    assert zameen.convert(1, "bigha", "kattha", "bihar") == pytest.approx(20)
    assert zameen.convert(1, "bigha", "kattha", "west-bengal") == pytest.approx(20)
    assert zameen.convert(1, "kattha", "sqft", "west-bengal") == pytest.approx(720)
    assert zameen.convert(1, "bigha", "katha", "assam") == pytest.approx(5)


def test_every_state_unit_is_positive_and_known():
    for key, s in zameen.STATES.items():
        for k, _hi, _en, sqft in s["local"]:
            assert sqft > 0, (key, k)
        for k in s["extra"]:
            assert k in zameen.UNITS, (key, k)


def test_page_renders_with_disclaimer(client):
    r = client.get("/bigha-calculator")
    assert r.status_code == 200
    html = r.text
    assert 'rel="canonical" href="https://krashimitra.in/bigha-calculator"' in html
    assert "अनुमानित" in html
    assert "निजी वेबसाइट" in html
    assert "पटवारी" in html
    # No "official" framing on a page about land records.
    assert "सरकारी नाप है।" not in html
    title = re.search(r"<title>(.*?)</title>", html).group(1)
    assert len(title) <= 68


def test_embedded_data_matches_the_table():
    data = json.loads(zameen._data_json().replace(r"<\/", "</"))
    assert data["up:bigha"]["sqm"] == pytest.approx(zameen.to_sqm(1, "bigha", "up"))
    assert data["up:bigha"]["est"] is True
    assert data["acre"]["est"] is False
    # Both pickers offer every unit, and the default pair renders server-side.
    html = zameen._options(zameen.DEFAULT_FROM)
    assert 'value="up:bigha" selected' in html
    assert html.count("<option") == len(data)


def test_first_paint_shows_the_answer(client):
    """1 बीघा (UP) → एकड़ is on the screen before any script runs."""
    html = client.get("/bigha-calculator").text
    assert '<div class="zm-num" id="zm-b" aria-live="polite">0.625</div>' in html


def test_listed_in_sitemap_llms_and_both_drawers(repo_root):
    from backend.routes import sitemap
    assert any(p == "/bigha-calculator" for p, *_ in sitemap.HUBS)
    llms = (repo_root / "backend" / "routes" / "llms.py").read_text(encoding="utf-8")
    assert '"/bigha-calculator"' in llms
    js = (repo_root / "frontend" / "drawer-menu.js").read_text(encoding="utf-8")
    py = (repo_root / "backend" / "routes" / "bhav.py").read_text(encoding="utf-8")
    assert "'/bigha-calculator'" in js and "🧮" in js
    assert "/bigha-calculator" in py and "🧮" in py
