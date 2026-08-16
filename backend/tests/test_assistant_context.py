"""What the assistant is actually able to see.

It kept answering "I do not have that information" about data sitting in the
database, because the context it was given was a summary - totals, and the top
few of anything. Ask about one invoice or one person and there was nothing
there to answer from.

These tests read the context and the lookup directly rather than calling the
model, so they check what the assistant is handed, which is the part that was
wrong. They also pin the thing that must never happen: one business seeing
another's records.
"""
import uuid

import pytest

import main
from conftest import make_employee, make_invoice


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


def client_row(email):
    with main.SessionLocal() as db:
        return db.query(main.models.DBClient).filter(
            main.models.DBClient.email == email).first()


def context_for(account):
    with main.SessionLocal() as db:
        row = db.query(main.models.DBClient).filter(
            main.models.DBClient.id == account["id"]).first()
        return main.build_business_context(db, row)


def lookup_for(account, question):
    with main.SessionLocal() as db:
        row = db.query(main.models.DBClient).filter(
            main.models.DBClient.id == account["id"]).first()
        return main.assistant_lookup(db, row, question)


@pytest.fixture
def me(tenant, account):
    """The signed-in account, with its database id."""
    with main.SessionLocal() as db:
        row = db.query(main.models.DBClient).filter(
            main.models.DBClient.email == account["email"]).first()
        return {"id": row.id, "email": account["email"]}


# --- the standing summary -----------------------------------------------------

def test_the_summary_covers_every_part_of_the_app(tenant, me):
    """Each of these headings was a question the assistant could not answer."""
    ctx = context_for(me)
    for heading in ("INVOICING", "QUOTES AND RECURRING BILLING", "PEOPLE",
                    "RECRUITMENT", "MONEY OUT", "CUSTOMERS", "ATTENDANCE", "ACCOUNT"):
        assert heading in ctx, f"the assistant cannot see {heading}"


def test_bills_are_visible(tenant, me):
    tenant.post("/api/bills", json={
        "vendor_name": "Supplier Ltd", "issue_date": "2026-01-05",
        "due_date": "2026-01-20", "amount": 250.0, "total": 250.0})
    assert "Bills: 1 total" in context_for(me)


def test_it_knows_who_owes_the_most(tenant, me):
    make_invoice(tenant, contact="Big Debtor Ltd", status="Awaiting Payment",
                 line_items=[{"description": "w", "qty": 1, "price": 5000.0,
                              "tax_rate": "No Tax"}])
    ctx = context_for(me)
    assert "Big Debtor Ltd owes" in ctx


def test_the_summary_never_adds_currencies_together(tenant, me):
    """The same rule the reports follow. One figure spanning currencies is a
    number that does not exist, and the assistant would quote it as fact."""
    for cur, price in (("GBP", 400.0), ("INR", 90000.0)):
        tenant.post("/api/invoices", json={
            "contact": "Mixed Ltd", "email": "m@example.com",
            "issue_date": "2026-01-01", "due_date": "2026-01-31",
            "status": "Awaiting Payment", "tax_type": "none", "currency": cur,
            "line_items": [{"description": "w", "qty": 1, "price": price,
                            "tax_rate": "No Tax"}]})
    ctx = context_for(me)
    line = next(l for l in ctx.split("\n") if l.startswith("- Outstanding:"))
    assert "GBP" in line and "INR" in line, line
    assert "90400" not in line.replace(",", ""), "currencies were added together"


# --- looking up what the question names ---------------------------------------

def test_it_finds_an_invoice_by_number(tenant, me):
    inv = make_invoice(tenant, contact="Acme Ltd")
    found = lookup_for(me, f"what is the status of {inv['number']}?")
    assert f"INVOICE {inv['number']}" in found
    assert "Acme Ltd" in found


def test_an_invoice_lookup_carries_its_lines(tenant, me):
    inv = make_invoice(tenant, contact="Acme Ltd", line_items=[
        {"description": "Roof repair", "qty": 2, "price": 150.0, "tax_rate": "No Tax"}])
    assert "Roof repair" in lookup_for(me, f"what is on {inv['number']}?")


def test_it_finds_a_customer_by_name(tenant, me):
    make_invoice(tenant, contact="Anika Care Limited", status="Awaiting Payment")
    found = lookup_for(me, "how much does Anika owe us?")
    assert "CUSTOMER Anika Care Limited" in found
    assert "outstanding" in found


def test_it_finds_an_employee_by_name(tenant, me):
    make_employee(tenant, first_name="Sarah", last_name="Daley")
    found = lookup_for(me, "when did Sarah Daley start?")
    assert "EMPLOYEE Sarah Daley" in found


def test_a_question_about_nothing_in_particular_matches_nothing(tenant, me):
    make_invoice(tenant, contact="Acme Ltd")
    assert lookup_for(me, "how are things going?") == ""


def test_common_words_do_not_drag_in_every_record(tenant, me):
    """'invoice' and 'customer' appear in most questions; matching on them
    would put the whole database in the prompt."""
    make_invoice(tenant, contact="Acme Ltd")
    assert lookup_for(me, "show me the invoice list for this customer") == ""


# --- isolation ----------------------------------------------------------------

def test_the_lookup_cannot_reach_another_business(client, tenant, me):
    """The one thing that must never happen."""
    mine = make_invoice(tenant, contact="My Private Customer")

    other = f"other-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/client/register", json={
        "email": other, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    main.rate_limiter._hits.clear()
    theirs = client_row(other)

    with main.SessionLocal() as db:
        found = main.assistant_lookup(
            db, theirs, f"tell me about {mine['number']} and My Private Customer")
    assert found == "", "another business's records leaked into the prompt"


def test_the_summary_is_per_tenant(client, tenant, me):
    make_invoice(tenant, contact="My Private Customer", status="Awaiting Payment")

    other = f"other-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/client/register", json={
        "email": other, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    main.rate_limiter._hits.clear()

    with main.SessionLocal() as db:
        ctx = main.build_business_context(db, client_row(other))
    assert "My Private Customer" not in ctx
