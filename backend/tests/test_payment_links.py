"""Payment links: get paid without raising an invoice by hand. Behind each is a
real one-line invoice, so the usual ways of paying, the receipt and the books
all apply - but it is never chased, it stops working on its day, and it can be
withdrawn while nobody has paid it."""
from datetime import date, timedelta

import pytest

import main
import models


@pytest.fixture(autouse=True)
def _reset():
    main.rate_limiter._hits.clear()
    with main.SessionLocal() as db:
        db.query(models.DBJobRun).delete()
        db.commit()
    yield


def d(n):
    return (date.today() + timedelta(days=n)).isoformat()


def link(tenant, **kw):
    payload = {"amount": 250.0, "description": "Deposit for the kitchen", "customer_name": "Dana Smith", "email": "dana@example.com"}
    payload.update(kw)
    res = tenant.post("/api/payment-links", json=payload)
    assert res.status_code == 200, res.text
    return res.json()


def public(tenant, tracking_id):
    return tenant.get(f"/api/public/invoices/{tracking_id}")


def set_expiry(lk, day):
    """By tracking id: invoice numbers repeat across businesses in the test database."""
    with main.SessionLocal() as db:
        inv = db.query(models.DBInvoice).filter(models.DBInvoice.tracking_id == lk["tracking_id"]).first()
        inv.payment_link_expires = day
        db.commit()


def test_a_link_is_made_with_a_real_invoice_behind_it(tenant):
    lk = link(tenant)
    assert (lk["state"], lk["amount"], lk["due"], lk["description"], lk["customer"]) == ("open", 250.0, 250.0, "Deposit for the kitchen", "Dana Smith")
    assert lk["expires_on"] == d(30) and lk["number"].startswith("INV-") and lk["tracking_id"]
    inv = tenant.get(f"/api/invoices/{lk['number']}").json()
    assert inv["status"] == "Awaiting Payment" and inv["due"] == 250.0 and len(inv["line_items"]) == 1
    assert inv["line_items"][0]["description"] == "Deposit for the kitchen" and inv["line_items"][0]["price"] == 250.0
    assert [i["number"] for i in tenant.get("/api/invoice-list").json()["items"]] == [lk["number"]], "it is counted as sales"


def test_the_page_the_customer_opens_says_what_it_is(tenant):
    lk = link(tenant, customer_name="")
    page = public(tenant, lk["tracking_id"]).json()
    assert page["title"] == "PAYMENT REQUEST" and page["payment_link"] is True and page["valid_until"] == d(30)
    assert page["amount_due"] == 250.0 and page["line_items"][0]["description"] == "Deposit for the kitchen"
    assert page["to"]["name"] == "", "no customer named, so the placeholder is not shown"
    named = public(tenant, link(tenant)["tracking_id"]).json()
    assert named["to"]["name"] == "Dana Smith"
    ordinary = tenant.post("/api/invoices", json={"contact": "Acme", "issue_date": d(0), "due_date": d(10), "status": "Awaiting Payment",
                                                 "line_items": [{"description": "x", "qty": 1, "price": 5, "tax_rate": "No Tax"}]}).json()
    plain = public(tenant, ordinary["tracking_id"]).json()
    assert plain["payment_link"] is False and plain["title"] != "PAYMENT REQUEST" and plain["valid_until"] == ""


def test_a_link_is_never_chased_and_makes_no_contact(tenant):
    lk = link(tenant)
    with main.SessionLocal() as db:
        inv = db.query(models.DBInvoice).filter(models.DBInvoice.tracking_id == lk["tracking_id"]).first()
        assert main.invoice_is_chased(db, inv) == (False, "paused"), "the gate the reminders and late fees both use"
        assert main.invoice_is_chased(db, inv, for_fee=True) == (False, "paused")
    contacts = tenant.get("/api/contacts").json()
    assert all(c.get("name") != "Payment link" for c in (contacts if isinstance(contacts, list) else contacts.get("contacts", [])))


@pytest.mark.parametrize("change,why", [
    ({"amount": 0}, "more than nothing"),
    ({"amount": 20_000_000}, "too large"),
    ({"description": "   "}, "what the payment is for"),
    ({"description": "x" * 201}, "200 characters"),
    ({"email": "not-an-email"}, "does not look right"),
    ({"send": True, "email": ""}, "Add the customer's email"),
    ({"expires_in_days": 0}, "between 1 and 365"),
    ({"expires_in_days": 366}, "between 1 and 365"),
])
def test_bad_links_are_refused_with_a_reason(tenant, change, why):
    payload = {"amount": 10, "description": "Pens"}
    payload.update(change)
    r = tenant.post("/api/payment-links", json=payload)
    assert r.status_code == 400 and why in r.json()["detail"], r.text
    assert tenant.get("/api/payment-links").json()["count"] == 0


def test_it_warns_when_nobody_could_pay_online(tenant, monkeypatch):
    assert "No online payment method" in link(tenant)["warning"]
    monkeypatch.setattr(main, "invoice_payment_methods", lambda db, inv: [{"provider": "razorpay"}])
    assert link(tenant)["warning"] == ""


def test_paying_it_in_full_makes_it_paid(tenant):
    lk = link(tenant)
    r = tenant.post(f"/api/invoices/{lk['number']}/payments", json={"amount": 250, "paid_on": d(0)})
    assert r.status_code == 200, r.text
    got = tenant.get("/api/payment-links").json()
    assert got["links"][0]["state"] == "paid" and got["paid_total"] == 250.0 and got["open_total"] == 0.0
    detail = tenant.get(f"/api/payment-links/{lk['number']}").json()
    assert detail["state"] == "paid" and detail["payments"][0]["amount"] == 250.0
    assert tenant.post(f"/api/payment-links/{lk['number']}/cancel").status_code == 400
    assert public(tenant, lk["tracking_id"]).json()["is_settled"] is True


def test_a_link_can_be_cancelled_while_unpaid(tenant):
    lk = link(tenant)
    r = tenant.post(f"/api/payment-links/{lk['number']}/cancel")
    assert r.status_code == 200 and r.json()["state"] == "cancelled"
    assert tenant.get(f"/api/invoices/{lk['number']}").json()["status"] == "Void"
    gone = public(tenant, lk["tracking_id"])
    assert gone.status_code == 404 and "cancelled" in gone.json()["detail"]
    assert tenant.get(f"/api/public/invoices/{lk['tracking_id']}/pay/methods").status_code == 404
    assert tenant.post(f"/api/payment-links/{lk['number']}/cancel").status_code == 400
    assert tenant.post(f"/api/payment-links/{lk['number']}/send").status_code == 400


def test_a_part_paid_link_cannot_be_cancelled(tenant):
    lk = link(tenant)
    tenant.post(f"/api/invoices/{lk['number']}/payments", json={"amount": 100, "paid_on": d(0)})
    r = tenant.post(f"/api/payment-links/{lk['number']}/cancel")
    assert r.status_code == 400 and "refund" in r.json()["detail"]
    assert tenant.get(f"/api/payment-links/{lk['number']}").json()["state"] == "open"


def test_an_expired_link_stops_working_on_its_day_even_before_the_job_runs(tenant):
    lk = link(tenant, expires_in_days=1)
    assert public(tenant, lk["tracking_id"]).status_code == 200
    set_expiry(lk, d(-1))
    gone = public(tenant, lk["tracking_id"])
    assert gone.status_code == 404 and "expired" in gone.json()["detail"]
    assert tenant.get(f"/api/public/invoices/{lk['tracking_id']}/pay/methods").status_code == 404
    assert tenant.get("/api/payment-links").json()["links"][0]["state"] == "expired"
    assert tenant.get("/api/payment-links").json()["open_total"] == 0.0


def test_the_expiry_job_voids_an_unpaid_link_and_leaves_a_part_paid_one(tenant):
    unpaid, part, fine = link(tenant), link(tenant), link(tenant)
    tenant.post(f"/api/invoices/{part['number']}/payments", json={"amount": 50, "paid_on": d(0)})
    set_expiry(unpaid, d(-2))
    set_expiry(part, d(-2))
    out = main.run_due_jobs(only="payment_link_expiry")
    assert out[0]["status"] == "done" and "link(s) expired" in out[0]["detail"], out
    assert tenant.get(f"/api/invoices/{unpaid['number']}").json()["status"] == "Void"
    assert tenant.get(f"/api/invoices/{part['number']}").json()["status"] == "Partially Paid"
    states = {l["number"]: l["state"] for l in tenant.get("/api/payment-links").json()["links"]}
    assert states == {unpaid["number"]: "expired", part["number"]: "expired", fine["number"]: "open"}


def test_the_list_filters_and_searches(tenant):
    a = link(tenant, description="Deposit", customer_name="Dana", reference="JOB-1")
    b = link(tenant, description="Final payment", customer_name="Eli", email="")
    tenant.post(f"/api/invoices/{b['number']}/payments", json={"amount": 250, "paid_on": d(0)})
    got = lambda **p: tenant.get("/api/payment-links", params=p).json()
    assert got()["count"] == 2 and [l["number"] for l in got()["links"]] == [b["number"], a["number"]]
    assert got(status="open")["count"] == 1 and got(status="paid")["count"] == 1 and got(status="expired")["count"] == 0
    assert got(q="job-1")["links"][0]["number"] == a["number"] and got(q="final")["links"][0]["number"] == b["number"]
    assert tenant.get("/api/payment-links", params={"status": "lost"}).status_code == 400


def test_a_link_is_sent_in_words_that_say_what_it_is(tenant, monkeypatch):
    seen = []
    monkeypatch.setattr(main, "deliver_and_record", lambda delivery_id, to, subject, body, from_header, html, *a, **k: seen.append((to, subject, body, html)))
    monkeypatch.setattr(main, "email_delivery_ready", lambda db, cid=None: (True, ""))
    monkeypatch.setattr(main, "platform_from_address", lambda *a, **k: "billing@aniprotech.test")
    lk = link(tenant, send=True)
    assert lk["sent_now"] is True and lk["send_error"] == ""
    to, subject, body, html = seen[0]
    assert to == "dana@example.com" and "has asked you to pay" in subject and "£250.00" in subject
    assert f"/invoice.html?id={lk['tracking_id']}" in body and f"/invoice.html?id={lk['tracking_id']}" in html
    assert "Deposit for the kitchen" in body and "Dear" not in body and "invoice number" not in body.lower() and "invoice" not in subject.lower()
    assert f"works until {d(30)}" in body
    again = tenant.post(f"/api/payment-links/{lk['number']}/send", json={"email": "other@example.com"})
    assert again.status_code == 200 and seen[1][0] == "other@example.com"
    assert tenant.get(f"/api/payment-links/{lk['number']}").json()["email"] == "other@example.com"
    assert tenant.post(f"/api/payment-links/{lk['number']}/send", json={"email": "nope"}).status_code == 400


def test_a_link_that_cannot_be_sent_is_still_made_and_says_why(tenant, monkeypatch):
    monkeypatch.setattr(main, "email_delivery_ready", lambda db, cid=None: (False, "no mail is set up"))
    lk = link(tenant, send=True)
    assert lk["state"] == "open" and lk["sent_now"] is False and "no mail is set up" in lk["send_error"]
    assert tenant.get("/api/payment-links").json()["count"] == 1
    no_address = link(tenant, email="")
    assert tenant.post(f"/api/payment-links/{no_address['number']}/send").status_code == 400


def test_the_payment_links_need_the_invoicing_plan():
    assert main.module_for_path("/api/payment-links") == "invoicing"
    assert main.module_for_path("/api/payment-links/INV-0001/cancel") == "invoicing"


def test_nothing_crosses_a_business(client, account):
    tenant = account["client"]
    lk = link(tenant)
    other = f"other-{account['email']}"
    client.post("/api/client/register", json={"email": other, "password": "Passw0rdTest", "company_name": "Other Co"})
    client.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})
    assert client.get("/api/payment-links").json()["count"] == 0
    assert client.get(f"/api/payment-links/{lk['number']}").status_code == 404
    assert client.post(f"/api/payment-links/{lk['number']}/cancel").status_code == 404
    assert client.post(f"/api/payment-links/{lk['number']}/send").status_code == 404
    assert link(client)["number"] == lk["number"], "numbers are each business's own"
    client.cookies.clear()
    assert client.get("/api/payment-links").status_code == 401
    assert client.post("/api/payment-links", json={"amount": 1, "description": "x"}).status_code == 401
    assert client.get(f"/api/public/invoices/{lk['tracking_id']}").status_code == 200, "the page itself needs no sign-in"


def test_an_ordinary_invoice_is_not_a_payment_link(tenant):
    inv = tenant.post("/api/invoices", json={"contact": "Acme", "issue_date": d(0), "due_date": d(10), "status": "Awaiting Payment",
                                            "line_items": [{"description": "x", "qty": 1, "price": 5, "tax_rate": "No Tax"}]}).json()
    assert tenant.get("/api/payment-links").json()["count"] == 0
    assert tenant.get(f"/api/payment-links/{inv['number']}").status_code == 404
    assert tenant.post(f"/api/payment-links/{inv['number']}/cancel").status_code == 404
