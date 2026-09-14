"""The numbers a head of people is asked for.

How many are here, how many came and went this year, how fast people
leave, how long they stay, and whether the reviews, certifications, leave
and goals are where they should be. All of it worked out from rows that
already exist, so it is right the day it is switched on and needs nothing
kept up to date. The tests build a small company with a known history and
check the arithmetic.
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


def leaves(tenant, emp, on):
    res = tenant.put(f"/api/employees/{emp['id']}", json={"status": "terminated", "end_date": on})
    assert res.status_code == 200, res.text


def analytics(tenant):
    res = tenant.get("/api/hr/analytics")
    assert res.status_code == 200, res.text
    return res.json()


def test_an_empty_company_is_all_zeros_not_an_error(tenant):
    a = analytics(tenant)
    assert a["headcount"]["now"] == 0
    assert a["headcount"]["turnover_pct"] == 0.0
    assert len(a["headcount"]["by_month"]) == 12
    assert a["reviews"] is None
    assert a["certifications"]["total"] == 0


def test_headcount_joiners_and_leavers_by_month(tenant):
    person(tenant, start_date=days(-400))                       # old hand
    person(tenant, start_date=days(-40))                        # joined last month or so
    gone = person(tenant, start_date=days(-300))
    leaves(tenant, gone, days(-10))                             # left this month
    a = analytics(tenant)["headcount"]
    assert a["now"] == 2
    assert a["joiners_12m"] == 2                # the recent joiner and the leaver both came this year
    assert a["leavers_12m"] == 1
    months = a["by_month"]
    assert months[-1]["month"] == date.today().strftime("%Y-%m")
    assert sum(m["joiners"] for m in months) == 2
    assert sum(m["leavers"] for m in months) == 1
    assert months[0]["headcount"] == 1          # a year ago only the old hand was here
    assert months[-1]["headcount"] == 2


def test_turnover_is_leavers_over_average_headcount(tenant):
    for _ in range(4):
        person(tenant, start_date=days(-800))
    gone = person(tenant, start_date=days(-800))
    leaves(tenant, gone, days(-100))
    a = analytics(tenant)["headcount"]
    # Five for the first part of the year, four after: average between 4 and 5,
    # one leaver, so turnover sits between 20 and 25 percent.
    assert 20.0 <= a["turnover_pct"] <= 25.0, a
    assert 4.0 <= a["average_headcount_12m"] <= 5.0


def test_tenure_and_its_bands(tenant):
    person(tenant, start_date=days(-100))       # under a year
    person(tenant, start_date=days(-500))       # 1-2
    person(tenant, start_date=days(-1200))      # 2-5
    person(tenant, start_date=days(-2500))      # over 5
    gone = person(tenant, start_date=days(-4000))
    leaves(tenant, gone, days(-1))              # leavers do not count towards tenure
    a = analytics(tenant)["headcount"]
    assert a["tenure_bands"] == {"under_1": 1, "1_to_2": 1, "2_to_5": 1, "over_5": 1}
    assert 2.5 < a["average_tenure_years"] < 3.5


def test_who_is_where(tenant):
    sales = tenant.post("/api/departments", json={"name": "Sales"}).json()
    person(tenant, department_id=sales["id"], employment_type="full_time")
    person(tenant, department_id=sales["id"], employment_type="part_time")
    person(tenant)
    a = analytics(tenant)["headcount"]
    assert a["by_department"][0] == {"name": "Sales", "count": 2}
    assert {"name": "No department", "count": 1} in a["by_department"]
    assert {"name": "part_time", "count": 1} in a["by_type"]


def test_the_latest_review_cycle_is_summarised(tenant):
    boss = person(tenant)
    person(tenant, reports_to=boss["id"])
    c = tenant.post("/api/review-cycles", json={"name": "H1"}).json()
    tenant.post(f"/api/review-cycles/{c['id']}/open")
    detail = tenant.get(f"/api/review-cycles/{c['id']}").json()
    boss_review = next(r for r in detail["reviews"] if r["employee_id"] == boss["id"])
    tenant.post(f"/api/reviews/{boss_review['id']}/manager", json={
        "answers": [{"rating": 4}] * 6, "rating": 4, "summary": "Solid"})
    r = analytics(tenant)["reviews"]
    assert r["cycle_name"] == "H1" and r["total"] == 2
    assert r["complete"] == 1 and r["awaiting_self"] == 1
    assert r["average"] == 4.0 and r["distribution"]["4"] == 1


def test_certifications_leave_and_goals(tenant):
    emp = person(tenant)
    tenant.post(f"/api/employees/{emp['id']}/certifications", json={"name": "A", "expires_on": days(5)})
    tenant.post(f"/api/employees/{emp['id']}/certifications", json={"name": "B", "expires_on": days(-5)})
    tenant.post(f"/api/employees/{emp['id']}/goals", json={
        "title": "Ten", "target_value": 10, "current_value": 5})
    tenant.post(f"/api/employees/{emp['id']}/goals", json={
        "title": "Late", "target_value": 10, "current_value": 0, "due_date": days(-3)})
    a = analytics(tenant)
    assert a["certifications"] == {"total": 2, "valid": 0, "expiring": 1, "expired": 1,
                                   "unverified": 0, "people_with_one": 1}
    assert a["goals"]["total"] == 2 and a["goals"]["overdue"] == 1
    assert a["goals"]["average_progress_pct"] == 25
    assert a["leave"]["days_taken"] == 0.0


def test_moves_in_the_last_year_are_counted(tenant):
    emp = person(tenant, job_title="Analyst", salary=3000.0)
    tenant.put(f"/api/employees/{emp['id']}", json={"salary": 3300})
    tenant.post(f"/api/employees/{emp['id']}/history", json={"kind": "promotion", "note": "Lead"})
    tenant.post(f"/api/employees/{emp['id']}/history", json={
        "kind": "promotion", "note": "Long ago", "effective_on": "2019-01-01"})
    m = analytics(tenant)["moves_12m"]
    assert m == {"promotions": 1, "pay_changes": 1, "transfers": 0, "manager_changes": 0}


def test_it_is_for_hr_only(tenant):
    emp = person(tenant)
    main.rate_limiter._hits.clear()
    tenant.post("/api/client/logout")
    tenant.post("/api/employee/auth/login", json={"email": emp["email"], "password": EMP_PASSWORD})
    assert tenant.get("/api/hr/analytics").status_code in (401, 403)
