"""Topping the wallet up by bank debit.

GoCardless is the only way a tenant pays now, and it is bank debit rather than
a card. That difference is the whole reason this file is careful: a submitted
Direct Debit can still fail days later for want of funds, so credit is added
when the money is confirmed and not a moment earlier. Crediting on submission
would mean a tenant spending a balance that never arrived.
"""
import hashlib
import hmac
import json

import pytest

import database
import main
import models


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("GOCARDLESS_ACCESS_TOKEN", "sandbox_token")
    monkeypatch.setenv("GOCARDLESS_WEBHOOK_SECRET", "whsec")
    monkeypatch.setenv("GOCARDLESS_ENVIRONMENT", "sandbox")
    yield


@pytest.fixture
def operator_client(client):
    """A signed-in operator. The gateway panel is theirs alone - a tenant
    has no business knowing which keys the platform holds."""
    main.rate_limiter._hits.clear()
    res = client.post("/api/superadmin/login", json={
        "identifier": "hello@keyroutes.co", "password": "TestSuper123"})
    assert res.status_code == 200, res.text
    return client


def signed(body: dict, secret="whsec"):
    raw = json.dumps(body).encode()
    sig = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return raw, {"Webhook-Signature": sig, "Content-Type": "application/json"}


def make_order(tenant, amount_minor=5000, status="pending"):
    cid = tenant.get("/api/client/me").json()["id"]
    with database.SessionLocal() as db:
        o = models.DBTopUpOrder(
            client_id=cid, provider="gocardless", amount_minor=amount_minor,
            currency="GBP", status=status, provider_order_id="BRQ123")
        db.add(o)
        db.commit()
        return o.id


def balance(tenant):
    return tenant.get("/api/wallet").json()["balance"]


def order_row(order_id):
    with database.SessionLocal() as db:
        return db.query(models.DBTopUpOrder).filter(
            models.DBTopUpOrder.id == order_id).first()


def event(action, order_id, resource="payments"):
    return {"events": [{
        "resource_type": resource, "action": action,
        "links": {"payment": "PM123", "billing_request": "BRQ123"},
        "metadata": {"order_id": str(order_id)},
    }]}


# --- what is offered -------------------------------------------------------

def test_gocardless_is_the_only_way_to_pay(tenant, configured):
    body = tenant.get("/api/wallet/providers").json()
    assert [p["key"] for p in body["providers"]] == ["gocardless"]


def test_the_card_gateways_are_not_offered(tenant, configured):
    keys = [p["key"] for p in tenant.get("/api/wallet/providers").json()["providers"]]
    for gone in ("stripe", "razorpay", "paypal"):
        assert gone not in keys


def test_a_card_provider_is_refused_outright(tenant, configured):
    """A tab left open on the old screen must not still start a card payment."""
    res = tenant.post("/api/wallet/topup", json={"amount": 25, "provider": "stripe"})
    assert res.status_code == 400


def test_a_currency_with_no_scheme_says_so(tenant, configured):
    """Bank debit runs on schemes - BACS, SEPA, ACH. A currency without one
    cannot be collected, and saying that beats failing at the gateway."""
    assert main.provider_takes_currency("gocardless", "INR") is False
    why = main.why_not_available("gocardless", "INR", configured=True)
    assert "bank debit" in why.lower()


def test_the_supported_currencies_are_taken(configured):
    for code in ("GBP", "EUR", "USD", "AUD"):
        assert main.provider_takes_currency("gocardless", code) is True


# --- the webhook, which is the only thing that moves money ------------------

def test_a_confirmed_payment_credits_the_wallet(tenant, configured):
    before = balance(tenant)
    order_id = make_order(tenant, 5000)
    raw, headers = signed(event("confirmed", order_id))

    res = tenant.post("/api/wallet/webhook/gocardless", content=raw, headers=headers)
    assert res.status_code == 200, res.text
    assert balance(tenant) == before + 50.0


def test_a_submitted_payment_credits_nothing(tenant, configured):
    """The point of the whole design. Submitted is not settled - a Direct
    Debit can still bounce days later."""
    before = balance(tenant)
    order_id = make_order(tenant, 5000)
    raw, headers = signed(event("submitted", order_id))

    tenant.post("/api/wallet/webhook/gocardless", content=raw, headers=headers)
    assert balance(tenant) == before
    assert order_row(order_id).credited is False


def test_a_failed_payment_credits_nothing_and_is_marked(tenant, configured):
    before = balance(tenant)
    order_id = make_order(tenant, 5000)
    raw, headers = signed(event("failed", order_id))

    tenant.post("/api/wallet/webhook/gocardless", content=raw, headers=headers)
    assert balance(tenant) == before
    assert order_row(order_id).status == "failed"


def test_the_same_payment_cannot_credit_twice(tenant, configured):
    """GoCardless retries webhooks. Twice delivered must not be twice paid."""
    before = balance(tenant)
    order_id = make_order(tenant, 5000)
    raw, headers = signed(event("confirmed", order_id))

    tenant.post("/api/wallet/webhook/gocardless", content=raw, headers=headers)
    tenant.post("/api/wallet/webhook/gocardless", content=raw, headers=headers)
    assert balance(tenant) == before + 50.0


def test_a_chargeback_does_not_silently_reverse_a_credit(tenant, configured):
    """Money already spent is an operator decision, not a webhook's."""
    order_id = make_order(tenant, 5000)
    raw, headers = signed(event("confirmed", order_id))
    tenant.post("/api/wallet/webhook/gocardless", content=raw, headers=headers)
    after_credit = balance(tenant)

    raw2, headers2 = signed(event("charged_back", order_id))
    tenant.post("/api/wallet/webhook/gocardless", content=raw2, headers=headers2)
    assert balance(tenant) == after_credit


# --- nobody may credit their own wallet ------------------------------------

def test_an_unsigned_webhook_is_refused(tenant, configured):
    order_id = make_order(tenant, 5000)
    before = balance(tenant)
    body = json.dumps(event("confirmed", order_id)).encode()

    res = tenant.post("/api/wallet/webhook/gocardless", content=body,
                      headers={"Content-Type": "application/json"})
    assert res.status_code == 400
    assert balance(tenant) == before


def test_a_wrongly_signed_webhook_is_refused(tenant, configured):
    order_id = make_order(tenant, 5000)
    before = balance(tenant)
    raw, headers = signed(event("confirmed", order_id), secret="not-the-secret")

    res = tenant.post("/api/wallet/webhook/gocardless", content=raw, headers=headers)
    assert res.status_code == 400
    assert balance(tenant) == before


def test_without_a_configured_secret_nothing_is_accepted(tenant, monkeypatch):
    """An unverifiable webhook is worse than none: it would let anyone who
    found the URL credit themselves."""
    monkeypatch.delenv("GOCARDLESS_WEBHOOK_SECRET", raising=False)
    order_id = make_order(tenant, 5000)
    raw, headers = signed(event("confirmed", order_id))

    res = tenant.post("/api/wallet/webhook/gocardless", content=raw, headers=headers)
    assert res.status_code == 503


def test_an_event_for_an_unknown_order_is_ignored_not_crashed(tenant, configured):
    raw, headers = signed(event("confirmed", 999999))
    res = tenant.post("/api/wallet/webhook/gocardless", content=raw, headers=headers)
    assert res.status_code == 200


# --- what the operator panel shows -----------------------------------------

def test_the_gateway_list_names_gocardless_first(operator_client, configured):
    body = operator_client.get("/api/superadmin/gateways").json()
    keys = [p["key"] for p in body["providers"]]
    assert "gocardless" in keys
    assert keys[0] == "gocardless", "the way tenants actually pay should lead"


def test_the_two_that_take_money_are_marked_primary(operator_client, configured):
    """Five gateways listed as equals invites configuring one no screen uses."""
    rows = {p["key"]: p for p in
            operator_client.get("/api/superadmin/gateways").json()["providers"]}
    assert rows["gocardless"]["role"] == "primary"
    assert rows["razorpay"]["role"] == "primary"
    assert rows["stripe"]["role"] == "legacy"
    assert rows["paypal"]["role"] == "legacy"


def test_each_gateway_says_what_it_is_for(operator_client, configured):
    for row in operator_client.get("/api/superadmin/gateways").json()["providers"]:
        assert row["used_for"], f"{row['key']} does not say what it is for"


def test_the_panel_reports_whether_the_webhook_can_be_verified(operator_client,
                                                               monkeypatch):
    """A token that works with no webhook secret is the quiet failure: money
    is taken and never credited, because the only thing that adds balance
    refuses unverified messages."""
    monkeypatch.setenv("GOCARDLESS_ACCESS_TOKEN", "tok")
    monkeypatch.delenv("GOCARDLESS_WEBHOOK_SECRET", raising=False)
    rows = {p["key"]: p for p in
            operator_client.get("/api/superadmin/gateways").json()["providers"]}
    assert rows["gocardless"]["enabled"] is True
    assert rows["gocardless"]["webhook_ready"] is False


def test_the_credential_check_is_operator_only(client):
    assert client.get("/api/superadmin/gocardless-check").status_code == 401


def test_the_check_says_so_when_there_is_no_token(operator_client, monkeypatch):
    monkeypatch.delenv("GOCARDLESS_ACCESS_TOKEN", raising=False)
    body = operator_client.get("/api/superadmin/gocardless-check").json()
    assert body["ok"] is False
    assert body["reason"] == "no_token"
