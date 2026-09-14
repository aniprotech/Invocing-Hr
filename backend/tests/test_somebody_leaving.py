"""Closing the door properly when somebody leaves.

Starting offboarding set a status and fired a workflow. Finishing it set
another status and was reachable from nothing in the browser, so everybody
who ever left stayed "offboarding" for good. In between, nothing looked at
what the person still had or was still responsible for.

That is the security hole. A leaver with the laptop still at home, a live
portal login, three people reporting to them and a leave request from one of
those people waiting on their approval - and the record said "offboarding"
and nothing else.

Two things this fixes that were true in production:

  - Sign-in refused a leaver, but nothing after sign-in did. The session is
    a signed cookie with nothing server-side to revoke, so somebody marked as
    having left kept every portal endpoint working until the cookie expired.
  - Nothing checked what they still held. The product knew - assets have
    open assignments - and nobody asked it.
"""
import uuid
from datetime import date

import pytest

import main
import models
from conftest import make_employee

EMP_PASSWORD = "EmpPass123"
TODAY = date.today().isoformat()


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


def person(tenant, **kw):
    kw.setdefault("password", EMP_PASSWORD)
    return make_employee(tenant, **kw)


def as_staff(client, emp):
    main.rate_limiter._hits.clear()
    client.post("/api/client/logout")
    res = client.post("/api/employee/auth/login",
                      json={"email": emp["email"], "password": EMP_PASSWORD})
    assert res.status_code == 200, res.text


def as_hr(client, account):
    client.post("/api/employee/auth/logout")
    res = client.post("/api/client/login", json={
        "email": account["email"], "password": account["password"]})
    assert res.status_code == 200, res.text


def issue_asset(tenant, emp, tag="LAP-001"):
    a = tenant.post("/api/assets", json={"tag": tag, "name": "MacBook", "category": "laptop"})
    assert a.status_code == 200, a.text
    r = tenant.post(f"/api/assets/{a.json()['id']}/assign", json={"employee_id": emp["id"]})
    assert r.status_code == 200, r.text
    return a.json()


def checklist(tenant, emp):
    res = tenant.get(f"/api/employees/{emp['id']}/offboarding")
    assert res.status_code == 200, res.text
    return res.json()


def leave(tenant, emp, **over):
    body = {"end_date": TODAY}
    body.update(over)
    return tenant.post(f"/api/employees/{emp['id']}/complete-offboard", json=body)


# --- the hole: a leaver kept working ------------------------------------------------

def test_a_leaver_is_thrown_out_of_the_portal_at_once(tenant, account):
    """Not at the next sign-in. Now, on the request they were in the middle
    of. The cookie is still valid; the account is not."""
    staff = person(tenant)
    as_staff(tenant, staff)
    assert tenant.get("/api/employee/profile").status_code == 200

    with main.SessionLocal() as db:
        row = db.query(models.DBEmployee).filter(models.DBEmployee.id == staff["id"]).first()
        row.status = "terminated"
        db.commit()

    res = tenant.get("/api/employee/profile")
    assert res.status_code == 401, res.text
    assert "closed" in res.json()["detail"]


def test_and_stays_out(tenant, account):
    staff = person(tenant)
    as_staff(tenant, staff)
    with main.SessionLocal() as db:
        row = db.query(models.DBEmployee).filter(models.DBEmployee.id == staff["id"]).first()
        row.status = "terminated"
        db.commit()
    tenant.get("/api/employee/profile")
    # The session was cleared, so even a route that does not check status
    # has nothing to work with.
    assert tenant.get("/api/employee/tasks").status_code == 401
    assert tenant.get("/api/feed").status_code == 401


def test_somebody_who_has_not_left_is_unaffected(tenant):
    staff = person(tenant)
    as_staff(tenant, staff)
    with main.SessionLocal() as db:
        row = db.query(models.DBEmployee).filter(models.DBEmployee.id == staff["id"]).first()
        row.status = "offboarding"
        db.commit()
    # Offboarding is still here. They may have handover to do.
    assert tenant.get("/api/employee/profile").status_code == 200


# --- the checklist ---------------------------------------------------------------------

def test_the_checklist_knows_what_they_still_hold(tenant):
    staff = person(tenant)
    issue_asset(tenant, staff, "LAP-014")
    issue_asset(tenant, staff, "PH-003")
    c = checklist(tenant, staff)
    assert sorted(a["tag"] for a in c["assets_out"]) == ["LAP-014", "PH-003"]
    assert c["ready"] is False
    assert any("2 item" in b for b in c["blocking"]), c["blocking"]


def test_a_returned_asset_is_not_still_out(tenant):
    staff = person(tenant)
    a = issue_asset(tenant, staff)
    assert tenant.post(f"/api/assets/{a['id']}/return", json={"condition": "good"}).status_code == 200
    c = checklist(tenant, staff)
    assert c["assets_out"] == []
    assert c["ready"] is True


def test_it_knows_who_will_be_left_without_a_manager(tenant):
    boss = person(tenant)
    person(tenant, first_name="One", last_name="Report", reports_to=boss["id"])
    person(tenant, first_name="Two", last_name="Report", reports_to=boss["id"])
    c = checklist(tenant, boss)
    assert sorted(r["name"] for r in c["direct_reports"]) == ["One Report", "Two Report"]


def test_it_knows_what_is_waiting_on_them(tenant, account):
    """A leave request their report made is waiting on somebody who is
    about to not be here. It will wait forever unless somebody notices."""
    boss = person(tenant)
    mine = person(tenant, reports_to=boss["id"])
    as_staff(tenant, mine)
    tenant.post("/api/employee/leave", json={
        "leave_type": "annual", "start_date": "2026-12-01", "end_date": "2026-12-02",
        "reason": "x"})
    tenant.post("/api/employee/expenses", json={
        "category": "travel", "amount": "5", "spent_on": TODAY, "description": "x"})
    as_hr(tenant, account)
    c = checklist(tenant, boss)
    assert c["decisions_waiting_on_them"] == 2
    assert c["ready"] is False
    assert any("2 decision" in b for b in c["blocking"]), c["blocking"]


def test_it_knows_what_they_are_owed(tenant, account):
    staff = person(tenant)
    as_staff(tenant, staff)
    r = tenant.post("/api/employee/expenses", json={
        "category": "travel", "amount": "40.00", "spent_on": TODAY, "description": "x"})
    as_hr(tenant, account)
    tenant.post(f"/api/expenses/{r.json()['id']}/decide", json={"action": "approve"})
    c = checklist(tenant, staff)
    assert c["expenses_owed"] == 40.0
    # Owed money is settled in the final pay. It is not a reason to keep the
    # account alive.
    assert c["ready"] is True


def test_it_knows_the_leave_they_are_owed(tenant):
    staff = person(tenant)
    c = checklist(tenant, staff)
    assert c["leave_owed_days"] >= 0
    assert "leave_owed_days" in c


def test_somebody_with_nothing_open_is_ready(tenant):
    staff = person(tenant)
    c = checklist(tenant, staff)
    assert c["ready"] is True
    assert c["blocking"] == []
    assert c["portal_access"] is True


# --- completing ----------------------------------------------------------------------------

def test_completing_needs_a_last_day(tenant):
    staff = person(tenant)
    assert leave(tenant, staff, end_date="").status_code == 400
    assert leave(tenant, staff, end_date="soon").status_code == 400


def test_completing_closes_the_account(tenant):
    staff = person(tenant)
    res = leave(tenant, staff, end_date="2026-09-30")
    assert res.status_code == 200, res.text
    with main.SessionLocal() as db:
        row = db.query(models.DBEmployee).filter(models.DBEmployee.id == staff["id"]).first()
        assert row.status == "terminated"
        assert row.end_date == "2026-09-30"
        assert row.offboarding_complete is True
    assert checklist(tenant, staff)["portal_access"] is False


def test_and_they_can_no_longer_sign_in(tenant):
    staff = person(tenant)
    leave(tenant, staff)
    main.rate_limiter._hits.clear()
    tenant.post("/api/client/logout")
    res = tenant.post("/api/employee/auth/login",
                      json={"email": staff["email"], "password": EMP_PASSWORD})
    # The same answer a stranger gets. Saying "you have left" would confirm
    # the address once belonged to somebody here.
    assert res.status_code == 401


def test_it_is_refused_while_equipment_is_out(tenant):
    """The check that was never made. The record said offboarding; the
    laptop was at their house."""
    staff = person(tenant)
    issue_asset(tenant, staff, "LAP-014")
    res = leave(tenant, staff)
    assert res.status_code == 409, res.text
    assert "not returned" in res.json()["detail"]
    with main.SessionLocal() as db:
        row = db.query(models.DBEmployee).filter(models.DBEmployee.id == staff["id"]).first()
        assert row.status != "terminated"


def test_unless_hr_says_to_go_ahead_and_says_why(tenant):
    """A laptop written off is a decision. It is recorded as one."""
    staff = person(tenant, first_name="Gone", last_name="Away")
    issue_asset(tenant, staff, "LAP-014")
    assert leave(tenant, staff, force=True).status_code == 400          # no reason
    res = leave(tenant, staff, force=True, force_note="Laptop written off, reported to insurer")
    assert res.status_code == 200, res.text
    assert res.json()["went_ahead_with"], res.json()
    with main.SessionLocal() as db:
        row = db.query(models.DBAuditLog).filter(
            models.DBAuditLog.action == "employee_left").order_by(
                models.DBAuditLog.id.desc()).first()
        assert "written off" in (row.details or ""), row.details


def test_it_is_refused_while_their_teams_decisions_wait_on_them(tenant, account):
    boss = person(tenant)
    mine = person(tenant, reports_to=boss["id"])
    as_staff(tenant, mine)
    tenant.post("/api/employee/leave", json={
        "leave_type": "annual", "start_date": "2026-12-01", "end_date": "2026-12-02",
        "reason": "x"})
    as_hr(tenant, account)
    res = leave(tenant, boss)
    assert res.status_code == 409
    assert "decision" in res.json()["detail"]


def test_completing_twice_is_refused(tenant):
    staff = person(tenant)
    assert leave(tenant, staff).status_code == 200
    assert leave(tenant, staff).status_code == 409


# --- their people ------------------------------------------------------------------------------

def test_their_reports_move_to_whoever_is_named(tenant):
    boss = person(tenant)
    successor = person(tenant, first_name="New", last_name="Boss")
    a = person(tenant, reports_to=boss["id"])
    b = person(tenant, reports_to=boss["id"])
    res = leave(tenant, boss, reassign_to=successor["id"])
    assert res.status_code == 200, res.text
    assert res.json()["reports_moved"] == 2
    with main.SessionLocal() as db:
        for who in (a, b):
            row = db.query(models.DBEmployee).filter(models.DBEmployee.id == who["id"]).first()
            assert row.reports_to == successor["id"]


def test_and_are_told(tenant):
    boss = person(tenant)
    successor = person(tenant, first_name="New", last_name="Boss")
    a = person(tenant, reports_to=boss["id"])
    leave(tenant, boss, reassign_to=successor["id"])

    as_staff(tenant, a)
    notes = tenant.get("/api/employee/notifications").json()["notifications"]
    assert any("New Boss" in n["message"] for n in notes), notes
    as_staff(tenant, successor)
    notes = tenant.get("/api/employee/notifications").json()["notifications"]
    assert any("now report" in n["title"] for n in notes), notes


def test_or_are_left_without_a_manager_rather_than_pointing_at_a_ghost(tenant):
    """Better a gap the org chart shows than a line to somebody who has gone
    - and a leave request routed to nobody, which is where this started."""
    boss = person(tenant)
    a = person(tenant, reports_to=boss["id"])
    res = leave(tenant, boss)
    assert res.status_code == 200
    assert res.json()["reports_moved"] == 1
    with main.SessionLocal() as db:
        row = db.query(models.DBEmployee).filter(models.DBEmployee.id == a["id"]).first()
        assert row.reports_to is None


def test_they_cannot_be_reassigned_to_the_person_leaving(tenant):
    boss = person(tenant)
    person(tenant, reports_to=boss["id"])
    assert leave(tenant, boss, reassign_to=boss["id"]).status_code == 400


def test_nor_to_somebody_who_has_also_left(tenant):
    boss = person(tenant)
    gone = person(tenant)
    leave(tenant, gone)
    person(tenant, reports_to=boss["id"])
    assert leave(tenant, boss, reassign_to=gone["id"]).status_code == 404


def test_nor_to_another_businesss_employee(tenant, client, account):
    boss = person(tenant)
    person(tenant, reports_to=boss["id"])
    email = f"other-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/client/register", json={
        "email": email, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    client.post("/api/client/login", json={"email": email, "password": "Passw0rdTest"})
    outsider = person(client)
    as_hr(tenant, account)
    assert leave(tenant, boss, reassign_to=outsider["id"]).status_code == 404


def test_a_department_they_headed_passes_to_the_successor(tenant):
    boss = person(tenant)
    successor = person(tenant)
    d = tenant.post("/api/departments", json={"name": f"D-{uuid.uuid4().hex[:5]}"}).json()
    tenant.put(f"/api/departments/{d['id']}/head", json={"head_id": boss["id"]})
    leave(tenant, boss, reassign_to=successor["id"])
    assert tenant.get(f"/api/departments/{d['id']}").json()["head_id"] == successor["id"]


def test_or_is_left_headless_rather_than_headed_by_a_ghost(tenant):
    boss = person(tenant)
    d = tenant.post("/api/departments", json={"name": f"D-{uuid.uuid4().hex[:5]}"}).json()
    tenant.put(f"/api/departments/{d['id']}/head", json={"head_id": boss["id"]})
    leave(tenant, boss)
    assert tenant.get(f"/api/departments/{d['id']}").json()["head_id"] is None


# --- whose it is -------------------------------------------------------------------------------------

def test_another_business_cannot_see_or_close_it(tenant, client, account):
    staff = person(tenant)
    email = f"other-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/client/register", json={
        "email": email, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    client.post("/api/client/login", json={"email": email, "password": "Passw0rdTest"})
    assert client.get(f"/api/employees/{staff['id']}/offboarding").status_code == 404
    assert client.post(f"/api/employees/{staff['id']}/complete-offboard",
                       json={"end_date": TODAY}).status_code == 404
