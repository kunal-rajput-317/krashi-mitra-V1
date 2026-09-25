"""/pay as one universal payment URL (2026-09-26), and /donate removed.

What this pins:

* **/pay is a hub, never a QR.** It lists the ways to pay and names nobody, so
  it may carry no upi:// link, no QR and no UPI ID. Money with no payer
  attached cannot be matched to a row.
* **Every /pay/{source}/{key} page is attributed.** Unknown source, unknown
  key, forged token → the same dead end, never a generic fee.
* **Custom links are signed.** The page prints the owner's text on our domain;
  an editable one could be turned into a fake scheme fee under our name.
* **Old links keep working.** /pay?d=<slug> is in dealers' WhatsApp chats.
* **/donate is gone** — 410, off the sitemap, out of every footer.
"""

import importlib
from datetime import datetime

import pytest

from backend.services import dealers

ADMIN = ("testadmin", "test-admin-pass")
_PAY_QR = 'class="pay-qr"'
TICK_EMAIL = "paylinks-tick@example.com"
BANNED_CLAIMS = ["सत्यापित", "verified by", "पहचान जाँच ली", "पहचान जाँची"]
NEVER_PAID = ("पेमेंट हो गया", "भुगतान सफल", "payment successful", "paid successfully")


@pytest.fixture()
def upi(monkeypatch):
    monkeypatch.setenv("KM_UPI_ID", "kunal@okhdfcbank")
    monkeypatch.setenv("KM_UPI_NAME", "KrashiMitra")
    monkeypatch.setenv("KM_LISTING_FEE", "500")
    from backend.services import upi as upi_mod
    return importlib.reload(upi_mod)


@pytest.fixture()
def clean(db_session):
    from backend.database.db import Buyer
    from backend.services import buyers
    db_session.query(Buyer).delete()
    db_session.commit()
    buyers.invalidate()
    yield db_session
    db_session.query(Buyer).delete()
    db_session.commit()
    buyers.invalidate()


@pytest.fixture()
def dealer(clean):
    return dealers.create(clean, {
        "name": "Sharma Traders", "district": "Hardoi", "state": "Uttar Pradesh",
        "phone": "9876543210", "kind": "trader", "commodities": ["wheat"],
    })


@pytest.fixture()
def tick_row(db_session):
    """A blue-tick application in the `applied` state, for a throwaway user."""
    from sqlalchemy import func

    from backend.database.db import SellerVerification, User, UserProfile
    from backend.services import seller_verify

    def _wipe():
        rows = db_session.query(User).filter(User.email == TICK_EMAIL).all()
        ids = [u.id for u in rows]
        accts = [u.user_id for u in rows if u.user_id is not None]
        if ids:
            db_session.query(SellerVerification).filter(
                SellerVerification.user_id.in_(ids)).delete(synchronize_session=False)
            if accts:
                db_session.query(UserProfile).filter(
                    UserProfile.user_id.in_(accts)).delete(synchronize_session=False)
            db_session.query(User).filter(User.id.in_(ids)).delete(synchronize_session=False)
            db_session.commit()

    _wipe()
    user = User(name="Pay Links", email=TICK_EMAIL, hashed_password="x",
                is_verified=True, created_at=datetime.utcnow())
    db_session.add(user)
    db_session.commit()
    n = (db_session.query(func.max(UserProfile.id)).scalar() or 0) + 1
    user.user_id = n
    db_session.add(UserProfile(id=n, user_id=n, name="Pay Links", phone_number="9870900222",
                               state="Uttar Pradesh", district="Hardoi", village="Rampur"))
    db_session.commit()
    row = seller_verify.apply(db_session, user.id, {
        "full_name": "गोपाल वर्मा", "phone": "9870900222", "village": "रामपुर",
        "district": "हरदोई", "state": "Uttar Pradesh", "plan": "m3"})
    yield row
    _wipe()


# ── The hub ─────────────────────────────────────────────────

class TestHub:
    def test_lists_every_way_to_pay(self, upi, client):
        t = client.get("/pay").text
        for href in ("/verify", "/dukanlisting", "/sponsor"):
            assert f'href="{href}"' in t, href
        assert "नीला टिक" in t and "कृषि दुकान" in t and "किराये की मशीन" in t

    def test_prices_come_from_the_rate_cards(self, upi, client):
        from backend.services import placements, seller_verify
        t = client.get("/pay").text
        for p in seller_verify.plans():
            assert f"₹{p['price']}" in t
        assert f"₹{placements.PRICE_DISTRICT} प्रति ज़िला" in t

    def test_carries_no_qr_no_link_and_no_vpa(self, upi, client):
        t = client.get("/pay").text
        assert "upi://pay?" not in t
        assert _PAY_QR not in t
        assert upi.vpa() not in t

    def test_is_noindex_and_never_calls_the_tick_a_check(self, upi, client):
        t = client.get("/pay").text
        assert "noindex" in t
        for word in BANNED_CLAIMS:
            assert word not in t, word

    def test_old_dealer_links_redirect(self, upi, dealer, client):
        r = client.get(f"/pay?d={dealer.slug}&amount=249", follow_redirects=False)
        assert r.status_code == 301
        assert r.headers["location"] == f"/pay/listing/{dealer.slug}?amount=249"
        r = client.get(f"/pay?d={dealer.slug}", follow_redirects=False)
        assert r.headers["location"] == f"/pay/listing/{dealer.slug}"


# ── One payer per page ──────────────────────────────────────

class TestPayerPages:
    @pytest.mark.parametrize("path", [
        "/pay/nonsense/abc", "/pay/listing/nobody-here", "/pay/dukan/nobody-here",
        "/pay/rent/nobody-here", "/pay/sponsor/nobody-here", "/pay/tick/NOPE00",
        "/pay/link/forged.token",
    ])
    def test_unknown_payer_gets_no_payable_page(self, upi, client, path):
        r = client.get(path)
        assert r.status_code == 200
        assert "upi://pay?" not in r.text, path
        assert _PAY_QR not in r.text, path
        assert "अधूरा" in r.text

    def test_listing_page_carries_the_source_in_the_reference(self, upi, dealer, client):
        t = client.get(f"/pay/listing/{dealer.slug}").text
        assert _PAY_QR in t
        assert f"tr=listing-{dealer.slug}"[:38] in t
        for claim in NEVER_PAID:
            assert claim not in t

    def test_tick_page_charges_the_plan_and_hides_the_name(self, upi, tick_row, client):
        from backend.services import seller_verify
        t = client.get(f"/pay/tick/{tick_row.ref}").text
        assert _PAY_QR in t
        assert f"₹{seller_verify.plan('m3')['price']}" in t
        assert tick_row.ref in t
        assert "गोपाल" not in t, "a member's name was printed on a public URL"
        assert "गारंटी नहीं है" in t
        for word in BANNED_CLAIMS:
            assert word not in t, word

    def test_verify_pay_pack_offers_the_page(self, upi, tick_row, client):
        d = client.get(f"/verify/pay/{tick_row.ref}").json()["data"]
        assert d["pay_url"].endswith(f"/pay/tick/{tick_row.ref}")
        assert "verify" not in d["note"].lower()

    def test_ads_script_skips_every_pay_page(self, repo_root):
        src = (repo_root / "frontend" / "ads.js").read_text(encoding="utf-8")
        assert "|pay|" in src and "(\\/|$)" in src


# ── Custom signed links ─────────────────────────────────────

class TestCustomLinks:
    def _make(self, client, **body):
        body = {"amount": "750", "purpose": "6 महीने की दुकान लिस्टिंग",
                "payer": "राम खाद भंडार", **body}
        return client.post("/admin/pay/link", json=body, auth=ADMIN)

    def test_requires_admin(self, upi, client):
        assert client.post("/admin/pay/link", json={"amount": 5}).status_code == 401

    def test_round_trip_shows_exactly_what_was_typed(self, upi, client):
        d = self._make(client).json()
        assert d["url"].startswith("https://krashimitra.in/pay/link/")
        assert d["qr_svg"] and d["link"].startswith("upi://pay?")
        assert "₹750" in d["whatsapp"] and d["url"] in d["whatsapp"]
        t = client.get(d["url"].replace("https://krashimitra.in", "")).text
        assert 'class="pay-amt">₹750<' in t
        assert "6 महीने की दुकान लिस्टिंग" in t and "राम खाद भंडार" in t
        assert d["ref"] in t

    def test_an_edited_token_is_refused(self, upi, client):
        d = self._make(client).json()
        body, sig = d["token"].split(".")
        from backend.services import pay_links
        forged = pay_links._b64(pay_links._unb64(body).replace(b"750", b"999"))
        t = client.get(f"/pay/link/{forged}.{sig}").text
        assert _PAY_QR not in t and "₹999" not in t

    @pytest.mark.parametrize("bad", [{"amount": "0"}, {"amount": "abc"},
                                     {"amount": "200000"}, {"purpose": "  "}])
    def test_bad_input_is_refused(self, upi, client, bad):
        assert self._make(client, **bad).status_code == 400

    def test_off_without_a_real_secret(self, upi, client, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", "change_this_secret_in_production")
        assert self._make(client).status_code == 400

    def test_making_a_link_records_nothing(self, upi, client, db_session):
        from backend.database.db import Payment
        before = db_session.query(Payment).count()
        assert self._make(client).status_code == 200
        db_session.expire_all()
        assert db_session.query(Payment).count() == before


# ── Admin collect buttons all hand out the page ─────────────

class TestCollectPacks:
    def test_dealer_collect_points_at_the_new_url(self, upi, dealer, client):
        d = client.get(f"/admin/buyers/{dealer.slug}/collect", auth=ADMIN,
                       params={"amount": "249"}).json()
        assert d["pay_url"] == f"https://krashimitra.in/pay/listing/{dealer.slug}?amount=249"

    def test_collect_pack_has_a_reference_and_a_message(self, upi):
        from backend.services import pay_links
        p = pay_links.collect_pack("dukan", "ram-khad", "राम खाद", "Hardoi", 300, "")
        assert "tr=dukan-ram-khad" in p["link"], "the shop's UPI reference came out empty"
        assert p["pay_url"] == "https://krashimitra.in/pay/dukan/ram-khad?amount=300"
        assert p["pay_url"] in p["whatsapp_text"]
        assert p["purpose"] == "कृषि दुकान लिस्टिंग"


# ── /donate is gone ─────────────────────────────────────────

class TestDonateRemoved:
    def test_answers_410(self, client):
        r = client.get("/donate")
        assert r.status_code == 410
        assert "upi://pay?" not in r.text

    def test_not_in_the_sitemap(self, client):
        assert "/donate" not in client.get("/sitemap.xml").text

    def test_footers_link_pay_instead(self, repo_root, client):
        assert "/donate" not in client.get("/bhav").text
        js = (repo_root / "frontend" / "km-support.js").read_text(encoding="utf-8")
        assert "href: '/pay'" in js and "href: '/donate'" not in js
