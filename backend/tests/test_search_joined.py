"""Global search finds bills, suppliers, credit notes and items, and shows a
business only what its plan includes.

The search covered invoices, quotes, customers, people and payslips. Bills,
suppliers, credit notes and saved items could only be found by opening
their own screens and scrolling.
"""
import uuid

import pytest

import main
import models
from conftest import make_employee, make_invoice


@pytest.fixture(autouse=True)
def _reset():
    main.rate_limiter._hits.clear()
    yield


def find(tenant, q):
    r = tenant.get("/api/search", params={"q": q})
    assert r.status_code == 200, r.text
    return r.json()["results"]


def kinds(tenant, q):
    return {r["type"] for r in find(tenant, q)}


def set_modules(value):
    with main.SessionLocal() as db:
        db.query(models.DBClient).order_by(models.DBClient.id.desc()).first().modules = value
        db.commit()


def test_a_bill_is_found_by_number_supplier_or_their_reference(tenant):
    b = tenant.post("/api/bills", json={"vendor_name": "Zephyr Paper", "amount": 10, "reference": "ZP-7781"}).json()
    for q in (b["number"], "zephyr", "zp-7781"):
        hit = next(r for r in find(tenant, q) if r["type"] == "bill")
        assert hit["id"] == b["id"] and hit["number"] == b["number"] and "Zephyr Paper" in hit["label"]


def test_a_supplier_is_found_by_name_account_or_email(tenant):
    s = tenant.post("/api/suppliers", json={"name": "Quokka Freight", "account_ref": "QF01", "email": "ap@quokka.example"}).json()
    for q in ("quokka", "qf01", "ap@quokka"):
        hit = next(r for r in find(tenant, q) if r["type"] == "supplier")
        assert hit["id"] == s["id"]


def test_a_credit_note_is_found_by_its_number_its_invoice_or_customer(tenant):
    inv = make_invoice(tenant, status="Awaiting Payment", contact="Yarrow Ltd", currency="GBP",
                       line_items=[{"description": "Work", "qty": 1, "price": 100.0, "tax_rate": "No Tax"}])
    cn = tenant.post("/api/credit-notes", json={"invoice_number": inv["number"]}).json()
    for q in (cn["number"], "yarrow"):
        hit = next(r for r in find(tenant, q) if r["type"] == "credit_note")
        assert hit["number"] == cn["number"] and inv["number"] in hit["sub"]


def test_an_item_is_found_by_code_or_name_with_its_stock(tenant):
    code = f"WMB-{uuid.uuid4().hex[:4]}"
    tenant.post("/api/items", json={"code": code, "name": "Wombat Blanket", "sale_price": 9, "track_inventory": True,
                                    "quantity_on_hand": 6, "average_cost": 2})
    for q in (code, "wombat"):
        hit = next(r for r in find(tenant, q) if r["type"] == "item")
        assert hit["number"] == code and hit["sub"] == "6 in stock"


def test_another_business_bills_and_suppliers_are_never_found(tenant, client):
    tenant.post("/api/bills", json={"vendor_name": "Secretive Supplies", "amount": 10})
    from fastapi.testclient import TestClient
    with TestClient(main.app) as other:
        other.post("/api/client/register", json={"email": "rival-search@example.com", "password": "Passw0rdTest", "company_name": "Rival"})
        other.post("/api/client/login", json={"email": "rival-search@example.com", "password": "Passw0rdTest"})
        assert other.get("/api/search", params={"q": "secretive"}).json()["results"] == []


def test_each_plan_searches_only_what_it_has(tenant):
    make_employee(tenant, first_name="Xanthe")
    tenant.post("/api/suppliers", json={"name": "Xanthe Supplies"})
    assert {"employee", "supplier"} <= kinds(tenant, "xanthe")
    set_modules("invoicing")
    assert kinds(tenant, "xanthe") == {"supplier"}
    set_modules("hr")
    assert kinds(tenant, "xanthe") == {"employee"}
