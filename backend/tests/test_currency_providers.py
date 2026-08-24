"""Offering only what will actually take the money.

A GBP wallet was offered Razorpay, which takes INR, so the top-up got all the
way to the gateway before failing. Which provider suits which currency is
knowable in advance, so it is decided here rather than discovered there.
"""
import pytest

import main
import models


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


@pytest.fixture
def superadmin(client):
    main.rate_limiter._hits.clear()
    res = client.post("/api/superadmin/login", json={
        "identifier": "hello@keyroutes.co", "password": "TestSuper123",
    })
    assert res.status_code == 200, res.text
    return client


@pytest.fixture
def all_keys(monkeypatch):
    """Every provider configured, so only currency decides."""
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setenv("STRIPE_PUBLISHABLE_KEY", "pk_test_x")
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_x")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "pp_id")
    monkeypatch.setenv("PAYPAL_SECRET", "pp_secret")
    monkeypatch.setenv("GOCARDLESS_ACCESS_TOKEN", "gc_token")
    yield


def wallet_currency(account, code):
    with main.SessionLocal() as db:
        row = db.query(models.DBClient).filter(
            models.DBClient.email == account["email"]).first()
        w = main.get_wallet(db, row.id)
        w.currency = code
        db.commit()


def providers(tenant):
    res = tenant.get("/api/wallet/providers")
    assert res.status_code == 200, res.text
    return {p["key"]: p for p in res.json()["providers"]}


# --- which provider takes what ------------------------------------------------

def test_razorpay_takes_rupees_and_not_pounds():
    assert main.provider_takes_currency("razorpay", "INR") is True
    assert main.provider_takes_currency("razorpay", "GBP") is False


def test_paypal_takes_pounds_and_not_rupees():
    """PayPal publishes a fixed list of balance currencies; INR is not on it."""
    assert main.provider_takes_currency("paypal", "GBP") is True
    assert main.provider_takes_currency("paypal", "USD") is True
    assert main.provider_takes_currency("paypal", "INR") is False


def test_stripe_is_treated_as_open():
    for code in ("GBP", "USD", "INR", "AUD"):
        assert main.provider_takes_currency("stripe", code) is True


def test_the_currency_is_read_case_insensitively():
    assert main.provider_takes_currency("razorpay", "inr") is True
    assert main.provider_takes_currency("paypal", "gbp") is True


def test_an_unknown_provider_takes_nothing():
    assert main.provider_takes_currency("bitcoin", "GBP") is False


# --- what the top-up screen is told -------------------------------------------

def test_a_pounds_wallet_can_be_collected_by_bank_debit(tenant, account, all_keys):
    """GBP runs on Bacs, so this is the ordinary case."""
    wallet_currency(account, "GBP")
    rows = providers(tenant)
    assert rows["gocardless"]["enabled"] is True
    assert rows["gocardless"]["unavailable_because"] == ""


def test_only_bank_debit_is_offered(tenant, account, all_keys):
    """Every card gateway is configured here, so this is not about keys. They
    are simply not a way to pay any more."""
    rows = providers(tenant)
    assert set(rows) == {"gocardless"}


def test_a_rupees_wallet_cannot_be_collected(tenant, account, all_keys):
    """Bank debit runs on schemes - Bacs, SEPA, ACH - and there is none for
    INR. Saying so here beats failing at the gateway."""
    wallet_currency(account, "INR")
    rows = providers(tenant)
    assert rows["gocardless"]["enabled"] is False
    assert rows["gocardless"]["configured"] is True, "the token is set; the currency is the problem"
    assert "bank debit" in rows["gocardless"]["unavailable_because"].lower()


def test_the_two_reasons_are_told_apart(tenant, account, monkeypatch):
    """No key and wrong currency are fixed in completely different places."""
    monkeypatch.delenv("GOCARDLESS_ACCESS_TOKEN", raising=False)
    wallet_currency(account, "GBP")
    assert "not set up" in providers(tenant)["gocardless"]["unavailable_because"].lower()

    monkeypatch.setenv("GOCARDLESS_ACCESS_TOKEN", "gc_token")
    wallet_currency(account, "INR")
    assert "bank debit" in providers(tenant)["gocardless"]["unavailable_because"].lower()


def test_a_usable_provider_explains_nothing(tenant, account, all_keys):
    wallet_currency(account, "GBP")
    assert providers(tenant)["gocardless"]["unavailable_because"] == ""


def test_it_says_so_when_nothing_takes_the_currency(tenant, account, all_keys):
    wallet_currency(account, "INR")
    body = tenant.get("/api/wallet/providers").json()
    assert body["any_enabled"] is False
    assert "INR" in body["none_take_currency"]


def test_international_razorpay_opens_it_up(monkeypatch):
    """An account with international payments enabled can charge in others.
    Razorpay no longer takes new top-ups, but old orders still settle through
    this, so the rule still has to hold."""
    monkeypatch.setattr(main, "RAZORPAY_INTERNATIONAL", True)
    assert main.provider_takes_currency("razorpay", "GBP") is True


# --- and the server refuses it too --------------------------------------------

def test_starting_a_doomed_top_up_is_refused(tenant, account, all_keys):
    """A tab left open across a currency change would otherwise send somebody
    to a gateway certain to turn them away."""
    wallet_currency(account, "INR")
    res = tenant.post("/api/wallet/topup", json={"amount": 25, "provider": "gocardless"})
    assert res.status_code == 400
    assert "bank debit" in res.json()["detail"].lower()


def test_a_supported_pairing_gets_past_the_check(tenant, account, all_keys, monkeypatch):
    """It should fail at the gateway call, not at the currency check - which is
    how we know the guard let it through."""
    wallet_currency(account, "GBP")

    def boom(*a, **k):
        raise RuntimeError("no network in tests")

    monkeypatch.setattr(main.httpx, "post", boom)
    res = tenant.post("/api/wallet/topup", json={"amount": 25, "provider": "gocardless"})
    assert res.status_code == 502
    assert "bank debit" not in res.json()["detail"].lower()
