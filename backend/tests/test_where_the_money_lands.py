"""Where the money lands, and whether the keys that collect it work.

A business names its accounts - the bank, the cash box - and every
receipt lands in one: the one picked on the form, the default when none
is picked, the gateway's own when a customer pays online. Totals per
account answer "how much came into the bank this month". Keys can be
checked against the provider before a customer finds out, and when a
customer's attempt fails because of them the business is told, once a
day, not never. Nothing crosses a business.
"""
from datetime import date

import pytest

import main
import models
from conftest import make_invoice


class FakeResponse:
    def __init__(self, payload, status_code=200, content_type="application/json"):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)
        self.headers = {"content-type": content_type}

    def json(self):
        return self._payload


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


def account(tenant, name, **kw):
    res = tenant.post("/api/accounts", json=dict({"name": name, "kind": "bank"}, **kw))
    assert res.status_code == 200, res.text
    return res.json()


def receive(tenant, number, amount, **kw):
    return tenant.post(f"/api/invoices/{number}/payments", json=dict({"amount": amount, "paid_on": date.today().isoformat()}, **kw))


def payments_of(tenant, number):
    return tenant.get(f"/api/invoices/{number}").json()["payments"]


def tracking_of(tenant, inv):
    me = tenant.get("/api/client/me").json()
    with main.SessionLocal() as db:
        return db.query(models.DBInvoice).filter(models.DBInvoice.number == inv["number"],
                                                 models.DBInvoice.client_id == me["id"]).first().tracking_id


def test_the_first_account_is_the_default_and_a_receipt_lands_in_it(tenant):
    assert tenant.get("/api/accounts").json()["accounts"] == []
    bank = account(tenant, "HDFC current", details="A/c 1234 · IFSC HDFC0001")
    assert bank["is_default"] is True and bank["kind"] == "bank"
    cash = account(tenant, "Cash box", kind="cash")
    assert cash["is_default"] is False
    inv = make_invoice(tenant, status="Awaiting Payment")
    assert receive(tenant, inv["number"], 50).status_code == 200
    got = payments_of(tenant, inv["number"])
    assert got[0]["account_id"] == bank["id"] and got[0]["account_name"] == "HDFC current", got


def test_a_receipt_can_name_the_account_and_only_an_open_one_of_mine(tenant):
    bank = account(tenant, "Bank")
    cash = account(tenant, "Cash box", kind="cash")
    inv = make_invoice(tenant, status="Awaiting Payment")
    assert receive(tenant, inv["number"], 10, account_id=cash["id"]).status_code == 200
    assert payments_of(tenant, inv["number"])[0]["account_name"] == "Cash box"
    assert receive(tenant, inv["number"], 10, account_id="abc").status_code in (400, 422), "not a number"
    assert receive(tenant, inv["number"], 10, account_id=999999).status_code == 400
    tenant.put(f"/api/accounts/{cash['id']}", json={"active": False})
    assert receive(tenant, inv["number"], 10, account_id=cash["id"]).status_code == 400, "a closed account takes nothing"
    assert receive(tenant, inv["number"], 10).status_code == 200
    assert payments_of(tenant, inv["number"])[-1]["account_id"] == bank["id"]


def test_with_no_accounts_a_receipt_is_simply_untracked(tenant):
    inv = make_invoice(tenant, status="Awaiting Payment")
    assert receive(tenant, inv["number"], 25).status_code == 200
    got = payments_of(tenant, inv["number"])[0]
    assert got["account_id"] is None and got["account_name"] == ""
    listed = tenant.get("/api/accounts").json()
    assert listed["untracked"]["all_time"] == 25.0 and listed["untracked"]["count"] == 1


def test_marking_paid_lands_in_the_default(tenant):
    bank = account(tenant, "Bank")
    inv = make_invoice(tenant, status="Awaiting Payment")
    assert tenant.post(f"/api/invoices/{inv['number']}/mark-paid").status_code == 200
    assert payments_of(tenant, inv["number"])[0]["account_id"] == bank["id"]


def test_the_default_moves_and_a_closed_account_cannot_hold_it(tenant):
    bank = account(tenant, "Bank")
    other = account(tenant, "Other bank")
    assert tenant.put(f"/api/accounts/{other['id']}", json={"is_default": True}).json()["is_default"] is True
    rows = {a["name"]: a for a in tenant.get("/api/accounts").json()["accounts"]}
    assert rows["Bank"]["is_default"] is False and rows["Other bank"]["is_default"] is True
    assert tenant.put(f"/api/accounts/{bank['id']}", json={"active": False}).status_code == 200
    assert tenant.put(f"/api/accounts/{bank['id']}", json={"is_default": True}).status_code == 400
    # Closing the default leaves nobody default.
    tenant.put(f"/api/accounts/{other['id']}", json={"active": False})
    assert all(not a["is_default"] for a in tenant.get("/api/accounts").json()["accounts"])
    # And the list of accounts is sorted default first.
    tenant.put(f"/api/accounts/{bank['id']}", json={"active": True, "is_default": True})
    assert tenant.get("/api/accounts").json()["accounts"][0]["name"] == "Bank"


def test_what_an_account_must_be(tenant):
    assert tenant.post("/api/accounts", json={"name": "  ", "kind": "bank"}).status_code == 400
    assert tenant.post("/api/accounts", json={"name": "X", "kind": "crypto"}).status_code == 400
    a = account(tenant, "Bank")
    assert tenant.put(f"/api/accounts/{a['id']}", json={"name": "Renamed", "details": "IBAN GB00"}).json()["details"] == "IBAN GB00"
    assert tenant.put(f"/api/accounts/{a['id']}", json={"kind": "crypto"}).status_code == 400


def test_an_account_with_receipts_is_closed_not_deleted(tenant):
    bank = account(tenant, "Bank")
    spare = account(tenant, "Spare")
    inv = make_invoice(tenant, status="Awaiting Payment")
    receive(tenant, inv["number"], 10, account_id=bank["id"])
    out = tenant.delete(f"/api/accounts/{bank['id']}").json()
    assert out["closed"] is True and "1 receipt" in out["message"]
    rows = {a["name"]: a for a in tenant.get("/api/accounts").json()["accounts"]}
    assert rows["Bank"]["active"] is False and rows["Bank"]["is_default"] is False
    assert payments_of(tenant, inv["number"])[0]["account_name"] == "Bank", "the receipt keeps its answer"
    assert tenant.delete(f"/api/accounts/{spare['id']}").json()["closed"] is False
    assert "Spare" not in {a["name"] for a in tenant.get("/api/accounts").json()["accounts"]}
    assert tenant.delete(f"/api/accounts/{spare['id']}").status_code == 404


def test_totals_per_account_this_month_last_month_all_time(tenant):
    bank = account(tenant, "Bank")
    cash = account(tenant, "Cash box", kind="cash")
    inv = make_invoice(tenant, status="Awaiting Payment", line_items=[{"description": "Big", "qty": 1, "price": 1000.0, "tax_rate": "0%"}])
    today = date.today()
    last = (today.replace(day=1) - main.timedelta(days=1)).isoformat()
    assert receive(tenant, inv["number"], 100, account_id=bank["id"]).status_code == 200
    assert receive(tenant, inv["number"], 200, account_id=bank["id"], paid_on=last).status_code == 200
    assert receive(tenant, inv["number"], 30, account_id=cash["id"]).status_code == 200
    rows = {a["name"]: a["totals"] for a in tenant.get("/api/accounts").json()["accounts"]}
    assert rows["Bank"] == {"this_month": 100.0, "last_month": 200.0, "all_time": 300.0, "count": 2, "last_on": today.isoformat()}
    assert rows["Cash box"]["this_month"] == 30.0 and rows["Cash box"]["count"] == 1


def test_an_online_payment_files_itself_under_the_gateway(tenant):
    bank = account(tenant, "Bank")
    inv = make_invoice(tenant, status="Awaiting Payment")
    tenant.put("/api/payment-gateways/stripe", json={"public_key": "pk_test_x", "secret_key": "sk_test_x", "is_active": True})
    tracking = tracking_of(tenant, inv)
    due = tenant.get(f"/api/public/invoices/{tracking}/pay/methods").json()["amount_due"]
    original = main.httpx.get
    main.httpx.get = lambda url, **kw: FakeResponse({"payment_status": "paid", "client_reference_id": tracking,
                                                     "amount_total": int(round(due * 100)), "payment_intent": "pi_1"})
    try:
        res = tenant.post(f"/api/public/invoices/{tracking}/pay/stripe/confirm", json={"session_id": "cs_1"})
    finally:
        main.httpx.get = original
    assert res.status_code == 200, res.text
    got = payments_of(tenant, inv["number"])[0]
    assert got["account_name"] == "Stripe" and got["account_id"] != bank["id"]
    rows = {a["name"]: a for a in tenant.get("/api/accounts").json()["accounts"]}
    assert rows["Stripe"]["kind"] == "gateway" and rows["Stripe"]["provider"] == "stripe" and rows["Stripe"]["is_default"] is False
    assert rows["Bank"]["is_default"] is True, "the gateway account never takes the default"
    assert rows["Stripe"]["totals"]["all_time"] == due


def test_nothing_crosses_a_business(tenant):
    bank = account(tenant, "Bank")
    other = "other-" + tenant.get("/api/client/me").json()["email"]
    tenant.post("/api/client/logout")
    main.rate_limiter._hits.clear()
    tenant.post("/api/client/register", json={"email": other, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    tenant.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})
    assert tenant.get("/api/accounts").json()["accounts"] == []
    assert tenant.put(f"/api/accounts/{bank['id']}", json={"name": "Stolen"}).status_code == 404
    assert tenant.delete(f"/api/accounts/{bank['id']}").status_code == 404
    inv = make_invoice(tenant, status="Awaiting Payment")
    assert receive(tenant, inv["number"], 10, account_id=bank["id"]).status_code == 400


# --- do the keys work -----------------------------------------------------------

def test_checking_keys_asks_the_provider_and_says_what_it_said(tenant, monkeypatch):
    assert tenant.post("/api/payment-gateways/stripe/check").status_code == 400, "nothing saved yet"
    tenant.put("/api/payment-gateways/stripe", json={"public_key": "pk_test_x", "secret_key": "sk_test_x", "is_active": True, "is_live": True})
    seen = {}

    def fake_get(url, **kw):
        seen["url"], seen["auth"] = url, kw.get("auth")
        return FakeResponse({"livemode": False, "available": []})
    monkeypatch.setattr(main.httpx, "get", fake_get)
    out = tenant.post("/api/payment-gateways/stripe/check").json()
    assert out["ok"] is True and "test mode" in out["message"] and out["live"] is False
    assert seen["url"].endswith("/v1/balance") and seen["auth"] == ("sk_test_x", "")
    assert "test keys but the box says live" in out["warning"]
    assert out["offered"] is True

    monkeypatch.setattr(main.httpx, "get", lambda url, **kw: FakeResponse({"error": {"message": "Invalid API Key provided"}}, 401))
    out = tenant.post("/api/payment-gateways/stripe/check").json()
    assert out["ok"] is False and "Invalid API Key" in out["message"] and out["offered"] is False

    def boom(url, **kw):
        raise RuntimeError("dns")
    monkeypatch.setattr(main.httpx, "get", boom)
    out = tenant.post("/api/payment-gateways/stripe/check").json()
    assert out["ok"] is False and "Could not reach" in out["message"]
    logs = tenant.get("/api/audit-logs").json()
    assert any(l["action"] == "payment_gateway_checked" for l in logs)


def test_razorpay_and_paypal_are_checked_their_own_way(tenant, monkeypatch):
    tenant.put("/api/payment-gateways/razorpay", json={"public_key": "rzp_live_x", "secret_key": "s", "is_active": True, "is_live": True})
    seen = {}

    def fake_get(url, **kw):
        seen["url"], seen["auth"] = url, kw.get("auth")
        return FakeResponse({"items": []})
    monkeypatch.setattr(main.httpx, "get", fake_get)
    out = tenant.post("/api/payment-gateways/razorpay/check").json()
    assert out["ok"] and out["live"] is True and out["warning"] == "" and "razorpay.com/v1/payments" in seen["url"] and seen["auth"] == ("rzp_live_x", "s")

    tenant.put("/api/payment-gateways/paypal", json={"public_key": "cid", "secret_key": "sec", "is_active": False})
    posted = []

    def fake_post(url, **kw):
        posted.append(url)
        return FakeResponse({"access_token": "t"} if "sandbox" in url else {"error_description": "Client Authentication failed"}, 200 if "sandbox" in url else 401)
    monkeypatch.setattr(main.httpx, "post", fake_post)
    out = tenant.post("/api/payment-gateways/paypal/check").json()
    assert out["ok"] and out["live"] is False and "sandbox" in out["message"] and len(posted) == 2
    assert out["offered"] is False, "correct keys, but not switched on"
    assert tenant.post("/api/payment-gateways/bitcoin/check").status_code == 400


def test_a_customer_who_cannot_pay_gets_the_business_told_once_a_day(tenant, outbox, monkeypatch):
    tenant.put("/api/payment-gateways/stripe", json={"public_key": "pk_test_x", "secret_key": "sk_bad", "is_active": True})
    inv = make_invoice(tenant, status="Awaiting Payment")
    tracking = tracking_of(tenant, inv)
    monkeypatch.setattr(main.httpx, "post", lambda url, **kw: FakeResponse({"error": {"message": "Invalid API Key provided: sk_bad"}}, 401))
    res = tenant.post(f"/api/public/invoices/{tracking}/pay/stripe/session")
    assert res.status_code == 502
    assert len(outbox) == 1 and "cannot pay you through Stripe" in outbox[0]["subject"]
    assert "Invalid API Key" in outbox[0]["body"] and "Check keys" in outbox[0]["body"]
    tenant.post(f"/api/public/invoices/{tracking}/pay/stripe/session")
    assert len(outbox) == 1, "the second failure the same day says nothing more"
    # Razorpay's failures reach the same place.
    tenant.put("/api/payment-gateways/razorpay", json={"public_key": "rzp_test_x", "secret_key": "s", "is_active": True})
    monkeypatch.setattr(main.httpx, "post", lambda url, **kw: FakeResponse({"error": {"description": "Authentication failed"}}, 401))
    assert tenant.post(f"/api/public/invoices/{tracking}/pay/razorpay/order").status_code == 502
    assert len(outbox) == 2 and "Razorpay" in outbox[1]["subject"]
