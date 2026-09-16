"""How often a farmer may change his display name.

The name is stamped on every Krashi Bazar card the account has posted and on
every offer sent against them, so a name that changes weekly leaves a buyer
unable to recognise the seller he spoke to yesterday.

The trap this guards: the profile form posts EVERY field back on every save, so
`full_name` arrives on a save that only changed the village. If re-sending the
same name counted as a rename, one unrelated profile edit would lock the farmer
out of his own name for a week — and he would never find out why.
"""

from datetime import datetime, timedelta

import pytest


EMAIL = "rename-kisan@example.com"


@pytest.fixture()
def member(db_session):
    """A verified, profiled account + bearer headers, cleaned on both sides."""
    from sqlalchemy import func

    from backend.database.db import BazarPost, User, UserProfile
    from backend.utils.auth_utils import create_access_token

    def _wipe():
        rows = db_session.query(User).filter(User.email == EMAIL).all()
        stale = [u.id for u in rows]
        accts = [u.user_id for u in rows if u.user_id is not None]
        if stale:
            db_session.query(BazarPost).filter(BazarPost.users_id.in_(stale)).delete()
            if accts:
                db_session.query(UserProfile).filter(
                    UserProfile.user_id.in_(accts)).delete()
            db_session.query(User).filter(User.id.in_(stale)).delete()
            db_session.commit()

    _wipe()
    user = User(name="Purana Naam", email=EMAIL, hashed_password="x",
                is_verified=True, created_at=datetime.utcnow())
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    n = (db_session.query(func.max(UserProfile.id)).scalar() or 0) + 1
    user.user_id = n
    db_session.commit()
    profile = UserProfile(id=n, user_id=n, name="Purana Naam",
                          phone_number="9876511111", state="Uttar Pradesh",
                          district="Hardoi", village="Rampur")
    db_session.add(profile)
    db_session.commit()
    yield user, profile, {"Authorization": f"Bearer {create_access_token(user.id, user.email)}"}
    _wipe()


class TestRenameCooldown:
    def test_the_first_rename_is_free(self, client, member):
        _, _, headers = member
        r = client.put("/profile", headers=headers, json={"full_name": "Naya Naam"})
        assert r.status_code == 200, r.text
        assert r.json()["data"]["full_name"] == "Naya Naam"

    def test_a_second_rename_inside_the_window_is_refused(self, client, member):
        _, _, headers = member
        assert client.put("/profile", headers=headers,
                          json={"full_name": "Naya Naam"}).status_code == 200
        r = client.put("/profile", headers=headers, json={"full_name": "Teesra Naam"})
        assert r.status_code == 429, r.text

    def test_resending_the_same_name_is_not_a_rename(self, client, member):
        """The profile form posts every field back on every save. Saving a
        village change must not burn the rename, and must not be refused."""
        _, _, headers = member
        for _ in range(5):
            r = client.put("/profile", headers=headers,
                           json={"full_name": "Purana Naam", "village": "Sitapur"})
            assert r.status_code == 200, r.text

        # the one real rename is still available
        assert client.put("/profile", headers=headers,
                          json={"full_name": "Naya Naam"}).status_code == 200

    def test_whitespace_only_difference_is_not_a_rename(self, client, member):
        _, _, headers = member
        assert client.put("/profile", headers=headers,
                          json={"full_name": "  Purana Naam  "}).status_code == 200
        assert client.put("/profile", headers=headers,
                          json={"full_name": "Naya Naam"}).status_code == 200

    def test_a_refused_rename_does_not_half_save_the_rest(self, client, member):
        """The cooldown is checked before any field is applied, so a refused
        save leaves the village alone instead of writing half the form."""
        _, _, headers = member
        client.put("/profile", headers=headers, json={"full_name": "Naya Naam"})

        r = client.put("/profile", headers=headers,
                       json={"full_name": "Teesra Naam", "village": "Kaithal"})
        assert r.status_code == 429

        got = client.get("/profile", headers=headers).json()["data"]
        assert got["village"] == "Rampur", "a refused rename still wrote the village"
        assert got["full_name"] == "Naya Naam"

    def test_the_window_rolls(self, client, member, db_session):
        from backend.database.db import UserProfile
        from backend.routes.profile import NAME_CHANGE_COOLDOWN_DAYS

        user, _, headers = member
        assert client.put("/profile", headers=headers,
                          json={"full_name": "Naya Naam"}).status_code == 200
        assert client.put("/profile", headers=headers,
                          json={"full_name": "Teesra Naam"}).status_code == 429

        row = (db_session.query(UserProfile)
               .filter(UserProfile.user_id == user.user_id).first())
        row.name_changed_at = datetime.utcnow() - timedelta(
            days=NAME_CHANGE_COOLDOWN_DAYS, minutes=1)
        db_session.commit()

        assert client.put("/profile", headers=headers,
                          json={"full_name": "Teesra Naam"}).status_code == 200
