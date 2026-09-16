"""Refunds: giving some or all of a receipt back.

Through the gateway that took the payment when there was one - Stripe by
payment intent, Razorpay by payment id, PayPal by capture - or recorded
when the business paid it back by hand. Never more than what is left of
the receipt. The invoice's paid and due move back, the status follows,
the customer is told, the audit log and a webhook hear, and the receipt
stays on record rather than being reversed away.
"""
import os

os.environ["WEBHOOKS_ASYNC"] = "0"

import pytest

import main
import models
from conftest import make_invoice


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


@pytest.fixture(autouse=True)
def _direct_collection():
    with main.SessionLocal() as db:
        row = db.query(models.DBSettings).filter(
            models.DBSettings.key == main.COLLECTION_SETTING, models.DBSettings.client_id == None).first()  # noqa: E711
        was = row.value if row else None
        if row:
            row.value = "direct"
            db.commit()
    yield
    if was is not None:
        with main.SessionLocal() as db:
            row = db.query(models.DBSettings).filter(
                models.DBSettings.key == main.COLLECTION_SETTING, models.DBSettings.client_id == None).first()  # noqa: E711
            if row:
                row.value = was
                db.commit()


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(main, "send_email_background",
                        lambda to, subject, body, from_email, html_body=None, **kw: (sent.append({"to": to, "subject": subject, "body": body, "from": from_email}), (True, ""))[1])
    return sent


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload, self.status_code, self.text = payload, status_code, str(payload)
        self.headers = {"content-type": "application/json"}

    def json(self):
        return self._payload


def receipt(tenant, number, amount, **kw):
    res = tenant.post(f"/api/invoices/{number}/payments", json=dict({"amount": amount, "paid_on": "2026-09-10", "method": "bank_transfer"}, **kw))
    assert res.status_code == 200, res.text
    return res.json()["payment_id"]


def online_receipt(number, client_email, method, reference, amount):
    """A receipt the way a gateway leaves one, without the gateway."""
    with main.SessionLocal() as db:
        cid = db.query(models.DBClient).filter(models.DBClient.email == client_email).first().id
        inv = db.query(models.DBInvoice).filter(models.DBInvoice.number == number, models.DBInvoice.client_id == cid).first()
        main.record_invoice_payment(db, inv, amount, method, reference, note="Paid online by the customer")
        db.commit()
        return db.query(models.DBPayment).filter(models.DBPayment.invoice_id == inv.id).order_by(models.DBPayment.id.desc()).first().id


def refund(tenant, number, pid, **body):
    return tenant.post(f"/api/invoices/{number}/payments/{pid}/refund", json=body)


def invoice(tenant, number):
    return tenant.get(f"/api/invoices/{number}").json()


def test_a_recorded_refund_moves_the_invoice_back_and_stays_on_the_receipt(tenant, account, outbox):
    tenant.post("/api/accounts", json={"name": "Bank", "kind": "bank"})
    inv = make_invoice(tenant, status="Awaiting Payment", line_items=[{"description": "x", "qty": 1, "price": 100.0, "tax_rate": "0%"}])
    pid = receipt(tenant, inv["number"], 100)
    assert invoice(tenant, inv["number"])["status"] == "Paid"
    res = refund(tenant, inv["number"], pid, amount=30, reason="Overcharged for delivery")
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["refund"]["method"] == "recorded" and out["refund"]["amount"] == 30.0 and out["refund"]["account_name"] == "Bank"
    assert out["status"] == "Partially Paid" and out["paid"] == 70.0 and out["due"] == 30.0
    got = invoice(tenant, inv["number"])
    assert got["payments"][0]["amount"] == 100.0 and got["payments"][0]["refunded"] == 30.0, "the receipt keeps its amount"
    assert got["refunded_total"] == 30.0 and got["refunds"][0]["reason"] == "Overcharged for delivery"
    assert out["customer_told"] is True and len(outbox) == 1
    assert "Refund of GBP 30.00 on invoice" in outbox[0]["subject"] and "Overcharged" in outbox[0]["body"] and "Acme Ltd <" in outbox[0]["from"]
    # The rest of it.
    assert refund(tenant, inv["number"], pid, tell_customer=False).status_code == 200
    got = invoice(tenant, inv["number"])
    assert got["status"] == "Awaiting Payment" and got["paid"] == 0 and got["due"] == 100.0 and got["payments"][0]["refunded"] == 100.0
    assert len(outbox) == 1, "not told when asked not to"
    logs = tenant.get("/api/audit-logs").json()
    assert sum(1 for l in logs if l["action"] == "invoice_refunded") == 2
    hit = next(l for l in logs if l["action"] == "invoice_refunded" and "30.00" in l["details"])
    assert "recorded" in hit["details"] and "Overcharged" in hit["details"]


def test_never_more_than_what_is_left_of_the_receipt(tenant):
    inv = make_invoice(tenant, status="Awaiting Payment", line_items=[{"description": "x", "qty": 1, "price": 100.0, "tax_rate": "0%"}])
    pid = receipt(tenant, inv["number"], 60)
    assert refund(tenant, inv["number"], pid, amount=0).status_code == 400
    assert refund(tenant, inv["number"], pid, amount="lots").status_code == 400
    assert refund(tenant, inv["number"], pid, amount=60.01).status_code == 400
    assert refund(tenant, inv["number"], pid, amount=50).status_code == 200
    res = refund(tenant, inv["number"], pid, amount=10.01)
    assert res.status_code == 400 and "10.00" in res.json()["detail"]
    assert refund(tenant, inv["number"], pid, amount=10).status_code == 200
    assert refund(tenant, inv["number"], pid, amount=0.01).status_code == 400
    assert refund(tenant, inv["number"], 999999).status_code == 404


def test_a_refunded_receipt_cannot_be_reversed_away(tenant):
    inv = make_invoice(tenant, status="Awaiting Payment")
    pid = receipt(tenant, inv["number"], 20)
    refund(tenant, inv["number"], pid, amount=5)
    res = tenant.delete(f"/api/invoices/{inv['number']}/payments/{pid}")
    assert res.status_code == 400 and "refunded" in res.json()["detail"]
    assert len(invoice(tenant, inv["number"])["payments"]) == 1


def test_a_stripe_receipt_is_refunded_through_stripe(tenant, account, monkeypatch, outbox):
    tenant.put("/api/payment-gateways/stripe", json={"public_key": "pk_test_x", "secret_key": "sk_test_x", "is_active": True})
    inv = make_invoice(tenant, status="Awaiting Payment", line_items=[{"description": "x", "qty": 1, "price": 80.0, "tax_rate": "0%"}])
    pid = online_receipt(inv["number"], account["email"], "stripe", "pi_abc", 80.0)
    posted = []

    def fake_post(url, **kw):
        posted.append((url, kw.get("auth"), kw.get("data")))
        return FakeResponse({"id": "re_1", "status": "succeeded"})
    monkeypatch.setattr(main.httpx, "post", fake_post)
    res = refund(tenant, inv["number"], pid, amount=25.5, reason="Returned one item")
    assert res.status_code == 200, res.text
    assert posted[0][0] == "https://api.stripe.com/v1/refunds" and posted[0][1] == ("sk_test_x", "")
    assert posted[0][2]["payment_intent"] == "pi_abc" and posted[0][2]["amount"] == 2550
    out = res.json()
    assert out["refund"]["method"] == "stripe" and out["refund"]["provider_refund_id"] == "re_1" and out["refund"]["status"] == "done"
    assert out["paid"] == 54.5 and out["due"] == 25.5
    assert "to your card" in outbox[0]["body"]
    # Stripe refusing: nothing recorded.
    monkeypatch.setattr(main.httpx, "post", lambda url, **kw: FakeResponse({"error": {"message": "Charge has already been refunded."}}, 400))
    res = refund(tenant, inv["number"], pid, amount=10)
    assert res.status_code == 502 and "already been refunded" in res.json()["detail"]
    assert invoice(tenant, inv["number"])["refunded_total"] == 25.5
    # Or record it here without asking Stripe - it was refunded in the dashboard.
    monkeypatch.setattr(main.httpx, "post", lambda url, **kw: (_ for _ in ()).throw(AssertionError("asked Stripe")))
    res = refund(tenant, inv["number"], pid, amount=10, through_gateway=False)
    assert res.status_code == 200 and res.json()["refund"]["method"] == "recorded"


def test_razorpay_and_paypal_receipts_go_back_their_own_way(tenant, account, monkeypatch, outbox):
    tenant.put("/api/payment-gateways/razorpay", json={"public_key": "rzp_test_x", "secret_key": "s", "is_active": True})
    tenant.put("/api/payment-gateways/paypal", json={"public_key": "cid", "secret_key": "sec", "is_active": True})
    rz = make_invoice(tenant, status="Awaiting Payment", currency="INR", line_items=[{"description": "x", "qty": 1, "price": 500.0, "tax_rate": "0%"}])
    pp = make_invoice(tenant, status="Awaiting Payment", line_items=[{"description": "x", "qty": 1, "price": 40.0, "tax_rate": "0%"}])
    rz_pid = online_receipt(rz["number"], account["email"], "razorpay", "pay_123", 500.0)
    pp_pid = online_receipt(pp["number"], account["email"], "paypal", "CAP9", 40.0)
    posted = []

    def fake_post(url, **kw):
        posted.append((url, kw))
        if url.endswith("/v1/oauth2/token"):
            return FakeResponse({"access_token": "tok"})
        if "/v1/payments/pay_123/refund" in url:
            return FakeResponse({"id": "rfnd_1", "status": "processed"})
        if url.endswith("/v2/payments/captures/CAP9/refund"):
            return FakeResponse({"id": "RF1", "status": "PENDING"})
        return FakeResponse({}, 404)
    monkeypatch.setattr(main.httpx, "post", fake_post)
    res = refund(tenant, rz["number"], rz_pid, amount=200)
    assert res.status_code == 200 and res.json()["refund"]["provider_refund_id"] == "rfnd_1" and res.json()["refund"]["status"] == "done"
    rz_call = next(c for c in posted if "pay_123/refund" in c[0])
    assert rz_call[0] == "https://api.razorpay.com/v1/payments/pay_123/refund" and rz_call[1]["auth"] == ("rzp_test_x", "s") and rz_call[1]["json"]["amount"] == 20000
    res = refund(tenant, pp["number"], pp_pid, amount=40, reason="Cancelled")
    assert res.status_code == 200, res.text
    assert res.json()["refund"]["status"] == "pending" and "still processing" in res.json()["message"]
    pp_call = next(c for c in posted if c[0].endswith("/CAP9/refund"))
    assert pp_call[0].startswith("https://api-m.sandbox.paypal.com/") and pp_call[1]["headers"]["Authorization"] == "Bearer tok"
    assert pp_call[1]["json"]["amount"] == {"value": "40.00", "currency_code": "GBP"} and pp_call[1]["json"]["note_to_payer"] == "Cancelled"
    assert invoice(tenant, pp["number"])["status"] == "Awaiting Payment"
    assert "to your PayPal account" in outbox[-1]["body"]


def test_a_receipt_with_no_gateway_behind_it_can_only_be_recorded(tenant, account):
    tenant.put("/api/payment-gateways/stripe", json={"public_key": "pk_test_x", "secret_key": "sk_test_x", "is_active": True})
    inv = make_invoice(tenant, status="Awaiting Payment")
    cash = receipt(tenant, inv["number"], 10, method="cash")
    res = refund(tenant, inv["number"], cash, amount=5, through_gateway=True)
    assert res.status_code == 400 and "record the refund" in res.json()["detail"]
    odd = online_receipt(inv["number"], account["email"], "stripe", "cs_not_an_intent", 20.0)
    res = refund(tenant, inv["number"], odd, amount=5)
    assert res.status_code == 400 and "no Stripe payment behind it" in res.json()["detail"]
    tenant.delete("/api/payment-gateways/stripe")
    assert refund(tenant, inv["number"], odd, amount=5).status_code == 400
    assert refund(tenant, inv["number"], odd, amount=5, through_gateway=False).status_code == 200


def test_the_webhook_hears_and_accounts_come_down(tenant):
    tenant.post("/api/webhooks", json={"url": "https://a.example/hook", "events": ["invoice.refunded"]})
    assert "invoice.refunded" in tenant.get("/api/webhooks").json()["events"]
    bank = tenant.post("/api/accounts", json={"name": "Bank", "kind": "bank"}).json()
    inv = make_invoice(tenant, status="Awaiting Payment", line_items=[{"description": "x", "qty": 1, "price": 100.0, "tax_rate": "0%"}])
    pid = receipt(tenant, inv["number"], 100, account_id=bank["id"])
    assert refund(tenant, inv["number"], pid, amount=40, refunded_on="2026-09-16").status_code == 200
    with main.SessionLocal() as db:
        d = db.query(models.DBWebhookDelivery).filter(models.DBWebhookDelivery.event == "invoice.refunded").order_by(models.DBWebhookDelivery.id.desc()).first()
        assert d is not None and inv["number"] in d.payload and '"recorded"' in d.payload
    rows = {a["name"]: a["totals"] for a in tenant.get("/api/accounts").json()["accounts"]}
    assert rows["Bank"]["all_time"] == 60.0


def test_nothing_crosses_a_business(tenant, account):
    inv = make_invoice(tenant, status="Awaiting Payment")
    pid = receipt(tenant, inv["number"], 10)
    other = f"other-{account['email']}"
    tenant.post("/api/client/logout")
    main.rate_limiter._hits.clear()
    tenant.post("/api/client/register", json={"email": other, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    tenant.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})
    assert refund(tenant, inv["number"], pid, amount=5).status_code == 404
