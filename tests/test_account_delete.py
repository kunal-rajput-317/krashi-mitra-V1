"""खाता हटाएँ — services/account_delete.py + routes/account_delete.py.

What is pinned:
  * it takes BOTH a password and an email OTP (OTP alone for a Google-only
    account), and a wrong one of either erases nothing;
  * the users and user_profiles rows SURVIVE — anonymised, never deleted, and
    user_id (the gapless account number) and is_verified untouched, because
    changing either fires the renumbering / un-verify guards in Postgres;
  * every token already issued stops working at once;
  * his own content goes; his comment on someone else's post stays in the
    thread with its text replaced; money records stay;
  * registration details are held 180 days, then purged;
  * the same email can sign up again.
"""
import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import func

from backend.database.db import (AccountDeletion, BazarComment, BazarPost, ChatHistory,
                                 Payment, SellerVerification, User, UserProfile)
from backend.services import account_delete
from backend.utils.auth_utils import create_access_token, hash_password

EMAIL = "delete-me@example.com"
PASSWORD = "Str0ng!Passw0rd"


@pytest.fixture()
def sent(monkeypatch):
    box = []
    import backend.routes.account_delete as route
    monkeypatch.setattr(route, "send_otp_email",
                        lambda to, otp, purpose="": box.append((to, otp, purpose)) or True)
    return box


@pytest.fixture(autouse=True)
def _cleanup(db_session):
    """These tests COMMIT users and profiles into the shared SQLite file; take
    them back out so later tests allocating account numbers do not collide."""
    yield
    db_session.rollback()
    ids = [u.id for u in db_session.query(User).filter(
        (User.email.like("%@example.com")) | (User.email.like("%@deleted.invalid"))).all()
        if u.email in (EMAIL, "neighbour@example.com", "google-user@example.com")
        or u.email.endswith("@deleted.invalid")]
    accts = [a for (a,) in db_session.query(User.user_id).filter(User.id.in_(ids)).all() if a]
    db_session.query(BazarComment).filter(BazarComment.users_id.in_(ids)).delete(synchronize_session=False)
    db_session.query(BazarPost).filter(BazarPost.users_id.in_(ids)).delete(synchronize_session=False)
    db_session.query(SellerVerification).filter(SellerVerification.user_id.in_(ids)).delete(synchronize_session=False)
    db_session.query(AccountDeletion).delete(synchronize_session=False)
    db_session.query(UserProfile).filter(UserProfile.user_id.in_(accts)).delete(synchronize_session=False)
    db_session.query(User).filter(User.id.in_(ids)).delete(synchronize_session=False)
    db_session.commit()


def _make_user(db, email=EMAIL, provider="email"):
    db.query(User).filter(User.email == email).delete()
    db.commit()
    u = User(name="Ram Kisan", email=email, hashed_password=hash_password(PASSWORD),
             is_verified=True, auth_provider=provider, created_at=datetime.utcnow() - timedelta(days=3),
             village="Rampur", google_id="g-123" if provider == "google" else None)
    db.add(u)
    db.commit()
    db.refresh(u)
    n = (db.query(func.max(UserProfile.id)).scalar() or 0) + 1
    u.user_id = n
    db.commit()
    db.add(UserProfile(id=n, user_id=n, name="Ram Kisan", phone_number="9876543210",
                       village="Rampur", district="Hardoi", state="Uttar Pradesh",
                       geo_lat=27.4, geo_lon=80.1, farm_size="2"))
    db.commit()
    return u


def _auth(u):
    return {"Authorization": "Bearer " + create_access_token(u.id, u.email)}


def _otp(client, hdr, sent):
    assert client.post("/account/delete/otp", headers=hdr).json()["success"]
    return sent[-1][1]


def test_wrong_password_or_otp_erases_nothing(client, db_session, sent):
    u = _make_user(db_session)
    hdr = _auth(u)
    assert client.get("/account/delete/info", headers=hdr).json()["data"]["has_password"] is True
    otp = _otp(client, hdr, sent)
    r = client.post("/account/delete", headers=hdr,
                    json={"otp": otp, "password": "wrong", "confirm": True}).json()
    assert not r["success"]
    r = client.post("/account/delete", headers=hdr,
                    json={"otp": "000000" if otp != "000000" else "111111",
                          "password": PASSWORD, "confirm": True}).json()
    assert not r["success"]
    r = client.post("/account/delete", headers=hdr,
                    json={"otp": otp, "password": PASSWORD, "confirm": False}).json()
    assert not r["success"]
    db_session.expire_all()
    assert db_session.query(User).filter(User.id == u.id).first().email == EMAIL


def test_delete_keeps_the_rows_but_erases_the_person(client, db_session, sent):
    u = _make_user(db_session)
    uid, acct_no = u.id, u.user_id
    other = _make_user(db_session, email="neighbour@example.com")

    # His own things, and a comment on his neighbour's post.
    mine = BazarPost(users_id=uid, post_type="sell", crop="गेहूं", text="बेचना है")
    theirs = BazarPost(users_id=other.id, post_type="sell", crop="धान", text="धान")
    db_session.add_all([mine, theirs])
    db_session.commit()
    db_session.add(BazarComment(post_id=theirs.id, users_id=uid, kind="offer",
                                text="मेरा नंबर 9876543210", offer_amount=2100))
    db_session.add(ChatHistory(user_id=uid, role="user", message="मेरे खेत में कीड़े"))
    db_session.add(SellerVerification(user_id=uid, ref="KMVDELTE", full_name="Ram Kisan",
                                      phone="9876543210", village="Rampur", fee_amount=199,
                                      paid_at=datetime.utcnow(), status="paid"))
    db_session.add(Payment(received_at=datetime.utcnow(), amount=199, source="verify",
                           source_key="KMVDELTE", payer="Ram Kisan", contact="9876543210"))
    db_session.commit()
    theirs_id, mine_id = theirs.id, mine.id

    hdr = _auth(u)
    otp = _otp(client, hdr, sent)
    assert sent[-1][0] == EMAIL and sent[-1][2] == "delete"
    r = client.post("/account/delete", headers=hdr,
                    json={"otp": otp, "password": PASSWORD, "confirm": True,
                          "reason": "privacy"}).json()
    assert r["success"], r
    db_session.expire_all()

    user = db_session.query(User).filter(User.id == uid).first()
    assert user is not None                                   # row kept
    assert user.user_id == acct_no and user.is_verified       # never touched
    assert user.email == f"deleted-{uid}@deleted.invalid"
    assert user.name == account_delete.DELETED_NAME and user.village is None
    prof = db_session.query(UserProfile).filter(UserProfile.user_id == acct_no).first()
    assert prof is not None and prof.phone_number is None and prof.geo_lat is None
    assert prof.farm_size is None and prof.village is None

    # Old token is dead.
    assert client.get("/account/delete/info", headers=hdr).status_code == 401

    assert db_session.query(BazarPost).filter(BazarPost.id == mine_id).first() is None
    assert db_session.query(BazarPost).filter(BazarPost.id == theirs_id).first() is not None
    c = db_session.query(BazarComment).filter(BazarComment.post_id == theirs_id).first()
    assert c.text == account_delete.REMOVED_COMMENT and c.offer_amount is None
    assert db_session.query(ChatHistory).filter(ChatHistory.user_id == uid).count() == 0

    # Money stays.
    v = db_session.query(SellerVerification).filter(SellerVerification.ref == "KMVDELTE").first()
    assert v.fee_amount == 199 and v.phone == "9876543210" and v.village is None
    assert db_session.query(Payment).filter(Payment.source_key == "KMVDELTE").count() == 1

    hold = db_session.query(AccountDeletion).filter(AccountDeletion.users_id == uid).first()
    assert hold.reg_email == EMAIL and hold.reg_phone == "9876543210"
    assert hold.verified_by == "password+otp" and hold.reason == "गोपनीयता की चिंता"
    assert json.loads(hold.erased)["posts"] == 1

    # The address is free again.
    from backend.routes.auth import _find_user_by_email
    assert _find_user_by_email(db_session, EMAIL) is None


def test_google_only_account_confirms_with_otp_alone(client, db_session, sent):
    u = _make_user(db_session, email="google-user@example.com", provider="google")
    hdr = _auth(u)
    assert client.get("/account/delete/info", headers=hdr).json()["data"]["has_password"] is False
    otp = _otp(client, hdr, sent)
    r = client.post("/account/delete", headers=hdr, json={"otp": otp, "confirm": True}).json()
    assert r["success"], r
    db_session.expire_all()
    u2 = db_session.query(User).filter(User.id == u.id).first()
    assert u2.google_id is None


def test_registration_details_are_purged_after_180_days(db_session):
    row = AccountDeletion(users_id=999001, deleted_at=datetime.utcnow() - timedelta(days=181),
                          verified_by="otp", reg_name="X", reg_email="x@example.com",
                          reg_phone="9000000000",
                          purge_after=datetime.utcnow() - timedelta(days=1))
    fresh = AccountDeletion(users_id=999002, deleted_at=datetime.utcnow(), verified_by="otp",
                            reg_email="y@example.com",
                            purge_after=datetime.utcnow() + timedelta(days=179))
    db_session.add_all([row, fresh])
    db_session.commit()
    account_delete.purge_expired(db_session)
    db_session.expire_all()
    assert row.reg_email is None and row.reg_phone is None and row.purged_at is not None
    assert fresh.reg_email == "y@example.com"
