"""Paying an invoice by card, and refusing to believe the browser.

A business could save and activate Stripe keys on the settings screen and see
them listed as active, while no customer could ever pay with them: every
invoice payment path was Razorpay only. The settings promised a method that
did not exist.

The rule worth guarding hardest is the one that costs money when it is wrong.
The browser comes back from Stripe claiming it paid; anyone can post that.
So the session is fetched from Stripe with the secret key and has to be paid,
raised against THIS invoice, and for at least what is owed. Drop the middle
check and a genuine one-pound session settles a thousand-pound invoice.
"""
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
    """The routing mode is platform-wide and outlives whichever test set it.

    In platform mode every payment goes through the operator's own Razorpay
    account and a tenant's Stripe keys are ignored on purpose, so these tests
    say which arrangement they are about rather than inheriting one.
    """
    with main.SessionLocal() as db:
        row = db.query(models.DBSettings).filter(
            models.DBSettings.key == main.COLLECTION_SETTING,
            models.DBSettings.client_id == None,        # noqa: E711
        ).first()
        was = row.value if row else None
        if row:
            row.value = "direct"
            db.commit()
    yield
    if was is not None:
        with main.SessionLocal() as db:
            row = db.query(models.DBSettings).filter(
                models.DBSettings.key == main.COLLECTION_SETTING,
                models.DBSettings.client_id == None,    # noqa: E711
            ).first()
            if row:
                row.value = was
                db.commit()


def enable_stripe(tenant, secret="sk_test_x", public="pk_test_x"):
    res = tenant.put("/api/payment-gateways/stripe", json={
        "public_key": public, "secret_key": secret, "is_active": True})
    assert res.status_code == 200, res.text


def invoice_row(number, client_id):
    with main.SessionLocal() as db:
        return db.query(models.DBInvoice).filter(
            models.DBInvoice.number == number,
            models.DBInvoice.client_id == client_id).first()


def tracking_of(tenant, inv):
    me = tenant.get("/api/client/me").json()
    return invoice_row(inv["number"], me["id"]).tracking_id


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self._payload


# --- what the page is told ----------------------------------------------------
def test_a_business_with_nothing_set_up_is_offered_nothing(tenant):
    inv = make_invoice(tenant, status="Awaiting Payment")
    got = tenant.get(f"/api/public/invoices/{tracking_of(tenant, inv)}/pay/methods").json()
    assert got["methods"] == [], got["methods"]


def test_activating_stripe_makes_it_offered(tenant):
    """The gap this whole change closes: active in settings, absent to the
    customer."""
    inv = make_invoice(tenant, status="Awaiting Payment")
    enable_stripe(tenant)
    got = tenant.get(f"/api/public/invoices/{tracking_of(tenant, inv)}/pay/methods").json()
    assert [m["provider"] for m in got["methods"]] == ["stripe"], got["methods"]


def test_the_offer_never_carries_a_key(tenant):
    """It is a public endpoint - no key of any kind belongs in the answer."""
    inv = make_invoice(tenant, status="Awaiting Payment")
    enable_stripe(tenant, secret="sk_test_supersecret", public="pk_test_public")
    raw = tenant.get(f"/api/public/invoices/{tracking_of(tenant, inv)}/pay/methods").text
    assert "sk_test_supersecret" not in raw
    assert "pk_test_public" not in raw


def test_a_paid_invoice_is_offered_nothing(tenant):
    inv = make_invoice(tenant, status="Awaiting Payment")
    enable_stripe(tenant)
    tracking = tracking_of(tenant, inv)
    with main.SessionLocal() as db:
        row = db.query(models.DBInvoice).filter(
            models.DBInvoice.tracking_id == tracking).first()
        row.status, row.due, row.paid = "Paid", 0, 100
        db.commit()
    got = tenant.get(f"/api/public/invoices/{tracking}/pay/methods").json()
    assert got["is_paid"] is True
    assert got["methods"] == []


# --- minor units ---------------------------------------------------------------
def test_ordinary_currencies_are_sent_in_pence():
    assert main.to_minor_units(12.34, "GBP") == 1234


def test_a_currency_with_no_smaller_unit_is_not_multiplied():
    """Yen has no subunit - times a hundred would charge a hundredfold."""
    assert main.to_minor_units(1200, "JPY") == 1200


# --- refusing the browser's word -----------------------------------------------
def confirm(tenant, tracking, session_payload, body=None, status=200):
    """Confirm a payment with Stripe's answer stubbed to session_payload."""
    calls = {}

    def fake_get(url, **kw):
        calls["url"] = url
        return FakeResponse(session_payload, status)

    original = main.httpx.get
    main.httpx.get = fake_get
    try:
        return tenant.post(f"/api/public/invoices/{tracking}/pay/stripe/confirm",
                           json=body or {"session_id": "cs_test_1"}), calls
    finally:
        main.httpx.get = original


def paid_session(tracking, amount_minor, **over):
    base = {"payment_status": "paid", "client_reference_id": tracking,
            "amount_total": amount_minor, "payment_intent": "pi_test_1"}
    base.update(over)
    return base


def test_a_verified_payment_settles_the_invoice(tenant):
    inv = make_invoice(tenant, status="Awaiting Payment")
    enable_stripe(tenant)
    tracking = tracking_of(tenant, inv)
    due = tenant.get(f"/api/public/invoices/{tracking}/pay/methods").json()["amount_due"]

    res, _ = confirm(tenant, tracking, paid_session(tracking, int(round(due * 100))))
    assert res.status_code == 200, res.text
    assert res.json()["paid"] is True
    assert res.json()["status"] == "Paid"


def test_a_session_for_another_invoice_is_refused(tenant):
    """A genuine session, genuinely paid, for a different and cheaper invoice.
    Without the reference check this settles whatever it is pointed at."""
    inv = make_invoice(tenant, status="Awaiting Payment")
    enable_stripe(tenant)
    tracking = tracking_of(tenant, inv)
    due = tenant.get(f"/api/public/invoices/{tracking}/pay/methods").json()["amount_due"]

    session = paid_session("some-other-invoice", int(round(due * 100)))
    res, _ = confirm(tenant, tracking, session)
    assert res.status_code == 400, res.text
    assert res.json()["detail"] == "That payment could not be verified"


def test_a_session_short_of_the_amount_is_refused(tenant):
    inv = make_invoice(tenant, status="Awaiting Payment")
    enable_stripe(tenant)
    tracking = tracking_of(tenant, inv)

    res, _ = confirm(tenant, tracking, paid_session(tracking, 1))
    assert res.status_code == 400
    assert res.json()["detail"] == "That payment could not be verified"


def test_an_unpaid_session_is_refused(tenant):
    inv = make_invoice(tenant, status="Awaiting Payment")
    enable_stripe(tenant)
    tracking = tracking_of(tenant, inv)
    due = tenant.get(f"/api/public/invoices/{tracking}/pay/methods").json()["amount_due"]

    session = paid_session(tracking, int(round(due * 100)), payment_status="unpaid")
    res, _ = confirm(tenant, tracking, session)
    assert res.status_code == 400
    assert "not completed" in res.json()["detail"]


def test_the_claim_is_checked_against_stripe_not_taken_on_trust(tenant):
    """The session id is looked up at Stripe, not simply believed."""
    inv = make_invoice(tenant, status="Awaiting Payment")
    enable_stripe(tenant)
    tracking = tracking_of(tenant, inv)
    due = tenant.get(f"/api/public/invoices/{tracking}/pay/methods").json()["amount_due"]

    _res, calls = confirm(tenant, tracking, paid_session(tracking, int(round(due * 100))))
    assert "api.stripe.com" in calls["url"], calls
    assert "cs_test_1" in calls["url"], calls


def test_paying_twice_only_records_once(tenant):
    """A customer refreshing the return page must not double-credit."""
    inv = make_invoice(tenant, status="Awaiting Payment")
    enable_stripe(tenant)
    tracking = tracking_of(tenant, inv)
    due = tenant.get(f"/api/public/invoices/{tracking}/pay/methods").json()["amount_due"]
    session = paid_session(tracking, int(round(due * 100)))

    first, _ = confirm(tenant, tracking, session)
    second, _ = confirm(tenant, tracking, session)
    assert first.json()["already_recorded"] is False
    assert second.json()["already_recorded"] is True


def test_confirming_without_stripe_set_up_is_refused(tenant):
    inv = make_invoice(tenant, status="Awaiting Payment")
    tracking = tracking_of(tenant, inv)
    res = tenant.post(f"/api/public/invoices/{tracking}/pay/stripe/confirm",
                      json={"session_id": "cs_test_1"})
    assert res.status_code == 503


def test_a_session_id_is_required(tenant):
    inv = make_invoice(tenant, status="Awaiting Payment")
    enable_stripe(tenant)
    tracking = tracking_of(tenant, inv)
    res = tenant.post(f"/api/public/invoices/{tracking}/pay/stripe/confirm", json={})
    assert res.status_code == 400
