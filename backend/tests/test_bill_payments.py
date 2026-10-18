"""Paying supplier bills: part and full payments, the ledger behind a bill's
running total, and the Payments list across every bill. Nothing crosses a
business."""
from datetime import date, timedelta

import pytest

import main


@pytest.fixture(autouse=True)
def _reset():
    main.rate_limiter._hits.clear()
    yield


def d(n):
    return (date.today() + timedelta(days=n)).isoformat()


def bill(tenant, number="B-1", vendor="Paper Co", total=100.0, status="Unpaid", due=10):
    res = tenant.post("/api/bills", json={"number": number, "vendor_name": vendor, "issue_date": d(-5), "due_date": d(due),
                                          "amount": total, "tax_amount": 0, "total": total, "status": status})
    assert res.status_code == 200, res.text
    return res.json()["id"]


def pay(tenant, bill_id, amount, **kw):
    return tenant.post(f"/api/bills/{bill_id}/payments", json=dict({"amount": amount, "paid_on": d(0)}, **kw))


def status(tenant, bill_id):
    return tenant.get(f"/api/bills/{bill_id}").json()


def test_a_part_payment_then_the_rest(tenant):
    b = bill(tenant)
    r = pay(tenant, b, 40, reference="BACS-1")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "Partially Paid" and r.json()["outstanding"] == 60.0
    assert status(tenant, b)["amount_paid"] == 40.0 and status(tenant, b)["status"] == "Partially Paid"
    r = pay(tenant, b, 60)
    assert r.json()["status"] == "Paid" and r.json()["outstanding"] == 0.0
    ledger = tenant.get(f"/api/bills/{b}/payments").json()
    assert ledger["paid"] == 100.0 and ledger["outstanding"] == 0.0 and len(ledger["payments"]) == 2
    assert ledger["payments"][1]["reference"] == "BACS-1"


@pytest.mark.parametrize("body,why", [
    ({"amount": 0}, "more than nothing"),
    ({"amount": -5}, "more than nothing"),
    ({"amount": 101}, "more than the"),
    ({"amount": 10, "method": "barter"}, "how it was paid"),
    ({"amount": 10, "paid_on": "yesterday"}, "YYYY-MM-DD"),
    ({"amount": 10, "account_id": 999999}, "not one of yours"),
])
def test_bad_payments_are_refused_with_a_reason(tenant, body, why):
    b = bill(tenant)
    r = tenant.post(f"/api/bills/{b}/payments", json=body)
    assert r.status_code == 400 and why in r.json()["detail"], r.text
    assert status(tenant, b)["amount_paid"] == 0.0


def test_a_paid_bill_takes_no_more(tenant):
    b = bill(tenant)
    pay(tenant, b, 100)
    r = pay(tenant, b, 1)
    assert r.status_code == 400 and "nothing left" in r.json()["detail"]


def test_one_click_pay_records_a_real_payment_for_what_is_left(tenant):
    b = bill(tenant)
    pay(tenant, b, 30)
    assert tenant.post(f"/api/bills/{b}/pay").json() == {"ok": True, "status": "Paid"}
    ledger = tenant.get(f"/api/bills/{b}/payments").json()
    assert [p["amount"] for p in ledger["payments"]] == [70.0, 30.0] and ledger["outstanding"] == 0.0
    assert status(tenant, b)["status"] == "Paid"
    assert tenant.post(f"/api/bills/{b}/pay").json()["status"] == "Paid"          # idempotent
    assert len(tenant.get(f"/api/bills/{b}/payments").json()["payments"]) == 2


def test_a_payment_can_be_reversed(tenant):
    b = bill(tenant)
    p1 = pay(tenant, b, 40).json()["payment_id"]
    pay(tenant, b, 60)
    r = tenant.delete(f"/api/bills/{b}/payments/{p1}")
    assert r.status_code == 200 and r.json()["status"] == "Partially Paid" and r.json()["outstanding"] == 40.0
    p2 = tenant.get(f"/api/bills/{b}/payments").json()["payments"][0]["id"]
    assert tenant.delete(f"/api/bills/{b}/payments/{p2}").json()["status"] == "Unpaid"
    assert status(tenant, b)["amount_paid"] == 0.0
    assert tenant.delete(f"/api/bills/{b}/payments/{p2}").status_code == 404


def test_the_payments_list_filters_and_totals(tenant):
    a = bill(tenant, "B-1", "Paper Co", 100)
    c = bill(tenant, "B-2", "Tea Ltd", 50)
    pay(tenant, a, 100, paid_on=d(-20), method="card", reference="VISA-9")
    pay(tenant, c, 20, paid_on=d(-2))
    pay(tenant, c, 30, paid_on=d(-1), method="cash")
    got = tenant.get("/api/bill-payments").json()
    assert got["count"] == 3 and got["total"] == 150.0
    assert [p["paid_on"] for p in got["payments"]] == [d(-1), d(-2), d(-20)], "newest first"
    assert got["payments"][0]["supplier"] == "Tea Ltd" and got["payments"][0]["bill_number"] == "B-2"
    assert tenant.get("/api/bill-payments", params={"q": "paper"}).json()["count"] == 1
    assert tenant.get("/api/bill-payments", params={"q": "visa"}).json()["count"] == 1
    assert tenant.get("/api/bill-payments", params={"start": d(-3)}).json()["total"] == 50.0
    assert tenant.get("/api/bill-payments", params={"end": d(-10)}).json()["total"] == 100.0
    assert tenant.get("/api/bill-payments", params={"method": "cash"}).json()["total"] == 30.0
    assert tenant.get("/api/bill-payments", params={"start": "x"}).status_code == 400
    assert tenant.get("/api/bill-payments", params={"method": "barter"}).status_code == 400
    csv = tenant.get("/api/bill-payments.csv").text.strip().splitlines()
    assert csv[0].startswith("Date,Supplier,Bill,Amount") and len(csv) == 4


def test_paying_from_one_of_your_accounts_names_it(tenant):
    acct = tenant.post("/api/accounts", json={"name": "Current account", "kind": "bank"})
    assert acct.status_code == 200, acct.text
    aid = acct.json().get("id") or acct.json().get("account", {}).get("id")
    b = bill(tenant)
    pay(tenant, b, 10, account_id=aid)
    assert tenant.get("/api/bill-payments").json()["payments"][0]["account"] == "Current account"


def test_nothing_crosses_a_business(client, account):
    tenant = account["client"]
    b = bill(tenant)
    p = pay(tenant, b, 10).json()["payment_id"]
    other = f"other-{account['email']}"
    client.post("/api/client/register", json={"email": other, "password": "Passw0rdTest", "company_name": "Other Co"})
    client.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})
    assert client.get("/api/bill-payments").json()["count"] == 0
    assert client.get(f"/api/bills/{b}/payments").status_code == 404
    assert client.post(f"/api/bills/{b}/payments", json={"amount": 5}).status_code == 404
    assert client.delete(f"/api/bills/{b}/payments/{p}").status_code == 404
    assert client.post(f"/api/bills/{b}/pay").status_code == 404
    client.cookies.clear()
    assert client.get("/api/bill-payments").status_code == 401
