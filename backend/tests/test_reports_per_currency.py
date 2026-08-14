"""Reports must never add one currency to another.

The sales pipeline had this bug first: pounds and rupees summed into a single
figure and printed with one symbol, which read in production as forty-four
trillion. The four report endpoints still had it. Aged receivables was the
worst of them - it labelled a mixed total with the account's own currency, so
the number looked authoritative and was wrong.
"""
import pytest

import main


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


def invoice(tenant, price, currency=None, status="Awaiting Payment",
            issue="2026-01-01", due="2026-01-31"):
    body = {
        "contact": "Customer Ltd", "email": "c@example.com",
        "issue_date": issue, "due_date": due, "status": status,
        "tax_type": "none",
        "line_items": [{"description": "Work", "qty": 1, "price": price,
                        "tax_rate": "No Tax"}],
    }
    if currency:
        body["currency"] = currency
    res = tenant.post("/api/invoices", json=body)
    assert res.status_code == 200, res.text
    return res.json()


def paid_invoice(tenant, price, currency=None):
    """Money only counts as received once it is recorded as a payment, so these
    go through mark-paid rather than being created with a Paid status."""
    inv = invoice(tenant, price, currency=currency)
    res = tenant.post(f"/api/invoices/{inv['number']}/mark-paid")
    assert res.status_code == 200, res.text
    return inv


def other(report, code):
    for block in report.get("other_currencies", []):
        if block["currency"] == code:
            return block
    return None


# --- the single-currency case must be untouched -------------------------------

@pytest.mark.parametrize("path", [
    "/api/reports/profit-loss", "/api/reports/balance-sheet",
    "/api/reports/cash-summary", "/api/reports/aged-receivables",
])
def test_one_currency_reports_nothing_extra(tenant, path):
    """Almost every account has a single currency. Those reports must look
    exactly as they did, with no stray foreign block."""
    invoice(tenant, 400.0)
    report = tenant.get(path).json()
    assert report["currency"] == "GBP"
    assert report["other_currencies"] == []


# --- the mixed case -----------------------------------------------------------

def test_aged_receivables_keeps_currencies_apart(tenant):
    invoice(tenant, 400.0, currency="GBP")
    invoice(tenant, 90000.0, currency="INR")

    report = tenant.get("/api/reports/aged-receivables").json()
    assert report["currency"] == "GBP"
    assert report["total_outstanding"] == 400.0, "rupees must not land in the pound total"

    rupees = other(report, "INR")
    assert rupees is not None, "the rupee invoice must still be reported"
    assert rupees["total_outstanding"] == 90000.0


def test_every_aged_row_says_what_currency_it_is_in(tenant):
    invoice(tenant, 400.0, currency="GBP")
    report = tenant.get("/api/reports/aged-receivables").json()
    assert all(r["currency"] == "GBP" for r in report["invoices"])


def test_profit_and_loss_keeps_currencies_apart(tenant):
    paid_invoice(tenant, 400.0, currency="GBP")
    paid_invoice(tenant, 90000.0, currency="INR")

    report = tenant.get("/api/reports/profit-loss").json()
    assert report["total_revenue"] == 400.0
    assert other(report, "INR")["total_revenue"] == 90000.0


def test_the_balance_sheet_keeps_currencies_apart(tenant):
    paid_invoice(tenant, 400.0, currency="GBP")
    paid_invoice(tenant, 90000.0, currency="INR")

    report = tenant.get("/api/reports/balance-sheet").json()
    assert report["assets"]["cash_collected"] == 400.0
    assert other(report, "INR")["assets"]["cash_collected"] == 90000.0


def test_cash_summary_keeps_currencies_apart(tenant):
    paid_invoice(tenant, 400.0, currency="GBP")
    paid_invoice(tenant, 90000.0, currency="INR")

    report = tenant.get("/api/reports/cash-summary").json()
    assert sum(report["money_in"]) == 400.0
    assert sum(other(report, "INR")["money_in"]) == 90000.0


# --- bills --------------------------------------------------------------------

def test_bills_stay_with_the_base_currency(tenant):
    """A bill has no currency column, so it is always in the books' currency.
    It must never be counted against a foreign invoice."""
    paid_invoice(tenant, 90000.0, currency="INR")
    tenant.post("/api/bills", json={
        "vendor_name": "Supplier", "issue_date": "2026-01-05",
        "due_date": "2026-01-20", "amount": 100.0, "total": 100.0})

    report = tenant.get("/api/reports/profit-loss").json()
    assert report["total_expenses"] == 100.0
    assert other(report, "INR")["total_expenses"] == 0.0


# --- the shape the UI relies on ----------------------------------------------

def test_an_empty_account_still_names_its_currency(tenant):
    report = tenant.get("/api/reports/balance-sheet").json()
    assert report["currency"] == "GBP"
    assert report["total_assets"] == 0.0


def test_a_blank_invoice_currency_counts_as_the_base(tenant):
    """Older invoices were saved with an empty currency string. Those are the
    account's own currency, not a separate one."""
    invoice(tenant, 400.0, currency="")
    report = tenant.get("/api/reports/aged-receivables").json()
    assert report["total_outstanding"] == 400.0
    assert report["other_currencies"] == []
