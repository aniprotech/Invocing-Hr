"""A receipt for one invoice must not pay off another.

The confirmation endpoint checked Razorpay's signature - hmac of
order_id|payment_id with the business's secret - and treated that as proof the
invoice was paid. The signature is genuine proof that a real payment happened
on that business's account. It says nothing about which invoice the money was
for, and both invoices of the same business are signed with the same secret.

Nothing recorded which invoice an order had been opened for, and the amount
written to the ledger came from `inv.due` rather than from what the payer was
actually charged. So a customer holding a valid receipt for their own ten
pound invoice could post the same three fields against a ten thousand pound
invoice from the same business, and it would be marked paid in full.

That is the test at the top of this file. The rest is making sure the fix did
not break paying an invoice normally.
"""
import hashlib
import hmac
import uuid

import pytest

import main
import models
from conftest import make_invoice


SECRET = "rzp_test_secret"


@pytest.fixture(autouse=True)
def razorpay(monkeypatch):
    """A gateway that always opens an order, and keys we know the secret of."""
    opened = []

    class Resp:
        status_code = 200
        text = ""

        def json(self):
            # Unique per call, as a real order id is - the column is unique, and
            # the whole suite shares one database.
            oid = f"order_{uuid.uuid4().hex[:16]}"
            opened.append(oid)
            return {"id": oid}

    monkeypatch.setattr(main.httpx, "post", lambda *a, **k: Resp())
    monkeypatch.setattr(main, "collecting_keys",
                        lambda db, client_id: ("rzp_test_key", SECRET, "direct"))
    return opened


def sign(order_id, payment_id):
    return hmac.new(SECRET.encode(), f"{order_id}|{payment_id}".encode(),
                    hashlib.sha256).hexdigest()


def an_invoice(tenant, price):
    """A sent invoice with a payment link, since a draft is not payable.

    Scoped to this test's own business. Every tenant numbers from INV-0001 and
    each test gets a fresh one, so looking an invoice up by number alone finds
    an earlier test's - which is the very mistake this file is about.
    """
    mine = tenant.get("/api/client/me").json()["id"]
    inv = make_invoice(tenant, line_items=[
        {"description": "Work", "qty": 1, "price": price, "tax_rate": "No Tax"}])
    with main.SessionLocal() as db:
        row = db.query(models.DBInvoice).filter(
            models.DBInvoice.client_id == mine,
            models.DBInvoice.number == inv["number"]).first()
        row.status = "Sent"          # a draft has no payment link
        db.commit()
        return {"number": row.number, "tracking_id": row.tracking_id, "id": row.id}


def start(client, inv):
    res = client.post(f"/api/public/invoices/{inv['tracking_id']}/pay/razorpay/order")
    assert res.status_code == 200, res.text
    return res.json()


def confirm(client, inv, order_id, payment_id, signature=None):
    return client.post(
        f"/api/public/invoices/{inv['tracking_id']}/pay/razorpay/verify",
        json={"razorpay_order_id": order_id,
              "razorpay_payment_id": payment_id,
              "razorpay_signature": signature or sign(order_id, payment_id)})


def paid_and_due(inv):
    """By tracking id, not number. Every tenant numbers from INV-0001, and the
    suite shares one database - looking up by number finds another test's
    invoice, which is the same mistake this file exists to be strict about."""
    with main.SessionLocal() as db:
        row = db.query(models.DBInvoice).filter(
            models.DBInvoice.tracking_id == inv["tracking_id"]).first()
        return round(row.paid or 0, 2), round(row.due or 0, 2), row.status


# --- the hole ---------------------------------------------------------------------

def test_a_receipt_cannot_be_moved_to_another_invoice(client, tenant):
    """The whole finding. Both invoices belong to the same business, so the
    same secret signs both and the signature verifies either way."""
    small = an_invoice(tenant, 10.0)
    large = an_invoice(tenant, 10000.0)

    order = start(client, small)                      # opened against the small one
    receipt = "pay_realpayment"

    moved = confirm(client, large, order["order_id"], receipt)

    assert moved.status_code == 400, \
        f"a 10.00 receipt was accepted against a 10000.00 invoice ({moved.status_code})"
    assert paid_and_due(large) == (0.0, 10000.0, "Sent"), \
        paid_and_due(large)


def test_and_the_signature_on_it_really_was_valid(client, tenant):
    """Otherwise the test above proves only that a bad signature is rejected,
    which was never the problem."""
    small = an_invoice(tenant, 10.0)
    order = start(client, small)
    receipt = "pay_realpayment2"

    ok = confirm(client, small, order["order_id"], receipt)
    assert ok.status_code == 200, \
        f"the signature was not actually valid, so the attack test proves nothing: {ok.text}"


def test_an_order_nobody_opened_is_refused(client, tenant):
    """A signature can be computed for any pair of strings by anyone who knows
    the secret - including the business itself, or anyone who has ever seen it."""
    inv = an_invoice(tenant, 500.0)
    res = confirm(client, inv, "order_invented", "pay_invented")
    assert res.status_code == 400, res.status_code
    assert paid_and_due(inv)[0] == 0.0


# --- what the payer was charged, not what happens to be outstanding -------------------

def test_the_amount_recorded_is_the_amount_charged(client, tenant):
    """It used to come from inv.due at confirmation time. That is the number
    that let a small receipt clear a large invoice, and it is also wrong on its
    own terms: the balance can move between opening the order and paying it."""
    inv = an_invoice(tenant, 300.0)
    order = start(client, inv)

    # Somebody records a part payment while the customer is at the gateway.
    with main.SessionLocal() as db:
        row = db.query(models.DBInvoice).filter(
            models.DBInvoice.tracking_id == inv["tracking_id"]).first()
        main.record_invoice_payment(db, row, 100.0, "bank_transfer", "manual-1")
        db.commit()

    assert confirm(client, inv, order["order_id"], "pay_x").status_code == 200

    paid, due, status = paid_and_due(inv)
    assert paid == 400.0, f"recorded {paid}, expected the 100 part payment plus the 300 charged"
    assert due == 0.0 and status == "Paid", (due, status)


# --- what must still work ------------------------------------------------------------

def test_paying_an_invoice_normally_still_works(client, tenant):
    inv = an_invoice(tenant, 250.0)
    order = start(client, inv)
    res = confirm(client, inv, order["order_id"], "pay_normal")

    assert res.status_code == 200, res.text
    assert res.json()["paid"] is True
    assert paid_and_due(inv) == (250.0, 0.0, "Paid")


def test_a_forged_signature_is_still_refused(client, tenant):
    inv = an_invoice(tenant, 40.0)
    order = start(client, inv)
    res = confirm(client, inv, order["order_id"], "pay_forged", signature="not-the-signature")
    assert res.status_code == 400
    assert paid_and_due(inv)[0] == 0.0


def test_the_same_receipt_twice_pays_once(client, tenant):
    """A customer refreshing the confirmation page must not pay twice."""
    inv = an_invoice(tenant, 90.0)
    order = start(client, inv)

    first = confirm(client, inv, order["order_id"], "pay_twice")
    second = confirm(client, inv, order["order_id"], "pay_twice")

    assert first.status_code == 200 and second.status_code == 200
    assert second.json()["already_recorded"] is True
    assert paid_and_due(inv) == (90.0, 0.0, "Paid")


def test_one_order_pays_once_even_with_a_second_receipt(client, tenant):
    """A gateway can hold more than one payment id against the same order - an
    attempt that failed and then one that worked - and each is signed. Without
    this the second could be presented afterwards and credited again."""
    inv = an_invoice(tenant, 120.0)
    order = start(client, inv)

    assert confirm(client, inv, order["order_id"], "pay_first").status_code == 200
    second = confirm(client, inv, order["order_id"], "pay_second")

    assert second.status_code == 409, \
        f"a second receipt on the same order was credited ({second.status_code})"
    assert paid_and_due(inv) == (120.0, 0.0, "Paid"), paid_and_due(inv)


def test_opening_a_payment_writes_the_order_down(client, tenant):
    """The link the confirmation relies on. If this is not stored, every
    payment is refused instead."""
    inv = an_invoice(tenant, 75.0)
    order = start(client, inv)

    with main.SessionLocal() as db:
        row = db.query(models.DBInvoicePaymentOrder).filter(
            models.DBInvoicePaymentOrder.provider_order_id == order["order_id"]).first()
    assert row is not None, "the order was not recorded against the invoice"
    assert row.invoice_id == inv["id"]
    assert row.amount_minor == 7500, row.amount_minor


def test_the_order_is_marked_paid_once_it_is_used(client, tenant):
    inv = an_invoice(tenant, 60.0)
    order = start(client, inv)
    confirm(client, inv, order["order_id"], "pay_marks")

    with main.SessionLocal() as db:
        row = db.query(models.DBInvoicePaymentOrder).filter(
            models.DBInvoicePaymentOrder.provider_order_id == order["order_id"]).first()
    assert row.status == "paid"
    assert row.provider_payment_id == "pay_marks"
