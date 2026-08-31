"""What a person can see of the calendar.

It was HR's alone, so an employee could not find out when the office is closed
- and was booking annual leave over public holidays, spending days they did not
need to spend. Their own goal deadlines, document expiries and onboarding dates
were on it too, and none of it reachable.

The employee list is assembled rather than filtered. Filtering leaks by
omission: the day somebody adds an event kind, it appears on the staff calendar
because nobody remembered to exclude it. So the tests check both that the right
things arrive and that the wrong ones never do.
"""
from datetime import datetime, timedelta

import pytest

import main
import models
from conftest import make_employee


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


TODAY = datetime.now().date()
THIS_MONTH = TODAY.replace(day=1)


def in_month(day):
    """A date inside the current month, whatever today is."""
    return THIS_MONTH.replace(day=day).strftime("%Y-%m-%d")


def sign_in(client, emp, password="EmpPass123"):
    main.rate_limiter._hits.clear()
    res = client.post("/api/employee/auth/login",
                      json={"email": emp["email"], "password": password})
    assert res.status_code == 200, res.text
    return client


def client_id(account):
    with main.SessionLocal() as db:
        return db.query(models.DBClient).filter(
            models.DBClient.email == account["email"]).first().id


@pytest.fixture
def staff(tenant):
    return make_employee(tenant, first_name="Ada", last_name="Reid",
                         password="EmpPass123")


def add_holiday(account, date, name="Bank Holiday", optional=False, recurring=False):
    with main.SessionLocal() as db:
        db.add(models.DBHoliday(client_id=client_id(account), date=date, name=name,
                                optional=optional, recurring=recurring))
        db.commit()


def add_leave(account, emp_id, start, end, status="approved", kind="annual"):
    with main.SessionLocal() as db:
        db.add(models.DBLeaveRequest(
            client_id=client_id(account), employee_id=emp_id, leave_type=kind,
            start_date=start, end_date=end, days=1.0, status=status))
        db.commit()


def events(tenant, **params):
    res = tenant.get("/api/employee/calendar", params=params)
    assert res.status_code == 200, res.text
    return res.json()["events"]


def titles(rows):
    return " | ".join(r["title"] for r in rows)


# --- the shape of it ----------------------------------------------------------

def test_an_empty_month_is_not_an_error(tenant, staff):
    """Asked about a month with nothing in it, deliberately far off.

    This used to ask about the current month and assume it was empty, which
    was only ever true by accident: creating an employee raises document
    requests due a week after their start date, so from the 1st of a month
    those land in the month being asked about. It passed in August and failed
    on the 1st of September, having tested nothing about emptiness in
    between."""
    sign_in(tenant, staff)
    body = tenant.get("/api/employee/calendar",
                      params={"start": "2032-04-01", "end": "2032-04-30"}).json()
    assert body["events"] == []
    assert body["start"] and body["end"]


def test_it_defaults_to_this_month(tenant, staff):
    sign_in(tenant, staff)
    body = tenant.get("/api/employee/calendar").json()
    assert body["start"] == THIS_MONTH.strftime("%Y-%m-%d")


def test_a_backwards_range_is_refused(tenant, staff):
    sign_in(tenant, staff)
    res = tenant.get("/api/employee/calendar",
                     params={"start": "2026-08-10", "end": "2026-08-01"})
    assert res.status_code == 400


def test_more_than_a_year_is_refused(tenant, staff):
    """A grid asks for a month; anything asking for a decade is not a grid."""
    sign_in(tenant, staff)
    res = tenant.get("/api/employee/calendar",
                     params={"start": "2020-01-01", "end": "2030-01-01"})
    assert res.status_code == 400


def test_the_calendar_needs_a_session(client):
    assert client.get("/api/employee/calendar").status_code == 401


# --- what belongs to everybody ------------------------------------------------

def test_company_holidays_are_on_it(tenant, staff, account):
    add_holiday(account, in_month(12), name="Summer Bank Holiday")
    sign_in(tenant, staff)
    rows = events(tenant)
    assert any(r["title"] == "Summer Bank Holiday" for r in rows), titles(rows)
    # Matched on the whole title. "Bank" as a substring also catches the
    # "Bank details" document every new employee is asked for, which is not a
    # holiday and never was - the filter was finding it and blaming this.
    assert all(r["kind"] == "holiday"
               for r in rows if r["title"] == "Summer Bank Holiday")


def test_an_optional_holiday_says_the_office_is_open(tenant, staff, account):
    """Optional means you may work it, so it still costs a day to take."""
    add_holiday(account, in_month(13), name="Optional Day", optional=True)
    sign_in(tenant, staff)
    row = next(r for r in events(tenant) if r["title"] == "Optional Day")
    assert "open" in row["subtitle"].lower()


def test_what_hr_puts_on_the_calendar_is_visible(tenant, staff, account):
    with main.SessionLocal() as db:
        db.add(models.DBCalendarEvent(
            client_id=client_id(account), date=in_month(14),
            title="All-hands", description="Main room", kind="meeting"))
        db.commit()
    sign_in(tenant, staff)
    assert any(r["title"] == "All-hands" for r in events(tenant))


# --- their own things ---------------------------------------------------------

def test_their_own_leave_is_theirs_in_full(tenant, staff, account):
    add_leave(account, staff["id"], in_month(5), in_month(6), kind="annual")
    sign_in(tenant, staff)
    row = next(r for r in events(tenant) if r["kind"] == "leave")
    assert row["mine"] is True
    assert "annual" in row["title"]


def test_their_own_pending_leave_shows_as_undecided(tenant, staff, account):
    add_leave(account, staff["id"], in_month(7), in_month(8), status="pending")
    sign_in(tenant, staff)
    row = next(r for r in events(tenant) if r["kind"] == "leave")
    assert "awaiting" in row["subtitle"].lower()


def test_their_goal_deadline_is_on_it(tenant, staff, account):
    with main.SessionLocal() as db:
        db.add(models.DBEmployeeGoal(
            client_id=client_id(account), employee_id=staff["id"],
            title="Close 10 tickets", target_value=10, current_value=4,
            unit="tickets", due_date=in_month(20), status="active"))
        db.commit()
    sign_in(tenant, staff)
    row = next(r for r in events(tenant) if r["kind"] == "goal")
    assert row["title"] == "Close 10 tickets"
    assert row["mine"] is True


def test_a_document_expiry_is_on_it(tenant, staff, account):
    with main.SessionLocal() as db:
        db.add(models.DBDocumentRequest(
            client_id=client_id(account), employee_id=staff["id"],
            name="Right to work", status="approved", expires_on=in_month(22)))
        db.commit()
    sign_in(tenant, staff)
    row = next(r for r in events(tenant) if r["kind"] == "document_expiry")
    assert row["title"] == "Right to work"


def test_every_entry_says_where_to_go_or_says_nothing(tenant, staff, account):
    """A row that names a tab must name one that exists."""
    add_leave(account, staff["id"], in_month(5), in_month(6))
    add_holiday(account, in_month(12))
    sign_in(tenant, staff)
    known = {"leave", "goals", "documents", "onboarding", "payslips", ""}
    for row in events(tenant):
        assert row.get("tab", "") in known, row


# --- and what is not theirs ---------------------------------------------------

def test_a_colleagues_leave_says_only_that_they_are_away(tenant, account):
    """The type of leave is health information about somebody else - "sick"
    beside a name is not a peer's to read."""
    mine = make_employee(tenant, first_name="Ada", last_name="Reid",
                         password="EmpPass123")
    theirs = make_employee(tenant, first_name="Sam", last_name="Ali")
    add_leave(account, theirs["id"], in_month(9), in_month(10), kind="sick")

    sign_in(tenant, mine)
    row = next(r for r in events(tenant) if r["kind"] == "leave")
    assert row["mine"] is False
    assert "Sam Ali" in row["title"]
    assert "sick" not in (row["title"] + row["subtitle"]).lower()


def test_a_colleagues_undecided_leave_is_not_anybodys_business(tenant, account):
    """It is not yet a fact about them, and a refused request that a colleague
    already saw is worse than one they never did."""
    mine = make_employee(tenant, first_name="Ada", last_name="Reid",
                         password="EmpPass123")
    theirs = make_employee(tenant, first_name="Sam", last_name="Ali")
    add_leave(account, theirs["id"], in_month(9), in_month(10), status="pending")

    sign_in(tenant, mine)
    assert [r for r in events(tenant) if r["kind"] == "leave"] == []


def test_a_colleagues_goal_never_appears(tenant, account):
    mine = make_employee(tenant, first_name="Ada", last_name="Reid",
                         password="EmpPass123")
    theirs = make_employee(tenant, first_name="Sam", last_name="Ali")
    with main.SessionLocal() as db:
        db.add(models.DBEmployeeGoal(
            client_id=client_id(account), employee_id=theirs["id"],
            title="Secret target", target_value=10, current_value=1,
            unit="x", due_date=in_month(18), status="active"))
        db.commit()

    sign_in(tenant, mine)
    rows = events(tenant)
    assert "Secret target" not in titles(rows)


def test_interviews_are_not_on_the_staff_calendar(tenant, account):
    """Recruitment is HR's, and a scheduled interview can say who is being
    replaced."""
    mine = make_employee(tenant, first_name="Ada", last_name="Reid",
                         password="EmpPass123")
    when = (TODAY + timedelta(days=2)).strftime("%Y-%m-%d 10:00")
    with main.SessionLocal() as db:
        db.add(models.DBInterview(
            client_id=client_id(account), submission_id=1, round_name="Final round",
            scheduled_at=when, status="scheduled"))
        db.commit()

    sign_in(tenant, mine)
    rows = events(tenant)
    assert "Final round" not in titles(rows)
    assert not any(r["kind"] == "interview" for r in rows)


def test_the_calendar_stops_at_the_tenant(tenant, account):
    """Another company's holidays are not this company's days off."""
    import uuid
    from fastapi.testclient import TestClient

    mine = make_employee(tenant, first_name="Ada", last_name="Reid",
                         password="EmpPass123")

    with TestClient(main.app) as other:
        main.rate_limiter._hits.clear()
        email = f"other-{uuid.uuid4().hex[:8]}@example.com"
        other.post("/api/client/register", json={
            "email": email, "password": "Passw0rdTest", "company_name": "Other Ltd"})
        other.post("/api/client/login", json={
            "email": email, "password": "Passw0rdTest"})
        add_holiday({"email": email}, in_month(15), name="Their Day")

    sign_in(tenant, mine)
    assert "Their Day" not in titles(events(tenant))


# --- holidays on their own ----------------------------------------------------

def test_holidays_can_be_read_directly(tenant, staff, account):
    """The most-asked question in a staff portal, and it had no answer."""
    add_holiday(account, in_month(12), name="Summer Bank Holiday")
    sign_in(tenant, staff)
    body = tenant.get("/api/employee/holidays").json()
    assert body["year"] == TODAY.year
    assert [h["name"] for h in body["holidays"]] == ["Summer Bank Holiday"]
    assert body["holidays"][0]["office_closed"] is True


def test_an_optional_day_is_not_a_closure(tenant, staff, account):
    add_holiday(account, in_month(16), name="Optional Day", optional=True)
    sign_in(tenant, staff)
    row = tenant.get("/api/employee/holidays").json()["holidays"][0]
    assert row["office_closed"] is False


def test_a_recurring_holiday_lands_in_the_year_asked_for(tenant, staff, account):
    """Christmas was entered once against some past year and still closes the
    office this one."""
    add_holiday(account, "2020-12-25", name="Christmas", recurring=True)
    sign_in(tenant, staff)
    body = tenant.get("/api/employee/holidays", params={"year": 2027}).json()
    assert body["holidays"][0]["date"] == "2027-12-25"


def test_holidays_need_a_session(client):
    assert client.get("/api/employee/holidays").status_code == 401


# --- notices ------------------------------------------------------------------

def test_an_announcement_can_be_read_again(tenant, staff, account):
    """It went out as a notification, and a notification once dismissed is
    gone."""
    res = tenant.post("/api/hr/announcements", json={
        "title": "Office closed Friday", "message": "Boiler repairs.",
        "audience": "everyone"})
    assert res.status_code == 200, res.text

    sign_in(tenant, staff)
    rows = tenant.get("/api/employee/announcements").json()
    assert [r["title"] for r in rows] == ["Office closed Friday"]
    assert rows[0]["message"] == "Boiler repairs."


def test_only_announcements_appear_there(tenant, staff, account):
    """The bell carries everything; this page is what the company said."""
    with main.SessionLocal() as db:
        emp = db.query(models.DBEmployee).filter(
            models.DBEmployee.id == staff["id"]).first()
        main.notify_employee(db, emp, "Your document was returned",
                             "Please send it again", kind="warning")
        db.commit()

    sign_in(tenant, staff)
    assert tenant.get("/api/employee/announcements").json() == []


def test_notices_are_only_this_persons(tenant, account):
    mine = make_employee(tenant, first_name="Ada", last_name="Reid",
                         password="EmpPass123")
    theirs = make_employee(tenant, first_name="Sam", last_name="Ali")
    with main.SessionLocal() as db:
        other = db.query(models.DBEmployee).filter(
            models.DBEmployee.id == theirs["id"]).first()
        main.notify_employee(db, other, "For Sam only", "x", kind="announcement")
        db.commit()

    sign_in(tenant, mine)
    assert tenant.get("/api/employee/announcements").json() == []


def test_notices_need_a_session(client):
    assert client.get("/api/employee/announcements").status_code == 401
