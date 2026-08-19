"""Charging somebody who is not there.

Two payers, one mechanism: a customer whose invoices are paid automatically,
and a business whose wallet tops itself up. Only the single HTTP call to the
gateway is untestable, so it is stubbed here and everything around it - who may
be charged, how much, and whether it has already happened - is checked for
real.

Most of these are about the charge that must NOT happen.
"""
import hashlib
import hmac
import uuid
from datetime import date, timedelta

import pytest

import main
import models
from conftest import make_invoice

SECRET = "tenant_secret_value"
KEY_ID = "rzp_test_key_id"


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


@pytest.fixture
def gateway(tenant):
    res = tenant.put("/api/payment-gateways/razorpay", json={
        "public_key": KEY_ID, "secret_key": SECRET, "is_active": True})
    assert res.status_code == 200, res.text


@pytest.fixture
def charges(monkeypatch):
    """Stand in for the gateway, recording what it was asked to take."""
    seen = []

    def fake(mandate, amount_minor, currency, description, key_id, key_secret):
        seen.append({"amount_minor": amount_minor, "currency": currency,
                     "description": description, "token": mandate.token_id})
        return f"pay_{len(seen)}", None

    monkeypatch.setattr(main, "charge_mandate", fake)
    return seen


@pytest.fixture
def refusing_gateway(monkeypatch):
    def fake(*a, **k):
        return None, "BAD_REQUEST_ERROR: token is not valid"
    monkeypatch.setattr(main, "charge_mandate", fake)


def client_id_of(account):
    with main.SessionLocal() as db:
        return db.query(models.DBClient).filter(
            models.DBClient.email == account["email"]).first().id


def give_mandate(account, payer_type="customer", payer_ref="Customer Ltd",
                 max_amount_minor=0, status="active"):
    """A standing permission, as the authorisation endpoint would leave it."""
    with main.SessionLocal() as db:
        m = models.DBPaymentMandate(
            client_id=client_id_of(account), payer_type=payer_type,
            payer_ref=payer_ref, token_id="token_abc", customer_id="cust_abc",
            method="card", masked="1111", currency="INR",
            max_amount_minor=max_amount_minor, status=status)
        db.add(m)
        db.commit()
        return m.id


def due_invoice(tenant, price=500.0, days_ago=1, contact="Customer Ltd"):
    due = date.today() - timedelta(days=days_ago)
    return make_invoice(
        tenant, contact=contact, status="Awaiting Payment", currency="INR",
        issue_date=(due - timedelta(days=14)).isoformat(),
        due_date=due.isoformat(),
        line_items=[{"description": "Work", "qty": 1, "price": price,
                     "tax_rate": "No Tax"}])


def run_invoice_job():
    with main.SessionLocal() as db:
        return main.job_invoice_autopay(db, main.datetime.now())


def run_topup_job():
    with main.SessionLocal() as db:
        return main.job_wallet_auto_topup(db, main.datetime.now())


# --- invoices that should be charged ------------------------------------------

def test_a_due_invoice_with_permission_is_paid(tenant, account, gateway, charges):
    inv = due_invoice(tenant)
    give_mandate(account)

    result = run_invoice_job()
    assert result["charged"] == 1
    assert charges[0]["amount_minor"] == 50000

    after = tenant.get(f"/api/invoices/{inv['number']}").json()
    assert after["status"] == "Paid"
    assert after["due"] == 0


def test_it_lands_in_the_ledger_like_any_other_payment(tenant, account, gateway, charges):
    inv = due_invoice(tenant)
    give_mandate(account)
    run_invoice_job()

    payments = tenant.get(f"/api/invoices/{inv['number']}").json()["payments"]
    assert len(payments) == 1
    assert payments[0]["method"] == "razorpay"
    assert "automatic" in payments[0].get("note", "").lower()


# --- invoices that must not be ------------------------------------------------

def test_without_permission_nothing_is_charged(tenant, account, gateway, charges):
    due_invoice(tenant)
    assert run_invoice_job()["charged"] == 0
    assert charges == []


def test_an_invoice_not_yet_due_is_left_alone(tenant, account, gateway, charges):
    due_invoice(tenant, days_ago=-7)      # falls due next week
    give_mandate(account)
    assert run_invoice_job()["charged"] == 0


def test_a_draft_is_never_charged(tenant, account, gateway, charges):
    """Nobody has agreed to a draft."""
    make_invoice(tenant, contact="Customer Ltd", status="Draft", currency="INR",
                 due_date=(date.today() - timedelta(days=2)).isoformat())
    give_mandate(account)
    assert run_invoice_job()["charged"] == 0


def test_a_cancelled_mandate_stops_it(tenant, account, gateway, charges):
    due_invoice(tenant)
    give_mandate(account, status="cancelled")
    assert run_invoice_job()["charged"] == 0


def test_a_ceiling_is_respected(tenant, account, gateway, charges):
    """"You may charge me" is not "you may charge me anything"."""
    due_invoice(tenant, price=500.0)
    give_mandate(account, max_amount_minor=10000)     # 100.00 ceiling
    assert run_invoice_job()["charged"] == 0
    assert charges == []


def test_a_different_customer_is_not_covered(tenant, account, gateway, charges):
    due_invoice(tenant, contact="Somebody Else Ltd")
    give_mandate(account, payer_ref="Customer Ltd")
    assert run_invoice_job()["charged"] == 0


def test_the_same_invoice_is_not_charged_twice(tenant, account, gateway, charges):
    due_invoice(tenant)
    give_mandate(account)
    assert run_invoice_job()["charged"] == 1
    assert run_invoice_job()["charged"] == 0, "the second run charged it again"
    assert len(charges) == 1


def test_a_failure_is_recorded_and_the_invoice_left_owing(tenant, account,
                                                          gateway, refusing_gateway):
    inv = due_invoice(tenant)
    give_mandate(account)

    result = run_invoice_job()
    assert result["charged"] == 0 and result["failed"] == 1

    after = tenant.get(f"/api/invoices/{inv['number']}").json()
    assert after["status"] != "Paid"
    assert after["due"] > 0

    with main.SessionLocal() as db:
        attempt = db.query(models.DBAutoCharge).filter(
            models.DBAutoCharge.client_id == client_id_of(account)).first()
        assert attempt.status == "failed"
        assert attempt.failure_reason


def test_a_rejected_token_stops_being_used(tenant, account, gateway, refusing_gateway):
    """Otherwise the same mandate fails against the gateway every night."""
    due_invoice(tenant)
    mid = give_mandate(account)
    run_invoice_job()

    with main.SessionLocal() as db:
        m = db.query(models.DBPaymentMandate).filter(
            models.DBPaymentMandate.id == mid).first()
        assert m.status == "failed"


# --- wallet topping itself up --------------------------------------------------

def set_wallet(account, balance_minor, threshold_minor, amount_minor, enabled=True):
    with main.SessionLocal() as db:
        w = main.get_wallet(db, client_id_of(account))
        w.balance_minor = balance_minor
        w.auto_topup_threshold_minor = threshold_minor
        w.auto_topup_amount_minor = amount_minor
        w.auto_topup_enabled = enabled
        db.commit()


def test_a_low_wallet_tops_itself_up(tenant, account, charges, monkeypatch):
    monkeypatch.setenv("RAZORPAY_KEY_ID", KEY_ID)
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", SECRET)
    give_mandate(account, payer_type="tenant", payer_ref="")
    set_wallet(account, balance_minor=100, threshold_minor=500, amount_minor=2000)

    assert run_topup_job()["topped_up"] == 1
    assert charges[0]["amount_minor"] == 2000

    balance = tenant.get("/api/wallet").json()["balance"]
    assert balance == 21.0      # 1.00 that was there, plus 20.00


def test_a_healthy_wallet_is_left_alone(tenant, account, charges, monkeypatch):
    monkeypatch.setenv("RAZORPAY_KEY_ID", KEY_ID)
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", SECRET)
    give_mandate(account, payer_type="tenant", payer_ref="")
    set_wallet(account, balance_minor=5000, threshold_minor=500, amount_minor=2000)
    assert run_topup_job()["topped_up"] == 0


def test_it_does_not_top_up_twice_in_a_day(tenant, account, charges, monkeypatch):
    """A wallet still below its threshold must not be charged on every run."""
    monkeypatch.setenv("RAZORPAY_KEY_ID", KEY_ID)
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", SECRET)
    give_mandate(account, payer_type="tenant", payer_ref="")
    set_wallet(account, balance_minor=0, threshold_minor=500, amount_minor=100)

    assert run_topup_job()["topped_up"] == 1
    assert run_topup_job()["topped_up"] == 0
    assert len(charges) == 1


def test_it_is_off_until_somebody_turns_it_on(tenant, account, charges, monkeypatch):
    monkeypatch.setenv("RAZORPAY_KEY_ID", KEY_ID)
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", SECRET)
    give_mandate(account, payer_type="tenant", payer_ref="")
    set_wallet(account, balance_minor=0, threshold_minor=500, amount_minor=2000,
               enabled=False)
    assert run_topup_job()["topped_up"] == 0


def test_turning_it_on_needs_permission_first(tenant):
    """Otherwise it is a setting that quietly does nothing."""
    res = tenant.put("/api/wallet/auto-topup",
                     json={"enabled": True, "threshold": 5, "amount": 20})
    assert res.status_code == 400
    assert "Authorise" in res.json()["detail"]


def test_turning_it_on_needs_an_amount(tenant, account):
    give_mandate(account, payer_type="tenant", payer_ref="")
    res = tenant.put("/api/wallet/auto-topup",
                     json={"enabled": True, "threshold": 5, "amount": 0})
    assert res.status_code == 400


def test_the_settings_round_trip(tenant, account):
    give_mandate(account, payer_type="tenant", payer_ref="")
    res = tenant.put("/api/wallet/auto-topup",
                     json={"enabled": True, "threshold": 5, "amount": 20})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["enabled"] is True
    assert body["threshold"] == 5.0
    assert body["amount"] == 20.0
    assert body["has_mandate"] is True


# --- who can see and stop them -------------------------------------------------

def test_a_business_sees_its_own_mandates(tenant, account):
    give_mandate(account, payer_ref="Customer Ltd")
    body = tenant.get("/api/autopay/mandates").json()
    assert [m["payer_ref"] for m in body["customers"]] == ["Customer Ltd"]


def test_cancelling_is_immediate(tenant, account, gateway, charges):
    due_invoice(tenant)
    mid = give_mandate(account)
    assert tenant.delete(f"/api/autopay/mandates/{mid}").status_code == 200
    assert run_invoice_job()["charged"] == 0


def test_one_business_cannot_cancel_another(client, tenant, account):
    mid = give_mandate(account)

    other = f"other-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/client/register", json={
        "email": other, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    main.rate_limiter._hits.clear()
    client.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})

    assert client.delete(f"/api/autopay/mandates/{mid}").status_code == 404
    assert client.get("/api/autopay/mandates").json()["customers"] == []


def test_authorising_needs_a_verified_payment(client, tenant, gateway):
    """A mandate is created from a payment the gateway signed, so agreeing is
    something the payer did at the checkout, not something anyone can post."""
    inv = due_invoice(tenant)
    tid = tenant.get(f"/api/invoices/{inv['number']}").json()["tracking_id"]

    res = client.post(f"/api/public/invoices/{tid}/autopay", json={
        "token_id": "token_x", "customer_id": "cust_x",
        "razorpay_order_id": "order_A", "razorpay_payment_id": "pay_B",
        "razorpay_signature": "not-a-real-signature"})
    assert res.status_code == 400
    assert "could not be verified" in res.json()["detail"]


def test_a_verified_authorisation_is_kept(client, tenant, gateway):
    inv = due_invoice(tenant)
    tid = tenant.get(f"/api/invoices/{inv['number']}").json()["tracking_id"]
    signature = hmac.new(SECRET.encode(), b"order_A|pay_B", hashlib.sha256).hexdigest()

    res = client.post(f"/api/public/invoices/{tid}/autopay", json={
        "token_id": "token_x", "customer_id": "cust_x", "method": "card",
        "masked": "4242", "max_amount": 1000,
        "razorpay_order_id": "order_A", "razorpay_payment_id": "pay_B",
        "razorpay_signature": signature})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "active"
    assert body["masked"] == "4242"
    assert body["max_amount"] == 1000.0
