"""Publishing an article from the admin panel instead of from a git commit.

Four things have to hold, and each one is a failure this site has already had
in some other form.

THE FILE IS A COPY, NOT THE ORIGINAL. Render's free tier replaces the
filesystem with a fresh checkout on every restart — that is how profile avatars
disappeared before they moved into Postgres. So a published article has to come
back on its own after the disk is wiped, without anyone pressing anything.

A FAILED PUBLISH LEAVES NOTHING BEHIND. The builder's validator is the only
thing standing between a typo and a live page, and a half-written article in
frontend/articles/ is worse than none: sitemap.py enumerates that directory, so
it would be handed to Google within the hour.

GENERATED MARKUP IS BALANCED. An unclosed <div> blanks the whole page on mobile
while desktop still looks fine, and 98% of this site's traffic is phones. The
markdown converter exists precisely so an author never hand-types a tag.

/articles/credits STILL ANSWERS. routes/articles.py now owns /articles/{slug},
which matches anything — including the photo-attribution page whose existence
is a licence condition of every CC BY image on the site.
"""

import json
import re
import shutil

import pytest

from backend.services import article_publish as ap


# ── a throwaway copy of the site to publish into ───────────────────────────

@pytest.fixture
def site(tmp_path, monkeypatch, repo_root):
    """Point the builder at a temp frontend so tests never touch the real one.

    The shell source is copied rather than stubbed: the whole promise of this
    feature is that a panel article gets the same chrome as a committed one, so
    a test that renders against a fake shell would not be testing it.
    """
    b = ap._builder()
    real = repo_root / "frontend"
    front = tmp_path / "frontend"
    (front / "articles").mkdir(parents=True)
    (front / "images" / "articles").mkdir(parents=True)
    shutil.copy(real / "articles" / "index.html", front / "articles" / "index.html")
    shutil.copy(real / "articles" / "tomato-leaf-curl.html",
                front / "articles" / "tomato-leaf-curl.html")

    monkeypatch.setattr(b, "FRONTEND", front)
    monkeypatch.setattr(b, "ARTICLES", front / "articles")
    monkeypatch.setattr(b, "INDEX", front / "articles" / "index.html")
    monkeypatch.setattr(b, "SHELL_SOURCE", front / "articles" / "tomato-leaf-curl.html")
    monkeypatch.setattr(b, "REDIRECTS", front / "_redirects")

    # The validator asserts every ../asset on the page exists on disk, because
    # a missing static file is served as 200-HTML here and fails silently.
    shell = (front / "articles" / "tomato-leaf-curl.html").read_text(encoding="utf-8")
    assets = set(re.findall(r'(?:src|href)="\.\./([^"?#]+)"', shell))
    # dukan-promo.js is not discoverable from the shell: the builder emits it
    # per-article, only for the sections that carry the दुकान block
    # (article_builder.wants_dukan_promo), so a promo-eligible article
    # references an asset the shell source never mentions.
    assets.add("dukan-promo.js")
    for rel in assets:
        p = front / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"")
    return front


def hero_bytes() -> bytes:
    from io import BytesIO
    from PIL import Image
    buf = BytesIO()
    Image.new("RGB", (1400, 900), (40, 120, 60)).save(buf, "PNG")
    return buf.getvalue()


def payload(slug="test-fasal-rog", **over) -> dict:
    para = "यह एक टेस्ट पैराग्राफ है जिसमें पर्याप्त शब्द हैं ताकि लेख की लंबाई पूरी हो। " * 12
    body = "\n\n".join(f"## 📖 सेक्शन {i}\n{para}" for i in range(1, 9))
    p = {
        "slug": slug,
        "cat": "keet",
        "title": "टेस्ट लेख — जाँच के लिए बनाया गया पेज है यह",
        "description": ("यह विवरण सत्तर अक्षरों से लंबा है ताकि SERP में पूरा दिखे "
                        "और बिल्डर का चेक पास हो — असर 30 दिन तक।"),
        "h1": "टेस्ट लेख",
        "h1_en": "Test Article",
        "body": body,
        "body_format": "md",
        "faqs": [[f"सवाल {i} क्या है?", f"जवाब {i} यह है — {i * 10} दिन।"]
                 for i in range(1, 7)],
        "image_caption": "जाँच के लिए बनाई गई तस्वीर",
    }
    p.update(over)
    return p


def publish(db, site, slug="test-fasal-rog", **over):
    ap.attach_image(db, slug, hero_bytes())
    return ap.save(db, payload(slug, **over))


# ── markdown → the site's own markup ───────────────────────────────────────

class TestMarkdown:
    MD = (
        "## 🐛 पहचान\n"
        "पहला **पैरा** और [भाव](https://krashimitra.in/bhav/wheat)।\n\n"
        "- **लक्षण एक:** पत्ती पीली\n"
        "- **लक्षण दो:** तना कमजोर\n\n"
        "> सामान्य सुझाव।\n\n"
        ">! डोज़ KVK से पुष्टि करें।\n\n"
        "## 📊 तुलना\n"
        "| पहचान | स्वस्थ | ग्रस्त |\n| --- | --- | --- |\n| पत्ती | हरी | पीली |\n\n"
        "### उप-शीर्षक\n1. पहला\n2. दूसरा\n"
    )

    def test_every_tag_is_closed(self):
        """The bug that blanks mobile and leaves desktop looking fine."""
        html = ap.md_to_html(self.MD)
        for tag in ("section", "div", "table", "ul", "ol", "li", "p", "tr", "td", "th"):
            opened = len(re.findall(rf"<{tag}[\s>]", html))
            closed = len(re.findall(rf"</{tag}>", html))
            assert opened == closed, f"<{tag}>: {opened} open vs {closed} close"

    def test_only_classes_that_already_exist(self):
        html = ap.md_to_html(self.MD)
        assert 'class="article-section"' in html
        assert 'class="section-heading"' in html
        assert 'class="article-table"' in html
        # doses/money/deadlines get the red box, not the friendly one
        assert 'class="tip-box warning"' in html
        assert 'class="tip-box info"' in html

    def test_leading_emoji_becomes_the_section_icon(self):
        html = ap.md_to_html(self.MD)
        assert '<span class="s-icon">🐛</span>' in html
        assert "<h2>पहचान</h2>" in html

    def test_ads_are_markers_never_raw_adsense(self):
        html = ap.md_to_html(self.MD)
        assert "km-ad-slot" in html
        assert "<ins" not in html and "adsbygoogle" not in html


# ── the payload the panel submits ──────────────────────────────────────────

class TestExpand:
    def test_derives_what_an_author_should_not_retype(self):
        a = ap.expand(payload())
        assert a["word_count"] > 500
        assert a["read_time"] == max(3, round(a["word_count"] / 200))
        assert a["cat_query"] == "keet"
        assert a["card"]["cats"] == "keet"          # a real filter chip
        assert a["card"]["accent"] == ap.CATS["keet"]["accent"]
        assert len(a["related"]) >= 2

    def test_slug_is_forced_lowercase_rather_than_rejected(self):
        """sitemap.py serves every article at stem.lower(); a mixed-case name
        makes the canonical and the sitemap disagree about which URL is real.
        The panel fixes it silently — an author typing a capital is not an
        error worth stopping for."""
        assert ap.expand(payload("Test-Fasal-Rog"))["slug"] == "test-fasal-rog"

    def test_a_slug_with_spaces_or_devanagari_is_refused(self):
        for bad in ("test fasal", "फसल-रोग", "ab", "x" * 90):
            with pytest.raises(ap.PublishError):
                ap.expand(payload(bad))

    def test_reserved_slugs_cannot_be_taken(self):
        for slug in ("credits", "meta", "index"):
            with pytest.raises(ap.PublishError):
                ap.expand(payload(slug))

    def test_category_must_be_a_real_chip(self):
        with pytest.raises(ap.PublishError):
            ap.expand(payload(cat="nonsense"))

    def test_related_links_point_at_files_that_exist(self, site):
        a = ap.expand(payload())
        for href, *_ in a["related"]:
            if "/articles/" in href:
                slug = href.rsplit("/", 1)[-1]
                assert (site / "articles" / f"{slug}.html").is_file(), href


# ── publishing ─────────────────────────────────────────────────────────────

class TestPublish:
    def test_page_lands_in_the_articles_directory(self, site, db_session):
        out = publish(db_session, site)
        assert out["ok"], out.get("problems")
        page = site / "articles" / "test-fasal-rog.html"
        assert page.is_file()
        doc = page.read_text(encoding="utf-8")
        # the same chrome as every committed article
        assert "km-shell.css" in doc and "km-footer" in doc
        assert doc.count("<h1>") == 1
        assert doc.count('<script type="application/ld+json">') == 3

    def test_hub_card_is_inserted_once_however_often_it_is_republished(
            self, site, db_session):
        publish(db_session, site)
        publish(db_session, site, title="टेस्ट लेख — दूसरा शीर्षक जाँच के लिए")
        index = (site / "articles" / "index.html").read_text(encoding="utf-8")
        assert index.count('href="test-fasal-rog"') == 1

    def test_hero_photo_feeds_the_page_the_card_and_og_image(self, site, db_session):
        publish(db_session, site)
        doc = (site / "articles" / "test-fasal-rog.html").read_text(encoding="utf-8")
        assert 'class="featured-image"' in doc
        assert "og-banner" not in doc                      # never the generic banner
        assert (site / "images" / "articles" / "test-fasal-rog.webp").is_file()
        assert (site / "images" / "articles" / "test-fasal-rog-card.webp").is_file()

    def test_a_page_that_fails_validation_is_not_left_on_disk(self, site, db_session):
        """A half-published article would be in the sitemap within the hour."""
        out = publish(db_session, site, slug="thin-one", body="## 📖 छोटा\nबहुत छोटा लेख।")
        assert out["ok"] is False
        assert out["problems"]
        assert not (site / "articles" / "thin-one.html").exists()
        assert ap.get(db_session, "thin-one") is None or \
            ap.get(db_session, "thin-one").status == "draft"

    def test_force_ships_it_and_records_what_was_wrong(self, site, db_session):
        ap.attach_image(db_session, "thin-one", hero_bytes())
        out = ap.save(db_session, payload("thin-one", body="## 📖 छोटा\nबहुत छोटा लेख।"),
                      force=True)
        assert out["ok"] and out["problems"]
        row = ap.get(db_session, "thin-one")
        assert json.loads(row.problems)                    # never silently forced

    def test_a_committed_article_cannot_be_overwritten(self, site, db_session):
        """Two pages at one URL is the failure the lowercase-slug work fixed."""
        with pytest.raises(ap.PublishError):
            ap.save(db_session, payload("tomato-leaf-curl"))

    def test_uploading_a_photo_does_not_buy_a_committed_slug(self, site, db_session):
        """The draft row an image upload creates must not read as ownership —
        otherwise a photo under a committed slug is enough to let the next
        publish overwrite that article, and its own hero with it."""
        hero = site / "images" / "articles" / "tomato-leaf-curl.webp"
        before = hero.read_bytes() if hero.exists() else None
        with pytest.raises(ap.PublishError):
            ap.attach_image(db_session, "tomato-leaf-curl", hero_bytes())
        # its own licensed photo, untouched
        assert (hero.read_bytes() if hero.exists() else None) == before
        with pytest.raises(ap.PublishError):
            ap.save(db_session, payload("tomato-leaf-curl"))

    def test_update_keeps_one_row_and_one_file(self, site, db_session):
        publish(db_session, site)
        publish(db_session, site, h1="टेस्ट लेख दूसरा")
        rows = ap.listing(db_session)
        assert [r["slug"] for r in rows].count("test-fasal-rog") == 1
        doc = (site / "articles" / "test-fasal-rog.html").read_text(encoding="utf-8")
        assert "टेस्ट लेख दूसरा" in doc


# ── the Render restart ─────────────────────────────────────────────────────

class TestRestore:
    def test_a_wiped_disk_comes_back_at_boot(self, site, db_session):
        publish(db_session, site)
        page = site / "articles" / "test-fasal-rog.html"
        image = site / "images" / "articles" / "test-fasal-rog.webp"
        # what Render does on every restart: the git checkout, nothing else
        page.unlink()
        image.unlink()

        result = ap.restore_all(db_session)

        assert result["failed"] == []
        assert "test-fasal-rog" in result["restored"]
        assert page.is_file(), "the article silently left the site"
        assert image.is_file(), "og:image and the hub card would be blank"

    def test_restore_is_idempotent(self, site, db_session):
        publish(db_session, site)
        ap.restore_all(db_session)
        ap.restore_all(db_session)
        index = (site / "articles" / "index.html").read_text(encoding="utf-8")
        assert index.count('href="test-fasal-rog"') == 1

    def test_listing_reports_a_row_whose_file_is_missing(self, site, db_session):
        publish(db_session, site)
        (site / "articles" / "test-fasal-rog.html").unlink()
        row = next(r for r in ap.listing(db_session) if r["slug"] == "test-fasal-rog")
        assert row["on_disk"] is False


class TestUnpublish:
    def test_page_card_and_row_all_go(self, site, db_session):
        publish(db_session, site)
        ap.delete(db_session, "test-fasal-rog")
        assert not (site / "articles" / "test-fasal-rog.html").exists()
        index = (site / "articles" / "index.html").read_text(encoding="utf-8")
        assert 'href="test-fasal-rog"' not in index
        assert ap.get(db_session, "test-fasal-rog") is None


# ── the routes ─────────────────────────────────────────────────────────────

class TestRoutes:
    def test_credits_is_not_shadowed_by_the_slug_route(self, client):
        """/articles/{slug} matches anything, and credits is a licence condition."""
        r = client.get("/articles/credits")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]

    def test_meta_is_not_shadowed_either(self, client):
        r = client.get("/articles/meta")
        assert r.status_code == 200
        assert isinstance(r.json(), dict)

    def test_html_form_301s_to_the_canonical(self, client):
        r = client.get("/articles/urea-guide-up.html", follow_redirects=False)
        assert r.status_code == 301
        assert r.headers["location"] == "/articles/urea-guide-up"

    def test_mixed_case_301s_to_lowercase(self, client):
        r = client.get("/articles/Urea-Guide-UP", follow_redirects=False)
        assert r.status_code == 301
        assert r.headers["location"] == "/articles/urea-guide-up"

    def test_a_committed_article_is_served(self, client):
        r = client.get("/articles/urea-guide-up")
        assert r.status_code == 200
        assert "<h1>" in r.text
        # Netlify only caches a proxied response when the origin opts in
        assert "Netlify-CDN-Cache-Control" in r.headers

    def test_an_unknown_slug_is_a_real_404(self, client):
        """A 200 homepage here is a soft-404 and index bloat."""
        r = client.get("/articles/koi-nahi-hai-yeh")
        assert r.status_code == 404

    def test_admin_endpoints_need_credentials(self, client):
        assert client.get("/admin/articles").status_code == 401
        assert client.post("/admin/articles", json=payload()).status_code == 401


# ── the panel's own API ────────────────────────────────────────────────────

AUTH = ("testadmin", "test-admin-pass")


class TestAdminApi:
    def test_check_reports_the_size_and_never_writes_a_file(self, site, client):
        r = client.post("/admin/articles/check", json=payload("api-check-one"), auth=AUTH)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["words"] > 1200
        # no hero uploaded yet, so the builder should be saying so
        assert any("hero" in p or "og:image" in p for p in d["problems"]), d["problems"]
        assert not (site / "articles" / "api-check-one.html").exists()

    def test_preview_returns_the_real_page_and_stores_nothing(self, site, client):
        r = client.post("/admin/articles/preview", json=payload("api-preview"), auth=AUTH)
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        assert r.text.count("<h1>") == 1
        assert not (site / "articles" / "api-preview.html").exists()

    def test_a_bad_payload_is_a_400_not_a_500(self, site, client):
        r = client.post("/admin/articles/check",
                        json=payload("api-bad", cat="nonsense"), auth=AUTH)
        assert r.status_code == 400

    def test_publish_flow(self, site, client):
        slug = "api-publish-one"
        img = client.post(f"/admin/articles/{slug}/image",
                          files={"file": ("hero.png", hero_bytes(), "image/png")},
                          auth=AUTH)
        assert img.status_code == 200, img.text

        r = client.post("/admin/articles", json=payload(slug), auth=AUTH)
        assert r.status_code == 200, r.text
        assert r.json()["url"].endswith(f"/articles/{slug}")
        assert (site / "articles" / f"{slug}.html").is_file()

        listed = client.get("/admin/articles", auth=AUTH).json()
        assert slug in [a["slug"] for a in listed["articles"]]
        assert listed["committed"] >= 1

        gone = client.delete(f"/admin/articles/{slug}", auth=AUTH)
        assert gone.status_code == 200
        assert not (site / "articles" / f"{slug}.html").exists()

    def test_a_page_the_builder_rejects_comes_back_as_422_with_reasons(
            self, site, client):
        slug = "api-thin"
        client.post(f"/admin/articles/{slug}/image",
                    files={"file": ("hero.png", hero_bytes(), "image/png")}, auth=AUTH)
        r = client.post("/admin/articles",
                        json=payload(slug, body="## 📖 छोटा\nबहुत छोटा।"), auth=AUTH)
        assert r.status_code == 422
        assert r.json()["detail"]["problems"]
        assert not (site / "articles" / f"{slug}.html").exists()

        forced = client.post("/admin/articles?force=true",
                             json=payload(slug, body="## 📖 छोटा\nबहुत छोटा।"), auth=AUTH)
        assert forced.status_code == 200
        assert (site / "articles" / f"{slug}.html").is_file()
        client.delete(f"/admin/articles/{slug}", auth=AUTH)

    def test_an_oversized_photo_is_refused_before_pillow_sees_it(self, site, client):
        r = client.post("/admin/articles/api-big/image",
                        files={"file": ("huge.png", b"x" * (9 * 1024 * 1024), "image/png")},
                        auth=AUTH)
        assert r.status_code == 413
