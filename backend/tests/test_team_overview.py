"""Everything a manager owes their team, in one answer.

Who is in and who is off today, what is waiting for a decision, reviews to
write, one-to-ones gone quiet, probations ending, skills to confirm,
goals overdue. Somebody who manages nobody gets an empty answer rather
than a page.
"""
from datetime import date, timedelta

import pytest

import main
from conftest import make_employee

EMP_PASSWORD = "EmpPass123"


def days(n):
    return (date.today() + timedelta(days=n)).isoformat()


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
    res = client.post("/api/employee/auth/login", json={"email": emp["email"], "password": EMP_PASSWORD})
    assert res.status_code == 200, res.text


def test_somebody_with_no_reports_is_not_a_manager(tenant):
    emp = person(tenant)
    as_staff(tenant, emp)
    out = tenant.get("/api/employee/team-overview").json()
    assert out["is_manager"] is False and out["reports"] == [] and out["waiting"] == []


def test_the_overview_gathers_what_the_manager_owes(tenant, account):
    boss = person(tenant, first_name="Bea", probation_months=0)
    a = person(tenant, first_name="Ann", reports_to=boss["id"], probation_end=days(5))
    b = person(tenant, first_name="Bob", reports_to=boss["id"], probation_months=0)
    gone = person(tenant, first_name="Gone", reports_to=boss["id"])
    tenant.put(f"/api/employees/{gone['id']}", json={"status": "terminated"})
    # Ann is off today; Bob has an overdue goal and a skill to confirm; a review cycle is open.
    with main.SessionLocal() as db:
        db.add(main.models.DBLeaveRequest(client_id=db.get(main.models.DBEmployee, a["id"]).client_id, employee_id=a["id"],
                                          leave_type="annual", start_date=days(-1), end_date=days(1), days=3, status="approved"))
        db.commit()
    tenant.post(f"/api/employees/{b['id']}/goals", json={"title": "Late", "target_value": 5, "current_value": 1, "due_date": days(-2)})
    c = tenant.post("/api/review-cycles", json={"name": "H1"}).json()
    tenant.post(f"/api/review-cycles/{c['id']}/open")
    as_staff(tenant, b)
    tenant.put("/api/employee/skills", json={"skills": [{"name": "SQL", "level": 3}]})
    tenant.post("/api/employee/leave", json={"leave_type": "annual", "start_date": days(20), "end_date": days(21), "reason": "x"})
    as_staff(tenant, boss)
    out = tenant.get("/api/employee/team-overview").json()
    # Signing in to the portal clocks Bob in, so he is "in" and Ann is off.
    assert out["is_manager"] and out["summary"] == {"reports": 2, "in": 1, "off": 1, "not_in": 0}
    rows = {r["name"].split()[0]: r for r in out["reports"]}
    assert set(rows) == {"Ann", "Bob"}, "the leaver is not on the team"
    assert rows["Ann"]["today"] == "off" and rows["Ann"]["today_detail"].startswith("annual until")
    assert rows["Bob"]["today"] == "in" and rows["Bob"]["today_detail"].startswith("since")
    assert rows["Ann"]["probation"]["due"] and rows["Bob"]["probation"] is None
    assert rows["Bob"]["goals_overdue"] == 1 and rows["Bob"]["skills_to_confirm"] == 1
    assert rows["Ann"]["review_to_write"] and rows["Ann"]["one_to_one_quiet"]
    waiting = {w["key"]: w["count"] for w in out["waiting"]}
    assert waiting["approvals"] == 1 and waiting["reviews"] == 2 and waiting["one_to_ones"] == 2
    assert waiting["probations"] == 1 and waiting["skills"] == 1 and waiting["goals"] == 1
    # A one-to-one held this month takes Ann out of the quiet list.
    ci = tenant.post("/api/employee/check-ins", json={"scheduled_for": days(-3), "employee_id": a["id"]}).json()
    tenant.post(f"/api/employee/check-ins/{ci['id']}/complete", json={"notes": "Held"})
    out = tenant.get("/api/employee/team-overview").json()
    assert not {r["name"].split()[0]: r for r in out["reports"]}["Ann"]["one_to_one_quiet"]
    assert {w["key"]: w["count"] for w in out["waiting"]}["one_to_ones"] == 1
