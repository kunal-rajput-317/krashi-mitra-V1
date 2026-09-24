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


def test_sponsor_payment_needs_an_amount_and_lands_in_the_ledger(client, admin_headers, db_session):
    db_session.add(Sponsor(slug="ledger-brand", name="Ledger Brand", category="seed",
                           url="https://example.com", active=False))
    db_session.commit()
    r = client.post("/admin/sponsor/ledger-brand/payment", json={}, headers=admin_headers)
    assert r.status_code == 400
    r = client.post("/admin/sponsor/ledger-brand/payment",
                    json={"amount": 150000, "ref": "UTR-BRAND"}, headers=admin_headers)
    assert r.status_code == 200
    db_session.expire_all()
    got = _for(db_session, "sponsor", "ledger-brand")
    assert [(p.amount, p.ref) for p in got] == [(150000, "UTR-BRAND")]


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


def test_manual_form_refuses_feature_sources(client, admin_headers):
    r = client.post("/admin/ledger", json={"source": "dukan", "amount": 500},
                    headers=admin_headers)
    assert r.status_code == 400
    r = client.post("/admin/ledger", json={"source": "adsense", "amount": 0},
                    headers=admin_headers)
    assert r.status_code == 400
    r = client.post("/admin/ledger", json={"source": "adsense", "amount": 2500,
                                           "date": "2026-09-20", "payer": "Google"},
                    headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["payment"]["date"] == "2026-09-20"


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
