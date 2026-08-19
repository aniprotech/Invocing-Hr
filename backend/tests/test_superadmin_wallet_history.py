"""Reading a tenant's wallet before topping it up.

Crediting an account without seeing why it is empty is how the same mistake
gets made twice, so the operator can read the ledger from the screen they top
up from. It is one tenant's financial history, so who may read it matters more
than what it says.
"""
import uuid

import pytest

import main


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


@pytest.fixture
def superadmin(client):
    main.rate_limiter._hits.clear()
    res = client.post("/api/superadmin/login", json={
        "identifier": "hello@keyroutes.co", "password": "TestSuper123",
    })
    assert res.status_code == 200, res.text
    return client


def a_tenant(client):
    """A business with its own wallet, made through the front door."""
    email = f"wallet-{uuid.uuid4().hex[:8]}@example.com"
    main.rate_limiter._hits.clear()
    res = client.post("/api/client/register", json={
        "email": email, "password": "Passw0rdTest", "company_name": "Wallet Ltd"})
    assert res.status_code == 200, res.text
    with main.SessionLocal() as db:
        row = db.query(main.models.DBClient).filter(
            main.models.DBClient.email == email).first()
        return {"id": row.id, "email": email}


def history(superadmin, client_id):
    res = superadmin.get(f"/api/superadmin/wallets/{client_id}/transactions")
    assert res.status_code == 200, res.text
    return res.json()


# --- what an operator sees ----------------------------------------------------

def test_a_new_wallet_reads_as_empty(client, superadmin):
    t = a_tenant(client)
    body = history(superadmin, t["id"])
    assert body["balance"] == 0.0
    assert body["transactions"] == []
    assert body["client"]["email"] == t["email"]


def test_a_top_up_appears_in_the_history(client, superadmin):
    t = a_tenant(client)
    superadmin.post(f"/api/superadmin/wallets/{t['id']}/adjust",
                    json={"amount": 25, "reason": "Bank transfer received"})

    body = history(superadmin, t["id"])
    assert body["balance"] == 25.0
    top = body["transactions"][0]
    assert top["direction"] == "credit"
    assert top["amount"] == 25.0
    assert top["description"] == "Bank transfer received"
    assert top["performed_by"] == "superadmin"


def test_the_running_balance_is_on_every_row(client, superadmin):
    """So a disputed balance can be traced without replaying the whole ledger."""
    t = a_tenant(client)
    for amount in (10, 15, -5):
        superadmin.post(f"/api/superadmin/wallets/{t['id']}/adjust",
                        json={"amount": amount, "reason": f"step {amount}"})

    rows = history(superadmin, t["id"])["transactions"]
    assert [r["balance_after"] for r in rows] == [20.0, 25.0, 10.0]


def test_newest_first(client, superadmin):
    t = a_tenant(client)
    superadmin.post(f"/api/superadmin/wallets/{t['id']}/adjust",
                    json={"amount": 5, "reason": "first"})
    superadmin.post(f"/api/superadmin/wallets/{t['id']}/adjust",
                    json={"amount": 5, "reason": "second"})
    rows = history(superadmin, t["id"])["transactions"]
    assert rows[0]["description"] == "second"


def test_an_unknown_client_is_not_found(superadmin):
    assert superadmin.get("/api/superadmin/wallets/999999/transactions").status_code == 404


# --- who may read it ----------------------------------------------------------

def test_a_tenant_cannot_read_its_own_through_this_door(client, tenant):
    """There is a tenant-facing statement for that. This one is the operator's,
    and it must not become a way in."""
    with main.SessionLocal() as db:
        row = db.query(main.models.DBClient).first()
        cid = row.id
    res = tenant.get(f"/api/superadmin/wallets/{cid}/transactions")
    assert res.status_code in (401, 403)


def test_a_tenant_cannot_read_another_business(client, tenant):
    other = a_tenant(client)
    main.rate_limiter._hits.clear()
    res = client.get(f"/api/superadmin/wallets/{other['id']}/transactions")
    assert res.status_code in (401, 403)


def test_a_stranger_is_refused(client):
    assert client.get("/api/superadmin/wallets/1/transactions").status_code in (401, 403)
