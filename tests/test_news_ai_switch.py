"""The कृषि न्यूज़ AI switch must actually stop the spending.

`news_ai_enabled` exists because the AI half of the news auto-pilot costs
money per call and the free tier can run out mid-morning (2026-09-12: every
Gemini image model returns 429 with `limit: 0` on a free key — image
generation is paid-only). A switch in the admin panel is worth nothing unless
three things hold, and all three are the kind that rot silently:

* **OFF means no model call.** Not "fewer", not "only the cheap one". If a
  single call still goes out, the switch has not done the one thing it is for.
* **OFF must gate the SCHEDULER, not just the button.** The auto-pilot stages
  stories on its own every few days without passing through any route. A
  switch wired only to the panel would leave the quota being spent by the half
  nobody is watching — which is the half that matters when the reason for
  switching off is a bill.
* **OFF must not break the section.** Posts still stage, still publish, still
  carry a real cover. Otherwise the switch is a demolition button and nobody
  will dare use it, which makes it as good as absent.
"""

import asyncio
from unittest.mock import patch

import pytest

from backend.config import get_setting, update_setting
from backend.services import news_auto_service as news


@pytest.fixture(autouse=True)
def isolated_funnel(tmp_path):
    """Point the funnel store at a throwaway file for every test here.

    run_discovery_and_stage() PERSISTS what it stages, and DATA_FILE is
    backend/data/news_funnel.json — a tracked file. Without this, running the
    suite edits the repo, and the staged post then collides with the next run
    through the duplicate check. Found the hard way: a probe run left five
    staged posts and a generated cover image in the working tree.
    """
    with patch.object(news, "DATA_FILE", tmp_path / "news_funnel.json"):
        yield


@pytest.fixture()
def admin_headers():
    """HTTP Basic, from the credentials conftest puts in the environment."""
    import base64
    import os
    raw = f"{os.environ['ADMIN_USER']}:{os.environ['ADMIN_PASS']}".encode()
    return {"Authorization": "Basic " + base64.b64encode(raw).decode()}


@pytest.fixture()
def ai_off():
    """Turn the switch off for one test, and always put it back."""
    before = get_setting("news_ai_enabled", True)
    update_setting("news_ai_enabled", False)
    yield
    update_setting("news_ai_enabled", before)


@pytest.fixture()
def spy():
    """Replace the model call with a counter. Any call at all is a failure in
    the off-tests, so this records rather than raises — a raised exception
    would be swallowed by the pipeline's own except-and-fall-back and the test
    would pass while the call was still being billed."""
    calls = []

    async def fake_call_ai(prompt, max_tokens=1500):
        calls.append(prompt)
        return ('{"title":"AI WROTE THIS","excerpt":"x","full_story":"y",'
                '"bullets":["a","b","c"],"category":"crop"}', "gemini")

    with patch.object(news, "call_ai", fake_call_ai):
        yield calls


def test_the_setting_exists_and_defaults_on():
    """Default ON: a fresh deploy keeps working. The switch is a brake, not an
    opt-in — nobody should have to discover it to get the section running."""
    assert get_setting("news_ai_enabled") is True


# ── OFF means no model call ─────────────────────────────────

def test_off_makes_no_model_call_for_the_text(db_engine, ai_off, spy):
    post = asyncio.run(news.format_agri_post_with_ai(
        "गेहूं का न्यूनतम समर्थन मूल्य बढ़ा — अधिसूचना जारी",
        "कृषि मंत्रालय की विज्ञप्ति के अनुसार इस सीज़न से नई दर लागू होगी।",
        "https://pib.gov.in/x"))
    assert spy == [], f"{len(spy)} model call(s) went out with the switch OFF"
    assert post, "the switch must not stop the post being built"
    # Straight from the source, not a model and not a canned string.
    assert "गेहूं" in post["title"], post["title"]


def test_off_makes_no_model_call_for_the_image(db_engine, ai_off, spy):
    img = asyncio.run(news.generate_ai_agri_image("गेहूं का भाव", "mandi",
                                                  post_id="t-off"))
    assert spy == [], "the image prompt was still synthesised with the switch OFF"
    assert img["source"] == "switched_off"
    assert img["success"] is True


def test_on_does_call_the_model(db_engine, spy):
    """The mirror of the two above — without it they would still pass if the
    pipeline stopped calling Gemini for some unrelated reason, and the switch
    would be untested while looking tested."""
    update_setting("news_ai_enabled", True)
    asyncio.run(news.format_agri_post_with_ai(
        "धान की सरकारी खरीद शुरू — केंद्रों की सूची",
        "खाद्य विभाग ने खरीद केंद्रों की सूची जारी की है।",
        "https://pib.gov.in/y"))
    assert spy, "AI is ON and no model call was made"


# ── OFF must not break the section ──────────────────────────

def test_off_still_produces_a_publishable_post(db_engine, ai_off, spy):
    """Every field the funnel, the SSR page and the cards read must be there.
    A post that stages but renders blank is a worse outcome than no post."""
    post = asyncio.run(news.format_agri_post_with_ai(
        "सोयाबीन की बुवाई का रकबा बढ़ा — विभाग का आंकड़ा",
        "कृषि विभाग के अनुसार इस साल रकबे में बढ़ोतरी दर्ज हुई है।",
        "https://pib.gov.in/z"))
    assert post
    for field in ("id", "title", "excerpt", "full_story", "bullets",
                  "category", "catLabel", "image", "status"):
        assert post.get(field), f"{field} is empty with the switch OFF"
    assert post["status"] == "staged"
    assert len(post["bullets"]) == 3
    # The cover is one of OUR photographs, never the source publisher's.
    assert post["image"].startswith("/images/"), post["image"]


def test_off_takes_the_category_from_the_source_text(db_engine, ai_off, spy):
    """With no model to classify it, the keyword pass has to. A section that
    files every story under "crop" when the switch is off is not usable."""
    post = asyncio.run(news.format_agri_post_with_ai(
        "प्याज मंडी में भाव चढ़ा — व्यापारियों की रिपोर्ट",
        "इस हफ़्ते मंडी भाव और MSP पर विस्तृत रिपोर्ट।",
        "https://example.com/mandi"))
    assert post["category"] == "mandi", post["category"]


def test_off_collapses_english_headlines_into_one_title(db_engine, ai_off, spy):
    """A LIMITATION, recorded so it is not rediscovered as a bug.

    With no model to translate, an English source headline cannot become a
    Hindi one — so the fallback substitutes a fixed generic title per category.
    Two English stories in the same category therefore produce the SAME title,
    and the second is rejected by the duplicate check (returns None).

    Two English stories in the same category therefore come out under the same
    title, and once the first is STAGED the second is rejected by the duplicate
    check. (Not rejected here: format_agri_post_with_ai does not persist, so
    with an empty funnel there is nothing to be a duplicate of — which is
    exactly the seam that made an earlier version of this test pass or fail
    depending on what a previous run had left in the funnel file.)

    This predates the switch — it is the Gemini-error path — but the switch is
    what makes it routine rather than rare. Hindi headlines are unaffected:
    they pass through as written. In practice, with AI off prefer Hindi
    sources, or edit the title in the funnel before publishing.
    """
    args = ("PIB note about the decision.", "https://pib.gov.in/en")
    first = asyncio.run(news.format_agri_post_with_ai("Govt raises wheat MSP", *args))
    second = asyncio.run(news.format_agri_post_with_ai("Centre revises paddy MSP", *args))
    assert first and second
    assert first["title"] == second["title"], (
        "if the fallback has learned to write a real Hindi title from an "
        "English headline, delete this test rather than weaken it")
    # …and neither title carries the story. That is the cost of AI off.
    assert "wheat" not in first["title"].lower()
    assert "paddy" not in second["title"].lower()


# ── the switch reaches the scheduler, not just the button ───

def test_the_switch_gates_the_autopilot_too(db_engine, ai_off, spy):
    """run_discovery_and_stage() is what the scheduler calls on its own, with
    no route and no admin in the loop. It reaches the model through
    format_agri_post_with_ai, so gating that function is what makes the
    switch real — this test is the proof that path is covered, not bypassed."""
    async def one_story():
        return [{"title": "Wheat MSP raised", "content": "PIB note.",
                 "url": "https://pib.gov.in/auto", "source": "PIB"}]

    with patch.object(news, "fetch_external_agri_stories", one_story):
        asyncio.run(news.run_discovery_and_stage(target_count=1))
    assert spy == [], "the auto-pilot called the model with the switch OFF"


# ── the admin route is what actually flips it ───────────────

def test_the_admin_endpoint_flips_it(client, admin_headers):
    """The panel POSTs to /admin/settings. update_setting() returns False for
    an unknown key and the route reports it in `skipped` with a 200 — so a
    renamed key would leave the switch silently inert, the toggle showing the
    state the user picked and the calls still going out."""
    try:
        r = client.post("/admin/settings", json={"news_ai_enabled": False},
                        headers=admin_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "news_ai_enabled" not in body.get("skipped", []), \
            "the key was not recognised — the switch does nothing"
        assert body["settings"]["news_ai_enabled"] is False
        assert get_setting("news_ai_enabled") is False
    finally:
        update_setting("news_ai_enabled", True)


def test_the_panel_can_read_the_state_back(client, admin_headers):
    """The toggle renders from the SERVER on every panel open, so the status
    payload has to carry it — otherwise a switch turned off on one machine
    shows as on for the next person and gets turned "on" again."""
    r = client.get("/admin/status", headers=admin_headers)
    assert r.status_code == 200, r.text
    assert "news_ai_enabled" in r.json()
