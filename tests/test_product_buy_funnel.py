"""The buy funnel on /product — the button, the row it writes, and the reply path.

/product/<slug> used to end on a WhatsApp link ("रेट पूछें") that drafted a
message and left. Nothing was recorded: no `orders` row, nothing in /admin,
nothing in the 📒 book, and no way to answer the farmer later unless somebody
happened to read that one chat. The funnel the business actually runs — pre-book
→ POST /order/log → the owner sources a dealer → quote_total comes back in the
book — lost its only front end when /shop was retired on 16 Sep 2026, while the
API, the admin queue and the book all stayed.

Two halves are pinned here, because each was broken in a way no smoke test could
see:

* **The sheet is on the page.** A 200 from /product proves nothing about whether
  the farmer has any way to place an enquiry.
* **/order/log accepts a logged-in farmer.** `_get_token_optional()` called
  `resolve_token_user_id()` without importing it, inside a bare
  `except Exception: pass`. The NameError was swallowed on every request, so a
  valid token resolved to None: every pre-book came back 401 "पहले लॉगिन करें"
  and every history read came back empty. With no page posting orders, nothing
  was left to notice.

What the sheet may NOT say is in tests/test_product_price_claims.py — we take an
enquiry, a dealer names the price, and no wording here may imply a sale.
"""

from datetime import datetime

import pytest

from backend.routes.product import _get_products

SLUG = _get_products()[0]["slug"]
BUYER = "product-prebook-buyer@example.com"


@pytest.fixture()
def buyer(db_session):
    """A verified account and its Bearer header.

    Verified matters: resolve_token_user() rejects a token whose account is not,
    so an unverified fixture would 401 for a reason that has nothing to do with
    what is being tested."""
    from backend.database.db import Order, User
    from backend.utils.auth_utils import create_access_token

    def _wipe():
        for u in db_session.query(User).filter(User.email == BUYER).all():
            db_session.query(Order).filter(Order.user_id == u.id).delete(
                synchronize_session=False)
            db_session.delete(u)
        db_session.commit()

    _wipe()
    user = User(name="रामलाल", email=BUYER, hashed_password="x",
                is_verified=True, created_at=datetime.utcnow())
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    yield user, {"Authorization": f"Bearer {create_access_token(user.id, user.email)}"}
    _wipe()


def _order_body(**over):
    body = {"product_name": "DAP खाद", "product_id": 5, "quantity": 2,
            "unit_price": 1350.0, "total": 2700.0, "phone": "9876500777",
            "customer_name": "रामलाल", "pincode": "273001", "source": "prebook"}
    body.update(over)
    return body


# ── the page ────────────────────────────────────────────────

def test_the_product_page_carries_the_prebook_sheet(client):
    html = client.get(f"/product/{SLUG}").text
    assert 'id="pb-ov"' in html, "the pre-book sheet is gone from the page"
    assert "kmOpenBuy()" in html, "nothing opens the sheet"
    # The four fields a dealer needs to quote: who, which number, how much,
    # where. Drop any one and the row cannot be answered.
    for field in ('id="pb-name"', 'id="pb-phone"', 'id="pb-q"', 'id="pb-pin"'):
        assert field in html, f"the pre-book form lost {field}"
    assert "/order/log" in html, "the sheet posts nowhere"


def test_the_page_no_longer_ends_on_a_whatsapp_draft(client):
    """The old CTA. A share button still opens WhatsApp — what may not come back
    is an enquiry whose only record is a chat message."""
    html = client.get(f"/product/{SLUG}").text
    assert "रेट पूछें" not in html


def test_the_quote_has_somewhere_to_land(client):
    """A tracking code with no page on the site to read it is the same dead end
    the WhatsApp-only button was. The 📒 book reads /order/history."""
    assert "krashibook.js" in client.get(f"/product/{SLUG}").text


# ── the row it writes ───────────────────────────────────────

def test_a_logged_in_farmer_can_place_a_prebook(client, buyer):
    """The regression: this returned 401 for every valid token."""
    user, headers = buyer
    r = client.post("/order/log", json=_order_body(), headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["success"] is True
    assert data["tracking_code"].startswith("KM-")

    from backend.database.db import Order, SessionLocal
    db = SessionLocal()
    try:
        row = db.query(Order).filter(
            Order.tracking_code == data["tracking_code"]).first()
        assert row is not None
        assert row.user_id == user.id          # filed against the account, not a guest
        assert row.is_guest is False
        assert row.status == "Pending"         # waiting on a dealer's quote
        assert row.pincode == "273001"         # the dealer match needs it
        assert row.customer_name == "रामलाल"
        assert row.quantity == 2 and row.total == 2700.0
    finally:
        db.close()


def test_a_prebook_without_a_login_is_refused(client):
    """Placing one needs an account: the quote comes back hours later, and a
    guest order was reachable only through a localStorage session_id."""
    assert client.post("/order/log", json=_order_body()).status_code == 401


def test_the_farmer_can_read_his_own_prebook_back(client, buyer):
    """Same helper, same swallowed NameError — history came back empty for a
    farmer who was signed in, which is what the 📒 book reads."""
    _, headers = buyer
    code = client.post("/order/log", json=_order_body(),
                       headers=headers).json()["tracking_code"]
    r = client.get("/order/history", headers=headers)
    assert r.status_code == 200
    codes = [o["tracking_code"] for o in r.json()["orders"]]
    assert code in codes, "a signed-in farmer cannot see the pre-book he just placed"
