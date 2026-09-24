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

    from backend.database.db import BazarMediaChange, BazarPost, User, UserProfile
    from backend.utils.auth_utils import create_access_token

    def _wipe():
        rows = db_session.query(User).filter(User.email == EMAIL).all()
        stale = [u.id for u in rows]
        accts = [u.user_id for u in rows if u.user_id is not None]
        if stale:
            db_session.query(BazarPost).filter(BazarPost.users_id.in_(stale)).delete()
            # bazar_media_changes is append-only and has no FK to cascade from
            # (see the model — a cascade would let a farmer reset his own daily
            # counter by deleting the listing), so the ledger has to be swept
            # here or every run leaves rows behind.
            db_session.query(BazarMediaChange).filter(
                BazarMediaChange.users_id.in_(stale)).delete()
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


# ── Replacing the photo ──────────────────────────────────────
# Asked for 17 Sep 2026, blocked until R2 went live on the 18th because a
# replacement meant writing to Render's ephemeral disk. Re-shooting a listing
# used to mean deleting the post and losing its likes, comments and offers.

R2_ENV = {
    "R2_ACCOUNT_ID":        "acct123",
    "R2_ACCESS_KEY_ID":     "AKIAEXAMPLE",
    "R2_SECRET_ACCESS_KEY": "s3cret-example-key",
    "R2_BUCKET":            "krashimitra-media",
    "R2_PUBLIC_BASE":       "https://media.krashimitra.in",
}


class _OK:
    status_code = 200
    text = ""


@pytest.fixture()
def r2(monkeypatch):
    """A configured bucket whose PUTs and DELETEs are recorded, not sent.

    The PUT log keeps the **headers** as well as the URL. Only the URL was kept
    at first, and that is precisely what let the Content-Type bug below through:
    the object was stored under the right key with the wrong type, and a log of
    keys alone could not tell the difference.
    """
    from backend.services import media_store

    for k, v in R2_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("R2_ENDPOINT", raising=False)
    log = {"put": [], "delete": [], "put_headers": []}

    def _put(url, data=None, headers=None, timeout=None):
        log["put"].append(url)
        log["put_headers"].append(headers or {})
        return _OK()

    monkeypatch.setattr(media_store.requests, "put", _put)
    monkeypatch.setattr(media_store.requests, "delete",
                        lambda url, headers=None, timeout=None:
                        (log["delete"].append(url), _OK())[1])
    return log


def _photo(w=800, h=600):
    import io

    from PIL import Image

    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(0, h, 8):
        for x in range(0, w, 8):
            px[x, y] = ((x * 7) % 256, (y * 13) % 256, ((x + y) * 3) % 256)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _post_with_photo(client, headers):
    r = client.post("/bazar/posts", headers=headers,
                    data={"post_type": "sell", "crop": "गेहूं", "price": "900"},
                    files={"media": ("crop.jpg", _photo(), "image/jpeg")})
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _change(client, headers, pid):
    return client.post(f"/bazar/posts/{pid}/media", headers=headers,
                       files={"media": ("new.jpg", _photo(640, 480), "image/jpeg")})


class TestChangePhoto:
    def test_the_photo_can_be_replaced(self, client, seller, r2):
        _, headers = seller
        post = _post_with_photo(client, headers)

        r = _change(client, headers, post["id"])
        assert r.status_code == 200, r.text
        new = r.json()["data"]["post"]
        assert new["media_url"] != post["media_url"]
        assert new["media_url"].startswith("https://media.krashimitra.in/bazar/")

    def test_the_old_object_is_deleted(self, client, seller, r2):
        """Otherwise every replacement leaks bytes into a 10 GB free tier that
        nothing will ever clean up."""
        from backend.services import media_store

        _, headers = seller
        post = _post_with_photo(client, headers)
        old_key = media_store.key_for(post["media_url"])

        _change(client, headers, post["id"])
        assert any(url.endswith(old_key) for url in r2["delete"]), (
            f"the replaced object {old_key} was never deleted from R2")

    def test_the_listing_keeps_its_likes_and_comments(self, client, seller, r2):
        """The whole reason this endpoint exists. Deleting and reposting was
        the old workaround and it threw away the conversation underneath."""
        _, headers = seller
        post = _post_with_photo(client, headers)
        client.post(f"/bazar/posts/{post['id']}/comments", headers=headers,
                    json={"text": "भाव क्या है?"})

        _change(client, headers, post["id"])
        after = client.get(f"/bazar/posts/{post['id']}", headers=headers).json()["data"]
        assert after["id"] == post["id"]
        assert after["comments_count"] == 1, (
            "replacing the photo lost the thread — that is the bug this replaces")

    def test_a_stranger_cannot_change_it(self, client, seller, r2):
        _, headers = seller
        post = _post_with_photo(client, headers)
        assert _change(client, {}, post["id"]).status_code == 401

    def test_the_fourth_change_in_a_day_is_refused(self, client, seller, r2):
        from backend.routes.bazar import MAX_MEDIA_CHANGES_PER_DAY

        _, headers = seller
        post = _post_with_photo(client, headers)
        for i in range(MAX_MEDIA_CHANGES_PER_DAY):
            assert _change(client, headers, post["id"]).status_code == 200, i
        r = _change(client, headers, post["id"])
        assert r.status_code == 429, r.text
        assert "3" in r.json()["detail"]

    def test_the_cap_is_per_account_not_per_listing(self, client, seller, r2):
        """A per-post counter would let one account spend thirty uploads a day
        across ten listings — the reason bazar_media_changes exists at all
        instead of another column on bazar_posts."""
        from backend.routes.bazar import MAX_MEDIA_CHANGES_PER_DAY

        _, headers = seller
        posts = [_post_with_photo(client, headers) for _ in range(4)]
        for i in range(MAX_MEDIA_CHANGES_PER_DAY):
            assert _change(client, headers, posts[i]["id"]).status_code == 200, i
        # A different listing, first change on that post, and still refused.
        r = _change(client, headers, posts[3]["id"])
        assert r.status_code == 429, (
            "the fourth upload of the day went through on a fresh listing — "
            "the cap is counting posts, not the account")

    def test_a_refused_upload_costs_nothing(self, client, seller, r2):
        """A farmer on a bad connection must be able to retry. An attempt that
        never stored anything may not spend one of the day's three."""
        _, headers = seller
        post = _post_with_photo(client, headers)

        bad = client.post(f"/bazar/posts/{post['id']}/media", headers=headers,
                          files={"media": ("notes.txt", b"not an image", "text/plain")})
        assert bad.status_code == 400, bad.text

        r = _change(client, headers, post["id"])
        assert r.status_code == 200, r.text
        assert r.json()["data"]["media_changes_left"] == 2, (
            "a rejected file was counted against the daily limit")

    def test_the_row_does_not_move_when_the_upload_fails(self, client, seller, r2,
                                                         monkeypatch):
        """The reverse order — clear the row, then upload — is how a listing
        ends up pointing at nothing, which is the original bug of this whole
        subsystem."""
        from backend.services import media_store

        _, headers = seller
        post = _post_with_photo(client, headers)

        class _Boom:
            status_code = 500
            text = "R2 said no"

        monkeypatch.setattr(media_store.requests, "put",
                            lambda url, data=None, headers=None, timeout=None: _Boom())
        assert _change(client, headers, post["id"]).status_code == 502

        after = client.get(f"/bazar/posts/{post['id']}", headers=headers).json()["data"]
        assert after["media_url"] == post["media_url"], (
            "a failed upload left the listing pointing at a photo that was "
            "never stored")

    def test_a_listing_with_no_photo_can_gain_one(self, client, seller, r2):
        """Nothing to replace is not an error — a text-only listing whose
        photo was lost to the old disk is exactly who needs this most."""
        _, headers = seller
        pid = _make_post(client, headers)
        r = _change(client, headers, pid)
        assert r.status_code == 200, r.text
        assert r.json()["data"]["post"]["media_url"]


# ── The uploaded file's NAME is load-bearing ─────────────────
# `_save_media` reads the extension to decide image vs video and, for a video,
# which Content-Type to store the R2 object with (VIDEO_CONTENT_TYPES). R2
# serves back whatever it was stored with, and a <video> tag will not play a
# file the browser is told is the wrong kind.
#
# The first cut of `onEditMediaPicked()` passed a hardcoded third argument to
# FormData.append — `fd.append('media', file, 'clip.mp4')` — which renamed every
# replacement. A farmer swapping in a .webm got an object stored as video/mp4
# and a listing whose video silently would not play. Nothing caught it: the
# tests used .jpg, the browser check stubbed the network, and the R2 log kept
# only keys. These two pin both halves.

WEBM_HEADER = b"\x1a\x45\xdf\xa3"       # EBML — what _is_video() looks for


class TestTheStoredContentTypeMatchesTheFile:
    def _replace_with(self, client, headers, pid, name, blob, mime):
        return client.post(f"/bazar/posts/{pid}/media", headers=headers,
                           files={"media": (name, blob, mime)})

    def test_a_webm_is_not_stored_as_mp4(self, client, seller, r2):
        _, headers = seller
        pid = _make_post(client, headers)

        r = self._replace_with(client, headers, pid, "clip.webm",
                               WEBM_HEADER + b"\x00" * 800, "video/webm")
        assert r.status_code == 200, r.text

        url = r.json()["data"]["post"]["media_url"]
        assert url.endswith(".webm"), f"the key lost its extension: {url}"
        ct = r2["put_headers"][-1].get("content-type")
        assert ct == "video/webm", (
            f"stored as {ct!r} — R2 will serve that back and the browser will "
            f"refuse to play a WebM it was told is an MP4")

    def test_a_mov_keeps_quicktime(self, client, seller, r2):
        _, headers = seller
        pid = _make_post(client, headers)
        r = self._replace_with(client, headers, pid, "clip.mov",
                               b"\x00\x00\x00\x18ftypqt  " + b"\x00" * 800,
                               "video/quicktime")
        assert r.status_code == 200, r.text
        assert r2["put_headers"][-1].get("content-type") == "video/quicktime"

    def test_the_confirmation_names_what_was_replaced(self, client, seller, r2):
        """The form takes both, so "फोटो बदल गई" after a video swap reads as
        the wrong listing having been touched."""
        _, headers = seller
        pid = _make_post(client, headers)

        r = self._replace_with(client, headers, pid, "clip.webm",
                               WEBM_HEADER + b"\x00" * 800, "video/webm")
        assert "Video" in r.json()["message"], r.json()["message"]

        r = self._replace_with(client, headers, pid, "crop.jpg", _photo(), "image/jpeg")
        assert "Photo" in r.json()["message"], r.json()["message"]

    def test_photos_are_always_webp_whatever_arrives(self, client, seller, r2):
        """Images have no such table — every one is re-encoded on the way in,
        which is what makes ~200 KB and the 10 GB tier's ~50k photos true."""
        _, headers = seller
        pid = _make_post(client, headers)
        r = self._replace_with(client, headers, pid, "crop.png", _photo(), "image/png")
        assert r.status_code == 200, r.text
        assert r.json()["data"]["post"]["media_url"].endswith(".webp")
        assert r2["put_headers"][-1].get("content-type") == "image/webp"


class TestTheEditFormDoesNotRenameTheFile:
    """A source guard, because the bug lived in the browser and no server test
    could see it — the endpoint was always given an honest filename."""

    def _js(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        return (root / "frontend" / "krashi_bajar.html").read_text(encoding="utf-8")

    def test_no_hardcoded_filename_on_the_media_field(self):
        import re

        js = self._js()
        appends = re.findall(r"\.append\(\s*['\"]media['\"]\s*,[^)]*\)", js)
        assert appends, "no media upload found — did the field get renamed?"
        for call in appends:
            # Two arguments only. A third is a filename override, and the
            # server decides the stored Content-Type from it.
            assert call.count(",") == 1, (
                f"{call.strip()} renames the uploaded file. The server reads "
                f"the extension to pick the stored Content-Type, and "
                f"shrinkImage() already keeps the name matching the bytes.")
