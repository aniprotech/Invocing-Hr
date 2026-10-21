"""Sales and purchase ledger arithmetic: pure, no database.

A ledger is one account's story in date order with a running balance. The
customer side (what customers owe) is built in main.py from invoices, receipts,
credit notes and refunds. The supplier side (what the business owes) is built
from bills, payments and supplier credit notes using what is in here.

Conventions, so nobody has to guess a sign:

* A customer's balance is what they owe the business. A supplier's balance is
  what the business owes them. Both are positive when money is owed.
* Everything that raises the balance is an "increase" (an invoice; a bill),
  everything that lowers it a "decrease" (a receipt; a payment; a credit).
* Money is rounded half up to two places, the way every figure shown is.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, Optional

AGE_BUCKETS = ("current", "1_30", "31_60", "61_90", "over_90")
BUCKET_LABELS = {"current": "Not yet due", "1_30": "1-30 days late", "31_60": "31-60 days late",
                 "61_90": "61-90 days late", "over_90": "Over 90 days late"}

BILL_OPEN = ("Awaiting Payment", "Unpaid", "Partially Paid")
BILL_METHODS = {"bank_transfer": "bank transfer", "card": "card", "cash": "cash", "cheque": "cheque",
                "direct_debit": "direct debit", "other": "other", "credit": "credit note",
                "credit_note": "credit note"}


def money(value) -> float:
    return float(Decimal(str(value if value is not None else 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def parse_day(value) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def age_bucket(days_late: int) -> str:
    """How late a debt is, in the five bands every ageing report uses. Not yet
    due (or due today) is "current"."""
    if days_late <= 0:
        return "current"
    if days_late <= 30:
        return "1_30"
    if days_late <= 60:
        return "31_60"
    if days_late <= 90:
        return "61_90"
    return "over_90"


def days_late(due, as_of) -> int:
    """Whole days past the due date, never negative. No due date means not late."""
    d, day = parse_day(due), parse_day(as_of)
    if not d or not day:
        return 0
    return max(0, (day - d).days)


# ---------------------------------------------------------------------------
# A bill: what is left on it, and what state that makes it
# ---------------------------------------------------------------------------

def bill_status(total, paid, current: str = "") -> str:
    """The status a bill should have from what is paid. A draft stays a draft
    and a void stays void - those are decisions, not arithmetic."""
    if current in ("Draft", "Void"):
        return current
    total, paid = money(total), money(paid)
    if total > 0 and paid >= total - 0.005:
        return "Paid"
    if paid > 0:
        return "Partially Paid"
    # Nothing paid: owed. The Purchases screens call that "Unpaid", older
    # bills "Awaiting Payment"; whichever the bill already had, it keeps.
    owed = "Unpaid" if current == "Unpaid" else "Awaiting Payment"
    if total <= 0 and paid <= 0:
        return "Paid" if current == "Paid" else owed
    return owed


def bill_balance(total, paid) -> float:
    return money(max(0.0, money(total) - money(paid)))


def paid_by(bill_total, issue_date, paid_total, payments: Iterable, as_of) -> float:
    """What had been paid on a bill by the end of a day. `payments` are
    (day, amount) pairs. Payments made before payments were recorded one by one
    leave `paid_total` larger than the pairs add up to; that difference is taken
    as paid when the bill was issued, the earliest it could have been."""
    day = parse_day(as_of)
    rows = [(parse_day(d), money(a)) for d, a in payments]
    explained = money(sum(a for _d, a in rows))
    unexplained = max(0.0, money(paid_total) - explained)
    got = sum(a for d, a in rows if d is None or (day and d <= day))
    issued = parse_day(issue_date)
    if unexplained and (issued is None or (day and issued <= day)):
        got += unexplained
    return money(got)


def outstanding_as_of(bill_total, issue_date, paid_total, payments: Iterable, as_of) -> float:
    """What was still owed on a bill at the end of a day: nothing before it was
    issued, otherwise its total less what had been paid by then."""
    day, issued = parse_day(as_of), parse_day(issue_date)
    if day and issued and issued > day:
        return 0.0
    return money(max(0.0, money(bill_total) - paid_by(bill_total, issue_date, paid_total, payments, as_of)))


# ---------------------------------------------------------------------------
# A running ledger
# ---------------------------------------------------------------------------

def running_ledger(events: list, start: str, end: str, base: str) -> list:
    """Per currency: the balance brought forward at `start`, each event from
    `start` to `end` in date order with the balance after it, and the balance
    carried out. An event is a dict with date (YYYY-MM-DD), kind, ref,
    description, increase, decrease, currency and optionally `order` (the
    sequence of things on one day: bills before the payments that settle them)
    and anything else, which is passed through."""
    out = []
    for cur in sorted({e["currency"] for e in events}, key=lambda c: (c != base, c)):
        mine = sorted((e for e in events if e["currency"] == cur),
                      key=lambda e: (e["date"], e.get("order", 0), str(e.get("ref", ""))))
        opening = money(sum(money(e["increase"]) - money(e["decrease"]) for e in mine if e["date"] < start))
        balance, lines = opening, []
        for e in mine:
            if e["date"] < start or e["date"] > end:
                continue
            balance = money(balance + money(e["increase"]) - money(e["decrease"]))
            lines.append(dict({k: v for k, v in e.items() if k != "order"}, balance=balance))
        out.append({"currency": cur, "opening_balance": opening, "lines": lines, "closing_balance": balance,
                    "increased": money(sum(l["increase"] for l in lines)), "decreased": money(sum(l["decrease"] for l in lines))})
    return out


# ---------------------------------------------------------------------------
# Credit limits
# ---------------------------------------------------------------------------

def credit_position(balance, limit, on_hold: bool = False) -> dict:
    """Where a customer stands against what they are allowed. A limit of 0 or
    none means no limit. `state` is one of: on_hold, over_limit, near_limit
    (90% or more used), ok, no_limit. On hold wins, because it is the thing to
    notice."""
    balance = money(balance)
    lim = money(limit) if limit else 0.0
    if lim <= 0:
        return {"limit": 0.0, "available": None, "used_pct": None, "over_limit": False,
                "state": "on_hold" if on_hold else "no_limit", "on_hold": bool(on_hold)}
    used = round(balance / lim * 100, 1) if lim else None
    over = balance > lim + 0.005
    state = "on_hold" if on_hold else ("over_limit" if over else ("near_limit" if balance >= lim * 0.9 else "ok"))
    return {"limit": lim, "available": money(lim - balance), "used_pct": used, "over_limit": over,
            "state": state, "on_hold": bool(on_hold)}


def blank_buckets() -> dict:
    return {b: 0.0 for b in AGE_BUCKETS}
