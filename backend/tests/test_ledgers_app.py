"""The sales and purchase ledgers, through the app.

The arithmetic is proven in test_ledgers.py. These are the joins: that a bill
posted to a supplier shows up on the right account, that payments and credit
notes come off it and nothing is counted twice, that the ledger agrees with the
bills under it on any day, and that one business never sees another's.

The hand-worked case used throughout: a supplier billed 100 on day -40 (due
-10, so 10 days late), then 200 on day -5 (due +25, not yet due). 30 has been
paid on the first. They owe 270 - 70 late and 200 not yet due.
"""
import json
from datetime import date, timedelta

import pytest

import database
import main
import models
import ledgers
from conftest import make_invoice


@pytest.fixture(autouse=True)
def _reset():
    main.rate_limiter._hits.clear()
    yield


def d(n):
    return (date.today() + timedelta(days=n)).isoformat()


def supplier(tenant, name="Acme Supplies", **kw):
    r = tenant.post("/api/suppliers", json={"name": name, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def bill(tenant, vendor="Acme Supplies", amount=100.0, issue=None, due=None, tax=0.0, **kw):
    body = dict(vendor_name=vendor, issue_date=issue or d(-40), due_date=due or d(-10), amount=amount, tax_amount=tax, **kw)
    r = tenant.post("/api/bills", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def pay(tenant, bill_id, amount, day=None, **kw):
    r = tenant.post(f"/api/bills/{bill_id}/payments", json={"amount": amount, "paid_on": day or d(-1), **kw})
    assert r.status_code == 200, r.text
    return r.json()


def get_bill(tenant, bill_id):
    return tenant.get(f"/api/bills/{bill_id}").json()


def credit(tenant, supplier_id, amount, **kw):
    """A supplier credit note, made the way the Purchases screen makes one: by
    the supplier's name, not set against a bill unless asked."""
    name = tenant.get(f"/api/suppliers/{supplier_id}").json()["name"]
    body = {"vendor_name": name, "amount": amount, "issue_date": d(-3), "apply_to_bill": False}
    body.update(kw)
    r = tenant.post("/api/supplier-credit-notes", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def use_credit(tenant, credit_id, bill_id, amount):
    r = tenant.post(f"/api/supplier-credit-notes/{credit_id}/allocate", json={"bill_id": bill_id, "amount": amount})
    assert r.status_code == 200, r.text
    return r.json()


def account(tenant, name="Acme Supplies", **q):
    rows = tenant.get("/api/ledger/purchases", params=q).json()["accounts"]
    return next((r for r in rows if r["supplier"] == name), None)


@pytest.fixture
def worked(tenant):
    """The hand-worked supplier: 100 (late) with 30 paid, and 200 not yet due."""
    first = bill(tenant, amount=100.0, issue=d(-40), due=d(-10), number="B-1")
    second = bill(tenant, amount=200.0, issue=d(-5), due=d(25), number="B-2")
    pay(tenant, first["id"], 30, d(-20))
    return first, second


# =====================================================================================
# Suppliers
# =====================================================================================

def test_a_supplier_is_made_listed_and_read_back(tenant):
    s = supplier(tenant, "Northwind Ltd", account_ref="NW01", email="ap@northwind.test", contact_person="Pat", phone_number="0207",
                 address="1 High St", tax_id="GB123", payment_terms_days=45, bank_details="Sort 12-34-56 Acc 12345678", notes="net 45")
    assert s["id"] and s["active"] is True and s["on_hold"] is False and s["payment_terms_days"] == 45 and s["account_ref"] == "NW01"
    assert [x["name"] for x in tenant.get("/api/suppliers").json()] == ["Northwind Ltd"]
    assert tenant.get(f"/api/suppliers/{s['id']}").json() == s


def test_a_supplier_needs_a_name(tenant):
    assert tenant.post("/api/suppliers", json={"name": "  "}).status_code == 400
    assert tenant.post("/api/suppliers", json={}).status_code == 400


def test_two_suppliers_cannot_share_a_name_in_any_case(tenant):
    supplier(tenant, "Acme Supplies")
    r = tenant.post("/api/suppliers", json={"name": "ACME  supplies"})
    assert r.status_code == 400 and "already have a supplier" in r.json()["detail"]


def test_an_account_reference_is_one_suppliers_alone(tenant):
    supplier(tenant, "A", account_ref="X1")
    r = tenant.post("/api/suppliers", json={"name": "B", "account_ref": "x1"})
    assert r.status_code == 400 and "already used" in r.json()["detail"]
    b = supplier(tenant, "B", account_ref="X2")
    assert tenant.put(f"/api/suppliers/{b['id']}", json={"account_ref": "X1"}).status_code == 400
    assert tenant.put(f"/api/suppliers/{b['id']}", json={"account_ref": "X2"}).status_code == 200    # its own is fine


@pytest.mark.parametrize("body,says", [
    ({"email": "not-an-email"}, "Invalid email"), ({"payment_terms_days": 400}, "between 0 and 365"), ({"payment_terms_days": -1}, "between 0 and 365"),
    ({"payment_terms_days": "soon"}, "number of days"), ({"currency": "U$D"}, "three-letter"),
])
def test_what_cannot_be_right_is_refused_in_plain_words(tenant, body, says):
    r = tenant.post("/api/suppliers", json={"name": "X", **body})
    assert r.status_code == 400 and says in r.json()["detail"], r.text


def test_a_supplier_in_the_books_currency_stores_no_currency(tenant):
    base = tenant.get("/api/client/me").json().get("currency") or "GBP"
    assert supplier(tenant, "Home", currency=base.lower())["currency"] == ""
    assert supplier(tenant, "Abroad", currency="usd")["currency"] == "USD"


def test_suppliers_can_be_searched_by_name_reference_or_email(tenant):
    supplier(tenant, "Acme", account_ref="AC9", email="a@x.test")
    supplier(tenant, "Zed", email="z@zed.test")
    names = lambda q: [s["name"] for s in tenant.get("/api/suppliers", params={"search": q}).json()]
    assert names("acm") == ["Acme"] and names("ac9") == ["Acme"] and names("zed.test") == ["Zed"] and names("nobody") == []


def test_renaming_a_supplier_renames_it_on_its_bills(tenant):
    s = supplier(tenant, "Old Name")
    b = bill(tenant, vendor="Old Name")
    tenant.put(f"/api/suppliers/{s['id']}", json={"name": "New Name"})
    assert get_bill(tenant, b["id"])["vendor_name"] == "New Name"


def test_a_supplier_nothing_was_posted_to_is_removed_and_one_with_bills_is_closed(tenant):
    unused = supplier(tenant, "Unused")
    assert tenant.delete(f"/api/suppliers/{unused['id']}").json()["closed"] is False
    assert tenant.get(f"/api/suppliers/{unused['id']}").status_code == 404
    b = bill(tenant, vendor="Used")
    r = tenant.delete(f"/api/suppliers/{b['supplier_id']}").json()
    assert r["closed"] is True and "stays on record" in r["message"]
    assert "Used" not in [s["name"] for s in tenant.get("/api/suppliers").json()]
    assert "Used" in [s["name"] for s in tenant.get("/api/suppliers", params={"include_inactive": 1}).json()]
    assert get_bill(tenant, b["id"])["supplier_id"] == b["supplier_id"]


def test_a_supplier_with_only_a_credit_note_is_closed_not_removed(tenant):
    s = supplier(tenant, "CreditOnly")
    credit(tenant, s["id"], 10)
    assert tenant.delete(f"/api/suppliers/{s['id']}").json()["closed"] is True


def test_suppliers_belong_to_one_business(tenant, client):
    s = supplier(tenant, "Mine")
    from fastapi.testclient import TestClient
    with TestClient(main.app) as other:
        other.post("/api/client/register", json={"email": "rival@example.com", "password": "Passw0rdTest", "company_name": "Rival"})
        other.post("/api/client/login", json={"email": "rival@example.com", "password": "Passw0rdTest"})
        assert other.get("/api/suppliers").json() == []
        assert other.get(f"/api/suppliers/{s['id']}").status_code == 404
        assert other.put(f"/api/suppliers/{s['id']}", json={"name": "Stolen"}).status_code == 404
        assert other.delete(f"/api/suppliers/{s['id']}").status_code == 404
        assert other.get(f"/api/ledger/purchases/{s['id']}").status_code == 404
        # the same name is free to the other business
        assert other.post("/api/suppliers", json={"name": "Mine"}).status_code == 200


# =====================================================================================
# Bills posted to a supplier
# =====================================================================================

def test_a_bill_typed_with_a_name_makes_the_supplier_and_links_to_it(tenant):
    b = bill(tenant, vendor="Fresh Co")
    assert b["supplier_id"] and [s["name"] for s in tenant.get("/api/suppliers").json()] == ["Fresh Co"]
    again = bill(tenant, vendor="fresh co", number="B-2")
    assert again["supplier_id"] == b["supplier_id"] and len(tenant.get("/api/suppliers").json()) == 1


def test_a_bill_can_name_its_supplier_by_id(tenant):
    s = supplier(tenant, "By Id")
    b = tenant.post("/api/bills", json={"supplier_id": s["id"], "amount": 10, "issue_date": d(-1), "due_date": d(10)}).json()
    assert b["supplier_id"] == s["id"] and get_bill(tenant, b["id"])["vendor_name"] == "By Id"


def test_a_bill_needs_a_supplier_that_is_one_of_yours(tenant):
    assert tenant.post("/api/bills", json={"amount": 10}).status_code == 400
    assert tenant.post("/api/bills", json={"supplier_id": 99999, "amount": 10}).status_code == 400
    assert tenant.post("/api/bills", json={"supplier_id": "abc", "amount": 10}).status_code == 400


def test_a_bill_gets_a_number_when_none_is_given_and_never_a_taken_one(tenant):
    a = bill(tenant)
    b = bill(tenant, vendor="Other")
    assert a["number"] == "BILL-0001" and b["number"] == "BILL-0002"
    tenant.delete(f"/api/bills/{a['id']}")
    assert bill(tenant, vendor="Third")["number"] == "BILL-0003"      # one past the highest, not the newest
    assert tenant.get("/api/next-bill-number").json()["number"] == "BILL-0004"


def test_a_bill_number_cannot_repeat_even_by_editing(tenant):
    a = bill(tenant, number="X-1")
    b = bill(tenant, number="X-2", vendor="Other")
    assert tenant.post("/api/bills", json={"vendor_name": "Z", "number": "X-1"}).status_code == 400
    r = tenant.put(f"/api/bills/{b['id']}", json={"number": "X-1"})
    assert r.status_code == 400 and "already exists" in r.json()["detail"]
    assert tenant.put(f"/api/bills/{a['id']}", json={"number": "X-1"}).status_code == 200


def test_the_due_date_follows_the_suppliers_terms_and_then_the_business(tenant):
    s = supplier(tenant, "Terms", payment_terms_days=45)
    b = tenant.post("/api/bills", json={"supplier_id": s["id"], "amount": 10, "issue_date": "2026-01-01"}).json()
    assert get_bill(tenant, b["id"])["due_date"] == "2026-02-15"
    c = tenant.post("/api/bills", json={"vendor_name": "NoTerms", "amount": 10, "issue_date": "2026-01-01"}).json()
    assert get_bill(tenant, c["id"])["due_date"] == "2026-01-15"           # the business's own default is 14 days


@pytest.mark.parametrize("body,says", [
    ({"issue_date": "2026-03-10", "due_date": "2026-03-01"}, "cannot be before"), ({"issue_date": "10/03/2026"}, "YYYY-MM-DD"),
    ({"amount": -5}, "between 0"), ({"amount": "lots"}, "must be a number"), ({"amount": "inf"}, "between 0"), ({"amount": 5e9}, "between 0"),
    ({"tax_amount": -1}, "between 0"), ({"amount": 100, "tax_amount": 20, "total": 150}, "not the amount plus the tax"),
    ({"status": "Banana"}, "status is"), ({"currency": "U$D"}, "three-letter"),
])
def test_a_bill_that_cannot_be_right_is_refused(tenant, body, says):
    r = tenant.post("/api/bills", json={"vendor_name": "X", "amount": 100, **body})
    assert r.status_code == 400 and says in r.json()["detail"], r.text


def test_the_total_is_the_amount_plus_the_tax(tenant):
    b = bill(tenant, amount=100.0, tax=20.0)
    assert get_bill(tenant, b["id"])["total"] == 120.0
    r = tenant.post("/api/bills", json={"vendor_name": "Old", "total": 55.0})     # a caller that only knew the total
    assert r.status_code == 200 and get_bill(tenant, r.json()["id"])["amount"] == 55.0


def test_a_new_bill_is_posted_unless_it_is_a_draft(tenant):
    assert get_bill(tenant, bill(tenant)["id"])["status"] == "Awaiting Payment"
    assert get_bill(tenant, bill(tenant, vendor="D", draft=True)["id"])["status"] == "Draft"


def test_a_bill_entered_as_already_paid_is_paid_by_a_payment(tenant):
    b = bill(tenant, amount=80.0, status="Paid", paid_on=d(-2), method="cash")
    got = get_bill(tenant, b["id"])
    assert got["status"] == "Paid" and got["amount_paid"] == 80.0 and got["balance"] == 0.0
    assert [(p["amount"], p["paid_on"], p["method"]) for p in got["payments"]] == [(80.0, d(-2), "cash")]


def test_a_bill_entered_part_paid_is_part_paid(tenant):
    got = get_bill(tenant, bill(tenant, amount=80.0, amount_paid=30)["id"])
    assert got["status"] == "Partially Paid" and got["balance"] == 50.0


def test_a_bill_can_be_in_another_currency(tenant):
    b = bill(tenant, vendor="Abroad", currency="usd")
    assert get_bill(tenant, b["id"])["currency"] == "USD"
    assert tenant.get("/api/bills").json()[0]["currency"] == "USD"


def test_the_bill_list_says_what_is_left_and_how_late(tenant, worked):
    rows = {r["number"]: r for r in tenant.get("/api/bills").json()}
    assert rows["B-1"]["balance"] == 70.0 and rows["B-1"]["overdue"] is True and rows["B-1"]["days_overdue"] == 10
    assert rows["B-2"]["balance"] == 200.0 and rows["B-2"]["overdue"] is False and rows["B-2"]["days_overdue"] == 0


def test_editing_a_bill_changes_it_and_leaves_what_was_paid(tenant, worked):
    first, _ = worked
    r = tenant.put(f"/api/bills/{first['id']}", json={"amount": 150.0, "reference": "PO-7", "notes": "changed"})
    got = get_bill(tenant, first["id"])
    assert r.status_code == 200 and got["total"] == 150.0 and got["amount_paid"] == 30.0 and got["balance"] == 120.0 and got["reference"] == "PO-7"
    assert got["status"] == "Partially Paid"


def test_a_bill_cannot_be_made_smaller_than_what_has_been_paid(tenant, worked):
    r = tenant.put(f"/api/bills/{worked[0]['id']}", json={"amount": 20.0})
    assert r.status_code == 400 and "30.00 has been paid" in r.json()["detail"]


def test_what_has_been_paid_cannot_be_typed_over(tenant, worked):
    r = tenant.put(f"/api/bills/{worked[0]['id']}", json={"amount_paid": 99})
    assert r.status_code == 400 and "Record a payment" in r.json()["detail"]
    assert tenant.put(f"/api/bills/{worked[0]['id']}", json={"amount_paid": 30}).status_code == 200      # unchanged is fine


def test_a_bill_with_payments_stays_with_its_supplier_and_its_currency(tenant, worked):
    other = supplier(tenant, "Somebody Else")
    assert tenant.put(f"/api/bills/{worked[0]['id']}", json={"supplier_id": other["id"]}).status_code == 400
    assert tenant.put(f"/api/bills/{worked[0]['id']}", json={"currency": "USD"}).status_code == 400
    assert tenant.put(f"/api/bills/{worked[1]['id']}", json={"supplier_id": other["id"]}).status_code == 200      # nothing paid yet


def test_a_draft_is_posted_and_a_paid_bill_cannot_go_back_to_a_draft(tenant, worked):
    draft = bill(tenant, vendor="D", draft=True)
    assert tenant.put(f"/api/bills/{draft['id']}", json={"draft": False}).status_code == 200
    assert get_bill(tenant, draft["id"])["status"] == "Awaiting Payment"
    r = tenant.put(f"/api/bills/{worked[0]['id']}", json={"draft": True})
    assert r.status_code == 400 and "back to a draft" in r.json()["detail"]
    assert tenant.put(f"/api/bills/{worked[0]['id']}", json={"status": "Void"}).status_code == 400


def test_every_draft_can_be_posted_at_once(tenant):
    for i in range(3):
        bill(tenant, vendor=f"S{i}", draft=True)
    bill(tenant, vendor="Posted")
    assert tenant.post("/api/bills/post-drafts").json() == {"posted": 3}
    assert {b["status"] for b in tenant.get("/api/bills").json()} == {"Awaiting Payment"}
    assert tenant.post("/api/bills/post-drafts").json() == {"posted": 0}


def test_a_deleted_bill_takes_its_payments_and_leaves_the_ledger(tenant, worked):
    assert tenant.delete(f"/api/bills/{worked[0]['id']}").status_code == 200
    assert tenant.get(f"/api/bills/{worked[0]['id']}").status_code == 404
    assert account(tenant)["total"] == 200.0


def test_a_bill_is_voided_only_when_nothing_has_been_paid_and_then_cannot_change(tenant, worked):
    assert tenant.post(f"/api/bills/{worked[0]['id']}/void").status_code == 400
    assert tenant.post(f"/api/bills/{worked[1]['id']}/void").json()["status"] == "Void"
    assert tenant.put(f"/api/bills/{worked[1]['id']}", json={"notes": "x"}).status_code == 400
    assert tenant.post(f"/api/bills/{worked[1]['id']}/payments", json={"amount": 5}).status_code == 400


# Payments on a bill - part payments, refusals, taking one back, the pay shortcut -
# are the Purchases screen's and are tested in test_bill_payments.py.


# =====================================================================================
# Paying a bill from a bank line
# =====================================================================================

def bank_line_for(tenant, bill_row, amount, description="ACME PAYMENT"):
    acc = tenant.post("/api/accounts", json={"name": "Main", "kind": "bank"}).json()
    tenant.post("/api/bank/import", json={"text": f"Date,Description,Amount\n{d(-1)},{description},-{amount:.2f}\n", "filename": "s.csv", "account_id": acc["id"]})
    line = next(l for l in tenant.get("/api/bank/lines", params={"status": "out"}).json()["lines"] if description in l["description"])
    return acc, line


def test_a_bank_line_paying_a_bill_leaves_a_payment_that_taking_back_removes(tenant):
    b = bill(tenant, amount=60.0)
    acc, line = bank_line_for(tenant, b, 60.0)
    r = tenant.post("/api/bank/lines/code", json={"ids": [line["id"]], "category": "bill", "bill_id": b["id"]})
    assert r.status_code == 200, r.text
    got = get_bill(tenant, b["id"])
    assert got["status"] == "Paid" and len(got["payments"]) == 1
    p = got["payments"][0]
    assert p["from_bank"] is True and p["amount"] == 60.0 and p["account_id"] == acc["id"] and p["account"] == "Main"
    # it cannot be deleted as an ordinary payment: the bank line owns it
    gone = tenant.delete(f"/api/bills/{b['id']}/payments/{p['id']}")
    assert gone.status_code == 400 and "Bank" in gone.json()["detail"]
    tenant.post(f"/api/bank/lines/{line['id']}/uncode")
    back = get_bill(tenant, b["id"])
    assert back["amount_paid"] == 0.0 and back["payments"] == [] and back["status"] == "Unpaid"


def test_a_coding_made_before_payments_were_recorded_one_by_one_still_comes_back(tenant):
    b = bill(tenant, amount=60.0)
    acc, line = bank_line_for(tenant, b, 60.0)
    tenant.post("/api/bank/lines/code", json={"ids": [line["id"]], "category": "bill", "bill_id": b["id"]})
    with main.SessionLocal() as db:        # as it was stored before: a running total and no payment row
        db.query(models.DBBillPayment).delete()
        db.commit()
    tenant.post(f"/api/bank/lines/{line['id']}/uncode")
    assert get_bill(tenant, b["id"])["amount_paid"] == 0.0


# =====================================================================================
# Supplier credit notes on the purchase ledger (the notes themselves are tested in
# test_supplier_credit_notes.py)
# =====================================================================================

def test_a_credit_note_lands_on_its_suppliers_account_by_name_or_by_its_bill(tenant, worked):
    credit(tenant, worked[0]["supplier_id"], 10)
    assert account(tenant)["credits"] == 10.0
    r = tenant.post("/api/supplier-credit-notes", json={"vendor_name": "Typed Differently Ltd", "amount": 5, "bill_id": worked[1]["id"],
                                                         "issue_date": d(-2), "apply_to_bill": False})
    assert r.status_code == 200, r.text
    assert account(tenant)["credits"] == 15.0          # by the bill it corrects, whatever name was typed


def test_a_credit_the_supplier_paid_back_no_longer_lowers_what_is_owed(tenant, worked):
    c = credit(tenant, worked[0]["supplier_id"], 50)
    assert account(tenant)["total"] == 220.0
    r = tenant.post(f"/api/supplier-credit-notes/{c['id']}/refund", json={"amount": 50, "date": d(-1)})
    assert r.status_code == 200, r.text
    assert account(tenant)["total"] == 270.0 and account(tenant)["credits"] == 0.0
    led = tenant.get(f"/api/ledger/purchases/{worked[0]['supplier_id']}", params={"start": d(-60), "end": d(0)}).json()["ledgers"][0]
    assert led["closing_balance"] == 270.0 and any(l["kind"] == "refund" for l in led["lines"])


def test_a_void_credit_note_is_not_on_the_ledger(tenant, worked):
    c = credit(tenant, worked[0]["supplier_id"], 50)
    tenant.post(f"/api/supplier-credit-notes/{c['id']}/void", json={"reason": "typed twice"})
    assert account(tenant)["credits"] == 0.0 and account(tenant)["total"] == 270.0


# =====================================================================================
# The purchase ledger
# =====================================================================================

def test_the_ledger_shows_what_is_owed_and_how_late(tenant, worked):
    a = account(tenant)
    assert a["total"] == 270.0 and a["current"] == 200.0 and a["1_30"] == 70.0 and a["overdue"] == 70.0
    assert a["bills"] == 2 and a["oldest_days"] == 10 and a["credits"] == 0.0 and a["last_bill"] == d(-5) and a["last_payment"] == d(-20)
    totals = tenant.get("/api/ledger/purchases").json()["totals"]
    assert totals["balance"] == 270.0 and totals["overdue"] == 70.0 and totals["buckets"]["current"] == 200.0 and totals["accounts_owing"] == 1


def test_credit_not_yet_used_comes_off_what_is_owed(tenant, worked):
    credit(tenant, worked[0]["supplier_id"], 50)
    a = account(tenant)
    assert a["credits"] == 50.0 and a["total"] == 220.0
    assert tenant.get("/api/ledger/purchases").json()["totals"]["credits"] == 50.0


def test_credit_set_against_a_bill_is_counted_once(tenant, worked):
    c = credit(tenant, worked[0]["supplier_id"], 50)
    use_credit(tenant, c["id"], worked[0]["id"], 50)
    a = account(tenant)
    assert a["total"] == 220.0 and a["credits"] == 0.0 and a["1_30"] == 20.0 and a["current"] == 200.0


def test_drafts_and_void_bills_are_not_on_the_ledger(tenant, worked):
    bill(tenant, vendor="Acme Supplies", amount=999.0, draft=True, number="DRAFT-1")
    v = bill(tenant, vendor="Acme Supplies", amount=888.0, number="VOID-1")
    tenant.post(f"/api/bills/{v['id']}/void")
    assert account(tenant)["total"] == 270.0


def test_a_supplier_with_nothing_owed_is_listed_unless_only_those_owing_are_asked_for(tenant, worked):
    supplier(tenant, "Quiet Co")
    names = lambda **q: [r["supplier"] for r in tenant.get("/api/ledger/purchases", params=q).json()["accounts"]]
    assert set(names()) == {"Acme Supplies", "Quiet Co"} and names(only_owing=1) == ["Acme Supplies"]


def test_the_ledger_is_sorted_by_what_is_owed_and_can_be_searched(tenant, worked):
    bill(tenant, vendor="Bigger Co", amount=900.0, number="B-9")
    assert [r["supplier"] for r in tenant.get("/api/ledger/purchases").json()["accounts"]] == ["Bigger Co", "Acme Supplies"]
    supplier(tenant, "Zeta", account_ref="ZZ1")
    assert [r["supplier"] for r in tenant.get("/api/ledger/purchases", params={"search": "zz1"}).json()["accounts"]] == ["Zeta"]


def test_the_ledger_can_be_worked_out_as_of_a_past_day(tenant, worked):
    # On day -30 only the first bill existed, with nothing paid (the 30 was paid on day -20).
    a = account(tenant, as_of=d(-30))
    assert a["total"] == 100.0 and a["current"] == 100.0 and a["bills"] == 1 and a["oldest_days"] == 0      # not yet late on that day
    a = account(tenant, as_of=d(-5))
    assert a["total"] == 270.0
    # Before either bill: nothing owed.
    assert account(tenant, as_of=d(-60), only_owing=1) is None


def test_a_bill_paid_off_stops_being_owed_from_the_day_it_was_paid(tenant):
    b = bill(tenant, amount=100.0, issue=d(-30), due=d(-5))
    pay(tenant, b["id"], 100, d(-10))
    assert account(tenant, as_of=d(-11))["total"] == 100.0
    assert account(tenant, as_of=d(-10), only_owing=1) is None


def test_a_payment_before_payments_were_recorded_one_by_one_still_counts(tenant):
    b = bill(tenant, amount=100.0, issue=d(-30), due=d(-5))
    with main.SessionLocal() as db:        # a running total with no payment row, as bills used to be paid
        db.query(models.DBBill).filter(models.DBBill.id == b["id"]).update({"amount_paid": 40.0, "status": "Partially Paid"})
        db.commit()
    assert account(tenant)["total"] == 60.0
    led = tenant.get(f"/api/ledger/purchases/{b['supplier_id']}", params={"start": d(-40), "end": d(0)}).json()["ledgers"][0]
    assert led["closing_balance"] == 60.0 and any("before payments were recorded" in l["description"] for l in led["lines"])


def test_a_foreign_bill_has_its_own_row_and_never_adds_to_the_books_currency(tenant, worked):
    bill(tenant, vendor="Acme Supplies", amount=500.0, currency="USD", number="USD-1")
    rows = [r for r in tenant.get("/api/ledger/purchases").json()["accounts"] if r["supplier"] == "Acme Supplies"]
    assert {r["currency"]: r["total"] for r in rows} == {"GBP": 270.0, "USD": 500.0} or {r["currency"]: r["total"] for r in rows}.get("USD") == 500.0
    body = tenant.get("/api/ledger/purchases").json()
    assert body["totals"]["balance"] == 270.0 and "USD" in body["other_currencies"]


def test_the_suppliers_ledger_runs_a_balance_down_the_page(tenant, worked):
    first, second = worked
    sid = first["supplier_id"]
    got = tenant.get(f"/api/ledger/purchases/{sid}", params={"start": d(-60), "end": d(0)}).json()
    led = got["ledgers"][0]
    assert led["opening_balance"] == 0.0 and led["closing_balance"] == 270.0
    assert [(l["kind"], l["ref"]) for l in led["lines"]] == [("bill", "B-1"), ("payment", "B-1"), ("bill", "B-2")] or [l["kind"] for l in led["lines"]] == ["bill", "payment", "bill"]
    assert [l["balance"] for l in led["lines"]] == [100.0, 70.0, 270.0] and led["increased"] == 300.0 and led["decreased"] == 30.0
    assert got["supplier"]["name"] == "Acme Supplies" and got["balance"] == {"GBP": 270.0}
    assert [b["number"] for b in got["open_bills"]] == ["B-1", "B-2"] and got["ageing"][0]["overdue"] == 70.0


def test_the_balance_is_carried_forward_into_a_later_period(tenant, worked):
    sid = worked[0]["supplier_id"]
    led = tenant.get(f"/api/ledger/purchases/{sid}", params={"start": d(-10), "end": d(0)}).json()["ledgers"][0]
    assert led["opening_balance"] == 70.0 and [l["ref"] for l in led["lines"]] == ["B-2"] and led["closing_balance"] == 270.0


def test_a_credit_note_lowers_the_ledger_once_even_when_it_is_set_against_a_bill(tenant, worked):
    sid = worked[0]["supplier_id"]
    c = credit(tenant, sid, 50)
    use_credit(tenant, c["id"], worked[0]["id"], 50)
    led = tenant.get(f"/api/ledger/purchases/{sid}", params={"start": d(-60), "end": d(0)}).json()["ledgers"][0]
    assert led["closing_balance"] == 220.0 and sum(1 for l in led["lines"] if l["kind"] == "credit") == 1
    assert not any(l["kind"] == "payment" and l.get("ref") == c["number"] for l in led["lines"])


def test_the_ledger_always_agrees_with_the_aged_balance(tenant, worked):
    sid = worked[0]["supplier_id"]
    credit(tenant, sid, 40)
    pay(tenant, worked[1]["id"], 55, d(-2))
    owed = account(tenant)["total"]
    led = tenant.get(f"/api/ledger/purchases/{sid}", params={"start": d(-90), "end": d(0)}).json()["ledgers"][0]
    assert led["closing_balance"] == owed == 175.0


def test_the_ledger_period_is_checked(tenant, worked):
    sid = worked[0]["supplier_id"]
    assert tenant.get(f"/api/ledger/purchases/{sid}", params={"start": "tomorrow"}).status_code == 400
    swapped = tenant.get(f"/api/ledger/purchases/{sid}", params={"start": d(0), "end": d(-30)}).json()
    assert swapped["start"] == d(-30) and swapped["end"] == d(0)
    assert tenant.get("/api/ledger/purchases/987654").status_code == 404
    assert tenant.get("/api/ledger/purchases", params={"as_of": "soon"}).status_code == 400


def test_a_bill_with_no_supplier_is_found_under_no_supplier(tenant):
    b = bill(tenant, vendor="Orphan", amount=40.0)
    with main.SessionLocal() as db:
        db.query(models.DBBill).filter(models.DBBill.id == b["id"]).update({"supplier_id": None})
        db.commit()
    a = account(tenant, name="No supplier")
    assert a is not None and a["total"] == 40.0 and a["supplier_id"] == 0
    assert tenant.get("/api/ledger/purchases/0").json()["ledgers"][0]["closing_balance"] == 40.0


def test_the_csv_exports_have_the_figures_and_do_not_run_as_formulas(tenant):
    evil = supplier(tenant, "=HYPERLINK(\"http://x\")", account_ref="+1")
    b = tenant.post("/api/bills", json={"supplier_id": evil["id"], "amount": 10, "issue_date": d(-3), "due_date": d(10), "number": "@SUM(1)"}).json()
    for path in ("/api/ledger/purchases.csv", f"/api/ledger/purchases/{evil['id']}/ledger.csv"):
        r = tenant.get(path)
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv"), path
        for line in r.text.splitlines():
            for cell in line.split(","):
                assert not cell.startswith(("=", "@", "+")), (path, cell)
    text = tenant.get("/api/ledger/purchases.csv").text
    assert text.splitlines()[0].startswith("supplier,account_ref,currency") and "10.0" in text


def test_the_csv_of_a_ledger_has_balances_brought_and_carried(tenant, worked):
    sid = worked[0]["supplier_id"]
    text = tenant.get(f"/api/ledger/purchases/{sid}/ledger.csv", params={"start": d(-60), "end": d(0)}).text
    assert "balance brought forward" in text and "balance carried forward" in text and text.strip().splitlines()[-1].endswith("270.0")


# =====================================================================================
# Customers: the account in the sales ledger
# =====================================================================================

def customer(tenant, name="Big Customer", **kw):
    r = tenant.post("/api/contacts", json={"name": name, "email": f"{name.split()[0].lower()}@example.com", **kw})
    assert r.status_code == 200, r.text
    return r.json()


def invoice_for(tenant, name, price, issue=None, due=None, status="Awaiting Payment", currency=None):
    kw = {"contact": name, "status": status, "issue_date": issue or d(-40), "due_date": due or d(-10),
          "line_items": [{"description": "Work", "qty": 1, "price": price, "tax_rate": "No Tax"}]}
    if currency:
        kw["currency"] = currency
    return make_invoice(tenant, **kw)


def sales_row(tenant, name="Big Customer", **q):
    return next((r for r in tenant.get("/api/ledger/sales", params=q).json()["accounts"] if r["contact"] == name), None)


def test_a_customer_has_an_account_reference_a_credit_limit_and_a_hold_flag(tenant):
    c = customer(tenant, account_ref="CUST-01", credit_limit=1000, on_hold=True)
    assert (c["account_ref"], c["credit_limit"], c["on_hold"]) == ("CUST-01", 1000.0, True)
    got = next(x for x in tenant.get("/api/contacts").json() if x["id"] == c["id"])
    assert (got["account_ref"], got["credit_limit"], got["on_hold"]) == ("CUST-01", 1000.0, True)
    assert tenant.put(f"/api/contacts/{c['id']}", json={"on_hold": False, "credit_limit": 0}).json()["on_hold"] is False


def test_a_customer_made_the_old_way_has_no_limit_and_is_not_on_hold(tenant):
    c = customer(tenant)
    assert (c["account_ref"], c["credit_limit"], c["on_hold"]) == ("", 0.0, False)


@pytest.mark.parametrize("body,says", [({"credit_limit": -1}, "between 0"), ({"credit_limit": "lots"}, "must be a number"), ({"credit_limit": "inf"}, "between 0")])
def test_a_credit_limit_that_cannot_be_right_is_refused(tenant, body, says):
    c = customer(tenant)
    r = tenant.put(f"/api/contacts/{c['id']}", json=body)
    assert r.status_code == 400 and says in r.json()["detail"], r.text


def test_an_account_reference_belongs_to_one_customer(tenant):
    a = customer(tenant, "Ann Co", account_ref="A1")
    r = tenant.post("/api/contacts", json={"name": "Bob Co", "account_ref": "a1"})
    assert r.status_code == 400 and "already used by Ann Co" in r.json()["detail"]
    assert tenant.put(f"/api/contacts/{a['id']}", json={"account_ref": "A1", "phone_number": "1"}).status_code == 200


def test_the_sales_ledger_shows_what_each_customer_owes_and_how_late(tenant):
    customer(tenant, "Big Customer")
    invoice_for(tenant, "Big Customer", 100.0, issue=d(-40), due=d(-10))
    invoice_for(tenant, "Big Customer", 200.0, issue=d(-5), due=d(25))
    r = sales_row(tenant)
    assert r["total"] == 300.0 and r["1_30"] == 100.0 and r["current"] == 200.0 and r["overdue"] == 100.0 and r["invoices"] == 2
    assert r["last_invoice"] == d(-5) and r["contact_id"]
    t = tenant.get("/api/ledger/sales").json()["totals"]
    assert t["balance"] == 300.0 and t["overdue"] == 100.0 and t["accounts_owing"] == 1


def test_a_customer_who_owes_nothing_is_listed_unless_only_debtors_are_asked_for(tenant):
    customer(tenant, "Big Customer")
    customer(tenant, "Quiet Customer")
    invoice_for(tenant, "Big Customer", 50.0)
    names = lambda **q: [r["contact"] for r in tenant.get("/api/ledger/sales", params=q).json()["accounts"]]
    assert set(names()) == {"Big Customer", "Quiet Customer"} and names(only_owing=1) == ["Big Customer"]


def test_a_payment_comes_off_the_sales_ledger_and_is_the_last_payment_date(tenant):
    customer(tenant, "Big Customer")
    inv = invoice_for(tenant, "Big Customer", 100.0)
    tenant.post(f"/api/invoices/{inv['number']}/payments", json={"amount": 40, "paid_on": d(-3), "method": "cash"})
    r = sales_row(tenant)
    assert r["total"] == 60.0 and r["last_payment"] == d(-3)


def test_credit_used_is_shown_against_the_limit(tenant):
    customer(tenant, "Big Customer", credit_limit=400)
    invoice_for(tenant, "Big Customer", 100.0, due=d(10))
    r = sales_row(tenant)
    assert r["credit_limit"] == 400.0 and r["available_credit"] == 300.0 and r["credit_state"] == "ok" and r["used_pct"] == 25.0
    invoice_for(tenant, "Big Customer", 270.0, due=d(10))
    assert sales_row(tenant)["credit_state"] == "near_limit"
    invoice_for(tenant, "Big Customer", 100.0, due=d(10))
    r = sales_row(tenant)
    assert r["credit_state"] == "over_limit" and r["available_credit"] == -70.0
    assert tenant.get("/api/ledger/sales").json()["totals"]["over_limit"] == 1


def test_an_account_on_hold_says_so_whatever_it_owes(tenant):
    c = customer(tenant, "Big Customer", credit_limit=1000, on_hold=True)
    invoice_for(tenant, "Big Customer", 5000.0)
    r = sales_row(tenant)
    assert r["credit_state"] == "on_hold" and r["on_hold"] is True
    assert tenant.get("/api/ledger/sales").json()["totals"]["on_hold"] == 1


def test_a_customer_with_no_limit_is_never_over_it(tenant):
    customer(tenant, "Big Customer")
    invoice_for(tenant, "Big Customer", 99999.0)
    r = sales_row(tenant)
    assert r["credit_state"] == "no_limit" and r["available_credit"] is None


def test_an_invoice_to_somebody_with_no_customer_record_is_still_on_the_ledger(tenant):
    invoice_for(tenant, "Walk-in Ltd", 75.0)
    made = next(c for c in tenant.get("/api/contacts").json() if c["name"] == "Walk-in Ltd")      # raising the invoice made one
    tenant.delete(f"/api/contacts/{made['id']}")
    r = sales_row(tenant, "Walk-in Ltd")
    assert r["total"] == 75.0 and r["contact_id"] is None and r["credit_state"] == "no_limit"


def test_a_drafted_or_voided_invoice_is_not_owed(tenant):
    customer(tenant, "Big Customer")
    invoice_for(tenant, "Big Customer", 500.0, status="Draft")
    assert sales_row(tenant, only_owing=1) is None


def test_the_sales_ledger_can_be_searched_by_reference_and_worked_out_for_a_past_day(tenant):
    customer(tenant, "Big Customer", account_ref="BC-7")
    customer(tenant, "Other Customer")
    invoice_for(tenant, "Big Customer", 100.0, issue=d(-40), due=d(-10))
    assert [r["contact"] for r in tenant.get("/api/ledger/sales", params={"search": "bc-7"}).json()["accounts"]] == ["Big Customer"]
    assert sales_row(tenant, as_of=d(-60), only_owing=1) is None
    assert sales_row(tenant, as_of=d(-30))["total"] == 100.0


def test_a_customer_in_another_currency_never_adds_to_the_books_currency(tenant):
    customer(tenant, "Big Customer")
    invoice_for(tenant, "Big Customer", 100.0)
    invoice_for(tenant, "Big Customer", 9000.0, currency="INR")
    body = tenant.get("/api/ledger/sales").json()
    assert body["totals"]["balance"] == 100.0 and "INR" in body["other_currencies"]
    assert {r["currency"]: r["total"] for r in body["accounts"] if r["contact"] == "Big Customer"}["INR"] == 9000.0


def test_a_limit_is_only_compared_with_what_is_owed_in_the_limits_currency(tenant):
    customer(tenant, "Big Customer", credit_limit=500)
    invoice_for(tenant, "Big Customer", 9000.0, currency="INR")
    inr = next(r for r in tenant.get("/api/ledger/sales").json()["accounts"] if r["contact"] == "Big Customer" and r["currency"] == "INR")
    assert inr["credit_state"] == "no_limit"


def test_a_customers_account_page_has_its_statement_credit_and_open_invoices(tenant):
    c = customer(tenant, "Big Customer", credit_limit=250, account_ref="BC-1")
    invoice_for(tenant, "Big Customer", 100.0, issue=d(-40), due=d(-10))
    invoice_for(tenant, "Big Customer", 200.0, issue=d(-5), due=d(25))
    got = tenant.get(f"/api/ledger/sales/{c['id']}", params={"start": d(-60), "end": d(0)}).json()
    assert got["account"]["account_ref"] == "BC-1" and got["account"]["credit"]["state"] == "over_limit"
    assert got["account"]["credit"]["balance"] == 300.0 and got["account"]["credit"]["available"] == -50.0
    st = got["statements"][0]
    assert st["closing_balance"] == 300.0 and [l["kind"] for l in st["lines"]] == ["invoice", "invoice"]
    assert len(got["open_invoices"]) == 2 and got["ageing"][0]["overdue"] == 100.0 if "overdue" in got["ageing"][0] else got["ageing"][0]["1_30"] == 100.0


def test_a_customers_page_is_theirs_alone(tenant, client):
    c = customer(tenant, "Mine Co")
    from fastapi.testclient import TestClient
    with TestClient(main.app) as other:
        other.post("/api/client/register", json={"email": "rival4@example.com", "password": "Passw0rdTest", "company_name": "Rival"})
        other.post("/api/client/login", json={"email": "rival4@example.com", "password": "Passw0rdTest"})
        assert other.get(f"/api/ledger/sales/{c['id']}").status_code == 404
        assert other.get("/api/ledger/sales").json()["accounts"] == []


def test_the_sales_ledger_csv_has_the_figures_and_the_credit_position(tenant):
    customer(tenant, "Big Customer", credit_limit=1000, account_ref="BC-1")
    invoice_for(tenant, "Big Customer", 100.0)
    r = tenant.get("/api/ledger/sales.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    head, row = r.text.strip().splitlines()[:2]
    assert head.startswith("customer,account_ref,currency") and "Big Customer" in row and "BC-1" in row and "ok" in row


# --- warned before selling to them --------------------------------------------------------------
def test_before_selling_you_are_told_if_the_account_is_on_hold_or_would_go_over(tenant):
    customer(tenant, "Big Customer", credit_limit=500)
    invoice_for(tenant, "Big Customer", 300.0, due=d(10))
    ok = tenant.get("/api/ledger/credit-check", params={"name": "Big Customer", "amount": 100}).json()
    assert ok["known"] and ok["warnings"] == [] and ok["balance"] == 300.0 and ok["available"] == 200.0
    over = tenant.get("/api/ledger/credit-check", params={"name": "big customer", "amount": 250}).json()
    assert over["state"] == "over_limit" and "over their 500.00 credit limit" in over["warnings"][0] and "550.00" in over["warnings"][0]
    c = next(x for x in tenant.get("/api/contacts").json() if x["name"] == "Big Customer")
    tenant.put(f"/api/contacts/{c['id']}", json={"on_hold": True})
    held = tenant.get("/api/ledger/credit-check", params={"name": "Big Customer"}).json()
    assert held["on_hold"] is True and "on hold" in held["warnings"][0]


def test_a_check_on_someone_unknown_or_with_a_silly_amount_is_calm(tenant):
    assert tenant.get("/api/ledger/credit-check", params={"name": "Nobody"}).json() == {"known": False, "state": "unknown", "warnings": []}
    assert tenant.get("/api/ledger/credit-check").json()["known"] is False
    customer(tenant, "Big Customer", credit_limit=100)
    for amount in ("nan", "inf", "-5"):
        r = tenant.get("/api/ledger/credit-check", params={"name": "Big Customer", "amount": amount})
        assert r.status_code == 200 and r.json()["warnings"] == [], amount


# =====================================================================================
# The reports that read bills
# =====================================================================================

def test_a_supplier_credit_lowers_what_the_business_spent(tenant):
    bill(tenant, amount=100.0, issue="2026-01-05", due="2026-01-20")
    s = tenant.get("/api/suppliers").json()[0]
    assert tenant.get("/api/reports/profit-loss").json()["total_expenses"] == 100.0
    credit(tenant, s["id"], 30, issue_date="2026-01-25")
    r = tenant.get("/api/reports/profit-loss").json()
    assert r["total_expenses"] == 70.0 and r["months"] == ["2026-01"] and r["expenses"] == [70.0]


def test_a_void_bill_is_not_an_expense(tenant):
    b = bill(tenant, amount=100.0, issue="2026-01-05", due="2026-01-20")
    tenant.post(f"/api/bills/{b['id']}/void")
    assert tenant.get("/api/reports/profit-loss").json()["total_expenses"] == 0.0


def test_a_foreign_bill_is_reported_in_its_own_currency_not_the_books(tenant):
    bill(tenant, amount=100.0, issue="2026-01-05", due="2026-01-20")
    bill(tenant, vendor="Abroad", amount=900.0, currency="USD", issue="2026-01-06", due="2026-01-20")
    r = tenant.get("/api/reports/profit-loss").json()
    usd = next(x for x in r["other_currencies"] if x["currency"] == "USD")
    assert r["total_expenses"] == 100.0 and usd["total_expenses"] == 900.0


def test_money_out_is_counted_in_the_month_it_was_paid(tenant):
    b = bill(tenant, amount=100.0, issue="2026-01-05", due="2026-01-20")
    pay(tenant, b["id"], 40, "2026-02-10")
    pay(tenant, b["id"], 60, "2026-03-02")
    r = tenant.get("/api/reports/cash-summary").json()
    out = dict(zip(r["months"], r["money_out"]))
    assert out == {"2026-02": 40.0, "2026-03": 60.0}


def test_a_credit_set_against_a_bill_is_not_money_out(tenant):
    b = bill(tenant, amount=100.0, issue="2026-01-05", due="2026-01-20")
    c = credit(tenant, b["supplier_id"], 30, issue_date="2026-01-10")
    use_credit(tenant, c["id"], b["id"], 30)
    pay(tenant, b["id"], 70, "2026-01-30")
    r = tenant.get("/api/reports/cash-summary").json()
    assert sum(r["money_out"]) == 70.0
    assert tenant.get("/api/reports/balance-sheet").json()["liabilities"]["accounts_payable"] == 0.0


def test_the_balance_sheet_owes_suppliers_less_credit_not_yet_used(tenant):
    b = bill(tenant, amount=100.0, issue="2026-01-05", due="2026-01-20")
    assert tenant.get("/api/reports/balance-sheet").json()["liabilities"]["accounts_payable"] == 100.0
    credit(tenant, b["supplier_id"], 25, issue_date="2026-01-10")
    assert tenant.get("/api/reports/balance-sheet").json()["liabilities"]["accounts_payable"] == 75.0


# =====================================================================================
# The plan, and who may ask
# =====================================================================================

def set_plan(tenant, modules):
    cid = tenant.get("/api/client/me").json()["id"]
    with main.SessionLocal() as db:
        db.query(models.DBClient).filter(models.DBClient.id == cid).update({"modules": modules})
        db.commit()


def test_the_ledgers_belong_to_the_invoicing_plan(tenant):
    for path in ("/api/suppliers", "/api/suppliers/1", "/api/supplier-credit-notes", "/api/ledger/purchases", "/api/ledger/sales", "/api/ledger/credit-check"):
        assert main.module_for_path(path) == "invoicing", path
    set_plan(tenant, "hr")
    for method, path in (("get", "/api/suppliers"), ("post", "/api/suppliers"), ("get", "/api/ledger/purchases"), ("get", "/api/ledger/sales"),
                         ("get", "/api/supplier-credit-notes"), ("get", "/api/ledger/credit-check")):
        assert getattr(tenant, method)(path).status_code == 403, path
    set_plan(tenant, "invoicing")
    assert tenant.get("/api/ledger/purchases").status_code == 200


def test_every_ledger_endpoint_needs_a_login(client):
    for method, path in (("get", "/api/suppliers"), ("post", "/api/suppliers"), ("put", "/api/suppliers/1"), ("delete", "/api/suppliers/1"),
                         ("get", "/api/supplier-credit-notes"), ("post", "/api/supplier-credit-notes/1/allocate"),
                         ("get", "/api/ledger/purchases"), ("get", "/api/ledger/purchases.csv"), ("get", "/api/ledger/purchases/1"),
                         ("get", "/api/ledger/purchases/1/ledger.csv"), ("get", "/api/ledger/sales"), ("get", "/api/ledger/sales.csv"),
                         ("get", "/api/ledger/sales/1"), ("get", "/api/ledger/credit-check"), ("delete", "/api/bills/1/payments/1"),
                         ("post", "/api/bills/1/void"), ("post", "/api/bills/post-drafts")):
        assert getattr(client, method)(path).status_code in (401, 403), path
    # Validated before sign-in is checked, so it is sent whole: refused all the same.
    assert client.post("/api/supplier-credit-notes", json={"vendor_name": "X", "amount": 5}).status_code in (401, 403)
    assert client.post("/api/bills/1/payments", json={"amount": 5}).status_code in (401, 403)


def test_a_read_only_member_can_read_the_ledgers_but_not_change_them(client, tenant):
    from test_team import invite, set_their_password, sign_in_as
    b = bill(tenant, amount=10.0)
    s = supplier(tenant, "Readable")
    member, email = invite(tenant, role="viewer")
    raw = set_their_password(member["id"])
    client.post("/api/client/reset-password", json={"token": raw, "password": "Colleague123"})
    sign_in_as(client, email)
    for path in ("/api/ledger/purchases", "/api/ledger/sales", "/api/suppliers", "/api/supplier-credit-notes", f"/api/bills/{b['id']}"):
        assert client.get(path).status_code == 200, path
    for method, path, body in (("post", "/api/suppliers", {"name": "X"}), ("put", f"/api/suppliers/{s['id']}", {"name": "Y"}),
                               ("post", f"/api/bills/{b['id']}/payments", {"amount": 1}), ("post", f"/api/bills/{b['id']}/pay", {}),
                               ("post", "/api/supplier-credit-notes", {"vendor_name": "Readable", "amount": 5}), ("post", f"/api/bills/{b['id']}/void", {}),
                               ("post", "/api/bills/post-drafts", {}), ("delete", f"/api/bills/{b['id']}", None)):
        res = getattr(client, method)(path, json=body) if body is not None else getattr(client, method)(path)
        assert res.status_code == 403 and "read-only" in res.json()["detail"].lower(), (method, path, res.status_code)


# =====================================================================================
# The migration
# =====================================================================================

def test_the_migration_turns_bill_names_into_suppliers_once_and_links_the_bills(tenant):
    cid = tenant.get("/api/client/me").json()["id"]
    with main.SessionLocal() as db:
        for i, name in enumerate(["Acme Ltd", "acme ltd ", "ACME LTD", "Zed", "", "  "]):
            db.add(models.DBBill(client_id=cid, number=f"OLD-{i}", vendor_name=name, vendor_email="a@acme.test" if "cme" in name.lower() else "",
                                 issue_date=d(-5), due_date=d(5), amount=10, total=10, status="Awaiting Payment"))
        db.commit()
        for stmt in database.SUPPLIER_BACKFILL:
            db.execute(main.text(stmt) if hasattr(main, "text") else __import__("sqlalchemy").text(stmt))
        db.commit()
        sup = db.query(models.DBSupplier).filter(models.DBSupplier.client_id == cid).all()
        assert sorted((s.name or "").lower() for s in sup) == ["acme ltd", "zed"]
        by = {b.number: b.supplier_id for b in db.query(models.DBBill).filter(models.DBBill.client_id == cid).all()}
        acme = next(s for s in sup if s.name.lower() == "acme ltd")
        assert by["OLD-0"] == by["OLD-1"] == by["OLD-2"] == acme.id and by["OLD-3"] is not None and by["OLD-4"] is None and by["OLD-5"] is None
        assert acme.email == "a@acme.test" and acme.active is True and acme.on_hold is False
        before = (len(sup), dict(by))
        for stmt in database.SUPPLIER_BACKFILL:                 # a second run changes nothing
            db.execute(__import__("sqlalchemy").text(stmt))
        db.commit()
        again = db.query(models.DBSupplier).filter(models.DBSupplier.client_id == cid).count()
        assert again == before[0]
        assert {b.number: b.supplier_id for b in db.query(models.DBBill).filter(models.DBBill.client_id == cid).all()} == before[1]


def test_the_migration_keeps_one_business_apart_from_another(tenant, client):
    mine = tenant.get("/api/client/me").json()["id"]
    from fastapi.testclient import TestClient
    with TestClient(main.app) as other:
        other.post("/api/client/register", json={"email": "rival5@example.com", "password": "Passw0rdTest", "company_name": "Rival"})
        other.post("/api/client/login", json={"email": "rival5@example.com", "password": "Passw0rdTest"})
        theirs = other.get("/api/client/me").json()["id"]
    sa = __import__("sqlalchemy")
    with main.SessionLocal() as db:
        for cid in (mine, theirs):
            db.add(models.DBBill(client_id=cid, number="OLD-1", vendor_name="Same Name", issue_date=d(-5), due_date=d(5), amount=1, total=1, status="Awaiting Payment"))
        db.commit()
        for stmt in database.SUPPLIER_BACKFILL:
            db.execute(sa.text(stmt))
        db.commit()
        rows = db.query(models.DBSupplier).filter(models.DBSupplier.name == "Same Name").all()
        assert sorted(r.client_id for r in rows) == sorted([mine, theirs])
        for cid in (mine, theirs):
            sid = db.query(models.DBSupplier.id).filter(models.DBSupplier.client_id == cid, models.DBSupplier.name == "Same Name").scalar()
            assert db.query(models.DBBill).filter(models.DBBill.client_id == cid).first().supplier_id == sid
