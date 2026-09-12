"""Every page Google can index must fit Google's SERP window.

[[serp-length-budgets]] set titles at 68 characters and descriptions at 162
back on 2026-07-29, and `tools/article_builder.py` has refused to build a
non-conforming article ever since. Nothing enforced the same rule on the
*route-rendered* pages, and by 2026-09-12 three families had drifted well past
it — each one silently, because a too-long description still renders fine in a
browser and only gets cut in the SERP, where we never look:

  * /naksha district pages — 768 sitemap URLs, 216k impressions at 0.63%.
    The title went through a `_fit()` ladder on 2026-09-06; the description
    two lines below it stayed a plain f-string and shipped at 190-221 chars.
    Ten of ten sampled live pages were over.

  * /product pages — 89 of 94 titles over budget, median 83. The template
    printed each product twice ("SSP (सिंगल सुपर फॉस्फेट) (SSP (Single Super
    Phosphate)) खरीदें ₹460 | कृषि मित्र दुकान") because name_hi and name_en
    are parallel names that each carry their own bracketed expansion.

  * the hand-written static pages — all sixteen carried a "| KrashiMitra"
    suffix that Google renders separately anyway, spending 14 of 68 characters
    on nothing.

The rule is cheap to state and impossible to remember, so it is asserted here
instead: every family gets one representative page, and the fixtures that need
no database are checked across their whole range rather than sampled.
"""

import json
import re
from pathlib import Path

import pytest

TITLE_MAX = 68
DESC_MAX = 162

# Google renders the site name beside the title, so a brand suffix inside it is
# duplicated text bought with keyword space. Legal pages keep theirs on purpose
# — "Privacy Policy" alone is not a result anyone can place.
BRAND_SUFFIX = re.compile(r"\|\s*(KrashiMitra|कृषि मित्र)")
BRAND_EXEMPT = {"/privacy-policy", "/terms"}


def _head(html, tag):
    if tag == "title":
        m = re.search(r"<title>(.*?)</title>", html, re.S)
    else:
        m = re.search(r'name="description"\s+content="([^"]*)"', html, re.S)
    return m.group(1).strip() if m else None


def _unescape(s):
    return (s.replace("&amp;", "&").replace("&quot;", '"')
             .replace("&lt;", "<").replace("&gt;", ">").replace("&#39;", "'"))


# ── the data-driven families, checked across their whole range ──────────────

def _fit(*variants, limit=TITLE_MAX):
    for v in variants:
        if len(v) <= limit:
            return v
    return min(variants, key=len)


class TestNakshaCoversEveryState:
    """36 states and 737 districts render from one JSON file and no database,
    so there is no excuse for sampling — the long names are exactly the ones
    that break, and a sample of ten will miss "राजन्ना सिरसिल्ला"."""

    @pytest.fixture(scope="class")
    def states(self, repo_root):
        data = json.loads(
            (repo_root / "backend" / "data" / "naksha_states.json").read_text("utf-8"))
        return data["states"]

    def test_every_state_title_fits(self, states):
        from backend.routes.naksha import _ABBR

        over = []
        for key, s in states.items():
            hi, en, n = s["hi"], s["en"], len(s["districts"])
            ab = _ABBR.get(key)
            variants = ([
                f"{hi} का नक्शा – {n} जिलों का HD मानचित्र | {en} ({ab}) Map",
                f"{hi} का नक्शा – {n} जिलों का मानचित्र | {en} ({ab}) Map",
                f"{hi} का नक्शा – {n} जिले | {en} ({ab}) Map, HD डाउनलोड",
                f"{hi} का नक्शा – {n} जिले | {en} ({ab}) Map",
                f"{hi} का नक्शा | {en} ({ab}) Map – {n} जिले",
            ] if ab else []) + [
                f"{hi} का नक्शा – {n} जिलों का HD मानचित्र | {en} Map",
                f"{hi} का नक्शा – {n} जिलों का मानचित्र | {en} Map",
                f"{hi} का नक्शा – {n} जिले | {en} Map",
                f"{hi} का नक्शा – {n} जिलों का HD मानचित्र | मुफ्त डाउनलोड",
                f"{hi} का नक्शा – {n} जिलों का HD मानचित्र (मुफ्त)",
                f"{hi} का नक्शा – {n} जिलों का HD मानचित्र",
            ]
            t = _fit(*variants)
            if len(t) > TITLE_MAX:
                over.append(f"{len(t)}: {t}")
        assert not over, over

    def test_every_district_description_fits(self, states):
        """The regression this file was written for. A single f-string here
        put 737 pages 30-60 characters over, every one of them cut."""
        over = []
        for s in states.values():
            shi, n = s["hi"], len(s["districts"])
            for d in s["districts"]:
                hi, en = d["hi"], d["en"]
                desc = _fit(
                    f"{hi} जिले का नक्शा ({en} district map) — {shi} के {n} जिलों में से एक। "
                    f"सैटेलाइट व्यू में अपना गांव और तहसील देखें, और {shi} का पूरा HD नक्शा "
                    f"मुफ्त डाउनलोड करें।",
                    f"{hi} जिले का नक्शा ({en} district map) — {shi} के {n} जिलों में से एक। "
                    f"सैटेलाइट व्यू में गांव व तहसील देखें, HD नक्शा मुफ्त डाउनलोड करें।",
                    f"{hi} का नक्शा ({en} district map) — {shi} के {n} जिलों में से एक। "
                    f"सैटेलाइट व्यू में गांव व तहसील देखें, HD नक्शा मुफ्त डाउनलोड।",
                    f"{hi} जिले का नक्शा ({en} district map), {shi}। सैटेलाइट व्यू में गांव व "
                    f"तहसील देखें, HD नक्शा मुफ्त डाउनलोड करें।",
                    f"{hi} जिले का नक्शा ({en} district map) — सैटेलाइट व्यू, गांव व तहसील, "
                    f"HD नक्शा मुफ्त डाउनलोड।",
                    f"{hi} का नक्शा ({en} district map) — सैटेलाइट व्यू व HD डाउनलोड।",
                    limit=DESC_MAX)
                if len(desc) > DESC_MAX:
                    over.append(f"{len(desc)}: {hi}/{en}")
        assert not over, over[:10]

    def test_abbreviation_states_carry_the_short_form(self, client):
        """"mp map" was 2,708 impressions at position 5.2 for four clicks
        (0.15%) in the 28 days to 9 Sep 2026 — the worst title/query mismatch
        measured on the site — because the title only ever said "Madhya
        Pradesh". Both spellings have real demand; the title carries both."""
        html = client.get("/naksha/madhya-pradesh").text
        title = _unescape(_head(html, "title"))
        assert "MP" in title, title
        assert "Madhya Pradesh" in title, title
        assert "मध्य प्रदेश" in title, title
        assert len(title) <= TITLE_MAX, f"{len(title)}: {title}"

    def test_district_list_page_answers_the_question_it_ranks_for(self, client):
        """These rank 6-10 for "गुजरात में कितने जिले हैं" and took zero
        clicks; the count was present but buried behind "सभी"."""
        html = client.get("/naksha/gujarat/jile").text
        title = _unescape(_head(html, "title"))
        assert "कितने जिले" in title, title
        assert "34" in title, title
        assert len(title) <= TITLE_MAX, f"{len(title)}: {title}"


class TestProductPages:
    """94 products render from the PRODUCTS array in shop.html — no database,
    so again the whole range is checked rather than a sample."""

    @pytest.fixture(scope="class")
    def products(self):
        from backend.routes.product import _get_by_slug

        return _get_by_slug()

    def test_every_product_page_fits(self, client, products):
        bad = []
        for slug in products:
            html = client.get(f"/product/{slug}").text
            title, desc = _unescape(_head(html, "title")), _unescape(_head(html, "description"))
            if len(title) > TITLE_MAX:
                bad.append(f"title {len(title)}: {title}")
            if len(desc) > DESC_MAX:
                bad.append(f"desc {len(desc)}: {slug}")
            if BRAND_SUFFIX.search(title):
                bad.append(f"brand suffix: {title}")
        assert not bad, bad[:8]

    def test_a_product_is_not_named_twice(self, products):
        """name_hi and name_en are parallel names, each already carrying its
        own expansion in brackets, so the old template printed the acronym
        twice — "SSP (सिंगल सुपर फॉस्फेट) (SSP (Single Super Phosphate))"."""
        from backend.routes.product import _bare_name

        p = products["ssp-single-super-phosphate"]
        assert _bare_name(p["name_hi"]) == "SSP"
        assert _bare_name(p["name_en"]) == "SSP"


class TestStaticPages:
    """The hand-written pages in frontend/. They never pass through a builder,
    which is exactly why every one of them had drifted."""

    @pytest.fixture(scope="class")
    def pages(self, repo_root):
        out = {}
        for path in sorted((repo_root / "frontend").glob("*.html")):
            if path.name == "np.html":      # a meta-refresh stub, no SERP life
                continue
            out[path.name] = path.read_text("utf-8")
        return out

    def test_titles_and_descriptions_fit(self, pages):
        bad = []
        for name, html in pages.items():
            title, desc = _head(html, "title"), _head(html, "description")
            assert title, f"{name} has no <title>"
            assert desc, f"{name} has no meta description"
            if len(_unescape(title)) > TITLE_MAX:
                bad.append(f"{name} title {len(_unescape(title))}: {title}")
            if len(_unescape(desc)) > DESC_MAX:
                bad.append(f"{name} desc {len(_unescape(desc))}")
        assert not bad, bad

    def test_no_brand_suffix_outside_the_legal_pages(self, pages):
        bad = [name for name, html in pages.items()
               if f"/{Path(name).stem}" not in BRAND_EXEMPT
               and BRAND_SUFFIX.search(_unescape(_head(html, "title") or ""))
               and Path(name).stem not in {"index"}]
        assert not bad, bad

    def test_og_and_twitter_match_the_title(self, pages):
        """A rewrite that updates <title> and leaves og:title behind ships a
        page that says two different things — which is what the first pass of
        this very change did, because the pages spell the same meta tag three
        different ways."""
        stale = []
        for name, html in pages.items():
            title = _unescape(_head(html, "title") or "")
            base = title.split("|")[0].strip()
            for attr, tag in (("property", "og:title"), ("name", "twitter:title")):
                m = re.search(rf'<meta\s+{attr}="{tag}"\s+content="([^"]*)"', html, re.S)
                if m and base and base not in _unescape(m.group(1)):
                    stale.append(f"{name} {tag}: {m.group(1)!r} vs {title!r}")
        assert not stale, stale

    def test_the_yojana_page_carries_the_phrase_it_ranks_for(self, pages):
        """"sarkari kisan yojana", "govt kisan yojana", "government kisan
        yojana" and "sarkari yojana kisan" were 1,628 impressions at positions
        12-28 and ZERO clicks in the 28 days to 9 Sep 2026, because the title
        was Devanagari and the queries are romanised. The same page converts
        at 7-10% when the query says "up", so the UP scope stays."""
        html = pages["sarkari_yojana.html"]
        snippet = f"{_head(html, 'title')} {_head(html, 'description')}".lower()
        assert "sarkari kisan yojana" in snippet, snippet
        assert "up" in snippet, snippet


class TestRouteHubs:
    """One page per remaining server-rendered family."""

    @pytest.mark.parametrize("url", [
        "/naksha", "/product/", "/ganna", "/rental", "/sawal",
        "/pashupalan/poultry",
    ])
    def test_hub_fits_and_carries_no_brand_suffix(self, client, url):
        r = client.get(url)
        if r.status_code != 200:
            pytest.skip(f"{url} -> {r.status_code} (needs data this run has not got)")
        title, desc = _unescape(_head(r.text, "title")), _head(r.text, "description")
        assert len(title) <= TITLE_MAX, f"{url}: {len(title)} chars: {title}"
        assert not BRAND_SUFFIX.search(title), f"{url}: {title}"
        if desc:
            assert len(_unescape(desc)) <= DESC_MAX, f"{url}: {len(_unescape(desc))}"

    def test_the_bhav_hub_is_findable_in_both_scripts(self, client):
        """The site's second-biggest page, and the one query "bhav" is 1,900
        impressions of it at position 9.6 for four clicks. The tier-3 and
        tier-4 templates learned to carry both spellings on 2026-09-06; this
        hub was missed and had no Latin character in it at all."""
        html = client.get("/bhav").text
        title = _unescape(_head(html, "title"))
        assert "मंडी भाव" in title, title
        assert re.search(r"[A-Za-z]", title), title
        assert len(title) <= TITLE_MAX, f"{len(title)}: {title}"
