"""The one thing an invoice email is for: getting paid.

What a customer received was a sentence with a link in it, near the bottom,
in the same grey as everything else. What every other invoice they receive
gives them is a block at the top - the amount, the date it is due, which
invoice it is - and one button. This is that block, in the invoice itself,
in every chase, and in the late-fee notice, pointing at the payment page
that already offers card, bank debit and the rest.

Once there is nothing left to pay the button would be a lie, so it becomes
a plain link. An invoice with no public page gets neither.
"""
from datetime import date, timedelta

import pytest

import main
import models
from conftest import make_invoice


@pytest.fixture(autouse=True)
def _reset():
    main.rate_limiter._hits.clear()
    with main.SessionLocal() as db:
        db.query(models.DBJobRun).delete()
        db.commit()
    yield


@pytest.fixture
def outbox(monkeypatch):
    """Every send, run at once, with the HTML half kept."""
    sent = []
    monkeypatch.setattr(main.BackgroundTasks, "add_task", lambda self, func, *a, **kw: func(*a, **kw))
    monkeypatch.setattr(main, "send_email_background",
                        lambda to, subject, body, from_email, html_body=None, *a, **kw:
                        (sent.append({"to": to, "subject": subject, "text": body, "html": html_body or ""}), (True, "sent"))[1])
    return sent


def d(n):
    return (date.today() + timedelta(days=n)).isoformat()


def an_invoice(tenant, **kw):
    fields = dict(status="Awaiting Payment", contact="Acme Ltd", email="acme@pay.test",
                  issue_date=d(0), due_date=d(14), tax_type="none",
                  line_items=[{"description": "Work", "qty": 1, "price": 5.0, "tax_rate": "No Tax"}])
    fields.update(kw)
    return make_invoice(tenant, **fields)


def send(tenant, inv):
    res = tenant.post(f"/api/invoices/{inv['number']}/send", json={"attach_pdf": False})
    assert res.status_code == 200, res.text
    return res


def row_for(inv):
    """By id, never by number: invoice numbers repeat across businesses."""
    with main.SessionLocal() as db:
        return db.query(models.DBInvoice).filter(models.DBInvoice.id == inv["id"]).first()


# --- the invoice itself ------------------------------------------------------
def test_the_invoice_email_carries_a_button_to_the_payment_page(tenant, outbox):
    inv = an_invoice(tenant)
    send(tenant, inv)
    html = outbox[0]["html"]
    assert "Review and pay" in html, html[:400]
    tracking = row_for(inv).tracking_id
    assert f"invoice.html?id={tracking}" in html


def test_the_block_says_what_is_owed_when_and_which_invoice(tenant, outbox):
    inv = an_invoice(tenant, due_date="2026-09-23")
    send(tenant, inv)
    html = outbox[0]["html"]
    assert "5.00 GBP" in html, html[:400]
    assert "Due 23 Sep 2026" in html
    assert f"Invoice #: {inv['number']}" in html


def test_the_plain_text_half_makes_the_same_offer(tenant, outbox):
    """With nothing written on the send screen and no saved wording, the
    generated message is what goes out - and it makes the same offer."""
    inv = an_invoice(tenant, due_date="2026-09-23")
    res = tenant.post(f"/api/invoices/{inv['number']}/send", json={"attach_pdf": False, "body": ""})
    assert res.status_code == 200, res.text
    text = outbox[0]["text"]
    assert "Review and pay: " in text and "invoice.html?id=" in text, text[-500:]
    assert "Due 23 Sep 2026" in text


def test_the_link_is_the_public_id_never_the_number(tenant, outbox):
    inv = an_invoice(tenant)
    send(tenant, inv)
    html = outbox[0]["html"]
    assert f"id={inv['number']}" not in html


def test_the_button_survives_a_body_the_business_wrote_itself(tenant, outbox):
    """The written words replace the message, not the way to pay."""
    inv = an_invoice(tenant)
    res = tenant.post(f"/api/invoices/{inv['number']}/send",
                      json={"attach_pdf": False, "subject": "Your invoice", "body": "Hi, here it is."})
    assert res.status_code == 200, res.text
    assert "Review and pay" in outbox[0]["html"]


# --- nothing left to pay -----------------------------------------------------
def test_a_settled_invoice_gets_a_link_not_a_button(tenant):
    inv = an_invoice(tenant)
    row = row_for(inv)
    row.status, row.due = "Paid", 0.0
    html, text = main.invoice_pay_block(row, "£", "https://x.test/invoice.html?id=abc")
    assert "Review and pay" not in html and "View this invoice online" in html
    assert text.startswith("View this invoice online: ")


def test_an_invoice_with_no_public_page_gets_neither(tenant):
    row = row_for(an_invoice(tenant))
    row.tracking_id = ""
    assert main.invoice_pay_block(row, "£") == ("", "")


# --- the chase and the fee ---------------------------------------------------
def test_a_chase_carries_the_button_in_the_colour_of_the_notice(tenant):
    row = row_for(an_invoice(tenant, issue_date=d(-44), due_date=d(-30)))
    for tone, colour in (("gentle", "#0f172a"), ("firm", "#b45309"), ("final", "#9f1239")):
        _s, text, html = main.reminder_copy({"days": 30, "tone": tone}, row, "Northwind", "£", 30, 0.0,
                                            None, "https://x.test/invoice.html?id=abc")
        assert "Review and pay" in html and f"background:{colour}" in html, tone
        assert "Review and pay: https://x.test/invoice.html?id=abc" in text, tone
        # The old sentence is gone, not printed alongside it.
        assert "View and pay online:" not in text, tone


def test_the_late_fee_notice_carries_it_too(tenant, monkeypatch, outbox):
    row = row_for(an_invoice(tenant, issue_date=d(-54), due_date=d(-40)))
    with main.SessionLocal() as db:
        inv = db.query(models.DBInvoice).filter(models.DBInvoice.id == row.id).first()
        fee = main.apply_late_fee(db, inv, 10.0, "flat", 40, date.today())
        db.commit()
        main.tell_customer_about_fee(db, inv, fee)
    assert outbox and "Review and pay" in outbox[0]["html"]
    assert "background:#b45309" in outbox[0]["html"], "the fee notice keeps its own colour"


# --- the block on its own ----------------------------------------------------
def test_a_name_with_a_quote_in_it_does_not_break_the_button():
    html = main.pay_block_html("https://x.test/i?a=1&b=2", "£5.00 GBP", "23 Sep 2026", 'INV-"01"')
    assert "&amp;b=2" in html, "the link is escaped for an attribute"
    assert '"' not in html.split('Invoice #:')[1].split('</div>')[0], "and so is the number"


def test_a_due_date_nobody_can_read_is_printed_as_it_stands(tenant):
    row = row_for(an_invoice(tenant))
    row.due_date = "whenever"
    html, _text = main.invoice_pay_block(row, "£", "https://x.test/i")
    assert "Due whenever" in html and "Review and pay" in html


def test_no_due_date_at_all_leaves_the_line_out(tenant):
    row = row_for(an_invoice(tenant))
    row.due_date = ""
    html, text = main.invoice_pay_block(row, "£", "https://x.test/i")
    assert "Due " not in html and "Review and pay" in html
    assert "Due " not in text


def test_the_amount_is_the_currency_the_invoice_is_in(tenant):
    row = row_for(an_invoice(tenant))
    row.currency = "usd"
    html, _ = main.invoice_pay_block(row, "$", "https://x.test/i")
    assert "$5.00 USD" in html
