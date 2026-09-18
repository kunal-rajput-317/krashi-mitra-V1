"""फॉलो करें paints on the tap, everywhere it appears.

The profile modal's button and the followers/following list each waited for
TWO round trips before anything changed on screen: `requireMember()` (which
can call /bazar/me) and then the follow POST. On a cold Render dyno with a
sleeping Neon compute that is seconds of a button that looks broken, so the
farmer presses it again. The feed card had already been made optimistic; the
two surfaces a farmer actually follows from had not.

All three now share one runner: paint first, ask the server after, roll back
if it refuses. What is pinned here is what would quietly bring the wait back:

  * no follow path may await a gate before painting — api() already turns the
    endpoint's 403 PROFILE_REQUIRED into the profile prompt, so the POST is
    the gate;
  * the paint has to cover every surface at once (feed cards, the profile
    modal, the list), or following from one place leaves the others lying;
  * a failed request must restore the previous label AND the previous
    followers count, or an optimistic flip becomes a permanent lie;
  * one in-flight request per user, so a double-tap cannot follow-then-unfollow.
"""

import io
import re
from pathlib import Path

import pytest


PAGE = Path(__file__).resolve().parents[1] / "frontend" / "krashi_bajar.html"


@pytest.fixture(scope="module")
def html():
    return io.open(PAGE, encoding="utf-8").read()


def _body(html, name):
    """The source of a top-level function, brace-matched."""
    m = re.search(r"^(?:async )?function %s\(" % re.escape(name), html, re.M)
    assert m, f"{name}() is gone"
    i = html.index("{", m.start())
    depth, j = 0, i
    while True:
        if html[j] == "{":
            depth += 1
        elif html[j] == "}":
            depth -= 1
            if depth == 0:
                return html[i:j + 1]
        j += 1


# ── Every surface goes through the one optimistic runner ─────

@pytest.mark.parametrize("fn", ["followFromCard", "toggleFollow", "toggleFollowInList"])
def test_every_follow_entry_point_delegates(html, fn):
    """The card, the profile modal and the list share one implementation.

    Three copies is how two of them drifted into waiting on the network.
    """
    assert "_runFollow(" in _body(html, fn)


def test_the_onclick_handlers_still_exist(html):
    """The names are wired from markup — renaming one silently kills the button."""
    assert "toggleFollow(${u.user_id})" in html
    assert "toggleFollowInList(${u.user_id})" in html
    assert "followFromCard(event, ${a.user_id})" in html


# ── Paint first, ask after ───────────────────────────────────

def test_nothing_is_awaited_before_the_paint(html):
    """_runFollow paints before its first await.

    requireMember() here meant a /bazar/me round trip in front of the POST,
    for a check the endpoint itself already makes.
    """
    body = _body(html, "_runFollow")
    assert "requireMember" not in body, "the pre-flight gate is back"
    paint = body.index("_paintFollow(")
    first_await = body.index("await ")
    assert paint < first_await, "the button waits on the network again"


def test_the_paint_covers_all_three_surfaces(html):
    body = _body(html, "_paintFollow")
    assert "data-follow-uid" in body          # feed cards
    assert "feedPosts" in body                # and their cached state
    assert "follow-btn" in body               # profile modal
    assert "prof-followers" in body           # its follower count
    assert "fl-btn-" in body                  # followers / following list
    assert "followListData" in body           # and its cache, for re-renders


def test_primary_is_toggled_not_just_following(html):
    """Unfollowing has to put the green 'primary' look back.

    The old code only ever added `.following`, so an unfollowed button fell
    through to the bare outline style and never looked tappable again.
    """
    body = _body(html, "_paintFollow")
    assert body.count("classList.toggle('primary'") == 2


# ── Failure rolls back ───────────────────────────────────────

def test_a_failed_request_restores_label_and_count(html):
    """Both the falsy-success branch and the throw put `prev` back."""
    body = _body(html, "_runFollow")
    assert body.count("_paintFollow(userId, prev, count)") == 2
    assert "catch" in body


def test_one_request_in_flight_per_user(html):
    body = _body(html, "_runFollow")
    assert "_followBusy.has(userId)" in body
    assert "_followBusy.delete(userId)" in body


def test_a_logged_out_tap_does_not_fake_a_follow(html):
    """No token → the login prompt, and no optimistic flip to undo."""
    body = _body(html, "_runFollow")
    gate = body.index("showPrompt('login')")
    assert gate < body.index("_paintFollow(")


# ── The cache-first page must actually reach returning phones ─

def test_service_worker_was_bumped_for_this():
    sw = io.open(PAGE.parent / "sw.js", encoding="utf-8").read()
    name = re.search(r"const CACHE_NAME = '([^']+)'", sw).group(1)
    assert name >= "krashimitra-v25", "krashi_bajar.html is precached cache-first"
