"""The document, drawn on the server.

Everything the system sends on its own - a scheduled send, a recurring
invoice, the invoice raised when a quote is accepted, every reminder - went
out with no PDF, because only the browser could draw one. Now the server
draws the same document, every send that arrives without a PDF gets it, and
the customer's page offers it too.
"""
import base64
import io

import pytest
from pypdf import PdfReader

import main
import pdf as pdf_engine
from conftest import make_invoice


def pages(data: bytes):
    assert data[:5] == b"%PDF-", data[:20]
    return PdfReader(io.BytesIO(data)).pages


def words(data: bytes):
    return "\n".join(p.extract_text() for p in pages(data))


LINES = [
    {"name": "Design", "description": "Brand identity: logo, palette, typography and a usage guide", "qty": 3, "price": 450, "disc": 10, "tax_rate": "20% VAT"},
    {"name": "Hosting", "description": "Twelve months", "qty": 1, "price": 240, "tax_rate": "20% VAT"},
    {"name": "Photography", "description": "Half day on site", "qty": 0.5, "price": 600, "tax_rate": "20% VAT"},
]

@pytest.fixture
def outbox(monkeypatch):
    """Every send, run at once, with what was attached to it."""
    sent = []
    monkeypatch.setattr(main.BackgroundTasks, "add_task", lambda self, func, *a, **kw: func(*a, **kw))

    def fake(to, subject, body, from_email, html_body=None, pdf_b64=None, pdf_filename="", logo_data="", client_id=None, cc="", bcc="", *a, **kw):
        sent.append({"to": to, "subject": subject, "pdf_b64": pdf_b64, "pdf_filename": pdf_filename})
        return True, "sent"
    monkeypatch.setattr(main, "send_email_background", fake)
    return sent


# A tiny PNG - one red pixel - that Pillow and reportlab both accept.
PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
# A different one for the signature - reportlab stores one copy of identical bytes.
PNG2 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAIAAAABCAIAAAB7QOjdAAAAD0lEQVR4nGNkYPjPwMAAAAQKAQHOAd3hAAAAAElFTkSuQmCC"


@pytest.fixture
def invoice(tenant):
    tenant.post("/api/settings", json={"company_address": "12 Harbour Street\nBristol BS1 4QA", "phone_number": "0117 000 0000",
                                       "company_abn": "GB123456789", "company_terms": "Payment within 30 days."})
    return make_invoice(tenant, contact="Acme Ltd", email="acme@example.com", status="Sent", issue_date="2026-09-01", due_date="2026-10-01",
                        to_company="Acme Ltd", to_address="1 Long Lane\nLondon EC1A 1AA", tax_type="exclusive",
                        bank_details="Sort code 40-00-00, account 12345678", line_items=LINES)


# --- what is on the page ------------------------------------------------------------
def test_the_document_carries_everything_the_screen_shows(tenant, invoice):
    r = tenant.get(f"/api/invoices/{invoice['number']}/pdf")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"] == f'inline; filename="{invoice["number"]}.pdf"'
    text = words(r.content)
    for expected in ("TAX INVOICE", invoice["number"], "2026-09-01", "Acme Ltd", "1 Long Lane", "London EC1A 1AA", "acme@example.com",
                     "Acme Ltd", "12 Harbour Street", "Tel: 0117 000 0000", "Tax ID: GB123456789",
                     "Description", "Quantity", "Unit Price", "Amount GBP",
                     "Brand identity", "1215.00", "Twelve months", "240.00", "Half day on site", "300.00",
                     "Account Details for payment: Sort code 40-00-00, account 12345678",
                     "Subtotal", "1755.00", "VAT", "351.00", "TOTAL  GBP", "2106.00 GBP",
                     "Due Date: 2026-10-01", "Payment within 30 days.", "PAYMENT ADVICE", "Amount Due", "Page 1"):
        assert expected in text, expected
    assert len(pages(r.content)) == 1


def test_quantities_read_as_the_screen_prints_them(tenant, invoice):
    text = words(tenant.get(f"/api/invoices/{invoice['number']}/pdf").content)
    assert "\n3\n" in text or " 3 " in text or "3 450.00" in text.replace("\n", " ")
    assert "3.0 " not in text and "1.0 " not in text and "0.5" in text


def test_a_quote_and_a_credit_note_say_what_they_are(tenant, invoice):
    q = tenant.post("/api/quotes", json={"contact": "Acme Ltd", "email": "acme@example.com", "issue_date": "2026-09-01", "expiry_date": "2026-09-30",
                                         "tax_type": "exclusive", "line_items": LINES[:1]}).json()
    text = words(tenant.get(f"/api/quotes/{q['number']}/pdf").content)
    assert "QUOTE" in text and "Quote Number" in text and "Valid Until: 2026-09-30" in text
    assert "PAYMENT ADVICE" not in text and "Account Details" not in text
    cn = tenant.post("/api/credit-notes", json={"invoice_number": invoice["number"], "reason": "Overcharged",
                                                "line_items": [{"name": "Hosting", "description": "Twelve months", "qty": 1, "price": 240, "tax_rate": "20% VAT"}]}).json()
    text = words(tenant.get(f"/api/credit-notes/{cn['number']}/pdf").content)
    assert "CREDIT NOTE" in text and f"Against Invoice: {invoice['number']}" in text and "Total Credited" not in text


def test_the_theme_decides_the_columns_the_title_and_the_footer(tenant, invoice):
    th = tenant.get("/api/branding-themes").json()["themes"][0]
    tenant.put(f"/api/branding-themes/{th['id']}", json={"show_quantity": False, "show_price": False, "show_discount": True, "show_tax": True,
                                                         "show_item": True, "label_amount": "Total", "approved_invoice_title": "INVOICE",
                                                         "footer_note": "Thank you for your business", "show_page_numbers": False,
                                                         "logo_position": "left", "font": "times"})
    text = words(tenant.get(f"/api/invoices/{invoice['number']}/pdf").content)
    assert "INVOICE" in text and "TAX INVOICE" not in text
    assert "Quantity" not in text and "Unit Price" not in text
    assert "Discount" in text and "Tax" in text and "Total GBP" in text
    assert "Item / Description" in text and "Design" in text
    assert "10%" in text and "20%" in text
    assert "Thank you for your business" in text and "Page 1" not in text


def test_a_long_invoice_runs_to_more_pages_with_the_table_header_on_each(tenant):
    many = [{"name": f"Line {i}", "description": "Something that was done on day " + str(i), "qty": 1, "price": 10, "tax_rate": "No Tax"} for i in range(60)]
    inv = make_invoice(tenant, status="Sent", line_items=many)
    data = tenant.get(f"/api/invoices/{inv['number']}/pdf").content
    ps = pages(data)
    assert len(ps) >= 2
    for p in ps:
        assert "Description" in p.extract_text()
    assert "Page 1" in ps[0].extract_text() and f"Page {len(ps)}" in ps[-1].extract_text()
    assert "600.00" in ps[-1].extract_text()


def test_a_logo_and_a_signature_are_drawn_when_saved(tenant, invoice):
    tenant.put("/api/client/logo", json={"logo_url": PNG})
    tenant.post("/api/settings", json={"company_signature": PNG2})
    data = tenant.get(f"/api/invoices/{invoice['number']}/pdf").content
    page = pages(data)[0]
    assert len(page.images) == 2, "the logo and the signature"
    assert "Authorised Signature" in page.extract_text() and "LOGO" not in page.extract_text()


def test_the_template_builder_can_hide_sections(tenant, invoice):
    tenant.post("/api/settings", json={"invoice_layout": '[{"id":"bank_details","visible":false},{"id":"payment_stub","visible":false},{"id":"terms_conditions","visible":false}]'})
    text = words(tenant.get(f"/api/invoices/{invoice['number']}/pdf").content)
    assert "Account Details" not in text and "PAYMENT ADVICE" not in text and "Payment within" not in text


def test_a_symbol_the_fonts_lack_is_spelled_out():
    assert pdf_engine.pdf_symbol("₹") == "Rs." and pdf_engine.pdf_symbol("£") == "£"
    data = pdf_engine.document_pdf({"number": "INV-9", "to": "Someone", "currency": "INR", "symbol": "₹",
                                    "line_items": [{"name": "x", "description": "", "qty": 1, "price": 100, "tax_rate": "No Tax"}]}, "invoice")
    assert "Rs.100.00 INR" in words(data)


# --- who gets it ---------------------------------------------------------------------------
def test_the_customer_can_take_the_document_from_their_page(client, tenant, invoice):
    r = client.get(f"/api/public/invoices/{invoice['tracking_id']}/pdf")
    assert r.status_code == 200 and words(r.content).count(invoice["number"]) >= 1
    draft = make_invoice(tenant, status="Draft", line_items=LINES[:1])
    assert client.get(f"/api/public/invoices/{draft['tracking_id']}/pdf").status_code == 404
    assert client.get("/api/public/invoices/not-a-real-one/pdf").status_code == 404


def test_a_send_without_a_pdf_from_the_screen_gets_the_servers(tenant, invoice, outbox):
    r = tenant.post(f"/api/invoices/{invoice['number']}/send", json={})
    assert r.status_code == 200, r.text
    sent = [m for m in outbox if m.get("to") == "acme@example.com"]
    assert sent, outbox
    attached = sent[-1].get("pdf_b64")
    assert attached and sent[-1].get("pdf_filename") == f"{invoice['number']}.pdf"
    assert invoice["number"] in words(base64.b64decode(attached))


def test_the_screens_own_pdf_still_wins_and_unticking_still_drops_it(tenant, invoice, outbox):
    mine = base64.b64encode(b"%PDF-1.4 mine").decode()
    tenant.post(f"/api/invoices/{invoice['number']}/send", json={"pdf_data": mine})
    assert outbox[-1].get("pdf_b64") == mine
    tenant.post(f"/api/invoices/{invoice['number']}/send", json={"attach_pdf": False})
    assert not outbox[-1].get("pdf_b64")


def test_a_reminder_carries_the_invoice(tenant, invoice, outbox):
    with main.SessionLocal() as db:
        row = db.query(main.models.DBInvoice).filter(main.models.DBInvoice.tracking_id == invoice["tracking_id"]).first()
        row.due_date = "2020-01-01"
        row.status = "Overdue"
        db.commit()
        main.send_dunning_reminder(db, row, {"days": 30, "tone": "final", "message": ""}, 30, main.date.today(), by="test")
    mail = [m for m in outbox if m.get("to") == "acme@example.com"][-1]
    assert mail.get("pdf_b64") and mail.get("pdf_filename") == f"{invoice['number']}.pdf"
    assert "TAX INVOICE" in words(base64.b64decode(mail["pdf_b64"]))
