"""New accounts are closed (owner's decision, 19 Nov 2026).

Closed is the default: with SIGNUP_OPEN unset, no route may create a usable
account, whether email signup, OTP verification or Google. Existing accounts
must still log in, because their owners need /profile to export or delete
their data, which the privacy policy promises.
"""
import pytest

from backend.routes import auth


class _TokenInfo:
    status_code = 200

    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


@pytest.fixture()
def closed(app, monkeypatch):
    monkeypatch.delenv("SIGNUP_OPEN", raising=False)
    monkeypatch.setitem(app.dependency_overrides, auth._LIMIT_SEND, lambda: None)
    sent = {}
    monkeypatch.setattr(auth, "send_otp_email",
                        lambda to, otp, purpose="verification": sent.__setitem__(to, otp) or True)
    return sent


def _google(monkeypatch, email, sub):
    monkeypatch.setattr(auth.httpx, "get", lambda *a, **k: _TokenInfo({
        "aud": auth.GOOGLE_CLIENT_ID, "email": email, "email_verified": "true",
        "sub": sub, "name": "Someone"}))


def _users(db_session, email):
    from backend.database.db import User
    return db_session.query(User).filter(User.email == email).count()


def _account(db_session, email, verified=True):
    from backend.database.db import User
    from backend.utils.auth_utils import hash_password
    db_session.add(User(name="Old", email=email, is_verified=verified,
                        hashed_password=hash_password("oldPass99"), otp="123456"))
    db_session.commit()


def test_closed_is_the_default(monkeypatch):
    monkeypatch.delenv("SIGNUP_OPEN", raising=False)
    assert auth.signup_open() is False
    for value in ("", "false", "0", "no", "off"):
        monkeypatch.setenv("SIGNUP_OPEN", value)
        assert auth.signup_open() is False


def test_status_tells_the_login_page(client, closed):
    r = client.get("/auth/status")
    assert r.json()["data"]["signup_open"] is False
    assert "no-store" in r.headers.get("cache-control", "")


def test_email_signup_is_refused_and_stores_nothing(client, db_session, closed):
    email = "lock-signup@example.com"
    r = client.post("/signup", json={"name": "New", "email": email,
                                     "password": "newPass99"}).json()
    assert r["success"] is False and r["data"]["signup_closed"] is True
    assert _users(db_session, email) == 0
    assert email not in closed   # no OTP email sent


def test_a_signup_begun_before_the_lock_cannot_finish(client, db_session, closed):
    email = "lock-halfway@example.com"
    _account(db_session, email, verified=False)
    assert client.post("/resend-otp", json={"email": email}).json()["success"] is False
    r = client.post("/verify-otp", json={"email": email, "otp": "123456",
                                         "password": "oldPass99"}).json()
    assert r["success"] is False
    assert client.post("/login", json={"email": email,
                                       "password": "oldPass99"}).json()["success"] is False


def test_google_cannot_make_a_new_account(client, db_session, closed, monkeypatch):
    email = "lock-google-new@example.com"
    _google(monkeypatch, email, "g-lock-new")
    r = client.post("/auth/google", json={"id_token": "x"}).json()
    assert r["success"] is False and r["data"]["signup_closed"] is True
    assert _users(db_session, email) == 0


def test_google_cannot_finish_a_half_made_account(client, db_session, closed, monkeypatch):
    email = "lock-google-half@example.com"
    _account(db_session, email, verified=False)
    _google(monkeypatch, email, "g-lock-half")
    assert client.post("/auth/google", json={"id_token": "x"}).json()["success"] is False


def test_existing_accounts_still_log_in(client, db_session, closed, monkeypatch):
    email = "lock-existing@example.com"
    _account(db_session, email)
    r = client.post("/login", json={"email": email, "password": "oldPass99"}).json()
    assert r["success"] is True and r["data"]["token"]

    _google(monkeypatch, email, "g-lock-existing")
    r = client.post("/auth/google", json={"id_token": "x"}).json()
    assert r["success"] is True and r["data"]["token"]


def test_signup_open_true_reopens(client, db_session, closed, monkeypatch):
    monkeypatch.setenv("SIGNUP_OPEN", "true")
    email = "lock-reopened@example.com"
    r = client.post("/signup", json={"name": "New", "email": email,
                                     "password": "newPass99"}).json()
    assert r["success"] is True
    assert client.get("/auth/status").json()["data"]["signup_open"] is True


def test_login_page_starts_closed(repo_root):
    """The signup link is hidden until the server says signups are open, so a
    slow or failed status call never offers something that will be refused."""
    html = (repo_root / "frontend/login.html").read_text(encoding="utf-8")
    assert 'id="signup-link" style="margin-top:14px;display:none;"' in html
    assert "/auth/status" in html
