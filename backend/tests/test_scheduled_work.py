"""Work that happens without anybody clicking anything.

The dangerous failures here are duplicates: an invoice raised twice for the
same month, or a customer chased twice for the same thing. Most of this is
about those.
"""
import uuid
from datetime import date, datetime, timedelta

import pytest

import main
import models


@pytest.fixture(autouse=True)
def _reset():
    main.rate_limiter._hits.clear()
    # Job claims are keyed by day; clear them so each test starts fresh.
    with main.SessionLocal() as db:
        db.query(models.DBJobRun).delete()
        db.commit()
    yield


def make_recurring(tenant, **overrides):
    payload = {
        "name": "Monthly retainer",
        "contact": "Retainer Client",
        "email": "billing@example.com",
        "frequency": "monthly",
        "next_run": date.today().strftime("%Y-%m-%d"),
        "payment_terms_days": 14,
        "tax_type": "exclusive",
        "line_items": [{"description": "Support retainer", "qty": 1, "price": 500.0,
                        "tax_rate": "No Tax"}],
    }
    payload.update(overrides)
    res = tenant.post("/api/recurring-invoices", json=payload)
    assert res.status_code == 200, res.text
    return res.json()


# --- date arithmetic ----------------------------------------------------------

def test_monthly_lands_on_the_same_day():
    assert main.advance_date(date(2026, 1, 15), "monthly") == date(2026, 2, 15)


def test_a_short_month_clamps_instead_of_skipping():
    """The 31st must still bill in February."""
    assert main.advance_date(date(2026, 1, 31), "monthly") == date(2026, 2, 28)


@pytest.mark.parametrize("freq,expected", [
    ("weekly", date(2026, 1, 22)),
    ("monthly", date(2026, 2, 15)),
    ("quarterly", date(2026, 4, 15)),
    ("yearly", date(2027, 1, 15)),
])
def test_every_frequency_advances(freq, expected):
    assert main.advance_date(date(2026, 1, 15), freq) == expected


def test_year_rolls_over():
    assert main.advance_date(date(2026, 12, 10), "monthly") == date(2027, 1, 10)


# --- issuing ------------------------------------------------------------------

def test_a_due_template_raises_an_invoice(tenant):
    make_recurring(tenant)
    before = len(tenant.get("/api/invoices").json())

    main.run_due_jobs(only="recurring_invoices")

    invoices = tenant.get("/api/invoices").json()
    assert len(invoices) == before + 1
    raised = invoices[0]
    assert raised["to"] == "Retainer Client"
    assert raised["due"] == 500.0
    assert raised["status"] == "Draft"


def test_running_twice_in_a_day_does_not_bill_twice(tenant):
    make_recurring(tenant)
    main.run_due_jobs(only="recurring_invoices")
    count = len(tenant.get("/api/invoices").json())

    second = main.run_due_jobs(only="recurring_invoices")
    assert second[0]["status"] == "already_done"
    assert len(tenant.get("/api/invoices").json()) == count


def test_the_schedule_moves_on(tenant):
    t = make_recurring(tenant, next_run=date.today().strftime("%Y-%m-%d"))
    main.run_due_jobs(only="recurring_invoices")

    after = next(x for x in tenant.get("/api/recurring-invoices").json() if x["id"] == t["id"])
    assert after["next_run"] > t["next_run"]
    assert after["invoices_created"] == 1
    assert after["last_invoice_number"]


def test_a_template_not_yet_due_is_left_alone(tenant):
    make_recurring(tenant, next_run=(date.today() + timedelta(days=10)).strftime("%Y-%m-%d"))
    before = len(tenant.get("/api/invoices").json())
    main.run_due_jobs(only="recurring_invoices")
    assert len(tenant.get("/api/invoices").json()) == before


def test_an_inactive_template_is_left_alone(tenant):
    make_recurring(tenant, is_active=False)
    before = len(tenant.get("/api/invoices").json())
    main.run_due_jobs(only="recurring_invoices")
    assert len(tenant.get("/api/invoices").json()) == before


def test_missed_periods_are_caught_up(tenant):
    """If the app was down for three months, three invoices are owed."""
    start = date.today() - timedelta(days=95)
    make_recurring(tenant, next_run=start.strftime("%Y-%m-%d"))
    before = len(tenant.get("/api/invoices").json())

    main.run_due_jobs(only="recurring_invoices")

    raised = len(tenant.get("/api/invoices").json()) - before
    assert raised >= 3, f"expected the missed months to be caught up, got {raised}"


def test_a_template_stops_at_its_end_date(tenant):
    t = make_recurring(
        tenant,
        next_run=(date.today() - timedelta(days=40)).strftime("%Y-%m-%d"),
        end_date=(date.today() - timedelta(days=10)).strftime("%Y-%m-%d"),
    )
    main.run_due_jobs(only="recurring_invoices")
    after = next(x for x in tenant.get("/api/recurring-invoices").json() if x["id"] == t["id"])
    assert after["is_active"] is False


def test_each_invoice_gets_its_own_number(tenant):
    start = date.today() - timedelta(days=65)
    make_recurring(tenant, next_run=start.strftime("%Y-%m-%d"))
    main.run_due_jobs(only="recurring_invoices")
    numbers = [i["number"] for i in tenant.get("/api/invoices").json()]
    assert len(numbers) == len(set(numbers))


# --- validation ---------------------------------------------------------------

def test_an_unknown_frequency_is_refused(tenant):
    res = tenant.post("/api/recurring-invoices", json={
        "contact": "X", "frequency": "fortnightly", "next_run": "2026-01-01",
        "line_items": [{"description": "x", "qty": 1, "price": 10.0}],
    })
    assert res.status_code == 400


def test_an_end_date_before_the_start_is_refused(tenant):
    res = tenant.post("/api/recurring-invoices", json={
        "contact": "X", "frequency": "monthly", "next_run": "2026-06-01",
        "end_date": "2026-01-01",
        "line_items": [{"description": "x", "qty": 1, "price": 10.0}],
    })
    assert res.status_code == 400


def test_silly_payment_terms_are_refused(tenant):
    res = tenant.post("/api/recurring-invoices", json={
        "contact": "X", "frequency": "monthly", "next_run": "2026-06-01",
        "payment_terms_days": 5000,
        "line_items": [{"description": "x", "qty": 1, "price": 10.0}],
    })
    assert res.status_code == 400


def test_editing_a_template_does_not_touch_invoices_already_raised(tenant):
    t = make_recurring(tenant)
    main.run_due_jobs(only="recurring_invoices")
    issued = tenant.get("/api/invoices").json()[0]

    tenant.put(f"/api/recurring-invoices/{t['id']}", json={
        "name": "Changed", "contact": "Retainer Client", "frequency": "monthly",
        "next_run": date.today().strftime("%Y-%m-%d"), "payment_terms_days": 14,
        "line_items": [{"description": "Now much more", "qty": 1, "price": 9999.0,
                        "tax_rate": "No Tax"}],
    })
    unchanged = tenant.get(f"/api/invoices/{issued['number']}").json()
    assert unchanged["total"] == 500.0


def test_stopping_a_template_keeps_its_invoices(tenant):
    t = make_recurring(tenant)
    main.run_due_jobs(only="recurring_invoices")
    number = tenant.get("/api/invoices").json()[0]["number"]

    assert tenant.delete(f"/api/recurring-invoices/{t['id']}").status_code == 200
    assert tenant.get(f"/api/invoices/{number}").status_code == 200


def test_recurring_is_per_tenant(client, tenant):
    t = make_recurring(tenant)
    other = f"other-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/client/register", json={
        "email": other, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    client.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})

    assert client.get("/api/recurring-invoices").json() == []
    assert client.delete(f"/api/recurring-invoices/{t['id']}").status_code == 404


def test_recurring_needs_a_session(client):
    assert client.get("/api/recurring-invoices").status_code == 401


# --- chasing overdue invoices -------------------------------------------------

def overdue_invoice(tenant, days, status="Awaiting Payment", email="payer@example.com"):
    issue = date.today() - timedelta(days=days + 14)
    due = date.today() - timedelta(days=days)
    inv = tenant.post("/api/invoices", json={
        "contact": "Late Payer", "email": email,
        "issue_date": issue.strftime("%Y-%m-%d"),
        "due_date": due.strftime("%Y-%m-%d"),
        "status": status, "tax_type": "none",
        "line_items": [{"description": "Work", "qty": 1, "price": 100.0,
                        "tax_rate": "No Tax"}],
    }).json()
    return inv


def test_the_ladder_picks_the_rung_reached():
    assert main.reminder_stage_for(0) is None
    assert main.reminder_stage_for(1) == 1
    assert main.reminder_stage_for(6) == 1
    assert main.reminder_stage_for(7) == 7
    assert main.reminder_stage_for(90) == 30


def test_an_overdue_invoice_is_chased(tenant):
    inv = overdue_invoice(tenant, days=8)
    main.run_due_jobs(only="overdue_reminders")

    sent = tenant.get(f"/api/invoices/{inv['number']}/reminders").json()
    assert len(sent) == 1
    assert sent[0]["stage_days"] == 7
    assert sent[0]["sent_to"] == "payer@example.com"


def test_the_same_rung_is_never_sent_twice(tenant):
    inv = overdue_invoice(tenant, days=8)
    main.run_due_jobs(only="overdue_reminders")
    with main.SessionLocal() as db:
        db.query(models.DBJobRun).delete()
        db.commit()
    main.run_due_jobs(only="overdue_reminders")

    assert len(tenant.get(f"/api/invoices/{inv['number']}/reminders").json()) == 1


def test_an_invoice_not_yet_due_is_not_chased(tenant):
    inv = tenant.post("/api/invoices", json={
        "contact": "On Time", "email": "ontime@example.com",
        "issue_date": date.today().strftime("%Y-%m-%d"),
        "due_date": (date.today() + timedelta(days=14)).strftime("%Y-%m-%d"),
        "status": "Awaiting Payment", "tax_type": "none",
        "line_items": [{"description": "Work", "qty": 1, "price": 100.0, "tax_rate": "No Tax"}],
    }).json()
    main.run_due_jobs(only="overdue_reminders")
    assert tenant.get(f"/api/invoices/{inv['number']}/reminders").json() == []


def test_a_paid_invoice_is_never_chased(tenant):
    inv = overdue_invoice(tenant, days=40)
    tenant.post(f"/api/invoices/{inv['number']}/mark-paid")
    main.run_due_jobs(only="overdue_reminders")
    assert tenant.get(f"/api/invoices/{inv['number']}/reminders").json() == []


def test_a_draft_is_never_chased(tenant):
    inv = overdue_invoice(tenant, days=40, status="Draft")
    main.run_due_jobs(only="overdue_reminders")
    assert tenant.get(f"/api/invoices/{inv['number']}/reminders").json() == []


def test_an_invoice_with_no_email_is_skipped(tenant):
    inv = overdue_invoice(tenant, days=40, email="")
    main.run_due_jobs(only="overdue_reminders")
    assert tenant.get(f"/api/invoices/{inv['number']}/reminders").json() == []


def test_later_rungs_still_go_out(tenant):
    inv = overdue_invoice(tenant, days=8)
    main.run_due_jobs(only="overdue_reminders")

    # Push the due date back so the invoice is now 30 days overdue.
    with main.SessionLocal() as db:
        # By id, not number: invoice numbers restart per tenant, so matching
        # on the number alone picks up somebody else's INV-0001.
        row = db.query(models.DBInvoice).filter(
            models.DBInvoice.id == inv["id"]).first()
        row.due_date = (date.today() - timedelta(days=31)).strftime("%Y-%m-%d")
        db.commit()
        db.query(models.DBJobRun).delete()
        db.commit()

    main.run_due_jobs(only="overdue_reminders")
    stages = [r["stage_days"] for r in
              tenant.get(f"/api/invoices/{inv['number']}/reminders").json()]
    assert stages == [7, 30]


# --- the runner itself --------------------------------------------------------

def test_a_period_is_claimed_only_once():
    first = main.run_due_jobs(only="recurring_invoices")
    second = main.run_due_jobs(only="recurring_invoices")
    assert first[0]["status"] in ("done", "failed")
    assert second[0]["status"] == "already_done"


def test_a_job_that_throws_is_recorded_and_does_not_stop_the_others():
    def boom(db, now):
        raise RuntimeError("nope")

    main.SCHEDULED_JOBS.append(("test_explodes", main.daily_key, boom))
    try:
        results = main.run_due_jobs(only="test_explodes")
        assert results[0]["status"] == "failed"
        assert "nope" in results[0]["detail"]
    finally:
        main.SCHEDULED_JOBS[:] = [j for j in main.SCHEDULED_JOBS if j[0] != "test_explodes"]


def test_an_operator_can_run_the_jobs_now(client, tenant):
    main.rate_limiter._hits.clear()
    client.post("/api/superadmin/login", json={
        "identifier": "hello@keyroutes.co", "password": "TestSuper123"})
    res = client.post("/api/superadmin/run-jobs")
    assert res.status_code == 200, res.text
    # A subset check, so registering another job does not fail this test.
    ran = {r["job"] for r in res.json()["results"]}
    assert {"recurring_invoices", "overdue_reminders"} <= ran
    assert ran == {j[0] for j in main.SCHEDULED_JOBS}


def test_running_the_jobs_needs_an_operator(client):
    assert client.post("/api/superadmin/run-jobs").status_code == 401
    assert client.get("/api/superadmin/job-runs").status_code == 401
