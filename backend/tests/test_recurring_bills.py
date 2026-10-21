"""Recurring bills: a supplier bill that comes round - rent, software, a
retainer - entered on its date, once, and never lost.

The dangerous failures are the same as for recurring invoices: a bill entered
twice for one month, or a month silently missed. Nothing crosses a business.
"""
from datetime import date, timedelta

import pytest

import main
import models


@pytest.fixture(autouse=True)
def _reset():
    main.rate_limiter._hits.clear()
    with main.SessionLocal() as db:           # job claims are keyed by day
        db.query(models.DBJobRun).delete()
        db.commit()
    yield


def d(n):
    return (date.today() + timedelta(days=n)).isoformat()


def make(tenant, **overrides):
    payload = {"name": "Office rent", "vendor_name": "Landlord Ltd", "vendor_email": "rent@landlord.example",
               "category": "rent", "reference": "LEASE-1", "amount": 1000.0, "tax_amount": 200.0,
               "frequency": "monthly", "payment_terms_days": 30, "next_run": d(0)}
    payload.update(overrides)
    res = tenant.post("/api/recurring-bills", json=payload)
    assert res.status_code == 200, res.text
    return res.json()


def bills(tenant):
    return tenant.get("/api/bills").json()


def test_a_template_is_saved_with_its_total(tenant):
    t = make(tenant)
    assert t["total"] == 1200.0 and t["is_active"] is True and t["bills_created"] == 0
    assert [x["id"] for x in tenant.get("/api/recurring-bills").json()] == [t["id"]]


@pytest.mark.parametrize("change,why", [
    ({"vendor_name": "  "}, "Supplier name"),
    ({"amount": 0}, "more than nothing"),
    ({"tax_amount": -1}, "negative"),
    ({"frequency": "daily"}, "Frequency"),
    ({"next_run": "tomorrow"}, "YYYY-MM-DD"),
    ({"end_date": d(-5)}, "before the first"),
    ({"payment_terms_days": 999}, "between 0 and 365"),
])
def test_bad_input_is_refused_with_a_reason(tenant, change, why):
    payload = {"vendor_name": "X", "amount": 10, "next_run": d(0)}
    payload.update(change)
    res = tenant.post("/api/recurring-bills", json=payload)
    assert res.status_code == 400 and why in res.json()["detail"], res.text


def test_a_due_template_enters_a_draft_bill(tenant):
    make(tenant)
    main.run_due_jobs(only="recurring_bills")
    got = bills(tenant)
    assert len(got) == 1
    b = got[0]
    assert (b["vendor_name"], b["total"], b["status"], b["category"], b["reference"]) == \
        ("Landlord Ltd", 1200.0, "Draft", "rent", "LEASE-1")
    assert b["number"].startswith("BILL-") and b["issue_date"] == d(0) and b["due_date"] == d(30)


def test_auto_approve_enters_it_awaiting_payment(tenant):
    make(tenant, auto_approve=True)
    main.run_due_jobs(only="recurring_bills")
    assert bills(tenant)[0]["status"] == "Unpaid"


def test_running_twice_in_a_day_does_not_bill_twice(tenant):
    make(tenant)
    main.run_due_jobs(only="recurring_bills")
    second = main.run_due_jobs(only="recurring_bills")
    assert second[0]["status"] == "already_done"
    assert len(bills(tenant)) == 1


def test_the_schedule_moves_on_and_counts(tenant):
    t = make(tenant)
    main.run_due_jobs(only="recurring_bills")
    after = tenant.get("/api/recurring-bills").json()[0]
    assert after["next_run"] > t["next_run"] and after["bills_created"] == 1
    assert after["last_run"] == d(0) and after["last_bill_number"] == bills(tenant)[0]["number"]


def test_a_missed_period_is_caught_up_not_lost(tenant):
    make(tenant, frequency="weekly", next_run=d(-15))          # due 15, 8 and 1 days ago
    main.run_due_jobs(only="recurring_bills")
    assert len(bills(tenant)) == 3
    assert sorted(b["issue_date"] for b in bills(tenant)) == [d(-15), d(-8), d(-1)]


def test_numbers_continue_the_existing_sequence(tenant):
    tenant.post("/api/bills", json={"number": "BILL-0007", "vendor_name": "Old", "issue_date": d(-9), "due_date": d(1),
                                    "amount": 5, "total": 5, "status": "Draft"})
    make(tenant)
    main.run_due_jobs(only="recurring_bills")
    assert sorted(b["number"] for b in bills(tenant)) == ["BILL-0007", "BILL-0008"]


def test_a_template_stops_at_its_end_date(tenant):
    t = make(tenant, frequency="weekly", next_run=d(-8), end_date=d(-1))
    main.run_due_jobs(only="recurring_bills")
    assert len(bills(tenant)) == 2                              # d(-8) and d(-1); d(6) is past the end
    after = tenant.get("/api/recurring-bills").json()[0]
    assert after["is_active"] is False and t["is_active"] is True


def test_a_paused_template_enters_nothing_and_resumes(tenant):
    t = make(tenant)
    assert tenant.post(f"/api/recurring-bills/{t['id']}/pause").json()["is_active"] is False
    main.run_due_jobs(only="recurring_bills")
    assert bills(tenant) == []
    assert tenant.post(f"/api/recurring-bills/{t['id']}/resume").json()["is_active"] is True
    with main.SessionLocal() as db:
        db.query(models.DBJobRun).delete()
        db.commit()
    main.run_due_jobs(only="recurring_bills")
    assert len(bills(tenant)) == 1


def test_an_ended_template_cannot_be_resumed_without_moving_its_end_date(tenant):
    t = make(tenant, frequency="weekly", next_run=d(-8), end_date=d(-1))
    main.run_due_jobs(only="recurring_bills")
    res = tenant.post(f"/api/recurring-bills/{t['id']}/resume")
    assert res.status_code == 400 and "end date" in res.json()["detail"]
    assert tenant.post(f"/api/recurring-bills/{t['id']}/explode").status_code == 404


def test_editing_a_template_never_rewrites_bills_already_entered(tenant):
    t = make(tenant)
    main.run_due_jobs(only="recurring_bills")
    res = tenant.put(f"/api/recurring-bills/{t['id']}", json={"vendor_name": "New Landlord", "amount": 1500, "tax_amount": 0,
                                                               "next_run": d(40), "frequency": "monthly"})
    assert res.status_code == 200 and res.json()["total"] == 1500.0
    assert bills(tenant)[0]["vendor_name"] == "Landlord Ltd" and bills(tenant)[0]["total"] == 1200.0


def test_deleting_stops_future_bills_and_keeps_the_ones_entered(tenant):
    t = make(tenant)
    main.run_due_jobs(only="recurring_bills")
    assert tenant.delete(f"/api/recurring-bills/{t['id']}").status_code == 200
    assert tenant.get("/api/recurring-bills").json() == [] and len(bills(tenant)) == 1
    assert tenant.delete(f"/api/recurring-bills/{t['id']}").status_code == 404


def test_nothing_crosses_a_business(client, account):
    tenant = account["client"]
    t = make(tenant)
    other_email = f"other-{account['email']}"
    client.post("/api/client/register", json={"email": other_email, "password": "Passw0rdTest", "company_name": "Other Co"})
    client.post("/api/client/login", json={"email": other_email, "password": "Passw0rdTest"})
    assert client.get("/api/recurring-bills").json() == []
    body = {"vendor_name": "Hijack", "amount": 1, "next_run": d(0)}
    assert client.put(f"/api/recurring-bills/{t['id']}", json=body).status_code == 404
    assert client.post(f"/api/recurring-bills/{t['id']}/pause").status_code == 404
    assert client.delete(f"/api/recurring-bills/{t['id']}").status_code == 404
    main.run_due_jobs(only="recurring_bills")                     # the job enters it for its owner only
    assert client.get("/api/bills").json() == []
    client.post("/api/client/login", json={"email": account["email"], "password": account["password"]})
    assert len(client.get("/api/bills").json()) == 1 and client.get("/api/recurring-bills").json()[0]["id"] == t["id"]
    client.cookies.clear()
    assert client.get("/api/recurring-bills").status_code == 401
    assert client.post("/api/recurring-bills", json=body).status_code == 401
