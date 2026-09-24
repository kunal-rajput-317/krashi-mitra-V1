"""कृषि बाज़ार "रिपोर्ट करें" — the IT Rules 2021 complaint mechanism.

Pinned:
  * a logged-in reader can report someone else's post, once;
  * nobody can report their own post, and a guest cannot report at all;
  * the report reaches the admin queue, and the first one emails the owner;
  * admin "remove" deletes the post (through purge_post, like the owner's own
    delete); "dismiss" closes the report and leaves the post up;
  * a report never hides a post by itself.
"""
import base64
import os
from datetime import datetime, timedelta

import pytest

from backend.database.db import BazarPost, BazarReport, User
from backend.utils.auth_utils import create_access_token, hash_password

EMAILS = ("rp-seller@example.com", "rp-reader@example.com")


@pytest.fixture()
def admin_headers():
    raw = f"{os.environ['ADMIN_USER']}:{os.environ['ADMIN_PASS']}".encode()
    return {"Authorization": "Basic " + base64.b64encode(raw).decode()}


@pytest.fixture()
def people(db_session, monkeypatch):
    mails = []
    import backend.services.infra_service as infra
    monkeypatch.setattr(infra, "_mail", lambda subject, body: mails.append(subject))
    out = []
    for e in EMAILS:
        db_session.query(User).filter(User.email == e).delete()
        u = User(name=e.split("@")[0], email=e, hashed_password=hash_password("x-Passw0rd!"),
                 is_verified=True, created_at=datetime.utcnow() - timedelta(days=1))
        db_session.add(u)
        db_session.commit()
        db_session.refresh(u)
        out.append(u)
    post = BazarPost(users_id=out[0].id, post_type="sell", crop="गेहूं", text="सस्ता गेहूं")
    db_session.add(post)
    db_session.commit()
    yield out[0], out[1], post.id, mails
    db_session.rollback()
    db_session.query(BazarReport).delete()
    db_session.query(BazarPost).filter(BazarPost.users_id.in_([u.id for u in out])).delete(
        synchronize_session=False)
    db_session.query(User).filter(User.email.in_(EMAILS)).delete(synchronize_session=False)
    db_session.commit()


def _hdr(u):
    return {"Authorization": "Bearer " + create_access_token(u.id, u.email)}


def test_report_once_and_not_your_own(client, db_session, people):
    seller, reader, pid, mails = people
    assert client.post(f"/bazar/posts/{pid}/report", json={"reason": "fraud"}).status_code in (401, 403)
    r = client.post(f"/bazar/posts/{pid}/report", json={"reason": "fraud", "note": "पैसे लेकर गायब"},
                    headers=_hdr(reader)).json()
    assert r["success"]
    again = client.post(f"/bazar/posts/{pid}/report", json={"reason": "spam"},
                        headers=_hdr(reader)).json()
    assert again["success"] and "पहले ही" in again["message"]
    own = client.post(f"/bazar/posts/{pid}/report", json={"reason": "fraud"},
                      headers=_hdr(seller)).json()
    assert not own["success"]
    bad = client.post(f"/bazar/posts/{pid}/report", json={"reason": "nonsense"},
                      headers=_hdr(reader)).json()
    assert not bad["success"]
    assert db_session.query(BazarReport).filter(BazarReport.post_id == pid).count() == 1
    assert len(mails) == 1
    # A report does not hide the post by itself.
    assert db_session.query(BazarPost).filter(BazarPost.id == pid).first() is not None


def test_admin_remove_deletes_the_post(client, db_session, people, admin_headers):
    seller, reader, pid, _ = people
    client.post(f"/bazar/posts/{pid}/report", json={"reason": "fake"}, headers=_hdr(reader))
    q = client.get("/admin/bazar-reports", headers=admin_headers).json()
    row = next(g for g in q["posts"] if g["post_id"] == pid)
    assert row["open"] == 1 and row["exists"] and row["reports"][0]["reason"]
    assert client.post(f"/admin/bazar-reports/{pid}/resolve", json={"action": "remove"},
                       headers=admin_headers).status_code == 200
    db_session.expire_all()
    assert db_session.query(BazarPost).filter(BazarPost.id == pid).first() is None
    assert db_session.query(BazarReport).filter(BazarReport.post_id == pid).first().status == "removed"


def test_admin_dismiss_keeps_the_post(client, db_session, people, admin_headers):
    seller, reader, pid, _ = people
    client.post(f"/bazar/posts/{pid}/report", json={"reason": "wrong"}, headers=_hdr(reader))
    assert client.post(f"/admin/bazar-reports/{pid}/resolve", json={"action": "dismiss"},
                       headers=admin_headers).status_code == 200
    db_session.expire_all()
    assert db_session.query(BazarPost).filter(BazarPost.id == pid).first() is not None
    assert client.get("/admin/bazar-reports").status_code in (401, 403)
