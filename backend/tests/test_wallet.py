"""Wallet, metered billing and payment gateway wiring.

The invariants that matter: the balance never drifts, never goes negative, a
paid top-up credits exactly once, and nothing credits a wallet without a
verified provider callback.
"""
import hashlib
import hmac
import json
import time

import pytest

import main
from conftest import make_employee


@pytest.fixture
def superadmin(client):
    main.rate_limiter._hits.clear()
    res = client.post("/api/superadmin/login", json={
        "identifier": "hello@keyroutes.co", "password": "TestSuper123",
    })
    assert res.status_code == 200, res.text
    return client



def client_id_for(superadmin_client, email):
    """The test database accumulates tenants, so the account under test has to
    be looked up by email rather than taking the first row."""
    rows = superadmin_client.get("/api/superadmin/clients").json()
    match = [r for r in rows if r["email"] == email]
    assert match, f"no tenant found for {email}"
    return match[0]["id"]

def credit(tenant_client, superadmin_client, amount, tenant_id):
    """Operator tops a tenant up, which is the path that works without keys."""
    return superadmin_client.post(f"/api/superadmin/wallets/{tenant_id}/adjust",
                                  json={"amount": amount, "reason": "test credit"})


# --- money conversion -------------------------------------------------------

@pytest.mark.parametrize("amount,currency,expected", [
    (10, "GBP", 1000), (0.05, "GBP", 5), (12.345, "GBP", 1235),
    (100, "JPY", 100),      # no minor unit
    (0, "GBP", 0),
])
def test_to_minor(amount, currency, expected):
    assert main.to_minor(amount, currency) == expected


def test_minor_round_trip_does_not_drift():
    """A hundred small debits must not lose a penny."""
    total = 0
    for _ in range(100):
        total += main.to_minor(0.07, "GBP")
    assert total == 700
    assert main.to_major(total, "GBP") == 7.00


# --- wallet basics ----------------------------------------------------------

def test_new_wallet_starts_empty(tenant):
    w = tenant.get("/api/wallet").json()
    assert w["balance"] == 0.0
    assert w["is_empty"] is True
    assert w["pricing"], "the tenant should be able to see what things cost"


def test_operator_credit_and_ledger(client, account, superadmin):
    cid = client_id_for(superadmin, account["email"])
    res = credit(None, superadmin, 25, cid)
    assert res.status_code == 200
    assert res.json()["balance"] == 25.0

    superadmin.post("/api/superadmin/logout")
    tenant = account["client"]
    tenant.post("/api/client/login", json={"email": account["email"], "password": account["password"]})
    assert tenant.get("/api/wallet").json()["balance"] == 25.0

    rows = tenant.get("/api/wallet/transactions").json()
    assert rows[0]["direction"] == "credit"
    assert rows[0]["amount"] == 25.0
    assert rows[0]["balance_after"] == 25.0


def test_adjustment_requires_a_reason(superadmin):
    cid = superadmin.get("/api/superadmin/clients").json()[0]["id"]
    res = superadmin.post(f"/api/superadmin/wallets/{cid}/adjust", json={"amount": 5})
    assert res.status_code == 400
    assert "reason" in res.json()["detail"].lower()


def test_debit_cannot_take_balance_negative(superadmin):
    cid = superadmin.get("/api/superadmin/clients").json()[0]["id"]
    superadmin.post(f"/api/superadmin/wallets/{cid}/adjust", json={"amount": 5, "reason": "seed"})
    res = superadmin.post(f"/api/superadmin/wallets/{cid}/adjust",
                          json={"amount": -50, "reason": "too much"})
    assert res.status_code == 400
    assert "below zero" in res.json()["detail"]


# --- metering ---------------------------------------------------------------

def test_action_is_free_until_priced(tenant):
    q = tenant.get("/api/wallet/quote?action=not_a_real_action").json()
    assert q["cost"] == 0.0
    assert q["affordable"] is True


def test_quote_respects_the_free_allowance(tenant):
    tenant.get("/api/wallet")                 # seeds pricing
    q = tenant.get("/api/wallet/quote?action=invoice_send&quantity=1").json()
    # invoice_send ships with a monthly free allowance, so the first is free.
    assert q["free_remaining"] > 0
    assert q["cost"] == 0.0


def test_charge_lands_on_the_ledger(client, account, superadmin):
    cid = client_id_for(superadmin, account["email"])
    superadmin.post(f"/api/superadmin/wallets/{cid}/adjust", json={"amount": 20, "reason": "seed"})
    # Remove the free allowance so the next call is billable.
    rules = superadmin.get("/api/superadmin/pricing").json()
    rule = next(r for r in rules if r["action_key"] == "ai_resume_screen")
    superadmin.put(f"/api/superadmin/pricing/{rule['id']}",
                   json={"unit_price": 0.40, "free_allowance": 0})
    superadmin.post("/api/superadmin/logout")

    tenant = account["client"]
    tenant.post("/api/client/login", json={"email": account["email"], "password": account["password"]})
    before = tenant.get("/api/wallet").json()["balance"]
    q = tenant.get("/api/wallet/quote?action=ai_resume_screen").json()
    assert q["cost"] == 0.40
    assert q["affordable"] is True

    charged = main.charge_wallet
    # Drive the charge directly; the AI endpoint itself needs an LLM key.
    import database
    with database.SessionLocal() as db:
        charged(db, cid, "ai_resume_screen", 1, "candidate-1")
        db.commit()

    after = tenant.get("/api/wallet").json()["balance"]
    assert round(before - after, 2) == 0.40
    tx = tenant.get("/api/wallet/transactions?direction=debit").json()[0]
    assert tx["action_key"] == "ai_resume_screen"
    assert tx["balance_after"] == after


def test_running_out_of_credit_is_refused_with_402(client, account, superadmin):
    client_id_for(superadmin, account["email"])
    rules = superadmin.get("/api/superadmin/pricing").json()
    rule = next(r for r in rules if r["action_key"] == "invoice_send")
    superadmin.put(f"/api/superadmin/pricing/{rule['id']}",
                   json={"unit_price": 2.00, "free_allowance": 0})
    superadmin.post("/api/superadmin/logout")

    tenant = account["client"]
    tenant.post("/api/client/login", json={"email": account["email"], "password": account["password"]})
    inv = tenant.post("/api/invoices", json={
        "contact": "C", "email": "c@example.com",
        "issue_date": "2026-01-01", "due_date": "2026-01-31",
        "line_items": [{"description": "X", "qty": 1, "price": 10}],
    }).json()

    res = tenant.post(f"/api/invoices/{inv['number']}/send")
    assert res.status_code == 402
    detail = res.json()["detail"]
    assert "credit" in detail.lower()
    assert "top up" in detail.lower()


def test_paid_action_does_not_charge_when_it_fails_validation(tenant):
    """An invoice with no email is refused before any charge."""
    inv = tenant.post("/api/invoices", json={
        "contact": "C", "issue_date": "2026-01-01", "due_date": "2026-01-31",
        "line_items": [{"description": "X", "qty": 1, "price": 10}],
    }).json()
    before = tenant.get("/api/wallet").json()["balance"]
    assert tenant.post(f"/api/invoices/{inv['number']}/send").status_code == 400
    assert tenant.get("/api/wallet").json()["balance"] == before


# --- pricing control --------------------------------------------------------

def test_operator_sets_the_price(superadmin):
    rules = superadmin.get("/api/superadmin/pricing").json()
    assert rules, "pricing should be seeded"
    rule = rules[0]
    res = superadmin.put(f"/api/superadmin/pricing/{rule['id']}",
                         json={"unit_price": 1.23, "free_allowance": 3})
    assert res.status_code == 200
    assert res.json()["unit_price"] == 1.23


@pytest.mark.parametrize("payload,fragment", [
    ({"unit_price": -1}, "negative"),
    ({"unit_price": 5000}, "looks wrong"),
    ({"free_allowance": -5}, "between 0 and 100000"),
])
def test_pricing_validation(superadmin, payload, fragment):
    rule = superadmin.get("/api/superadmin/pricing").json()[0]
    res = superadmin.put(f"/api/superadmin/pricing/{rule['id']}", json=payload)
    assert res.status_code == 400
    assert fragment in res.json()["detail"]


def test_tenants_cannot_set_prices(tenant):
    assert tenant.get("/api/superadmin/pricing").status_code == 401
    assert tenant.put("/api/superadmin/pricing/1", json={"unit_price": 0}).status_code == 401
    assert tenant.post("/api/superadmin/wallets/1/adjust",
                       json={"amount": 1000, "reason": "free money"}).status_code == 401


# --- gateways ---------------------------------------------------------------

def test_providers_report_themselves_as_unconfigured(tenant, monkeypatch):
    for var in ("STRIPE_SECRET_KEY", "RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET",
                "PAYPAL_CLIENT_ID", "PAYPAL_SECRET", "GOCARDLESS_ACCESS_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    data = tenant.get("/api/wallet/providers").json()
    assert data["any_enabled"] is False
    assert all(p["enabled"] is False for p in data["providers"])


def test_topup_against_an_unconfigured_provider_says_so(tenant, monkeypatch):
    """Unconfigured names the setting that is missing, because the person who
    hits this is the one who can fix it."""
    monkeypatch.delenv("GOCARDLESS_ACCESS_TOKEN", raising=False)
    res = tenant.post("/api/wallet/topup", json={"amount": 25, "provider": "gocardless"})
    assert res.status_code == 503
    assert "not configured" in res.json()["detail"]
    assert "GOCARDLESS_ACCESS_TOKEN" in res.json()["detail"]


@pytest.mark.parametrize("amount,code", [(0.5, 400), (99999, 400)])
def test_topup_amount_limits(tenant, amount, code):
    assert tenant.post("/api/wallet/topup",
                       json={"amount": amount, "provider": "gocardless"}).status_code == code


def test_unknown_provider_rejected(tenant):
    res = tenant.post("/api/wallet/topup", json={"amount": 25, "provider": "bitcoin"})
    assert res.status_code == 400


def test_webhook_without_a_secret_is_refused(client, monkeypatch):
    """An unverified webhook would let anyone credit their own wallet."""
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("RAZORPAY_WEBHOOK_SECRET", raising=False)
    assert client.post("/api/wallet/webhook/stripe", json={}).status_code == 503
    assert client.post("/api/wallet/webhook/razorpay", json={}).status_code == 503


def test_webhook_with_a_bad_signature_is_refused(client, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    res = client.post("/api/wallet/webhook/stripe",
                      headers={"stripe-signature": "t=1,v1=deadbeef"}, json={})
    assert res.status_code == 400

    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "rzp_test")
    res = client.post("/api/wallet/webhook/razorpay",
                      headers={"x-razorpay-signature": "nonsense"}, json={})
    assert res.status_code == 400


def test_razorpay_webhook_credits_once_with_a_valid_signature(client, account, monkeypatch):
    """The whole point of the ledger: a retried webhook must not pay twice."""
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "rzp_secret")
    tenant = account["client"]
    import database
    with database.SessionLocal() as db:
        cid = db.query(main.models.DBClient).filter(
            main.models.DBClient.email == account["email"]
        ).first().id
        order = main.models.DBTopUpOrder(
            client_id=cid, provider="razorpay", amount_minor=5000,
            currency="GBP", status="pending", provider_order_id="order_TEST123",
        )
        db.add(order)
        db.commit()

    body = json.dumps({
        "event": "payment.captured",
        "payload": {"payment": {"entity": {
            "id": "pay_TEST", "order_id": "order_TEST123", "amount": 5000,
        }}},
    }).encode()
    sig = hmac.new(b"rzp_secret", body, hashlib.sha256).hexdigest()

    first = client.post("/api/wallet/webhook/razorpay", content=body,
                        headers={"x-razorpay-signature": sig,
                                 "content-type": "application/json"})
    assert first.status_code == 200
    assert first.json()["credited"] is True

    # Gateways retry; the second delivery must be a no-op.
    second = client.post("/api/wallet/webhook/razorpay", content=body,
                         headers={"x-razorpay-signature": sig,
                                  "content-type": "application/json"})
    assert second.status_code == 200
    assert second.json()["credited"] is False

    tenant.post("/api/client/login", json={"email": account["email"], "password": account["password"]})
    assert tenant.get("/api/wallet").json()["balance"] == 50.0


def test_razorpay_underpayment_is_not_credited(client, account, monkeypatch):
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "rzp_secret")
    import database
    with database.SessionLocal() as db:
        cid = db.query(main.models.DBClient).filter(
            main.models.DBClient.email == account["email"]
        ).first().id
        db.add(main.models.DBTopUpOrder(
            client_id=cid, provider="razorpay", amount_minor=10000,
            currency="GBP", status="pending", provider_order_id="order_SHORT",
        ))
        db.commit()

    body = json.dumps({
        "event": "payment.captured",
        "payload": {"payment": {"entity": {
            "id": "pay_SHORT", "order_id": "order_SHORT", "amount": 100,
        }}},
    }).encode()
    sig = hmac.new(b"rzp_secret", body, hashlib.sha256).hexdigest()
    res = client.post("/api/wallet/webhook/razorpay", content=body,
                      headers={"x-razorpay-signature": sig,
                               "content-type": "application/json"})
    assert res.json().get("ignored") == "amount mismatch"


def test_stripe_replayed_webhook_is_refused(client, monkeypatch):
    """An old captured webhook must not work later."""
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    body = json.dumps({"type": "checkout.session.completed"}).encode()
    old = str(int(time.time()) - 4000)
    sig = hmac.new(b"whsec_test", f"{old}.".encode() + body, hashlib.sha256).hexdigest()
    res = client.post("/api/wallet/webhook/stripe", content=body,
                      headers={"stripe-signature": f"t={old},v1={sig}",
                               "content-type": "application/json"})
    assert res.status_code == 400


# --- operator reporting -----------------------------------------------------

def test_revenue_report(superadmin):
    cid = superadmin.get("/api/superadmin/clients").json()[0]["id"]
    superadmin.post(f"/api/superadmin/wallets/{cid}/adjust", json={"amount": 30, "reason": "seed"})
    data = superadmin.get("/api/superadmin/revenue").json()
    for key in ("total_topped_up", "total_consumed", "outstanding_liability", "months", "by_action"):
        assert key in data
    assert data["outstanding_liability"] >= 0


def test_gateway_readiness_is_visible_to_the_operator(superadmin):
    data = superadmin.get("/api/superadmin/gateways").json()
    keys = {p["key"] for p in data["providers"]}
    assert keys == {"stripe", "razorpay", "paypal"}
    stripe = next(p for p in data["providers"] if p["key"] == "stripe")
    assert "STRIPE_SECRET_KEY" in stripe["required_env"]


def test_wallet_is_tenant_scoped(client, account, superadmin):
    cid = client_id_for(superadmin, account["email"])
    superadmin.post(f"/api/superadmin/wallets/{cid}/adjust", json={"amount": 40, "reason": "seed"})
    superadmin.post("/api/superadmin/logout")

    client.post("/api/client/register", json={"email": "other-wallet@example.com", "password": "Passw0rdTest"})
    client.post("/api/client/login", json={"email": "other-wallet@example.com", "password": "Passw0rdTest"})
    assert client.get("/api/wallet").json()["balance"] == 0.0
    assert client.get("/api/wallet/transactions").json() == []
