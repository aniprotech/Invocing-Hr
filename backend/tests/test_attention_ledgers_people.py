"""What needs you today, for the parts of the app that arrived later: the
sales and purchase ledgers, pay, what is owed to HMRC and the pension, pay
days HMRC has not heard about, pension letters and expense claims.

Each was only visible on its own screen. These check each one reaches the
panel when, and only when, there is something to do, and that a business
without the module never sees the other module's work.
"""
from datetime import date, timedelta

import pytest

import main
import models
from conftest import make_employee, make_invoice


@pytest.fixture(autouse=True)
def _reset():
    main.rate_limiter._hits.clear()
    yield


def d(n):
    return (date.today() + timedelta(days=n)).isoformat()


def items(tenant):
    r = tenant.get("/api/dashboard/attention")
    assert r.status_code == 200, r.text
    return {i["key"]: i for i in r.json()["items"]}


def cid():
    with main.SessionLocal() as db:
        return db.query(models.DBClient).order_by(models.DBClient.id.desc()).first().id


def set_modules(value):
    with main.SessionLocal() as db:
        db.get(models.DBClient, cid()).modules = value
        db.commit()


def owing(tenant, contact="Acme Ltd", amount=500.0):
    return make_invoice(tenant, status="Awaiting Payment", contact=contact, email="a@x.test", issue_date=d(-5), due_date=d(25),
                        tax_type="none", currency="GBP", line_items=[{"description": "Work", "qty": 1, "price": amount, "tax_rate": "No Tax"}])


def contact(tenant, name="Acme Ltd", **kw):
    r = tenant.post("/api/contacts", json={"name": name, "email": "a@x.test", **kw})
    assert r.status_code == 200, r.text
    return r.json()


# --- the sales ledger ---------------------------------------------------------------------------
def test_a_customer_over_their_credit_limit_is_shown(tenant):
    contact(tenant, credit_limit=300)
    assert "customers_over_limit" not in items(tenant)
    owing(tenant, amount=500)
    it = items(tenant)["customers_over_limit"]
    assert it["count"] == 1 and it["amount"] == 500.0 and it["view"] == "sales-ledger-view"


def test_a_customer_within_their_limit_is_not(tenant):
    contact(tenant, credit_limit=1000)
    owing(tenant, amount=500)
    assert "customers_over_limit" not in items(tenant)


def test_a_customer_on_hold_is_shown_only_while_they_owe(tenant):
    contact(tenant, on_hold=True)
    assert "customers_on_hold" not in items(tenant)
    owing(tenant)
    it = items(tenant)["customers_on_hold"]
    assert it["count"] == 1 and it["tone"] == "info"


# --- the purchase ledger --------------------------------------------------------------------------
def test_a_supplier_on_hold_with_a_bill_due_is_shown(tenant):
    s = tenant.post("/api/suppliers", json={"name": "Held Co", "on_hold": True}).json()
    tenant.post("/api/bills", json={"supplier_id": s["id"], "amount": 80, "issue_date": d(-20), "due_date": d(30)})
    assert "suppliers_on_hold" not in items(tenant)          # not due for a month
    tenant.post("/api/bills", json={"supplier_id": s["id"], "amount": 80, "issue_date": d(-20), "due_date": d(3)})
    tenant.post("/api/bills", json={"supplier_id": s["id"], "amount": 20, "issue_date": d(-20), "due_date": d(-3)})
    it = items(tenant)["suppliers_on_hold"]
    assert it["count"] == 1 and it["view"] == "purchase-ledger-view"


def test_a_supplier_not_on_hold_is_left_to_bills_due(tenant):
    s = tenant.post("/api/suppliers", json={"name": "Fine Co"}).json()
    tenant.post("/api/bills", json={"supplier_id": s["id"], "amount": 80, "issue_date": d(-20), "due_date": d(3)})
    got = items(tenant)
    assert "suppliers_on_hold" not in got and "bills_due" in got


def test_draft_bills_are_shown_until_posted(tenant):
    b = tenant.post("/api/bills", json={"vendor_name": "Draft Co", "amount": 10, "issue_date": d(-1), "draft": True}).json()
    assert items(tenant)["bills_draft"]["count"] == 1
    tenant.post("/api/bills/post-drafts")
    assert "bills_draft" not in items(tenant)
    assert b["status"] == "Draft"


# --- pay -------------------------------------------------------------------------------------------
def payslip(tenant, emp, pay_date):
    r = tenant.post("/api/payslips", json=dict(employee_id=emp["id"], period_start=pay_date[:8] + "01", period_end=pay_date, pay_date=pay_date))
    assert r.status_code == 200, r.text
    return r.json()


def test_a_payslip_past_pay_day_and_unpaid_is_shown_worst(tenant):
    emp = make_employee(tenant)
    p = payslip(tenant, emp, d(-2))
    payslip(tenant, emp, d(40))                               # not pay day yet
    it = items(tenant)["wages_unpaid"]
    assert it["count"] == 1 and it["tone"] == "bad" and it["view"] == "payroll-view"
    assert tenant.post(f"/api/payslips/{p['id']}/mark-paid").status_code == 200
    assert "wages_unpaid" not in items(tenant)


def test_hmrc_and_pension_money_overdue_is_shown(tenant):
    tenant.put("/api/payroll/settings", json={"regime": "uk"})
    emp = make_employee(tenant, salary=4000.0, tax_rate=0.0, pay_frequency="monthly", ni_number="AB123456C", tax_code="1257L",
                        ni_category="A", date_of_birth="1990-01-01")
    p = payslip(tenant, emp, "2026-04-30")                    # tax month 1, due 22 May 2026
    tenant.post(f"/api/payslips/{p['id']}/mark-paid")
    with main.SessionLocal() as db:
        c = db.get(models.DBClient, cid())
        left = main.payroll_liabilities(db, c, 2026)["months"][0]["paye"]["left"]
    if date.today() > date(2026, 5, 22):
        it = items(tenant)["payroll_overdue"]
        assert it["tone"] == "bad" and it["amount"] >= left > 0 and it["currency"] == "GBP"
        tenant.post("/api/payroll/remittances", json={"kind": "hmrc", "tax_year": 2026, "tax_month": 1, "amount": left, "paid_on": d(0)})
        assert "payroll_overdue" not in items(tenant)


def test_pay_days_not_sent_to_hmrc_show_only_once_this_app_can_send(tenant, monkeypatch):
    tenant.put("/api/payroll/settings", json={"regime": "uk"})
    emp = make_employee(tenant, salary=3000.0, tax_rate=0.0, pay_frequency="monthly", ni_number="AB123456C", tax_code="1257L",
                        ni_category="A", date_of_birth="1990-01-01")
    payslip(tenant, emp, d(-3))
    monkeypatch.delenv("HMRC_VENDOR_ID", raising=False)
    assert "fps_not_sent" not in items(tenant)
    monkeypatch.setenv("HMRC_VENDOR_ID", "1234")
    it = items(tenant)["fps_not_sent"]
    assert it["count"] == 1 and it["filter"] == "hmrc"


def test_pension_letters_due_are_shown(tenant):
    emp = make_employee(tenant)
    assert "pension_letters" not in items(tenant)
    with main.SessionLocal() as db:
        db.get(models.DBEmployee, emp["id"]).pension_letter_due = "enrolment"
        db.commit()
    it = items(tenant)["pension_letters"]
    assert it["count"] == 1 and it["filter"] == "pension"


def test_expense_claims_waiting_and_owed_are_shown_with_their_money(tenant):
    emp = make_employee(tenant)
    with main.SessionLocal() as db:
        c = cid()
        db.add(models.DBExpenseClaim(client_id=c, employee_id=emp["id"], amount_minor=1250, currency="GBP", spent_on=d(-3), status="pending"))
        db.add(models.DBExpenseClaim(client_id=c, employee_id=emp["id"], amount_minor=4000, currency="GBP", spent_on=d(-3), status="approved"))
        db.add(models.DBExpenseClaim(client_id=c, employee_id=emp["id"], amount_minor=999, currency="EUR", spent_on=d(-3), status="approved"))
        db.add(models.DBExpenseClaim(client_id=c, employee_id=emp["id"], amount_minor=500, currency="GBP", spent_on=d(-3), status="paid"))
        db.commit()
    got = items(tenant)
    assert got["expenses_pending"]["count"] == 1 and got["expenses_pending"]["amount"] == 12.5 and got["expenses_pending"]["filter"] == "pending"
    assert got["expenses_unpaid"]["count"] == 2 and got["expenses_unpaid"]["amount"] == 40.0 and got["expenses_unpaid"]["filter"] == "approved"


# --- each module sees its own work -----------------------------------------------------------------
def test_an_invoicing_only_business_never_sees_pay_and_an_hr_only_one_never_sees_ledgers(tenant):
    emp = make_employee(tenant)
    payslip(tenant, emp, d(-2))
    tenant.post("/api/bills", json={"vendor_name": "Draft Co", "amount": 10, "issue_date": d(-1), "draft": True})
    assert {"wages_unpaid", "bills_draft"} <= set(items(tenant))
    set_modules("invoicing")
    got = items(tenant)
    assert "wages_unpaid" not in got and "bills_draft" in got
    set_modules("hr")
    got = items(tenant)
    assert "wages_unpaid" in got and "bills_draft" not in got
