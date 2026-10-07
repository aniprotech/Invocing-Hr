"""Stock: what is on the shelf, why, and what a sale does to it.

Three rules carry everything here.

  1. Every change to a quantity is a row in the stock ledger. The number on an
     item is a running total of that ledger and is never written on its own, so
     "why is it 14" always has an answer and the total can be rebuilt.

  2. A sale takes stock out when an invoice is issued - not drafted, not paid -
     and puts it back if the invoice is voided, deleted, or lowered. This is
     worked out from the invoice as it stands against what the ledger already
     says was taken for it, rather than from "the status changed", because an
     invoice's status and lines are written from a dozen places and a rule that
     had to be remembered at each of them would be forgotten at one. Run
     twice, it does nothing the second time.

  3. Nothing is ever taken out for a sale that was already out. Switching
     tracking on declares a count and covers every invoice already issued with
     a "baseline" row that moves no stock, so touching an old invoice later
     does not take it out of a shelf that was counted after it left.

Selling more than is on hand is allowed and shown, not refused: a business that
cannot raise an invoice because a count is a day behind will stop using the
count. The shelf simply reads negative, and says so.
"""
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import event, func
from sqlalchemy.orm import Session

import models

EPS = 1e-9
MAX_QUANTITY = 1_000_000_000
NOT_ISSUED = ("Draft", "Void")
SALE_KINDS = ("sale", "sale_reversal", "baseline")
COUNT_REASONS = ("stocktake", "damaged", "lost", "found", "returned", "other")
_TOUCHED = "stock_touched_invoices"


class StockError(ValueError):
    """Something wrong with what was asked for, said in words a person can act
    on. The routes turn it into a 400."""


# --- pure arithmetic ---------------------------------------------------------

def invoice_is_issued(status):
    """Stock leaves when an invoice is real - anything but a draft or a void."""
    return (status or "") not in NOT_ISSUED


def clean_quantity(raw, label="Quantity", allow_zero=False, allow_negative=False):
    """A quantity as a number: finite, in range, to four places. Four, because
    people sell by the metre and the kilo, and no more, because float drift
    past that turns "none left" into 1e-12 left."""
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise StockError(f"{label} must be a number")
    if value != value or value in (float("inf"), float("-inf")):
        raise StockError(f"{label} must be a number")
    if abs(value) > MAX_QUANTITY:
        raise StockError(f"{label} is too large")
    if value < 0 and not allow_negative:
        raise StockError(f"{label} cannot be negative")
    if value == 0 and not allow_zero:
        raise StockError(f"{label} must be more than nothing")
    return round(value, 4)


def clean_cost(raw, label="Unit cost"):
    """What one unit cost. Blank is nothing, which is allowed - a gift, a
    sample, or somebody who does not track cost."""
    if raw in (None, ""):
        return 0.0
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise StockError(f"{label} must be a number")
    if value != value or value in (float("inf"), float("-inf")):
        raise StockError(f"{label} must be a number")
    if value < 0:
        raise StockError(f"{label} cannot be negative")
    if value > MAX_QUANTITY:
        raise StockError(f"{label} is too large")
    return round(value, 4)


def average_after_receipt(on_hand, average_cost, quantity, unit_cost):
    """The average cost of a unit once stock arrives: what is on the shelf at
    its average, and what came in at what it cost, over the lot.

    A shelf that is empty or negative has nothing to average with, so the
    new stock sets the price. Averaging into a negative balance would give a
    cost that is meaningless and sometimes negative.
    """
    on_hand = on_hand or 0.0
    if on_hand <= EPS:
        return round(unit_cost, 4)
    total = on_hand + quantity
    if total <= EPS:
        return round(unit_cost, 4)
    return round((on_hand * (average_cost or 0.0) + quantity * unit_cost) / total, 4)


def stock_value(on_hand, average_cost):
    """What the shelf is worth. A negative shelf is worth nothing - it is a
    debt of goods, not an asset, and subtracting it would hide real stock."""
    if (on_hand or 0.0) <= EPS:
        return 0.0
    # Half-up on the decimal, the way money() rounds everywhere else in the
    # app. Python's round() would call 8.325 "8.32", and a shelf value that
    # rounds differently from every invoice total is a reconciliation argument.
    value = Decimal(str(on_hand)) * Decimal(str(average_cost or 0.0))
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def stock_status(track, on_hand, reorder_level):
    """untracked, over (sold more than we had), out, low, or ok."""
    if not track:
        return "untracked"
    on_hand = on_hand or 0.0
    if on_hand < -EPS:
        return "over"
    if on_hand <= EPS:
        return "out"
    if (reorder_level or 0.0) > 0 and on_hand <= reorder_level + EPS:
        return "low"
    return "ok"


def today():
    return datetime.now().strftime("%Y-%m-%d")


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# --- the ledger ----------------------------------------------------------------

def book(db, item, kind, quantity, *, unit_cost=None, affects_stock=True,
         invoice_id=None, invoice_number="", reason="", note="", moved_on="",
         created_by=""):
    """Write one row and move the item's total by it. The only place a quantity
    changes."""
    if affects_stock:
        item.quantity_on_hand = round((item.quantity_on_hand or 0.0) + quantity, 4)
    row = models.DBStockMovement(
        client_id=item.client_id, item_id=item.id, kind=kind,
        quantity=round(quantity, 4), affects_stock=bool(affects_stock),
        unit_cost=round(item.average_cost or 0.0 if unit_cost is None else unit_cost, 4),
        balance_after=round(item.quantity_on_hand or 0.0, 4),
        invoice_id=invoice_id, invoice_number=(invoice_number or "")[:60],
        reason=(reason or "")[:40], note=(note or "")[:200],
        moved_on=moved_on or today(), created_by=(created_by or "")[:120])
    db.add(row)
    return row


def receive(db, item, quantity, unit_cost, *, note="", moved_on="", created_by=""):
    """Stock arrives. The average cost is worked out before the quantity moves,
    because it averages what was there with what is coming."""
    quantity = clean_quantity(quantity, "Quantity received")
    unit_cost = clean_cost(unit_cost)
    _require_tracked(item)
    item.average_cost = average_after_receipt(
        item.quantity_on_hand, item.average_cost, quantity, unit_cost)
    return book(db, item, "received", quantity, unit_cost=unit_cost, note=note,
                moved_on=moved_on, created_by=created_by)


def count(db, item, counted, reason, *, note="", created_by=""):
    """A physical count. The movement is the difference from what the book said,
    so a count that agrees changes nothing and says so."""
    counted = clean_quantity(counted, "The count", allow_zero=True)
    reason = (reason or "").strip().lower()
    if reason not in COUNT_REASONS:
        raise StockError("Say why: " + ", ".join(COUNT_REASONS))
    _require_tracked(item)
    delta = round(counted - (item.quantity_on_hand or 0.0), 4)
    if abs(delta) <= EPS:
        raise StockError("That is what the book already says")
    return book(db, item, "adjustment", delta, reason=reason, note=note,
                created_by=created_by)


def start_tracking(db, item, counted, unit_cost=None, *, created_by=""):
    """Turn stock tracking on, with a count to start from.

    The count replaces whatever number was there, and the invoices already
    issued with this item are covered with baseline rows - that stock left
    before the shelf was counted, and must not leave again.
    """
    counted = clean_quantity(counted, "Opening count", allow_zero=True)
    cost = clean_cost(unit_cost) if unit_cost not in (None, "") else (
        item.average_cost or item.purchase_price or 0.0)
    item.track_inventory = True
    item.average_cost = round(cost, 4)
    # The number on an item is the ledger and nothing else. Whatever was typed
    # there before tracking - a legacy quantity nobody maintained - is not
    # stock, so it is replaced by what the ledger says (nothing, the first
    # time) and the count is booked as the movement that gets it to the count.
    was = _ledger_total(db, item)
    item.quantity_on_hand = was
    delta = round(counted - was, 4)
    if abs(delta) > EPS or not _has_movements(db, item):
        book(db, item, "opening", delta, unit_cost=cost, note="Counted when tracking started",
             created_by=created_by)
    baseline(db, item)


def stop_tracking(item):
    """Stop moving stock for this item. What was recorded stays, and so does the
    last quantity - this does not forget anything, it stops adding to it."""
    item.track_inventory = False


def _require_tracked(item):
    if not item.track_inventory:
        raise StockError("Start tracking stock for this item first")


def _ledger_total(db, item):
    """What the ledger says is on the shelf: every row that moved stock."""
    total = db.query(func.sum(models.DBStockMovement.quantity)).filter(
        models.DBStockMovement.client_id == item.client_id,
        models.DBStockMovement.item_id == item.id,
        models.DBStockMovement.affects_stock == True).scalar()          # noqa: E712
    return round(total or 0.0, 4)


def _has_movements(db, item):
    return db.query(models.DBStockMovement.id).filter(
        models.DBStockMovement.client_id == item.client_id,
        models.DBStockMovement.item_id == item.id).first() is not None


def _booked_units(db, invoice_ids):
    """{(invoice_id, item_id): units the ledger says were taken for the invoice}."""
    if not invoice_ids:
        return {}
    rows = db.query(
        models.DBStockMovement.invoice_id, models.DBStockMovement.item_id,
        func.sum(models.DBStockMovement.quantity)
    ).filter(
        models.DBStockMovement.invoice_id.in_(list(invoice_ids)),
        models.DBStockMovement.kind.in_(SALE_KINDS),
    ).group_by(models.DBStockMovement.invoice_id, models.DBStockMovement.item_id).all()
    # Quantities are negative for units taken, so the units are the negation.
    return {(i, it): -(total or 0.0) for i, it, total in rows}


def _desired_units(db, invoice_ids):
    """{(invoice_id, item_id): units the invoice says should be out}. An invoice
    that is not issued, or is gone, wants none."""
    if not invoice_ids:
        return {}, {}
    invoices = {i.id: i for i in db.query(models.DBInvoice).filter(
        models.DBInvoice.id.in_(list(invoice_ids))).all()}
    want = {}
    lines = db.query(models.DBLineItem).filter(
        models.DBLineItem.invoice_id.in_(list(invoice_ids)),
        models.DBLineItem.item_id != None).all()          # noqa: E711
    for line in lines:
        inv = invoices.get(line.invoice_id)
        if inv is None or not invoice_is_issued(inv.status):
            continue
        key = (line.invoice_id, line.item_id)
        want[key] = want.get(key, 0.0) + float(line.qty or 0.0)
    return want, invoices


def reconcile(db, invoice_ids, *, note_prefix="Invoice"):
    """Bring the ledger in line with these invoices as they now stand.

    For each (invoice, item) the units that should be out are compared with the
    units the ledger says are out, and the difference is booked. Only tracked
    items move; an item's own business must match the invoice's, so a line
    naming somebody else's item moves nothing.
    """
    invoice_ids = {i for i in invoice_ids if i}
    if not invoice_ids:
        return 0
    want, invoices = _desired_units(db, invoice_ids)
    have = _booked_units(db, invoice_ids)
    booked = 0
    # By item first, always, so two invoices touching the same items lock them
    # in the same order and cannot wait on each other.
    for key in sorted(set(want) | set(have), key=lambda k: (k[1], k[0])):
        invoice_id, item_id = key
        item = db.query(models.DBItem).filter(
            models.DBItem.id == item_id).with_for_update().first()
        if item is None or not item.track_inventory:
            continue
        inv = invoices.get(invoice_id)
        if inv is not None and inv.client_id != item.client_id:
            continue
        delta_units = round(want.get(key, 0.0) - have.get(key, 0.0), 4)
        if abs(delta_units) <= EPS:
            continue
        number = inv.number if inv is not None else _last_number(db, invoice_id, item_id)
        book(db, item, "sale" if delta_units > 0 else "sale_reversal", -delta_units,
             invoice_id=invoice_id, invoice_number=number,
             note=(f"{note_prefix} {number}" if inv is not None
                   else f"{note_prefix} {number} was deleted"))
        booked += 1
    return booked


def baseline(db, item):
    """Cover every invoice already issued with this item, moving nothing.

    After a count, the invoices that were issued before it are already reflected
    in it. Each one gets a row for the difference between what it should have
    out and what the ledger has out, flagged as moving no stock.
    """
    ids = {r[0] for r in db.query(models.DBLineItem.invoice_id).join(
        models.DBInvoice, models.DBInvoice.id == models.DBLineItem.invoice_id).filter(
        models.DBLineItem.item_id == item.id,
        models.DBInvoice.client_id == item.client_id).all()}
    ids |= {r[0] for r in db.query(models.DBStockMovement.invoice_id).filter(
        models.DBStockMovement.item_id == item.id,
        models.DBStockMovement.client_id == item.client_id,
        models.DBStockMovement.invoice_id != None).distinct().all()}      # noqa: E711
    if not ids:
        return 0
    want, invoices = _desired_units(db, ids)
    have = _booked_units(db, ids)
    made = 0
    for invoice_id in sorted(ids):
        key = (invoice_id, item.id)
        delta_units = round(want.get(key, 0.0) - have.get(key, 0.0), 4)
        if abs(delta_units) <= EPS:
            continue
        inv = invoices.get(invoice_id)
        # An invoice that has since been deleted still has a number, in the
        # ledger that remembers it.
        number = inv.number if inv is not None else _last_number(db, invoice_id, item.id)
        book(db, item, "baseline", -delta_units, affects_stock=False,
             invoice_id=invoice_id, invoice_number=number,
             note="Out before tracking started")
        made += 1
    return made


def _last_number(db, invoice_id, item_id):
    row = db.query(models.DBStockMovement.invoice_number).filter(
        models.DBStockMovement.invoice_id == invoice_id,
        models.DBStockMovement.item_id == item_id,
        models.DBStockMovement.invoice_number != "").order_by(
        models.DBStockMovement.id.desc()).first()
    return row[0] if row else str(invoice_id)


# --- keeping up with invoices, wherever they are written from ----------------------------------------

def _collect(session, flush_context, instances):
    """Note which invoices this flush touches, so they can be reconciled when it
    commits. Looks at the objects being written, which is every ORM path;
    code that rewrites lines in bulk also writes the invoice, so it is seen."""
    touched = None
    for obj in list(session.new) + list(session.dirty) + list(session.deleted):
        if isinstance(obj, models.DBInvoice):
            ref = obj
        elif isinstance(obj, models.DBLineItem):
            ref = obj.invoice_id or getattr(obj, "invoice", None)
        else:
            continue
        if ref is None:
            continue
        if touched is None:
            touched = session.info.setdefault(_TOUCHED, set())
        touched.add(ref)


def _on_commit(session):
    """The last chance to move stock inside the same transaction as the invoice,
    so the two succeed or fail together."""
    # Changes not yet flushed count too: a route that edits an invoice and
    # commits has not touched the database at this point, and the flush below
    # is the first the hook hears of them.
    if not (_TOUCHED in session.info or session.new or session.dirty or session.deleted):
        return
    session.flush()
    touched = session.info.pop(_TOUCHED, None)
    if not touched:
        return
    ids = set()
    for ref in touched:
        ids.add(ref if isinstance(ref, int) else getattr(ref, "id", None))
    reconcile(session, ids)


def _on_rollback(session, previous_transaction):
    session.info.pop(_TOUCHED, None)


_installed = False


def install():
    """Hook every session. Safe to call more than once."""
    global _installed
    if _installed:
        return
    event.listen(Session, "before_flush", _collect)
    event.listen(Session, "before_commit", _on_commit)
    event.listen(Session, "after_soft_rollback", _on_rollback)
    _installed = True
