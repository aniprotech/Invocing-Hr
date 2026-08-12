"""One search box that finds things.

The old one ran in the browser over whatever lists happened to be loaded, and
matched invoices on fields the API does not return, so a customer's name never
matched anything and employees were unfindable until you had opened their tab.
"""
import uuid

import pytest

import main
from conftest import make_employee


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


@pytest.fixture
def stocked(tenant):
    tenant.post("/api/invoices", json={
        "contact": "Bramley Works", "email": "accounts@bramley.co",
        "issue_date": "2026-01-01", "due_date": "2026-01-31", "tax_type": "none",
        "line_items": [{"description": "w", "qty": 1, "price": 100.0, "tax_rate": "No Tax"}],
    })
    tenant.post("/api/quotes", json={
        "contact": "Cavendish Ltd", "email": "buy@cavendish.co",
        "issue_date": "2026-01-01", "expiry_date": "2026-12-31", "tax_type": "none",
        "title": "Brand refresh",
        "line_items": [{"description": "w", "qty": 1, "price": 500.0, "tax_rate": "No Tax"}],
    })
    tenant.post("/api/contacts", json={
        "name": "Dorrington PLC", "email": "hello@dorrington.co",
        "phone_number": "+44 121 555 0142"})
    emp = make_employee(tenant, first_name="Ada", last_name="Lovelace",
                        job_title="Analytical Engineer")
    tenant.post("/api/recurring-invoices", json={
        "name": "Ellsworth retainer", "contact": "Ellsworth Ltd",
        "frequency": "monthly", "next_run": "2026-06-01",
        "line_items": [{"description": "w", "qty": 1, "price": 50.0, "tax_rate": "No Tax"}]})
    return {"employee": emp}


def find(tenant, q):
    res = tenant.get(f"/api/search?q={q}")
    assert res.status_code == 200, res.text
    return res.json()["results"]


def kinds(results):
    return {r["type"] for r in results}


# --- the bug this replaced ----------------------------------------------------

def test_a_customer_name_finds_their_invoice(stocked, tenant):
    """The old search read inv.client_name, which the API never returns, so
    searching a customer found nothing at all."""
    hits = [r for r in find(tenant, "Bramley") if r["type"] == "invoice"]
    assert hits, "a customer name should find their invoice"
    assert "Bramley Works" in hits[0]["label"]


def test_a_customer_email_finds_their_invoice(stocked, tenant):
    assert any(r["type"] == "invoice" for r in find(tenant, "bramley.co"))


def test_a_contact_phone_number_matches(stocked, tenant):
    """The old search read c.phone; the API returns phone_number."""
    assert any(r["type"] == "contact" for r in find(tenant, "555 0142"))


# --- coverage -----------------------------------------------------------------

def test_quotes_are_searchable(stocked, tenant):
    assert any(r["type"] == "quote" for r in find(tenant, "Cavendish"))


def test_a_quote_is_found_by_its_subject(stocked, tenant):
    assert any(r["type"] == "quote" for r in find(tenant, "Brand refresh"))


def test_recurring_invoices_are_searchable(stocked, tenant):
    assert any(r["type"] == "recurring" for r in find(tenant, "Ellsworth"))


def test_employees_are_searchable_without_opening_their_tab(stocked, tenant):
    """They used to be invisible until the Employees list had been loaded."""
    hits = [r for r in find(tenant, "Lovelace") if r["type"] == "employee"]
    assert hits
    assert hits[0]["id"] == stocked["employee"]["id"]


def test_an_employee_is_found_by_job_title(stocked, tenant):
    assert any(r["type"] == "employee" for r in find(tenant, "Analytical"))


def test_an_invoice_is_found_by_number(stocked, tenant):
    hits = [r for r in find(tenant, "INV-") if r["type"] == "invoice"]
    assert hits
    assert hits[0]["number"].startswith("INV-")


def test_results_carry_enough_to_open_the_record(stocked, tenant):
    for r in find(tenant, "Bramley"):
        assert r["number"] or r["id"], "a result must be openable"


# --- behaviour ----------------------------------------------------------------

def test_a_short_term_returns_nothing(tenant):
    assert find(tenant, "a") == []


def test_search_is_case_insensitive(stocked, tenant):
    assert kinds(find(tenant, "BRAMLEY")) == kinds(find(tenant, "bramley"))


def test_nothing_matching_is_an_empty_list(stocked, tenant):
    assert find(tenant, "zzzznothinghere") == []


def test_results_are_capped(stocked, tenant):
    for i in range(30):
        tenant.post("/api/invoices", json={
            "contact": f"Cappable {i}", "email": "c@example.com",
            "issue_date": "2026-01-01", "due_date": "2026-01-31", "tax_type": "none",
            "line_items": [{"description": "w", "qty": 1, "price": 10.0, "tax_rate": "No Tax"}],
        })
    assert len([r for r in find(tenant, "Cappable") if r["type"] == "invoice"]) <= 8


# --- isolation ----------------------------------------------------------------

def test_search_never_crosses_tenants(client, tenant, stocked):
    other = f"other-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/client/register", json={
        "email": other, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    client.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})

    assert client.get("/api/search?q=Bramley").json()["results"] == []
    assert client.get("/api/search?q=Lovelace").json()["results"] == []


def test_search_needs_a_session(client):
    assert client.get("/api/search?q=anything").status_code == 401
