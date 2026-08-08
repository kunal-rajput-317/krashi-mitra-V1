"""Krashi Bazar's guest-tolerant auth helper must be handed a real Session.

`get_optional_user()` is called by hand from inside the endpoints, not resolved
by FastAPI as a dependency. It was declared `db: Session = Depends(get_db)`
anyway, so every hand-call passed the Depends SENTINEL as the session and died
on `db.query()`:

    AttributeError: 'Depends' object has no attribute 'query'

The failure mode is why it survived: guests return None before touching `db`,
so the feed looked perfectly healthy while every LOGGED-IN farmer got a 500 —
the feed empty, and a post that had in fact saved appearing to have vanished
because the refetch behind it blew up too.

Each endpoint that reads the viewer optionally is pinned here, plus the write →
read round trip that is what a farmer actually experiences.
"""

from datetime import datetime

import pytest


EMAIL = "bazar-feed-viewer@example.com"


@pytest.fixture()
def viewer(db_session):
    """A verified account with a farmer profile, plus its bearer headers.

    Verified and profiled on purpose: an unverified account resolves to None
    and would make these tests pass as a "guest" without ever exercising the
    logged-in path they exist to cover.

    Cleaned up on both sides, like tests/test_dealer_pipeline.py's `clean`:
    db_session rolls back its own transaction but the commits below have
    already landed, so a leftover row would collide on users.email in the
    next test of the file.
    """
    from sqlalchemy import func

    from backend.database.db import BazarPost, User, UserProfile
    from backend.utils.auth_utils import create_access_token

    def _wipe():
        rows  = db_session.query(User).filter(User.email == EMAIL).all()
        stale = [u.id for u in rows]
        # user_profiles keys on the account number, not users.id — see
        # UserProfile.user_id in backend/database/db.py.
        accts = [u.user_id for u in rows if u.user_id is not None]
        if stale:
            db_session.query(BazarPost).filter(BazarPost.user_id.in_(stale)).delete()
            if accts:
                db_session.query(UserProfile).filter(
                    UserProfile.user_id.in_(accts)).delete()
            db_session.query(User).filter(User.id.in_(stale)).delete()
            db_session.commit()

    _wipe()
    user = User(name="Feed Kisan", email=EMAIL,
                hashed_password="x", is_verified=True,
                created_at=datetime.utcnow())
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    # Mirror what ensure_user_profile() does on Postgres: allocate the account
    # number, put it on the users row, then carry it into BOTH profile columns.
    n = (db_session.query(func.max(UserProfile.id)).scalar() or 0) + 1
    user.user_id = n
    db_session.commit()
    db_session.add(UserProfile(
        id=n, user_id=n, name="Feed Kisan", phone_number="9876543210",
        state="Uttar Pradesh", district="Hardoi", village="Rampur"))
    db_session.commit()
    yield user, {"Authorization": f"Bearer {create_access_token(user.id, user.email)}"}
    _wipe()


def test_helper_takes_no_depends_default():
    """The regression itself: a Depends() default here is silently broken.

    Guarding the signature and not only the behaviour, because the endpoints
    would still 500 if someone re-added the default to "make it a dependency"
    — and only for logged-in users, which is the part nobody tests by hand.
    """
    import inspect
    from fastapi import params
    from backend.routes.bazar import get_optional_user

    db_param = inspect.signature(get_optional_user).parameters["db"]
    assert not isinstance(db_param.default, params.Depends), (
        "get_optional_user is hand-called, not dependency-resolved; a "
        "Depends() default arrives as the sentinel object, not a Session"
    )
    assert db_param.default is inspect.Parameter.empty, "db must be required"


@pytest.mark.parametrize("path", [
    "/bazar/feed",
    "/bazar/users/{uid}",
    "/bazar/users/{uid}/followers",
    "/bazar/users/{uid}/following",
])
def test_optional_auth_endpoints_serve_a_logged_in_viewer(client, viewer, path):
    user, headers = viewer
    url = path.format(uid=user.id)

    assert client.get(url).status_code == 200, f"{url} broken for guests"
    r = client.get(url, headers=headers)
    assert r.status_code == 200, f"{url} returned {r.status_code} for a logged-in viewer"
    assert r.json()["success"] is True


def test_post_then_read_back(client, viewer):
    """What the farmer does: publish a listing, then see the feed."""
    user, headers = viewer

    created = client.post("/bazar/posts", headers=headers, data={
        "post_type": "sell", "crop": "गेहूं",
        "text": "10 क्विंटल गेहूं बेचना है", "price": "2400",
    })
    assert created.status_code == 200, created.text
    post_id = created.json()["data"]["id"]

    feed = client.get("/bazar/feed", headers=headers)
    assert feed.status_code == 200, feed.text
    ids = [p["id"] for p in feed.json()["data"]["posts"]]
    assert post_id in ids, "the post saved but the author cannot see it"

    single = client.get(f"/bazar/posts/{post_id}", headers=headers)
    assert single.status_code == 200
    assert single.json()["data"]["is_mine"] is True, (
        "the viewer was not resolved, so his own post is not marked as his"
    )
