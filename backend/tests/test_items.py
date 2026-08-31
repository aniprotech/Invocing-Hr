"""Things the business sells, saved once and reused.

Every invoice line was typed from scratch, so the same product got a slightly
different name, price and account each time somebody billed it - and nothing
could report on what was actually being sold.

The rules worth holding down are the ones that decide whether the catalogue
stays usable: a code is a handle, so it has to be unique and matched the way
people type it; and an item that has been billed is retired rather than
deleted, because old invoices have to keep meaning what they said.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


def add_item(tenant, **overrides):
    body = {"code": "BMW", "name": "BMW hire", "sale_price": 250,
            "sale_account": "200 - Sales", "description": "Daily hire"}
    body.update(overrides)
    res = tenant.post("/api/items", json=body)
    assert res.status_code == 200, res.text
    return res.json()


def codes(tenant, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    res = tenant.get("/api/items" + ("?" + query if query else ""))
    assert res.status_code == 200, res.text
    return [i["code"] for i in res.json()["items"]]


# --- keeping the catalogue ---------------------------------------------------
def test_an_item_can_be_saved_and_listed(tenant):
    add_item(tenant)
    assert codes(tenant) == ["BMW"]


def test_what_was_saved_comes_back(tenant):
    item = add_item(tenant, sale_price=250.5)
    assert item["name"] == "BMW hire"
    assert item["sale_price"] == 250.5
    assert item["sale_account"] == "200 - Sales"
    assert item["is_sold"] is True
    assert item["is_purchased"] is False


def test_an_item_needs_a_code(tenant):
    """It is the handle people type; without one there is nothing to find."""
    assert tenant.post("/api/items", json={"code": "   ", "name": "X"}).status_code == 400


def test_the_same_code_cannot_be_used_twice(tenant):
    add_item(tenant)
    res = tenant.post("/api/items", json={"code": "BMW", "name": "Something else"})
    assert res.status_code == 400
    assert "BMW" in res.json()["detail"], "it should say which code is taken"


def test_the_same_code_in_a_different_case_is_the_same_code(tenant):
    """Two of them means two of everything in every report that follows."""
    add_item(tenant)
    assert tenant.post("/api/items", json={"code": "bmw"}).status_code == 400


def test_a_trailing_space_does_not_make_a_second_item(tenant):
    """Invisible in the box, and would let the same code exist twice."""
    add_item(tenant)
    assert tenant.post("/api/items", json={"code": "BMW "}).status_code == 400


@pytest.mark.parametrize("price", [-1, "free"])
def test_a_price_that_is_not_a_price_is_refused(tenant, price):
    assert tenant.post("/api/items", json={
        "code": f"X{uuid.uuid4().hex[:6]}", "sale_price": price}).status_code == 400


def test_an_item_can_be_edited(tenant):
    item = add_item(tenant)
    res = tenant.put(f"/api/items/{item['id']}",
                     json={"name": "BMW daily hire", "sale_price": 275})
    assert res.status_code == 200, res.text
    assert res.json()["name"] == "BMW daily hire"
    assert res.json()["sale_price"] == 275


def test_editing_cannot_take_a_code_another_item_already_has(tenant):
    add_item(tenant)
    other = add_item(tenant, code="AUDI", name="Audi hire")
    res = tenant.put(f"/api/items/{other['id']}", json={"code": "BMW"})
    assert res.status_code == 400


def test_an_item_can_keep_its_own_code_when_edited(tenant):
    """Renaming without changing the code must not collide with itself."""
    item = add_item(tenant)
    res = tenant.put(f"/api/items/{item['id']}",
                     json={"code": "BMW", "name": "Renamed"})
    assert res.status_code == 200, res.text


# --- retiring, not deleting ---------------------------------------------------
def test_removing_an_item_retires_it(tenant):
    """An invoice already raised copied its details; a business that deletes a
    product and then cannot find it in a report has lost something."""
    item = add_item(tenant)
    assert tenant.delete(f"/api/items/{item['id']}").status_code == 200
    assert codes(tenant) == []
    assert "BMW" in codes(tenant, include_inactive="true")


def test_a_retired_code_can_be_brought_back(tenant):
    item = add_item(tenant)
    tenant.delete(f"/api/items/{item['id']}")
    res = tenant.put(f"/api/items/{item['id']}", json={"is_active": True})
    assert res.status_code == 200, res.text
    assert codes(tenant) == ["BMW"]


# --- the lookup behind the invoice line ---------------------------------------
def test_searching_matches_the_code(tenant):
    add_item(tenant)
    add_item(tenant, code="AUDI", name="Audi hire")
    assert codes(tenant, q="bm") == ["BMW"]


def test_searching_matches_the_name_too(tenant):
    add_item(tenant)
    add_item(tenant, code="AUDI", name="Audi hire")
    assert codes(tenant, q="audi") == ["AUDI"]


def test_searching_ignores_case(tenant):
    add_item(tenant)
    assert codes(tenant, q="BMW") == ["BMW"]
    assert codes(tenant, q="bmw") == ["BMW"]


def test_a_retired_item_is_not_offered_on_a_new_line(tenant):
    item = add_item(tenant)
    tenant.delete(f"/api/items/{item['id']}")
    assert codes(tenant, q="bmw") == []


def test_the_lookup_is_capped(tenant):
    """A business with thousands of products must not send all of them to
    fill a dropdown showing eight."""
    for i in range(12):
        add_item(tenant, code=f"SKU{i:03d}", name=f"Product {i}")
    assert len(codes(tenant, limit=5)) == 5


def test_an_absurd_limit_is_brought_back_down(tenant):
    add_item(tenant)
    res = tenant.get("/api/items?limit=100000")
    assert res.status_code == 200, res.text


# --- whose catalogue it is -----------------------------------------------------
def test_one_business_cannot_see_or_touch_another_s_items(tenant):
    mine = add_item(tenant)

    with TestClient(main.app) as other:
        email = f"other-{uuid.uuid4().hex[:8]}@example.com"
        other.post("/api/client/register", json={
            "email": email, "password": "Passw0rdTest", "company_name": "Other Ltd"})
        other.post("/api/client/login",
                   json={"email": email, "password": "Passw0rdTest"})

        assert other.get("/api/items").json()["items"] == []
        assert other.put(f"/api/items/{mine['id']}",
                         json={"name": "Hijacked"}).status_code == 404
        assert other.delete(f"/api/items/{mine['id']}").status_code == 404

        # And the same code is free for them to use, because it is theirs.
        assert other.post("/api/items", json={"code": "BMW"}).status_code == 200

    assert tenant.get("/api/items").json()["items"][0]["name"] == "BMW hire"


def test_a_stranger_cannot_read_the_catalogue(client):
    assert client.get("/api/items").status_code in (401, 403)
