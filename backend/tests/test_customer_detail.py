"""One customer's whole history in one place.

Contacts were a flat list: you could see that Bramley Works existed but not
what they had been quoted, billed, or paid.
"""
import uuid

import pytest

import main


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


@pytest.fixture
def customer(tenant):
    c = tenant.post("/api/contacts", json={
        "name": "Bramley Works", "email": "accounts@bramley.co",
        "phone_number": "+44 121 555 0142"}).json()
    return c


def bill(tenant, price=400.0, contact="Bramley Works", currency="", status="Awaiting Payment"):
    return tenant.post("/api/invoices", json={
        "contact": contact, "email": "accounts@bramley.co",
        "issue_date": "2026-01-01", "due_date": "2026-01-31",
        "status": status, "tax_type": "none", "currency": currency,
        "line_items": [{"description": "w", "qty": 1, "price": price,
                        "tax_rate": "No Tax"}]}).json()


def detail(tenant, contact_id):
    res = tenant.get(f"/api/contacts/{contact_id}/detail")
    assert res.status_code == 200, res.text
    return res.json()


def amount(totals, currency="GBP"):
    for t in totals or []:
        if t["currency"] == currency:
            return t["value"]
    return 0


def test_a_new_customer_has_nothing_yet(tenant, customer):
    d = detail(tenant, customer["id"])
    assert d["contact"]["name"] == "Bramley Works"
    assert d["invoices"] == [] and d["quotes"] == [] and d["payments"] == []
    assert d["summary"]["outstanding"] == []


def test_their_invoices_are_listed(tenant, customer):
    bill(tenant, 400.0)
    bill(tenant, 250.0)
    d = detail(tenant, customer["id"])
    assert d["summary"]["invoice_count"] == 2
    assert amount(d["summary"]["billed"]) == 650.0
    assert amount(d["summary"]["outstanding"]) == 650.0


def test_somebody_elses_invoice_is_not_theirs(tenant, customer):
    bill(tenant, 400.0)
    bill(tenant, 999.0, contact="Someone Else Ltd")
    d = detail(tenant, customer["id"])
    assert d["summary"]["invoice_count"] == 1
    assert amount(d["summary"]["billed"]) == 400.0


def test_the_name_match_ignores_case(tenant, customer):
    bill(tenant, 400.0, contact="bramley works")
    assert detail(tenant, customer["id"])["summary"]["invoice_count"] == 1


def test_paying_moves_the_balance(tenant, customer):
    inv = bill(tenant, 400.0)
    tenant.post(f"/api/invoices/{inv['number']}/mark-paid")

    d = detail(tenant, customer["id"])
    assert amount(d["summary"]["paid"]) == 400.0
    assert d["summary"]["outstanding"] == []
    assert len(d["payments"]) == 1
    assert d["payments"][0]["invoice_number"] == inv["number"]


def test_two_currencies_give_two_balances(tenant, customer):
    bill(tenant, 100.0, currency="GBP")
    bill(tenant, 5000.0, currency="INR")
    billed = detail(tenant, customer["id"])["summary"]["billed"]
    assert {t["currency"]: t["value"] for t in billed} == {"GBP": 100.0, "INR": 5000.0}


def test_their_quotes_are_listed(tenant, customer):
    tenant.post("/api/quotes", json={
        "contact": "Bramley Works", "email": "a@b.co",
        "issue_date": "2026-01-01", "expiry_date": "2026-12-31",
        "tax_type": "none", "title": "Brand refresh",
        "line_items": [{"description": "w", "qty": 1, "price": 1000.0,
                        "tax_rate": "No Tax"}]})
    d = detail(tenant, customer["id"])
    assert d["summary"]["quote_count"] == 1
    assert d["quotes"][0]["title"] == "Brand refresh"
    assert d["quotes"][0]["total"] == 1000.0


def test_overdue_invoices_are_flagged(tenant, customer):
    tenant.post("/api/invoices", json={
        "contact": "Bramley Works", "email": "a@b.co",
        "issue_date": "2020-01-01", "due_date": "2020-01-31",
        "status": "Awaiting Payment", "tax_type": "none",
        "line_items": [{"description": "w", "qty": 1, "price": 300.0,
                        "tax_rate": "No Tax"}]})
    d = detail(tenant, customer["id"])
    assert d["summary"]["overdue_count"] == 1
    assert d["invoices"][0]["is_overdue"] is True
    assert d["invoices"][0]["days_overdue"] > 0


def test_a_draft_is_not_counted_as_owed(tenant, customer):
    bill(tenant, 400.0, status="Draft")
    d = detail(tenant, customer["id"])
    assert d["summary"]["invoice_count"] == 1
    assert d["summary"]["outstanding"] == []


def test_another_tenant_cannot_read_it(client, tenant, customer):
    other = f"other-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/client/register", json={
        "email": other, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    client.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})
    assert client.get(f"/api/contacts/{customer['id']}/detail").status_code == 404


def test_it_needs_a_session(client):
    assert client.get("/api/contacts/1/detail").status_code == 401


def test_an_unknown_customer_is_a_404(tenant):
    assert tenant.get("/api/contacts/999999/detail").status_code == 404
