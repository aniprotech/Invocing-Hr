"""Credit notes from suppliers: taken off the bill they correct, set against
other bills, or paid back - with the note keeping count of what is left, and
the bill's payment history saying where each credit went."""
from datetime import date, timedelta

import pytest

import main


@pytest.fixture(autouse=True)
def _reset():
    main.rate_limiter._hits.clear()
    yield


def d(n):
    return (date.today() + timedelta(days=n)).isoformat()


def bill(tenant, number="B-1", vendor="Paper Co", total=100.0):
    res = tenant.post("/api/bills", json={"number": number, "vendor_name": vendor, "issue_date": d(-5), "due_date": d(10),
                                          "amount": total, "tax_amount": 0, "total": total, "status": "Unpaid"})
    assert res.status_code == 200, res.text
    return res.json()["id"]


def note(tenant, **kw):
    payload = {"amount": 30.0}
    payload.update(kw)
    res = tenant.post("/api/supplier-credit-notes", json=payload)
    assert res.status_code == 200, res.text
    return res.json()


def get_bill(tenant, bill_id):
    return tenant.get(f"/api/bills/{bill_id}").json()


def test_a_credit_note_against_a_bill_comes_straight_off_it(tenant):
    b = bill(tenant)
    n = note(tenant, bill_id=b, amount=30, tax_amount=6, supplier_ref="CN-778", reason="Damaged goods")
    assert n["number"] == "SCN-0001" and n["total"] == 36.0 and n["vendor_name"] == "Paper Co" and n["bill_number"] == "B-1"
    assert (n["allocated"], n["remaining"], n["status"]) == (36.0, 0.0, "Applied")
    assert get_bill(tenant, b)["amount_paid"] == 36.0 and get_bill(tenant, b)["status"] == "Partially Paid"
    ledger = tenant.get(f"/api/bills/{b}/payments").json()["payments"]
    assert ledger[0]["method"] == "credit_note" and ledger[0]["reference"] == "SCN-0001" and ledger[0]["amount"] == 36.0
    assert [a["bill_number"] for a in n["allocations"]] == ["B-1"]


def test_a_credit_bigger_than_the_bill_keeps_the_rest(tenant):
    b = bill(tenant, total=20)
    n = note(tenant, bill_id=b, amount=50)
    assert (n["allocated"], n["remaining"], n["status"]) == (20.0, 30.0, "Open")
    assert get_bill(tenant, b)["status"] == "Paid"


def test_a_credit_note_need_not_be_applied_or_against_a_bill(tenant):
    b = bill(tenant)
    n = note(tenant, bill_id=b, amount=10, apply_to_bill=False)
    assert (n["allocated"], n["remaining"], n["status"]) == (0.0, 10.0, "Open") and get_bill(tenant, b)["amount_paid"] == 0.0
    solo = note(tenant, vendor_name="Tea Ltd", amount=5)
    assert solo["vendor_name"] == "Tea Ltd" and solo["bill_number"] == "" and solo["number"] == "SCN-0002"


@pytest.mark.parametrize("body,why", [
    ({"amount": 0, "vendor_name": "X"}, "more than nothing"),
    ({"amount": 5}, "Supplier name"),
    ({"amount": 5, "vendor_name": "X", "tax_amount": -1}, "negative"),
    ({"amount": 5, "vendor_name": "X", "issue_date": "soon"}, "YYYY-MM-DD"),
    ({"amount": 5, "bill_id": 999999}, "Bill not found"),
])
def test_bad_credit_notes_are_refused_with_a_reason(tenant, body, why):
    r = tenant.post("/api/supplier-credit-notes", json=body)
    assert r.status_code in (400, 404) and why in r.json()["detail"], r.text


def test_credit_can_be_set_against_another_bill(tenant):
    b1, b2 = bill(tenant, "B-1"), bill(tenant, "B-2")
    n = note(tenant, vendor_name="Paper Co", amount=40, bill_id=b1, apply_to_bill=False)
    r = tenant.post(f"/api/supplier-credit-notes/{n['id']}/allocate", json={"bill_id": b2, "amount": 25})
    assert r.status_code == 200, r.text
    assert (r.json()["allocated"], r.json()["remaining"], r.json()["status"]) == (25.0, 15.0, "Open")
    assert get_bill(tenant, b2)["amount_paid"] == 25.0 and get_bill(tenant, b1)["amount_paid"] == 0.0
    r = tenant.post(f"/api/supplier-credit-notes/{n['id']}/allocate", json={"bill_id": b2, "amount": 15})
    assert r.json()["status"] == "Applied" and r.json()["remaining"] == 0.0


def test_allocation_is_refused_when_there_is_not_enough(tenant):
    b1, b2 = bill(tenant, "B-1", total=100), bill(tenant, "B-2", total=10)
    n = note(tenant, vendor_name="Paper Co", amount=40)
    url = f"/api/supplier-credit-notes/{n['id']}/allocate"
    assert "Only 40.00" in tenant.post(url, json={"bill_id": b1, "amount": 41}).json()["detail"]
    assert "more than the" in tenant.post(url, json={"bill_id": b2, "amount": 11}).json()["detail"]
    assert tenant.post(url, json={"bill_id": b1, "amount": 0}).status_code == 400
    assert tenant.post(url, json={"amount": 5}).status_code == 400
    assert tenant.post(url, json={"bill_id": 999999, "amount": 5}).status_code == 404
    assert tenant.get(f"/api/supplier-credit-notes/{n['id']}").json()["allocated"] == 0.0


def test_a_credit_can_be_taken_back_off_a_bill(tenant):
    b = bill(tenant)
    n = note(tenant, bill_id=b, amount=30)
    pid = n["allocations"][0]["payment_id"]
    r = tenant.delete(f"/api/supplier-credit-notes/{n['id']}/allocations/{pid}")
    assert r.status_code == 200 and (r.json()["allocated"], r.json()["remaining"], r.json()["status"]) == (0.0, 30.0, "Open")
    assert get_bill(tenant, b)["amount_paid"] == 0.0 and get_bill(tenant, b)["status"] == "Unpaid"
    assert tenant.delete(f"/api/supplier-credit-notes/{n['id']}/allocations/{pid}").status_code == 404


def test_the_credit_cannot_be_faked_or_removed_through_the_bill(tenant):
    b = bill(tenant)
    n = note(tenant, bill_id=b, amount=30)
    r = tenant.post(f"/api/bills/{b}/payments", json={"amount": 5, "method": "credit_note"})
    assert r.status_code == 400 and "from the credit note" in r.json()["detail"]
    assert tenant.post(f"/api/bills/{b}/pay", json={"method": "credit_note"}).status_code == 400
    r = tenant.delete(f"/api/bills/{b}/payments/{n['allocations'][0]['payment_id']}")
    assert r.status_code == 400 and "credit note" in r.json()["detail"]


def test_a_refund_uses_up_credit(tenant):
    n = note(tenant, vendor_name="Paper Co", amount=50)
    url = f"/api/supplier-credit-notes/{n['id']}/refund"
    assert tenant.post(url, json={"amount": 51}).status_code == 400
    assert tenant.post(url, json={"amount": 0}).status_code == 400
    assert tenant.post(url, json={"amount": 5, "method": "credit_note"}).status_code == 400
    assert tenant.post(url, json={"amount": 5, "date": "x"}).status_code == 400
    r = tenant.post(url, json={"amount": 20, "date": d(-1), "method": "bank_transfer", "reference": "RF-1"})
    assert r.status_code == 200, r.text
    assert (r.json()["refunded"], r.json()["remaining"], r.json()["status"], r.json()["refunded_on"]) == (20.0, 30.0, "Open", d(-1))
    assert tenant.post(url, json={"amount": 30}).json()["status"] == "Applied"


def test_void_only_while_nothing_is_used(tenant):
    b = bill(tenant)
    used = note(tenant, bill_id=b, amount=10)
    r = tenant.post(f"/api/supplier-credit-notes/{used['id']}/void", json={})
    assert r.status_code == 400 and "bill first" in r.json()["detail"]
    paid_back = note(tenant, vendor_name="X", amount=10)
    tenant.post(f"/api/supplier-credit-notes/{paid_back['id']}/refund", json={"amount": 1})
    assert "paid back" in tenant.post(f"/api/supplier-credit-notes/{paid_back['id']}/void", json={}).json()["detail"]
    fresh = note(tenant, vendor_name="Y", amount=10)
    r = tenant.post(f"/api/supplier-credit-notes/{fresh['id']}/void", json={"reason": "Entered twice"})
    assert r.status_code == 200 and r.json()["status"] == "Void" and r.json()["void_reason"] == "Entered twice"
    assert tenant.post(f"/api/supplier-credit-notes/{fresh['id']}/void", json={}).status_code == 400
    assert tenant.post(f"/api/supplier-credit-notes/{fresh['id']}/allocate", json={"bill_id": b, "amount": 1}).status_code == 400
    assert tenant.post(f"/api/supplier-credit-notes/{fresh['id']}/refund", json={"amount": 1}).status_code == 400


def test_deleting_a_bill_gives_its_credit_back_to_the_note(tenant):
    b = bill(tenant)
    n = note(tenant, bill_id=b, amount=30)
    assert tenant.delete(f"/api/bills/{b}").status_code == 200
    got = tenant.get(f"/api/supplier-credit-notes/{n['id']}").json()
    assert (got["allocated"], got["remaining"], got["status"], got["bill_id"]) == (0.0, 30.0, "Open", None)
    assert tenant.get("/api/bill-payments").json()["count"] == 0


def test_the_list_filters_and_totals_what_is_open(tenant):
    b = bill(tenant)
    note(tenant, bill_id=b, amount=30, supplier_ref="CN-1")                       # applied
    note(tenant, vendor_name="Tea Ltd", amount=25, supplier_ref="TEA-9")           # open
    v = note(tenant, vendor_name="Void Ltd", amount=7)
    tenant.post(f"/api/supplier-credit-notes/{v['id']}/void", json={})
    got = tenant.get("/api/supplier-credit-notes").json()
    assert got["count"] == 3 and got["open_total"] == 25.0
    assert [n["number"] for n in got["credit_notes"]] == ["SCN-0003", "SCN-0002", "SCN-0001"]
    assert tenant.get("/api/supplier-credit-notes", params={"status": "open"}).json()["count"] == 1
    assert tenant.get("/api/supplier-credit-notes", params={"status": "applied"}).json()["count"] == 1
    assert tenant.get("/api/supplier-credit-notes", params={"q": "tea-9"}).json()["count"] == 1
    assert tenant.get("/api/supplier-credit-notes", params={"q": "paper"}).json()["count"] == 1
    assert tenant.get("/api/supplier-credit-notes", params={"status": "lost"}).status_code == 400


def test_nothing_crosses_a_business(client, account):
    tenant = account["client"]
    b = bill(tenant)
    n = note(tenant, bill_id=b, amount=10, apply_to_bill=False)
    other = f"other-{account['email']}"
    client.post("/api/client/register", json={"email": other, "password": "Passw0rdTest", "company_name": "Other Co"})
    client.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})
    assert client.get("/api/supplier-credit-notes").json()["count"] == 0
    assert client.get(f"/api/supplier-credit-notes/{n['id']}").status_code == 404
    assert client.post(f"/api/supplier-credit-notes/{n['id']}/allocate", json={"bill_id": b, "amount": 1}).status_code == 404
    assert client.post(f"/api/supplier-credit-notes/{n['id']}/void", json={}).status_code == 404
    assert client.post("/api/supplier-credit-notes", json={"amount": 5, "bill_id": b}).status_code == 404
    client.cookies.clear()
    assert client.get("/api/supplier-credit-notes").status_code == 401
