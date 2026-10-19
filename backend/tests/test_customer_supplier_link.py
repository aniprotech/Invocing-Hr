"""A business that is both a customer and a supplier.

They were two records that knew nothing of each other: what the business
owed them and what they owed the business were on two screens, and the net
was for somebody to work out. The accounts stay separate - the books keep
them that way - but each now names the other, with both balances and the net.
"""
from datetime import date, timedelta

import pytest

import main
from conftest import make_invoice


@pytest.fixture(autouse=True)
def _reset():
    main.rate_limiter._hits.clear()
    yield


def d(n):
    return (date.today() + timedelta(days=n)).isoformat()


def contact(tenant, name):
    r = tenant.post("/api/contacts", json={"name": name, "email": "x@example.com"})
    assert r.status_code == 200, r.text
    return r.json()


def supplier(tenant, name, **kw):
    r = tenant.post("/api/suppliers", json={"name": name, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def sell(tenant, name, amount):
    return make_invoice(tenant, status="Awaiting Payment", contact=name, currency="GBP", issue_date=d(-5), due_date=d(20),
                        line_items=[{"description": "Work", "qty": 1, "price": amount, "tax_rate": "No Tax"}])


def buy(tenant, supplier_id, amount):
    r = tenant.post("/api/bills", json={"supplier_id": supplier_id, "amount": amount, "issue_date": d(-5), "due_date": d(20)})
    assert r.status_code == 200, r.text


def test_a_linked_supplier_and_customer_show_each_other_and_the_net(tenant):
    c = contact(tenant, "Harbour Ltd")
    s = supplier(tenant, "Harbour Trading", contact_id=c["id"])
    assert s["contact_id"] == c["id"]
    sell(tenant, "Harbour Ltd", 500)
    buy(tenant, s["id"], 200)
    p = tenant.get(f"/api/ledger/purchases/{s['id']}").json()["also_customer"]
    assert p["contact_id"] == c["id"] and p["how"] == "linked"
    assert p["position"] == [{"currency": "GBP", "they_owe_us": 500.0, "we_owe_them": 200.0, "net": 300.0}]
    q = tenant.get(f"/api/ledger/sales/{c['id']}").json()["also_supplier"]
    assert q["supplier_id"] == s["id"] and q["how"] == "linked" and q["position"][0]["net"] == 300.0


def test_the_same_name_is_matched_when_nothing_is_linked(tenant):
    c = contact(tenant, "Quay Co")
    s = supplier(tenant, "quay co")
    buy(tenant, s["id"], 80)
    p = tenant.get(f"/api/ledger/purchases/{s['id']}").json()["also_customer"]
    assert p["how"] == "same_name" and p["position"] == [{"currency": "GBP", "they_owe_us": 0.0, "we_owe_them": 80.0, "net": -80.0}]
    assert tenant.get(f"/api/ledger/sales/{c['id']}").json()["also_supplier"]["supplier_id"] == s["id"]


def test_an_explicit_link_wins_over_a_same_name_match(tenant):
    a = contact(tenant, "Pier Ltd")
    contact(tenant, "Other Ltd")
    s = supplier(tenant, "Other Ltd", contact_id=a["id"])
    assert tenant.get(f"/api/ledger/purchases/{s['id']}").json()["also_customer"]["contact_id"] == a["id"]


def test_nothing_in_common_shows_nothing(tenant):
    c = contact(tenant, "Lonely Ltd")
    s = supplier(tenant, "Solo Supplies")
    assert tenant.get(f"/api/ledger/purchases/{s['id']}").json()["also_customer"] is None
    assert tenant.get(f"/api/ledger/sales/{c['id']}").json()["also_supplier"] is None


def test_a_link_can_be_removed(tenant):
    c = contact(tenant, "Dock Ltd")
    s = supplier(tenant, "Dock Supplies", contact_id=c["id"])
    r = tenant.put(f"/api/suppliers/{s['id']}", json={"contact_id": None})
    assert r.status_code == 200 and r.json()["contact_id"] is None
    assert tenant.get(f"/api/ledger/purchases/{s['id']}").json()["also_customer"] is None


@pytest.mark.parametrize("bad,says", [("abc", "Pick one of your customers"), (999999, "not one of yours")])
def test_a_link_must_be_to_one_of_your_customers(tenant, bad, says):
    r = tenant.post("/api/suppliers", json={"name": "Odd Co", "contact_id": bad})
    assert r.status_code == 400 and says in r.json()["detail"]


def test_one_customer_is_linked_to_one_supplier(tenant):
    c = contact(tenant, "Wharf Ltd")
    supplier(tenant, "Wharf A", contact_id=c["id"])
    r = tenant.post("/api/suppliers", json={"name": "Wharf B", "contact_id": c["id"]})
    assert r.status_code == 400 and "already linked to the supplier Wharf A" in r.json()["detail"]


def test_a_same_name_match_does_not_steal_a_customer_already_linked_elsewhere(tenant):
    c = contact(tenant, "Jetty Ltd")
    linked = supplier(tenant, "Jetty Holdings", contact_id=c["id"])
    namesake = supplier(tenant, "Jetty Ltd")
    assert tenant.get(f"/api/ledger/purchases/{namesake['id']}").json()["also_customer"] is None
    assert tenant.get(f"/api/ledger/sales/{c['id']}").json()["also_supplier"]["supplier_id"] == linked["id"]


def test_another_businesses_customer_cannot_be_linked(tenant, client):
    from fastapi.testclient import TestClient
    with TestClient(main.app) as other:
        other.post("/api/client/register", json={"email": "rival-link@example.com", "password": "Passw0rdTest", "company_name": "Rival"})
        other.post("/api/client/login", json={"email": "rival-link@example.com", "password": "Passw0rdTest"})
        theirs = other.post("/api/contacts", json={"name": "Their Customer"}).json()
    r = tenant.post("/api/suppliers", json={"name": "Mine", "contact_id": theirs["id"]})
    assert r.status_code == 400 and "not one of yours" in r.json()["detail"]
