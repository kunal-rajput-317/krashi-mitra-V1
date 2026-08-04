"""The profile form is the only place a name can be edited, so users.name
depends entirely on _sync_user mirroring it back.

It did not, and the two tables drifted permanently the first time a farmer
corrected his own name: users kept the signup (or Google) value while
user_profiles got the real one. Four of thirteen live accounts had diverged —
'Kunal' vs 'kunal rajput', 'AVDHESH PRATAP SINGH' vs 'OMPRAKASH SINGH' — and
which name a farmer saw depended on which table the surface happened to read.
"""

from backend.database.db import User, UserProfile
from backend.routes.profile import _sync_user


def _pair(name_on_user: str, name_on_profile: str):
    user = User(id=1, name=name_on_user, email="f@example.com",
                hashed_password="x", preferred_language="hindi")
    profile = UserProfile(user_id=1, name=name_on_profile, language="hindi")
    return user, profile


class _FakeSession:
    """_sync_user only ever calls db.add(); nothing here needs a real session."""

    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)


class TestNameSync:
    def test_edited_name_reaches_users(self):
        user, profile = _pair("Kunal", "kunal rajput")
        _sync_user(user, profile, _FakeSession())
        assert user.name == "kunal rajput"

    def test_google_signup_name_loses_to_the_typed_one(self):
        """alerts.display_name() already prefers the profile name; users.name
        has to agree or the same farmer reads differently per surface."""
        user, profile = _pair("AVDHESH PRATAP SINGH", "OMPRAKASH SINGH")
        _sync_user(user, profile, _FakeSession())
        assert user.name == "OMPRAKASH SINGH"

    def test_whitespace_is_trimmed(self):
        user, profile = _pair("seth\n", "  Chotu  ")
        _sync_user(user, profile, _FakeSession())
        assert user.name == "Chotu"

    def test_blank_profile_name_does_not_wipe_the_account_name(self):
        """PUT /profile applies any non-None field, so full_name="" reaches
        here. users.name is NOT NULL — an empty mirror would fail the write."""
        for blank in ("", "   "):
            user, profile = _pair("Rajesh Kumar", blank)
            _sync_user(user, profile, _FakeSession())
            assert user.name == "Rajesh Kumar"

    def test_still_mirrors_the_other_fields(self):
        user, profile = _pair("Kunal", "kunal rajput")
        profile.village, profile.district = "Sitapur", "Hardoi"
        profile.primary_crop, profile.language = "wheat", "hindi"
        _sync_user(user, profile, _FakeSession())
        assert (user.village, user.district, user.primary_crop) == (
            "Sitapur", "Hardoi", "wheat")

    def test_avatar_is_never_mirrored(self):
        """user_profiles is the avatar's sole home — the users column was
        dropped, so touching it here would raise."""
        user, profile = _pair("Kunal", "kunal rajput")
        profile.avatar_url = "data:image/webp;base64,AAAA"
        _sync_user(user, profile, _FakeSession())
        assert not hasattr(user, "avatar_url")
