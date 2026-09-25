"""आपका डेटा — the profile page's self-serve data rights (added 25 Sep 2026).

The privacy policy promised two things the site could not do:
  * "जानने का अधिकार" — see what we hold. Now GET /profile/export returns it
    as one JSON file.
  * "सहमति वापस लेने का अधिकार: लोकेशन … कभी भी बंद" — but a saved device
    fix stayed on user_profiles until the whole account was deleted. Now
    DELETE /profile/location clears it.

Pinned here: the export carries the farmer's own data and never a secret
(password hash, OTP, Google id) or an admin-only field (the dealer's name);
clearing the location clears only the device fix, never the typed address;
both refuse a caller with no token. Also pinned: the unprotected order admin
endpoints removed the same day stay removed.
"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import func

from backend.database.db import ChatHistory, Order, User, UserProfile
from backend.utils.auth_utils import create_access_token, hash_password

EMAIL = "data-rights@example.com"


def _purge(db):
    db.rollback()
    ids = [i for (i,) in db.query(User.id).filter(User.email == EMAIL).all()]
    accts = [a for (a,) in db.query(User.user_id).filter(User.id.in_(ids)).all() if a]
    db.query(ChatHistory).filter(ChatHistory.user_id.in_(ids)).delete(synchronize_session=False)
    db.query(Order).filter(Order.tracking_code == "KM-DRTEST").delete(synchronize_session=False)
    db.query(UserProfile).filter(UserProfile.user_id.in_(accts)).delete(synchronize_session=False)
    db.query(User).filter(User.id.in_(ids)).delete(synchronize_session=False)
    db.commit()


@pytest.fixture()
def farmer(db_session):
    db = db_session
    _purge(db)
    try:
        u = _seed(db)
    except Exception:
        _purge(db)
        raise
    try:
        yield u
    finally:
        _purge(db)


def _seed(db):
    u = User(name="Shyam Kisan", email=EMAIL, hashed_password=hash_password("Str0ng!Passw0rd"),
             is_verified=True, auth_provider="email", otp="123456",
             created_at=datetime.utcnow() - timedelta(days=2), google_id="g-secret")
    db.add(u)
    db.commit()
    db.refresh(u)
    n = max(db.query(func.max(UserProfile.id)).scalar() or 0,
            db.query(func.max(User.user_id)).scalar() or 0) + 1
    u.user_id = n
    db.commit()
    db.add(UserProfile(id=n, user_id=n, name="Shyam Kisan", phone_number="9876500000",
                       village="Rampur", district="Hardoi", state="Uttar Pradesh",
                       geo_lat=27.4, geo_lon=80.1, geo_location="Hardoi, UP"))
    db.add(ChatHistory(user_id=u.id, role="user", message="गेहूं में कौन सी खाद?"))
    db.add(Order(tracking_code="KM-DRTEST", user_id=u.id, user_email=EMAIL,
                 product_name="DAP", quantity=1, unit_price=1350, total=1350,
                 phone="9876500000",
                 dealer_name="Secret Dealer Traders"))
    db.commit()
    return u


def _auth(u):
    return {"Authorization": "Bearer " + create_access_token(u.id, u.email)}


def test_export_returns_own_data_and_no_secrets(client, farmer):
    r = client.get("/profile/export", headers=_auth(farmer))
    assert r.status_code == 200
    assert "attachment" in r.headers.get("content-disposition", "")
    body = r.text
    data = r.json()
    assert data["account"]["email"] == EMAIL
    assert data["profile"]["phone_number"] == "9876500000"
    assert data["ai_chats"][0]["message"] == "गेहूं में कौन सी खाद?"
    assert data["orders"][0]["product_name"] == "DAP"
    for secret in ("hashed_password", "google_id", "g-secret", "123456",
                   "dealer_name", "Secret Dealer Traders"):
        assert secret not in body, f"{secret!r} leaked into the data export"


def test_clearing_location_keeps_the_typed_address(client, db_session, farmer):
    r = client.delete("/profile/location", headers=_auth(farmer))
    assert r.json()["success"]
    db_session.expire_all()
    p = db_session.query(UserProfile).filter(UserProfile.user_id == farmer.user_id).first()
    assert p.geo_lat is None and p.geo_lon is None and p.geo_location is None
    assert p.district == "Hardoi" and p.village == "Rampur"


def test_both_need_a_login(client):
    assert client.get("/profile/export").status_code in (401, 403)
    assert client.delete("/profile/location").status_code in (401, 403)


@pytest.mark.parametrize("method,path", [
    ("get", "/order/all?admin_key=krashimitra_admin_2026"),
    ("put", "/order/status"),
    ("put", "/order/quote"),
])
def test_unprotected_order_admin_routes_stay_gone(client, method, path):
    body = {"tracking_code": "KM-X", "admin_key": "x", "status": "Booked",
            "quote_total": 1, "delivery_info": "x"}
    r = client.get(path) if method == "get" else client.put(path, json=body)
    assert r.status_code in (404, 405), f"{path} is reachable again"
