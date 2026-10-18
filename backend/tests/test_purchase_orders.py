"""Purchase orders: written as a draft, approved, billed once, voided or
deleted - with the figures worked out on the server from the lines."""
from datetime import date, timedelta

import pytest

import main


@pytest.fixture(autouse=True)
def _reset():
    main.rate_limiter._hits.clear()
    yield


def d(n):
    return (date.today() + timedelta(days=n)).isoformat()


LINES = [{"description": "Reams of paper", "qty": 10, "price": 4.5, "tax_rate": 20},
         {"description": "Delivery", "qty": 1, "price": 5, "tax_rate": 0}]


def order(tenant, **kw):
    payload = {"vendor_name": "Paper Co", "vendor_email": "ap@paper.example", "issue_date": d(0), "delivery_date": d(7),
               "reference": "REQ-5", "lines": LINES}
    payload.update(kw)
    res = tenant.post("/api/purchase-orders", json=payload)
    assert res.status_code == 200, res.text
    return res.json()


def test_a_draft_is_saved_with_its_figures_worked_out(tenant):
    po = order(tenant)
    assert po["number"] == "PO-0001" and po["status"] == "Draft"
    assert (po["subtotal"], po["tax_total"], po["total"]) == (50.0, 9.0, 59.0)
    assert [ln["net"] for ln in po["lines"]] == [45.0, 5.0]
    assert order(tenant)["number"] == "PO-0002"


@pytest.mark.parametrize("change,why", [
    ({"vendor_name": " "}, "Supplier name"),
    ({"lines": []}, "at least one line"),
    ({"lines": [{"description": " ", "qty": 1, "price": 1}]}, "Line 1 needs a description"),
    ({"lines": [{"description": "x", "qty": 0, "price": 1}]}, "quantity"),
    ({"lines": [{"description": "x", "qty": 1, "price": -1}]}, "price cannot be negative"),
    ({"lines": [{"description": "x", "qty": 1, "price": 1, "tax_rate": 120}]}, "between 0 and 100"),
    ({"issue_date": "soon"}, "YYYY-MM-DD"),
    ({"issue_date": d(5), "delivery_date": d(1)}, "before the order date"),
    ({"lines": [{"description": "x", "qty": 1, "price": 1}] * 101}, "At most 100"),
])
def test_bad_orders_are_refused_with_a_reason(tenant, change, why):
    payload = {"vendor_name": "X", "lines": [{"description": "x", "qty": 1, "price": 1}]}
    payload.update(change)
    r = tenant.post("/api/purchase-orders", json=payload)
    assert r.status_code == 400 and why in r.json()["detail"], r.text


def test_only_a_draft_can_be_edited(tenant):
    po = order(tenant)
    r = tenant.put(f"/api/purchase-orders/{po['id']}", json={"vendor_name": "Other Co", "lines": [{"description": "Pens", "qty": 2, "price": 3}]})
    assert r.status_code == 200 and r.json()["vendor_name"] == "Other Co" and r.json()["total"] == 6.0 and len(r.json()["lines"]) == 1
    tenant.post(f"/api/purchase-orders/{po['id']}/approve")
    r = tenant.put(f"/api/purchase-orders/{po['id']}", json={"vendor_name": "X", "lines": LINES})
    assert r.status_code == 400 and "approved order cannot be edited" in r.json()["detail"]


def test_approve_then_bill_makes_a_draft_bill_once(tenant):
    po = order(tenant)
    assert "Approve the order" in tenant.post(f"/api/purchase-orders/{po['id']}/bill").json()["detail"]
    assert tenant.post(f"/api/purchase-orders/{po['id']}/approve").json()["status"] == "Approved"
    assert "already approved" in tenant.post(f"/api/purchase-orders/{po['id']}/approve").json()["detail"]
    r = tenant.post(f"/api/purchase-orders/{po['id']}/bill", json={"due_days": 14})
    assert r.status_code == 200, r.text
    assert r.json()["order"]["status"] == "Billed" and r.json()["order"]["bill_number"] == r.json()["bill_number"]
    bill = tenant.get(f"/api/bills/{r.json()['bill_id']}").json()
    assert (bill["vendor_name"], bill["status"], bill["total"], bill["amount"], bill["tax_amount"], bill["reference"]) == \
        ("Paper Co", "Draft", 59.0, 50.0, 9.0, "PO-0001")
    assert bill["due_date"] == d(14) and "PO-0001" in bill["notes"]
    assert [(ln["description"], ln["qty"], ln["tax_rate"]) for ln in bill["line_items"]] == [("Reams of paper", 10, "20%"), ("Delivery", 1, "0%")]
    again = tenant.post(f"/api/purchase-orders/{po['id']}/bill")
    assert again.status_code == 400 and "Already billed" in again.json()["detail"]
    assert len(tenant.get("/api/bills").json()) == 1


def test_bad_payment_terms_are_refused(tenant):
    po = order(tenant)
    tenant.post(f"/api/purchase-orders/{po['id']}/approve")
    assert tenant.post(f"/api/purchase-orders/{po['id']}/bill", json={"due_days": 999}).status_code == 400
    assert tenant.post(f"/api/purchase-orders/{po['id']}/bill", json={"due_days": "soon"}).status_code == 400
    assert tenant.get("/api/bills").json() == []


def test_deleting_the_bill_lets_the_order_be_billed_again(tenant):
    po = order(tenant)
    tenant.post(f"/api/purchase-orders/{po['id']}/approve")
    made = tenant.post(f"/api/purchase-orders/{po['id']}/bill").json()
    assert tenant.delete(f"/api/bills/{made['bill_id']}").status_code == 200
    got = tenant.get(f"/api/purchase-orders/{po['id']}").json()
    assert (got["status"], got["bill_id"], got["bill_number"]) == ("Approved", None, "")
    assert tenant.post(f"/api/purchase-orders/{po['id']}/bill").status_code == 200


def test_void_and_delete(tenant):
    a, b, c = order(tenant), order(tenant), order(tenant)
    assert tenant.delete(f"/api/purchase-orders/{a['id']}").status_code == 200
    assert tenant.get(f"/api/purchase-orders/{a['id']}").status_code == 404
    tenant.post(f"/api/purchase-orders/{b['id']}/approve")
    assert "stays on record" in tenant.delete(f"/api/purchase-orders/{b['id']}").json()["detail"]
    r = tenant.post(f"/api/purchase-orders/{b['id']}/void", json={"reason": "Cancelled by us"})
    assert r.status_code == 200 and r.json()["status"] == "Void" and r.json()["void_reason"] == "Cancelled by us"
    assert tenant.post(f"/api/purchase-orders/{b['id']}/void").status_code == 400
    assert tenant.post(f"/api/purchase-orders/{b['id']}/approve").status_code == 400
    tenant.post(f"/api/purchase-orders/{c['id']}/approve")
    billed = tenant.post(f"/api/purchase-orders/{c['id']}/bill").json()
    assert "billed as" in tenant.post(f"/api/purchase-orders/{c['id']}/void").json()["detail"]
    assert billed["order"]["status"] == "Billed"


def test_the_list_filters_and_totals_what_is_approved(tenant):
    a = order(tenant, vendor_name="Paper Co", reference="REQ-5")
    b = order(tenant, vendor_name="Tea Ltd", reference="TEA-1")
    tenant.post(f"/api/purchase-orders/{b['id']}/approve")
    got = tenant.get("/api/purchase-orders").json()
    assert got["count"] == 2 and got["approved_total"] == 59.0
    assert [o["number"] for o in got["orders"]] == ["PO-0002", "PO-0001"]
    assert tenant.get("/api/purchase-orders", params={"status": "draft"}).json()["count"] == 1
    assert tenant.get("/api/purchase-orders", params={"status": "approved"}).json()["orders"][0]["id"] == b["id"]
    assert tenant.get("/api/purchase-orders", params={"q": "tea-1"}).json()["count"] == 1
    assert tenant.get("/api/purchase-orders", params={"q": "po-0001"}).json()["orders"][0]["id"] == a["id"]
    assert tenant.get("/api/purchase-orders", params={"status": "lost"}).status_code == 400


def test_nothing_crosses_a_business(client, account):
    tenant = account["client"]
    po = order(tenant)
    other = f"other-{account['email']}"
    client.post("/api/client/register", json={"email": other, "password": "Passw0rdTest", "company_name": "Other Co"})
    client.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})
    assert client.get("/api/purchase-orders").json()["count"] == 0
    assert client.get(f"/api/purchase-orders/{po['id']}").status_code == 404
    for action in ("approve", "bill", "void"):
        assert client.post(f"/api/purchase-orders/{po['id']}/{action}").status_code == 404
    assert client.delete(f"/api/purchase-orders/{po['id']}").status_code == 404
    assert client.put(f"/api/purchase-orders/{po['id']}", json={"vendor_name": "x", "lines": LINES}).status_code == 404
    assert order(client)["number"] == "PO-0001", "numbers are each business's own"
    client.cookies.clear()
    assert client.get("/api/purchase-orders").status_code == 401
