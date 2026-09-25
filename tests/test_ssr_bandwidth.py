"""Two ways the server-rendered pages stop re-sending bytes that haven't changed.

1. The shared stylesheet is ONE long-cached file, linked, not ~12.6 KB gzipped
   inlined into every /bhav, /naksha, /product… page.
2. Pages carry an ETag, so the edge re-checking an unchanged page gets a 304.

Both exist because Render suspends the workspace at 5 GB/month of egress —
see backend/services/bandwidth_meter.py.
"""

import re

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route
from starlette.applications import Starlette
from starlette.testclient import TestClient

from backend.routes import bhav
from backend.utils.conditional_get import ConditionalGetMiddleware, etag_for


# ── 1. the shared stylesheet ────────────────────────────────────

def _shell_client():
    app = FastAPI()
    app.include_router(bhav.router)
    return TestClient(app)


def test_doc_links_the_shell_instead_of_inlining_it(monkeypatch):
    # The header and footer read the mandi index from the DB; none here.
    monkeypatch.setattr(bhav, "_get_index", lambda *a, **k: {})
    html = bhav._doc("t", "d", "https://krashimitra.in/x", "", "<p>body</p>",
                     extra_css=".only-this-page{color:red}",
                     journey=False).body.decode()
    assert bhav.SHELL_CSS_LINK in html
    # A long run of the shared sheet must not appear in the page any more.
    assert bhav._CSS[:400] not in html
    # The caller's own rules still ride inline.
    assert ".only-this-page{color:red}" in html


def test_shell_css_is_served_and_cached_for_a_year():
    href = re.search(r'href="([^"]+)"', bhav.SHELL_CSS_LINK).group(1)
    r = _shell_client().get(href)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/css")
    assert r.text == bhav._SHELL_CSS
    assert "immutable" in r.headers["cache-control"]
    assert "immutable" in r.headers["cdn-cache-control"]


def test_an_old_hash_still_gets_a_stylesheet_but_not_immutable():
    # HTML cached at the edge from before a deploy links the previous hash; an
    # unstyled page would be worse than a few minutes of slightly-off styles.
    r = _shell_client().get("/ssr-css/shell.000000000000.css")
    assert r.status_code == 200
    assert r.text == bhav._SHELL_CSS
    assert "immutable" not in r.headers["cache-control"]


def test_the_hash_follows_the_content():
    import hashlib
    want = hashlib.sha256(bhav._SHELL_CSS.encode("utf-8")).hexdigest()[:12]
    assert bhav._SHELL_CSS_VER == want


# ── 2. ETag + 304 ───────────────────────────────────────────────

_PAGE = {"body": "<p>" + "भाव " * 400 + "</p>"}
_PUBLIC = {"Cache-Control": "public, max-age=300",
           "CDN-Cache-Control": "public, max-age=3600"}


def _page(request):
    return HTMLResponse(_PAGE["body"], headers=_PUBLIC)


def _private(request):
    return HTMLResponse("<p>मेरा खाता</p>" * 100,
                        headers={"Cache-Control": "private, no-store"})


def _cookie(request):
    r = HTMLResponse("<p>x</p>" * 100, headers=_PUBLIC)
    r.set_cookie("s", "1")
    return r


def _json(request):
    return JSONResponse({"a": 1}, headers=_PUBLIC)


def _etag_client():
    app = Starlette(routes=[Route("/p", _page), Route("/private", _private),
                            Route("/cookie", _cookie), Route("/api", _json),
                            Route("/p", _page, methods=["POST"])])
    # Same order as main.py: ETag layer inside gzip.
    app.add_middleware(ConditionalGetMiddleware)
    app.add_middleware(GZipMiddleware, minimum_size=500, compresslevel=6)
    return TestClient(app)


def test_page_carries_a_weak_etag_of_its_body():
    r = _etag_client().get("/p")
    assert r.status_code == 200
    assert r.headers["etag"] == etag_for(_PAGE["body"].encode())
    assert r.headers["etag"].startswith('W/"')


def test_unchanged_page_is_a_304_with_its_cache_headers():
    c = _etag_client()
    tag = c.get("/p").headers["etag"]
    r = c.get("/p", headers={"If-None-Match": tag})
    assert r.status_code == 304
    assert r.content == b""
    assert r.headers["etag"] == tag
    assert r.headers["cdn-cache-control"] == _PUBLIC["CDN-Cache-Control"]
    assert "content-type" not in r.headers


def test_tag_matches_with_or_without_the_weak_prefix():
    # Cloudflare re-weakens or re-sends tags when it re-encodes a body.
    c = _etag_client()
    tag = c.get("/p").headers["etag"]
    assert c.get("/p", headers={"If-None-Match": tag[2:]}).status_code == 304
    assert c.get("/p", headers={"If-None-Match": f'"zzz", {tag}'}).status_code == 304


def test_a_changed_page_is_sent_in_full():
    c = _etag_client()
    tag = c.get("/p").headers["etag"]
    old = _PAGE["body"]
    try:
        _PAGE["body"] = old + "<p>नया भाव</p>"
        r = c.get("/p", headers={"If-None-Match": tag})
        assert r.status_code == 200
        assert "नया भाव" in r.text
        assert r.headers["etag"] != tag
    finally:
        _PAGE["body"] = old


def test_if_modified_since_alone_never_produces_a_304():
    # Last-Modified on /bhav is the report DATE; same-day fetches change the
    # page without changing it. Only a body hash may answer "not modified".
    r = _etag_client().get("/p", headers={
        "If-Modified-Since": "Fri, 31 Dec 2100 00:00:00 GMT"})
    assert r.status_code == 200


def test_personal_cookie_and_json_responses_are_left_alone():
    c = _etag_client()
    for path in ("/private", "/cookie", "/api"):
        r = c.get(path, headers={"If-None-Match": "*"})
        assert r.status_code == 200, path
        assert "etag" not in r.headers, path


def test_gzip_still_applies_to_the_full_page():
    r = _etag_client().get("/p", headers={"Accept-Encoding": "gzip"})
    assert r.headers.get("content-encoding") == "gzip"
    assert "etag" in r.headers
