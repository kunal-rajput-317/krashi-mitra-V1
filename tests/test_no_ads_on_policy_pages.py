"""No ads on the legal pages — owner's rule, 2026-09-26.

/terms and /privacy-policy are where a reader decides whether to trust the
site. Two things would put an ad there, and both are pinned:

* the page's own HTML loading adsbygoogle.js — that alone switches on Google
  Auto ads, whatever ads.js decides;
* ads.js (bootstrapped by drawer-menu.js on every page) not listing the path
  in its OFF rule.
"""
import re

import pytest

POLICY_PAGES = ["terms", "privacy-policy"]


@pytest.mark.parametrize("page", POLICY_PAGES)
def test_the_page_does_not_load_adsense(repo_root, page):
    html = (repo_root / "frontend" / f"{page}.html").read_text(encoding="utf-8")
    assert "adsbygoogle" not in html, f"{page}.html loads AdSense (Auto ads)"
    assert "googlesyndication" not in html


@pytest.mark.parametrize("path", ["/terms", "/terms.html", "/privacy-policy",
                                  "/privacy-policy.html", "/terms/"])
def test_ads_js_skips_the_page(repo_root, path):
    src = (repo_root / "frontend" / "ads.js").read_text(encoding="utf-8")
    m = re.search(r"var OFF = /(.+)/;", src)
    assert m, "ads.js OFF rule not found"
    assert re.match(m.group(1).replace("\\/", "/"), path), f"ads.js would run on {path}"


def test_the_loader_itself_refuses_a_no_ads_page(repo_root):
    """Auto ads needs adsbygoogle.js on the page; the only code that injects it
    must check OFF itself, not rely on its caller having checked."""
    src = (repo_root / "frontend" / "ads.js").read_text(encoding="utf-8")
    body = src[src.index("function loader()"):]
    body = body[:body.index("\n  }\n")]
    assert "OFF.test(location.pathname)" in body


# The privacy policy promises "no ads on /terms, this policy, and every /pay
# page". These keep the promise and the code in step.

@pytest.mark.parametrize("path", ["/pay", "/pay/listing/x", "/pay/tick/X", "/pay/link/a.b"])
def test_pay_pages_are_ad_free(client, repo_root, path):
    assert "adsbygoogle" not in client.get(path).text, f"{path} loads AdSense"
    src = (repo_root / "frontend" / "ads.js").read_text(encoding="utf-8")
    m = re.search(r"var OFF = /(.+)/;", src)
    assert re.match(m.group(1).replace("\/", "/"), path)


def test_the_policies_say_what_the_code_does(repo_root):
    privacy = (repo_root / "frontend" / "privacy-policy.html").read_text(encoding="utf-8")
    assert "इन पेजों पर कोई विज्ञापन नहीं दिखाया जाता" in privacy
    assert "पेमेंट लिंक" in privacy, "the payer name a payment link can carry is not disclosed"
    terms = (repo_root / "frontend" / "terms.html").read_text(encoding="utf-8")
    assert 'id="payment-terms"' in terms
    assert "दान (donation) नहीं लेता" in terms
