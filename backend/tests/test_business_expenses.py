"""Business expenses: money already spent that did not come as a supplier
bill - recorded, found, totalled, exported. Not the staff claims under People."""
from datetime import date, timedelta

import pytest

import main


@pytest.fixture(autouse=True)
def _reset():
    main.rate_limiter._hits.clear()
    yield


def d(n):
    return (date.today() + timedelta(days=n)).isoformat()


def spend(tenant, **kw):
    payload = {"spent_on": d(0), "payee": "Stationers", "description": "Pens", "category": "office", "amount": 10.0,
               "tax_amount": 2.0, "method": "card", "reference": "RCPT-1"}
    payload.update(kw)
    res = tenant.post("/api/business-expenses", json=payload)
    assert res.status_code == 200, res.text
    return res.json()


def test_an_expense_is_recorded_with_its_total(tenant):
    e = spend(tenant)
    assert (e["total"], e["category"], e["method"], e["payee"], e["spent_on"]) == (12.0, "office", "card", "Stationers", d(0))
    assert spend(tenant, spent_on="")["spent_on"] == d(0), "no date means today"


@pytest.mark.parametrize("change,why", [
    ({"payee": " ", "description": ""}, "who it was paid to"),
    ({"amount": 0}, "more than nothing"),
    ({"tax_amount": -1}, "negative"),
    ({"spent_on": "lunchtime"}, "YYYY-MM-DD"),
    ({"category": "yachts"}, "category"),
    ({"method": "barter"}, "how it was paid"),
    ({"account_id": 999999}, "not one of yours"),
])
def test_bad_expenses_are_refused_with_a_reason(tenant, change, why):
    payload = {"payee": "X", "amount": 5}
    payload.update(change)
    r = tenant.post("/api/business-expenses", json=payload)
    assert r.status_code == 400 and why in r.json()["detail"], r.text


def test_either_a_payee_or_a_description_will_do(tenant):
    assert spend(tenant, payee="", description="Parking")["description"] == "Parking"
    assert spend(tenant, payee="Cafe", description="")["payee"] == "Cafe"


def test_an_expense_can_be_edited_and_deleted(tenant):
    e = spend(tenant)
    r = tenant.put(f"/api/business-expenses/{e['id']}", json={"payee": "Other", "amount": 20, "tax_amount": 0, "category": "travel", "method": "cash"})
    assert r.status_code == 200 and (r.json()["payee"], r.json()["total"], r.json()["category"], r.json()["method"]) == ("Other", 20.0, "travel", "cash")
    assert tenant.put(f"/api/business-expenses/{e['id']}", json={"payee": "", "amount": 5}).status_code == 400
    assert tenant.delete(f"/api/business-expenses/{e['id']}").status_code == 200
    assert tenant.delete(f"/api/business-expenses/{e['id']}").status_code == 404
    assert tenant.get("/api/business-expenses").json()["count"] == 0


def test_the_list_filters_totals_and_splits_by_category(tenant):
    spend(tenant, spent_on=d(-40), payee="Old Cafe", category="travel", amount=50, tax_amount=0, reference="OLD-1")
    spend(tenant, spent_on=d(-3), payee="Stationers", category="office", amount=10, tax_amount=2)
    spend(tenant, spent_on=d(-1), payee="Landlord", description="Deposit", category="rent", amount=100, tax_amount=0)
    got = tenant.get("/api/business-expenses").json()
    assert got["count"] == 3 and got["total"] == 162.0
    assert [e["payee"] for e in got["expenses"]] == ["Landlord", "Stationers", "Old Cafe"], "newest first"
    assert got["by_category"] == {"rent": 100.0, "office": 12.0, "travel": 50.0}
    assert "rent" in got["categories"] and "card" in got["methods"]
    g = lambda **p: tenant.get("/api/business-expenses", params=p).json()
    assert g(start=d(-5))["total"] == 112.0 and g(end=d(-10))["total"] == 50.0
    assert g(category="office")["count"] == 1 and g(q="deposit")["count"] == 1 and g(q="old-1")["count"] == 1
    assert tenant.get("/api/business-expenses", params={"start": "x"}).status_code == 400
    assert tenant.get("/api/business-expenses", params={"category": "yachts"}).status_code == 400
    csv = tenant.get("/api/business-expenses.csv", params={"start": d(-5)}).text.strip().splitlines()
    assert csv[0].startswith("Date,Paid to,Description,Category") and len(csv) == 3


def test_paying_from_one_of_your_accounts_names_it(tenant):
    acct = tenant.post("/api/accounts", json={"name": "Company card", "kind": "bank"}).json()
    aid = acct.get("id") or acct.get("account", {}).get("id")
    e = spend(tenant, account_id=aid)
    assert e["account"] == "Company card" and tenant.get("/api/business-expenses").json()["expenses"][0]["account"] == "Company card"


def test_nothing_crosses_a_business(client, account):
    tenant = account["client"]
    e = spend(tenant)
    other = f"other-{account['email']}"
    client.post("/api/client/register", json={"email": other, "password": "Passw0rdTest", "company_name": "Other Co"})
    client.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})
    assert client.get("/api/business-expenses").json()["count"] == 0
    assert client.put(f"/api/business-expenses/{e['id']}", json={"payee": "x", "amount": 1}).status_code == 404
    assert client.delete(f"/api/business-expenses/{e['id']}").status_code == 404
    assert client.get("/api/business-expenses.csv").text.strip().count("\n") == 0
    client.cookies.clear()
    assert client.get("/api/business-expenses").status_code == 401
    assert client.post("/api/business-expenses", json={"payee": "x", "amount": 1}).status_code == 401
