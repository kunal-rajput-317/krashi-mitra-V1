"""The ₹500 rail: UPI link building, the call log, and recording payment.

Three properties carry the weight here.

**A generated link is never evidence of payment.** A upi:// hand-off goes to the
dealer's own app and reports nothing back, so nothing in the collect path may
set `paid_at`. Only an explicit POST from a human who saw the credit does. A
regression here would have the panel — and the 31-Aug test — counting revenue
that never arrived.

**The deep link cannot be steered by its inputs.** The transaction note is built
from a firm name that arrived over a public, unauthenticated form. An unescaped
`&am=` in that name would rewrite the amount on the confirmation screen the
dealer is looking at, which is a payment-redirection bug, not a formatting one.

**No VPA is ever invented.** Unset config makes every surface say "not
configured"; a fallback would silently route a dealer's money to a stranger.
"""

import importlib

import pytest

from backend.services import dealers

ADMIN = ("testadmin", "test-admin-pass")


@pytest.fixture()
def upi(monkeypatch):
    """services/upi.py with a known VPA. Reloaded because DEFAULT_AMOUNT is read
    from the environment at import time."""
    monkeypatch.setenv("KM_UPI_ID", "kunal@okhdfcbank")
    monkeypatch.setenv("KM_UPI_NAME", "KrashiMitra")
    monkeypatch.setenv("KM_LISTING_FEE", "500")
    from backend.services import upi as upi_mod
    return importlib.reload(upi_mod)


@pytest.fixture()
def clean(db_session):
    from backend.database.db import Buyer
    from backend.services import buyers
    from backend.utils import security

    security._hits.clear()
    db_session.query(Buyer).delete()
    db_session.commit()
    buyers.invalidate()
    yield db_session
    db_session.query(Buyer).delete()
    db_session.commit()
    buyers.invalidate()


@pytest.fixture()
def dealer(clean):
    return dealers.create(clean, {
        "name": "Sharma Traders", "district": "Hardoi", "state": "Uttar Pradesh",
        "phone": "9876543210", "kind": "trader", "commodities": ["wheat"],
    })


class TestLinkCannotBeSteered:
    """The note carries a public-form firm name into a money URL."""

    def test_ampersand_in_name_cannot_append_parameters(self, upi):
        pack = upi.collect("Evil&am=1&pa=attacker@upi", "Hardoi")
        # The only am= and pa= in the URL are the ones we put there.
        assert pack["link"].count("am=") == 1
        assert pack["link"].count("pa=") == 1
        assert "attacker" not in pack["link"].split("pa=")[1].split("&")[0]
        assert f"pa={upi.vpa().replace('@', '%40')}" in pack["link"]

    def test_reported_note_matches_the_note_in_the_link(self, upi):
        """A caller rendering pack['note'] must see what the dealer's app will."""
        pack = upi.collect("A&B=C Traders", "Hardoi")
        assert "&" not in pack["note"] and "=" not in pack["note"]

    def test_devanagari_name_transliterates_into_the_note(self, upi):
        """Most firm names are in Hindi, and the note charset alone drops all
        of it. The name must appear in the note, transliterated — not replaced
        by the district or the slug, which was the interim fix."""
        pack = upi.collect("शर्मा ट्रेडर्स", "Hardoi", ref="shrma-tredrs-hardoi")
        assert "  " not in pack["note"], "stripped characters left a wall of spaces"
        assert "Sharma" in pack["note"], "the firm's actual name is missing from its own note"
        assert "Hardoi" in pack["note"]

    def test_devanagari_name_alone_still_transliterates(self, upi):
        """No district given — the name itself must not fall back to the slug."""
        pack = upi.collect("गुप्ता खाद बीज भंडार", "", ref="gupta-khad-beej-bhandar")
        assert "Gupta" in pack["note"]

    def test_note_prefers_a_latin_name_over_the_slug(self, upi):
        pack = upi.collect("Sharma Traders", "Hardoi", ref="sharma-traders-hardoi")
        assert "Sharma Traders Hardoi" in pack["note"]

    def test_amount_is_clamped(self, upi):
        assert upi.clean_amount("750") == 750
        for bad in ("999999", "-5", "0", "abc", "", None):
            assert upi.clean_amount(bad) == upi.DEFAULT_AMOUNT

    def test_amount_in_link_is_the_clamped_one(self, upi):
        assert "am=500" in upi.collect("X", "Y", amount="9999999")["link"]


class TestNoVpaIsEverInvented:
    def test_unconfigured_yields_no_link_and_no_qr(self, monkeypatch):
        monkeypatch.setenv("KM_UPI_ID", "")
        from backend.services import upi as upi_mod
        mod = importlib.reload(upi_mod)
        assert mod.configured() is False
        assert mod.link(500) == ""
        assert mod.collect("Sharma", "Hardoi")["link"] == ""

    @pytest.mark.parametrize("bad", ["noatsign", "a@", "@psp", "has space@bank", ""])
    def test_malformed_vpa_is_not_configured(self, monkeypatch, bad):
        monkeypatch.setenv("KM_UPI_ID", bad)
        from backend.services import upi as upi_mod
        assert importlib.reload(upi_mod).configured() is False

    def test_collect_endpoint_503s_rather_than_guessing(self, monkeypatch, dealer, client):
        monkeypatch.setenv("KM_UPI_ID", "")
        from backend.services import upi as upi_mod
        importlib.reload(upi_mod)
        r = client.get(f"/admin/buyers/{dealer.slug}/collect", auth=ADMIN)
        assert r.status_code == 503
        assert "KM_UPI_ID" in r.json()["detail"]


class TestGeneratingALinkIsNotPayment:
    """The property that keeps the revenue number honest."""

    def test_collect_does_not_mark_the_dealer_paid(self, upi, dealer, client, clean):
        r = client.get(f"/admin/buyers/{dealer.slug}/collect", auth=ADMIN)
        assert r.status_code == 200, r.text
        assert r.json()["link"].startswith("upi://pay?")

        clean.refresh(dealer)
        assert dealer.paid_at is None, "generating a QR marked the dealer as paid"
        assert dealers.funnel(clean)["paid"] == 0

    def test_only_the_payment_endpoint_sets_paid_at(self, upi, dealer, client, clean):
        client.get(f"/admin/buyers/{dealer.slug}/collect", auth=ADMIN)
        r = client.post(f"/admin/buyers/{dealer.slug}/payment",
                        json={"amount": 500, "ref": "123456789012"}, auth=ADMIN)
        assert r.status_code == 200, r.text

        clean.refresh(dealer)
        assert dealer.paid_at is not None
        assert dealer.paid_amount == 500
        assert dealer.payment_ref == "123456789012"
        assert dealer.active is True, "paying did not list him"
        assert dealer.status == "listed"

    def test_payment_requires_a_real_amount(self, upi, dealer, client):
        for bad in (0, -5, "abc"):
            r = client.post(f"/admin/buyers/{dealer.slug}/payment",
                            json={"amount": bad}, auth=ADMIN)
            assert r.status_code == 400, f"{bad!r} was accepted as a payment"

    def test_renewal_extends_rather_than_resets(self, upi, dealer, clean):
        dealers.record_payment(clean, dealer.slug, 500)
        first = dealer.paid_until
        dealers.record_payment(clean, dealer.slug, 500)
        clean.refresh(dealer)
        assert dealer.paid_until > first, "a renewal threw away the days already bought"


class TestCallLog:
    """Telling 'the market said no' apart from 'the calls never happened'."""

    def test_a_new_dealer_has_never_been_called(self, dealer, clean):
        assert dealer.called_at is None
        assert dealers.funnel(clean)["called"] == 0

    def test_logging_a_call_counts_it(self, dealer, client, clean):
        r = client.post(f"/admin/buyers/{dealer.slug}/call",
                        json={"result": "interested", "note": "wants wheat only"},
                        auth=ADMIN)
        assert r.status_code == 200, r.text
        clean.refresh(dealer)
        assert dealer.called_at is not None
        assert dealer.call_count == 1
        assert dealer.call_result == "interested"
        assert "wants wheat only" in dealer.note
        assert r.json()["funnel"]["called"] == 1

    def test_repeated_calls_accumulate_and_keep_earlier_notes(self, dealer, clean):
        dealers.log_call(clean, dealer.slug, "no_answer")
        dealers.log_call(clean, dealer.slug, "interested", "call back Monday")
        clean.refresh(dealer)
        assert dealer.call_count == 2
        assert "call back Monday" in dealer.note

    def test_a_no_answer_is_not_recorded_as_progress(self, dealer, clean):
        before = dealer.status
        dealers.log_call(clean, dealer.slug, "no_answer")
        clean.refresh(dealer)
        assert dealer.status == before, "an unanswered call moved him along the funnel"
        assert dealer.called_at is not None, "the attempt itself should still be logged"
        assert dealers.funnel(clean)["interested"] == 0

    def test_refusal_is_distinguishable_from_never_called(self, dealer, clean):
        dealers.log_call(clean, dealer.slug, "not_interested")
        clean.refresh(dealer)
        assert dealer.status == "rejected"
        f = dealers.funnel(clean)
        assert f["called"] == 1 and f["refused"] == 1

    def test_unknown_result_is_rejected(self, dealer, client, clean):
        r = client.post(f"/admin/buyers/{dealer.slug}/call",
                        json={"result": "vibes"}, auth=ADMIN)
        assert r.status_code == 400
        clean.refresh(dealer)
        assert dealer.called_at is None


class TestFunnel:
    def test_free_and_paid_listings_are_counted_apart(self, upi, dealer, clean):
        # An admin-added dealer is live but unpaid — that is the free listing
        # the plan trades for a reference.
        f = dealers.funnel(clean)
        assert f["free_live"] == 1 and f["paid"] == 0

        dealers.record_payment(clean, dealer.slug, 500)
        f = dealers.funnel(clean)
        assert f["free_live"] == 0 and f["paid"] == 1 and f["paid_live"] == 1
        assert f["revenue"] == 500

    def test_targets_match_the_deadline_checklist(self, clean):
        assert dealers.funnel(clean)["targets"] == {
            "added": 20, "called": 10, "free_live": 3, "paid": 1}


class TestPayPage:
    """The public page. It may never claim payment happened."""

    def test_renders_for_a_known_dealer(self, upi, dealer, client):
        r = client.get(f"/pay?d={dealer.slug}")
        assert r.status_code == 200
        assert "Sharma Traders" in r.text
        assert "upi://pay?" in r.text

    def test_is_noindex(self, upi, dealer, client):
        assert "noindex" in client.get(f"/pay?d={dealer.slug}").text

    def test_never_claims_payment_succeeded(self, upi, dealer, client):
        body = client.get(f"/pay?d={dealer.slug}").text
        for claim in ("पेमेंट हो गया", "भुगतान सफल", "payment successful", "paid successfully"):
            assert claim not in body

    def test_vpa_is_shown_directly(self, upi, dealer, client):
        """QR and the pay button are one path; the plain-text, copyable VPA is
        shown alongside them directly, not behind a reveal — user's explicit
        call 2026-08-03 after trying the hide-behind-a-tap version."""
        body = client.get(f"/pay?d={dealer.slug}").text
        assert upi.vpa() in body
        assert 'id="pay-vpa-text"' in body

    def test_unknown_dealer_still_renders_a_payable_page(self, upi, client):
        """A mistyped link must not 404 in front of someone ready to pay."""
        r = client.get("/pay?d=does-not-exist")
        assert r.status_code == 200
        assert "upi://pay?" in r.text

    def test_no_dealer_at_all_still_renders(self, upi, client):
        assert client.get("/pay").status_code == 200

    def test_says_so_when_upi_is_unconfigured(self, monkeypatch, dealer, client):
        monkeypatch.setenv("KM_UPI_ID", "")
        from backend.services import upi as upi_mod
        importlib.reload(upi_mod)
        r = client.get(f"/pay?d={dealer.slug}")
        assert r.status_code == 200
        assert "upi://pay?" not in r.text
        assert "चालू नहीं" in r.text

    def test_amount_in_the_query_is_clamped(self, upi, dealer, client):
        assert "am=500" in client.get(f"/pay?d={dealer.slug}&amount=9999999").text


class TestAuth:
    """Outreach data is commercial and the panel is Basic-auth'd; the new
    endpoints must not be the ones that leak it."""

    def test_collect_requires_admin(self, client):
        assert client.get("/admin/buyers/x/collect").status_code == 401

    @pytest.mark.parametrize("path", ["/admin/buyers/x/call", "/admin/buyers/x/payment"])
    def test_writes_require_admin(self, path, client):
        assert client.post(path, json={}).status_code == 401

    def test_receipt_requires_admin(self, client):
        assert client.get("/admin/buyers/x/receipt").status_code == 401


class TestEditableAmountAndPurpose:
    """The fee is not one fixed number and 'what is this for' is owner-worded
    copy — both editable per request, from the panel, without touching env."""

    def test_default_amount_and_purpose_when_none_given(self, upi, dealer, client):
        d = client.get(f"/admin/buyers/{dealer.slug}/collect", auth=ADMIN).json()
        assert d["amount"] == 500
        assert d["purpose"]
        assert d["purpose"] in d["whatsapp"]

    def test_custom_amount_and_purpose_are_reflected(self, upi, dealer, client):
        d = client.get(f"/admin/buyers/{dealer.slug}/collect", auth=ADMIN,
                       params={"amount": "750", "purpose": "featured slot, 60 din"}).json()
        assert d["amount"] == 750
        assert d["purpose"] == "featured slot, 60 din"
        assert "featured slot, 60 din" in d["whatsapp"]
        assert "₹750" in d["whatsapp"]

    def test_purpose_never_reaches_the_upi_deep_link(self, upi, dealer, client):
        """The purpose is WhatsApp-message copy, not the UPI transaction note
        — it has none of the note's length/charset constraints, and must not
        end up in the field a bank statement actually shows."""
        d = client.get(f"/admin/buyers/{dealer.slug}/collect", auth=ADMIN,
                       params={"purpose": "totally unrelated to the bank note"}).json()
        assert "totally unrelated" not in d["link"]

    def test_purpose_is_length_clipped(self, upi, dealer, client):
        d = client.get(f"/admin/buyers/{dealer.slug}/collect", auth=ADMIN,
                       params={"purpose": "x" * 500}).json()
        assert len(d["purpose"]) <= 200

    def test_collect_reports_prior_payment_state(self, upi, dealer, client, clean):
        before = client.get(f"/admin/buyers/{dealer.slug}/collect", auth=ADMIN).json()
        assert before["paid_at"] is None

        dealers.record_payment(clean, dealer.slug, 500, ref="abc123")
        after = client.get(f"/admin/buyers/{dealer.slug}/collect", auth=ADMIN).json()
        assert after["paid_at"] is not None
        assert after["paid_amount"] == 500
        assert after["payment_ref"] == "abc123"


class TestReceipt:
    """A receipt can only describe a payment record_payment() already wrote —
    never one this endpoint invents."""

    def test_404_for_unknown_dealer(self, upi, client):
        r = client.get("/admin/buyers/does-not-exist/receipt", auth=ADMIN)
        assert r.status_code == 404

    def test_400_when_never_paid(self, upi, dealer, client):
        r = client.get(f"/admin/buyers/{dealer.slug}/receipt", auth=ADMIN)
        assert r.status_code == 400

    def test_receipt_after_payment_has_the_real_numbers(self, upi, dealer, client, clean):
        dealers.record_payment(clean, dealer.slug, 500, ref="txn999", months=1)
        r = client.get(f"/admin/buyers/{dealer.slug}/receipt", auth=ADMIN)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["paid_amount"] == 500
        assert d["payment_ref"] == "txn999"
        assert "₹500" in d["receipt"]
        assert "txn999" in d["receipt"]
        assert dealer.name in d["receipt"] or "Sharma Traders" in d["receipt"]

    def test_receipt_is_not_a_tax_invoice(self, upi, dealer, client, clean):
        """No entity is registered yet — this must never claim to be GST-valid."""
        dealers.record_payment(clean, dealer.slug, 500)
        body = client.get(f"/admin/buyers/{dealer.slug}/receipt", auth=ADMIN).json()["receipt"]
        for claim in ("GSTIN", "Tax Invoice", "GST No"):
            assert claim not in body

    def test_receipt_reflects_renewal_not_first_payment(self, upi, dealer, client, clean):
        dealers.record_payment(clean, dealer.slug, 500)
        first_until = client.get(f"/admin/buyers/{dealer.slug}/receipt", auth=ADMIN).json()["paid_until"]
        dealers.record_payment(clean, dealer.slug, 500)
        second_until = client.get(f"/admin/buyers/{dealer.slug}/receipt", auth=ADMIN).json()["paid_until"]
        assert second_until > first_until
