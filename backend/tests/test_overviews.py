"""The Sales and Purchases overview screens: draft, awaiting payment, overdue
and finished, counted on the server, for one business only."""
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


def inv(tenant, contact, total, issued, due, status="Awaiting Payment"):
    return make_invoice(tenant, status=status, contact=contact, issue_date=issued, due_date=due, tax_type="none",
                        line_items=[{"description": "x", "qty": 1, "price": float(total), "tax_rate": "No Tax"}])


def bill(tenant, number, vendor, total, due, status="Unpaid", paid=0):
    res = tenant.post("/api/bills", json={"number": number, "vendor_name": vendor, "issue_date": d(-30), "due_date": d(due),
                                          "amount": total, "tax_amount": 0, "total": total, "status": status,
                                          "amount_paid": paid})
    assert res.status_code == 200, res.text


def test_sales_overview_splits_draft_awaiting_overdue_and_done(tenant):
    inv(tenant, "Acme", 100, d(-40), d(-10))                      # overdue
    inv(tenant, "Acme", 50, d(-30), d(-5))                        # overdue
    inv(tenant, "Bolt", 200, d(-2), d(3))                         # awaiting, due this week
    inv(tenant, "Cray", 80, d(-2), d(10))                         # awaiting, due next week
    inv(tenant, "Dyn", 300, d(-1), d(25), status="Draft")         # draft
    p = inv(tenant, "Eve", 400, d(-30), d(-1))
    tenant.post(f"/api/invoices/{p['number']}/payments", json={"amount": 400, "paid_on": d(-2), "method": "cash"})
    o = tenant.get("/api/sales/overview").json()
    assert o["draft"] == {"count": 1, "amount": 300.0}
    assert o["overdue"] == {"count": 2, "amount": 150.0}
    assert o["awaiting"] == {"count": 2, "amount": 280.0}
    assert o["done"] == {"count": 1, "amount": 400.0}
    assert o["due_this_week"] == 200.0 and o["due_next_week"] == 80.0
    assert o["customers_owing_most"][:2] == [{"name": "Bolt", "owed": 200.0}, {"name": "Acme", "owed": 150.0}]


def test_purchases_overview_counts_what_is_still_owed(tenant):
    bill(tenant, "B-1", "Paper Co", 100, -5)                       # overdue
    bill(tenant, "B-2", "Paper Co", 60, 3, paid=20)                # awaiting, 40 left
    bill(tenant, "B-3", "Tea Ltd", 25, 9, status="Draft")          # draft
    bill(tenant, "B-4", "Tea Ltd", 75, -20, status="Paid", paid=75)
    with main.SessionLocal() as db:       # the bills API has no part-payment, so write it as a payment run would
        db.query(main.models.DBBill).filter(main.models.DBBill.number == "B-2").update({"amount_paid": 20.0})
        db.commit()
    o = tenant.get("/api/purchases/overview").json()
    assert o["draft"] == {"count": 1, "amount": 25.0}
    assert o["overdue"] == {"count": 1, "amount": 100.0}
    assert o["awaiting"] == {"count": 1, "amount": 40.0}
    assert o["done"] == {"count": 1, "amount": 75.0}
    assert o["due_this_week"] == 40.0
    assert o["suppliers_owed_most"][0] == {"name": "Paper Co", "owed": 140.0}


def test_overviews_need_a_signed_in_business_and_do_not_cross(client, account):
    other = account["client"]
    inv(other, "Acme", 100, d(-40), d(-10))
    client.cookies.clear()
    assert client.get("/api/sales/overview").status_code == 401
    assert client.get("/api/purchases/overview").status_code == 401


def test_suppliers_are_worked_out_from_bills_and_matched_loosely(tenant):
    bill(tenant, "S-1", "Paper Co", 100, -5)                       # overdue
    bill(tenant, "S-2", "paper  co ", 60, 3)                        # same supplier, other spelling
    bill(tenant, "S-3", "Tea Ltd", 25, 9, status="Draft")           # a draft is not owed
    bill(tenant, "S-4", "Tea Ltd", 75, -20, status="Paid", paid=75)
    got = tenant.get("/api/purchases/suppliers").json()
    names = [s["name"] for s in got["suppliers"]]
    assert names == ["Paper Co", "Tea Ltd"], "one Paper Co, most owed first"
    paper, tea = got["suppliers"]
    assert (paper["bills"], paper["billed"], paper["owed"], paper["overdue"]) == (2, 160.0, 160.0, 1)
    assert (tea["bills"], tea["billed"], tea["owed"]) == (2, 100.0, 0.0)


def test_suppliers_need_a_signed_in_business(client):
    client.cookies.clear()
    assert client.get("/api/purchases/suppliers").status_code == 401
