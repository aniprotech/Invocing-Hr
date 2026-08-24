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
def collections(monkeypatch):
    """Stand in for GoCardless, recording what it was asked to collect.

    Collection is by bank debit now, so the job asks for money and stops. The
    webhook is what credits, once the bank confirms - which is why these tests
    check the wallet does NOT move here.
    """
    seen = []

    class FakeResponse:
        status_code = 201

        @staticmethod
        def json():
            return {"payments": {"id": f"PM{len(seen)}"}}

    def fake_post(url, json=None, headers=None, timeout=None):
        seen.append({
            "amount_minor": json["payments"]["amount"],
            "currency": json["payments"]["currency"],
            "mandate": json["payments"]["links"]["mandate"],
            # The key GoCardless dedupes on, so a job run twice cannot collect
            # twice from a bank account.
            "idempotency_key": (headers or {}).get("Idempotency-Key", ""),
        })
        return FakeResponse()

    monkeypatch.setenv("GOCARDLESS_ACCESS_TOKEN", "sandbox_token")
    monkeypatch.setattr(main.httpx, "post", fake_post)
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
                 max_amount_minor=0, status="active", provider="razorpay"):
    """A standing permission, as the authorisation endpoint would leave it."""
    with main.SessionLocal() as db:
        m = models.DBPaymentMandate(
            client_id=client_id_of(account), payer_type=payer_type,
            payer_ref=payer_ref, token_id="token_abc", customer_id="cust_abc",
            method="card", masked="1111", currency="INR",
            provider=provider,
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


def test_a_low_wallet_asks_for_a_top_up(tenant, account, collections):
    give_mandate(account, payer_type="tenant", payer_ref="", provider="gocardless")
    set_wallet(account, balance_minor=100, threshold_minor=500, amount_minor=2000)

    assert run_topup_job()["requested"] == 1
    assert collections[0]["amount_minor"] == 2000


def test_the_job_does_not_credit_anything_itself(tenant, account, collections):
    """The heart of it. A bank debit that has been requested is not one that
    has been paid - it can still fail days later for want of funds. Crediting
    here would hand a tenant balance that never arrived."""
    give_mandate(account, payer_type="tenant", payer_ref="", provider="gocardless")
    set_wallet(account, balance_minor=100, threshold_minor=500, amount_minor=2000)

    before = tenant.get("/api/wallet").json()["balance"]
    run_topup_job()
    assert tenant.get("/api/wallet").json()["balance"] == before


def test_the_collection_is_left_pending_for_the_webhook(tenant, account, collections):
    give_mandate(account, payer_type="tenant", payer_ref="", provider="gocardless")
    set_wallet(account, balance_minor=100, threshold_minor=500, amount_minor=2000)
    run_topup_job()

    with main.SessionLocal() as db:
        order = db.query(models.DBTopUpOrder).filter(
            models.DBTopUpOrder.client_id == client_id_of(account)).first()
    assert order.provider == "gocardless"
    assert order.status == "pending"
    assert order.credited is False


def test_a_healthy_wallet_is_left_alone(tenant, account, collections):
    give_mandate(account, payer_type="tenant", payer_ref="", provider="gocardless")
    set_wallet(account, balance_minor=5000, threshold_minor=500, amount_minor=2000)
    assert run_topup_job()["requested"] == 0
    assert collections == []


def test_it_does_not_collect_twice_in_a_day(tenant, account, collections):
    """A wallet still below its threshold must not be collected from on every
    run - and the idempotency key is the second belt, so even a retry that got
    through would be deduped by GoCardless."""
    give_mandate(account, payer_type="tenant", payer_ref="", provider="gocardless")
    set_wallet(account, balance_minor=0, threshold_minor=500, amount_minor=100)

    assert run_topup_job()["requested"] == 1
    assert run_topup_job()["requested"] == 0
    assert len(collections) == 1
    assert collections[0]["idempotency_key"]


def test_it_is_off_until_somebody_turns_it_on(tenant, account, collections):
    give_mandate(account, payer_type="tenant", payer_ref="", provider="gocardless")
    set_wallet(account, balance_minor=0, threshold_minor=500, amount_minor=2000,
               enabled=False)
    assert run_topup_job()["requested"] == 0


def test_a_mandate_from_a_gateway_we_no_longer_use_is_not_collected(
        tenant, account, collections):
    """Bank debit is the only way money is taken now. An old card mandate
    cannot be used, and that has to be visible rather than look like nothing
    was due."""
    give_mandate(account, payer_type="tenant", payer_ref="", provider="razorpay")
    set_wallet(account, balance_minor=0, threshold_minor=500, amount_minor=2000)

    result = run_topup_job()
    assert result["requested"] == 0
    assert result["failed"] == 1
    assert collections == []
