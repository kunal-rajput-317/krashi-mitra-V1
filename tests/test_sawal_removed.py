"""/sawal was removed on 2026-09-28 (LEGAL_RULES §2).

It republished Kisan Call Centre answers verbatim: doses on every crop page and
pesticides banned in India on five of them, with no safety notice. These tests
keep it gone: every URL answers 410 so Google drops it, nothing on the site
links to it, and the harvest that filled it does not come back.
"""
from pathlib import Path

import pytest

from backend.services import ecosystem as E

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("path", ["/sawal", "/sawal/", "/sawal/jowar",
                                  "/sawal/aam", "/sawal/sitemap.xml"])
def test_every_sawal_url_is_gone(client, path):
    r = client.get(path, follow_redirects=False)
    assert r.status_code == 410, f"{path} -> {r.status_code}"
    assert "noindex" in r.text


def test_the_gone_page_names_no_remedy(client):
    text = client.get("/sawal/jowar").text
    for word in ("फोरेट", "किलोग्राम प्रति एकड़", "स्ट्रेप्टो"):
        assert word not in text


def test_no_section_links_to_sawal():
    assert "sawal" not in E.SECTIONS
    for section in list(E.SECTIONS) + [""]:
        ctx = E.Ctx(section=section, canon=f"https://krashimitra.in/{section}")
        for step in E.next_steps(ctx, n=99):
            assert "/sawal" not in step.href, (section, step.href)


def test_sawal_is_not_in_the_sitemap(client):
    assert "/sawal" not in client.get("/sitemap.xml").text


def test_the_kcc_harvest_is_gone():
    assert not (ROOT / "backend/services/kcc_service.py").exists()
    src = (ROOT / "backend/services/mandi_scheduler.py").read_text(encoding="utf-8")
    assert "kcc_service" not in src
