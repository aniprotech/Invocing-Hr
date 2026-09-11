"""Letting a manager decide their own team's leave.

Leave and attendance corrections could only ever be decided by HR. Both
endpoints take get_client_user - the business account - and a leave request
recorded its approver as the literal string "HR" whatever happened, so the
record could not answer the one question anybody asks afterwards. In a company
of any size every request funnelled through one desk, and the person who
actually knows whether somebody can be spared that week had no say and no
view of it.

And nobody who could act was ever told. Requesting leave notified the
requester - "your request has been submitted" - and no one else. The request
then sat until somebody happened to open the HR screen, which for leave
starting on Monday is the kind of waiting that gets noticed on Monday.

The decision itself is not reimplemented for managers. decide_leave and
decide_correction are shared with HR's endpoints, because an entitlement rule
that applied on one route and not the other would be no rule at all. The tests
that matter most here are therefore not the happy path but the boundary: whose
requests a manager may touch, and whose they may not.
"""
import uuid

import pytest

import main
import models
from conftest import make_employee

EMP_PASSWORD = "EmpPass123"


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


def person(tenant, **kw):
    kw.setdefault("password", EMP_PASSWORD)
    return make_employee(tenant, **kw)


def sign_in(client, emp):
    main.rate_limiter._hits.clear()
    res = client.post("/api/employee/auth/login",
                      json={"email": emp["email"], "password": EMP_PASSWORD})
    assert res.status_code == 200, res.text


def ask_for_leave(client, emp, days=2, leave_type="annual",
                  start="2026-11-02", end="2026-11-03"):
    sign_in(client, emp)
    res = client.post("/api/employee/leave", json={
        "leave_type": leave_type, "start_date": start, "end_date": end,
        "reason": "A break"})
    assert res.status_code == 200, res.text
    with main.SessionLocal() as db:
        return db.query(models.DBLeaveRequest).filter(
            models.DBLeaveRequest.employee_id == emp["id"]).order_by(
                models.DBLeaveRequest.id.desc()).first().id


def approvals(client):
    return client.get("/api/employee/approvals").json()


# --- the list that did not exist ---------------------------------------------------

def test_a_manager_sees_their_teams_leave(tenant):
    boss = person(tenant, first_name="Dana", last_name="Boss")
    mine = person(tenant, first_name="Sam", last_name="Mine", reports_to=boss["id"])
    ask_for_leave(tenant, mine)

    sign_in(tenant, boss)
    got = approvals(tenant)
    assert got["count"] == 1, got
    assert [l["employee"] for l in got["leave"]] == ["Sam Mine"]
    assert got["leave"][0]["days"] == 2


def test_and_not_somebody_elses_team(tenant):
    boss = person(tenant)
    other_boss = person(tenant)
    theirs = person(tenant, first_name="Not", last_name="Mine",
                    reports_to=other_boss["id"])
    ask_for_leave(tenant, theirs)

    sign_in(tenant, boss)
    assert approvals(tenant)["count"] == 0


def test_somebody_with_no_reports_has_nothing_to_decide(tenant):
    lone = person(tenant)
    sign_in(tenant, lone)
    got = approvals(tenant)
    assert got == {"count": 0, "leave": [], "corrections": [], "expenses": []}


def test_the_list_shows_what_it_would_cost_them(tenant):
    """Approving leave without knowing what is left is the decision people get
    wrong, so the balance is worked out here rather than held in somebody's
    head."""
    boss = person(tenant)
    mine = person(tenant, reports_to=boss["id"])
    ask_for_leave(tenant, mine)

    sign_in(tenant, boss)
    row = approvals(tenant)["leave"][0]
    assert row["annual_remaining"] is not None, row


def test_a_decided_request_leaves_the_list(tenant):
    boss = person(tenant)
    mine = person(tenant, reports_to=boss["id"])
    leave_id = ask_for_leave(tenant, mine)

    sign_in(tenant, boss)
    assert tenant.post(f"/api/employee/approvals/leave/{leave_id}",
                       json={"action": "approve"}).status_code == 200
    assert approvals(tenant)["count"] == 0


# --- deciding ------------------------------------------------------------------------

def test_a_manager_can_approve(tenant):
    boss = person(tenant, first_name="Dana", last_name="Boss")
    mine = person(tenant, reports_to=boss["id"])
    leave_id = ask_for_leave(tenant, mine)

    sign_in(tenant, boss)
    res = tenant.post(f"/api/employee/approvals/leave/{leave_id}",
                      json={"action": "approve"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "approved"


def test_a_manager_can_reject(tenant):
    boss = person(tenant)
    mine = person(tenant, reports_to=boss["id"])
    leave_id = ask_for_leave(tenant, mine)

    sign_in(tenant, boss)
    res = tenant.post(f"/api/employee/approvals/leave/{leave_id}",
                      json={"action": "reject"})
    assert res.json()["status"] == "rejected"


def test_the_record_says_who_decided(tenant):
    """It used to say "HR" whatever happened, so the record could not answer
    the question it exists to answer."""
    boss = person(tenant, first_name="Dana", last_name="Boss")
    mine = person(tenant, reports_to=boss["id"])
    leave_id = ask_for_leave(tenant, mine)

    sign_in(tenant, boss)
    tenant.post(f"/api/employee/approvals/leave/{leave_id}",
                json={"action": "approve"})

    with main.SessionLocal() as db:
        row = db.query(models.DBLeaveRequest).filter(
            models.DBLeaveRequest.id == leave_id).first()
        assert row.approved_by == "Dana Boss", row.approved_by
        assert row.decided_at


def test_the_person_is_told_who_decided(tenant):
    boss = person(tenant, first_name="Dana", last_name="Boss")
    mine = person(tenant, reports_to=boss["id"])
    leave_id = ask_for_leave(tenant, mine)

    sign_in(tenant, boss)
    tenant.post(f"/api/employee/approvals/leave/{leave_id}",
                json={"action": "approve"})

    sign_in(tenant, mine)
    notes = tenant.get("/api/employee/notifications").json()["notifications"]
    assert any("Dana Boss" in n["message"] for n in notes), notes


def test_deciding_twice_is_refused(tenant):
    boss = person(tenant)
    mine = person(tenant, reports_to=boss["id"])
    leave_id = ask_for_leave(tenant, mine)

    sign_in(tenant, boss)
    tenant.post(f"/api/employee/approvals/leave/{leave_id}", json={"action": "approve"})
    res = tenant.post(f"/api/employee/approvals/leave/{leave_id}", json={"action": "reject"})
    assert res.status_code == 409, res.text


def test_an_action_that_is_not_one_is_refused(tenant):
    boss = person(tenant)
    mine = person(tenant, reports_to=boss["id"])
    leave_id = ask_for_leave(tenant, mine)

    sign_in(tenant, boss)
    assert tenant.post(f"/api/employee/approvals/leave/{leave_id}",
                       json={"action": "maybe"}).status_code == 400


# --- the boundary, which is the part that matters ---------------------------------------

def test_nobody_approves_their_own_leave(tenant):
    """The control the whole thing rests on. A manager asking for leave is
    still somebody asking for leave."""
    boss = person(tenant)
    person(tenant, reports_to=boss["id"])          # so they are a manager at all
    leave_id = ask_for_leave(tenant, boss)

    sign_in(tenant, boss)
    assert tenant.post(f"/api/employee/approvals/leave/{leave_id}",
                       json={"action": "approve"}).status_code == 404
    with main.SessionLocal() as db:
        assert db.query(models.DBLeaveRequest).filter(
            models.DBLeaveRequest.id == leave_id).first().status == "pending"


def test_not_even_if_they_report_to_themselves(tenant):
    """A bad row can make somebody their own manager. The id check is done
    before the reporting line is read, so it cannot be walked around."""
    boss = person(tenant)
    with main.SessionLocal() as db:
        row = db.query(models.DBEmployee).filter(
            models.DBEmployee.id == boss["id"]).first()
        row.reports_to = row.id
        db.commit()
    leave_id = ask_for_leave(tenant, boss)

    sign_in(tenant, boss)
    assert tenant.post(f"/api/employee/approvals/leave/{leave_id}",
                       json={"action": "approve"}).status_code == 404


def test_a_colleague_cannot_decide_it(tenant):
    boss = person(tenant)
    mine = person(tenant, reports_to=boss["id"])
    bystander = person(tenant)
    leave_id = ask_for_leave(tenant, mine)

    sign_in(tenant, bystander)
    assert tenant.post(f"/api/employee/approvals/leave/{leave_id}",
                       json={"action": "approve"}).status_code == 404


def test_the_requester_cannot_approve_themselves(tenant):
    boss = person(tenant)
    mine = person(tenant, reports_to=boss["id"])
    leave_id = ask_for_leave(tenant, mine)

    sign_in(tenant, mine)
    assert tenant.post(f"/api/employee/approvals/leave/{leave_id}",
                       json={"action": "approve"}).status_code == 404


def test_a_skip_level_manager_does_not_decide_it(tenant):
    """Direct reports only. Approving around somebody's actual manager is a
    decision a company makes deliberately, and HR can already decide
    anything."""
    top = person(tenant)
    middle = person(tenant, reports_to=top["id"])
    bottom = person(tenant, reports_to=middle["id"])
    leave_id = ask_for_leave(tenant, bottom)

    sign_in(tenant, top)
    assert approvals(tenant)["count"] == 0
    assert tenant.post(f"/api/employee/approvals/leave/{leave_id}",
                       json={"action": "approve"}).status_code == 404


def test_another_business_cannot_reach_it(tenant, client, account):
    boss = person(tenant)
    mine = person(tenant, reports_to=boss["id"])
    leave_id = ask_for_leave(tenant, mine)

    email = f"other-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/client/register", json={
        "email": email, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    client.post("/api/client/login", json={
        "email": email, "password": "Passw0rdTest"})
    outsider = person(client)
    theirs = person(client, reports_to=outsider["id"])
    sign_in(client, outsider)

    assert client.get("/api/employee/approvals").json()["count"] == 0
    assert client.post(f"/api/employee/approvals/leave/{leave_id}",
                       json={"action": "approve"}).status_code == 404


def test_a_manager_who_stops_being_one_stops_deciding(tenant):
    """The reporting line is read at the moment of the decision, not taken
    from the list the page was drawn from."""
    boss = person(tenant)
    mine = person(tenant, reports_to=boss["id"])
    leave_id = ask_for_leave(tenant, mine)

    with main.SessionLocal() as db:
        row = db.query(models.DBEmployee).filter(
            models.DBEmployee.id == mine["id"]).first()
        row.reports_to = None
        db.commit()

    sign_in(tenant, boss)
    assert tenant.post(f"/api/employee/approvals/leave/{leave_id}",
                       json={"action": "approve"}).status_code == 404


# --- the same rules as HR ----------------------------------------------------------------

def test_a_manager_cannot_approve_past_the_entitlement(tenant):
    """Shared with HR's route on purpose. A rule that applied on one and not
    the other would be no rule."""
    boss = person(tenant)
    mine = person(tenant, reports_to=boss["id"])
    leave_id = ask_for_leave(tenant, mine)

    with main.SessionLocal() as db:
        row = db.query(models.DBLeaveRequest).filter(
            models.DBLeaveRequest.id == leave_id).first()
        row.days = 9999
        db.commit()

    sign_in(tenant, boss)
    res = tenant.post(f"/api/employee/approvals/leave/{leave_id}",
                      json={"action": "approve"})
    assert res.status_code == 400, res.text
    assert "entitlement" in res.json()["detail"]


def test_hr_can_still_decide_anything(tenant):
    """Managers are an addition, not a replacement. HR keeps the override,
    which is what covers a manager who is away."""
    boss = person(tenant)
    mine = person(tenant, reports_to=boss["id"])
    leave_id = ask_for_leave(tenant, mine)

    res = tenant.post(f"/api/leave/requests/{leave_id}/action",
                      json={"action": "approve"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "approved"


# --- being told there is something to decide ------------------------------------------------

def test_the_manager_is_told_a_request_has_arrived(tenant):
    """Only the requester was told, so a request sat until somebody happened
    to look."""
    boss = person(tenant)
    mine = person(tenant, first_name="Sam", last_name="Mine", reports_to=boss["id"])
    ask_for_leave(tenant, mine)

    sign_in(tenant, boss)
    notes = tenant.get("/api/employee/notifications").json()["notifications"]
    assert any("Sam Mine" in n["message"] for n in notes), notes


def test_the_requester_is_still_told_too(tenant):
    boss = person(tenant)
    mine = person(tenant, reports_to=boss["id"])
    ask_for_leave(tenant, mine)

    sign_in(tenant, mine)
    notes = tenant.get("/api/employee/notifications").json()["notifications"]
    assert any("submitted" in n["message"].lower() for n in notes), notes


def test_somebody_with_no_manager_still_gets_their_leave_in(tenant):
    """Nobody to tell is not a reason to refuse the request. HR sees it on
    their own list either way."""
    lone = person(tenant)
    leave_id = ask_for_leave(tenant, lone)
    with main.SessionLocal() as db:
        assert db.query(models.DBLeaveRequest).filter(
            models.DBLeaveRequest.id == leave_id).first().status == "pending"


# --- attendance corrections take the same route -----------------------------------------------

def a_correction(tenant, emp):
    """A day on the record, and a request to change it."""
    with main.SessionLocal() as db:
        att = models.DBAttendance(
            client_id=emp["client_id"] if "client_id" in emp else None,
            employee_id=emp["id"], date="2026-10-05",
            clock_in="09:00:00", clock_out="", status="needs_review")
        row = db.query(models.DBEmployee).filter(
            models.DBEmployee.id == emp["id"]).first()
        att.client_id = row.client_id
        db.add(att)
        db.flush()
        c = models.DBAttendanceCorrection(
            client_id=row.client_id, employee_id=emp["id"], attendance_id=att.id,
            old_clock_in="09:00:00", old_clock_out="",
            requested_clock_in="09:00:00", requested_clock_out="17:30:00",
            reason="Forgot to clock out")
        db.add(c)
        db.commit()
        return c.id


def test_a_manager_sees_their_teams_attendance_corrections(tenant):
    boss = person(tenant)
    mine = person(tenant, first_name="Sam", last_name="Mine", reports_to=boss["id"])
    a_correction(tenant, mine)

    sign_in(tenant, boss)
    got = approvals(tenant)
    assert got["count"] == 1, got
    assert got["corrections"][0]["employee"] == "Sam Mine"
    # The day is on the attendance row, not the request, and it is the whole
    # subject of the decision.
    assert got["corrections"][0]["date"] == "2026-10-05"
    assert "17:30" in got["corrections"][0]["asked_for"]


def test_a_manager_approving_one_writes_the_hours_through(tenant):
    boss = person(tenant)
    mine = person(tenant, reports_to=boss["id"])
    cid = a_correction(tenant, mine)

    sign_in(tenant, boss)
    res = tenant.post(f"/api/employee/approvals/correction/{cid}",
                      json={"decision": "approve"})
    assert res.status_code == 200, res.text

    with main.SessionLocal() as db:
        row = db.query(models.DBAttendanceCorrection).filter(
            models.DBAttendanceCorrection.id == cid).first()
        att = db.query(models.DBAttendance).filter(
            models.DBAttendance.id == row.attendance_id).first()
        assert att.clock_out == "17:30:00"
        assert att.total_hours == 8.5
        assert row.status == "approved"


def test_rejecting_one_leaves_the_day_alone(tenant):
    boss = person(tenant)
    mine = person(tenant, reports_to=boss["id"])
    cid = a_correction(tenant, mine)

    sign_in(tenant, boss)
    tenant.post(f"/api/employee/approvals/correction/{cid}",
                json={"decision": "reject", "note": "That was a half day"})

    with main.SessionLocal() as db:
        row = db.query(models.DBAttendanceCorrection).filter(
            models.DBAttendanceCorrection.id == cid).first()
        att = db.query(models.DBAttendance).filter(
            models.DBAttendance.id == row.attendance_id).first()
        assert att.clock_out == ""
        assert row.status == "rejected"
        assert row.note == "That was a half day"


def test_a_correction_cannot_be_decided_by_somebody_elses_manager(tenant):
    boss = person(tenant)
    other_boss = person(tenant)
    theirs = person(tenant, reports_to=other_boss["id"])
    cid = a_correction(tenant, theirs)

    sign_in(tenant, boss)
    assert tenant.post(f"/api/employee/approvals/correction/{cid}",
                       json={"decision": "approve"}).status_code == 404


def test_nobody_approves_their_own_attendance_correction(tenant):
    boss = person(tenant)
    person(tenant, reports_to=boss["id"])
    cid = a_correction(tenant, boss)

    sign_in(tenant, boss)
    assert tenant.post(f"/api/employee/approvals/correction/{cid}",
                       json={"decision": "approve"}).status_code == 404
