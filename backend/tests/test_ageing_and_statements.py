"""Who owes what and for how long, and the statement a customer asks for.

The ageing report is per customer, bucketed by how late as of a day,
with days sales outstanding on top and a CSV out the side. A statement
is one customer's invoices, receipts and refunds in date order with a
running balance - per currency, never added across them - on screen, as
a file, by email, and monthly to everyone with a balance when the
business asks. Nothing crosses a business.
"""
from datetime import date, datetime, timedelta

import pytest

import main
from conftest import make_invoice


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(main, "send_email_background",
                        lambda to, subject, body, from_email, html_body=None, **kw: (sent.append({"to": to, "subject": subject, "body": body, "html": html_body, "from": from_email}), (True, ""))[1])
    return sent


def d(n):
    return (date.today() + timedelta(days=n)).isoformat()


def inv(tenant, contact, total, issued, due, **kw):
    return make_invoice(tenant, status="Awaiting Payment", contact=contact, issue_date=issued, due_date=due,
                        line_items=[{"description": "x", "qty": 1, "price": float(total), "tax_rate": "0%"}], **kw)


def pay(tenant, number, amount, on, **kw):
    res = tenant.post(f"/api/invoices/{number}/payments", json=dict({"amount": amount, "paid_on": on, "method": "bank_transfer"}, **kw))
    assert res.status_code == 200, res.text
    return res.json()["payment_id"]


def contact(tenant, name, email="", **kw):
    res = tenant.post("/api/contacts", json=dict({"name": name, "email": email}, **kw))
    assert res.status_code == 200, res.text
    return res.json()


def test_ageing_is_per_customer_bucketed_by_how_late(tenant):
    acme = contact(tenant, "Acme", "acme@example.com")
    inv(tenant, "Acme", 100, d(-100), d(-95))          # over 90
    inv(tenant, "Acme", 200, d(-40), d(-35))           # 31-60
    a3 = inv(tenant, "Acme", 300, d(-5), d(10))        # current
    pay(tenant, a3["number"], 50, d(-1))
    inv(tenant, "Bolt", 400, d(-20), d(-10))           # 1-30; invoicing a name makes its contact record
    paid = inv(tenant, "Bolt", 500, d(-20), d(-10))
    tenant.post(f"/api/invoices/{paid['number']}/mark-paid")
    make_invoice(tenant, contact="Draft Co", status="Draft")
    r = tenant.get("/api/reports/ageing").json()
    assert r["as_of"] == date.today().isoformat() and r["currency"] == "GBP"
    rows = {c["contact"]: c for c in r["customers"]}
    assert rows["Acme"]["over_90"] == 100.0 and rows["Acme"]["31_60"] == 200.0 and rows["Acme"]["current"] == 250.0
    assert rows["Acme"]["total"] == 550.0 and rows["Acme"]["invoices"] == 3 and rows["Acme"]["oldest_days"] == 95
    assert rows["Acme"]["contact_id"] == acme["id"] and rows["Acme"]["email"] == "acme@example.com"
    assert rows["Bolt"]["1_30"] == 400.0 and rows["Bolt"]["total"] == 400.0 and isinstance(rows["Bolt"]["contact_id"], int)
    assert "Draft Co" not in rows
    assert [c["contact"] for c in r["customers"]] == ["Acme", "Bolt"], "biggest debtor first"
    assert r["buckets"] == {"current": 250.0, "1_30": 400.0, "31_60": 200.0, "61_90": 0.0, "over_90": 100.0}
    assert r["total_outstanding"] == 950.0 and r["customers_owing"] == 2
    # DSO: receivables over the last 90 days' sales, times 90. Sales in the
    # window: 200 + 300 + 400 + 500 = 1400 (the 100 is older than 90 days).
    assert r["sales_90d"] == 1400.0 and r["dso"] == round(950 / 1400 * 90, 1)
    assert r["invoices"][0]["days_overdue"] == 95 and r["invoices"][0]["bucket"] == "over_90"


def test_ageing_as_of_an_earlier_day_forgets_later_receipts(tenant):
    a = inv(tenant, "Acme", 100, d(-60), d(-30))
    pay(tenant, a["number"], 100, d(-2))
    assert tenant.get("/api/reports/ageing").json()["customers"] == [], "paid now"
    r = tenant.get("/api/reports/ageing", params={"as_of": d(-10)}).json()
    assert r["customers"][0]["total"] == 100.0 and r["customers"][0]["1_30"] == 100.0, "was owed then, 20 days late"
    assert tenant.get("/api/reports/ageing", params={"as_of": d(-70)}).json()["customers"] == [], "not yet issued"
    assert tenant.get("/api/reports/ageing", params={"as_of": "nonsense"}).status_code == 400


def test_other_currencies_are_listed_never_added(tenant):
    inv(tenant, "Acme", 100, d(-10), d(-5))
    inv(tenant, "Acme", 900, d(-10), d(-5), currency="USD")
    r = tenant.get("/api/reports/ageing").json()
    assert r["total_outstanding"] == 100.0 and r["other_currencies"] == ["USD"]
    rows = [(c["contact"], c["currency"], c["total"]) for c in r["customers"]]
    assert rows == [("Acme", "GBP", 100.0), ("Acme", "USD", 900.0)]


def test_the_ageing_csvs(tenant):
    inv(tenant, "Acme, Ltd", 100, d(-10), d(-5))
    res = tenant.get("/api/reports/ageing.csv")
    assert res.status_code == 200 and res.headers["content-type"].startswith("text/csv")
    lines = res.text.strip().splitlines()
    assert lines[0].startswith("customer,email,currency,invoices,current,1_30") and '"Acme, Ltd"' in lines[1] and lines[1].endswith(",5")
    detail = tenant.get("/api/reports/ageing.csv", params={"detail": 1}).text.strip().splitlines()
    assert detail[0].startswith("invoice,customer,currency") and "INV-" in detail[1] and ",1_30," in detail[1]


def test_a_statement_runs_the_balance_through_invoices_receipts_and_refunds(tenant):
    acme = contact(tenant, "Acme", "acme@example.com")
    old = inv(tenant, "Acme", 100, d(-200), d(-170))                    # before the period: brought forward
    pay(tenant, old["number"], 40, d(-190))
    a = inv(tenant, "Acme", 300, d(-30), d(-1))
    pid = pay(tenant, a["number"], 200, d(-20), reference="FPS 1")
    tenant.post(f"/api/invoices/{a['number']}/payments/{pid}/refund", json={"amount": 50, "reason": "Short delivery", "refunded_on": d(-10), "tell_customer": False})
    inv(tenant, "Bolt", 999, d(-5), d(20))                              # somebody else
    inv(tenant, "Acme", 10, d(5), d(30))                                # after the period
    r = tenant.get(f"/api/contacts/{acme['id']}/statement", params={"start": d(-90), "end": d(0)}).json()
    assert r["contact"]["name"] == "Acme" and r["start"] == d(-90) and r["end"] == d(0)
    st = r["statements"][0]
    assert st["currency"] == "GBP" and st["opening_balance"] == 60.0, "100 invoiced less 40 paid, before the period"
    kinds = [(l["kind"], l["debit"], l["credit"], l["balance"]) for l in st["lines"]]
    assert kinds == [("invoice", 300.0, 0.0, 360.0), ("payment", 0.0, 200.0, 160.0), ("refund", 50.0, 0.0, 210.0)]
    assert st["lines"][1]["description"] == f"Payment on {a['number']} (bank transfer)" and st["lines"][2]["description"].endswith("Short delivery")
    assert st["closing_balance"] == 210.0 and st["invoiced"] == 300.0 and st["received"] == 200.0
    assert st["overdue"] == 210.0, "both invoices are past due at the end of the period"
    # Default period: the last ninety days.
    r2 = tenant.get(f"/api/contacts/{acme['id']}/statement").json()
    assert r2["start"] == d(-90) and r2["end"] == d(0)
    # Swapped dates are put the right way round; a bad one is refused.
    assert tenant.get(f"/api/contacts/{acme['id']}/statement", params={"start": d(0), "end": d(-90)}).json()["start"] == d(-90)
    assert tenant.get(f"/api/contacts/{acme['id']}/statement", params={"start": "x"}).status_code == 400
    csv = tenant.get(f"/api/contacts/{acme['id']}/statement.csv", params={"start": d(-90), "end": d(0)}).text.strip().splitlines()
    assert csv[0] == "date,kind,invoice,description,currency,debit,credit,balance" and "opening balance" in csv[1] and "closing balance" in csv[-1]
    assert csv[-1].endswith(",210.0")


def test_a_statement_is_per_currency(tenant):
    acme = contact(tenant, "Acme")
    inv(tenant, "Acme", 100, d(-10), d(5))
    inv(tenant, "Acme", 5000, d(-10), d(5), currency="INR")
    sts = tenant.get(f"/api/contacts/{acme['id']}/statement").json()["statements"]
    assert [(s["currency"], s["closing_balance"]) for s in sts] == [("GBP", 100.0), ("INR", 5000.0)]


def test_sending_a_statement_emails_the_customer_from_the_business(tenant, account, outbox):
    acme = contact(tenant, "Acme", "acme@example.com")
    a = inv(tenant, "Acme", 300, d(-30), d(-1))
    pay(tenant, a["number"], 100, d(-20))
    res = tenant.post(f"/api/contacts/{acme['id']}/statement/send", json={"start": d(-60), "end": d(0), "note": "Please settle the balance below."})
    assert res.status_code == 200, res.text
    assert res.json()["to"] == "acme@example.com"
    m = outbox[0]
    assert m["to"] == "acme@example.com" and m["from"].startswith("Acme Ltd <") and "Statement of account from Acme Ltd" in m["subject"]
    assert "Please settle" in m["body"] and f"Invoice {a['number']}" in m["body"] and "Balance at" in m["body"] and "200.00" in m["body"]
    assert "<table" in m["html"] and "of which overdue 200.00" in m["html"]
    logs = tenant.get("/api/audit-logs").json()
    assert any(l["action"] == "statement_sent" and "acme@example.com" in l["details"] for l in logs)
    # No address anywhere: refused. An address on the invoice but not the record: used.
    nobody = contact(tenant, "Nobody")
    inv(tenant, "Nobody", 10, d(-3), d(10), email="")
    assert tenant.post(f"/api/contacts/{nobody['id']}/statement/send", json={}).status_code == 400
    ghost = contact(tenant, "Ghost")
    inv(tenant, "Ghost", 10, d(-3), d(10), email="ghost@example.com")
    assert tenant.post(f"/api/contacts/{ghost['id']}/statement/send", json={}).json()["to"] == "ghost@example.com"
    # Nothing in the period: nothing sent.
    assert tenant.post(f"/api/contacts/{acme['id']}/statement/send", json={"start": d(-400), "end": d(-300)}).status_code == 400


def test_monthly_statements_go_on_the_first_to_those_with_a_balance_when_asked(tenant, account, outbox):
    acme = contact(tenant, "Acme", "acme@example.com")
    contact(tenant, "Settled", "settled@example.com")
    first = date.today().replace(day=1)
    last_month_end = first - timedelta(days=1)
    mid_last = last_month_end.replace(day=15).isoformat()
    inv(tenant, "Acme", 120, mid_last, mid_last)
    s = inv(tenant, "Settled", 80, mid_last, mid_last)
    pay(tenant, s["number"], 80, mid_last)          # settled within the month, so nothing to say
    now = datetime.combine(first, datetime.min.time()).replace(hour=8)
    with main.SessionLocal() as db:
        assert main.job_monthly_statements(db, now.replace(day=2)) == "not the first"
        assert main.job_monthly_statements(db, now) == "0 sent", "off unless the business asks"
    tenant.post("/api/settings", json={"monthly_statements": "1"})
    with main.SessionLocal() as db:
        assert main.job_monthly_statements(db, now) == "1 sent"
    assert [m["to"] for m in outbox] == ["acme@example.com"]
    assert last_month_end.replace(day=1).isoformat() in outbox[0]["subject"] and last_month_end.isoformat() in outbox[0]["subject"]
    assert any(name == "monthly_statements" for name, _k, _f in main.SCHEDULED_JOBS)


def test_nothing_crosses_a_business(tenant, account):
    acme = contact(tenant, "Acme", "acme@example.com")
    inv(tenant, "Acme", 100, d(-10), d(-5))
    other = f"other-{account['email']}"
    tenant.post("/api/client/logout")
    main.rate_limiter._hits.clear()
    tenant.post("/api/client/register", json={"email": other, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    tenant.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})
    inv(tenant, "Acme", 7, d(-10), d(-5))
    r = tenant.get("/api/reports/ageing").json()
    assert [c["total"] for c in r["customers"]] == [7.0]
    assert tenant.get(f"/api/contacts/{acme['id']}/statement").status_code == 404
    assert tenant.post(f"/api/contacts/{acme['id']}/statement/send", json={}).status_code in (403, 404)
