"""A password may be changed at most five times a day.

/reset-password is the only path that rewrites a password. Without a cap an
account can be churned through passwords all day — by its owner, or by whoever
is holding the mailbox — and the day it matters the login history says nothing.
The cap is keyed by email, not IP: it is the account being protected, so the
counter has to follow it across networks.
"""

from datetime import datetime, timedelta

import pytest

from backend.routes import auth
from backend.utils import security


@pytest.fixture(autouse=True)
def fresh_daily_counters():
    """The cap store is process-global; don't inherit another test's count."""
    with security._daily_lock:
        security._daily.clear()
    yield
    with security._daily_lock:
        security._daily.clear()


class _FakeUser:
    def __init__(self):
        self.email           = "kisan@example.com"
        self.otp             = "123456"
        self.otp_expiry      = datetime.utcnow() + timedelta(minutes=10)
        self.hashed_password = "old-hash"
        self.is_verified     = True


class _FakeDB:
    def __init__(self, user):
        self.user    = user
        self.commits = 0

    def commit(self):
        self.commits += 1


@pytest.fixture
def user_and_db(monkeypatch):
    user = _FakeUser()
    db   = _FakeDB(user)
    monkeypatch.setattr(auth, "_find_user_by_email", lambda _db, _email: user)
    return user, db


def _reset(db, password="KisanBhai@2026"):
    """One /reset-password call with a valid, unexpired OTP."""
    db.user.otp        = "123456"
    db.user.otp_expiry = datetime.utcnow() + timedelta(minutes=10)
    body = auth.ResetPasswordRequest(
        email="kisan@example.com", otp="123456", new_password=password,
    )
    return auth.reset_password(body, db)


def test_five_changes_a_day_are_allowed(user_and_db):
    _, db = user_and_db
    for i in range(auth.MAX_PASSWORD_CHANGES_PER_DAY):
        assert _reset(db, f"KisanBhai@202{i}")["success"] is True


def test_sixth_change_is_refused(user_and_db):
    user, db = user_and_db
    for i in range(auth.MAX_PASSWORD_CHANGES_PER_DAY):
        _reset(db, f"KisanBhai@202{i}")

    hash_before = user.hashed_password
    out = _reset(db, "KisanBhai@9999")

    assert out["success"] is False
    assert str(auth.MAX_PASSWORD_CHANGES_PER_DAY) in out["message"]
    assert user.hashed_password == hash_before, "the password was changed anyway"


def test_a_wrong_otp_does_not_spend_one_of_the_five(user_and_db):
    """The cap counts changes, not attempts — otherwise anyone who knows an
    email could burn the owner's five tries with junk OTPs."""
    _, db = user_and_db
    for _ in range(10):
        body = auth.ResetPasswordRequest(
            email="kisan@example.com", otp="000000", new_password="KisanBhai@2026",
        )
        auth.reset_password(body, db)
        auth._clear_otp_attempts("kisan@example.com")

    for i in range(auth.MAX_PASSWORD_CHANGES_PER_DAY):
        assert _reset(db, f"KisanBhai@202{i}")["success"] is True


def test_a_weak_password_does_not_spend_one_of_the_five(user_and_db):
    _, db = user_and_db
    body = auth.ResetPasswordRequest(
        email="kisan@example.com", otp="123456", new_password="abc",
    )
    assert auth.reset_password(body, db)["success"] is False

    for i in range(auth.MAX_PASSWORD_CHANGES_PER_DAY):
        assert _reset(db, f"KisanBhai@202{i}")["success"] is True


def test_the_cap_follows_the_account_not_the_case_of_the_email(user_and_db):
    """`Kisan@Example.com` and `kisan@example.com` are one account."""
    _, db = user_and_db
    for i in range(auth.MAX_PASSWORD_CHANGES_PER_DAY):
        _reset(db, f"KisanBhai@202{i}")

    db.user.otp        = "123456"
    db.user.otp_expiry = datetime.utcnow() + timedelta(minutes=10)
    body = auth.ResetPasswordRequest(
        email="Kisan@Example.com", otp="123456", new_password="KisanBhai@9999",
    )
    assert auth.reset_password(body, db)["success"] is False
