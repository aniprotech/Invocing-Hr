"""The assistant can see the ledgers, credit notes, staff expenses, payroll
money, the pension, HMRC filings and stock.

Each was built after the assistant, which answered questions about them by
saying it could not see them. These read what it is handed.
"""
import uuid
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


def me():
    with main.SessionLocal() as db:
        return db.query(models.DBClient).order_by(models.DBClient.id.desc()).first().id


def context():
    with main.SessionLocal() as db:
        return main.build_business_context(db, db.get(models.DBClient, me()))


def test_it_sees_suppliers_what_is_owed_and_who_is_on_hold(tenant):
    tenant.post("/api/suppliers", json={"name": "Held Haulage", "on_hold": True})
    tenant.post("/api/bills", json={"vendor_name": "Big Paper", "amount": 300, "issue_date": d(-40), "due_date": d(-10)})
    tenant.post("/api/bills", json={"vendor_name": "Draft Co", "amount": 5, "draft": True})
    c = context()
    assert "PURCHASE LEDGER" in c and "on hold: Held Haulage" in c
    assert "We owe Big Paper GBP 300.00, 300.00 overdue" in c and "Draft bills not yet posted: 1" in c


def test_it_sees_customers_over_their_limit_and_credit_notes(tenant):
    tenant.post("/api/contacts", json={"name": "Over Ltd", "email": "o@x.test", "credit_limit": 50})
    inv = make_invoice(tenant, status="Awaiting Payment", contact="Over Ltd", currency="GBP",
                       line_items=[{"description": "Work", "qty": 1, "price": 100.0, "tax_rate": "No Tax"}])
    assert "over their credit limit: Over Ltd" in context()
    tenant.post("/api/credit-notes", json={"invoice_number": inv["number"], "reason": "Damaged"})
    c = context()
    assert "Credit notes issued: 1" in c and f"against {inv['number']} to Over Ltd" in c and "Damaged" in c


def test_it_sees_expense_claims_waiting_and_owed(tenant):
    emp = make_employee(tenant)
    with main.SessionLocal() as db:
        db.add(models.DBExpenseClaim(client_id=me(), employee_id=emp["id"], amount_minor=2500, currency="GBP", spent_on=d(-2), status="pending"))
        db.add(models.DBExpenseClaim(client_id=me(), employee_id=emp["id"], amount_minor=1000, currency="GBP", spent_on=d(-2), status="approved"))
        db.commit()
    c = context()
    assert "Waiting for a decision: 1 (GBP 25.00)" in c and "Approved but not yet repaid: 1 (GBP 10.00)" in c


def test_it_sees_what_is_owed_to_hmrc_and_the_pension_and_the_filings(tenant):
    tenant.put("/api/payroll/settings", json={"regime": "uk"})
    tenant.put("/api/pension/scheme", json={"enabled": True, "provider": "NEST", "employer_pct": 3, "employee_pct": 5})
    emp = make_employee(tenant, salary=3000.0, tax_rate=0.0, pay_frequency="monthly", ni_number="AB123456C", tax_code="1257L",
                        ni_category="A", date_of_birth="1990-01-01")
    tenant.post("/api/payslips", json=dict(employee_id=emp["id"], period_start="2026-09-01", period_end="2026-09-30", pay_date="2026-09-30"))
    c = context()
    assert "Owed to HMRC (PAYE tax, NI, student loans) and not yet paid over: GBP" in c
    assert "WORKPLACE PENSION" in c and "Provider: NEST" in c
    assert "2026-09-30 not sent" in c


def test_it_sees_stock_to_reorder(tenant):
    code = f"LOW-{uuid.uuid4().hex[:4]}"
    tenant.post("/api/items", json={"code": code, "name": "Lowish", "sale_price": 3, "track_inventory": True,
                                    "quantity_on_hand": 2, "average_cost": 1.5, "reorder_level": 5})
    c = context()
    assert "STOCK" in c and "To reorder or out of stock: 1" in c and f"{code}: 2 on hand, reorder at 5" in c


def test_a_part_that_breaks_is_left_out_not_the_whole_context(tenant, monkeypatch):
    tenant.post("/api/suppliers", json={"name": "Anyone"})
    monkeypatch.setattr(main, "purchase_accounts", lambda *a, **k: 1 / 0)
    c = context()
    assert "PURCHASE LEDGER" not in c and "INVOICING" in c and "SALES LEDGER" in c


def test_each_plan_sees_only_its_own_parts(tenant):
    make_employee(tenant)
    with main.SessionLocal() as db:
        db.get(models.DBClient, me()).modules = "invoicing"
        db.commit()
    c = context()
    assert "PURCHASE LEDGER" in c and "STAFF EXPENSE CLAIMS" not in c
    with main.SessionLocal() as db:
        db.get(models.DBClient, me()).modules = "hr"
        db.commit()
    c = context()
    assert "PURCHASE LEDGER" not in c and "STAFF EXPENSE CLAIMS" in c
