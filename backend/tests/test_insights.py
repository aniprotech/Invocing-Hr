"""Insights counted from what actually happened.

The dashboard drew one chart and it was invented: five points made by
multiplying today's revenue by 0.2, 0.4, 0.5, 0.8 and 1. It looked like a
history and was arithmetic on a single number - worse than no chart, because
somebody reads a trend off it and decides something.

So the thing worth guarding hardest is that every number here comes from an
invoice or a payment that exists, and that a month with no trade is reported
as no trade rather than as a zero somebody might read as a bad month.
"""
from datetime import datetime, timedelta

import pytest

import main
import models
from conftest import make_invoice


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


def day(offset):
    return (datetime.now() + timedelta(days=offset)).strftime("%Y-%m-%d")


def insights(tenant, **params):
    res = tenant.get("/api/insights", params=params)
    assert res.status_code == 200, res.text
    return res.json()


def bill(tenant, *, contact="Customer Ltd", issue=None, due=None, price=100.0,
         status="Awaiting Payment", terms=30):
    # An invoice due before it was raised is refused, rightly - so an overdue
    # one is raised far enough back for its due date to follow it.
    if due is not None and issue is None:
        offset = (datetime.strptime(due, "%Y-%m-%d") - datetime.now()).days
        issue = day(offset - terms)
    return make_invoice(
        tenant, contact=contact, status=status,
        issue_date=issue or day(0), due_date=due or day(30),
        line_items=[{"description": "Work", "qty": 1, "price": price,
                     "tax_rate": "No Tax"}])


def pay(tenant, number, amount, on=None):
    res = tenant.post(f"/api/invoices/{number}/payments",
                      json={"amount": amount, "paid_on": on or day(0)})
    assert res.status_code == 200, res.text
    return res.json()


# --- the shape the page relies on ------------------------------------------------
def test_an_empty_business_gets_empty_series_not_an_error(tenant):
    got = insights(tenant)
    assert got["months"], "no months at all"
    assert got["totals"]["invoices"] == 0
    assert got["status_breakdown"] == []
    assert got["top_customers"] == []


def test_the_window_covers_the_months_asked_for(tenant):
    assert len(insights(tenant, months=3)["months"]) == 3
    assert len(insights(tenant, months=12)["months"]) == 12


def test_a_silly_window_is_brought_back_to_something_sensible(tenant):
    """A chart of one month is not a trend and one of ten years will not draw."""
    assert len(insights(tenant, months=1)["months"]) == 3
    assert len(insights(tenant, months=500)["months"]) == 24


def test_every_series_is_as_long_as_the_months(tenant):
    """A series shorter than its labels silently shifts every point onto the
    wrong month."""
    got = insights(tenant, months=6)
    for name, series in got["series"].items():
        assert len(series) == 6, (name, len(series))


# --- the numbers themselves --------------------------------------------------------
def test_invoiced_is_what_was_invoiced(tenant):
    bill(tenant, price=100)
    bill(tenant, price=250)
    got = insights(tenant)
    assert got["totals"]["invoiced"] == 350.0, got["totals"]


def test_a_draft_is_not_counted_as_business_done(tenant):
    """A draft has not been sent to anybody."""
    bill(tenant, price=100)
    bill(tenant, price=999, status="Draft")
    assert insights(tenant)["totals"]["invoiced"] == 100.0


def test_collected_follows_the_payments_not_the_invoices(tenant):
    inv = bill(tenant, price=200)
    pay(tenant, inv["number"], 80)
    got = insights(tenant)
    assert got["totals"]["collected"] == 80.0, got["totals"]
    assert got["totals"]["outstanding"] == 120.0, got["totals"]


def test_a_month_with_no_trade_reports_a_zero_not_a_gap(tenant):
    """The bar has to be there and flat, or the month vanishes off the axis."""
    got = insights(tenant, months=6)
    assert got["series"]["invoiced"][0] == 0


def test_a_month_nobody_paid_in_reports_no_average_rather_than_zero(tenant):
    """Zero days to pay would read as everybody paying instantly."""
    got = insights(tenant, months=6)
    assert all(v is None for v in got["series"]["days_to_pay"]), got["series"]["days_to_pay"]


def test_how_long_people_took_to_pay_is_measured_not_guessed(tenant):
    inv = bill(tenant, issue=day(-10), price=100)
    pay(tenant, inv["number"], 100, on=day(0))
    got = insights(tenant)
    assert got["totals"]["average_days_to_pay"] == 10.0, got["totals"]


# --- the breakdowns ------------------------------------------------------------------
def test_invoices_are_broken_down_by_status(tenant):
    bill(tenant, price=10)
    bill(tenant, price=10, status="Draft")
    labels = {row["label"]: row["value"] for row in insights(tenant)["status_breakdown"]}
    assert labels.get("Awaiting Payment") == 1, labels
    assert labels.get("Draft") == 1, labels


def test_the_best_customers_are_the_ones_who_paid(tenant):
    """Ranked on money received, not money billed - an unpaid invoice does not
    make somebody a good customer."""
    big = bill(tenant, contact="Pays Late Ltd", price=900)
    small = bill(tenant, contact="Pays Up Ltd", price=100)
    pay(tenant, small["number"], 100)

    top = insights(tenant)["top_customers"]
    assert top[0]["label"] == "Pays Up Ltd", top
    assert not any(row["label"] == "Pays Late Ltd" for row in top), top


def test_the_biggest_debtors_are_listed(tenant):
    bill(tenant, contact="Owes Us Ltd", price=500)
    debtors = insights(tenant)["top_debtors"]
    assert debtors[0]["label"] == "Owes Us Ltd"
    assert debtors[0]["value"] == 500.0


def test_somebody_who_owes_nothing_is_not_called_a_debtor(tenant):
    inv = bill(tenant, contact="Settled Ltd", price=100)
    pay(tenant, inv["number"], 100)
    assert insights(tenant)["top_debtors"] == []


# --- ageing ---------------------------------------------------------------------------
def test_money_not_yet_due_is_not_called_overdue(tenant):
    bill(tenant, due=day(20), price=300)
    ageing = {row["label"]: row["value"] for row in insights(tenant)["ageing"]}
    assert ageing["Not yet due"] == 300.0, ageing
    assert ageing["1-30 days"] == 0


def test_overdue_money_lands_in_the_right_bucket(tenant):
    bill(tenant, due=day(-10), price=100)
    bill(tenant, due=day(-45), price=200)
    bill(tenant, due=day(-120), price=400)
    ageing = {row["label"]: row["value"] for row in insights(tenant)["ageing"]}
    assert ageing["1-30 days"] == 100.0, ageing
    assert ageing["31-60 days"] == 200.0, ageing
    assert ageing["Over 90 days"] == 400.0, ageing


def test_a_paid_invoice_ages_nothing(tenant):
    inv = bill(tenant, due=day(-120), price=400)
    pay(tenant, inv["number"], 400)
    assert all(row["value"] == 0 for row in insights(tenant)["ageing"])


def test_every_ageing_bucket_is_present_even_when_empty(tenant):
    """The chart draws fixed bars; a missing one shifts the rest along."""
    labels = [row["label"] for row in insights(tenant)["ageing"]]
    assert labels == ["Not yet due", "1-30 days", "31-60 days",
                      "61-90 days", "Over 90 days"], labels


# --- other people's books ---------------------------------------------------------------
def test_one_business_never_sees_another_s_figures(tenant, client):
    bill(tenant, contact="Mine Ltd", price=1000)
    import uuid
    email = f"other-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/client/register", json={
        "email": email, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    client.post("/api/client/login", json={"email": email, "password": "Passw0rdTest"})
    got = client.get("/api/insights").json()
    assert got["totals"]["invoiced"] == 0, got["totals"]
    assert got["top_customers"] == []


def test_insights_need_a_session(client):
    assert client.get("/api/insights").status_code in (401, 403)
