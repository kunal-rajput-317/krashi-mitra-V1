"""The admin panel may never invent a session, or a number.

admin/index.html used to have a "Mock Control Mode". If /admin/status could not
be reached — a cold Render instance was enough — it did three things that are
each worse than showing nothing:

  * `doLogin()` caught ANY error whose message contained "Failed" (every offline
    fetch says "Failed to fetch"), set AUTH_TOKEN to a token nothing had
    validated, and hid the login overlay;
  * the session-restore path, on an unreachable backend, left the panel open
    with AUTH_TOKEN empty, so getAuthHeader() sent `Authorization: ''` and every
    panel behind it got a 401 it then displayed as "no data" — which is how the
    नीला टिक queue came to report an empty queue while two farmers waited in it;
  * the dashboard was painted from a `defaultMockData` literal on page load —
    1420 chroma chunks, 24 cache entries, gemini_configured: true — so the first
    figures the owner read were measurements of nothing, and they stayed until a
    real answer arrived, or forever if none did.

This panel is where money is recorded by hand: a blue tick is granted by someone
looking at a bank app and pressing "₹ मिला". A screen that fabricates state is
not a degraded panel, it is a panel that lies to the one person who cannot check
it against anything else.

The checks below read the source, because none of this is visible from Python or
from an API response — the endpoints were healthy the whole time it was broken.
"""

import io
import re
from pathlib import Path

import pytest

PANEL = Path(__file__).resolve().parents[1] / "admin" / "index.html"


@pytest.fixture(scope="module")
def html():
    return io.open(PANEL, encoding="utf-8").read()


def strip_comments(src):
    """Drop comment LINES.

    The comments deliberately name what was removed, so the next person reading
    this file learns why rather than reinventing it. Only code may be asserted
    against.

    Done line by line rather than with a regex over the whole file: this panel
    contains URLs and regexes with `/*` and `*/` inside string literals, and a
    non-greedy s-flag match across them silently swallowed real code — the first
    version of this fixture ate `function doLogin()` itself.
    """
    out, in_block, in_html = [], False, False
    for line in src.split("\n"):
        t = line.strip()
        if in_block:
            if "*/" in t:
                in_block = False
            continue
        if in_html:
            if "-->" in t:
                in_html = False
            continue
        if t.startswith("/*"):
            if "*/" not in t[2:]:
                in_block = True
            continue
        if t.startswith("<!--"):
            if "-->" not in t[4:]:
                in_html = True
            continue
        if t.startswith("//") or t.startswith("*"):
            continue
        out.append(line)
    return "\n".join(out)


@pytest.fixture(scope="module")
def code(html):
    return strip_comments(html)


def test_mock_mode_is_gone(code):
    for ghost in ("defaultMockData", "Mock Preview", "Mock Control", "mockup mode",
                  "Mock Config"):
        assert ghost not in code, f"{ghost!r} is back in the admin panel"


def test_no_fabricated_system_figures(code):
    """The exact numbers that used to be printed as if measured."""
    for invented in ("chroma_chunks: 1420", "cache_entries: 24",
                     "gemini_keys_count: 3"):
        assert invented not in code, f"hard-coded {invented!r} is back"


def test_an_unreachable_backend_does_not_produce_a_session(html):
    """The restore path must end at the login overlay, not inside the panel.

    Sliced from the raw file and stripped afterwards: the block's own boundary
    used to be a `//` comment, which the stripper now removes.
    """
    start = html.index("let serverOnline = false;")
    block = strip_comments(html[start:html.index("document.getElementById('clock')",
                                                 start)])

    # The old shape was `if (serverOnline) { logout(); } else { ...mock... }`,
    # so logout() ran ONLY when the server had answered. An unreachable backend
    # skipped it and called loadOverview() instead — a data load with
    # AUTH_TOKEN still empty, which 401s and renders as "no data" everywhere.
    assert "if (serverOnline) {\n    logout();" not in block, (
        "logout() is conditional on the server again — an unreachable backend "
        "leaves the panel open with no token")
    # Only the fall-through tail: the three success paths above legitimately
    # call loadOverview(), each right after a validated /admin/status.
    tail = block[block.rindex("catch(e) {}"):]
    assert "loadOverview();" not in tail, (
        "the offline path loads data again with no session; every panel behind "
        "it will 401 and show that as empty")
    assert "logout();" in tail, "nothing forces the login overlay back"

    # And nothing here may reveal the panel: those two lines belong to the
    # success paths, each of which returns right after initDashboard(data).
    assert "overlay.classList.add('hidden')" not in block
    assert "adminApp.classList.add('visible')" not in block


def test_a_failed_login_does_not_set_a_token(code):
    """doLogin's catch is where the fake session was minted."""
    start = code.index("function doLogin()")
    fn = code[start:code.index("function logout()", start)]
    catch = fn[fn.index(".catch("):]

    assert "AUTH_TOKEN =" not in catch, (
        "a failed login assigns AUTH_TOKEN again — that is the mock session")
    assert "sessionStorage.setItem" not in catch, (
        "a failed login persists a token again")
    assert "classList.add('hidden')" not in catch, (
        "a failed login hides the login overlay again")


def test_a_cold_backend_does_not_cost_a_lockout(code):
    """A 30s lockout is the answer to a wrong password, not to a sleeping server.

    Render's free tier spins down; the owner opening the panel after an idle
    hour would otherwise be locked out for half a minute for the server's sake.
    """
    start = code.index("function doLogin()")
    fn = code[start:code.index("function logout()", start)]
    assert "e.kind = 'credentials'" in fn, "the 401 path is no longer distinguished"
    assert "e.kind = 'server'" in fn, "a non-401 server response is no longer distinguished"
    assert re.search(r"if \(e\.kind === 'credentials'\) \{[^}]*startCooldown\(30\)",
                     fn, re.S), "startCooldown is no longer gated on bad credentials"
