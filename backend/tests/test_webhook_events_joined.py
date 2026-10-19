"""Webhooks for what the ledgers, payroll money and stock do.

These were already happening - an invoice raised, a bill paid, payroll run,
a payslip paid, stock received on a bill - and nothing outside the app could
hear any of it. A payment typed in by hand did not even say "paid", although
the same payment made online did. Each event here is subscribable, and goes
out when, and only when, the thing happened.
"""
import json
import uuid
from datetime import date, timedelta

import pytest

import main
import models
from conftest import make_employee, make_invoice


@pytest.fixture(autouse=True)
def _reset():
    main.rate_limiter._hits.clear()
    yield


@pytest.fixture
def net(monkeypatch):
    calls = []
    monkeypatch.setenv("WEBHOOKS_ASYNC", "0")       # the test drives delivery, no thread racing it
    monkeypatch.setattr(main, "_post_webhook", lambda url, body, headers, timeout=6: (calls.append(json.loads(body)) or (200, "")))
    return calls


def d(n):
    return (date.today() + timedelta(days=n)).isoformat()


def hook(tenant, *events):
    r = tenant.post("/api/webhooks", json={"url": "https://hooks.example/in", **({"events": list(events)} if events else {})})
    assert r.status_code == 200, r.text
    return r.json()


def sent(net, event=None):
    with main.SessionLocal() as db:
        main.deliver_webhooks(db)
    return [c for c in net if event is None or c["event"] == event]


NEW = ("invoice.created", "invoice.sent", "bill.created", "bill.paid", "supplier.created",
       "payroll.run", "payslip.paid", "expense.paid", "hmrc.submitted", "stock.moved")


def test_every_new_event_can_be_subscribed_to(tenant):
    for e in NEW:
        assert e in main.WEBHOOK_EVENTS
        assert tenant.post("/api/webhooks", json={"url": f"https://h{uuid.uuid4().hex[:4]}.example/in", "events": [e]}).status_code == 200


def test_an_invoice_raised_and_paid_by_hand_is_heard(tenant, net):
    hook(tenant, "invoice.created", "invoice.paid")
    inv = make_invoice(tenant, status="Awaiting Payment", contact="Acme Ltd", currency="GBP",
                       line_items=[{"description": "Work", "qty": 1, "price": 100.0, "tax_rate": "No Tax"}])
    made = sent(net, "invoice.created")
    assert len(made) == 1 and made[0]["data"]["invoice"] == inv["number"] and made[0]["data"]["total"] == 100.0
    r = tenant.post(f"/api/invoices/{inv['number']}/payments", json={"amount": 40, "method": "bank_transfer", "reference": "BACS 1"})
    assert r.status_code == 200, r.text
    paid = sent(net, "invoice.paid")
    assert len(paid) == 1 and paid[0]["data"]["amount"] == 40 and paid[0]["data"]["status"] == "Partially Paid"
    assert paid[0]["data"]["reference"] == "BACS 1" and paid[0]["data"]["currency"] == "GBP"


def test_an_invoice_is_sent_only_once_it_was_delivered(tenant, net):
    hook(tenant, "invoice.sent")
    inv = make_invoice(tenant, status="Awaiting Payment", contact="Acme Ltd", email="acme@example.com",
                       line_items=[{"description": "Work", "qty": 1, "price": 100.0, "tax_rate": "No Tax"}])
    assert sent(net, "invoice.sent") == []
    with main.SessionLocal() as db:
        mine = db.query(models.DBClient).order_by(models.DBClient.id.desc()).first().id      # invoice numbers repeat across businesses
        row = models.DBEmailDelivery(client_id=mine,
                                     kind="invoice", reference=inv["number"], to_email="acme@example.com", status="queued")
        db.add(row)
        db.flush()
        main._mark_delivered(db, row)
        db.commit()
    got = sent(net, "invoice.sent")
    assert len(got) == 1 and got[0]["data"]["to"] == "acme@example.com"


def test_a_bill_created_and_paid_off_in_parts_says_paid_once(tenant, net):
    hook(tenant, "bill.created", "bill.paid", "supplier.created")
    b = tenant.post("/api/bills", json={"vendor_name": "Paper Co", "amount": 100, "issue_date": d(-3), "due_date": d(20)}).json()
    assert [e["data"]["name"] for e in sent(net, "supplier.created")] == ["Paper Co"]
    assert [e["data"]["bill"] for e in sent(net, "bill.created")] == [b["number"]]
    tenant.post(f"/api/bills/{b['id']}/payments", json={"amount": 60})
    assert sent(net, "bill.paid") == []
    r = tenant.post(f"/api/bills/{b['id']}/payments", json={"amount": 40})
    assert r.status_code == 200, r.text
    paid = sent(net, "bill.paid")
    assert len(paid) == 1 and paid[0]["data"]["last_payment"] == 40 and paid[0]["data"]["total"] == 100


def test_a_draft_bill_is_created_but_not_paid(tenant, net):
    hook(tenant, "bill.created", "bill.paid")
    tenant.post("/api/bills", json={"vendor_name": "Draft Co", "amount": 100, "draft": True})
    assert [e["data"]["status"] for e in sent(net, "bill.created")] == ["Draft"]
    assert sent(net, "bill.paid") == []


def test_payroll_run_and_a_payslip_paid_are_heard(tenant, net):
    hook(tenant, "payroll.run", "payslip.paid")
    make_employee(tenant, salary=3000.0)
    r = tenant.post("/api/payroll/run", json={"period_start": "2026-09-01", "period_end": "2026-09-30", "pay_date": "2026-09-30"})
    assert r.status_code == 200, r.text
    run = sent(net, "payroll.run")
    assert len(run) == 1 and run[0]["data"]["payslips"] == 1 and run[0]["data"]["pay_date"] == "2026-09-30"
    number = r.json()["created"][0]["number"]
    pid = next(p["id"] for p in tenant.get("/api/payslips").json() if p["number"] == number)
    tenant.post(f"/api/payslips/{pid}/mark-paid")
    assert len(sent(net, "payslip.paid")) == 1


def test_a_run_that_made_no_payslips_is_not_announced(tenant, net):
    hook(tenant, "payroll.run")
    make_employee(tenant, salary=3000.0)
    run = {"period_start": "2026-09-01", "period_end": "2026-09-30", "pay_date": "2026-09-30"}
    assert tenant.post("/api/payroll/run", json=run).status_code == 200
    assert len(sent(net, "payroll.run")) == 1
    again = tenant.post("/api/payroll/run", json=run)          # everybody already has a payslip for it
    assert again.status_code == 200 and again.json()["created"] == [], again.text
    assert len(sent(net, "payroll.run")) == 1


def test_stock_received_on_a_bill_is_heard_with_its_document(tenant, net):
    hook(tenant, "stock.moved")
    it = tenant.post("/api/items", json={"code": f"S-{uuid.uuid4().hex[:5]}", "name": "Box", "sale_price": 5, "track_inventory": True,
                                         "quantity_on_hand": 0, "average_cost": 1}).json()
    b = tenant.post("/api/bills", json={"vendor_name": "Box Co", "amount": 10, "issue_date": d(-1)}).json()
    tenant.post(f"/api/bills/{b['id']}/receive", json={"lines": [{"item_id": it["id"], "quantity": 4, "unit_cost": 2}]})
    got = sent(net, "stock.moved")
    assert len(got) == 1 and got[0]["data"]["document"] == f"bill:{b['id']}" and got[0]["data"]["lines"][0]["quantity"] == 4


def test_a_hook_that_did_not_ask_for_an_event_does_not_get_it(tenant, net):
    hook(tenant, "employee.created")
    tenant.post("/api/bills", json={"vendor_name": "Quiet Co", "amount": 10})
    assert sent(net) == []
