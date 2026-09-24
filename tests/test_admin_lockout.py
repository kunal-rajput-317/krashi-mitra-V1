"""The admin panel locks an IP out after repeated wrong passwords, and never
counts the owner's own successful requests toward that limit."""
import base64
import os

from backend.routes import admin


def _hdr(pw):
    raw = f"{os.environ['ADMIN_USER']}:{pw}".encode()
    return {"Authorization": "Basic " + base64.b64encode(raw).decode()}


def test_ten_wrong_passwords_lock_the_ip_out(client):
    admin._admin_fails.clear()
    good = _hdr(os.environ["ADMIN_PASS"])
    for _ in range(30):                               # heavy normal use: never locks
        assert client.get("/admin/ledger", headers=good).status_code == 200
    for _ in range(admin._ADMIN_FAIL_LIMIT):
        assert client.get("/admin/ledger", headers=_hdr("wrong")).status_code == 401
    # Locked now — even the right password waits out the window.
    assert client.get("/admin/ledger", headers=good).status_code == 429
    admin._admin_fails.clear()
    assert client.get("/admin/ledger", headers=good).status_code == 200
