"""GET /profile must actually return, for both shapes of authenticated caller.

The regression this exists for: `get_profile()` read the module-level helper
`acct()` on its first line and, further down, assigned `acct = db.query(User)...`
for the no-profile branch. In Python that assignment makes the name local for
the *whole* function, so the first line raised UnboundLocalError and every
single call returned 500 — for eleven days, and only for logged-in users, which
is precisely the path no automated check and no anonymous smoke test covers.

From outside it looked like a backend outage: the profile page rendered with
0 posts / 0 followers / 0 following and no error anyone could see.
"""
from datetime import datetime

import pytest
from sqlalchemy import func

from backend.database.db import User, UserProfile
from backend.utils.auth_utils import create_access_token

EMAIL = "profile-fetch-test@krashimitra.test"


def _wipe(db_session):
    stale = [u.id for u in db_session.query(User).filter(User.email == EMAIL).all()]
    if stale:
        accts = [u.user_id for u in db_session.query(User).filter(User.id.in_(stale)).all()
                 if u.user_id is not None]
        if accts:
            db_session.query(UserProfile).filter(UserProfile.user_id.in_(accts)).delete(
                synchronize_session=False)
        db_session.query(User).filter(User.id.in_(stale)).delete(synchronize_session=False)
        db_session.commit()


@pytest.fixture()
def account(db_session):
    """A verified account with no profile row yet — the branch that shadowed."""
    _wipe(db_session)
    user = User(name="Profile Kisan", email=EMAIL, hashed_password="x",
                is_verified=True, created_at=datetime.utcnow())
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    yield user, {"Authorization": f"Bearer {create_access_token(user.id, user.email)}"}
    _wipe(db_session)


class TestGetProfile:
    def test_account_without_a_profile_does_not_500(self, client, account):
        """The exact production failure: this branch is what shadowed `acct`."""
        user, headers = account
        r = client.get("/profile", headers=headers)
        assert r.status_code == 200, (
            f"GET /profile returned {r.status_code}; the page shows an empty "
            f"profile and no farmer can see why. Body: {r.text[:300]}")
        body = r.json()
        assert body["data"]["email"] == EMAIL
        assert body["data"]["full_name"] == "Profile Kisan"

    def test_account_with_a_profile_returns_it(self, client, account, db_session):
        user, headers = account
        n = (db_session.query(func.max(UserProfile.id)).scalar() or 0) + 1
        user.user_id = n
        db_session.commit()
        db_session.add(UserProfile(id=n, user_id=n, name="Profile Kisan",
                                   phone_number="9876543210", state="Uttar Pradesh",
                                   district="Hardoi", village="Rampur"))
        db_session.commit()

        r = client.get("/profile", headers=headers)
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert body["success"] is True
        d = body["data"]
        assert d["email"] == EMAIL
        # The header card the screenshot showed as 0/0/0 — present and numeric.
        for k in ("posts_count", "followers_count", "following_count"):
            assert isinstance(d[k], int), f"{k} missing from GET /profile"

    def test_no_token_is_rejected_not_crashed(self, client):
        assert client.get("/profile").status_code in (401, 403)


def test_get_profile_never_shadows_the_acct_helper():
    """Guards the shape, not just the behaviour.

    `acct` is imported at module level and called on the first line. Any
    assignment to that name anywhere in the function makes it local for the
    entire body and reintroduces the 500 — a one-word change that no reviewer
    would flag and that only breaks for authenticated users.
    """
    import ast
    import inspect
    import textwrap

    from backend.routes import profile as mod

    src = textwrap.dedent(inspect.getsource(mod.get_profile))
    assigned = {n.id for n in ast.walk(ast.parse(src))
                if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
    assert "acct" not in assigned, (
        "get_profile() assigns `acct`, shadowing the module-level helper it "
        "calls on its first line — every call will raise UnboundLocalError. "
        "Name the local `account`, as the rest of this file does.")
