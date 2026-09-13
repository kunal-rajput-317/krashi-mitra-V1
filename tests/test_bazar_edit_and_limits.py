"""Editing a listing, and the limits that keep editing from being free.

A farmer who typed 900 where he meant 9000 has to be able to fix it — deleting
and reposting loses the offers and the comment thread underneath. But an edit is
a Neon write plus a re-render of a page whose bandwidth already suspended this
site once, and a price that moves five times a day is not a price a buyer can
act on. So editing exists and is capped, and both halves are pinned here.

The limits are rolling 24h windows rather than calendar days on purpose: a
calendar reset can be doubled by acting at 23:59 and again at 00:01. The two
tests that matter most are the ones that could silently spend a farmer's quota
without him doing anything wrong — a no-op save, and a rejected edit.
"""

from datetime import datetime, timedelta

import pytest


EMAIL = "bazar-edit-kisan@example.com"


@pytest.fixture()
def seller(db_session):
    """A verified, profiled account + bearer headers, cleaned on both sides.

    Same shape as tests/test_bazar_feed_optional_auth.py::viewer — db_session
    rolls back its own transaction, but the commits here have already landed,
    so a leftover row would collide on users.email next run.
    """
    from sqlalchemy import func

    from backend.database.db import BazarPost, User, UserProfile
    from backend.utils.auth_utils import create_access_token

    def _wipe():
        rows = db_session.query(User).filter(User.email == EMAIL).all()
        stale = [u.id for u in rows]
        accts = [u.user_id for u in rows if u.user_id is not None]
        if stale:
            db_session.query(BazarPost).filter(BazarPost.user_id.in_(stale)).delete()
            if accts:
                db_session.query(UserProfile).filter(
                    UserProfile.user_id.in_(accts)).delete()
            db_session.query(User).filter(User.id.in_(stale)).delete()
            db_session.commit()

    _wipe()
    user = User(name="Edit Kisan", email=EMAIL, hashed_password="x",
                is_verified=True, created_at=datetime.utcnow())
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    n = (db_session.query(func.max(UserProfile.id)).scalar() or 0) + 1
    user.user_id = n
    db_session.commit()
    db_session.add(UserProfile(
        id=n, user_id=n, name="Edit Kisan", phone_number="9876500000",
        state="Uttar Pradesh", district="Hardoi", village="Rampur"))
    db_session.commit()
    yield user, {"Authorization": f"Bearer {create_access_token(user.id, user.email)}"}
    _wipe()


def _make_post(client, headers, **over):
    data = {"post_type": "sell", "crop": "गेहूं",
            "text": "10 क्विंटल गेहूं", "price": "900"}
    data.update(over)
    r = client.post("/bazar/posts", headers=headers, data=data)
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


class TestEdit:
    def test_a_mistyped_price_can_be_fixed(self, client, seller):
        _, headers = seller
        pid = _make_post(client, headers)

        r = client.patch(f"/bazar/posts/{pid}", headers=headers,
                         json={"price": 9000})
        assert r.status_code == 200, r.text
        assert r.json()["data"]["post"]["price"] == 9000
        assert r.json()["data"]["post"]["crop"] == "गेहूं"

    def test_absent_is_not_null(self, client, seller):
        """Sending only `price` must not blank the fields left out.

        This is the whole reason EditPostRequest reads model_fields_set instead
        of treating None as "unchanged" — with the naive version every edit
        would quietly erase the crop, the text and the quantity.
        """
        _, headers = seller
        pid = _make_post(client, headers, quantity="10")

        client.patch(f"/bazar/posts/{pid}", headers=headers, json={"price": 9000})
        post = client.get(f"/bazar/posts/{pid}", headers=headers).json()["data"]
        assert post["crop"] == "गेहूं"
        assert post["text"] == "10 क्विंटल गेहूं"
        assert post["quantity"] == 10

    def test_explicit_null_clears(self, client, seller):
        """...while a field actually sent as null is a deliberate clear."""
        _, headers = seller
        pid = _make_post(client, headers, old_price="2500")

        r = client.patch(f"/bazar/posts/{pid}", headers=headers,
                         json={"old_price": None})
        assert r.status_code == 200, r.text
        assert r.json()["data"]["post"]["old_price"] is None

    def test_a_guest_cannot_edit(self, client, seller):
        _, headers = seller
        pid = _make_post(client, headers)
        assert client.patch(f"/bazar/posts/{pid}", json={"price": 1}).status_code == 401

    def test_text_cannot_be_emptied_on_a_post_with_no_photo(self, client, seller):
        """create_post refuses a post that is neither text nor media, and an
        edit must not be a way around that rule."""
        _, headers = seller
        pid = _make_post(client, headers)
        r = client.patch(f"/bazar/posts/{pid}", headers=headers, json={"text": "  "})
        assert r.status_code == 400


class TestEditLimit:
    def test_the_fourth_edit_in_a_day_is_refused(self, client, seller):
        from backend.routes.bazar import MAX_EDITS_PER_POST_DAY

        _, headers = seller
        pid = _make_post(client, headers)

        for i in range(MAX_EDITS_PER_POST_DAY):
            r = client.patch(f"/bazar/posts/{pid}", headers=headers,
                             json={"price": 1000 + i})
            assert r.status_code == 200, f"edit {i + 1} refused: {r.text}"

        r = client.patch(f"/bazar/posts/{pid}", headers=headers, json={"price": 7777})
        assert r.status_code == 429, r.text

    def test_a_no_op_save_does_not_spend_one(self, client, seller):
        """A double-tapped Save, or opening the form and saving it unchanged,
        must not cost the farmer an edit."""
        _, headers = seller
        pid = _make_post(client, headers, price="2400")

        for _ in range(5):
            r = client.patch(f"/bazar/posts/{pid}", headers=headers,
                             json={"price": 2400})
            assert r.status_code == 200, r.text

        assert client.patch(f"/bazar/posts/{pid}", headers=headers,
                            json={"price": 2500}).status_code == 200

    def test_a_rejected_edit_does_not_spend_one(self, client, seller):
        """Validation runs before the counter, so a typo the server refuses
        does not eat one of the day's three."""
        _, headers = seller
        pid = _make_post(client, headers)

        for _ in range(5):
            assert client.patch(f"/bazar/posts/{pid}", headers=headers,
                                json={"price": -5}).status_code == 400

        assert client.patch(f"/bazar/posts/{pid}", headers=headers,
                            json={"price": 2500}).status_code == 200

    def test_the_window_rolls(self, client, seller, db_session):
        """Once 24h have passed since the window opened, the count resets."""
        from backend.database.db import BazarPost
        from backend.routes.bazar import MAX_EDITS_PER_POST_DAY

        _, headers = seller
        pid = _make_post(client, headers)
        for i in range(MAX_EDITS_PER_POST_DAY):
            client.patch(f"/bazar/posts/{pid}", headers=headers,
                         json={"price": 100 + i})
        assert client.patch(f"/bazar/posts/{pid}", headers=headers,
                            json={"price": 999}).status_code == 429

        row = db_session.query(BazarPost).filter(BazarPost.id == pid).first()
        row.edit_window_start = datetime.utcnow() - timedelta(days=1, minutes=1)
        db_session.commit()

        assert client.patch(f"/bazar/posts/{pid}", headers=headers,
                            json={"price": 999}).status_code == 200


class TestPostLimit:
    def test_the_daily_listing_cap_holds(self, client, seller):
        from backend.routes.bazar import MAX_POSTS_PER_DAY

        _, headers = seller
        for i in range(MAX_POSTS_PER_DAY):
            _make_post(client, headers, text=f"listing {i}")

        r = client.post("/bazar/posts", headers=headers, data={
            "post_type": "sell", "crop": "गेहूं", "text": "one too many"})
        assert r.status_code == 429, r.text


class TestBuyListings:
    def test_a_farmer_can_post_a_buy_listing(self, client, seller):
        """The composer hardcoded post_type='sell' until 2026-09-14, so nobody
        could ever say "खरीदना है" from this page. The API has to accept it."""
        _, headers = seller
        pid = _make_post(client, headers, post_type="buy")
        post = client.get(f"/bazar/posts/{pid}", headers=headers).json()["data"]
        assert post["post_type"] == "buy"

    def test_an_existing_listing_can_switch_over(self, client, seller):
        _, headers = seller
        pid = _make_post(client, headers)
        r = client.patch(f"/bazar/posts/{pid}", headers=headers,
                         json={"post_type": "buy"})
        assert r.status_code == 200, r.text
        assert r.json()["data"]["post"]["post_type"] == "buy"

    def test_but_not_to_nonsense(self, client, seller):
        _, headers = seller
        pid = _make_post(client, headers)
        assert client.patch(f"/bazar/posts/{pid}", headers=headers,
                            json={"post_type": "barter"}).status_code == 400
