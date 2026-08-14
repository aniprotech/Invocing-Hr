"""The employee profile is the one place HR looks a person up, so it has to
answer every question about them from a single call."""
import pytest

from conftest import make_employee, work_every_day


@pytest.fixture
def person(client, tenant):
    emp = make_employee(tenant, salary=3200.0, tax_rate=20.0, level="L4", password="EmpPass123")
    return emp


def test_profile_returns_every_section(tenant, person):
    d = tenant.get(f"/api/employees/{person['id']}").json()
    for key in ("leave_balance", "on_leave_today", "leave_requests", "attendance_summary",
                "goals", "documents", "direct_reports", "hired_from", "payslips",
                "onboarding_items"):
        assert key in d, f"missing {key}"


def test_profile_leave_balance_tracks_requests(client, tenant, person):
    client.post("/api/employee/auth/login", json={"email": person["email"], "password": "EmpPass123"})
    client.post("/api/employee/leave", json={
        "leave_type": "annual", "start_date": "2026-09-07", "end_date": "2026-09-11",
    })
    client.post("/api/employee/auth/logout")

    d = tenant.get(f"/api/employees/{person['id']}").json()
    assert d["leave_balance"]["annual_pending"] == 5.0
    assert d["leave_balance"]["annual_remaining"] == 20.0
    assert len(d["leave_requests"]) == 1
    assert d["leave_requests"][0]["status"] == "pending"


def test_profile_reflects_approval_without_a_separate_call(client, account):
    """Approving in the Leave tab must show up on the profile, since both read
    the same records."""
    tenant = account["client"]
    emp = make_employee(tenant, password="EmpPass123")
    client.post("/api/employee/auth/login", json={"email": emp["email"], "password": "EmpPass123"})
    client.post("/api/employee/leave", json={
        "leave_type": "annual", "start_date": "2026-10-05", "end_date": "2026-10-09",
    })
    client.post("/api/employee/auth/logout")
    client.post("/api/client/login", json={"email": account["email"], "password": account["password"]})

    leave_id = tenant.get("/api/leave/requests").json()[0]["id"]
    tenant.post(f"/api/leave/requests/{leave_id}/action", json={"action": "approve"})

    d = tenant.get(f"/api/employees/{emp['id']}").json()
    assert d["leave_balance"]["annual_taken"] == 5.0
    assert d["leave_balance"]["annual_pending"] == 0
    assert d["leave_requests"][0]["status"] == "approved"


def test_profile_shows_someone_currently_clocked_in(client, tenant, person):
    # Logging in clocks the employee in; they stay clocked in until logout.
    work_every_day(tenant)
    client.post("/api/employee/auth/login", json={"email": person["email"], "password": "EmpPass123"})
    a = tenant.get(f"/api/employees/{person['id']}").json()["attendance_summary"]
    assert a["days_present"] == 1
    assert a["clocked_in_today"] is True
    assert a["today_clock_in"]


def test_profile_shows_a_completed_day(client, tenant, person):
    work_every_day(tenant)
    client.post("/api/employee/auth/login", json={"email": person["email"], "password": "EmpPass123"})
    client.post("/api/employee/auth/logout")   # logout clocks them out
    a = tenant.get(f"/api/employees/{person['id']}").json()["attendance_summary"]
    assert a["days_present"] == 1
    assert a["clocked_in_today"] is False
    assert a["today_clock_in"] and a["today_clock_out"]


def test_profile_lists_direct_reports(tenant):
    boss = make_employee(tenant)
    report = make_employee(tenant, reports_to=boss["id"])
    d = tenant.get(f"/api/employees/{boss['id']}").json()
    assert [r["id"] for r in d["direct_reports"]] == [report["id"]]


def test_profile_shows_recruitment_origin(client, tenant):
    """A hire should stay connected to the application it came from."""
    form = tenant.post("/api/recruitment/forms", json={
        "title": "Application", "fields": "[]",
        "pipeline_stages": '["Applied","Hired"]',
    }).json()
    client.post(f"/api/recruitment/form/{form['form_token']}/submit", json={
        "answers": "{}", "candidate_name": "Ada Byron", "candidate_email": "ada@example.com",
    })
    sub = tenant.get(f"/api/recruitment/forms/{form['id']}/submissions").json()[0]
    hired = tenant.post(f"/api/recruitment/submissions/{sub['id']}/hire", json={}).json()

    d = tenant.get(f"/api/employees/{hired['employee_id']}").json()
    assert d["hired_from"] is not None
    assert d["hired_from"]["submission_id"] == sub["id"]


def test_profile_without_recruitment_origin(tenant, person):
    assert tenant.get(f"/api/employees/{person['id']}").json()["hired_from"] is None


def test_profile_payslips_appear_after_a_payroll_run(tenant, person):
    tenant.post("/api/payroll/run", json={
        "period_start": "2026-08-01", "period_end": "2026-08-31", "pay_date": "2026-09-01",
    })
    d = tenant.get(f"/api/employees/{person['id']}").json()
    assert len(d["payslips"]) == 1
    assert d["payslips"][0]["net_pay"] > 0


def test_profile_is_tenant_scoped(client, tenant, person):
    client.post("/api/client/logout")
    client.post("/api/client/register", json={"email": "nosy@example.com", "password": "Passw0rdTest"})
    client.post("/api/client/login", json={"email": "nosy@example.com", "password": "Passw0rdTest"})
    assert client.get(f"/api/employees/{person['id']}").status_code == 404
