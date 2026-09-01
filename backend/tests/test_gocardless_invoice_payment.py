"""Paying an invoice by bank debit.

A card payment is done when the customer comes back. A Direct Debit is not:
they have authorised it, and the money moves days later. So the rule this
whole path turns on is that returning from GoCardless settles nothing - only
a confirmed payment on the webhook marks the invoice paid.

Getting that wrong looks harmless and is not: the invoice reads Paid, chasing
stops, and the money may never arrive.

The second rule is where the money lands. GoCardless runs on the operator's
own account, so it can only be offered when invoice money is meant to arrive
there. Offering it in direct mode would take a customer's payment into the
wrong account entirely.
"""
import hashlib
import hmac
import json

import pytest

import main
import models
from conftest import make_invoice


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


def set_mode(value):
    with main.SessionLocal() as db:
        row = db.query(models.DBSettings).filter(
            models.DBSettings.key == main.COLLECTION_SETTING,
            models.DBSettings.client_id == None,        # noqa: E711
        ).first()
        was = row.value if row else None
        if row:
            row.value = value
        else:
            db.add(models.DBSettings(key=main.COLLECTION_SETTING,
                                     client_id=None, value=value))
        db.commit()
        return was


@pytest.fixture
def platform_mode(monkeypatch):
    """The arrangement GoCardless belongs to, said rather than inherited."""
    monkeypatch.setenv("GOCARDLESS_ACCESS_TOKEN", "gc_test_token")
    main.gateway_config.cache_clear() if hasattr(main.gateway_config, "cache_clear") else None
    was = set_mode("platform")
    yield
    set_mode(was or "direct")


def payable(tenant, **over):
    return make_invoice(tenant, status="Awaiting Payment", **over)


def tracking_of(tenant, inv):
    me = tenant.get("/api/client/me").json()
    with main.SessionLocal() as db:
        return db.query(models.DBInvoice).filter(
            models.DBInvoice.number == inv["number"],
            models.DBInvoice.client_id == me["id"]).first().tracking_id


def invoice_by_tracking(tracking):
    with main.SessionLocal() as db:
        row = db.query(models.DBInvoice).filter(
            models.DBInvoice.tracking_id == tracking).first()
        return {"id": row.id, "status": row.status,
                "due": float(row.due or 0), "paid": float(row.paid or 0)}


# --- when it is offered ------------------------------------------------------
def test_bank_payment_is_offered_when_the_platform_collects(tenant, platform_mode):
    inv = payable(tenant, currency="GBP")
    got = tenant.get(f"/api/public/invoices/{tracking_of(tenant, inv)}/pay/methods").json()
    assert "gocardless" in [m["provider"] for m in got["methods"]], got["methods"]


def test_it_is_not_offered_when_businesses_collect_for_themselves(tenant, monkeypatch):
    """The operator's own GoCardless account would take the money, while the
    business is expecting it in theirs."""
    monkeypatch.setenv("GOCARDLESS_ACCESS_TOKEN", "gc_test_token")
    was = set_mode("direct")
    try:
        inv = payable(tenant, currency="GBP")
        got = tenant.get(f"/api/public/invoices/{tracking_of(tenant, inv)}/pay/methods").json()
        assert "gocardless" not in [m["provider"] for m in got["methods"]]
    finally:
        set_mode(was or "direct")


def test_a_currency_gocardless_cannot_debit_is_not_offered(tenant, platform_mode):
    """INR is not a bank-debit currency here, and a button that always fails
    is worse than no button."""
    inv = payable(tenant, currency="INR")
    got = tenant.get(f"/api/public/invoices/{tracking_of(tenant, inv)}/pay/methods").json()
    assert "gocardless" not in [m["provider"] for m in got["methods"]]


def test_starting_it_in_direct_mode_is_refused(tenant, monkeypatch):
    monkeypatch.setenv("GOCARDLESS_ACCESS_TOKEN", "gc_test_token")
    was = set_mode("direct")
    try:
        inv = payable(tenant, currency="GBP")
        res = tenant.post(
            f"/api/public/invoices/{tracking_of(tenant, inv)}/pay/gocardless/start")
        assert res.status_code == 503, res.text
    finally:
        set_mode(was or "direct")


# --- the webhook is what settles it -------------------------------------------
def post_event(tenant, action, invoice_id, payment_id="PM123"):
    body = json.dumps({"events": [{
        "resource_type": "payments", "action": action,
        "links": {"payment": payment_id},
        "metadata": {"invoice_id": str(invoice_id)},
    }]}).encode()
    secret = main.gateway_config()["gocardless"]["webhook_secret"]
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return tenant.post("/api/wallet/webhook/gocardless", content=body,
                       headers={"webhook-signature": signature,
                                "Content-Type": "application/json"})


@pytest.fixture
def webhook_ready(monkeypatch):
    monkeypatch.setenv("GOCARDLESS_WEBHOOK_SECRET", "whsec_test")
    yield


def test_a_confirmed_payment_settles_the_invoice(tenant, platform_mode, webhook_ready):
    inv = payable(tenant, currency="GBP")
    tracking = tracking_of(tenant, inv)
    row = invoice_by_tracking(tracking)

    res = post_event(tenant, "confirmed", row["id"])
    assert res.status_code == 200, res.text
    assert invoice_by_tracking(tracking)["status"] == "Paid"


def test_an_authorised_but_uncleared_debit_leaves_it_outstanding(
        tenant, platform_mode, webhook_ready):
    """The whole point. The payer has agreed; the money has not moved. An
    invoice reading Paid here would stop anyone chasing it."""
    inv = payable(tenant, currency="GBP")
    tracking = tracking_of(tenant, inv)
    row = invoice_by_tracking(tracking)

    post_event(tenant, "submitted", row["id"])
    after = invoice_by_tracking(tracking)
    assert after["status"] != "Paid", after
    assert after["due"] == row["due"]


def test_a_failed_debit_does_not_mark_it_paid(tenant, platform_mode, webhook_ready):
    inv = payable(tenant, currency="GBP")
    tracking = tracking_of(tenant, inv)
    row = invoice_by_tracking(tracking)

    post_event(tenant, "failed", row["id"])
    assert invoice_by_tracking(tracking)["status"] != "Paid"


def test_the_same_confirmation_twice_only_pays_once(tenant, platform_mode, webhook_ready):
    """GoCardless retries a webhook it did not get an answer to."""
    inv = payable(tenant, currency="GBP")
    tracking = tracking_of(tenant, inv)
    row = invoice_by_tracking(tracking)

    post_event(tenant, "confirmed", row["id"])
    first = invoice_by_tracking(tracking)
    post_event(tenant, "confirmed", row["id"])
    second = invoice_by_tracking(tracking)
    assert first["paid"] == second["paid"], (first, second)


def test_an_unsigned_webhook_is_refused(tenant, platform_mode, webhook_ready):
    """Anyone can post to this URL - the signature is what makes it true."""
    inv = payable(tenant, currency="GBP")
    tracking = tracking_of(tenant, inv)
    row = invoice_by_tracking(tracking)

    body = json.dumps({"events": [{
        "resource_type": "payments", "action": "confirmed",
        "links": {"payment": "PM1"},
        "metadata": {"invoice_id": str(row["id"])},
    }]}).encode()
    res = tenant.post("/api/wallet/webhook/gocardless", content=body,
                      headers={"webhook-signature": "not-the-signature",
                               "Content-Type": "application/json"})
    assert res.status_code == 400
    assert invoice_by_tracking(tracking)["status"] != "Paid"


def test_an_invoice_we_do_not_have_is_noted_not_crashed(
        tenant, platform_mode, webhook_ready):
    res = post_event(tenant, "confirmed", 99999999)
    assert res.status_code == 200
    assert res.json()["events"][0]["result"] == "unknown invoice"


def test_wallet_topups_still_go_through_the_same_webhook(
        tenant, platform_mode, webhook_ready):
    """The two share this endpoint, so an event with no invoice id must still
    reach the wallet path rather than being swallowed."""
    body = json.dumps({"events": [{
        "resource_type": "payments", "action": "confirmed",
        "links": {"payment": "PM-unknown-order"},
        "metadata": {"order_id": "99999999"},
    }]}).encode()
    secret = main.gateway_config()["gocardless"]["webhook_secret"]
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    res = tenant.post("/api/wallet/webhook/gocardless", content=body,
                      headers={"webhook-signature": signature,
                               "Content-Type": "application/json"})
    assert res.status_code == 200
    assert res.json()["events"][0]["result"] == "unknown order"
