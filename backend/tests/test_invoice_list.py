"""The invoice list at scale: found, filtered, sorted, paged, exported, and
acted on in bulk - on the server, so five thousand invoices are no slower
than fifty. The old whole-list route is untouched. Nothing crosses a
business.
"""
import uuid
from datetime import date, timedelta

import pytest

import main
from conftest import make_invoice


@pytest.fixture(autouse=True)
def _reset():
    main.rate_limiter._hits.clear()
    yield


def d(n):
    return (date.today() + timedelta(days=n)).isoformat()


def inv(tenant, contact, total, issued, due, status="Awaiting Payment", **kw):
    return make_invoice(tenant, status=status, contact=contact, issue_date=issued, due_date=due, tax_type="none",
                        line_items=[{"description": "x", "qty": 1, "price": float(total), "tax_rate": "No Tax"}], **kw)


def seed(tenant):
    a = inv(tenant, "Acme", 100, d(-40), d(-10))                       # overdue
    b = inv(tenant, "Bolt", 200, d(-20), d(10))                        # open, not due
    c = inv(tenant, "Acme", 300, d(-5), d(25), status="Draft")         # draft
    p = inv(tenant, "Cray", 400, d(-30), d(-1))                        # paid
    tenant.post(f"/api/invoices/{p['number']}/payments", json={"amount": 400, "paid_on": d(-2), "method": "cash"})
    e = inv(tenant, "Acme", 50, d(-60), d(-30), reference="PO-77", email="acme@example.com")   # overdue, older
    return a, b, c, p, e


def rows(tenant, **params):
    res = tenant.get("/api/invoice-list", params=params)
    assert res.status_code == 200, res.text
    return res.json()


def test_the_list_is_paged_sorted_and_summed_on_the_server(tenant):
    a, b, c, p, e = seed(tenant)
    page = rows(tenant, limit=2)
    assert [i["number"] for i in page["items"]] == [e["number"], p["number"]], "newest first"
    assert page["total"] == 5 and page["limit"] == 2 and page["offset"] == 0
    assert page["summary"] == {"count": 5, "owed": 350.0, "overdue_owed": 150.0, "overdue_count": 2, "paid": 400.0}
    page2 = rows(tenant, limit=2, offset=2)
    assert [i["number"] for i in page2["items"]] == [c["number"], b["number"]]
    assert [i["number"] for i in rows(tenant, limit=2, offset=4)["items"]] == [a["number"]]
    assert rows(tenant, sort="amount", dir="desc")["items"][0]["number"] == p["number"] or rows(tenant, sort="amount", dir="desc")["items"][0]["due"] == 300.0
    assert [i["to"] for i in rows(tenant, sort="customer", dir="asc")["items"]][:3] == ["Acme", "Acme", "Acme"]
    assert [i["date"] for i in rows(tenant, sort="date", dir="asc")["items"]] == [d(-60), d(-40), d(-30), d(-20), d(-5)]
    assert rows(tenant, limit=9999)["limit"] == 200
    assert tenant.get("/api/invoice-list", params={"sort": "colour"}).status_code == 400
    assert tenant.get("/api/invoice-list", params={"status": "lost"}).status_code == 400


def test_filters_by_status_search_customer_and_dates(tenant):
    a, b, c, p, e = seed(tenant)
    assert {i["number"] for i in rows(tenant, status="overdue")["items"]} == {a["number"], e["number"]}
    assert {i["number"] for i in rows(tenant, status="unpaid")["items"]} == {a["number"], b["number"], e["number"]}
    assert [i["number"] for i in rows(tenant, status="draft")["items"]] == [c["number"]]
    assert [i["number"] for i in rows(tenant, status="paid")["items"]] == [p["number"]]
    assert rows(tenant, status="awaiting-payment")["total"] == 3
    assert {i["number"] for i in rows(tenant, q="acme")["items"]} == {a["number"], c["number"], e["number"]}, "name, any case"
    assert [i["number"] for i in rows(tenant, q="po-77")["items"]] == [e["number"]], "reference"
    assert [i["number"] for i in rows(tenant, q="acme@example")["items"]] == [e["number"]], "email"
    assert [i["number"] for i in rows(tenant, q=a["number"])["items"]] == [a["number"]], "number"
    assert rows(tenant, customer="Bolt")["total"] == 1
    assert {i["number"] for i in rows(tenant, start=d(-35), end=d(-10))["items"]} == {p["number"], b["number"]}
    assert rows(tenant, status="overdue", q="acme", start=d(-45))["total"] == 1
    summary = rows(tenant, status="overdue")["summary"]
    assert summary["count"] == 2 and summary["owed"] == 150.0
    assert tenant.get("/api/invoice-list", params={"start": "yesterday"}).status_code == 400


def test_the_match_comes_down_as_a_file(tenant):
    a, b, c, p, e = seed(tenant)
    res = tenant.get("/api/invoice-list.csv", params={"status": "overdue", "sort": "date", "dir": "asc"})
    assert res.status_code == 200 and res.headers["content-type"].startswith("text/csv")
    assert f"invoices-overdue-{d(0)}.csv" in res.headers.get("content-disposition", "")
    lines = res.text.strip().splitlines()
    assert lines[0] == "Number,Ref,Customer,Email,Issued,Due date,Status,Currency,Total,Paid,Due,Days overdue,Sent"
    assert len(lines) == 3 and lines[1].startswith(f"{e['number']},PO-77,Acme,acme@example.com,{d(-60)},{d(-30)},Awaiting Payment,GBP,50.00,0.00,50.00,30,")
    assert lines[2].split(",")[0] == a["number"] and lines[2].split(",")[11] == "10"


def test_bulk_actions_do_each_one_and_say_which_could_not_be(tenant, monkeypatch):
    monkeypatch.setattr(main.BackgroundTasks, "add_task", lambda self, func, *a, **kw: None)
    monkeypatch.setattr(main, "send_email_background", lambda *a, **kw: (True, "sent"))
    a, b, c, p, e = seed(tenant)
    res = tenant.post("/api/invoice-list/bulk", json={"numbers": [a["number"], c["number"], "INV-9999"], "action": "mark_sent"})
    assert res.status_code == 200, res.text
    assert res.json()["done"] == [a["number"], c["number"]] and res.json()["failed"] == [{"number": "INV-9999", "why": "Invoice not found"}]
    assert tenant.get(f"/api/invoices/{a['number']}").json()["status"] == "Sent" and tenant.get(f"/api/invoices/{c['number']}").json()["status"] == "Sent"
    res = tenant.post("/api/invoice-list/bulk", json={"numbers": [a["number"]], "action": "mark_sent"})
    assert res.json()["done"] == [] and "Already sent" in res.json()["failed"][0]["why"]
    # Reminders go to the ones that can take one; the rest say why.
    res = tenant.post("/api/invoice-list/bulk", json={"numbers": [a["number"], e["number"], p["number"], b["number"]], "action": "chase"})
    assert res.status_code == 200, res.text
    assert set(res.json()["done"]) == {a["number"], e["number"], b["number"]} and res.json()["failed"][0]["number"] == p["number"]
    assert len(tenant.get(f"/api/invoices/{a['number']}/reminders").json()) == 1
    # Sending needs an address the invoice has.
    quiet = inv(tenant, "Quiet", 10, d(-1), d(10), email="")
    res = tenant.post("/api/invoice-list/bulk", json={"numbers": [b["number"], quiet["number"]], "action": "send"})
    assert res.status_code == 200, res.text
    assert res.json()["done"] == [b["number"]] and "email" in res.json()["failed"][0]["why"].lower()
    # Only drafts go in the bin this way.
    draft2 = inv(tenant, "Acme", 5, d(0), d(10), status="Draft")
    res = tenant.post("/api/invoice-list/bulk", json={"numbers": [draft2["number"], b["number"]], "action": "delete_drafts"})
    assert res.json()["done"] == [draft2["number"]] and "draft" in res.json()["failed"][0]["why"].lower()
    assert tenant.get(f"/api/invoices/{draft2['number']}").status_code == 404
    for bad in ({"numbers": [], "action": "send"}, {"numbers": [a["number"]], "action": "burn"}, {"numbers": ["x"] * 101, "action": "send"}):
        assert tenant.post("/api/invoice-list/bulk", json=bad).status_code == 400, bad


def test_the_old_list_still_comes_down_whole(tenant):
    seed(tenant)
    assert len(tenant.get("/api/invoices").json()) == 5


def test_nothing_crosses_a_business(client, account):
    tenant = account["client"]
    a, b, c, p, e = seed(tenant)
    other_email = f"other-{account['email']}"
    client.post("/api/client/register", json={"email": other_email, "password": "Passw0rdTest", "company_name": "Other Co"})
    client.post("/api/client/login", json={"email": other_email, "password": "Passw0rdTest"})
    assert client.get("/api/invoice-list").json()["total"] == 0
    assert client.get("/api/invoice-list.csv").text.strip().splitlines()[1:] == []
    res = client.post("/api/invoice-list/bulk", json={"numbers": [a["number"]], "action": "mark_sent"})
    assert res.json()["done"] == [] and res.json()["failed"][0]["why"] == "Invoice not found"
    client.cookies.clear()
    assert client.get("/api/invoice-list").status_code == 401
    assert client.get("/api/invoice-list.csv").status_code == 401
    assert client.post("/api/invoice-list/bulk", json={"numbers": ["x"], "action": "send"}).status_code == 401
