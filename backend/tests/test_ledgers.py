"""The arithmetic under the sales and purchase ledgers, with no database.

Every figure a ledger shows is worked out from documents - bills, payments,
credit notes - so the working has to be right on the edges: the day a debt
turns late, a bill paid in three goes, a payment made before payments were
recorded one by one, an account that spans two currencies.
"""
import pytest

import ledgers as L


# --- how late ------------------------------------------------------------------------
@pytest.mark.parametrize("days,bucket", [
    (-30, "current"), (-1, "current"), (0, "current"), (1, "1_30"), (30, "1_30"), (31, "31_60"), (60, "31_60"),
    (61, "61_90"), (90, "61_90"), (91, "over_90"), (400, "over_90"),
])
def test_a_debt_falls_into_the_band_for_how_late_it_is(days, bucket):
    assert L.age_bucket(days) == bucket


@pytest.mark.parametrize("due,as_of,late", [
    ("2026-05-31", "2026-05-31", 0), ("2026-05-31", "2026-06-01", 1), ("2026-05-31", "2026-05-01", 0),
    ("2026-05-01", "2026-07-01", 61), ("", "2026-07-01", 0), ("not a date", "2026-07-01", 0), (None, None, 0),
    ("2026-05-31T10:00:00", "2026-06-02", 2),
])
def test_days_late_is_whole_days_past_due_and_never_negative(due, as_of, late):
    assert L.days_late(due, as_of) == late


def test_every_band_has_a_label_and_the_buckets_start_at_zero():
    assert set(L.BUCKET_LABELS) == set(L.AGE_BUCKETS) and L.blank_buckets() == {b: 0.0 for b in L.AGE_BUCKETS}


# --- a bill's state --------------------------------------------------------------------
@pytest.mark.parametrize("total,paid,current,status", [
    (100, 0, "Awaiting Payment", "Awaiting Payment"), (100, 40, "Awaiting Payment", "Partially Paid"),
    (100, 100, "Awaiting Payment", "Paid"), (100, 99.996, "Awaiting Payment", "Paid"), (100, 99.99, "Awaiting Payment", "Partially Paid"),
    (100, 100, "Partially Paid", "Paid"), (100, 0, "Paid", "Awaiting Payment"), (100, 0, "Partially Paid", "Awaiting Payment"),
    (100, 0, "Draft", "Draft"), (100, 100, "Void", "Void"), (0, 0, "Paid", "Paid"), (0, 0, "Awaiting Payment", "Awaiting Payment"),
    (100, 140, "Awaiting Payment", "Paid"),
])
def test_a_bills_status_follows_what_is_paid(total, paid, current, status):
    assert L.bill_status(total, paid, current) == status


@pytest.mark.parametrize("total,paid,left", [(100, 0, 100.0), (100, 40.5, 59.5), (100, 100, 0.0), (100, 130, 0.0), (0.1 + 0.2, 0.3, 0.0)])
def test_what_is_left_on_a_bill_is_never_negative_and_never_floats_off(total, paid, left):
    assert L.bill_balance(total, paid) == left


# --- what was owed on a day -----------------------------------------------------------
PAYS = [("2026-03-10", 40), ("2026-04-10", 35)]


@pytest.mark.parametrize("as_of,owed", [
    ("2026-02-28", 0.0),            # not yet issued
    ("2026-03-01", 100.0),          # the day it was issued
    ("2026-03-09", 100.0), ("2026-03-10", 60.0), ("2026-04-09", 60.0), ("2026-04-10", 25.0), ("2026-12-31", 25.0),
])
def test_what_was_owed_on_a_bill_on_any_day(as_of, owed):
    assert L.outstanding_as_of(100, "2026-03-01", 75, PAYS, as_of) == owed


def test_payments_before_they_were_recorded_one_by_one_count_from_the_day_the_bill_was_issued():
    # 100 billed, 30 paid in total, but only 10 recorded individually: the other 20 predate the record.
    pays = [("2026-04-01", 10)]
    assert L.paid_by(100, "2026-03-01", 30, pays, "2026-03-15") == 20.0
    assert L.paid_by(100, "2026-03-01", 30, pays, "2026-04-01") == 30.0
    assert L.outstanding_as_of(100, "2026-03-01", 30, pays, "2026-03-15") == 80.0
    assert L.outstanding_as_of(100, "2026-03-01", 30, pays, "2026-04-02") == 70.0


def test_a_bill_with_nothing_recorded_but_something_paid_is_paid_from_the_start():
    assert L.paid_by(50, "2026-03-01", 50, [], "2026-03-01") == 50.0
    assert L.outstanding_as_of(50, "2026-03-01", 50, [], "2026-03-01") == 0.0


def test_a_payment_with_no_date_counts_as_made():
    assert L.paid_by(100, "2026-03-01", 20, [("", 20)], "2026-03-02") == 20.0


def test_overpaid_is_never_a_negative_debt():
    assert L.outstanding_as_of(100, "2026-03-01", 120, [("2026-03-02", 120)], "2026-03-05") == 0.0


# --- a running ledger ------------------------------------------------------------------
def ev(day, kind, inc=0.0, dec=0.0, cur="GBP", ref="", order=0, **more):
    return dict(date=day, kind=kind, ref=ref, description=f"{kind} {ref}", increase=inc, decrease=dec, currency=cur, order=order, **more)


def test_a_ledger_carries_a_balance_forward_and_runs_it_down_the_page():
    events = [ev("2026-01-05", "bill", 100, ref="B1"), ev("2026-01-20", "payment", dec=40, ref="P1", order=2),
              ev("2026-02-03", "bill", 60, ref="B2"), ev("2026-02-10", "payment", dec=20, ref="P2", order=2)]
    out = L.running_ledger(events, "2026-02-01", "2026-02-28", "GBP")
    assert len(out) == 1
    led = out[0]
    assert led["opening_balance"] == 60.0 and [l["balance"] for l in led["lines"]] == [120.0, 100.0] and led["closing_balance"] == 100.0
    assert led["increased"] == 60.0 and led["decreased"] == 20.0


def test_the_first_and_last_day_are_both_included():
    events = [ev("2026-02-01", "bill", 10, ref="A"), ev("2026-02-28", "bill", 5, ref="B"), ev("2026-03-01", "bill", 99, ref="C")]
    led = L.running_ledger(events, "2026-02-01", "2026-02-28", "GBP")[0]
    assert [l["ref"] for l in led["lines"]] == ["A", "B"] and led["closing_balance"] == 15.0 and led["opening_balance"] == 0.0


def test_on_one_day_a_bill_comes_before_the_payment_that_settles_it():
    # The refs sort the wrong way round on purpose, so only the order can put the bill first.
    events = [ev("2026-02-01", "payment", dec=50, ref="A-PAY", order=2), ev("2026-02-01", "bill", 50, ref="Z-BILL", order=0)]
    led = L.running_ledger(events, "2026-02-01", "2026-02-28", "GBP")[0]
    assert [l["kind"] for l in led["lines"]] == ["bill", "payment"] and [l["balance"] for l in led["lines"]] == [50.0, 0.0]


def test_each_currency_has_its_own_ledger_and_the_books_currency_comes_first():
    events = [ev("2026-02-01", "bill", 100, cur="USD", ref="U"), ev("2026-02-02", "bill", 10, cur="GBP", ref="G"), ev("2026-02-03", "bill", 7, cur="EUR", ref="E")]
    out = L.running_ledger(events, "2026-02-01", "2026-02-28", "GBP")
    assert [o["currency"] for o in out] == ["GBP", "EUR", "USD"] and [o["closing_balance"] for o in out] == [10.0, 7.0, 100.0]


def test_a_ledger_of_nothing_is_nothing():
    assert L.running_ledger([], "2026-02-01", "2026-02-28", "GBP") == []


def test_extra_fields_on_an_event_come_through_and_the_sort_key_does_not():
    out = L.running_ledger([ev("2026-02-01", "bill", 10, ref="A", bill_id=7)], "2026-02-01", "2026-02-28", "GBP")[0]["lines"][0]
    assert out["bill_id"] == 7 and "order" not in out


def test_a_balance_can_go_negative_when_credits_exceed_bills():
    led = L.running_ledger([ev("2026-02-01", "bill", 10, ref="A"), ev("2026-02-02", "credit", dec=25, ref="C", order=1)], "2026-02-01", "2026-02-28", "GBP")[0]
    assert led["closing_balance"] == -15.0


def test_pence_do_not_drift_over_many_lines():
    events = [ev(f"2026-02-{d:02d}", "bill", 0.1, ref=f"B{d}") for d in range(1, 11)]
    assert L.running_ledger(events, "2026-02-01", "2026-02-28", "GBP")[0]["closing_balance"] == 1.0


# --- credit limits -------------------------------------------------------------------------
@pytest.mark.parametrize("balance,limit,hold,state,available", [
    (500, 1000, False, "ok", 500.0), (900, 1000, False, "near_limit", 100.0), (1000, 1000, False, "near_limit", 0.0),
    (1000.004, 1000, False, "near_limit", -0.0), (1000.01, 1000, False, "over_limit", -0.01), (1500, 1000, False, "over_limit", -500.0),
    (500, 0, False, "no_limit", None), (500, None, False, "no_limit", None), (500, 1000, True, "on_hold", 500.0), (5000, 1000, True, "on_hold", -4000.0),
    (500, 0, True, "on_hold", None), (0, 1000, False, "ok", 1000.0),
])
def test_where_an_account_stands_against_its_credit_limit(balance, limit, hold, state, available):
    pos = L.credit_position(balance, limit, hold)
    assert pos["state"] == state and pos["on_hold"] is hold
    assert (pos["available"] == available) or (available is not None and abs(pos["available"] - available) < 0.0001)


def test_over_limit_is_only_true_past_the_limit():
    assert L.credit_position(1000, 1000)["over_limit"] is False
    assert L.credit_position(1000.01, 1000)["over_limit"] is True
    assert L.credit_position(50, 0)["over_limit"] is False


def test_the_share_of_the_limit_used_is_given():
    assert L.credit_position(250, 1000)["used_pct"] == 25.0 and L.credit_position(250, 0)["used_pct"] is None


# --- money ------------------------------------------------------------------------------------
@pytest.mark.parametrize("raw,out", [(0.005, 0.01), (0.004, 0.0), (1.005, 1.01), (-1.005, -1.01), (None, 0.0), ("2.5", 2.5), (2.675, 2.68)])
def test_money_rounds_half_up_the_way_every_figure_shown_does(raw, out):
    assert L.money(raw) == out
