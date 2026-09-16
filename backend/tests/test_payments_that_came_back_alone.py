"""Payments that came back without the customer, and the business hearing.

A customer who paid on the gateway's page and shut the tab had paid; the
invoice never knew. Every order opened at a gateway is now written down,
and a sweep asks about the ones still open - after the customer has had
ten minutes to come back on their own - and settles or closes them. The
business is emailed on every online payment, once, and a webhook that
wants invoice.paid hears.
"""
import os
import uuid
from datetime import datetime, timedelta

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


@pytest.fixture(autouse=True)
def _no_leftover_orders():
    """The sweep is platform-wide. Orders other tests opened and never
    closed would be asked about here, against this test's stubs."""
    with main.SessionLocal() as db:
        db.query(models.DBInvoicePaymentOrder).filter(
            models.DBInvoicePaymentOrder.status == "created").update({"status": "expired"}, synchronize_session=False)
        db.commit()
    yield


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(main, "send_email_background",
                        lambda to, subject, body, from_email, html_body=None, **kw: (sent.append({"to": to, "subject": subject, "body": body}), (True, ""))[1])
    return sent


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload, self.status_code, self.text = payload, status_code, str(payload)
        self.headers = {"content-type": "application/json"}

    def json(self):
        return self._payload


def tracking_of(tenant, inv):
    me = tenant.get("/api/client/me").json()
    with main.SessionLocal() as db:
        return db.query(models.DBInvoice).filter(models.DBInvoice.number == inv["number"],
                                                 models.DBInvoice.client_id == me["id"]).first().tracking_id


def age_order(order_id, minutes):
    with main.SessionLocal() as db:
        row = db.query(models.DBInvoicePaymentOrder).filter(models.DBInvoicePaymentOrder.provider_order_id == order_id).first()
        row.created_at = (datetime.now() - timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
        db.commit()


def order_status(order_id):
    with main.SessionLocal() as db:
        return db.query(models.DBInvoicePaymentOrder).filter(models.DBInvoicePaymentOrder.provider_order_id == order_id).first().status


def sweep():
    with main.SessionLocal() as db:
        return main.sweep_online_payments(db)


def open_stripe(tenant, monkeypatch, inv):
    tenant.put("/api/payment-gateways/stripe", json={"public_key": "pk_test_x", "secret_key": "sk_test_x", "is_active": True})
    sid = "cs_" + uuid.uuid4().hex[:10]
    monkeypatch.setattr(main.httpx, "post", lambda url, **kw: FakeResponse({"id": sid, "url": "https://checkout.stripe.test/" + sid}))
    res = tenant.post(f"/api/public/invoices/{tracking_of(tenant, inv)}/pay/stripe/session")
    assert res.status_code == 200, res.text
    return sid


# --- Stripe -----------------------------------------------------------------------

def test_a_stripe_session_is_written_down_and_swept_when_paid(tenant, monkeypatch, outbox):
    inv = make_invoice(tenant, status="Awaiting Payment")
    t = tracking_of(tenant, inv)
    sid = open_stripe(tenant, monkeypatch, inv)
    assert order_status(sid) == "created"
    due = tenant.get(f"/api/public/invoices/{t}/pay/methods").json()["amount_due"]
    asked = []

    def fake_get(url, **kw):
        asked.append((url, kw.get("auth")))
        return FakeResponse({"id": sid, "status": "complete", "payment_status": "paid", "client_reference_id": t,
                             "amount_total": int(round(due * 100)), "payment_intent": "pi_swept"})
    monkeypatch.setattr(main.httpx, "get", fake_get)
    # Too young: the customer gets ten minutes to come back on their own.
    t1 = sweep()
    assert t1["checked"] == 0 and asked == [] and order_status(sid) == "created"
    age_order(sid, 11)
    t2 = sweep()
    assert t2["checked"] == 1 and t2["paid"] == 1
    assert asked[0][0].endswith(f"/v1/checkout/sessions/{sid}") and asked[0][1] == ("sk_test_x", "")
    got = tenant.get(f"/api/invoices/{inv['number']}").json()
    assert got["status"] == "Paid" and got["payments"][0]["reference"] == "pi_swept" and got["payments"][0]["account_name"] == "Stripe"
    assert order_status(sid) == "paid"
    assert len(outbox) == 1 and outbox[0]["subject"].startswith(f"{inv['number']} paid: GBP") and "by card" in outbox[0]["subject"]
    # Swept once; the next sweep has nothing to ask.
    n = len(asked)
    assert sweep()["checked"] == 0 and len(asked) == n


def test_an_unpaid_expired_or_wrong_stripe_session_settles_nothing(tenant, monkeypatch, outbox):
    inv = make_invoice(tenant, status="Awaiting Payment")
    t = tracking_of(tenant, inv)
    sid = open_stripe(tenant, monkeypatch, inv)
    age_order(sid, 20)
    monkeypatch.setattr(main.httpx, "get", lambda url, **kw: FakeResponse({"id": sid, "status": "open", "payment_status": "unpaid", "client_reference_id": t, "amount_total": 12000}))
    assert sweep()["open"] == 1 and order_status(sid) == "created", "still open, asked again next time"
    monkeypatch.setattr(main.httpx, "get", lambda url, **kw: FakeResponse({"id": sid, "status": "expired", "payment_status": "unpaid", "client_reference_id": t}))
    assert sweep()["expired"] == 1 and order_status(sid) == "expired"
    # A paid session that names another invoice, or is short, is refused and not asked about again.
    sid2 = open_stripe(tenant, monkeypatch, inv)
    age_order(sid2, 20)
    monkeypatch.setattr(main.httpx, "get", lambda url, **kw: FakeResponse({"id": sid2, "status": "complete", "payment_status": "paid", "client_reference_id": "someone-else", "amount_total": 999999}))
    sweep()
    assert order_status(sid2) == "refused"
    assert tenant.get(f"/api/invoices/{inv['number']}").json()["status"] != "Paid"
    assert outbox == []


def test_the_customers_own_return_marks_the_session_paid_so_the_sweep_leaves_it(tenant, monkeypatch, outbox):
    inv = make_invoice(tenant, status="Awaiting Payment")
    t = tracking_of(tenant, inv)
    sid = open_stripe(tenant, monkeypatch, inv)
    due = tenant.get(f"/api/public/invoices/{t}/pay/methods").json()["amount_due"]
    monkeypatch.setattr(main.httpx, "get", lambda url, **kw: FakeResponse({"id": sid, "payment_status": "paid", "client_reference_id": t, "amount_total": int(round(due * 100)), "payment_intent": "pi_1"}))
    assert tenant.post(f"/api/public/invoices/{t}/pay/stripe/confirm", json={"session_id": sid}).json()["paid"] is True
    assert order_status(sid) == "paid" and len(outbox) == 1
    tenant.post(f"/api/public/invoices/{t}/pay/stripe/confirm", json={"session_id": sid})
    assert len(outbox) == 1, "a refresh does not write to the business twice"
    age_order(sid, 30)
    assert sweep()["checked"] == 0


def test_an_order_older_than_two_days_is_closed_without_asking(tenant, monkeypatch):
    inv = make_invoice(tenant, status="Awaiting Payment")
    sid = open_stripe(tenant, monkeypatch, inv)
    age_order(sid, 49 * 60)
    monkeypatch.setattr(main.httpx, "get", lambda url, **kw: (_ for _ in ()).throw(AssertionError("asked")))
    t = sweep()
    assert t["expired"] == 1 and t["checked"] == 0 and order_status(sid) == "expired"


def test_an_invoice_settled_by_hand_closes_its_open_orders(tenant, monkeypatch):
    inv = make_invoice(tenant, status="Awaiting Payment")
    sid = open_stripe(tenant, monkeypatch, inv)
    age_order(sid, 20)
    tenant.post(f"/api/invoices/{inv['number']}/mark-paid")
    monkeypatch.setattr(main.httpx, "get", lambda url, **kw: (_ for _ in ()).throw(AssertionError("asked")))
    assert sweep()["expired"] == 1 and order_status(sid) == "expired"


# --- Razorpay ---------------------------------------------------------------------

def test_a_razorpay_order_paid_but_never_confirmed_is_swept(tenant, monkeypatch, outbox):
    tenant.put("/api/payment-gateways/razorpay", json={"public_key": "rzp_test_x", "secret_key": "s", "is_active": True})
    inv = make_invoice(tenant, status="Awaiting Payment", currency="INR")
    t = tracking_of(tenant, inv)
    oid = "order_" + uuid.uuid4().hex[:8]
    monkeypatch.setattr(main.httpx, "post", lambda url, **kw: FakeResponse({"id": oid}))
    out = tenant.post(f"/api/public/invoices/{t}/pay/razorpay/order").json()
    assert out["order_id"] == oid
    age_order(oid, 15)
    asked = []

    def fake_get(url, **kw):
        asked.append((url, kw.get("auth")))
        return FakeResponse({"items": [
            {"id": "pay_failed", "status": "failed", "amount": out["amount"], "currency": "INR"},
            {"id": "pay_ok", "status": "captured", "amount": out["amount"], "currency": "INR"}]})
    monkeypatch.setattr(main.httpx, "get", fake_get)
    assert sweep()["paid"] == 1
    assert asked[0][0].endswith(f"/v1/orders/{oid}/payments") and asked[0][1] == ("rzp_test_x", "s")
    got = tenant.get(f"/api/invoices/{inv['number']}").json()
    assert got["status"] == "Paid" and got["payments"][0]["reference"] == "pay_ok"
    assert order_status(oid) == "paid" and len(outbox) == 1 and "by Razorpay" in outbox[0]["subject"]
    # Short or wrong-currency captures do not count.
    inv2 = make_invoice(tenant, status="Awaiting Payment", currency="INR")
    oid2 = "order_" + uuid.uuid4().hex[:8]
    monkeypatch.setattr(main.httpx, "post", lambda url, **kw: FakeResponse({"id": oid2}))
    out2 = tenant.post(f"/api/public/invoices/{tracking_of(tenant, inv2)}/pay/razorpay/order").json()
    age_order(oid2, 15)
    monkeypatch.setattr(main.httpx, "get", lambda url, **kw: FakeResponse({"items": [{"id": "pay_short", "status": "captured", "amount": out2["amount"] - 1, "currency": "INR"}]}))
    assert sweep()["open"] == 1 and tenant.get(f"/api/invoices/{inv2['number']}").json()["status"] != "Paid"


# --- PayPal -----------------------------------------------------------------------

def test_an_approved_paypal_order_is_captured_by_the_sweep(tenant, monkeypatch, outbox):
    tenant.put("/api/payment-gateways/paypal", json={"public_key": "cid", "secret_key": "sec", "is_active": True})
    inv = make_invoice(tenant, status="Awaiting Payment")
    t = tracking_of(tenant, inv)
    oid = "ORD" + uuid.uuid4().hex[:8].upper()
    due = tenant.get(f"/api/public/invoices/{t}/pay/methods").json()["amount_due"]
    calls = []

    def fake_post(url, **kw):
        calls.append(url)
        if url.endswith("/v1/oauth2/token"):
            return FakeResponse({"access_token": "tok"})
        if url.endswith("/v2/checkout/orders"):
            return FakeResponse({"id": oid, "links": [{"rel": "approve", "href": "https://www.sandbox.paypal.com/checkoutnow?token=" + oid}]})
        if url.endswith("/capture"):
            return FakeResponse({"id": oid, "status": "COMPLETED", "purchase_units": [{"reference_id": t, "payments": {"captures": [
                {"id": "CAPS", "status": "COMPLETED", "amount": {"currency_code": "GBP", "value": f"{due:.2f}"}}]}}]})
        return FakeResponse({}, 404)
    monkeypatch.setattr(main.httpx, "post", fake_post)
    monkeypatch.setattr(main.httpx, "get", lambda url, **kw: FakeResponse({"id": oid, "status": "APPROVED"}))
    assert tenant.post(f"/api/public/invoices/{t}/pay/paypal/order").json()["order_id"] == oid
    age_order(oid, 12)
    assert sweep()["paid"] == 1
    assert any(u.endswith(f"/v2/checkout/orders/{oid}/capture") for u in calls), calls
    got = tenant.get(f"/api/invoices/{inv['number']}").json()
    assert got["status"] == "Paid" and got["payments"][0]["reference"] == "CAPS" and got["payments"][0]["account_name"] == "PayPal"
    assert order_status(oid) == "paid" and len(outbox) == 1 and "by PayPal" in outbox[0]["subject"]
    # Once paid, the customer's late return records nothing more.
    assert tenant.post(f"/api/public/invoices/{t}/pay/paypal/capture", json={"order_id": oid}).json()["already_recorded"] is True
    assert len(outbox) == 1


def test_a_voided_paypal_order_is_closed_and_a_created_one_left_open(tenant, monkeypatch):
    tenant.put("/api/payment-gateways/paypal", json={"public_key": "cid", "secret_key": "sec", "is_active": True})
    inv = make_invoice(tenant, status="Awaiting Payment")
    t = tracking_of(tenant, inv)
    oid = "ORD" + uuid.uuid4().hex[:8].upper()
    monkeypatch.setattr(main.httpx, "post", lambda url, **kw: FakeResponse({"access_token": "tok"}) if url.endswith("/token") else FakeResponse({"id": oid, "links": [{"rel": "approve", "href": "https://x/" + oid}]}))
    tenant.post(f"/api/public/invoices/{t}/pay/paypal/order")
    age_order(oid, 12)
    monkeypatch.setattr(main.httpx, "get", lambda url, **kw: FakeResponse({"id": oid, "status": "CREATED"}))
    assert sweep()["open"] == 1 and order_status(oid) == "created"
    monkeypatch.setattr(main.httpx, "get", lambda url, **kw: FakeResponse({"id": oid, "status": "VOIDED"}))
    assert sweep()["expired"] == 1 and order_status(oid) == "expired"


# --- the business hears -------------------------------------------------------------

def test_the_notice_can_be_switched_off_and_the_webhook_hears_regardless(tenant, monkeypatch, outbox):
    tenant.post("/api/webhooks", json={"url": "https://a.example/hook", "events": ["invoice.paid"]})
    assert "invoice.paid" in tenant.get("/api/webhooks").json()["events"]
    tenant.post("/api/settings", json={"notify_online_payments": "0"})
    inv = make_invoice(tenant, status="Awaiting Payment")
    t = tracking_of(tenant, inv)
    sid = open_stripe(tenant, monkeypatch, inv)
    due = tenant.get(f"/api/public/invoices/{t}/pay/methods").json()["amount_due"]
    monkeypatch.setattr(main.httpx, "get", lambda url, **kw: FakeResponse({"id": sid, "payment_status": "paid", "client_reference_id": t, "amount_total": int(round(due * 100)), "payment_intent": "pi_q"}))
    assert tenant.post(f"/api/public/invoices/{t}/pay/stripe/confirm", json={"session_id": sid}).status_code == 200
    assert outbox == [], "switched off"
    with main.SessionLocal() as db:
        d = db.query(models.DBWebhookDelivery).filter(models.DBWebhookDelivery.event == "invoice.paid").order_by(models.DBWebhookDelivery.id.desc()).first()
        assert d is not None and inv["number"] in d.payload and '"stripe"' in d.payload


def test_the_sweep_is_a_scheduled_job(tenant):
    assert any(name == "online_payment_sweep" for name, _k, _f in main.SCHEDULED_JOBS)
    with main.SessionLocal() as db:
        out = main.job_online_payment_sweep(db, datetime.now())
    assert "asked" in out and "paid" in out
