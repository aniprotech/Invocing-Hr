"""Somebody leaving, on the money side: their final pay, their pension, and
the P45 they take to their next job.

Offboarding already handled equipment, leave, expenses and their team. It did
not say whether they had been paid, did not end their pension membership, and
there was no P45. These check all three.
"""
import pytest

import main
import models
from conftest import make_employee


@pytest.fixture(autouse=True)
def _reset():
    main.rate_limiter._hits.clear()
    yield


def go_uk(tenant):
    assert tenant.put("/api/payroll/settings", json={"regime": "uk"}).status_code == 200


def person(tenant, **kw):
    f = dict(salary=3000.0, tax_rate=0.0, pay_frequency="monthly", ni_number="AB123456C", tax_code="1257L", ni_category="A",
             date_of_birth="1990-01-01", address="1 High Street, Leeds, LS1 4AB", gender="F")
    f.update(kw)
    return make_employee(tenant, **f)


def payslip(tenant, emp, pay_date):
    r = tenant.post("/api/payslips", json=dict(employee_id=emp["id"], period_start=pay_date[:8] + "01", period_end=pay_date, pay_date=pay_date))
    assert r.status_code == 200, r.text
    return tenant.get(f"/api/payslips/{r.json()['id']}").json()


def checklist(tenant, emp):
    return tenant.get(f"/api/employees/{emp['id']}/offboarding").json()


def leave(tenant, emp, day="2026-05-31", **kw):
    tenant.post(f"/api/employees/{emp['id']}/offboard")
    r = tenant.post(f"/api/employees/{emp['id']}/complete-offboard", json={"end_date": day, **kw})
    assert r.status_code == 200, r.text
    return r.json()


# --- final pay -----------------------------------------------------------------------------
def test_the_checklist_says_what_is_not_yet_paid_and_the_last_payslip(tenant):
    go_uk(tenant)
    emp = person(tenant)
    a = payslip(tenant, emp, "2026-04-30")
    b = payslip(tenant, emp, "2026-05-29")
    tenant.post(f"/api/payslips/{a['id']}/mark-paid")
    fp = checklist(tenant, emp)["final_pay"]
    assert fp["unpaid_payslips"] == 1 and fp["unpaid_net"] == b["net_pay"]
    assert fp["last_payslip"]["number"] == b["number"] and fp["last_payslip"]["pay_date"] == "2026-05-29"


def test_somebody_never_paid_has_no_last_payslip(tenant):
    emp = make_employee(tenant)
    fp = checklist(tenant, emp)["final_pay"]
    assert fp == {"last_payslip": None, "unpaid_payslips": 0, "unpaid_net": 0.0}


def test_final_pay_never_stops_them_leaving(tenant):
    go_uk(tenant)
    emp = person(tenant)
    payslip(tenant, emp, "2026-04-30")
    assert checklist(tenant, emp)["ready"] is True
    leave(tenant, emp)


# --- the pension ---------------------------------------------------------------------------------
def test_leaving_ends_their_pension_membership_and_names_the_provider(tenant):
    go_uk(tenant)
    tenant.put("/api/pension/scheme", json={"enabled": True, "provider": "NEST", "employer_pct": 3, "employee_pct": 5})
    emp = person(tenant)
    payslip(tenant, emp, "2026-04-30")
    assert tenant.get(f"/api/employees/{emp['id']}").json()["pension_status"] == "member"
    pen = checklist(tenant, emp)["pension"]
    assert pen == {"member": True, "status": "member", "provider": "NEST"}
    out = leave(tenant, emp)
    assert out["pension_ended"] is True and out["pension_provider"] == "NEST"
    assert tenant.get(f"/api/employees/{emp['id']}").json()["pension_status"] == ""


def test_somebody_not_in_the_pension_leaves_it_alone(tenant):
    emp = make_employee(tenant)
    out = leave(tenant, emp)
    assert out["pension_ended"] is False and checklist(tenant, emp)["pension"]["member"] is False


# --- the P45 ----------------------------------------------------------------------------------------
def test_a_p45_has_pay_and_tax_in_this_job_and_in_total(tenant):
    go_uk(tenant)
    emp = person(tenant, p45_tax_year=2026, p45_taxable_pay=1000.0, p45_tax=150.0)
    slips = [payslip(tenant, emp, "2026-04-30"), payslip(tenant, emp, "2026-05-29")]
    leave(tenant, emp, "2026-05-31")
    p = tenant.get(f"/api/employees/{emp['id']}/p45").json()
    pay = round(sum(s["uk"]["taxable_pay"] for s in slips), 2)
    tax = round(sum(s["tax_amount"] for s in slips), 2)
    assert p["pay_this_employment"] == pay and p["tax_this_employment"] == tax
    assert p["total_pay_to_date"] == round(pay + 1000, 2) and p["total_tax_to_date"] == round(tax + 150, 2)
    assert p["leaving_date"] == "2026-05-31" and p["tax_year"] == "2026-27" and p["payslips"] == 2
    assert p["last_period"] == {"type": "month", "number": 2}
    assert p["tax_code"] == "1257L" and p["week1_month1"] is False
    assert p["employee"]["ni_number"] == "AB123456C" and p["employee"]["postcode"] == "LS1 4AB" and p["employee"]["address_lines"] == ["1 High Street", "Leeds"]


def test_a_p45_from_a_previous_year_leaves_out_that_years_p45(tenant):
    go_uk(tenant)
    emp = person(tenant, p45_tax_year=2025, p45_taxable_pay=1000.0, p45_tax=150.0)
    payslip(tenant, emp, "2026-04-30")
    leave(tenant, emp, "2026-04-30")
    p = tenant.get(f"/api/employees/{emp['id']}/p45").json()
    assert p["total_pay_to_date"] == p["pay_this_employment"]


def test_a_scottish_week_one_code_is_shown_as_it_was_used(tenant):
    go_uk(tenant)
    emp = person(tenant, tax_code="S1257L M1")
    payslip(tenant, emp, "2026-04-30")
    leave(tenant, emp, "2026-04-30")
    p = tenant.get(f"/api/employees/{emp['id']}/p45").json()
    assert p["tax_code"].startswith("S1257L") and p["week1_month1"] is True


def test_a_student_loan_carries_on_to_the_next_job(tenant):
    go_uk(tenant)
    emp = person(tenant, student_loan_plan="2", postgrad_loan=True)
    payslip(tenant, emp, "2026-04-30")
    leave(tenant, emp, "2026-04-30")
    p = tenant.get(f"/api/employees/{emp['id']}/p45").json()
    assert p["student_loan"] is True and p["student_loan_plan"] == "2" and p["postgrad_loan"] is True


def test_what_is_missing_from_a_p45_is_said(tenant):
    go_uk(tenant)
    emp = person(tenant, ni_number="", address="")
    payslip(tenant, emp, "2026-04-30")
    leave(tenant, emp, "2026-04-30")
    missing = " ".join(tenant.get(f"/api/employees/{emp['id']}/p45").json()["missing"])
    assert "PAYE reference" in missing and "NI number" in missing and "address" in missing
    tenant.put("/api/hmrc/rti/settings", json={"office_no": "123", "paye_ref": "AB456", "ao_ref": "123PA00012345"})
    p = tenant.get(f"/api/employees/{emp['id']}/p45").json()
    assert p["employer"]["paye_reference"] == "123/AB456" and "PAYE reference" not in " ".join(p["missing"])


def test_a_p45_needs_a_last_day_and_uk_payroll(tenant):
    go_uk(tenant)
    emp = person(tenant)
    r = tenant.get(f"/api/employees/{emp['id']}/p45")
    assert r.status_code == 400 and "last day" in r.json()["detail"]
    assert tenant.get(f"/api/employees/{emp['id']}/p45", params={"leaving": "2026-05-31"}).status_code == 200
    assert tenant.get(f"/api/employees/{emp['id']}/p45", params={"leaving": "soon"}).status_code == 400
    tenant.put("/api/payroll/settings", json={"regime": "simple"})
    r = tenant.get(f"/api/employees/{emp['id']}/p45", params={"leaving": "2026-05-31"})
    assert r.status_code == 400 and "UK payroll" in r.json()["detail"]


def test_the_checklist_says_whether_a_p45_can_be_made(tenant):
    go_uk(tenant)
    emp = person(tenant)
    assert checklist(tenant, emp)["p45_ready"] is False
    payslip(tenant, emp, "2026-04-30")
    c = checklist(tenant, emp)
    assert c["p45_ready"] is True and c["uk_payroll"] is True


def test_another_business_cannot_see_a_p45(tenant, client):
    go_uk(tenant)
    emp = person(tenant)
    from fastapi.testclient import TestClient
    with TestClient(main.app) as other:
        other.post("/api/client/register", json={"email": "rival-p45@example.com", "password": "Passw0rdTest", "company_name": "Rival"})
        other.post("/api/client/login", json={"email": "rival-p45@example.com", "password": "Passw0rdTest"})
        assert other.get(f"/api/employees/{emp['id']}/p45", params={"leaving": "2026-05-31"}).status_code == 404
