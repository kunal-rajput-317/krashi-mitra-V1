"""Personal data we stopped keeping — services/pii_guard.py + services/retention.py.

What is pinned:
  * an Aadhaar-like number typed into free text is masked before it is
    saved, in every script's digits, while phone numbers — which sellers put
    in Bazar posts and must keep — survive;
  * the mask is applied by the ORM, so a route cannot forget it;
  * AI chats older than 90 days are deleted, newer ones kept;
  * orders older than 2 years lose name/email/phone/pincode but keep the
    product and the money;
  * the device location sent to the server is rounded to ~1 km.
"""
from datetime import datetime, timedelta

from backend.database.db import ChatHistory, Order
from backend.services import pii_guard, retention
from backend.services.pii_guard import MASK, mask_aadhaar

AADHAAR = "234567890124"        # passes the Verhoeff check


def test_verhoeff_matches_the_textbook_example():
    assert pii_guard._verhoeff_ok("2363")
    assert not pii_guard._verhoeff_ok("2364")


def test_aadhaar_is_masked_in_every_layout():
    for typed in (AADHAAR, "2345 6789 0124", "2345-6789-0124", "२३४५ ६७८९ ०१२४"):
        out = mask_aadhaar(f"मेरा आधार {typed} है")
        assert out == f"मेरा आधार {MASK} है", typed


def test_phone_numbers_and_other_numbers_survive():
    keep = [
        "9876543210",                    # 10-digit mobile
        "+91 98765 43210",
        "+919876543216",                 # after a + it is a phone
        "919876543216",                  # 91 + mobile, passes Verhoeff, still a phone
        "234567890125",                  # wrong check digit
        "134567890124",                  # Aadhaar never starts with 0/1
        "1234567890123",                 # 13 digits
        "40 क्विंटल, ₹2400",
    ]
    for text in keep:
        assert mask_aadhaar(text) == text, text


def test_none_and_non_strings_pass_through():
    assert mask_aadhaar(None) is None
    assert mask_aadhaar("") == ""
    assert mask_aadhaar(5) == 5


def test_orm_masks_on_insert_and_update(db_session):
    row = ChatHistory(role="user", message=f"आधार {AADHAAR}")
    db_session.add(row)
    db_session.flush()
    assert row.message == f"आधार {MASK}"

    row.message = f"फिर से {AADHAAR}"
    db_session.flush()
    assert row.message == f"फिर से {MASK}"


def test_every_free_text_column_is_hooked():
    from backend.database import db
    for model, cols in db._FREE_TEXT.items():
        for col in cols:
            assert col in model.__table__.columns, f"{model.__name__}.{col}"


def test_old_chats_are_deleted_new_ones_kept(db_session):
    now = datetime.utcnow()
    old = ChatHistory(role="user", message="पुराना", created_at=now - timedelta(days=91))
    new = ChatHistory(role="user", message="नया", created_at=now - timedelta(days=89))
    db_session.add_all([old, new])
    db_session.flush()
    old_id, new_id = old.id, new.id

    try:
        retention.purge_old_chats(db_session, now)   # commits
        ids = {i for (i,) in db_session.query(ChatHistory.id).all()}
        assert old_id not in ids and new_id in ids
    finally:
        db_session.query(ChatHistory).filter(ChatHistory.id.in_([old_id, new_id])) \
                  .delete(synchronize_session=False)
        db_session.commit()


def _order(code, age_days, now):
    return Order(tracking_code=code, user_email="f@example.com", user_name="रामू",
                 customer_name="रामू", phone="9876543210", pincode="241001",
                 delivery_info="गाँव तक", session_id="s1", product_name="यूरिया",
                 quantity=2, unit_price=270.0, total=540.0,
                 created_at=now - timedelta(days=age_days))


def test_old_orders_lose_contact_details_keep_the_money(db_session):
    now = datetime.utcnow()
    old, new = _order("KM-RET-OLD", 731, now), _order("KM-RET-NEW", 700, now)
    db_session.add_all([old, new])
    db_session.flush()

    try:
        retention.anonymise_old_orders(db_session, now)   # commits
        db_session.expire_all()

        old = db_session.query(Order).filter_by(tracking_code="KM-RET-OLD").one()
        assert (old.user_email, old.user_name, old.customer_name, old.phone,
                old.pincode, old.delivery_info, old.session_id) == (None, None, None, "", None, None, None)
        assert (old.product_name, old.quantity, old.total) == ("यूरिया", 2, 540.0)

        new = db_session.query(Order).filter_by(tracking_code="KM-RET-NEW").one()
        assert new.phone == "9876543210" and new.user_email == "f@example.com"
    finally:
        db_session.rollback()
        db_session.query(Order).filter(Order.tracking_code.like("KM-RET-%")) \
                  .delete(synchronize_session=False)
        db_session.commit()


def test_chat_question_is_masked_before_the_ai_sees_it(repo_root):
    src = (repo_root / "backend/routes/chatbot.py").read_text(encoding="utf-8")
    assert "body.q = mask_aadhaar(" in src


def test_location_sent_to_server_is_rounded_to_about_1km(repo_root):
    js = (repo_root / "frontend/location.js").read_text(encoding="utf-8")
    assert "lat: roundKm(lat), lon: roundKm(lon)" in js
    assert "Math.round(v * 100) / 100" in js


def test_farm_size_is_retired_everywhere(repo_root):
    """Owner, 24 Oct 2026: farm size is not needed. Not mapped, not re-added
    on startup, scheduled for erase + drop, and never asked for again."""
    from backend.database import db
    assert "farm_size" not in db.UserProfile.__table__.columns
    assert "farm_size_unit" not in db.UserProfile.__table__.columns
    assert ("user_profiles_2026_10_24", ("farm_size", "farm_size_unit")) in db._RETIREMENTS
    names = [n for n, _ in db._RETIREMENTS]
    assert len(names) == len(set(names))            # each batch its own clock
    for f in ("backend/routes/profile.py", "backend/routes/auth.py",
              "frontend/profile.html"):
        src = (repo_root / f).read_text(encoding="utf-8")
        assert '"farm_size"' not in src and "farm_size:" not in src \
            and 'id="farm_size"' not in src, f


def test_retention_sweep_is_scheduled(repo_root):
    src = (repo_root / "backend/services/mandi_scheduler.py").read_text(encoding="utf-8")
    assert "func               = _retention_sweep" in src
