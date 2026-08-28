"""One calendar for everything that has a date.

A leave request, an interview, a goal's due date, a document about to expire -
each already existed for its own reason, in its own screen, with no way to see
what was landing the same week as anything else. This reads all of them into
one shape, adds a place for HR to type in something that has no home
elsewhere (a reminder, a meeting), and reminds by email once for anything due
soon that nobody would otherwise notice creeping up.
"""
from datetime import datetime, timedelta

import pytest

import main
import models


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    main.rate_limiter._hits.clear()
    # calendar_reminders claims (job_name, today's date) the first time it
    # runs and every test in this module runs on the same day, so without
    # clearing DBJobRun every test after the first silently gets
    # "already_done" and its assertions test nothing.
    with main.SessionLocal() as db:
        db.query(models.DBJobRun).delete()
        db.query(models.DBCalendarReminderSent).delete()
        db.commit()
    yield


def get_events(tenant, start, end):
    res = tenant.get(f"/api/hr/calendar?start={start}&end={end}")
    assert res.status_code == 200, res.text
    return res.json()["events"]


def make_employee(tenant, **overrides):
    body = {"first_name": "Ada", "last_name": "Reid", "email": "ada@cal.test",
            "job_title": "Analyst", "status": "active"}
    body.update(overrides)
    res = tenant.post("/api/employees", json=body)
    assert res.status_code == 200, res.text
    return res.json()


def client_id_of(tenant):
    return tenant.get("/api/client/me").json()["id"]


def about(sent, needle):
    """Which of the emails actually sent are about this one thing.

    The database is shared for the whole test module, and the job correctly
    scans every tenant - so counting the whole mailbox would be counting
    other tests' leftovers as well as this one's.
    """
    return [call for call in sent if needle in call[1]]


def add_leave(tenant, emp_id, start_date, end_date, status="approved"):
    """Leave is booked through the employee portal in production; a direct
    row is enough here, since it is the calendar's reading of one that is
    under test, not the booking flow, which has its own suite."""
    with main.SessionLocal() as db:
        row = models.DBLeaveRequest(
            client_id=client_id_of(tenant), employee_id=emp_id,
            leave_type="annual", start_date=start_date, end_date=end_date,
            days=1, status=status)
        db.add(row)
        db.commit()
        return row.id


def add_goal(tenant, emp_id, title, due_date, **overrides):
    body = {"title": title, "due_date": due_date, "target_value": 100,
            "current_value": 40, "unit": "%"}
    body.update(overrides)
    res = tenant.post(f"/api/employees/{emp_id}/goals", json=body)
    assert res.status_code == 200, res.text
    return res.json()["id"]


def complete_goal(goal_id):
    with main.SessionLocal() as db:
        goal = db.query(models.DBEmployeeGoal).filter(
            models.DBEmployeeGoal.id == goal_id).first()
        goal.status = "completed"
        db.commit()


def add_document(tenant, emp_id, name, expires_on, requirement_id=None, **overrides):
    with main.SessionLocal() as db:
        row = models.DBDocumentRequest(
            client_id=client_id_of(tenant), employee_id=emp_id,
            requirement_id=requirement_id, name=name, requires_expiry=True,
            expires_on=expires_on, status=overrides.get("status", "approved"),
            due_date=overrides.get("due_date", ""))
        db.add(row)
        db.commit()
        return row.id


# --- custom entries ----------------------------------------------------------
def test_hr_can_add_a_reminder(tenant):
    res = tenant.post("/api/hr/calendar-events", json={
        "date": "2026-09-10", "title": "Renew fire extinguisher contract"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["title"] == "Renew fire extinguisher contract"
    assert body["kind"] == "reminder"        # the default


def test_it_shows_up_on_the_calendar(tenant):
    tenant.post("/api/hr/calendar-events",
               json={"date": "2026-09-10", "title": "Board meeting", "kind": "meeting"})
    events = get_events(tenant, "2026-09-01", "2026-09-30")
    assert [e["title"] for e in events] == ["Board meeting"]
    assert events[0]["kind"] == "meeting"
    assert events[0]["editable"] is True


def test_a_time_is_optional_but_has_to_be_a_time(tenant):
    ok = tenant.post("/api/hr/calendar-events", json={
        "date": "2026-09-10", "title": "Standup", "time": "09:30"})
    assert ok.status_code == 200, ok.text

    bad = tenant.post("/api/hr/calendar-events", json={
        "date": "2026-09-10", "title": "Standup", "time": "9:30am"})
    assert bad.status_code == 400


@pytest.mark.parametrize("date", ["", "10/09/2026", "nonsense"])
def test_a_date_that_is_not_a_date_is_refused(tenant, date):
    res = tenant.post("/api/hr/calendar-events", json={"date": date, "title": "X"})
    assert res.status_code == 400


def test_an_entry_needs_a_title(tenant):
    res = tenant.post("/api/hr/calendar-events",
                      json={"date": "2026-09-10", "title": "   "})
    assert res.status_code == 400


def test_the_kind_has_to_be_one_of_the_offered_ones(tenant):
    res = tenant.post("/api/hr/calendar-events",
                      json={"date": "2026-09-10", "title": "X", "kind": "sabotage"})
    assert res.status_code == 400


def test_notify_days_before_has_to_be_sane(tenant):
    res = tenant.post("/api/hr/calendar-events", json={
        "date": "2026-09-10", "title": "X", "notify_days_before": -1})
    assert res.status_code == 400
    res = tenant.post("/api/hr/calendar-events", json={
        "date": "2026-09-10", "title": "X", "notify_days_before": 500})
    assert res.status_code == 400


def test_an_entry_can_be_edited(tenant):
    row = tenant.post("/api/hr/calendar-events",
                      json={"date": "2026-09-10", "title": "Draft"}).json()
    res = tenant.put(f"/api/hr/calendar-events/{row['id']}",
                     json={"title": "Final", "date": "2026-09-12"})
    assert res.status_code == 200, res.text
    events = get_events(tenant, "2026-09-01", "2026-09-30")
    assert events[0]["title"] == "Final" and events[0]["date"] == "2026-09-12"


def test_editing_a_nonexistent_entry_is_a_404(tenant):
    res = tenant.put("/api/hr/calendar-events/999999", json={"title": "X"})
    assert res.status_code == 404


def test_an_entry_can_be_removed(tenant):
    row = tenant.post("/api/hr/calendar-events",
                      json={"date": "2026-09-10", "title": "Gone soon"}).json()
    assert tenant.delete(f"/api/hr/calendar-events/{row['id']}").status_code == 200
    assert get_events(tenant, "2026-09-01", "2026-09-30") == []


def test_one_business_cannot_see_or_touch_another_s_calendar(tenant):
    import uuid
    from fastapi.testclient import TestClient

    mine = tenant.post("/api/hr/calendar-events",
                       json={"date": "2026-09-10", "title": "Private"}).json()

    with TestClient(main.app) as other:
        email = f"other-{uuid.uuid4().hex[:8]}@example.com"
        other.post("/api/client/register", json={
            "email": email, "password": "Passw0rdTest", "company_name": "Other Ltd"})
        other.post("/api/client/login",
                   json={"email": email, "password": "Passw0rdTest"})

        assert get_events(other, "2026-09-01", "2026-09-30") == []
        assert other.delete(f"/api/hr/calendar-events/{mine['id']}").status_code == 404

    assert len(get_events(tenant, "2026-09-01", "2026-09-30")) == 1


# --- the range -----------------------------------------------------------------
def test_with_no_query_string_it_defaults_to_the_current_month(tenant):
    today = datetime.now().date()
    tenant.post("/api/hr/calendar-events",
               json={"date": today.strftime("%Y-%m-%d"), "title": "Today"})
    res = tenant.get("/api/hr/calendar")
    assert res.status_code == 200, res.text
    assert [e["title"] for e in res.json()["events"]] == ["Today"]


def test_an_entry_outside_the_range_does_not_show(tenant):
    tenant.post("/api/hr/calendar-events",
               json={"date": "2026-10-01", "title": "Next month"})
    assert get_events(tenant, "2026-09-01", "2026-09-30") == []


def test_end_before_start_is_refused(tenant):
    res = tenant.get("/api/hr/calendar?start=2026-09-30&end=2026-09-01")
    assert res.status_code == 400


def test_asking_for_more_than_a_year_is_refused(tenant):
    res = tenant.get("/api/hr/calendar?start=2020-01-01&end=2026-01-01")
    assert res.status_code == 400


# --- holidays --------------------------------------------------------------
def test_a_holiday_appears_on_the_calendar(tenant):
    tenant.post("/api/hr/holidays", json={"date": "2026-12-25", "name": "Christmas Day"})
    events = get_events(tenant, "2026-12-01", "2026-12-31")
    assert [e["title"] for e in events] == ["Christmas Day"]
    assert events[0]["kind"] == "holiday" and events[0]["editable"] is False


def test_every_event_carries_a_human_readable_kind(tenant):
    tenant.post("/api/hr/holidays", json={"date": "2026-12-25", "name": "Christmas Day"})
    events = get_events(tenant, "2026-12-01", "2026-12-31")
    assert events[0]["kind_label"] == "Holiday"


def test_a_recurring_holiday_appears_in_a_later_year_too(tenant):
    tenant.post("/api/hr/holidays", json={
        "date": "2020-12-25", "name": "Christmas Day", "recurring": True})
    events = get_events(tenant, "2030-12-01", "2030-12-31")
    assert [e["date"] for e in events] == ["2030-12-25"]


def test_a_fixed_holiday_does_not_repeat(tenant):
    tenant.post("/api/hr/holidays", json={"date": "2026-12-25", "name": "One-off closure"})
    assert get_events(tenant, "2030-12-01", "2030-12-31") == []


# --- leave -------------------------------------------------------------------
def test_approved_leave_shows_the_person_and_the_dates(tenant):
    emp = make_employee(tenant)
    add_leave(tenant, emp["id"], "2026-09-05", "2026-09-07")
    events = get_events(tenant, "2026-09-01", "2026-09-30")
    leave_events = [e for e in events if e["kind"] == "leave"]
    assert len(leave_events) == 1, events
    assert "Ada Reid" in leave_events[0]["title"]
    assert "2026-09-05" in leave_events[0]["subtitle"]


def test_leave_spanning_into_the_range_still_shows(tenant):
    """Leave that started last month and runs into this one must not
    disappear just because its start date sits outside the window."""
    emp = make_employee(tenant)
    add_leave(tenant, emp["id"], "2026-08-28", "2026-09-03")
    events = get_events(tenant, "2026-09-01", "2026-09-30")
    assert any(e["kind"] == "leave" for e in events), events


def test_leave_entirely_before_the_range_does_not_show(tenant):
    emp = make_employee(tenant)
    add_leave(tenant, emp["id"], "2026-07-01", "2026-07-03")
    events = get_events(tenant, "2026-09-01", "2026-09-30")
    assert not any(e["kind"] == "leave" for e in events)


def test_a_pending_request_is_shown_as_pending(tenant):
    emp = make_employee(tenant)
    add_leave(tenant, emp["id"], "2026-09-05", "2026-09-07", status="pending")
    events = get_events(tenant, "2026-09-01", "2026-09-30")
    leave_events = [e for e in events if e["kind"] == "leave"]
    assert "awaiting" in leave_events[0]["subtitle"].lower()


def test_a_rejected_request_does_not_show(tenant):
    emp = make_employee(tenant)
    add_leave(tenant, emp["id"], "2026-09-05", "2026-09-07", status="rejected")
    events = get_events(tenant, "2026-09-01", "2026-09-30")
    assert not any(e["kind"] == "leave" for e in events)


# --- goals -------------------------------------------------------------------
def test_a_goal_s_due_date_is_on_the_calendar(tenant):
    emp = make_employee(tenant)
    add_goal(tenant, emp["id"], "Ship the report", "2026-09-20")
    events = get_events(tenant, "2026-09-01", "2026-09-30")
    goal_events = [e for e in events if e["kind"] == "goal"]
    assert len(goal_events) == 1, events
    assert goal_events[0]["title"] == "Ship the report"
    assert "40" in goal_events[0]["subtitle"] and "100" in goal_events[0]["subtitle"]


def test_a_completed_goal_drops_off_the_calendar(tenant):
    emp = make_employee(tenant)
    gid = add_goal(tenant, emp["id"], "Ship the report", "2026-09-20")
    complete_goal(gid)
    events = get_events(tenant, "2026-09-01", "2026-09-30")
    assert not any(e["kind"] == "goal" for e in events)


def test_a_goal_with_no_due_date_does_not_appear_anywhere(tenant):
    emp = make_employee(tenant)
    add_goal(tenant, emp["id"], "No deadline", "")
    events = get_events(tenant, "2026-01-01", "2026-12-31")
    assert not any(e["kind"] == "goal" for e in events)


# --- reminders ---------------------------------------------------------------
def test_a_reminder_is_sent_the_right_number_of_days_before(tenant, monkeypatch):
    sent = []
    monkeypatch.setattr(main, "send_email_background",
                        lambda *a, **kw: sent.append(a) or (True, "ok"))

    today = datetime.now().date()
    due = (today + timedelta(days=2)).strftime("%Y-%m-%d")
    tenant.post("/api/hr/calendar-events",
               json={"date": due, "title": "Insurance renewal", "notify_days_before": 2})

    main.run_due_jobs(only="calendar_reminders")
    assert len(about(sent, "Insurance renewal")) == 1, sent


def test_a_reminder_is_not_sent_early(tenant, monkeypatch):
    sent = []
    monkeypatch.setattr(main, "send_email_background",
                        lambda *a, **kw: sent.append(a) or (True, "ok"))

    today = datetime.now().date()
    due = (today + timedelta(days=5)).strftime("%Y-%m-%d")
    tenant.post("/api/hr/calendar-events",
               json={"date": due, "title": "Too soon to say", "notify_days_before": 2})

    main.run_due_jobs(only="calendar_reminders")
    assert about(sent, "Too soon to say") == []


def test_a_reminder_is_never_sent_twice(tenant, monkeypatch):
    sent = []
    monkeypatch.setattr(main, "send_email_background",
                        lambda *a, **kw: sent.append(a) or (True, "ok"))

    today = datetime.now().date()
    due = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    tenant.post("/api/hr/calendar-events",
               json={"date": due, "title": "Once only", "notify_days_before": 1})

    main.run_due_jobs(only="calendar_reminders")
    main.run_due_jobs(only="calendar_reminders")
    assert len(about(sent, "Once only")) == 1


def test_notify_days_before_zero_never_sends(tenant, monkeypatch):
    """A plain note on the calendar does not have to be an email as well."""
    sent = []
    monkeypatch.setattr(main, "send_email_background",
                        lambda *a, **kw: sent.append(a) or (True, "ok"))

    today = datetime.now().date()
    tenant.post("/api/hr/calendar-events", json={
        "date": today.strftime("%Y-%m-%d"), "title": "Just a note",
        "notify_days_before": 0})

    main.run_due_jobs(only="calendar_reminders")
    assert about(sent, "Just a note") == []


def test_deleting_an_event_stops_a_reminder_still_pending(tenant, monkeypatch):
    sent = []
    monkeypatch.setattr(main, "send_email_background",
                        lambda *a, **kw: sent.append(a) or (True, "ok"))

    today = datetime.now().date()
    due = (today + timedelta(days=10)).strftime("%Y-%m-%d")
    row = tenant.post("/api/hr/calendar-events", json={
        "date": due, "title": "Cancelled plan", "notify_days_before": 10}).json()
    tenant.delete(f"/api/hr/calendar-events/{row['id']}")

    main.run_due_jobs(only="calendar_reminders")
    assert about(sent, "Cancelled plan") == []


def test_a_goal_is_reminded_three_days_out(tenant, monkeypatch):
    sent = []
    monkeypatch.setattr(main, "send_email_background",
                        lambda *a, **kw: sent.append(a) or (True, "ok"))

    emp = make_employee(tenant)
    today = datetime.now().date()
    due = (today + timedelta(days=3)).strftime("%Y-%m-%d")
    add_goal(tenant, emp["id"], "Close the quarter", due)

    main.run_due_jobs(only="calendar_reminders")
    assert len(about(sent, "Close the quarter")) == 1


def test_a_goal_is_not_reminded_on_a_different_day(tenant, monkeypatch):
    sent = []
    monkeypatch.setattr(main, "send_email_background",
                        lambda *a, **kw: sent.append(a) or (True, "ok"))

    emp = make_employee(tenant)
    today = datetime.now().date()
    due = (today + timedelta(days=7)).strftime("%Y-%m-%d")
    add_goal(tenant, emp["id"], "Not yet", due)

    main.run_due_jobs(only="calendar_reminders")
    assert about(sent, "Not yet") == []


def test_a_completed_goal_is_never_reminded(tenant, monkeypatch):
    sent = []
    monkeypatch.setattr(main, "send_email_background",
                        lambda *a, **kw: sent.append(a) or (True, "ok"))

    emp = make_employee(tenant)
    today = datetime.now().date()
    due = (today + timedelta(days=3)).strftime("%Y-%m-%d")
    gid = add_goal(tenant, emp["id"], "Close the quarter (done)", due)
    complete_goal(gid)

    main.run_due_jobs(only="calendar_reminders")
    assert about(sent, "Close the quarter (done)") == []


def test_a_document_uses_its_own_reminder_window(tenant, monkeypatch):
    """expiry_reminder_days has existed on the requirement since the field was
    added, with nothing that ever read it until this job."""
    sent = []
    monkeypatch.setattr(main, "send_email_background",
                        lambda *a, **kw: sent.append(a) or (True, "ok"))

    emp = make_employee(tenant)
    rule = tenant.post("/api/onboarding/requirements", json={
        "name": "Right to work", "requires_expiry": True,
        "expiry_reminder_days": 14}).json()

    today = datetime.now().date()
    add_document(tenant, emp["id"], "Right to work",
                (today + timedelta(days=14)).strftime("%Y-%m-%d"),
                requirement_id=rule["id"])

    main.run_due_jobs(only="calendar_reminders")
    assert len(about(sent, "Right to work")) == 1, sent


def test_a_document_with_no_requirement_falls_back_to_thirty_days(tenant, monkeypatch):
    sent = []
    monkeypatch.setattr(main, "send_email_background",
                        lambda *a, **kw: sent.append(a) or (True, "ok"))

    emp = make_employee(tenant)
    today = datetime.now().date()
    add_document(tenant, emp["id"], "Passport",
                (today + timedelta(days=30)).strftime("%Y-%m-%d"))

    main.run_due_jobs(only="calendar_reminders")
    assert len(about(sent, "Passport")) == 1, sent


def test_a_document_that_does_not_expire_is_never_reminded(tenant, monkeypatch):
    sent = []
    monkeypatch.setattr(main, "send_email_background",
                        lambda *a, **kw: sent.append(a) or (True, "ok"))

    emp = make_employee(tenant)
    with main.SessionLocal() as db:
        row = models.DBDocumentRequest(
            client_id=client_id_of(tenant), employee_id=emp["id"],
            name="Contract (no expiry)", requires_expiry=False, expires_on="",
            status="approved")
        db.add(row)
        db.commit()

    main.run_due_jobs(only="calendar_reminders")
    assert about(sent, "Contract (no expiry)") == []
