# ============================================================
# KrashiMitra — /international country pages (server side)
#
# The pages themselves are FILES, built by tools/build_international.py and
# served statically by Netlify — see frontend/_redirects. This router exists
# so the same URLs also answer on Render: the backend is what /share, /bhav
# and every proxied route run on, and a URL that works on one host and 404s
# on the other is how /ganna shipped broken once already.
#
# It used to be one hand-written handler per country, which meant adding a
# country was two edits in two files that could silently disagree. The code
# list now comes from the directory itself: any {code}.html the builder
# writes is served, and nothing else is. Two letters only, so no path can
# escape the folder.
# ============================================================

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["international"])

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
INTL_DIR = FRONTEND_DIR / "international"

# Same one-day cache the other static-ish pages use: these change only when
# the builder runs, and a country page is not worth a request to origin per
# view on a 512MB box.
_HEADERS = {"Cache-Control": "public, max-age=3600, s-maxage=86400"}


def _page(name: str) -> HTMLResponse:
    path = INTL_DIR / name
    if not path.is_file():
        raise HTTPException(status_code=404)
    return HTMLResponse(content=path.read_text(encoding="utf-8"), headers=_HEADERS)


@router.get("/international", response_class=HTMLResponse)
@router.get("/international/", response_class=HTMLResponse)
def international_hub():
    return _page("index.html")


@router.get("/international/{code}", response_class=HTMLResponse)
def international_country(code: str):
    """/international/us and friends.

    A two-letter lowercase code only. Anything else 404s rather than reaching
    the filesystem — `code` is user input and INTL_DIR holds nothing but these
    pages, so the shape check is the whole guard.
    """
    if len(code) != 2 or not code.isascii() or not code.isalpha():
        raise HTTPException(status_code=404)
    return _page(f"{code.lower()}.html")


# The short forms — /us, /uk, /ae … — are registered from the files on disk
# rather than written out, so a country the builder adds is live here the
# moment its page exists. Registered one by one (not as /{code}) because a
# two-letter catch-all at the site root would shadow every other route.
def _register_short_paths() -> None:
    if not INTL_DIR.is_dir():
        return
    for f in sorted(INTL_DIR.glob("??.html")):
        code = f.stem.lower()
        if not code.isascii() or not code.isalpha():
            continue

        def handler(_name=f.name):
            return _page(_name)

        router.add_api_route(f"/{code}", handler, methods=["GET"],
                             response_class=HTMLResponse, tags=["international"],
                             name=f"portal_{code}")


_register_short_paths()
