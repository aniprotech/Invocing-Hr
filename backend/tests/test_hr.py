"""HR portal: employee lifecycle, leave rules and attendance maths."""
import pytest

import main
from conftest import make_employee, work_every_day
from main import working_days_between


# --- leave day counting ----------------------------------------------------

@pytest.mark.parametrize("start,end,expected", [
    ("2026-01-05", "2026-01-09", 5.0),   # Mon-Fri
    ("2026-01-05", "2026-01-11", 5.0),   # Mon-Sun, weekend excluded
    ("2026-01-05", "2026-01-05", 1.0),   # single day
    ("2026-01-10", "2026-01-11", 0.0),   # weekend only
    ("2026-01-09", "2026-01-05", 0.0),   # reversed
])
def test_working_days_between(start, end, expected):
    assert working_days_between(start, end) == expected


# --- leave requests --------------------------------------------------------

@pytest.fixture
def employee_session(client, tenant):
    """An employee logged into the employee portal."""
    emp = make_employee(tenant, password="EmpPass123")
    res = client.post("/api/employee/auth/login", json={
        "email": emp["email"], "password": "EmpPass123",
    })
    assert res.status_code == 200, res.text
    return {"employee": emp, "client": client}


def test_leave_days_are_computed_server_side(employee_session):
    c = employee_session["client"]
    res = c.post("/api/employee/leave", json={
        "leave_type": "annual", "start_date": "2026-03-02", "end_date": "2026-03-06",
        "days": 999,   # a hostile/incorrect client value must be ignored
    })
    assert res.status_code == 200, res.text
    assert res.json()["days"] == 5.0


def test_leave_cannot_exceed_entitlement(employee_session):
    c = employee_session["client"]
    res = c.post("/api/employee/leave", json={
        "leave_type": "annual", "start_date": "2026-04-01", "end_date": "2026-12-31",
    })
    assert res.status_code == 400
    assert "remaining" in res.json()["detail"]


def test_overlapping_leave_is_rejected(employee_session):
    c = employee_session["client"]
    assert c.post("/api/employee/leave", json={
        "leave_type": "annual", "start_date": "2026-05-04", "end_date": "2026-05-08",
    }).status_code == 200
    res = c.post("/api/employee/leave", json={
        "leave_type": "annual", "start_date": "2026-05-06", "end_date": "2026-05-12",
    })
    assert res.status_code == 409
    assert "overlaps" in res.json()["detail"]


def test_leave_dates_must_be_valid(employee_session):
    c = employee_session["client"]
    assert c.post("/api/employee/leave", json={
        "start_date": "2026-06-10", "end_date": "2026-06-01",
    }).status_code == 400
    assert c.post("/api/employee/leave", json={
        "start_date": "", "end_date": "",
    }).status_code == 400
    # A weekend-only range contains no working days.
    assert c.post("/api/employee/leave", json={
        "start_date": "2026-06-06", "end_date": "2026-06-07",
    }).status_code == 400


def test_leave_balance_reflects_pending_and_approved(client, tenant):
    emp = make_employee(tenant, password="EmpPass123")
    client.post("/api/employee/auth/login", json={"email": emp["email"], "password": "EmpPass123"})
    client.post("/api/employee/leave", json={
        "leave_type": "annual", "start_date": "2026-07-06", "end_date": "2026-07-10",
    })
    balance = client.get("/api/employee/leave").json()["balance"]
    assert balance["annual_total"] == 25
    assert balance["annual_pending"] == 5.0
    assert balance["annual_remaining"] == 20.0


def test_hr_can_approve_only_once(client, account):
    tenant = account["client"]
    emp = make_employee(tenant, password="EmpPass123")

    client.post("/api/employee/auth/login", json={"email": emp["email"], "password": "EmpPass123"})
    client.post("/api/employee/leave", json={
        "leave_type": "annual", "start_date": "2026-08-03", "end_date": "2026-08-07",
    })
    client.post("/api/employee/auth/logout")
    client.post("/api/client/login", json={"email": account["email"], "password": account["password"]})

    requests = tenant.get("/api/leave/requests").json()
    leave_id = requests[0]["id"]

    assert tenant.post(f"/api/leave/requests/{leave_id}/action", json={"action": "approve"}).status_code == 200
    # Second attempt must not silently re-approve and re-notify.
    assert tenant.post(f"/api/leave/requests/{leave_id}/action", json={"action": "approve"}).status_code == 409
    # An unrecognised action is rejected rather than treated as "reject".
    assert tenant.post(f"/api/leave/requests/{leave_id}/action", json={"action": "maybe"}).status_code == 400


def test_leave_entitlement_is_configurable(tenant):
    emp = make_employee(tenant)
    res = tenant.put(f"/api/employees/{emp['id']}/leave-entitlement",
                     json={"annual_days": 32, "sick_days": 5})
    assert res.status_code == 200, res.text
    assert res.json()["annual_total"] == 32
    assert res.json()["sick_remaining"] == 5

    assert tenant.put(f"/api/employees/{emp['id']}/leave-entitlement",
                      json={"annual_days": -1}).status_code == 400


# --- employee lifecycle ----------------------------------------------------

def test_employee_with_history_can_be_deleted(client, tenant, account):
    """Deleting anyone who had clocked in, booked leave or had a payslip used to
    fail on a foreign key violation."""
    emp = make_employee(tenant, password="EmpPass123")

    tenant.post("/api/payslips", json={
        "employee_id": emp["id"], "period_start": "2026-01-01",
        "period_end": "2026-01-31", "pay_date": "2026-02-01",
    })
    tenant.post(f"/api/employees/{emp['id']}/goals", json={"title": "Ship the thing"})

    client.post("/api/employee/auth/login", json={"email": emp["email"], "password": "EmpPass123"})
    client.post("/api/employee/attendance/clock-in", json={})
    client.post("/api/employee/leave", json={
        "leave_type": "annual", "start_date": "2026-09-07", "end_date": "2026-09-08",
    })
    client.post("/api/employee/auth/logout")
    # Signing in as staff drops the owner session on this shared client.
    main.rate_limiter._hits.clear()
    client.post("/api/client/login", json={"email": account["email"],
                                          "password": account["password"]})

    res = tenant.delete(f"/api/employees/{emp['id']}")
    assert res.status_code == 200, res.text
    assert tenant.get(f"/api/employees/{emp['id']}").status_code == 404


def test_deleting_a_manager_clears_reports_to(tenant):
    manager = make_employee(tenant)
    report = make_employee(tenant, reports_to=manager["id"])
    assert tenant.delete(f"/api/employees/{manager['id']}").status_code == 200
    assert tenant.get(f"/api/employees/{report['id']}").json()["reports_to"] in (None, 0, "")


def test_deleting_a_department_detaches_employees(tenant):
    dept = tenant.post("/api/departments", json={"name": "Temporary"}).json()
    emp = make_employee(tenant, department_id=dept["id"])
    assert tenant.delete(f"/api/departments/{dept['id']}").status_code == 200
    assert tenant.get(f"/api/employees/{emp['id']}").status_code == 200


# --- attendance ------------------------------------------------------------

def test_login_clocks_in_and_clock_out_records_hours(client, tenant):
    """Logging into the employee portal clocks you in automatically, so a
    second explicit clock-in is a duplicate."""
    work_every_day(tenant)
    emp = make_employee(tenant, password="EmpPass123")
    login = client.post("/api/employee/auth/login", json={
        "email": emp["email"], "password": "EmpPass123",
    })
    assert login.status_code == 200
    assert login.json()["clock_in"]

    assert client.post("/api/employee/attendance/clock-in", json={}).status_code == 400

    out = client.post("/api/employee/attendance/clock-out")
    assert out.status_code == 200, out.text
    # Hours may round to ~0 in a fast test, but must never go negative - that
    # would feed a negative figure straight into payroll.
    assert out.json()["total_hours"] >= 0
    # Clocking out twice is refused.
    assert client.post("/api/employee/attendance/clock-out").status_code == 400


def test_clock_out_after_already_clocking_out_is_refused(client, tenant):
    work_every_day(tenant)
    emp = make_employee(tenant, password="EmpPass123")
    client.post("/api/employee/auth/login", json={"email": emp["email"], "password": "EmpPass123"})
    assert client.post("/api/employee/attendance/clock-out").status_code == 200
    assert client.post("/api/employee/attendance/clock-out").status_code == 400


# --- isolation -------------------------------------------------------------

def test_employees_are_tenant_scoped(client, tenant):
    emp = make_employee(tenant)
    client.post("/api/client/logout")
    client.post("/api/client/register", json={
        "email": "other-hr@example.com", "password": "Passw0rdTest",
    })
    client.post("/api/client/login", json={"email": "other-hr@example.com", "password": "Passw0rdTest"})
    assert client.get(f"/api/employees/{emp['id']}").status_code == 404
    assert client.delete(f"/api/employees/{emp['id']}").status_code == 404


def test_employee_endpoints_require_employee_session(client):
    client.post("/api/employee/auth/logout")
    client.post("/api/client/logout")
    assert client.get("/api/employee/leave").status_code == 401
    assert client.post("/api/employee/attendance/clock-in", json={}).status_code == 401
