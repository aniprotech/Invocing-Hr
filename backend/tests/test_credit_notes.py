"""Credit notes: the way a sent invoice is corrected.

A credit note is its own numbered document against an invoice. What it
credits comes off what the invoice is owed; anything beyond that - the
customer had already paid - is theirs to have back: set against another
of their invoices, or paid back, and the note keeps count of both. It can
be withdrawn until it has been used. The statement shows the invoice
whole, the credit, and the money back, and never counts a credit twice.
It goes to the customer by email with the PDF. Nothing crosses a business.
"""
import uuid
from datetime import date, timedelta

import pytest

import main
import models
from conftest import make_invoice


@pytest.fixture(autouse=True)
def _reset():
    main.rate_limiter._hits.clear()
    yield


def d(n):
    return (date.today() + timedelta(days=n)).isoformat()


def uniq(stem):
    return f"{stem}-{uuid.uuid4().hex[:6]}@example.com"


def inv(tenant, contact="Acme", email=None, lines=None, **kw):
    return make_invoice(tenant, status="Awaiting Payment", contact=contact, email=email or uniq("acme"),
                        issue_date=d(-10), due_date=d(20), tax_type="none",
                        line_items=lines or [{"name": "Design", "description": "Design work", "qty": 2, "price": 300.0, "tax_rate": "No Tax"},
                                             {"name": "Hosting", "description": "Hosting", "qty": 1, "price": 400.0, "tax_rate": "No Tax"}], **kw)


def pay(tenant, number, amount, on=None, **kw):
    res = tenant.post(f"/api/invoices/{number}/payments", json=dict({"amount": amount, "paid_on": on or d(0), "method": "bank_transfer"}, **kw))
    assert res.status_code == 200, res.text
    return res.json()["payment_id"]


def credit(tenant, number, **body):
    res = tenant.post("/api/credit-notes", json=dict({"invoice_number": number}, **body))
    assert res.status_code == 200, res.text
    return res.json()


def test_a_credit_note_for_the_whole_invoice_takes_it_all_off(tenant):
    a = inv(tenant)
    cn = credit(tenant, a["number"], reason="Job cancelled")
    assert cn["number"] == "CN-0001" and cn["invoice_number"] == a["number"] and cn["status"] == "Issued"
    assert cn["total"] == 1000.0 and cn["applied"] == 1000.0 and cn["unapplied"] == 0 and cn["reason"] == "Job cancelled"
    assert [(li["name"], li["qty"], li["price"]) for li in cn["line_items"]] == [("Design", 2.0, 300.0), ("Hosting", 1.0, 400.0)]
    assert cn["to"] == "Acme" and cn["email"] == a["email"] and cn["date"] == d(0) and cn["company"]["name"]
    got = tenant.get(f"/api/invoices/{a['number']}").json()
    assert got["due"] == 0 and got["status"] == "Credited" and got["credited"] == 1000.0
    assert [c["number"] for c in got["credit_notes"]] == ["CN-0001"]
    assert got["chasing"]["next"] is None, "nothing owed, nothing chased"
    # The customer's own page says so.
    public = tenant.get(f"/api/public/invoices/{a['tracking_id']}").json()
    assert public["is_settled"] is True and public["amount_due"] == 0
    assert public["credit_notes"] == [{"number": "CN-0001", "date": d(0), "amount": 1000.0, "reason": "Job cancelled"}]
    # Numbered in sequence, listed newest first.
    b = inv(tenant)
    assert credit(tenant, b["number"])["number"] == "CN-0002"
    assert [c["number"] for c in tenant.get("/api/credit-notes").json()] == ["CN-0002", "CN-0001"]
    assert [c["number"] for c in tenant.get("/api/credit-notes", params={"invoice": a["number"]}).json()] == ["CN-0001"]


def test_a_part_credit_by_lines_and_no_more_than_the_invoice(tenant):
    a = inv(tenant)
    cn = credit(tenant, a["number"], line_items=[{"name": "Design", "description": "One day not done", "qty": 1, "price": 300, "tax_rate": "No Tax"}])
    assert cn["total"] == 300.0 and cn["applied"] == 300.0
    got = tenant.get(f"/api/invoices/{a['number']}").json()
    assert got["due"] == 700.0 and got["status"] == "Awaiting Payment" and got["credited"] == 300.0
    assert got["total"] == 1000.0, "the invoice itself is untouched"
    res = tenant.post("/api/credit-notes", json={"invoice_number": a["number"], "line_items": [{"description": "Too much", "qty": 1, "price": 800, "tax_rate": "No Tax"}]})
    assert res.status_code == 400 and "only 700.00" in res.json()["detail"], res.text
    for bad, why in [([], "at least one"), ([{"description": "x", "qty": 0, "price": 1}], "more than zero"),
                     ([{"description": "x", "qty": 1, "price": -1}], "negative"), ([{"description": "x", "qty": 1, "price": 1, "disc": 150}], "between 0 and 100"),
                     ([{"description": "x", "qty": "many", "price": 1}], "numbers")]:
        res = tenant.post("/api/credit-notes", json={"invoice_number": a["number"], "line_items": bad})
        assert res.status_code == 400 and why in res.json()["detail"], (bad, res.text)
    assert tenant.post("/api/credit-notes", json={"invoice_number": "INV-9999"}).status_code == 404
    draft = make_invoice(tenant, status="Draft")
    assert tenant.post("/api/credit-notes", json={"invoice_number": draft["number"]}).status_code == 400
    # Tax follows the invoice: an exclusive-tax invoice credits tax too.
    taxed = make_invoice(tenant, status="Awaiting Payment", line_items=[{"description": "Work", "qty": 1, "price": 100.0, "tax_rate": "20% VAT"}])
    cn2 = credit(tenant, taxed["number"])
    assert cn2["subtotal"] == 100.0 and cn2["tax_total"] == 20.0 and cn2["total"] == 120.0
    assert tenant.get(f"/api/invoices/{taxed['number']}").json()["due"] == 0


def test_a_credit_beyond_what_is_owed_is_the_customers_to_have_back(tenant):
    a = inv(tenant, email="acme@example.com")
    pay(tenant, a["number"], 1000)
    cn = credit(tenant, a["number"], line_items=[{"description": "Overcharged", "qty": 1, "price": 400, "tax_rate": "No Tax"}])
    assert cn["applied"] == 0 and cn["unapplied"] == 400.0
    assert tenant.get(f"/api/invoices/{a['number']}").json()["status"] == "Paid", "the invoice was paid; that stands"
    # Set against another of Acme's invoices.
    b = inv(tenant, email="acme@example.com", lines=[{"description": "Next job", "qty": 1, "price": 250.0, "tax_rate": "No Tax"}])
    res = tenant.post(f"/api/credit-notes/{cn['number']}/allocate", json={"invoice_number": b["number"]})
    assert res.status_code == 200, res.text
    assert res.json()["invoice"] == {"number": b["number"], "status": "Paid", "paid": 250.0, "due": 0.0}
    note = res.json()["credit_note"]
    assert note["allocated"] == 250.0 and note["unapplied"] == 150.0
    assert note["allocations"] == [{"payment_id": note["allocations"][0]["payment_id"], "invoice_number": b["number"], "amount": 250.0, "on": d(0)}]
    got_b = tenant.get(f"/api/invoices/{b['number']}").json()
    assert got_b["payments"][0]["method"] == "credit_note" and got_b["payments"][0]["reference"] == cn["number"]
    # Not somebody else's invoice, not the same invoice, not more than is left.
    other = inv(tenant, contact="Bolt", email=uniq("bolt"))
    res = tenant.post(f"/api/credit-notes/{cn['number']}/allocate", json={"invoice_number": other["number"]})
    assert res.status_code == 400 and "somebody else" in res.json()["detail"]
    assert tenant.post(f"/api/credit-notes/{cn['number']}/allocate", json={"invoice_number": a["number"]}).status_code == 400
    c = inv(tenant, email="acme@example.com")
    res = tenant.post(f"/api/credit-notes/{cn['number']}/allocate", json={"invoice_number": c["number"], "amount": 151})
    assert res.status_code == 400 and "150.00" in res.json()["detail"]
    # A credit set against an invoice is not money, so it cannot be refunded;
    # reversing the receipt on the books gives the credit back.
    pid = got_b["payments"][0]["id"]
    res = tenant.post(f"/api/invoices/{b['number']}/payments/{pid}/refund", json={"amount": 10, "tell_customer": False})
    assert res.status_code == 400 and "credit note" in res.json()["detail"]
    assert tenant.delete(f"/api/invoices/{b['number']}/payments/{pid}").status_code == 200
    assert tenant.get(f"/api/credit-notes/{cn['number']}").json()["unapplied"] == 400.0
    assert tenant.get(f"/api/invoices/{b['number']}").json()["due"] == 250.0


def test_what_is_left_can_be_paid_back_and_the_accounts_know(tenant):
    bank = tenant.post("/api/accounts", json={"name": "Bank", "kind": "bank"}).json()
    a = inv(tenant)
    pay(tenant, a["number"], 1000, account_id=bank["id"])
    cn = credit(tenant, a["number"], line_items=[{"description": "Overcharged", "qty": 1, "price": 100, "tax_rate": "No Tax"}])
    res = tenant.post(f"/api/credit-notes/{cn['number']}/refund", json={"amount": 60, "method": "bank_transfer", "account_id": bank["id"], "reference": "FPS back"})
    assert res.status_code == 200, res.text
    note = res.json()["credit_note"]
    assert note["refunded"] == 60.0 and note["unapplied"] == 40.0 and note["refunded_on"] == d(0) and note["refund_reference"] == "FPS back"
    assert note["refund_account_name"] == "Bank"
    res = tenant.post(f"/api/credit-notes/{cn['number']}/refund", json={"amount": 41})
    assert res.status_code == 400 and "40.00" in res.json()["detail"]
    res = tenant.post(f"/api/credit-notes/{cn['number']}/refund", json={})
    assert res.status_code == 200 and res.json()["credit_note"]["refunded"] == 100.0 and res.json()["credit_note"]["unapplied"] == 0
    assert tenant.post(f"/api/credit-notes/{cn['number']}/refund", json={}).status_code == 400
    assert tenant.post(f"/api/credit-notes/{cn['number']}/allocate", json={"invoice_number": a["number"]}).status_code == 400
    rows = {x["name"]: x["totals"] for x in tenant.get("/api/accounts").json()["accounts"]}
    assert rows["Bank"]["all_time"] == 900.0, "1000 in, 100 paid back"
    # A credit set against an invoice is never money into an account.
    b = inv(tenant, lines=[{"description": "Next", "qty": 1, "price": 50.0, "tax_rate": "No Tax"}])
    pay(tenant, b["number"], 50, account_id=bank["id"])
    cn2 = credit(tenant, b["number"])
    c = inv(tenant, lines=[{"description": "After", "qty": 1, "price": 50.0, "tax_rate": "No Tax"}])
    tenant.post(f"/api/credit-notes/{cn2['number']}/allocate", json={"invoice_number": c["number"]})
    listed = tenant.get("/api/accounts").json()
    rows = {x["name"]: x["totals"] for x in listed["accounts"]}
    assert rows["Bank"]["all_time"] == 950.0
    assert (listed.get("untracked") or {}).get("all_time", 0) == 0 and (listed.get("untracked") or {}).get("count", 0) == 0


def test_the_statement_shows_the_invoice_whole_the_credit_and_the_money_back(tenant):
    acme = tenant.post("/api/contacts", json={"name": "Acme", "email": "acme@example.com"}).json()
    a = inv(tenant, email="acme@example.com")
    pay(tenant, a["number"], 1000, d(-5))
    cn = credit(tenant, a["number"], line_items=[{"description": "Overcharged", "qty": 1, "price": 300, "tax_rate": "No Tax"}], issue_date=d(-4))
    b = inv(tenant, email="acme@example.com", lines=[{"description": "Next", "qty": 1, "price": 500.0, "tax_rate": "No Tax"}])
    tenant.post(f"/api/credit-notes/{cn['number']}/allocate", json={"invoice_number": b["number"], "amount": 100})
    credit(tenant, b["number"], line_items=[{"description": "Discount agreed", "qty": 1, "price": 50, "tax_rate": "No Tax"}], issue_date=d(-3))
    tenant.post(f"/api/credit-notes/{cn['number']}/refund", json={"amount": 200, "method": "cash", "refunded_on": d(-1)})
    st = tenant.get(f"/api/contacts/{acme['id']}/statement", params={"start": d(-30), "end": d(0)}).json()["statements"][0]
    kinds = [(l["kind"], l["debit"], l["credit"], l["balance"]) for l in st["lines"]]
    assert kinds == [("invoice", 1000.0, 0.0, 1000.0), ("invoice", 500.0, 0.0, 1500.0), ("payment", 0.0, 1000.0, 500.0),
                     ("credit_note", 0.0, 300.0, 200.0), ("credit_note", 0.0, 50.0, 150.0), ("refund", 200.0, 0.0, 350.0)], kinds
    assert st["closing_balance"] == 350.0 == tenant.get(f"/api/invoices/{b['number']}").json()["due"]
    assert "Credit note CN-0001 against" in st["lines"][3]["description"] and "paid back (cash)" in st["lines"][5]["description"]


def test_a_credit_note_can_be_withdrawn_until_it_is_used(tenant):
    a = inv(tenant)
    pay(tenant, a["number"], 400)
    cn = credit(tenant, a["number"])
    assert tenant.get(f"/api/invoices/{a['number']}").json()["status"] == "Paid"
    res = tenant.post(f"/api/credit-notes/{cn['number']}/void", json={"reason": "Wrong invoice"})
    assert res.status_code == 200, res.text
    assert res.json()["invoice"] == {"number": a["number"], "status": "Partially Paid", "due": 600.0}
    note = res.json()["credit_note"]
    assert note["status"] == "Void" and note["voided_on"] == d(0) and note["void_reason"] == "Wrong invoice" and note["unapplied"] == 0
    got = tenant.get(f"/api/invoices/{a['number']}").json()
    assert got["credited"] == 0 and got["credit_notes"][0]["status"] == "Void"
    assert tenant.get(f"/api/public/invoices/{a['tracking_id']}").json()["credit_notes"] == []
    assert tenant.post(f"/api/credit-notes/{cn['number']}/void", json={}).status_code == 400
    for path in ("allocate", "refund", "send"):
        assert tenant.post(f"/api/credit-notes/{cn['number']}/{path}", json={"invoice_number": a["number"]}).status_code == 400
    # The room it took is free again, and the next number carries on.
    cn2 = credit(tenant, a["number"])
    assert cn2["number"] == "CN-0002" and cn2["total"] == 1000.0 and cn2["applied"] == 600.0 and cn2["unapplied"] == 400.0
    b = inv(tenant)
    tenant.post(f"/api/credit-notes/{cn2['number']}/allocate", json={"invoice_number": b["number"], "amount": 100})
    res = tenant.post(f"/api/credit-notes/{cn2['number']}/void", json={})
    assert res.status_code == 400 and "stays on record" in res.json()["detail"]


def test_a_credit_note_goes_to_the_customer_with_the_pdf(tenant, monkeypatch):
    sent = []
    monkeypatch.setattr(main.BackgroundTasks, "add_task", lambda self, func, *a, **kw: func(*a, **kw))
    monkeypatch.setattr(main, "send_email_background", lambda *a, **kw: (sent.append((a, kw)), (True, "sent"))[1])
    a = inv(tenant, email="acme@example.com")
    cn = credit(tenant, a["number"], reason="Short delivery", line_items=[{"name": "Design", "description": "One day", "qty": 1, "price": 300, "tax_rate": "No Tax"}])
    res = tenant.post(f"/api/credit-notes/{cn['number']}/send", json={"pdf_data": "QUJD", "message": "Sorry about that."})
    assert res.status_code == 200, res.text
    assert len(sent) == 1
    args, kw = sent[0]
    to, subject, body, from_email, html = args[:5]
    assert to == "acme@example.com" and subject == f"Credit note CN-0001 against invoice {a['number']} from Acme Ltd"
    assert "Reason: Short delivery" in body and "Sorry about that." in body and f"takes £300.00 off what invoice {a['number']} was owed" in body
    assert "Total credited: £300.00" in body and args[5] == "QUJD" and args[6] == "CN-0001.pdf"
    assert "Credit note" in html and "CN-0001" in html
    note = tenant.get(f"/api/credit-notes/{cn['number']}").json()
    assert note["sent"] == d(0)
    with main.SessionLocal() as db:
        row = db.query(models.DBEmailDelivery).filter(models.DBEmailDelivery.kind == "credit_note",
                                                      models.DBEmailDelivery.reference == "CN-0001").order_by(models.DBEmailDelivery.id.desc()).first()
        assert row is not None and row.status == "sent"
    no_mail = make_invoice(tenant, status="Awaiting Payment", contact="Nobody", email="")
    cn2 = credit(tenant, no_mail["number"])
    assert tenant.post(f"/api/credit-notes/{cn2['number']}/send", json={}).status_code == 400


def test_nothing_crosses_a_business(client, account):
    tenant = account["client"]
    a = inv(tenant)
    cn = credit(tenant, a["number"])
    other_email = f"other-{account['email']}"
    client.post("/api/client/register", json={"email": other_email, "password": "Passw0rdTest", "company_name": "Other Co"})
    client.post("/api/client/login", json={"email": other_email, "password": "Passw0rdTest"})
    assert client.get("/api/credit-notes").json() == []
    assert client.get(f"/api/credit-notes/{cn['number']}").status_code == 404
    for path in ("allocate", "refund", "void", "send"):
        assert client.post(f"/api/credit-notes/{cn['number']}/{path}", json={}).status_code == 404
    assert client.post("/api/credit-notes", json={"invoice_number": a["number"]}).status_code == 404
    # Its own first note is its own CN-0001.
    mine = inv(client)
    assert credit(client, mine["number"])["number"] == "CN-0001"
    client.cookies.clear()
    assert client.get("/api/credit-notes").status_code == 401
    assert client.post("/api/credit-notes", json={"invoice_number": a["number"]}).status_code == 401
