"""Search across the HR side, and the spreadsheets people ask for.

Typing a skill answers who can do it, a policy title opens it, a department
opens its people. And leave, absence and the pay review come out as CSV,
because the question "can I have that as a spreadsheet" is always the
next one.
"""
from datetime import date, timedelta

import pytest

import main
from conftest import make_employee


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


def person(tenant, **kw):
    kw.setdefault("password", "EmpPass123")
    return make_employee(tenant, **kw)


def test_search_finds_skills_policies_and_departments(tenant):
    emp = person(tenant, first_name="Ann")
    tenant.put(f"/api/employees/{emp['id']}/skills", json={"skills": [{"name": "Payroll run", "level": 4}]})
    tenant.post("/api/policies", json={"title": "Expenses policy", "body": "Keep receipts."})
    tenant.post("/api/departments", json={"name": "Payroll team"})
    hits = tenant.get("/api/search?q=payroll").json()["results"]
    kinds = {(h["type"], h["label"]) for h in hits}
    assert ("skill", "Payroll run") in kinds and ("department", "Payroll team") in kinds
    skill = next(h for h in hits if h["type"] == "skill")
    assert skill["sub"] == "1 person has it"
    assert any(h["type"] == "policy" and h["label"] == "Expenses policy" for h in tenant.get("/api/search?q=expenses").json()["results"])


def test_the_spreadsheets(tenant):
    emp = person(tenant, first_name="Ann", last_name="Lee", level="L3", salary=3000.0)
    tenant.put("/api/pay-bands/L3", json={"min": 30000, "max": 50000})
    with main.SessionLocal() as db:
        e = db.get(main.models.DBEmployee, emp["id"])
        db.add(main.models.DBLeaveRequest(client_id=e.client_id, employee_id=emp["id"], leave_type="sick",
                                          start_date=(date.today() - timedelta(days=3)).isoformat(),
                                          end_date=(date.today() - timedelta(days=2)).isoformat(), days=2, status="approved"))
        db.commit()
    leave = tenant.get("/api/leave/export.csv")
    assert leave.headers["content-type"].startswith("text/csv") and "Ann Lee,sick," in leave.text
    assert "Ann Lee" not in tenant.get(f"/api/leave/export.csv?year={date.today().year - 1}").text
    absence = tenant.get("/api/absence/export.csv").text
    assert absence.splitlines()[0] == "name,job_title,spells,days,bradford,band,last_spell" and "Ann Lee,,1,2.0,2,Fine" in absence
    pay = tenant.get("/api/pay-review/export.csv").text
    assert pay.splitlines()[0].startswith("name,job_title,department,level") and "Ann Lee,,,L3,monthly,3000.0,36000.0,30000.0,40000.0,50000.0,0.9,within" in pay


def test_the_spreadsheets_are_hr_only(tenant):
    emp = person(tenant)
    main.rate_limiter._hits.clear()
    tenant.post("/api/client/logout")
    tenant.post("/api/employee/auth/login", json={"email": emp["email"], "password": "EmpPass123"})
    for p in ("/api/leave/export.csv", "/api/absence/export.csv", "/api/pay-review/export.csv"):
        assert tenant.get(p).status_code in (401, 403), p
