"""The festival popup is admin-only, and its upload has a ceiling.

/api/festival was the one admin surface in the app with no credential check on
it at all. Three POST routes — the popup config, the image upload and the AI
image generator — were reachable by anyone with curl, on production:

* **/config** sets the modal that every page on the site shows, including its
  text, its picture and the dates it is live between. A stranger could put
  anything in front of every farmer who opened the site.
* **/generate-image** spends money. It burns a Gemini call and then an Imagen 3
  generation, which is billed per image, against every key in the rotation.
* **/upload-image** wrote to this host's disk from an unauthenticated request,
  read the whole body into RAM on a 512MB box, and trusted the filename's
  extension about what the bytes were.

It was invisible from the panel because the panel didn't send credentials on
those four calls either, so the two halves agreed and the tab worked.

The sweep at the bottom is the part that matters most: it fails for any FUTURE
write route added to this router without a check, which is exactly how the
first three got here.
"""

import base64

import pytest

from backend.routes import festival

AUTH     = ("testadmin", "test-admin-pass")
BAD_PASS = ("testadmin", "not-the-password")

# A real 1x1 PNG — the byte sniffer has to see a genuine image header.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

VALID_CONFIG = {
    "active": True,
    "festival_name": "परीक्षा पर्व",
    "title": "शुभकामनाएं",
    "blessing_summary": "मंगलकामनाएं",
    "image_url": "",
    "start_time": "2026-01-01T00:00:00+05:30",
    "end_time": "2026-01-02T23:59:59+05:30",
}


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """Keep every write in this file away from the committed config and images."""
    monkeypatch.setattr(festival, "CONFIG_FILE", tmp_path / "festival_config.json")
    monkeypatch.setattr(festival, "FESTIVAL_IMG_DIR", tmp_path / "festivals")
    festival.FESTIVAL_IMG_DIR.mkdir(parents=True, exist_ok=True)
    return tmp_path


class TestTheWriteRoutesNeedCredentials:
    def test_config_rejects_an_anonymous_caller(self, client, sandbox):
        r = client.post("/api/festival/config", json=VALID_CONFIG)
        assert r.status_code == 401
        assert not festival.CONFIG_FILE.exists(), "a rejected call still wrote the config"

    def test_config_rejects_a_wrong_password(self, client, sandbox):
        r = client.post("/api/festival/config", json=VALID_CONFIG, auth=BAD_PASS)
        assert r.status_code == 401

    def test_upload_rejects_an_anonymous_caller(self, client, sandbox):
        r = client.post(
            "/api/festival/upload-image",
            files={"file": ("diya.png", PNG, "image/png")},
        )
        assert r.status_code == 401
        assert not list(festival.FESTIVAL_IMG_DIR.iterdir()), "a rejected upload still hit disk"

    def test_image_generation_rejects_an_anonymous_caller(self, client):
        """The expensive one. 401 has to land before any key is touched."""
        r = client.post("/api/festival/generate-image", json={"festival_name": "दिवाली"})
        assert r.status_code == 401

    def test_reading_the_config_stays_public(self, client):
        """The popup on every public page fetches this. It must not need a login."""
        r = client.get("/api/festival/config")
        assert r.status_code == 200
        assert r.json()["success"] is True


class TestTheUploadCeiling:
    def test_an_admin_can_still_upload(self, client, sandbox):
        r = client.post(
            "/api/festival/upload-image",
            files={"file": ("diya.png", PNG, "image/png")},
            auth=AUTH,
        )
        assert r.status_code == 200, r.text
        assert r.json()["image_url"].startswith("/images/festivals/")

    def test_bytes_that_are_not_an_image_are_refused(self, client, sandbox):
        """The extension used to be the only thing checked."""
        r = client.post(
            "/api/festival/upload-image",
            files={"file": ("payload.png", b"MZ\x90\x00" + b"\x00" * 512, "image/png")},
            auth=AUTH,
        )
        assert r.status_code == 400
        assert not list(festival.FESTIVAL_IMG_DIR.iterdir())

    def test_over_twelve_megabytes_is_refused(self, client, sandbox):
        big = PNG + b"\x00" * (13 * 1024 * 1024)
        r = client.post(
            "/api/festival/upload-image",
            files={"file": ("big.png", big, "image/png")},
            auth=AUTH,
        )
        assert r.status_code == 413
        assert not list(festival.FESTIVAL_IMG_DIR.iterdir())

    def test_just_under_the_ceiling_is_accepted(self, client, sandbox):
        near = PNG + b"\x00" * (11 * 1024 * 1024)
        r = client.post(
            "/api/festival/upload-image",
            files={"file": ("near.png", near, "image/png")},
            auth=AUTH,
        )
        assert r.status_code == 200, r.text

    def test_the_ceiling_matches_the_one_bazar_uses(self):
        """One number for a photo upload, not two that drift apart."""
        from backend.routes import bazar

        assert festival.MAX_IMAGE_BYTES == bazar.MAX_IMAGE_BYTES == 12 * 1024 * 1024


def _guarded(dependant) -> bool:
    """Is require_admin anywhere in this route's dependency tree?"""
    from backend.routes.admin import require_admin

    if dependant.call is require_admin:
        return True
    return any(_guarded(sub) for sub in dependant.dependencies)


def test_no_festival_write_route_is_left_unguarded(app):
    """The sweep. Add a POST to this router without a check and this fails."""
    from backend.routes.admin import require_admin  # noqa: F401 — imported by _guarded

    unguarded = [
        f"{sorted(m for m in route.methods if m != 'HEAD')} {route.path}"
        for route in app.routes
        if getattr(route, "path", "").startswith("/api/festival")
        and getattr(route, "methods", set()) & {"POST", "PUT", "PATCH", "DELETE"}
        and not _guarded(route.dependant)
    ]
    assert not unguarded, f"festival write routes with no admin check: {unguarded}"
