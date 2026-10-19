"""Payroll and staff money in the books.

Before this, payroll stopped at the payslip: the profit and loss, the cash
summary and the balance sheet never saw a penny of pay, what was taken from pay
for HMRC and the pension was owed to nobody, and an expense claim marked paid
left no trace in the money. These check that each of them now reaches the
books, once, and that taking a bank line's coding back undoes what it paid.

The hand-worked month used throughout: 3,000 gross, 1257L, category A, paid
on 2026-04-30 (tax month 1, so HMRC is due 2026-05-22).
"""
from datetime import date, timedelta

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
             date_of_birth="1990-01-01")
    f.update(kw)
    return make_employee(tenant, **f)


def payslip(tenant, emp, pay_date="2026-04-30"):
    r = tenant.post("/api/payslips", json=dict(employee_id=emp["id"], period_start=pay_date[:8] + "01", period_end=pay_date, pay_date=pay_date))
    assert r.status_code == 200, r.text
    return tenant.get(f"/api/payslips/{r.json()['id']}").json()


def account(tenant, name="Current"):
    return tenant.post("/api/accounts", json={"name": name, "kind": "bank"}).json()


def bank_out(tenant, acc, amount, words="PAYROLL", day="2026-04-30"):
    tenant.post("/api/bank/import", json={"text": f"Date,Description,Amount\n{day},{words},-{amount:.2f}\n", "filename": "s.csv", "account_id": acc["id"]})
    return next(l for l in tenant.get("/api/bank/lines", params={"status": "out"}).json()["lines"] if words in l["description"])


def claim(tenant, emp_id, amount=45.0, status="approved", spent_on="2026-05-10", currency="GBP"):
    cid = tenant.get("/api/client/me").json()["id"]
    with main.SessionLocal() as db:
        row = models.DBExpenseClaim(client_id=cid, employee_id=emp_id, category="travel", amount_minor=int(round(amount * 100)),
                                    currency=currency, spent_on=spent_on, description="train", status=status)
        db.add(row)
        db.commit()
        return row.id


def pl(tenant):
    return tenant.get("/api/reports/profit-loss").json()


def months(report, key):
    return dict(zip(report["months"], report[key]))


@pytest.fixture
def uk(tenant):
    go_uk(tenant)
    emp = person(tenant)
    ps = payslip(tenant, emp)
    return emp, ps


# --- tax months ---------------------------------------------------------------------------
@pytest.mark.parametrize("day,expect", [("2026-04-06", (2026, 1)), ("2026-04-30", (2026, 1)), ("2026-05-05", (2026, 1)), ("2026-05-06", (2026, 2)),
                                        ("2026-12-31", (2026, 9)), ("2027-03-05", (2026, 11)), ("2027-04-05", (2026, 12)), ("2026-04-05", (2025, 12)), ("", (0, 0))])
def test_every_day_falls_in_its_tax_month(day, expect):
    assert main.tax_month_of(day) == expect


@pytest.mark.parametrize("month,first,last,due", [(1, "2026-04-06", "2026-05-05", "2026-05-22"), (9, "2026-12-06", "2027-01-05", "2027-01-22"),
                                                  (12, "2027-03-06", "2027-04-05", "2027-04-22")])
def test_a_tax_months_payment_is_due_on_the_22nd_after_it_ends(month, first, last, due):
    f, l, d = main.tax_month_bounds(2026, month)
    assert (f.isoformat(), l.isoformat(), d.isoformat()) == (first, last, due)


# --- what is owed to HMRC and the pension --------------------------------------------------
def test_the_month_owes_hmrc_what_the_payslips_took(tenant, uk):
    _emp, ps = uk
    got = tenant.get("/api/payroll/liabilities", params={"tax_year": 2026}).json()
    m1 = got["months"][0]
    want = round(ps["tax_amount"] + ps["uk"]["employee_ni"] + ps["uk"]["employer_ni"] + ps["uk"]["student_loan"] + ps["uk"]["postgrad_loan"], 2)
    assert m1["paye"]["total"] == want and m1["paye"]["left"] == want and m1["payslips"] == 1 and m1["due"] == "2026-05-22"
    assert m1["paye"]["tax"] == ps["tax_amount"] and m1["paye"]["employer_ni"] == ps["uk"]["employer_ni"]
    assert all(m["paye"]["status"] == "nothing" for m in got["months"][1:])
    assert got["label"] == "2026-27" and got["totals"]["paye_left"] == want and "Employment Allowance" in got["note"]


def test_a_month_past_its_due_date_and_unpaid_is_overdue(tenant, uk):
    got = tenant.get("/api/payroll/liabilities", params={"tax_year": 2026}).json()
    late = date.today() > date(2026, 5, 22)
    assert got["months"][0]["paye"]["status"] == ("overdue" if late else got["months"][0]["paye"]["status"])
    if late:
        assert got["totals"]["overdue"] >= 1


def test_paying_hmrc_brings_what_is_owed_down_and_can_be_taken_back(tenant, uk):
    owed = tenant.get("/api/payroll/liabilities", params={"tax_year": 2026}).json()["months"][0]["paye"]["total"]
    r = tenant.post("/api/payroll/remittances", json={"kind": "hmrc", "tax_year": 2026, "tax_month": 1, "amount": owed - 100, "paid_on": "2026-05-20", "reference": "123PA00012345"})
    assert r.status_code == 200, r.text
    m1 = tenant.get("/api/payroll/liabilities", params={"tax_year": 2026}).json()["months"][0]["paye"]
    assert m1["paid"] == round(owed - 100, 2) and m1["left"] == 100.0
    tenant.post("/api/payroll/remittances", json={"kind": "hmrc", "tax_year": 2026, "tax_month": 1, "amount": 100, "paid_on": "2026-05-21"})
    got = tenant.get("/api/payroll/liabilities", params={"tax_year": 2026}).json()
    assert got["months"][0]["paye"]["status"] == "paid" and len(got["remittances"]) == 2
    tenant.delete(f"/api/payroll/remittances/{r.json()['id']}")
    assert tenant.get("/api/payroll/liabilities", params={"tax_year": 2026}).json()["months"][0]["paye"]["left"] == round(owed - 100, 2)


@pytest.mark.parametrize("body,says", [
    ({"kind": "vat"}, "HMRC or to the pension"), ({"tax_month": 13}, "1 to 12"), ({"tax_year": 1990}, "tax year"), ({"amount": 0}, "more than zero"),
    ({"amount": -1}, "between 0"), ({"amount": 999999}, "more than is owed"), ({"paid_on": "soon"}, "YYYY-MM-DD"), ({"account_id": 99999}, "not one of yours"),
])
def test_a_payment_that_cannot_be_right_is_refused(tenant, uk, body, says):
    payload = {"kind": "hmrc", "tax_year": 2026, "tax_month": 1, "amount": 10, **body}
    r = tenant.post("/api/payroll/remittances", json=payload)
    assert r.status_code == 400 and says in r.json()["detail"], r.text


def test_the_pension_is_owed_both_shares(tenant):
    go_uk(tenant)
    tenant.put("/api/pension/scheme", json={"enabled": True, "provider": "NEST", "employer_pct": 3, "employee_pct": 5})
    emp = person(tenant)
    ps = payslip(tenant, emp)
    pen = ps["uk"]["pension"]
    m1 = tenant.get("/api/payroll/liabilities", params={"tax_year": 2026}).json()["months"][0]["pension"]
    assert m1["total"] == round(pen["employee"] + pen["employer"], 2) and m1["employee"] == pen["employee"]
    r = tenant.post("/api/payroll/remittances", json={"kind": "pension", "tax_year": 2026, "tax_month": 1, "amount": m1["total"], "paid_on": "2026-05-15"})
    assert r.status_code == 200
    assert tenant.get("/api/payroll/liabilities", params={"tax_year": 2026}).json()["months"][0]["pension"]["status"] == "paid"


def test_simple_payroll_owes_hmrc_nothing_here(tenant):
    emp = make_employee(tenant, salary=3000.0, tax_rate=20.0)
    tenant.post("/api/payslips", json=dict(employee_id=emp["id"], period_start="2026-04-01", period_end="2026-04-30", pay_date="2026-04-30"))
    assert tenant.get("/api/payroll/liabilities", params={"tax_year": 2026}).json()["totals"]["paye_left"] == 0.0


def test_a_tax_year_out_of_range_is_refused(tenant):
    assert tenant.get("/api/payroll/liabilities", params={"tax_year": 1800}).status_code == 400


# --- paying payslips -------------------------------------------------------------------------
def test_a_payslip_paid_says_when_and_from_where(tenant, uk):
    _emp, ps = uk
    acc = account(tenant)
    r = tenant.post(f"/api/payslips/{ps['id']}/mark-paid", json={"paid_on": "2026-04-30", "account_id": acc["id"]})
    assert r.status_code == 200 and r.json()["paid_on"] == "2026-04-30"
    with main.SessionLocal() as db:
        row = db.query(models.DBPayslip).filter(models.DBPayslip.id == ps["id"]).first()
        assert (row.status, row.paid_on, row.paid_account_id) == ("Paid", "2026-04-30", acc["id"])


def test_mark_paid_with_nothing_said_still_works(tenant, uk):
    _emp, ps = uk
    assert tenant.post(f"/api/payslips/{ps['id']}/mark-paid").status_code == 200


def test_a_paid_or_void_payslip_cannot_be_paid_again(tenant, uk):
    _emp, ps = uk
    tenant.post(f"/api/payslips/{ps['id']}/mark-paid")
    r = tenant.post(f"/api/payslips/{ps['id']}/mark-paid")
    assert r.status_code == 400 and "already paid" in r.json()["detail"]


def test_a_payroll_is_paid_in_one_go_by_one_bank_line(tenant):
    go_uk(tenant)
    a, b = payslip(tenant, person(tenant)), payslip(tenant, person(tenant, salary=2000.0))
    acc = account(tenant)
    total = round(a["net_pay"] + b["net_pay"], 2)
    line = bank_out(tenant, acc, total)
    r = tenant.post("/api/payroll/pay", json={"payslip_ids": [a["id"], b["id"]], "bank_line_id": line["id"]})
    assert r.status_code == 200 and r.json() == {"paid": 2, "net_pay": total}
    coded = next(l for l in tenant.get("/api/bank/lines", params={"status": "coded"}).json()["lines"] if l["id"] == line["id"])
    assert coded["status"] == "coded" and coded["category"] == "wages", coded
    with main.SessionLocal() as db:
        rows = db.query(models.DBPayslip).filter(models.DBPayslip.id.in_([a["id"], b["id"]])).all()
        assert {r.status for r in rows} == {"Paid"} and {r.bank_line_id for r in rows} == {line["id"]} and {r.paid_on for r in rows} == {"2026-04-30"}
        assert {r.paid_account_id for r in rows} == {acc["id"]}
    # the line's coding taken back: both owed again
    tenant.post(f"/api/bank/lines/{line['id']}/uncode")
    with main.SessionLocal() as db:
        rows = db.query(models.DBPayslip).filter(models.DBPayslip.id.in_([a["id"], b["id"]])).all()
        assert {r.status for r in rows} == {"Draft"} and {r.bank_line_id for r in rows} == {None} and {r.paid_on for r in rows} == {""}


def test_a_bank_line_must_be_the_amount_money_out_uncoded_and_yours(tenant, client, uk):
    _emp, ps = uk
    acc = account(tenant)
    wrong = bank_out(tenant, acc, ps["net_pay"] + 1, words="WRONG")
    r = tenant.post(f"/api/payslips/{ps['id']}/mark-paid", json={"bank_line_id": wrong["id"]})
    assert r.status_code == 400 and "come to" in r.json()["detail"]
    tenant.post("/api/bank/import", json={"text": "Date,Description,Amount\n2026-04-30,MONEY IN,500.00\n", "filename": "s.csv", "account_id": acc["id"]})
    money_in = next(l for l in tenant.get("/api/bank/lines").json()["lines"] if "MONEY IN" in l["description"])
    assert "money in" in tenant.post(f"/api/payslips/{ps['id']}/mark-paid", json={"bank_line_id": money_in["id"]}).json()["detail"]
    assert "not one of yours" in tenant.post(f"/api/payslips/{ps['id']}/mark-paid", json={"bank_line_id": 999999}).json()["detail"]
    right = bank_out(tenant, acc, ps["net_pay"], words="RIGHT")
    tenant.post("/api/bank/lines/code", json={"ids": [right["id"]], "category": "rent"})
    assert "already been coded" in tenant.post(f"/api/payslips/{ps['id']}/mark-paid", json={"bank_line_id": right["id"]}).json()["detail"]
    assert tenant.get(f"/api/payslips/{ps['id']}").json()["status"] != "Paid"


def test_a_mistaken_mark_paid_can_be_undone_but_not_one_from_the_bank(tenant, uk):
    _emp, ps = uk
    tenant.post(f"/api/payslips/{ps['id']}/mark-paid")
    r = tenant.post(f"/api/payslips/{ps['id']}/unmark-paid")
    assert r.status_code == 200 and r.json()["status"] == "Draft"
    assert tenant.post(f"/api/payslips/{ps['id']}/unmark-paid").status_code == 400
    acc = account(tenant)
    line = bank_out(tenant, acc, ps["net_pay"])
    tenant.post(f"/api/payslips/{ps['id']}/mark-paid", json={"bank_line_id": line["id"]})
    r = tenant.post(f"/api/payslips/{ps['id']}/unmark-paid")
    assert r.status_code == 400 and "Bank" in r.json()["detail"]


def test_a_payment_to_hmrc_from_a_bank_line_codes_it_and_uncoding_takes_it_back(tenant, uk):
    owed = tenant.get("/api/payroll/liabilities", params={"tax_year": 2026}).json()["months"][0]["paye"]["total"]
    line = bank_out(tenant, account(tenant), owed, words="HMRC CUMBERNAULD", day="2026-05-20")
    r = tenant.post("/api/payroll/remittances", json={"kind": "hmrc", "tax_year": 2026, "tax_month": 1, "amount": owed, "bank_line_id": line["id"]})
    assert r.status_code == 200 and r.json()["paid_on"] == "2026-05-20"
    assert tenant.delete(f"/api/payroll/remittances/{r.json()['id']}").status_code == 400
    tenant.post(f"/api/bank/lines/{line['id']}/uncode")
    assert tenant.get("/api/payroll/liabilities", params={"tax_year": 2026}).json()["months"][0]["paye"]["left"] == owed


# --- expense claims ---------------------------------------------------------------------------
def test_a_claim_paid_says_when_and_from_where_and_can_be_undone(tenant):
    emp = make_employee(tenant)
    cid = claim(tenant, emp["id"])
    acc = account(tenant)
    r = tenant.post(f"/api/expenses/{cid}/paid", json={"paid_on": "2026-05-12", "account_id": acc["id"]})
    assert r.status_code == 200 and r.json()["paid_on"] == "2026-05-12"
    r = tenant.post(f"/api/expenses/{cid}/unpaid")
    assert r.status_code == 200 and r.json()["status"] == "approved"
    assert tenant.post(f"/api/expenses/{cid}/unpaid").status_code == 409


def test_a_claim_repaid_by_a_bank_line_is_undone_by_uncoding_it(tenant):
    emp = make_employee(tenant)
    cid = claim(tenant, emp["id"], amount=45.0)
    line = bank_out(tenant, account(tenant), 45.0, words="REPAY ANN", day="2026-05-13")
    r = tenant.post(f"/api/expenses/{cid}/paid", json={"bank_line_id": line["id"]})
    assert r.status_code == 200 and r.json()["paid_on"] == "2026-05-13"
    assert tenant.post(f"/api/expenses/{cid}/unpaid").status_code == 400
    tenant.post(f"/api/bank/lines/{line['id']}/uncode")
    with main.SessionLocal() as db:
        row = db.query(models.DBExpenseClaim).filter(models.DBExpenseClaim.id == cid).first()
        assert (row.status, row.bank_line_id, row.paid_on) == ("approved", None, "")


def test_a_claim_not_yet_approved_cannot_be_paid(tenant):
    emp = make_employee(tenant)
    cid = claim(tenant, emp["id"], status="pending")
    assert tenant.post(f"/api/expenses/{cid}/paid").status_code == 409


# --- the reports --------------------------------------------------------------------------------
def test_staff_cost_reaches_the_profit_and_loss(tenant, uk):
    _emp, ps = uk
    r = pl(tenant)
    cost = round(ps["gross_pay"] + ps["uk"]["employer_ni"] + ((ps["uk"]["pension"] or {}).get("employer") or 0), 2)
    assert months(r, "expenses")["2026-04"] == cost and r["expense_parts"]["payroll"] == cost and r["total_expenses"] == cost


def test_an_approved_claim_is_an_expense_in_the_month_it_was_spent(tenant):
    emp = make_employee(tenant)
    claim(tenant, emp["id"], amount=45.0, spent_on="2026-05-10")
    claim(tenant, emp["id"], amount=99.0, status="pending")
    claim(tenant, emp["id"], amount=77.0, status="rejected")
    r = pl(tenant)
    assert months(r, "expenses") == {"2026-05": 45.0} and r["expense_parts"]["staff_expenses"] == 45.0


def test_a_claim_in_another_currency_is_reported_in_its_own(tenant):
    emp = make_employee(tenant)
    claim(tenant, emp["id"], amount=500.0, currency="INR")
    r = pl(tenant)
    assert r["total_expenses"] == 0.0 and next(x for x in r["other_currencies"] if x["currency"] == "INR")["total_expenses"] == 500.0


def test_money_out_is_net_pay_hmrc_and_claims_in_the_month_they_left(tenant, uk):
    _emp, ps = uk
    tenant.post(f"/api/payslips/{ps['id']}/mark-paid", json={"paid_on": "2026-05-01"})
    tenant.post("/api/payroll/remittances", json={"kind": "hmrc", "tax_year": 2026, "tax_month": 1, "amount": 100, "paid_on": "2026-05-20"})
    emp = make_employee(tenant)
    cid = claim(tenant, emp["id"], amount=45.0)
    tenant.post(f"/api/expenses/{cid}/paid", json={"paid_on": "2026-06-02"})
    out = months(tenant.get("/api/reports/cash-summary").json(), "money_out")
    assert out == {"2026-05": round(ps["net_pay"] + 100, 2), "2026-06": 45.0}


def test_the_balance_sheet_owes_wages_hmrc_the_pension_and_claims(tenant, uk):
    _emp, ps = uk
    emp = make_employee(tenant)
    claim(tenant, emp["id"], amount=45.0)
    owed_hmrc = tenant.get("/api/payroll/liabilities", params={"tax_year": 2026}).json()["months"][0]["paye"]["total"]
    liab = tenant.get("/api/reports/balance-sheet").json()["liabilities"]
    assert liab["wages_owed"] == ps["net_pay"] and liab["paye_owed"] == owed_hmrc and liab["expense_claims_owed"] == 45.0
    tenant.post(f"/api/payslips/{ps['id']}/mark-paid")
    tenant.post("/api/payroll/remittances", json={"kind": "hmrc", "tax_year": 2026, "tax_month": 1, "amount": owed_hmrc, "paid_on": "2026-05-20"})
    bs = tenant.get("/api/reports/balance-sheet").json()
    assert bs["liabilities"]["wages_owed"] == 0.0 and bs["liabilities"]["paye_owed"] == 0.0
    assert bs["total_liabilities"] == round(sum(bs["liabilities"].values()), 2)


def test_a_void_payslip_costs_nothing_and_owes_nothing(tenant, uk):
    _emp, ps = uk
    with main.SessionLocal() as db:
        db.query(models.DBPayslip).filter(models.DBPayslip.id == ps["id"]).update({"status": "Void"})
        db.commit()
    assert pl(tenant)["total_expenses"] == 0.0
    assert tenant.get("/api/reports/balance-sheet").json()["liabilities"]["wages_owed"] == 0.0
    assert tenant.get("/api/payroll/liabilities", params={"tax_year": 2026}).json()["totals"]["paye_left"] == 0.0


# --- one business, and who may ---------------------------------------------------------------
def test_another_businesss_bank_line_cannot_pay_these_payslips(tenant, client, uk):
    _emp, ps = uk
    from fastapi.testclient import TestClient
    with TestClient(main.app) as other:
        other.post("/api/client/register", json={"email": "rival-pm@example.com", "password": "Passw0rdTest", "company_name": "Rival"})
        other.post("/api/client/login", json={"email": "rival-pm@example.com", "password": "Passw0rdTest"})
        theirs = bank_out(other, account(other), ps["net_pay"], words="THEIRS")
        assert other.get("/api/payroll/liabilities").json()["totals"]["paye_left"] == 0.0
        assert other.post(f"/api/payslips/{ps['id']}/mark-paid").status_code == 404
    assert "not one of yours" in tenant.post(f"/api/payslips/{ps['id']}/mark-paid", json={"bank_line_id": theirs["id"]}).json()["detail"]


def test_payroll_money_belongs_to_the_hr_plan(tenant):
    for path in ("/api/payroll/liabilities", "/api/payroll/remittances", "/api/payroll/pay"):
        assert main.module_for_path(path) == "hr"
