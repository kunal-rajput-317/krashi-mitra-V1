"""Listing media survives a redeploy.

Every crop photo a farmer had ever posted was a 404 by 14 Sep 2026 — Render
wipes its disk on redeploy while the DB keeps pointing at the missing file, so
the feed rendered black bars over four real listings. Media now goes to
Cloudflare R2.

What is pinned here is what would silently break that again:

  * a half-configured bucket must read as OFF, not as "upload into the void" —
    bytes nobody can fetch back are the original bug wearing a new hat;
  * the SigV4 signature, because a wrong one fails only in production, only on
    a real upload, and reads as a generic 403;
  * the photo must actually shrink, since the whole free-tier budget assumes
    ~200 KB and not the 4 MB a phone hands over;
  * an absolute R2 URL must not be prefixed with the backend origin anywhere —
    the WhatsApp/OG preview glued the two together and previewed nothing.
"""

import asyncio
import hashlib
import io

import pytest

from backend.services import media_store


R2_ENV = {
    "R2_ACCOUNT_ID":        "acct123",
    "R2_ACCESS_KEY_ID":     "AKIAEXAMPLE",
    "R2_SECRET_ACCESS_KEY": "s3cret-example-key",
    "R2_BUCKET":            "krashimitra-media",
    "R2_PUBLIC_BASE":       "https://media.krashimitra.in",
}


@pytest.fixture()
def r2(monkeypatch):
    """A fully configured bucket, with no R2_ENDPOINT override."""
    for k, v in R2_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("R2_ENDPOINT", raising=False)
    return R2_ENV


def _photo(w=4032, h=3024, fmt="JPEG"):
    """Bytes roughly the shape of what a phone camera produces."""
    from PIL import Image

    img = Image.new("RGB", (w, h))
    # Flat colour compresses to almost nothing and would make the shrink test
    # vacuous, so give it something to encode.
    px = img.load()
    for y in range(0, h, 8):
        for x in range(0, w, 8):
            px[x, y] = ((x * 7) % 256, (y * 13) % 256, ((x + y) * 3) % 256)
    buf = io.BytesIO()
    img.save(buf, format=fmt, quality=95)
    return buf.getvalue()


# ── Configuration ────────────────────────────────────────────

def test_enabled_only_when_every_credential_is_present(r2, monkeypatch):
    assert media_store.enabled()
    for missing in R2_ENV:
        monkeypatch.delenv(missing, raising=False)
        assert not media_store.enabled(), (
            f"{missing} is unset and R2 still reports enabled — a half-configured "
            f"bucket must fall back to disk, not upload bytes nobody can read"
        )
        monkeypatch.setenv(missing, R2_ENV[missing])


def test_disabled_with_no_env_at_all(monkeypatch):
    for k in list(R2_ENV) + ["R2_ENDPOINT"]:
        monkeypatch.delenv(k, raising=False)
    assert not media_store.enabled()


def test_put_refuses_when_unconfigured(monkeypatch):
    for k in list(R2_ENV) + ["R2_ENDPOINT"]:
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(RuntimeError):
        media_store.put(b"x", "bazar/x.webp", "image/webp")


def test_public_base_trailing_slash_does_not_double(monkeypatch):
    for k, v in R2_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("R2_PUBLIC_BASE", "https://media.krashimitra.in/")
    assert media_store.public_url("bazar/a.webp") == \
        "https://media.krashimitra.in/bazar/a.webp"


def test_owns_and_key_for_round_trip(r2):
    url = media_store.public_url("bazar/deadbeef.webp")
    assert media_store.owns(url)
    assert media_store.key_for(url) == "bazar/deadbeef.webp"
    # A legacy disk path and another origin are not ours to delete.
    assert not media_store.owns("/uploads/bazar/deadbeef.jpg")
    assert not media_store.owns("https://example.com/bazar/deadbeef.webp")
    assert not media_store.owns(None)


# ── SigV4 ────────────────────────────────────────────────────

def test_signature_covers_the_payload(r2):
    """Two different bodies must not produce the same signature.

    x-amz-content-sha256 is the whole point of SigV4 for an upload: without the
    payload in the signed string, a signature intercepted once would authorise
    any body at that key.
    """
    url_a, head_a = media_store._sign("PUT", "bazar/a.webp", b"one",
                                      {"content-type": "image/webp"})
    url_b, head_b = media_store._sign("PUT", "bazar/a.webp", b"two",
                                      {"content-type": "image/webp"})
    assert url_a == url_b
    assert head_a["x-amz-content-sha256"] == hashlib.sha256(b"one").hexdigest()
    assert head_a["Authorization"] != head_b["Authorization"]


def test_signed_request_shape(r2):
    url, headers = media_store._sign("PUT", "bazar/a.webp", b"body", {
        "content-type":  "image/webp",
        "cache-control": media_store.CACHE_CONTROL,
    })
    # Path style against the account endpoint — R2 has no virtual-host form.
    assert url == ("https://acct123.r2.cloudflarestorage.com"
                   "/krashimitra-media/bazar/a.webp")
    assert headers["host"] == "acct123.r2.cloudflarestorage.com"

    auth = headers["Authorization"]
    assert auth.startswith("AWS4-HMAC-SHA256 Credential=AKIAEXAMPLE/")
    # R2 accepts "auto" and nothing else.
    assert "/auto/s3/aws4_request" in auth

    signed = auth.split("SignedHeaders=")[1].split(",")[0]
    names = signed.split(";")
    assert names == sorted(names), "SignedHeaders must be in lexical order"
    for required in ("host", "x-amz-content-sha256", "x-amz-date"):
        assert required in names
    # Everything named as signed must actually be a header we send, or the
    # server recomputes over a different set and rejects with a bare 403.
    for n in names:
        assert n in headers
    assert "authorization" not in names


def test_endpoint_override_is_honoured(r2, monkeypatch):
    monkeypatch.setenv("R2_ENDPOINT", "https://s3.example.test")
    url, headers = media_store._sign("DELETE", "bazar/a.webp", b"", {})
    assert url == "https://s3.example.test/krashimitra-media/bazar/a.webp"
    assert headers["host"] == "s3.example.test"
    # Empty body signs as the SHA-256 of nothing, not as an empty string.
    assert headers["x-amz-content-sha256"] == hashlib.sha256(b"").hexdigest()


def test_put_sends_the_bytes_and_returns_the_public_url(r2, monkeypatch):
    seen = {}

    class _Resp:
        status_code = 200
        text = ""

    def _fake_put(url, data=None, headers=None, timeout=None):
        seen.update(url=url, data=data, headers=headers)
        return _Resp()

    monkeypatch.setattr(media_store.requests, "put", _fake_put)
    out = media_store.put(b"webp-bytes", "bazar/x.webp", "image/webp")

    assert out == "https://media.krashimitra.in/bazar/x.webp"
    assert seen["data"] == b"webp-bytes"
    assert seen["headers"]["content-type"] == "image/webp"
    # Keys are UUIDs, so the bytes at a URL can never change — cache forever.
    assert "immutable" in seen["headers"]["cache-control"]


def test_put_raises_on_a_rejected_upload(r2, monkeypatch):
    class _Resp:
        status_code = 403
        text = "SignatureDoesNotMatch"

    monkeypatch.setattr(media_store.requests, "put",
                        lambda *a, **k: _Resp())
    with pytest.raises(RuntimeError):
        media_store.put(b"x", "bazar/x.webp", "image/webp")


def test_delete_is_best_effort_and_never_raises(r2, monkeypatch):
    def _boom(*a, **k):
        raise OSError("network down")

    monkeypatch.setattr(media_store.requests, "delete", _boom)
    # A farmer deleting his own listing must not be blocked by R2 being down.
    assert media_store.delete("https://media.krashimitra.in/bazar/x.webp") is False


def test_delete_skips_urls_we_do_not_own(r2, monkeypatch):
    def _never(*a, **k):
        raise AssertionError("must not call R2 for a foreign URL")

    monkeypatch.setattr(media_store.requests, "delete", _never)
    assert media_store.delete("/uploads/bazar/old.jpg") is False


# ── Image re-encoding ────────────────────────────────────────

def test_shrink_bounds_the_long_edge_and_shrinks_the_bytes():
    from PIL import Image

    raw = _photo()
    out, ctype, ext = media_store.shrink_image(raw)

    assert (ctype, ext) == ("image/webp", ".webp")
    img = Image.open(io.BytesIO(out))
    assert img.format == "WEBP"
    assert max(img.size) == media_store.MAX_EDGE
    # The free-tier budget assumes ~200 KB per photo, not the megabytes a
    # phone hands over. Anything close to the original means the re-encode
    # silently stopped happening.
    assert len(out) < len(raw) / 4


def test_shrink_leaves_a_small_photo_within_bounds():
    from PIL import Image

    out, _, _ = media_store.shrink_image(_photo(800, 600, fmt="PNG"))
    img = Image.open(io.BytesIO(out))
    assert img.size == (800, 600), "an already-small photo must not be upscaled"


def test_shrink_honours_exif_orientation():
    """A phone records rotation in EXIF instead of rotating the pixels."""
    from PIL import Image

    img = Image.new("RGB", (400, 200), (10, 120, 60))
    buf = io.BytesIO()
    exif = img.getexif()
    exif[0x0112] = 6          # Orientation: rotate 90° CW
    img.save(buf, format="JPEG", exif=exif)

    out, _, _ = media_store.shrink_image(buf.getvalue())
    assert Image.open(io.BytesIO(out)).size == (200, 400)


def test_shrink_rejects_a_non_image():
    with pytest.raises(ValueError):
        media_store.shrink_image(b"this is not a photo, it is a sentence")


def test_shrink_rejects_a_decompression_bomb(monkeypatch):
    """The byte cap says nothing about pixel count, which is the whole trick."""
    monkeypatch.setattr(media_store, "MAX_PIXELS", 1000)
    with pytest.raises(ValueError):
        media_store.shrink_image(_photo(200, 200))


# ── The upload path end to end ───────────────────────────────

def _upload(data: bytes, filename: str):
    from fastapi import UploadFile

    return UploadFile(file=io.BytesIO(data), filename=filename)


def test_photo_upload_lands_in_r2_as_webp(r2, monkeypatch):
    from backend.routes import bazar

    sent = {}

    class _Resp:
        status_code = 200
        text = ""

    def _fake_put(url, data=None, headers=None, timeout=None):
        sent.update(url=url, data=data, headers=headers)
        return _Resp()

    monkeypatch.setattr(media_store.requests, "put", _fake_put)

    raw = _photo()
    url, kind = asyncio.run(bazar._save_media(_upload(raw, "crop.jpg")))

    assert kind == "image"
    assert url.startswith("https://media.krashimitra.in/bazar/")
    assert url.endswith(".webp"), "a JPEG must be stored re-encoded, not as-is"
    # The bytes that left the building are the shrunk WebP, not the original.
    assert sent["data"][:4] == b"RIFF" and sent["data"][8:12] == b"WEBP"
    assert len(sent["data"]) < len(raw) / 4
    assert sent["headers"]["content-type"] == "image/webp"


def test_video_upload_is_stored_unchanged(r2, monkeypatch):
    """No ffmpeg on this dyno, so a video goes up exactly as it arrived."""
    from backend.routes import bazar

    sent = {}

    class _Resp:
        status_code = 200
        text = ""

    monkeypatch.setattr(media_store.requests, "put",
                        lambda url, data=None, headers=None, timeout=None:
                        (sent.update(url=url, data=data, headers=headers), _Resp())[1])

    body = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 2048
    url, kind = asyncio.run(bazar._save_media(_upload(body, "clip.mp4")))

    assert kind == "video"
    assert url.endswith(".mp4")
    assert sent["data"] == body
    assert sent["headers"]["content-type"] == "video/mp4"


def test_upload_falls_back_to_disk_without_credentials(monkeypatch, tmp_path):
    """`uvicorn` with no R2 env must still accept a photo, or local development
    of the composer is impossible."""
    from backend.routes import bazar

    for k in list(R2_ENV) + ["R2_ENDPOINT"]:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(bazar, "BAZAR_UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(media_store.requests, "put", lambda *a, **k:
                        pytest.fail("must not call R2 when unconfigured"))

    url, kind = asyncio.run(bazar._save_media(_upload(_photo(1200, 900), "crop.jpg")))
    assert (url, kind) == (f"/uploads/bazar/{url.rsplit('/', 1)[-1]}", "image")
    written = list(tmp_path.iterdir())
    assert len(written) == 1 and written[0].suffix == ".webp"


def test_production_refuses_to_store_media_on_the_ephemeral_disk(monkeypatch, tmp_path):
    """The silent-data-loss setting must be loud.

    Writing to Render's disk looked like success for months while every photo
    was thrown away on the next redeploy. With R2 unconfigured in production the
    upload now fails in front of the farmer instead.
    """
    from fastapi import HTTPException

    from backend.routes import bazar

    for k in list(R2_ENV) + ["R2_ENDPOINT"]:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(bazar, "IS_PROD", True)
    monkeypatch.setattr(bazar, "BAZAR_UPLOAD_DIR", tmp_path)

    with pytest.raises(HTTPException) as e:
        asyncio.run(bazar._save_media(_upload(_photo(800, 600), "crop.jpg")))
    assert e.value.status_code == 503
    assert not list(tmp_path.iterdir()), "nothing may be written to a disk that forgets"


def test_video_content_types_are_not_all_mp4():
    """R2 serves objects back with the type they were stored under, and a
    <video> tag will not play a file it is told is the wrong kind."""
    from backend.routes import bazar

    assert set(bazar.VIDEO_CONTENT_TYPES) == bazar.VIDEO_EXTS
    assert bazar.VIDEO_CONTENT_TYPES[".webm"] == "video/webm"
    assert bazar.VIDEO_CONTENT_TYPES[".mov"] == "video/quicktime"


def test_a_failed_r2_upload_is_a_502_not_a_broken_listing(r2, monkeypatch):
    """The old code created the post regardless; a listing must never be saved
    pointing at bytes that never arrived."""
    from fastapi import HTTPException

    from backend.routes import bazar

    monkeypatch.setattr(media_store.requests, "put", lambda *a, **k:
                        (_ for _ in ()).throw(OSError("connection reset")))

    with pytest.raises(HTTPException) as e:
        asyncio.run(bazar._save_media(_upload(_photo(800, 600), "crop.jpg")))
    assert e.value.status_code == 502


def test_oversize_upload_is_refused_before_it_is_stored(r2, monkeypatch):
    from fastapi import HTTPException

    from backend.routes import bazar

    monkeypatch.setattr(bazar, "MAX_IMAGE_BYTES", 1024)
    monkeypatch.setattr(media_store.requests, "put", lambda *a, **k:
                        pytest.fail("an oversize file must never reach R2"))

    with pytest.raises(HTTPException) as e:
        asyncio.run(bazar._save_media(_upload(_photo(2000, 1500), "crop.jpg")))
    assert e.value.status_code == 400


def test_a_renamed_executable_is_refused_on_its_magic_number(r2, monkeypatch):
    """The extension only says what the caller claims."""
    from fastapi import HTTPException

    from backend.routes import bazar

    monkeypatch.setattr(media_store.requests, "put", lambda *a, **k:
                        pytest.fail("non-media must never reach R2"))

    with pytest.raises(HTTPException) as e:
        asyncio.run(bazar._save_media(_upload(b"MZ\x90\x00" + b"\x00" * 900, "crop.jpg")))
    assert e.value.status_code == 400


def test_unknown_extension_is_refused(r2):
    from fastapi import HTTPException

    from backend.routes import bazar

    with pytest.raises(HTTPException) as e:
        asyncio.run(bazar._save_media(_upload(b"%PDF-1.4\n", "rate-list.pdf")))
    assert e.value.status_code == 400


# ── Through the real endpoint ────────────────────────────────

SELLER_EMAIL = "bazar-media-kisan@example.com"


@pytest.fixture()
def seller(db_session):
    """A verified, profiled, reachable account + bearer headers.

    Same shape as tests/test_bazar_edit_and_limits.py::seller — the commits
    here outlive db_session's rollback, so a leftover row would collide on
    users.email next run.
    """
    from datetime import datetime

    from sqlalchemy import func

    from backend.database.db import BazarPost, User, UserProfile
    from backend.utils.auth_utils import create_access_token

    def _wipe():
        rows = db_session.query(User).filter(User.email == SELLER_EMAIL).all()
        stale = [u.id for u in rows]
        ids = [u.user_id for u in rows if u.user_id is not None]
        if stale:
            db_session.query(BazarPost).filter(BazarPost.users_id.in_(stale)).delete()
            if ids:
                db_session.query(UserProfile).filter(UserProfile.user_id.in_(ids)).delete()
            db_session.query(User).filter(User.id.in_(stale)).delete()
            db_session.commit()

    _wipe()
    user = User(name="Media Kisan", email=SELLER_EMAIL, hashed_password="x",
                is_verified=True, created_at=datetime.utcnow())
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    n = (db_session.query(func.max(UserProfile.id)).scalar() or 0) + 1
    user.user_id = n
    db_session.commit()
    db_session.add(UserProfile(
        id=n, user_id=n, name="Media Kisan", phone_number="9876500001",
        state="Uttar Pradesh", district="Hardoi", village="Rampur"))
    db_session.commit()
    yield user, {"Authorization": f"Bearer {create_access_token(user.id, user.email)}"}
    _wipe()


def test_posting_a_listing_with_a_photo_end_to_end(client, seller, r2, monkeypatch):
    """The multipart POST a farmer's phone actually sends.

    Everything above exercises _save_media directly; this is the only test that
    proves the form field, the profile/phone gate, the upload and the stored
    row line up.
    """
    sent = {}

    class _Resp:
        status_code = 200
        text = ""

    def _fake_put(url, data=None, headers=None, timeout=None):
        sent.update(url=url, data=data, headers=headers)
        return _Resp()

    monkeypatch.setattr(media_store.requests, "put", _fake_put)

    _, headers = seller
    r = client.post(
        "/bazar/posts",
        headers=headers,
        data={"post_type": "sell", "crop": "केला", "price": "2100"},
        files={"media": ("crop.jpg", _photo(3000, 2000), "image/jpeg")},
    )
    assert r.status_code == 200, r.text

    post = r.json()["data"]
    assert post["media_type"] == "image"
    assert post["media_url"].startswith("https://media.krashimitra.in/bazar/")
    assert post["media_url"].endswith(".webp")
    # The URL in the row is the one the bytes were PUT to.
    assert sent["url"].endswith(media_store.key_for(post["media_url"]))

    # And the feed serves it back as an absolute URL the browser can fetch
    # without the API base being glued on the front.
    feed = client.get("/bazar/feed").json()["data"]["posts"]
    mine = next(p for p in feed if p["id"] == post["id"])
    assert mine["media_url"] == post["media_url"]


def test_deleting_a_listing_removes_its_object_from_r2(client, seller, r2, monkeypatch):
    class _Resp:
        status_code = 200
        text = ""

    deleted = []
    monkeypatch.setattr(media_store.requests, "put",
                        lambda url, data=None, headers=None, timeout=None: _Resp())
    monkeypatch.setattr(media_store.requests, "delete",
                        lambda url, headers=None, timeout=None:
                        (deleted.append(url), _Resp())[1])

    _, headers = seller
    pid = client.post(
        "/bazar/posts", headers=headers,
        data={"post_type": "sell", "crop": "केला"},
        files={"media": ("crop.jpg", _photo(900, 700), "image/jpeg")},
    ).json()["data"]["id"]

    assert client.delete(f"/bazar/posts/{pid}", headers=headers).status_code == 200
    assert len(deleted) == 1 and "/krashimitra-media/bazar/" in deleted[0]


# ── The callers that assumed a relative path ─────────────────

def test_bazar_caps_are_what_a_farmer_on_rural_data_can_send():
    from backend.routes import bazar

    assert bazar.MAX_IMAGE_BYTES == 12 * 1024 * 1024
    assert bazar.MAX_VIDEO_BYTES == 40 * 1024 * 1024
    # Held in memory during upload on a 512 MB instance.
    assert bazar.MAX_VIDEO_BYTES <= 64 * 1024 * 1024


@pytest.fixture()
def listing(db_session):
    """One sell listing whose photo is on R2, cleaned up on the way out."""
    from backend.database.db import BazarPost

    post = BazarPost(
        users_id="r2-media-test-user",
        post_type="sell",
        crop="केला",
        media_url="https://media.krashimitra.in/bazar/abc123.webp",
        media_type="image",
        price=2100,
        unit="क्विंटल",
    )
    db_session.add(post)
    db_session.commit()
    try:
        yield post
    finally:
        db_session.delete(post)
        db_session.commit()


def test_share_preview_uses_the_r2_url_verbatim(client, listing):
    """og:image was built as BACKEND + media_url.

    With media on R2 that concatenates two absolute URLs into one string, and
    the WhatsApp preview for a listing renders no image at all.
    """
    html = client.get(f"/share/bazar/{listing.id}").text
    assert 'content="https://media.krashimitra.in/bazar/abc123.webp"' in html
    assert "onrender.comhttps://" not in html
    assert "krashimitra.inhttps://" not in html


def test_share_preview_still_prefixes_a_legacy_upload_path(client, db_session):
    """Rows from before R2 hold a relative path and must keep resolving."""
    from backend.database.db import BazarPost

    post = BazarPost(
        users_id="r2-media-test-legacy",
        post_type="sell",
        crop="गेहूं",
        media_url="/uploads/bazar/old.jpg",
        media_type="image",
    )
    db_session.add(post)
    db_session.commit()
    try:
        html = client.get(f"/share/bazar/{post.id}").text
        assert 'content="http' in html
        assert "/uploads/bazar/old.jpg" in html
        assert 'content="/uploads/' not in html, "a bare path is not a valid og:image"
    finally:
        db_session.delete(post)
        db_session.commit()


def test_frontend_caps_match_the_backend():
    """The composer rejects oversize files client-side, and its numbers are a
    separate copy. A farmer told 50 MB is fine by a page whose server refuses
    at 12 MB waits through the whole upload to be told no."""
    import io as _io
    from pathlib import Path

    html = _io.open(
        Path(__file__).resolve().parents[1] / "frontend" / "krashi_bajar.html",
        encoding="utf-8",
    ).read()
    assert "const MAX_IMAGE_MB   = 12;" in html
    assert "const MAX_VIDEO_MB   = 40;" in html
    # And the hint the farmer actually reads, in every language the page ships.
    assert html.count("photo ≤ 12MB, video ≤ 40MB") >= 4
