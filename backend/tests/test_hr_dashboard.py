"""The HR portal's landing page.

There wasn't one. HR opened on the employee list, so a leave request waiting on
a decision, a document sitting unreviewed, or somebody who never clocked in
were all only found by going looking. This is one call that answers "what needs
me today", built around outstanding work rather than headline numbers.

Nothing here is stored: every figure is counted from the records at the moment
it is asked for, so it cannot drift out of step with them.
"""
import uuid
from datetime import datetime, timedelta

import pytest

import main
import models
from conftest import make_employee


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


TODAY = datetime.now().strftime("%Y-%m-%d")


def board(tenant):
    res = tenant.get("/api/hr/dashboard")
    assert res.status_code == 200, res.text
    return res.json()


def queue(data, key):
    return next(w["count"] for w in data["waiting_on_you"] if w["key"] == key)


def client_id(account):
    with main.SessionLocal() as db:
        return db.query(models.DBClient).filter(
            models.DBClient.email == account["email"]).first().id


def set_status(emp_id, status):
    """The create endpoint always starts people at onboarding, which is right -
    a status is reached, not declared. Tests that need a later one set it."""
    with main.SessionLocal() as db:
        row = db.query(models.DBEmployee).filter(
            models.DBEmployee.id == emp_id).first()
        row.status = status
        db.commit()


def staffed(tenant, status, **kw):
    emp = make_employee(tenant, **kw)
    set_status(emp["id"], status)
    return emp


def add_leave(account, emp_id, start, end, status="approved", leave_type="annual"):
    with main.SessionLocal() as db:
        db.add(models.DBLeaveRequest(
            client_id=client_id(account), employee_id=emp_id, leave_type=leave_type,
            start_date=start, end_date=end, days=1.0, status=status))
        db.commit()


# --- an empty tenant is not an error ------------------------------------------

def test_a_new_tenant_gets_zeroes_rather_than_a_blank_page(tenant):
    data = board(tenant)
    assert data["headcount"]["total"] == 0
    assert data["today"]["expected"] == 0
    assert data["waiting_total"] == 0
    assert data["coming_up"]["starting"] == []


def test_it_is_the_tenants_own_numbers(tenant):
    from fastapi.testclient import TestClient

    make_employee(tenant)
    make_employee(tenant)
    assert board(tenant)["headcount"]["total"] == 2

    with TestClient(main.app) as other:
        main.rate_limiter._hits.clear()
        email = f"other-{uuid.uuid4().hex[:10]}@example.com"
        other.post("/api/client/register", json={
            "email": email, "password": "Passw0rdTest", "company_name": "Other Ltd"})
        other.post("/api/client/login", json={
            "email": email, "password": "Passw0rdTest"})
        assert board(other)["headcount"]["total"] == 0


def test_signing_out_shuts_it(client):
    assert client.get("/api/hr/dashboard").status_code in (401, 403)


# --- headcount ----------------------------------------------------------------

def test_headcount_is_split_by_where_people_are(tenant):
    staffed(tenant, "active")
    staffed(tenant, "active")
    staffed(tenant, "onboarding")
    staffed(tenant, "offboarding")
    staffed(tenant, "terminated")

    h = board(tenant)["headcount"]
    assert h == {"total": 5, "active": 2, "onboarding": 1, "offboarding": 1}


# --- today --------------------------------------------------------------------

def test_people_who_have_left_are_not_expected_in(tenant):
    staffed(tenant, "active")
    staffed(tenant, "onboarding")
    staffed(tenant, "terminated")
    assert board(tenant)["today"]["expected"] == 2


def test_clocking_in_moves_somebody_out_of_unaccounted_for(tenant):
    emp = make_employee(tenant, first_name="Ada", last_name="Reid")
    assert board(tenant)["today"]["unaccounted_count"] == 1

    res = tenant.post("/api/attendance/clock-in", json={"employee_id": emp["id"]})
    assert res.status_code == 200, res.text

    data = board(tenant)["today"]
    assert data["clocked_in"] == 1
    assert data["unaccounted_count"] == 0
    assert "Ada Reid" not in data["unaccounted_for"]


def test_somebody_on_leave_is_not_unaccounted_for_either(tenant, account):
    """They are accounted for - they told you. Two different situations, and
    only one of them is worth chasing."""
    emp = make_employee(tenant, first_name="Ada", last_name="Reid")
    add_leave(account, emp["id"], TODAY, TODAY)

    data = board(tenant)["today"]
    assert data["unaccounted_count"] == 0
    assert [p["name"] for p in data["on_leave"]] == ["Ada Reid"]


def test_a_leave_that_straddles_today_counts(tenant, account):
    """Counting only leave that starts today would show somebody back on day
    two of a fortnight off."""
    emp = make_employee(tenant)
    started = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
    ends = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")
    add_leave(account, emp["id"], started, ends)

    assert len(board(tenant)["today"]["on_leave"]) == 1


def test_leave_that_has_not_been_approved_does_not_excuse_anybody(tenant, account):
    emp = make_employee(tenant)
    add_leave(account, emp["id"], TODAY, TODAY, status="pending")

    data = board(tenant)["today"]
    assert data["on_leave"] == []
    assert data["unaccounted_count"] == 1


def test_leave_finished_yesterday_does_not_linger(tenant, account):
    emp = make_employee(tenant)
    a = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
    b = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    add_leave(account, emp["id"], a, b)
    assert board(tenant)["today"]["on_leave"] == []


def test_the_named_list_is_capped_but_the_count_is_not(tenant):
    """Twenty names down the side of a card helps nobody; the number still has
    to be right."""
    for _ in range(11):
        make_employee(tenant)
    data = board(tenant)["today"]
    assert data["unaccounted_count"] == 11
    assert len(data["unaccounted_for"]) == 8


# --- the queues ---------------------------------------------------------------

def test_a_pending_leave_request_shows_up_as_work(tenant, account):
    emp = make_employee(tenant)
    assert queue(board(tenant), "leave") == 0
    add_leave(account, emp["id"], TODAY, TODAY, status="pending")
    assert queue(board(tenant), "leave") == 1


def test_deciding_it_takes_it_off_the_list(tenant, account):
    emp = make_employee(tenant)
    add_leave(account, emp["id"], TODAY, TODAY, status="pending")
    with main.SessionLocal() as db:
        row = db.query(models.DBLeaveRequest).filter(
            models.DBLeaveRequest.employee_id == emp["id"]).first()
        row.status = "approved"
        db.commit()
    assert queue(board(tenant), "leave") == 0


def test_an_unanswered_staff_request_is_counted(tenant):
    emp = make_employee(tenant, password="EmpPass123")
    main.rate_limiter._hits.clear()
    tenant.post("/api/employee/auth/login",
                json={"email": emp["email"], "password": "EmpPass123"})
    tenant.post("/api/employee/requests", json={
        "subject": "Payslip query", "message": "August tax looks high."})

    main.rate_limiter._hits.clear()
    assert queue(board(tenant), "requests") == 1


def test_the_total_is_the_sum_of_the_queues(tenant, account):
    """Taking somebody on raises document requests of its own, so the total
    moves for reasons this test is not about. What has to hold is that it is
    the sum, and that it follows."""
    emp = make_employee(tenant)
    before = board(tenant)
    assert before["waiting_total"] == sum(w["count"] for w in before["waiting_on_you"])

    add_leave(account, emp["id"], TODAY, TODAY, status="pending")
    add_leave(account, emp["id"], TODAY, TODAY, status="pending")

    after = board(tenant)
    assert after["waiting_total"] == sum(w["count"] for w in after["waiting_on_you"])
    assert after["waiting_total"] == before["waiting_total"] + 2


def test_every_queue_names_the_page_that_clears_it(tenant):
    """A count nobody can act on is just a number."""
    for row in board(tenant)["waiting_on_you"]:
        assert row["view"].endswith("-view"), row
        assert row["label"]


# --- what lands soon ----------------------------------------------------------

def test_somebody_starting_next_week_is_flagged(tenant):
    soon = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d")
    make_employee(tenant, first_name="Nia", last_name="Okoro",
                  start_date=soon, job_title="Analyst")

    starting = board(tenant)["coming_up"]["starting"]
    assert [p["name"] for p in starting] == ["Nia Okoro"]
    assert starting[0]["date"] == soon


def test_somebody_who_started_last_month_is_not(tenant):
    past = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    make_employee(tenant, start_date=past)
    assert board(tenant)["coming_up"]["starting"] == []


def test_a_start_date_months_out_is_not_yet_news(tenant):
    far = (datetime.now() + timedelta(days=60)).strftime("%Y-%m-%d")
    make_employee(tenant, start_date=far)
    assert board(tenant)["coming_up"]["starting"] == []


def test_an_employee_with_no_start_date_does_not_appear(tenant):
    make_employee(tenant, start_date="")
    assert board(tenant)["coming_up"]["starting"] == []
