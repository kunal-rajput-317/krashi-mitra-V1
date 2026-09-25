"""हिसाब — the payment ledger (services/ledger.py, routes/admin_ledger.py).

What is pinned:
  * every feature's record_payment() writes exactly one ledger row, and a
    renewal adds a SECOND row instead of overwriting the first — the defect
    this ledger exists to fix;
  * a refund is a negative row, and a second refund click does not refund twice;
  * nothing is deleted: a void keeps the row, marks it, and drops it from totals;
  * the financial year splits on 1 April IST;
  * the backfill copies an existing payment once, however often it runs;
  * the manual form refuses feature sources (they would double-count);
  * the CSV carries every row, voided ones marked.
"""
import base64
import os
from datetime import datetime, timedelta

import pytest

from backend.database.db import Payment, Sponsor
from backend.services import ledger


@pytest.fixture()
def admin_headers():
    raw = f"{os.environ['ADMIN_USER']}:{os.environ['ADMIN_PASS']}".encode()
    return {"Authorization": "Basic " + base64.b64encode(raw).decode()}


def _for(db, source, key):
    return (db.query(Payment)
              .filter(Payment.source == source, Payment.source_key == key)
              .order_by(Payment.id).all())


def test_a_renewal_adds_a_row_instead_of_overwriting(db_session):
    from backend.services import krashi_dukan
    from backend.database.db import DukanShop
    shop = DukanShop(slug="ledger-test-shop", name="Ledger Test Shop", phone="9999999999")
    db_session.add(shop)
    db_session.commit()

    krashi_dukan.record_payment(db_session, "ledger-test-shop", 500, ref="UTR111")
    krashi_dukan.record_payment(db_session, "ledger-test-shop", 700, ref="UTR222")

    got = _for(db_session, "dukan", "ledger-test-shop")
    assert [(p.amount, p.ref) for p in got] == [(500, "UTR111"), (700, "UTR222")]
    assert got[0].payer == "Ledger Test Shop"


def test_sponsor_payment_needs_an_amount_and_lands_in_the_ledger(client, admin_headers, db_session, paid):
    db_session.add(Sponsor(slug="ledger-brand", name="Ledger Brand", category="seed",
                           url="https://example.com", active=False))
    db_session.commit()
    r = client.post("/admin/sponsor/ledger-brand/payment", json={}, headers=admin_headers)
    assert r.status_code == 400
    r = client.post("/admin/sponsor/ledger-brand/payment",
                    json=paid(150000, method="bank", ref="UTRBRAND0001"),
                    headers=admin_headers)
    assert r.status_code == 200, r.text
    db_session.expire_all()
    got = _for(db_session, "sponsor", "ledger-brand")
    assert [(p.amount, p.ref, p.method) for p in got] == [(150000, "UTRBRAND0001", "bank")]


def test_refund_is_a_negative_row_and_only_once(db_session):
    from backend.services import seller_verify
    from backend.database.db import SellerVerification
    row = SellerVerification(user_id=987654, ref="KMVLEDGR", full_name="Refund Farmer",
                             phone="9000000000", fee_amount=199,
                             paid_at=datetime.utcnow(), status="paid")
    db_session.add(row)
    db_session.commit()
    seller_verify.record_refund(db_session, "KMVLEDGR")
    seller_verify.record_refund(db_session, "KMVLEDGR")
    got = _for(db_session, "verify", "KMVLEDGR")
    assert [p.amount for p in got] == [-199]


def test_void_keeps_the_row_but_drops_it_from_totals(db_session):
    fy = ledger.current_fy()
    before = ledger.summary(db_session, fy)["total"]
    p = ledger.record(db_session, "adsense", 1234, payer="Google", origin="manual")
    db_session.commit()
    assert ledger.summary(db_session, fy)["total"] == before + 1234
    with pytest.raises(ValueError):
        ledger.void(db_session, p.id, "   ")
    ledger.void(db_session, p.id, "typed twice")
    assert db_session.query(Payment).filter(Payment.id == p.id).count() == 1
    assert ledger.summary(db_session, fy)["total"] == before
    assert "typed twice" in ledger.to_csv(db_session, fy)


def test_financial_year_splits_on_1_april_ist():
    # 31 Mar 2027 23:00 IST is still FY 2026-27; 1 Apr 2027 00:30 IST is 2027-28.
    assert ledger.fy_of(datetime(2027, 3, 31, 17, 30)) == "2026-27"
    assert ledger.fy_of(datetime(2027, 3, 31, 19, 0)) == "2027-28"
    a, b = ledger.fy_bounds("2026-27")
    assert ledger.fy_of(a) == "2026-27" and ledger.fy_of(b - timedelta(seconds=1)) == "2026-27"


def test_backfill_copies_an_old_payment_once(db_session):
    paid = datetime.utcnow() - timedelta(days=40)
    db_session.add(Sponsor(slug="old-brand", name="Old Brand", category="tractor",
                           url="https://example.com", active=False,
                           amount=90000, paid_at=paid))
    db_session.commit()
    ledger.backfill(db_session)
    ledger.backfill(db_session)
    got = _for(db_session, "sponsor", "old-brand")
    assert len(got) == 1 and got[0].amount == 90000 and got[0].origin == "backfill"


def test_manual_form_refuses_feature_sources(client, admin_headers, paid):
    r = client.post("/admin/ledger", json=paid(500, source="dukan"),
                    headers=admin_headers)
    assert r.status_code == 400
    r = client.post("/admin/ledger", json=paid(0, source="adsense"),
                    headers=admin_headers)
    assert r.status_code == 400
    day = (datetime.utcnow() + timedelta(hours=5, minutes=30) - timedelta(days=3)).date().isoformat()
    r = client.post("/admin/ledger", json=paid(2500, source="adsense", date=day,
                                               payer="Google", method="bank",
                                               ref="ADSENSE0920"),
                    headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["payment"]["date"] == day


def test_ledger_is_admin_only(client):
    assert client.get("/admin/ledger").status_code in (401, 403)
    assert client.get("/admin/ledger/export.csv").status_code in (401, 403)


def test_csv_opens_in_excel_with_hindi(client, admin_headers):
    r = client.get("/admin/ledger/export.csv", headers=admin_headers)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert r.text.startswith("﻿") and "Reference (UPI/UTR)" in r.text


def test_rupees_in_words_uses_indian_grouping():
    assert ledger.rupees_in_words(150000) == "One Lakh Fifty Thousand"
    assert ledger.rupees_in_words(199) == "One Hundred Ninety Nine"
    assert ledger.rupees_in_words(12345678) == (
        "One Crore Twenty Three Lakh Forty Five Thousand Six Hundred Seventy Eight")


def test_receipt_never_calls_itself_a_tax_invoice(client, admin_headers, db_session, monkeypatch):
    monkeypatch.delenv("KM_GSTIN", raising=False)
    p = ledger.record(db_session, "sponsor", 150000, payer="Receipt Brand", ref="UTR-R1",
                      origin="manual")
    db_session.commit()
    r = client.get(f"/admin/ledger/{p.id}/receipt", headers=admin_headers)
    assert r.status_code == 200
    assert "₹1,50,000" in r.text and "UTR-R1" in r.text
    assert "not a GST tax invoice" in r.text
    assert "Tax Invoice" not in r.text
    assert client.get(f"/admin/ledger/{p.id}/receipt").status_code in (401, 403)


# ── Nothing wrong gets in (services/ledger.py::clean_entry) ────────────────
# The ledger is what the ITR and GST return are filed from. A doubt is a
# refusal with the reason, never a guess, and a refusal touches nothing.

def _ist_day(days_ago=0):
    return (datetime.utcnow() + timedelta(hours=5, minutes=30)
            - timedelta(days=days_ago)).date().isoformat()


@pytest.mark.parametrize("bad", ["1,500", "499.5", 499.5, "₹500", "", None, True, 0, -5,
                                 ledger.MAX_ENTRY + 1])
def test_an_amount_is_exactly_what_was_typed_or_refused(db_session, paid, bad):
    with pytest.raises(ValueError):
        ledger.clean_entry(db_session, paid(bad))


def test_a_good_amount_is_kept_exactly(db_session, paid):
    assert ledger.clean_entry(db_session, paid("1500")).amount == 1500
    assert ledger.clean_entry(db_session, paid(1500.0)).amount == 1500


@pytest.mark.parametrize("day", ["", "26-09-2026", "2026-13-01"])
def test_the_date_it_landed_is_required_and_real(db_session, paid, day):
    with pytest.raises(ValueError):
        ledger.clean_entry(db_session, paid(500, date=day))


def test_no_future_date_and_no_absurdly_old_one(db_session, paid):
    with pytest.raises(ValueError):
        ledger.clean_entry(db_session, paid(500, date=_ist_day(-1)))
    with pytest.raises(ValueError):
        ledger.clean_entry(db_session, paid(500, date=_ist_day(ledger.MAX_AGE_DAYS + 1)))
    e = ledger.clean_entry(db_session, paid(500, date=_ist_day(0)))
    assert e.received_at <= datetime.utcnow()
    assert ledger.fy_of(e.received_at) == ledger.current_fy() or _ist_day(0).endswith("-04-01")
    assert (e.received_at + timedelta(hours=5, minutes=30)).date().isoformat() == _ist_day(0)


def test_the_method_is_chosen_never_defaulted(db_session, paid):
    with pytest.raises(ValueError):
        ledger.clean_entry(db_session, paid(500, method=""))
    with pytest.raises(ValueError):
        ledger.clean_entry(db_session, paid(500, method="cash"))
    # "other" (cash / cheque) must say what it was.
    with pytest.raises(ValueError):
        ledger.clean_entry(db_session, paid(500, method="other", note="", ref=""))


@pytest.mark.parametrize("ref", ["", "T2409261234567890", "12345678901", "1234567890123",
                                 "UTR77"])
def test_upi_needs_the_12_digit_utr(db_session, paid, ref):
    with pytest.raises(ValueError):
        ledger.clean_entry(db_session, paid(500, method="upi", ref=ref))


def test_references_are_stored_in_the_statements_shape(db_session, paid):
    e = ledger.clean_entry(db_session, paid(500, method="upi", ref=" 4123 4567 8901 "))
    assert e.ref == "412345678901"
    e = ledger.clean_entry(db_session, paid(500, method="bank", ref="sbin426912345678"))
    assert e.ref == "SBIN426912345678"
    with pytest.raises(ValueError):
        ledger.clean_entry(db_session, paid(500, method="bank", ref="UTR-12/34"))


def test_the_payer_is_required(db_session, paid):
    with pytest.raises(ValueError):
        ledger.clean_entry(db_session, paid(500, payer="  "))


def test_the_same_reference_twice_is_refused_and_touches_nothing(client, admin_headers,
                                                                  db_session, paid):
    from backend.database.db import DukanShop
    for slug in ("dup-shop-a", "dup-shop-b"):
        db_session.add(DukanShop(slug=slug, name=slug, phone="9999999999"))
    db_session.commit()
    body = paid(500, method="upi", ref="998877665544", payer="Dup Payer")
    r = client.post("/admin/dukan/shops/dup-shop-a/payment", json=body, headers=admin_headers)
    assert r.status_code == 200, r.text
    # A double click, or the same credit recorded on another panel.
    for path in ("/admin/dukan/shops/dup-shop-a/payment",
                 "/admin/dukan/shops/dup-shop-b/payment"):
        r = client.post(path, json=body, headers=admin_headers)
        assert r.status_code == 400 and "पहले से दर्ज" in r.json()["detail"]
    r = client.post("/admin/ledger", json=dict(body, source="other"), headers=admin_headers)
    assert r.status_code == 400
    db_session.expire_all()
    b = db_session.query(DukanShop).filter(DukanShop.slug == "dup-shop-b").one()
    assert b.paid_at is None and not b.active, "a refused payment still listed the shop"
    assert len(db_session.query(Payment).filter(Payment.ref == "998877665544").all()) == 1
    # Voiding the row frees the reference: the fix for a mistyped entry.
    pid = db_session.query(Payment).filter(Payment.ref == "998877665544").one().id
    ledger.void(db_session, pid, "wrong shop")
    r = client.post("/admin/dukan/shops/dup-shop-b/payment", json=body, headers=admin_headers)
    assert r.status_code == 200, r.text


def test_the_ledger_and_the_listing_carry_the_bank_date_and_details(client, admin_headers,
                                                                     db_session, paid):
    from backend.database.db import DukanShop
    db_session.add(DukanShop(slug="dated-shop", name="Dated Shop", phone="9999999999"))
    db_session.commit()
    day = _ist_day(5)
    r = client.post("/admin/dukan/shops/dated-shop/payment",
                    json=paid(600, date=day, method="bank", ref="N265261234567890",
                              payer="RAMESH KUMAR"),
                    headers=admin_headers)
    assert r.status_code == 200, r.text
    db_session.expire_all()
    p = _for(db_session, "dukan", "dated-shop")[-1]
    o = ledger.out(p)
    assert (o["date"], o["amount"], o["method"], o["ref"], o["payer"]) == (
        day, 600, "bank", "N265261234567890", "RAMESH KUMAR")
    shop = db_session.query(DukanShop).filter(DukanShop.slug == "dated-shop").one()
    assert shop.paid_at == p.received_at, "the listing and the ledger disagree on the date"


def test_the_tick_records_exactly_what_arrived(db_session):
    from backend.services import seller_verify
    from backend.database.db import SellerVerification
    db_session.add(SellerVerification(user_id=987001, ref="KMVEXACT", full_name="Exact",
                                      phone="9000000001", fee_amount=199, status="pending"))
    db_session.commit()
    with pytest.raises(ValueError):
        seller_verify.record_payment(db_session, "KMVEXACT", 0)
    db_session.rollback()
    seller_verify.record_payment(db_session, "KMVEXACT", 150)
    assert [p.amount for p in _for(db_session, "verify", "KMVEXACT")] == [150]


def test_a_refund_is_the_whole_fee_with_its_own_reference(client, admin_headers,
                                                          db_session, paid):
    from backend.database.db import SellerVerification
    db_session.add(SellerVerification(user_id=987002, ref="KMVRFUND", full_name="Refund Two",
                                      phone="9000000002", fee_amount=199,
                                      paid_at=datetime.utcnow(), status="rejected"))
    db_session.commit()
    url = "/admin/verifications/KMVRFUND/refund"
    assert client.post(url, json={}, headers=admin_headers).status_code == 400
    r = client.post(url, json=paid(99, method="upi", ref="555566667777"), headers=admin_headers)
    assert r.status_code == 400 and "199" in r.json()["detail"]
    r = client.post(url, json=paid(199, method="upi", ref="555566667777"), headers=admin_headers)
    assert r.status_code == 200, r.text
    db_session.expire_all()
    got = _for(db_session, "verify", "KMVRFUND")
    assert [(p.amount, p.ref, p.method) for p in got] == [(-199, "555566667777", "upi")]


def test_every_route_that_records_money_checks_the_entry_first(repo_root):
    """The structural guard. A new payment route that skips clean_entry() would
    put unchecked amounts, dates and references in the tax record."""
    import ast
    writers = {"record_payment", "record_refund", "record"}
    checks = {"entry_or_400", "clean_entry"}
    missing, seen = [], 0
    for path in sorted((repo_root / "backend" / "routes").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if fn.name == "entry_or_400":
                continue
            called = set()
            for node in ast.walk(fn):
                if not isinstance(node, ast.Call):
                    continue
                f = node.func
                if isinstance(f, ast.Attribute):
                    owner = getattr(f.value, "id", "")
                    if f.attr in writers and (f.attr != "record" or owner == "ledger"):
                        called.add(f.attr)
                elif isinstance(f, ast.Name) and f.id in checks:
                    called.add(f.id)
                # record_payment handed to a _write() wrapper as an argument
                for a in node.args:
                    if isinstance(a, ast.Attribute) and a.attr in ("record_payment", "record_refund"):
                        called.add(a.attr)
            if called & writers:
                seen += 1
                if not called & checks:
                    missing.append(f"{path.name}::{fn.name}")
    assert seen >= 7, f"the scan found only {seen} payment routes; it is not looking properly"
    assert not missing, f"records money without ledger.clean_entry(): {missing}"


# ── TDS and affiliate income ──────────────────────────────────────────────
# `amount` is what reached the bank; `tds` is what the payer deducted and paid
# to the government for us. Income is the two together, and that is what the
# ₹20 lakh GST bar, the CSV and the receipt report.

@pytest.mark.parametrize("bad", ["1,000", "10.5", "abc", -5, 1000, 5000])
def test_tds_is_whole_rupees_and_less_than_the_bank_credit(db_session, paid, bad):
    with pytest.raises(ValueError):
        ledger.clean_entry(db_session, paid(1000, tds=bad))


@pytest.mark.parametrize("blank", [None, "", "  ", "0", 0])
def test_no_tds_is_zero(db_session, paid, blank):
    assert ledger.clean_entry(db_session, paid(1000, tds=blank)).tds == 0


def test_income_counts_the_tds_and_the_bank_figure_stays_the_bank_figure(
        client, admin_headers, db_session, paid):
    fy = ledger.current_fy()
    before = ledger.summary(db_session, fy)
    r = client.post("/admin/ledger",
                    json=paid(90000, tds=10000, source="sponsor", method="bank",
                              ref="TDSSPONSOR01", payer="Big Tractor Co"),
                    headers=admin_headers)
    assert r.status_code == 200, r.text
    o = r.json()["payment"]
    assert (o["amount"], o["tds"], o["gross"]) == (90000, 10000, 100000)
    after = ledger.summary(db_session, fy)
    assert after["total"] - before["total"] == 100000, "the GST bar must count the TDS too"
    assert after["received"] - before["received"] == 90000
    assert after["tds"] - before["tds"] == 10000
    csv_text = ledger.to_csv(db_session, fy)
    assert "Gross income (INR),TDS (INR),Received in bank (INR)" in csv_text
    assert ",100000,10000,90000," in csv_text


def test_the_receipt_is_for_the_gross_and_shows_the_tds(client, admin_headers, db_session):
    p = ledger.record(db_session, "sponsor", 90000, tds=10000, payer="Receipt TDS Co",
                      ref="UTRRECEIPTTDS", origin="manual")
    db_session.commit()
    r = client.get(f"/admin/ledger/{p.id}/receipt", headers=admin_headers)
    assert "₹1,00,000" in r.text and "One Lakh Only" in r.text
    assert "₹10,000" in r.text and "₹90,000" in r.text


def test_a_refund_carries_no_tds(db_session, client, admin_headers, paid):
    with pytest.raises(ValueError):
        ledger.record(db_session, "verify", -199, tds=10)
    from backend.database.db import SellerVerification
    db_session.add(SellerVerification(user_id=987003, ref="KMVRFTDS", full_name="Refund Tds",
                                      phone="9000000003", fee_amount=199,
                                      paid_at=datetime.utcnow(), status="rejected"))
    db_session.commit()
    r = client.post("/admin/verifications/KMVRFTDS/refund",
                    json=paid(199, tds=10, method="upi", ref="444455556666"),
                    headers=admin_headers)
    assert r.status_code == 400 and "TDS" in r.json()["detail"]


def test_a_feature_payment_can_carry_tds(client, admin_headers, db_session, paid):
    from backend.database.db import DukanShop
    db_session.add(DukanShop(slug="tds-shop", name="TDS Shop", phone="9999999999"))
    db_session.commit()
    r = client.post("/admin/dukan/shops/tds-shop/payment",
                    json=paid(980, tds=20, method="bank", ref="TDSSHOP00980"),
                    headers=admin_headers)
    assert r.status_code == 200, r.text
    db_session.expire_all()
    p = _for(db_session, "dukan", "tds-shop")[-1]
    assert (p.amount, p.tds, ledger.gross(p)) == (980, 20, 1000)


def test_affiliate_income_is_its_own_source_and_counts(client, admin_headers, db_session, paid):
    assert "affiliate" in ledger.SOURCES
    fy = ledger.current_fy()
    before = ledger.summary(db_session, fy)["total"]
    r = client.post("/admin/ledger",
                    json=paid(1960, tds=40, source="affiliate", method="bank",
                              ref="AMZNPAYOUT0926", payer="Amazon Seller Services"),
                    headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["payment"]["source_label"] == ledger.SOURCES["affiliate"]
    s = ledger.summary(db_session, fy)
    assert s["total"] - before == 2000
    assert any(b["source"] == "affiliate" for b in s["by_source"])
