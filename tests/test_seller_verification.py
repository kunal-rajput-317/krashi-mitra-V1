"""The blue tick: paid for, but never sold.

krashi_bajar.html tells every buyer that a ticked seller was checked BY
KrashiMitra. That is a claim this site publishes about a named person, on a
page where money changes hands, and the project's standing rule is that it
never takes on a claim it would have to defend. The claim is only safe while
it is true — so the fee buys the review and a human grants the badge.

What is pinned here is every way that could quietly stop being true:

  * paying must never set users.seller_verified — not through the service, not
    through the admin endpoint that records the money;
  * a public form must never be able to write its own status;
  * a refused application clears the tick and owes the money back;
  * the badge expires, because a seller checked once is not verified forever,
    and both the feed and the WhatsApp preview read the flag without ever
    seeing the row that knows the window closed.
"""

from datetime import datetime, timedelta

import pytest

from backend.services import seller_verify


EMAIL = "bluetick-applicant@example.com"


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


# ── The rule the whole feature rests on ──────────────────────

def test_paying_does_not_grant_the_badge(db_session, applicant):
    """The fee buys the review. This is the test that stops the badge from
    becoming a thing you can simply buy."""
    row = _apply(db_session, applicant)
    seller_verify.record_payment(db_session, row.ref, 199, "UTR123")

    db_session.refresh(row)
    assert row.status == seller_verify.PAID
    assert row.paid_at is not None
    assert not _verified(db_session, applicant), (
        "payment set seller_verified — the site would now be publishing "
        "'verified by KrashiMitra' about someone nobody checked"
    )


def test_only_approve_touches_the_flag(db_session, applicant):
    """Belt and braces on the above: read the source, not just the behaviour.

    A future edit could grant the badge from some new code path that this
    file's other tests never call.
    """
    import inspect
    import re

    src = inspect.getsource(seller_verify)
    setters = [m for m in re.finditer(r"user\.seller_verified\s*=", src)]
    assert len(setters) == 3, (
        f"expected seller_verified to be written in exactly 3 places "
        f"(approve/reject/expire_due), found {len(setters)}"
    )
    # And none of them is inside record_payment. Docstrings and comments are
    # stripped first: that function's docstring explains that it does not touch
    # the flag, and saying so is not doing so.
    pay_code = re.sub(r'""".*?"""', "", inspect.getsource(seller_verify.record_payment),
                      flags=re.S)
    pay_code = re.sub(r"#[^\n]*", "", pay_code)
    assert "seller_verified" not in pay_code


def test_the_application_form_cannot_write_its_own_status(db_session, applicant):
    """apply() takes a dict straight off a public form."""
    row = seller_verify.apply(db_session, applicant.id, {
        "full_name": "राम सिंह", "phone": "9870900111",
        "status": "approved", "paid_at": datetime.utcnow(),
        "valid_until": datetime.utcnow() + timedelta(days=999),
    })
    assert row.status == seller_verify.APPLIED
    assert row.paid_at is None
    assert row.valid_until is None
    assert not _verified(db_session, applicant)


def test_an_unknown_id_kind_falls_back_rather_than_storing_junk(db_session, applicant):
    row = _apply(db_session, applicant, id_kind="<script>alert(1)</script>")
    assert row.id_kind == "other"


# ── Approval, rejection, refund ──────────────────────────────

def test_approve_grants_the_badge_with_an_end_date(db_session, applicant):
    row = _apply(db_session, applicant)
    seller_verify.record_payment(db_session, row.ref, 199)
    out = seller_verify.approve(db_session, row.ref, by="owner")

    assert out.status == seller_verify.APPROVED
    assert out.valid_until > datetime.utcnow()
    assert out.reviewed_by == "owner"
    assert _verified(db_session, applicant)


def test_renewing_early_does_not_lose_the_days_already_paid_for(db_session, applicant):
    row = _apply(db_session, applicant)
    first = seller_verify.approve(db_session, row.ref)
    end_1 = first.valid_until
    second = seller_verify.approve(db_session, row.ref)
    assert second.valid_until > end_1, "an early renewal reset the clock instead of extending it"


def test_rejecting_takes_the_badge_back_and_owes_a_refund(db_session, applicant):
    row = _apply(db_session, applicant)
    seller_verify.record_payment(db_session, row.ref, 199)
    seller_verify.approve(db_session, row.ref)
    assert _verified(db_session, applicant)

    out = seller_verify.reject(db_session, row.ref, reason="नंबर किसी और का निकला")
    assert out.status == seller_verify.REJECTED
    assert out.valid_until is None
    assert not _verified(db_session, applicant)
    assert seller_verify.refund_due(out), "a paid application refused a badge is owed its money"

    seller_verify.record_refund(db_session, row.ref)
    db_session.refresh(out)
    assert not seller_verify.refund_due(out)


def test_an_unpaid_rejection_owes_nothing(db_session, applicant):
    row = _apply(db_session, applicant)
    out = seller_verify.reject(db_session, row.ref, reason="फ़ोन नहीं उठा")
    assert not seller_verify.refund_due(out)


def test_reapplying_after_rejection_starts_clean(db_session, applicant):
    row = _apply(db_session, applicant)
    seller_verify.reject(db_session, row.ref, reason="गाँव मेल नहीं खाया")
    again = _apply(db_session, applicant)
    assert again.status == seller_verify.APPLIED
    assert again.reject_reason is None
    assert again.ref == row.ref, "the reference must survive — it is the thread to the bank credit"


# ── Expiry ───────────────────────────────────────────────────

def test_the_badge_expires_and_the_flag_goes_with_it(db_session, applicant):
    """The feed and the WhatsApp preview read users.seller_verified directly
    and never see this row, so the sweep is what keeps the claim current."""
    row = _apply(db_session, applicant)
    seller_verify.approve(db_session, row.ref)
    row.valid_until = datetime.utcnow() - timedelta(days=1)
    db_session.commit()

    assert seller_verify.expire_due(db_session) == 1
    db_session.refresh(row)
    assert row.status == seller_verify.EXPIRED
    assert not _verified(db_session, applicant)


def test_the_sweep_is_idempotent(db_session, applicant):
    row = _apply(db_session, applicant)
    seller_verify.approve(db_session, row.ref)
    row.valid_until = datetime.utcnow() - timedelta(days=1)
    db_session.commit()
    assert seller_verify.expire_due(db_session) == 1
    assert seller_verify.expire_due(db_session) == 0


def test_a_live_badge_is_left_alone(db_session, applicant):
    row = _apply(db_session, applicant)
    seller_verify.approve(db_session, row.ref)
    assert seller_verify.expire_due(db_session) == 0
    assert _verified(db_session, applicant)


def test_the_expiry_sweep_is_actually_scheduled():
    """Without a timer the badge only expires when the seller happens to open
    his own page — while the feed keeps asserting he is verified."""
    import inspect

    from backend.services import mandi_scheduler

    src = inspect.getsource(mandi_scheduler)
    assert "_expire_badges" in src
    assert "seller_badge_expiry" in src


# ── The reference ────────────────────────────────────────────

def test_the_reference_is_readable_off_a_phone_screen(db_session, applicant):
    """Somebody matches a bank credit to an application by typing this in."""
    row = _apply(db_session, applicant)
    assert row.ref.startswith("KMV") and len(row.ref) == 10
    assert not (set(row.ref) & set("01OI")), "0/O and 1/I are unreadable in a statement search"


def test_by_ref_is_case_insensitive(db_session, applicant):
    row = _apply(db_session, applicant)
    assert seller_verify.by_ref(db_session, row.ref.lower()) is not None
    assert seller_verify.by_ref(db_session, "  " + row.ref + "  ") is not None
    assert seller_verify.by_ref(db_session, "") is None


# ── The routes ───────────────────────────────────────────────

def test_the_page_is_noindex(client):
    r = client.get("/verify")
    assert r.status_code == 200
    assert "noindex" in r.text
    # And it must not promise the badge for money.
    assert "शुल्क सत्यापन की जाँच का है, टिक का नहीं" in r.text


def test_the_page_never_claims_a_payment_happened(client):
    """A upi:// hand-off reports nothing back; a page that printed a receipt
    off a tapped link would be inventing one."""
    body = client.get("/verify").text
    assert "पेमेंट हो गया" not in body
    assert "भुगतान हो गया" not in body


def test_applying_needs_a_login(client):
    assert client.post("/verify/apply", json={"full_name": "x"}).status_code in (401, 403)


def test_a_reachable_number_is_required(client, db_session, applicant):
    """The entire check is a phone call."""
    from backend.utils.auth_utils import create_access_token

    h = {"Authorization": f"Bearer {create_access_token(applicant.id, applicant.email)}"}
    r = client.post("/verify/apply", headers=h,
                    json={"full_name": "राम सिंह", "phone": "123"})
    assert r.status_code == 400


def test_the_pay_pack_carries_the_ref_but_no_personal_data(client, db_session, applicant):
    row = _apply(db_session, applicant)
    d = client.get(f"/verify/pay/{row.ref}").json()["data"]
    assert d["ref"] == row.ref
    assert row.ref in d["note"]
    blob = str(d)
    for private in ("राम सिंह", "9870900111", EMAIL):
        assert private not in blob, f"{private} leaked onto a ref-addressable endpoint"


# ── The admin queue ──────────────────────────────────────────
# The panel is the human half of the claim: the only place the tick is granted.

AUTH = ("testadmin", "test-admin-pass")


def test_the_queue_needs_admin_credentials(client):
    assert client.get("/admin/verifications").status_code == 401


def test_the_queue_shows_an_application_and_what_it_is_owed(client, db_session, applicant):
    row = _apply(db_session, applicant)
    d = client.get("/admin/verifications", auth=AUTH).json()["data"]

    mine = [i for i in d["items"] if i["ref"] == row.ref]
    assert len(mine) == 1
    item = mine[0]
    assert item["status"] == seller_verify.APPLIED
    assert item["phone"] == "9870900111"          # the number to ring
    assert item["verified_now"] is False
    assert d["fee"] == seller_verify.fee()


def test_recording_a_payment_through_the_panel_does_not_tick(client, db_session, applicant):
    """The same guard as the service, at the HTTP edge — this is the endpoint
    somebody will be clicking while money is arriving."""
    row = _apply(db_session, applicant)
    r = client.post(f"/admin/verifications/{row.ref}/payment",
                    json={"amount": 199, "ref": "UTR77"}, auth=AUTH)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == seller_verify.PAID
    assert not _verified(db_session, applicant)


def test_a_payment_of_nothing_is_refused(client, db_session, applicant):
    row = _apply(db_session, applicant)
    r = client.post(f"/admin/verifications/{row.ref}/payment",
                    json={"amount": 0}, auth=AUTH)
    assert r.status_code == 400


def test_approve_is_the_endpoint_that_grants_it(client, db_session, applicant):
    row = _apply(db_session, applicant)
    client.post(f"/admin/verifications/{row.ref}/payment", json={"amount": 199}, auth=AUTH)
    r = client.post(f"/admin/verifications/{row.ref}/approve", json={}, auth=AUTH)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == seller_verify.APPROVED
    assert _verified(db_session, applicant)


def test_rejecting_through_the_panel_clears_the_tick(client, db_session, applicant):
    row = _apply(db_session, applicant)
    client.post(f"/admin/verifications/{row.ref}/payment", json={"amount": 199}, auth=AUTH)
    client.post(f"/admin/verifications/{row.ref}/approve", json={}, auth=AUTH)
    r = client.post(f"/admin/verifications/{row.ref}/reject",
                    json={"reason": "नंबर मेल नहीं खाया"}, auth=AUTH)
    assert r.json()["data"] == {"status": seller_verify.REJECTED, "refund_due": True}
    assert not _verified(db_session, applicant)


def test_the_collect_pack_carries_a_sendable_message(client, db_session, applicant):
    row = _apply(db_session, applicant)
    d = client.get(f"/admin/verifications/{row.ref}/collect", auth=AUTH).json()["data"]
    assert row.ref in d["whatsapp"]
    assert str(d["amount"]) in d["whatsapp"]
    # It must not promise the tick for the money.
    assert "टिक चालू कर देंगे" in d["whatsapp"]
    assert "पूरा शुल्क वापस" in d["whatsapp"]


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
    # The confirm on Approve is the actual control on the published claim.
    assert "फ़ोन करके पहचान जाँच ली है" in html
