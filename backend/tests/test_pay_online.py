"""'View and pay online': a code to scan and the ways to pay, as badges, on the
invoice PDF, in the email and on the customer's page - only ever the ways this
business really has switched on, and nothing at all when there is nothing to
pay with or nowhere for the code to go."""
import io
import json

import pytest
from pypdf import PdfReader

import main
from conftest import make_invoice


@pytest.fixture(autouse=True)
def _reset():
    main.rate_limiter._hits.clear()
    yield


def words(data: bytes):
    assert data[:5] == b"%PDF-"
    return "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(data)).pages)


def invoice(tenant, **kw):
    kw.setdefault("status", "Awaiting Payment")
    return make_invoice(tenant, contact="Acme Ltd", email="acme@example.com", issue_date="2026-09-01", due_date="2026-10-01", tax_type="exclusive",
                        line_items=[{"name": "Design", "description": "Logo", "qty": 1, "price": 100, "tax_rate": "No Tax"}], **kw)


def methods(monkeypatch, *providers):
    monkeypatch.setattr(main, "invoice_payment_methods", lambda db, inv: [{"provider": p, "label": p, "mode": "direct"} for p in providers])


# --- the code ------------------------------------------------------------------------
def test_the_qr_code_is_a_proper_square_with_its_three_finder_patterns():
    m = main.qr_matrix("https://aniprotech.com/invoice.html?id=0b5e8c4d-1234-4abc-9def-0123456789ab&pay=1")
    n = len(m)
    assert n in (v * 4 + 17 for v in range(1, 41)) and all(len(r) == n and set(r) <= {"0", "1"} for r in m)
    for top, left in ((0, 0), (0, n - 7), (n - 7, 0)):                    # the 7x7 squares in three corners
        assert all(m[top][left + i] == "1" and m[top + 6][left + i] == "1" and m[top + i][left] == "1" and m[top + i][left + 6] == "1" for i in range(7))
        assert all(m[top + 1 + i][left + 1] == "0" for i in range(5)) and m[top + 3][left + 3] == "1"
    assert all(m[6][c] == ("1" if c % 2 == 0 else "0") for c in range(8, n - 8)), "the timing pattern between them"
    assert main.qr_matrix("https://aniprotech.com/a") != main.qr_matrix("https://aniprotech.com/b")
    assert main.qr_matrix("https://aniprotech.com/a") == main.qr_matrix("https://aniprotech.com/a")


def test_a_longer_address_makes_a_bigger_code_that_still_fits_the_page():
    short = len(main.qr_matrix("https://a.co/i?id=1"))
    long_ = len(main.qr_matrix("https://aniprotech.com/invoice.html?id=" + "x" * 36 + "&pay=1"))
    assert short < long_ <= 57, "no bigger than version 10 for any address we make"


# --- which badges --------------------------------------------------------------------
def test_the_badges_are_the_ways_to_pay_in_a_fixed_order():
    assert main.pay_badges_for(["stripe"]) == ["visa", "mastercard", "amex", "applepay", "googlepay"]
    assert main.pay_badges_for(["paypal", "stripe"]) == ["visa", "mastercard", "amex", "applepay", "googlepay", "paypal"]
    assert main.pay_badges_for(["razorpay", "stripe"]) == ["visa", "mastercard", "amex", "applepay", "googlepay", "upi"], "no duplicates"
    assert main.pay_badges_for(["gocardless", "saltedge"]) == ["bank"]
    assert main.pay_badges_for(["nonsense"]) == [] and main.pay_badges_for([]) == []


# --- when there is a block -----------------------------------------------------------
def block_for(tenant, **kw):
    inv = invoice(tenant, **kw)
    with main.SessionLocal() as db:
        row = db.query(main.models.DBInvoice).filter(main.models.DBInvoice.tracking_id == tenant.get(f"/api/invoices/{inv['number']}").json()["tracking_id"]).first()
        return inv, main.pay_online_block(db, row, None)


def test_the_block_has_a_heading_a_link_the_badges_and_a_code_for_that_link(tenant, monkeypatch):
    monkeypatch.setattr(main, "page_url", lambda path, request=None: "https://aniprotech.test" + path)
    methods(monkeypatch, "stripe", "paypal")
    inv, b = block_for(tenant)
    assert b["heading"] == "View and pay online" and b["badges"][-1] == "paypal" and "visa" in b["badges"]
    assert b["url"].startswith("https://aniprotech.test/invoice.html?id=") and b["url"].endswith("&pay=1")
    assert b["matrix"] == main.qr_matrix(b["url"]), "the code is the link"


@pytest.mark.parametrize("status", ["Paid", "Void"])
def test_nothing_to_pay_means_no_block(tenant, monkeypatch, status):
    methods(monkeypatch, "stripe")
    assert block_for(tenant, status=status)[1] is None


def test_no_way_to_pay_online_means_no_block(tenant, monkeypatch):
    methods(monkeypatch)
    assert block_for(tenant)[1] is None


def test_an_address_a_phone_could_not_open_means_no_block(tenant, monkeypatch):
    methods(monkeypatch, "stripe")
    monkeypatch.setattr(main, "page_url", lambda path, request=None: path)          # no host known: a bare path
    assert block_for(tenant)[1] is None


def test_a_failure_working_it_out_never_takes_the_document_down(tenant, monkeypatch):
    def boom(db, inv):
        raise RuntimeError("gateway lookup failed")
    monkeypatch.setattr(main, "invoice_payment_methods", boom)
    inv, b = block_for(tenant)
    assert b is None
    assert tenant.get(f"/api/invoices/{inv['number']}/pdf").status_code == 200


# --- the invoice and its PDF ----------------------------------------------------------
def test_the_invoice_the_screen_loads_carries_the_block(tenant, monkeypatch):
    methods(monkeypatch, "stripe")
    inv = invoice(tenant)
    got = tenant.get(f"/api/invoices/{inv['number']}").json()
    assert got["pay_online"]["heading"] == "View and pay online" and got["pay_online"]["url"].endswith("&pay=1") and len(got["pay_online"]["matrix"]) >= 21
    methods(monkeypatch)
    assert tenant.get(f"/api/invoices/{inv['number']}").json()["pay_online"] is None


def test_the_pdf_says_view_and_pay_online_when_there_is_a_way_to_pay(tenant, monkeypatch):
    methods(monkeypatch, "stripe")
    inv = invoice(tenant)
    text = words(tenant.get(f"/api/invoices/{inv['number']}/pdf").content)
    assert "View and pay online" in text and "Scan the code with your phone to pay." in text and "TOTAL" in text


def test_the_pdf_leaves_it_out_when_there_is_nothing_to_offer(tenant, monkeypatch):
    methods(monkeypatch)
    inv = invoice(tenant)
    assert "View and pay online" not in words(tenant.get(f"/api/invoices/{inv['number']}/pdf").content)
    methods(monkeypatch, "stripe")
    paid = invoice(tenant, status="Paid")
    assert "View and pay online" not in words(tenant.get(f"/api/invoices/{paid['number']}/pdf").content)


def test_a_business_can_hide_it_from_its_template(tenant, monkeypatch):
    methods(monkeypatch, "stripe")
    inv = invoice(tenant)
    assert "View and pay online" in words(tenant.get(f"/api/invoices/{inv['number']}/pdf").content)
    layout = [{"id": "pay_online", "visible": False, "label": "View and pay online"}]
    assert tenant.post("/api/settings", json={"invoice_layout": json.dumps(layout)}).status_code == 200
    assert "View and pay online" not in words(tenant.get(f"/api/invoices/{inv['number']}/pdf").content)


def test_quotes_and_credit_notes_do_not_get_one(tenant, monkeypatch):
    methods(monkeypatch, "stripe")
    with main.SessionLocal() as db:
        client = db.query(main.models.DBClient).first()
        inv = db.query(main.models.DBInvoice).first()
        if inv is None:
            pytest.skip("no invoice to borrow")
        for kind in ("quote", "credit_note"):
            assert main.pdf_document_data(db, inv, client, kind)["pay_online"] is None


def test_the_customers_own_download_has_it_too(tenant, monkeypatch):
    methods(monkeypatch, "stripe")
    inv = invoice(tenant)
    tracking = tenant.get(f"/api/invoices/{inv['number']}").json()["tracking_id"]
    r = tenant.get(f"/api/public/invoices/{tracking}/pdf")
    assert r.status_code == 200 and "View and pay online" in words(r.content)


def test_the_pdf_draws_with_every_badge_and_many_lines_without_breaking(tenant, monkeypatch):
    methods(monkeypatch, "stripe", "paypal", "razorpay", "gocardless")
    inv = make_invoice(tenant, contact="Acme Ltd", email="a@b.co", status="Awaiting Payment", issue_date="2026-09-01", due_date="2026-10-01", tax_type="exclusive",
                       line_items=[{"name": f"Item {i}", "description": "x " * 40, "qty": 1, "price": 10, "tax_rate": "No Tax"} for i in range(1, 38)])
    data = tenant.get(f"/api/invoices/{inv['number']}/pdf").content
    pages = PdfReader(io.BytesIO(data)).pages
    assert len(pages) >= 2 and "View and pay online" in "\n".join(p.extract_text() for p in pages)
    assert "View and pay online" in pages[-1].extract_text(), "beside the totals, on the page the totals are on"


# --- the email and the page -----------------------------------------------------------
def test_the_email_button_has_the_badges_under_it():
    class Inv:
        due, status, currency, number, due_date, tracking_id = 50.0, "Awaiting Payment", "GBP", "INV-1", "2026-10-01", "abc"
    html, text = main.invoice_pay_block(Inv, "£", "https://aniprotech.test/invoice.html?id=abc", badges=["visa", "mastercard", "applepay", "bank"])
    assert "Review and pay" in html and "Pay online with" in html
    for label in ("VISA", "mastercard", "Apple Pay", "Pay by bank"):
        assert label in html
    plain, _ = main.invoice_pay_block(Inv, "£", "https://aniprotech.test/invoice.html?id=abc")
    assert "Review and pay" in plain and "Pay online with" not in plain, "no badges asked for, none shown"
    assert "Pay online with" not in main.pay_block_html("x", "£1", "", "INV-1")


def test_an_email_that_is_sent_carries_the_badges(tenant, monkeypatch):
    seen = []
    monkeypatch.setattr(main, "deliver_and_record", lambda delivery_id, to, subject, body, from_header, html_body, *a, **k: seen.append(html_body))
    methods(monkeypatch, "stripe")
    inv = invoice(tenant)
    r = tenant.post(f"/api/invoices/{inv['number']}/send", json={})
    assert r.status_code == 200, r.text
    assert "Pay online with" in seen[0] and "Apple Pay" in seen[0] and "VISA" in seen[0]
    methods(monkeypatch)
    again = invoice(tenant)
    tenant.post(f"/api/invoices/{again['number']}/send", json={})
    assert "Pay online with" not in seen[1]


def test_the_customers_page_is_told_which_badges_to_draw(tenant, monkeypatch):
    methods(monkeypatch, "paypal", "gocardless")
    inv = invoice(tenant)
    tracking = tenant.get(f"/api/invoices/{inv['number']}").json()["tracking_id"]
    payment = tenant.get(f"/api/public/invoices/{tracking}").json()["payment"]
    assert payment["badges"] == ["paypal", "bank"] and payment["providers"] == ["paypal", "gocardless"]


def test_the_pdf_needs_the_signed_in_business_and_does_not_cross(client, account, monkeypatch):
    tenant = account["client"]
    methods(monkeypatch, "stripe")
    inv = invoice(tenant)
    other = f"other-{account['email']}"
    client.post("/api/client/register", json={"email": other, "password": "Passw0rdTest", "company_name": "Other Co"})
    client.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})
    assert client.get(f"/api/invoices/{inv['number']}/pdf").status_code == 404
    assert client.get(f"/api/invoices/{inv['number']}").status_code == 404
    client.cookies.clear()
    assert client.get(f"/api/invoices/{inv['number']}/pdf").status_code == 401
