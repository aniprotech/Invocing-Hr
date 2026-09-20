"""Payslip calculation, payroll runs and the guards around them."""

from conftest import make_employee


def test_salaried_employee_basic_pay(tenant):
    emp = make_employee(tenant, salary=3000.0, tax_rate=20.0)
    res = tenant.post("/api/payslips", json={
        "employee_id": emp["id"], "period_start": "2026-01-01",
        "period_end": "2026-01-31", "pay_date": "2026-02-01",
    })
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["gross_pay"] == 3000.00
    assert body["net_pay"] == 2400.00     # 3000 less 20% tax


def test_hourly_employee_is_paid_for_hours_worked(tenant):
    """The bug this guards: hourly staff have salary == 0, and basic pay was
    read straight off `salary`, so their payslip came out at zero."""
    emp = make_employee(tenant, salary=0.0, hourly_rate=25.0, tax_rate=0.0)
    res = tenant.post("/api/payslips", json={
        "employee_id": emp["id"], "period_start": "2026-01-01",
        "period_end": "2026-01-31", "pay_date": "2026-02-01",
        "hours_worked": 120.0,
    })
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["gross_pay"] == 3000.00   # 120h x 25, not 0
    assert body["net_pay"] == 3000.00


def test_overtime_and_deductions_are_included(tenant):
    emp = make_employee(tenant, salary=2000.0, tax_rate=10.0, deductions=50.0)
    res = tenant.post("/api/payslips", json={
        "employee_id": emp["id"], "period_start": "2026-02-01",
        "period_end": "2026-02-28", "pay_date": "2026-03-01",
        "overtime_hours": 10.0, "overtime_rate": 30.0,
        "bonus": 100.0, "allowances": 50.0, "insurance": 25.0,
    })
    body = res.json()
    # gross = 2000 + 300 OT + 100 bonus + 50 allowances
    assert body["gross_pay"] == 2450.00
    # deductions = 245 tax + 25 insurance + 50 standing
    assert body["net_pay"] == 2130.00


def test_payslip_number_survives_a_delete(tenant):
    """Numbering used to count rows, so deleting one made the next create
    collide with an existing number."""
    emp = make_employee(tenant)
    first = tenant.post("/api/payslips", json={
        "employee_id": emp["id"], "period_start": "2026-01-01",
        "period_end": "2026-01-31", "pay_date": "2026-02-01",
    }).json()
    second = tenant.post("/api/payslips", json={
        "employee_id": emp["id"], "period_start": "2026-02-01",
        "period_end": "2026-02-28", "pay_date": "2026-03-01",
    }).json()
    assert tenant.delete(f"/api/payslips/{second['id']}").status_code == 200

    third = tenant.post("/api/payslips", json={
        "employee_id": emp["id"], "period_start": "2026-03-01",
        "period_end": "2026-03-31", "pay_date": "2026-04-01",
    })
    assert third.status_code == 200, third.text
    assert third.json()["number"] != first["number"]


def test_overlapping_pay_period_is_blocked(tenant):
    emp = make_employee(tenant)
    tenant.post("/api/payslips", json={
        "employee_id": emp["id"], "period_start": "2026-01-01",
        "period_end": "2026-01-31", "pay_date": "2026-02-01",
    })
    res = tenant.post("/api/payslips", json={
        "employee_id": emp["id"], "period_start": "2026-01-15",
        "period_end": "2026-02-15", "pay_date": "2026-02-20",
    })
    assert res.status_code == 409
    # ...but can be overridden deliberately.
    res = tenant.post("/api/payslips?allow_overlap=true", json={
        "employee_id": emp["id"], "period_start": "2026-01-15",
        "period_end": "2026-02-15", "pay_date": "2026-02-20",
    })
    assert res.status_code == 200


def test_editing_a_payslip_recomputes_net(tenant):
    """Components were editable while gross/net were frozen, leaving a payslip
    whose total did not match its own lines."""
    emp = make_employee(tenant, salary=2000.0, tax_rate=0.0)
    ps = tenant.post("/api/payslips", json={
        "employee_id": emp["id"], "period_start": "2026-04-01",
        "period_end": "2026-04-30", "pay_date": "2026-05-01",
    }).json()
    assert ps["net_pay"] == 2000.00

    res = tenant.put(f"/api/payslips/{ps['id']}", json={"bonus": 500.0})
    assert res.status_code == 200, res.text
    assert res.json()["gross_pay"] == 2500.00
    assert res.json()["net_pay"] == 2500.00

    fetched = tenant.get(f"/api/payslips/{ps['id']}").json()
    assert fetched["net_pay"] == 2500.00


def test_paid_payslip_is_protected(tenant):
    emp = make_employee(tenant)
    ps = tenant.post("/api/payslips", json={
        "employee_id": emp["id"], "period_start": "2026-05-01",
        "period_end": "2026-05-31", "pay_date": "2026-06-01",
    }).json()
    tenant.post(f"/api/payslips/{ps['id']}/mark-paid")

    assert tenant.put(f"/api/payslips/{ps['id']}", json={"bonus": 1.0}).status_code == 409
    assert tenant.delete(f"/api/payslips/{ps['id']}").status_code == 409

    # Reopening it makes both possible again.
    assert tenant.post(f"/api/payslips/{ps['id']}/unmark-paid").status_code == 200
    assert tenant.put(f"/api/payslips/{ps['id']}", json={"bonus": 1.0}).status_code == 200


def test_payslip_shows_department_name(tenant):
    dept = tenant.post("/api/departments", json={"name": "Engineering"}).json()
    emp = make_employee(tenant, department_id=dept["id"])
    ps = tenant.post("/api/payslips", json={
        "employee_id": emp["id"], "period_start": "2026-06-01",
        "period_end": "2026-06-30", "pay_date": "2026-07-01",
    }).json()
    detail = tenant.get(f"/api/payslips/{ps['id']}").json()
    assert detail["employee"]["department_name"] == "Engineering"


def test_payroll_run_generates_for_all_active_employees(tenant):
    a = make_employee(tenant, salary=1000.0, tax_rate=0.0)
    b = make_employee(tenant, salary=2000.0, tax_rate=0.0)
    res = tenant.post("/api/payroll/run", json={
        "period_start": "2026-07-01", "period_end": "2026-07-31", "pay_date": "2026-08-01",
    })
    assert res.status_code == 200, res.text
    body = res.json()
    ids = {row["employee_id"] for row in body["created"]}
    assert {a["id"], b["id"]}.issubset(ids)
    assert body["total_gross"] >= 3000.00
    # Numbers issued in one run must be unique.
    numbers = [row["number"] for row in body["created"]]
    assert len(numbers) == len(set(numbers))


def test_payroll_run_skips_already_paid_periods(tenant):
    emp = make_employee(tenant, salary=1000.0)
    first = tenant.post("/api/payroll/run", json={
        "period_start": "2026-09-01", "period_end": "2026-09-30", "pay_date": "2026-10-01",
    })
    assert first.status_code == 200
    again = tenant.post("/api/payroll/run", json={
        "period_start": "2026-09-01", "period_end": "2026-09-30", "pay_date": "2026-10-01",
    }).json()
    assert again["created"] == []
    assert any(row["employee_id"] == emp["id"] for row in again["skipped"])


def test_payroll_run_rejects_a_backwards_period(tenant):
    make_employee(tenant)
    res = tenant.post("/api/payroll/run", json={
        "period_start": "2026-10-31", "period_end": "2026-10-01", "pay_date": "2026-11-01",
    })
    assert res.status_code == 400


def test_ytd_totals(tenant):
    emp = make_employee(tenant, salary=1000.0, tax_rate=10.0)
    for month in ("01", "02", "03"):
        tenant.post("/api/payslips", json={
            "employee_id": emp["id"],
            "period_start": f"2027-{month}-01", "period_end": f"2027-{month}-28",
            "pay_date": f"2027-{month}-28",
        })
    ytd = tenant.get(f"/api/employees/{emp['id']}/ytd?year=2027").json()
    assert ytd["payslip_count"] == 3
    assert ytd["gross_pay"] == 3000.00
    assert ytd["tax_amount"] == 300.00
    assert ytd["net_pay"] == 2700.00


def test_payslips_are_tenant_scoped(client, tenant):
    emp = make_employee(tenant)
    ps = tenant.post("/api/payslips", json={
        "employee_id": emp["id"], "period_start": "2026-11-01",
        "period_end": "2026-11-30", "pay_date": "2026-12-01",
    }).json()

    client.post("/api/client/logout")
    client.post("/api/client/register", json={
        "email": "other-payroll@example.com", "password": "Passw0rdTest",
    })
    client.post("/api/client/login", json={
        "email": "other-payroll@example.com", "password": "Passw0rdTest",
    })
    assert client.get(f"/api/payslips/{ps['id']}").status_code == 404
    assert client.delete(f"/api/payslips/{ps['id']}").status_code == 404
