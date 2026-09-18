"""The blue tick: a paid membership, and nothing more than that.

Changed 2026-09-18. The tick used to mean "KrashiMitra ने फ़ोन पर इस विक्रेता
की पहचान जाँची है", and this file's job was to stop that claim from being
quietly sold: paying could never grant the badge, only a human after a call.

The tick is now what X's blue check is — this member pays for कृषि मित्र
प्रीमियम. Payment IS the grant, so the old guard is gone and the opposite one
matters instead. The exposure did not disappear, it inverted:

  * before, the risk was selling a claim nobody checked;
  * now, the risk is a page that still DESCRIBES the badge as a check.

So what is pinned here is:

  * paying grants the badge, for the term that was actually bought — a ₹499
    3-month credit must not buy one month, and a ₹199 one must not buy three;
  * saying you paid grants nothing — /verify/paid is a button on the farmer's
    own phone, and if it could tick him the badge would be free;
  * a public form still cannot write its own status or its own payment;
  * no user-facing copy calls the tick a verification — not /verify, not the
    feed, not the WhatsApp message the owner sends to collect;
  * revoking clears the flag and owes the money back — a term cut short was
    not delivered;
  * the badge expires whether it was paid for or comped, because the feed and
    the WhatsApp preview read the flag and never see the row.
"""

import re
from datetime import datetime, timedelta

import pytest

from backend.services import seller_verify


EMAIL = "bluetick-applicant@example.com"

# Every way the site could start describing a paid badge as a checked one. The
# sweeps below look at what a farmer can READ, so they run over rendered pages
# and over source with its comments stripped — a comment that names the banned
# word in order to explain the rule is the opposite of the problem, and a sweep
# that fired on one would just teach the next person to delete the explanation.
BANNED_CLAIMS = ["सत्यापित", "verified by", "पहचान जाँच ली", "पहचान जाँची"]


def _visible(src: str) -> str:
    """Drop HTML and block comments — what is left is what ships to a reader."""
    src = re.sub(r"<!--.*?-->", "", src, flags=re.S)
    return re.sub(r"/\*.*?\*/", "", src, flags=re.S)


def _user(db_session, email=EMAIL, name="Tick Applicant"):
    from sqlalchemy import func

    from backend.database.db import User, UserProfile

    user = User(name=name, email=email, hashed_password="x",
                is_verified=True, created_at=datetime.utcnow())
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    n = (db_session.query(func.max(UserProfile.id)).scalar() or 0) + 1
    user.user_id = n
    db_session.commit()
    db_session.add(UserProfile(id=n, user_id=n, name=name, phone_number="9870900111",
                               state="Uttar Pradesh", district="Hardoi", village="Rampur"))
    db_session.commit()
    return user


@pytest.fixture()
def applicant(db_session):
    from backend.database.db import SellerVerification, User, UserProfile

    def _wipe():
        rows = db_session.query(User).filter(User.email == EMAIL).all()
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
    user = _user(db_session)
    yield user
    _wipe()


def _apply(db_session, user, **over):
    data = {"full_name": "राम सिंह", "phone": "9870900111", "village": "रामपुर",
            "district": "हरदोई", "state": "Uttar Pradesh", "id_kind": "aadhaar"}
    data.update(over)
    return seller_verify.apply(db_session, user.id, data)


def _verified(db_session, user):
    from backend.database.db import User

    db_session.expire_all()
    return bool(db_session.query(User).filter(User.id == user.id).first().seller_verified)


# ── The rule the whole feature now rests on ──────────────────

def test_paying_grants_the_badge(db_session, applicant):
    """Payment is the whole of what the badge says, so it is the grant."""
    row = _apply(db_session, applicant)
    assert not _verified(db_session, applicant), "signing up alone must not tick"

    seller_verify.record_payment(db_session, row.ref, 199, "UTR123")
    db_session.refresh(row)

    assert row.status == seller_verify.PAID
    assert row.paid_at is not None
    assert row.valid_until > datetime.utcnow()
    assert _verified(db_session, applicant)


def test_saying_you_paid_does_not_grant_the_badge(db_session, applicant):
    """/verify/paid is a button on the farmer's own phone.

    This is the guard that replaced the old one. A upi:// hand-off reports
    nothing back, so his tap is a claim, not a payment — if it could tick him,
    the badge would be free to anybody who can press a button.
    """
    row = _apply(db_session, applicant)
    seller_verify.claim_payment(db_session, applicant.id, "UTR-I-SWEAR")

    db_session.refresh(row)
    assert row.payment_claimed_at is not None
    assert row.paid_at is None
    assert row.status == seller_verify.APPLIED
    assert row.valid_until is None
    assert not _verified(db_session, applicant), (
        "a self-declared payment granted the badge — it is now free to anyone "
        "who can tap a button"
    )
    assert seller_verify.payment_claimed(row)


def test_only_four_places_write_the_flag(db_session, applicant):
    """Belt and braces: read the source, not just the behaviour.

    record_payment grants it; approve comps it; revoke and expire_due clear it.
    A fifth writer is a new way to get a tick that no test here exercises.
    """
    import inspect

    src = inspect.getsource(seller_verify)
    setters = re.findall(r"user\.seller_verified\s*=", src)
    assert len(setters) == 4, (
        f"expected seller_verified to be written in exactly 4 places "
        f"(record_payment/approve/revoke/expire_due), found {len(setters)}"
    )


def test_the_signup_form_cannot_write_its_own_status_or_payment(db_session, applicant):
    """apply() takes a dict straight off a public form.

    The fee is now the only thing between a farmer and a tick, so a form that
    could set `status` or `paid_at` would be the whole gate.
    """
    row = seller_verify.apply(db_session, applicant.id, {
        "full_name": "राम सिंह", "phone": "9870900111",
        "status": "paid", "paid_at": datetime.utcnow(),
        "payment_claimed_at": datetime.utcnow(),
        "valid_until": datetime.utcnow() + timedelta(days=999),
    })
    assert row.status == seller_verify.APPLIED
    assert row.paid_at is None
    assert row.payment_claimed_at is None
    assert row.valid_until is None
    assert not _verified(db_session, applicant)


def test_an_unknown_id_kind_falls_back_rather_than_storing_junk(db_session, applicant):
    row = _apply(db_session, applicant, id_kind="<script>alert(1)</script>")
    assert row.id_kind == "other"


# ── The two plans ────────────────────────────────────────────

def test_both_plans_are_priced_with_a_higher_struck_figure(db_session):
    plans = {p["code"]: p for p in seller_verify.plans()}
    assert plans["m1"]["months"] == 1 and plans["m1"]["price"] == 199
    assert plans["m1"]["mrp"] == 399
    assert plans["m3"]["months"] == 3 and plans["m3"]["price"] == 499
    assert plans["m3"]["mrp"] == 699
    for p in plans.values():
        assert p["mrp"] > p["price"], (
            "a struck price at or below the real one is not an anchor, it is a "
            "mistake on a page about money"
        )
        assert p["per_month"] == round(p["price"] / p["months"])


def test_the_longer_plan_is_actually_cheaper_per_month():
    """The only reason two plans exist. If this inverts, the 3-month card is
    asking a farmer to pay more for committing longer."""
    plans = {p["code"]: p for p in seller_verify.plans()}
    assert plans["m3"]["per_month"] < plans["m1"]["per_month"]


def test_a_struck_price_below_the_real_one_is_dropped(monkeypatch):
    monkeypatch.setenv("KM_VERIFY_M1_MRP", "150")
    plans = {p["code"]: p for p in seller_verify.plans()}
    assert plans["m1"]["mrp"] is None
    assert plans["m1"]["save_pct"] is None


def test_an_unknown_plan_code_buys_the_cheapest_term_not_a_free_one(db_session, applicant):
    """A junk code arrives from a request body, so it must not 500 or comp."""
    row = _apply(db_session, applicant, plan="m99")
    assert row.plan == "m1"
    assert row.fee_amount == 199


def test_paying_buys_the_term_that_was_chosen(db_session, applicant):
    """A ₹499 credit has to buy three months, or the cheaper plan is better."""
    row = _apply(db_session, applicant, plan="m3")
    assert row.fee_amount == 499
    seller_verify.record_payment(db_session, row.ref, 499)
    db_session.refresh(row)

    days = (row.valid_until - datetime.utcnow()).days
    assert 85 <= days <= 92, f"3-month plan bought {days} days"

    other = _user(db_session, "bluetick-monthly@example.com", "Monthly Member")
    try:
        m = seller_verify.apply(db_session, other.id, {"full_name": "x", "plan": "m1"})
        seller_verify.record_payment(db_session, m.ref, 199)
        db_session.refresh(m)
        assert (m.valid_until - datetime.utcnow()).days <= 31
    finally:
        from backend.database.db import SellerVerification, User, UserProfile
        db_session.query(SellerVerification).filter(
            SellerVerification.user_id == other.id).delete(synchronize_session=False)
        db_session.query(UserProfile).filter(
            UserProfile.user_id == other.user_id).delete(synchronize_session=False)
        db_session.query(User).filter(User.id == other.id).delete(synchronize_session=False)
        db_session.commit()


def test_renewing_early_does_not_lose_the_days_already_paid_for(db_session, applicant):
    row = _apply(db_session, applicant)
    first = seller_verify.record_payment(db_session, row.ref, 199)
    end_1 = first.valid_until
    second = seller_verify.record_payment(db_session, row.ref, 199)
    assert second.valid_until > end_1, "an early renewal reset the clock instead of extending it"


# ── The comp, the kill switch, the refund ────────────────────

def test_approve_comps_a_membership_without_a_payment(db_session, applicant):
    row = _apply(db_session, applicant)
    out = seller_verify.approve(db_session, row.ref, by="owner")

    assert out.status == seller_verify.APPROVED
    assert out.paid_at is None, "a comp must not look like a payment in the books"
    assert out.valid_until > datetime.utcnow()
    assert out.reviewed_by == "owner"
    assert _verified(db_session, applicant)
    assert seller_verify.is_active(out)


def test_revoking_takes_the_badge_back_and_owes_a_refund(db_session, applicant):
    row = _apply(db_session, applicant)
    seller_verify.record_payment(db_session, row.ref, 199)
    assert _verified(db_session, applicant)

    out = seller_verify.revoke(db_session, row.ref, reason="किसी और के नाम से खाता")
    assert out.status == seller_verify.REJECTED
    assert out.valid_until is None
    assert not _verified(db_session, applicant)
    assert seller_verify.refund_due(out), "a term cut short was not delivered"

    seller_verify.record_refund(db_session, row.ref)
    db_session.refresh(out)
    assert not seller_verify.refund_due(out)


def test_revoking_an_unpaid_comp_owes_nothing(db_session, applicant):
    row = _apply(db_session, applicant)
    seller_verify.approve(db_session, row.ref)
    out = seller_verify.revoke(db_session, row.ref, reason="धोखाधड़ी")
    assert not seller_verify.refund_due(out)


def test_reapplying_after_a_revoke_starts_clean(db_session, applicant):
    row = _apply(db_session, applicant)
    seller_verify.revoke(db_session, row.ref, reason="गाँव मेल नहीं खाया")
    again = _apply(db_session, applicant)
    assert again.status == seller_verify.APPLIED
    assert again.reject_reason is None
    assert again.ref == row.ref, "the reference must survive — it is the thread to the bank credit"


# ── Expiry ───────────────────────────────────────────────────

@pytest.mark.parametrize("grant", ["paid", "comped"])
def test_the_badge_expires_and_the_flag_goes_with_it(db_session, applicant, grant):
    """The feed and the WhatsApp preview read users.seller_verified directly
    and never see this row, so the sweep is what keeps the badge honest.

    Both ways of holding a live badge are swept: filtering on `approved` alone
    would have left every PAYING member ticked forever.
    """
    row = _apply(db_session, applicant)
    if grant == "paid":
        seller_verify.record_payment(db_session, row.ref, 199)
    else:
        seller_verify.approve(db_session, row.ref)
    row.valid_until = datetime.utcnow() - timedelta(days=1)
    db_session.commit()

    assert seller_verify.expire_due(db_session) == 1
    db_session.refresh(row)
    assert row.status == seller_verify.EXPIRED
    assert not _verified(db_session, applicant)
    assert not seller_verify.is_active(row)


def test_the_sweep_is_idempotent(db_session, applicant):
    row = _apply(db_session, applicant)
    seller_verify.record_payment(db_session, row.ref, 199)
    row.valid_until = datetime.utcnow() - timedelta(days=1)
    db_session.commit()
    assert seller_verify.expire_due(db_session) == 1
    assert seller_verify.expire_due(db_session) == 0


def test_a_live_badge_is_left_alone(db_session, applicant):
    row = _apply(db_session, applicant)
    seller_verify.record_payment(db_session, row.ref, 199)
    assert seller_verify.expire_due(db_session) == 0
    assert _verified(db_session, applicant)


def test_the_expiry_sweep_is_actually_scheduled():
    """Without a timer the badge only expires when the member happens to open
    his own page — while the feed keeps showing the tick he stopped paying for."""
    import inspect

    from backend.services import mandi_scheduler

    src = inspect.getsource(mandi_scheduler)
    assert "_expire_badges" in src
    assert "seller_badge_expiry" in src


# ── The reference ────────────────────────────────────────────

def test_the_reference_is_readable_off_a_phone_screen(db_session, applicant):
    """Somebody matches a bank credit to a membership by typing this in."""
    row = _apply(db_session, applicant)
    assert row.ref.startswith("KMV") and len(row.ref) == 10
    assert not (set(row.ref) & set("01OI")), "0/O and 1/I are unreadable in a statement search"


def test_by_ref_is_case_insensitive(db_session, applicant):
    row = _apply(db_session, applicant)
    assert seller_verify.by_ref(db_session, row.ref.lower()) is not None
    assert seller_verify.by_ref(db_session, "  " + row.ref + "  ") is not None
    assert seller_verify.by_ref(db_session, "") is None


# ── The page ─────────────────────────────────────────────────

def test_the_page_is_noindex(client):
    r = client.get("/verify")
    assert r.status_code == 200
    assert "noindex" in r.text


def test_the_page_never_calls_the_badge_a_verification(client):
    """The guard that replaced "the fee buys the check".

    A paid badge described as a check is a claim about a named person that
    nobody makes — the same exposure as before, arrived at from the other side.
    """
    body = client.get("/verify").text
    for word in BANNED_CLAIMS:
        assert word not in body, f"/verify calls the paid badge a check: {word!r}"


def test_the_page_says_what_the_tick_is_not(client):
    """Saying nothing would leave a buyer to assume. It has to be explicit."""
    body = client.get("/verify").text
    assert "प्रीमियम" in body
    assert "गारंटी नहीं" in body


def test_the_page_never_claims_a_payment_happened(client):
    """A upi:// hand-off reports nothing back; a page that printed a receipt
    off a tapped link would be inventing one."""
    body = client.get("/verify").text
    assert "पेमेंट हो गया" not in body
    assert "भुगतान हो गया" not in body


def test_the_page_offers_both_plans_with_their_struck_prices(client):
    body = client.get("/verify").text
    for figure in ("199", "399", "499", "699"):
        assert figure in body, f"/verify does not print ₹{figure}"


def test_the_plans_endpoint_is_public_and_carries_no_personal_data(client):
    """krashi_bajar.html is a static file and asks for the prices."""
    r = client.get("/verify/plans")
    assert r.status_code == 200
    plans = r.json()["data"]["plans"]
    assert {p["code"] for p in plans} == {"m1", "m3"}
    assert all("price" in p and "mrp" in p for p in plans)


def test_applying_needs_a_login(client):
    assert client.post("/verify/apply", json={"full_name": "x"}).status_code in (401, 403)


def test_claiming_a_payment_needs_a_login(client):
    """Otherwise it is an unauthenticated write on somebody else's row."""
    assert client.post("/verify/paid", json={}).status_code in (401, 403)


def test_a_reachable_number_is_required(client, db_session, applicant):
    """Not a check — the only way to reach him about a renewal or a refund."""
    from backend.utils.auth_utils import create_access_token

    h = {"Authorization": f"Bearer {create_access_token(applicant.id, applicant.email)}"}
    r = client.post("/verify/apply", headers=h,
                    json={"full_name": "राम सिंह", "phone": "123"})
    assert r.status_code == 400


def test_claiming_a_payment_over_http_still_does_not_tick(client, db_session, applicant):
    """The same guard as the service, at the HTTP edge."""
    from backend.utils.auth_utils import create_access_token

    _apply(db_session, applicant)
    h = {"Authorization": f"Bearer {create_access_token(applicant.id, applicant.email)}"}
    r = client.post("/verify/paid", headers=h, json={"paid_ref": "UTR999"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["payment_claimed"] is True
    assert not _verified(db_session, applicant)


def test_the_pay_pack_carries_the_ref_but_no_personal_data(client, db_session, applicant):
    row = _apply(db_session, applicant)
    d = client.get(f"/verify/pay/{row.ref}").json()["data"]
    assert d["ref"] == row.ref
    assert row.ref in d["note"]
    blob = str(d)
    for private in ("राम सिंह", "9870900111", EMAIL):
        assert private not in blob, f"{private} leaked onto a ref-addressable endpoint"


# ── The feed's own copy ──────────────────────────────────────

def test_the_bazar_page_does_not_describe_the_tick_as_a_check():
    """krashi_bajar.html is where a BUYER reads what the tick means, in three
    languages. It is the page the old claim was published on."""
    import io
    from pathlib import Path

    html = io.open(Path(__file__).resolve().parents[1] / "frontend" / "krashi_bajar.html",
                   encoding="utf-8").read()
    for word in BANNED_CLAIMS:
        assert word not in _visible(html), (
            f"the feed still calls the paid tick a check: {word!r}")
    # And it must still say what the badge is NOT — in every language it offers.
    assert "गारंटी नहीं" in html
    assert "not a guarantee" in html
    assert "ಖಾತರಿಯಲ್ಲ" in html


def test_the_bazar_page_offers_the_tick_inside_the_feed():
    """Below the feed AND below "और देखें" is a place nobody arrives at on an
    infinite list — which is where the only offer used to be."""
    import io
    from pathlib import Path

    html = io.open(Path(__file__).resolve().parents[1] / "frontend" / "krashi_bajar.html",
                   encoding="utf-8").read()
    assert "withTickCta(" in html
    assert "tickCtaHtml()" in html
    assert "bz-tickcta" in html
    # Priced from the server, never from literals in the page.
    assert "/verify/plans" in html
    assert "is-verified" in html, "the ocean ring is never applied to an avatar"


def test_the_profile_page_shows_the_membership():
    import io
    from pathlib import Path

    html = io.open(Path(__file__).resolve().parents[1] / "frontend" / "profile.html",
                   encoding="utf-8").read()
    assert "loadTickStatus" in html
    assert "pf-tick" in html
    assert "/verify/me" in html
    assert "is-verified" in html, "a member's own avatar never gets the ring"
    for word in BANNED_CLAIMS:
        assert word not in _visible(html), (
            f"/profile calls the paid tick a check: {word!r}")


# ── The admin queue ──────────────────────────────────────────

AUTH = ("testadmin", "test-admin-pass")


def test_the_queue_needs_admin_credentials(client):
    assert client.get("/admin/verifications").status_code == 401


def test_a_new_signup_shows_up_with_its_payment_pending(client, db_session, applicant):
    """The owner has to be able to see money that has not arrived."""
    row = _apply(db_session, applicant, plan="m3")
    d = client.get("/admin/verifications", auth=AUTH).json()["data"]

    mine = [i for i in d["items"] if i["ref"] == row.ref]
    assert len(mine) == 1
    item = mine[0]
    assert item["status"] == seller_verify.APPLIED
    assert item["pay_status"] == "pending"
    assert item["verified_now"] is False
    assert item["active"] is False
    assert item["plan"] == "m3"
    assert item["fee_amount"] == 499
    assert item["phone"] == "9870900111"


def test_a_claimed_payment_shows_as_claimed_and_sorts_to_the_top(client, db_session, applicant):
    """The one state where somebody is waiting on us."""
    row = _apply(db_session, applicant)
    seller_verify.claim_payment(db_session, applicant.id, "UTR55")

    d = client.get("/admin/verifications", auth=AUTH).json()["data"]
    item = [i for i in d["items"] if i["ref"] == row.ref][0]
    assert item["pay_status"] == "claimed"
    assert item["verified_now"] is False
    assert d["items"][0]["ref"] == row.ref, "a waiting payment was not at the top"
    assert d["awaiting_confirm"] >= 1


def test_recording_the_payment_through_the_panel_grants_the_tick(client, db_session, applicant):
    """This is the endpoint somebody will be clicking while money arrives."""
    row = _apply(db_session, applicant)
    r = client.post(f"/admin/verifications/{row.ref}/payment",
                    json={"amount": 199, "ref": "UTR77"}, auth=AUTH)
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["status"] == seller_verify.PAID
    assert body["active"] is True
    assert body["days_left"] is not None
    assert _verified(db_session, applicant)

    after = client.get("/admin/verifications", auth=AUTH).json()["data"]
    item = [i for i in after["items"] if i["ref"] == row.ref][0]
    assert item["pay_status"] == "received"


def test_a_payment_of_nothing_is_refused(client, db_session, applicant):
    row = _apply(db_session, applicant)
    r = client.post(f"/admin/verifications/{row.ref}/payment",
                    json={"amount": 0}, auth=AUTH)
    assert r.status_code == 400
    assert not _verified(db_session, applicant)


def test_approve_is_the_comp_and_leaves_the_books_alone(client, db_session, applicant):
    row = _apply(db_session, applicant)
    r = client.post(f"/admin/verifications/{row.ref}/approve", json={}, auth=AUTH)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == seller_verify.APPROVED
    assert _verified(db_session, applicant)
    db_session.refresh(row)
    assert row.paid_at is None


def test_revoking_through_the_panel_clears_the_tick(client, db_session, applicant):
    row = _apply(db_session, applicant)
    client.post(f"/admin/verifications/{row.ref}/payment", json={"amount": 199}, auth=AUTH)
    r = client.post(f"/admin/verifications/{row.ref}/reject",
                    json={"reason": "किसी और के नाम से खाता"}, auth=AUTH)
    assert r.json()["data"] == {"status": seller_verify.REJECTED, "refund_due": True}
    assert not _verified(db_session, applicant)


def test_the_collect_message_sells_a_membership_not_a_check(client, db_session, applicant):
    """A WhatsApp message is as public a claim as a web page."""
    row = _apply(db_session, applicant, plan="m3")
    d = client.get(f"/admin/verifications/{row.ref}/collect", auth=AUTH).json()["data"]
    assert row.ref in d["whatsapp"]
    assert str(d["amount"]) in d["whatsapp"]
    assert "प्रीमियम" in d["whatsapp"]
    assert "गारंटी नहीं है" in d["whatsapp"]
    for word in BANNED_CLAIMS:
        assert word not in d["whatsapp"], f"the collect message promises a check: {word!r}"


def test_unknown_refs_404_rather_than_creating_anything(client):
    for path, method in [("payment", "post"), ("approve", "post"),
                         ("reject", "post"), ("refund", "post"), ("collect", "get")]:
        call = getattr(client, method)
        kw = {"json": {"amount": 199}} if method == "post" else {}
        r = call(f"/admin/verifications/KMVZZZZZZZ/{path}", auth=AUTH, **kw)
        assert r.status_code == 404, f"{path} -> {r.status_code}"


def test_the_admin_panel_has_the_tab_wired_up():
    """A queue nobody can open is a queue nobody works."""
    import io
    from pathlib import Path

    html = io.open(Path(__file__).resolve().parents[1] / "admin" / "index.html",
                   encoding="utf-8").read()
    assert "switchPage('verifications'" in html
    assert 'id="page-verifications"' in html
    assert "if (pageId === 'verifications') loadVerifications();" in html
    # ₹ मिला is now the grant, so its confirm is the control on the screen.
    assert "बैंक ऐप में पैसा आया हुआ दिख रहा है?" in html
    # And the panel must show the payment state, not just the membership state.
    assert "VF_PAY" in html
    assert "awaiting_confirm" in html


def test_a_failed_queue_load_is_not_reported_as_an_empty_queue():
    """The panel said "कोई आवेदन नहीं" while two applications sat in the DB.

    loadVerifications() only treated a 404 as a failure; every other bad
    response fell through to `(j.data && j.data.items) || []`, so a 401 on an
    expired admin token — or a 502 while Render was cold — emptied the list and
    painted the empty state. The owner then had no way to tell "nobody has
    applied" from "the request did not answer", which is the difference between
    doing nothing and losing a paying member.
    """
    import io
    from pathlib import Path

    html = io.open(Path(__file__).resolve().parents[1] / "admin" / "index.html",
                   encoding="utf-8").read()
    start = html.index("async function loadVerifications()")
    fn = html[start:html.index("function renderVerifications()", start)]

    assert "if (!r.ok)" in fn, "a non-200 response is still treated as data"
    assert "!j.data) throw" in fn, "a body with no data is still treated as data"
    # The badge must not be written from a filtered view, or asking for
    # "चालू (भुगतान)" would report that nobody is waiting on a payment.
    assert "badge && !_vfFilter" in fn
    # And the failure text has to deny the empty-queue reading out loud.
    assert "यह \"कोई आवेदन नहीं\" नहीं है" in fn

    # The empty state itself must distinguish the two nothings.
    render = html[html.index("function renderVerifications()"):]
    assert "इस छाँट में कोई नहीं" in render
    assert "अभी तक कोई आवेदन नहीं आया।" in render
