"""Paying an invoice with PayPal.

Offered when the business has PayPal keys switched on and the invoice is
in a currency PayPal settles. An order is opened for the amount due and
bound to the invoice; the customer approves it on PayPal's page; coming
back, the server captures the order and believes only what PayPal says
it captured - for this invoice, for at least what it asked. A refresh
records nothing twice; a capture for a cheaper invoice settles nothing;
a refused credential tells the business.
"""
import uuid

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
                        lambda to, subject, body, from_email, html_body=None, **kw: (sent.append({"to": to, "subject": subject, "body": body}), (True, ""))[1])
    return sent


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)
        self.headers = {"content-type": "application/json"}

    def json(self):
        return self._payload


class FakePayPal:
    """Answers the token, order and capture calls the way PayPal does,
    and remembers what it was asked."""

    def __init__(self, capture=None, order_status=200, token_status=200, capture_status=200):
        self.calls = []
        # PayPal's ids are unique; so are these, or a test's order would be
        # found belonging to an earlier test's invoice.
        self.order_id = "ORD" + uuid.uuid4().hex[:8].upper()
        self.capture = capture
        self.order_status, self.token_status, self.capture_status = order_status, token_status, capture_status

    def post(self, url, **kw):
        self.calls.append({"url": url, "auth": kw.get("auth"), "headers": kw.get("headers") or {}, "json": kw.get("json"), "data": kw.get("data")})
        if url.endswith("/v1/oauth2/token"):
            return FakeResponse({"access_token": "A.token"} if self.token_status == 200 else {"error": "invalid_client", "error_description": "Client Authentication failed"}, self.token_status)
        if url.endswith("/v2/checkout/orders"):
            if self.order_status != 200:
                return FakeResponse({"name": "UNPROCESSABLE_ENTITY", "message": "The requested action could not be performed.",
                                     "details": [{"issue": "CURRENCY_NOT_SUPPORTED", "description": "Currency code not supported."}]}, self.order_status)
            return FakeResponse({"id": self.order_id, "status": "CREATED", "links": [
                {"rel": "self", "href": "https://api.sandbox.paypal.com/v2/checkout/orders/" + self.order_id},
                {"rel": "approve", "href": "https://www.sandbox.paypal.com/checkoutnow?token=" + self.order_id}]})
        if "/capture" in url:
            if self.capture_status != 200:
                return FakeResponse({"name": "UNPROCESSABLE_ENTITY", "details": [{"issue": "ORDER_NOT_APPROVED"}]}, self.capture_status)
            return FakeResponse(dict(self.capture, id=self.order_id))
        return FakeResponse({}, 404)


def enable_paypal(tenant, live=False):
    res = tenant.put("/api/payment-gateways/paypal", json={"public_key": "cid", "secret_key": "sec", "is_active": True, "is_live": live})
    assert res.status_code == 200, res.text


def tracking_of(tenant, inv):
    me = tenant.get("/api/client/me").json()
    with main.SessionLocal() as db:
        return db.query(models.DBInvoice).filter(models.DBInvoice.number == inv["number"],
                                                 models.DBInvoice.client_id == me["id"]).first().tracking_id


def captured(tracking, value, currency="GBP", status="COMPLETED", cap_status="COMPLETED", reference=None):
    return {"status": status, "purchase_units": [{
        "reference_id": tracking if reference is None else reference,
        "payments": {"captures": [{"id": "CAP1", "status": cap_status, "amount": {"currency_code": currency, "value": value}}]}}]}


def test_paypal_is_offered_when_switched_on_and_the_currency_is_one_it_settles(tenant):
    inv = make_invoice(tenant, status="Awaiting Payment")
    t = tracking_of(tenant, inv)
    assert tenant.get(f"/api/public/invoices/{t}/pay/methods").json()["methods"] == []
    enable_paypal(tenant)
    assert [m["provider"] for m in tenant.get(f"/api/public/invoices/{t}/pay/methods").json()["methods"]] == ["paypal"]
    rupees = make_invoice(tenant, status="Awaiting Payment", currency="INR")
    assert tenant.get(f"/api/public/invoices/{tracking_of(tenant, rupees)}/pay/methods").json()["methods"] == [], "PayPal does not settle INR"
    raw = tenant.get(f"/api/public/invoices/{t}/pay/methods").text
    assert "cid" not in raw.split('"provider"')[0] and "sec" not in raw


def test_an_order_is_opened_for_the_amount_due_bound_to_the_invoice(tenant, monkeypatch):
    inv = make_invoice(tenant, status="Awaiting Payment")
    enable_paypal(tenant)
    t = tracking_of(tenant, inv)
    due = tenant.get(f"/api/public/invoices/{t}/pay/methods").json()["amount_due"]
    pp = FakePayPal()
    monkeypatch.setattr(main.httpx, "post", pp.post)
    res = tenant.post(f"/api/public/invoices/{t}/pay/paypal/order")
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["order_id"] == pp.order_id and out["approve_url"].startswith("https://www.sandbox.paypal.com/") and out["live"] is False
    token_call, order_call = pp.calls[0], pp.calls[1]
    assert token_call["url"] == "https://api-m.sandbox.paypal.com/v1/oauth2/token" and token_call["auth"] == ("cid", "sec")
    assert order_call["url"] == "https://api-m.sandbox.paypal.com/v2/checkout/orders"
    assert order_call["headers"]["Authorization"] == "Bearer A.token"
    unit = order_call["json"]["purchase_units"][0]
    assert unit["reference_id"] == t and unit["custom_id"] == inv["number"]
    assert unit["amount"] == {"currency_code": "GBP", "value": f"{due:.2f}"}
    assert order_call["json"]["application_context"]["return_url"].endswith(f"/invoice.html?id={t}&paypal=return")
    with main.SessionLocal() as db:
        row = db.query(models.DBInvoicePaymentOrder).filter(models.DBInvoicePaymentOrder.provider_order_id == pp.order_id).first()
        assert row.provider == "paypal" and row.amount_minor == int(round(due * 100)) and row.status == "created"


def test_live_keys_go_to_the_live_api(tenant, monkeypatch):
    inv = make_invoice(tenant, status="Awaiting Payment")
    enable_paypal(tenant, live=True)
    pp = FakePayPal()
    monkeypatch.setattr(main.httpx, "post", pp.post)
    assert tenant.post(f"/api/public/invoices/{tracking_of(tenant, inv)}/pay/paypal/order").json()["live"] is True
    assert pp.calls[0]["url"].startswith("https://api-m.paypal.com/")


def test_a_capture_settles_the_invoice_once(tenant, monkeypatch):
    inv = make_invoice(tenant, status="Awaiting Payment")
    enable_paypal(tenant)
    t = tracking_of(tenant, inv)
    due = tenant.get(f"/api/public/invoices/{t}/pay/methods").json()["amount_due"]
    pp = FakePayPal(capture=captured(t, f"{due:.2f}"))
    monkeypatch.setattr(main.httpx, "post", pp.post)
    tenant.post(f"/api/public/invoices/{t}/pay/paypal/order")
    res = tenant.post(f"/api/public/invoices/{t}/pay/paypal/capture", json={"order_id": pp.order_id})
    assert res.status_code == 200, res.text
    assert res.json() == {"paid": True, "already_recorded": False, "invoice_number": inv["number"], "status": "Paid"}
    assert pp.calls[-1]["url"].endswith("/v2/checkout/orders/" + pp.order_id + "/capture")
    got = tenant.get(f"/api/invoices/{inv['number']}").json()
    assert got["status"] == "Paid" and got["due"] == 0
    assert got["payments"][0]["method"] == "paypal" and got["payments"][0]["reference"] == "CAP1" and got["payments"][0]["account_name"] == "PayPal"
    # The customer refreshes: nothing is asked of PayPal, nothing recorded twice.
    n = len(pp.calls)
    again = tenant.post(f"/api/public/invoices/{t}/pay/paypal/capture", json={"order_id": pp.order_id})
    assert again.json()["already_recorded"] is True and len(pp.calls) == n
    assert len(tenant.get(f"/api/invoices/{inv['number']}").json()["payments"]) == 1


def test_the_capture_is_believed_only_for_this_invoice_and_this_amount(tenant, monkeypatch):
    small = make_invoice(tenant, status="Awaiting Payment", line_items=[{"description": "x", "qty": 1, "price": 10.0, "tax_rate": "0%"}])
    big = make_invoice(tenant, status="Awaiting Payment", line_items=[{"description": "y", "qty": 1, "price": 900.0, "tax_rate": "0%"}])
    enable_paypal(tenant)
    ts, tb = tracking_of(tenant, small), tracking_of(tenant, big)
    pp = FakePayPal(capture=captured(ts, "10.00"))
    monkeypatch.setattr(main.httpx, "post", pp.post)
    tenant.post(f"/api/public/invoices/{ts}/pay/paypal/order")
    # A real, approved order for the small invoice presented against the big one.
    assert tenant.post(f"/api/public/invoices/{tb}/pay/paypal/capture", json={"order_id": pp.order_id}).status_code == 400
    assert tenant.get(f"/api/invoices/{big['number']}").json()["due"] == 900.0
    # A capture that names the big invoice, on an order opened for the small
    # one. PayPal would never say this; the order's own binding is what refuses it.
    pp.capture = captured(tb, "900.00")
    assert tenant.post(f"/api/public/invoices/{tb}/pay/paypal/capture", json={"order_id": pp.order_id}).status_code == 400
    assert tenant.get(f"/api/invoices/{big['number']}").json()["due"] == 900.0
    pp.capture = captured(ts, "10.00")
    # An order nobody opened.
    assert tenant.post(f"/api/public/invoices/{ts}/pay/paypal/capture", json={"order_id": "ORDX"}).status_code == 400
    assert tenant.post(f"/api/public/invoices/{ts}/pay/paypal/capture", json={}).status_code == 400
    # PayPal says the capture was for less, or in another currency, or not complete.
    for bad in (captured(ts, "9.99"), captured(ts, "10.00", currency="USD"), captured(ts, "10.00", cap_status="PENDING"),
                captured(ts, "10.00", status="APPROVED"), captured(ts, "10.00", reference=tb)):
        pp.capture = bad
        assert tenant.post(f"/api/public/invoices/{ts}/pay/paypal/capture", json={"order_id": pp.order_id}).status_code == 400, bad
    assert tenant.get(f"/api/invoices/{small['number']}").json()["due"] == 10.0
    # PayPal refusing the capture outright.
    pp.capture, pp.capture_status = captured(ts, "10.00"), 422
    assert tenant.post(f"/api/public/invoices/{ts}/pay/paypal/capture", json={"order_id": pp.order_id}).status_code == 400
    pp.capture_status = 200
    assert tenant.post(f"/api/public/invoices/{ts}/pay/paypal/capture", json={"order_id": pp.order_id}).status_code == 200


def test_a_refused_credential_or_order_tells_the_business(tenant, outbox, monkeypatch):
    inv = make_invoice(tenant, status="Awaiting Payment")
    enable_paypal(tenant)
    t = tracking_of(tenant, inv)
    monkeypatch.setattr(main.httpx, "post", FakePayPal(token_status=401).post)
    res = tenant.post(f"/api/public/invoices/{t}/pay/paypal/order")
    assert res.status_code == 502 and "notified" in res.json()["detail"]
    assert len(outbox) == 1 and "PayPal" in outbox[0]["subject"] and "Client Authentication failed" in outbox[0]["body"]
    monkeypatch.setattr(main.httpx, "post", FakePayPal(order_status=422).post)
    assert tenant.post(f"/api/public/invoices/{t}/pay/paypal/order").status_code == 502
    assert len(outbox) == 1, "once a day"
    assert "cid" not in outbox[0]["body"] and "sec" not in outbox[0]["body"].split("Check")[0]


def test_nothing_is_offered_or_opened_without_keys_or_for_a_paid_invoice(tenant, monkeypatch):
    inv = make_invoice(tenant, status="Awaiting Payment")
    t = tracking_of(tenant, inv)
    assert tenant.post(f"/api/public/invoices/{t}/pay/paypal/order").status_code == 503
    assert tenant.post(f"/api/public/invoices/{t}/pay/paypal/capture", json={"order_id": "ORDX"}).status_code == 503
    enable_paypal(tenant)
    tenant.post(f"/api/invoices/{inv['number']}/mark-paid")
    assert tenant.post(f"/api/public/invoices/{t}/pay/paypal/order").status_code == 409
    rupees = make_invoice(tenant, status="Awaiting Payment", currency="INR")
    assert tenant.post(f"/api/public/invoices/{tracking_of(tenant, rupees)}/pay/paypal/order").status_code == 409


def test_the_zero_decimal_currencies_are_sent_whole(tenant, monkeypatch):
    inv = make_invoice(tenant, status="Awaiting Payment", currency="JPY", line_items=[{"description": "x", "qty": 1, "price": 1200.0, "tax_rate": "0%"}])
    enable_paypal(tenant)
    t = tracking_of(tenant, inv)
    pp = FakePayPal(capture=captured(t, "1200", currency="JPY"))
    monkeypatch.setattr(main.httpx, "post", pp.post)
    assert tenant.post(f"/api/public/invoices/{t}/pay/paypal/order").json()["amount"] == "1200"
    assert pp.calls[1]["json"]["purchase_units"][0]["amount"]["value"] == "1200"
    assert tenant.post(f"/api/public/invoices/{t}/pay/paypal/capture", json={"order_id": pp.order_id}).status_code == 200
    got = tenant.get(f"/api/invoices/{inv['number']}").json()
    assert got["due"] == 0 and got["payments"][0]["amount"] == 1200.0


def test_the_public_page_draws_buttons_for_a_business_without_razorpay(tenant):
    """The page only draws Pay buttons when the invoice carries a payment
    block. That block used to need Razorpay keys, so a business with only
    PayPal or Stripe had its methods listed and no button to press."""
    inv = make_invoice(tenant, status="Awaiting Payment")
    t = tracking_of(tenant, inv)
    assert tenant.get(f"/api/public/invoices/{t}").json()["payment"] is None
    enable_paypal(tenant)
    block = tenant.get(f"/api/public/invoices/{t}").json()["payment"]
    assert block and block["providers"] == ["paypal"] and block["key_id"] == ""
    tenant.put("/api/payment-gateways/razorpay", json={"public_key": "rzp_test_x", "secret_key": "s", "is_active": True})
    block = tenant.get(f"/api/public/invoices/{t}").json()["payment"]
    assert block["provider"] == "razorpay" and block["key_id"] == "rzp_test_x" and set(block["providers"]) == {"razorpay", "paypal"}
    assert "\"s\"" not in tenant.get(f"/api/public/invoices/{t}").text
    tenant.post(f"/api/invoices/{inv['number']}/mark-paid")
    assert tenant.get(f"/api/public/invoices/{t}").json()["payment"] is None
