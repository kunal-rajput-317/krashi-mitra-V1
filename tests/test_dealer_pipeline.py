"""The dealer pipeline: public signup → admin queue → live on the district page.

Two properties carry the weight here.

**The trust rule is structural.** data/buyers.json states it in prose — a blue
tick is a claim we make to a farmer about a stranger's phone number, so it costs
one real phone call. Prose does not enforce anything. `from_signup()` has no
code path to `active` or `verified`, and these tests fail if one is ever added.

**Durability is the reason the table exists at all.** Render's free plan has no
persistent disk, so a dealer written back into data/buyers.json would survive
until the next restart and then silently revert. The admin panel therefore must
never write to the seed file — asserted directly, because that regression looks
like success right up until the dyno sleeps.
"""

import json

import pytest

from backend.services import buyers, dealers

ADMIN = ("testadmin", "test-admin-pass")     # set in conftest before backend import


@pytest.fixture()
def clean(db_session, monkeypatch):
    """Empty buyers table, caches dropped on both sides, rate limiter reset.

    The limiter is process-global and keyed by IP; every test here shares
    TestClient's, so without the reset the fourth signup in the file 429s and
    the failure looks like a validation bug.
    """
    from backend.database.db import Buyer
    from backend.utils import security

    security._hits.clear()
    db_session.query(Buyer).delete()
    db_session.commit()
    buyers.invalidate()
    monkeypatch.setattr(buyers, "_cache", None)
    monkeypatch.setattr(buyers, "_mtime", -1.0)
    monkeypatch.setattr(buyers, "_place_idx", {})
    yield db_session
    db_session.query(Buyer).delete()
    db_session.commit()
    buyers.invalidate()


def _signup(client, **over):
    body = {"name": "Sharma Traders", "kind": "trader", "state": "Uttar Pradesh",
            "district": "Hardoi", "market": "Hardoi Mandi",
            "commodities": ["wheat"], "phone": "9876543210"}
    body.update(over)
    return client.post("/dukan/signup", json=body)


class TestPublicSignupCannotListItself:
    """The trust rule, enforced in the schema rather than remembered."""

    def test_signup_is_accepted(self, clean, client):
        response = _signup(client)
        assert response.status_code == 200, response.text
        assert response.json()["success"] is True

    def test_signup_lands_inactive_and_unverified(self, clean, client):
        _signup(client)
        row = clean.query(dealers.Buyer).filter(dealers.Buyer.name == "Sharma Traders").one()
        assert row.active is False, "a self-signup went live without a phone call"
        assert row.verified is False, "a self-signup awarded itself the blue tick"
        assert row.source == "signup"
        assert row.status == "new"

    def test_signup_cannot_set_the_flags_directly(self, clean, client):
        """The payload is attacker-controlled; the flags must be ignored."""
        _signup(client, active=True, verified=True, featured=True, status="listed")
        row = clean.query(dealers.Buyer).filter(dealers.Buyer.name == "Sharma Traders").one()
        assert (row.active, row.verified, row.featured) == (False, False, False)
        assert row.status == "new"

    def test_pending_signup_is_invisible_to_farmers(self, clean, client):
        """The read side must not surface it — no district, no sitemap, nothing."""
        _signup(client)
        buyers.invalidate()
        assert buyers.for_place("wheat", "Uttar Pradesh", "Hardoi") == []
        assert buyers.live_places() == set()


class TestApprovalPutsItLive:
    """The other direction: after the call, it has to actually appear."""

    def _pending_slug(self, clean, client):
        _signup(client)
        return clean.query(dealers.Buyer).filter(
            dealers.Buyer.name == "Sharma Traders").one().slug

    def test_approve_makes_it_visible(self, clean, client):
        slug = self._pending_slug(clean, client)
        dealers.approve(clean, slug)
        rows = buyers.for_place("wheat", "Uttar Pradesh", "Hardoi")
        assert [b["name"] for b in rows] == ["Sharma Traders"]
        assert rows[0]["verified"] is True

    def test_approved_dealer_opens_the_district_gate(self, clean, client):
        """Same gate the sitemap and the noindex flag both read."""
        from backend.routes import bhav

        slug = self._pending_slug(clean, client)
        assert bhav._has_kharidar("wheat", "Uttar Pradesh", "Hardoi") is False
        dealers.approve(clean, slug)
        assert bhav._has_kharidar("wheat", "Uttar Pradesh", "Hardoi") is True

    def test_edit_takes_effect_without_waiting_out_the_cache(self, clean, client):
        """The panel exists to be used while standing in front of the dealer."""
        slug = self._pending_slug(clean, client)
        dealers.approve(clean, slug)
        dealers.update(clean, slug, {"name": "Sharma Brothers"})
        assert buyers.for_place("wheat", "Uttar Pradesh", "Hardoi")[0]["name"] \
            == "Sharma Brothers"

    def test_delete_removes_it_from_the_directory(self, clean, client):
        slug = self._pending_slug(clean, client)
        dealers.approve(clean, slug)
        assert dealers.delete(clean, slug) is True
        assert buyers.for_place("wheat", "Uttar Pradesh", "Hardoi") == []


class TestAdminSurface:
    def test_listing_requires_auth(self, clean, client):
        assert client.get("/admin/buyers").status_code == 401

    def test_write_requires_auth(self, clean, client):
        response = client.post("/admin/buyers", json={"name": "X", "district": "Y",
                                                      "phone": "9876543210"})
        assert response.status_code == 401

    def test_admin_sees_the_pending_queue_farmers_cannot(self, clean, client):
        _signup(client)
        body = client.get("/admin/buyers", auth=ADMIN).json()
        assert [b["name"] for b in body["buyers"]] == ["Sharma Traders"]
        assert body["counts"]["pending"] == 1
        assert body["counts"]["live"] == 0

    def test_admin_created_dealer_is_live_immediately(self, clean, client):
        """The owner adds it *because* he just spoke to the dealer."""
        response = client.post("/admin/buyers", auth=ADMIN, json={
            "name": "Verma Aadhat", "district": "Hardoi", "state": "Uttar Pradesh",
            "phone": "9998887770", "commodities": ["wheat"]})
        assert response.status_code == 200, response.text
        assert [b["name"] for b in buyers.for_place("wheat", "Uttar Pradesh", "Hardoi")] \
            == ["Verma Aadhat"]

    def test_approve_over_http(self, clean, client):
        _signup(client)
        slug = client.get("/admin/buyers", auth=ADMIN).json()["buyers"][0]["slug"]
        response = client.patch(f"/admin/buyers/{slug}", auth=ADMIN,
                                json={"active": True, "verified": True})
        assert response.status_code == 200, response.text
        assert response.json()["counts"]["live"] == 1

    def test_unknown_slug_is_404(self, clean, client):
        assert client.patch("/admin/buyers/nope", auth=ADMIN,
                            json={"active": True}).status_code == 404
        assert client.delete("/admin/buyers/nope", auth=ADMIN).status_code == 404


class TestSeedFileIsNeverWritten:
    """Why the table exists. A write here reverts on the next dyno restart."""

    def test_admin_create_does_not_touch_buyers_json(self, clean, client, repo_root):
        path = repo_root / "backend" / "data" / "buyers.json"
        before = path.read_bytes()
        client.post("/admin/buyers", auth=ADMIN, json={
            "name": "Disk Test", "district": "Hardoi", "phone": "9876500000"})
        assert path.read_bytes() == before, (
            "admin wrote to the JSON seed — on Render's free plan (no persistent "
            "disk) that dealer is lost on the next restart")

    def test_seed_file_still_parses_and_keeps_its_documentation(self, repo_root):
        """The seed is committed and hand-read; the note is load-bearing."""
        data = json.loads((repo_root / "backend" / "data" / "buyers.json")
                          .read_text(encoding="utf-8"))
        assert "_note" in data
        assert isinstance(data.get("buyers"), list)


class TestSeedAndTableMerge:
    def test_db_row_overrides_a_seed_row_with_the_same_slug(self, clean, tmp_path,
                                                            monkeypatch):
        """So a committed listing can be corrected from the panel, no deploy."""
        seed = tmp_path / "buyers.json"
        seed.write_text(json.dumps({"buyers": [{
            "id": "seeded-one", "active": True, "name": "Old Name",
            "state": "Uttar Pradesh", "district": "Hardoi",
            "commodities": [], "phone": "9000000000"}]}), encoding="utf-8")
        monkeypatch.setattr(buyers, "_PATH", seed)
        monkeypatch.setattr(buyers, "_cache", None)
        monkeypatch.setattr(buyers, "_mtime", -1.0)

        assert buyers.for_place("wheat", "Uttar Pradesh", "Hardoi")[0]["name"] == "Old Name"

        row = dealers.create(clean, {"name": "Corrected Name", "district": "Hardoi",
                                     "state": "Uttar Pradesh", "phone": "9000000000"})
        row.slug = "seeded-one"
        clean.commit()
        buyers.invalidate()
        monkeypatch.setattr(buyers, "_cache", None)   # force the merge to rerun

        names = [b["name"] for b in buyers.for_place("wheat", "Uttar Pradesh", "Hardoi")]
        assert names == ["Corrected Name"], f"seed override failed: {names}"

    def test_directory_survives_a_dead_database(self, clean, tmp_path, monkeypatch):
        """A kharidar page must render off the seed while Neon is asleep."""
        seed = tmp_path / "buyers.json"
        seed.write_text(json.dumps({"buyers": [{
            "id": "seeded-one", "active": True, "name": "Seed Trader",
            "state": "Uttar Pradesh", "district": "Hardoi",
            "commodities": [], "phone": "9000000000"}]}), encoding="utf-8")
        monkeypatch.setattr(buyers, "_PATH", seed)
        monkeypatch.setattr(buyers, "_cache", None)
        monkeypatch.setattr(buyers, "_mtime", -1.0)

        def _dead(*a, **k):
            raise RuntimeError("could not connect to server")

        monkeypatch.setattr("backend.database.db.SessionLocal", _dead)
        buyers.invalidate()

        assert [b["name"] for b in buyers.for_place("wheat", "Uttar Pradesh", "Hardoi")] \
            == ["Seed Trader"]


class TestSlugs:
    """The slug is permanent: LeadClick quotes it, so a rename must not orphan
    the click history. That makes it worth being readable at creation time."""

    def test_hindi_names_do_not_all_collapse_to_one_slug(self, clean):
        """The regression this exists to prevent — an ASCII-only slugify drops
        every Devanagari character, so every Hindi firm becomes dealer-<dist>-N."""
        a = dealers.create(clean, {"name": "शर्मा ट्रेडर्स", "district": "Hardoi",
                                   "phone": "9876543210"})
        b = dealers.create(clean, {"name": "गुप्ता आढ़तिया", "district": "Hardoi",
                                   "phone": "9876543211"})
        assert a.slug != b.slug
        assert not a.slug.startswith("dealer-"), a.slug
        assert "shrma" in a.slug and "hardoi" in a.slug, a.slug

    def test_collisions_still_get_a_counter(self, clean):
        first = dealers.create(clean, {"name": "Sharma Traders", "district": "Hardoi",
                                       "phone": "9876543210"})
        second = dealers.create(clean, {"name": "Sharma Traders", "district": "Hardoi",
                                        "phone": "9876543211"})
        assert first.slug == "sharma-traders-hardoi"
        assert second.slug == "sharma-traders-hardoi-2"

    def test_slug_is_url_safe(self, clean):
        row = dealers.create(clean, {"name": "मेसर्स राज कुमार & Sons (Pvt.)",
                                     "district": "Sri Ganganagar", "phone": "9876543210"})
        assert all(ch.isalnum() or ch == "-" for ch in row.slug)
        assert "--" not in row.slug
        assert not row.slug.startswith("-") and not row.slug.endswith("-")

    def test_rename_keeps_the_slug(self, clean):
        """Otherwise the dealer's lead_clicks history detaches on a typo fix."""
        row = dealers.create(clean, {"name": "Old Firm", "district": "Hardoi",
                                     "phone": "9876543210"})
        before = row.slug
        dealers.update(clean, before, {"name": "New Firm"})
        assert clean.query(dealers.Buyer).filter_by(slug=before).one().name == "New Firm"


class TestPhoneNormalisation:
    @pytest.mark.parametrize("raw, expected", [
        ("9876543210", "9876543210"),
        ("+91 98765 43210", "9876543210"),
        ("098765-43210", "9876543210"),
        ("91 9876543210", "9876543210"),
        ("12345", ""),              # too short
        ("1234567890", ""),         # Indian mobiles do not start with 1
        ("", ""),
    ])
    def test_clean_phone(self, raw, expected):
        assert dealers.clean_phone(raw) == expected

    def test_signup_without_a_reachable_number_is_rejected(self, clean, client):
        """The whole value of a queued row is being able to ring it back."""
        response = _signup(client, phone="12345", whatsapp="")
        assert response.status_code == 400

    def test_signup_without_a_name_is_rejected(self, clean, client):
        assert _signup(client, name="").status_code == 400
