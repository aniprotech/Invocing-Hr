"""Quotes answered online: the customer's own page for a quote.

A quote has a link nobody can guess. The page shows exactly what the
customer may see, counts opens, and lets them accept with their name or
decline with a reason - once, and not after it has expired. Acceptance is
written down (who, when, from where), raises the invoice when the
business wants that, tells the business, and reaches integrations. The
quote email carries the link. Nothing crosses a business.
"""
import os
from datetime import date, timedelta

os.environ["WEBHOOKS_ASYNC"] = "0"          # rows only; nothing goes out

import pytest

import main
import models


@pytest.fixture(autouse=True)
def _reset():
    main.rate_limiter._hits.clear()
    yield


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(main, "send_email_background",
                        lambda to, subject, body, from_email, html_body=None, *a, **kw: (sent.append({"to": to, "subject": subject, "body": body, "html": html_body}), (True, ""))[1])
    return sent


def d(n):
    return (date.today() + timedelta(days=n)).isoformat()


def make_quote(tenant, **overrides):
    payload = {"contact": "Prospect Ltd", "email": "buyer@example.com", "issue_date": d(-1), "expiry_date": d(14), "tax_type": "exclusive",
               "title": "Brand refresh", "summary": "Two days of design", "terms": "Half up front",
               "line_items": [{"name": "Design", "description": "Brand refresh", "qty": 2, "price": 500.0, "tax_rate": "20% (VAT on Income)"}]}
    payload.update(overrides)
    res = tenant.post("/api/quotes", json=payload)
    assert res.status_code == 200, res.text
    return res.json()


def public(client, q):
    return client.get(f"/api/public/quotes/{q['tracking_id']}")


def test_a_quote_has_a_page_of_its_own_that_shows_only_what_the_customer_may_see(client, tenant):
    q = make_quote(tenant)
    assert q["tracking_id"] and len(q["tracking_id"]) >= 32
    res = public(client, q)
    assert res.status_code == 200, res.text
    p = res.json()
    assert p["number"] == q["number"] and p["title"] == "QUOTE" and p["subject"] == "Brand refresh" and p["summary"] == "Two days of design" and p["terms"] == "Half up front"
    assert p["total"] == 1200.0 and p["subtotal"] == 1000.0 and p["tax"] == 200.0 and p["currency_symbol"] == "£"
    assert p["line_items"] == [{"name": "Design", "description": "Brand refresh", "qty": 2.0, "price": 500.0, "amount": 1000.0}]
    assert p["from"]["company"] == "Acme Ltd" and p["to"]["name"] == "Prospect Ltd"
    assert p["can_answer"] is True and p["status"] == "Draft" and p["invoice"] is None
    assert "client_id" not in p and "id" not in p and "email" not in p["to"]
    assert client.get("/api/public/quotes/not-a-real-id").status_code == 404
    # Opening it is counted where the business can see.
    public(client, q)
    got = tenant.get(f"/api/quotes/{q['number']}").json()
    assert got["open_count"] == 2 and got["last_opened"]


def test_the_customer_accepts_with_their_name_and_the_invoice_is_raised(client, tenant, outbox):
    q = make_quote(tenant)
    tenant.post(f"/api/quotes/{q['number']}/status", json={"status": "Sent"})
    res = client.post(f"/api/public/quotes/{q['tracking_id']}/accept", json={"name": "Dana Buyer", "note": "Start Monday please"}, headers={"x-forwarded-for": "203.0.113.9"})
    assert res.status_code == 200, res.text
    p = res.json()["quote"]
    assert p["status"] == "Invoiced" and p["can_answer"] is False and p["accepted_by"] == "Dana Buyer" and p["accepted_at"] == d(0)
    assert p["invoice"]["number"] == "INV-0001" and p["invoice"]["due"] == 1200.0 and p["invoice"]["status"] == "Awaiting Payment" and "/invoice.html?id=" in p["invoice"]["link"]
    got = tenant.get(f"/api/quotes/{q['number']}").json()
    assert got["status"] == "Invoiced" and got["invoice_number"] == "INV-0001" and got["accepted_by"] == "Dana Buyer" and got["decided_at"] == d(0)
    inv = tenant.get("/api/invoices/INV-0001").json()
    assert inv["to"] == "Prospect Ltd" and inv["total"] == 1200.0 and inv["due_date"] == d(14)
    assert [li["name"] for li in inv["line_items"]] == ["Design"]
    with main.SessionLocal() as db:
        row = db.query(models.DBQuote).filter(models.DBQuote.tracking_id == q["tracking_id"]).first()
        assert row.accepted_ip == "203.0.113.9"
        log = db.query(models.DBAuditLog).filter(models.DBAuditLog.entity_id == row.id, models.DBAuditLog.action == "quote_accepted_online").first()
        assert log is not None and "Dana Buyer" in log.details and "Start Monday please" in log.details
    # The business hears, with the note and the invoice.
    mine = [m for m in outbox if m["subject"].startswith(f"Quote {q['number']} accepted")]
    assert len(mine) == 1 and "Dana Buyer" in mine[0]["subject"] and "Start Monday please" in mine[0]["body"] and "Invoice INV-0001 has been raised" in mine[0]["body"]
    # Once is enough.
    assert client.post(f"/api/public/quotes/{q['tracking_id']}/accept", json={"name": "Dana Buyer"}).status_code == 409
    assert client.post(f"/api/public/quotes/{q['tracking_id']}/decline", json={}).status_code == 409


def test_a_business_can_keep_the_invoice_for_later(client, tenant, outbox):
    tenant.post("/api/settings", json={"quote_accept_raises_invoice": "0"})
    q = make_quote(tenant)
    res = client.post(f"/api/public/quotes/{q['tracking_id']}/accept", json={"name": "Dana"})
    assert res.status_code == 200, res.text
    assert res.json()["quote"]["status"] == "Accepted" and res.json()["quote"]["invoice"] is None
    got = tenant.get(f"/api/quotes/{q['number']}").json()
    assert got["status"] == "Accepted" and not got["invoice_number"]
    assert "No invoice raised" in [m for m in outbox if "accepted" in m["subject"]][0]["body"]
    # The business converts it when ready, as before.
    assert tenant.post(f"/api/quotes/{q['number']}/convert", json={}).status_code == 200


def test_a_name_is_the_signature(client, tenant):
    q = make_quote(tenant)
    res = client.post(f"/api/public/quotes/{q['tracking_id']}/accept", json={"name": "  "})
    assert res.status_code == 400 and "name" in res.json()["detail"]
    assert public(client, q).json()["can_answer"] is True


def test_the_customer_declines_with_a_reason(client, tenant, outbox):
    q = make_quote(tenant)
    res = client.post(f"/api/public/quotes/{q['tracking_id']}/decline", json={"name": "Dana", "reason": "Too dear"})
    assert res.status_code == 200, res.text
    assert res.json()["quote"]["status"] == "Declined" and res.json()["quote"]["can_answer"] is False
    got = tenant.get(f"/api/quotes/{q['number']}").json()
    assert got["status"] == "Declined" and got["declined_reason"] == "Too dear" and got["decided_at"] == d(0)
    mine = [m for m in outbox if m["subject"].startswith(f"Quote {q['number']} declined")]
    assert len(mine) == 1 and "Too dear" in mine[0]["body"]
    assert client.post(f"/api/public/quotes/{q['tracking_id']}/accept", json={"name": "Dana"}).status_code == 409
    assert client.post(f"/api/public/quotes/{q['tracking_id']}/decline", json={}).status_code == 409


def test_an_expired_quote_cannot_be_answered(client, tenant):
    q = make_quote(tenant, issue_date=d(-30), expiry_date=d(-1))
    p = public(client, q).json()
    assert p["status"] == "Expired" and p["can_answer"] is False
    res = client.post(f"/api/public/quotes/{q['tracking_id']}/accept", json={"name": "Dana"})
    assert res.status_code == 410 and d(-1) in res.json()["detail"]
    assert client.post(f"/api/public/quotes/{q['tracking_id']}/decline", json={"reason": "late"}).status_code == 410
    assert tenant.get(f"/api/quotes/{q['number']}").json()["status"] == "Expired"


def test_the_quote_email_carries_the_link(tenant, outbox, monkeypatch):
    monkeypatch.setenv("APP_BASE_URL", "https://bills.example.test")
    monkeypatch.setattr(main.BackgroundTasks, "add_task", lambda self, func, *a, **kw: func(*a, **kw))
    q = make_quote(tenant)
    res = tenant.post(f"/api/quotes/{q['number']}/send", json={})
    assert res.status_code == 200, res.text
    mail = [m for m in outbox if m["to"] == "buyer@example.com"][0]
    assert f"https://bills.example.test/quote.html?id={q['tracking_id']}" in mail["body"]
    assert "View and accept this quote" in mail["html"] and f"quote.html?id={q['tracking_id']}" in mail["html"]


def test_integrations_hear_of_the_answer(client, tenant):
    tenant.post("/api/webhooks", json={"url": "https://hooks.example.test/q", "events": ["quote.accepted", "quote.declined"]})
    q = make_quote(tenant)
    client.post(f"/api/public/quotes/{q['tracking_id']}/accept", json={"name": "Dana"})
    with main.SessionLocal() as db:
        rows = db.query(models.DBWebhookDelivery).filter(models.DBWebhookDelivery.event == "quote.accepted").all()
        assert rows and any(q["number"] in (r.payload or "") and "Dana" in (r.payload or "") for r in rows)


def test_nothing_crosses_a_business_and_the_link_is_the_only_way_in(client, account):
    tenant = account["client"]
    q = make_quote(tenant)
    other_email = f"other-{account['email']}"
    client.post("/api/client/register", json={"email": other_email, "password": "Passw0rdTest", "company_name": "Other Co"})
    client.post("/api/client/login", json={"email": other_email, "password": "Passw0rdTest"})
    assert client.get(f"/api/quotes/{q['number']}").status_code == 404
    # The public page answers to the link, whoever holds it, and to nothing else.
    client.cookies.clear()
    assert public(client, q).status_code == 200
    assert client.get(f"/api/public/quotes/{q['number']}").status_code == 404
