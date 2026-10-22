"""Two gaps in "View and pay online", closed.

The payment page refuses a draft invoice and one behind an expired payment
link, so a QR code on either would open nothing. And the Payment options
page listed each method without the marks it puts on the invoice.
"""
import pytest

import main
import models
from test_pay_online import invoice, methods


@pytest.fixture(autouse=True)
def _reset():
    main.rate_limiter._hits.clear()
    yield


def pay_online(tenant, inv):
    return tenant.get(f"/api/invoices/{inv['number']}").json()["pay_online"]


def test_a_draft_carries_no_code_that_would_open_nothing(tenant, monkeypatch):
    methods(monkeypatch, "stripe")
    assert pay_online(tenant, invoice(tenant, status="Draft")) is None
    assert pay_online(tenant, invoice(tenant)) is not None


def test_nor_does_an_invoice_behind_an_expired_payment_link(tenant, monkeypatch):
    methods(monkeypatch, "stripe")
    inv = invoice(tenant)
    with main.SessionLocal() as db:
        row = db.query(models.DBInvoice).filter(models.DBInvoice.id == inv["id"]).first()
        row.payment_link, row.payment_link_expires = "active", "2020-01-01"
        db.commit()
    assert pay_online(tenant, inv) is None
    with main.SessionLocal() as db:
        db.query(models.DBInvoice).filter(models.DBInvoice.id == inv["id"]).first().payment_link_expires = "2999-01-01"
        db.commit()
    assert pay_online(tenant, inv) is not None


def test_each_payment_method_lists_the_marks_it_puts_on_the_invoice(tenant):
    d = tenant.get("/api/payment-gateways").json()
    by = {g["provider"]: g for g in d["gateways"]}
    assert by["stripe"]["badges"] == ["visa", "mastercard", "amex", "applepay", "googlepay"]
    assert by["paypal"]["badges"] == ["paypal"] and by["razorpay"]["badges"] == ["visa", "mastercard", "upi"]
    assert "VISA" in by["stripe"]["badges_html"] and "<script" not in by["stripe"]["badges_html"]
    assert d["platform_methods"][0]["badges"] == ["bank"]
