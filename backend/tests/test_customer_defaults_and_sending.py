"""A customer's own terms, and invoices that send themselves.

A customer can have their own payment terms, currency and a copy address;
every document to them is copied there, and an invoice raised from a
quote follows their terms. An invoice can be told to send itself on a
day; a recurring template marked auto-send actually sends; an accepted
quote's invoice reaches the customer. The system sends the way the Send
button does - charged, recorded, marked sent - and when it cannot, the
business is told and the audit log says why. Nothing crosses a business.
"""
from datetime import date, timedelta

import pytest

import main
import models
from conftest import make_invoice


@pytest.fixture(autouse=True)
def _reset():
    main.rate_limiter._hits.clear()
    with main.SessionLocal() as db:
        db.query(models.DBJobRun).delete()
        db.commit()
    yield


@pytest.fixture
def outbox(monkeypatch):
    """Every send, run at once, delivered by a mail provider that always says yes."""
    sent = []
    monkeypatch.setattr(main.BackgroundTasks, "add_task", lambda self, func, *a, **kw: func(*a, **kw))
    monkeypatch.setattr(main, "send_email_background",
                        lambda to, subject, body, from_email, html_body=None, pdf_b64=None, pdf_filename="", logo_data="", client_id=None, cc="", bcc="", *a, **kw:
                        (sent.append({"to": to, "subject": subject, "body": body, "cc": cc, "client_id": client_id}), (True, "sent"))[1])
    return sent


def d(n):
    return (date.today() + timedelta(days=n)).isoformat()


def contact(tenant, **kw):
    res = tenant.post("/api/contacts", json=dict({"name": "Acme", "email": "acme@example.com"}, **kw))
    assert res.status_code == 200, res.text
    return res.json()


def inv(tenant, **kw):
    fields = dict(status="Awaiting Payment", contact="Acme", email="acme@example.com", issue_date=d(0), due_date=d(14), tax_type="none",
                  line_items=[{"description": "x", "qty": 1, "price": 100.0, "tax_rate": "No Tax"}])
    fields.update(kw)
    return make_invoice(tenant, **fields)


def clear_runs():
    with main.SessionLocal() as db:
        db.query(models.DBJobRun).delete()
        db.commit()


def test_a_customer_has_terms_a_currency_and_a_copy_address(tenant):
    c = contact(tenant, payment_terms_days=30, currency="usd", cc_email="accounts@acme.example.com")
    assert c["payment_terms_days"] == 30 and c["currency"] == "USD" and c["cc_email"] == "accounts@acme.example.com"
    res = tenant.put(f"/api/contacts/{c['id']}", json={"payment_terms_days": "", "currency": ""})
    assert res.json()["payment_terms_days"] is None and res.json()["currency"] == "" and res.json()["cc_email"] == "accounts@acme.example.com", "left alone when not sent"
    for bad, why in [({"payment_terms_days": 400}, "between 0 and 365"), ({"payment_terms_days": "soon"}, "number"), ({"currency": "12"}, "three-letter"), ({"cc_email": "not-an-address"}, "Invalid email")]:
        res = tenant.put(f"/api/contacts/{c['id']}", json=bad)
        assert res.status_code == 400 and why in res.json()["detail"], (bad, res.text)
    found = tenant.get("/api/contacts/search", params={"q": "acme"}).json()
    assert found[0]["cc_email"] == "accounts@acme.example.com" and "payment_terms_days" in found[0]


def test_everything_to_the_customer_is_copied_to_their_copy_address(tenant, outbox):
    contact(tenant, cc_email="accounts@acme.example.com")
    a = inv(tenant)
    res = tenant.post(f"/api/invoices/{a['number']}/send", json={"cc": "boss@acme.example.com, accounts@acme.example.com"})
    assert res.status_code == 200, res.text
    mail = [m for m in outbox if m["to"] == "acme@example.com"][-1]
    assert mail["cc"] == "boss@acme.example.com, accounts@acme.example.com", "typed once, copied once"
    assert tenant.post(f"/api/invoices/{a['number']}/email-preview", json={}).json()["cc"] == "accounts@acme.example.com"
    # A reminder, a credit note and a statement go there too.
    late = make_invoice(tenant, status="Awaiting Payment", contact="Acme", email="acme@example.com", issue_date=d(-30), due_date=d(-3), tax_type="none",
                        line_items=[{"description": "x", "qty": 1, "price": 100.0, "tax_rate": "No Tax"}])
    tenant.post(f"/api/invoices/{late['number']}/chase", json={})
    assert [m for m in outbox if m["to"] == "acme@example.com"][-1]["cc"] == "accounts@acme.example.com"
    cn = tenant.post("/api/credit-notes", json={"invoice_number": a["number"]}).json()
    tenant.post(f"/api/credit-notes/{cn['number']}/send", json={})
    assert [m for m in outbox if "Credit note" in m["subject"]][-1]["cc"] == "accounts@acme.example.com"
    cid = tenant.get("/api/contacts").json()[0]["id"]
    tenant.post(f"/api/contacts/{cid}/statement/send", json={})
    assert [m for m in outbox if "tatement" in m["subject"]][-1]["cc"] == "accounts@acme.example.com"
    # Not when the copy address is the recipient.
    tenant.put(f"/api/contacts/{cid}", json={"cc_email": "acme@example.com"})
    tenant.post(f"/api/invoices/{a['number']}/send", json={})
    assert [m for m in outbox if m["to"] == "acme@example.com"][-1]["cc"] == ""


def test_an_accepted_quote_follows_the_customers_terms_and_the_invoice_is_emailed(client, tenant, outbox):
    contact(tenant, name="Prospect Ltd", email="buyer@example.com", payment_terms_days=45)
    q = tenant.post("/api/quotes", json={"contact": "Prospect Ltd", "email": "buyer@example.com", "issue_date": d(0), "expiry_date": d(14), "tax_type": "none",
                                          "line_items": [{"name": "Work", "description": "x", "qty": 1, "price": 500.0, "tax_rate": "No Tax"}]}).json()
    res = client.post(f"/api/public/quotes/{q['tracking_id']}/accept", json={"name": "Dana"})
    assert res.status_code == 200, res.text
    number = res.json()["quote"]["invoice"]["number"]
    got = tenant.get(f"/api/invoices/{number}").json()
    assert got["due_date"] == d(45), "the customer's own terms, not the business's fortnight"
    mail = [m for m in outbox if m["to"] == "buyer@example.com" and number in m["subject"]]
    assert len(mail) == 1, "the invoice went to the customer on acceptance"
    assert got["status"] == "Sent" and got["sent"] == d(0)


def test_an_invoice_can_be_told_to_send_itself_on_a_day(tenant, outbox):
    a = inv(tenant, status="Draft")
    res = tenant.post(f"/api/invoices/{a['number']}/schedule", json={"send_at": d(2)})
    assert res.status_code == 200 and res.json()["send_at"] == d(2), res.text
    assert tenant.get(f"/api/invoices/{a['number']}").json()["send_at"] == d(2)
    assert [i for i in tenant.get("/api/invoice-list").json()["items"] if i["number"] == a["number"]][0]["send_at"] == d(2)
    assert tenant.post(f"/api/invoices/{a['number']}/schedule", json={"send_at": d(-1)}).status_code == 400
    assert tenant.post(f"/api/invoices/{a['number']}/schedule", json={"send_at": "tuesday"}).status_code == 400
    no_mail = make_invoice(tenant, status="Draft", contact="Nobody", email="")
    assert tenant.post(f"/api/invoices/{no_mail['number']}/schedule", json={"send_at": d(1)}).status_code == 400
    # Not today: nothing goes.
    main.run_due_jobs(only="scheduled_sends")
    assert not [m for m in outbox if m["to"] == "acme@example.com"]
    assert tenant.get(f"/api/invoices/{a['number']}").json()["status"] == "Draft"
    # The day comes.
    with main.SessionLocal() as db:
        row = db.query(models.DBInvoice).filter(models.DBInvoice.tracking_id == a["tracking_id"]).first()
        row.send_at = d(0)
        db.commit()
    clear_runs()
    out = main.run_due_jobs(only="scheduled_sends")
    assert [r["detail"] for r in out if r["job"] == "scheduled_sends"] == ["1 sent"]
    mail = [m for m in outbox if m["to"] == "acme@example.com"]
    assert len(mail) == 1 and a["number"] in mail[0]["subject"]
    got = tenant.get(f"/api/invoices/{a['number']}").json()
    assert got["status"] == "Sent" and got["sent"] == d(0) and got["send_at"] == ""
    with main.SessionLocal() as db:
        mine = db.query(models.DBInvoice).filter(models.DBInvoice.tracking_id == a["tracking_id"]).first()
        deliveries = db.query(models.DBEmailDelivery).filter(models.DBEmailDelivery.client_id == mine.client_id, models.DBEmailDelivery.kind == "invoice",
                                                             models.DBEmailDelivery.reference == a["number"]).all()
        assert len(deliveries) == 1 and deliveries[0].status == "sent", "recorded like a send by hand"
    # Cancelled means cancelled.
    b = inv(tenant, status="Draft")
    tenant.post(f"/api/invoices/{b['number']}/schedule", json={"send_at": d(0)})
    res = tenant.post(f"/api/invoices/{b['number']}/schedule", json={"send_at": ""})
    assert res.status_code == 200 and res.json()["send_at"] == ""
    clear_runs()
    main.run_due_jobs(only="scheduled_sends")
    assert len([m for m in outbox if m["to"] == "acme@example.com"]) == 1


def test_when_the_system_cannot_send_the_business_hears_and_it_tries_again(tenant, outbox, monkeypatch):
    a = inv(tenant, status="Draft")
    tenant.post(f"/api/invoices/{a['number']}/schedule", json={"send_at": d(0)})
    monkeypatch.setattr(main, "email_delivery_ready", lambda db, client_id=None: (False, "no mail is set up"))
    out = main.run_due_jobs(only="scheduled_sends")
    assert [r["detail"] for r in out if r["job"] == "scheduled_sends"] == ["0 sent, 1 could not be"]
    assert not [m for m in outbox if m["to"] == "acme@example.com"]
    told = [m for m in outbox if m["subject"] == f"Invoice {a['number']} could not be sent"]
    assert len(told) == 1 and "no mail is set up" in told[0]["body"]
    got = tenant.get(f"/api/invoices/{a['number']}").json()
    assert got["status"] == "Draft" and got["send_at"] == d(0), "kept, to be tried again"
    with main.SessionLocal() as db:
        log = db.query(models.DBAuditLog).filter(models.DBAuditLog.action == "invoice_send_failed", models.DBAuditLog.entity_name == a["number"]).first()
        assert log is not None and "no mail is set up" in log.details


def test_a_recurring_template_marked_auto_send_actually_sends(tenant, outbox):
    res = tenant.post("/api/recurring-invoices", json={
        "name": "Retainer", "contact": "Acme", "email": "acme@example.com", "frequency": "monthly", "next_run": d(0),
        "payment_terms_days": 14, "tax_type": "exclusive", "auto_send": True,
        "line_items": [{"description": "Support", "qty": 1, "price": 500.0, "tax_rate": "No Tax"}]})
    assert res.status_code == 200, res.text
    quiet = tenant.post("/api/recurring-invoices", json={
        "name": "Drafts", "contact": "Bolt", "email": "bolt@example.com", "frequency": "monthly", "next_run": d(0),
        "payment_terms_days": 14, "tax_type": "exclusive", "auto_send": False,
        "line_items": [{"description": "Support", "qty": 1, "price": 50.0, "tax_rate": "No Tax"}]}).json()
    out = main.run_due_jobs(only="recurring_invoices")
    # The job is platform-wide: other tests' templates are raised too, so
    # only the sends are counted here.
    detail = [r["detail"] for r in out if r["job"] == "recurring_invoices"][0]
    assert detail.endswith(", 1 sent"), detail
    mine = [i for i in tenant.get("/api/invoices").json() if i["to"] == "Acme"]
    assert len(mine) == 1 and mine[0]["status"] == "Sent" and mine[0]["sent"] == d(0)
    mail = [m for m in outbox if m["to"] == "acme@example.com"][0]
    assert mine[0]["number"] in mail["subject"] and "invoice.html?id=" in mail["body"], "the invoice, with its link, though nobody was on a request"
    drafts = [i for i in tenant.get("/api/invoices").json() if i["to"] == "Bolt"]
    assert len(drafts) == 1 and drafts[0]["status"] == "Draft" and not [m for m in outbox if m["to"] == "bolt@example.com"]


def test_nothing_crosses_a_business(client, account, outbox):
    tenant = account["client"]
    a = inv(tenant, status="Draft")
    other_email = f"other-{account['email']}"
    client.post("/api/client/register", json={"email": other_email, "password": "Passw0rdTest", "company_name": "Other Co"})
    client.post("/api/client/login", json={"email": other_email, "password": "Passw0rdTest"})
    assert client.post(f"/api/invoices/{a['number']}/schedule", json={"send_at": d(1)}).status_code == 404
    client.cookies.clear()
    assert client.post(f"/api/invoices/{a['number']}/schedule", json={"send_at": d(1)}).status_code == 401
