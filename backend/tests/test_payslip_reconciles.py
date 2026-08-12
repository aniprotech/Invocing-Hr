"""A payslip has to add up.

An employee with a standing deduction on their record got a payslip whose four
deduction lines summed to less than the total printed underneath them. On a
real one: tax 20,375 and three zeroes, total 20,575. The missing 200 was the
standing deduction, which was in the total and on no line.
"""
import pytest

import main
from conftest import make_employee


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


def payslip_for(tenant, emp, **overrides):
    body = {
        "employee_id": emp["id"], "period_start": "2026-08-01",
        "period_end": "2026-08-31", "pay_date": "2026-08-31",
        "basic_salary": 80000.0, "bonus": 1000.0, "allowances": 500.0,
    }
    body.update(overrides)
    res = tenant.post("/api/payslips", json=body)
    assert res.status_code == 200, res.text
    # The create response is a summary; the figures come from reading it back,
    # which is also where the derived standing deduction appears.
    created = res.json()
    ps_id = created.get("id") or created.get("payslip", {}).get("id")
    assert ps_id, created
    full = tenant.get(f"/api/payslips/{ps_id}")
    assert full.status_code == 200, full.text
    return full.json()


def test_the_deduction_lines_add_up_to_the_total(tenant):
    """The exact shape of the payslip in the report: a standing deduction of
    200 that appeared nowhere."""
    emp = make_employee(tenant, salary=80000.0, tax_rate=25.0, deductions=200.0)
    ps = payslip_for(tenant, emp)

    lines = (ps["tax_amount"] + ps["insurance"] + ps["retirement"]
             + ps["other_deductions"] + ps["standing_deduction"])
    assert round(lines, 2) == round(ps["total_deductions"], 2)
    assert ps["standing_deduction"] == 200.0


def test_the_standing_deduction_is_reported(tenant):
    emp = make_employee(tenant, salary=80000.0, tax_rate=25.0, deductions=200.0)
    ps = payslip_for(tenant, emp)

    assert ps["gross_pay"] == 81500.0
    assert ps["tax_amount"] == 20375.0
    assert ps["total_deductions"] == 20575.0
    assert ps["net_pay"] == 60925.0


def test_nothing_is_invented_when_there_is_no_standing_deduction(tenant):
    emp = make_employee(tenant, salary=80000.0, tax_rate=25.0, deductions=0.0)
    ps = payslip_for(tenant, emp)
    assert ps["standing_deduction"] == 0.0
    assert round(ps["tax_amount"] + ps["insurance"] + ps["retirement"]
                 + ps["other_deductions"], 2) == round(ps["total_deductions"], 2)


def test_it_reconciles_alongside_the_other_deductions(tenant):
    emp = make_employee(tenant, salary=80000.0, tax_rate=10.0, deductions=150.0)
    ps = payslip_for(tenant, emp, insurance=90.0, retirement=60.0,
                     other_deductions=30.0)

    lines = (ps["tax_amount"] + ps["insurance"] + ps["retirement"]
             + ps["other_deductions"] + ps["standing_deduction"])
    assert round(lines, 2) == round(ps["total_deductions"], 2)
    assert ps["standing_deduction"] == 150.0
    assert round(ps["gross_pay"] - ps["total_deductions"], 2) == ps["net_pay"]


def test_reading_a_payslip_back_also_reconciles(tenant):
    """Derived on read, so payslips issued before this fix reconcile too."""
    emp = make_employee(tenant, salary=80000.0, tax_rate=25.0, deductions=200.0)
    ps = payslip_for(tenant, emp)
    lines = (ps["tax_amount"] + ps["insurance"] + ps["retirement"]
             + ps["other_deductions"] + ps["standing_deduction"])
    assert round(lines, 2) == round(ps["total_deductions"], 2)
