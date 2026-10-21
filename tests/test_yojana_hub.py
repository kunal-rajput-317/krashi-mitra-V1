# -*- coding: utf-8 -*-
"""The /sarkari_yojana hub is generated from the scheme articles.

tools/yojana_hub.py writes the cards, state filters, FAQ and JSON-LD between
<!-- yojana-hub:NAME --> markers. Until Oct 2026 those were hand-written and
promised eligibility, pushed loans and a savings product behind "अभी आवेदन
करें", and called a closed 2017 loan waiver "चालू" (LEGAL_RULES §1, §3).
These tests keep the page equal to what the generator writes, so a hand edit
or a forgotten rebuild fails CI instead of shipping.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import yojana_hub  # noqa: E402

HUB = ROOT / "frontend" / "sarkari_yojana.html"


def _doc() -> str:
    return HUB.read_text(encoding="utf-8")


def test_every_scheme_article_names_a_state():
    # entries() raises, naming the file, when a scheme article has no state.
    assert yojana_hub.entries()


def test_hub_matches_what_the_generator_writes():
    doc = _doc()
    assert yojana_hub.render(doc) == doc, (
        "frontend/sarkari_yojana.html is out of date with tools/articles — "
        "run: python tools/yojana_hub.py")


def test_every_card_links_to_a_real_guide():
    files = {p.stem.lower() for p in (ROOT / "frontend" / "articles").glob("*.html")}
    hrefs = re.findall(r'<a class="btn-apply" href="/articles/([^"]+)"', _doc())
    assert len(hrefs) == len(yojana_hub.entries())
    missing = [h for h in hrefs if h not in files]
    assert not missing, f"hub cards link to guides that do not exist: {missing}"


def test_hub_makes_no_promise_of_its_own():
    """No eligibility, apply button, loan or savings pitch on the hub (§1, §3)."""
    doc = _doc()
    for phrase in ("अभी आवेदन करें", "चालू है", "पात्रता जांचें", "badge badge-hot",
                   "ऋण मोचन", "किसान विकास पत्र", 'detail-label">पात्रता',
                   # two hand-made "ads" with dead buttons: a KCC loan pitch
                   # and "सोलर पंप — 90% सब्सिडी"
                   "KCC या किसान लोन", 'id="ad-sticky-bottom"'):
        assert phrase not in doc, f"/sarkari_yojana carries '{phrase}' again"


def test_faq_schema_matches_the_visible_faq():
    doc = _doc()
    ld = re.search(r"<!-- yojana-hub:faq-ld -->\n<script[^>]*>(.*?)</script>", doc, re.S)
    questions = [q["name"] for q in json.loads(ld.group(1))["mainEntity"]]
    visible = re.findall(r"<summary[^>]*>\s*<span[^>]*>❓</span>\s*(.*?)\s*</summary>", doc, re.S)
    assert questions == [re.sub(r"<[^>]+>", "", v) for v in visible]
