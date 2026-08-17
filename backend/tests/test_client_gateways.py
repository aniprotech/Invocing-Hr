"""A business collecting money into its own account.

Two separate things that must never be confused: the platform's keys, in the
environment, take wallet top-ups - money paid to us. These belong to the tenant
and take invoice payments - money paid to them.

The part that matters most is the verification. A browser saying "I paid" is
worth nothing; anyone can post that. Razorpay signs order|payment with a secret
only the two of us hold, and recomputing it here is what makes the claim true.
Everything below is about that boundary holding.
"""
import hashlib
import hmac
import uuid

import pytest

import main
import models
from conftest import make_invoice


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


SECRET = "rzp_test_secret_value"
KEY_ID = "rzp_test_key_id"


def set_up_gateway(tenant, public=KEY_ID, secret=SECRET, active=True):
    res = tenant.put("/api/payment-gateways/razorpay", json={
        "public_key": public, "secret_key": secret, "is_active": active})
    assert res.status_code == 200, res.text
    return res.json()


def link_for(tenant, number):
    res = tenant.get(f"/api/invoices/{number}")
    assert res.status_code == 200, res.text
    return res.json()["tracking_id"]


def issued(tenant, **kw):
    kw.setdefault("status", "Awaiting Payment")
    return make_invoice(tenant, **kw)


def sign(order_id, payment_id, secret=SECRET):
    return hmac.new(secret.encode(), f"{order_id}|{payment_id}".encode(),
                    hashlib.sha256).hexdigest()


# --- keeping the keys -------------------------------------------------------

def test_a_business_can_save_its_own_keys(tenant):
    saved = set_up_gateway(tenant)
    assert saved["provider"] == "razorpay"
    assert saved["public_key"] == KEY_ID
    assert saved["is_active"] is True


def test_the_secret_is_never_returned(tenant):
    """This endpoint is read by a browser."""
    set_up_gateway(tenant)
    body = tenant.get("/api/payment-gateways").json()
    rzp = next(g for g in body["gateways"] if g["provider"] == "razorpay")
    assert SECRET not in str(body)
    assert rzp["has_secret"] is True
    assert rzp["secret_key"].endswith(SECRET[-4:])
    assert rzp["secret_key"].startswith("*")


def test_saving_again_without_the_secret_keeps_the_old_one(tenant):
    """The browser only ever had a masked value. Sending it back must not
    overwrite the real key with asterisks."""
    set_up_gateway(tenant)
    tenant.put("/api/payment-gateways/razorpay",
               json={"public_key": "rzp_new_id", "secret_key": "************alue"})

    with main.SessionLocal() as db:
        row = db.query(models.DBClientGateway).filter(
            models.DBClientGateway.public_key == "rzp_new_id").first()
        assert row.secret_key == SECRET


def test_it_will_not_go_active_without_both_keys(tenant):
    res = tenant.put("/api/payment-gateways/razorpay",
                     json={"public_key": "only_the_public_half", "is_active": True})
    assert res.status_code == 400
    assert "Both keys" in res.json()["detail"]


def test_an_unknown_provider_is_refused(tenant):
    assert tenant.put("/api/payment-gateways/bitcoin",
                      json={"public_key": "x"}).status_code == 400


def test_keys_do_not_cross_between_businesses(client, tenant):
    set_up_gateway(tenant)

    other = f"other-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/client/register", json={
        "email": other, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    main.rate_limiter._hits.clear()
    client.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})

    body = client.get("/api/payment-gateways").json()
    assert SECRET not in str(body)
    assert all(not g["has_secret"] for g in body["gateways"])


# --- what the customer's page is told ----------------------------------------

def test_the_page_offers_payment_once_keys_are_set(client, tenant):
    inv = issued(tenant)
    tid = link_for(tenant, inv["number"])

    before = client.get(f"/api/public/invoices/{tid}").json()
    assert before["payment"] is None, "nothing to pay with yet"

    set_up_gateway(tenant)
    after = client.get(f"/api/public/invoices/{tid}").json()
    assert after["payment"]["provider"] == "razorpay"
    assert after["payment"]["key_id"] == KEY_ID


def test_the_page_never_carries_the_secret(client, tenant):
    set_up_gateway(tenant)
    inv = issued(tenant)
    body = client.get(f"/api/public/invoices/{link_for(tenant, inv['number'])}").text
    assert SECRET not in body


def test_a_settled_invoice_is_not_offered_for_payment(client, tenant):
    set_up_gateway(tenant)
    inv = issued(tenant)
    tid = link_for(tenant, inv["number"])
    tenant.post(f"/api/invoices/{inv['number']}/mark-paid")

    body = client.get(f"/api/public/invoices/{tid}").json()
    assert body["is_settled"] is True
    assert body["payment"] is None


# --- the verification boundary ------------------------------------------------

def pay(client, tid, order_id="order_ABC", payment_id="pay_XYZ", signature=None):
    return client.post(f"/api/public/invoices/{tid}/pay/razorpay/verify", json={
        "razorpay_order_id": order_id,
        "razorpay_payment_id": payment_id,
        "razorpay_signature": signature if signature is not None
        else sign(order_id, payment_id),
    })


def test_a_verified_payment_marks_the_invoice_paid(client, tenant):
    set_up_gateway(tenant)
    inv = issued(tenant)
    tid = link_for(tenant, inv["number"])

    res = pay(client, tid)
    assert res.status_code == 200, res.text
    assert res.json()["paid"] is True

    after = tenant.get(f"/api/invoices/{inv['number']}").json()
    assert after["status"] == "Paid"
    assert after["due"] == 0


def test_it_lands_in_the_ledger_as_a_receipt(client, tenant):
    """Not just a status change - the payment has to be explainable."""
    set_up_gateway(tenant)
    inv = issued(tenant)
    pay(client, link_for(tenant, inv["number"]), payment_id="pay_LEDGER")

    payments = tenant.get(f"/api/invoices/{inv['number']}").json()["payments"]
    assert len(payments) == 1
    assert payments[0]["method"] == "razorpay"
    assert payments[0]["reference"] == "pay_LEDGER"


def test_an_unsigned_claim_is_refused(client, tenant):
    """Anyone can post to this endpoint. Saying you paid is not paying."""
    set_up_gateway(tenant)
    inv = issued(tenant)
    tid = link_for(tenant, inv["number"])

    res = pay(client, tid, signature="not-a-real-signature")
    assert res.status_code == 400
    assert "could not be verified" in res.json()["detail"]

    after = tenant.get(f"/api/invoices/{inv['number']}").json()
    assert after["status"] != "Paid"
    assert after["due"] > 0


def test_a_signature_from_another_secret_is_refused(client, tenant):
    """The signature has to be from this business's key, not any key."""
    set_up_gateway(tenant)
    inv = issued(tenant)
    tid = link_for(tenant, inv["number"])

    res = pay(client, tid, signature=sign("order_ABC", "pay_XYZ", "somebody_elses_secret"))
    assert res.status_code == 400
    assert tenant.get(f"/api/invoices/{inv['number']}").json()["status"] != "Paid"


def test_tampering_with_the_amount_is_impossible(client, tenant):
    """The amount is taken from the invoice, never from the request, so there
    is nothing in the body worth editing."""
    set_up_gateway(tenant)
    inv = issued(tenant, line_items=[
        {"description": "Work", "qty": 1, "price": 500.0, "tax_rate": "No Tax"}])
    tid = link_for(tenant, inv["number"])

    res = client.post(f"/api/public/invoices/{tid}/pay/razorpay/verify", json={
        "razorpay_order_id": "order_ABC", "razorpay_payment_id": "pay_XYZ",
        "razorpay_signature": sign("order_ABC", "pay_XYZ"),
        "amount": 1, "due": 1,
    })
    assert res.status_code == 200
    payments = tenant.get(f"/api/invoices/{inv['number']}").json()["payments"]
    assert payments[0]["amount"] == 500.0


def test_the_same_payment_cannot_be_recorded_twice(client, tenant):
    """A refresh of the confirmation, or a webhook arriving again."""
    set_up_gateway(tenant)
    inv = issued(tenant)
    tid = link_for(tenant, inv["number"])

    first = pay(client, tid, payment_id="pay_ONCE")
    second = pay(client, tid, payment_id="pay_ONCE")
    assert first.json()["already_recorded"] is False
    assert second.json()["already_recorded"] is True

    detail = tenant.get(f"/api/invoices/{inv['number']}").json()
    assert len(detail["payments"]) == 1
    assert detail["paid"] == detail["payments"][0]["amount"]


def test_incomplete_details_are_refused(client, tenant):
    set_up_gateway(tenant)
    inv = issued(tenant)
    tid = link_for(tenant, inv["number"])
    res = client.post(f"/api/public/invoices/{tid}/pay/razorpay/verify",
                      json={"razorpay_order_id": "order_ABC"})
    assert res.status_code == 400


def test_paying_needs_the_business_to_have_set_it_up(client, tenant):
    inv = issued(tenant)
    res = pay(client, link_for(tenant, inv["number"]))
    assert res.status_code == 503


def test_a_draft_cannot_be_paid(client, tenant):
    set_up_gateway(tenant)
    inv = make_invoice(tenant, status="Draft")
    assert pay(client, link_for(tenant, inv["number"])).status_code == 404


def test_a_guessed_link_cannot_be_paid(client, tenant):
    set_up_gateway(tenant)
    issued(tenant)
    assert pay(client, str(uuid.uuid4())).status_code == 404
