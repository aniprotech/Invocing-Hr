"""Days the business is closed.

Without a calendar, a public holiday was indistinguishable from everybody
failing to turn up. The register showed a company of absentees, and the dial in
the employee portal asked for a full day's hours nobody was meant to work -
which is the sort of thing that gets argued about at a pay review months later.

A holiday now closes the office: the day is not expected, and both the register
and the portal say which holiday it is rather than only that nothing happened.
"""
import pytest

import main


@pytest.fixture
def calendar(tenant):
    def add(**kw):
        body = {"date": "2026-12-25", "name": "Christmas Day"}
        body.update(kw)
        res = tenant.post("/api/hr/holidays", json=body)
        assert res.status_code == 200, res.text
        return res.json()
    return add


# --- keeping the calendar ---------------------------------------------------
def test_a_holiday_can_be_added_and_listed(tenant, calendar):
    calendar()
    rows = tenant.get("/api/hr/holidays").json()["holidays"]
    assert [h["name"] for h in rows] == ["Christmas Day"]


def test_the_same_day_cannot_be_booked_twice(tenant, calendar):
    """Two entries would close the office twice and read as a duplicate."""
    calendar()
    res = tenant.post("/api/hr/holidays",
                      json={"date": "2026-12-25", "name": "Xmas"})
    assert res.status_code == 400
    assert "Christmas Day" in res.json()["detail"], "it should say what is there"


@pytest.mark.parametrize("date", ["", "25/12/2026", "2026-13-01", "nonsense"])
def test_a_date_that_is_not_a_date_is_refused(tenant, date):
    res = tenant.post("/api/hr/holidays", json={"date": date, "name": "X"})
    assert res.status_code == 400


def test_a_holiday_needs_a_name(tenant):
    """"Closed" with no reason is worse than not knowing."""
    res = tenant.post("/api/hr/holidays", json={"date": "2026-05-04", "name": "  "})
    assert res.status_code == 400


def test_a_holiday_can_be_renamed_and_moved(tenant, calendar):
    row = calendar()
    res = tenant.put(f"/api/hr/holidays/{row['id']}",
                     json={"name": "Christmas", "date": "2026-12-26"})
    assert res.status_code == 200, res.text
    after = tenant.get("/api/hr/holidays").json()["holidays"][0]
    assert after["name"] == "Christmas" and after["date"] == "2026-12-26"


def test_a_holiday_can_be_removed(tenant, calendar):
    row = calendar()
    assert tenant.delete(f"/api/hr/holidays/{row['id']}").status_code == 200
    assert tenant.get("/api/hr/holidays").json()["holidays"] == []


def test_one_business_cannot_see_or_touch_another_s_calendar(tenant):
    """Every tenant route funnels through the same check; this is the one that
    would be noticed last, because a wrong calendar still looks like a
    calendar."""
    import uuid

    from fastapi.testclient import TestClient

    mine = tenant.post("/api/hr/holidays",
                       json={"date": "2026-08-31", "name": "Bank Holiday"}).json()

    with TestClient(main.app) as other:
        email = f"other-{uuid.uuid4().hex[:8]}@example.com"
        other.post("/api/client/register", json={
            "email": email, "password": "Passw0rdTest", "company_name": "Other Ltd"})
        other.post("/api/client/login",
                   json={"email": email, "password": "Passw0rdTest"})

        assert other.get("/api/hr/holidays").json()["holidays"] == []
        assert other.delete(f"/api/hr/holidays/{mine['id']}").status_code == 404

    assert len(tenant.get("/api/hr/holidays").json()["holidays"]) == 1


# --- a recurring day is entered once ----------------------------------------
def test_a_recurring_holiday_covers_later_years(tenant, calendar):
    """Christmas entered against 2026 still closes the office in 2030."""
    calendar(recurring=True)
    assert tenant.get("/api/hr/day-kind?date=2030-12-25").json()["kind"] == "holiday"


def test_a_fixed_holiday_does_not(tenant, calendar):
    calendar(recurring=False)
    assert tenant.get("/api/hr/day-kind?date=2030-12-25").json()["kind"] != "holiday"


def test_narrowing_to_a_year_keeps_the_recurring_ones(tenant, calendar):
    """They were entered against some past year and still close the office."""
    calendar(date="2020-12-25", recurring=True)
    calendar(date="2026-07-04", name="Founders Day")
    names = [h["name"] for h in
             tenant.get("/api/hr/holidays?year=2026").json()["holidays"]]
    assert "Christmas Day" in names and "Founders Day" in names


# --- what a holiday does to the day -----------------------------------------
def test_a_holiday_is_not_a_working_day(tenant, calendar):
    calendar(date="2026-06-03")           # a Wednesday
    day = tenant.get("/api/hr/day-kind?date=2026-06-03").json()
    assert day["kind"] == "holiday"
    assert day["expected"] is False
    assert day["label"] == "Christmas Day"


def test_and_is_told_apart_from_a_weekend(tenant):
    """Both are "not working". Which one it is, is the whole point."""
    weekend = tenant.get("/api/hr/day-kind?date=2026-06-06").json()   # Saturday
    assert weekend["kind"] == "rest_day"
    assert weekend["expected"] is False


def test_an_ordinary_day_is_just_a_working_day(tenant):
    day = tenant.get("/api/hr/day-kind?date=2026-06-03").json()
    assert day["kind"] == "working" and day["expected"] is True


def test_an_optional_holiday_leaves_the_office_open(tenant, calendar):
    """Some days are marked but not closed. Staff are still expected."""
    calendar(date="2026-06-03", name="Summer social", optional=True)
    day = tenant.get("/api/hr/day-kind?date=2026-06-03").json()
    assert day["kind"] == "optional_holiday"
    assert day["expected"] is True
    assert day["label"] == "Summer social"


def test_a_closing_holiday_beats_an_optional_one_on_the_same_day(tenant):
    tenant.post("/api/hr/holidays", json={
        "date": "2026-06-03", "name": "Summer social", "optional": True})
    # The same date is refused, so this is the realistic version: a recurring
    # closure landing on a day already marked optional.
    tenant.post("/api/hr/holidays", json={
        "date": "2020-06-03", "name": "Founders Day", "recurring": True})
    day = tenant.get("/api/hr/day-kind?date=2026-06-03").json()
    assert day["expected"] is False, "an optional day must not hold the office open"
    assert day["label"] == "Founders Day"


# --- what the two screens are told ------------------------------------------
def test_the_portal_is_told_it_is_a_holiday(tenant, calendar):
    """So it can say which one rather than refusing to clock in without a
    reason."""
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    calendar(date=today, name="Company Day")

    emp = tenant.post("/api/employees", json={
        "first_name": "Ada", "last_name": "Reid", "email": "ada@holiday.test",
        "job_title": "Analyst", "status": "active"}).json()
    tenant.put(f"/api/employees/{emp['id']}/set-password",
               json={"password": "Emp!12345"})
    tenant.post("/api/employee/auth/login",
                json={"email": "ada@holiday.test", "password": "Emp!12345"})

    today_view = tenant.get("/api/employee/attendance/today").json()
    assert today_view["is_working_day"] is False
    assert today_view["day"]["kind"] == "holiday"
    assert today_view["day"]["label"] == "Company Day"


def test_the_register_can_say_the_office_is_closed(tenant, calendar):
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    calendar(date=today, name="Company Day")

    body = tenant.get("/api/attendance/live?with_day=1").json()
    assert body["day"]["kind"] == "holiday"
    assert "employees" in body


def test_the_register_still_answers_the_old_way_by_default(tenant):
    """Callers that only want the rows are unchanged."""
    assert isinstance(tenant.get("/api/attendance/live").json(), list)
