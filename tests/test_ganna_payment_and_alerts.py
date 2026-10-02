"""/ganna round of 2026-09-30: payment page, calculators, the SAP alert, and the
honesty rules that come with them.

What this pins:
  * the hub's title leads with the romanised query its impressions come from,
    and never prints an old season's SAP under the new season's label;
  * every calculator result is labelled अनुमानित (LEGAL_RULES §3);
  * every /ganna page says it is a private website (LEGAL_RULES §1);
  * /ganna/bhugtan is a real page, not swallowed by the /ganna/{state} wildcard;
  * the SAP alert rings once per season, only after the new rate is recorded,
    and the mandi alert pass never touches those rows;
  * /bhav/sugarcane hands its 404 to /ganna.
"""
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.routes import ganna
from backend.services import ganna_alerts

ROOT = Path(__file__).resolve().parents[1]


# Pages are fetched through conftest's `client` fixture — the real app, so the
# shared shell's own lookups (sponsor slot, journey strip) run against the test DB.


def _title(html):
    return re.search(r"<title>(.*?)</title>", html, re.S).group(1)


def test_hub_title_leads_with_the_romanised_query(client):
    t = _title(client.get("/ganna").text)
    assert t.startswith("Ganne Ka Rate")
    assert len(t) <= 68
    assert "कृषि मित्र" not in t


def test_hub_title_never_carries_a_sap_figure(client):
    # The SAP on file can belong to the season before the one in the title.
    t = _title(client.get("/ganna").text)
    for st in ganna._states():
        for r in st.get("rates", []):
            assert f"₹{r['rate']}" not in t or r["rate"] == ganna.current_season()[1].get("rate")


def test_hub_says_whose_season_the_sap_bars_are(client):
    season, _ = ganna.current_season()
    html = client.get("/ganna").text
    old = {s.get("season") for s in ganna._states()
           if s.get("rates") and s.get("season") and s.get("season") != season}
    for o in old:
        assert f"{o} सीजन की आखिरी सरकारी घोषणा" in html


@pytest.mark.parametrize("url", ["/ganna", "/ganna/bhugtan", "/ganna/uttar-pradesh",
                                 "/ganna/maharashtra", "/ganna/bihar", "/ganna/karnataka"])
def test_every_page_says_it_is_a_private_website(client, url):
    html = client.get(url).text
    assert "कृषि मित्र एक निजी" in html


@pytest.mark.parametrize("url", ["/ganna", "/ganna/uttar-pradesh", "/ganna/maharashtra",
                                 "/ganna/karnataka"])
def test_calculator_is_always_labelled_estimated(client, url):
    html = client.get(url).text
    assert 'class="gn-panel gn-calc"' in html
    box = html.split('class="gn-panel gn-calc"', 1)[1].split("</div>\n</div>", 1)[0]
    assert "अनुमानित" in box


def test_frp_calculator_carries_the_same_formula_as_the_server(client):
    _, frp = ganna.current_season()
    html = client.get("/ganna").text
    assert f'data-base="{frp["rate"]:g}"' in html
    assert f'data-step="{frp["step"]:g}"' in html
    assert f'data-floor="{frp["floor_rate"]:g}"' in html


def test_sap_state_calculator_offers_its_own_declared_rates(client):
    st = ganna._state("uttar-pradesh")
    html = client.get("/ganna/uttar-pradesh").text
    for r in st["rates"]:
        assert f'<option value="{r["rate"]:g}">' in html


def test_bhugtan_is_its_own_page_and_in_the_sitemap(client):
    r = client.get("/ganna/bhugtan", follow_redirects=False)
    assert r.status_code == 200
    assert "14 दिन" in r.text and "15% सालाना" in r.text
    assert 'class="gn-panel gn-int"' in r.text
    assert "https://krashimitra.in/ganna/bhugtan" in client.get("/ganna/sitemap.xml").text


def test_bhugtan_names_no_mill_as_owing_money(client):
    html = client.get("/ganna/bhugtan").text
    assert "किसी मिल ने कितना भुगतान किया, यह हम नहीं बताते" in html
    assert "बकाया रखा" not in html and "डिफॉल्टर" not in html


def test_bell_only_where_the_sap_is_still_awaited(client):
    season, _ = ganna.current_season()
    for st in ganna._states():
        html = client.get(f"/ganna/{st['slug']}").text
        has_bell = f'data-c="{ganna_alerts.COMMODITY}"' in html
        assert has_bell == ganna.sap_awaited(st, season), st["slug"]


def _alert(state, last=None):
    return SimpleNamespace(id=1, state=state, last_price=last)


def test_alert_rings_only_once_the_new_season_is_recorded():
    old = {"slug": "uttar-pradesh", "kind": "sap", "season": "2025-26",
           "rates": [{"hi": "अगेती प्रजाति", "rate": 400}]}
    new = dict(old, season="2026-27")
    a = _alert("uttar-pradesh")
    assert list(ganna_alerts.due([a], {"uttar-pradesh": old}, "2026-27")) == []
    assert list(ganna_alerts.due([a], {"uttar-pradesh": new}, "2026-27")) == [(a, new)]


def test_alert_rings_at_most_once_per_season():
    st = {"slug": "punjab", "kind": "sap", "season": "2026-27", "rates": [{"hi": "x", "rate": 1}]}
    assert list(ganna_alerts.due([_alert("punjab", "2026-27")], {"punjab": st}, "2026-27")) == []


def test_alert_never_rings_for_a_state_without_a_recorded_rate():
    st = {"slug": "bihar", "kind": "sap", "season": "2026-27", "rates": []}
    assert list(ganna_alerts.due([_alert("bihar")], {"bihar": st}, "2026-27")) == []
    assert list(ganna_alerts.due([_alert("nowhere")], {}, "2026-27")) == []


def test_alert_payload_carries_the_stop_button_and_the_state_page(monkeypatch):
    from backend.services import alert_stop
    monkeypatch.setattr(alert_stop, "token", lambda ids: "tok")
    st = {"slug": "uttar-pradesh", "hi": "उत्तर प्रदेश",
          "rates": [{"hi": "अगेती प्रजाति", "rate": 410}]}
    p = ganna_alerts._payload(st, "2026-27", [7])
    assert p["stop"] == "tok"
    assert p["url"].endswith("/ganna/uttar-pradesh")
    assert "₹410" in p["body"]


def test_mandi_alert_pass_skips_sap_rows():
    src = (ROOT / "backend/services/push_service.py").read_text(encoding="utf-8")
    assert "MandiAlert.commodity != GANNA_SAP" in src


def test_bhav_sugarcane_404_goes_to_ganna():
    lines = (ROOT / "frontend/_redirects").read_text(encoding="utf-8").splitlines()
    rules = [l.split() for l in lines if l.strip() and not l.lstrip().startswith("#")]
    idx = next(i for i, r in enumerate(rules) if r[0] == "/bhav/sugarcane")
    assert rules[idx][1:] == ["/ganna", "301"]          # unforced: a 404 rescue
    assert idx < next(i for i, r in enumerate(rules) if r[0] == "/bhav/*")


def test_ganna_guide_up_no_longer_prints_the_wrong_up_sap():
    html = (ROOT / "frontend/articles/ganna-guide-up.html").read_text(encoding="utf-8")
    assert "₹370/क्विंटल" not in html and "₹ 370" not in html
    assert "₹400/क्विंटल" in html
