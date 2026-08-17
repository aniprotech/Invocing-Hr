"""The invoice page a customer opens.

An invoice used to leave as a PDF attached to an email. Miss the mail and the
customer had nothing, and there was nowhere to put a pay button. This is a page
carrying one invoice, reached by its tracking id.

It takes no session, so most of what matters here is what it refuses and what
it does not say.
"""
import uuid

import pytest

import main
import models
from conftest import make_invoice


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


def tracking_id_of(tenant, number):
    """Read it back through the tenant's own endpoint.

    Looking it up by number alone finds whichever business made INV-0001
    first - every tenant here numbers from one, so an unscoped query in a
    test is the same bug as an unscoped query in the app.
    """
    res = tenant.get(f"/api/invoices/{number}")
    assert res.status_code == 200, res.text
    return res.json()["tracking_id"]


def issued(tenant, **kw):
    kw.setdefault("status", "Awaiting Payment")
    return make_invoice(tenant, **kw)


# --- what the customer sees ---------------------------------------------------

def test_an_issued_invoice_can_be_opened_without_signing_in(client, tenant):
    inv = issued(tenant, contact="Anika Care Limited")
    res = client.get(f"/api/public/invoices/{tracking_id_of(tenant, inv['number'])}")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["number"] == inv["number"]
    assert body["to"]["name"] == "Anika Care Limited"


def test_it_carries_everything_needed_to_pay(client, tenant):
    inv = issued(tenant, line_items=[
        {"description": "Garden shed netting", "qty": 2, "price": 100.0,
         "tax_rate": "No Tax"}])
    body = client.get(f"/api/public/invoices/{tracking_id_of(tenant, inv['number'])}").json()

    assert body["line_items"][0]["description"] == "Garden shed netting"
    assert body["line_items"][0]["amount"] == 200.0
    assert body["amount_due"] > 0
    assert body["currency"] and body["currency_symbol"]
    assert body["due_date"]
    assert "company" in body["from"]


def test_it_uses_the_business_branding(client, tenant):
    """The customer should recognise who it is from."""
    themes = tenant.get("/api/branding-themes").json()["themes"]
    tenant.put(f"/api/branding-themes/{themes[0]['id']}", json={
        "brand_color": "#00a3e0", "approved_invoice_title": "INVOICE",
        "payment_terms": "Payable within 14 days."})

    inv = issued(tenant)
    body = client.get(f"/api/public/invoices/{tracking_id_of(tenant, inv['number'])}").json()
    assert body["brand_color"] == "#00a3e0"
    assert body["title"] == "INVOICE"
    assert body["payment_terms"] == "Payable within 14 days."


def test_a_paid_invoice_says_so(client, tenant):
    inv = issued(tenant)
    tenant.post(f"/api/invoices/{inv['number']}/mark-paid")
    body = client.get(f"/api/public/invoices/{tracking_id_of(tenant, inv['number'])}").json()
    assert body["is_settled"] is True
    assert body["amount_due"] == 0


def test_opening_the_page_is_counted(client, tenant):
    """The same signal the tracking pixel gave, for people who read the page
    instead of the email."""
    inv = issued(tenant)
    tid = tracking_id_of(tenant, inv["number"])
    client.get(f"/api/public/invoices/{tid}")
    client.get(f"/api/public/invoices/{tid}")

    stats = tenant.get(f"/api/invoices/{inv['number']}/open-stats").json()
    assert stats["open_count"] >= 2


# --- what it refuses ----------------------------------------------------------

def test_a_guessed_address_gets_nothing(client, tenant):
    issued(tenant)
    assert client.get(f"/api/public/invoices/{uuid.uuid4()}").status_code == 404
    assert client.get("/api/public/invoices/INV-0001").status_code == 404
    assert client.get("/api/public/invoices/1").status_code == 404


def test_a_draft_is_not_readable(client, tenant):
    """It has not been issued to anybody yet."""
    inv = make_invoice(tenant, status="Draft")
    res = client.get(f"/api/public/invoices/{tracking_id_of(tenant, inv['number'])}")
    assert res.status_code == 404


def test_a_void_invoice_is_withdrawn(client, tenant):
    """The link may already have been forwarded; voiding has to end it."""
    inv = issued(tenant)
    tid = tracking_id_of(tenant, inv["number"])
    assert client.get(f"/api/public/invoices/{tid}").status_code == 200

    tenant.put(f"/api/invoices/{inv['number']}", json={
        "contact": "Customer Ltd", "email": "c@example.com",
        "issue_date": inv["date"], "due_date": inv["due_date"],
        "status": "Void", "tax_type": "none",
        "line_items": [{"description": "w", "qty": 1, "price": 10.0,
                        "tax_rate": "No Tax"}]})
    assert client.get(f"/api/public/invoices/{tid}").status_code == 404


# --- what it must never say ---------------------------------------------------

def test_it_leaks_nothing_internal(client, tenant):
    """A public page grows leaks the moment it reuses an internal serialiser,
    so this pins the shape rather than trusting it."""
    inv = issued(tenant)
    body = client.get(f"/api/public/invoices/{tracking_id_of(tenant, inv['number'])}").json()

    for forbidden in ("client_id", "id", "tracking_id", "open_count",
                      "last_opened", "email", "phone_number", "sent"):
        assert forbidden not in body, f"{forbidden} is on the public page"


def test_it_does_not_expose_the_customer_contact_details(client, tenant):
    """Their name appears because it is their invoice. Their email and phone
    are the business's record of them, not something to publish on a URL that
    may be forwarded."""
    inv = issued(tenant, contact="Anika Care Limited", email="private@example.com")
    body = client.get(f"/api/public/invoices/{tracking_id_of(tenant, inv['number'])}").json()
    assert body["to"] == {"name": "Anika Care Limited"}
    assert "private@example.com" not in str(body)


def test_one_link_shows_only_that_invoice(client, tenant):
    a = issued(tenant, contact="First Customer")
    b = issued(tenant, contact="Second Customer")
    body = client.get(f"/api/public/invoices/{tracking_id_of(tenant, a['number'])}").json()
    assert body["to"]["name"] == "First Customer"
    assert b["number"] not in str(body)


def test_a_link_never_reaches_another_business(client, tenant):
    """Two tenants, and the id is the only thing the endpoint trusts."""
    mine = issued(tenant, contact="My Customer")
    # Read before switching: these fixtures share one HTTP client, so after the
    # other business signs in, asking for INV-0001 returns theirs.
    my_link = tracking_id_of(tenant, mine["number"])

    other = f"other-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/client/register", json={
        "email": other, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    main.rate_limiter._hits.clear()
    client.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})
    theirs = issued(client, contact="Their Customer")

    body = client.get(f"/api/public/invoices/{my_link}").json()
    # Both businesses number from INV-0001, so the number proves nothing here -
    # who it is from and who it is to are what tell the two apart.
    assert body["from"]["company"] != "Other Ltd"
    assert body["to"]["name"] == "My Customer"
    assert "Their Customer" not in str(body)

    # And their own link shows theirs, so the id is doing the work.
    their_link = tracking_id_of(client, theirs["number"])
    theirs_body = client.get(f"/api/public/invoices/{their_link}").json()
    assert theirs_body["from"]["company"] == "Other Ltd"
    assert theirs_body["to"]["name"] == "Their Customer"


def test_the_email_points_at_the_customer_page(client, tenant):
    """It used to say "view and pay online" and link to the business's own
    sign-in page - a customer has no account there and never will."""
    import inspect
    source = inspect.getsource(main.send_invoice_email)
    assert "invoice.html?id={inv.tracking_id}" in source
    assert "login.html" not in source, "the customer is being sent to a sign-in page"
