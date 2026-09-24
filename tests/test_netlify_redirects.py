"""frontend/_redirects, as served by this origin.

Driven against a stub ASGI app rather than the real one: the rules are about
routing, and the real app would drag in the database. The stub answers 200 for
a handful of paths that stand in for real content and 404 for everything else,
which is the only thing the middleware needs to tell apart.

The URLs asserted here are the ones that actually broke on 16 Sep 2026 when
Netlify left the request path -- see backend/utils/netlify_redirects.py.
"""
from pathlib import Path

import pytest
from starlette.responses import PlainTextResponse
from starlette.testclient import TestClient

from backend.utils.netlify_redirects import (
    NetlifyRedirectMiddleware,
    Rule,
    parse,
)

REPO = Path(__file__).resolve().parents[1]
RULES = REPO / "frontend" / "_redirects"

# Paths the stub pretends are real pages. /shop and /international/us.html are
# the load-bearing ones: both exist as files, and the rules that touch them
# must resolve in opposite directions.
REAL = {
    "/shop.html",
    "/shop",
    "/international/us.html",
    "/international/index.html",
    "/bhav",
    "/product",
    "/naksha",
}


async def stub(scope, receive, send):
    if scope["type"] == "lifespan":  # TestClient opens one before any request
        while True:
            message = await receive()
            await send({"type": message["type"] + ".complete"})
            if message["type"] == "lifespan.shutdown":
                return
    path = scope["path"]
    status = 200 if path in REAL else 404
    await PlainTextResponse(path, status_code=status)(scope, receive, send)


@pytest.fixture(scope="module")
def client():
    app = NetlifyRedirectMiddleware(stub, rules_path=RULES)
    with TestClient(app) as c:
        yield c


# ── the 35 that 404'd in production ──────────────────────────────────

@pytest.mark.parametrize("source,target", [
    ("/mandi", "/bhav"),
    ("/mandi.html", "/bhav"),
    ("/naksha.html", "/naksha"),
    # These land on the FINAL destination, not on another 301 — the bare
    # /dukanlisting redirects again on this origin. /map is a real page now.
    ("/map.html", "/map"),
    ("/dukan", "/dukanlisting/"),
    ("/dukan.html", "/dukanlisting/"),
    ("/dukan/product", "/dukanlisting/"),
    ("/us.html", "/international/us"),
    ("/bd.html", "/international/bd"),
    ("/farm", "/pashupalan"),
    ("/farm/poultry", "/pashupalan/anda-rate"),
    ("/up-ka-naksha", "/naksha/uttar-pradesh"),
    ("/rajasthan-ka-naksha", "/naksha/rajasthan"),
    ("/bihar-ke-jile", "/naksha/bihar/jile"),
])
def test_indexed_url_redirects(client, source, target):
    r = client.get(source, follow_redirects=False)
    assert r.status_code == 301, f"{source} should 301, got {r.status_code}"
    assert r.headers["location"] == target


def test_retired_shop_redirects_even_though_the_file_exists(client):
    """The forced-rule case, and the reason this is middleware.

    /shop was retired on 16 Sep 2026 in favour of /product, but frontend has
    served shop.html at that URL. Without the `!`, the static mount wins and a
    farmer keeps landing on the retired page.
    """
    r = client.get("/shop", follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"] == "/product"


def test_a_real_page_beats_an_unforced_rule(client):
    """/international/* -> index.html must not swallow a country page.

    The rule carries no `!`, so on Netlify it only fires when nothing else
    answers. Applied eagerly it would rewrite every /international/*.html to
    the hub, quietly replacing 15 country pages with one.
    """
    r = client.get("/international/us.html")
    assert r.status_code == 200
    assert r.text == "/international/us.html"


def test_unforced_rule_rescues_a_404(client):
    """/global has no file behind it; the rule is the only thing serving it."""
    r = client.get("/global")
    assert r.status_code == 200
    assert r.text == "/international/index.html"


def test_splat_is_replayed(client):
    r = client.get("/farm/poultry/anda-rate/haryana", follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"] == "/pashupalan/anda-rate/haryana"


def test_bare_parent_matches_its_own_wildcard(client):
    """`/farm/*` covers /farm itself with an empty splat, as it does on
    Netlify -- /farm was earning impressions before the rename."""
    r = client.get("/farm/anything", follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"] == "/pashupalan"


def test_query_string_survives_a_redirect(client):
    r = client.get("/mandi?crop=wheat&district=lucknow", follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"] == "/bhav?crop=wheat&district=lucknow"


def test_untouched_paths_pass_straight_through(client):
    r = client.get("/bhav")
    assert r.status_code == 200
    assert r.text == "/bhav"


def test_a_genuine_404_stays_a_404(client):
    """The `/* /404.html 404` catch-all is skipped, so an unmatched path must
    reach the app and keep its status -- not get rewritten to the 404 page
    with a 200 on it, which is how soft-404s get indexed."""
    r = client.get("/no-such-page-anywhere")
    assert r.status_code == 404


def test_post_is_never_redirected(client):
    """Rewriting a POST would silently drop its body."""
    r = client.post("/shop", follow_redirects=False)
    assert r.status_code != 301


def test_a_real_handler_is_not_displaced_by_a_forced_rule(tmp_path):
    """The app's own routes outrank the file, forced or not.

    routes/poultry.py already 301s the whole /farm/* tree, deliberately to an
    absolute https://krashimitra.in/... URL after that handler was once an open
    redirect (2026-09-12). A forced rule reading the same path out of a text
    file would have replaced it with a relative Location and silently undone
    the fix — which is exactly what test_poultry.py caught here.

    A forced rule may only pre-empt the static mount, so with no file behind
    the path the handler has to answer.
    """
    rules = tmp_path / "_redirects"
    rules.write_text("/farm  /pashupalan  301!\n", encoding="utf-8")
    empty = tmp_path / "frontend"
    empty.mkdir()

    async def app_with_a_handler(scope, receive, send):
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                await send({"type": message["type"] + ".complete"})
                if message["type"] == "lifespan.shutdown":
                    return
        await PlainTextResponse("the handler ran", status_code=200)(
            scope, receive, send)

    app = NetlifyRedirectMiddleware(
        app_with_a_handler, rules_path=rules, frontend_dir=empty)
    with TestClient(app) as c:
        r = c.get("/farm", follow_redirects=False)
    assert r.status_code == 200
    assert r.text == "the handler ran"


def test_a_rule_cannot_reach_outside_the_frontend_directory(tmp_path):
    """`..` in a URL must not let the static-file test fire a forced rule off
    something above frontend/."""
    rules = tmp_path / "_redirects"
    rules.write_text("/x  /y  301!\n", encoding="utf-8")
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (tmp_path / "secret.html").write_text("no", encoding="utf-8")

    mw = NetlifyRedirectMiddleware(stub, rules_path=rules, frontend_dir=frontend)
    assert mw._static_file_exists("/../secret.html") is False


# ── parsing ──────────────────────────────────────────────────────────

def test_rules_pointing_at_this_origin_are_skipped():
    """They told Netlify where the backend lives. The backend is now what is
    running, so the app already routes those paths; re-applying them would
    bounce /bhav/wheat to itself."""
    forced, fallback = parse(
        "/bhav/*   https://krashi-mitra-v1-p099.onrender.com/bhav/:splat   200\n"
        "/health   https://krashi-mitra-v1-p099.onrender.com/health        200!\n",
        own_origins={"krashi-mitra-v1-p099.onrender.com"},
    )
    assert forced == [] and fallback == []


def test_a_retired_origin_still_counts_as_ourselves():
    """config/backend-origin.txt keeps every old address as an `#old` line for
    exactly this reason -- see backend-origin-single-source."""
    forced, fallback = parse(
        "/x  https://krashi-mitra-v1-muup.onrender.com/x  200\n",
        own_origins={"krashi-mitra-v1-p099.onrender.com",
                     "krashi-mitra-v1-muup.onrender.com"},
    )
    assert forced == [] and fallback == []


def test_the_real_file_parses_and_is_not_empty():
    forced, fallback = parse(RULES.read_text(encoding="utf-8"))
    assert len(forced) > 200, "the 301! rules should dominate the file"
    assert fallback, "the unforced rewrites should survive parsing"
    assert all(r.status == 301 for r in forced if r.status != 200)


def test_comments_and_blank_lines_are_ignored():
    forced, fallback = parse("# a comment\n\n   \n/a  /b  301!\n", own_origins=set())
    assert len(forced) == 1 and not fallback
    assert forced[0].source == "/a"


def test_wildcard_only_matches_its_own_subtree():
    rule = Rule("/farm/*", "/pashupalan", 301, True)
    assert rule.match("/farm") == "/pashupalan"
    assert rule.match("/farm/poultry") == "/pashupalan"
    assert rule.match("/farmers") is None
