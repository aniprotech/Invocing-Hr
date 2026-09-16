"""Billed to and billed from, on every document.

A customer has a company, a billing address and a tax id, kept on the
contact. An invoice or quote raised to them carries a copy as it stood
that day - the contact can change later, the document must not - and
what is typed on a document teaches a contact that knew less. Recurring
invoices and converted quotes carry it too, the public page shows both
parties, and the business's own tax id sits beside its name.
"""
import pytest

import main
import models
from conftest import make_invoice


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


def me(tenant, number):
    return tenant.get(f"/api/invoices/{number}").json()


def test_a_contact_holds_company_address_and_tax_id(tenant):
    c = tenant.post("/api/contacts", json={"name": "Ann", "email": "a@x", "company": "Ann & Co", "address": "1 High St\nLeeds", "tax_id": "GB123"}).json()
    assert c["company"] == "Ann & Co" and c["address"] == "1 High St\nLeeds" and c["tax_id"] == "GB123"
    listed = next(x for x in tenant.get("/api/contacts").json() if x["id"] == c["id"])
    assert listed["company"] == "Ann & Co"
    found = tenant.get("/api/contacts/search", params={"q": "Ann"}).json()[0]
    assert found["address"] == "1 High St\nLeeds"
    up = tenant.put(f"/api/contacts/{c['id']}", json={"tax_id": "GB999"}).json()
    assert up["tax_id"] == "GB999" and up["company"] == "Ann & Co", "only what was sent changes"
    assert tenant.get(f"/api/contacts/{c['id']}/detail").json()["contact"]["company"] == "Ann & Co"
    # Posting the same name again fills blanks but never overwrites.
    again = tenant.post("/api/contacts", json={"name": "Ann", "company": "Other", "address": ""}).json()
    assert again["company"] == "Ann & Co"


def test_an_invoice_takes_the_billing_details_from_the_contact_and_keeps_its_own_copy(tenant):
    tenant.post("/api/contacts", json={"name": "Ann", "company": "Ann & Co", "address": "1 High St", "tax_id": "GB123"})
    inv = make_invoice(tenant, contact="Ann")
    got = me(tenant, inv["number"])
    assert got["bill_to"] == {"name": "Ann", "company": "Ann & Co", "address": "1 High St", "email": "customer@example.com", "phone": "", "tax_id": "GB123"}
    assert got["to_company"] == "Ann & Co"
    assert got["bill_from"]["name"] == "Acme Ltd" and "tax_id" in got["bill_from"]
    # The contact moves; the invoice stays where it was raised.
    cid = next(x for x in tenant.get("/api/contacts").json() if x["name"] == "Ann")["id"]
    tenant.put(f"/api/contacts/{cid}", json={"address": "2 New Road"})
    assert me(tenant, inv["number"])["bill_to"]["address"] == "1 High St"
    # Typed on the invoice: the invoice takes it, and the contact learns what it lacked.
    inv2 = make_invoice(tenant, contact="Bo", to_company="Bo Ltd", to_address="9 Lane", to_tax_id="IN27AAA")
    assert me(tenant, inv2["number"])["bill_to"]["company"] == "Bo Ltd"
    bo = next(x for x in tenant.get("/api/contacts").json() if x["name"] == "Bo")
    assert bo["company"] == "Bo Ltd" and bo["address"] == "9 Lane" and bo["tax_id"] == "IN27AAA"
    # Typed differently on a later invoice: that invoice differs; the contact keeps its own.
    inv3 = make_invoice(tenant, contact="Bo", to_address="Site office, Unit 4")
    assert me(tenant, inv3["number"])["bill_to"]["address"] == "Site office, Unit 4" and me(tenant, inv3["number"])["bill_to"]["company"] == "Bo Ltd"
    assert next(x for x in tenant.get("/api/contacts").json() if x["name"] == "Bo")["address"] == "9 Lane"


def test_editing_an_invoice_can_change_who_it_is_billed_to(tenant):
    inv = make_invoice(tenant, contact="Ann", to_company="Ann & Co")
    body = {"contact": "Ann", "email": "a@x", "issue_date": "2026-01-01", "due_date": "2026-01-31", "tax_type": "exclusive",
            "to_company": "Ann Holdings", "to_address": "Tower 1", "to_tax_id": "",
            "line_items": [{"description": "Consulting", "qty": 1, "price": 100.0, "tax_rate": "20% VAT"}]}
    assert tenant.put(f"/api/invoices/{inv['number']}", json=body).status_code == 200
    got = me(tenant, inv["number"])["bill_to"]
    assert got["company"] == "Ann Holdings" and got["address"] == "Tower 1" and got["tax_id"] == ""


def test_quotes_carry_it_and_hand_it_to_the_invoice_they_become(tenant):
    tenant.post("/api/contacts", json={"name": "Cy", "company": "Cy Works", "address": "Dock 3", "tax_id": "T1"})
    q = tenant.post("/api/quotes", json={"contact": "Cy", "issue_date": "2026-01-01", "expiry_date": "2026-01-31",
                                         "line_items": [{"description": "x", "qty": 1, "price": 50.0, "tax_rate": "0%"}]}).json()
    detail = tenant.get(f"/api/quotes/{q['number']}").json()
    assert detail["bill_to"]["company"] == "Cy Works" and detail["to_address"] == "Dock 3"
    tenant.post(f"/api/quotes/{q['number']}/status", json={"status": "Accepted"})
    conv = tenant.post(f"/api/quotes/{q['number']}/convert", json={})
    assert conv.status_code == 200, conv.text
    number = conv.json().get("invoice_number") or conv.json().get("number")
    assert me(tenant, number)["bill_to"] == {"name": "Cy", "company": "Cy Works", "address": "Dock 3", "email": "", "phone": "", "tax_id": "T1"}


def test_a_recurring_invoice_takes_the_contacts_details_when_it_is_raised(tenant):
    tenant.post("/api/contacts", json={"name": "Dee", "company": "Dee Ltd", "address": "Unit 2", "tax_id": "D9"})
    res = tenant.post("/api/recurring-invoices", json={"name": "Retainer", "contact": "Dee", "email": "d@x", "frequency": "monthly",
                                                       "next_run": "2026-01-01", "payment_terms_days": 14,
                                                       "line_items": [{"description": "Retainer", "qty": 1, "price": 100.0, "tax_rate": "0%"}]})
    assert res.status_code == 200, res.text
    rec_id = res.json()["id"]
    with main.SessionLocal() as db:
        t = db.get(models.DBRecurringInvoice, rec_id)
        inv = main.issue_recurring_invoice(db, t, main._parse_date("2026-01-01"))
        db.commit()
        number = inv.number
    got = me(tenant, number)["bill_to"]
    assert got["company"] == "Dee Ltd" and got["address"] == "Unit 2" and got["tax_id"] == "D9"


def test_the_public_page_shows_both_parties(tenant):
    inv = make_invoice(tenant, contact="Ann", to_company="Ann & Co", to_address="1 High St", to_tax_id="GB123", status="Awaiting Payment")
    tracking = me(tenant, inv["number"])["tracking_id"]
    body = tenant.get(f"/api/public/invoices/{tracking}").json()
    assert body["to"] == {"name": "Ann", "company": "Ann & Co", "address": "1 High St", "tax_id": "GB123"}
    assert body["from"]["company"] == "Acme Ltd" and "tax_id" in body["from"]


def test_nothing_crosses_a_business(tenant, account):
    tenant.post("/api/contacts", json={"name": "Ann", "company": "Ann & Co", "address": "1 High St", "tax_id": "GB123"})
    other = f"other-{account['email']}"
    tenant.post("/api/client/logout")
    main.rate_limiter._hits.clear()
    tenant.post("/api/client/register", json={"email": other, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    tenant.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})
    inv = make_invoice(tenant, contact="Ann")
    assert me(tenant, inv["number"])["bill_to"]["company"] == "", "another business's Ann is not this Ann"
