"""The /international country pages must stay honest, built, and reachable.

These pages were rewritten on 2026-09-10 because the old hand-written ones
promised American farmers things this site does not do — "USDA Zone-
Calibrated" planting windows, a "Disease Diagnosis Scanner — Live Now", frost
alerts for US counties, "80+ North American plant pathogens". Every price
here comes from Agmarknet, an Indian government feed; there is no disease
scanner and never was after it was dropped. Search Console agreed with the
diagnosis before anyone read the pages: 1,936 US impressions in 90 days
produced one click, and every attributable query from all 127 countries
outside India was about India.

Three failure modes are guarded here, all of which had already happened:

  1. A CLAIM WE CANNOT KEEP. BANNED_CLAIMS below is the list of things the
     old pages said. A page that says any of them again fails.
  2. A PAGE THAT CANNOT EARN OR BE MEASURED. All eight old pages shipped
     without ads.js, analytics.js or the shell — so even a page ranking
     perfectly earned nothing, and nobody could have seen it happen.
  3. A PAGE NETLIFY WILL NOT SERVE. Netlify serves frontend/ statically and
     _redirects decides what /us resolves to; a country added to COUNTRIES
     without its rule falls through to the catch-all and 404s on the apex
     domain while answering 200 on Render — exactly how /ganna shipped once.
"""

import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from tools.build_international import (  # noqa: E402
    COUNTRIES, FAQ, HUB_LANGS, LABELS, LANGS, OUT_DIR, SCRIPT_RANGE, T, TITLE_MAX,
    desc_of, label, page_strings, render, render_hub, title_of,
)

REDIRECTS = REPO / "frontend" / "_redirects"
DESC_MAX = 162          # the site-wide meta-description budget
CORE_URLS = ["/bhav", "/naksha", "/sarkari_yojana", "/articles/",
             "/krashi_news", "/", "/about", "/privacy-policy"]

# Verbatim from the pages this rewrite replaced. Matched case-insensitively
# against the rendered HTML. Do not "fix" a failure by softening the wording —
# the page must not make the claim at all.
BANNED_CLAIMS = [
    "usda",                    # zone calibration, grant guides, hardiness zones
    "hardiness",
    "disease diagnosis",       # the scanner was dropped; it is not "Live Now"
    "diagnosis scanner",
    "frost alert",
    "freeze alert",
    "plant pathogens",
    "zone-calibrated",
    "24/7",                    # nothing here is staffed
    "100% free forever",
]


def _pages():
    """code -> rendered HTML, from the builder rather than from disk, so a
    claim cannot be reintroduced in the template and hidden by a stale file."""
    out = {c.code: render(c) for c in COUNTRIES}
    out["index"] = render_hub()
    return out


# Parametrise over CODES, never over the HTML: pytest builds a test id from
# each argument and exports it in PYTEST_CURRENT_TEST, and a 16KB page blows
# the 32,767-character Windows environment-variable limit before a single
# assertion runs.
CODES = sorted(_pages())
PAGES = _pages()


def rules():
    """(source, target) per _redirects rule, in file order — Netlify takes
    the first match, so order is part of the meaning."""
    out = []
    for line in REDIRECTS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            out.append((parts[0], parts[1]))
    return out


def resolves_to(path: str) -> str:
    """What Netlify serves for `path`, first matching rule wins."""
    for src, target in rules():
        if src == path:
            return target
        if src.endswith("/*") and path.startswith(src[:-1]):
            return target
    return ""


# ── 1. honesty ───────────────────────────────────────────────
@pytest.mark.parametrize("code", CODES)
def test_page_makes_no_claim_we_cannot_keep(code):
    low = PAGES[code].lower()
    found = [c for c in BANNED_CLAIMS if c in low]
    assert not found, (
        f"/{code} makes a claim this site cannot keep: {found}. Every price "
        f"here is Agmarknet (India) and there is no disease scanner. Say what "
        f"is true instead — see the header of tools/build_international.py.")


@pytest.mark.parametrize("code", CODES)
def test_page_states_the_data_is_indian(code):
    """The one claim these pages MUST make, so a reader abroad is never
    misled about whose mandi prices they are looking at."""
    assert "Agmarknet" in PAGES[code], (
        f"/{code} never names the data source. A page selling Indian prices "
        f"to a reader in another country has to say they are Indian.")


# ── 2. can earn, can be measured ─────────────────────────────
@pytest.mark.parametrize("code", CODES)
def test_page_carries_the_shell(code):
    """drawer-menu.js bootstraps km-shell.css AND ads.js — it is the single
    line that makes a page look like the rest of the site and earn from it.
    All eight pages this replaced were missing all three."""
    for needed in ("drawer-menu.js", "analytics.js", "km-shell.css",
                   "header-scroll.js", "bottomnav.js"):
        assert needed in PAGES[code], f"/{code} does not load {needed}"


# ── 3. reachable, and within the SERP budgets ────────────────
@pytest.mark.parametrize("c", COUNTRIES, ids=[c.code for c in COUNTRIES])
def test_country_is_served_by_netlify(c):
    want = f"/international/{c.code}.html"
    assert resolves_to(f"/{c.code}") == want, (
        f"/{c.code} does not resolve to its page — it falls through to "
        f"{resolves_to('/' + c.code) or 'the catch-all 404'}. Run "
        f"`python tools/build_international.py --redirects` and paste the "
        f"block into frontend/_redirects.")
    assert resolves_to(f"/international/{c.code}") == want, (
        f"/international/{c.code} is swallowed by the /international/* "
        f"wildcard — its own rule must come first.")


@pytest.mark.parametrize("c", COUNTRIES, ids=[c.code for c in COUNTRIES])
def test_country_is_in_the_sitemap(c):
    src = (REPO / "backend" / "routes" / "sitemap.py").read_text(encoding="utf-8")
    assert f'"international/{c.code}.html"' in src, (
        f"/{c.code} is not in sitemap.py's manifest, so Google only finds it "
        f"by luck.")


@pytest.mark.parametrize("c", COUNTRIES, ids=[c.code for c in COUNTRIES])
def test_serp_budgets(c):
    """Every language, not just the one that ships — a reader who switches to
    Arabic gets document.title from the island, and a title written to the
    English budget can be 20 characters longer once translated."""
    for lang in c.langs:
        t, d = title_of(c, lang), desc_of(c, lang)
        assert len(t) <= TITLE_MAX, f"/{c.code} {lang} title is {len(t)} chars: {t}"
        assert len(d) <= DESC_MAX, f"/{c.code} {lang} description is {len(d)} chars"
        assert "KrashiMitra" not in t, f"/{c.code} {lang} title carries a brand suffix"


@pytest.mark.parametrize("c", COUNTRIES, ids=[c.code for c in COUNTRIES])
def test_title_script_matches_the_page_language(c):
    """A title in the wrong script converts ~2.7x worse at the same position,
    which is why the page ships in langs[0] rather than in Hindi for everyone.
    A Nepali page whose title came out Latin is that defect in a new place."""
    for lang in c.langs:
        rng = SCRIPT_RANGE[lang]
        t = title_of(c, lang)
        if rng is None:
            assert not any(re.search(r, t) for r in
                           {v for v in SCRIPT_RANGE.values() if v}), (
                f"/{c.code} {lang} should be a Latin title but is not: {t}")
        else:
            assert re.search(rng, t), (
                f"/{c.code} {lang} title is not written in {lang}: {t}")


# ── the language toggle ──────────────────────────────────────
@pytest.mark.parametrize("c", COUNTRIES, ids=[c.code for c in COUNTRIES])
def test_page_ships_in_the_country_own_language(c):
    """langs[0] is what a crawler and a JS-off phone see, so it has to be the
    country's own language — that is the whole point of the pass."""
    assert c.langs, f"/{c.code} has no languages"
    assert c.lang == c.langs[0]
    assert "en" in c.langs, f"/{c.code} has no English option"
    assert "hi" in c.langs, (
        f"/{c.code} dropped Hindi — every destination page (/bhav, /naksha, "
        f"/sarkari_yojana) is written in Hindi and the query log says these "
        f"visitors type Hindi.")
    assert len(set(c.langs)) == len(c.langs), f"/{c.code} lists a language twice"
    html = PAGES[c.code]
    assert f'<html lang="{c.lang}">' in html, f"/{c.code} does not declare lang={c.lang}"


@pytest.mark.parametrize("code", CODES)
def test_language_switch_is_buttons_not_links(code):
    """An <a href="?lang=ar"> would be a crawlable URL and would multiply
    these 16 pages by their language count in an index whose measured
    bottleneck is bloat. Same rule free_month.card() follows."""
    html = PAGES[code]
    picker = html[html.index('id="km-lang-pick"'):]
    picker = picker[:picker.index("</div>")]
    assert "<a " not in picker, f"/{code}'s language picker contains a link"
    assert picker.count("<button") >= 2, f"/{code}'s picker offers fewer than two languages"
    assert "?lang=" not in html, f"/{code} builds a per-language URL"


@pytest.mark.parametrize("c", COUNTRIES, ids=[c.code for c in COUNTRIES])
def test_every_offered_language_is_actually_translated(c):
    """The toggle promising a language it then renders in English is worse
    than not offering it. Every UI string and every link label a page uses
    must exist in every language that page offers."""
    for lang in c.langs:
        missing = [k for k, v in T.items() if lang not in v]
        assert not missing, f"/{c.code} offers {lang} but T is missing {missing}"
        assert lang in FAQ, f"/{c.code} offers {lang} but there is no FAQ for it"
        for url in set(CORE_URLS) | set(c.seen):
            assert lang in LABELS[url], (
                f"/{c.code} offers {lang} but LABELS[{url}] has no {lang}")


@pytest.mark.parametrize("c", COUNTRIES, ids=[c.code for c in COUNTRIES])
def test_island_carries_every_language_but_the_default(c):
    """The default is restored from the markup it shipped with, so shipping
    it twice would only be weight — and every OTHER language has to be in the
    island or its button does nothing."""
    html = PAGES[c.code]
    blob = html[html.index('id="km-i18n">') + len('id="km-i18n">'):]
    blob = json.loads(blob[:blob.index("</script>")])
    assert blob["def"] == c.lang
    assert blob["langs"] == c.langs
    assert set(blob["s"]) == set(c.langs) - {c.lang}, (
        f"/{c.code}'s island languages do not match its toggle")
    for lang in c.langs:
        assert blob["meta"][lang]["dir"] == LANGS[lang]["dir"]
    keys = {k for k in re.findall(r'data-i18n="([^"]+)"', html)}
    for lang, tbl in blob["s"].items():
        gap = keys - set(tbl)
        assert not gap, f"/{c.code} {lang} cannot translate {sorted(gap)[:5]}"


@pytest.mark.parametrize("c", COUNTRIES, ids=[c.code for c in COUNTRIES])
def test_arabic_pages_are_rtl(c):
    if c.lang != "ar":
        return
    assert '<div id="km-i18n-root" dir="rtl">' in PAGES[c.code], (
        f"/{c.code} ships in Arabic but its content wrapper is not RTL")
    assert "Noto+Sans+Arabic" in PAGES[c.code], (
        f"/{c.code} ships in Arabic but never loads an Arabic font")


def test_hub_ships_in_english_with_hindi():
    html = PAGES["index"]
    assert '<html lang="en">' in html
    assert HUB_LANGS[0] == "en" and "hi" in HUB_LANGS


# ── the files on disk must match the builder ─────────────────
def test_pages_on_disk_are_current():
    stale = []
    for name, html in {**{f"{c.code}.html": render(c) for c in COUNTRIES},
                       "index.html": render_hub()}.items():
        p = OUT_DIR / name
        if not p.is_file() or p.read_text(encoding="utf-8") != html:
            stale.append(name)
    assert not stale, ("run `python tools/build_international.py` — stale: "
                       + ", ".join(stale))


def test_no_orphan_pages():
    """A leftover file from the hand-written era would still be served, and
    would still be making its old promises."""
    known = {f"{c.code}.html" for c in COUNTRIES} | {"index.html"}
    orphans = sorted(f.name for f in OUT_DIR.glob("*.html") if f.name not in known)
    assert not orphans, f"no COUNTRIES row for: {orphans}"


def test_every_link_target_is_a_page_we_publish():
    """Each card links somewhere real. The old pages pointed at /chat for
    everything, including 'Start Free Scouting'."""
    for c in COUNTRIES:
        for url in c.seen:
            assert url in LABELS, f"/{c.code} links {url}, which has no label"
            assert label(url, c.lang), f"/{c.code} links {url} with an empty label"
