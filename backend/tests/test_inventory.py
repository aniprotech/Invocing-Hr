"""Stock: what is on the shelf, why it is that number, and what a sale does.

The rules, in the order they matter:

  * The quantity on an item is a running total of a ledger and is never written
    on its own. After anything at all, it equals what the ledger says.
  * A sale takes stock out when its invoice is issued - not drafted, not paid -
    and puts it back if the invoice is voided, deleted or lowered. Doing the
    same thing twice does nothing the second time.
  * Switching tracking on declares a count, and the invoices already issued are
    not taken out of it again.
  * Selling more than is on hand is allowed, and shows as negative.
  * One business can never move another's stock.
"""
import uuid
from datetime import date, timedelta

import pytest

import inventory as inv_mod
import main
import models
from conftest import make_invoice

ISSUED = "Awaiting Payment"


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


# --- helpers ----------------------------------------------------------------------------

def new_item(tenant, code=None, **over):
    body = {"code": code or f"SKU-{uuid.uuid4().hex[:6]}", "name": "Widget", "sale_price": 10.0,
            "purchase_price": 4.0}
    body.update(over)
    res = tenant.post("/api/items", json=body)
    assert res.status_code == 200, res.text
    return res.json()


def tracked(tenant, quantity=10, cost=4.0, **over):
    """An item with a count to start from."""
    return new_item(tenant, track_inventory=True, quantity_on_hand=quantity, average_cost=cost, **over)


def lines(*pairs):
    """[(item, qty), ...] as invoice lines. An item of None is an unlinked line."""
    out = []
    for item, qty in pairs:
        out.append({"description": "Sold", "qty": qty, "price": 10.0, "tax_rate": "No Tax",
                    **({"item_id": item["id"]} if item else {})})
    return out


def invoice(tenant, *pairs, status="Draft", **over):
    over.setdefault("currency", "GBP")
    return make_invoice(tenant, line_items=lines(*pairs), status=status, **over)


def edit(tenant, inv, *pairs, status=None, **over):
    body = {"contact": inv.get("contact") or "Customer Ltd", "email": "customer@example.com",
            "issue_date": "2026-01-01", "due_date": "2026-01-31", "tax_type": "exclusive",
            "line_items": lines(*pairs), "status": status or inv["status"], "currency": "GBP"}
    body.update(over)
    res = tenant.put(f"/api/invoices/{inv['number']}", json=body)
    assert res.status_code == 200, res.text
    return res.json()


def item(tenant, item_id):
    for it in tenant.get("/api/inventory?view=all").json()["items"]:
        if it["id"] == item_id:
            return it
    raise AssertionError(f"item {item_id} not in the inventory")


def on_hand(tenant, it):
    return item(tenant, it["id"])["quantity_on_hand"]


def moves(tenant, it, limit=200):
    res = tenant.get(f"/api/inventory/{it['id']}/movements?limit={limit}")
    assert res.status_code == 200, res.text
    return res.json()["movements"]


def ledger_total(tenant, it):
    """What the ledger says is on the shelf: every row that moved stock."""
    return round(sum(m["quantity"] for m in moves(tenant, it, 1000) if m["affects_stock"]), 4)


def assert_book_agrees(tenant, *items):
    """The invariant. The number on the item is the ledger, whatever happened."""
    for it in items:
        assert on_hand(tenant, it) == ledger_total(tenant, it), \
            f"{it['code']}: the number is {on_hand(tenant, it)} but the ledger says {ledger_total(tenant, it)}"


def sale_rows(tenant, it):
    return [m for m in moves(tenant, it) if m["kind"] in ("sale", "sale_reversal")]


# =====================================================================================
# The arithmetic
# =====================================================================================

@pytest.mark.parametrize("raw,expected", [(5, 5.0), ("5", 5.0), (2.5, 2.5), ("0.0001", 0.0001),
                                          (1.23456, 1.2346), (1_000_000_000, 1_000_000_000.0)])
def test_a_quantity_is_a_number_to_four_places(raw, expected):
    assert inv_mod.clean_quantity(raw) == expected


@pytest.mark.parametrize("raw", [0, "0", -1, "-0.5", "abc", "", None, float("nan"), float("inf"),
                                 float("-inf"), 1_000_000_001, [], {}])
def test_a_quantity_that_makes_no_sense_is_refused(raw):
    with pytest.raises(inv_mod.StockError):
        inv_mod.clean_quantity(raw)


def test_a_count_may_be_zero_and_a_signed_amount_may_be_negative_when_allowed():
    assert inv_mod.clean_quantity(0, allow_zero=True) == 0.0
    assert inv_mod.clean_quantity(-3, allow_negative=True) == -3.0
    with pytest.raises(inv_mod.StockError):
        inv_mod.clean_quantity(-3, allow_zero=True)


@pytest.mark.parametrize("raw,expected", [(None, 0.0), ("", 0.0), (0, 0.0), ("4.5", 4.5), (1.23456, 1.2346)])
def test_a_cost_may_be_blank_or_nothing_but_not_negative(raw, expected):
    assert inv_mod.clean_cost(raw) == expected


@pytest.mark.parametrize("raw", [-1, "x", float("nan"), float("inf"), 1_000_000_001])
def test_a_bad_cost_is_refused(raw):
    with pytest.raises(inv_mod.StockError):
        inv_mod.clean_cost(raw)


@pytest.mark.parametrize("on_hand,avg,qty,cost,expected", [
    (10, 4.0, 10, 6.0, 5.0),            # a fair average of what was there and what came
    (10, 4.0, 5, 4.0, 4.0),             # same price, same average
    (0, 4.0, 5, 7.0, 7.0),              # an empty shelf takes the new price
    (-3, 4.0, 5, 7.0, 7.0),             # a negative shelf is no basis for an average
    (-5, 4.0, 5, 7.0, 7.0),             # received exactly what was owed
    (10, 4.0, 10, 0.0, 2.0),            # a gift halves it
    (1, 3.0, 2, 6.0, 5.0),
])
def test_the_average_cost_after_stock_arrives(on_hand, avg, qty, cost, expected):
    assert inv_mod.average_after_receipt(on_hand, avg, qty, cost) == expected


def test_a_negative_shelf_is_worth_nothing_not_less_than_nothing():
    assert inv_mod.stock_value(10, 4.0) == 40.0
    assert inv_mod.stock_value(0, 4.0) == 0.0
    assert inv_mod.stock_value(-5, 4.0) == 0.0
    assert inv_mod.stock_value(2.5, 3.33) == 8.33


@pytest.mark.parametrize("track,qty,reorder,status", [
    (False, 50, 10, "untracked"),
    (True, 50, 10, "ok"),
    (True, 11, 10, "ok"),
    (True, 10, 10, "low"),              # at the line is low
    (True, 3, 10, "low"),
    (True, 0, 10, "out"),
    (True, 0, 0, "out"),
    (True, -2, 10, "over"),
    (True, 3, 0, "ok"),                 # no reorder line set, so never "low"
    (True, None, 5, "out"),
])
def test_what_state_the_shelf_is_in(track, qty, reorder, status):
    assert inv_mod.stock_status(track, qty, reorder) == status


@pytest.mark.parametrize("status,issued", [("Draft", False), ("Void", False), ("Awaiting Payment", True),
                                           ("Sent", True), ("Paid", True), ("Partially Paid", True),
                                           ("Overdue", True), ("Credited", True), ("", True), (None, True)])
def test_which_invoices_are_real_enough_to_take_stock(status, issued):
    assert inv_mod.invoice_is_issued(status) is issued


# =====================================================================================
# Items and the ledger
# =====================================================================================

def test_a_new_tracked_item_starts_from_a_count_and_says_so(tenant):
    it = tracked(tenant, quantity=12, cost=3.5)
    assert it["track_inventory"] and it["quantity_on_hand"] == 12.0 and it["average_cost"] == 3.5
    assert it["stock_value"] == 42.0 and it["stock_status"] == "ok"
    rows = moves(tenant, it)
    assert [(m["kind"], m["quantity"], m["balance_after"]) for m in rows] == [("opening", 12.0, 12.0)]
    assert rows[0]["created_by"]
    assert_book_agrees(tenant, it)


def test_the_cost_defaults_to_the_purchase_price(tenant):
    it = new_item(tenant, track_inventory=True, quantity_on_hand=5, purchase_price=7.0)
    assert it["average_cost"] == 7.0


def test_an_untracked_item_keeps_its_quantity_and_has_no_ledger(tenant):
    it = new_item(tenant, quantity_on_hand=9)
    assert it["track_inventory"] is False and it["quantity_on_hand"] == 9.0 and it["stock_status"] == "untracked"
    assert it["stock_value"] == 0.0
    assert moves(tenant, it) == []


def test_a_tracked_item_with_a_bad_opening_count_is_refused(tenant):
    res = tenant.post("/api/items", json={"code": "BAD1", "track_inventory": True, "quantity_on_hand": "lots"})
    assert res.status_code == 400
    res = tenant.post("/api/items", json={"code": "BAD2", "track_inventory": True, "quantity_on_hand": -4})
    assert res.status_code == 400
    assert "BAD1" not in [i["code"] for i in tenant.get("/api/items").json()["items"]]
    assert "BAD2" not in [i["code"] for i in tenant.get("/api/items").json()["items"]]


def test_the_reorder_level_is_kept(tenant):
    it = tracked(tenant, quantity=5, reorder_level=8)
    assert it["reorder_level"] == 8.0 and it["stock_status"] == "low"
    res = tenant.put(f"/api/inventory/{it['id']}/reorder", json={"reorder_level": 2})
    assert res.status_code == 200 and res.json()["stock_status"] == "ok"
    assert tenant.put(f"/api/inventory/{it['id']}/reorder", json={"reorder_level": -1}).status_code == 400


def test_a_new_quantity_on_a_tracked_item_is_a_count_not_an_overwrite(tenant):
    it = tracked(tenant, quantity=10)
    res = tenant.put(f"/api/items/{it['id']}", json={"quantity_on_hand": 7})
    assert res.status_code == 200 and res.json()["quantity_on_hand"] == 7.0
    last = moves(tenant, it)[0]
    assert (last["kind"], last["quantity"], last["reason"], last["note"]) == ("adjustment", -3.0, "other", "Changed on the item")
    assert_book_agrees(tenant, it)


def test_putting_back_the_same_quantity_changes_nothing_but_the_rest_of_the_edit_still_applies(tenant):
    it = tracked(tenant, quantity=10)
    res = tenant.put(f"/api/items/{it['id']}", json={"quantity_on_hand": 10, "name": "Renamed"})
    assert res.status_code == 200 and res.json()["name"] == "Renamed"
    assert len(moves(tenant, it)) == 1


def test_a_bad_quantity_edit_is_refused_and_leaves_the_stock_alone(tenant):
    it = tracked(tenant, quantity=10)
    assert tenant.put(f"/api/items/{it['id']}", json={"quantity_on_hand": -1}).status_code == 400
    assert tenant.put(f"/api/items/{it['id']}", json={"quantity_on_hand": "x"}).status_code == 400
    assert on_hand(tenant, it) == 10.0 and len(moves(tenant, it)) == 1


def test_turning_tracking_on_from_the_item_is_a_count(tenant):
    it = new_item(tenant)
    res = tenant.put(f"/api/items/{it['id']}", json={"track_inventory": True, "quantity_on_hand": 20})
    assert res.status_code == 200 and res.json()["quantity_on_hand"] == 20.0
    assert moves(tenant, it)[0]["kind"] == "opening"
    assert_book_agrees(tenant, it)


def test_a_quantity_typed_before_tracking_was_never_stock_and_does_not_survive_it(tenant):
    """Items carried a quantity nobody maintained. Tracking starts from a count,
    and the old number must not leave the ledger and the shelf disagreeing."""
    it = new_item(tenant, quantity_on_hand=9)
    res = tenant.post(f"/api/inventory/{it['id']}/track", json={"quantity": 20})
    assert res.status_code == 200 and res.json()["quantity_on_hand"] == 20.0
    assert [(m["kind"], m["quantity"]) for m in moves(tenant, it)] == [("opening", 20.0)]
    assert_book_agrees(tenant, it)


def test_turning_tracking_off_keeps_the_history_and_the_last_number(tenant):
    it = tracked(tenant, quantity=10)
    res = tenant.put(f"/api/items/{it['id']}", json={"track_inventory": False})
    assert res.json()["track_inventory"] is False and res.json()["quantity_on_hand"] == 10.0
    assert len(moves(tenant, it)) == 1


def test_the_items_list_carries_the_stock_fields(tenant):
    it = tracked(tenant, quantity=4, reorder_level=5, cost=2.0)
    got = next(i for i in tenant.get("/api/items").json()["items"] if i["id"] == it["id"])
    assert (got["quantity_on_hand"], got["reorder_level"], got["average_cost"], got["stock_status"]) == (4.0, 5.0, 2.0, "low")


# --- receiving, counting, starting and stopping ----------------------------------------------

def test_receiving_stock_adds_it_and_averages_the_cost(tenant):
    it = tracked(tenant, quantity=10, cost=4.0)
    res = tenant.post(f"/api/inventory/{it['id']}/receive", json={"quantity": 10, "unit_cost": 6, "note": "Delivery 88"})
    assert res.status_code == 200, res.text
    got = res.json()
    assert got["quantity_on_hand"] == 20.0 and got["average_cost"] == 5.0 and got["stock_value"] == 100.0
    last = moves(tenant, it)[0]
    assert (last["kind"], last["quantity"], last["unit_cost"], last["balance_after"], last["note"]) == \
        ("received", 10.0, 6.0, 20.0, "Delivery 88")
    assert_book_agrees(tenant, it)


def test_receiving_into_an_empty_shelf_sets_the_cost(tenant):
    it = tracked(tenant, quantity=0, cost=4.0)
    got = tenant.post(f"/api/inventory/{it['id']}/receive", json={"quantity": 5, "unit_cost": 9}).json()
    assert got["average_cost"] == 9.0 and got["quantity_on_hand"] == 5.0


@pytest.mark.parametrize("body", [
    {"quantity": 0, "unit_cost": 1}, {"quantity": -2, "unit_cost": 1}, {"quantity": "x", "unit_cost": 1},
    {"unit_cost": 1}, {"quantity": 5, "unit_cost": -1}, {"quantity": 5, "unit_cost": "x"},
    {"quantity": 5, "unit_cost": 1, "date": "not a date"},
    {"quantity": 5, "unit_cost": 1, "date": (date.today() + timedelta(days=3)).isoformat()},
])
def test_receiving_nonsense_is_refused_and_changes_nothing(tenant, body):
    it = tracked(tenant, quantity=10)
    assert tenant.post(f"/api/inventory/{it['id']}/receive", json=body).status_code == 400
    assert on_hand(tenant, it) == 10.0 and len(moves(tenant, it)) == 1


def test_stock_can_be_received_on_an_earlier_day(tenant):
    it = tracked(tenant, quantity=1)
    day = (date.today() - timedelta(days=5)).isoformat()
    tenant.post(f"/api/inventory/{it['id']}/receive", json={"quantity": 2, "unit_cost": 1, "date": day})
    assert moves(tenant, it)[0]["moved_on"] == day


def test_an_untracked_item_cannot_be_received_or_counted(tenant):
    it = new_item(tenant)
    r1 = tenant.post(f"/api/inventory/{it['id']}/receive", json={"quantity": 5, "unit_cost": 1})
    r2 = tenant.post(f"/api/inventory/{it['id']}/count", json={"counted": 5, "reason": "stocktake"})
    assert r1.status_code == 400 and "Start tracking" in r1.json()["detail"]
    assert r2.status_code == 400


def test_a_count_records_the_difference_and_why(tenant):
    it = tracked(tenant, quantity=10)
    res = tenant.post(f"/api/inventory/{it['id']}/count", json={"counted": 8, "reason": "damaged", "note": "Water in the van"})
    assert res.status_code == 200 and res.json()["quantity_on_hand"] == 8.0
    last = moves(tenant, it)[0]
    assert (last["kind"], last["quantity"], last["reason"], last["note"], last["balance_after"]) == \
        ("adjustment", -2.0, "damaged", "Water in the van", 8.0)
    res = tenant.post(f"/api/inventory/{it['id']}/count", json={"counted": 11, "reason": "found"})
    assert res.json()["quantity_on_hand"] == 11.0 and moves(tenant, it)[0]["quantity"] == 3.0
    assert_book_agrees(tenant, it)


def test_a_count_of_zero_is_a_count(tenant):
    it = tracked(tenant, quantity=3)
    assert tenant.post(f"/api/inventory/{it['id']}/count", json={"counted": 0, "reason": "lost"}).json()["stock_status"] == "out"


@pytest.mark.parametrize("body", [
    {"counted": 10, "reason": "stocktake"},                   # exactly what the book says
    {"counted": 5},                                           # no reason
    {"counted": 5, "reason": "because"},                      # not a reason
    {"counted": -1, "reason": "lost"}, {"counted": "x", "reason": "lost"}, {"reason": "lost"},
])
def test_a_count_that_is_not_a_count_is_refused(tenant, body):
    it = tracked(tenant, quantity=10)
    assert tenant.post(f"/api/inventory/{it['id']}/count", json=body).status_code == 400
    assert len(moves(tenant, it)) == 1 and on_hand(tenant, it) == 10.0


def test_starting_to_track_declares_what_is_on_the_shelf(tenant):
    it = new_item(tenant)
    res = tenant.post(f"/api/inventory/{it['id']}/track", json={"quantity": 30, "unit_cost": 2.5, "reorder_level": 10})
    assert res.status_code == 200, res.text
    got = res.json()
    assert (got["track_inventory"], got["quantity_on_hand"], got["average_cost"], got["reorder_level"]) == (True, 30.0, 2.5, 10.0)
    assert [m["kind"] for m in moves(tenant, it)] == ["opening"]


def test_starting_to_track_twice_is_refused(tenant):
    it = tracked(tenant, quantity=3)
    assert tenant.post(f"/api/inventory/{it['id']}/track", json={"quantity": 9}).status_code == 409
    assert on_hand(tenant, it) == 3.0


def test_starting_to_track_with_a_bad_count_is_refused(tenant):
    it = new_item(tenant)
    assert tenant.post(f"/api/inventory/{it['id']}/track", json={"quantity": -5}).status_code == 400
    assert tenant.post(f"/api/inventory/{it['id']}/track", json={"quantity": "x"}).status_code == 400
    assert item(tenant, it["id"])["track_inventory"] is False and moves(tenant, it) == []


def test_stopping_keeps_everything_and_sales_stop_moving_it(tenant):
    it = tracked(tenant, quantity=10)
    assert tenant.post(f"/api/inventory/{it['id']}/stop").json()["track_inventory"] is False
    invoice(tenant, (it, 4), status=ISSUED)
    assert on_hand(tenant, it) == 10.0 and len(moves(tenant, it)) == 1


# --- the history ----------------------------------------------------------------------------

def test_the_history_is_newest_first_with_a_running_balance(tenant):
    it = tracked(tenant, quantity=10)
    tenant.post(f"/api/inventory/{it['id']}/receive", json={"quantity": 5, "unit_cost": 4})
    tenant.post(f"/api/inventory/{it['id']}/count", json={"counted": 12, "reason": "damaged"})
    got = tenant.get(f"/api/inventory/{it['id']}/movements").json()
    assert [(m["kind"], m["balance_after"]) for m in got["movements"]] == [("adjustment", 12.0), ("received", 15.0), ("opening", 10.0)]
    assert got["item"]["id"] == it["id"]


def test_the_history_can_be_limited(tenant):
    it = tracked(tenant, quantity=1)
    for _ in range(3):
        tenant.post(f"/api/inventory/{it['id']}/receive", json={"quantity": 1, "unit_cost": 1})
    assert len(moves(tenant, it, limit=2)) == 2


# =====================================================================================
# What a sale does
# =====================================================================================

def test_a_draft_takes_nothing(tenant):
    it = tracked(tenant, quantity=10)
    invoice(tenant, (it, 4))
    assert on_hand(tenant, it) == 10.0 and sale_rows(tenant, it) == []


def test_an_invoice_raised_as_issued_takes_stock_out_and_says_which(tenant):
    it = tracked(tenant, quantity=10, cost=4.0)
    inv = invoice(tenant, (it, 4), status=ISSUED)
    assert on_hand(tenant, it) == 6.0
    (row,) = sale_rows(tenant, it)
    assert (row["kind"], row["quantity"], row["invoice_number"], row["unit_cost"], row["balance_after"]) == \
        ("sale", -4.0, inv["number"], 4.0, 6.0)
    assert_book_agrees(tenant, it)


def test_issuing_a_draft_takes_the_stock_then(tenant):
    it = tracked(tenant, quantity=10)
    inv = invoice(tenant, (it, 3))
    assert on_hand(tenant, it) == 10.0
    edit(tenant, inv, (it, 3), status=ISSUED)
    assert on_hand(tenant, it) == 7.0
    assert_book_agrees(tenant, it)


def test_the_same_invoice_edited_without_change_takes_nothing_more(tenant):
    it = tracked(tenant, quantity=10)
    inv = invoice(tenant, (it, 3), status=ISSUED)
    for _ in range(3):
        edit(tenant, inv, (it, 3))
    assert on_hand(tenant, it) == 7.0 and len(sale_rows(tenant, it)) == 1


def test_raising_the_quantity_takes_the_difference(tenant):
    it = tracked(tenant, quantity=10)
    inv = invoice(tenant, (it, 3), status=ISSUED)
    edit(tenant, inv, (it, 5))
    assert on_hand(tenant, it) == 5.0
    assert [(m["kind"], m["quantity"]) for m in sale_rows(tenant, it)] == [("sale", -2.0), ("sale", -3.0)]
    assert_book_agrees(tenant, it)


def test_lowering_the_quantity_gives_the_difference_back(tenant):
    it = tracked(tenant, quantity=10)
    inv = invoice(tenant, (it, 5), status=ISSUED)
    edit(tenant, inv, (it, 2))
    assert on_hand(tenant, it) == 8.0
    assert sale_rows(tenant, it)[0]["kind"] == "sale_reversal" and sale_rows(tenant, it)[0]["quantity"] == 3.0
    assert_book_agrees(tenant, it)


def test_changing_the_item_on_a_line_moves_both_shelves(tenant):
    a, b = tracked(tenant, quantity=10), tracked(tenant, quantity=10)
    inv = invoice(tenant, (a, 4), status=ISSUED)
    edit(tenant, inv, (b, 4))
    assert on_hand(tenant, a) == 10.0 and on_hand(tenant, b) == 6.0
    assert_book_agrees(tenant, a, b)


def test_unlinking_a_line_gives_the_stock_back(tenant):
    it = tracked(tenant, quantity=10)
    inv = invoice(tenant, (it, 4), status=ISSUED)
    edit(tenant, inv, (None, 4))
    assert on_hand(tenant, it) == 10.0


def test_voiding_gives_the_stock_back_and_re_issuing_takes_it_again(tenant):
    it = tracked(tenant, quantity=10)
    inv = invoice(tenant, (it, 4), status=ISSUED)
    edit(tenant, inv, (it, 4), status="Void")
    assert on_hand(tenant, it) == 10.0
    edit(tenant, inv, (it, 4), status=ISSUED)
    assert on_hand(tenant, it) == 6.0
    assert_book_agrees(tenant, it)


def test_putting_an_issued_invoice_back_to_draft_gives_the_stock_back(tenant):
    it = tracked(tenant, quantity=10)
    inv = invoice(tenant, (it, 4), status=ISSUED)
    edit(tenant, inv, (it, 4), status="Draft")
    assert on_hand(tenant, it) == 10.0


def test_deleting_an_issued_invoice_gives_the_stock_back_and_says_why(tenant):
    it = tracked(tenant, quantity=10)
    inv = invoice(tenant, (it, 4), status=ISSUED)
    assert tenant.delete(f"/api/invoices/{inv['number']}").status_code == 200
    assert on_hand(tenant, it) == 10.0
    last = moves(tenant, it)[0]
    assert last["kind"] == "sale_reversal" and last["quantity"] == 4.0
    assert last["invoice_number"] == inv["number"] and "deleted" in last["note"]
    assert_book_agrees(tenant, it)


def test_deleting_a_draft_changes_nothing(tenant):
    it = tracked(tenant, quantity=10)
    inv = invoice(tenant, (it, 4))
    tenant.delete(f"/api/invoices/{inv['number']}")
    assert on_hand(tenant, it) == 10.0 and len(moves(tenant, it)) == 1


def test_being_paid_does_not_touch_the_stock(tenant):
    it = tracked(tenant, quantity=10)
    inv = invoice(tenant, (it, 4), status=ISSUED)
    assert tenant.post(f"/api/invoices/{inv['number']}/mark-paid").status_code == 200
    assert on_hand(tenant, it) == 6.0 and len(sale_rows(tenant, it)) == 1


def test_a_part_payment_does_not_touch_the_stock(tenant):
    it = tracked(tenant, quantity=10)
    inv = invoice(tenant, (it, 4), status=ISSUED)
    assert tenant.post(f"/api/invoices/{inv['number']}/payments", json={"amount": 5.0}).status_code == 200
    assert on_hand(tenant, it) == 6.0 and len(sale_rows(tenant, it)) == 1


def test_two_lines_of_one_item_are_one_movement(tenant):
    it = tracked(tenant, quantity=10)
    invoice(tenant, (it, 2), (it, 3), status=ISSUED)
    (row,) = sale_rows(tenant, it)
    assert row["quantity"] == -5.0 and on_hand(tenant, it) == 5.0


def test_quantities_may_be_fractions(tenant):
    it = tracked(tenant, quantity=10)
    invoice(tenant, (it, 2.5), status=ISSUED)
    assert on_hand(tenant, it) == 7.5


def test_several_items_on_one_invoice_each_move(tenant):
    a, b = tracked(tenant, quantity=10), tracked(tenant, quantity=5)
    invoice(tenant, (a, 1), (b, 2), status=ISSUED)
    assert (on_hand(tenant, a), on_hand(tenant, b)) == (9.0, 3.0)


def test_a_line_with_no_item_moves_nothing(tenant):
    it = tracked(tenant, quantity=10)
    invoice(tenant, (None, 4), status=ISSUED)
    assert on_hand(tenant, it) == 10.0


def test_an_untracked_item_on_a_line_moves_nothing_but_remembers_the_link(tenant):
    it = new_item(tenant)
    inv = invoice(tenant, (it, 4), status=ISSUED)
    assert item(tenant, it["id"])["quantity_on_hand"] == 0.0
    got = tenant.get(f"/api/invoices/{inv['number']}").json()
    assert got["line_items"][0]["item_id"] == it["id"]


def test_the_link_is_given_back_when_an_invoice_is_read(tenant):
    it = tracked(tenant, quantity=10)
    inv = invoice(tenant, (it, 4), (None, 1))
    got = tenant.get(f"/api/invoices/{inv['number']}").json()
    assert [l["item_id"] for l in got["line_items"]] == [it["id"], None]


# --- selling what is not there -----------------------------------------------------------------------

def test_selling_everything_leaves_none(tenant):
    it = tracked(tenant, quantity=4)
    invoice(tenant, (it, 4), status=ISSUED)
    assert item(tenant, it["id"])["stock_status"] == "out"


def test_selling_more_than_is_on_hand_is_allowed_and_shows_negative(tenant):
    it = tracked(tenant, quantity=4)
    res = make_invoice(tenant, line_items=lines((it, 7)), status=ISSUED, currency="GBP")
    assert res["status"] == ISSUED
    got = item(tenant, it["id"])
    assert got["quantity_on_hand"] == -3.0 and got["stock_status"] == "over" and got["stock_value"] == 0.0
    assert_book_agrees(tenant, it)


def test_receiving_what_was_owed_brings_it_back_to_zero(tenant):
    it = tracked(tenant, quantity=4)
    invoice(tenant, (it, 7), status=ISSUED)
    tenant.post(f"/api/inventory/{it['id']}/receive", json={"quantity": 3, "unit_cost": 5})
    assert item(tenant, it["id"])["stock_status"] == "out"


def test_low_stock_is_flagged_by_the_reorder_level(tenant):
    it = tracked(tenant, quantity=10, reorder_level=4)
    invoice(tenant, (it, 6), status=ISSUED)
    assert item(tenant, it["id"])["stock_status"] == "low"


# --- switching tracking on and off around real invoices ---------------------------------------------

def test_invoices_issued_before_tracking_started_are_not_taken_out_of_the_count(tenant):
    it = new_item(tenant)
    old = invoice(tenant, (it, 5), status=ISSUED)
    tenant.post(f"/api/inventory/{it['id']}/track", json={"quantity": 10})
    assert on_hand(tenant, it) == 10.0
    base = [m for m in moves(tenant, it) if m["kind"] == "baseline"]
    assert len(base) == 1 and base[0]["quantity"] == -5.0 and base[0]["affects_stock"] is False
    assert base[0]["invoice_number"] == old["number"]
    # Touching the old invoice - a payment, an edit that changes nothing - takes nothing.
    tenant.post(f"/api/invoices/{old['number']}/mark-paid")
    assert on_hand(tenant, it) == 10.0
    assert_book_agrees(tenant, it)


def test_an_old_invoice_edited_after_tracking_started_moves_only_the_difference(tenant):
    it = new_item(tenant)
    old = invoice(tenant, (it, 5), status=ISSUED)
    tenant.post(f"/api/inventory/{it['id']}/track", json={"quantity": 10})
    edit(tenant, old, (it, 7))
    assert on_hand(tenant, it) == 8.0
    assert_book_agrees(tenant, it)


def test_a_draft_that_predates_tracking_takes_stock_when_it_is_issued(tenant):
    it = new_item(tenant)
    draft = invoice(tenant, (it, 3))
    tenant.post(f"/api/inventory/{it['id']}/track", json={"quantity": 10})
    assert on_hand(tenant, it) == 10.0
    edit(tenant, draft, (it, 3), status=ISSUED)
    assert on_hand(tenant, it) == 7.0


def test_invoices_issued_while_tracking_was_off_are_covered_when_it_comes_back_on(tenant):
    it = tracked(tenant, quantity=10)
    tenant.post(f"/api/inventory/{it['id']}/stop")
    during = invoice(tenant, (it, 4), status=ISSUED)
    assert on_hand(tenant, it) == 10.0
    tenant.post(f"/api/inventory/{it['id']}/track", json={"quantity": 6})
    assert on_hand(tenant, it) == 6.0
    tenant.post(f"/api/invoices/{during['number']}/mark-paid")
    assert on_hand(tenant, it) == 6.0
    assert_book_agrees(tenant, it)


def test_an_invoice_voided_while_tracking_was_off_does_not_give_stock_back_afterwards(tenant):
    it = tracked(tenant, quantity=10)
    inv = invoice(tenant, (it, 4), status=ISSUED)
    assert on_hand(tenant, it) == 6.0
    tenant.post(f"/api/inventory/{it['id']}/stop")
    edit(tenant, inv, (it, 4), status="Void")
    tenant.post(f"/api/inventory/{it['id']}/track", json={"quantity": 6})
    assert on_hand(tenant, it) == 6.0
    edit(tenant, inv, (it, 4), status="Void")
    assert on_hand(tenant, it) == 6.0
    assert_book_agrees(tenant, it)


def test_a_baseline_also_covers_an_invoice_deleted_while_tracking_was_off(tenant):
    it = tracked(tenant, quantity=10)
    inv = invoice(tenant, (it, 4), status=ISSUED)
    tenant.post(f"/api/inventory/{it['id']}/stop")
    tenant.delete(f"/api/invoices/{inv['number']}")           # gone, but the ledger still says 4 went out for it
    tenant.post(f"/api/inventory/{it['id']}/track", json={"quantity": 6})
    base = [m for m in moves(tenant, it) if m["kind"] == "baseline"]
    assert len(base) == 1 and base[0]["quantity"] == 4.0 and base[0]["affects_stock"] is False
    assert base[0]["invoice_number"] == inv["number"]
    assert on_hand(tenant, it) == 6.0
    assert_book_agrees(tenant, it)


def test_a_line_changed_on_its_own_moves_stock_even_though_the_invoice_itself_was_not_touched(tenant):
    it = tracked(tenant, quantity=10)
    invoice(tenant, (it, 3), status=ISSUED)
    with main.SessionLocal() as db:
        line = db.query(models.DBLineItem).filter(models.DBLineItem.item_id == it["id"]).first()
        line.qty = 5
        db.commit()
    assert on_hand(tenant, it) == 5.0
    assert_book_agrees(tenant, it)


def test_a_line_that_ends_up_naming_another_businesss_item_moves_nothing_of_theirs(tenant, account, client):
    """The API refuses such a link. This is the guard behind it, for a link that
    got there some other way."""
    mine = tracked(tenant, quantity=10)
    inv = invoice(tenant, (mine, 1), status=ISSUED)
    me_id = tenant.get("/api/client/me").json()["id"]
    second_business(client, f"guard-{uuid.uuid4().hex[:8]}@example.com")
    theirs = tracked(client, quantity=10)
    with main.SessionLocal() as db:
        number = inv["number"]
        row = db.query(models.DBInvoice).filter(models.DBInvoice.number == number, models.DBInvoice.client_id == me_id).first()
        line = db.query(models.DBLineItem).filter(models.DBLineItem.invoice_id == row.id).first()
        line.item_id = theirs["id"]
        db.commit()
    assert on_hand(client, theirs) == 10.0 and len(moves(client, theirs)) == 1


# --- quotes ----------------------------------------------------------------------------------------

def make_quote(tenant, *pairs):
    body = {"contact": "Customer Ltd", "email": "customer@example.com", "issue_date": "2026-01-01",
            "expiry_date": "2026-12-31", "tax_type": "exclusive", "currency": "GBP", "line_items": lines(*pairs)}
    res = tenant.post("/api/quotes", json=body)
    assert res.status_code == 200, res.text
    return res.json()


def test_a_quote_takes_no_stock(tenant):
    it = tracked(tenant, quantity=10)
    make_quote(tenant, (it, 4))
    assert on_hand(tenant, it) == 10.0


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(main, "send_email_background",
                        lambda to, subject, body, from_email, html_body=None, *a, **kw: (sent.append(subject), (True, ""))[1])
    return sent


def test_a_quote_remembers_its_items(tenant):
    it = tracked(tenant, quantity=10)
    q = make_quote(tenant, (it, 4), (None, 1))
    got = tenant.get(f"/api/quotes/{q['number']}").json()
    assert [l["item_id"] for l in got["line_items"]] == [it["id"], None]


def test_converting_a_quote_by_hand_makes_a_draft_that_takes_nothing_until_it_is_issued(tenant):
    it = tracked(tenant, quantity=10)
    q = make_quote(tenant, (it, 4))
    res = tenant.post(f"/api/quotes/{q['number']}/convert")
    assert res.status_code == 200, res.text
    got = tenant.get(f"/api/invoices/{res.json()['invoice_number']}").json()
    assert got["status"] == "Draft" and got["line_items"][0]["item_id"] == it["id"]
    assert on_hand(tenant, it) == 10.0
    edit(tenant, got, (it, 4), status=ISSUED)
    assert on_hand(tenant, it) == 6.0
    assert_book_agrees(tenant, it)


def test_a_customer_accepting_a_quote_online_takes_the_stock(tenant, outbox):
    it = tracked(tenant, quantity=10)
    q = make_quote(tenant, (it, 4))
    tenant.post(f"/api/quotes/{q['number']}/status", json={"status": "Sent"})
    res = tenant.post(f"/api/public/quotes/{q['tracking_id']}/accept", json={"name": "Dana Buyer"})
    assert res.status_code == 200, res.text
    number = res.json()["quote"]["invoice"]["number"]
    assert res.json()["quote"]["invoice"]["status"] == ISSUED
    assert tenant.get(f"/api/invoices/{number}").json()["line_items"][0]["item_id"] == it["id"]
    assert on_hand(tenant, it) == 6.0
    assert sale_rows(tenant, it)[0]["invoice_number"] == number
    assert_book_agrees(tenant, it)


def test_a_quote_cannot_name_another_businesses_item(tenant, account, client):
    mine = tracked(tenant, quantity=1)
    second_business(client, f"q-{uuid.uuid4().hex[:8]}@example.com")
    res = client.post("/api/quotes", json={"contact": "X", "email": "x@example.com", "issue_date": "2026-01-01",
                                           "expiry_date": "2026-12-31", "tax_type": "exclusive", "currency": "GBP",
                                           "line_items": lines((mine, 1))})
    assert res.status_code == 400 and "not in your items" in res.json()["detail"]


# --- one business and another ---------------------------------------------------------------------------

def second_business(client, email):
    client.post("/api/client/logout")
    assert client.post("/api/client/register", json={"email": email, "password": "Passw0rdTest", "company_name": "Other Ltd"}).status_code == 200
    assert client.post("/api/client/login", json={"email": email, "password": "Passw0rdTest"}).status_code == 200


def test_a_line_cannot_name_another_businesses_item(tenant, account, client):
    mine = tracked(tenant, quantity=10)
    second_business(client, f"other-{uuid.uuid4().hex[:8]}@example.com")
    theirs = tracked(client, quantity=10)
    # The second business tries to sell the first one's stock.
    res = client.post("/api/invoices", json={"contact": "X", "email": "x@example.com", "issue_date": "2026-01-01",
                                            "due_date": "2026-01-31", "tax_type": "exclusive", "currency": "GBP",
                                            "status": ISSUED, "line_items": lines((mine, 5))})
    assert res.status_code == 400 and "not in your items" in res.json()["detail"]
    assert on_hand(client, theirs) == 10.0
    client.post("/api/client/logout")
    client.post("/api/client/login", json={"email": account["email"], "password": account["password"]})
    assert on_hand(client, mine) == 10.0


def test_one_business_cannot_see_or_move_anothers_stock(tenant, account, client):
    mine = tracked(tenant, quantity=10)
    second_business(client, f"other-{uuid.uuid4().hex[:8]}@example.com")
    for method, path, body in (
        ("post", f"/api/inventory/{mine['id']}/receive", {"quantity": 1, "unit_cost": 1}),
        ("post", f"/api/inventory/{mine['id']}/count", {"counted": 1, "reason": "lost"}),
        ("post", f"/api/inventory/{mine['id']}/track", {"quantity": 1}),
        ("post", f"/api/inventory/{mine['id']}/stop", {}),
        ("put", f"/api/inventory/{mine['id']}/reorder", {"reorder_level": 1}),
        ("get", f"/api/inventory/{mine['id']}/movements", None),
    ):
        res = getattr(client, method)(path, **({"json": body} if body is not None else {}))
        assert res.status_code == 404, (path, res.status_code)
    assert client.get("/api/inventory?view=all").json()["items"] == []
    client.post("/api/client/logout")
    client.post("/api/client/login", json={"email": account["email"], "password": account["password"]})
    assert on_hand(client, mine) == 10.0 and len(moves(client, mine)) == 1


def test_a_line_naming_an_item_that_does_not_exist_is_refused_whole(tenant):
    it = tracked(tenant, quantity=10)
    body = {"contact": "X", "email": "x@example.com", "issue_date": "2026-01-01", "due_date": "2026-01-31",
            "tax_type": "exclusive", "currency": "GBP", "status": ISSUED,
            "line_items": lines((it, 1)) + [{"description": "Ghost", "qty": 1, "price": 1.0, "tax_rate": "No Tax", "item_id": 99999999}]}
    assert tenant.post("/api/invoices", json=body).status_code == 400
    assert on_hand(tenant, it) == 10.0 and sale_rows(tenant, it) == []


def test_an_edit_naming_an_item_that_does_not_exist_changes_nothing(tenant):
    it = tracked(tenant, quantity=10)
    inv = invoice(tenant, (it, 2), status=ISSUED)
    bad = lines((it, 5)) + [{"description": "Ghost", "qty": 1, "price": 1.0, "tax_rate": "No Tax", "item_id": 99999999}]
    res = tenant.put(f"/api/invoices/{inv['number']}", json={
        "contact": "Customer Ltd", "email": "customer@example.com", "issue_date": "2026-01-01", "due_date": "2026-01-31",
        "tax_type": "exclusive", "line_items": bad, "status": ISSUED, "currency": "GBP"})
    assert res.status_code == 400
    assert on_hand(tenant, it) == 8.0


def test_a_retired_item_still_counts_on_the_invoices_that_already_name_it(tenant):
    it = tracked(tenant, quantity=10)
    inv = invoice(tenant, (it, 3), status=ISSUED)
    assert tenant.delete(f"/api/items/{it['id']}").status_code == 200
    tenant.delete(f"/api/invoices/{inv['number']}")
    got = tenant.get(f"/api/inventory/{it['id']}/movements").json()
    assert got["item"]["quantity_on_hand"] == 10.0


# =====================================================================================
# The Inventory screen's data
# =====================================================================================

def overview(tenant, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    res = tenant.get("/api/inventory" + ("?" + query if query else ""))
    assert res.status_code == 200, res.text
    return res.json()


def test_the_overview_totals_cover_everything_whatever_is_shown(tenant):
    ok = tracked(tenant, code="OK1", quantity=10, cost=2.0, reorder_level=3)
    low = tracked(tenant, code="LOW1", quantity=2, cost=5.0, reorder_level=3)
    out = tracked(tenant, code="OUT1", quantity=0, cost=1.0)
    over = tracked(tenant, code="OVER1", quantity=1, cost=9.0)
    invoice(tenant, (over, 4), status=ISSUED)
    plain = new_item(tenant, code="PLAIN1")
    got = overview(tenant, view="out")
    assert sorted(i["code"] for i in got["items"]) == ["OUT1", "OVER1"]
    t = got["totals"]
    assert (t["tracked"], t["untracked"], t["low"], t["out"], t["over"]) == (4, 1, 1, 1, 1)
    assert t["stock_value"] == 30.0               # 10*2 + 2*5; nothing for empty or negative shelves


def test_the_views(tenant):
    tracked(tenant, code="A1", quantity=10)
    tracked(tenant, code="B1", quantity=1, reorder_level=5)
    new_item(tenant, code="C1")
    codes = lambda v: sorted(i["code"] for i in overview(tenant, view=v)["items"])           # noqa: E731
    assert codes("tracked") == ["A1", "B1"] and codes("all") == ["A1", "B1", "C1"]
    assert codes("untracked") == ["C1"] and codes("low") == ["B1"] and codes("out") == []
    assert overview(tenant)["view"] == "tracked", "tracked is the default"
    assert overview(tenant, view="nonsense")["view"] == "tracked"


def test_the_low_tab_includes_what_has_run_out_or_gone_negative_since_those_need_ordering_most(tenant):
    tracked(tenant, code="L1", quantity=2, reorder_level=5)
    tracked(tenant, code="O1", quantity=0)
    gone = tracked(tenant, code="N1", quantity=1)
    invoice(tenant, (gone, 3), status=ISSUED)
    tracked(tenant, code="F1", quantity=50, reorder_level=5)
    assert sorted(i["code"] for i in overview(tenant, view="low")["items"]) == ["L1", "N1", "O1"]


def test_search_matches_code_or_name_and_leaves_the_totals_alone(tenant):
    tracked(tenant, code="ALPHA", name="Blue gadget", quantity=1)
    tracked(tenant, code="BETA", name="Red thing", quantity=1)
    got = overview(tenant, view="all", q="gadget")
    assert [i["code"] for i in got["items"]] == ["ALPHA"] and got["totals"]["tracked"] == 2
    assert [i["code"] for i in overview(tenant, view="all", q="beta")["items"]] == ["BETA"]


def test_retired_items_are_not_on_the_shelf(tenant):
    it = tracked(tenant, code="GONE", quantity=5)
    tenant.delete(f"/api/items/{it['id']}")
    assert "GONE" not in [i["code"] for i in overview(tenant, view="all")["items"]]
    assert overview(tenant)["totals"]["tracked"] == 0


def test_the_overview_is_capped(tenant):
    for n in range(5):
        new_item(tenant, code=f"CAP{n}")
    got = overview(tenant, view="all", limit=2)
    assert len(got["items"]) == 2 and got["shown"] == 5


def test_the_valuation_export(tenant):
    tracked(tenant, code="V1", name="Fine wine", quantity=3, cost=10.0, reorder_level=2)
    tracked(tenant, code="V2", name="=HYPERLINK(\"http://evil\")", quantity=1, cost=1.0)
    new_item(tenant, code="UNTRACKED")
    res = tenant.get("/api/inventory/export.csv")
    assert res.status_code == 200 and res.headers["content-type"].startswith("text/csv")
    text = res.text
    assert text.splitlines()[0] == "Code,Name,On hand,Average cost,Value,Reorder level,Status"
    assert "V1,Fine wine,3,10.00,30.00,2,ok" in text
    assert "UNTRACKED" not in text
    assert "'=HYPERLINK" in text and ",=HYPERLINK" not in text, "a name must never reach a spreadsheet as a formula"


def stock_line(tenant):
    items = tenant.get("/api/dashboard/attention").json()["items"]
    return next((i for i in items if i["key"] == "stock_low"), None)


def test_the_dashboard_says_nothing_about_stock_to_a_business_that_keeps_none(tenant):
    new_item(tenant)
    assert stock_line(tenant) is None


def test_the_dashboard_counts_what_is_low_out_or_oversold_and_links_to_it(tenant):
    tracked(tenant, quantity=10, reorder_level=3)                    # fine
    tracked(tenant, quantity=2, reorder_level=3)                     # low
    tracked(tenant, quantity=0)                                      # out
    sold = tracked(tenant, quantity=1)
    invoice(tenant, (sold, 4), status=ISSUED)                        # oversold
    line = stock_line(tenant)
    assert line["count"] == 3 and line["label"] == "Items to reorder"
    assert (line["view"], line["filter"], line["tone"]) == ("inventory-view", "low", "warn")


def test_a_retired_or_untracked_item_is_not_something_to_reorder(tenant):
    gone = tracked(tenant, quantity=0)
    tenant.delete(f"/api/items/{gone['id']}")
    stopped = tracked(tenant, quantity=0)
    tenant.post(f"/api/inventory/{stopped['id']}/stop")
    assert stock_line(tenant) is None


def test_one_business_is_not_told_about_anothers_shelves(tenant, account, client):
    tracked(tenant, quantity=0)
    second_business(client, f"dash-{uuid.uuid4().hex[:8]}@example.com")
    assert stock_line(client) is None


def test_the_inventory_belongs_to_the_invoicing_plan():
    assert main.module_for_path("/api/inventory") == "invoicing"
    assert main.module_for_path("/api/inventory/3/receive") == "invoicing"


# =====================================================================================
# Taken together
# =====================================================================================

def test_after_a_busy_week_the_book_still_agrees_with_every_invoice(tenant):
    a, b = tracked(tenant, quantity=50, cost=3.0), tracked(tenant, quantity=20, cost=8.0)
    i1 = invoice(tenant, (a, 5), (b, 2), status=ISSUED)
    i2 = invoice(tenant, (a, 10), status=ISSUED)
    tenant.post(f"/api/inventory/{a['id']}/receive", json={"quantity": 20, "unit_cost": 4})
    edit(tenant, i1, (a, 7), (b, 1))
    edit(tenant, i2, (a, 10), status="Void")
    tenant.delete(f"/api/invoices/{i1['number']}")
    i3 = invoice(tenant, (a, 4))
    edit(tenant, i3, (a, 4), status=ISSUED)
    tenant.post(f"/api/inventory/{b['id']}/count", json={"counted": 19, "reason": "stocktake"})
    assert_book_agrees(tenant, a, b)
    assert on_hand(tenant, a) == 50 + 20 - 4 and on_hand(tenant, b) == 19.0


def test_every_invoice_has_exactly_what_it_sold_out_of_the_ledger(tenant):
    it = tracked(tenant, quantity=100)
    made = [invoice(tenant, (it, q), status=ISSUED) for q in (1, 2, 3)]
    edit(tenant, made[1], (it, 9))
    totals = {}
    for m in moves(tenant, it, 1000):
        if m["kind"] in ("sale", "sale_reversal"):
            totals[m["invoice_number"]] = totals.get(m["invoice_number"], 0.0) + m["quantity"]
    assert totals == {made[0]["number"]: -1.0, made[1]["number"]: -9.0, made[2]["number"]: -3.0}
    assert on_hand(tenant, it) == 100 - 13


def test_a_failed_request_leaves_the_stock_exactly_as_it_was(tenant):
    it = tracked(tenant, quantity=10)
    bad = {"contact": "X", "email": "x@example.com", "issue_date": "2026-01-31", "due_date": "2026-01-01",
           "tax_type": "exclusive", "currency": "GBP", "status": ISSUED, "line_items": lines((it, 4))}
    assert tenant.post("/api/invoices", json=bad).status_code == 400
    assert on_hand(tenant, it) == 10.0 and sale_rows(tenant, it) == []
