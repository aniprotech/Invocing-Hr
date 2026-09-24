"""UK payroll, through the app: the switch, the employee's codes, and payslips
worked on the tax year so far.

The arithmetic itself is proven in test_uk_paye.py against hand-worked
figures. These tests are about the joins: that a business opts in, that the
right history is counted as "the year so far", that a P45 counts for tax and
not NI, that a starter with no code gets the one HMRC's checklist says, and
that nothing about the flat-rate payroll changes for anybody else.
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
    res = tenant.put("/api/payroll/settings", json={"regime": "uk"})
    assert res.status_code == 200, res.text
    return res.json()


def uk_employee(tenant, **kw):
    fields = dict(salary=3000.0, tax_rate=0.0, pay_frequency="monthly", ni_number="AB123456C",
                  tax_code="1257L", ni_category="A")
    fields.update(kw)
    return make_employee(tenant, **fields)


def payslip(tenant, emp, pay_date, start=None, end=None, **kw):
    res = tenant.post("/api/payslips", json=dict(
        employee_id=emp["id"], period_start=start or pay_date[:8] + "01", period_end=end or pay_date,
        pay_date=pay_date, **kw))
    assert res.status_code == 200, res.text
    return tenant.get(f"/api/payslips/{res.json()['id']}").json()


# --- the switch ---------------------------------------------------------------
def test_a_business_starts_on_the_payroll_it_always_had(tenant):
    s = tenant.get("/api/payroll/settings").json()
    assert s["regime"] == "simple"
    assert s["tax_year"] == "2026-27" and s["rates_ready"] is True
    assert "HMRC" in s["rates_source"]


def test_a_business_opts_in_to_uk_payroll(tenant):
    assert go_uk(tenant)["regime"] == "uk"
    assert tenant.get("/api/payroll/settings").json()["regime"] == "uk"


def test_only_the_two_payrolls_exist(tenant):
    assert tenant.put("/api/payroll/settings", json={"regime": "us"}).status_code == 400


def test_the_flat_rate_payroll_is_untouched(tenant):
    emp = make_employee(tenant, salary=3000.0, tax_rate=20.0)
    ps = payslip(tenant, emp, "2026-04-30")
    assert ps["regime"] == "simple" and ps["uk"] is None
    assert ps["tax_amount"] == 600.0 and ps["net_pay"] == 2400.0


# --- the employee's codes -----------------------------------------------------------
def test_the_employee_keeps_their_codes(tenant):
    emp = uk_employee(tenant, ni_number="ab 12 34 56 c", student_loan_plan="Plan 2", postgrad_loan=True)
    got = tenant.get(f"/api/employees/{emp['id']}").json()
    assert got["ni_number"] == "AB123456C", "spaces out, capitals in"
    assert (got["tax_code"], got["ni_category"], got["student_loan_plan"], got["postgrad_loan"]) == ("1257L", "A", "2", True)


@pytest.mark.parametrize("field,value,says", [
    ("ni_number", "QQ12345C", "two letters, six numbers"),
    ("ni_number", "DA123456A", "never used"),
    ("ni_number", "GB123456A", "never used"),
    ("ni_number", "QQ123456C", "never used"),   # HMRC's own example, never issued
    ("tax_code", "1257", "Tax code"),
    ("tax_code", "D3", "Tax code"),
    ("ni_category", "Q", "not one HMRC uses"),
    ("student_loan_plan", "3", "1, 2, 4 or 5"),
    ("starter_declaration", "D", "A, B or C"),
])
def test_a_code_that_would_break_a_payroll_run_is_refused_on_the_way_in(tenant, field, value, says):
    emp = uk_employee(tenant)
    res = tenant.put(f"/api/employees/{emp['id']}", json={field: value})
    assert res.status_code == 400 and says in res.json()["detail"], res.text


def test_a_bad_code_is_refused_when_the_employee_is_created_too(tenant):
    res = tenant.post("/api/employees", json={"first_name": "Ann", "last_name": "Lee",
                                              "email": "ann.lee@example.com", "tax_code": "ABC"})
    assert res.status_code == 400 and "Tax code" in res.json()["detail"]


# --- UK payslips ---------------------------------------------------------------------
def test_a_uk_payslip_is_worked_by_paye(tenant):
    go_uk(tenant)
    emp = uk_employee(tenant, student_loan_plan="2")
    ps = payslip(tenant, emp, "2026-04-30")
    uk = ps["uk"]
    assert ps["regime"] == "uk"
    assert (uk["tax_year"], uk["tax_period"], uk["tax_code"], uk["ni_category"]) == ("2026-27", 1, "1257L", "A")
    assert ps["tax_amount"] == 390.20
    assert (uk["employee_ni"], uk["employer_ni"], uk["student_loan"]) == (156.16, 387.45, 49.0)
    # 3,000 - 390.20 - 156.16 - 49
    assert ps["net_pay"] == 2404.64
    assert ps["standing_deduction"] == 0.0, "NI and the loan are their own lines, not a standing deduction"


def test_month_2_carries_the_year_so_far(tenant):
    go_uk(tenant)
    emp = uk_employee(tenant)
    payslip(tenant, emp, "2026-04-30")
    ps = payslip(tenant, emp, "2026-05-29")
    assert ps["uk"]["tax_period"] == 2
    assert ps["tax_amount"] == 390.40
    ytd = ps["uk"]["year_to_date"]
    assert (ytd["payslips"], ytd["gross_pay"], ytd["tax"]) == (2, 6000.0, 780.60)
    assert ytd["employee_ni"] == 312.32


def test_a_void_payslip_is_not_part_of_the_year(tenant):
    go_uk(tenant)
    emp = uk_employee(tenant)
    first = payslip(tenant, emp, "2026-04-30")
    with main.SessionLocal() as db:
        db.query(models.DBPayslip).filter(models.DBPayslip.id == first["id"]).update({"status": "Void"})
        db.commit()
    # Month 2 on its own: two months' tax-free pay against one month's pay.
    # 3,000 - 2,096.50 = 903 x 20% = 180.60
    assert payslip(tenant, emp, "2026-05-29")["tax_amount"] == 180.60


def test_week_1_month_1_ignores_the_history(tenant):
    go_uk(tenant)
    emp = uk_employee(tenant, tax_code="1257L M1")
    payslip(tenant, emp, "2026-04-30")
    assert payslip(tenant, emp, "2026-05-29")["tax_amount"] == 390.20


def test_a_scottish_employee_pays_scottish_tax(tenant):
    go_uk(tenant)
    emp = uk_employee(tenant, tax_code="S1257L")
    assert payslip(tenant, emp, "2026-04-30")["tax_amount"] == 392.26


def test_a_director_pays_no_ni_until_the_years_earnings_pass_the_threshold(tenant):
    go_uk(tenant)
    emp = uk_employee(tenant, salary=4000.0, is_director=True)
    ps = payslip(tenant, emp, "2026-04-30")
    assert ps["uk"]["employee_ni"] == 0.0


def test_an_under_21_costs_the_employer_no_ni(tenant):
    go_uk(tenant)
    emp = uk_employee(tenant, ni_category="M")
    ps = payslip(tenant, emp, "2026-04-30")
    assert ps["uk"]["employer_ni"] == 0.0 and ps["uk"]["employee_ni"] == 156.16


# --- starters -------------------------------------------------------------------------
def test_a_starter_with_no_code_and_no_declaration_gets_0t_on_this_period_only(tenant):
    go_uk(tenant)
    emp = uk_employee(tenant, tax_code="")
    ps = payslip(tenant, emp, "2026-04-30")
    # No tax-free pay: 3,000 x 20% = 600.00
    assert ps["uk"]["tax_code"] == "0T X"
    assert ps["tax_amount"] == 600.00


@pytest.mark.parametrize("declaration,code,tax", [
    ("A", "1257L", 390.20),
    ("B", "1257L X", 390.20),
    ("C", "BR", 600.00),
])
def test_the_starter_checklist_decides_the_code_until_hmrc_sends_one(tenant, declaration, code, tax):
    go_uk(tenant)
    emp = uk_employee(tenant, tax_code="", starter_declaration=declaration)
    ps = payslip(tenant, emp, "2026-04-30")
    assert ps["uk"]["tax_code"] == code
    assert ps["tax_amount"] == tax


def test_pay_from_a_previous_job_this_year_counts_for_tax_but_not_ni(tenant):
    """A starter in June whose P45 shows 6,000 pay and 780.60 tax: their first
    payslip here is month 3 on the year so far, exactly as if they had been
    here all along. NI has no memory of the other job."""
    go_uk(tenant)
    emp = uk_employee(tenant, p45_tax_year=2026, p45_taxable_pay=6000.0, p45_tax=780.60)
    ps = payslip(tenant, emp, "2026-06-30")
    assert ps["uk"]["tax_period"] == 3
    assert ps["tax_amount"] == 390.40
    assert ps["uk"]["employee_ni"] == 156.16


def test_a_directors_p45_does_not_count_towards_their_ni_here(tenant):
    """NI is per employment. A director who earned 20,000 elsewhere earlier
    in the year has earned 4,000 here, and 4,000 is under this year's
    primary threshold."""
    go_uk(tenant)
    emp = uk_employee(tenant, salary=4000.0, is_director=True,
                      p45_tax_year=2026, p45_taxable_pay=20000.0, p45_tax=2000.0)
    assert payslip(tenant, emp, "2026-06-30")["uk"]["employee_ni"] == 0.0


def test_a_p45_from_last_tax_year_is_ignored(tenant):
    go_uk(tenant)
    emp = uk_employee(tenant, p45_tax_year=2025, p45_taxable_pay=6000.0, p45_tax=780.60)
    # Month 3 with no pay counted before: 3,000 against three months' tax-free pay
    assert payslip(tenant, emp, "2026-06-30")["tax_amount"] == 0.0


# --- editing ---------------------------------------------------------------------------
def test_an_edited_uk_payslip_is_worked_again_on_the_year_so_far(tenant):
    go_uk(tenant)
    emp = uk_employee(tenant)
    ps = payslip(tenant, emp, "2026-04-30")
    res = tenant.put(f"/api/payslips/{ps['id']}", json={"bonus": 1000})
    assert res.status_code == 200, res.text
    again = tenant.get(f"/api/payslips/{ps['id']}").json()
    # 4,000 - 1,048.25 = 2,951 x 20% = 590.20
    assert again["gross_pay"] == 4000.0 and again["tax_amount"] == 590.20


def test_a_typed_tax_figure_does_not_overrule_paye(tenant):
    go_uk(tenant)
    emp = uk_employee(tenant)
    ps = payslip(tenant, emp, "2026-04-30", tax_amount=5.0)
    assert ps["tax_amount"] == 390.20


def test_switching_back_does_not_rewrite_a_payslip_already_made(tenant):
    go_uk(tenant)
    emp = uk_employee(tenant)
    ps = payslip(tenant, emp, "2026-04-30")
    tenant.put("/api/payroll/settings", json={"regime": "simple"})
    tenant.put(f"/api/payslips/{ps['id']}", json={"notes": "checked"})
    again = tenant.get(f"/api/payslips/{ps['id']}").json()
    assert again["regime"] == "uk" and again["tax_amount"] == 390.20
    # Still NI and all: 3,000 - 390.20 - 156.16
    assert again["uk"]["employee_ni"] == 156.16 and again["net_pay"] == 2453.64


def test_a_year_with_no_rates_is_refused_rather_than_guessed(tenant):
    go_uk(tenant)
    emp = uk_employee(tenant)
    res = tenant.post("/api/payslips", json={"employee_id": emp["id"], "period_start": "2027-04-06",
                                             "period_end": "2027-05-05", "pay_date": "2027-04-30"})
    assert res.status_code == 400 and "2027-28" in res.json()["detail"]


# --- the payroll run --------------------------------------------------------------------
def test_a_uk_payroll_run_says_what_is_owed_to_hmrc_and_what_it_costs(tenant):
    go_uk(tenant)
    uk_employee(tenant, student_loan_plan="2")
    uk_employee(tenant, ni_number="", tax_code="")
    res = tenant.post("/api/payroll/run", json={"period_start": "2026-04-01", "period_end": "2026-04-30",
                                                "pay_date": "2026-04-30"})
    assert res.status_code == 200, res.text
    run = res.json()
    assert run["regime"] == "uk" and len(run["created"]) == 2
    # one on 1257L (390.20 tax), one on 0T X (600.00); NI 156.16 each; one loan 49
    assert run["total_tax"] == 990.20
    assert run["total_employee_ni"] == 312.32 and run["total_employer_ni"] == 774.90
    assert run["owed_to_hmrc"] == 990.20 + 312.32 + 774.90 + 49
    assert run["employer_cost"] == 6000 + 774.90
    reasons = " ".join(w["reason"] for w in run["warnings"])
    assert "no NI number" in reasons and "0T" in reasons


def test_the_preview_shows_a_payslip_before_it_is_made(tenant):
    go_uk(tenant)
    emp = uk_employee(tenant)
    res = tenant.post("/api/payroll/preview", json={"employee_id": emp["id"], "pay_date": "2026-04-30"})
    assert res.status_code == 200, res.text
    assert res.json()["tax_amount"] == 390.20
    assert tenant.get("/api/payslips").status_code == 200
    with main.SessionLocal() as db:
        assert db.query(models.DBPayslip).filter(models.DBPayslip.employee_id == emp["id"]).count() == 0


# --- one business at a time ---------------------------------------------------------------
def test_another_business_keeps_its_own_payroll(tenant, client, account):
    go_uk(tenant)
    other = f"other-{account['email']}"
    client.post("/api/client/logout")
    client.post("/api/client/register", json={"email": other, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    client.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})
    assert client.get("/api/payroll/settings").json()["regime"] == "simple"


# --- the emailed payslip ----------------------------------------------------------------
@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(main.BackgroundTasks, "add_task", lambda self, func, *a, **kw: func(*a, **kw))
    monkeypatch.setattr(main, "send_email_background",
                        lambda to, subject, body, from_email, html_body=None, *a, **kw:
                        (sent.append({"to": to, "html": html_body or ""}), (True, "sent"))[1])
    return sent


def test_the_emailed_uk_payslip_lists_what_paye_took(tenant, outbox):
    go_uk(tenant)
    emp = uk_employee(tenant, student_loan_plan="2")
    ps = payslip(tenant, emp, "2026-04-30")
    res = tenant.post(f"/api/payslips/{ps['id']}/send", json={})
    assert res.status_code == 200, res.text
    html = outbox[-1]["html"]
    assert "Income Tax (code 1257L)" in html and "390.20" in html
    assert "National Insurance (category A)" in html and "156.16" in html
    assert "Student loan (plan 2)" in html
    assert "Tax year 2026-27, period 1" in html and "AB123456C" in html
    # The flat-rate rows that mean nothing on a UK payslip are gone.
    assert ">Retirement<" not in html


def test_the_emailed_flat_rate_payslip_is_as_it_was(tenant, outbox):
    emp = make_employee(tenant, salary=3000.0, tax_rate=20.0)
    ps = payslip(tenant, emp, "2026-04-30")
    tenant.post(f"/api/payslips/{ps['id']}/send", json={})
    html = outbox[-1]["html"]
    assert ">Tax<" in html and ">Retirement<" in html and "National Insurance" not in html
