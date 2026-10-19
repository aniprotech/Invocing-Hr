"""Stock moved by documents other than a sale.

Stock only ever moved on a sales invoice or by hand. A bill for goods did not
put them on the shelf, goods a customer sent back on a credit note did not
come back, goods returned to a supplier did not leave, and an invoice raised
from a recurring template lost the item it sold. These check each, and that
none of them can be done twice by accident.
"""
import uuid
from datetime import date, timedelta

import pytest

import main
import models
from conftest import make_invoice


@pytest.fixture(autouse=True)
def _reset():
    main.rate_limiter._hits.clear()
    yield


def d(n):
    return (date.today() + timedelta(days=n)).isoformat()


def tracked(tenant, quantity=10, cost=4.0):
    r = tenant.post("/api/items", json={"code": f"SKU-{uuid.uuid4().hex[:6]}", "name": "Widget", "sale_price": 10.0,
                                        "purchase_price": 4.0, "track_inventory": True, "quantity_on_hand": quantity,
                                        "average_cost": cost})
    assert r.status_code == 200, r.text
    return r.json()


def on_hand(tenant, item):
    return next(i for i in tenant.get("/api/inventory?view=all").json()["items"] if i["id"] == item["id"])


def moves(tenant, item):
    return tenant.get(f"/api/inventory/{item['id']}/movements").json()["movements"]


def bill(tenant, **kw):
    body = {"vendor_name": "Acme Supplies", "amount": 100.0, "issue_date": d(-2), "due_date": d(20)}
    body.update(kw)
    r = tenant.post("/api/bills", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def sold(tenant, item, qty):
    return make_invoice(tenant, line_items=[{"description": "Sold", "qty": qty, "price": 10.0, "tax_rate": "No Tax", "item_id": item["id"]}],
                        status="Awaiting Payment", currency="GBP")


# --- a bill puts goods on the shelf ---------------------------------------------------------
def test_a_bill_receives_its_goods_into_stock_at_their_cost(tenant):
    it = tracked(tenant, 10, 4.0)
    b = bill(tenant)
    r = tenant.post(f"/api/bills/{b['id']}/receive", json={"lines": [{"item_id": it["id"], "quantity": 10, "unit_cost": 6.0}]})
    assert r.status_code == 200, r.text
    got = on_hand(tenant, it)
    assert got["quantity_on_hand"] == 20 and got["average_cost"] == 5.0
    mv = moves(tenant, it)[0]
    assert mv["kind"] == "received" and mv["document"] == f"bill:{b['id']}" and b["number"] in mv["note"]
    assert mv["moved_on"] == d(-2)
    rows = tenant.get(f"/api/bills/{b['id']}/stock").json()["received"]
    assert rows == [{"item_id": it["id"], "code": it["code"], "quantity": 10, "unit_cost": 6.0, "moved_on": d(-2)}]


def test_the_same_bill_is_not_received_twice_unless_asked(tenant):
    it = tracked(tenant, 0)
    b = bill(tenant)
    body = {"lines": [{"item_id": it["id"], "quantity": 5, "unit_cost": 4}]}
    assert tenant.post(f"/api/bills/{b['id']}/receive", json=body).status_code == 200
    r = tenant.post(f"/api/bills/{b['id']}/receive", json=body)
    assert r.status_code == 409 and "already been received" in r.json()["detail"]
    assert on_hand(tenant, it)["quantity_on_hand"] == 5
    assert tenant.post(f"/api/bills/{b['id']}/receive", json={**body, "again": True}).status_code == 200
    assert on_hand(tenant, it)["quantity_on_hand"] == 10


def test_a_draft_or_void_bill_receives_nothing(tenant):
    it = tracked(tenant, 0)
    draft = bill(tenant, draft=True)
    r = tenant.post(f"/api/bills/{draft['id']}/receive", json={"lines": [{"item_id": it["id"], "quantity": 1}]})
    assert r.status_code == 400 and "draft" in r.json()["detail"]
    b = bill(tenant)
    assert tenant.post(f"/api/bills/{b['id']}/void").status_code == 200
    assert tenant.post(f"/api/bills/{b['id']}/receive", json={"lines": [{"item_id": it["id"], "quantity": 1}]}).status_code == 400
    assert on_hand(tenant, it)["quantity_on_hand"] == 0


@pytest.mark.parametrize("lines,says", [
    (None, "Say which items"),
    ([], "Say which items"),
    ([{"quantity": 1}], "names an item"),
    ([{"item_id": "x", "quantity": 1}], "names an item"),
    (["oops"], "names an item"),
    ([{"item_id": 0, "quantity": 0}], "Item not found"),
])
def test_what_a_receipt_cannot_be_is_refused(tenant, lines, says):
    b = bill(tenant)
    r = tenant.post(f"/api/bills/{b['id']}/receive", json={"lines": lines})
    assert r.status_code in (400, 404) and says in r.json()["detail"], r.text


def test_a_receipt_needs_a_real_quantity_each_item_once_and_a_tracked_item(tenant):
    it = tracked(tenant, 0)
    b = bill(tenant)
    for q in (0, -1, "lots"):
        assert tenant.post(f"/api/bills/{b['id']}/receive", json={"lines": [{"item_id": it["id"], "quantity": q}]}).status_code == 400
    twice = [{"item_id": it["id"], "quantity": 1}, {"item_id": it["id"], "quantity": 2}]
    assert "once" in tenant.post(f"/api/bills/{b['id']}/receive", json={"lines": twice}).json()["detail"]
    plain = tenant.post("/api/items", json={"code": f"P-{uuid.uuid4().hex[:5]}", "name": "Service", "sale_price": 5}).json()
    r = tenant.post(f"/api/bills/{b['id']}/receive", json={"lines": [{"item_id": plain["id"], "quantity": 1}]})
    assert r.status_code == 400 and "not tracked" in r.json()["detail"]
    assert on_hand(tenant, it)["quantity_on_hand"] == 0


def test_one_bad_line_receives_nothing(tenant):
    a, b_ = tracked(tenant, 0), tracked(tenant, 0)
    b = bill(tenant)
    r = tenant.post(f"/api/bills/{b['id']}/receive", json={"lines": [{"item_id": a["id"], "quantity": 3}, {"item_id": b_["id"], "quantity": 1, "unit_cost": -2}]})
    assert r.status_code == 400
    assert on_hand(tenant, a)["quantity_on_hand"] == 0 and moves(tenant, a)[0]["kind"] == "opening"


def test_a_future_receipt_date_is_brought_back_to_today(tenant):
    it = tracked(tenant, 0)
    b = bill(tenant)
    tenant.post(f"/api/bills/{b['id']}/receive", json={"lines": [{"item_id": it["id"], "quantity": 1}], "date": d(30)})
    assert moves(tenant, it)[0]["moved_on"] == date.today().isoformat()


# --- a customer's credit note brings goods back ------------------------------------------------
def test_goods_returned_on_a_credit_note_come_back_at_their_average_cost(tenant):
    it = tracked(tenant, 10, 4.0)
    inv = sold(tenant, it, 3)
    assert on_hand(tenant, it)["quantity_on_hand"] == 7
    cn = tenant.post("/api/credit-notes", json={"invoice_number": inv["number"]}).json()
    r = tenant.post(f"/api/credit-notes/{cn['number']}/restock", json={"lines": [{"item_id": it["id"], "quantity": 2}]})
    assert r.status_code == 200, r.text
    got = on_hand(tenant, it)
    assert got["quantity_on_hand"] == 9 and got["average_cost"] == 4.0
    mv = moves(tenant, it)[0]
    assert mv["kind"] == "return_in" and mv["document"] == f"credit_note:{cn['number']}" and mv["unit_cost"] == 4.0


def test_no_more_comes_back_than_the_invoice_sold(tenant):
    it = tracked(tenant, 10)
    inv = sold(tenant, it, 3)
    cn = tenant.post("/api/credit-notes", json={"invoice_number": inv["number"]}).json()
    url = f"/api/credit-notes/{cn['number']}/restock"
    r = tenant.post(url, json={"lines": [{"item_id": it["id"], "quantity": 4}]})
    assert r.status_code == 400 and "Only 3" in r.json()["detail"]
    assert tenant.post(url, json={"lines": [{"item_id": it["id"], "quantity": 2}]}).status_code == 200
    r = tenant.post(url, json={"lines": [{"item_id": it["id"], "quantity": 2}]})
    assert r.status_code == 400 and "Only 1" in r.json()["detail"]
    assert tenant.post(url, json={"lines": [{"item_id": it["id"], "quantity": 1}]}).status_code == 200
    assert on_hand(tenant, it)["quantity_on_hand"] == 10


def test_an_item_not_on_the_invoice_cannot_come_back_on_its_credit_note(tenant):
    it, other = tracked(tenant, 10), tracked(tenant, 10)
    inv = sold(tenant, it, 1)
    cn = tenant.post("/api/credit-notes", json={"invoice_number": inv["number"]}).json()
    r = tenant.post(f"/api/credit-notes/{cn['number']}/restock", json={"lines": [{"item_id": other["id"], "quantity": 1}]})
    assert r.status_code == 400 and "not on the invoice" in r.json()["detail"]


def test_a_missing_or_void_credit_note_restocks_nothing(tenant):
    it = tracked(tenant, 10)
    assert tenant.post("/api/credit-notes/CN-NOPE/restock", json={"lines": [{"item_id": it["id"], "quantity": 1}]}).status_code == 404
    inv = sold(tenant, it, 1)
    cn = tenant.post("/api/credit-notes", json={"invoice_number": inv["number"]}).json()
    with main.SessionLocal() as db:
        db.query(models.DBCreditNote).filter(models.DBCreditNote.id == cn["id"]).update({"status": "Void"})
        db.commit()
    r = tenant.post(f"/api/credit-notes/{cn['number']}/restock", json={"lines": [{"item_id": it["id"], "quantity": 1}]})
    assert r.status_code == 400 and "void" in r.json()["detail"]


# --- goods sent back to a supplier -----------------------------------------------------------
def test_goods_sent_back_to_a_supplier_leave_stock(tenant):
    it = tracked(tenant, 10, 4.0)
    s = tenant.post("/api/suppliers", json={"name": f"Sup {uuid.uuid4().hex[:4]}"}).json()
    cr = tenant.post("/api/supplier-credits", json={"supplier_id": s["id"], "amount": 8, "issue_date": d(-1)}).json()
    url = f"/api/supplier-credits/{cr['id']}/return-stock"
    r = tenant.post(url, json={"lines": [{"item_id": it["id"], "quantity": 2}]})
    assert r.status_code == 200, r.text
    assert on_hand(tenant, it)["quantity_on_hand"] == 8
    mv = moves(tenant, it)[0]
    assert mv["kind"] == "return_out" and mv["quantity"] == -2 and mv["document"] == f"supplier_credit:{cr['id']}"
    assert tenant.post(url, json={"lines": [{"item_id": it["id"], "quantity": 1}]}).status_code == 409
    assert tenant.post(url, json={"lines": [{"item_id": it["id"], "quantity": 1}], "again": True}).status_code == 200
    assert on_hand(tenant, it)["quantity_on_hand"] == 7
    assert tenant.post(f"/api/supplier-credits/{cr['id']}/void").status_code == 200
    assert tenant.post(url, json={"lines": [{"item_id": it["id"], "quantity": 1}], "again": True}).status_code == 400


# --- a recurring invoice keeps the item it sells -----------------------------------------------
def test_a_recurring_template_keeps_its_item_and_its_invoices_take_stock(tenant):
    it = tracked(tenant, 10)
    r = tenant.post("/api/recurring-invoices", json={
        "name": "Monthly box", "contact": "Box Ltd", "email": "box@example.com", "frequency": "monthly",
        "next_run": "2026-01-01", "payment_terms_days": 14, "tax_type": "exclusive",
        "line_items": [{"description": "Box", "qty": 2, "price": 10.0, "tax_rate": "No Tax", "item_id": it["id"]}]})
    assert r.status_code == 200, r.text
    rec = next(x for x in tenant.get("/api/recurring-invoices").json() if x["id"] == r.json()["id"])
    assert rec["line_items"][0]["item_id"] == it["id"]
    upd = tenant.put(f"/api/recurring-invoices/{rec['id']}", json={
        "name": "Monthly box", "contact": "Box Ltd", "email": "box@example.com", "frequency": "monthly",
        "next_run": "2026-01-01", "payment_terms_days": 14, "tax_type": "exclusive",
        "line_items": [{"description": "Box", "qty": 3, "price": 10.0, "tax_rate": "No Tax", "item_id": it["id"]}]})
    assert upd.status_code == 200, upd.text
    rec = next(x for x in tenant.get("/api/recurring-invoices").json() if x["id"] == rec["id"])
    assert rec["line_items"][0]["item_id"] == it["id"]
    with main.SessionLocal() as db:
        t = db.get(models.DBRecurringInvoice, rec["id"])
        inv = main.issue_recurring_invoice(db, t, main._parse_date("2026-01-01"))
        db.commit()
        assert [li.item_id for li in inv.line_items] == [it["id"]]
        assert inv.status == "Draft"
        inv_id = inv.id
    assert on_hand(tenant, it)["quantity_on_hand"] == 10      # a draft takes nothing
    with main.SessionLocal() as db:
        db.get(models.DBInvoice, inv_id).status = "Awaiting Payment"
        db.commit()
    assert on_hand(tenant, it)["quantity_on_hand"] == 7       # issued, it does


# --- one business cannot touch another's stock ------------------------------------------------
def test_another_business_cannot_receive_into_or_restock_your_items(tenant):
    from fastapi.testclient import TestClient
    it = tracked(tenant, 5)
    with TestClient(main.app) as other:
        other.post("/api/client/register", json={"email": "rival-stockdocs@example.com", "password": "Passw0rdTest", "company_name": "Rival"})
        other.post("/api/client/login", json={"email": "rival-stockdocs@example.com", "password": "Passw0rdTest"})
        theirs = other.post("/api/bills", json={"vendor_name": "Z", "amount": 10, "issue_date": d(-1)}).json()
        r = other.post(f"/api/bills/{theirs['id']}/receive", json={"lines": [{"item_id": it["id"], "quantity": 100}]})
        assert r.status_code == 404
        mine = bill(tenant)
        assert other.post(f"/api/bills/{mine['id']}/receive", json={"lines": [{"item_id": it["id"], "quantity": 1}]}).status_code == 404
        assert other.get(f"/api/bills/{mine['id']}/stock").status_code == 404
    assert on_hand(tenant, it)["quantity_on_hand"] == 5
