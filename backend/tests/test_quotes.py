"""Quotes: priced proposals that can become invoices."""
import uuid



def make_quote(tenant, line_items=None, **overrides):
    payload = {
        "contact": "Prospect Ltd",
        "email": "buyer@example.com",
        "issue_date": "2026-01-01",
        "expiry_date": "2026-01-31",
        "tax_type": "exclusive",
        "line_items": line_items if line_items is not None else [
            {"name": "Design", "description": "Brand refresh", "qty": 2,
             "price": 500.0, "tax_rate": "20% (VAT on Income)"},
        ],
    }
    payload.update(overrides)
    res = tenant.post("/api/quotes", json=payload)
    assert res.status_code == 200, res.text
    return res.json()


# --- numbering ---------------------------------------------------------------

def test_quote_numbers_start_at_one_and_increment(tenant):
    first = make_quote(tenant)
    second = make_quote(tenant)
    assert first["number"] == "QU-0001"
    assert second["number"] == "QU-0002"


def test_quote_numbering_is_separate_from_invoices(tenant):
    """QU-0007 must not consume INV-0007."""
    tenant.post("/api/invoices", json={
        "contact": "C", "email": "c@example.com", "issue_date": "2026-01-01",
        "due_date": "2026-01-31",
        "line_items": [{"description": "x", "qty": 1, "price": 10.0}],
    })
    quote = make_quote(tenant)
    assert quote["number"] == "QU-0001"
    assert tenant.get("/api/next-invoice-number").json()["next_number"] == "INV-0002"
    assert tenant.get("/api/next-quote-number").json()["next_number"] == "QU-0002"


def test_duplicate_quote_number_is_refused(tenant):
    make_quote(tenant, quote_number="QU-9000")
    res = tenant.post("/api/quotes", json={
        "contact": "X", "email": "x@example.com", "issue_date": "2026-01-01",
        "expiry_date": "2026-01-31", "quote_number": "QU-9000",
        "line_items": [{"description": "x", "qty": 1, "price": 10.0}],
    })
    assert res.status_code == 409


# --- money -------------------------------------------------------------------

def test_totals_use_each_line_s_own_tax_rate(tenant):
    quote = make_quote(tenant, line_items=[
        {"description": "Taxed", "qty": 1, "price": 100.0, "tax_rate": "20% (VAT on Income)"},
        {"description": "Zero rated", "qty": 1, "price": 100.0, "tax_rate": "No Tax"},
    ])
    assert quote["subtotal"] == 200.0
    assert quote["tax_total"] == 20.0
    assert quote["total"] == 220.0


def test_discount_reduces_the_line(tenant):
    quote = make_quote(tenant, line_items=[
        {"description": "Discounted", "qty": 2, "price": 100.0, "disc": 10,
         "tax_rate": "No Tax"},
    ])
    assert quote["total"] == 180.0


# --- validation --------------------------------------------------------------

def test_expiry_cannot_precede_issue_date(tenant):
    res = tenant.post("/api/quotes", json={
        "contact": "X", "email": "x@example.com",
        "issue_date": "2026-02-01", "expiry_date": "2026-01-01",
        "line_items": [{"description": "x", "qty": 1, "price": 10.0}],
    })
    assert res.status_code == 400
    assert "expiry" in res.json()["detail"].lower()


def test_a_quote_needs_line_items(tenant):
    res = tenant.post("/api/quotes", json={
        "contact": "X", "email": "x@example.com", "issue_date": "2026-01-01",
        "expiry_date": "2026-01-31", "line_items": [],
    })
    assert res.status_code == 400


# --- lifecycle ---------------------------------------------------------------

def test_expiry_is_derived_not_stored(tenant):
    """A quote nobody answered before its expiry reads as Expired."""
    quote = make_quote(tenant, issue_date="2020-01-01", expiry_date="2020-01-31")
    assert quote["stored_status"] == "Draft"
    assert quote["status"] == "Expired"
    assert quote["is_expired"] is True


def test_accepting_a_quote_records_the_date(tenant):
    quote = make_quote(tenant)
    res = tenant.post(f"/api/quotes/{quote['number']}/status", json={"status": "Accepted"})
    assert res.status_code == 200
    assert res.json()["status"] == "Accepted"
    assert res.json()["decided_at"]


def test_an_accepted_quote_does_not_read_as_expired(tenant):
    quote = make_quote(tenant, issue_date="2020-01-01", expiry_date="2020-01-31")
    tenant.post(f"/api/quotes/{quote['number']}/status", json={"status": "Accepted"})
    assert tenant.get(f"/api/quotes/{quote['number']}").json()["status"] == "Accepted"


def test_unknown_status_is_refused(tenant):
    quote = make_quote(tenant)
    res = tenant.post(f"/api/quotes/{quote['number']}/status", json={"status": "Maybe"})
    assert res.status_code == 400


# --- conversion --------------------------------------------------------------

def test_converting_creates_an_invoice_with_the_same_lines(tenant):
    quote = make_quote(tenant, line_items=[
        {"name": "Design", "description": "Brand refresh", "qty": 2, "price": 500.0,
         "tax_rate": "20% (VAT on Income)"},
        {"name": "Copy", "description": "Website copy", "qty": 1, "price": 250.0,
         "tax_rate": "20% (VAT on Income)"},
    ])
    res = tenant.post(f"/api/quotes/{quote['number']}/convert", json={})
    assert res.status_code == 200, res.text
    inv_number = res.json()["invoice_number"]

    invoice = tenant.get(f"/api/invoices/{inv_number}").json()
    assert len(invoice["line_items"]) == 2
    assert invoice["total"] == quote["total"]
    assert invoice["to"] == quote["to"]
    # The quote is the record of what was agreed, so it survives the conversion.
    assert invoice["ref"] == quote["number"]


def test_conversion_links_both_ways_and_happens_once(tenant):
    quote = make_quote(tenant)
    inv_number = tenant.post(f"/api/quotes/{quote['number']}/convert", json={}).json()["invoice_number"]

    after = tenant.get(f"/api/quotes/{quote['number']}").json()
    assert after["status"] == "Invoiced"
    assert after["invoice_number"] == inv_number

    again = tenant.post(f"/api/quotes/{quote['number']}/convert", json={})
    assert again.status_code == 409


def test_a_declined_quote_cannot_be_invoiced(tenant):
    quote = make_quote(tenant)
    tenant.post(f"/api/quotes/{quote['number']}/status", json={"status": "Declined"})
    res = tenant.post(f"/api/quotes/{quote['number']}/convert", json={})
    assert res.status_code == 400


def test_an_invoiced_quote_is_locked(tenant):
    quote = make_quote(tenant)
    tenant.post(f"/api/quotes/{quote['number']}/convert", json={})
    assert tenant.delete(f"/api/quotes/{quote['number']}").status_code == 400
    res = tenant.put(f"/api/quotes/{quote['number']}", json={
        "contact": "Changed", "email": "x@example.com", "issue_date": "2026-01-01",
        "expiry_date": "2026-01-31",
        "line_items": [{"description": "x", "qty": 1, "price": 10.0}],
    })
    assert res.status_code == 400


def test_due_date_defaults_to_fourteen_days_after_issue(tenant):
    quote = make_quote(tenant)
    res = tenant.post(f"/api/quotes/{quote['number']}/convert",
                      json={"issue_date": "2026-03-01"})
    invoice = tenant.get(f"/api/invoices/{res.json()['invoice_number']}").json()
    assert invoice["date"] == "2026-03-01"
    assert invoice["due_date"] == "2026-03-15"


# --- editing and deleting ----------------------------------------------------

def test_updating_replaces_the_lines_and_retotals(tenant):
    quote = make_quote(tenant)
    res = tenant.put(f"/api/quotes/{quote['number']}", json={
        "contact": "Prospect Ltd", "email": "buyer@example.com",
        "issue_date": "2026-01-01", "expiry_date": "2026-02-28",
        "tax_type": "exclusive",
        "line_items": [{"description": "Only line", "qty": 1, "price": 50.0,
                        "tax_rate": "No Tax"}],
    })
    assert res.status_code == 200, res.text
    assert res.json()["total"] == 50.0
    assert len(res.json()["line_items"]) == 1
    assert res.json()["expiry_date"] == "2026-02-28"


def test_deleting_removes_the_quote_and_its_lines(tenant):
    quote = make_quote(tenant)
    assert tenant.delete(f"/api/quotes/{quote['number']}").status_code == 200
    assert tenant.get(f"/api/quotes/{quote['number']}").status_code == 404


# --- tenant isolation --------------------------------------------------------

def test_a_quote_is_invisible_to_another_tenant(client, tenant):
    quote = make_quote(tenant)

    other_email = f"other-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/client/register", json={
        "email": other_email, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    client.post("/api/client/login", json={
        "email": other_email, "password": "Passw0rdTest"})

    assert client.get(f"/api/quotes/{quote['number']}").status_code == 404
    assert client.get("/api/quotes").json() == []
    assert client.delete(f"/api/quotes/{quote['number']}").status_code == 404
    assert client.post(f"/api/quotes/{quote['number']}/convert", json={}).status_code == 404


def test_quotes_require_a_session(client):
    assert client.get("/api/quotes").status_code == 401


# --- sending -----------------------------------------------------------------

def test_sending_without_an_email_address_is_refused(tenant):
    quote = make_quote(tenant, email="")
    res = tenant.post(f"/api/quotes/{quote['number']}/send", json={})
    assert res.status_code == 400
    assert "email" in res.json()["detail"].lower()


def test_sending_rejects_a_malformed_address(tenant):
    quote = make_quote(tenant, email="not-an-address")
    res = tenant.post(f"/api/quotes/{quote['number']}/send", json={})
    assert res.status_code == 400


def test_creating_a_quote_saves_the_contact(tenant):
    make_quote(tenant, contact="Brand New Co", email="new@example.com")
    names = [c["name"] for c in tenant.get("/api/contacts").json()]
    assert "Brand New Co" in names
