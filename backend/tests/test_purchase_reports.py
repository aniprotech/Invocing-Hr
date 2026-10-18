"""Purchase reports: who you owe and for how long, and where the money went.
Counted on the server; nothing crosses a business."""
from datetime import date, timedelta

import pytest

import main


@pytest.fixture(autouse=True)
def _reset():
    main.rate_limiter._hits.clear()
    yield


def d(n):
    return (date.today() + timedelta(days=n)).isoformat()


def bill(tenant, number, vendor, total, issued, due, status="Unpaid", category="general"):
    res = tenant.post("/api/bills", json={"number": number, "vendor_name": vendor, "issue_date": issued, "due_date": due,
                                          "amount": total, "tax_amount": 0, "total": total, "status": status, "category": category})
    assert res.status_code == 200, res.text
    return res.json()["id"]


def test_the_new_purchases_endpoints_need_the_invoicing_plan():
    for path in ("/api/bill-payments", "/api/bill-payments.csv", "/api/supplier-credit-notes", "/api/supplier-credit-notes/3/allocate",
                 "/api/purchase-orders", "/api/purchase-orders/3/bill", "/api/business-expenses", "/api/business-expenses.csv",
                 "/api/recurring-bills", "/api/purchases/reports/spend", "/api/purchases/suppliers", "/api/bills/3/payments"):
        assert main.module_for_path(path) == "invoicing", path


def test_ageing_buckets_what_is_owed_by_how_late(tenant):
    bill(tenant, "B-1", "Paper Co", 100, d(-90), d(-70))          # 70 days late
    bill(tenant, "B-2", "Paper Co", 50, d(-40), d(-10))           # 10 days late
    bill(tenant, "B-3", "Tea Ltd", 30, d(-5), d(20))              # not yet due
    bill(tenant, "B-4", "Tea Ltd", 999, d(-5), d(-3), status="Draft")      # a draft is not owed
    paid = bill(tenant, "B-5", "Tea Ltd", 40, d(-60), d(-30))
    tenant.post(f"/api/bills/{paid}/payments", json={"amount": 40, "paid_on": d(-1)})     # paid yesterday
    got = tenant.get("/api/purchases/reports/ageing").json()
    assert got["buckets"] == {"current": 30.0, "1_30": 50.0, "31_60": 0.0, "61_90": 100.0, "over_90": 0.0}
    assert got["total_outstanding"] == 180.0
    assert [s["name"] for s in got["suppliers"]] == ["Paper Co", "Tea Ltd"]
    paper = got["suppliers"][0]
    assert (paper["bills"], paper["total"], paper["61_90"], paper["1_30"], paper["oldest_days"]) == (2, 150.0, 100.0, 50.0, 70)
    assert [b["number"] for b in got["bills"]] == ["B-1", "B-2", "B-3"], "oldest first, the paid and the draft left out"
    assert got["bills"][0]["bucket"] == "61_90" and got["bills"][0]["days_overdue"] == 70


def test_ageing_as_of_a_past_day_counts_payments_by_their_date(tenant):
    b = bill(tenant, "B-1", "Paper Co", 100, d(-60), d(-40))
    tenant.post(f"/api/bills/{b}/payments", json={"amount": 100, "paid_on": d(-10)})
    now = tenant.get("/api/purchases/reports/ageing").json()
    then = tenant.get("/api/purchases/reports/ageing", params={"as_of": d(-20)}).json()
    assert now["total_outstanding"] == 0.0
    assert then["total_outstanding"] == 100.0 and then["buckets"]["1_30"] == 100.0, "then, it was 20 days late and unpaid"
    assert tenant.get("/api/purchases/reports/ageing", params={"as_of": d(-70)}).json()["total_outstanding"] == 0.0, "not yet issued"
    assert tenant.get("/api/purchases/reports/ageing", params={"as_of": "x"}).status_code == 400


def test_a_bill_paid_before_payments_were_kept_counts_as_paid(tenant):
    b = bill(tenant, "B-1", "Old Co", 100, d(-30), d(-5))
    tenant.put(f"/api/bills/{b}", json={"amount_paid": 100, "status": "Paid"})        # no payment record behind it
    assert tenant.get("/api/purchases/reports/ageing").json()["total_outstanding"] == 0.0


def test_ageing_csv_by_supplier_and_by_bill(tenant):
    bill(tenant, "B-1", "Paper Co", 100, d(-40), d(-10))
    by_supplier = tenant.get("/api/purchases/reports/ageing.csv").text.strip().splitlines()
    assert by_supplier[0].startswith("supplier,bills,current") and by_supplier[1].startswith("Paper Co,1,")
    detail = tenant.get("/api/purchases/reports/ageing.csv", params={"detail": 1}).text.strip().splitlines()
    assert detail[0].startswith("bill,supplier,issued") and detail[1].startswith("B-1,Paper Co,")


def seed_spend(tenant):
    bill(tenant, "B-1", "Paper Co", 100, d(-3), d(10), category="office")
    bill(tenant, "B-2", "Paper  Co ", 50, d(-2), d(10), category="office")
    bill(tenant, "B-3", "Landlord", 400, d(-1), d(10), category="rent")
    bill(tenant, "B-4", "Draft Ltd", 999, d(-1), d(10), status="Draft", category="rent")
    bill(tenant, "B-5", "Old Co", 70, d(-200), d(-190), category="travel")                 # outside the range below
    tenant.post("/api/business-expenses", json={"spent_on": d(-2), "payee": "Paper Co", "category": "office", "amount": 20, "tax_amount": 0})
    tenant.post("/api/business-expenses", json={"spent_on": d(-1), "payee": "Cafe", "category": "travel", "amount": 30, "tax_amount": 0})
    tenant.post("/api/supplier-credit-notes", json={"vendor_name": "Paper Co", "amount": 25, "issue_date": d(-1)})
    void = tenant.post("/api/supplier-credit-notes", json={"vendor_name": "Paper Co", "amount": 500, "issue_date": d(-1)}).json()
    tenant.post(f"/api/supplier-credit-notes/{void['id']}/void", json={})


def test_spend_by_supplier_category_and_month(tenant):
    seed_spend(tenant)
    got = tenant.get("/api/purchases/reports/spend", params={"start": d(-30), "end": d(0)}).json()
    assert got["summary"] == {"bills": 550.0, "expenses": 50.0, "credits": 25.0, "net": 575.0}, "drafts, voided credits and old bills left out"
    sup = {s["name"]: s for s in got["by_supplier"]}
    assert (sup["Paper Co"]["bills"], sup["Paper Co"]["expenses"], sup["Paper Co"]["credits"], sup["Paper Co"]["net"]) == (150.0, 20.0, 25.0, 145.0)
    assert [s["name"] for s in got["by_supplier"]] == ["Landlord", "Paper Co", "Cafe"], "biggest net spend first, spellings merged"
    cats = {c["name"]: c for c in got["by_category"]}
    assert (cats["office"]["bills"], cats["office"]["expenses"], cats["office"]["net"]) == (150.0, 20.0, 170.0)
    assert cats["rent"]["net"] == 400.0 and cats["travel"]["net"] == 30.0 and "credits" not in cats["office"]
    assert sum(m["net"] for m in got["by_month"]) == 575.0 and got["by_month"] == sorted(got["by_month"], key=lambda m: m["name"])


def test_spend_range_defaults_and_is_checked(tenant):
    seed_spend(tenant)
    assert tenant.get("/api/purchases/reports/spend").json()["start"] == date.today().replace(month=1, day=1).isoformat()
    wide = tenant.get("/api/purchases/reports/spend", params={"start": d(-400), "end": d(0)}).json()
    assert wide["summary"]["bills"] == 620.0, "the old bill is inside a wider range"
    assert tenant.get("/api/purchases/reports/spend", params={"start": d(0), "end": d(-5)}).status_code == 400
    assert tenant.get("/api/purchases/reports/spend", params={"start": "x"}).status_code == 400


def test_spend_csv_views(tenant):
    seed_spend(tenant)
    p = {"start": d(-30), "end": d(0)}
    sup = tenant.get("/api/purchases/reports/spend.csv", params=p).text.strip().splitlines()
    assert sup[0] == "supplier,bills,expenses,credits,net" and sup[1].startswith("Landlord,400.0")
    cat = tenant.get("/api/purchases/reports/spend.csv", params=dict(p, view="category")).text.strip().splitlines()
    assert cat[0] == "category,bills,expenses,total" and len(cat) == 4
    mon = tenant.get("/api/purchases/reports/spend.csv", params=dict(p, view="month")).text.strip().splitlines()
    assert mon[0] == "month,bills,expenses,credits,net"
    assert tenant.get("/api/purchases/reports/spend.csv", params=dict(p, view="weather")).status_code == 400


def test_nothing_crosses_a_business(client, account):
    tenant = account["client"]
    seed_spend(tenant)
    other = f"other-{account['email']}"
    client.post("/api/client/register", json={"email": other, "password": "Passw0rdTest", "company_name": "Other Co"})
    client.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})
    assert client.get("/api/purchases/reports/ageing").json()["total_outstanding"] == 0.0
    assert client.get("/api/purchases/reports/spend", params={"start": d(-30)}).json()["summary"]["net"] == 0.0
    assert client.get("/api/purchases/reports/spend.csv", params={"start": d(-30)}).text.strip().count("\n") == 0
    client.cookies.clear()
    assert client.get("/api/purchases/reports/ageing").status_code == 401
    assert client.get("/api/purchases/reports/spend").status_code == 401
