"""Which account a customer's payment lands in.

Two arrangements. In direct mode each business uses its own Razorpay keys and
is paid straight away. In platform mode everything comes through one account
the operator holds - which means the customer has paid and the business has
not, so every collection is money owed until it is paid out.

Holding other people's money is a commitment rather than a shortcut, and the
settlement ledger is the record of it. Most of what matters here is that the
ledger cannot be skipped, double-counted, or cleared without evidence.
"""
import hashlib
import hmac
import uuid

import pytest

import main
import models
from conftest import make_invoice

PLATFORM_ID = "rzp_test_platform_id"
PLATFORM_SECRET = "platform_secret_value"
TENANT_ID = "rzp_test_tenant_id"
TENANT_SECRET = "tenant_secret_value"


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


@pytest.fixture
def superadmin():
    """The operator, on a session of their own - a tenant signing in on the
    same cookie now starts a fresh session and would evict this one."""
    from fastapi.testclient import TestClient
    main.rate_limiter._hits.clear()
    with TestClient(main.app) as operator:
        res = operator.post("/api/superadmin/login", json={
            "identifier": "hello@keyroutes.co", "password": "TestSuper123",
        })
        assert res.status_code == 200, res.text
        yield operator


@pytest.fixture
def platform_keys(monkeypatch):
    """The operator's own Razorpay account, as env vars."""
    monkeypatch.setenv("RAZORPAY_KEY_ID", PLATFORM_ID)
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", PLATFORM_SECRET)
    yield


def set_mode(superadmin, mode):
    res = superadmin.put("/api/superadmin/collection-mode", json={"mode": mode})
    assert res.status_code == 200, res.text
    return res.json()


def tenant_gateway(tenant):
    res = tenant.put("/api/payment-gateways/razorpay", json={
        "public_key": TENANT_ID, "secret_key": TENANT_SECRET, "is_active": True})
    assert res.status_code == 200, res.text


def issued(tenant, **kw):
    kw.setdefault("status", "Awaiting Payment")
    return make_invoice(tenant, **kw)


def link_for(tenant, number):
    return tenant.get(f"/api/invoices/{number}").json()["tracking_id"]


def sign(secret, order_id="order_A", payment_id="pay_B"):
    return hmac.new(secret.encode(), f"{order_id}|{payment_id}".encode(),
                    hashlib.sha256).hexdigest()


def pay(client, tid, secret, payment_id="pay_B"):
    return client.post(f"/api/public/invoices/{tid}/pay/razorpay/verify", json={
        "razorpay_order_id": "order_A",
        "razorpay_payment_id": payment_id,
        "razorpay_signature": sign(secret, "order_A", payment_id),
    })


def settlements(superadmin, status="owed"):
    res = superadmin.get(f"/api/superadmin/settlements?status={status}")
    assert res.status_code == 200, res.text
    return res.json()["settlements"]


# --- the switch ---------------------------------------------------------------

def test_it_starts_in_direct_mode(superadmin):
    """Nobody's money is pooled until somebody decides it should be."""
    assert superadmin.get("/api/superadmin/collection-mode").json()["mode"] == "direct"


def test_platform_mode_needs_the_platform_keys(superadmin, monkeypatch):
    monkeypatch.delenv("RAZORPAY_KEY_ID", raising=False)
    monkeypatch.delenv("RAZORPAY_KEY_SECRET", raising=False)
    res = superadmin.put("/api/superadmin/collection-mode", json={"mode": "platform"})
    assert res.status_code == 400
    assert "RAZORPAY_KEY_ID" in res.json()["detail"]


def test_the_mode_sticks(superadmin, platform_keys):
    set_mode(superadmin, "platform")
    assert superadmin.get("/api/superadmin/collection-mode").json()["mode"] == "platform"
    set_mode(superadmin, "direct")
    assert superadmin.get("/api/superadmin/collection-mode").json()["mode"] == "direct"


def test_an_unknown_mode_is_refused(superadmin):
    assert superadmin.put("/api/superadmin/collection-mode",
                          json={"mode": "whatever"}).status_code == 400


def test_only_the_operator_can_change_it(tenant):
    assert tenant.get("/api/superadmin/collection-mode").status_code in (401, 403)
    assert tenant.put("/api/superadmin/collection-mode",
                      json={"mode": "platform"}).status_code in (401, 403)


# --- which secret a payment is checked against --------------------------------

def test_direct_mode_uses_the_businesss_own_secret(client, tenant, superadmin,
                                                   account, platform_keys):
    set_mode(superadmin, "direct")
    main.rate_limiter._hits.clear()
    client.post("/api/client/login", json={"email": account["email"],
                                           "password": account["password"]})
    tenant_gateway(tenant)
    inv = issued(tenant)
    tid = link_for(tenant, inv["number"])

    assert pay(client, tid, TENANT_SECRET).status_code == 200
    assert tenant.get(f"/api/invoices/{inv['number']}").json()["status"] == "Paid"


def test_platform_mode_ignores_the_businesss_own_keys(client, tenant, superadmin,
                                                      account, platform_keys):
    """Otherwise a business that had set its own up would quietly keep
    collecting directly while the operator believed everything came through
    one account."""
    main.rate_limiter._hits.clear()
    client.post("/api/client/login", json={"email": account["email"],
                                           "password": account["password"]})
    tenant_gateway(tenant)
    inv = issued(tenant)
    tid = link_for(tenant, inv["number"])
    set_mode(superadmin, "platform")

    # Their own secret is no longer the one that counts.
    assert pay(client, tid, TENANT_SECRET).status_code == 400
    assert pay(client, tid, PLATFORM_SECRET).status_code == 200


def test_the_customer_page_offers_the_platform_key(client, tenant, superadmin,
                                                   account, platform_keys):
    set_mode(superadmin, "platform")
    main.rate_limiter._hits.clear()
    client.post("/api/client/login", json={"email": account["email"],
                                           "password": account["password"]})
    inv = issued(tenant)
    tid = link_for(tenant, inv["number"])

    body = client.get(f"/api/public/invoices/{tid}").json()
    assert body["payment"]["key_id"] == PLATFORM_ID
    assert PLATFORM_SECRET not in str(body), "the secret must never reach a page"


def test_a_business_with_no_keys_can_still_be_paid_in_platform_mode(
        client, tenant, superadmin, account, platform_keys):
    """The point of the arrangement: nobody has to set anything up."""
    set_mode(superadmin, "platform")
    main.rate_limiter._hits.clear()
    client.post("/api/client/login", json={"email": account["email"],
                                           "password": account["password"]})
    inv = issued(tenant)
    tid = link_for(tenant, inv["number"])

    assert client.get(f"/api/public/invoices/{tid}").json()["payment"] is not None
    assert pay(client, tid, PLATFORM_SECRET).status_code == 200


# --- the money that is now owed ------------------------------------------------

def test_a_platform_collection_is_recorded_as_owed(client, tenant, superadmin,
                                                   account, platform_keys):
    set_mode(superadmin, "platform")
    main.rate_limiter._hits.clear()
    client.post("/api/client/login", json={"email": account["email"],
                                           "password": account["password"]})
    inv = issued(tenant, line_items=[
        {"description": "Work", "qty": 1, "price": 500.0, "tax_rate": "No Tax"}])
    tid = link_for(tenant, inv["number"])
    pay(client, tid, PLATFORM_SECRET, payment_id="pay_OWED")

    rows = settlements(superadmin)
    mine = [r for r in rows if r["gateway_payment_id"] == "pay_OWED"]
    assert len(mine) == 1
    assert mine[0]["amount"] == 500.0
    assert mine[0]["status"] == "owed"
    assert mine[0]["invoice_number"] == inv["number"]


def test_direct_collection_owes_nobody_anything(client, tenant, superadmin,
                                                account, platform_keys):
    set_mode(superadmin, "direct")
    main.rate_limiter._hits.clear()
    client.post("/api/client/login", json={"email": account["email"],
                                           "password": account["password"]})
    tenant_gateway(tenant)
    inv = issued(tenant)
    tid = link_for(tenant, inv["number"])
    before = len(settlements(superadmin))

    pay(client, tid, TENANT_SECRET, payment_id="pay_DIRECT")
    assert len(settlements(superadmin)) == before, "the money went straight to them"


def test_a_replayed_payment_is_not_owed_twice(client, tenant, superadmin,
                                              account, platform_keys):
    """The receipt is recorded once, and so is the debt."""
    set_mode(superadmin, "platform")
    main.rate_limiter._hits.clear()
    client.post("/api/client/login", json={"email": account["email"],
                                           "password": account["password"]})
    inv = issued(tenant)
    tid = link_for(tenant, inv["number"])

    pay(client, tid, PLATFORM_SECRET, payment_id="pay_TWICE")
    pay(client, tid, PLATFORM_SECRET, payment_id="pay_TWICE")

    rows = [r for r in settlements(superadmin)
            if r["gateway_payment_id"] == "pay_TWICE"]
    assert len(rows) == 1


def test_paying_out_needs_a_reference(client, tenant, superadmin, account,
                                      platform_keys):
    """Clearing a debt without evidence it was sent is how one gets cleared
    twice, or never."""
    set_mode(superadmin, "platform")
    main.rate_limiter._hits.clear()
    client.post("/api/client/login", json={"email": account["email"],
                                           "password": account["password"]})
    inv = issued(tenant)
    pay(client, link_for(tenant, inv["number"]), PLATFORM_SECRET, payment_id="pay_OUT")

    sid = [r for r in settlements(superadmin)
           if r["gateway_payment_id"] == "pay_OUT"][0]["id"]
    assert superadmin.post(f"/api/superadmin/settlements/{sid}/paid-out",
                           json={}).status_code == 400

    ok = superadmin.post(f"/api/superadmin/settlements/{sid}/paid-out",
                         json={"reference": "NEFT-99812"})
    assert ok.status_code == 200
    assert ok.json()["status"] == "paid_out"


def test_it_cannot_be_paid_out_twice(client, tenant, superadmin, account,
                                     platform_keys):
    set_mode(superadmin, "platform")
    main.rate_limiter._hits.clear()
    client.post("/api/client/login", json={"email": account["email"],
                                           "password": account["password"]})
    inv = issued(tenant)
    pay(client, link_for(tenant, inv["number"]), PLATFORM_SECRET, payment_id="pay_ONCE")
    sid = [r for r in settlements(superadmin)
           if r["gateway_payment_id"] == "pay_ONCE"][0]["id"]

    superadmin.post(f"/api/superadmin/settlements/{sid}/paid-out",
                    json={"reference": "NEFT-1"})
    again = superadmin.post(f"/api/superadmin/settlements/{sid}/paid-out",
                            json={"reference": "NEFT-2"})
    assert again.status_code == 409


def test_the_operator_can_see_the_total_owed(client, tenant, superadmin,
                                             account, platform_keys):
    set_mode(superadmin, "platform")
    main.rate_limiter._hits.clear()
    client.post("/api/client/login", json={"email": account["email"],
                                           "password": account["password"]})
    inv = issued(tenant, currency="INR", line_items=[
        {"description": "Work", "qty": 1, "price": 300.0, "tax_rate": "No Tax"}])
    pay(client, link_for(tenant, inv["number"]), PLATFORM_SECRET, payment_id="pay_TOTAL")

    body = superadmin.get("/api/superadmin/collection-mode").json()
    assert body["owed_count"] >= 1
    assert any(t["amount"] >= 300.0 for t in body["owed_to_tenants"])


def test_settlements_are_operator_only(tenant):
    assert tenant.get("/api/superadmin/settlements").status_code in (401, 403)
    assert tenant.post("/api/superadmin/settlements/1/paid-out",
                       json={"reference": "x"}).status_code in (401, 403)
