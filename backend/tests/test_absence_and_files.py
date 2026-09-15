"""Sickness read the way HR reads it, and people in and out as a file.

The Bradford score is spells squared times days over fifty-two weeks -
ten separate Mondays disrupt more than one fortnight - with the usual
bands, and the day-of-week pattern beside it. A CSV of people goes in
checked row by row, with a dry run that says what would happen and what
is wrong; the same columns come out; and everything about one person
comes out as one file, for a subject access request or for the person
themselves, without the manager's private notes.
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
    res = client.post("/api/employee/auth/login",
                      json={"email": emp["email"], "password": EMP_PASSWORD})
    assert res.status_code == 200, res.text


def sick(tenant, emp_id, start_days_ago, length=1):
    """An approved sick spell written straight in, dated in the past."""
    with main.SessionLocal() as db:
        start = date.today() - timedelta(days=start_days_ago)
        emp = db.get(main.models.DBEmployee, emp_id)
        db.add(main.models.DBLeaveRequest(client_id=emp.client_id, employee_id=emp_id, leave_type="sick",
                                          start_date=start.isoformat(),
                                          end_date=(start + timedelta(days=length - 1)).isoformat(),
                                          days=float(length), status="approved"))
        db.commit()


# --- absence -------------------------------------------------------------------------

def test_bradford_is_spells_squared_times_days(tenant):
    often = person(tenant, first_name="Often")
    once = person(tenant, first_name="Once")
    for ago in (10, 40, 70, 100):
        sick(tenant, often["id"], ago, 1)           # 4 spells, 4 days -> 64
    sick(tenant, once["id"], 20, 10)                # 1 spell, 10 days -> 10
    out = tenant.get("/api/absence").json()
    rows = {p["name"].split()[0]: p for p in out["people"]}
    assert rows["Often"]["bradford"] == 64 and rows["Often"]["band"] == "Watch" and rows["Often"]["spells"] == 4
    assert rows["Once"]["bradford"] == 10 and rows["Once"]["band"] == "Fine"
    assert [p["name"].split()[0] for p in out["people"]] == ["Often", "Once"]
    assert out["totals"]["sick_days"] == 14.0 and out["totals"]["spells"] == 5
    assert out["totals"]["people_off_sick"] == 2


def test_only_approved_sick_leave_inside_a_year_counts(tenant):
    emp = person(tenant)
    sick(tenant, emp["id"], 400, 5)                 # too old
    with main.SessionLocal() as db:
        db.add(main.models.DBLeaveRequest(client_id=db.get(main.models.DBEmployee, emp["id"]).client_id,
                                          employee_id=emp["id"], leave_type="annual", start_date=days(-5),
                                          end_date=days(-5), days=1, status="approved"))
        db.add(main.models.DBLeaveRequest(client_id=db.get(main.models.DBEmployee, emp["id"]).client_id,
                                          employee_id=emp["id"], leave_type="sick", start_date=days(-3),
                                          end_date=days(-3), days=1, status="pending"))
        db.commit()
    assert tenant.get("/api/absence").json()["people"] == []
    gone = person(tenant)
    sick(tenant, gone["id"], 5, 2)
    tenant.put(f"/api/employees/{gone['id']}", json={"status": "terminated"})
    assert tenant.get("/api/absence").json()["people"] == []


def test_the_weekday_pattern_and_the_bands(tenant):
    emp = person(tenant)
    monday = date.today() - timedelta(days=date.today().weekday() + 7)     # last Monday
    for weeks in range(3):
        sick(tenant, emp["id"], (date.today() - (monday - timedelta(weeks=weeks))).days, 1)
    out = tenant.get("/api/absence").json()
    by_day = {d["day"]: d["spells"] for d in out["spells_by_weekday"]}
    assert by_day["Mon"] == 3 and by_day["Fri"] == 0
    assert [b["label"] for b in out["bands"]] == ["Fine", "Watch", "Concern", "Act", "Serious"]
    a = tenant.get("/api/hr/analytics").json()["absence"]
    assert a["spells"] == 3 and a["top"][0]["bradford"] == 27


# --- a file in -----------------------------------------------------------------------------

CSV = """first_name,last_name,email,job_title,department,manager_email,level,salary,start_date
Bea,Boss,bea@acme.example,Head of Ops,Ops,,L6,6000,2024-01-15
Ravi,Kumar,ravi@acme.example,Analyst,Ops,bea@acme.example,L3,3000,2026-08-01
Bad,Row,not-an-email,,,,,,
Lena,Ortiz,lena@acme.example,Designer,Design,bea@acme.example,L9,abc,2026-13-40
"""


def test_a_dry_run_says_what_would_happen_and_writes_nothing(tenant):
    before = len(tenant.get("/api/employees").json())
    res = tenant.post("/api/people/import?dry_run=1", json={"csv": CSV})
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["dry_run"] and out["summary"] == {"rows": 4, "create": 2, "update": 0, "skip": 2}
    by_row = {r["row"]: r for r in out["rows"]}
    assert by_row[4]["problems"] == ["no email"]
    assert set(by_row[5]["problems"]) == {"unknown level L9", "start_date is not YYYY-MM-DD", "salary is not a number"}
    assert by_row[2]["new_department"] is True
    assert len(tenant.get("/api/employees").json()) == before


def test_the_file_is_written_with_departments_and_managers_resolved(tenant):
    res = tenant.post("/api/people/import", json={"csv": CSV})
    assert res.status_code == 200, res.text
    assert res.json()["summary"]["create"] == 2
    people = {e["email"]: e for e in tenant.get("/api/employees").json()}
    ravi = tenant.get(f"/api/employees/{people['ravi@acme.example']['id']}").json()
    assert ravi["department_name"] == "Ops" and ravi["manager_name"] == "Bea Boss"
    assert ravi["level"] == "L3" and ravi["salary"] == 3000.0 and ravi["start_date"] == "2026-08-01"
    assert ravi["probation"]["status"] == "on_probation"
    # The same file again updates rather than duplicates.
    again = tenant.post("/api/people/import", json={"csv": CSV.replace("Analyst", "Senior Analyst")}).json()
    assert again["summary"]["update"] == 2 and again["summary"]["create"] == 0
    assert len([e for e in tenant.get("/api/employees").json() if e["email"] == "ravi@acme.example"]) == 1
    assert tenant.get(f"/api/employees/{people['ravi@acme.example']['id']}").json()["job_title"] == "Senior Analyst"


def test_a_file_without_the_right_header_is_refused(tenant):
    assert tenant.post("/api/people/import", json={"csv": "name,phone\nA,1\n"}).status_code == 400
    assert tenant.post("/api/people/import", json={"csv": ""}).status_code == 400
    dup = "first_name,last_name,email\nA,B,x@y.example\nC,D,x@y.example\n"
    out = tenant.post("/api/people/import?dry_run=1", json={"csv": dup}).json()
    assert out["rows"][1]["problems"] == ["the same email twice in the file"]


def test_the_export_is_the_import_columns(tenant):
    person(tenant, first_name="Ann", last_name="Lee", job_title="Dev", level="L3")
    res = tenant.get("/api/people/export.csv")
    assert res.status_code == 200 and res.headers["content-type"].startswith("text/csv")
    lines = res.text.strip().splitlines()
    assert lines[0].startswith("first_name,last_name,email,job_title,department,manager_email,level")
    assert any(l.startswith("Ann,Lee,") and ",L3," in l for l in lines[1:])
    # And it goes back in.
    out = tenant.post("/api/people/import?dry_run=1", json={"csv": res.text}).json()
    assert out["summary"]["skip"] == 0 and out["summary"]["update"] == out["summary"]["rows"]


# --- one person as a file -------------------------------------------------------------------

def test_everything_about_one_person_but_never_the_managers_private_note(tenant, account):
    boss = person(tenant, first_name="Bea")
    emp = person(tenant, first_name="Ravi", reports_to=boss["id"], salary=3000.0)
    tenant.put(f"/api/employees/{emp['id']}", json={"salary": 3300})
    tenant.put(f"/api/employees/{emp['id']}/skills", json={"skills": [{"name": "SQL", "level": 3}]})
    as_staff(tenant, boss)
    c = tenant.post("/api/employee/check-ins", json={"scheduled_for": days(-1), "employee_id": emp["id"]}).json()
    tenant.post(f"/api/employee/check-ins/{c['id']}/complete", json={"notes": "Shared words", "private_note": "PRIVATE WORDS"})
    as_staff(tenant, emp)
    res = tenant.get("/api/employee/my-data")
    assert res.status_code == 200
    mine = res.json()
    assert mine["profile"]["email"] == emp["email"] and mine["profile"]["salary"] == 3300.0
    assert mine["employment_history"][0]["kind"] == "pay_change"
    assert mine["skills"][0]["name"] == "SQL"
    assert mine["one_to_ones"][0]["notes"] == "Shared words"
    assert "PRIVATE WORDS" not in res.text
    tenant.post("/api/employee/auth/logout")
    tenant.post("/api/client/login", json={"email": account["email"], "password": account["password"]})
    hr = tenant.get(f"/api/employees/{emp['id']}/export")
    assert hr.status_code == 200 and "PRIVATE WORDS" not in hr.text
    assert hr.json()["profile"]["manager"] == f"Bea {boss['last_name']}"
    assert tenant.get(f"/api/employees/{emp['id']}/export").json()["exported_at"]


def test_another_business_cannot_export_or_import_into_this_one(tenant, account):
    emp = person(tenant)
    other = f"other-{account['email']}"
    tenant.post("/api/client/logout")
    tenant.post("/api/client/register", json={"email": other, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    tenant.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})
    assert tenant.get(f"/api/employees/{emp['id']}/export").status_code == 404
    assert tenant.get("/api/people/export.csv").text.strip().count("\n") == 0
    assert tenant.get("/api/absence").json()["totals"]["people"] == 0
