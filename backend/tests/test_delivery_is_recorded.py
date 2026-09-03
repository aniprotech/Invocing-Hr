"""What was delivered, rather than what was attempted.

Sending is handed to a background task, so the answer to the browser goes out
before anybody knows whether the message left. The invoice was marked Sent at
that moment and the wallet was charged. When the send then failed, the
business had paid, the ledger said Sent, and nobody chased an invoice the
customer never received.

So the tests worth having are all about the failing path: it must not say
sent, and it must give the money back.
"""
import uuid

import pytest

import main
import models


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


def make_invoice(tenant):
    res = tenant.post("/api/invoices", json={
        "contact": "Customer Ltd", "email": "customer@example.com",
        "issue_date": "2026-01-01", "due_date": "2026-01-31",
        "status": "Awaiting Payment", "tax_type": "exclusive",
        "line_items": [{"description": "Work", "qty": 1, "price": 100.0,
                        "tax_rate": "No Tax"}]})
    assert res.status_code == 200, res.text
    return res.json()


def latest_delivery():
    with main.SessionLocal() as db:
        return db.query(models.DBEmailDelivery).order_by(
            models.DBEmailDelivery.id.desc()).first()


def invoice_row(tenant, number):
    return tenant.get(f"/api/invoices/{number}").json()


def run_pending_tasks(monkeypatch, outcome):
    """Stand in for the mail provider and run the delivery inline."""
    calls = []

    def fake_send(*a, **kw):
        calls.append((a, kw))
        return outcome

    monkeypatch.setattr(main, "send_email_background", fake_send)
    return calls


@pytest.fixture
def deliver_now(monkeypatch):
    """Background tasks normally run after the response; here they run at
    once, so a test can see what the delivery decided."""
    def immediate(self, func, *args, **kwargs):
        func(*args, **kwargs)

    monkeypatch.setattr(main.BackgroundTasks, "add_task", immediate)


# --- the happy path -------------------------------------------------------------
def test_a_delivered_invoice_is_marked_sent(tenant, deliver_now, monkeypatch):
    run_pending_tasks(monkeypatch, (True, "sent"))
    inv = make_invoice(tenant)

    res = tenant.post(f"/api/invoices/{inv['number']}/send", json={})
    assert res.status_code == 200, res.text

    after = invoice_row(tenant, inv["number"])
    assert after["status"] == "Sent", after["status"]
    assert after["sent"], "no sent date"
    assert latest_delivery().status == "sent"


# --- the point of all this --------------------------------------------------------
def test_an_invoice_that_did_not_send_is_not_marked_sent(tenant, deliver_now,
                                                         monkeypatch):
    run_pending_tasks(monkeypatch, (False, "mailbox unavailable"))
    inv = make_invoice(tenant)
    before = invoice_row(tenant, inv["number"])["status"]

    res = tenant.post(f"/api/invoices/{inv['number']}/send", json={})
    assert res.status_code == 200, res.text

    after = invoice_row(tenant, inv["number"])
    assert after["status"] == before, f"{before} became {after['status']}"
    assert not after["sent"], "it recorded a send date for a message that failed"


def test_the_failure_and_its_reason_are_written_down(tenant, deliver_now,
                                                     monkeypatch):
    """A failure nobody can see is a failure nobody acts on."""
    run_pending_tasks(monkeypatch, (False, "mailbox unavailable"))
    inv = make_invoice(tenant)
    tenant.post(f"/api/invoices/{inv['number']}/send", json={})

    row = latest_delivery()
    assert row.status == "failed"
    assert "mailbox unavailable" in row.error
    assert row.reference == inv["number"]
    assert row.completed_at


def test_a_send_that_raises_is_caught_and_recorded(tenant, deliver_now,
                                                   monkeypatch):
    """A provider library that throws must not leave the row saying pending
    for ever."""
    def explode(*a, **kw):
        raise RuntimeError("connection reset")

    monkeypatch.setattr(main, "send_email_background", explode)
    inv = make_invoice(tenant)
    tenant.post(f"/api/invoices/{inv['number']}/send", json={})

    row = latest_delivery()
    assert row.status == "failed"
    assert "connection reset" in row.error


# --- the money ---------------------------------------------------------------------
def wallet_balance(tenant):
    return tenant.get("/api/wallet").json()["balance_minor"]


def test_a_failed_send_gives_the_charge_back(tenant, deliver_now, monkeypatch):
    """Nobody should pay for a message that never left.

    Driven through deliver_and_record with a charge on the row, because the
    test tenant is not on a paid plan - branching on "if anything was
    charged" made this pass without ever exercising the refund, which is the
    only part worth testing.
    """
    run_pending_tasks(monkeypatch, (False, "rejected"))
    inv = make_invoice(tenant)
    tenant.post(f"/api/invoices/{inv['number']}/send", json={})

    row = latest_delivery()
    with main.SessionLocal() as db:
        fresh = db.query(models.DBEmailDelivery).filter(
            models.DBEmailDelivery.id == row.id).first()
        fresh.status = "pending"
        fresh.refunded = False
        fresh.charge_minor = 250          # what a paid plan would have taken
        db.commit()

    before = wallet_balance(tenant)
    main.deliver_and_record(row.id, "customer@example.com", "s", "b", "f@x.test")
    after = wallet_balance(tenant)

    assert after == before + 250, f"{before} -> {after}, expected the 250 back"
    with main.SessionLocal() as db:
        assert db.query(models.DBEmailDelivery).filter(
            models.DBEmailDelivery.id == row.id).first().refunded is True


def test_a_delivered_send_keeps_the_charge(tenant, deliver_now, monkeypatch):
    run_pending_tasks(monkeypatch, (True, "sent"))
    inv = make_invoice(tenant)
    tenant.post(f"/api/invoices/{inv['number']}/send", json={})
    row = latest_delivery()
    assert row.status == "sent"
    assert row.refunded is False


def test_the_refund_happens_once(tenant, deliver_now, monkeypatch):
    """Two refunds for one failure is money out of the operator's pocket, and
    a retried background task is exactly how that happens."""
    run_pending_tasks(monkeypatch, (False, "rejected"))
    inv = make_invoice(tenant)
    tenant.post(f"/api/invoices/{inv['number']}/send", json={})

    row = latest_delivery()
    with main.SessionLocal() as db:
        fresh = db.query(models.DBEmailDelivery).filter(
            models.DBEmailDelivery.id == row.id).first()
        fresh.status = "pending"
        fresh.refunded = False
        fresh.charge_minor = 250
        db.commit()

    main.deliver_and_record(row.id, "customer@example.com", "s", "b", "f@x.test")
    once = wallet_balance(tenant)
    main.deliver_and_record(row.id, "customer@example.com", "s", "b", "f@x.test")
    assert wallet_balance(tenant) == once, "it paid out twice"


# --- what the answer says ------------------------------------------------------------
def test_the_answer_does_not_claim_it_was_sent(tenant, deliver_now, monkeypatch):
    """It used to answer status Sent before anything had been attempted."""
    run_pending_tasks(monkeypatch, (False, "rejected"))
    inv = make_invoice(tenant)
    body = tenant.post(f"/api/invoices/{inv['number']}/send", json={}).json()
    assert body["status"] != "Sent", body
    assert "delivery_id" in body, body
