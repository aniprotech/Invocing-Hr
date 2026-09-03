"""The two ways money moves, and what each one checks before believing it.

A customer pays a business, and a business tops up its wallet with us. Both
end in somebody's balance going up, so both have to be sure the money is
really there before it does.

Two things were not being checked. A bank debit collected into the platform
account was written into the settlement ledger as a Razorpay payment, so an
operator reconciling a payout would have looked in the wrong account for it.
And the PayPal top-up credited the amount on our own order rather than the
amount PayPal said it had taken - the only money path here that was not
comparing the two.
"""
import pytest

import main
import models


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


# --- money collected for a business ------------------------------------------------
def make_invoice(tenant, price=100.0):
    res = tenant.post("/api/invoices", json={
        "contact": "Customer Ltd", "email": "customer@example.com",
        "issue_date": "2026-01-01", "due_date": "2026-01-31",
        "status": "Awaiting Payment", "tax_type": "exclusive",
        "line_items": [{"description": "Work", "qty": 1, "price": price,
                        "tax_rate": "No Tax"}]})
    assert res.status_code == 200, res.text
    return res.json()


def invoice_row(tenant, number):
    me = tenant.get("/api/client/me").json()
    with main.SessionLocal() as db:
        return db.query(models.DBInvoice).filter(
            models.DBInvoice.number == number,
            models.DBInvoice.client_id == me["id"]).first()


def test_a_settlement_says_which_gateway_is_holding_the_money(tenant):
    """It is how the operator finds it again. Everything was written down as
    Razorpay, including bank debits that are nowhere near Razorpay."""
    inv = make_invoice(tenant)
    row = invoice_row(tenant, inv["number"])

    with main.SessionLocal() as db:
        live = db.query(models.DBInvoice).filter(
            models.DBInvoice.id == row.id).first()
        main.record_settlement(db, live, 10000, "GBP", "PM123",
                               gateway="gocardless")
        db.commit()
        got = db.query(models.DBSettlement).order_by(
            models.DBSettlement.id.desc()).first()
        assert got.gateway == "gocardless", got.gateway


def test_it_still_defaults_to_razorpay_for_the_flow_that_had_no_argument(tenant):
    inv = make_invoice(tenant)
    row = invoice_row(tenant, inv["number"])
    with main.SessionLocal() as db:
        live = db.query(models.DBInvoice).filter(
            models.DBInvoice.id == row.id).first()
        main.record_settlement(db, live, 10000, "INR", "pay_1")
        db.commit()
        got = db.query(models.DBSettlement).order_by(
            models.DBSettlement.id.desc()).first()
        assert got.gateway == "razorpay"


def test_a_settlement_is_owed_until_somebody_pays_it_out(tenant):
    """Money in the platform account is the tenant's, not the operator's."""
    inv = make_invoice(tenant)
    row = invoice_row(tenant, inv["number"])
    with main.SessionLocal() as db:
        live = db.query(models.DBInvoice).filter(
            models.DBInvoice.id == row.id).first()
        main.record_settlement(db, live, 10000, "GBP", "PM1", gateway="gocardless")
        db.commit()
        got = db.query(models.DBSettlement).order_by(
            models.DBSettlement.id.desc()).first()
        assert got.status == "owed"
        assert got.client_id == live.client_id


# --- money topped up into a wallet ----------------------------------------------------
class FakePayPal:
    """Stands in for PayPal's capture call."""
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self.payload


def capture_payload(value, currency="GBP", status="COMPLETED"):
    return {
        "status": status,
        "purchase_units": [{"payments": {"captures": [{
            "id": "CAP123",
            "amount": {"value": f"{value:.2f}", "currency_code": currency},
        }]}}],
    }


@pytest.fixture
def paypal_order(tenant):
    """A top-up waiting to be captured, for 50.00."""
    me = tenant.get("/api/client/me").json()
    with main.SessionLocal() as db:
        order = models.DBTopUpOrder(
            client_id=me["id"], provider="paypal", amount_minor=5000,
            currency="GBP", provider_order_id="PPORDER1", status="pending")
        db.add(order)
        db.commit()
        db.refresh(order)
        return order.id


def capture(tenant, order_id, payload, monkeypatch, status_code=200):
    monkeypatch.setattr(main, "_paypal_token", lambda: "token")
    monkeypatch.setattr(main.httpx, "post",
                        lambda *a, **kw: FakePayPal(payload, status_code))
    return tenant.post(f"/api/wallet/topup/{order_id}/capture-paypal")


def balance(tenant):
    return tenant.get("/api/wallet").json()["balance_minor"]


def test_a_full_payment_tops_the_wallet_up(tenant, paypal_order, monkeypatch):
    before = balance(tenant)
    res = capture(tenant, paypal_order, capture_payload(50.00), monkeypatch)
    assert res.status_code == 200, res.text
    assert balance(tenant) == before + 5000


def test_paying_less_than_the_top_up_is_refused(tenant, paypal_order, monkeypatch):
    """It credited the figure on our own order however much actually arrived."""
    before = balance(tenant)
    res = capture(tenant, paypal_order, capture_payload(1.00), monkeypatch)
    assert res.status_code == 400, res.text
    assert "less than" in res.json()["detail"]
    assert balance(tenant) == before, "it credited a payment that was short"


def test_paying_in_another_currency_is_refused(tenant, paypal_order, monkeypatch):
    """Fifty of something else is not fifty pounds."""
    before = balance(tenant)
    res = capture(tenant, paypal_order,
                  capture_payload(50.00, currency="USD"), monkeypatch)
    assert res.status_code == 400, res.text
    assert balance(tenant) == before


def test_a_capture_with_no_readable_amount_is_refused(tenant, paypal_order,
                                                      monkeypatch):
    """Better to fail and be chased than to guess at somebody's money."""
    before = balance(tenant)
    res = capture(tenant, paypal_order,
                  {"status": "COMPLETED", "purchase_units": []}, monkeypatch)
    assert res.status_code == 502, res.text
    assert balance(tenant) == before


def test_an_incomplete_payment_credits_nothing(tenant, paypal_order, monkeypatch):
    before = balance(tenant)
    res = capture(tenant, paypal_order,
                  capture_payload(50.00, status="PENDING"), monkeypatch)
    assert res.status_code == 200
    assert res.json()["credited"] is False
    assert balance(tenant) == before


def test_paying_more_than_asked_is_allowed(tenant, paypal_order, monkeypatch):
    """Overpaying is the payer's business; refusing it would strand money
    that has already left their account."""
    before = balance(tenant)
    res = capture(tenant, paypal_order, capture_payload(60.00), monkeypatch)
    assert res.status_code == 200, res.text
    # Credited at what the order was for, which is what the wallet promised.
    assert balance(tenant) == before + 5000


def test_capturing_twice_credits_once(tenant, paypal_order, monkeypatch):
    """Refreshing the return page is how this happens."""
    capture(tenant, paypal_order, capture_payload(50.00), monkeypatch)
    once = balance(tenant)
    capture(tenant, paypal_order, capture_payload(50.00), monkeypatch)
    assert balance(tenant) == once


def test_one_business_cannot_capture_another_s_top_up(tenant, paypal_order,
                                                      client, monkeypatch):
    import uuid
    email = f"other-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/client/register", json={
        "email": email, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    client.post("/api/client/login", json={"email": email, "password": "Passw0rdTest"})

    monkeypatch.setattr(main, "_paypal_token", lambda: "token")
    monkeypatch.setattr(main.httpx, "post",
                        lambda *a, **kw: FakePayPal(capture_payload(50.00)))
    res = client.post(f"/api/wallet/topup/{paypal_order}/capture-paypal")
    assert res.status_code == 404, res.text
