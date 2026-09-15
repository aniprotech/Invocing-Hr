"""Who else is off, and the person's own morning.

A pending leave request carries the others in the same department already
approved off on any of those days - the question behind the decision -
for HR's list and the manager's approvals alike, and for nobody outside
the department. And a person whose portal filled up overnight gets one
email in the morning saying so, once, only if something did.
"""
from datetime import date, datetime, timedelta

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


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(main, "send_email_background",
                        lambda to, subject, body, from_email, html_body=None, **kw: (sent.append({"to": to, "subject": subject, "body": body}), (True, ""))[1])
    return sent


def person(tenant, **kw):
    kw.setdefault("password", EMP_PASSWORD)
    return make_employee(tenant, **kw)


def as_staff(client, emp):
    main.rate_limiter._hits.clear()
    client.post("/api/client/logout")
    res = client.post("/api/employee/auth/login", json={"email": emp["email"], "password": EMP_PASSWORD})
    assert res.status_code == 200, res.text


def approved_off(emp_id, start, end):
    with main.SessionLocal() as db:
        e = db.get(main.models.DBEmployee, emp_id)
        db.add(main.models.DBLeaveRequest(client_id=e.client_id, employee_id=emp_id, leave_type="annual",
                                          start_date=start, end_date=end, days=2, status="approved"))
        db.commit()


def test_a_pending_request_says_who_else_in_the_department_is_off(tenant, account):
    ops = tenant.post("/api/departments", json={"name": "Ops"}).json()
    boss = person(tenant, first_name="Bea", department_id=ops["id"])
    asker = person(tenant, first_name="Ravi", department_id=ops["id"], reports_to=boss["id"])
    mate = person(tenant, first_name="Mo", last_name="Off", department_id=ops["id"])
    elsewhere = person(tenant, first_name="Other")
    approved_off(mate["id"], days(11), days(12))          # overlaps
    approved_off(elsewhere["id"], days(11), days(12))     # another department: not a clash
    as_staff(tenant, asker)
    res = tenant.post("/api/employee/leave", json={"leave_type": "annual", "start_date": days(10), "end_date": days(11), "reason": "x"})
    assert res.status_code == 200, res.text
    as_staff(tenant, boss)
    row = tenant.get("/api/employee/approvals").json()["leave"][0]
    assert [o["name"] for o in row["others_off"]] == ["Mo Off"] and row["others_off"][0]["from"] == days(11)
    tenant.post("/api/employee/auth/logout")
    tenant.post("/api/client/login", json={"email": account["email"], "password": account["password"]})
    hr_row = next(l for l in tenant.get("/api/leave/requests").json() if l["employee_id"] == asker["id"])
    assert [o["name"] for o in hr_row["others_off"]] == ["Mo Off"]
    # Once decided, the question is moot and the list is not worked out.
    with main.SessionLocal() as db:
        lv = db.query(main.models.DBLeaveRequest).filter(main.models.DBLeaveRequest.employee_id == asker["id"]).first()
        main.decide_leave(db, lv, "approve", "HR")
        db.commit()
    hr_row = next(l for l in tenant.get("/api/leave/requests").json() if l["employee_id"] == asker["id"])
    assert hr_row["others_off"] == []


def test_a_person_gets_one_morning_email_when_something_landed(tenant, account, outbox):
    boss = person(tenant, first_name="Bea", probation_months=0)
    emp = person(tenant, first_name="Ravi", reports_to=boss["id"])
    c = tenant.post("/api/review-cycles", json={"name": "H1"}).json()
    tenant.post(f"/api/review-cycles/{c['id']}/open")          # tells everybody in the cycle
    with main.SessionLocal() as db:
        out = main.job_employee_digest(db, datetime.now().replace(hour=8))
    assert out.endswith("sent")
    mine = [m for m in outbox if m["to"] == emp["email"]]
    assert len(mine) == 1 and "Review: H1" in mine[0]["body"] and "thing" in mine[0]["subject"]
    with main.SessionLocal() as db:
        assert main.job_employee_digest(db, datetime.now().replace(hour=6)) == "too early"


def test_the_employee_digest_can_be_switched_off(tenant, account, outbox):
    boss = person(tenant, first_name="Bea", probation_months=0)
    emp = person(tenant, reports_to=boss["id"])
    c = tenant.post("/api/review-cycles", json={"name": "H1"}).json()
    tenant.post(f"/api/review-cycles/{c['id']}/open")
    tenant.post("/api/settings", json={"employee_digest": "0"})
    with main.SessionLocal() as db:
        main.job_employee_digest(db, datetime.now().replace(hour=8))
    assert not any(m["to"] == emp["email"] for m in outbox)
