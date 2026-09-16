"""The leave year: accrual, carry-over, pro-rata.

A balance is for the leave year that contains today, not for all time -
last year's days no longer eat this year's. The year starts on a day the
business picks; days come up front or month by month; what is left at the
end carries over up to a cap and lapses after a while; a joiner gets the
share of the year they are here for. The policy is the business's own.
"""
from datetime import date, timedelta

import pytest

import main
from conftest import make_employee


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


def emp_row(emp_id):
    with main.SessionLocal() as db:
        return db.get(main.models.DBEmployee, emp_id)


def balance(emp_id, today):
    with main.SessionLocal() as db:
        return main.leave_balance_for(db, db.get(main.models.DBEmployee, emp_id), today)


def person(tenant, start_date, annual):
    """Somebody who joined on a day with a yearly entitlement."""
    emp = make_employee(tenant, start_date=start_date, password="EmpPass123")
    res = tenant.put(f"/api/employees/{emp['id']}/leave-entitlement", json={"annual_days": annual})
    assert res.status_code == 200, res.text
    return emp


def approved(tenant, emp_id, start, end, days, kind="annual"):
    with main.SessionLocal() as db:
        e = db.get(main.models.DBEmployee, emp_id)
        db.add(main.models.DBLeaveRequest(client_id=e.client_id, employee_id=emp_id, leave_type=kind,
                                          start_date=start, end_date=end, days=days, status="approved"))
        db.commit()


def policy(tenant, **body):
    res = tenant.put("/api/hr/leave-policy", json=body)
    assert res.status_code == 200, res.text
    return res.json()


def test_last_years_days_no_longer_count_against_this_year(tenant):
    emp = person(tenant, "2024-03-01", 20)
    approved(tenant, emp["id"], "2025-06-02", "2025-06-06", 5)
    approved(tenant, emp["id"], "2026-02-02", "2026-02-03", 2)
    b = balance(emp["id"], date(2026, 6, 15))
    assert b["leave_year_start"] == "2026-01-01" and b["leave_year_end"] == "2026-12-31"
    assert b["annual_taken"] == 2 and b["annual_total"] == 20 and b["annual_remaining"] == 18
    assert b["annual_carried"] == 0, "nothing carries over unless the business allows it"
    assert balance(emp["id"], date(2025, 12, 1))["annual_taken"] == 5, "and last year's balance still reads right"


def test_the_leave_year_can_start_in_april(tenant):
    p = policy(tenant, year_start="04-01")
    assert p["year_start"] == "04-01" and p["current_year_start"].endswith("-04-01")
    emp = person(tenant, "2024-03-01", 24)
    approved(tenant, emp["id"], "2026-03-10", "2026-03-11", 2)      # last leave year
    approved(tenant, emp["id"], "2026-05-04", "2026-05-05", 2)      # this one
    b = balance(emp["id"], date(2026, 6, 15))
    assert b["leave_year_start"] == "2026-04-01" and b["leave_year_end"] == "2027-03-31"
    assert b["annual_taken"] == 2 and b["annual_remaining"] == 22
    assert balance(emp["id"], date(2026, 3, 20))["leave_year_start"] == "2025-04-01"
    assert tenant.put("/api/hr/leave-policy", json={"year_start": "31-12"}).status_code == 400
    assert tenant.put("/api/hr/leave-policy", json={"accrual": "weekly"}).status_code == 400
    assert tenant.put("/api/hr/leave-policy", json={"carry_over_max": -1}).status_code == 400


def test_a_joiner_gets_the_share_of_the_year_they_are_here_for(tenant):
    emp = person(tenant, "2026-07-01", 24)
    b = balance(emp["id"], date(2026, 9, 1))
    assert b["annual_accrued"] == 12.1, "half the year left, near enough (184 of 365 days)"
    policy(tenant, pro_rata=False)
    assert balance(emp["id"], date(2026, 9, 1))["annual_accrued"] == 24
    later = person(tenant, "2027-02-01", 24)
    assert balance(later["id"], date(2026, 9, 1))["annual_accrued"] == 0, "not here yet"


def test_monthly_accrual_earns_days_as_the_year_goes(tenant):
    policy(tenant, accrual="monthly")
    emp = person(tenant, "2024-01-01", 24)
    assert balance(emp["id"], date(2026, 1, 1))["annual_accrued"] == 0
    assert balance(emp["id"], date(2026, 1, 30))["annual_accrued"] == 0, "a month is earned at the end of its last day"
    assert balance(emp["id"], date(2026, 1, 31))["annual_accrued"] == 2
    assert balance(emp["id"], date(2026, 7, 15))["annual_accrued"] == 12
    assert balance(emp["id"], date(2026, 12, 31))["annual_accrued"] == 24, "the last month is not lost to the year after"
    joiner = person(tenant, "2026-03-15", 24)
    assert balance(joiner["id"], date(2026, 6, 20))["annual_accrued"] == 6, "three whole months since joining"
    assert balance(joiner["id"], date(2026, 6, 13))["annual_accrued"] == 4


def test_what_is_left_carries_over_up_to_the_cap_and_then_lapses(tenant):
    policy(tenant, carry_over_max=5, carry_over_expires_months=3)
    emp = person(tenant, "2024-01-01", 20)
    approved(tenant, emp["id"], "2025-08-04", "2025-08-08", 5)             # 15 left last year, capped to 5
    b = balance(emp["id"], date(2026, 2, 1))
    assert b["annual_carried"] == 5 and b["annual_total"] == 25 and b["carry_expires_on"] == "2026-03-31"
    assert b["annual_remaining"] == 25
    # Two of the carried days used before it lapses: they stay; the other three go.
    approved(tenant, emp["id"], "2026-02-09", "2026-02-10", 2)
    b = balance(emp["id"], date(2026, 4, 15))
    assert b["annual_carried"] == 2 and b["annual_total"] == 22 and b["annual_taken"] == 2 and b["annual_remaining"] == 20
    # Never lapsing.
    policy(tenant, carry_over_expires_months=0)
    b = balance(emp["id"], date(2026, 4, 15))
    assert b["annual_carried"] == 5 and b["carry_expires_on"] == "" and b["annual_remaining"] == 23
    # Somebody who used it all last year carries nothing; a joiner this year carries nothing.
    used = person(tenant, "2024-01-01", 20)
    approved(tenant, used["id"], "2025-03-03", "2025-03-28", 20)
    assert balance(used["id"], date(2026, 2, 1))["annual_carried"] == 0
    new = person(tenant, "2026-01-10", 20)
    assert balance(new["id"], date(2026, 2, 1))["annual_carried"] == 0


def test_a_request_is_checked_against_this_years_balance(tenant):
    emp = person(tenant, "2024-01-01", 3)
    last_year = date.today().replace(year=date.today().year - 1)
    approved(tenant, emp["id"], last_year.isoformat(), last_year.isoformat(), 3)   # would have used it all, once
    tenant.put("/api/attendance/settings", json={"working_days": "1,2,3,4,5,6,7"})
    main.rate_limiter._hits.clear()
    tenant.post("/api/client/logout")
    assert tenant.post("/api/employee/auth/login", json={"email": emp["email"], "password": "EmpPass123"}).status_code == 200
    soon = (date.today() + timedelta(days=30)).isoformat()
    res = tenant.post("/api/employee/leave", json={"leave_type": "annual", "start_date": soon, "end_date": soon, "reason": "x"})
    assert res.status_code == 200, res.text
    b = tenant.get("/api/employee/leave-balance").json()
    assert b["annual_pending"] == 1 and b["annual_remaining"] == 2 and "leave_year_start" in b


def test_the_policy_is_read_back_and_logged_and_is_the_business_s_own(tenant, account):
    p = tenant.get("/api/hr/leave-policy").json()
    assert p == {"year_start": "01-01", "accrual": "upfront", "carry_over_max": 0.0, "carry_over_expires_months": 3, "pro_rata": True,
                 "current_year_start": f"{date.today().year}-01-01", "current_year_end": f"{date.today().year}-12-31", "accruals": ["upfront", "monthly"]}
    policy(tenant, year_start="04-01", accrual="monthly", carry_over_max=10, carry_over_expires_months=6, pro_rata=False)
    p = tenant.get("/api/hr/leave-policy").json()
    assert (p["year_start"], p["accrual"], p["carry_over_max"], p["carry_over_expires_months"], p["pro_rata"]) == ("04-01", "monthly", 10.0, 6, False)
    assert any(l["action"] == "leave_policy_updated" for l in tenant.get("/api/audit-logs").json())
    other = f"other-{account['email']}"
    tenant.post("/api/client/logout")
    main.rate_limiter._hits.clear()
    tenant.post("/api/client/register", json={"email": other, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    tenant.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})
    assert tenant.get("/api/hr/leave-policy").json()["year_start"] == "01-01"
