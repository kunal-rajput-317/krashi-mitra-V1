"""Regressions for the 20 Oct 2026 security audit.

Each test pins one hole that was open on that date. If one fails, the hole is
back — fix the change, never this file.
"""
import base64
import json
import os
from datetime import datetime

import pytest

from backend.routes import admin, alerts, auth, bhav, chatbot
from backend.services import buyers


# ── Google login ─────────────────────────────────────────────

class _TokenInfo:
    status_code = 200

    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


def _google(monkeypatch, **info):
    monkeypatch.setattr(auth.httpx, "get", lambda *a, **k: _TokenInfo(info))


def _existing_account(db_session, email):
    from backend.database.db import User
    from backend.utils.auth_utils import hash_password
    db_session.add(User(name="Real", email=email,
                        hashed_password=hash_password("realPass99"), is_verified=True))
    db_session.commit()


def test_google_token_minted_for_another_site_is_refused(client, db_session, monkeypatch):
    """With GOOGLE_CLIENT_ID unset the audience check was skipped, so an
    id_token any other website obtained from its own visitors logged them in
    here — into the account that already held that email."""
    email = "audit-aud@example.com"
    _existing_account(db_session, email)
    _google(monkeypatch, aud="someone-elses-app.apps.googleusercontent.com",
            email=email, email_verified="true", sub="g-aud")
    r = client.post("/auth/google", json={"id_token": "x"}).json()
    assert r["success"] is False


def test_google_unverified_email_string_false_is_refused(client, db_session, monkeypatch):
    """tokeninfo sends "false" as a string; `not "false"` is False."""
    email = "audit-unverified@example.com"
    _existing_account(db_session, email)
    _google(monkeypatch, aud=auth.GOOGLE_CLIENT_ID, email=email,
            email_verified="false", sub="g-unv")
    r = client.post("/auth/google", json={"id_token": "x"}).json()
    assert r["success"] is False


def test_google_login_for_our_app_still_works(client, monkeypatch):
    _google(monkeypatch, aud=auth.GOOGLE_CLIENT_ID, email="audit-google-ok@example.com",
            email_verified="true", sub="g-ok", name="Ok")
    r = client.post("/auth/google", json={"id_token": "x"}).json()
    assert r["success"] is True and r["data"]["token"]


# ── XSS ──────────────────────────────────────────────────────

def test_pay_page_escapes_the_path_in_its_canonical_link(client):
    r = client.get("/pay/%22%3E%3Csvg%20onload%3Dalert(1)%3E/x")
    assert "<svg onload" not in r.text
    assert "&quot;&gt;&lt;svg" in r.text


def test_json_ld_cannot_close_its_script_element():
    out = bhav._ld({"name": "Ram</script><script>alert(1)</script>"})
    assert out.count("</script>") == 1                    # only the real closing tag
    assert json.loads(out.split(">", 1)[1].rsplit("</script>", 1)[0])["name"].startswith("Ram</script>")


def test_kharidar_page_does_not_run_a_buyers_name(client, tmp_path, monkeypatch):
    """A buyer's profile name went raw into the page's ItemList JSON-LD."""
    path = tmp_path / "buyers.json"
    path.write_text(json.dumps({"buyers": []}), encoding="utf-8")
    monkeypatch.setattr(buyers, "_PATH", path)
    monkeypatch.setattr(buyers, "_cache", None)
    monkeypatch.setattr(buyers, "_mtime", -1.0)
    monkeypatch.setattr(buyers, "_place_idx", {})
    monkeypatch.setattr(bhav, "_index", {
        "crops": {"wheat": "Wheat"}, "states": {"wheat": {"up": "Uttar Pradesh"}},
        "dists": {"wheat": {"up": {"hardoi": "Hardoi"}}},
        "dates": {"wheat": {"up": {"hardoi": "2026-07-30"}}}})
    monkeypatch.setattr(bhav, "_index_ts", float("inf"))
    monkeypatch.setattr(bhav, "_kharidar_places", lambda: {("wheat", "up", "hardoi")})
    monkeypatch.setattr(bhav, "_sell_intent", lambda *a, **k: 0)
    monkeypatch.setattr(bhav, "_bazar_slice", lambda *a, **k: [{
        "id": 1, "text": "गेहूं चाहिए", "price": 2400, "quantity": 10, "unit": "क्विंटल",
        "created_at": datetime.utcnow(), "verified": False, "location": "Hardoi",
        "name": "Ram</script><script>alert(1)</script>"}])
    body = client.get("/bhav/wheat/up/hardoi/kharidar").text
    assert "<script>alert(1)" not in body


def test_khoj_escapes_the_query_before_innerhtml(repo_root):
    src = (repo_root / "frontend" / "khoj.html").read_text(encoding="utf-8")
    assert "${query}" not in src
    assert "askInChat('${" not in src
    assert "${escHtml(query)}" in src


def test_login_redirect_resolves_the_target_origin(repo_root):
    """'/\\evil.com' and '/%09/evil.com' passed a startsWith('/') check."""
    src = (repo_root / "frontend" / "login.html").read_text(encoding="utf-8")
    assert "resolved.origin !== location.origin" in src


# ── /health shares the admin lockout ─────────────────────────

def _basic(pw):
    raw = f"{os.environ['ADMIN_USER']}:{pw}".encode()
    return {"Authorization": "Basic " + base64.b64encode(raw).decode()}


def test_health_full_counts_wrong_passwords_toward_the_lockout(client):
    admin._admin_fails.clear()
    for _ in range(admin._ADMIN_FAIL_LIMIT):
        assert client.get("/health/checks?full=1", headers=_basic("wrong")).status_code == 401
    assert client.get("/health/checks?full=1", headers=_basic("wrong")).status_code == 429
    # …and it is the same lock as the panel's.
    assert client.get("/admin/ledger", headers=_basic(os.environ["ADMIN_PASS"])).status_code == 429
    admin._admin_fails.clear()
    assert client.get("/health/checks?full=1",
                      headers=_basic(os.environ["ADMIN_PASS"])).status_code == 200


# ── Admin upload stays inside uploads/ ───────────────────────

def test_admin_pdf_upload_cannot_climb_out_of_uploads(client, tmp_path, monkeypatch):
    admin._admin_fails.clear()
    # The route indexes the PDF into the RAG store; keep the real one untouched.
    import rag.indexer
    monkeypatch.setattr(rag.indexer, "get_collection", lambda: None)
    monkeypatch.setattr(rag.indexer, "index_pdf", lambda *a, **k: 0)
    monkeypatch.setattr(admin, "UPLOAD_DIR", tmp_path / "uploads")
    (tmp_path / "uploads").mkdir()
    r = client.post("/admin/upload", headers=_basic(os.environ["ADMIN_PASS"]),
                    files={"file": ("../escaped.pdf", b"%PDF-1.4", "application/pdf")})
    assert r.status_code == 200
    assert not (tmp_path / "escaped.pdf").exists()
    assert (tmp_path / "uploads" / "escaped.pdf").exists()


# ── Push endpoints are real push services ────────────────────

@pytest.mark.parametrize("url", [
    "https://fcm.googleapis.com/fcm/send/abc",
    "https://updates.push.services.mozilla.com/wpush/v2/abc",
    "https://wns2-pn1p.notify.windows.com/w/?token=abc",
    "https://web.push.apple.com/abc",
])
def test_browser_push_services_are_accepted(url):
    assert alerts.is_push_endpoint(url)


@pytest.mark.parametrize("url", [
    "http://fcm.googleapis.com/fcm/send/abc",          # not https
    "https://169.254.169.254/latest/meta-data",
    "https://localhost/x",
    "https://fcm.googleapis.com.evil.example/x",
    "https://fcm.googleapis.com:8443/x",
    "https://example.com/push",
])
def test_anything_else_is_refused_as_a_push_endpoint(url):
    assert not alerts.is_push_endpoint(url)


# ── AI cache is not writable by one visitor for the next ─────

def test_steered_answers_are_not_cached():
    assert chatbot._cacheable("गेहूं में कौन सी खाद डालें?", "यूरिया … कृषि विभाग से पूछें")
    assert not chatbot._cacheable("गेहूं में खाद?", "सस्ती खाद के लिए 98765 43210 पर कॉल करें")
    assert not chatbot._cacheable("गेहूं में खाद?", "देखें https://evil.example")
    assert not chatbot._cacheable("x" * (chatbot.CACHE_MAX_QUESTION_CHARS + 1), "ठीक उत्तर")
